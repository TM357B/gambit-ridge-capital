"""Tests des agents enrichis (macro FRED, crypto Binance, optimisation)."""

import unittest

import numpy as np

from gambit_ridge.core.agent import MarketData
from gambit_ridge.data.simulation import simulate_market_data
from gambit_ridge.teams.macro import MacroRegimeAgent, build_macro_team


class TestMacroRegimeAgent(unittest.TestCase):
    def _agent(self, factors):
        return MacroRegimeAgent(
            "macro-test",
            "test",
            ["SPY"],
            factors=factors,
            mom_lookback=20,
            mr_lookback=30,
        )

    def test_inverted_curve_reduces_long_conviction(self):
        factors = {"T10Y2Y": [-0.5], "VIXCLS": [14.0], "DGS10": [4.0] * 200}
        data = simulate_market_data(["SPY"], 90, 1)
        baseline = self._agent({}).analyze(data)
        shifted = self._agent(factors).analyze(data)
        base_long = {s.ticker: s.conviction for s in baseline.signals}
        for s in shifted.signals:
            if s.direction.value == "long":
                self.assertLess(s.conviction, base_long.get(s.ticker, 1.0))

    def test_high_vix_adds_contrarian_boost(self):
        factors = {"T10Y2Y": [0.5], "VIXCLS": [35.0], "DGS10": [4.0] * 200}
        agent = self._agent(factors)
        data = simulate_market_data(["SPY"], 90, 1)
        report = agent.analyze(data)
        self.assertGreater(report.context["regime_shift"], 0.0)
        self.assertTrue(any("VIX" in n for n in report.context["regime_notes"]))

    def test_neutral_regime(self):
        factors = {"T10Y2Y": [0.5], "VIXCLS": [20.0], "DGS10": [4.0] * 200}
        agent = self._agent(factors)
        data = simulate_market_data(["SPY"], 90, 1)
        report = agent.analyze(data)
        self.assertIn("régime macro neutre", report.context["regime_notes"])

    def test_build_macro_team_with_factors(self):
        team = build_macro_team({"VIXCLS": [15.0]})
        self.assertEqual(team.team, "Macro")
        self.assertEqual(len(team.agents), 2)
        self.assertIsInstance(team.agents[0], MacroRegimeAgent)


if __name__ == "__main__":
    unittest.main()
