"""Tests de la campagne 9 : budget de risque par classe et coût du levier (données synthétiques)."""

import unittest
from types import SimpleNamespace

import numpy as np

from gambit_ridge.research import campaign9 as c9
from gambit_ridge.research.portfolio import ewma_covariance

TK = ["SPY", "QQQ", "TLT", "IEF", "GLD", "USO", "UUP", "FXE"]


class TestBudgetParClasse(unittest.TestCase):
    def test_classes_et_vol_totale(self):
        self.assertEqual(c9.classes(["SPY", "UNG", "FXA", "BWX"]), ["Actions", "Matières premières", "Devises", "Obligations"])
        rng = np.random.default_rng(0)
        P = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, (900, len(TK))), axis=0))
        W = c9.tendance_par_classe(P, TK)
        cov = ewma_covariance(P)
        vols = [np.sqrt(W[t] @ cov[t] @ W[t]) for t in range(400, 900, 50) if np.abs(W[t]).sum() > 0]
        self.assertTrue(vols)
        for v in vols:
            self.assertLessEqual(v, 0.10 + 1e-6)          # jamais plus de risque que la cible
        self.assertLessEqual(np.abs(W).max(), 0.40 + 1e-9)
        self.assertLessEqual(np.abs(W).sum(axis=1).max(), 2.0 + 1e-9)


class TestLevier(unittest.TestCase):
    def test_interets_et_pret_de_titres(self):
        T = 300
        W = np.zeros((T, 2))
        W[:, 0], W[:, 1] = 0.8, -0.3
        sim = SimpleNamespace(weights=W, returns=np.full(T, 0.0004))
        taux = np.full(T, 0.03)
        r1, r2 = c9._avec_levier(sim, 1.0, taux), c9._avec_levier(sim, 2.0, taux)
        # levier 1 : pas d'emprunt (0,8 < 1), seulement le prêt de titres sur la vente
        self.assertAlmostEqual(r1[5], 0.0004 - 0.3 * 0.005 / 252)
        # levier 2 : 1,6 acheteur -> 0,6 emprunté à 3 % + 1 %, et 0,6 vendu à 0,5 %
        self.assertAlmostEqual(r2[5], 2 * 0.0004 - (0.6 * 0.04 + 0.6 * 0.005) / 252)
        self.assertEqual(r2[0], 2 * 0.0004)


if __name__ == "__main__":
    unittest.main()
