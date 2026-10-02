"""Connecteur Yahoo Finance (chart API publique, sans clé) + univers ETF.

Pourquoi des ETF : ce sont des instruments réellement négociables
(contrairement aux niveaux spot FRED — gaz Henry Hub, Brent spot — qu'on
ne peut pas acheter tels quels). Les prix « adjclose » incluent dividendes
et coupons : le rendement d'un ETF obligataire est donc complet.

Cache disque par symbole (data_cache/yahoo_<SYM>.json), rafraîchi au plus
une fois par jour.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"

# Univers multi-actifs : 20 ETF liquides, historique commun depuis 2007-04.
# classe d'actifs -> {symbole: libellé}
ETF_UNIVERSE: dict[str, dict[str, str]] = {
    "Actions": {
        "SPY": "S&P 500",
        "QQQ": "Nasdaq 100",
        "IWM": "Russell 2000",
        "EFA": "Actions développées hors US",
        "EEM": "Actions émergentes",
        "EWJ": "Actions Japon",
        "VNQ": "Immobilier coté US",
    },
    "Obligations": {
        "TLT": "Treasuries 20+ ans",
        "IEF": "Treasuries 7-10 ans",
        "TIP": "Obligations indexées inflation",
        "LQD": "Crédit investment grade",
        "HYG": "Crédit high yield",
    },
    "Matières premières": {
        "GLD": "Or",
        "SLV": "Argent",
        "DBC": "Panier matières premières",
        "USO": "Pétrole WTI",
        "DBA": "Agriculture",
    },
    "Devises": {
        "UUP": "Dollar index long",
        "FXE": "Euro",
        "FXY": "Yen",
    },
}

CRYPTO_UNIVERSE: dict[str, str] = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ether",
    "XRP-USD": "XRP",
    "LTC-USD": "Litecoin",
    "ADA-USD": "Cardano",
    "BNB-USD": "BNB",
    "DOGE-USD": "Dogecoin",
}


def asset_class_of(symbol: str) -> str:
    for cls, members in ETF_UNIVERSE.items():
        if symbol in members:
            return cls
    if symbol in CRYPTO_UNIVERSE:
        return "Crypto"
    return "Autre"


def all_etf_symbols() -> list[str]:
    return [s for members in ETF_UNIVERSE.values() for s in members]


# Fuseau et heure de clôture par type de symbole : une barre datée D n'est
# « complète » qu'une fois la séance D close sur sa place de cotation.
_CLOSE_RULES = [
    (lambda s: s.endswith("-USD"), "UTC", (23, 59)),          # crypto : bougie UTC
    (lambda s: s.endswith("=X"), "Europe/London", (23, 59)),  # devises : 24 h, date Londres
    (lambda s: s.endswith("=F"), "America/New_York", (17, 30)),
    (lambda s: s.endswith(".PA") or s in ("^FCHI",), "Europe/Paris", (17, 45)),
    (lambda s: s in ("^GDAXI", "^STOXX50E"), "Europe/Berlin", (17, 45)),
    (lambda s: s in ("^FTSE",), "Europe/London", (16, 45)),
    (lambda s: s in ("^SSMI",), "Europe/Zurich", (17, 45)),
    (lambda s: s in ("^IBEX",) or s.endswith(".MC"), "Europe/Madrid", (17, 45)),
    (lambda s: s in ("FTSEMIB.MI",) or s.endswith(".MI"), "Europe/Rome", (17, 45)),
    (lambda s: s.endswith(".T") or s in ("^N225",), "Asia/Tokyo", (15, 30)),
    (lambda s: s in ("^HSI",) or s.endswith(".HK"), "Asia/Hong_Kong", (16, 15)),
    (lambda s: s.endswith(".SS") or s.endswith(".SZ"), "Asia/Shanghai", (15, 10)),
    (lambda s: s in ("^KS11",), "Asia/Seoul", (15, 40)),
    (lambda s: s in ("^AXJO",) or s.endswith(".AX"), "Australia/Sydney", (16, 15)),
    (lambda s: s in ("^BSESN", "^NSEI"), "Asia/Kolkata", (15, 40)),
    (lambda s: s in ("^TWII",), "Asia/Taipei", (13, 40)),
    (lambda s: s in ("^GSPTSE",) or s.endswith(".TO"), "America/Toronto", (16, 30)),
    (lambda s: s in ("^BVSP",) or s.endswith(".SA"), "America/Sao_Paulo", (17, 30)),
    (lambda s: s in ("^MXX",), "America/Mexico_City", (15, 30)),
]


def complete_cutoff(symbol: str, now: datetime | None = None) -> str:
    """Dernière date ISO dont la séance est close pour ce symbole."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    tz, (hh, mm) = "America/New_York", (16, 30)
    for rule, z, close in _CLOSE_RULES:
        if rule(symbol):
            tz, (hh, mm) = z, close
            break
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
    day = local.date()
    if (local.hour, local.minute) < (hh, mm):
        day -= timedelta(days=1)
    if tz != "UTC":  # marchés fermés le week-end (devises incluses)
        while day.weekday() >= 5:
            day -= timedelta(days=1)
    return day.isoformat()


class YahooConnector:
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2={now}&interval=1d"

    def __init__(self, cache_dir: Path | None = None, max_age_hours: float = 20.0) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.max_age = max_age_hours * 3600

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"yahoo_{symbol}.json"

    def _download(self, symbol: str) -> dict[str, float]:
        url = self.URL.format(sym=symbol, now=int(time.time()) + 86400)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read())
                res = data["chart"]["result"][0]
                adj = res["indicators"]["adjclose"][0]["adjclose"]
                # date de séance dans le fuseau de la place (sinon les devises,
                # horodatées à minuit Londres, tombent la veille en UTC)
                offset = int(res.get("meta", {}).get("gmtoffset") or 0)
                out: dict[str, float] = {}
                for ts, p in zip(res["timestamp"], adj):
                    if p is None or not np.isfinite(p) or p <= 0:
                        continue
                    d = datetime.fromtimestamp(ts + offset, tz=timezone.utc).date().isoformat()
                    out[d] = float(p)
                return out
            except Exception as exc:  # réseau, quota, format
                last_err = exc
                time.sleep(1 + attempt)
        raise RuntimeError(f"Yahoo {symbol}: {last_err}")

    def fetch(self, symbol: str, refresh: bool = False) -> dict[str, float]:
        """date ISO -> close ajusté. Utilise le cache s'il est récent."""
        path = self._cache_path(symbol)
        cached = None
        if path.exists():
            try:
                cached = json.loads(path.read_text())
            except Exception:
                cached = None
        fresh = cached is not None and time.time() - path.stat().st_mtime < self.max_age
        if cached is not None and (fresh or not refresh):
            return cached
        try:
            data = self._download(symbol)
        except Exception:
            if cached is not None:
                return cached  # hors ligne : on garde le cache
            raise
        self.cache_dir.mkdir(exist_ok=True)
        path.write_text(json.dumps(data))
        return data


def load_aligned(
    symbols: list[str], *, refresh: bool = False, connector: YahooConnector | None = None
) -> tuple[list[str], dict[str, np.ndarray]]:
    """Séries alignées sur les dates communes à tous les symboles."""
    conn = connector or YahooConnector()
    raw = {s: conn.fetch(s, refresh=refresh) for s in symbols}
    common = set.intersection(*(set(v) for v in raw.values()))
    dates = sorted(common)
    prices = {s: np.array([raw[s][d] for d in dates], dtype=float) for s in symbols}
    return dates, prices


def load_etf_universe(refresh: bool = False) -> tuple[list[str], dict[str, np.ndarray]]:
    return load_aligned(all_etf_symbols(), refresh=refresh)


def load_crypto_universe(refresh: bool = False) -> tuple[list[str], dict[str, np.ndarray]]:
    return load_aligned(list(CRYPTO_UNIVERSE), refresh=refresh)


def market_snapshot() -> list[dict]:
    """Dernières clôtures + variations, lues UNIQUEMENT depuis le cache disque
    (aucun appel réseau : le paper trading rafraîchit le cache chaque jour)."""
    from datetime import date as _date

    conn = YahooConnector()
    names = {s: n for m in ETF_UNIVERSE.values() for s, n in m.items()} | CRYPTO_UNIVERSE
    out = []
    for sym in all_etf_symbols() + list(CRYPTO_UNIVERSE):
        path = conn._cache_path(sym)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        cut = complete_cutoff(sym)
        ds = sorted(d for d in data if d <= cut)
        if len(ds) < 260:
            continue
        px = [data[d] for d in ds]
        year_start = next((i for i, d in enumerate(ds) if d[:4] == ds[-1][:4]), 0)
        base_ytd = px[year_start - 1] if year_start > 0 else px[0]
        out.append({
            "symbol": sym,
            "name": names.get(sym, sym),
            "asset_class": asset_class_of(sym),
            "date": ds[-1],
            "last": px[-1],
            "chg_1d": px[-1] / px[-2] - 1.0,
            "chg_1m": px[-1] / px[-22] - 1.0,
            "chg_ytd": px[-1] / base_ytd - 1.0,
            "chg_1y": px[-1] / px[-253] - 1.0,
        })
    return out
