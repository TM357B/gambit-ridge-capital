"""Campagne de recherche n° 4 (octobre 2026) — construction du portefeuille et exécution.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Référence : la stratégie ETF de production (« 60/40 + couche tendance », 20 ETF,
socle 50 %, filtre anti micro-trades 25 % / 0,5 %, rebalancement tous les 5 jours).
Les signaux ne changent pas : seules la construction et l'exécution varient.

Essais (8) :
  P1 Rebalancement quotidien (avec le filtre) — proche du moteur live, qui
     réajuste en séance dès que l'écart dépasse le filtre
  P2 Rebalancement mensuel (21 jours)
  P3 Filtre anti micro-trades élargi (50 % de la cible / 1 % du capital)
  P4 Sans filtre anti micro-trades
  P5 Socle 60/40 réduit : 30 % du capital (couche tendance 70 %)
  P6 Socle 60/40 renforcé : 70 % du capital (couche tendance 30 %)
  P7 Contrôle du drawdown : exposition divisée par 2 quand la baisse depuis
     le plus haut dépasse 10 %, rétablie quand elle repasse sous 5 %
     (calculé sur la performance réalisée de la stratégie, causal)
  P8 Plafond par classe d'actifs : la couche tendance ne peut pas dépasser
     40 % de son exposition brute dans une même classe (actions, obligations,
     matières premières, devises)

Périodes, coûts, règle d'acceptation : identiques aux campagnes 1 à 3
(développement -> 2019-12-31, validation 2020 -> aujourd'hui, 5 bps ;
Sharpe dév. >= réf. + 0,05, DSR >= 0,90, Sharpe validation >= réf. - 0,05,
pire baisse validation pas plus de 3 points au-delà de la réf.).

Tests multiples : le Deflated Sharpe Ratio est calculé sur TOUS les Sharpe de
développement des campagnes 1, 2 et 4 (univers ETF) — 32 séries au total
(compte corrigé après exécution : l'annonce initiale de 35 était une erreur de calcul) —
et non sur les seuls essais de cette campagne.
Un essai accepté n'entre au portefeuille qu'avec l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign4
Sortie : data/research_campaign4_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import signals as sg
from .backtest import deflated_sharpe, period_metrics, simulate
from .campaign import RULES, _classes, _core_matrix, _trend_parts
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP, apply_buffer, core_plus_overlay
from .portfolio import build_weights, ewma_covariance

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign4_2026-10.json"
PREVIOUS = [ROOT / "data" / "research_campaign_2026-10.json", ROOT / "data" / "research_campaign2_2026-10.json"]


def _class_cap(W: np.ndarray, classes: list[str], cap: float = 0.40) -> np.ndarray:
    """Plafonne l'exposition brute de chaque classe à `cap` de l'exposition brute totale."""
    out = W.copy()
    groups = {c: [j for j, x in enumerate(classes) if x == c] for c in set(classes)}
    for t in range(len(W)):
        for _ in range(50):  # point fixe : la part de chaque classe dans le brut FINAL <= cap
            gross = np.abs(out[t]).sum()
            over = [idx for idx in groups.values() if np.abs(out[t, idx]).sum() > cap * gross * (1 + 1e-9)]
            if gross <= 0 or not over:
                break
            for idx in over:
                out[t, idx] *= cap * gross / np.abs(out[t, idx]).sum()
    return out


def _drawdown_control(returns: np.ndarray, cut: float = 0.10, restore: float = 0.05) -> np.ndarray:
    """Facteur d'exposition causal (décidé à t avec la performance réalisée jusqu'à t)."""
    scale = np.ones(len(returns))
    eq, peak, reduced = 1.0, 1.0, False
    for t in range(len(returns)):
        eq *= 1.0 + returns[t] * (0.5 if reduced else 1.0)
        peak = max(peak, eq)
        dd = 1.0 - eq / peak
        if not reduced and dd > cut:
            reduced = True
        elif reduced and dd < restore:
            reduced = False
        scale[t] = 0.5 if reduced else 1.0
    return scale


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned

    t0 = time.time()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    T = len(dates)
    vol, cov = sg.garch_vol(P), ewma_covariance(P)
    trend = build_weights(_trend_parts(P), vol, cov)
    core = _core_matrix(T, tk)
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]} ({time.time() - t0:.0f}s)", file=sys.stderr)

    def prod(core_share=0.5, rel=0.25, abs_min=0.005, every=5, buffer=True, trend_w=trend):
        W = core_plus_overlay(core, trend_w, core_share=core_share)
        return apply_buffer(W, rel=rel, abs_min=abs_min, every=every) if buffer else W

    # chaque essai : (nom, description, poids cibles, période de rebalancement)
    trials = {
        "REF": ("Référence — production actuelle", "Socle 50 %, filtre 25 % / 0,5 %, tous les 5 jours.", prod(), 5),
        "P1": ("Rebalancement quotidien", "Filtre appliqué chaque jour (proche du moteur live).", prod(every=1), 1),
        "P2": ("Rebalancement mensuel", "Tous les 21 jours.", prod(every=21), 21),
        "P3": ("Filtre anti micro-trades élargi", "50 % de la cible / 1 % du capital.", prod(rel=0.5, abs_min=0.01), 5),
        "P4": ("Sans filtre anti micro-trades", "Cible appliquée telle quelle.", prod(buffer=False), 5),
        "P5": ("Socle réduit à 30 %", "Couche tendance 70 %.", prod(core_share=0.3), 5),
        "P6": ("Socle renforcé à 70 %", "Couche tendance 30 %.", prod(core_share=0.7), 5),
        "P8": ("Plafond de 40 % par classe d'actifs", "Sur la couche tendance.", prod(trend_w=_class_cap(trend, _classes(tk))), 5),
    }
    ref_rets = simulate(P, trials["REF"][2], ETF_COST_BPS, rebalance_every=5).returns
    scale = _drawdown_control(ref_rets)
    trials["P7"] = ("Contrôle du drawdown (-10 % / -5 %)", "Exposition /2 au-delà de 10 % de baisse, rétablie sous 5 %.",
                    trials["REF"][2] * scale[:, None], 5)  # même cadence que la référence : seul le contrôle change

    d = np.array(dates)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END
    res, sims = {}, {}
    for key in ["REF", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"]:
        name, desc, W, every = trials[key]
        sim = simulate(P, W, ETF_COST_BPS, rebalance_every=every)
        sims[key] = sim
        res[key] = {"nom": f"{key} — {name}", "description": desc,
                    "developpement": period_metrics(sim.returns, sim, dev, 252),
                    "validation": period_metrics(sim.returns, sim, val, 252)}
    previous = []
    for path in PREVIOUS:
        try:
            previous += [r["developpement"]["sharpe"] for r in json.loads(path.read_text())["resultats"].values()]
        except Exception as exc:
            print(f"campagne précédente illisible ({path.name}) : {exc}", file=sys.stderr)
    trial_sharpes = previous + [r["developpement"]["sharpe"] for k, r in res.items() if k != "REF"]
    ref = res["REF"]
    for key, r in res.items():
        r["dsr_developpement"] = deflated_sharpe(sims[key].returns[dev], trial_sharpes, 252)
        if key == "REF":
            continue
        checks = {
            "gain_developpement": r["developpement"]["sharpe"] >= ref["developpement"]["sharpe"] + RULES["dev_gain"],
            "dsr": r["dsr_developpement"] >= RULES["dsr"],
            "validation_non_contredite": r["validation"]["sharpe"] >= ref["validation"]["sharpe"] - RULES["val_tol"],
            "drawdown_validation": r["validation"]["max_dd"] >= ref["validation"]["max_dd"] - RULES["dd_tol"],
        }
        r["criteres"] = {k: bool(v) for k, v in checks.items()}
        r["verdict"] = "ACCEPTÉ" if all(checks.values()) else "REJETÉ"
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES,
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais (campagnes 1, 2 et 4)")
    print(f"{'Essai':<48} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL CAGR':>8} {'VAL DD':>7} {'TO/an':>6} {'coûts/an':>8}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va = r["developpement"], r["validation"]
        print(f"{r['nom'][:48]:<48} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['cagr']:>8.1%} "
              f"{va['max_dd']:>7.1%} {va.get('turnover_annuel', 0):>6.1f} {va.get('couts_annuels', 0):>8.2%}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
