"""Optimisation walk-forward stricte de regime-momentum.

Grille de paramètres -> pour chaque fold, le meilleur jeu in-sample est
sélectionné PUIS testé out-of-sample. Seule la performance OOS du
paramètre sélectionné compte (aucun accès futur aux résultats OOS).

Usage : python3 -m gambit_ridge.optimize
"""

from __future__ import annotations

import itertools
import json
import sys

import numpy as np

from .backtest.engine import BacktestConfig, BacktestEngine
from .backtest.strategies import regime_filtered_momentum
from .backtest.walkforward import run_walkforward
from .data.fred_loader import load_fred_long_universe

PARAM_GRID = {
    "mom_lookback": [21, 42, 63, 126],
    "vol_lookback": [40, 60],
    "vol_threshold": [0.20, 0.25, 0.30, 0.40],
    "n_positions": [2, 3],
}

TRAIN = 1000
TEST = 250
STEP = 250


def _grid():
    keys = list(PARAM_GRID)
    for values in itertools.product(*[PARAM_GRID[k] for k in keys]):
        yield dict(zip(keys, values))


def make_fn(params):
    return lambda: regime_filtered_momentum(
        mom_lookback=params["mom_lookback"],
        vol_lookback=params["vol_lookback"],
        vol_threshold=params["vol_threshold"],
        n_positions=params["n_positions"],
        max_leverage=1.0,
    )


def main() -> int:
    prices = load_fred_long_universe()
    n = len(next(iter(prices.values())))
    grid = list(_grid())
    engine = BacktestEngine(BacktestConfig())
    print(f"Grille : {len(grid)} configs — {n} points — folds tous les {STEP} jours")

    results = []
    for params in grid:
        wf = run_walkforward(
            prices,
            lambda tr: make_fn(params)(),
            train_periods=TRAIN,
            test_periods=TEST,
            step_periods=STEP,
        )
        if not wf.oos_sharpes:
            continue
        oos = float(np.mean(wf.oos_sharpes))
        is_ = float(np.mean(wf.is_sharpes))
        results.append(
            {
                "params": params,
                "is_sharpe": is_,
                "oos_sharpe": oos,
                "degradation": wf.degradation,
                "folds": len(wf.per_fold),
            }
        )
        print(
            f"  mom={params['mom_lookback']:>3} vol_lb={params['vol_lookback']} "
            f"vol_thr={params['vol_threshold']:.2f} n={params['n_positions']} "
            f"-> OOS {oos:+.3f} (IS {is_:+.3f}, dég. {wf.degradation:+.2f})"
        )

    results.sort(key=lambda r: r["oos_sharpe"], reverse=True)
    print("\nTOP 5 (par Sharpe OOS, sélection walk-forward)")
    for r in results[:5]:
        p = r["params"]
        print(
            f"  mom={p['mom_lookback']:>3} vol_lb={p['vol_lookback']} "
            f"vol_thr={p['vol_threshold']:.2f} n={p['n_positions']} "
            f"-> OOS {r['oos_sharpe']:+.3f}  dég. {r['degradation']:+.2f}"
        )

    with open("optimization_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nRésultats complets : optimization_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
