"""Tests : surveillance de l'exploitation — détection des anomalies d'activité."""

import unittest
from datetime import datetime
from unittest import mock

from gambit_ridge.ops import watchdog as W

TODAY = datetime.now().date().isoformat()


def _live(daily, **extra):
    return {"updated": datetime.now().isoformat(timespec="seconds"), "daily": daily, **extra}


class TestWatchdog(unittest.TestCase):
    def _check(self, live, services=None, baseline=""):
        services = services or {n: "active" for n in W.SERVICES}
        with mock.patch.object(W, "_load", side_effect=lambda p: live if p.name == "live_state.json" else {}), \
             mock.patch.object(W, "_service_states", return_value=services), \
             mock.patch("gambit_ridge.live.engine.enabled", return_value=True):
            return W.check(baseline)

    def _keys(self, res):
        return {i["key"] for i in res["issues"]}

    def test_all_green(self):
        daily = [{"date": f"2026-10-0{i}", "alpaca_equity": 100_000 + 50 * i, "paper_equity": 1_000_000 + 500 * i, "notional": 4_000, "refused": 0} for i in range(1, 6)]
        self.assertEqual(self._check(_live(daily))["issues"], [])

    def test_week_of_october_5_is_flagged(self):
        # 186 k$ échangés sur 100 k$ et -0,4 point contre le paper
        daily = [{"date": f"2026-10-0{i}", "alpaca_equity": 100_000 - 140 * i, "paper_equity": 1_000_000 - 600 * i, "notional": 37_000, "refused": 0} for i in range(1, 6)]
        keys = self._keys(self._check(_live(daily)))
        self.assertIn("rotation", keys)
        daily[-1]["alpaca_equity"] = 99_000
        self.assertIn("decrochage", self._keys(self._check(_live(daily))))

    def test_baseline_ignores_older_days(self):
        daily = [{"date": f"2026-10-0{i}", "alpaca_equity": 100_000, "paper_equity": 1_000_000, "notional": 37_000, "refused": 0} for i in range(1, 6)]
        self.assertNotIn("rotation", self._keys(self._check(_live(daily), baseline="2026-10-05")))

    def test_service_down_and_stale_engine(self):
        live = _live([])
        live["updated"] = "2026-10-01T00:00:00"
        keys = self._keys(self._check(live, services={**{n: "active" for n in W.SERVICES}, "gambit-live": "failed"}))
        self.assertEqual(keys, {"service-gambit-live", "live-fige"})

    def test_recent_refusals_flagged_old_ones_ignored(self):
        from datetime import timedelta

        now = datetime.now()
        recent = [{"status": "refusé", "at": (now - timedelta(minutes=m)).isoformat(timespec="seconds"), "symbol": "BTC/USD", "error": "insufficient balance"} for m in (5, 10)]
        old = [{"status": "refusé", "at": (now - timedelta(hours=3)).isoformat(timespec="seconds"), "symbol": "BTC/USD"}] * 200
        self.assertIn("refus", self._keys(self._check(_live([], orders=recent))))
        self.assertNotIn("refus", self._keys(self._check(_live([], orders=old))))


if __name__ == "__main__":
    unittest.main()
