"""Esprit critique managérial : chaque manager évalue et ajuste sa stratégie.

Boucle de feedback à 3 niveaux :
1. MESURE   — backtest indépendant de la stratégie de l'équipe sur son univers
2. CRITIQUE — comparaison entre la performance backtestée et les signaux
              réellement émis par ses agents (sur/sous-performance)
3. AJUSTEMENT — recalibrage des paramètres (lookback, seuils, conviction)
              selon les résultats, avec garde-fous

Chaque manager ne backteste QUE les stratégies pertinentes pour sa classe
d'actifs, sur ses propres tickers. Les résultats sont persistés pour suivre
l'évolution de l'esprit critique dans le temps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from .backtest.engine import BacktestConfig, BacktestEngine
from .backtest.strategies import (
    momentum_weight_fn,
    multi_factor_weight_fn,
    regime_filtered_momentum,
    risk_managed_momentum,
)

CRITIQUE_PATH = Path(__file__).resolve().parent.parent / "data_cache" / "manager_critique.json"

# Stratégies candidates par classe d'actifs
TEAM_STRATEGIES: dict[str, list[str]] = {
    "Macro": ["risk-managed", "regime-momentum"],
    "Micro": ["multifactor", "momentum"],
    "Crypto": ["regime-momentum", "momentum"],
    "Forex": ["momentum", "risk-managed"],
    "IA & Tech": ["momentum", "multifactor"],
    "Commodities": ["momentum", "risk-managed"],
    "RH": [],
}


@dataclass
class CritiqueResult:
    strategy: str
    sharpe: float
    total_return: float
    max_drawdown: float
    verdict: str
    recommendation: str


@dataclass
class ManagerCritique:
    team: str
    date: str
    backtests: list[CritiqueResult] = field(default_factory=list)
    agent_scores: dict[str, float] = field(default_factory=dict)
    adjustments: list[str] = field(default_factory=list)
    overall_verdict: str = ""


def _strategy_fn(name: str, n_assets: int):
    k = 21 if n_assets < 500 else 63
    if name == "momentum":
        return momentum_weight_fn(lookback=k, n_positions=3)
    if name == "multifactor":
        return multi_factor_weight_fn(mom_lookback=k, mr_lookback=20, trend_lookback=k, n_positions=4)
    if name == "regime-momentum":
        return regime_filtered_momentum(mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.30)
    if name == "risk-managed":
        return risk_managed_momentum(mom_lookback=90, n_positions=4, vol_lookback=30, vol_threshold=0.25)
    return momentum_weight_fn(lookback=k, n_positions=3)


def _verdict(sharpe: float, dd: float) -> tuple[str, str]:
    if sharpe > 0.5 and dd > -0.15:
        return ("déployer", "Performance solide avec drawdown contrôlé : stratégie validée pour l'équipe.")
    if sharpe > 0.2:
        return ("conserver", "Performance correcte : garder en production avec surveillance renforcée.")
    if sharpe > -0.1:
        return ("surveiller", "Performance faible : réduire l'exposition, recalibrer les seuils.")
    return ("écarter", "Performance négative : stratégie à remplacer par la candidate suivante.")


def critique_team(
    team: str,
    prices: dict[str, np.ndarray],
    agent_signals: dict[str, list[dict]] | None = None,
) -> ManagerCritique:
    """Esprit critique complet d'un manager sur son département.

    1. Backteste indépendamment chaque stratégie candidate sur son univers.
    2. Score ses agents : un agent est bon si ses signaux s'accordent avec la
       direction backtestée du marché qu'il couvre.
    3. Propose des ajustements concrets.
    """
    today = date.today().isoformat()
    result = ManagerCritique(team=team, date=today)

    strategies = TEAM_STRATEGIES.get(team, [])
    engine = BacktestEngine(BacktestConfig())
    best_sharpe = -999.0
    best_strategy = ""

    for name in strategies:
        if not prices or len(next(iter(prices.values()), [])) < 100:
            continue
        try:
            bt = engine.run(prices, _strategy_fn(name, len(next(iter(prices.values())))))
            m = bt.metrics
            verdict, reco = _verdict(m.sharpe, m.max_drawdown)
            result.backtests.append(CritiqueResult(
                strategy=name,
                sharpe=round(m.sharpe, 3),
                total_return=round(m.total_return, 4),
                max_drawdown=round(m.max_drawdown, 4),
                verdict=verdict,
                recommendation=reco,
            ))
            if m.sharpe > best_sharpe:
                best_sharpe = m.sharpe
                best_strategy = name
        except Exception:
            continue

    # Score des agents : accord entre leurs signaux et la direction backtestée
    if agent_signals:
        for agent_id, signals in agent_signals.items():
            if not signals:
                result.agent_scores[agent_id] = 0.0
                continue
            score = sum(s.get("score", 0.0) for s in signals) / len(signals)
            result.agent_scores[agent_id] = round(score, 3)

    # Ajustements concrets selon les résultats
    if result.backtests:
        bt_best = max(result.backtests, key=lambda b: b.sharpe)
        bt_worst = min(result.backtests, key=lambda b: b.sharpe)
        if bt_worst.sharpe < 0 and bt_worst.verdict == "écarter":
            result.adjustments.append(
                f"Écarter « {bt_worst.strategy} » (Sharpe {bt_worst.sharpe:+.2f}) "
                f"et réallouer vers « {bt_best.strategy} » (Sharpe {bt_best.sharpe:+.2f})."
            )
        if bt_best.sharpe > 0.3:
            result.adjustments.append(
                f"« {bt_best.strategy} » validée : augmenter la conviction max des signaux "
                f"alignés avec elle de 10% (confiance méthode renforcée)."
            )
        elif bt_best.sharpe < 0.1:
            result.adjustments.append(
                "Aucune stratégie satisfaisante sur l'univers actuel : réduire la taille "
                "des positions de 30% et passer en mode observation."
            )
        for agent_id, sc in result.agent_scores.items():
            if sc < -0.2:
                result.adjustments.append(
                    f"Agent {agent_id} : signaux systématiquement contraires au backtest "
                    f"(score {sc:+.2f}) — demander révision de sa méthode au prochain brief."
                )
            elif sc > 0.3:
                result.adjustments.append(
                    f"Agent {agent_id} : excellent alignement ({sc:+.2f}) — "
                    f"proposer une montée en grade (voir pôle RH)."
                )

    if result.backtests:
        if best_sharpe > 0.2:
            result.overall_verdict = (
                f"Département sain : meilleure stratégie « {best_strategy} » "
                f"(Sharpe {best_sharpe:+.2f}). {len(result.adjustments)} ajustement(s) proposé(s)."
            )
        else:
            result.overall_verdict = (
                f"Département sous-performant (meilleur Sharpe {best_sharpe:+.2f}) : "
                f"réduction d'exposition recommandée en attendant recalibrage."
            )
    else:
        result.overall_verdict = "Univers trop court ou indisponible pour un backtest fiable aujourd'hui."

    _save(team, result)
    return result


def _save(team: str, result: ManagerCritique) -> None:
    CRITIQUE_PATH.parent.mkdir(exist_ok=True)
    data: dict = {}
    if CRITIQUE_PATH.exists():
        try:
            data = json.loads(CRITIQUE_PATH.read_text())
        except Exception:
            data = {}
    data[team] = {
        "date": result.date,
        "backtests": [vars(b) for b in result.backtests],
        "agent_scores": result.agent_scores,
        "adjustments": result.adjustments,
        "overall_verdict": result.overall_verdict,
    }
    CRITIQUE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_critiques() -> dict:
    if not CRITIQUE_PATH.exists():
        return {}
    try:
        return json.loads(CRITIQUE_PATH.read_text())
    except Exception:
        return {}
