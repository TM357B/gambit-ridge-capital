"""Tests des modèles de « Machine Learning in Finance » (gambit_ridge/quant) : QLBS, GP, filtre
particulaire, inférence bayésienne, mélanges, Box-Jenkins, ACP."""

import json
import math
import os
import unittest

import numpy as np

from gambit_ridge.options.black_scholes import grecques, prix_bs
from gambit_ridge.quant import bayes, gp, particle, qlbs, timeseries
from gambit_ridge.quant.optim import nelder_mead


class TestOptim(unittest.TestCase):
    def test_rosenbrock(self):
        x, f, _ = nelder_mead(lambda v: (1 - v[0]) ** 2 + 100 * (v[1] - v[0] ** 2) ** 2, [-1.2, 1.0], iter_max=2000, tol=1e-12)
        np.testing.assert_allclose(x, [1, 1], atol=1e-3)


class TestQLBS(unittest.TestCase):
    def test_bsplines_partition_unite(self):
        x = np.linspace(-1, 2, 500)
        B = qlbs.bsplines(x, 12)
        np.testing.assert_allclose(B.sum(axis=1), 1.0, atol=1e-10)
        self.assertTrue((B >= -1e-12).all())

    def test_limite_black_scholes(self):
        # λ = 0, μ = r : prix équitable ≈ BS, couverture t0 ≈ delta BS
        S, X = qlbs.simuler(100, 0.03, 0.15, 1.0, 24, 30000)
        d = qlbs.resoudre_dp(S, X, 100, 0.03, 1.0, 0.0, "put")
        self.assertAlmostEqual(d["Pi"][:, 0].mean(), prix_bs(100, 100, 1, 0.03, 0.15, "put"), delta=0.12)
        self.assertAlmostEqual(d["a"][:, 0].mean(), grecques(100, 100, 1, 0.03, 0.15, "put")["delta"], delta=0.03)

    def test_exemple_du_livre(self):
        # § 4.6 : put ATM, μ 5 %, σ 15 %, r 3 %, λ 0,001, 24 pas -> 4,90 ± 0,12 (BS 4,53)
        S, X = qlbs.simuler(100, 0.05, 0.15, 1.0, 24, 30000)
        d = qlbs.resoudre_dp(S, X, 100, 0.03, 1.0, 0.001, "put")
        prix = -d["Q"][:, 0].mean()
        self.assertTrue(4.70 < prix < 5.10, prix)
        self.assertGreater(prix, prix_bs(100, 100, 1, 0.03, 0.15, "put"))  # prime de risque de couverture

    def test_prix_croit_avec_aversion(self):
        S, X = qlbs.simuler(100, 0.05, 0.15, 1.0, 12, 10000)
        prix = [-qlbs.resoudre_dp(S, X, 100, 0.03, 1.0, l, "call")["Q"][:, 0].mean() for l in (0.0, 0.002, 0.01)]
        self.assertTrue(prix[0] < prix[1] < prix[2])

    def test_fonction_terminal(self):
        out = qlbs.qlbs({"n": "4000", "pas": "8"})
        json.dumps(out, allow_nan=False)
        with self.assertRaises(ValueError):
            qlbs.qlbs({"type": "swap"})


class TestGP(unittest.TestCase):
    def test_derivees_contre_differences_finies(self):
        rng = np.random.default_rng(0)
        X = rng.uniform(-2, 2, (25, 1))
        m = gp.GP([0.7], bruit=1e-3).ajuster(X, np.sin(2 * X[:, 0]), optimiser=False)
        x0, h = np.array([[0.3]]), 1e-4
        d1, d2 = m.derivees(x0)
        f = lambda v: m.predire(np.array([[v]]), variance=False)[0]
        self.assertAlmostEqual(d1[0], (f(0.3 + h) - f(0.3 - h)) / (2 * h), places=5)
        self.assertAlmostEqual(d2[0], (f(0.3 + h) - 2 * f(0.3) + f(0.3 - h)) / h**2, places=2)

    def test_incertitude_hors_donnees(self):
        X = np.linspace(0, 1, 10)[:, None]
        m = gp.GP([0.2], bruit=1e-3).ajuster(X, X[:, 0] ** 2, optimiser=False)
        _, v_in = m.predire([[0.5]])
        _, v_out = m.predire([[3.0]])
        self.assertGreater(v_out[0], 100 * v_in[0])

    def test_grecques_apprises(self):
        d = gp.gp_greeks({"points": "12"})
        json.dumps(d, allow_nan=False)
        self.assertLess(d["erreurs"]["prix_max"], 0.02)
        self.assertLess(d["erreurs"]["delta_max"], 0.01)
        self.assertLess(d["erreurs"]["gamma_max"], 0.15 * d["erreurs"]["gamma_ref"])


class TestParticules(unittest.TestCase):
    @staticmethod
    def _simuler(T, mu, phi, sv, rho, graine=0):
        rng = np.random.default_rng(graine)
        x, y = np.empty(T), np.empty(T)
        x[0] = mu
        for t in range(T):
            e = rng.standard_normal()
            y[t] = e * math.exp(x[t] / 2)
            if t < T - 1:
                x[t + 1] = mu * (1 - phi) + phi * x[t] + sv * (rho * e + math.sqrt(1 - rho**2) * rng.standard_normal())
        return x, y

    def test_filtre_suit_la_vol(self):
        x, y = self._simuler(800, math.log(1e-4), 0.97, 0.25, -0.5)
        llh, f = particle.filtre(y, math.log(1e-4), 0.97, 0.25, -0.5, M=800, garder=True)
        vraie = np.sqrt(np.exp(x) * 252)
        self.assertGreater(np.corrcoef(f["moyenne"][50:], vraie[50:])[0, 1], 0.7)
        self.assertGreater(np.mean((vraie >= f["q05"] * 0.8) & (vraie <= f["q95"] * 1.2)), 0.8)

    def test_vraisemblance_maximale_pres_des_vrais_parametres(self):
        x, y = self._simuler(1000, math.log(1e-4), 0.97, 0.25, -0.6, graine=3)
        vrai, _ = particle.filtre(y, math.log(1e-4), 0.97, 0.25, -0.6, M=500)
        faux, _ = particle.filtre(y, math.log(1e-4), 0.60, 0.25, 0.6, M=500)
        self.assertGreater(vrai, faux + 10)


class TestBayes(unittest.TestCase):
    def test_a_priori_plat_redonne_les_mco(self):
        rng = np.random.default_rng(1)
        X = np.column_stack([np.ones(400), rng.standard_normal(400)])
        y = X @ [0.5, 1.7] + 0.3 * rng.standard_normal(400)
        reg = bayes.RegressionBayesienne([0, 0], np.eye(2) * 1e8, a0=1e-3, b0=1e-6).mettre_a_jour(X, y)
        np.testing.assert_allclose(reg.m, np.linalg.lstsq(X, y, rcond=None)[0], atol=1e-6)
        lo, hi, _ = reg.intervalle(1)
        self.assertTrue(lo < 1.7 < hi)

    def test_sequentiel_egal_lot(self):
        rng = np.random.default_rng(2)
        X = np.column_stack([np.ones(300), rng.standard_normal(300)])
        y = X @ [0.1, -0.8] + rng.standard_normal(300)
        lot = bayes.RegressionBayesienne([0, 1], np.eye(2), 2, 1).mettre_a_jour(X, y)
        seq = bayes.RegressionBayesienne([0, 1], np.eye(2), 2, 1)
        for i in range(0, 300, 50):
            seq.mettre_a_jour(X[i:i + 50], y[i:i + 50])
        np.testing.assert_allclose(seq.m, lot.m, atol=1e-10)
        self.assertAlmostEqual(seq.b, lot.b, places=8)

    def test_melange_retrouve_deux_regimes(self):
        rng = np.random.default_rng(4)
        x = np.concatenate([rng.normal(0.001, 0.008, 4000), rng.normal(-0.002, 0.03, 1000)])
        m = bayes.melange_em(x, 2)
        np.testing.assert_allclose(np.sqrt(m["variances"]), [0.008, 0.03], rtol=0.1)
        np.testing.assert_allclose(m["poids"], [0.8, 0.2], atol=0.05)
        lls = [bayes.melange_em(x, k)["llh"] for k in (1, 2, 3)]
        bic, _, w = bayes.selection(lls, [2, 5, 8], len(x))
        self.assertEqual(int(np.argmin(bic)), 1)  # 2 régimes, pas 3 : rasoir d'Occam
        self.assertAlmostEqual(w.sum(), 1.0)


class TestSeriesTemporelles(unittest.TestCase):
    def test_pacf_ar2(self):
        rng = np.random.default_rng(1)
        e = rng.standard_normal(6000)
        x = np.zeros(6000)
        for t in range(2, 6000):
            x[t] = 0.5 * x[t - 1] - 0.3 * x[t - 2] + e[t]
        p = timeseries.pacf(x, 4)
        self.assertAlmostEqual(p[2], -0.3, delta=0.04)
        self.assertLess(abs(p[3]), 0.05)
        best = min((timeseries.ajuster_ar(x, k) for k in range(6)), key=lambda m: m["bic"])
        self.assertEqual(best["p"], 2)

    def test_adf_et_ljung_box(self):
        rng = np.random.default_rng(2)
        e = rng.standard_normal(3000)
        self.assertFalse(timeseries.adf(np.cumsum(e))["stationnaire_5pct"])
        self.assertTrue(timeseries.adf(e)["stationnaire_5pct"])
        self.assertGreater(timeseries.ljung_box(e, 10)[1], 0.01)
        ar = np.zeros(3000)
        for t in range(1, 3000):
            ar[t] = 0.4 * ar[t - 1] + e[t]
        self.assertLess(timeseries.ljung_box(ar, 10)[1], 1e-6)

    def test_prevision_ar1(self):
        m = {"p": 1, "c": 0.0, "phi": np.array([0.5]), "s2": 1.0}
        prev, et = timeseries.prevoir_ar(m, [2.0], 3)
        np.testing.assert_allclose(prev, [1.0, 0.5, 0.25])
        np.testing.assert_allclose(et ** 2, [1, 1.25, 1.3125])

    def test_acp_niveau_pente(self):
        rng = np.random.default_rng(3)
        mat = np.linspace(0, 1, 8)
        f = rng.standard_normal((2000, 2)) * [5.0, 1.5]
        M = f[:, :1] * np.ones(8) + f[:, 1:] * (mat - 0.5) + 0.05 * rng.standard_normal((2000, 8))
        a = timeseries.acp(M)
        self.assertGreater(a["part"][0], 0.9)
        self.assertTrue((a["vecteurs"][:, 0] > 0).all())  # niveau : tout du même signe
        self.assertGreater(a["vecteurs"][-1, 1], a["vecteurs"][0, 1])  # pente montante


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (Yahoo)")
class TestFonctionsReseau(unittest.TestCase):
    def test_fonctions(self):
        from gambit_ridge import market_functions as mf

        for d in (mf.tsa("SPY"), mf.beta("AAPL"), mf.regm("SPY", {"ans": "5"}), mf.modl()):
            json.dumps(d, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
