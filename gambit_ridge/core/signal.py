"""Signal normalisé : seule monnaie commune entre tous les agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"          # quelques jours à quelques semaines
    POSITION = "position"    # plusieurs semaines à plusieurs mois
    STRATEGIC = "strategic"  # allocation de fond


@dataclass
class Signal:
    """Signal émis par un agent.

    conviction : [0, 1] — force de la thèse après analyse
    confidence : [0, 1] — qualité des données / fiabilité du modèle
    """

    agent: str
    ticker: str
    direction: SignalDirection
    conviction: float
    confidence: float
    horizon: TimeHorizon
    thesis: str
    risk_notes: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def score(self) -> float:
        """Score composite [-1, 1] utilisé pour l'agrégation et le sizing."""
        if self.direction is SignalDirection.NEUTRAL:
            return 0.0
        base = self.conviction * self.confidence
        return base if self.direction is SignalDirection.LONG else -base

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not 0.0 <= self.conviction <= 1.0:
            errors.append(f"conviction hors bornes: {self.conviction}")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append(f"confidence hors bornes: {self.confidence}")
        if not self.ticker:
            errors.append("ticker manquant")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "ticker": self.ticker,
            "direction": self.direction.value,
            "conviction": round(self.conviction, 3),
            "confidence": round(self.confidence, 3),
            "horizon": self.horizon.value,
            "thesis": self.thesis,
            "score": round(self.score(), 3),
            "risk_notes": list(self.risk_notes),
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
        }
