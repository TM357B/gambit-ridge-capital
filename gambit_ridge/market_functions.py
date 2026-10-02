"""Fonctions de marché « façon Bloomberg » sur données gratuites.

GP   : graphique de prix d'un ticker Yahoo (moyennes mobiles 50 / 200 j)
DES  : fiche d'un actif (performances, risque, bêta, position du fonds)
FXC  : matrice des taux croisés + variation du jour (carte de chaleur)
WCRS : classement des devises contre dollar sur plusieurs horizons
ECST : statistiques économiques US (FRED, sans clé)

Les fonctions qui exigent des consensus d'économistes payants (ECSU,
ECFC, FXFC) ne sont volontairement PAS simulées.
"""

from __future__ import annotations

import re
from datetime import date

import numpy as np

from .data.yahoo import CRYPTO_UNIVERSE, ETF_UNIVERSE, YahooConnector, asset_class_of, complete_cutoff

SYMBOL_RE = re.compile(r"^[A-Z0-9.^=\-]{1,15}$")

# devise -> (symbole Yahoo, True si le cours est « USD par unité », False si « unités par USD »)
FX = {
    "EUR": ("EURUSD=X", True), "JPY": ("JPY=X", False), "GBP": ("GBPUSD=X", True),
    "CHF": ("CHF=X", False), "CAD": ("CAD=X", False), "AUD": ("AUDUSD=X", True),
    "NZD": ("NZDUSD=X", True), "SEK": ("SEK=X", False), "NOK": ("NOK=X", False),
    "CNY": ("CNY=X", False), "MXN": ("MXN=X", False), "ZAR": ("ZAR=X", False),
    "BRL": ("BRL=X", False), "INR": ("INR=X", False), "KRW": ("KRW=X", False),
    "SGD": ("SGD=X", False),
}
FX_NAMES = {
    "USD": "Dollar US", "EUR": "Euro", "JPY": "Yen", "GBP": "Livre sterling", "CHF": "Franc suisse",
    "CAD": "Dollar canadien", "AUD": "Dollar australien", "NZD": "Dollar néo-zélandais",
    "SEK": "Couronne suédoise", "NOK": "Couronne norvégienne", "CNY": "Yuan", "MXN": "Peso mexicain",
    "ZAR": "Rand", "BRL": "Real brésilien", "INR": "Roupie indienne", "KRW": "Won", "SGD": "Dollar de Singapour",
}
FXC_MAJORS = ["USD", "EUR", "JPY", "GBP", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK"]

# ECST : (id FRED, libellé, transformation, unité)
ECST = {
    "Croissance": [
        ("A191RL1Q225SBEA", "PIB réel (t/t annualisé)", "level", "%"),
        ("INDPRO", "Production industrielle (g.a.)", "yoy", "%"),
        ("RSAFS", "Ventes au détail (g.a.)", "yoy", "%"),
        ("HOUST", "Mises en chantier (milliers, rythme annuel)", "level", ""),
        ("UMCSENT", "Confiance des ménages (Michigan)", "level", ""),
    ],
    "Emploi": [
        ("UNRATE", "Taux de chômage", "level", "%"),
        ("PAYEMS", "Créations d'emplois non agricoles (milliers)", "diff", ""),
        ("ICSA", "Inscriptions hebdo au chômage", "level", ""),
    ],
    "Prix": [
        ("CPIAUCSL", "Inflation CPI (g.a.)", "yoy", "%"),
        ("CPILFESL", "CPI sous-jacent (g.a.)", "yoy", "%"),
        ("PCEPILFE", "PCE sous-jacent (g.a.) — cible Fed", "yoy", "%"),
    ],
    "Taux & conditions financières": [
        ("DFF", "Fed funds effectif", "level", "%"),
        ("DGS2", "Treasury 2 ans", "level", "%"),
        ("DGS10", "Treasury 10 ans", "level", "%"),
        ("T10Y2Y", "Pente 10 ans - 2 ans", "level", "pt"),
        ("BAMLH0A0HYM2", "Spread high yield", "level", "%"),
        ("VIXCLS", "VIX", "level", ""),
        ("M2SL", "Masse monétaire M2 (g.a.)", "yoy", "%"),
    ],
}


def _check(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not SYMBOL_RE.match(s):
        raise ValueError(f"ticker invalide : {symbol!r}")
    return s


def _series(symbol: str) -> tuple[list[str], np.ndarray]:
    data = YahooConnector().fetch(symbol, refresh=True)
    cut = complete_cutoff(symbol)
    ds = sorted(d for d in data if d <= cut)  # séances closes uniquement
    if len(ds) < 30:
        raise ValueError(f"pas assez d'historique pour {symbol}")
    return ds, np.array([data[d] for d in ds], dtype=float)


def _names() -> dict[str, str]:
    return {s: n for m in ETF_UNIVERSE.values() for s, n in m.items()} | CRYPTO_UNIVERSE


# --------------------------------------------------------------------- GP

def gp(symbol: str) -> dict:
    s = _check(symbol)
    ds, px = _series(s)

    def sma(n):
        out = np.full(len(px), np.nan)
        if len(px) >= n:
            c = np.cumsum(np.insert(px, 0, 0.0))
            out[n - 1:] = (c[n:] - c[:-n]) / n
        return out

    m50, m200 = sma(50), sma(200)
    clean = lambda a: [None if not np.isfinite(x) else round(float(x), 6) for x in a]
    return {"symbol": s, "name": _names().get(s, s), "dates": ds, "close": clean(px), "sma50": clean(m50), "sma200": clean(m200)}


# --------------------------------------------------------------------- DES

def des(symbol: str) -> dict:
    s = _check(symbol)
    ds, px = _series(s)
    r = np.diff(np.log(px))
    ppy = 365 if s.endswith("-USD") else 252
    last = float(px[-1])
    yr = px[-min(len(px), ppy + 1):]

    def ret(n):
        return float(px[-1] / px[-1 - n] - 1) if len(px) > n else None

    y0 = next((i for i, d in enumerate(ds) if d[:4] == ds[-1][:4]), 0)
    peak = np.maximum.accumulate(px)
    out = {
        "symbol": s, "name": _names().get(s, s), "asset_class": asset_class_of(s),
        "date": ds[-1], "last": last, "history_start": ds[0], "n_obs": len(px),
        "returns": {"1 j": ret(1), "1 sem.": ret(5), "1 mois": ret(21), "3 mois": ret(63),
                    "YTD": float(px[-1] / px[y0 - 1] - 1) if y0 > 0 else None, "1 an": ret(ppy), "3 ans": ret(3 * ppy)},
        "high_52w": float(yr.max()), "low_52w": float(yr.min()),
        "vol_1m": float(np.std(r[-21:], ddof=1) * np.sqrt(ppy)),
        "vol_1y": float(np.std(r[-ppy:], ddof=1) * np.sqrt(ppy)),
        "max_dd_1y": float((yr / np.maximum.accumulate(yr) - 1).min()),
        "drawdown_now": float(px[-1] / peak[-1] - 1),
        "max_dd_all": float((px / peak - 1).min()),
    }
    # bêta et corrélation 1 an contre le S&P 500
    if s != "SPY":
        try:
            sds, spx = _series("SPY")
            common = sorted(set(ds) & set(sds))[-(ppy + 1):]
            idx_a = {d: i for i, d in enumerate(ds)}
            idx_b = {d: i for i, d in enumerate(sds)}
            ra = np.diff(np.log([px[idx_a[d]] for d in common]))
            rb = np.diff(np.log([spx[idx_b[d]] for d in common]))
            if len(ra) > 60:
                out["beta_spy"] = float(np.cov(ra, rb)[0, 1] / np.var(rb, ddof=1))
                out["corr_spy"] = float(np.corrcoef(ra, rb)[0, 1])
        except Exception:
            pass
    # position et signal dans le portefeuille papier
    try:
        from .paper import _load_journal

        j = _load_journal()
        pos = j.get("positions", {}).get(s)
        det = j.get("last_detail", {}).get(s)
        out["fund"] = {"weight": pos["weight"] if pos else 0.0, "signal": det.get("signal") if det else None,
                       "in_universe": det is not None}
    except Exception:
        pass
    return out


# --------------------------------------------------------------------- FX

def _fx_usd_per_unit() -> tuple[list[str], dict[str, np.ndarray]]:
    """Valeur en USD d'une unité de chaque devise, alignée sur les dates communes."""
    conn = YahooConnector()
    raw = {}
    for ccy, (sym, usd_per) in FX.items():
        data = conn.fetch(sym, refresh=True)
        raw[ccy] = {d: (v if usd_per else 1.0 / v) for d, v in data.items() if d <= complete_cutoff(sym) and v > 0}
    common = sorted(set.intersection(*(set(v) for v in raw.values())))[-800:]
    series = {ccy: np.array([raw[ccy][d] for d in common]) for ccy in raw}
    series["USD"] = np.ones(len(common))
    return common, series


def fxc(currencies: list[str] | None = None) -> dict:
    ccys = currencies or FXC_MAJORS
    dates, usd = _fx_usd_per_unit()
    matrix, change = {}, {}
    for r in ccys:
        matrix[r], change[r] = {}, {}
        for c in ccys:
            if r == c:
                continue
            cross = usd[r] / usd[c]  # unités de c pour 1 unité de r
            matrix[r][c] = float(cross[-1])
            change[r][c] = float(cross[-1] / cross[-2] - 1)
    return {"date": dates[-1], "currencies": ccys, "names": {c: FX_NAMES[c] for c in ccys}, "matrix": matrix, "change_1d": change}


def wcrs() -> dict:
    dates, usd = _fx_usd_per_unit()
    horizons = {"1 j": 1, "1 sem.": 5, "1 mois": 21, "3 mois": 63, "1 an": 252}
    y0 = next((i for i, d in enumerate(dates) if d[:4] == dates[-1][:4]), 0)
    rows = []
    for ccy, s in usd.items():
        if ccy == "USD":
            continue
        row = {"ccy": ccy, "name": FX_NAMES[ccy], "spot_usd": float(s[-1])}
        for k, n in horizons.items():
            row[k] = float(s[-1] / s[-1 - n] - 1) if len(s) > n else None
        row["YTD"] = float(s[-1] / s[y0 - 1] - 1) if y0 > 0 else None
        row["vol_3m"] = float(np.std(np.diff(np.log(s[-64:])), ddof=1) * np.sqrt(252))
        rows.append(row)
    return {"date": dates[-1], "base": "USD", "horizons": list(horizons) + ["YTD"], "rows": rows}


# --------------------------------------------------------------------- ECST

def ecst() -> dict:
    from .data.fred import FredConnector

    conn = FredConnector()
    sections = []
    for title, items in ECST.items():
        rows = []
        for sid, label, tf, unit in items:
            try:
                ds, vals = conn.fetch_series(sid)
            except Exception:
                continue
            # séries quotidiennes / hebdo : une observation par mois (fin de mois) pour l'historique
            if sid in ("DFF", "DGS2", "DGS10", "T10Y2Y", "BAMLH0A0HYM2", "VIXCLS", "ICSA"):
                by_month: dict[str, tuple[str, float]] = {}
                for d, v in zip(ds, vals):
                    by_month[d[:7]] = (d, float(v))
                ds = [v[0] for v in by_month.values()]
                vals = np.array([v[1] for v in by_month.values()])
                # dernier point = dernière observation réelle
            if tf == "yoy":
                step = 12
                if len(vals) <= step:
                    continue
                vals = (vals[step:] / vals[:-step] - 1.0) * 100.0
                ds = ds[step:]
            elif tf == "diff":
                vals = np.diff(vals)
                ds = ds[1:]
            hist = [round(float(v), 2) for v in vals[-24:]]
            rows.append({
                "id": sid, "label": label, "unit": unit,
                "last": hist[-1], "prev": hist[-2] if len(hist) > 1 else None,
                "date": ds[-1], "history": hist, "history_dates": ds[-24:],
            })
        sections.append({"title": title, "rows": rows})
    return {"sections": sections, "source": "FRED (Federal Reserve Bank of St. Louis)"}


# --------------------------------------------------------------------- WEI

WEI = {
    "Amériques": {"^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones", "^RUT": "Russell 2000",
                  "^GSPTSE": "Canada S&P/TSX", "^BVSP": "Brésil Bovespa", "^MXX": "Mexique IPC"},
    "Europe": {"^STOXX50E": "Euro Stoxx 50", "^GDAXI": "Allemagne DAX", "^FCHI": "France CAC 40",
               "^FTSE": "Royaume-Uni FTSE 100", "^SSMI": "Suisse SMI", "^IBEX": "Espagne IBEX 35", "FTSEMIB.MI": "Italie FTSE MIB"},
    "Asie-Pacifique": {"^N225": "Japon Nikkei 225", "^HSI": "Hong Kong Hang Seng", "000001.SS": "Chine Shanghai",
                       "^KS11": "Corée Kospi", "^AXJO": "Australie ASX 200", "^BSESN": "Inde Sensex", "^TWII": "Taïwan TAIEX"},
}


def wei() -> dict:
    """World Equity Indices : niveau et performances des grands indices mondiaux."""
    from concurrent.futures import ThreadPoolExecutor

    conn = YahooConnector()

    def one(sym):
        try:
            d = conn.fetch(sym, refresh=True)
        except Exception:
            return sym, None
        ds = sorted(x for x in d if x <= complete_cutoff(sym))
        if len(ds) < 260:
            return sym, None
        px = [d[x] for x in ds]
        y0 = next((i for i, x in enumerate(ds) if x[:4] == ds[-1][:4]), 0)
        return sym, {"symbol": sym, "date": ds[-1], "last": px[-1], "chg_1d": px[-1] / px[-2] - 1, "chg_1w": px[-1] / px[-6] - 1,
                     "chg_1m": px[-1] / px[-22] - 1, "chg_ytd": px[-1] / px[y0 - 1] - 1 if y0 > 0 else None, "chg_1y": px[-1] / px[-253] - 1}

    syms = [s for g in WEI.values() for s in g]
    with ThreadPoolExecutor(max_workers=8) as pool:
        res = dict(pool.map(one, syms))
    return {"regions": [{"region": r, "rows": [{**res[s], "name": n} for s, n in g.items() if res.get(s)]} for r, g in WEI.items()]}


# --------------------------------------------------------------------- GC

GC_SERIES = [("1 M", "DGS1MO"), ("3 M", "DGS3MO"), ("6 M", "DGS6MO"), ("1 A", "DGS1"), ("2 A", "DGS2"), ("3 A", "DGS3"),
             ("5 A", "DGS5"), ("7 A", "DGS7"), ("10 A", "DGS10"), ("20 A", "DGS20"), ("30 A", "DGS30")]


def gc() -> dict:
    """Courbe des taux du Trésor américain (FRED) : aujourd'hui, il y a 1 mois, il y a 1 an."""
    from datetime import timedelta

    from .data.fred import FredConnector

    conn = FredConnector()
    series = {}
    for label, sid in GC_SERIES:
        ds, vals = conn.fetch_series(sid)
        series[label] = dict(zip(ds, (float(v) for v in vals)))
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    last = common[-1]

    def at(days_back):
        target = (date.fromisoformat(last) - timedelta(days=days_back)).isoformat()
        d = max(x for x in common if x <= target)
        return d, [series[lab][d] for lab, _ in GC_SERIES]

    d0, now = last, [series[lab][last] for lab, _ in GC_SERIES]
    d1, m1 = at(30)
    d2, y1 = at(365)
    s = dict(zip([lab for lab, _ in GC_SERIES], now))
    return {"maturities": [lab for lab, _ in GC_SERIES], "curves": [
        {"label": f"Aujourd'hui ({d0})", "date": d0, "yields": now},
        {"label": f"Il y a 1 mois ({d1})", "date": d1, "yields": m1},
        {"label": f"Il y a 1 an ({d2})", "date": d2, "yields": y1}],
        "spreads": {"2 A - 10 A": round((s["10 A"] - s["2 A"]) * 100), "3 M - 10 A": round((s["10 A"] - s["3 M"]) * 100),
                    "5 A - 30 A": round((s["30 A"] - s["5 A"]) * 100)},
        "source": "FRED — rendements constants du Trésor américain"}
