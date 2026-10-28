"""Couverture du portefeuille RÉEL du fonds (positions du paper trading) — fonction terminal HEDGE.

Mesure ce que le fonds porte aujourd'hui et ce qu'il faudrait pour le couvrir :
bêta (MCO, EWMA, Kalman, de baisse), ratio à variance minimale et son efficacité, couverture à
CVaR minimale, VaR/CVaR avant et après, nombre de contrats (MES, ES ; ZN pour les taux via la
DV01), coût d'un put et d'un collar au VIX du jour, chocs de marché couverts / non couverts.
Les poids sont tenus constants sur l'historique (photographie du portefeuille du jour).
Outil d'analyse : il ne passe aucun ordre et ne modifie pas la stratégie.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import maths as hm

RACINE = Path(__file__).resolve().parent.parent.parent
JOURNAL = RACINE / "data_cache" / "paper_journal_v2.json"
CAMPAGNE = RACINE / "data" / "research_campaign12_2026-10.json"
FENETRE = 504  # deux ans de séances
# Duration modifiée approximative des ETF obligataires (fiches émetteurs, ordre de grandeur) :
# sert à la DV01 du fonds. Les ETF non obligataires ont une duration nulle ici.
DURATION = {"SHY": 1.9, "IEI": 4.4, "IEF": 7.3, "TLT": 16.5, "TIP": 6.7, "LQD": 8.3, "HYG": 3.2, "EMB": 6.9, "BWX": 7.8}
ZN_DURATION = 6.0  # contrat 10 ans du CBOT (livrable le moins cher), approximation
CONTRATS = {"MES": ("ES=F", 5.0, "Micro E-mini S&P 500"), "ES": ("ES=F", 50.0, "E-mini S&P 500")}


def _positions() -> tuple[dict[str, float], float, str]:
    j = json.loads(JOURNAL.read_text())
    dernier = j["equity_history"][-1]
    return dernier["weights"], float(dernier["equity"]), dernier["date"]


def _prix(symboles: list[str]) -> tuple[list[str], dict[str, np.ndarray]]:
    from ..data.yahoo import YahooConnector

    conn = YahooConnector()
    brut = {s: conn.fetch(s, refresh=False) for s in symboles}
    # crypto cotée 7 j/7 : on s'aligne sur les séances de SPY
    dates = sorted(set(brut["SPY"]).intersection(*(set(v) for v in brut.values())))
    return dates, {s: np.array([brut[s][d] for d in dates], dtype=float) for s in symboles}


def _dernier(symbole: str) -> float | None:
    from ..data.yahoo import YahooConnector

    try:
        d = YahooConnector().fetch(symbole, refresh=False)
        return float(d[max(d)]) if d else None
    except Exception:
        return None


def _vix() -> tuple[float, str]:
    from ..data.fred import FredConnector

    d, v = FredConnector().fetch_series("VIXCLS")
    ok = np.isfinite(v)
    return float(v[ok][-1]), d[int(np.flatnonzero(ok)[-1])]


def analyse(params: dict | None = None) -> dict:
    p = {k: (v[0] if isinstance(v, list) else v) for k, v in (params or {}).items()}
    poids, actif, date_pos = _positions()
    capital = float(p.get("c") or actif)
    poids = {k: v for k, v in poids.items() if abs(v) > 1e-6}
    symboles = sorted(set(poids) | {"SPY"})
    dates, px = _prix(symboles)
    dates, px = dates[-FENETRE - 1:], {k: v[-FENETRE - 1:] for k, v in px.items()}
    R = {k: v[1:] / v[:-1] - 1 for k, v in px.items()}
    r_spy = R["SPY"]
    r_p = sum(w * R[k] for k, w in poids.items())

    stat = hm.ratio_variance_min(r_p, r_spy)
    b_ewma = hm.beta_ewma(r_p, r_spy)
    b_kal = hm.beta_kalman(r_p, r_spy)
    b_bas = hm.beta_baisse(r_p, r_spy)
    cv = hm.ratio_cvar(r_p, r_spy, h_max=max(1.0, 2 * abs(stat["h"])))
    h_vm = float(b_ewma[-1]) if np.isfinite(b_ewma[-1]) else stat["h"]

    def risque(r):
        out = {}
        for a in (0.95, 0.99):
            x = hm.var_cvar(r, a)
            out[f"{int(a * 100)}"] = {"var": x["var"], "cvar": x["cvar"], "var_cf": x["var_cf"]}
        nav = np.cumprod(1 + r)
        out["vol"] = float(np.std(r, ddof=1) * math.sqrt(252))
        out["pire_baisse"] = float((nav / np.maximum.accumulate(nav) - 1).min())
        out["rendement_annuel"] = float(nav[-1] ** (252 / len(r)) - 1)
        return out

    avant = risque(r_p)
    apres_vm = risque(r_p - h_vm * r_spy)
    apres_cvar = risque(r_p - cv["h"] * r_spy)

    # contrats
    es = _dernier("ES=F") or float(px["SPY"][-1]) * 10.0
    contrats = {k: {"nom": nom, "multiplicateur": m, "prix": es, **hm.nb_contrats(h_vm, capital, es, m)}
                for k, (_, m, nom) in CONTRATS.items()}
    dv01 = sum(poids.get(k, 0.0) * d for k, d in DURATION.items()) * capital * 1e-4
    zn = _dernier("ZN=F") or 112.0
    dv01_zn = zn * 1000 * ZN_DURATION * 1e-4
    taux = {"dv01_fonds": float(dv01), "duration_fonds": float(sum(poids.get(k, 0.0) * d for k, d in DURATION.items())),
            "prix_zn": zn, "dv01_zn": float(dv01_zn), "contrats_zn": int(round(dv01 / dv01_zn)) if dv01_zn else 0,
            "detail": {k: {"poids": poids[k], "duration": d, "dv01": poids[k] * d * capital * 1e-4} for k, d in DURATION.items() if k in poids}}

    # options au VIX du jour
    vix, date_vix = _vix()
    S = float(px["SPY"][-1])
    from ..data.fred import FredConnector
    try:
        _, t3 = FredConnector().fetch_series("DGS3MO")
        rf = float(t3[np.isfinite(t3)][-1]) / 100
    except Exception:
        rf = 0.04
    tau = 21 / 252
    put = float(hm.bs(S, 0.95 * S, tau, rf, vix / 100 + 0.03, True))
    call = float(hm.bs(S, 1.05 * S, tau, rf, max(vix / 100 - 0.02, 0.05), False))
    notion = max(h_vm, 0.0) * capital
    options = {"vix": vix, "date_vix": date_vix, "spy": S, "taux": rf,
               "put": {"strike": 0.95 * S, "prix": put, "cout_mois": put / S * notion, "cout_an_pct_actif": put / S * max(h_vm, 0) * 12,
                       "delta": float(hm.delta_bs(S, 0.95 * S, tau, rf, vix / 100 + 0.03, True)), "contrats_spy": int(round(notion / (100 * S)))},
               "collar": {"strike_call": 1.05 * S, "prix_call": call, "cout_mois": (put - call) / S * notion,
                          "cout_an_pct_actif": (put - call) / S * max(h_vm, 0) * 12}}

    # chocs instantanés (sensibilités au premier ordre, Belghaieb p. 11)
    chocs = []
    for nom, ds, dy in (("S&P 500 −10 %", -0.10, 0.0), ("S&P 500 −20 %", -0.20, 0.0), ("Taux +100 pb", 0.0, 0.01),
                        ("Krach 2022 : actions −20 %, taux +200 pb", -0.20, 0.02)):
        brut = h_vm * ds * capital - dv01 * dy * 1e4
        couv_actions = -contrats["MES"]["contrats"] * contrats["MES"]["notionnel_contrat"] * ds
        couv_taux = taux["contrats_zn"] * dv01_zn * dy * 1e4
        chocs.append({"scenario": nom, "sans": brut, "avec_mes": brut + couv_actions, "avec_mes_zn": brut + couv_actions + couv_taux})

    camp = None
    if CAMPAGNE.exists():
        c = json.loads(CAMPAGNE.read_text())
        camp = {"genere_le": c["genere_le"], "essais": [
            {"cle": k, "nom": v["nom"], "sharpe_dev": v["developpement"]["sharpe"], "sharpe_val": v["validation"]["sharpe"],
             "dd_val": v["validation"]["max_dd"], "sharpe_0107": v["echantillon_2001_2007"]["sharpe"],
             "cvar_val": v["cvar95_jour"]["validation"], "crises": v["crises"], "verdict": v.get("verdict", "référence")}
            for k, v in c["resultats"].items()]}

    pas = max(1, len(dates) // 250)
    return {
        "date_positions": date_pos, "actif": actif, "capital": capital, "n_lignes": len(poids),
        "periode": [dates[1], dates[-1]], "n_jours": len(r_p),
        "beta": {"mco": stat["h"], "ewma": h_vm, "kalman": float(b_kal[-1]), "baisse": b_bas, "rho": stat["rho"],
                 "efficacite": stat["efficacite"]},
        "cvar_optimal": cv, "risque": {"avant": avant, "variance_min": apres_vm, "cvar_min": apres_cvar},
        "contrats": contrats, "taux": taux, "options": options, "chocs": chocs, "campagne12": camp,
        "serie": {"dates": dates[1::pas], "ewma": [None if not np.isfinite(x) else round(float(x), 4) for x in b_ewma[::pas]],
                  "kalman": [round(float(x), 4) for x in b_kal[::pas]]},
        "sources": ["Dixon, Halperin, Bilokon — ML in Finance, ch. 10 éq. 10.10 (variance minimale)",
                    "Belghaieb — Sales & Trading p. 11 (DV01) et p. 15 (contrats ≈ bêta × valeur / notionnel)",
                    "Rockafellar & Uryasev (2000) — CVaR", "Ang, Chen & Xing (2006) — bêta de baisse"],
    }
