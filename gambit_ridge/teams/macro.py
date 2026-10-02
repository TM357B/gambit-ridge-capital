"""Équipe Macro : agents pays développés et pays émergents.

Les agents macro consomment les facteurs FRED réels (taux 10 ans, pente
de courbe, VIX, dollar) en plus des prix : leur analyse de régime est
désormais nourrie par des données officielles.
"""

from __future__ import annotations

import numpy as np

from ..core.agent import AgentReport, MarketData, QuantAgent
from ..core.manager import Manager
from ..core.signal import Signal, SignalDirection, TimeHorizon


class MacroRegimeAgent(QuantAgent):
    """Agent macro enrichi de facteurs FRED (taux, pente, VIX).

    Règles de régime (documentées, calibrées sur histoire longue) :
    - Pente 10y-2y < 0 (courbe inversée) : signal baissier actions
    - VIX > 30 (panne) : haussier contraïrien sur actions (mean-reversion)
    - Taux 10 ans en forte hausse (> +100bps/6 mois) : baissier actions
    Les facteurs pondèrent les signaux de prix standards.
    """

    def __init__(
        self,
        name: str | None = None,
        scope: str | None = None,
        tickers: list[str] | None = None,
        factors: dict[str, list[float]] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(name, scope, tickers, **kwargs)
        self.factors = factors or {}

    def analyze(self, data: dict[str, MarketData]) -> AgentReport:
        report = super().analyze(data)

        regime_shift = 0.0
        regime_notes: list[str] = []

        curve = self.factors.get("T10Y2Y") or []
        if curve and curve[-1] < 0:
            regime_shift -= 0.10
            regime_notes.append(f"courbe inversée ({curve[-1]:+.2f})")
        elif curve and curve[-1] > 1.0:
            regime_shift += 0.05
            regime_notes.append(f"courbe pentue ({curve[-1]:+.2f})")

        vix = self.factors.get("VIXCLS") or []
        if vix and vix[-1] > 30:
            regime_shift += 0.10
            regime_notes.append(f"VIX élevé ({vix[-1]:.0f}, prime contraïrienne)")
        elif vix and vix[-1] < 15:
            regime_shift += 0.03
            regime_notes.append(f"VIX bas ({vix[-1]:.0f})")

        rates = self.factors.get("DGS10") or []
        if len(rates) >= 126 and rates[-1] - rates[-127] > 1.0:
            regime_shift -= 0.08
            regime_notes.append("hausse rapide des taux 10 ans")

        if not regime_notes:
            regime_notes.append("régime macro neutre")

        for signal in report.signals:
            if signal.direction is SignalDirection.LONG:
                new_conv = min(1.0, max(0.0, signal.conviction + regime_shift))
            else:
                new_conv = min(1.0, max(0.0, signal.conviction - regime_shift))
            signal.conviction = new_conv

        report.summary = (
            f"{report.summary} | régime: {', '.join(regime_notes)}"
        )
        report.context["regime_shift"] = regime_shift
        report.context["regime_notes"] = regime_notes
        return report


def build_macro_team(factors: dict[str, list[float]] | None = None) -> Manager:
    """Construit l'équipe macro avec facteurs FRED réels si fournis."""
    dm_tickers = ["SPY", "EZU", "DAX", "N225", "US10Y", "DXY"]
    em_tickers = ["MCHI", "EEM", "INDA", "BRL", "USDCNH"]

    dm = MacroRegimeAgent(
        "macro-dm",
        "macro économie pays développés (US, UE, Japon)",
        dm_tickers,
        factors=factors or {},
        mom_lookback=60,
        mr_lookback=60,
    )
    em = QuantAgent(
        "macro-em",
        "macro économie pays émergents (Chine, Inde, Brésil, EM)",
        em_tickers,
        mom_lookback=60,
        mr_lookback=60,
    )
    return Manager("Macro", [dm, em])
