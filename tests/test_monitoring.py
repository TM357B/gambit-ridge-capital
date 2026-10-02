"""Tests : santé de la stratégie et contrôle croisé des prix."""

import unittest
from unittest import mock

import numpy as np

from gambit_ridge.monitoring import health as H
from gambit_ridge.data import crosscheck as X


def _journal(daily_returns):
    eq, hist = 1_000_000.0, []
    for i, r in enumerate(daily_returns):
        pnl = eq * r
        eq += pnl
        hist.append({"date": f"2026-10-{i + 1:02d}", "equity": eq, "day_pnl": pnl})
    return {"equity_history": hist}


REF = {"dates": [f"d{i}" for i in range(2000)], "returns": list(np.random.default_rng(1).normal(0.0004, 0.005, 2000))}


class TestHealth(unittest.TestCase):
    def _run(self, live):
        with mock.patch("gambit_ridge.paper._load_journal", return_value=_journal(live)), \
             mock.patch.object(H, "_reference", return_value=REF):
            return H.health()

    def test_too_early(self):
        self.assertEqual(self._run([0.001, 0.002])["status"], "trop tôt")

    def test_normal_week(self):
        self.assertEqual(self._run(list(np.random.default_rng(2).normal(0.0004, 0.005, 25)))["status"], "dans la norme")

    def test_crash_is_out_of_range(self):
        h = self._run([0.0] * 15 + [-0.04] * 5)
        self.assertEqual(h["status"], "hors norme")


class TestCrossCheck(unittest.TestCase):
    def test_disagreement_freezes_only_that_line(self):
        dates = ["2026-09-30", "2026-10-01"]
        prices = {"SPY": np.array([100.0, 101.0]), "TLT": np.array([50.0, 50.5])}
        ref = {"SPY": {"2026-09-30": 200.0, "2026-10-01": 202.0},       # +1 % : identique
               "TLT": {"2026-09-30": 80.0, "2026-10-01": 77.0}}        # -3,75 % contre +1 %
        with mock.patch("gambit_ridge.brokers.alpaca.has_credentials", return_value=True), \
             mock.patch.object(X, "alpaca_closes", return_value=ref):
            issues, bad = X.cross_check("etf", dates, prices)
        self.assertEqual(bad, {"TLT"})
        self.assertEqual(len(issues), 1)

    def test_no_credentials_skips(self):
        with mock.patch("gambit_ridge.brokers.alpaca.has_credentials", return_value=False):
            issues, bad = X.cross_check("etf", ["a", "b"], {"SPY": np.array([1.0, 2.0])})
        self.assertEqual(bad, set())
        self.assertIn("sauté", issues[0])


if __name__ == "__main__":
    unittest.main()
