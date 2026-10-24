"""Tests de l'étude de robustesse : PBO (CSCV), signaux aléatoires, statistiques de trading."""

import unittest
from datetime import date, timedelta

import numpy as np

from gambit_ridge.research import robustesse as rb


class TestCSCV(unittest.TestCase):
    def test_bruit_pur_pbo_proche_de_moitie(self):
        # 30 stratégies sans aucun avantage : choisir la meilleure en échantillon ne vaut rien hors échantillon
        # (une seule série varie beaucoup : les coupes sont très corrélées, d'où la moyenne sur plusieurs tirages)
        pbos = [rb.cscv(np.random.default_rng(g).normal(0, 0.01, (800, 30)), S=10) for g in range(12)]
        self.assertEqual(pbos[0]["n_combinaisons"], 252)
        self.assertAlmostEqual(np.mean([r["pbo"] for r in pbos]), 0.5, delta=0.15)

    def test_vraie_superiorite_pbo_faible(self):
        rng = np.random.default_rng(2)
        R = rng.normal(0, 0.01, (1600, 20))
        R[:, 7] += 0.002  # une stratégie réellement meilleure (Sharpe ≈ 3)
        res = rb.cscv(R, S=10)
        self.assertLess(res["pbo"], 0.05)
        self.assertGreater(res["sharpe_oos_meilleur_median"], 2.0)


class TestSignauxAleatoires(unittest.TestCase):
    def test_meme_intensite_et_meme_rythme(self):
        T = 3000
        sig = np.zeros((T, 2))
        sig[:, 0] = np.where((np.arange(T) // 50) % 2 == 0, 0.3, -0.3)  # retournement tous les 50 jours
        sig[:, 1] = 0.1                                                 # jamais de retournement
        alea, p = rb.signaux_aleatoires(sig, 200, np.random.default_rng(3))
        self.assertEqual(alea.shape, (200, T, 2))
        np.testing.assert_allclose(np.abs(alea), np.abs(sig)[None].repeat(200, 0))
        self.assertAlmostEqual(p[0], 59 / 3000, places=6)
        flips = (np.diff(np.sign(alea[:, :, 0]), axis=1) != 0).mean()
        self.assertAlmostEqual(flips, p[0], delta=0.004)
        self.assertGreater((np.sign(alea[:, 0, 0]) > 0).mean(), 0.35)  # sens de départ tiré au hasard


class TestStatsRendements(unittest.TestCase):
    def test_valeurs_connues(self):
        r = np.array([0.01, -0.005, -0.005, -0.005, 0.02, 0.0, 0.01, -0.01])
        d0 = date(2026, 1, 1)
        dates = [(d0 + timedelta(days=i)).isoformat() for i in range(len(r))]
        s = rb.stats_rendements(r, dates)
        j = s["jours"]
        self.assertEqual(j["n"], 8)
        self.assertAlmostEqual(j["taux_gain"], 3 / 8)
        self.assertAlmostEqual(j["profit_factor"], 0.04 / 0.025)
        self.assertEqual(j["pire_serie_pertes"], 3)
        self.assertAlmostEqual(j["meilleur"], 0.02)
        self.assertEqual(s["mois"]["n"], 1)
        self.assertAlmostEqual(s["mois_detail"][0]["rendement"], np.prod(1 + r) - 1)


class TestSimulationLot(unittest.TestCase):
    def test_couts_et_rebalancement(self):
        # deux actifs à prix constants, poids fixes : rendement = -coûts au premier rebalancement seulement
        P = np.ones((30, 2)) * 100
        W = np.zeros((1, 30, 2))
        W[0, :, 0] = 0.5
        ret, couts, _ = rb.lot_simuler(P, W, 10, every=5)
        self.assertAlmostEqual(-ret[0].sum(), couts[0].sum(), places=12)
        self.assertAlmostEqual(couts[0].sum(), 0.5 * 10 / 1e4, places=12)


if __name__ == "__main__":
    unittest.main()
