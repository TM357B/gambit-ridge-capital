"""Tests du cœur quantitatif et du conseil."""

import unittest

from gambit_ridge.core.risk import RiskLimits
from gambit_ridge.core.sizing import kelly_fraction, vol_target_size
from gambit_ridge.core.signal import Signal, SignalDirection, TimeHorizon
from gambit_ridge.data.simulation import all_configured_tickers, simulate_market_data
from gambit_ridge.demo import build_fund


class TestSizing(unittest.TestCase):
    def test_kelly_positive_edge(self):
        f = kelly_fraction(0.55, 1.3, fraction=0.25)
        self.assertGreater(f, 0.0)
        self.assertLess(f, 0.25)

    def test_kelly_no_edge(self):
        self.assertEqual(kelly_fraction(0.5, 1.0), 0.0)

    def test_kelly_invalid_ratio(self):
        self.assertEqual(kelly_fraction(0.6, 0.0), 0.0)

    def test_vol_target_bounds(self):
        self.assertEqual(vol_target_size(1.0, 0.5), 0.3)
        self.assertEqual(vol_target_size(10.0, 0.001), 3.0)
        self.assertEqual(vol_target_size(0.0, 0.2), 0.0)


class TestSignal(unittest.TestCase):
    def _signal(self, direction, conviction=0.5, confidence=0.8):
        return Signal(
            agent="t", ticker="X", direction=direction, conviction=conviction,
            confidence=confidence, horizon=TimeHorizon.SWING, thesis="",
        )

    def test_score_signs(self):
        self.assertGreater(self._signal(SignalDirection.LONG).score(), 0)
        self.assertLess(self._signal(SignalDirection.SHORT).score(), 0)
        self.assertEqual(self._signal(SignalDirection.NEUTRAL).score(), 0)

    def test_validation(self):
        s = self._signal(SignalDirection.LONG, conviction=1.5)
        self.assertTrue(s.validate())


class TestCouncil(unittest.TestCase):
    def test_full_meeting(self):
        council = build_fund()
        data = simulate_market_data(all_configured_tickers(), 90, 42)
        briefing = council.meeting(data)
        self.assertEqual(len(briefing.sections), 6)
        self.assertLessEqual(
            sum(abs(w) for w in briefing.proposed_allocation.values()),
            RiskLimits().max_total_gross + 1e-9,
        )
        self.assertTrue(all(w != 0 for w in briefing.proposed_allocation.values()))

    def test_determinism(self):
        data1 = simulate_market_data(["BTC"], 50, 7)
        data2 = simulate_market_data(["BTC"], 50, 7)
        self.assertEqual(data1["BTC"].prices, data2["BTC"].prices)


if __name__ == "__main__":
    unittest.main()
