"""Tests du module research : causalité stricte des signaux + moteur."""

import unittest

import numpy as np

from gambit_ridge.research import signals as sg
from gambit_ridge.research.backtest import deflated_sharpe, probabilistic_sharpe, simulate
from gambit_ridge.research.portfolio import build_weights, ewma_covariance


def _prices(T=700, N=3, seed=1):
    rng = np.random.default_rng(seed)
    drift = np.array([0.0004, -0.0002, 0.0001])[:N]
    r = rng.normal(drift, 0.01, size=(T, N))
    return 100 * np.exp(np.cumsum(r, axis=0))


class TestCausality(unittest.TestCase):
    """signal(P[:t+1])[t] doit être identique à signal(P)[t] : aucune
    ligne ne dépend de données postérieures."""

    def _check(self, fn, P, cuts=(300, 450, 699)):
        full = fn(P)
        for t in cuts:
            part = fn(P[: t + 1])
            np.testing.assert_allclose(part[t], full[t], rtol=1e-9, atol=1e-12,
                                       err_msg=f"{fn.__name__} fuit à t={t}")

    def test_signals_causal(self):
        P = _prices()
        for fn in (sg.ewma_vol, sg.tsmom, sg.ewma_trend, sg.kalman_trend):
            self._check(fn, P)

    def test_garch_causal(self):
        P = _prices(T=650)
        self._check(lambda X: sg.garch_vol(X, min_history=500, refit_every=100), P, cuts=(520, 649))

    def test_hmm_causal(self):
        P = _prices(T=640)
        self._check(lambda X: sg.hmm_risk_scale(X, min_history=500, refit_every=100)[:, None], P, cuts=(560, 639))

    def test_covariance_causal(self):
        P = _prices()
        full = ewma_covariance(P)
        np.testing.assert_allclose(ewma_covariance(P[:401])[400], full[400])


class TestGarch(unittest.TestCase):
    def test_recovers_parameters(self):
        rng = np.random.default_rng(0)
        w, a, b = 2e-6, 0.08, 0.90
        n = 4000
        r = np.zeros(n)
        h = w / (1 - a - b)
        for t in range(1, n):
            h = w + a * r[t - 1] ** 2 + b * h
            r[t] = np.sqrt(h) * rng.normal()
        _, a_hat, b_hat = sg.fit_garch11(r)
        self.assertAlmostEqual(a_hat + b_hat, a + b, delta=0.03)
        self.assertLess(abs(a_hat - a), 0.04)


class TestSimulate(unittest.TestCase):
    def test_constant_weight_no_cost(self):
        P = _prices(T=200, N=1)
        W = np.ones((200, 1))
        res = simulate(P, W, 0.0, rebalance_every=1)
        eq = np.prod(1 + res.returns)
        self.assertAlmostEqual(eq, P[-1, 0] / P[0, 0], places=9)

    def test_costs_charged_on_turnover(self):
        P = np.ones((10, 2)) * 100
        W = np.zeros((10, 2)); W[0] = [0.5, -0.5]
        res = simulate(P, W, 10.0, rebalance_every=1)
        # entrée (1.0 de turnover) puis sortie (1.0) à 10 bps
        self.assertAlmostEqual(res.costs.sum(), 2 * 1.0 * 10 / 1e4)

    def test_vol_target(self):
        P = _prices(T=900)
        vol = sg.ewma_vol(P)
        cov = ewma_covariance(P)
        W = build_weights(np.ones_like(P), vol, cov, port_vol=0.10, max_gross=10, max_position=10)
        res = simulate(P, W, 0.0, rebalance_every=1)
        realised = res.returns[200:].std() * np.sqrt(252)
        self.assertAlmostEqual(realised, 0.10, delta=0.02)


class TestDeflatedSharpe(unittest.TestCase):
    def test_more_trials_lower_confidence(self):
        rng = np.random.default_rng(3)
        r = rng.normal(0.0004, 0.01, 2500)
        few = deflated_sharpe(r, [0.5, 0.3], 252)
        many = deflated_sharpe(r, list(rng.normal(0.3, 0.3, 50)), 252)
        self.assertGreater(probabilistic_sharpe(r), few)
        self.assertGreater(few, many)


if __name__ == "__main__":
    unittest.main()
