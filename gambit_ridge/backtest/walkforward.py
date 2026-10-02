"""Validation walk-forward : anti data-snooping / overfitting.

Principe : on optimise les paramètres sur une fenêtre d'entraînement,
puis on teste sur la fenêtre suivante (out-of-sample), en avançant
d'un pas à chaque fois. Seule la performance out-of-sample compte.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .engine import BacktestEngine, BacktestResult
from .metrics import compute_metrics


@dataclass
class WalkForwardResult:
    oos_equity: list[float] = field(default_factory=list)
    oos_returns: list[float] = field(default_factory=list)
    per_fold: list[dict] = field(default_factory=list)
    is_sharpes: list[float] = field(default_factory=list)
    oos_sharpes: list[float] = field(default_factory=list)

    @property
    def degradation(self) -> float:
        """Ratio OOS/IS : < 0.5 signale un fort overfitting."""
        if not self.is_sharpes or not self.oos_sharpes:
            return 0.0
        is_mean = np.mean(self.is_sharpes)
        oos_mean = np.mean(self.oos_sharpes)
        if is_mean <= 0:
            return 0.0
        return float(oos_mean / is_mean)


def run_walkforward(
    prices: dict[str, np.ndarray],
    strategy_factory,
    *,
    train_periods: int = 504,
    test_periods: int = 126,
    step_periods: int = 126,
    embargo_periods: int = 0,
) -> WalkForwardResult:
    """Walk-forward avec ré-optimisation à chaque fold.

    strategy_factory(train_prices) -> weight_fn
    Le factory reçoit la fenêtre d'entraînement et doit renvoyer la
    fonction de poids (potentiellement avec des paramètres optimisés
    sur ces données uniquement).

    embargo_periods : gap purgé entre la fin du train et le début du
    test (Dixon, Halperin & Bilokon, chap. 7 — purged walk-forward).
    Sans embargo, les indicateurs à lookback long du début du test
    chevauchent la fin du train : fuite de données dès qu'un modèle
    supervisé est impliqué. On coupe la fin du train d'autant.
    """
    tickers = sorted(prices)
    n = len(prices[tickers[0]]) if tickers else 0
    engine = BacktestEngine()
    result = WalkForwardResult()

    start = 0
    while start + train_periods + test_periods <= n:
        train_slice = {
            tk: prices[tk][start : start + train_periods - embargo_periods]
            for tk in tickers
        }
        test_start = start + train_periods

        weight_fn = strategy_factory(train_slice)

        is_result = engine.run(train_slice, weight_fn)

        # OOS avec warm-up : la fenêtre test s'étend sur tout l'historique
        # connu à la date test_start (train inclus — il est bien dans le
        # passé du test), mais seules les métriques de la portion test
        # comptent. Sans cela, les stratégies à lookback long restent
        # flat pendant ~lookback jours au début de chaque fold, ce qui
        # écrase artificiellement le Sharpe OOS vers 0 (artefact de
        # warm-up, pas de la performance réelle).
        warmup_end = test_start + test_periods
        eval_slice = {
            tk: prices[tk][start:warmup_end] for tk in tickers
        }
        full_oos = engine.run(eval_slice, weight_fn)
        oos_returns = full_oos.returns[test_start - start :]
        oos_equity = full_oos.equity[test_start - start :]
        oos_metrics = compute_metrics(
            oos_equity, oos_returns, full_oos.trade_returns,
            engine.config.periods_per_year,
        )

        result.is_sharpes.append(is_result.metrics.sharpe)
        result.oos_sharpes.append(oos_metrics.sharpe)
        result.oos_equity.extend(oos_equity.tolist())
        result.oos_returns.extend(oos_returns.tolist())
        result.per_fold.append(
            {
                "train": [start, start + train_periods],
                "test": [test_start, test_start + test_periods],
                "is_sharpe": is_result.metrics.sharpe,
                "oos_sharpe": oos_metrics.sharpe,
                "oos_return": oos_metrics.total_return,
            }
        )

        start += step_periods

    return result
