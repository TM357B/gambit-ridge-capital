"""Tests : moteur live — planification des ordres et garde-fous d'activité."""

import unittest

from gambit_ridge.live.engine import plan_orders

OK = {"tradable": True, "shortable": True, "easy_to_borrow": True}


class TestPlanOrders(unittest.TestCase):
    def _plan(self, weights, held, can=None, assets=None, pending=frozenset(), prices=None):
        kinds = {t: ("crypto" if t.endswith("-USD") else "etf") for t in set(weights) | set(held)}
        prices = prices or {t: 100.0 for t in kinds}
        assets = assets or {t: OK for t in kinds}
        return plan_orders(weights, kinds, prices, held, 100_000.0, assets, can or {"etf": True, "crypto": True}, set(pending))

    def test_buys_to_target(self):
        o, _ = self._plan({"SPY": 0.30}, {})
        self.assertEqual((o[0]["side"], o[0]["qty"]), ("buy", 300))

    def test_buffer_skips_small_moves(self):
        o, _ = self._plan({"SPY": 0.30}, {"SPY": 290})  # 29 % contre 30 % : dans la tolérance
        self.assertEqual(o, [])

    def test_closes_exited_position(self):
        o, _ = self._plan({}, {"SPY": 3})
        self.assertEqual((o[0]["side"], o[0]["qty"]), ("sell", 3))

    def test_market_closed_no_etf_orders(self):
        o, _ = self._plan({"SPY": 0.30, "BTC-USD": 0.05}, {}, can={"etf": False, "crypto": True})
        self.assertEqual([x["ticker"] for x in o], ["BTC-USD"])
        self.assertAlmostEqual(o[0]["qty"], 50.0)

    def test_no_crypto_short_and_no_unborrowable_short(self):
        assets = {"FXE": {"tradable": True, "shortable": True, "easy_to_borrow": False}, "BTC-USD": OK}
        o, skipped = self._plan({"FXE": -0.1, "BTC-USD": -0.05}, {}, assets=assets)
        self.assertEqual(o, [])
        self.assertEqual(len(skipped), 2)

    def test_side_flip_closes_first(self):
        o, _ = self._plan({"TLT": -0.10}, {"TLT": 50})
        self.assertEqual((o[0]["side"], o[0]["qty"], o[0]["target"]), ("sell", 50, 0.0))

    def test_pending_order_not_duplicated(self):
        o, skipped = self._plan({"SPY": 0.30}, {}, pending={"SPY"})
        self.assertEqual(o, [])
        self.assertIn("SPY : ordre déjà en attente", skipped)

    def test_missing_price_reported(self):
        o, skipped = self._plan({"BNB-USD": 0.008}, {}, prices={"BNB-USD": None})
        self.assertEqual(o, [])
        self.assertTrue(skipped and skipped[0].startswith("BNB-USD"))

    def test_crypto_sell_never_exceeds_holding(self):
        # bug du 2026-10-08 : 0,004574925 BTC détenus, ordre de 0,004575 -> refusé en boucle par Alpaca
        o, _ = self._plan({}, {"BTC-USD": 0.004574925}, prices={"BTC-USD": 82800.0})
        self.assertEqual(len(o), 1)
        self.assertTrue(o[0]["close"])
        self.assertLessEqual(o[0]["qty"], 0.004574925)

    def test_crypto_partial_sell_floored(self):
        held = 0.050000004  # 4,1 % du compte, cible 1 %
        o, _ = self._plan({"BTC-USD": 0.01}, {"BTC-USD": held}, prices={"BTC-USD": 82800.0})
        self.assertEqual(o[0]["side"], "sell")
        self.assertFalse(o[0]["close"])
        self.assertLessEqual(o[0]["qty"], held)
        self.assertLessEqual(o[0]["qty"], held - 0.01 * 100_000 / 82800.0 + 1e-9)  # jamais arrondi au-dessus

    def test_dust_position_ignored(self):
        o, skipped = self._plan({}, {"ADA-USD": 0.000000082}, prices={"ADA-USD": 0.25})
        self.assertEqual((o, skipped), ([], []))

    def test_sells_before_buys(self):
        o, _ = self._plan({"SPY": 0.30}, {"QQQ": 100})
        self.assertEqual([x["side"] for x in o], ["sell", "buy"])


class TestPaperDrift(unittest.TestCase):
    def test_marks_paper_at_live_prices(self):
        from gambit_ridge.live.engine import paper_drift

        pos = {"SPY": {"weight": 0.30, "last_price": 100.0}, "TIP": {"weight": -0.10, "last_price": 50.0},
               "BTC-USD": {"weight": 0.03, "last_price": 80_000.0}, "BNB-USD": {"weight": 0.01, "last_price": 700.0}}
        live = {"SPY": 101.0, "TIP": 49.0, "BTC-USD": 76_000.0}  # BNB sans prix live : inchangé
        self.assertAlmostEqual(paper_drift(pos, live), 0.30 * 0.01 + (-0.10) * (-0.02) + 0.03 * (-0.05))

    def test_aberrant_price_ignored(self):
        from gambit_ridge.live.engine import paper_drift

        self.assertEqual(paper_drift({"SPY": {"weight": 0.3, "last_price": 100.0}}, {"SPY": 10.0}), 0.0)


class TestDayGuard(unittest.TestCase):
    def _engine(self, orders_today):
        from gambit_ridge.live import engine as E

        e = E.Engine.__new__(E.Engine)  # sans connexion Alpaca
        e.state = {"equity": 100_000.0, "orders": orders_today, "guard_notified": "2026-10-10"}
        return e

    def test_asset_order_cap(self):
        from gambit_ridge.live.engine import MAX_ORDERS_PER_ASSET

        done = [{"at": "2026-10-10T10:00:00", "status": "envoyé", "ticker": "LTC-USD", "notional": 2000}] * MAX_ORDERS_PER_ASSET
        kept, notes = self._engine(done)._day_guard([{"ticker": "LTC-USD", "notional": 2000}, {"ticker": "SPY", "notional": 2000}], "2026-10-10")
        self.assertEqual([o["ticker"] for o in kept], ["SPY"])
        self.assertEqual(len(notes), 1)

    def test_turnover_cap(self):
        done = [{"at": "2026-10-10T10:00:00", "status": "envoyé", "ticker": f"T{i}", "notional": 10_000} for i in range(5)]  # 50 %
        kept, notes = self._engine(done)._day_guard([{"ticker": "SPY", "notional": 9_000}, {"ticker": "QQQ", "notional": 9_000}], "2026-10-10")
        self.assertEqual([o["ticker"] for o in kept], ["SPY"])  # 59 % passe, 68 % non

    def test_yesterday_does_not_count(self):
        done = [{"at": "2026-10-09T10:00:00", "status": "envoyé", "ticker": "LTC-USD", "notional": 90_000}] * 5
        kept, _ = self._engine(done)._day_guard([{"ticker": "LTC-USD", "notional": 2000}], "2026-10-10")
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
