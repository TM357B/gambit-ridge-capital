"""Tests du langage de requête GRQL (façon BQL) : syntaxe, univers, champs, opérations, CSV."""

import os
import unittest
import zlib
from datetime import date, timedelta
from unittest import mock

import numpy as np

from gambit_ridge.query import grql


def _historique(self, tk):
    """Cours synthétiques déterministes : A monte de 10 %/an, B baisse, SPY sert de référence."""
    n = 600
    ds = [(date.today() - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]
    rng = np.random.default_rng(zlib.crc32(tk.encode()))  # graine stable (hash() change à chaque processus)
    tendance = {"A": 0.60, "B": -0.60, "SPY": 0.08, "EURUSD=X": 0.0, "USDEUR=X": 0.0}.get(tk, 0.0)
    r = tendance / 365 + 0.005 * rng.standard_normal(n)
    if tk == "USDEUR=X":
        return ds, np.full(n, 0.9)
    return ds, 100 * np.exp(np.cumsum(r))


class TestSyntaxe(unittest.TestCase):
    def test_analyse_complete(self):
        q = grql.analyser("let(#p = return(1y); #v = volatility(1y);) get(name, #p / #v) for(['AAPL']) with(dates = range(-6m, 0d), currency = 'EUR')")
        self.assertEqual([n for n, _ in q["let"]], ["#p", "#v"])
        self.assertEqual([lab for lab, _ in q["get"]], ["name", "#p / #v"])
        self.assertEqual(set(q["with"]), {"dates", "currency"})

    def test_erreurs_lisibles(self):
        for src, morceau in [("get(px_last for(['A'])", "« ) » attendu"), ("get(x)", "for(...) manquante"), ("for(['A'])", "get(...) manquante"),
                             ("get(x) for(['A']) select(y)", "clause inconnue"), ("get(x) get(y) for(['A'])", "en double"), ("get(x ? 2) for(['A'])", "caractère inattendu")]:
            with self.assertRaises(grql.ErreurRequete) as ctx:
                grql.analyser(src)
            self.assertIn(morceau, str(ctx.exception), src)

    def test_identifiants_bloomberg(self):
        self.assertEqual(grql.titre("AAPL US Equity"), "AAPL")
        self.assertEqual(grql.titre("SPX Index"), "^GSPC")
        self.assertEqual(grql.titre("EURUSD Curncy"), "EURUSD=X")
        self.assertEqual(grql.titre("btc"), "BTC-USD")

    def test_precedence(self):
        q = grql.analyser("get(1 + 2 * 3 > 6 and not 0) for(['A'])")
        ev = grql.Evaluateur(q)
        self.assertIs(ev.valeur(q["get"][0][1], "A"), True)
        q = grql.analyser("get(-(1 + 2) * 2) for(['A'])")
        self.assertEqual(grql.Evaluateur(q).valeur(q["get"][0][1], "A"), -6.0)


@mock.patch.object(grql.Contexte, "historique", _historique)
@mock.patch.object(grql.Contexte, "cotation", lambda self, tk: {"devise": "USD", "nom": f"Société {tk}", "capitalisation": 1e9})
class TestEvaluation(unittest.TestCase):
    def test_champs_de_marche(self):
        r = grql.executer("get(return(1y), volatility(1y), max_drawdown(1y), beta('SPY', 1y), name) for(['A', 'B'])")
        a, b = r["lignes"]
        self.assertGreater(a["valeurs"][1], 0.05)  # vol ~ 0,005 × √252 ≈ 8 %
        self.assertLessEqual(a["valeurs"][2], 0)
        self.assertEqual(a["valeurs"][4], "Société A")
        _, px = _historique(None, "A")
        self.assertIsNotNone(b["valeurs"][3])

    def test_let_et_operations(self):
        r = grql.executer("let(#p = return(1y); #v = volatility(1y);) get(#p, #v, #p / #v, round(#v * 100, 1)) for(['A'])")
        p, v, ratio, arrondi = r["lignes"][0]["valeurs"]
        self.assertAlmostEqual(ratio, p / v, delta=1e-4 * abs(ratio))  # sorties arrondies à 6 décimales
        self.assertEqual(arrondi, round(v * 100, 1))

    def test_series_et_devise(self):
        r = grql.executer("get(px_last) for(['A']) with(dates = range(-1m, 0d), currency = 'EUR')")
        s = r["series"]["px_last"]
        self.assertGreater(len(s["dates"]), 20)
        _, px = _historique(None, "A")
        self.assertAlmostEqual(s["par_id"]["A"][-1], round(px[-1] * 0.9, 6), places=4)
        csv = grql.en_csv(r)
        self.assertTrue(csv.startswith("date,A"))

    def test_filter_et_top(self):
        with mock.patch.dict(grql.MEMBRES, {"TEST": ["A", "B", "SPY"]}):
            r = grql.executer("get(return(1y)) for(filter(members('TEST'), return(1y) > 0))")
            ids = [l["id"] for l in r["lignes"]]
            self.assertNotIn("B", ids)
            r = grql.executer("get(return(1y)) for(top(members('TEST'), return(1y), 1))")
            self.assertEqual(len(r["lignes"]), 1)

    def test_erreur_par_titre_sans_arret(self):
        r = grql.executer("get(inconnu) for(['A', 'B'])")
        self.assertEqual(len(r["lignes"]), 2)
        self.assertIn("champ ou fonction inconnu", r["erreurs"]["A"])


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (Yahoo)")
class TestReseau(unittest.TestCase):
    def test_requete_reelle(self):
        r = grql.executer("get(px_last, return(1y)) for(['SPY', 'QQQ'])")
        self.assertEqual(len(r["lignes"]), 2)
        self.assertIsNotNone(r["lignes"][0]["valeurs"][0])


if __name__ == "__main__":
    unittest.main()
