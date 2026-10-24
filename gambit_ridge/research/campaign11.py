"""Campagne de recherche n° 11 (octobre 2026) — la production en contrats à terme à 2 / 2,5x, et limiter la pire baisse.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Demande de Tom (24/10) : creuser la production actuelle mise en contrats à terme à 2 / 2,5x — coûts réels chez
Interactive Brokers, dépôt de garantie, comportement en crise — et limiter la pire baisse (par exemple réduire
l'exposition quand le fonds baisse). Aucun argent réel : simulation sur l'historique avec la grille PUBLIQUE d'IBKR.

Grille relevée le 24/10/2026 (interactivebrokers.com, IBKR Pro) : contrats « micro » 0,25 $ + frais de marché
(≈ 1 $ par contrat au total), contrats standard 0,85 $ + frais ; emprunt en dollars = taux de référence + 1,5 %
jusqu'à 100 000 $ (+1 % au-delà) ; dépôts de garantie initiaux (bourse CME, 24/10) en % du notionnel : indices
actions ≈ 8 %, Treasury 10 ans 1,9 %, 30 ans 3,8 %, or 5,6 %, argent 9 %, pétrole 15,5 %, euro 1,6 %, yen 3,9 %.

Mise en œuvre « contrats à terme quand ils existent » (figée) — poids de production × k :
  SPY→MES, QQQ→MNQ, IWM→M2K, EWJ→MNK, IEF→ZN, TLT→ZB, GLD→MGC, SLV→SIL, USO→MCL, FXE→M6E, FXY→6J : rendement de
  l'ETF − taux à 3 mois − 0,25 %/an (base), 2 bps par unité échangée, changement d'échéance 2 bps × |position|
  (mensuel pétrole, trimestriel le reste).
  EFA, EEM, VNQ, TIP, LQD, HYG, DBC, DBA, UUP : restent en ETF (5 bps), financés par le compte : trésorerie
  positive rémunérée au taux − 0,5 %, négative payée au taux + 1,5 % ; ventes à découvert 0,5 %/an, produit non rémunéré.
  Taux de référence = rendement du Trésor à 3 mois (FRED DGS3MO, connu la veille).
  Mise en œuvre « tout en ETF » pour comparaison : même calcul sans aucun contrat à terme.

PARTIE A — information (pas des essais) : rendement, vol, Sharpe, pire baisse, pire année glissante, baisses en
2008-2009, 2020 et 2022, k = 1 ; 2 ; 2,5 ; 3 pour les deux mises en œuvre. Dépôt de garantie : contrats (marge
initiale ci-dessus) + ETF (Reg T : 25 % des achats, 30 % des ventes) en % de l'actif net, médiane et maximum, et
maximum si les bourses doublent les marges en crise ; « appel de marge » si l'exigence dépasse l'actif net.
Arrondi au contrat près pour un compte de 100 000 $, 250 000 $ et 1 000 000 $ : écart de poids moyen et écart de
suivi annuel par rapport aux poids exacts (notionnels de contrats = multiplicateur × cours du contrat continu Yahoo).

PARTIE B — essais (base = mise en œuvre contrats à terme à k = 2,5 ; exposition décidée avec l'information de la
veille ; changement d'exposition facturé 3 bps × |Δk| × exposition brute) :
  D1 Réduction selon la baisse : exposition k tant que le fonds (levier compris) est à moins de 5 % de son plus
     haut ; de −5 % à −20 %, baisse linéaire jusqu'à 1x ; 1x au-delà ; remontée symétrique.
  D2 Volatilité du fonds visée : k × (vol cible / vol réalisée 63 j du fonds sans levier), bornée entre 1x et 3x ;
     vol cible = médiane de la vol 63 j de la production sur le développement (2008-2019).
  D3 Filtre de tendance sur le fonds : k si la production sans levier est au-dessus de sa moyenne 200 j, sinon 1x.
Périodes : développement 2008-04 → 2019, validation 2020 → aujourd'hui, échantillon 2001-2007 (proxys campagne 5).
Règle d'acceptation (risque, pas rendement) : pire baisse de développement améliorée d'au moins 5 points ;
rendement annuel de développement >= base − 1 point ; Sharpe de développement >= base − 0,05 ; validation : pire
baisse pas pire que la base et rendement >= base − 1 point ; 2001-2007 : pire baisse pas pire que la base.
Les mêmes règles sont aussi montrées à k = 2 (information).

Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom ; l'argent réel exige compte IBKR, données de
marché et avis juridique.

Usage : python3 -m gambit_ridge.research.campaign11
Sortie : data/research_campaign11_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from .backtest import period_metrics, simulate
from .campaign import _fred_on, _production
from .campaign9 import CRISES
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign11_2026-10.json"

# ETF -> (contrat, symbole Yahoo du contrat continu, multiplicateur, marge initiale en % du notionnel, roll mensuel)
CONTRATS = {
    "SPY": ("MES", "ES=F", 5, 0.075, False), "QQQ": ("MNQ", "NQ=F", 2, 0.079, False), "IWM": ("M2K", "RTY=F", 5, 0.086, False),
    "EWJ": ("MNK", "^N225", 0.5, 0.083, False), "IEF": ("ZN", "ZN=F", 1000, 0.019, False), "TLT": ("ZB", "ZB=F", 1000, 0.038, False),
    "GLD": ("MGC", "GC=F", 10, 0.056, False), "SLV": ("SIL", "SI=F", 1000, 0.090, False), "USO": ("MCL", "CL=F", 100, 0.155, True),
    "FXE": ("M6E", "6E=F", 12500, 0.016, False), "FXY": ("6J", "6J=F", 12_500_000, 0.039, False),
}
BASE_FUT = 0.0025
COUT_FUT_BPS, COUT_ROLL_BPS, COUT_EXPO_BPS = 2.0, 2.0, 3.0
ECART_CASH_POS, ECART_CASH_NEG, FRAIS_VENTE = -0.005, 0.015, 0.005
REG_T_ACHAT, REG_T_VENTE = 0.25, 0.30
LEVIERS = (1.0, 2.0, 2.5, 3.0)
K_BASE = 2.5
CAPITAUX = (100_000, 250_000, 1_000_000)


def masque_contrats(tickers: list[str]) -> np.ndarray:
    return np.array([t in CONTRATS for t in tickers])


def rendements_leviers(R: np.ndarray, W: np.ndarray, tickers: list[str], dates: list[str], rf: np.ndarray,
                       k: np.ndarray | float, contrats: bool = True) -> np.ndarray:
    """Rendement quotidien du fonds à l'exposition k (scalaire ou série décidée la veille), coûts IBKR compris.
    R : rendements quotidiens des ETF (T×N) ; W : poids détenus sans levier (T×N, après rebalancement à t)."""
    T, N = R.shape
    k = np.broadcast_to(np.asarray(k, dtype=float), (T,))
    fut = masque_contrats(tickers) if contrats else np.zeros(N, bool)
    rfj = np.nan_to_num(rf, nan=0.02)
    out = np.zeros(T)
    mois = np.array([d[:7] for d in dates])
    nouveau_mois = np.r_[False, mois[1:] != mois[:-1]]
    trimestre = nouveau_mois & np.array([int(d[5:7]) in (3, 6, 9, 12) for d in dates])
    roll_mensuel = np.array([CONTRATS[t][4] if t in CONTRATS else False for t in tickers])
    cout_unite = np.where(fut, COUT_FUT_BPS, ETF_COST_BPS) / 1e4
    for t in range(1, T):
        w = k[t - 1] * W[t - 1]
        jr = rfj[t - 1] / 252
        pnl = float(w[~fut] @ R[t, ~fut]) + float(w[fut] @ (R[t, fut] - (rfj[t - 1] + BASE_FUT) / 252))
        achats = float(np.clip(w[~fut], 0, None).sum())
        ventes = float(-np.clip(w[~fut], None, 0).sum())
        cash = 1.0 - achats  # produit des ventes non rémunéré
        pnl += cash * (jr + (ECART_CASH_POS if cash >= 0 else ECART_CASH_NEG) / 252) - ventes * FRAIS_VENTE / 252
        # coûts : échanges (variation des poids levier compris), changements d'échéance, changement d'exposition
        w_prev = k[t - 2] * W[t - 2] if t >= 2 else np.zeros(N)
        echange = np.abs(w - w_prev * (1 + R[t - 1]) / max(1 + float(w_prev @ R[t - 1]), 1e-9))
        cout = float(echange @ cout_unite)
        if nouveau_mois[t]:
            roll = fut & (roll_mensuel | trimestre[t])
            cout += float(np.abs(w[roll]).sum()) * COUT_ROLL_BPS / 1e4
        out[t] = pnl - cout
    return out


def _poids_detenus(sim) -> np.ndarray:
    return sim.weights


def depot_garantie(W: np.ndarray, tickers: list[str], k: float, contrats: bool = True, nav: np.ndarray | None = None) -> np.ndarray:
    """Exigence de dépôt (contrats : marge initiale ; ETF : Reg T maintenance) en part de l'actif net."""
    fut = masque_contrats(tickers) if contrats else np.zeros(len(tickers), bool)
    mg = np.array([CONTRATS[t][3] if t in CONTRATS else 0.0 for t in tickers])
    w = k * W
    req = (np.abs(w[:, fut]) * mg[fut]).sum(axis=1)
    req += REG_T_ACHAT * np.clip(w[:, ~fut], 0, None).sum(axis=1) + REG_T_VENTE * (-np.clip(w[:, ~fut], None, 0)).sum(axis=1)
    return req


def mesures(r: np.ndarray, dates: list[str], masque: np.ndarray) -> dict:
    m = period_metrics(r, None, masque, 252)
    d = np.array(dates)
    rr, dm = r[masque], d[masque]
    eq = np.cumprod(1 + rr)
    gl = eq[252:] / eq[:-252] - 1 if len(eq) > 252 else np.array([np.nan])
    crises = {}
    for cn, (a, b) in CRISES.items():
        sel = (dm >= a) & (dm <= b)
        if sel.sum() > 5:
            e = np.cumprod(1 + rr[sel])
            crises[cn] = float((e / np.maximum.accumulate(e) - 1).min())
    return {"cagr": m["cagr"], "vol": m["vol"], "sharpe": m["sharpe"], "max_dd": m["max_dd"],
            "pire_annee_glissante": float(np.nanmin(gl)), "pire_jour": float(rr.min()), "crises": crises}


# ---------------------------------------------------------------- limiteurs de baisse (partie B)

def expo_baisse(r_base_k: np.ndarray, k: float, haut: float = -0.05, bas: float = -0.20) -> np.ndarray:
    """D1 : exposition décidée sur la baisse du fonds (levier compris) depuis son plus haut, connue la veille."""
    T = len(r_base_k)
    expo = np.full(T, k)
    eq, pic = 1.0, 1.0
    for t in range(1, T):
        # rendement du jour à l'exposition décidée hier, reconstruit depuis le rendement à k (proportionnel)
        eq *= 1 + r_base_k[t] * expo[t - 1] / k
        pic = max(pic, eq)
        dd = eq / pic - 1
        f = 1.0 if dd >= haut else (0.0 if dd <= bas else (dd - bas) / (haut - bas))
        expo[t] = 1.0 + (k - 1.0) * f
    return expo


def expo_vol(r_sans_levier: np.ndarray, k: float, cible: float, fen: int = 63) -> np.ndarray:
    """D2 : k × cible / vol réalisée 63 j (sans levier, connue la veille), bornée [1, 3]."""
    T = len(r_sans_levier)
    expo = np.full(T, k)
    for t in range(fen + 1, T):
        v = float(np.std(r_sans_levier[t - fen:t]) * np.sqrt(252))
        if v > 1e-6:
            expo[t] = np.clip(k * cible / v, 1.0, 3.0)
    return expo


def expo_tendance(r_sans_levier: np.ndarray, k: float, fen: int = 200) -> np.ndarray:
    """D3 : k si la production sans levier est au-dessus de sa moyenne 200 j (la veille), sinon 1x."""
    eq = np.cumprod(1 + r_sans_levier)
    expo = np.full(len(eq), k)
    for t in range(fen + 1, len(eq)):
        expo[t] = k if eq[t - 1] >= eq[t - fen - 1:t - 1].mean() else 1.0
    return expo


def avec_expo(R, W, tickers, dates, rf, expo) -> np.ndarray:
    """Rendement à l'exposition variable, plus le coût de changement d'exposition."""
    r = rendements_leviers(R, W, tickers, dates, rf, expo)
    brut = np.abs(W).sum(axis=1)
    dk = np.r_[0.0, np.abs(np.diff(expo))]
    return r - np.r_[0.0, (dk * brut)[:-1]] * COUT_EXPO_BPS / 1e4


# ---------------------------------------------------------------- arrondi au contrat

def arrondi(W: np.ndarray, R: np.ndarray, tickers: list[str], dates: list[str], k: float, capital: float) -> dict:
    from ..data.yahoo import YahooConnector

    yc = YahooConnector()
    T = len(dates)
    ecarts, suivi = [], np.zeros(T)
    notion = {}
    for t_, (_, sym, mult, _, _) in CONTRATS.items():
        if t_ not in tickers:
            continue
        d = yc.fetch(sym)
        ks = sorted(d)
        idx = np.searchsorted(ks, dates, side="right") - 1
        notion[t_] = np.array([d[ks[i]] * mult if i >= 0 else np.nan for i in idx])
    nav = capital
    for t in range(1, T):
        e_t = 0.0
        for t_, n_ in notion.items():
            j = tickers.index(t_)
            cible = k * W[t - 1, j]
            if np.isnan(n_[t - 1]) or n_[t - 1] <= 0:
                continue
            reel = np.round(cible * nav / n_[t - 1]) * n_[t - 1] / nav
            e_t += abs(reel - cible)
            suivi[t] += (reel - cible) * R[t, j]
        ecarts.append(e_t)
        nav *= 1 + k * float(W[t - 1] @ R[t])
    m = np.arange(T) >= WARMUP
    return {"capital": capital, "ecart_poids_moyen": float(np.mean(np.array(ecarts)[m[1:]])),
            "ecart_suivi_annuel": float(np.std(suivi[m]) * np.sqrt(252))}


# ---------------------------------------------------------------- campagne

def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import load_presample

    t0 = time.time()
    base = all_etf_symbols()
    dates, p = load_aligned(base, refresh=True)
    d = np.array(dates)
    P = np.column_stack([p[t] for t in base])
    R = np.zeros_like(P)
    R[1:] = P[1:] / P[:-1] - 1
    sim = simulate(P, _production(P, base), ETF_COST_BPS, rebalance_every=5)
    W = sim.weights
    rf = _fred_on(dates, "DGS3MO") / 100.0
    tout = np.arange(len(d)) >= WARMUP
    dev = tout & (d <= DEV_END)
    val = d > DEV_END

    # PARTIE A
    partie_a = {"mises_en_oeuvre": {}, "depot_garantie": {}, "arrondi": []}
    for nom, fut in (("contrats_a_terme", True), ("tout_en_etf", False)):
        lignes = []
        for k in LEVIERS:
            r = rendements_leviers(R, W, base, dates, rf, k, contrats=fut)
            lignes.append({"levier": k, "tout": mesures(r, dates, tout), "developpement": mesures(r, dates, dev),
                           "validation": mesures(r, dates, val)})
        partie_a["mises_en_oeuvre"][nom] = lignes
    stress = np.zeros(len(d), bool)
    for a, b in CRISES.values():
        stress |= (d >= a) & (d <= b)
    for k in (2.0, 2.5, 3.0):
        dep = depot_garantie(W, base, k)
        fut = masque_contrats(base)
        mg = np.array([CONTRATS[t][3] if t in CONTRATS else 0.0 for t in base])
        dep_stress = dep + np.where(stress, (np.abs(k * W[:, fut]) * mg[fut]).sum(axis=1), 0.0)  # marges doublées en crise
        partie_a["depot_garantie"][str(k)] = {"median": float(np.median(dep[tout])), "max": float(dep[tout].max()),
                                              "max_marges_doublees_en_crise": float(dep_stress[tout].max()),
                                              "appel_de_marge": bool(dep_stress[tout].max() > 1.0)}
    for cap in CAPITAUX:
        partie_a["arrondi"].append(arrondi(W, R, base, dates, K_BASE, cap))
    print(f"  partie A ({time.time() - t0:.0f}s)", file=sys.stderr)

    # PARTIE B
    r0 = sim.returns
    vol63 = np.array([np.std(r0[t - 63:t]) * np.sqrt(252) if t >= 63 else np.nan for t in range(len(r0))])
    cible = float(np.nanmedian(vol63[dev]))
    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in base])
    R0 = np.zeros_like(P0)
    R0[1:] = P0[1:] / P0[:-1] - 1
    sim0 = simulate(P0, _production(P0, base), ETF_COST_BPS, rebalance_every=5)
    rf0 = _fred_on(pd_, "DGS3MO") / 100.0
    pre = np.arange(len(pd_)) >= WARMUP

    def essais(k: float, R_, W_, dts, rf_, r0_) -> dict:
        r_k = rendements_leviers(R_, W_, base, dts, rf_, k)
        return {"BASE": r_k,
                "D1": avec_expo(R_, W_, base, dts, rf_, expo_baisse(r_k, k)),
                "D2": avec_expo(R_, W_, base, dts, rf_, expo_vol(r0_, k, cible)),
                "D3": avec_expo(R_, W_, base, dts, rf_, expo_tendance(r0_, k))}

    noms = {"BASE": "Base — production en contrats à terme", "D1": "Réduction selon la baisse (−5 % → −20 %)",
            "D2": "Volatilité du fonds visée", "D3": "Filtre de tendance 200 j sur le fonds"}
    resultats = {}
    for k in (K_BASE, 2.0):
        rs, rs0 = essais(k, R, W, dates, rf, r0), essais(k, R0, sim0.weights, pd_, rf0, sim0.returns)
        bloc = {}
        for key, r in rs.items():
            bloc[key] = {"nom": f"{key} — {noms[key]}", "developpement": mesures(r, dates, dev), "validation": mesures(r, dates, val),
                         "echantillon_2001_2007": mesures(rs0[key], pd_, pre)}
        b = bloc["BASE"]
        for key, x in bloc.items():
            if key == "BASE":
                continue
            checks = {
                "baisse_dev_amelioree_5_points": x["developpement"]["max_dd"] >= b["developpement"]["max_dd"] + 0.05,
                "rendement_dev": x["developpement"]["cagr"] >= b["developpement"]["cagr"] - 0.01,
                "sharpe_dev": x["developpement"]["sharpe"] >= b["developpement"]["sharpe"] - 0.05,
                "baisse_validation": x["validation"]["max_dd"] >= b["validation"]["max_dd"],
                "rendement_validation": x["validation"]["cagr"] >= b["validation"]["cagr"] - 0.01,
                "baisse_2001_2007": x["echantillon_2001_2007"]["max_dd"] >= b["echantillon_2001_2007"]["max_dd"],
            }
            x["criteres"] = {c: bool(v) for c, v in checks.items()}
            x["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
        resultats[str(k)] = bloc
    print(f"  partie B ({time.time() - t0:.0f}s)", file=sys.stderr)

    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "periode": [str(d[WARMUP]), dates[-1]],
              "vol_cible_d2": cible, "partie_a": partie_a, "resultats_par_levier": resultats,
              # vue jugée (k = 2,5) pour l'onglet Recherche : la base sert de référence
              "resultats": {("REF" if key == "BASE" else key): x for key, x in resultats[str(K_BASE)].items()},
              "duree_s": round(time.time() - t0)}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def _ligne(nom, m):
    c = m["crises"]
    return (f"{nom:<44} {m['cagr']:>6.1%} {m['vol']:>6.1%} {m['sharpe']:>5.2f} {m['max_dd']:>7.1%} {m['pire_annee_glissante']:>7.1%} "
            f"{m['pire_jour']:>6.1%} {c.get('2008-2009', float('nan')):>7.1%} {c.get('Covid 2020', float('nan')):>6.1%} {c.get('2022', float('nan')):>6.1%}")


def main() -> int:
    rep = run()
    a = rep["partie_a"]
    tete = f"{'':<44} {'rend.':>6} {'vol':>6} {'Shrp':>5} {'pire b':>7} {'pire12':>7} {'p.jour':>6} {'08-09':>7} {'2020':>6} {'2022':>6}"
    print(f"\nPARTIE A — {rep['periode'][0]} → {rep['periode'][1]} (tout l'historique)\n" + tete)
    for nom, lignes in a["mises_en_oeuvre"].items():
        for l in lignes:
            print(_ligne(f"{nom} {l['levier']}x", l["tout"]))
    print("\nDépôt de garantie (part de l'actif net) :", json.dumps(a["depot_garantie"], ensure_ascii=False))
    print("Arrondi au contrat (2,5x) :", [(x["capital"], f"{x['ecart_poids_moyen']:.1%}", f"{x['ecart_suivi_annuel']:.2%}") for x in a["arrondi"]])
    for k, bloc in rep["resultats_par_levier"].items():
        print(f"\nPARTIE B — exposition {k}x (vol cible D2 {rep['vol_cible_d2']:.1%})")
        for per in ("developpement", "validation", "echantillon_2001_2007"):
            print(f"  {per}\n  " + tete)
            for key, x in bloc.items():
                print("  " + _ligne(x["nom"][:44], x[per]))
        for key, x in bloc.items():
            if "verdict" in x:
                print(f"  {key} : {x['verdict']} {x['criteres']}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
