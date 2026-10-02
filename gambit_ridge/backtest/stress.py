"""Stress tests : évaluer les stratégies sur les grandes crises financières.

Les fenêtres de crise sont définies en DATES RÉELLES (ISO) et résolues
en indices par rapport aux dates de la série chargée. Les anciennes
fenêtres à index fixe dépendaient de l'univers et tombaient au mauvais
endroit selon les données (biais B2 de l'audit Phase 0).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .engine import BacktestEngine, BacktestResult


@dataclass
class CrisisWindow:
    name: str
    start: int   # index de début (approximation en périodes)
    end: int     # index de fin


@dataclass(frozen=True)
class DatedCrisis:
    """Crise définie par des dates ISO, indépendante de l'univers chargé."""
    name: str
    start: str
    end: str


DATED_CRISES: list[DatedCrisis] = [
    DatedCrisis("Krach 1987 (lundi noir)", "1987-10-01", "1987-12-31"),
    DatedCrisis("Bulle dot-com 2000-2002", "2000-03-01", "2002-10-31"),
    DatedCrisis("Crise financière 2008", "2007-10-01", "2009-03-31"),
    DatedCrisis("COVID mars 2020", "2020-02-15", "2020-05-31"),
    DatedCrisis("Crise des taux 2022", "2022-01-03", "2022-10-31"),
]


def resolve_crisis_windows(dates: list[str]) -> list[CrisisWindow]:
    """Convertit les crises datées en indices sur la série chargée.

    dates : liste de dates ISO alignées avec les prix (une par période).
    Les crises hors de l'historique disponible sont ignorées.
    """
    idx = {d: i for i, d in enumerate(dates)}
    windows: list[CrisisWindow] = []
    for c in DATED_CRISES:
        in_range = [i for d, i in idx.items() if c.start <= d <= c.end]
        if not in_range:
            continue
        windows.append(CrisisWindow(c.name, min(in_range), max(in_range)))
    return windows


def run_stress_tests(
    prices: dict[str, np.ndarray],
    weight_fn,
    windows: list[CrisisWindow] | None = None,
) -> dict[str, BacktestResult]:
    """Backteste la stratégie en isolation sur chaque fenêtre de crise.

    Retourne un dictionnaire nom de crise -> résultat de backtest restreint
    à la fenêtre (avec burn-in pour que les indicateurs techniques soient
    déjà "chauds" à l'entrée de la crise).
    """
    engine = BacktestEngine()
    results: dict[str, BacktestResult] = {}

    for window in (windows or []):
        sliced = {
            ticker: series[max(0, window.start - 100): window.end + 1]
            for ticker, series in prices.items()
        }
        sliced = {tk: s for tk, s in sliced.items() if len(s) > 10}
        if not sliced:
            continue

        def _fn(t, ctx, _w=window):
            # Réindexe : le temps local t correspond au temps global t + offset
            offset = max(0, _w.start - 100)
            return weight_fn(t + offset, ctx)

        results[window.name] = engine.run(sliced, _fn)

    return results
