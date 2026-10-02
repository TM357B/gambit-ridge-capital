"""Client Saxo OpenAPI — environnement de SIMULATION uniquement.

Authentification : jeton d'accès (« 24-hour token » du portail développeur
https://www.developer.saxo/openapi/token), rangé dans le Trousseau macOS par
scripts/saxo_token.sh (service gambit-ridge-capital, compte SAXO_TOKEN) ou dans
la variable d'environnement SAXO_TOKEN. Le jeton n'est jamais écrit sur disque
en clair ni journalisé.

Garde-fou : la base URL est figée sur /sim/ ; le client refuse de démarrer si
on tente de la changer vers l'environnement réel.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

SIM_BASE = "https://gateway.saxobank.com/sim/openapi"


class SaxoError(RuntimeError):
    pass


def _token() -> str:
    tok = os.environ.get("SAXO_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", "gambit-ridge-capital", "-a", "SAXO_TOKEN", "-w"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    raise SaxoError("Jeton Saxo absent — lance : bash scripts/saxo_token.sh")


class SaxoClient:
    def __init__(self, base: str = SIM_BASE) -> None:
        if "/sim/" not in base:
            raise SaxoError("Seul l'environnement de simulation Saxo est autorisé.")
        self.base = base
        self._account: dict | None = None

    # ------------------------------------------------------------- HTTP
    def _req(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code == 401:
                raise SaxoError("Jeton Saxo expiré ou invalide (durée 24 h) — relance : bash scripts/saxo_token.sh") from None
            raise SaxoError(f"Saxo {method} {path} -> HTTP {exc.code} : {detail}") from None

    # ------------------------------------------------------------- compte
    def account(self) -> dict:
        if self._account is None:
            accs = self._req("GET", "/port/v1/accounts/me").get("Data", [])
            if not accs:
                raise SaxoError("Aucun compte Saxo trouvé")
            a = accs[0]
            self._account = {"AccountKey": a["AccountKey"], "ClientKey": a["ClientKey"], "Currency": a.get("Currency"), "AccountId": a.get("AccountId")}
        return self._account

    def balance(self) -> dict:
        a = self.account()
        return self._req("GET", "/port/v1/balances", {"ClientKey": a["ClientKey"], "AccountKey": a["AccountKey"]})

    def net_positions(self) -> list[dict]:
        a = self.account()
        data = self._req("GET", "/port/v1/netpositions", {"ClientKey": a["ClientKey"], "FieldGroups": "NetPositionBase,NetPositionView,DisplayAndFormat"})
        return data.get("Data", [])

    # ------------------------------------------------------------- marché
    def search(self, keywords: str, asset_types: str = "Etf,Etc,Etn,CfdOnEtf,CfdOnEtc") -> list[dict]:
        a = self.account()
        return self._req("GET", "/ref/v1/instruments", {"KeyWords": keywords, "AssetTypes": asset_types, "AccountKey": a["AccountKey"], "$top": 20}).get("Data", [])

    def instrument(self, uic: int, asset_type: str) -> dict:
        return self._req("GET", f"/ref/v1/instruments/details/{uic}/{asset_type}")

    def quote(self, uic: int, asset_type: str) -> dict:
        a = self.account()
        d = self._req("GET", "/trade/v1/infoprices", {"Uic": uic, "AssetType": asset_type, "AccountKey": a["AccountKey"], "FieldGroups": "Quote,DisplayAndFormat"})
        return d.get("Quote", {})

    # ------------------------------------------------------------- ordres
    def order_body(self, uic: int, asset_type: str, buy_sell: str, amount: float) -> dict:
        return {"AccountKey": self.account()["AccountKey"], "Uic": uic, "AssetType": asset_type, "BuySell": buy_sell,
                "Amount": amount, "OrderType": "Market", "OrderDuration": {"DurationType": "DayOrder"}, "ManualOrder": False}

    def precheck(self, body: dict) -> dict:
        return self._req("POST", "/trade/v2/orders/precheck", body=body)

    def place(self, body: dict) -> dict:
        return self._req("POST", "/trade/v2/orders", body=body)
