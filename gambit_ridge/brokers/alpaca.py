"""Client Alpaca — compte PAPER uniquement (https://paper-api.alpaca.markets).

Clés : Trousseau macOS (service gambit-ridge-capital, comptes ALPACA_KEY_ID et
ALPACA_SECRET, rangées par scripts/alpaca_keys.sh) ou variables
d'environnement du même nom. Jamais écrites en clair ni journalisées.
Garde-fou : la base URL est figée sur l'environnement paper.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

PAPER_BASE = "https://paper-api.alpaca.markets"
RETRIES = 3          # tentatives par requête sur erreur réseau / 429 / 5xx
BACKOFF = (2, 5)     # secondes d'attente entre tentatives


class AlpacaError(RuntimeError):
    pass


def _secret(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", "gambit-ridge-capital", "-a", name, "-w"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    raise AlpacaError("Clés Alpaca absentes — lance : bash scripts/alpaca_keys.sh")


def has_credentials() -> bool:
    try:
        _secret("ALPACA_KEY_ID")
        _secret("ALPACA_SECRET")
        return True
    except AlpacaError:
        return False


class AlpacaClient:
    def __init__(self, base: str = PAPER_BASE) -> None:
        if "paper-api" not in base:
            raise AlpacaError("Seul le compte paper Alpaca est autorisé.")
        self.base = base

    def _req(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers={
            "APCA-API-KEY-ID": _secret("ALPACA_KEY_ID"), "APCA-API-SECRET-KEY": _secret("ALPACA_SECRET"),
            "Content-Type": "application/json", "Accept": "application/json"})
        for attempt in range(RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:300]
                # 401 = clés invalides. 403 sert AUSSI aux refus métier (solde insuffisant, vente à
                # découvert interdite…) : on garde alors le message d'Alpaca, sinon le diagnostic est faux.
                if exc.code == 401 or (exc.code == 403 and not detail.strip().startswith("{")):
                    raise AlpacaError(f"Clés Alpaca refusées (HTTP {exc.code}) — vérifie qu'il s'agit des clés PAPER : bash scripts/alpaca_keys.sh") from None
                if (exc.code == 429 or exc.code >= 500) and attempt < RETRIES - 1:
                    time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                    continue
                raise AlpacaError(f"Alpaca {method} {path} -> HTTP {exc.code} : {detail}") from None
            except (urllib.error.URLError, OSError) as exc:  # coupure, reset, timeout
                if attempt < RETRIES - 1:
                    time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
                    continue
                raise AlpacaError(f"Alpaca {method} {path} -> réseau ({RETRIES} essais) : {getattr(exc, 'reason', exc)}") from None

    def account(self) -> dict:
        return self._req("GET", "/v2/account")

    def clock(self) -> dict:
        return self._req("GET", "/v2/clock")

    def positions(self) -> list[dict]:
        return self._req("GET", "/v2/positions")

    def asset(self, symbol: str) -> dict:
        return self._req("GET", f"/v2/assets/{urllib.parse.quote(symbol, safe='')}")

    def open_orders(self) -> list[dict]:
        return self._req("GET", "/v2/orders", {"status": "open", "limit": 500})

    def cancel(self, order_id: str) -> None:
        self._req("DELETE", f"/v2/orders/{order_id}")

    def order_by_client_id(self, client_order_id: str) -> dict:
        return self._req("GET", "/v2/orders:by_client_order_id", {"client_order_id": client_order_id})

    def submit(self, symbol: str, qty: float, side: str, tif: str, client_order_id: str) -> dict:
        try:
            return self._req("POST", "/v2/orders", body={"symbol": symbol, "qty": str(qty), "side": side, "type": "market",
                                                         "time_in_force": tif, "client_order_id": client_order_id})
        except AlpacaError as exc:
            # Une nouvelle tentative après une réponse perdue tombe sur l'ordre déjà créé :
            # client_order_id est unique, on récupère l'ordre au lieu de le doubler.
            if "HTTP 422" in str(exc) and "client_order_id" in str(exc):
                return self.order_by_client_id(client_order_id)
            raise

    def close_position(self, symbol: str) -> dict:
        """Solde TOUTE la position (quantité exacte côté Alpaca : aucun problème d'arrondi)."""
        return self._req("DELETE", f"/v2/positions/{urllib.parse.quote(symbol.replace('/', ''), safe='')}")

    def portfolio_history(self, period: str = "1A") -> dict:
        return self._req("GET", "/v2/account/portfolio/history", {"period": period, "timeframe": "1D"})
