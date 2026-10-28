"""BULL : percentiles et moyennes mobiles du thermomètre de bulle (hors réseau)."""

import unittest

import numpy as np

from gambit_ridge.equity.bulle import _mensuel, _mm, percentile


class TestBulle(unittest.TestCase):
    def test_percentile(self):
        h = np.arange(100.0)
        self.assertAlmostEqual(percentile(h, 50.0), 0.5)
        self.assertEqual(percentile(h, 1000.0), 1.0)
        self.assertEqual(percentile(h, -1.0), 0.0)
        self.assertAlmostEqual(percentile(np.array([1.0, np.nan, 3.0]), 2.0), 0.5)

    def test_moyenne_mobile_causale(self):
        x = np.arange(10.0)
        m = _mm(x, 3)
        self.assertTrue(np.isnan(m[:2]).all())
        self.assertAlmostEqual(m[2], 1.0)
        self.assertAlmostEqual(m[-1], 8.0)
        # causale : ajouter des points après t ne change pas m[t]
        self.assertTrue(np.allclose(_mm(x[:6], 3)[2:], m[2:6]))

    def test_mensuel_garde_le_dernier_point(self):
        d, v = _mensuel(["2026-01-02", "2026-01-30", "2026-02-03"], np.array([1.0, 2.0, 3.0]))
        self.assertEqual(d, ["2026-01", "2026-02"])
        self.assertEqual(v, [2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
