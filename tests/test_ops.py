"""Tests de l'exploitation : contrôles qualité, clôtures, valorisation, attribution."""

import unittest
from datetime import date, datetime, timezone

import numpy as np

from gambit_ridge.data.yahoo import complete_cutoff
from gambit_ridge.research.quality import check_sleeve


def _series(n=400, last_jump=0.0, flat_tail=0):
    p = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0, 0.01, n))
    if flat_tail:
        p[-flat_tail:] = p[-flat_tail - 1]
    p[-1] = p[-2] * (1 + last_jump) if last_jump else p[-1]
    return p


class TestQuality(unittest.TestCase):
    def test_clean_data_passes(self):
        issues, bad = check_sleeve("etf", ["2026-09-30"], {"SPY": _series()}, today=date(2026, 10, 1))
        self.assertEqual((issues, bad), ([], set()))

    def test_stale_source_blocks_everything(self):
        issues, bad = check_sleeve("etf", ["2026-09-01"], {"SPY": _series(), "TLT": _series()}, today=date(2026, 10, 1))
        self.assertTrue(issues)
        self.assertEqual(bad, {"SPY", "TLT"})

    def test_jump_and_frozen_prices_flagged(self):
        _, bad = check_sleeve("etf", ["2026-09-30"], {"A": _series(last_jump=0.40), "B": _series(flat_tail=6), "C": _series()}, today=date(2026, 10, 1))
        self.assertEqual(bad, {"A", "B"})


class TestCloseRules(unittest.TestCase):
    def test_us_close(self):
        before = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)   # 15 h New York
        after = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)    # 17 h New York
        self.assertEqual(complete_cutoff("SPY", before), "2026-09-30")
        self.assertEqual(complete_cutoff("SPY", after), "2026-10-01")

    def test_weekend_rolls_back_to_friday(self):
        sunday = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(complete_cutoff("SPY", sunday), "2026-10-02")
        self.assertEqual(complete_cutoff("BTC-USD", sunday), "2026-10-03")  # crypto : 7 j/7


class TestMarkToMarket(unittest.TestCase):
    def test_suspect_price_not_used_and_weights_drift(self):
        from gambit_ridge.paper import _mark_to_market

        j = {"equity_history": [{"equity": 1_000_000.0}],
             "positions": {"SPY": {"weight": 0.5, "last_price": 100.0}, "TLT": {"weight": 0.5, "last_price": 100.0}}}
        before, after, attrib = _mark_to_market(j, {"SPY": 110.0, "TLT": 1000.0}, skip={"TLT"})
        self.assertAlmostEqual(after - before, 50_000.0)
        self.assertAlmostEqual(attrib["SPY"], 50_000.0)
        self.assertEqual(attrib["TLT"], 0.0)
        self.assertEqual(j["positions"]["TLT"]["last_price"], 100.0)  # prix suspect ignoré
        self.assertAlmostEqual(j["positions"]["SPY"]["weight"], 0.55 / 1.05)


if __name__ == "__main__":
    unittest.main()
