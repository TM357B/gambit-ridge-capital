"""Backtest vectorisé à poids cibles, avec dérive des poids et coûts par actif.

Convention temporelle (identique au moteur historique) : la cible W[t] est
décidée à la clôture t avec les données <= t, et porte le rendement
P[t+1]/P[t] - 1. Différences de réalisme vs backtest/engine.py :
- entre deux rebalancements, les poids DÉRIVENT avec les prix (on ne
  suppose pas un rebalancement quotidien gratuit) ;
- coûts (commission + slippage) par actif, prélevés sur le turnover
  réellement exécuté (cible - poids dérivés).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, sqrt

import numpy as np

from ..backtest.metrics import compute_metrics


@dataclass
class SimResult:
    returns: np.ndarray      # (T,) rendement net du jour t (porté de t-1 à t)
    weights: np.ndarray      # (T, N) poids détenus après rebalancement à t
    turnover: np.ndarray     # (T,) turnover exécuté à t
    costs: np.ndarray        # (T,)


def simulate(
    P: np.ndarray,
    W_target: np.ndarray,
    cost_bps: np.ndarray | float,
    rebalance_every: int = 5,
    start: int = 0,
) -> SimResult:
    T, N = P.shape
    R = np.zeros((T, N))
    R[1:] = P[1:] / P[:-1] - 1.0
    cost = np.broadcast_to(np.asarray(cost_bps, dtype=float) / 1e4, (N,))
    W_target = np.nan_to_num(W_target)
    held = np.zeros(N)
    out_ret = np.zeros(T)
    out_w = np.zeros((T, N))
    out_to = np.zeros(T)
    out_cost = np.zeros(T)
    for t in range(start, T):
        if t > start:
            gross_ret = float(held @ R[t])
            out_ret[t] = gross_ret
            # dérive : chaque position évolue avec son actif, le cash au taux 0
            denom = 1.0 + gross_ret
            held = held * (1.0 + R[t]) / denom if denom > 1e-9 else held * 0.0
        if (t - start) % rebalance_every == 0:
            trade = W_target[t] - held
            c = float(np.abs(trade) @ cost)
            out_to[t] = float(np.abs(trade).sum())
            out_cost[t] = c
            out_ret[t] -= c  # coût payé à la clôture t, imputé au jour t
            held = W_target[t].copy()
        out_w[t] = held
    return SimResult(out_ret, out_w, out_to, out_cost)


def period_metrics(returns: np.ndarray, sim: SimResult | None, mask: np.ndarray, ppy: int) -> dict:
    r = returns[mask]
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    m = compute_metrics(eq, r, None, ppy)
    out = {
        "sharpe": m.sharpe,
        "cagr": m.cagr,
        "vol": m.volatility,
        "max_dd": m.max_drawdown,
        "sortino": m.sortino,
        "calmar": m.calmar,
        "cvar95": m.cvar_95,
        "n_days": int(mask.sum()),
    }
    if sim is not None:
        years = mask.sum() / ppy
        out["turnover_annuel"] = float(sim.turnover[mask].sum() / years) if years > 0 else 0.0
        out["gross_moyen"] = float(np.abs(sim.weights[mask]).sum(axis=1).mean())
        out["couts_annuels"] = float(sim.costs[mask].sum() / years) if years > 0 else 0.0
    return out


# ---------------------------------------------------------------------------
# Multiple testing : Probabilistic / Deflated Sharpe Ratio
# (Bailey & López de Prado, 2014)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse de la CDF normale (Acklam), précision ~1e-9."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    lo, hi = 0.02425, 1 - 0.02425
    if p < lo:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > hi:
        q = sqrt(-2 * log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def probabilistic_sharpe(returns: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """P(SR vrai > sr_benchmark) — SR en unités PAR PÉRIODE (non annualisé)."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 30 or r.std(ddof=1) == 0:
        return 0.0
    sr = r.mean() / r.std(ddof=1)
    z = (r - r.mean()) / r.std(ddof=0)
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    denom = sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, 1e-12))
    return _norm_cdf((sr - sr_benchmark) * sqrt(n - 1) / denom)


def deflated_sharpe(returns: np.ndarray, trial_sharpes: list[float], ppy: int) -> float:
    """DSR : PSR contre le Sharpe maximal ATTENDU parmi N essais sans edge.

    trial_sharpes : Sharpe annualisés de tous les essais comparés
    (y compris celui-ci). Plus on teste de variantes, plus la barre monte.
    """
    n_trials = max(len(trial_sharpes), 1)
    if n_trials == 1:
        return probabilistic_sharpe(returns, 0.0)
    var_sr = float(np.var(np.asarray(trial_sharpes) / sqrt(ppy), ddof=1))
    g = 0.5772156649
    sr0 = sqrt(max(var_sr, 1e-12)) * (
        (1 - g) * _norm_ppf(1 - 1.0 / n_trials) + g * _norm_ppf(1 - 1.0 / (n_trials * exp(1)))
    )
    return probabilistic_sharpe(returns, sr0)
