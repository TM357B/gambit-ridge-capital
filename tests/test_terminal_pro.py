"""Tests des fonctions « pro » du terminal (HP, DVD, RG, OMON, FLDS, DOCS) sur données synthétiques, hors ligne."""

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from gambit_ridge import terminal_pro as tp


def _ohlc(s):
    if s.startswith("ZZZ"):
        raise ValueError(f"pas de cours pour {s}")
    d0 = date(2020, 1, 1)
    barres = {}
    for i in range(1500):
        d = d0 + timedelta(days=i)
        if d.weekday() < 5:
            c = 100.0 + i * 0.05
            barres[d.isoformat()] = [c - 0.5, c + 1.0, c - 1.0, c, 1000, c * (1 + i / 1500 * 0.1)]  # ajusté > brut : dividendes
    div = [((d0 + timedelta(days=91 * k)).isoformat(), 0.5 + 0.01 * k) for k in range(1, 16)]
    return {"barres": barres, "dividendes": div, "devise": "USD", "nom": f"Société {s}", "prix": None}


@mock.patch.object(tp, "_ohlc", _ohlc)
class TestTerminalPro(unittest.TestCase):
    def test_hp_jour_semaine_mois(self):
        j = tp.hp("AAPL", {"per": "D"})
        self.assertEqual(j["lignes"][0]["date"], max(_ohlc("AAPL")["barres"]))  # le plus récent d'abord
        self.assertAlmostEqual(j["lignes"][0]["variation"], j["lignes"][0]["cloture"] / j["lignes"][1]["cloture"] - 1)
        s = tp.hp("AAPL", {"per": "W"})
        l = s["lignes"][1]  # semaine complète : 5 séances
        self.assertEqual(l["volume"], 5000)
        self.assertGreaterEqual(l["haut"], l["cloture"])
        m = tp.hp("AAPL", {"per": "M"})
        self.assertEqual(len({x["date"][:7] for x in m["lignes"]}), len(m["lignes"]))
        with self.assertRaises(ValueError):
            tp.hp("AAPL", {"per": "X"})
        with self.assertRaises(ValueError):
            tp.hp("A A", {})

    def test_dvd(self):
        d = tp.dvd("JNJ")
        self.assertEqual(d["frequence"], "trimestriel")
        self.assertEqual(d["lignes"][0]["ex_date"], _ohlc("JNJ")["dividendes"][-1][0])
        self.assertGreater(d["rendement_12m"], 0)

    def test_rg_rendement_total_superieur_au_cours(self):
        r = tp.rg("SPY", {"l": "SPY,TLT", "p": "1A"})
        self.assertEqual([x["symbol"] for x in r["tableau"]], ["SPY", "TLT"])
        for x in r["tableau"]:
            self.assertGreater(x["rendement_total"], x["variation_cours"])  # les dividendes réinvestis s'ajoutent
            self.assertAlmostEqual(x["apport_dividendes"], x["rendement_total"] - x["variation_cours"])
        with self.assertRaises(ValueError):
            tp.rg("SPY", {"p": "2J"})

    def test_aiguillage(self):
        with self.assertRaises(KeyError):
            tp.repondre("inconnue", "", {})


class TestOmon(unittest.TestCase):
    def test_chaine_et_vol_implicite(self):
        from gambit_ridge.options.black_scholes import prix_bs

        S, r, T = 100.0, 0.04, 30 / 365
        ech = (date.today() + timedelta(days=30)).isoformat()
        quotes = []
        for K in (90.0, 100.0, 110.0):
            for t in ("call", "put"):
                p = prix_bs(S, K, T, r, 0.2, t)
                quotes.append({"echeance": ech, "type": t, "strike": K, "bid": p - 0.01, "ask": p + 0.01, "volume": 10, "open_interest": 100, "last": p})
        chaine = {"spot": S, "dividend_yield": 0.0, "quotes": quotes, "fetched_utc": "2026-10-28T08:00:00+00:00"}
        with mock.patch("gambit_ridge.data.yahoo_options.fetch_option_chain", lambda s: chaine), \
             mock.patch("gambit_ridge.options.monte_carlo.taux_sans_risque", lambda: r):
            o = tp.omon("SPY", {})
        self.assertEqual(o["atm"], 100.0)
        self.assertEqual(o["echeance"], ech)
        self.assertFalse(o["hors_seance"])
        atm = next(l for l in o["lignes"] if l["strike"] == 100.0)
        self.assertAlmostEqual(atm["call"]["iv"], 0.2, delta=0.01)
        self.assertAlmostEqual(atm["put"]["iv"], 0.2, delta=0.01)
        self.assertAlmostEqual(o["put_call_oi"], 1.0)


class TestFldsDocs(unittest.TestCase):
    def test_flds(self):
        d = tp.flds("", {"q": "PX_LAST"})
        self.assertTrue(any(x["champ"] == "PX_LAST" and x["dispo"] for x in d["champs"]))
        payants = tp.flds("", {"q": "BEST_EPS"})["champs"]
        self.assertTrue(payants and not payants[0]["dispo"])

    def test_docs_sans_toile_puis_avec(self):
        with tempfile.TemporaryDirectory() as t:
            dossier = Path(t)
            with mock.patch.object(tp, "ARAIGNEE", dossier):
                self.assertFalse(tp.docs("", {})["disponible"])
                (dossier / "textes").mkdir()
                (dossier / "textes" / "a.json").write_text(json.dumps({"fichier": "/x/Livre.pdf", "pages": [
                    "The minimum variance hedge ratio is rho times sigma s over sigma f, a classic hedge ratio result." * 2,
                    "Unrelated page about cooking recipes and gardening tips for the weekend." * 2,
                    "Another page on portfolio construction; a hedge ratio and minimum variance appear once here." * 2]}))
                (dossier / "toile.json").write_text(json.dumps([{"id": "c", "famille": "Couverture", "titre": "Ratio", "priorite": 3, "mentions": 2,
                                                                  "pages": [{"doc": "Livre.pdf", "page": 1, "n": 2}], "code": ["gambit_ridge/hedge/maths.py"],
                                                                  "nb_fichiers_code": 1, "score_trou": 0}]))
                tp._INDEX.update(t=0.0, idx=None)
                if tp._araignee() is None:  # version publique : pas d'araignée, pas de plein texte
                    self.assertFalse(tp.docs("", {"q": "hedge"})["plein_texte"])
                    return
                d = tp.docs("", {"q": "minimum variance hedge ratio"})
                self.assertTrue(d["plein_texte"])
                self.assertEqual(d["resultats"][0]["page"], 1)
                self.assertIn("HEDGE", d["concepts"][0]["commandes"])
                lu = tp.docs("", {"doc": "Livre.pdf", "page": "1"})["lecture"]
                self.assertEqual((lu["page"], lu["pages"]), (1, 3))
        tp._INDEX.update(t=0.0, idx=None)


if __name__ == "__main__":
    unittest.main()
