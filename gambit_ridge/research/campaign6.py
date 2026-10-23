"""Campagne de recherche n° 6 (octobre 2026) — volatilité stochastique (Dixon, Halperin & Bilokon, ch. 7).

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Question : la couche tendance dimensionne chaque position par une prévision de volatilité
GARCH(1,1). Sur SPY (2023-2026), un modèle de volatilité stochastique avec effet de levier
(SVL), suivi par filtre particulaire, a une bien meilleure vraisemblance que la GARCH
(AIC meilleur de ~70 points ; fonction SVOL du terminal). Une meilleure prévision de vol
améliore-t-elle la stratégie ?

Référence : la stratégie ETF de production (« 60/40 + couche tendance », 20 ETF, socle 50 %,
filtre anti micro-trades 25 % / 0,5 %, rebalancement tous les 5 jours). Seule change la
prévision de volatilité passée à build_weights ; signaux, covariance, socle, coûts identiques.

Calibrage SANS FUITE : les paramètres (μ, φ, σ_v, ρ, et p, σ_J pour les sauts) de chaque actif
sont estimés UNE FOIS, par maximum de vraisemblance particulaire, sur l'échantillon 2000-09 ->
2007-04 des instruments proxys de la campagne 5 (même liste, research/campaign5.PROXY) — avant
le premier jour des données testées. Puis le filtre avance jour par jour sur 2007-2026 avec ces
paramètres fixes : la vol utilisée à la clôture t ne dépend que des rendements jusqu'à t
(même convention que garch_vol). Limite connue : les proxys contrats à terme sans ajustement de
roulement ajoutent des sauts artificiels au calibrage (la variante V2 les absorbe en partie).

Essais (3) :
  V1 SVL  : levier, sans sauts (4 paramètres)
  V2 SVLJ : levier + sauts (6 paramètres)
  V3 Moyenne de modèles (ch. 2 § 7.5) : variance = ½ variance GARCH + ½ variance SVL

Périodes, coûts, règle d'acceptation : identiques aux campagnes 1 à 4 (développement ->
2019-12-31 après 260 séances de rodage, validation 2020 -> aujourd'hui, 5 bps ; Sharpe dév.
>= réf. + 0,05 ; DSR >= 0,90 ; Sharpe validation >= réf. - 0,05 ; pire baisse validation pas
plus de 3 points au-delà de la réf.). La validation 2020-2026 ne sert qu'à vérifier qu'elle
ne contredit pas : elle ne choisit rien.

Tests multiples : DSR calculé sur tous les Sharpe de développement des campagnes 1, 2 et 4
plus les 3 essais de cette campagne. Un essai accepté n'entre au portefeuille qu'avec
l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign6
Sortie : data/research_campaign6_2026-10.json
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
from .campaign import RULES, _core_matrix, _production
from .campaign5 import load_presample
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign6_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4")]
M_CALIBRAGE, M_FILTRE = 300, 1000


def calibrer_presample(tickers: list[str]) -> dict:
    """Paramètres SVL et SVLJ de chaque actif, sur le seul échantillon 2000-2007 (proxys)."""
    from ..quant.particle import calibrer

    d, p = load_presample()
    out = {}
    for tk in tickers:
        y = np.diff(np.log(p[tk]))
        y = y[np.isfinite(y)]
        y = y - y.mean()
        svl, llh1, _ = calibrer(y, sauts=False, M=M_CALIBRAGE, iter_par_param=50)
        svlj, llh2, _ = calibrer(y, sauts=True, M=M_CALIBRAGE, iter_par_param=40)
        out[tk] = {"svl": [float(v) for v in svl], "svlj": [float(v) for v in svlj], "llh_svl": llh1, "llh_svlj": llh2,
                   "n": int(len(y))}
        print(f"  {tk:5s} φ={svl[1]:.3f} σv={svl[2]:.3f} ρ={svl[3]:+.2f} · sauts p={svlj[4]:.3f}", file=sys.stderr)
    return {"periode": [d[0], d[-1]], "parametres": out}


def vols_sv(P: np.ndarray, tickers: list[str], calib: dict, cle: str) -> np.ndarray:
    from ..quant.particle import vol_predictive

    r = sg.log_returns(P)
    V = np.empty_like(r)
    for j, tk in enumerate(tickers):
        mu, phi, sv, rho, pj, sj = calib["parametres"][tk][cle]
        y = np.nan_to_num(r[:, j])
        V[:, j] = vol_predictive(y, mu, phi, sv, rho, pj, sj, M=M_FILTRE, graine=11 + j)
    return V


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned

    t0 = time.time()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    T = len(dates)
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    print("calibrage SV sur 2000-2007 (proxys)…", file=sys.stderr)
    calib = calibrer_presample(tk)
    vol_g = sg.garch_vol(P)
    vol_svl = vols_sv(P, tk, calib, "svl")
    vol_svlj = vols_sv(P, tk, calib, "svlj")
    vol_moy = np.sqrt(0.5 * vol_g**2 + 0.5 * vol_svl**2)
    print(f"filtres terminés ({time.time() - t0:.0f}s)", file=sys.stderr)

    core = _core_matrix(T, tk)
    trials = {
        "REF": ("Référence — production actuelle (GARCH)", "Prévision de vol GARCH(1,1), réestimée chaque année.", vol_g),
        "V1": ("Vol stochastique SVL (levier)", "Filtre particulaire, paramètres 2000-2007.", vol_svl),
        "V2": ("Vol stochastique SVLJ (levier + sauts)", "Filtre particulaire, paramètres 2000-2007.", vol_svlj),
        "V3": ("Moyenne de modèles GARCH / SVL", "Variance = ½ GARCH + ½ SVL.", vol_moy),
    }
    d = np.array(dates)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END
    res, sims = {}, {}
    for key, (name, desc, vol) in trials.items():
        W = _production(P, tk, vol=vol, core=core)
        sim = simulate(P, W, ETF_COST_BPS, rebalance_every=5)
        sims[key] = sim
        res[key] = {"nom": f"{key} — {name}", "description": desc,
                    "developpement": period_metrics(sim.returns, sim, dev, 252),
                    "validation": period_metrics(sim.returns, sim, val, 252),
                    "vol_mediane_prevue": float(np.median(vol[WARMUP:]))}
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
    report = {"genere_le": date.today().isoformat(), "protocole": __doc__, "regles": RULES, "calibrage": calib,
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais (campagnes 1, 2, 4 et 6)")
    print(f"{'Essai':<48} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL CAGR':>8} {'VAL DD':>7}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va = r["developpement"], r["validation"]
        print(f"{r['nom'][:48]:<48} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['cagr']:>8.1%} "
              f"{va['max_dd']:>7.1%}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
