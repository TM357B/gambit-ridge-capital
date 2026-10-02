"""Tests du moteur de backtest, des métriques et du walk-forward."""

import unittest

import numpy as np

from gambit_ridge.backtest.engine import BacktestConfig, BacktestEngine
from gambit_ridge.backtest.metrics import compute_metrics
from gambit_ridge.backtest.strategies import (
    mean_reversion_weight_fn,
    momentum_weight_fn,
)
from gambit_ridge.backtest.walkforward import run_walkforward
from gambit_ridge.data.synthetic_history import (
    SYNTHETIC_TICKERS,
    crisis_year_windows,
    generate_synthetic_history,
)


def _const_growth(n=300, rate=0.001):
    return 100.0 * np.cumprod(1.0 + np.full(n, rate))


class TestEngine(unittest.TestCase):
    def test_buy_hold_positive_drift_makes_money(self):
        """Sanity check : long sur un actif qui monte -> equity monte."""
        prices = {"UP": _const_growth(300, 0.001)}
        engine = BacktestEngine(BacktestConfig(commission_bps=0, slippage_bps=0))
        res = engine.run(prices, lambda t, ctx: {"UP": 1.0})
        self.assertGreater(res.metrics.total_return, 0.30)
        self.assertAlmostEqual(res.equity[-1] / res.equity[0], prices["UP"][-1] / prices["UP"][0], places=8)

    def test_costs_reduce_performance(self):
        prices = {"UP": _const_growth(300, 0.001)}
        free = BacktestEngine(BacktestConfig(commission_bps=0, slippage_bps=0))
        costly = BacktestEngine(BacktestConfig(commission_bps=50, slippage_bps=50))
        wf = lambda t, ctx: {"UP": 1.0 if t % 10 == 0 else 0.0}
        r_free = free.run(prices, wf)
        r_costly = costly.run(prices, wf)
        self.assertLess(r_costly.metrics.total_return, r_free.metrics.total_return)

    def test_zero_cost_no_trading_matches_hold(self):
        """Sans coûts ni trades, l'equity suit exactement l'actif."""
        growth = _const_growth(100, 0.005)
        prices = {"X": growth}
        engine = BacktestEngine(BacktestConfig(commission_bps=0, slippage_bps=0))
        res = engine.run(prices, lambda t, ctx: {"X": 1.0})
        self.assertTrue(np.allclose(res.equity, growth * (res.equity[0] / growth[0])))

    def test_misaligned_series_raises(self):
        with self.assertRaises(ValueError):
            BacktestEngine().run({"A": np.ones(100), "B": np.ones(90)}, lambda t, c: {})

    def test_flat_series_no_crash(self):
        prices = {"FLAT": np.full(50, 100.0)}
        res = BacktestEngine().run(prices, lambda t, c: {})
        self.assertEqual(res.metrics.total_return, 0.0)


class TestMetrics(unittest.TestCase):
    def test_metrics_on_known_series(self):
        equity = np.array([100.0, 110.0, 99.0, 105.0])
        returns = np.array([0.10, -0.10, 0.0606])
        m = compute_metrics(equity, returns, periods_per_year=252)
        self.assertAlmostEqual(m.total_return, 0.05, places=6)
        self.assertLess(m.max_drawdown, 0.0)
        self.assertAlmostEqual(m.var_95, np.percentile(returns, 5), places=6)

    def test_trade_stats(self):
        m = compute_metrics(np.array([100, 110]), np.array([0.1]), [0.1, -0.05, 0.02])
        self.assertAlmostEqual(m.win_rate, 2 / 3)
        self.assertGreater(m.profit_factor, 1.0)


class TestWalkForward(unittest.TestCase):
    def test_walkforward_runs(self):
        prices = generate_synthetic_history(n_years=4, seed=3)
        wf = momentum_weight_fn(lookback=21, n_positions=2)
        result = run_walkforward(
            prices, lambda train: wf, train_periods=500, test_periods=200, step_periods=200
        )
        self.assertGreater(len(result.per_fold), 0)
        test_len = 200
        self.assertEqual(len(result.oos_equity), len(result.per_fold) * test_len)
        self.assertEqual(len(result.oos_returns), len(result.per_fold) * (test_len - 1))


class TestSyntheticHistory(unittest.TestCase):
    def test_generation(self):
        prices = generate_synthetic_history(n_years=2, seed=1)
        self.assertEqual(set(prices), set(SYNTHETIC_TICKERS))
        for series in prices.values():
            self.assertEqual(len(series), 2 * 252 + 1)
            self.assertTrue(np.all(series > 0))

    def test_determinism(self):
        a = generate_synthetic_history(n_years=1, seed=5)
        b = generate_synthetic_history(n_years=1, seed=5)
        for tk in a:
            self.assertTrue(np.array_equal(a[tk], b[tk]))

    def test_crisis_drawdowns_exist(self):
        """Les crises simulées doivent produire de vrais drawdowns."""
        prices = generate_synthetic_history(n_years=40, seed=7)
        eq = prices["US_EQUITY"]
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak
        self.assertLess(dd.min(), -0.15)

    def test_crisis_windows_in_range(self):
        windows = crisis_year_windows()
        self.assertEqual(len(windows), 5)
        for _, start, end in windows:
            self.assertGreater(start, 0)
            self.assertLess(end, 40 * 252)


class TestStrategies(unittest.TestCase):
    def test_momentum_direction(self):
        up = np.linspace(100, 200, 60)
        down = np.linspace(100, 50, 60)
        fn = momentum_weight_fn(lookback=20, n_positions=1)
        w = fn(59, {"UP": up, "DOWN": down})
        self.assertGreater(w["UP"], 0)
        self.assertLess(w["DOWN"], 0)

    def test_mean_reversion_signal(self):
        series = np.concatenate([np.full(50, 100.0), [130.0]])
        fn = mean_reversion_weight_fn(lookback=30, z_threshold=1.5)
        w = fn(50, {"X": series})
        self.assertLess(w.get("X", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()


class TestWalkForwardWarmup(unittest.TestCase):
    """Régression : l'OOS doit voir l'historique de warm-up (train inclus),
    sinon les stratégies à lookback long restent flat et le Sharpe OOS
    s'effondre artificiellement vers 0 (artefact de warm-up)."""

    def test_oos_uses_warmup_history(self):
        prices = generate_synthetic_history(n_years=4, seed=5)
        wf = momentum_weight_fn(lookback=200, n_positions=2)  # lookback long
        result = run_walkforward(
            prices, lambda train: wf,
            train_periods=500, test_periods=200, step_periods=200,
        )
        self.assertGreater(len(result.per_fold), 0)
        # Sans warm-up, chaque fold OOS serait flat ~200 jours sur 200.
        # Avec le correctif, les rendements OOS ne sont pas tous nuls.
        oos = np.array(result.oos_returns)
        self.assertTrue(np.any(oos != 0.0))
