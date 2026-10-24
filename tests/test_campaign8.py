"""Tests des règles de la campagne 8 (calendrier, socle en parité de risque) sur données synthétiques."""

import unittest
from datetime import date, timedelta

import numpy as np

from gambit_ridge.research import campaign8 as c8


def _jours(debut, n):
    d, out = date.fromisoformat(debut), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


class TestCalendrier(unittest.TestCase):
    def test_tournant_de_mois(self):
        ds = _jours("2026-01-26", 15)  # fin janvier -> mi-février
        tm = c8.jours_tournant_de_mois(ds)
        choisis = [d for d, k in zip(ds, tm) if k]
        # 30/01 dernier jour de janvier ; 02, 03, 04/02 trois premiers de février (le 26/01 est hors fenêtre :
        # c'est le premier jour de la série, mais pas un début de mois)
        self.assertIn("2026-01-30", choisis)
        self.assertEqual([d for d in choisis if d >= "2026-02-01"], ["2026-02-02", "2026-02-03", "2026-02-04"])

    def test_veilles_de_feries(self):
        ds = ["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07"]  # 03/07 férié (vendredi)
        self.assertEqual(c8.veilles_de_feries(ds).tolist(), [False, True, False, False])
        ds = ["2026-07-09", "2026-07-10", "2026-07-13"]  # simple week-end
        self.assertEqual(c8.veilles_de_feries(ds).tolist(), [False, False, False])


class TestSocle(unittest.TestCase):
    def test_parite_de_risque(self):
        rng = np.random.default_rng(1)
        tk = list(c8.PARITE) + ["QQQ"]
        T = 400
        vols = np.array([0.01, 0.02, 0.005, 0.004, 0.012, 0.015, 0.02])
        P = 100 * np.exp(np.cumsum(rng.normal(0, 1, (T, len(tk))) * vols, axis=0))
        W = c8.socle_parite(P, tk, None)
        np.testing.assert_allclose(W[:c8.FENETRE_VOL].sum(axis=1), 1.0)       # rodage : 60/40
        self.assertAlmostEqual(W[300].sum(), 1.0)
        self.assertEqual(W[300, tk.index("QQQ")], 0.0)
        self.assertGreater(W[300, tk.index("TIP")], W[300, tk.index("TLT")])     # moins volatil -> plus de poids
        Wl = c8.socle_parite(P, tk, 0.08)
        self.assertLessEqual(np.abs(Wl[300]).sum(), c8.LEVIER_MAX + 1e-9)


if __name__ == "__main__":
    unittest.main()
