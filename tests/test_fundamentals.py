"""Tests du loader de fondamentaux — règle anti-look-ahead n°1."""
import unittest
from datetime import date
from pathlib import Path

from gambit_ridge.data.fundamentals import (
    DEFAULT_LAG_DAYS,
    FundamentalRow,
    fundamentals_visible_at,
    load_fundamentals,
)

CSV = Path(__file__).resolve().parent.parent / "data" / "fundamentals.csv"


class TestFundamentals(unittest.TestCase):
    def test_load(self):
        rows = load_fundamentals(CSV)
        self.assertGreaterEqual(len(rows), 51)
        tickers = {r.ticker for r in rows}
        for t in ("PLTR", "NVDA", "BRK.B", "ASML", "SPACEX", "AMD", "TSLA", "JPM", "MSFT"):
            self.assertIn(t, tickers)
        self.assertEqual(len([r for r in rows if r.ticker == "MSFT"]), 5)

    def test_multi_tickers_dates(self):
        rows = load_fundamentals(CSV)
        per = {(r.ticker, r.periode): r.fin_periode.isoformat() for r in rows}
        self.assertEqual(per[("AMD", "FY2021")], "2021-12-25")
        self.assertEqual(per[("AMD", "FY2025")], "2025-12-27")
        self.assertEqual(per[("MSFT", "FY2026")], "2026-06-30")
        self.assertEqual(per[("TSLA", "TTM")], "2026-06-30")
        amd_ttm = next(r for r in rows if r.ticker == "AMD" and r.periode == "TTM")
        self.assertAlmostEqual(amd_ttm.values["free_cash_flow"], 8403.0)
        tsla_ttm = next(r for r in rows if r.ticker == "TSLA" and r.periode == "TTM")
        self.assertAlmostEqual(tsla_ttm.values["net_income"], 3804.0)
        msft_fy26 = next(r for r in rows if r.ticker == "MSFT" and r.periode == "FY2026")
        self.assertIsNone(msft_fy26.values["revenue"])  # compte de resultat absent
        self.assertAlmostEqual(msft_fy26.values["capex"], -115948.0)  # derive FCF-OCF

    def test_numeric_parsing(self):
        rows = load_fundamentals(CSV)
        fy25 = next(r for r in rows if r.periode == "FY2025")
        self.assertAlmostEqual(fy25.values["revenue"], 4475.0)
        self.assertAlmostEqual(fy25.values["marge_nette_pct"], 36.31)
        self.assertIsNone(fy25.values["interest_expense"])  # champ vide

    def test_visible_from_uses_lag_when_no_pub_date(self):
        rows = load_fundamentals(CSV)
        for r in rows:
            self.assertIsNone(r.date_publication)
            self.assertEqual(r.visible_from, r.fin_periode.replace() if False else
                             date.fromordinal(r.fin_periode.toordinal() + DEFAULT_LAG_DAYS))

    def test_anti_lookahead(self):
        rows = load_fundamentals(CSV)
        # Le 2024-06-01 : FY2024 (fin 2024-12-31) ne doit PAS être visible
        v = fundamentals_visible_at(rows, "2024-06-01")
        self.assertEqual(v["PLTR"].periode, "FY2023")
        # NVDA FY2024 finit le 2024-01-28 -> visible des 2024-03-13
        self.assertEqual(v["NVDA"].periode, "FY2024")
        # Avant la première publication : rien
        self.assertEqual(fundamentals_visible_at(rows, "2022-01-01"), {})

    def test_latest_visible_wins(self):
        rows = load_fundamentals(CSV)
        v = fundamentals_visible_at(rows, "2026-12-31")
        self.assertEqual(v["PLTR"].periode, "TTM")
        self.assertEqual(v["NVDA"].periode, "TTM")
        self.assertEqual(v["ASML"].periode, "TTM")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_fundamentals("/tmp/inexistant_fundamentals.csv")


if __name__ == "__main__":
    unittest.main()
