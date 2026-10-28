"""BULL — thermomètre de bulle : valorisation, déconnexion avec l'économie, largeur, complaisance, titres IA.

Uniquement des données gratuites et réelles :
- CAPE de Shiller (P/E ajusté du cycle sur 10 ans), mensuel depuis 1871 : table publique multpl.com
  (reprise des données de R. Shiller, point du mois en cours = dernier cours).
- Indicateur de Buffett : actions des sociétés non financières US (Fed, comptes Z.1, FRED NCBEILQ027S)
  / PIB nominal (FRED GDP), trimestriel depuis 1945 ; prolongé jusqu'à aujourd'hui avec le Wilshire 5000
  (Yahoo ^W5000) depuis la fin du dernier trimestre publié.
- Largeur : S&P 500 équipondéré / pondéré par les capitalisations (RSP / SPY, depuis 2003) et part des
  11 secteurs SPDR au-dessus de leur moyenne 200 jours. La vraie ligne avance/baisse du NYSE n'est pas
  diffusée gratuitement : ces deux mesures en sont l'équivalent le plus proche.
- Complaisance : VIX (depuis 1990) et SKEW du CBOE (prix du risque extrême). Le ratio put/call total
  du CBOE n'est plus publié gratuitement en historique depuis 2019 : non affiché plutôt qu'inventé.
- Titres IA : cours Yahoo (perf. 1 an, écart à la moyenne 200 jours, capitalisation, PER) et, pour les
  hyperscalers déposant à la SEC, investissements (capex) des douze derniers mois rapportés au flux
  d'exploitation (SEC EDGAR).

Chaque indicateur est classé en percentile de sa propre histoire ; le thermomètre est la moyenne des
percentiles (sens « plus haut = plus tendu »). Ce n'est pas un signal de trading : aucun de ces
indicateurs ne date un krach (le CAPE a dépassé 30 en 1997, trois ans avant le sommet de 2000).
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

import numpy as np

CACHE = Path(__file__).resolve().parent.parent.parent / "data_cache" / "bulle.json"
TTL_S = 6 * 3600

SECTEURS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
TITRES = [
    ("NVDA", "Nvidia", "semi-conducteurs"), ("TSM", "TSMC", "semi-conducteurs"), ("ASML", "ASML", "semi-conducteurs"),
    ("AVGO", "Broadcom", "semi-conducteurs"), ("MSFT", "Microsoft", "big tech"), ("GOOGL", "Alphabet", "big tech"),
    ("AMZN", "Amazon", "big tech"), ("META", "Meta", "big tech"), ("AAPL", "Apple", "big tech"),
    ("ORCL", "Oracle", "second rang"), ("PLTR", "Palantir", "second rang"),
]
HYPERSCALERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL"]
MOIS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def cape_mensuel() -> tuple[list[str], np.ndarray]:
    """CAPE de Shiller mensuel (dates ISO croissantes). Cache disque 24 h, repli sur le cache hors ligne."""
    path = CACHE.parent / "cape_shiller.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        d = json.loads(path.read_text())
        return d["dates"], np.array(d["valeurs"])
    try:
        req = urllib.request.Request("https://www.multpl.com/shiller-pe/table/by-month", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode("utf-8", "replace")
        points = {}
        for jour, val in re.findall(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>([^<]+)</td>", page):
            m, j, a = re.match(r"(\w{3}) (\d+), (\d{4})", jour).groups()
            v = float(html.unescape(val).strip().replace(",", ""))
            points[date(int(a), MOIS[m], int(j)).isoformat()] = v
        if len(points) < 1000:
            raise ValueError(f"table CAPE incomplète ({len(points)} points)")
        dates = sorted(points)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"dates": dates, "valeurs": [points[d] for d in dates]}))
        return dates, np.array([points[d] for d in dates])
    except Exception:
        if path.exists():
            d = json.loads(path.read_text())
            return d["dates"], np.array(d["valeurs"])
        raise


def percentile(hist: np.ndarray, v: float) -> float:
    """Part de l'historique strictement inférieure à v (0-1)."""
    h = hist[np.isfinite(hist)]
    return float((h < v).mean()) if len(h) else float("nan")


def _mm(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def _mensuel(dates: list[str], v: np.ndarray) -> tuple[list[str], list[float]]:
    """Dernier point de chaque mois (graphiques légers)."""
    out: dict[str, float] = {}
    for d, x in zip(dates, v):
        if np.isfinite(x):
            out[d[:7]] = float(x)
    return list(out), list(out.values())


def _buffett(yahoo) -> dict:
    from ..data.fred import FredConnector

    fred = FredConnector()
    de, eq = fred.fetch_series("NCBEILQ027S")  # millions de $
    dg, pib = fred.fetch_series("GDP")  # milliards de $, rythme annuel
    pib_d = dict(zip(dg, pib))
    dates = [d for d in de if d in pib_d]
    ratio = np.array([eq[de.index(d)] / 1000 / pib_d[d] for d in dates])
    # le trimestre t est publié ~10 semaines après sa fin : la valeur est datée de la fin du trimestre
    fin_trim = {"01": "03-31", "04": "06-30", "07": "09-30", "10": "12-31"}
    fin_dernier = dates[-1][:5] + fin_trim[dates[-1][5:7]]
    estime, base_w = None, None
    try:
        w = yahoo.fetch("^W5000", refresh=True)
        wd = sorted(w)
        avant = [d for d in wd if d <= fin_dernier]
        if avant and wd[-1] > fin_dernier:
            base_w = w[avant[-1]]
            estime = float(ratio[-1] * w[wd[-1]] / base_w)  # PIB tenu constant : légère surestimation
            date_estime = wd[-1]
    except Exception:
        pass
    actuel = estime if estime is not None else float(ratio[-1])
    return {
        "dates": dates, "valeurs": ratio.round(4).tolist(), "dernier_publie": float(ratio[-1]), "date_publie": fin_dernier,
        "actuel": actuel, "date_actuel": date_estime if estime is not None else fin_dernier, "estime": estime is not None,
        "percentile": percentile(ratio, actuel), "moyenne": float(ratio.mean()), "max_2000": float(ratio[[d < "2001" for d in dates]].max()),
        "capitalisation_estimee_md": float(eq[-1] / 1000 * (actuel / ratio[-1])),
    }


def _serie(yahoo, sym: str) -> tuple[list[str], np.ndarray]:
    p = yahoo.fetch(sym, refresh=True)  # sans refresh, un vieux cache est servi indéfiniment
    d = sorted(p)
    return d, np.array([p[x] for x in d])


def calcul() -> dict:
    from ..data.yahoo import YahooConnector, load_aligned

    yahoo = YahooConnector(max_age_hours=6)
    out: dict = {"genere_le": datetime.now().strftime("%Y-%m-%d %H:%M"), "erreurs": []}

    # 1. CAPE
    dc, cape = cape_mensuel()
    pics = {}
    for an, (a, b) in {"1929": ("1929-01", "1929-12"), "2000": ("1999-06", "2000-12"), "2021": ("2021-01", "2022-01")}.items():
        m = [v for d, v in zip(dc, cape) if a <= d[:7] <= b]
        pics[an] = max(m) if m else None
    out["cape"] = {"dates": [d[:7] for d in dc], "valeurs": cape.round(2).tolist(), "actuel": float(cape[-1]), "date": dc[-1],
                   "percentile": percentile(cape[:-1], cape[-1]), "moyenne": float(cape.mean()), "mediane": float(np.median(cape)), "pics": pics,
                   "mois_au_dessus_30": int((cape > 30).sum())}

    # 2. Buffett
    try:
        out["buffett"] = _buffett(yahoo)
    except Exception as exc:
        out["buffett"] = None
        out["erreurs"].append(f"Buffett : {exc}")

    # 3. Largeur : RSP / SPY et secteurs au-dessus de la MM200
    d, px = load_aligned(["RSP", "SPY"], refresh=True, connector=yahoo)
    rel = px["RSP"] / px["SPY"]
    rel = rel / rel[0]
    perf = lambda x, n: float(x[-1] / x[-1 - n] - 1) if len(x) > n else None  # noqa: E731
    i_haut = int(np.argmax(rel))
    xm, ym = _mensuel(d, rel)
    # écart de perf. sur 12 mois glissants : équipondéré - pondéré (négatif = hausse concentrée)
    e12 = np.full(len(rel), np.nan)
    e12[252:] = (px["RSP"][252:] / px["RSP"][:-252]) - (px["SPY"][252:] / px["SPY"][:-252])
    secteurs = []
    for s in SECTEURS:
        try:
            ds, ps = _serie(yahoo, s)
            mm = _mm(ps, 200)
            secteurs.append({"symbole": s, "au_dessus": bool(ps[-1] > mm[-1]), "ecart_mm200": float(ps[-1] / mm[-1] - 1), "perf_1an": perf(ps, 252)})
        except Exception as exc:
            out["erreurs"].append(f"{s} : {exc}")
    out["largeur"] = {"dates": xm, "rsp_spy": [round(v, 4) for v in ym], "rsp_1an": perf(px["RSP"], 252), "spy_1an": perf(px["SPY"], 252),
                      "ecart_12m": float(e12[-1]), "percentile_ecart": percentile(-e12[252:-1], -e12[-1]),
                      "baisse_depuis_haut": float(rel[-1] / rel[i_haut] - 1), "date_haut": d[i_haut], "debut": d[0],
                      "secteurs": secteurs, "part_secteurs_au_dessus": (sum(s["au_dessus"] for s in secteurs) / len(secteurs)) if secteurs else None}

    # 4. Complaisance : VIX et SKEW
    dv, vix = _serie(yahoo, "^VIX")
    vm = _mm(vix, 21)
    xv, yv = _mensuel(dv, vm)
    comp = {"vix": float(vix[-1]), "vix_mm1m": float(vm[-1]), "date": dv[-1], "vix_mediane": float(np.median(vix)),
            "percentile_calme": percentile(-vm[20:-1], -vm[-1]), "dates": xv, "vix_mensuel": [round(v, 2) for v in yv]}
    try:
        dk, skew = _serie(yahoo, "^SKEW")
        comp.update(skew=float(skew[-1]), skew_percentile=percentile(skew[:-1], skew[-1]), skew_mediane=float(np.median(skew)))
    except Exception as exc:
        out["erreurs"].append(f"SKEW : {exc}")
    out["complaisance"] = comp

    # 5. Titres IA
    titres = []
    try:
        from ..data.yahoo_options import cotations
        q = cotations([t for t, _, _ in TITRES])
    except Exception as exc:
        q = {}
        out["erreurs"].append(f"cotations : {exc}")
    for t, nom, groupe in TITRES:
        ligne = {"symbole": t, "nom": nom, "groupe": groupe}
        try:
            dt, pt = _serie(yahoo, t)
            mm = _mm(pt, 200)
            ligne.update(perf_1an=perf(pt, 252), perf_3ans=perf(pt, 756), ecart_mm200=float(pt[-1] / mm[-1] - 1),
                         baisse_depuis_haut=float(pt[-1] / pt[-252:].max() - 1),
                         historique=[round(float(v), 2) for v in pt[-252::5]])
        except Exception as exc:
            out["erreurs"].append(f"{t} : {exc}")
        c = q.get(t, {})
        ligne.update(capitalisation=c.get("capitalisation"), per=c.get("per_yahoo"))
        titres.append(ligne)
    out["titres"] = titres
    caps = [x["capitalisation"] for x in titres if x.get("capitalisation")]
    if caps and out.get("buffett"):
        out["poids_titres_ia"] = sum(caps) / (out["buffett"]["capitalisation_estimee_md"] * 1e9)

    # 6. Capex des hyperscalers (SEC EDGAR)
    capex = []
    try:
        from ..data import edgar
        for t in HYPERSCALERS:
            try:
                c = edgar.comptes(t)
                tt = c["ttm"]
                annuel = [{"annee": a["annee"], "capex": a.get("investissements"), "flux": a.get("flux_operationnel")} for a in c["annuel"][-6:]]
                capex.append({"symbole": t, "capex_ttm": tt.get("investissements"), "flux_ttm": tt.get("flux_operationnel"),
                              "ca_ttm": tt.get("chiffre_affaires"), "fin": tt.get("fin"), "annuel": annuel,
                              "capex_sur_flux": (tt["investissements"] / tt["flux_operationnel"]) if tt.get("investissements") and tt.get("flux_operationnel") else None})
            except Exception as exc:
                out["erreurs"].append(f"EDGAR {t} : {exc}")
    except Exception as exc:
        out["erreurs"].append(f"EDGAR : {exc}")
    out["capex"] = capex

    # 7. Thermomètre : moyenne des percentiles (plus haut = plus tendu)
    composantes = [("Cherté historique (CAPE)", out["cape"]["percentile"])]
    if out.get("buffett"):
        composantes.append(("Bourse / économie (Buffett)", out["buffett"]["percentile"]))
    composantes.append(("Concentration (équipondéré à la traîne)", out["largeur"]["percentile_ecart"]))
    composantes.append(("Complaisance (VIX bas)", comp["percentile_calme"]))
    out["thermometre"] = {"composantes": [{"nom": n, "percentile": p} for n, p in composantes],
                          "score": float(np.nanmean([p for _, p in composantes]))}
    return out


def bulle(rafraichir: bool = False) -> dict:
    """Rapport mis en cache 6 h (EDGAR + 25 séries Yahoo : trop lent pour chaque affichage)."""
    if not rafraichir and CACHE.exists() and time.time() - CACHE.stat().st_mtime < TTL_S:
        return json.loads(CACHE.read_text())
    rep = calcul()
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(rep))
    return rep
