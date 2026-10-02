"""Tests Phase 3 : allocation RL (chap. 9-10) — G-learning et Q-learning."""
import unittest

import numpy as np

from gambit_ridge.models.allocation import GLearningAllocator, QLearningAllocator
from gambit_ridge.models.allocation.strategy import rl_ranking_strategy
from gambit_ridge.backtest.engine import BacktestEngine


def _make_data(seed=1, n=800, k=6):
    rng = np.random.default_rng(seed)
    drift = rng.normal(0.0003, 0.0002, k)
    vol = rng.uniform(0.008, 0.02, k)
    rets = rng.normal(drift[:, None], vol[:, None], (k, n))
    return {f"A{i}": 100 * np.cumprod(1 + rets[i]) for i in range(k)}


def _fake_probs(n, k=3, seed=0):
    rng = np.random.default_rng(seed)
    P = rng.dirichlet(np.ones(k), size=n)
    return P


class TestGLearning(unittest.TestCase):
    def test_fit_act_shapes(self):
        r = np.random.default_rng(2).normal(0.0002, 0.01, 500)
        P = _fake_probs(500)
        g = GLearningAllocator().fit(r, P)
        self.assertTrue(g.fitted)
        lev = g.act(P[-1], 0.5)
        self.assertLessEqual(abs(lev), 1.0)

    def test_high_vol_reduces_leverage(self):
        r = np.random.default_rng(3).normal(0.0001, 0.03, 500)
        P = _fake_probs(500, seed=3)
        g = GLearningAllocator(lambda_risk=50.0).fit(r, P)
        # régime le plus volatil vs le plus calme
        order = np.argsort(g.vol_by_regime)
        calm = np.zeros(3); calm[order[0]] = 1.0
        wild = np.zeros(3); wild[order[-1]] = 1.0
        self.assertLess(g.act(wild, 0.0), g.act(calm, 0.0) + 0.2)

    def test_unfitted_returns_zero(self):
        self.assertEqual(GLearningAllocator().act(np.ones(3) / 3, 0.0), 0.0)


class TestQLearning(unittest.TestCase):
    def test_fit_act(self):
        r = np.random.default_rng(4).normal(0.0003, 0.012, 600)
        P = _fake_probs(600, seed=4)
        q = QLearningAllocator().fit(r, P)
        self.assertTrue(q.fitted)
        lev = q.act(P[-1], 0.01, 0.0)
        self.assertIn(lev, [-1.0, -0.5, 0.0, 0.5, 1.0])

    def test_unfitted_returns_zero(self):
        self.assertEqual(QLearningAllocator().act(np.ones(3) / 3, 0.01, 0.0), 0.0)

    def test_q_table_bounded(self):
        r = np.random.default_rng(5).normal(0.0005, 0.02, 800)
        P = _fake_probs(800, seed=5)
        q = QLearningAllocator().fit(r, P)
        self.assertTrue(np.all(np.isfinite(q.Q)))


class TestRLStrategy(unittest.TestCase):
    def test_fixed_leverage_runs(self):
        prices = _make_data()
        fn = rl_ranking_strategy(allocator="fixed", fixed_leverage=0.5)
        res = BacktestEngine().run(prices, fn)
        self.assertTrue(np.all(np.isfinite(res.equity)))

    def test_glearning_runs_and_finite(self):
        prices = _make_data(n=600)
        fn = rl_ranking_strategy(allocator="glearning")
        res = BacktestEngine().run(prices, fn)
        self.assertTrue(np.all(np.isfinite(res.equity)))
        self.assertTrue(np.all(res.equity > 0))

    def test_qlearning_runs_and_finite(self):
        prices = _make_data(n=600)
        fn = rl_ranking_strategy(allocator="qlearning")
        res = BacktestEngine().run(prices, fn)
        self.assertTrue(np.all(np.isfinite(res.equity)))
        self.assertTrue(np.all(res.equity > 0))


if __name__ == "__main__":
    unittest.main()
