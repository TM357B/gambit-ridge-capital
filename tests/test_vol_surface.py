"""Tests du module options : Black-Scholes, vol implicite, surface de volatilité."""

import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from gambit_ridge.options import vol_surface as vs
from gambit_ridge.options.black_scholes import prix_bs, vega, vol_implicite


class TestBlackScholes(unittest.TestCase):
    def test_aller_retour(self):
        for S, K, T, r, q, sigma in [(100, 100, 1, 0.04, 0.0, 0.20), (760, 600, 0.05, 0.04, 0.012, 0.45),
                                     (760, 900, 2.0, 0.04, 0.012, 0.13), (50, 55, 0.25, 0.0, 0.0, 0.80)]:
            for t in ("call", "put"):
                p = prix_bs(S, K, T, r, sigma, t, q)
                self.assertAlmostEqual(vol_implicite(p, S, K, T, r, t, q), sigma, delta=1e-7)

    def test_valeur_de_reference(self):
        # Hull : S=42, K=40, T=0,5, r=10 %, sigma=20 % -> call 4,76, put 0,81
        self.assertAlmostEqual(prix_bs(42, 40, 0.5, 0.10, 0.20, "call"), 4.7594, places=4)
        self.assertAlmostEqual(prix_bs(42, 40, 0.5, 0.10, 0.20, "put"), 0.8086, places=4)

    def test_parite_call_put(self):
        S, K, T, r, q, s = 760, 740, 0.4, 0.04, 0.012, 0.18
        c, p = prix_bs(S, K, T, r, s, "call", q), prix_bs(S, K, T, r, s, "put", q)
        self.assertAlmostEqual(c - p, S * math.exp(-q * T) - K * math.exp(-r * T), places=9)

    def test_vega_par_differences(self):
        h = 1e-5
        num = (prix_bs(100, 105, 0.5, 0.03, 0.25 + h) - prix_bs(100, 105, 0.5, 0.03, 0.25 - h)) / (2 * h)
        self.assertAlmostEqual(num, vega(100, 105, 0.5, 0.03, 0.25), places=5)

    def test_prix_hors_bornes(self):
        self.assertTrue(math.isnan(vol_implicite(150.0, 100, 100, 1, 0.04, "call")))  # call > spot
        self.assertTrue(math.isnan(vol_implicite(0.0, 100, 100, 1, 0.04, "call")))
        self.assertTrue(math.isnan(vol_implicite(1.0, 100, 50, 1, 0.04, "call")))  # sous l'intrinsèque


class TestInterpolation(unittest.TestCase):
    def test_sans_extrapolation_ni_trou(self):
        grille = np.array([0.80, 0.90, 0.95, 1.00, 1.03, 1.10, 1.20])
        x, y = [0.90, 1.00, 1.02, 1.10], [0.30, 0.20, 0.19, 0.18]
        v = vs.interpoler_smile(x, y, grille, trou_max=0.11)
        self.assertTrue(np.isnan(v[0]) and np.isnan(v[-1]))  # hors plage cotée
        self.assertAlmostEqual(v[2], 0.25)
        v = vs.interpoler_smile(x, y, grille, trou_max=0.05)
        self.assertTrue(np.isnan(v[2]) and np.isnan(v[4]))  # trous de 10 % et 8 % : vides
        self.assertAlmostEqual(v[3], 0.20)  # strikes cotés : gardés
        self.assertAlmostEqual(v[5], 0.18)


class TestSurfaceDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spot, cls.taux, cls.div, cls.brut, _ = vs.marche_demo()

    def test_nettoyage(self):
        propre, rejets = vs.nettoyer(self.brut, self.spot)
        self.assertGreater(rejets["option dans la monnaie (ITM)"], 0)
        self.assertGreater(rejets["strike hors 75-125 % du spot"], 0)
        self.assertTrue((propre["spread_rel"] <= vs.SPREAD_MAX).all())
        self.assertTrue(((propre["type"] == "put") == (propre["strike"] < self.spot)).all())  # OTM seulement

    def test_parite_retrouve_le_dividende(self):
        forwards = vs.forwards_implicites(self.brut, self.spot, self.taux, 0.0)  # faux dividende fourni
        for _, q_T, source in forwards.values():
            self.assertEqual(source, "parité")
            self.assertAlmostEqual(q_T, self.div, delta=0.002)

    def test_surface_retrouve_la_vraie_vol(self):
        points, surf, _, _ = vs.calculer(self.spot, self.taux, 0.0, self.brut)
        err = np.abs(points["iv"] - vs.vol_demo(points["moneyness"], points["T"]))
        self.assertLess(np.median(err), 0.001)
        self.assertEqual(surf["n_calendaire"], 0)
        # Interpolation en variance totale : exacte aux échéances cotées.
        np.testing.assert_allclose(surf["surface"][0], surf["smiles"][0], equal_nan=True)
        np.testing.assert_allclose(surf["surface"][-1], surf["smiles"][-1], equal_nan=True)

    def test_export_csv(self):
        points, surf, _, _ = vs.calculer(self.spot, self.taux, self.div, self.brut)
        with tempfile.TemporaryDirectory() as d:
            vs.exporter(points, surf, Path(d))
            lignes = (Path(d) / "points_iv.csv").read_text().splitlines()
            self.assertEqual(len(lignes), len(points["iv"]) + 1)
            self.assertTrue(lignes[0].startswith("echeance,T,type,strike"))
            self.assertEqual(len((Path(d) / "surface_grille.csv").read_text().splitlines()), vs.N_GRILLE_T + 1)

    def test_resume_json_sans_nan(self):
        """Ce que sert /api/fn/ovdv doit passer JSON.parse : aucun NaN."""
        import json
        from datetime import datetime

        points, surf, forwards, rejets = vs.calculer(self.spot, self.taux, self.div, self.brut)
        r = vs.resume_json("DEMO", self.spot, self.taux, self.brut, points, surf, forwards, rejets,
                           datetime(2026, 10, 23, 12, 0, tzinfo=vs.NY))
        json.dumps(r, allow_nan=False)
        self.assertEqual(len(r["grid"]["vols"]), vs.N_GRILLE_T)
        self.assertEqual(len(r["grid"]["vols"][0]), len(r["moneyness"]))
        self.assertAlmostEqual(r["kpi"]["atm_1m"], float(vs.vol_demo(1.0, 30 / 365)), delta=0.003)
        self.assertGreater(r["kpi"]["skew_1m"], 0)  # puts plus chers que les calls

    def test_sans_options(self):
        with self.assertRaises(ValueError):
            vs.calculer(self.spot, self.taux, self.div, vs._filtrer(self.brut, self.brut["T"] < 0.05))


class TestDependances(unittest.TestCase):
    def test_numpy_seul(self):
        """Règle du dépôt : ni scipy ni pandas dans le module options."""
        code = ("import sys; import gambit_ridge.options.vol_surface, gambit_ridge.data.yahoo_options; "
                "print(','.join(m for m in ('scipy', 'pandas', 'matplotlib') if m in sys.modules))")
        racine = Path(__file__).resolve().parent.parent
        out = subprocess.run([sys.executable, "-c", code], cwd=racine, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "")


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (Yahoo options)")
class TestYahooOptions(unittest.TestCase):
    def test_surface_spy(self):
        spot, taux, div, brut, _ = vs.charger_marche("SPY")
        points, surf, forwards, _ = vs.calculer(spot, taux, div, brut)
        self.assertGreater(len(points["iv"]), 500)
        atm = surf["atm"][np.isfinite(surf["atm"])]
        self.assertTrue(((atm > 0.03) & (atm < 1.5)).all())


if __name__ == "__main__":
    unittest.main()
