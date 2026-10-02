"""Service de backtest pour le dashboard.

Réutilise le moteur, le walk-forward et les sources de données du package.
`synth` fonctionne 100% offline ; `fred` va chercher l'historique réel.
"""

from __future__ import annotations

import numpy as np

from .backtest.engine import BacktestConfig, BacktestEngine
from .backtest.walkforward import run_walkforward
from .backtest_cli import _load_prices, _strategy_registry

MAX_CURVE_POINTS = 400


def _downsample(values: np.ndarray, max_points: int = MAX_CURVE_POINTS) -> list[float]:
    n = len(values)
    if n <= max_points:
        return [float(v) for v in values]
    idx = np.linspace(0, n - 1, max_points, dtype=int)
    return [float(values[i]) for i in idx]


def _fx_registry() -> dict[str, callable]:
    """Stratégies forex (données FRED 6 paires + taux 3M, ~24 ans).

    Attention : aucune n'a validé de edge OOS positif au 2026-09 — elles
    sont fournies pour exploration, pas pour production.
    """
    from .backtest.fx_strategies import carry_weight_fn, stat_arb_fx_weight_fn
    from .data.fred_fx import PAIR_LEGDS, load_fx_universe

    prices, rates = load_fx_universe()
    pairs_legs = dict(PAIR_LEGDS)
    return prices, {
        "fx-carry": lambda: carry_weight_fn(pairs_legs, rates),
        "fx-statarb": lambda: stat_arb_fx_weight_fn(),
        "fx-carry-trend": lambda: _carry_trend_fn(pairs_legs, rates),
    }


def _carry_trend_fn(pairs_legs: dict, rates: dict):
    from .backtest.fx_strategies import carry_trend_weight_fn

    return carry_trend_weight_fn(pairs_legs, rates)


def _binance_registry() -> tuple[dict, dict]:
    """Stratégies adaptées au régime crypto (vol élevée, 24/7, ~1000 bars)."""
    from .backtest.strategies import (
        momentum_weight_fn,
        regime_filtered_momentum,
        risk_managed_momentum,
    )
    from .data.binance import BINANCE_SYMBOLS, BinanceConnector

    conn = BinanceConnector()
    prices = {}
    for tk in BINANCE_SYMBOLS:
        _, closes, _ = conn.fetch_klines(tk, "1d", 1000)
        if len(closes) >= 900:
            prices[tk] = closes.tolist()
    n_min = min((len(v) for v in prices.values()), default=0)
    prices = {tk: v[-n_min:] for tk, v in prices.items()}
    return prices, {
        "crypto-momentum": lambda: momentum_weight_fn(lookback=63, n_positions=5),
        "crypto-regime": lambda: regime_filtered_momentum(
            mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.60
        ),
        "crypto-risk-managed": lambda: risk_managed_momentum(
            mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.60,
            use_correlation_filter=False,
        ),
    }


def _equities_registry() -> tuple[dict, dict]:
    """Univers actions cotées du portefeuille fondamental (Yahoo local)."""
    import csv
    from pathlib import Path
    csv_path = Path(__file__).resolve().parent.parent / "data" / "equity_prices.csv"
    if not csv_path.exists():
        raise ValueError("data/equity_prices.csv absent — lancez scripts/fetch_equity_prices.py")
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    tickers = [t for t in rows[0] if t != "date"]
    series = {tk: [] for tk in tickers}
    dates = []
    for r in rows:
        dates.append(r["date"])
        for tk in tickers:
            v = r.get(tk, "")
            series[tk].append(float(v) if v else None)
    # aligne sur la première date où tous les prix existent sauf PLTR (IPO tardif)
    core = [t for t in tickers if t != "PLTR"]
    start = 0
    for i in range(len(dates)):
        if all(series[t][i] is not None for t in core):
            start = i
            break
    prices = {}
    for t in tickers:
        col = series[t][start:]
        # forward-fill des trous éventuels
        filled, last = [], None
        for v in col:
            if v is not None:
                last = v
            filled.append(last)
        # PLTR n'existe qu'à partir de son IPO : on ne garde que la partie non-NaN
        if filled[0] is None:
            first_idx = next((i for i, v in enumerate(filled) if v is not None), None)
            if first_idx is None:
                continue
            filled = filled[first_idx:]
        prices[t] = filled
    n_min = min(len(v) for v in prices.values())
    prices = {t: v[-n_min:] for t, v in prices.items()}
    from .backtest.strategies import (
        momentum_weight_fn,
        regime_filtered_momentum,
        risk_managed_momentum,
    )
    return prices, {
        "equities-momentum": lambda: momentum_weight_fn(lookback=90, n_positions=3),
        "equities-regime": lambda: regime_filtered_momentum(
            mom_lookback=90, n_positions=3, vol_lookback=30, vol_threshold=0.40
        ),
        "equities-risk-managed": lambda: risk_managed_momentum(
            mom_lookback=90, n_positions=3, vol_lookback=30, vol_threshold=0.40,
            use_correlation_filter=False,
        ),
    }


def run_backtest(strategy: str, data: str) -> dict:
    """Exécute un backtest complet (full + walk-forward) et retourne un dict JSON-sérialisable."""
    if data in ("fred-fx", "binance", "equities"):
        if data == "equities":
            prices, registry = _equities_registry()
        elif data == "fred-fx":
            prices, registry = _fx_registry()
        else:
            prices, registry = _binance_registry()
        horizon = "long"
        if strategy not in registry and strategy != "all":
            raise ValueError(f"stratégie inconnue: {strategy}")
        selected = list(registry) if strategy == "all" else [strategy]
        wf_params = {"train_periods": 504, "test_periods": 126, "step_periods": 126}
        engine = BacktestEngine(BacktestConfig())
        strategies = {}
        for name in selected:
            res = engine.run(prices, registry[name]())
            wf = run_walkforward(
                prices, lambda tr, _n=name: registry[_n](), **wf_params
            )
            eq = res.equity / res.equity[0] * 100.0
            strategies[name] = {
                "metrics": res.metrics.__dict__,
                "equity_curve": _downsample(eq),
                "walkforward": {
                    "folds": len(wf.per_fold),
                    "is_sharpe_mean": float(np.mean(wf.is_sharpes)),
                    "oos_sharpe_mean": float(np.mean(wf.oos_sharpes)),
                    "degradation": wf.degradation,
                },
            }
        return {
            "strategy": strategy,
            "data": data,
            "n_periods": len(next(iter(prices.values()))),
            "n_assets": len(prices),
            "strategies": strategies,
        }

    prices, horizon = _load_prices(data)
    registry = _strategy_registry(horizon)
    if strategy not in registry and strategy != "all":
        raise ValueError(f"stratégie inconnue: {strategy}")

    wf_params = {
        "short": {"train_periods": 240, "test_periods": 120, "step_periods": 60},
        "medium": {"train_periods": 1000, "test_periods": 500, "step_periods": 250},
        "long": {"train_periods": 504, "test_periods": 126, "step_periods": 126},
    }[horizon]

    engine = BacktestEngine(BacktestConfig())
    selected = list(registry) if strategy == "all" else [strategy]
    strategies = {}
    for name in selected:
        res = engine.run(prices, registry[name]())
        wf = run_walkforward(prices, lambda tr, _n=name: registry[_n](), **wf_params)
        eq = res.equity / res.equity[0] * 100.0
        strategies[name] = {
            "metrics": res.metrics.__dict__,
            "equity_curve": _downsample(eq),
            "walkforward": {
                "folds": len(wf.per_fold),
                "is_sharpe_mean": float(np.mean(wf.is_sharpes)),
                "oos_sharpe_mean": float(np.mean(wf.oos_sharpes)),
                "degradation": wf.degradation,
            },
        }

    n_periods = len(next(iter(prices.values())))
    return {
        "strategy": strategy,
        "data": data,
        "n_periods": n_periods,
        "n_assets": len(prices),
        "strategies": strategies,
    }


AVAILABLE_STRATEGIES = [
    "momentum",
    "meanrev",
    "multifactor",
    "regime-momentum",
    "risk-managed",
    "pairs-tech",
    "combo",
    "all",
]

AVAILABLE_DATA = ["synth", "fred", "fred-long", "real", "fred-fx", "binance", "equities"]

FX_STRATEGIES = ["fx-carry", "fx-statarb", "fx-carry-trend"]
