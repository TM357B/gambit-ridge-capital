"""Manager : dirige une équipe d'agents, filtre et agrège leurs signaux."""

from __future__ import annotations

from dataclasses import dataclass, field

from .agent import Agent, AgentReport, MarketData
from .signal import Signal, SignalDirection


@dataclass
class TeamSynthesis:
    """Synthèse produite par un manager pour le conseil."""

    team: str
    headline: str
    top_signals: list[Signal] = field(default_factory=list)
    per_agent: list[AgentReport] = field(default_factory=list)
    aggregate_score: float = 0.0
    watchlist: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "team": self.team,
            "headline": self.headline,
            "aggregate_score": round(self.aggregate_score, 3),
            "top_signals": [s.to_dict() for s in self.top_signals],
            "watchlist": list(self.watchlist),
            "agents": [
                {"agent": r.agent, "summary": r.summary, "data_quality": r.data_quality}
                for r in self.per_agent
            ],
        }


class Manager:
    """Manager d'équipe : pattern présent dans toutes les équipes.

    Rôles :
    1. Répartit les données de marché aux agents de son équipe
    2. Collecte les rapports, filtre les signaux faibles ou invalides
    3. Sélectionne les signaux les plus importants pour le conseil
    4. Rédige la synthèse quotidienne de son équipe
    """

    def __init__(self, team: str, agents: list[Agent], *, max_signals: int = 5) -> None:
        self.team = team
        self.agents = agents
        self.max_signals = max_signals

    def run(self, data: dict[str, MarketData]) -> TeamSynthesis:
        reports: list[AgentReport] = []
        for agent in self.agents:
            scoped = {
                t: d
                for t, d in data.items()
                if t in agent.universe()
            }
            reports.append(agent.analyze(scoped))

        all_signals = [s for r in reports for s in r.signals]
        valid = [s for s in all_signals if not s.validate()]
        ranked = sorted(valid, key=lambda s: abs(s.score()), reverse=True)

        # Suppression des signaux contradictoires sur un même ticker :
        # on garde le plus fort (le manager tranche).
        best_per_ticker: dict[str, Signal] = {}
        for s in ranked:
            if s.ticker not in best_per_ticker:
                best_per_ticker[s.ticker] = s

        top = list(best_per_ticker.values())[: self.max_signals]
        agg = (
            sum(s.score() for s in valid) / len(valid)
            if valid
            else 0.0
        )

        headline = self._headline(top, agg)
        watchlist = sorted({s.ticker for s in valid if abs(s.score()) < 0.15})

        return TeamSynthesis(
            team=self.team,
            headline=headline,
            top_signals=top,
            per_agent=reports,
            aggregate_score=agg,
            watchlist=watchlist,
        )

    def _headline(self, top: list[Signal], agg: float) -> str:
        if not top:
            return "aucun signal exploitable aujourd'hui"
        bias = (
            "haussier" if agg > 0.05
            else "baissier" if agg < -0.05
            else "neutre"
        )
        lead = top[0]
        return (
            f"Biais {bias} (score agrégé {agg:+.2f}). "
            f"Signal principal : {lead.ticker} {lead.direction.value} "
            f"({lead.conviction:.0%} conviction, {lead.confidence:.0%} confiance)"
        )
