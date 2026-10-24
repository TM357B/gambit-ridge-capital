"""Tests des fonctions FA (SEC EDGAR), EQS (screener) et GEW (macro mondiale)."""

import json
import os
import unittest
from unittest import mock

from gambit_ridge.data import edgar
from gambit_ridge.equity import eqs as eqs_mod


def _faits():
    """Faits XBRL factices : un exercice clos fin septembre, des trimestres, deux balises de chiffre d'affaires."""
    return {
        "Revenues": {"units": {"USD": [
            {"frame": "CY2023", "val": 100, "end": "2023-09-30", "form": "10-K"},
            {"frame": "CY2024", "val": 90, "end": "2024-09-30", "form": "10-K"},  # balise partielle (sous-total)
        ]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            {"frame": "CY2024", "val": 120, "end": "2024-09-30", "form": "10-K"},
            {"frame": "CY2023Q4", "val": 28, "end": "2023-12-31", "form": "10-Q"},
            {"frame": "CY2024Q1", "val": 30, "end": "2024-03-31", "form": "10-Q"},
            {"frame": "CY2024Q4", "val": 35, "end": "2024-12-31", "form": "10-Q"},
            {"frame": "CY2025Q1", "val": 33, "end": "2025-03-31", "form": "10-Q"},
        ]}},
    }


class TestEdgar(unittest.TestCase):
    def test_fusion_des_balises(self):
        par = edgar._par_periode(_faits(), edgar.FLUX["chiffre_affaires"], r"CY\d{4}", plus_grande=True)
        self.assertEqual(par["CY2024"][0], 120)  # la plus grande valeur l'emporte (total, pas sous-total)
        self.assertEqual(par["CY2023"][0], 100)  # seule balise disponible cette année-là

    def test_douze_derniers_mois(self):
        cf = {"entityName": "Test", "facts": {"us-gaap": _faits(), "dei": {}}}
        with mock.patch.object(edgar, "cik_de", return_value=(1, "Test")), mock.patch.object(edgar, "_get", return_value=cf):
            c = edgar.comptes("TEST")
        # dernier exercice (120, clos 2024-09) + trimestres depuis (35 + 33) - mêmes trimestres un an plus tôt (28 + 30)
        self.assertEqual(c["ttm"]["chiffre_affaires"], 120 + 35 + 33 - 28 - 30)
        self.assertEqual(c["ttm"]["fin"], "2025-03-31")
        self.assertEqual([l["annee"] for l in c["annuel"]], ["2023", "2024"])

    def test_formulaire_4(self):
        xml = """<?xml version="1.0"?><ownershipDocument>
          <reportingOwner><reportingOwnerId><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
          <reportingOwnerRelationship><isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>CFO</officerTitle></reportingOwnerRelationship></reportingOwner>
          <nonDerivativeTable><nonDerivativeTransaction>
            <transactionDate><value>2026-10-01</value></transactionDate>
            <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
            <transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>50.5</value></transactionPricePerShare>
            <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
            <postTransactionAmounts><sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
          </nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
        dep = {"cik": 1, "tous": [{"type": "4", "accession": "0001-26-000001", "document": "xslF345X06/f4.xml", "lien": "L"}]}
        with mock.patch.object(edgar, "depots", return_value=dep), mock.patch.object(edgar, "_get", return_value=xml):
            tx = edgar.dirigeants("TEST")
        self.assertEqual(len(tx), 1)
        t = tx[0]
        self.assertEqual((t["nom"], t["role"], t["type"], t["actions"], t["montant"]), ("Doe Jane", "CFO", "Achat", 1000.0, 50500.0))

    def test_ticker_inconnu(self):
        with mock.patch.object(edgar, "tickers", return_value={"AAPL": {"cik": 320193, "nom": "Apple"}}):
            with self.assertRaises(ValueError):
                edgar.cik_de("ZZZZ")


class TestScreener(unittest.TestCase):
    def test_ratios_et_valeurs_non_plausibles(self):
        l = {"capitalisation": 1000, "chiffre_affaires": 500, "ca_prec": 400, "resultat_net": 50, "resultat_op": 80, "fcf": 60,
             "fonds_propres": 250, "tresorerie": 100, "dette": 200}
        r = eqs_mod._ratios(l)
        self.assertAlmostEqual(r["per"], 20)
        self.assertAlmostEqual(r["roe"], 0.2)
        self.assertAlmostEqual(r["croissance_ca"], 0.25)
        self.assertAlmostEqual(r["ve_ebit"], (1000 + 200 - 100) / 80)
        self.assertAlmostEqual(r["dette_fp"], 0.8)
        aberrant = eqs_mod._ratios({**l, "resultat_net": 5000, "fcf": 900})
        self.assertIsNone(aberrant["per"])  # PER < 1
        self.assertIsNone(aberrant["rendement_fcf"])  # rendement FCF > 40 %

    def test_filtres_et_tri(self):
        univers = {"annee": 2025, "date": "2026-10-24", "lignes": [
            {"ticker": "A", "nom": "A", "fin": "", "capitalisation": 5e9, "chiffre_affaires": 2e9, "ca_prec": 1.5e9, "resultat_net": 4e8, "resultat_op": 5e8, "fcf": 3e8, "fonds_propres": 1e9, "tresorerie": 0, "dette": 1e8},
            {"ticker": "B", "nom": "B", "fin": "", "capitalisation": 5e9, "chiffre_affaires": 2e9, "ca_prec": 2e9, "resultat_net": 1e8, "resultat_op": 2e8, "fcf": 1e8, "fonds_propres": 2e9, "tresorerie": 0, "dette": 0},
            {"ticker": "C", "nom": "C", "fin": "", "capitalisation": 1e9, "chiffre_affaires": 2e9, "ca_prec": 1e9, "resultat_net": 4e8, "resultat_op": 5e8, "fcf": 3e8, "fonds_propres": 1e9, "tresorerie": 0, "dette": 0},
        ]}
        with mock.patch.object(eqs_mod, "construire_univers", return_value=univers):
            d = eqs_mod.eqs({"roe_min": "0.3", "cap_min": "2"})
            self.assertEqual([r["ticker"] for r in d["lignes"]], ["A"])  # C trop petite, B ROE 5 %
            d = eqs_mod.eqs({"tri": "per", "sens": "asc"})
            self.assertEqual([r["ticker"] for r in d["lignes"]], ["A", "B"])
            with self.assertRaises(ValueError):
                eqs_mod.eqs({"tri": "inconnu"})


@unittest.skipIf(os.environ.get("GRC_OFFLINE"), "nécessite le réseau (SEC, FMI, BRI, FRED)")
class TestReseau(unittest.TestCase):
    def test_fonctions(self):
        from gambit_ridge import market_functions as mf

        f = mf.fa("AAPL")
        json.dumps(f, allow_nan=False)
        self.assertGreater(f["annuel"][-1]["chiffre_affaires"], 1e11)
        g = mf.gew()
        json.dumps(g, allow_nan=False)
        self.assertEqual(len(g["annees"]), 3)
        e = mf.eqs({"preset": "geants", "n": "5"})
        self.assertEqual(len(e["lignes"]), 5)


if __name__ == "__main__":
    unittest.main()
