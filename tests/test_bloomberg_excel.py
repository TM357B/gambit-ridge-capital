"""Tests de la compatibilité Bloomberg pour Excel (BDP, BDH, BDS, BQL) sur données synthétiques."""

import unittest
from datetime import date, timedelta
from unittest import mock

from gambit_ridge.query import bloomberg as b


def _barres(tk):
    if tk.startswith("ZZZ"):
        raise b.ErreurBloomberg(b.INVALIDE)
    d0 = date(2025, 1, 1)
    barres = {}
    for i in range(400):
        d = d0 + timedelta(days=i)
        if d.weekday() < 5:
            c = 100.0 + i * 0.1 if tk != "SPY" else 400.0 + i * 0.05 + (i % 7) * 0.3
            barres[d.isoformat()] = [c - 0.5, c + 1.0, c - 1.0, c, 1000 + i, c * 0.98]
    return {"barres": barres, "dividendes": [("2025-05-12", 0.25), ("2025-08-11", 0.26)], "devise": "USD", "nom": f"Société {tk}",
            "prix": None}


@mock.patch.object(b, "_barres", _barres)
@mock.patch.object(b, "_cotation", lambda tk: {})
class TestBloomberg(unittest.TestCase):
    def test_bdp_champs_et_unites(self):
        derniere = max(_barres("AAPL")["barres"])
        self.assertAlmostEqual(b.bdp("AAPL US Equity", "PX_LAST"), _barres("AAPL")["barres"][derniere][3])
        self.assertEqual(b.bdp("AAPL US Equity", "px_volume"), _barres("AAPL")["barres"][derniere][4])  # casse indifférente
        self.assertEqual(b.bdp("AAPL US Equity", "NAME"), "Société AAPL")
        self.assertGreater(b.bdp("AAPL US Equity", "CHG_PCT_1YR"), 20)  # en %, comme Bloomberg
        self.assertEqual(b.bdp("AAPL US Equity", "BEST_EPS"), b.INDISPONIBLE)
        self.assertEqual(b.bdp("AAPL US Equity", "PAS_UN_CHAMP"), "#N/A Invalid Field")
        self.assertEqual(b.bdp("ZZZ US Equity", "PX_LAST"), b.INVALIDE)

    def test_bdh_periodicite_et_options(self):
        t = b.bdh("AAPL US Equity", ["PX_LAST", "PX_VOLUME"], "20250301", "20250331")
        self.assertEqual(t[0][0], "2025-03-03")
        self.assertEqual(len(t[0]), 3)
        w = b.bdh("AAPL US Equity", ["PX_LAST"], "20250301", "20250331", ["Per=W"])
        self.assertEqual([r[0] for r in w], ["2025-03-07", "2025-03-14", "2025-03-21", "2025-03-28", "2025-03-31"])
        h = b.bdh("AAPL US Equity", ["PX_LAST"], "20250301", "20250331", ["Per=M", "Dts=H"])
        self.assertEqual(len(h), 1)
        self.assertEqual(len(h[0]), 1)
        d = b.bdh("AAPL US Equity", ["PX_LAST"], "20250301", "20250310", ["Sort=D"])
        self.assertGreater(d[0][0], d[-1][0])
        with self.assertRaises(b.ErreurBloomberg):
            b.bdh("AAPL US Equity", ["BEST_EPS"], "-1Y")

    def test_dates_bloomberg(self):
        t = date(2026, 10, 24)
        self.assertEqual(b.date_bloomberg("-1Y", t), date(2025, 10, 24))
        self.assertEqual(b.date_bloomberg("-6M", t), date(2026, 4, 24))
        self.assertEqual(b.date_bloomberg("-1CY", t), date(2026, 1, 1))
        self.assertEqual(b.date_bloomberg("20240229", t), date(2024, 2, 29))
        self.assertEqual(b.date_bloomberg("", t), t)
        self.assertEqual(b.date_bloomberg("-1M", date(2026, 3, 31)), date(2026, 2, 28))

    def test_bds(self):
        div = b.bds("AAPL US Equity", "DVD_HIST_ALL", ["Headers=Y"])
        self.assertEqual(div[0][4], "Dividend Amount")
        self.assertEqual(div[1][1:5], ["2025-08-11", "", "", 0.26])  # plus récent d'abord, montant en 5e colonne
        self.assertEqual(b.bds("MAG7 Index", "INDX_MEMBERS")[0], ["AAPL US"])
        with self.assertRaises(b.ErreurBloomberg):
            b.bds("SPX Index", "INDX_MEMBERS")

    def test_format_echange(self):
        self.assertEqual(b.en_tsv([["2025-01-02", 1.5e-05, None, True]]), "2025-01-02\t1.5E-05\t\tTRUE")
        self.assertEqual(b.en_tsv(float("nan")), b.ABSENT)
        self.assertEqual(b.repondre("bds", {"s": "SPX Index", "f": "INDX_MEMBERS"}).split(" (")[0], "#N/A Index Members Not Available")
        self.assertEqual(b.repondre("xyz", {}), "#N/A Unknown Function")

    def test_identifiants(self):
        self.assertEqual(b.titre("XBTUSD Curncy"), "BTC-USD")
        self.assertEqual(b.titre("SPX Index"), "^GSPC")
        self.assertEqual(b.titre("EURUSD Curncy"), "EURUSD=X")


if __name__ == "__main__":
    unittest.main()
