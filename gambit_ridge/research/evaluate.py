"""Banc d'évaluation des stratégies — protocole figé AVANT de regarder les résultats.

Protocole :
- Univers ETF (20 instruments négociables, 4 classes d'actifs), 2007-04 -> aujourd'hui.
- Période de DÉVELOPPEMENT : début des signaux -> 2019-12-31. C'est la seule
  qui sert à choisir la stratégie retenue.
- Période de VALIDATION (holdout) : 2020-01-01 -> aujourd'hui. Jamais utilisée
  pour choisir ; rapportée telle quelle (COVID, inflation 2022, etc.).
- Paramètres fixés a priori (littérature), pas de grille d'optimisation.
- Coûts : 5 bps par unité de turnover sur ETF (commission + slippage),
  20 bps sur crypto. Rebalancement hebdomadaire. Dérive des poids modélisée.
- Multiple testing : Deflated Sharpe Ratio calculé sur l'ensemble des essais.

Usage : python3 -m gambit_ridge.research.evaluate [--skip-ml] [--crypto]
Sortie : data/research_report.json (lu par le dashboard).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from . import signals as sg
from .backtest import deflated_sharpe, period_metrics, simulate
from .portfolio import build_weights, ewma_covariance, risk_parity_long_only

REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "research_report.json"

ETF_COST_BPS = 5.0
CRYPTO_COST_BPS = 20.0
DEV_END = "2019-12-31"
CRYPTO_DEV_END = "2022-12-31"
WARMUP = 260


def _weights_from_weight_fn(P: np.ndarray, tickers: list[str], weight_fn, every: int = 5) -> np.ndarray:
    """Adapte une stratégie historique weight_fn(t, prix<=t) en matrice de poids."""
    T, N = P.shape
    W = np.zeros((T, N))
    last = np.zeros(N)
    for t in range(T):
        if t % every == 0:
            target = weight_fn(t, {tk: P[: t + 1, j] for j, tk in enumerate(tickers)})
            last = np.array([target.get(tk, 0.0) for tk in tickers])
        W[t] = last
    return W


def etf_candidates(dates, prices, include_ml: bool = True) -> dict[str, dict]:
    tickers = list(prices)
    P = np.column_stack([prices[t] for t in tickers])
    T, N = P.shape
    t0 = time.time()
    vol_ewma = sg.ewma_vol(P)
    vol_garch = sg.garch_vol(P)
    cov = ewma_covariance(P)
    print(f"  vol/cov : {time.time() - t0:.0f}s", file=sys.stderr)
    s_tsmom = sg.tsmom(P, 252)
    s_ewma = sg.ewma_trend(P)
    t0 = time.time()
    s_kalman = sg.kalman_trend(P)
    print(f"  kalman : {time.time() - t0:.0f}s", file=sys.stderr)
    t0 = time.time()
    hmm_scale = sg.hmm_risk_scale(P)
    print(f"  hmm : {time.time() - t0:.0f}s", file=sys.stderr)
    s_ens = (s_tsmom + s_ewma + s_kalman) / 3.0

    idx = {t: i for i, t in enumerate(tickers)}
    C: dict[str, dict] = {}

    def add(name, W, famille, desc):
        C[name] = {"W": W, "famille": famille, "description": desc}

    W = np.zeros((T, N)); W[:, idx["SPY"]] = 1.0
    add("Benchmark — S&P 500 (SPY)", W, "benchmark", "100 % SPY, achat-conservation.")
    W = np.zeros((T, N)); W[:, idx["SPY"]] = 0.6; W[:, idx["IEF"]] = 0.4
    add("Benchmark — 60/40", W, "benchmark", "60 % SPY / 40 % Treasuries 7-10 ans, rebalancé.")
    add("Benchmark — Parité de risque", risk_parity_long_only(vol_ewma, cov), "benchmark",
        "Long-only, chaque actif à risque égal, vol cible 10 %.")

    from ..backtest.adaptive import adaptive_regime_momentum
    from ..backtest.strategies import risk_managed_momentum

    t0 = time.time()
    add("Existant — Regime-momentum v2", _weights_from_weight_fn(P, tickers, adaptive_regime_momentum()),
        "existant", "Momentum cross-sectionnel 42 j, 2 long / 2 short, crisis guard (v2 Mistral).")
    add("Existant — Risk-managed momentum",
        _weights_from_weight_fn(P, tickers, risk_managed_momentum(
            mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.15,
            use_correlation_filter=False, port_target_vol=0.15)),
        "existant", "Fallback actuel du paper trading actions.")
    print(f"  existants : {time.time() - t0:.0f}s", file=sys.stderr)
    if include_ml:
        from ..models.signals.strategy import ml_ranking_strategy
        t0 = time.time()
        add("Existant — Ridge ML (production)",
            _weights_from_weight_fn(P, tickers, ml_ranking_strategy(
                model="ridge", horizon=21, train_window=750, rebalance_every=5,
                n_positions=4, lam=10.0)),
            "existant", "Moteur actuel du paper trading : classement ridge cross-sectionnel.")
        print(f"  ridge : {time.time() - t0:.0f}s", file=sys.stderr)

    add("TSMOM 12 mois (vol EWMA)", build_weights(s_tsmom, vol_ewma, cov), "nouveau",
        "Signe du rendement 12 mois par actif, positions à risque égal, vol EWMA.")
    add("TSMOM 12 mois (vol GARCH)", build_weights(s_tsmom, vol_garch, cov), "nouveau",
        "Idem avec prévision de vol GARCH(1,1) — chap. 6 §2.9.")
    add("Tendance EWMA multi-vitesses", build_weights(s_ewma, vol_garch, cov), "nouveau",
        "Croisements de moyennes exponentielles 8/24, 16/48, 32/96 — chap. 6 §2.10.")
    add("Tendance Kalman", build_weights(s_kalman, vol_garch, cov), "nouveau",
        "Pente du log-prix filtrée (modèle niveau + pente), t-stat — chap. 7.")
    add("Ensemble tendance", build_weights(s_ens, vol_garch, cov), "nouveau",
        "Moyenne des 3 signaux (TSMOM, EWMA, Kalman), vol GARCH, vol cible 10 %.")
    add("Ensemble tendance + régime HMM", build_weights(s_ens, vol_garch, cov, risk_scale=hmm_scale), "nouveau",
        "Ensemble, exposition réduite quand le HMM filtré détecte le régime haute vol — chap. 7.")

    # Combinaisons socle de primes de risque + tendance (moyennage de modèles,
    # chap. 2 §7.5 : on ne parie pas sur un seul modèle).
    W_trend = build_weights(s_ens, vol_garch, cov)
    W_rp = C["Benchmark — Parité de risque"]["W"]
    W_6040 = C["Benchmark — 60/40"]["W"]
    add("Parité de risque + tendance", apply_buffer(rescale_to_vol(0.5 * W_rp + 0.5 * W_trend, cov)), "nouveau",
        "50/50 parité de risque et ensemble tendance, remis à 10 % de vol, filtre anti micro-trades.")
    add("60/40 + couche tendance", apply_buffer(core_plus_overlay(W_6040, W_trend)), "nouveau",
        "Socle 30 % SPY / 20 % IEF + 50 % d'ensemble tendance (vol 10 %), filtre anti micro-trades.")
    return C


def rescale_to_vol(W: np.ndarray, cov: np.ndarray, target: float = 0.10, max_gross: float = 2.0) -> np.ndarray:
    out = np.zeros_like(W)
    for t in range(len(W)):
        w = W[t]
        v = float(np.sqrt(max(w @ cov[t] @ w, 0.0)))
        if v > 0:
            w = w * target / v
        g = np.abs(w).sum()
        out[t] = w * min(1.0, max_gross / g) if g > 0 else w
    return out


def core_plus_overlay(W_core: np.ndarray, W_trend: np.ndarray, core_share: float = 0.5) -> np.ndarray:
    """Socle (poids notionnels) + couche tendance (déjà à vol cible)."""
    return core_share * W_core + (1.0 - core_share) * W_trend


def apply_buffer(W: np.ndarray, rel: float = 0.25, abs_min: float = 0.005, every: int = 5) -> np.ndarray:
    """Filtre anti micro-trades : un poids n'est modifié que si l'écart à la
    cible dépasse 25 % de la cible (ou 0,5 % du capital). Réduit les coûts
    sans changer l'exposition de fond."""
    out = np.zeros_like(W)
    cur = np.zeros(W.shape[1])
    for t in range(len(W)):
        if t % every == 0:
            tgt = W[t]
            move = np.abs(tgt - cur) > np.maximum(rel * np.abs(tgt), abs_min)
            cur = np.where(move, tgt, cur)
        out[t] = cur
    return out


def carry_section(etf_dates, etf_prices, etf_cands, retained: str) -> dict:
    """Carry de change G10 (research/carry.py) : seul, filtré par la tendance, et en
    surcouche (0,5x) de la stratégie ETF retenue. Mêmes périodes, même règle de sélection."""
    from .carry import carry_signal, carry_total_return_index, load_carry_data

    fdates, ccys, spot, rates = load_carry_data()
    TR = carry_total_return_index(spot, rates)
    vol, cov = sg.ewma_vol(TR), ewma_covariance(TR)
    S = carry_signal(rates)
    trend = (sg.tsmom(TR) + sg.ewma_trend(TR) + sg.kalman_trend(TR)) / 3.0
    variants = {"Carry G10": S, "Carry G10 filtré tendance": np.where(np.sign(trend) == -S, 0.0, S)}
    fd = np.array(fdates)
    fdev = (np.arange(len(fd)) >= WARMUP) & (fd <= DEV_END)
    fhold = fd > DEV_END
    P = np.column_stack([etf_prices[t] for t in etf_prices])
    base = simulate(P, etf_cands[retained]["W"], ETF_COST_BPS, rebalance_every=5).returns
    ed = np.array(etf_dates)
    edev = (np.arange(len(ed)) >= WARMUP) & (ed <= DEV_END)
    ehold = ed > DEV_END
    out = {}
    for name, sig in variants.items():
        W = build_weights(sig, vol, cov, port_vol=0.10, max_gross=3.0, max_position=1.0)
        sim = simulate(TR, W, 3.0, rebalance_every=5)
        out[name] = {"developpement": period_metrics(sim.returns, sim, fdev, 252),
                     "validation": period_metrics(sim.returns, sim, fhold, 252)}
        eq = np.cumprod(1.0 + sim.returns)
        idx = np.searchsorted(fd, ed, side="right") - 1
        ceq = np.where(idx >= 0, eq[np.clip(idx, 0, None)], np.nan)
        cr = np.zeros(len(ed))
        cr[1:] = ceq[1:] / ceq[:-1] - 1.0
        comb = base + 0.5 * np.nan_to_num(cr)
        out[f"{retained} + 0,5× {name}"] = {"developpement": period_metrics(comb, None, edev, 252),
                                             "validation": period_metrics(comb, None, ehold, 252)}
    ref = period_metrics(base, None, edev, 252)["sharpe"]
    best = max(out, key=lambda n: out[n]["developpement"]["sharpe"])
    verdict = ("REJETÉ — aucune variante n'améliore le Sharpe de développement de la stratégie retenue "
               f"({ref:.2f})" if out[best]["developpement"]["sharpe"] <= ref else f"À ÉTUDIER — {best} bat la référence en développement")
    return {"debut": fdates[WARMUP], "fin": fdates[-1], "devises": ccys, "resultats": out, "reference_dev_sharpe": ref, "verdict": verdict,
            "methode": "Terme de change roulé (spot + différentiel de taux / 252), taux 3 mois OCDE avec 2 mois de retard de publication, long 3 / short 3 devises, risque égal, vol 10 %, coûts 3 bps."}


def crypto_candidates(dates, prices) -> dict[str, dict]:
    tickers = list(prices)
    P = np.column_stack([prices[t] for t in tickers])
    T, N = P.shape
    vol = sg.ewma_vol(P)
    vol_g = sg.garch_vol(P)
    cov = ewma_covariance(P)
    s_ens = (sg.tsmom(P, 252) + sg.ewma_trend(P) + sg.kalman_trend(P)) / 3.0
    s_long = np.clip(s_ens, 0, None)  # pas de short crypto (financement, borrow)
    from ..backtest.strategies import regime_filtered_momentum

    C: dict[str, dict] = {}
    W = np.zeros((T, N)); W[:, tickers.index("BTC-USD")] = 1.0
    C["Benchmark — Bitcoin"] = {"W": W, "famille": "benchmark", "description": "100 % BTC."}
    C["Existant — Crypto regime-momentum"] = {
        "W": _weights_from_weight_fn(P, tickers, regime_filtered_momentum(
            mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.60)),
        "famille": "existant", "description": "Fallback actuel de la poche crypto."}
    C["Tendance crypto long/short"] = {
        "W": build_weights(s_ens, vol_g, cov, port_vol=0.25, max_gross=1.0, max_position=0.5),
        "famille": "nouveau", "description": "Ensemble tendance (TSMOM, EWMA, Kalman), long et short, vol cible 25 %, brut <= 100 %."}
    C["Tendance crypto long-only"] = {
        "W": build_weights(s_long, vol_g, cov, port_vol=0.25, max_gross=1.0, max_position=0.5),
        "famille": "nouveau", "description": "Ensemble tendance (TSMOM, EWMA, Kalman), positions longues uniquement — cash quand la tendance est négative. Vol cible 25 %."}
    return C


def evaluate(dates, prices, cands, *, cost_bps, dev_end, ppy) -> dict:
    tickers = list(prices)
    P = np.column_stack([prices[t] for t in tickers])
    d = np.array(dates)
    dev = (np.arange(len(d)) >= WARMUP) & (d <= dev_end)
    hold = d > dev_end
    full = np.arange(len(d)) >= WARMUP
    sims = {n: simulate(P, c["W"], cost_bps, rebalance_every=5) for n, c in cands.items()}
    dev_sharpes = [period_metrics(s.returns, s, dev, ppy)["sharpe"] for s in sims.values()]
    ref_name = next((n for n in cands if "60/40" in n or "Bitcoin" in n), None)
    ref_vol = {k: np.std(sims[ref_name].returns[m], ddof=1) for k, m in (("dev", dev), ("val", hold))} if ref_name else {}
    out = {}
    for name, s in sims.items():
        equal_risk = {}
        for k, m in (("dev", dev), ("val", hold)):
            v = np.std(s.returns[m], ddof=1)
            if ref_vol and v > 0:
                scaled = s.returns[m] * ref_vol[k] / v
                yrs = m.sum() / ppy
                equal_risk[k] = float(np.prod(1 + scaled) ** (1 / yrs) - 1)
        eq = np.cumprod(1.0 + s.returns[full])
        step = max(1, len(eq) // 300)
        last_w = s.weights[-1]
        out[name] = {
            "famille": cands[name]["famille"],
            "description": cands[name]["description"],
            "developpement": period_metrics(s.returns, s, dev, ppy),
            "validation": period_metrics(s.returns, s, hold, ppy),
            "complet": period_metrics(s.returns, s, full, ppy),
            "dsr_developpement": deflated_sharpe(s.returns[dev], dev_sharpes, ppy),
            "reference_risque": ref_name,
            "cagr_risque_egal": equal_risk,
            "courbe": {"dates": [str(x) for x in d[full][::step]], "equity": [round(float(x), 4) for x in eq[::step]]},
            "poids_actuels": {tk: round(float(w), 4) for tk, w in zip(tickers, last_w) if abs(w) > 1e-4},
        }
    return out


def _print_table(title: str, res: dict) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(f"{'Stratégie':<36} {'DEV Sharpe':>10} {'DEV MaxDD':>9} {'DSR':>5} | {'VAL Sharpe':>10} {'VAL CAGR':>8} {'VAL MaxDD':>9} {'TO/an':>6}")
    for n, r in res.items():
        dv, va = r["developpement"], r["validation"]
        print(f"{n:<36} {dv['sharpe']:>10.2f} {dv['max_dd']:>9.1%} {r['dsr_developpement']:>5.2f} | "
              f"{va['sharpe']:>10.2f} {va['cagr']:>8.1%} {va['max_dd']:>9.1%} {va.get('turnover_annuel', 0):>6.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-ml", action="store_true", help="ne pas recalculer le ridge (lent)")
    ap.add_argument("--no-crypto", action="store_true")
    args = ap.parse_args()

    from ..data.yahoo import load_crypto_universe, load_etf_universe

    report = {"genere_le": date.today().isoformat(), "protocole": {
        "dev_fin": DEV_END, "crypto_dev_fin": CRYPTO_DEV_END,
        "couts_bps": {"etf": ETF_COST_BPS, "crypto": CRYPTO_COST_BPS},
        "rebalancement": "hebdomadaire", "selection": "sur la période de développement uniquement"}}

    dates, prices = load_etf_universe()
    print(f"ETF : {len(prices)} actifs, {dates[0]} -> {dates[-1]}", file=sys.stderr)
    cands = etf_candidates(dates, prices, include_ml=not args.skip_ml)
    report["etf"] = evaluate(dates, prices, cands, cost_bps=ETF_COST_BPS, dev_end=DEV_END, ppy=252)
    report["etf_univers"] = {"debut": dates[WARMUP], "fin": dates[-1], "actifs": list(prices)}
    _print_table("UNIVERS ETF — développement 2008-2019 | validation 2020-aujourd'hui", report["etf"])

    try:
        retained_etf = max((n for n, r in report["etf"].items() if r["famille"] == "nouveau"), key=lambda n: report["etf"][n]["developpement"]["sharpe"])
        report["carry"] = carry_section(dates, prices, cands, retained_etf)
        print("\nCARRY G10 :", report["carry"]["verdict"])
        for n, r in report["carry"]["resultats"].items():
            print(f"  {n:<58} DEV {r['developpement']['sharpe']:.2f} | VAL {r['validation']['sharpe']:.2f}")
    except Exception as exc:
        print("carry indisponible :", exc, file=sys.stderr)

    if not args.no_crypto:
        cdates, cprices = load_crypto_universe()
        ccands = crypto_candidates(cdates, cprices)
        report["crypto"] = evaluate(cdates, cprices, ccands, cost_bps=CRYPTO_COST_BPS,
                                    dev_end=CRYPTO_DEV_END, ppy=365)
        report["crypto_univers"] = {"debut": cdates[WARMUP], "fin": cdates[-1], "actifs": list(cprices)}
        _print_table("CRYPTO — développement 2018-2022 | validation 2023-aujourd'hui", report["crypto"])

    for key in ("etf", "crypto"):
        if key not in report:
            continue
        pool = {n: r for n, r in report[key].items() if r["famille"] == "nouveau"}
        best = max(pool, key=lambda n: pool[n]["developpement"]["sharpe"])
        for n, r in report[key].items():
            r["retenue"] = n == best
        report[f"{key}_retenue"] = best
        print(f"Retenue ({key}, sélection sur le développement uniquement) : {best}")

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"\nRapport : {REPORT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
