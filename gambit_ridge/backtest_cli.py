"""CLI de backtest : performance longue période + stress crises + walk-forward.

Sources de données :
  real  : Polygon (2 ans réels, plan gratuit — limité)
  fred  : FRED décennal officiel (gratuit, ~10 ans large / ~55 ans long)
  synth : historique synthétique ~40 ans avec crises intégrées
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from .backtest.engine import BacktestConfig, BacktestEngine
from .backtest.strategies import (
    combine_strategies,
    mean_reversion_weight_fn,
    momentum_weight_fn,
    multi_factor_weight_fn,
    pairs_trading_weight_fn,
    regime_filtered_momentum,
    risk_managed_momentum,
)
from .backtest.stress import CrisisWindow, run_stress_tests
from .backtest.walkforward import run_walkforward
from .data.synthetic_history import crisis_year_windows, generate_synthetic_history


def _strategy_registry(horizon: str) -> dict[str, callable]:
    """Retourne les stratégies adaptées à la longueur d'historique."""
    short = horizon == "short"   # ~480 bars (2 ans Polygon)
    medium = horizon == "medium"  # ~2400 bars (10 ans FRED)
    k = 21 if short else 63
    vol_thr = 0.35 if short else (0.25 if medium else 0.30)
    return {
        "momentum": lambda: momentum_weight_fn(lookback=k, n_positions=3),
        "meanrev": lambda: mean_reversion_weight_fn(
            lookback=15 if short else 30, z_threshold=1.5
        ),
        "multifactor": lambda: multi_factor_weight_fn(
            mom_lookback=k,
            mr_lookback=15 if short else 20,
            trend_lookback=k,
            n_positions=4,
        ),
        "regime-momentum": lambda: regime_filtered_momentum(
            mom_lookback=90,
            n_positions=4,
            vol_lookback=30,
            vol_threshold=0.15,
        ),
        "risk-managed": lambda: risk_managed_momentum(
            mom_lookback=90,
            n_positions=4,
            vol_lookback=30,
            vol_threshold=0.15,
            use_correlation_filter=False,
            port_target_vol=0.15,
        ),
        "pairs-tech": lambda: pairs_trading_weight_fn(
            pair=("SP500", "NASDAQCOM"),
            lookback=40 if short else 60,
            entry_z=2.0,
            max_weight=0.4,
        ),
        "combo": lambda: combine_strategies(
            multi_factor_weight_fn(mom_lookback=k, mr_lookback=15 if short else 20),
            risk_managed_momentum(
                mom_lookback=90,
                n_positions=4,
                vol_lookback=30,
                vol_threshold=0.15,
                use_correlation_filter=False,
            ),
            weights=[0.6, 0.4],
        ),
    }


def _load_prices(source: str):
    if source == "real":
        from .data.loader import load_backtest_universe

        return load_backtest_universe("2024-09-01", "2026-09-01"), "short"
    if source == "fred":
        from .data.fred_loader import load_fred_universe

        return load_fred_universe(), "medium"
    if source == "fred-long":
        from .data.fred_loader import load_fred_long_universe

        return load_fred_long_universe(), "long"
    return generate_synthetic_history(), "long"


def _fmt_metrics(m) -> str:
    return (
        f"  Rendement total : {m.total_return:>10.1%}   CAGR : {m.cagr:>7.2%}\n"
        f"  Volatilité      : {m.volatility:>10.2%}   Sharpe : {m.sharpe:>7.2f}\n"
        f"  Sortino         : {m.sortino:>10.2f}   Calmar : {m.calmar:>7.2f}\n"
        f"  Max drawdown    : {m.max_drawdown:>10.2%}   VaR95 : {m.var_95:>7.2%}\n"
        f"  Win rate        : {m.win_rate:>10.1%}   Profit factor : {m.profit_factor:>7.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest Gambit Ridge Capital")
    parser.add_argument(
        "--strategy",
        default="multifactor",
        help="momentum | meanrev | multifactor | regime-momentum | pairs-tech | combo | all",
    )
    parser.add_argument(
        "--data",
        choices=["synth", "real", "fred", "fred-long"],
        default="fred",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    prices, horizon = _load_prices(args.data)
    registry = _strategy_registry(horizon)

    wf_params = {
        "short": {"train_periods": 240, "test_periods": 120, "step_periods": 60},
        "medium": {"train_periods": 1000, "test_periods": 500, "step_periods": 250},
        "long": {"train_periods": 504, "test_periods": 126, "step_periods": 126},
    }[horizon]

    selected = list(registry) if args.strategy == "all" else [args.strategy]
    engine = BacktestEngine(BacktestConfig())
    results = {}
    for name in selected:
        if name not in registry:
            print(f"stratégie inconnue: {name}", file=sys.stderr)
            return 1
        results[name] = engine.run(prices, registry[name]())

    labels = {
        "synth": "synthétique 40 ans",
        "real": "Polygon réel 2 ans",
        "fred": "FRED réel ~10 ans (6 actifs)",
        "fred-long": "FRED réel ~55 ans (Nasdaq + JPY)",
    }

    if args.json:
        payload = {
            "data": args.data,
            "strategies": {n: {"full": r.metrics.__dict__} for n, r in results.items()},
            "walkforward": {
                n: {
                    "folds": len(wf.per_fold),
                    "is_sharpe_mean": float(np.mean(wf.is_sharpes)),
                    "oos_sharpe_mean": float(np.mean(wf.oos_sharpes)),
                    "degradation": wf.degradation,
                }
                for n in results
                for wf in [
                    run_walkforward(prices, lambda tr, _n=n: registry[_n](), **wf_params)
                ]
            },
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    print("=" * 72)
    print(
        f"  BACKTEST — {len(results)} stratégie(s) — {labels[args.data]}"
    )
    print("=" * 72)
    for name, res in results.items():
        print(f"\n── {name} " + "─" * max(0, 60 - len(name)))
        print(_fmt_metrics(res.metrics))

    print("\n" + "-" * 72)
    print("WALK-FORWARD (OOS uniquement)")
    wf_by_name = {}
    for name in results:
        wf = run_walkforward(
            prices, lambda tr, _n=name: registry[_n](), **wf_params
        )
        wf_by_name[name] = wf
        print(
            f"  {name:<18} folds {len(wf.per_fold):3d}   "
            f"IS {np.mean(wf.is_sharpes):+.2f}   OOS {np.mean(wf.oos_sharpes):+.2f}   "
            f"dég. {wf.degradation:+.2f}"
        )

    print("\n" + "-" * 72)
    print("STRESS TESTS")
    if args.data in ("real", "fred", "fred-long"):
        # Crises datées résolues sur les dates réelles de la série (biais B2 corrigé)
        dated_windows = None
        try:
            from .backtest.stress import resolve_crisis_windows
            if args.data in ("fred", "fred-long"):
                from .data.fred_loader import load_fred_universe_with_dates
                _, common_dates = load_fred_universe_with_dates()
            else:
                from .data.loader import load_backtest_universe_with_dates
                _, common_dates = load_backtest_universe_with_dates("2024-09-01", "2026-09-01")
            dated_windows = resolve_crisis_windows(common_dates)
        except Exception:
            dated_windows = None
        for name in results:
            res = results[name]
            eq = res.equity
            peak = np.maximum.accumulate(eq)
            dd = (eq - peak) / peak
            trough = int(np.argmin(dd))
            pre = max(0, trough - 60)
            stress = engine.run(
                {tk: s[pre : trough + 1] for tk, s in prices.items()},
                registry[name](),
            )
            m = stress.metrics
            print(
                f"  {name:<18} drawdown principal : rendement {m.total_return:+7.1%}   "
                f"max DD {m.max_drawdown:7.1%}   Sharpe {m.sharpe:+.2f}"
            )
            if dated_windows:
                for w in dated_windows:
                    sres = run_stress_tests(prices, registry[name](), [w]).get(w.name)
                    if sres is None:
                        continue
                    wm = sres.metrics
                    print(
                        f"    {w.name:<26} rendement {wm.total_return:+7.1%}   "
                        f"max DD {wm.max_drawdown:7.1%}   Sharpe {wm.sharpe:+.2f}"
                    )
    else:
        windows = [CrisisWindow(n, s, e) for n, s, e in crisis_year_windows()]
        for name in results:
            print(f"  [{name}]")
            for wname, sres in run_stress_tests(prices, registry[name](), windows).items():
                m = sres.metrics
                print(
                    f"    {wname:<28} rendement {m.total_return:+7.1%}   "
                    f"max DD {m.max_drawdown:7.1%}   Sharpe {m.sharpe:+.2f}"
                )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
