"""Tests du laboratoire Monte-Carlo, des grecques et des fonctions de marché quant (MC, OVML, GC3D, BUDG, MAC, ILBE)."""

import json
import math
import os
import unittest

import numpy as np

from gambit_ridge.options import monte_carlo as mc
from gambit_ridge.options.black_scholes import grecques, prix_bs


class TestGrecques(unittest.TestCase):
    def test_differences_finies(self):
        S, K, T, r, s, q = 100.0, 105.0, 0.5, 0.03, 0.25, 0.01
        for typ in ("call", "put"):
            g = grecques(S, K, T, r, s, typ, q)
            h = 1e-3
            p = lambda **kw: prix_bs(kw.get("S", S), K, kw.get("T", T), kw.get("r", r), kw.get("s", s), typ, q)
            self.assertAlmostEqual(g["delta"], (p(S=S + h) - p(S=S - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g["gamma"], (p(S=S + h) - 2 * p() + p(S=S - h)) / h**2, places=3)
            self.assertAlmostEqual(g["vega"], (p(s=s + h) - p(s=s - h)) / (2 * h) / 100, places=5)
            self.assertAlmostEqual(g["rho"], (p(r=r + h) - p(r=r - h)) / (2 * h) / 100, places=5)
            self.assertAlmostEqual(g["theta"], -(p(T=T + h) - p(T=T - h)) / (2 * h) / 365, places=5)

    def test_parite_des_deltas(self):
        c, p = grecques(100, 100, 1, 0.04, 0.2, "call", 0.01), grecques(100, 100, 1, 0.04, 0.2, "put", 0.01)
        self.assertAlmostEqual(c["delta"] - p["delta"], math.exp(-0.01), places=10)
        self.assertAlmostEqual(c["gamma"], p["gamma"], places=12)


class TestSimulation(unittest.TestCase):
    def test_gbm_moments(self):
        sim = mc.simuler(100.0, 252, 100_000, "gbm", 0.05, 0.2, graine=1)
        self.assertAlmostEqual(sim["terminal"].mean(), 100 * math.exp(0.05), delta=0.3)  # E[S_T] = S0 e^{mu T}
        lr = np.log(sim["terminal"] / 100)
        self.assertAlmostEqual(lr.std(), 0.2, delta=0.003)

    def test_antithetique_symetrique(self):
        sim = mc.simuler(100.0, 20, 2_000, "gbm", 0.0, 0.2, graine=3)
        lr = np.log(sim["terminal"] / 100) + 0.5 * 0.2**2 * 20 / 252
        np.testing.assert_allclose(lr[:1000], -lr[1000:], atol=1e-12)  # chocs z et -z

    def test_student_variance_unitaire(self):
        sim = mc.simuler(100.0, 252, 60_000, "student", 0.0, 0.2, ddl=4.0, graine=2)
        lr = np.log(sim["terminal"] / 100)
        self.assertAlmostEqual(lr.std(), 0.2, delta=0.006)  # mêmes volatilités, queues plus épaisses

    def test_bootstrap_garde_la_vol_historique(self):
        rng = np.random.default_rng(5)
        hist = rng.normal(0.0004, 0.015, 3000)
        sim = mc.simuler(100.0, 252, 40_000, "bootstrap", 0.0, 0.99, rendements=hist, graine=4)
        self.assertAlmostEqual(sim["sigma"], 0.015 * math.sqrt(252), delta=0.01)  # vol réelle, pas le 0.99 fourni
        self.assertAlmostEqual(np.log(sim["terminal"] / 100).mean(), -0.5 * sim["sigma"] ** 2, delta=0.01)  # recentré

    def test_eventail_et_drawdown(self):
        sim = mc.simuler(100.0, 126, 5_000, "gbm", 0.0, 0.3, graine=6)
        self.assertEqual(sim["eventail"].shape[1], len(sim["points"]))
        self.assertTrue((sim["eventail"][:, 0] == 100).all())
        self.assertTrue((sim["dd_max"] <= 0).all())


class TestPricing(unittest.TestCase):
    S0, r, q, s = 100.0, 0.04, 0.01, 0.25

    def _sim(self, produit, jours=252, n=100_000):
        return mc.simuler(self.S0, jours, n, "gbm", self.r - self.q, self.s, graine=11, produit=produit)

    def test_europeens_contre_black_scholes(self):
        for produit, K in (("call", 100.0), ("put", 90.0)):
            out = mc.pricer(produit, self._sim(produit), self.S0, K, None, 1.0, self.r, self.q, "gbm", self.s)
            self.assertLess(abs(out["prix_cv"] - out["bs"]), 3 * out["se_cv"] + 1e-3, produit)
            # la variable de contrôle réduit toujours la variance ; beaucoup pour un call (S_T très corrélé),
            # moins pour un put en dehors de la monnaie
            self.assertGreater(out["gain_variance"], 3.0 if produit == "call" else 1.2)

    def test_barriere_et_asiatique_moins_chers(self):
        call = mc.pricer("call", self._sim("uo_call"), self.S0, 100.0, None, 1.0, self.r, self.q, "gbm", self.s)["prix"]
        uo = mc.pricer("uo_call", self._sim("uo_call"), self.S0, 100.0, 130.0, 1.0, self.r, self.q, "gbm", self.s)["prix"]
        asian = mc.pricer("asian_call", self._sim("asian_call"), self.S0, 100.0, None, 1.0, self.r, self.q, "gbm", self.s)["prix"]
        self.assertLess(uo, call)  # désactivée au-dessus de 130
        self.assertLess(asian, call)  # la moyenne est moins volatile que S_T

    def test_digital(self):
        out = mc.pricer("digital_call", self._sim("call"), self.S0, 100.0, None, 1.0, self.r, self.q, "gbm", self.s)
        d2 = (math.log(1.0) + (self.r - self.q - 0.5 * self.s**2)) / self.s
        exact = math.exp(-self.r) * 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        self.assertLess(abs(out["prix"] - exact), 3 * out["se"])

    def test_convergence(self):
        out = mc.pricer("call", self._sim("call", n=40_000), self.S0, 100.0, None, 1.0, self.r, self.q, "gbm", self.s)
        cv = out["convergence"]
        self.assertEqual(cv["n"][-1], 40_000)
        larg = np.array(cv["haut"]) - np.array(cv["bas"])
        self.assertLess(larg[-1], larg[0] / 4)  # 1/sqrt(N) : de 500 à 40 000, intervalle ~9 fois plus étroit


class TestParametres(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError):
            mc.mc("SPY", {"modele": "inconnu"})
        with self.assertRaises(ValueError):
            mc.mc("SPY", {"produit": "swaption"})
        with self.assertRaises(ValueError):
            mc._nombre({"n": "10"}, "n", 0, 1000, 200000)

    def test_json_sans_nan(self):
        d = mc._json({"a": float("nan"), "b": [np.float64(1.5), np.inf], "c": np.int64(3)})
        self.assertEqual(json.loads(json.dumps(d, allow_nan=False)), {"a": None, "b": [1.5, None], "c": 3})

    def test_calibrage(self):
        rng = np.random.default_rng(9)
        px = 100 * np.exp(np.cumsum(rng.standard_t(4, 3000) * 0.01))
        cal = mc.calibrer(px)
        self.assertGreater(cal["kurtosis"], 1.0)  # Student à 4 ddl : queues épaisses détectées
        self.assertTrue(3.0 <= cal["ddl"] <= 30.0)


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (Yahoo, FRED, The Economist)")
class TestFonctionsReseau(unittest.TestCase):
    def test_mc_spy(self):
        d = mc.mc("SPY", {"produit": "call", "n": "20000", "horizon": "63"})
        json.dumps(d, allow_nan=False)
        self.assertLess(abs(d["pricing"]["prix_cv"] - d["pricing"]["bs"]), 4 * d["pricing"]["se_cv"])

    def test_fonctions_marche(self):
        from gambit_ridge import market_functions as mf

        for d in (mf.gc3d(2), mf.budg(), mf.mac("EUR"), mf.ilbe()):
            json.dumps(d, allow_nan=False)
        g = mf.gc3d(2)
        self.assertEqual(len(g["yields"][0]), len(g["maturities"]))


if __name__ == "__main__":
    unittest.main()
