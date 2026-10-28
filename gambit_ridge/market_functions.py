"""Fonctions de marché « façon Bloomberg » sur données gratuites.

GP   : graphique de prix d'un ticker Yahoo (moyennes mobiles 50 / 200 j)
DES  : fiche d'un actif (performances, risque, bêta, position du fonds)
FXC  : matrice des taux croisés + variation du jour (carte de chaleur)
WCRS : classement des devises contre dollar sur plusieurs horizons
ECST : statistiques économiques US (FRED, sans clé)
OVDV : surface de volatilité implicite d'un sous-jacent à options cotées

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


# --------------------------------------------------------------------- OVDV

def ovdv(symbol: str) -> dict:
    """Surface de volatilité implicite (options cotées US, Yahoo) : smiles, structure ATM, grille.

    Outil d'analyse : ne pilote pas le portefeuille. Calcul dans options/vol_surface.py.
    """
    from .options.vol_surface import ovdv as surface

    return surface(_check(symbol))


# --------------------------------------------------------------------- MC / OVML

def mc(symbol: str, params: dict | None = None) -> dict:
    """Laboratoire Monte-Carlo paramétrable (options/monte_carlo.py)."""
    from .options.monte_carlo import mc as lancer

    return lancer(_check(symbol), params)


def ovml(symbol: str, params: dict | None = None) -> dict:
    """Pricer d'option façon OVML : prix et grecques Black-Scholes, vol lue sur la surface OVDV.

    Paramètres : type (call/put), strike (% du spot), jours (calendaires), vol (« surface » ou %),
    quantite (contrats de 100).
    """
    import math

    from .options.black_scholes import grecques
    from .options.monte_carlo import taux_sans_risque
    from .options.vol_surface import ovdv as surface

    s = _check(symbol)
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    typ = p.get("type", "call")
    if typ not in ("call", "put"):
        raise ValueError("type : call ou put")
    try:
        k_pct = float(p.get("strike", 100)) / 100
        jours = float(p.get("jours", 91))
        qte = float(p.get("quantite", 1))
    except ValueError:
        raise ValueError("strike, jours et quantité doivent être des nombres") from None
    if not (0.3 <= k_pct <= 3 and 1 <= jours <= 1100):
        raise ValueError("strike entre 30 et 300 % du spot, maturité entre 1 et 1 100 jours")

    surf, note = None, ""
    try:
        surf = surface(s)
        spot, taux = surf["spot"], surf["rate"]
    except Exception as exc:  # sous-jacent sans options cotées
        note = f"pas de surface de vol ({exc})"
        ds, px = _series(s)
        spot, taux = float(px[-1]), taux_sans_risque()

    div = 0.0
    source = p.get("vol", "surface")
    if source == "surface":
        if surf is None:
            raise ValueError(f"{s} : {note} — indique une vol (ex. vol=20)")
        J = np.array(surf["grid"]["days"], dtype=float)
        V = np.array([[np.nan if v is None else v for v in r] for r in surf["grid"]["vols"]], dtype=float)
        Km = np.array(surf["moneyness"], dtype=float)
        i = int(np.argmin(np.abs(J - min(max(jours, J[0]), J[-1]))))
        ok = np.isfinite(V[i])
        if not ok.any():
            raise ValueError("surface vide à cette maturité")
        vol = float(np.interp(k_pct, Km[ok], V[i, ok]))
        if not J[0] <= jours <= J[-1]:
            note = f"maturité hors des échéances cotées : vol lue à {J[i]:.0f} jours"
        proche = min(surf["expiries"], key=lambda e: abs(e["days"] - jours))
        div = proche["div"] if proche["days"] >= 30 else 0.0
    else:
        try:
            vol = float(source) / 100
        except ValueError:
            raise ValueError("vol : « surface » ou un nombre en %") from None
        if not 0.01 <= vol <= 3:
            raise ValueError("vol entre 1 et 300 %")

    T = jours / 365
    K = k_pct * spot
    g = grecques(spot, K, T, taux, vol, typ, div)
    mult = 100 * qte
    xs = np.linspace(0.7 * spot, 1.3 * spot, 61)
    aujourd_hui = [grecques(x, K, T, taux, vol, typ, div)["prix"] for x in xs]
    echeance = np.maximum(xs - K, 0) if typ == "call" else np.maximum(K - xs, 0)
    return {"symbol": s, "spot": spot, "type": typ, "strike": K, "strike_pct": k_pct, "jours": jours, "vol": vol,
            "vol_source": source, "taux": taux, "dividende": div, "forward": spot * math.exp((taux - div) * T),
            "quantite": qte, "multiplicateur": mult, "note": note,
            "grecques": g, "position": {k: v * mult for k, v in g.items()},
            "profil": {"spot": xs.round(4).tolist(), "aujourdhui": [round(v - g["prix"], 4) for v in aujourd_hui],
                       "echeance": [round(float(v) - g["prix"], 4) for v in echeance]}}


# --------------------------------------------------------------------- GC3D

def gc3d(years: str | float = 5) -> dict:
    """Courbe des taux du Trésor américain dans le temps (surface date × maturité), FRED."""
    from .data.fred import FredConnector

    try:
        ans = float(years or 5)
    except ValueError:
        raise ValueError("période en années invalide") from None
    ans = min(max(ans, 1), 25)
    conn = FredConnector()
    series = {}
    for label, sid in GC_SERIES:
        ds, vals = conn.fetch_series(sid)
        series[label] = dict(zip(ds, (float(v) for v in vals)))
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    debut = (date.fromisoformat(common[-1]).replace(year=date.fromisoformat(common[-1]).year - int(ans))).isoformat()
    jours = [d for d in common if d >= debut]
    labels = [lab for lab, _ in GC_SERIES]
    # ACP des variations quotidiennes (Dixon et al., ch. 6 § 5) : niveau, pente, courbure
    from .quant.timeseries import acp

    # le 1 mois est exclu : bruit propre aux T-bills (plafond de la dette, fins de mois) qui capterait un facteur
    lab_acp = labels[1:]
    Y = np.array([[series[lab][d] for lab in lab_acp] for d in jours])
    a = acp(np.diff(Y, axis=0) * 100)  # en points de base
    scores = np.vstack([np.zeros((1, 3)), np.cumsum(a["scores"][:, :3], axis=0)])
    pas = max(1, len(jours) // 160)  # ~160 dates : surface fluide et légère
    jours = jours[::-1][::pas][::-1]
    if jours[-1] != common[-1]:
        jours.append(common[-1])
    z = [[series[lab][d] for lab in labels] for d in jours]
    arr = np.array(z)
    pos = {d: i for i, d in enumerate(d for d in common if d >= debut)}
    return {"dates": jours, "maturities": labels, "yields": z, "min": float(arr.min()), "max": float(arr.max()),
            "last": z[-1], "first": z[0], "source": "FRED — rendements constants du Trésor américain",
            "acp": {"maturites": lab_acp, "part": a["part"][:5].tolist(), "vecteurs": a["vecteurs"][:, :3].T.tolist(),
                    "vol_pb_jour": np.sqrt(a["valeurs"][:3]).tolist(),
                    "scores": [[float(scores[pos[d], k]) for d in jours] for k in range(3)]}}


# --------------------------------------------------------------------- BUDG

def budg() -> dict:
    """Budget fédéral américain : recettes, dépenses, solde (exercices budgétaires), FRED."""
    from .data.fred import FredConnector

    conn = FredConnector()

    def annuel(sid):
        ds, vals = conn.fetch_series(sid)
        return {d[:4]: float(v) for d, v in zip(ds, vals)}

    recettes, depenses, solde = annuel("FYFR"), annuel("FYONET"), annuel("FYFSD")
    pib = annuel("FYFSGDA188S")
    ds, rec = conn.fetch_series("USREC")
    recession = sorted({d[:4] for d, v in zip(ds, rec) if float(v) >= 1})
    annees = sorted(a for a in set(recettes) & set(depenses) & set(solde) if a >= "1940")
    to_t = 1e-6  # millions -> milliers de milliards
    return {"years": annees, "receipts": [recettes[a] * to_t for a in annees], "outlays": [depenses[a] * to_t for a in annees],
            "balance": [solde[a] * to_t for a in annees], "balance_gdp": [pib.get(a) for a in annees],
            "recession_years": [a for a in recession if a in set(annees)],
            "source": "FRED (US Treasury, Office of Management and Budget) — exercices budgétaires d'octobre à septembre"}


# --------------------------------------------------------------------- MAC

BIGMAC_URL = "https://raw.githubusercontent.com/TheEconomist/big-mac-data/master/output-data/big-mac-full-index.csv"


def mac(base: str = "USD") -> dict:
    """Indice Big Mac (The Economist) : sur/sous-évaluation des devises par parité de pouvoir d'achat."""
    import csv
    import io
    import time
    import urllib.request

    from .data.yahoo import CACHE_DIR

    base = (base or "USD").upper()
    if base not in ("USD", "EUR", "GBP", "JPY", "CNY"):
        raise ValueError("base : USD, EUR, GBP, JPY ou CNY")
    path = CACHE_DIR / "bigmac.csv"
    if not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400:
        try:
            req = urllib.request.Request(BIGMAC_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                texte = r.read().decode()
            CACHE_DIR.mkdir(exist_ok=True)
            path.write_text(texte)
        except Exception:
            if not path.exists():
                raise
    rows = list(csv.DictReader(io.StringIO(path.read_text())))
    derniere = max(r["date"] for r in rows)
    precedente = max(r["date"] for r in rows if r["date"] < derniere)
    avant = {r["iso_a3"]: r for r in rows if r["date"] == precedente}

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    out = []
    for r in rows:
        if r["date"] != derniere or r["currency_code"] == base:
            continue
        brut, ajuste = num(r.get(f"{base}_raw")), num(r.get(f"{base}_adjusted"))
        if brut is None:
            continue
        p = avant.get(r["iso_a3"], {})
        out.append({"pays": r["name"], "devise": r["currency_code"], "prix_local": num(r["local_price"]),
                    "prix_usd": num(r["dollar_price"]), "change": num(r["dollar_ex"]), "brut": brut, "ajuste": ajuste,
                    "brut_precedent": num(p.get(f"{base}_raw"))})
    out.sort(key=lambda x: x["brut"], reverse=True)
    return {"date": derniere, "precedent": precedente, "base": base, "rows": out,
            "source": "The Economist — Big Mac index (github.com/TheEconomist/big-mac-data)"}


# --------------------------------------------------------------------- ILBE

def ilbe() -> dict:
    """Inflation anticipée américaine : points morts 5 et 10 ans, forward 5 ans dans 5 ans, inflation réalisée."""
    from .data.fred import FredConnector

    conn = FredConnector()
    out = {}
    for cle, sid in (("be5", "T5YIE"), ("be10", "T10YIE"), ("fwd5y5y", "T5YIFR"), ("dgs10", "DGS10"), ("tips10", "DFII10")):
        ds, vals = conn.fetch_series(sid)
        out[cle] = dict(zip(ds, (float(v) for v in vals)))
    dsc, cpi = conn.fetch_series("CPIAUCSL")
    cpi_yoy = {dsc[i]: (cpi[i] / cpi[i - 12] - 1) * 100 for i in range(12, len(dsc))}
    jours = sorted(set(out["be5"]) & set(out["be10"]) & set(out["fwd5y5y"]))
    debut = (date.fromisoformat(jours[-1]).replace(year=date.fromisoformat(jours[-1]).year - 10)).isoformat()
    jours = [d for d in jours if d >= debut]
    hebdo = jours[::5] + ([jours[-1]] if (len(jours) - 1) % 5 else [])
    mois = sorted(d for d in cpi_yoy if d >= debut)
    dern = jours[-1]

    def il_y_a(serie, jours_avant):
        from datetime import timedelta

        cible = (date.fromisoformat(dern) - timedelta(days=jours_avant)).isoformat()
        d = max(x for x in serie if x <= cible)
        return serie[d]

    kpi = {k: {"now": out[k][max(out[k])], "m1": il_y_a(out[k], 30), "y1": il_y_a(out[k], 365)}
           for k in ("be5", "be10", "fwd5y5y", "dgs10", "tips10")}
    kpi["cpi"] = {"now": cpi_yoy[mois[-1]], "date": mois[-1]}
    return {"date": dern, "dates": hebdo, "be5": [out["be5"][d] for d in hebdo], "be10": [out["be10"][d] for d in hebdo],
            "fwd5y5y": [out["fwd5y5y"][d] for d in hebdo], "cpi_dates": mois, "cpi_yoy": [cpi_yoy[d] for d in mois],
            "kpi": kpi, "source": "FRED — points morts nominal vs TIPS (Réserve fédérale de St. Louis), CPI (BLS)"}


# --------------------------------------------------------------------- Modèles « Machine Learning in Finance »

def _p(params):
    return {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}


def qlbs(params: dict | None = None) -> dict:
    """QLBS : pricing et couverture d'options par programmation dynamique (Dixon et al., ch. 10)."""
    from .quant.qlbs import qlbs as calcul

    return calcul(_p(params))


def gpg(params: dict | None = None) -> dict:
    """Prix, delta et gamma appris par processus gaussien (ch. 3 § 5)."""
    from .quant.gp import gp_greeks

    return gp_greeks(_p(params))


def gpvs(symbol: str) -> dict:
    """Surface de vol implicite lissée par processus gaussien, avec incertitude (ch. 3)."""
    from .quant.gp import gp_vol_surface

    return gp_vol_surface(_check(symbol))


def svol(symbol: str, params: dict | None = None) -> dict:
    """Volatilité stochastique (SVL/SVLJ) par filtre particulaire, contre GARCH (ch. 7)."""
    from .quant.particle import svol as calcul

    return calcul(_check(symbol), _p(params))


def beta(symbol: str, params: dict | None = None) -> dict:
    """Bêta bayésien avec intervalle de crédibilité et apprentissage séquentiel (ch. 2-3)."""
    from .quant.bayes import beta as calcul

    p = _p(params)
    if "indice" in p:
        p["indice"] = _check(p["indice"])
    return calcul(_check(symbol), p)


def regm(symbol: str, params: dict | None = None) -> dict:
    """Régimes : mélanges gaussiens (EM, BIC) contre HMM à persistance (ch. 2 et 7)."""
    from .quant.bayes import regm as calcul

    return calcul(_check(symbol), _p(params))


def tsa(symbol: str, params: dict | None = None) -> dict:
    """Box-Jenkins : ADF, ACF/PACF, AR par AIC/BIC, Ljung-Box, validation croisée, prévision (ch. 6)."""
    from .quant.timeseries import tsa as calcul

    return calcul(_check(symbol), _p(params))


# Catalogue des modèles du fonds — une seule source pour l'écran MODL.
# statut : production | analyse | rejeté (n'a pas battu la référence hors échantillon) | désactivé
CATALOGUE = [
    ("Stratégie de production", [
        ("Momentum de série temporelle 12 mois (TSMOM)", "research/signals.py", "ch. 6", "production", "RES"),
        ("Lissage exponentiel multi-vitesses (EWMA)", "research/signals.py", "ch. 6 § 2.10", "production", "RES"),
        ("Tendance par filtre de Kalman (niveau local + pente)", "research/signals.py", "ch. 7 § 2.2", "production", "RES"),
        ("Volatilité GARCH(1,1) pour le dimensionnement", "research/signals.py", "ch. 6 § 2.9", "production", "SPY SVOL"),
        ("Covariance EWMA rétrécie, risque égal, vol cible 10 %", "research/portfolio.py", "ch. 6", "production", "RISK"),
        ("Socle 60/40 + couche tendance, 95 % ETF / 5 % crypto", "research/production.py", "—", "production", "PORT"),
    ]),
    ("Modèles évalués et rejetés (banc et 11 campagnes, 62 essais)", [
        ("Limiteurs de baisse à 2,5x en contrats à terme : réduction selon la baisse, vol du fonds visée, filtre de tendance", "research/campaign11.py", "—", "rejeté", "CAMP"),
        ("Tendance et portage sur 52 marchés à terme (matières, taux, devises, indices), données gratuites corrigées", "research/campaign10.py", "—", "rejeté", "CAMP"),
        ("Volatilité stochastique (SVL, SVLJ, moyenne avec GARCH) pour le dimensionnement", "research/campaign6.py", "ch. 7 § 3-4", "rejeté", "CAMP"),
        ("Budget de risque par classe d'actifs, univers élargi aux matières premières, devises et obligations hors US", "research/campaign9.py", "—", "rejeté", "CAMP"),
        ("Socle en parité de risque « All Weather », effets de calendrier (tournant de mois, fériés, Sell in May)", "research/campaign8.py", "—", "rejeté", "CAMP"),
        ("Règles d'entrée / sortie : cassures de Donchian, stops suiveurs, zone neutre, long seul", "research/campaign7.py", "—", "rejeté", "CAMP"),
        ("Régression ridge transversale (classement ML)", "models/signals/linear.py", "ch. 3-4", "rejeté", "RES"),
        ("Réseau feedforward / autoencodeur", "models/signals/", "ch. 4, 8 § 6", "rejeté", "RES"),
        ("Filtre de régimes HMM (Baum-Welch, Viterbi)", "models/regimes/hmm.py", "ch. 7 § 2", "rejeté", "SPY REGM"),
        ("Allocation par Q-learning et G-learning", "models/allocation/", "ch. 9-10 § 5", "désactivé", "RES"),
        ("Portage de change G10 (carry)", "research/carry.py", "—", "rejeté", "RES"),
        ("Variantes de campagnes (filtre de courbe, vol gérée, rebalancement…)", "research/campaign*.py", "—", "rejeté", "CAMP"),
    ]),
    ("Thermomètre de bulle", [
        ("CAPE de Shiller, indicateur de Buffett, largeur (RSP/SPY, secteurs), VIX et SKEW en percentiles historiques", "equity/bulle.py", "—", "analyse", "BULL"),
        ("Titres IA (semi-conducteurs, big tech, second rang) et capex des hyperscalers (SEC EDGAR)", "equity/bulle.py", "—", "analyse", "BULL"),
    ]),
    ("Contrôles de robustesse", [
        ("Référence aléatoire : 2 000 stratégies au timing tiré au hasard (test de permutation)", "research/robustesse.py", "—", "analyse", "ROB"),
        ("Probabilité de surapprentissage (PBO, CSCV) sur 108 variantes", "research/robustesse.py", "—", "analyse", "ROB"),
        ("Statistiques de trading : taux de gain, profit factor, séries de pertes", "research/robustesse.py", "—", "analyse", "ROB"),
    ]),
    ("Options et dérivés", [
        ("Black-Scholes, grecques, vol implicite", "options/black_scholes.py", "ch. 10 § 3.4", "analyse", "SPY OVML"),
        ("Surface de volatilité implicite (parité call-put, variance totale)", "options/vol_surface.py", "—", "analyse", "SPY OVDV"),
        ("Surface de vol lissée par processus gaussien", "quant/gp.py", "ch. 3", "analyse", "SPY GPVS"),
        ("Prix et grecques appris par processus gaussien", "quant/gp.py", "ch. 3 § 5", "analyse", "GPG"),
        ("QLBS : pricing par apprentissage par renforcement (prog. dynamique)", "quant/qlbs.py", "ch. 10 § 2-4", "analyse", "QLBS"),
        ("Monte-Carlo : GBM, Student, bootstrap ; exotiques ; variable de contrôle", "options/monte_carlo.py", "ch. 9 § 5.1", "analyse", "SPY MC"),
    ]),
    ("Volatilité, régimes et séries temporelles", [
        ("Volatilité stochastique avec levier et sauts, filtre particulaire", "quant/particle.py", "ch. 7 § 3-4", "analyse", "SPY SVOL"),
        ("Mélanges gaussiens (EM) et sélection BIC / moyenne de modèles", "quant/bayes.py", "ch. 2 § 7-8", "analyse", "SPY REGM"),
        ("Box-Jenkins : ADF, ACF/PACF, AR, Ljung-Box, validation croisée", "quant/timeseries.py", "ch. 6 § 3-4", "analyse", "SPY TSA"),
        ("Bêta bayésien séquentiel (Normale-Gamma inverse)", "quant/bayes.py", "ch. 2 § 6, ch. 3 § 2", "analyse", "AAPL BETA"),
        ("ACP de la courbe des taux : niveau, pente, courbure", "quant/timeseries.py", "ch. 6 § 5", "analyse", "GC3D"),
        ("Projection à un an par bootstrap par blocs", "projection.py", "—", "analyse", "PROJ"),
    ]),
]


def modl() -> dict:
    """Catalogue de tous les modèles du fonds, avec leur statut et la commande du terminal qui les montre."""
    import json
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent / "data"
    essais = 0
    for f in sorted(racine.glob("research_campaign*_2026-10.json")):
        try:
            essais += len(json.loads(f.read_text()).get("resultats", []))
        except Exception:
            pass
    return {"sections": [{"titre": t, "modeles": [{"nom": n, "fichier": f, "livre": c, "statut": s, "commande": cmd}
                                                   for n, f, c, s, cmd in rows]} for t, rows in CATALOGUE],
            "livre": "Dixon, Halperin & Bilokon — Machine Learning in Finance: From Theory to Practice (Springer, 2020)",
            "lignes_resultats_campagnes": essais}


# --------------------------------------------------------------------- Actions et macro (sources officielles gratuites)

def fa(symbol: str) -> dict:
    """Fiche financière d'une société cotée aux États-Unis (SEC EDGAR)."""
    from .equity.fa import fa as fiche

    return fiche(_check(symbol))


def eqs(params: dict | None = None) -> dict:
    """Screener d'actions américaines (SEC EDGAR + cours)."""
    from .equity.eqs import eqs as screener

    return screener(_p(params))


def gew() -> dict:
    """Économie mondiale : FMI (réalisé et prévisions), BRI (taux directeurs), FRED/OCDE (taux à 10 ans)."""
    from .data.macro_monde import gew as monde

    return monde()


# --------------------------------------------------------------------- ROB : robustesse

def rob() -> dict:
    """Robustesse : référence aléatoire, PBO, statistiques de trading (rapport research/robustesse.py) + réel (paper)."""
    import json
    from pathlib import Path

    from .research.robustesse import OUT, stats_rendements

    if not OUT.exists():
        raise ValueError("rapport absent — lancer python3 -m gambit_ridge.research.robustesse")
    rep = json.loads(OUT.read_text())
    rep.pop("protocole", None)
    journal = Path(__file__).resolve().parent.parent / "data_cache" / "paper_journal_v2.json"
    rep["reel"] = None
    if journal.exists():
        h = json.loads(journal.read_text()).get("equity_history", [])
        eq = np.array([x["equity"] for x in h], dtype=float)
        if len(eq) >= 6:
            r = np.concatenate([[eq[0] / 1_000_000 - 1], eq[1:] / eq[:-1] - 1])
            rep["reel"] = {"debut": h[0]["date"], "fin": h[-1]["date"], **stats_rendements(r, [x["date"] for x in h])}
    return rep


# --------------------------------------------------------------------- HEDGE : couverture du fonds

def hedge(params: dict | None = None) -> dict:
    """Couverture du portefeuille réel : bêtas, variance minimale, CVaR, contrats MES/ES/ZN, puts, collar, chocs."""
    from .hedge.portefeuille import analyse

    p = _p(params)
    if "c" in p:
        try:
            p["c"] = float(p["c"])
        except (TypeError, ValueError):
            raise ValueError("capital invalide (paramètre c)")
        if not 1_000 <= p["c"] <= 1e10:
            raise ValueError("capital hors bornes (1 000 à 10 milliards)")
    return analyse(p)


# --------------------------------------------------------------------- BULL : thermomètre de bulle

def bull(params: dict | None = None) -> dict:
    """Thermomètre de bulle : CAPE, Buffett, largeur, complaisance, titres IA, capex des hyperscalers."""
    from .equity.bulle import bulle

    return bulle(rafraichir=_p(params).get("r") == "1")
