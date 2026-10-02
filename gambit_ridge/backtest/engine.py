"""Moteur de backtest vectorisé avec coûts de transaction réalistes.

Modèle simplifié mais honnête :
- Signaux calculés en fin de période t, exécutés à l'ouverture de t+1
  (pas de look-ahead bias)
- Coûts de transaction proportionnels appliqués sur le turnover
- Slippage modélisé comme coût additionnel
- Le noyau est vectorisé numpy ; l'orchestration reste en Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .metrics import PerformanceMetrics, compute_metrics


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    commission_bps: float = 2.0          # 2bps de commission
    slippage_bps: float = 5.0             # 5bps de slippage
    periods_per_year: int = 252
    risk_free_rate: float = 0.02


@dataclass
class BacktestResult:
    equity: np.ndarray
    returns: np.ndarray
    weights_history: np.ndarray
    metrics: PerformanceMetrics
    config: BacktestConfig
    trade_returns: list[float] = field(default_factory=list)


class BacktestEngine:
    """Backtest d'une stratégie à poids cibles.

    weight_fn(t, prices_until_t) -> dict[ticker, poids]
    Le moteur se charge de l'exécution, des coûts et de l'equity.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        prices: dict[str, np.ndarray],
        weight_fn,
    ) -> BacktestResult:
        """Exécute le backtest.

        prices : ticker -> série de prix (même longueur, alignés)
        """
        tickers = sorted(prices)
        if not tickers:
            raise ValueError("aucune série de prix fournie")
        n = len(prices[tickers[0]])
        if any(len(prices[t]) != n for t in tickers):
            raise ValueError("séries de prix non alignées")

        P = np.vstack([prices[t] for t in tickers])   # (assets, periods)
        R = np.zeros((n - 1, len(tickers)))
        R[:, :] = (P[:, 1:] / P[:, :-1]).T - 1.0

        capital = self.config.initial_capital
        equity = np.zeros(n)
        equity[0] = capital
        returns_arr = np.zeros(n - 1)
        weights_hist = np.zeros((n - 1, len(tickers)))
        trade_returns: list[float] = []

        prev_weights = np.zeros(len(tickers))
        cost_rate = (self.config.commission_bps + self.config.slippage_bps) / 10_000.0

        for t in range(n - 1):
            # Poids cibles calculés avec les données jusqu'à t inclus
            target = weight_fn(t, {tk: prices[tk][: t + 1] for tk in tickers})
            w = np.array([target.get(tk, 0.0) for tk in tickers])

            turnover = float(np.abs(w - prev_weights).sum())
            cost = turnover * cost_rate

            port_ret = float(np.dot(w, R[t]))
            net_ret = port_ret - cost
            capital *= 1.0 + net_ret

            equity[t + 1] = capital
            returns_arr[t] = net_ret
            weights_hist[t] = w
            if turnover > 0:
                trade_returns.append(net_ret)

            prev_weights = w

        metrics = compute_metrics(
            equity, returns_arr, trade_returns, self.config.periods_per_year
        )
        return BacktestResult(
            equity=equity,
            returns=returns_arr,
            weights_history=weights_hist,
            metrics=metrics,
            config=self.config,
            trade_returns=trade_returns,
        )
