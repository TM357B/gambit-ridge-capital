"""Barres quotidiennes brutes (ouverture, plus haut, plus bas, clôture, volume) et dividendes, Yahoo v8.

Contrairement à YahooConnector (clôtures ajustées des dividendes, pour les rendements), ces
cours sont ceux affichés par les places — ajustés des seules divisions d'actions — comme le
PX_LAST de Bloomberg. Sert à la compatibilité Excel (query/bloomberg.py).
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=0&period2={now}&interval=1d&events=div%2Csplit"


def _court(x):
    """Yahoo stocke les cours en simple précision : 351.7300109863281 -> 351.73."""
    return None if x is None else float(np.format_float_positional(np.float32(x), unique=True, trim="-"))


def _telecharger(symbole: str) -> dict:
    req = urllib.request.Request(URL.format(sym=urllib.request.quote(symbole), now=int(time.time()) + 86400),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        res = json.loads(resp.read())["chart"]["result"][0]
    decalage = int(res.get("meta", {}).get("gmtoffset") or 0)
    jour = lambda ts: datetime.fromtimestamp(ts + decalage, tz=timezone.utc).date().isoformat()
    q = res["indicators"]["quote"][0]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(res["timestamp"])
    barres = {}
    for i, ts in enumerate(res.get("timestamp") or []):
        c = q["close"][i]
        if c is None or c <= 0:
            continue
        barres[jour(ts)] = [_court(q["open"][i]), _court(q["high"][i]), _court(q["low"][i]), _court(c), q["volume"][i], _court(adj[i])]
    dividendes = sorted((jour(int(v["date"])), float(v["amount"])) for v in (res.get("events") or {}).get("dividends", {}).values())
    meta = res.get("meta", {})
    return {"barres": barres, "dividendes": dividendes, "devise": meta.get("currency"), "nom": meta.get("longName") or meta.get("shortName"),
            "prix": meta.get("regularMarketPrice")}


def charger(symbole: str, max_age_minutes: float = 15.0, cache_dir: Path | None = None) -> dict:
    """{'barres': {date: [o, h, l, c, v, adj]}, 'dividendes': [(date ex, montant)], 'devise', 'nom', 'prix'} — cache court."""
    path = (cache_dir or CACHE_DIR) / f"yahoo_ohlc_{symbole.replace('/', '_')}.json"
    if path.exists() and time.time() - path.stat().st_mtime < max_age_minutes * 60:
        return json.loads(path.read_text())
    try:
        data = _telecharger(symbole)
    except Exception:
        if path.exists():
            return json.loads(path.read_text())  # hors ligne : dernier état connu
        raise
    if not data["barres"]:
        raise ValueError(f"{symbole} : aucun cours")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return data
