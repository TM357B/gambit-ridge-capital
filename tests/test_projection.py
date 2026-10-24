"""Tests : projection par bootstrap et format des campagnes de recherche."""

import unittest

import numpy as np

from gambit_ridge import projection as P


class TestProjection(unittest.TestCase):
    def test_shape_and_base(self):
        r = np.random.default_rng(0).normal(0.0004, 0.005, 1500)
        eq = P.simulate(r, horizon=252, paths=200)
        self.assertEqual(eq.shape, (200, 253))
        self.assertTrue(np.all(eq[:, 0] == 1.0))

    def test_deterministic(self):
        r = np.random.default_rng(0).normal(0.0004, 0.005, 1500)
        self.assertTrue(np.array_equal(P.simulate(r, paths=50), P.simulate(r, paths=50)))

    def test_blocks_are_contiguous_history(self):
        # rendements = leur propre indice : chaque bloc doit être une suite d'indices consécutifs
        r = np.arange(1000, dtype=float) * 1e-9
        rng = np.random.default_rng(7)
        starts = rng.integers(0, len(r) - 21 + 1, size=(1, 1))
        eq = P.simulate(r, horizon=21, paths=1, block=21, seed=7)
        expected = np.cumprod(1.0 + r[starts[0, 0]: starts[0, 0] + 21])
        self.assertTrue(np.allclose(eq[0, 1:], expected))

    def test_zero_returns_flat(self):
        self.assertTrue(np.allclose(P.simulate(np.zeros(500), paths=10), 1.0))

    def test_prudent_is_lower(self):
        p = P.projection(1_000_000.0)
        self.assertLess(p["prudent"]["rendement"]["50"], p["rendement"]["50"])
        self.assertGreater(p["prudent"]["prob_perte"], p["prob_perte"])


class TestCampaignsApi(unittest.TestCase):
    def test_all_campaigns_listed_with_verdicts(self):
        from gambit_ridge.research.campaigns_api import campaigns

        c = campaigns()
        self.assertEqual([x["n"] for x in c["campagnes"]], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        self.assertEqual(c["total_essais"], sum(x["n_essais"] for x in c["campagnes"]))
        for x in c["campagnes"]:
            for t in x["essais"]:
                self.assertIsNotNone(t["dev"]["sharpe"])
                if t["verdict"]:
                    self.assertIn(t["verdict"], ("ACCEPTÉ", "REJETÉ"))


if __name__ == "__main__":
    unittest.main()
