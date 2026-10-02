"""Moteur de backtest décennal + stress tests des grandes crises financières."""

from .engine import BacktestConfig, BacktestResult, BacktestEngine
from .metrics import compute_metrics, PerformanceMetrics
from .stress import DATED_CRISES, DatedCrisis, resolve_crisis_windows, run_stress_tests
from .walkforward import WalkForwardResult, run_walkforward

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "BacktestEngine",
    "compute_metrics",
    "PerformanceMetrics",
    "DATED_CRISES",
    "DatedCrisis",
    "resolve_crisis_windows",
    "run_stress_tests",
    "WalkForwardResult",
    "run_walkforward",
]
