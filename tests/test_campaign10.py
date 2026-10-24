"""Tests de la campagne 10 et des données « contrats à terme gratuits » (données synthétiques, hors ligne)."""

import unittest
from datetime import date, timedelta

import numpy as np

from gambit_ridge.data import contrats_gratuits as cg
from gambit_ridge.research import campaign10 as c10
from gambit_ridge.research.portfolio import ewma_covariance


def _jours_ouvres(debut: str, n: int) -> list[str]:
    d, out = date.fromisoformat(debut), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


class TestChangementsDEcheance(unittest.TestCase):
    def test_calage_retrouve_un_saut_plante(self):
        dates = _jours_ouvres("2001-01-02", 4000)
        rng = np.random.default_rng(1)
        r = rng.normal(0, 0.02, len(dates))
        vrais = cg.jours_de_changement(dates, (3, 5, 7, 9, 12), 0, "j15", 0)  # comme le maïs
        r[vrais] += 0.03
        regle = cg.calage_changements(dates, r, (3, 5, 7, 9, 12))
        trouves = cg.jours_de_changement(dates, regle["mois_liste"], regle["decalage"], regle["ancre"], regle["k"])
        commun = len(set(trouves) & set(vrais)) / len(vrais)
        self.assertGreater(commun, 0.8)                            # règles équivalentes possibles, mêmes jours
        self.assertGreater(regle["t"], cg.SEUIL_T)

    def test_jour_du_changement(self):
        dates = _jours_ouvres("2010-01-04", 300)
        j = cg.jours_de_changement(dates, (3,), 0, "j15", 0)
        self.assertEqual(dates[j[0]], "2010-03-15")
        j = cg.jours_de_changement(dates, range(1, 13), -1, "fin", -1)  # avant-dernier jour ouvré du mois précédent
        self.assertIn("2010-01-28", [dates[i] for i in j])

    def test_pic_isole_neutralise(self):
        r = np.array([0.0, 0.01, 0.40, -0.39, 0.0])
        self.assertTrue(np.allclose(cg._pics_isoles(r)[2:4], 0.0))


class TestTaux(unittest.TestCase):
    def test_duration_obligation_au_pair(self):
        dmod, conv = cg._duration_convexite(np.array([0.04]), 10)
        self.assertAlmostEqual(float(dmod[0]), 8.18, places=1)   # 10 ans au pair à 4 % : ≈ 8,2
        self.assertGreater(float(conv[0]), 70)


class TestCampagne10(unittest.TestCase):
    def test_report_de_calendrier_sans_anticipation(self):
        u = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
        cibles = ["2020-01-02", "2020-01-06", "2020-01-07"]
        r = np.array([0.5, 0.01, 0.02, 0.03, 0.04])
        out = c10.sur_dates(u, r, cibles)
        self.assertAlmostEqual(out[0], 0.01)                       # rien d'antérieur au calendrier cible
        self.assertAlmostEqual(out[1], 1.02 * 1.03 - 1)            # le 03 est reporté au 06, jamais avant
        self.assertAlmostEqual(out[2], 0.04)

    def test_programme_vol_et_bornes(self):
        rng = np.random.default_rng(0)
        T = 900
        classes = ["Matières premières"] * 3 + ["Taux"] * 2 + ["Devises"] * 2 + ["Actions"] * 2
        vols = np.array([0.30, 0.25, 0.35, 0.02, 0.08, 0.10, 0.10, 0.18, 0.22]) / np.sqrt(252)
        R = rng.normal(0.0002, 1.0, (T, len(classes))) * vols
        R[:100, 0] = np.nan                                        # cotation tardive
        u = {"classes": classes, "portage": np.zeros_like(R), "dates": _jours_ouvres("2005-01-03", T)}
        W = c10.programme(u, R)
        self.assertTrue(np.all(W[:360, 0] == 0))                    # aucun signal avant 260 séances de cotation
        cov = ewma_covariance(c10._indices(R))
        for t in range(400, T, 50):
            if np.abs(W[t]).sum() > 0:
                self.assertLessEqual(float(np.sqrt(W[t] @ cov[t] @ W[t])), 0.10 + 1e-6)
        self.assertLessEqual(np.abs(W).max(), c10.POS_MAX + 1e-9)
        self.assertLessEqual(np.abs(W).sum(axis=1).max(), c10.BRUT_MAX + 1e-9)

    def test_cout_des_changements(self):
        d = ["2020-02-27", "2020-02-28", "2020-03-02", "2020-03-03"]
        u = {"dates": d, "classes": ["Matières premières", "Taux"]}
        held = np.array([[1.0, 2.0]] * 4)
        c = c10.cout_changements(u, held)
        self.assertEqual(c[1], 0.0)
        self.assertAlmostEqual(c[2], (1.0 + 2.0) * c10.COUT_ROLL_BPS / 1e4)  # mars : mensuel + trimestriel
        self.assertEqual(c[3], 0.0)

    def test_sans_derive(self):
        R = np.array([[0.01, 0.02], [0.03, np.nan], [0.02, 0.01]])
        u = {"rendements": R, "classes": ["Matières premières", "Actions"]}
        out = cg.sans_derive(u)
        self.assertAlmostEqual(float(np.log1p(out[:, 0]).sum()), 0.0)
        self.assertTrue(np.isnan(out[1, 1]))


if __name__ == "__main__":
    unittest.main()
