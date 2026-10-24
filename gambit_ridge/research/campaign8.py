"""Campagne de recherche n° 8 (octobre 2026) — diversification : socle et sources de rendement non liées à la tendance.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Question : sept campagnes ont montré que les réglages de la couche tendance ne s'améliorent plus.
La moitié du fonds est un socle 60/40 (SPY / IEF) qui dépend de deux actifs ; et tout le reste
du rendement vient de la tendance. Un socle plus diversifié ou une source de rendement liée au
calendrier (décorrélée de la tendance) améliorent-ils le fonds ?

Référence : la stratégie ETF de production (« 60/40 + couche tendance », 20 ETF, socle 50 %,
vol GARCH, covariance EWMA, vol cible 10 %, filtre 25 % / 0,5 %, rebalancement tous les 5 jours,
5 bps). Paramètres tirés de la littérature, AUCUNE grille, aucun réglage a posteriori.

Essais (5) :
  Socle (remplace le 60/40 ; la couche tendance ne change pas) :
  C1 Socle en parité de risque (« All Weather » simplifié, Qian 2005 ; Asness, Frazzini &
     Pedersen 2012) : SPY, TLT, IEF, TIP, GLD, DBC pondérés par l'inverse de leur volatilité
     réalisée sur 252 séances, puis ramenés à la même volatilité que le socle 60/40 (constante
     de la campagne 1 : médiane de la vol 21 j du 60/40 sur 2008-2019), exposition brute du
     socle plafonnée à 2.
  C2 Même socle en parité de risque, SANS levier (poids qui somment à 1).
  Calendrier (poche autonome ramenée à 10 % de vol ex ante, ajoutée en surcouche 0,5x comme
  en campagne 2 : fonds = production + 0,5 x poche ; rebalancement quotidien, 5 bps) :
  S1 Tournant de mois (Lakonishok & Smidt 1988 ; McConnell & Xu 2008) : SPY détenu sur le
     dernier jour de bourse du mois et les 3 premiers du mois suivant, à plat sinon.
  S2 Veilles de jours fériés (Ariel 1990) : SPY détenu sur la séance qui précède un jour
     ouvré sans cotation (calendrier de bourse connu à l'avance), à plat sinon.
  S3 « Sell in May » (Bouman & Jacobsen 2002) : la part actions du socle est divisée par
     deux du 1er mai au 31 octobre.

Pistes écartées AVANT calcul, faute de données suffisantes : portage crypto par les taux de
financement des contrats perpétuels (historique Binance à partir de fin 2019 : aucun
échantillon de développement) ; ETF « qualité / faible volatilité » (2011-2013 : développement
trop court, et la faible volatilité a déjà été rejetée en campagne 2).

Périodes et règle d'acceptation : identiques à la campagne 7 (développement -> 2019-12-31 après
260 séances de rodage, validation 2020 -> aujourd'hui ; Sharpe dév. >= réf. + 0,05 ; DSR >= 0,90 ;
Sharpe validation >= réf. − 0,05 ; pire baisse validation pas plus de 3 points au-delà de la
réf. ; Sharpe 2001-2007, échantillon reconstitué de la campagne 5, >= réf. − 0,05). La
validation ne choisit rien.

Tests multiples : DSR calculé sur tous les Sharpe de développement des campagnes 1, 2, 4, 6 et 7
plus les 5 essais de cette campagne. Un essai accepté n'entre au portefeuille qu'avec
l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign8
Sortie : data/research_campaign8_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from .backtest import deflated_sharpe, period_metrics, simulate
from .campaign import CORE, OVERLAY, RULES, _core_matrix, _production
from .campaign2 import _vol_target
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP
from .portfolio import ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign8_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4", "6", "7")]
PARITE = ("SPY", "TLT", "IEF", "TIP", "GLD", "DBC")
FENETRE_VOL, LEVIER_MAX = 252, 2.0


def socle_parite(P: np.ndarray, tk: list[str], cible: float | None) -> np.ndarray:
    """Poids du socle en parité de risque (inverse de la vol 252 j), causal. cible=None : sans levier.
    Avant 252 séances : socle 60/40 (période de rodage, non mesurée)."""
    T = len(P)
    idx = [tk.index(t) for t in PARITE]
    R = np.zeros((T, len(idx)))
    R[1:] = P[1:, idx] / P[:-1, idx] - 1.0
    cov = ewma_covariance(P[:, idx]) if cible is not None else None
    W = _core_matrix(T, tk)
    for t in range(FENETRE_VOL, T):
        vol = R[t - FENETRE_VOL + 1:t + 1].std(axis=0, ddof=1)
        if not np.all(vol > 0):
            continue
        w = (1.0 / vol) / (1.0 / vol).sum()
        if cible is not None:
            v = float(np.sqrt(max(w @ cov[t] @ w, 1e-16)))  # covariance EWMA annualisée (comme build_weights)
            w = w * min(cible / v, LEVIER_MAX)
        row = np.zeros(len(tk))
        row[idx] = w
        W[t] = row
    return W


def jours_tournant_de_mois(dates: list[str]) -> np.ndarray:
    """Vrai pour le dernier jour de bourse de chaque mois et les 3 premiers du mois suivant."""
    m = np.array([d[:7] for d in dates])
    out = np.zeros(len(dates), dtype=bool)
    for i in range(len(dates)):
        dernier = i + 1 < len(dates) and m[i + 1] != m[i]
        rang = 0
        while i - rang - 1 >= 0 and m[i - rang - 1] == m[i]:
            rang += 1
            if rang >= 3:
                break
        out[i] = dernier or rang < 3
    return out


def veilles_de_feries(dates: list[str]) -> np.ndarray:
    """Vrai pour une séance suivie d'un jour ouvré (lundi-vendredi) sans cotation."""
    from datetime import timedelta

    out = np.zeros(len(dates), dtype=bool)
    for i in range(len(dates) - 1):
        d, suivant = date.fromisoformat(dates[i]), date.fromisoformat(dates[i + 1])
        j = d + timedelta(days=1)
        while j < suivant:
            if j.weekday() < 5:
                out[i] = True
                break
            j += timedelta(days=1)
    return out


def poche_calendrier(P: np.ndarray, tk: list[str], jours: np.ndarray) -> np.ndarray:
    """Poche SPY détenue pour gagner le rendement des `jours` (position prise à la clôture de la veille),
    ramenée à 10 % de vol ex ante, rebalancement quotidien, 5 bps."""
    W = np.zeros_like(P)
    s = tk.index("SPY")
    W[:-1, s] = jours[1:].astype(float)
    W = _vol_target(W, P)
    return simulate(P, W, ETF_COST_BPS, rebalance_every=1).returns


def mesurer(P: np.ndarray, tk: list[str], dates: list[str], masques: dict, cible: float) -> tuple[dict, dict]:
    T = len(P)
    ref_sim = simulate(P, _production(P, tk), ETF_COST_BPS, rebalance_every=5)
    ref = ref_sim.returns
    mai_oct = np.array([5 <= int(d[5:7]) <= 10 for d in dates])
    socles = {
        "C1": ("Socle en parité de risque, même vol que le 60/40", "SPY TLT IEF TIP GLD DBC, inverse de la vol 252 j, levier ≤ 2.",
               socle_parite(P, tk, cible)),
        "C2": ("Socle en parité de risque, sans levier", "Mêmes six actifs, poids qui somment à 1.", socle_parite(P, tk, None)),
        "S3": ("« Sell in May » : actions du socle /2 de mai à octobre", "Bouman & Jacobsen (2002).",
               _core_matrix(T, tk, scale_equity=np.where(mai_oct, 0.5, 1.0))),
    }
    poches = {
        "S1": ("Tournant de mois (poche SPY, surcouche 0,5x)", "Dernier jour + 3 premiers jours du mois.", jours_tournant_de_mois(dates)),
        "S2": ("Veilles de jours fériés (poche SPY, surcouche 0,5x)", "Séance précédant un jour ouvré sans cotation.", veilles_de_feries(dates)),
    }
    res = {"REF": {"nom": "REF — Référence — production actuelle", "description": "Socle 60/40 + couche tendance.",
                   **{k: period_metrics(ref, ref_sim, m, 252) for k, m in masques.items()}}}
    series = {"REF": ref}
    for key, (nom, desc, core) in socles.items():
        sim = simulate(P, _production(P, tk, core=core), ETF_COST_BPS, rebalance_every=5)
        series[key] = sim.returns
        res[key] = {"nom": f"{key} — {nom}", "description": desc, **{k: period_metrics(sim.returns, sim, m, 252) for k, m in masques.items()},
                    "socle_brut_moyen": float(np.abs(core[WARMUP:]).sum(axis=1).mean())}
    for key, (nom, desc, jours) in poches.items():
        poche = poche_calendrier(P, tk, jours)
        combo = ref + OVERLAY * poche
        series[key] = combo
        res[key] = {"nom": f"{key} — {nom}", "description": desc, **{k: period_metrics(combo, None, m, 252) for k, m in masques.items()},
                    "poche_seule": {k: period_metrics(poche, None, m, 252) for k, m in masques.items()},
                    "part_des_jours": float(jours.mean()),
                    "correlation_poche_production": float(np.corrcoef(poche[WARMUP:], ref[WARMUP:])[0, 1])}
    return res, series


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import _campaign1_vol_target, load_presample

    t0 = time.time()
    cible = _campaign1_vol_target()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    d = np.array(dates)
    T = len(dates)
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]} · vol cible du socle {cible:.1%}", file=sys.stderr)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END
    res, series = mesurer(P, tk, dates, {"developpement": dev, "validation": val}, cible)

    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in tk])
    res0, _ = mesurer(P0, tk, pd_, {"echantillon_2001_2007": np.arange(len(pd_)) >= WARMUP}, cible)
    for k in res:
        res[k]["echantillon_2001_2007"] = res0[k]["echantillon_2001_2007"]
    print(f"mesures terminées ({time.time() - t0:.0f}s)", file=sys.stderr)

    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values()]
        except Exception as exc:
            print(f"campagne précédente illisible ({path.name}) : {exc}", file=sys.stderr)
    trial_sharpes = previous + [r["developpement"]["sharpe"] for k, r in res.items() if k != "REF"]
    ref = res["REF"]
    for key, r in res.items():
        r["dsr_developpement"] = deflated_sharpe(series[key][dev], trial_sharpes, 252)
        if key == "REF":
            continue
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
            "echantillon_2001_2007": r["echantillon_2001_2007"]["sharpe"] >= ref["echantillon_2001_2007"]["sharpe"] - RULES["val_tol"],
        }
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "parametres": {"actifs_parite": list(PARITE), "fenetre_vol": FENETRE_VOL, "levier_max_socle": LEVIER_MAX,
                             "vol_cible_socle": cible, "surcouche": OVERLAY, "socle_reference": CORE},
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais (campagnes 1, 2, 4, 6, 7 et 8)")
    print(f"{'Essai':<58} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL DD':>7} {'VAL CAGR':>8} {'01-07':>6}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va, pr = r["developpement"], r["validation"], r["echantillon_2001_2007"]
        print(f"{r['nom'][:58]:<58} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['max_dd']:>7.1%} "
              f"{va['cagr']:>8.1%} {pr['sharpe']:>6.2f}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
