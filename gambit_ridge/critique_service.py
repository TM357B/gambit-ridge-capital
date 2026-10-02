"""Orchestration de l'esprit critique managérial : chaque manager backteste
indépendamment les stratégies de son département sur SON univers de données,
puis propose des ajustements. Tourne en arrière-plan pour ne jamais bloquer
le dashboard ; les résultats sont persistés dans data_cache/manager_critique.json
et exposés via /api/critique."""
from __future__ import annotations

import threading
import traceback

import numpy as np

from .manager_critique import critique_team, load_critiques

_LOCK = threading.Lock()
_STATUS: dict = {"running": False, "last_error": None, "done_teams": []}


def _universe_for_team(team: str) -> dict[str, np.ndarray] | None:
    """Univers de prix propre à chaque département (données réelles quand dispo)."""
    try:
        if team == "Macro":
            from .backtest_cli import _load_prices
            prices, _ = _load_prices("fred")
            return prices
        if team == "Forex":
            from .data.fred_fx import load_fx_universe
            prices, _ = load_fx_universe()
            return prices
        if team == "Crypto":
            from .backtest_service import _binance_registry
            prices, _ = _binance_registry()
            return prices
        if team in ("Micro", "IA & Tech", "Commodities"):
            from .backtest_cli import _load_prices
            prices, _ = _load_prices("synth")
            return prices
    except Exception:
        return None
    return None


def run_all_critiques() -> dict:
    """Exécute la critique de tous les managers (bloquant, ~1-2 min)."""
    global _STATUS
    with _LOCK:
        if _STATUS["running"]:
            return {"status": "already_running", **_STATUS}
        _STATUS = {"running": True, "last_error": None, "done_teams": []}
    results: dict = {}
    teams = ["Macro", "Forex", "Crypto", "Micro", "IA & Tech", "Commodities"]
    for team in teams:
        prices = _universe_for_team(team)
        if not prices or len(next(iter(prices.values()), [])) < 100:
            results[team] = {"error": "univers de données indisponible"}
            continue
        try:
            r = critique_team(team, prices)
            results[team] = {
                "date": r.date,
                "backtests": [vars(b) for b in r.backtests],
                "agent_scores": r.agent_scores,
                "adjustments": r.adjustments,
                "overall_verdict": r.overall_verdict,
            }
            _STATUS["done_teams"].append(team)
        except Exception as exc:  # noqa: BLE001
            results[team] = {"error": str(exc)}
            _STATUS["last_error"] = f"{team}: {exc}"
    _STATUS["running"] = False
    return results


def start_critiques_async() -> dict:
    """Lance la critique en arrière-plan (non bloquant pour l'UI)."""
    if _STATUS["running"]:
        return {"status": "already_running"}
    t = threading.Thread(target=run_all_critiques, daemon=True)
    t.start()
    return {"status": "started"}


def get_critique_state() -> dict:
    """État courant pour le dashboard : résultats persistés + statut du run."""
    return {
        "status": "running" if _STATUS["running"] else "idle",
        "last_error": _STATUS["last_error"],
        "done_teams": _STATUS["done_teams"],
        "critiques": load_critiques(),
    }
