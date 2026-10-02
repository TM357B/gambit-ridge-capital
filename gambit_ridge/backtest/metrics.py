"""Métriques de performance standard de l'industrie."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PerformanceMetrics:
    total_return: float
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    profit_factor: float
    n_trades: int
    var_95: float
    cvar_95: float
    avg_holding_days: float


def compute_metrics(
    equity: np.ndarray,
    returns: np.ndarray,
    trade_returns: list[float] | None = None,
    periods_per_year: int = 252,
) -> PerformanceMetrics:
    """Calcule les métriques à partir d'une courbe d'equity.

    equity : valeurs du portefeuille (index 0 = départ)
    returns : rendements périodiques, len = len(equity) - 1
    """
    equity = np.asarray(equity, dtype=float)
    returns = np.asarray(returns, dtype=float)

    total_return = float(equity[-1] / equity[0] - 1.0)
    n_years = len(returns) / periods_per_year
    cagr = float((equity[-1] / equity[0]) ** (1.0 / n_years) - 1.0) if n_years > 0 else 0.0

    vol = float(np.std(returns, ddof=1)) * np.sqrt(periods_per_year)
    mean = float(np.mean(returns)) * periods_per_year
    sharpe = mean / vol if vol > 0 else 0.0

    downside = returns[returns < 0]
    downside_vol = (
        float(np.std(downside, ddof=1)) * np.sqrt(periods_per_year)
        if len(downside) > 1
        else 0.0
    )
    sortino = mean / downside_vol if downside_vol > 0 else 0.0

    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = float(np.min(dd))

    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    var95 = float(np.percentile(returns, 5))
    tail = returns[returns <= var95]
    cvar95 = float(np.mean(tail)) if len(tail) > 0 else var95

    trades = trade_returns or []
    if trades:
        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = len(wins) / len(trades)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        avg_hold = len(returns) / len(trades)
    else:
        win_rate, profit_factor, avg_hold = 0.0, 0.0, 0.0

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        volatility=vol,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        calmar=calmar,
        win_rate=win_rate,
        profit_factor=profit_factor,
        n_trades=len(trades),
        var_95=var95,
        cvar_95=cvar95,
        avg_holding_days=avg_hold,
    )
