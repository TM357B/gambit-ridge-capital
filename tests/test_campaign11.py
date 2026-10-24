"""Tests de la campagne 11 : levier en contrats à terme, coûts IBKR, dépôt de garantie, limiteurs de baisse."""

import unittest

import numpy as np

from gambit_ridge.research import campaign11 as c11

TK = ["SPY", "IEF", "LQD"]          # deux en contrats à terme, un en ETF
DATES = [f"2020-01-{i:02d}" for i in range(1, 11)]


class TestLevier(unittest.TestCase):
    def setUp(self):
        self.R = np.zeros((10, 3))
        self.R[1:, 0], self.R[1:, 1], self.R[1:, 2] = 0.01, 0.002, 0.001
        self.W = np.tile([0.3, 0.2, 0.1], (10, 1))

    def test_tout_en_etf_sans_taux(self):
        r = c11.rendements_leviers(self.R, self.W, TK, DATES, np.zeros(10), 1.0, contrats=False)
        brut = self.W[0] @ self.R[5]
        cash = (1 - 0.6) * c11.ECART_CASH_POS / 252   # trésorerie positive rémunérée au taux − 0,5 %
        self.assertAlmostEqual(r[5], brut + cash, places=5)  # écart : rééquilibrage quotidien de poids constants

    def test_contrats_payent_taux_et_base_emprunt_au_bon_tarif(self):
        rf = np.full(10, 0.04)
        r = c11.rendements_leviers(self.R, self.W, TK, DATES, rf, 2.5)
        w = 2.5 * self.W[0]
        attendu = w[2] * 0.001 + w[0] * (0.01 - (0.04 + c11.BASE_FUT) / 252) + w[1] * (0.002 - (0.04 + c11.BASE_FUT) / 252)
        attendu += (1 - w[2]) * (0.04 + c11.ECART_CASH_POS) / 252      # seul l'ETF consomme de la trésorerie
        self.assertAlmostEqual(r[5], attendu, places=5)  # écart : rééquilibrage quotidien de poids constants
        W2 = np.tile([0.0, 0.0, 1.0], (10, 1))                           # 2,5x tout en ETF : 1,5 emprunté
        r2 = c11.rendements_leviers(self.R, W2, TK, DATES, rf, 2.5)
        self.assertAlmostEqual(r2[5], 2.5 * 0.001 - 1.5 * (0.04 + c11.ECART_CASH_NEG) / 252, places=5)  # écart : rééquilibrage quotidien de poids constants

    def test_depot(self):
        dep = c11.depot_garantie(self.W, TK, 2.5)
        attendu = 2.5 * (0.3 * 0.075 + 0.2 * 0.019) + c11.REG_T_ACHAT * 2.5 * 0.1
        self.assertAlmostEqual(dep[0], attendu)


class TestLimiteurs(unittest.TestCase):
    def test_bornes(self):
        rng = np.random.default_rng(0)
        r = rng.normal(0.0003, 0.01, 1500)
        r[500:560] = -0.02                                  # krach
        e1 = c11.expo_baisse(2.5 * r, 2.5)
        self.assertTrue(np.all((e1 >= 1.0) & (e1 <= 2.5)))
        self.assertLess(e1[560], 1.5)                       # réduit après le krach
        e2 = c11.expo_vol(r, 2.5, 0.07)
        self.assertTrue(np.all((e2 >= 1.0) & (e2 <= 3.0)))
        e3 = c11.expo_tendance(r, 2.5)
        self.assertTrue(set(np.unique(e3)) <= {1.0, 2.5})
        self.assertEqual(e3[0], 2.5)


if __name__ == "__main__":
    unittest.main()
