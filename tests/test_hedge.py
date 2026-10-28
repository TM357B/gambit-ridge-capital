"""Tests des maths de couverture (gambit_ridge/hedge/maths.py) et de la campagne 12."""

import math
import unittest

import numpy as np

from gambit_ridge.hedge import maths as hm
from gambit_ridge.research import campaign12 as c12


class TestRatios(unittest.TestCase):
    def setUp(self):
        g = np.random.default_rng(7)
        self.f = g.normal(0, 0.01, 5000)
        self.p = 0.8 * self.f + g.normal(0, 0.004, 5000)

    def test_variance_min_retrouve_le_beta(self):
        r = hm.ratio_variance_min(self.p, self.f)
        self.assertAlmostEqual(r["h"], 0.8, delta=0.02)
        # efficacité = ρ² : part de variance retirée par la couverture
        self.assertAlmostEqual(r["efficacite"], r["rho"] ** 2, places=6)
        self.assertLess(r["vol_apres"], r["vol_avant"])

    def test_multi_equivaut_a_l_ols(self):
        g = np.random.default_rng(1)
        F = g.normal(0, 0.01, (3000, 2))
        p = 0.5 * F[:, 0] - 0.3 * F[:, 1] + g.normal(0, 0.002, 3000)
        h = hm.ratio_multi(p, F)
        self.assertTrue(np.allclose(h, [0.5, -0.3], atol=0.02))

    def test_contrats_exemple_du_livre(self):
        # Belghaieb p. 15 : 10 M€, bêta 1,2, future de 200 000 € de notionnel -> 60 contrats
        r = hm.nb_contrats(1.2, 10e6, 4000.0, 50.0)
        self.assertEqual(r["contrats"], 60)
        self.assertAlmostEqual(r["beta_residuel"], 0.0)

    def test_cvar_couverture_baisse_la_cvar(self):
        r = hm.ratio_cvar(self.p, self.f)
        self.assertLess(r["cvar_apres"], r["cvar_avant"])
        self.assertAlmostEqual(r["h"], 0.8, delta=0.15)

    def test_var_cvar(self):
        r = np.linspace(-0.05, 0.05, 1001)
        v = hm.var_cvar(r, 0.95)
        self.assertGreater(v["cvar"], v["var"])
        self.assertAlmostEqual(v["var"], 0.045, delta=0.001)

    def test_beta_baisse(self):
        g = np.random.default_rng(3)
        m = g.normal(0, 0.01, 4000)
        p = np.where(m < 0, 1.5 * m, 0.5 * m)  # plus sensible quand le marché baisse
        self.assertAlmostEqual(hm.beta_baisse(p, m), 1.5, places=6)


class TestCausalite(unittest.TestCase):
    """La valeur en t ne doit dépendre que des données jusqu'à t."""

    def test_series(self):
        g = np.random.default_rng(11)
        f = g.normal(0, 0.01, 600)
        p = 0.7 * f + g.normal(0, 0.005, 600)
        R = np.column_stack([p, f])
        for fn in (lambda a, b: hm.beta_ewma(a, b), lambda a, b: hm.beta_kalman(a, b),
                   lambda a, b: hm.correlation_ewma(a, b),
                   lambda a, b: hm.cvar_glissante_ratio(a, b, fenetre=100, tous_les=1),
                   lambda a, b: hm.betas_ewma(np.column_stack([a, b]), b)[:, 0]):
            plein = fn(p, f)
            for t in (150, 300, 599):
                coupe = fn(p[:t + 1], f[:t + 1])
                self.assertTrue(np.allclose(np.nan_to_num(coupe[t]), np.nan_to_num(plein[t])))
        self.assertAlmostEqual(np.nanmean(hm.beta_ewma(p, f)[300:]), 0.7, delta=0.1)
        self.assertAlmostEqual(float(hm.beta_kalman(p, f)[-1]), 0.7, delta=0.15)


class TestOptions(unittest.TestCase):
    def test_parite_call_put(self):
        S, K, T, r, s = 100.0, 95.0, 0.25, 0.03, 0.2
        c = float(hm.bs(S, K, T, r, s, False))
        p = float(hm.bs(S, K, T, r, s, True))
        self.assertAlmostEqual(c - p, S - K * math.exp(-r * T), places=8)
        self.assertAlmostEqual(float(hm.bs(90.0, 95.0, 0.0, r, s, True)), 5.0)

    def test_put_paie_dans_le_krach_et_coute_sinon(self):
        T = 60
        S_plat = np.full(T, 100.0)
        vix = np.full(T, 20.0)
        r0 = np.zeros(T)
        n = np.ones(T)
        calme = hm.overlay_options(S_plat, vix, r0, n)["rendements"]
        self.assertLess(calme.sum(), 0)  # on paie la prime
        S_krach = S_plat.copy()
        S_krach[10:] = 75.0
        krach = hm.overlay_options(S_krach, vix, r0, n)["rendements"]
        self.assertGreater(krach.sum(), 0.15)  # put 95 sur un indice à 75 : ~20 % de l'actif
        self.assertTrue(np.allclose(hm.overlay_options(S_krach, vix, r0, np.zeros(T))["rendements"], 0.0))

    def test_collar_moins_cher_que_le_put(self):
        T = 60
        S = np.full(T, 100.0)
        vix, r0, n = np.full(T, 20.0), np.zeros(T), np.ones(T)
        put = hm.overlay_options(S, vix, r0, n)["rendements"].sum()
        collar = hm.overlay_options(S, vix, r0, n, otm_call=0.05)["rendements"].sum()
        self.assertGreater(collar, put)


class TestCampagne12(unittest.TestCase):
    def test_beta_portefeuille(self):
        g = np.random.default_rng(5)
        T = 400
        r_spy = g.normal(0, 0.01, T)
        R = np.column_stack([r_spy, 0.5 * r_spy + g.normal(0, 0.001, T)])
        R[0] = np.nan
        W = np.tile([0.3, 0.6], (T, 1))
        b = c12.beta_portefeuille(W, R, 0)
        self.assertAlmostEqual(float(b[-1]), 0.3 + 0.6 * 0.5, delta=0.05)

    def test_moyenne_mobile(self):
        x = np.arange(10, dtype=float)
        m = c12.moyenne_mobile(x, 3)
        self.assertTrue(np.isnan(m[1]))
        self.assertAlmostEqual(m[2], 1.0)
        self.assertAlmostEqual(m[9], 8.0)


if __name__ == "__main__":
    unittest.main()
