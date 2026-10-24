"""Chaîne d'options Yahoo Finance (API v7, sans clé) avec cache disque court.

L'API options exige un cookie de session et un « crumb » : on les obtient
une fois par appel (fc.yahoo.com puis /v1/test/getcrumb), en bibliothèque
standard. Cache : data_cache/yahoo_options_<SYM>.json, 15 min par défaut.
"""

from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"
BASE = "https://query2.finance.yahoo.com"


def _opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", "Mozilla/5.0")]
    try:
        op.open("https://fc.yahoo.com", timeout=15).close()  # pose le cookie, même en 404
    except urllib.error.HTTPError as exc:
        exc.close()
    except Exception:
        pass
    crumb = op.open(f"{BASE}/v1/test/getcrumb", timeout=15).read().decode().strip()
    return op, crumb


def _get(op, url):
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with op.open(url, timeout=20) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # réseau, quota
            last_err = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"Yahoo options : {last_err}")


def _download(symbol: str) -> dict:
    op, crumb = _opener()
    first = _get(op, f"{BASE}/v7/finance/options/{symbol}?crumb={crumb}")["optionChain"]["result"][0]
    quote = first["quote"]
    out = {
        "symbol": symbol,
        "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spot": float(quote["regularMarketPrice"]),
        "dividend_yield": quote.get("trailingAnnualDividendYield"),
        "quotes": [],
    }
    for ts in first["expirationDates"]:
        res = _get(op, f"{BASE}/v7/finance/options/{symbol}?date={ts}&crumb={crumb}")["optionChain"]["result"][0]
        echeance = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        for chaine in res.get("options", []):
            for type_option, cotes in (("call", chaine.get("calls", [])), ("put", chaine.get("puts", []))):
                for c in cotes:
                    out["quotes"].append({
                        "echeance": echeance, "type": type_option, "strike": float(c["strike"]),
                        "bid": float(c.get("bid") or 0.0), "ask": float(c.get("ask") or 0.0),
                        "volume": int(c.get("volume") or 0), "open_interest": int(c.get("openInterest") or 0),
                    })
    return out


def fetch_option_chain(symbol: str, refresh: bool = False, max_age_minutes: float = 15.0,
                       cache_dir: Path | None = None) -> dict:
    """Spot, dividende et cotations de toutes les échéances (cache court)."""
    path = (cache_dir or CACHE_DIR) / f"yahoo_options_{symbol}.json"
    cached = None
    if path.exists():
        try:
            cached = json.loads(path.read_text())
        except Exception:
            cached = None
    fresh = cached is not None and time.time() - path.stat().st_mtime < max_age_minutes * 60
    if cached is not None and fresh and not refresh:
        return cached
    try:
        data = _download(symbol)
    except Exception:
        if cached is not None:
            return cached  # hors ligne : dernier instantané connu
        raise
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def cotations(symboles: list[str], max_age_minutes: float = 15.0, cache_dir: Path | None = None) -> dict[str, dict]:
    """Cours et capitalisation de nombreux tickers d'un coup (API v7 quote, lots de 150), cache court par lot."""
    import hashlib

    out: dict[str, dict] = {}
    syms = sorted({s.upper() for s in symboles if s})
    op = crumb = None
    for i in range(0, len(syms), 150):
        lot = syms[i:i + 150]
        cle = hashlib.sha1(",".join(lot).encode()).hexdigest()[:16]
        path = (cache_dir or CACHE_DIR) / f"yahoo_quotes_{cle}.json"
        if path.exists() and time.time() - path.stat().st_mtime < max_age_minutes * 60:
            res = json.loads(path.read_text())
        else:
            if op is None:
                op, crumb = _opener()
            try:
                res = _get(op, f"{BASE}/v7/finance/quote?symbols={','.join(lot)}&crumb={crumb}")["quoteResponse"]["result"]
            except Exception:
                if not path.exists():
                    raise
                res = json.loads(path.read_text())
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(res))
        for q in res:
            out[q["symbol"]] = {"prix": q.get("regularMarketPrice"), "capitalisation": q.get("marketCap"), "devise": q.get("currency"),
                                "variation_jour": q.get("regularMarketChangePercent"), "nom": q.get("longName") or q.get("shortName"),
                                "per_yahoo": q.get("trailingPE"), "plus_haut_52s": q.get("fiftyTwoWeekHigh"), "plus_bas_52s": q.get("fiftyTwoWeekLow")}
    return out
