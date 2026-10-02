import os
"""Tests du connecteur FRED et des univers décennaux."""

import unittest

import numpy as np

from gambit_ridge.data.fred import FredConnector
from gambit_ridge.data.fred_loader import (
    load_fred_universe,
    load_fred_long_universe,
)


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (FRED)")
class TestFredConnector(unittest.TestCase):
    def test_fetch_nasdaq(self):
        c = FredConnector()
        dates, values = c.fetch_series("NASDAQCOM")
        self.assertGreater(len(dates), 5000)
        self.assertEqual(len(dates), len(values))
        self.assertTrue(np.all(values > 0))
        self.assertEqual(dates[0], "1971-02-05")

    def test_cache_readback(self):
        c = FredConnector()
        d1, v1 = c.fetch_series("VIXCLS")
        d2, v2 = c.fetch_series("VIXCLS")
        self.assertEqual(d1, d2)
        self.assertTrue(np.array_equal(v1, v2))

    def test_missing_values_excluded(self):
        c = FredConnector()
        dates, values = c.fetch_series("DGS10")
        self.assertEqual(len(dates), len(values))
        self.assertTrue(np.all(np.isfinite(values)))


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (FRED)")
class TestFredUniverses(unittest.TestCase):
    def test_large_universe(self):
        u = load_fred_universe()
        self.assertGreaterEqual(len(u), 6)
        lengths = {len(s) for s in u.values()}
        self.assertEqual(len(lengths), 1)
        self.assertGreater(next(iter(lengths)), 2000)

    def test_long_universe(self):
        u = load_fred_long_universe()
        self.assertGreaterEqual(len(u), 2)
        lengths = {len(s) for s in u.values()}
        self.assertEqual(len(lengths), 1)
        self.assertGreater(next(iter(lengths)), 8000)
        for tk, s in u.items():
            if tk == "DCOILWTICO":
                # Avril 2020 : les contrats WTI ont réellement été négatifs
                self.assertTrue(np.all(s > -40))
            else:
                self.assertTrue(np.all(s > 0))


if __name__ == "__main__":
    unittest.main()
