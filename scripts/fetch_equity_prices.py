"""Récupération des prix quotidiens (close ajusté) pour les tickers cotés
du pipeline fondamentaux, via l'API publique Yahoo Finance chart.

Sortie : data/equity_prices.csv (format wide : date + une colonne par ticker).
Tickers privés (SPACEX) exclus — pas de prix de marché.
"""
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TICKERS = ["PLTR", "NVDA", "BRK-B", "ASML", "AMD", "TSLA", "JPM", "MSFT"]
OUT = Path(__file__).resolve().parent.parent / "data" / "equity_prices.csv"


def fetch(symbol: str) -> dict[str, float]:
    now = int(time.time()) + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1=1420070400&period2={now}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out: dict[str, float] = {}
    for t, p in zip(ts, adj):
        if p is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        out[d] = float(p)
    return out


def main() -> None:
    series: dict[str, dict[str, float]] = {}
    for tk in TICKERS:
        series[tk] = fetch(tk)
        print(tk, len(series[tk]), "bars")
        time.sleep(1.0)
    dates = sorted(set().union(*[set(s) for s in series.values()]))
    tickers = list(series)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + tickers)
        for d in dates:
            w.writerow([d] + [series[tk].get(d, "") for tk in tickers])
    print("OK", OUT, len(dates), "dates")


if __name__ == "__main__":
    main()
