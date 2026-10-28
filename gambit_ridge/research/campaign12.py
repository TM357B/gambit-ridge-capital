"""Campagne de recherche n° 12 (octobre 2026) — un vrai hedge : couvrir le fonds avec les maths.

PROTOCOLE FIGÉ ET COMMITÉ AVANT TOUT CALCUL (pré-enregistrement) :

Question : le fonds n'a aucune couverture explicite. Sa protection vient de la couche tendance
(qui peut vendre) et des obligations du socle 60/40. Or le socle reste long actions en toute
circonstance (30 % SPY), et en 2022 les obligations ont baissé avec les actions. Une couverture
calculée — au sens des docs lus par l'araignée (scripts/araignee) — fait-elle mieux ?
  - ratio à variance minimale u* = Cov/Var (Dixon-Halperin-Bilokon, ch. 10, éq. 10.10) ;
  - couverture du bêta par contrat sur indice, contrats ≈ β × valeur / notionnel (Belghaieb,
    « Sales & Trading », p. 15) ; ici le contrat est représenté par une position vendeuse de SPY
    (le micro E-mini MES suit le S&P 500 ; base et financement négligés, coût 5 bps comme l'ETF) ;
  - protection par options (puts, collar) valorisées en Black-Scholes à la vol du VIX + skew ;
  - couverture minimisant la CVaR (Rockafellar-Uryasev).

Référence : la stratégie ETF de production (identique aux campagnes 7 à 9 : « 60/40 + couche
tendance », 20 ETF, rebalancement tous les 5 jours, 5 bps). Rien ne change dans la stratégie :
on AJOUTE une couche de couverture sur SPY.

Bêta du portefeuille β_t = Σ_j w_j,t β_j,t, avec w les poids cibles de production en t et β_j,t
le bêta EWMA (demi-vie 63 j) de chaque ETF contre SPY, causal. Couverture h_t (fraction de
l'actif vendue en SPY) : poids SPY ramené de w_SPY,t à w_SPY,t − h_t.

Essais (6), paramètres fixés par construction ou tirés de la littérature, AUCUNE grille :
  H1 Couverture partielle permanente : h = 0,5 β_t (on garde la moitié de la prime actions).
  H2 Couverture conditionnelle à la tendance : h = β_t si SPY < sa moyenne 200 j, sinon 0.
  H3 Couverture des corrélations en crise : h = β_t si la corrélation EWMA 63 j SPY-IEF > 0
     (les obligations ne couvrent plus les actions, cas de 2022), sinon 0.
  H4 Puts protecteurs : achat tous les 21 jours de puts SPY 5 % hors de la monnaie à 21 jours,
     notionnel max(β_t, 0) × actif, vol = VIX + 3 pts, frais 5 % de la prime, règlement en
     espèces à l'échéance.
  H5 Collar : H4 + vente de calls 5 % hors de la monnaie au même notionnel, vol = VIX − 2 pts.
  H6 Couverture à CVaR minimale : h_t = argmin CVaR 95 % de (r_ref − h r_SPY) sur les 252
     derniers jours, h ∈ [0, max(β_t, 0)] par pas de 0,05, réestimé tous les 5 jours.

Périodes et règle d'acceptation : identiques à la campagne 7 (5 critères) : développement
-> 2019-12-31 après 260 séances de rodage ; Sharpe dév. >= réf. + 0,05 ; DSR >= 0,90 ; Sharpe
validation >= réf. − 0,05 ; pire baisse validation pas plus de 3 points au-delà de la réf. ;
Sharpe 2001-2007 (proxys de la campagne 5) >= réf. − 0,05. Rapportés sans être des critères :
CVaR 95 % quotidienne, rendement et pire baisse dans les trois crises (2008-09-01 -> 2009-03-09,
2020-02-19 -> 2020-03-23, 2022-01-03 -> 2022-10-12), coût annuel de la couverture.

Tests multiples : DSR calculé sur tous les Sharpe de développement des campagnes 1, 2, 4, 6 et
7 plus les 6 essais de cette campagne. Un essai accepté n'entre au portefeuille qu'avec
l'accord de Tom.

Usage : python3 -m gambit_ridge.research.campaign12
Sortie : data/research_campaign12_2026-10.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from ..hedge import maths as hm
from .backtest import deflated_sharpe, period_metrics, simulate
from .campaign import RULES, _fred_on, _production
from .evaluate import DEV_END, ETF_COST_BPS, WARMUP

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "research_campaign12_2026-10.json"
PREVIOUS = [ROOT / "data" / f"research_campaign{n}_2026-10.json" for n in ("", "2", "4", "6", "7")]
DEMI_VIE, SMA = 63, 200
PART_H1 = 0.5
PUT_OTM, CALL_OTM, ECHEANCE = 0.05, 0.05, 21
SKEW_PUT, SKEW_CALL, FRAIS = 0.03, -0.02, 0.05
CVAR_FEN, CVAR_ALPHA, CVAR_PAS = 252, 0.95, 0.05
CRISES = {"2008": ("2008-09-01", "2009-03-09"), "covid": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-10-12")}


def rendements(P: np.ndarray) -> np.ndarray:
    R = np.full(P.shape, np.nan)
    R[1:] = P[1:] / P[:-1] - 1.0
    return R


def beta_portefeuille(W: np.ndarray, R: np.ndarray, j_spy: int) -> np.ndarray:
    """β_t = Σ_j w_j,t β_j,t (bêtas EWMA causaux contre SPY)."""
    B = hm.betas_ewma(R, R[:, j_spy], DEMI_VIE)
    return np.nansum(np.nan_to_num(W) * B, axis=1) * np.where(np.all(np.isnan(B), axis=1), np.nan, 1.0)


def moyenne_mobile(x: np.ndarray, n: int) -> np.ndarray:
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.full(len(x), np.nan)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def couvertures(P: np.ndarray, tk: list[str], dates: list[str]) -> dict:
    """Pour chaque essai : (nom, description, h_t ou None, overlay ou None)."""
    j = tk.index("SPY")
    R = rendements(P)
    W = _production(P, tk)
    beta = beta_portefeuille(W, R, j)
    bplus = np.maximum(np.nan_to_num(beta), 0.0)
    spy = P[:, j]
    tendance_baisse = spy < moyenne_mobile(spy, SMA)
    corr = hm.correlation_ewma(np.nan_to_num(R[:, j]), np.nan_to_num(R[:, tk.index("IEF")]), DEMI_VIE)
    vix = _fred_on(dates, "VIXCLS", lag_days=0)
    taux = _fred_on(dates, "DGS3MO", lag_days=1) / 100.0
    ref = simulate(P, W, ETF_COST_BPS, rebalance_every=5)
    h6 = hm.cvar_glissante_ratio(ref.returns, np.nan_to_num(R[:, j]), CVAR_FEN, CVAR_ALPHA, h_max=bplus, pas=CVAR_PAS)
    puts = hm.overlay_options(spy, vix, taux, bplus, otm_put=PUT_OTM, echeance=ECHEANCE, skew_put=SKEW_PUT, frais=FRAIS)
    collar = hm.overlay_options(spy, vix, taux, bplus, otm_put=PUT_OTM, otm_call=CALL_OTM, echeance=ECHEANCE,
                                skew_put=SKEW_PUT, skew_call=SKEW_CALL, frais=FRAIS)
    return {
        "W": W, "beta": beta, "j": j, "ref": ref,
        "essais": {
            "REF": ("Référence — production actuelle, sans couverture", "", None, None),
            "H1": ("Couverture permanente 0,5 β (variance minimale)", "Moitié du bêta vendue en contrat S&P 500.", PART_H1 * np.nan_to_num(beta), None),
            "H2": ("Couverture du bêta si SPY < moyenne 200 j", "Bêta entièrement couvert en tendance baissière.", np.where(tendance_baisse, np.nan_to_num(beta), 0.0), None),
            "H3": ("Couverture du bêta si corrélation SPY-IEF > 0", "Quand les obligations ne couvrent plus.", np.where(np.nan_to_num(corr) > 0, np.nan_to_num(beta), 0.0), None),
            "H4": ("Puts SPY 5 % hors de la monnaie, 1 mois", "Notionnel β, vol VIX + 3 pts, frais 5 %.", None, puts),
            "H5": ("Collar put −5 % / call +5 %, 1 mois", "Puts financés par la vente de calls.", None, collar),
            "H6": ("Couverture à CVaR 95 % minimale (252 j)", "h ∈ [0, β], Rockafellar-Uryasev.", np.nan_to_num(h6), None),
        },
    }


def _crises(r: np.ndarray, dates: list[str]) -> dict:
    d = np.array(dates)
    out = {}
    for k, (a, b) in CRISES.items():
        m = (d >= a) & (d <= b)
        if m.sum() < 5:
            continue
        nav = np.cumprod(1 + r[m])
        out[k] = {"rendement": float(nav[-1] - 1), "pire_baisse": float((nav / np.maximum.accumulate(nav) - 1).min())}
    return out


def mesurer(P, tk, dates, masques) -> tuple[dict, dict]:
    c = couvertures(P, tk, dates)
    res, rets = {}, {}
    for key, (nom, desc, h, ov) in c["essais"].items():
        if h is None and ov is None:
            sim, r = c["ref"], c["ref"].returns
        elif h is not None:
            W = c["W"].copy()
            W[:, c["j"]] -= h
            sim = simulate(P, W, ETF_COST_BPS, rebalance_every=5)
            r = sim.returns
        else:
            sim = c["ref"]
            r = c["ref"].returns + ov["rendements"]
        rets[key] = r
        res[key] = {"nom": f"{key} — {nom}", "description": desc,
                    **{k: period_metrics(r, sim, m, 252) for k, m in masques.items()},
                    "cvar95_jour": {k: hm.cvar(r[m], 0.95) for k, m in masques.items()},
                    "crises": _crises(r, dates),
                    "couverture_moyenne": float(np.mean(h[WARMUP:])) if h is not None else float(np.mean(np.maximum(np.nan_to_num(c["beta"][WARMUP:]), 0))),
                    }
        if ov is not None:
            res[key]["cout_annuel"] = float(np.sum(ov["rendements"][WARMUP:]) / max(len(dates) - WARMUP, 1) * 252)
    for key in res:
        if key != "REF":
            res[key]["cout_annuel_vs_ref"] = {k: res[key][k]["cagr"] - res["REF"][k]["cagr"] for k in masques if "cagr" in res[key][k]}
    return res, rets


def run() -> dict:
    from ..data.yahoo import all_etf_symbols, load_aligned
    from .campaign5 import load_presample

    t0 = time.time()
    dates, p = load_aligned(all_etf_symbols(), refresh=False)
    tk = list(p)
    P = np.column_stack([p[t] for t in tk])
    T = len(dates)
    d = np.array(dates)
    print(f"univers : {len(tk)} ETF, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    dev = (np.arange(T) >= WARMUP) & (d <= DEV_END)
    val = d > DEV_END
    res, rets = mesurer(P, tk, dates, {"developpement": dev, "validation": val})

    pd_, pp = load_presample()
    P0 = np.column_stack([pp[t] for t in tk])
    pre = np.arange(len(pd_)) >= WARMUP
    res0, _ = mesurer(P0, tk, pd_, {"echantillon_2001_2007": pre})
    for k in res:
        res[k]["echantillon_2001_2007"] = res0[k]["echantillon_2001_2007"]
        res[k]["crises"].update(res0[k]["crises"])
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
        r["dsr_developpement"] = deflated_sharpe(rets[key][dev], trial_sharpes, 252)
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
              "parametres": {"demi_vie_beta": DEMI_VIE, "sma": SMA, "part_h1": PART_H1, "put_otm": PUT_OTM, "call_otm": CALL_OTM,
                             "echeance": ECHEANCE, "skew_put": SKEW_PUT, "skew_call": SKEW_CALL, "frais_prime": FRAIS,
                             "cvar": {"fenetre": CVAR_FEN, "alpha": CVAR_ALPHA, "pas": CVAR_PAS}},
              "essais_comptes_dans_le_dsr": len(trial_sharpes), "duree_s": round(time.time() - t0), "resultats": res}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return report


def main() -> int:
    rep = run()
    print(f"\nDSR calculé sur {rep['essais_comptes_dans_le_dsr']} essais (campagnes 1, 2, 4, 6, 7 et 12)")
    print(f"{'Essai':<50} {'DEV Sh':>6} {'DSR':>5} {'VAL Sh':>6} {'VAL DD':>7} {'01-07':>6} {'CVaR v':>6} {'2008':>6} {'2020':>6} {'2022':>6}  Verdict")
    for k, r in rep["resultats"].items():
        dv, va, pr, cr = r["developpement"], r["validation"], r["echantillon_2001_2007"], r["crises"]
        c = lambda n: f"{cr[n]['rendement']:>6.1%}" if n in cr else f"{'—':>6}"
        print(f"{r['nom'][:50]:<50} {dv['sharpe']:>6.2f} {r['dsr_developpement']:>5.2f} {va['sharpe']:>6.2f} {va['max_dd']:>7.1%} "
              f"{pr['sharpe']:>6.2f} {r['cvar95_jour']['validation']:>6.2%} {c('2008')} {c('covid')} {c('2022')}  {r.get('verdict', 'référence')}")
    print(f"\nRapport : {OUT} ({rep['duree_s']} s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
