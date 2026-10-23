"""Tests : client Alpaca — nouvelles tentatives réseau et envoi idempotent."""

import io
import json
import unittest
import urllib.error
from unittest import mock

from gambit_ridge.brokers import alpaca as A


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(payload):
    return _Resp(json.dumps(payload).encode())


def _http(code, body=""):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body.encode()))


class TestAlpacaRetry(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(A, "_secret", return_value="k"), mock.patch.object(A.time, "sleep")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.c = A.AlpacaClient()

    def _urlopen(self, *effects):
        return mock.patch.object(A.urllib.request, "urlopen", side_effect=list(effects))

    def test_reset_then_ok(self):
        with self._urlopen(ConnectionResetError(54, "reset"), _ok({"equity": "1"})) as m:
            self.assertEqual(self.c.account(), {"equity": "1"})
        self.assertEqual(m.call_count, 2)

    def test_5xx_then_ok(self):
        with self._urlopen(_http(503), _ok({"is_open": False})):
            self.assertEqual(self.c.clock(), {"is_open": False})

    def test_gives_up_after_retries(self):
        with self._urlopen(*[ConnectionResetError(54, "reset")] * A.RETRIES) as m:
            with self.assertRaises(A.AlpacaError):
                self.c.account()
        self.assertEqual(m.call_count, A.RETRIES)

    def test_no_retry_on_4xx(self):
        with self._urlopen(_http(422, "bad qty")) as m:
            with self.assertRaises(A.AlpacaError):
                self.c.account()
        self.assertEqual(m.call_count, 1)

    def test_403_business_refusal_keeps_alpaca_message(self):
        # 403 « solde insuffisant » n'est pas un problème de clés
        with self._urlopen(_http(403, '{"code":40310000,"message":"insufficient balance for BTC"}')):
            with self.assertRaises(A.AlpacaError) as ctx:
                self.c.submit("BTC/USD", 1, "sell", "gtc", "x")
        self.assertIn("insufficient balance", str(ctx.exception))
        self.assertNotIn("Clés", str(ctx.exception))

    def test_401_is_a_key_problem(self):
        with self._urlopen(_http(401, '{"message":"unauthorized"}')):
            with self.assertRaises(A.AlpacaError) as ctx:
                self.c.account()
        self.assertIn("Clés", str(ctx.exception))

    def test_submit_recovers_existing_order(self):
        # 1re tentative : ordre créé mais réponse perdue ; 2e : doublon refusé ; on relit l'ordre.
        dup = _http(422, '{"message":"client_order_id must be unique"}')
        with self._urlopen(ConnectionResetError(54, "reset"), dup, _ok({"id": "abc"})):
            r = self.c.submit("SPY", 1, "buy", "opg", "grc-test")
        self.assertEqual(r["id"], "abc")


if __name__ == "__main__":
    unittest.main()
