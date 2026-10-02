"""Tests de la couche données : connecteurs, cache, alignement."""

import unittest

import numpy as np

from gambit_ridge.core.agent import MarketData
from gambit_ridge.data.simulation import simulate_market_data
from gambit_ridge.data.synthetic_history import generate_synthetic_history
from gambit_ridge.data.loader import align_series


class TestSimulation(unittest.TestCase):
    def test_market_data_stats(self):
        data = simulate_market_data(["BTC"], 120, 1)
        md = data["BTC"]
        self.assertEqual(len(md.prices), 121)
        rets = md.returns()
        self.assertEqual(len(rets), 120)
        self.assertGreater(md.volatility(), 0.0)
        self.assertTrue(all(p > 0 for p in md.prices))

    def test_zscore_finite(self):
        data = simulate_market_data(["GLD"], 60, 2)
        self.assertTrue(np.isfinite(data["GLD"].zscore(30)))


class TestSyntheticHistory(unittest.TestCase):
    def test_all_positive_and_same_length(self):
        prices = generate_synthetic_history(n_years=3, seed=2)
        lengths = {len(s) for s in prices.values()}
        self.assertEqual(len(lengths), 1)
        for s in prices.values():
            self.assertTrue(np.all(s > 0))


class TestAlign(unittest.TestCase):
    def test_align_truncates(self):
        series = {"A": np.arange(100.0), "B": np.arange(80.0)}
        aligned = align_series(series)
        self.assertEqual(len(aligned["A"]), 80)
        self.assertEqual(len(aligned["B"]), 80)


if __name__ == "__main__":
    unittest.main()
