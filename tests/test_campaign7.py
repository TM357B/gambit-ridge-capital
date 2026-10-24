"""Tests des règles d'entrée / sortie de la campagne 7 (sur prix synthétiques)."""

import unittest

import numpy as np

from gambit_ridge.research import campaign7 as c7


def _prix(*segments):
    """Prix linéaires par morceaux : segments de (nombre de jours, variation par jour)."""
    p = [100.0]
    for n, pas in segments:
        p += [p[-1] + pas * (i + 1) for i in range(n)]
    return np.array(p)[:, None]


class TestRegles(unittest.TestCase):
    def test_atr_clotures(self):
        P = _prix((40, 1.0))
        a = c7.atr_clotures(P, 20)
        self.assertTrue(np.isnan(a[19, 0]))
        self.assertAlmostEqual(a[30, 0], 1.0)

    def test_donchian_entre_sur_cassure_et_sort_sur_stop(self):
        # plat bruité, hausse franche, puis chute : achat à la cassure, sortie après un recul de 3 ATR
        rng = np.random.default_rng(0)
        plat = 100 + rng.normal(0, 0.3, 80)
        hausse = plat[-1] + np.arange(1, 41) * 1.0
        chute = hausse[-1] - np.arange(1, 21) * 1.0
        P = np.concatenate([plat, hausse, chute])[:, None]
        S = c7.donchian_stop(P)
        self.assertEqual(S[100, 0], 1)          # en position pendant la hausse
        sortie = 120 + np.argmax(S[120:, 0] == 0)
        self.assertLess(sortie, 120 + 8)        # sortie peu après ~3 ATR de recul (ATR ≈ 1)
        self.assertGreater(sortie, 120 + 1)

    def test_stop_puis_reentree_au_changement_de_signe(self):
        P = _prix((30, 1.0), (10, -1.0), (30, 1.0))
        E = np.ones_like(P)
        E[45:50] = -1.0                          # retournement du signal, puis retour à la hausse
        S = c7.avec_stop(E, P)
        self.assertEqual(S[25, 0], 1.0)
        self.assertEqual(S[40, 0], 0.0)         # stoppé pendant le recul
        self.assertEqual(S[47, 0], -1.0)        # nouveau signal : nouvelle position
        self.assertEqual(S[60, 0], 1.0)

    def test_zone_neutre_et_hysteresis(self):
        E = np.array([0.1, 0.4, 0.6, 0.3, 0.05, -0.2, -0.6, -0.1, 0.2])[:, None]
        np.testing.assert_allclose(c7.zone_neutre(E)[:, 0], [0, 0.4, 0.6, 0, 0, 0, -0.6, 0, 0])
        np.testing.assert_allclose(c7.hysteresis(E)[:, 0], [0, 0, 0.6, 0.3, 0.05, 0, -0.6, -0.1, 0])

    def test_long_seul(self):
        E = np.array([[0.5, -0.5], [-0.3, 0.2]])
        np.testing.assert_allclose(c7.long_seul(E), [[0.5, 0], [0, 0.2]])
        np.testing.assert_allclose(c7.long_seul(E, [0]), [[0.5, -0.5], [0, 0.2]])


if __name__ == "__main__":
    unittest.main()
