"""Tests des stratégies enrichies de la bibliothèque."""

import unittest

import numpy as np

from gambit_ridge.backtest.strategies import (
    combine_strategies,
    mean_reversion_weight_fn,
    momentum_score,
    momentum_weight_fn,
    multi_factor_weight_fn,
    pairs_trading_weight_fn,
    realized_vol,
    regime_filtered_momentum,
    trend_quality,
)


def _trending(n=120, drift=0.002, vol=0.005, seed=1):
    rng = np.random.default_rng(seed)
    rets = drift + vol * rng.standard_normal(n)
    return 100.0 * np.cumprod(1 + rets)


def _mean_reverting(n=120, seed=2):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.9 * x[i - 1] + rng.standard_normal() * 2.0
    return 100.0 + x


class TestPrimitives(unittest.TestCase):
    def test_momentum_score_sign(self):
        up = _trending(120, drift=0.003)
        down = _trending(120, drift=-0.003)
        self.assertGreater(momentum_score(up, 60), 0)
        self.assertLess(momentum_score(down, 60), 0)

    def test_momentum_score_short_series(self):
        self.assertEqual(momentum_score(np.ones(5), 60), 0.0)

    def test_trend_quality(self):
        clean = np.exp(np.linspace(0, 1, 100))  # tendance parfaite
        noisy = 100 + np.random.default_rng(3).standard_normal(100) * 10
        self.assertGreater(trend_quality(clean, 99), 0.9)
        self.assertLess(abs(trend_quality(noisy, 99)), 0.9)

    def test_realized_vol_positive(self):
        arr = _trending(100, vol=0.02)
        self.assertGreater(realized_vol(arr, 60), 0.0)


class TestMultiFactor(unittest.TestCase):
    def test_selects_extremes(self):
        up = _trending(120, drift=0.004, seed=10)
        down = _trending(120, drift=-0.004, seed=11)
        flat = 100 + np.random.default_rng(12).standard_normal(120)
        fn = multi_factor_weight_fn(mom_lookback=63, mr_lookback=20, n_positions=1)
        w = fn(119, {"UP": up, "DOWN": down, "FLAT": flat})
        self.assertIn(w.get("UP", 0) > 0, (True,))
        self.assertLess(w.get("DOWN", 0), 0)

    def test_gross_exposure_bounded(self):
        data = {f"T{i}": _trending(120, seed=i) for i in range(8)}
        fn = multi_factor_weight_fn(n_positions=3, max_leverage=1.0)
        w = fn(119, data)
        gross = sum(abs(x) for x in w.values())
        self.assertLessEqual(gross, 1.0 + 1e-9)

    def test_vol_filter_excludes(self):
        calm = _trending(120, vol=0.005, seed=20)
        wild = _trending(120, vol=0.08, seed=21)
        fn = multi_factor_weight_fn(vol_filter=0.5, n_positions=2)
        w = fn(119, {"CALM": calm, "WILD": wild})
        self.assertNotIn("WILD", w)


class TestRegimeMomentum(unittest.TestCase):
    def test_reduces_size_in_high_vol(self):
        calm = _trending(120, drift=0.003, vol=0.005, seed=30)
        wild_up = _trending(120, drift=0.003, vol=0.05, seed=31)
        fn = regime_filtered_momentum(mom_lookback=63, n_positions=2, vol_threshold=0.3)
        w = fn(119, {"CALM": calm, "WILD": wild_up})
        if "CALM" in w and "WILD" in w:
            self.assertGreater(abs(w["CALM"]), abs(w["WILD"]))

    def test_bounds(self):
        data = {f"T{i}": _trending(120, seed=40 + i) for i in range(6)}
        fn = regime_filtered_momentum(mom_lookback=63, n_positions=2, max_leverage=1.0)
        w = fn(119, data)
        self.assertLessEqual(sum(abs(x) for x in w.values()), 1.0 + 1e-9)


class TestPairsTrading(unittest.TestCase):
    def test_entry_on_divergence(self):
        rng = np.random.default_rng(5)
        a = 100 * np.exp(np.cumsum(rng.standard_normal(120) * 0.01))
        # Choc haussier sur B : le ratio A/B chute -> z négatif -> long A, short B
        b = a[:-1].tolist() + [a[-1] * 1.10]
        b = np.array(b)
        fn = pairs_trading_weight_fn(pair=("A", "B"), lookback=60, entry_z=2.0)
        w = fn(119, {"A": a, "B": b})
        self.assertGreater(w.get("A", 0), 0)
        self.assertLess(w.get("B", 0), 0)

    def test_no_trade_when_converged(self):
        rng = np.random.default_rng(6)
        a = 100 * np.exp(np.cumsum(rng.standard_normal(120) * 0.01))
        b = a * 1.05
        fn = pairs_trading_weight_fn(pair=("A", "B"), lookback=60, entry_z=2.0)
        w = fn(119, {"A": a, "B": b})
        self.assertEqual(w, {})

    def test_missing_ticker(self):
        fn = pairs_trading_weight_fn(pair=("A", "B"), lookback=60)
        self.assertEqual(fn(119, {"A": np.ones(100)}), {})


class TestCombine(unittest.TestCase):
    def test_weights_mismatch_raises(self):
        with self.assertRaises(ValueError):
            combine_strategies(momentum_weight_fn(), mean_reversion_weight_fn(), weights=[0.5])

    def test_combines_outputs(self):
        up = _trending(120, drift=0.003, seed=50)
        down = _trending(120, drift=-0.003, seed=51)
        combo = combine_strategies(
            momentum_weight_fn(lookback=63, n_positions=1),
            mean_reversion_weight_fn(lookback=20),
            weights=[0.7, 0.3],
        )
        w = combo(119, {"UP": up, "DOWN": down})
        self.assertIsInstance(w, dict)


if __name__ == "__main__":
    unittest.main()
