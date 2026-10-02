"""Conseil : chaque manager rapporte ses signaux clés → briefing quotidien.

Le conseil applique le sizing quantitatif (Kelly recadré + vol-targeting),
vérifie les limites de risque, et ajuste le poids du thème IA vers
l'objectif d'allocation voulu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core.agent import MarketData
from ..core.manager import Manager, TeamSynthesis
from ..core.risk import RiskLimits
from ..core.sizing import kelly_fraction, vol_target_size
from ..core.signal import Signal, TimeHorizon


@dataclass
class DailyBriefing:
    day: date
    sections: list[TeamSynthesis] = field(default_factory=list)
    proposed_allocation: dict[str, float] = field(default_factory=dict)
    risk_reasons: list[str] = field(default_factory=list)
    ia_share: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day.isoformat(),
            "teams": [s.to_dict() for s in self.sections],
            "proposed_allocation": {
                k: round(v, 4) for k, v in self.proposed_allocation.items()
            },
            "risk_reasons": list(self.risk_reasons),
            "ia_share": round(self.ia_share, 3),
        }


class Council:
    """Réunion quotidienne des managers."""

    def __init__(
        self,
        managers: list[Manager],
        risk: RiskLimits | None = None,
        *,
        ia_tickers: set[str] | None = None,
    ) -> None:
        self.managers = managers
        self.risk = risk or RiskLimits()
        self.ia_tickers = ia_tickers or set()

    def meeting(self, data: dict[str, MarketData], day: date | None = None) -> DailyBriefing:
        day = day or date.today()
        sections = [m.run(data) for m in self.managers]

        allocation = self._size_positions(sections)
        verdict = self.risk.check(allocation)
        ia_share = self.risk.ia_theme_weight(allocation, self.ia_tickers)

        return DailyBriefing(
            day=day,
            sections=sections,
            proposed_allocation=allocation,
            risk_reasons=verdict.reasons,
            ia_share=ia_share,
        )

    def _size_positions(self, sections: list[TeamSynthesis]) -> dict[str, float]:
        """Convertis les signaux du conseil en allocation pondérée.

        Position = score × vol-target, multiplié par le Kelly recadré
        implicite d'une stratégie momentum/mean-reversion historiquement
        proche de 55% win-rate, ratio gain/perte 1.3.
        """
        kf = kelly_fraction(0.55, 1.3, fraction=0.25)
        allocation: dict[str, float] = {}
        for section in sections:
            for signal in section.top_signals:
                weight = self._weight_for(signal, kf)
                if weight != 0.0:
                    allocation[signal.ticker] = weight
        # Normalisation : l'exposition brute ne dépasse pas la limite
        gross = sum(abs(w) for w in allocation.values())
        if gross > self.risk.max_total_gross:
            scale = self.risk.max_total_gross / gross
            allocation = {t: w * scale for t, w in allocation.items()}
        return allocation

    def _weight_for(self, signal: Signal, kelly: float) -> float:
        vol = signal.metrics.get("volatility", 0.0)
        if signal.horizon is TimeHorizon.STRATEGIC:
            target_vol = 0.10
        else:
            target_vol = 0.15
        base = vol_target_size(signal.score(), vol, target_vol=target_vol)
        return max(-self.risk.max_position, min(self.risk.max_position, base * kelly * 10))
