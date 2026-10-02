"""Connecteur Binance public (crypto, 24/7) — gratuit, sans clé.

API klines publique : historique journalier ou intraday, pas de clé
requise pour les données de marché. Cache disque par symbole.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np

from ..core.agent import MarketData

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"

BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "AVAX": "AVAXUSDT",
    "DOGE": "DOGEUSDT",
    "LINK": "LINKUSDT",
    "DOT": "DOTUSDT",
    "POL": "POLUSDT",       # ex-MATIC (renommé sept. 2024)
    "LTC": "LTCUSDT",
    "ATOM": "ATOMUSDT",
    "UNI": "UNIUSDT",
    "NEAR": "NEARUSDT",
    "APT": "APTUSDT",
    "ARB": "ARBUSDT",
    "OP": "OPUSDT",
    "SUI": "SUIUSDT",
    "TIA": "TIAUSDT",
    "INJ": "INJUSDT",
    "RENDER": "RENDERUSDT", # ex-RNDR (renommé juil. 2024)
    "FIL": "FILUSDT",
    "ETC": "ETCUSDT",
    "AAVE": "AAVEUSDT",
}


class BinanceConnector:
    """Klines Binance : OHLCV journalier, cache disque, sans clé."""

    BASE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR

    def _cache_path(self, symbol: str, interval: str, limit: int) -> Path:
        return self.cache_dir / f"binance_{symbol}_{interval}_{limit}.json"

    def fetch_klines(
        self,
        ticker: str,
        interval: str = "1d",
        limit: int = 1000,
    ) -> tuple[list[int], np.ndarray, np.ndarray]:
        """Retourne (timestamps_ms, closes, volumes) du plus ancien au récent."""
        symbol = BINANCE_SYMBOLS.get(ticker, ticker)
        path = self._cache_path(symbol, interval, limit)
        cached = None
        if path.exists():
            try:
                cached = json.loads(path.read_text())
            except Exception:
                path.unlink(missing_ok=True)
        # cache valable 20 h : sans expiration, les prix restaient figés à la
        # date du premier téléchargement
        if cached is not None and time.time() - path.stat().st_mtime < 20 * 3600:
            return cached["dates"], np.array(cached["closes"], dtype=float), np.array(cached["volumes"], dtype=float)

        url = f"{self.BASE_URL}?symbol={symbol}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "gambit-ridge/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                rows = json.loads(resp.read().decode())
        except Exception:
            if cached is not None:  # hors ligne : on garde le cache périmé
                return cached["dates"], np.array(cached["closes"], dtype=float), np.array(cached["volumes"], dtype=float)
            raise

        dates = [int(r[0]) for r in rows]
        closes = [float(r[4]) for r in rows]
        volumes = [float(r[5]) for r in rows]
        self.cache_dir.mkdir(exist_ok=True)
        path.write_text(json.dumps({"dates": dates, "closes": closes, "volumes": volumes}))
        time.sleep(0.05)
        return dates, np.array(closes, dtype=float), np.array(volumes, dtype=float)

    def fetch(self, ticker: str, periods: int = 90) -> MarketData:
        _, closes, volumes = self.fetch_klines(ticker, "1d", min(max(periods, 30), 1000))
        return MarketData(ticker=ticker, prices=closes.tolist(), volumes=volumes.tolist())


def load_binance_universe(min_common: int = 900) -> dict[str, np.ndarray]:
    """Univers crypto aligné (~24 actifs, ~1000 bars journaliers).

    Utilise le cache disque du connecteur ; les symboles trop courts sont
    écartés, les séries alignées sur l'intersection des timestamps.
    """
    conn = BinanceConnector()
    raw: dict[str, tuple[list[int], np.ndarray]] = {}
    for symbol in BINANCE_SYMBOLS.values():
        try:
            dates, closes, _ = conn.fetch_klines(symbol, "1d", 1000)
            if len(closes) >= min_common:
                raw[symbol] = (dates, closes)
                continue
        except Exception:
            continue
    if not raw:
        raise RuntimeError("aucun symbole binance chargé")
    # Symboles dont la fenêtre ne recouvre pas la majorité (caches obsolètes,
    # jetons délistés/renommés type MATIC→POL) : exclus automatiquement,
    # sinon l'intersection tombe à quelques centaines de points.
    ref_dates = max(raw.values(), key=lambda x: len(x[0]))[0]
    ref_set = set(ref_dates)
    usable = {
        sym: (dates, closes)
        for sym, (dates, closes) in raw.items()
        if len(ref_set & set(dates)) >= int(min_common * 0.9)
    }
    if len(usable) < 5:
        raise RuntimeError("univers binance trop réduit après nettoyage")
    common = set.intersection(*(set(d) for d, _ in usable.values()))
    common = sorted(common)
    if len(common) < min_common:
        raise RuntimeError(f"intersection binance trop courte: {len(common)} points")
    aligned: dict[str, np.ndarray] = {}
    for symbol, (dates, closes) in usable.items():
        idx = {d: i for i, d in enumerate(dates)}
        sel = sorted(idx[d] for d in common)
        aligned[symbol] = np.array(closes[sel], dtype=float)
    return aligned
