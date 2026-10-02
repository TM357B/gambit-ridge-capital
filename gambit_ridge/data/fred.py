"""Connecteur FRED (Federal Reserve Economic Data) — gratuit, sans clé.

Séries décennales officielles : indices, taux, forex, matières, volatilité.
Le CSV fredgraph.csv est public et stable ; pas de limite de débit stricte
mais on met en cache disque par série pour la reproductibilité.
"""

from __future__ import annotations

import io
import csv
import time
import urllib.request
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data_cache"

FRED_SERIES = {
    "SP500": "S&P 500",
    "NASDAQCOM": "Nasdaq Composite",
    "DGS10": "Treasuries 10 ans",
    "T10Y2Y": "Pente 10y-2y",
    "DGS2": "Treasuries 2 ans",
    "DCOILBRENTEU": "Brent",
    "DTWEXBGS": "Dollar index broad",
    "VIXCLS": "VIX",
    "DEXUSEU": "USD/EUR",
    "DEXJPUS": "JPY/USD",
    "CPIAUCSL": "CPI US (mensuel)",
}


class FredConnector:
    """Téléchargeur de séries FRED avec cache disque par série."""

    BASE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR

    def _cache_path(self, series_id: str) -> Path:
        return self.cache_dir / f"fred_{series_id}.csv"

    def fetch_series(self, series_id: str) -> tuple[list[str], np.ndarray]:
        """Retourne (dates ISO, valeurs) avec les points manquants (.) exclus."""
        path = self._cache_path(series_id)
        text = None
        stale = None
        if path.exists():
            try:
                text = path.read_text()
                if "observation" not in text.split("\n")[0]:
                    text = None
            except Exception:
                text = None
            # cache valable 24 h : sans expiration, les séries restaient figées
            if text is not None and time.time() - path.stat().st_mtime > 24 * 3600:
                stale, text = text, None
        if text is None:
            req = urllib.request.Request(
                f"{self.BASE_URL}?id={series_id}",
                headers={"User-Agent": "gambit-ridge/0.1"},
            )
            last_err = None
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        text = resp.read().decode()
                    last_err = None
                    break
                except Exception as exc:
                    last_err = exc
                    time.sleep(1 + attempt)
            if last_err is not None:
                if stale is not None:  # hors ligne : on garde l'ancienne version
                    text = stale
                else:
                    raise last_err
            else:
                self.cache_dir.mkdir(exist_ok=True)
                path.write_text(text)

        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        dates: list[str] = []
        values: list[float] = []
        for row in reader:
            if len(row) < 2:
                continue
            date, raw = row[0], row[1]
            if raw in (".", ""):
                continue
            try:
                values.append(float(raw))
                dates.append(date)
            except ValueError:
                continue
        return dates, np.array(values, dtype=float)
