"""Agent de base : collecte, analyse, signal. Spécialisé par équipe."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .signal import Signal


@dataclass
class MarketData:
    """Vue de marché fournie à un agent par la couche data."""

    ticker: str
    prices: list[float] = field(default_factory=list)   # chronologique
    volumes: list[float] = field(default_factory=list)
    fundamentals: dict[str, float] = field(default_factory=dict)

    def returns(self) -> list[float]:
        if len(self.prices) < 2:
            return []
        return [
            (self.prices[i] / self.prices[i - 1]) - 1.0
            for i in range(1, len(self.prices))
        ]

    def momentum(self, lookback: int = 20) -> float:
        if len(self.prices) < lookback + 1:
            return 0.0
        return self.prices[-1] / self.prices[-1 - lookback] - 1.0

    def volatility(self, lookback: int = 30) -> float:
        rets = self.returns()[-lookback:]
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var)

    def zscore(self, lookback: int = 30) -> float:
        window = self.prices[-lookback:]
        if len(window) < 2:
            return 0.0
        mean = sum(window) / len(window)
        var = sum((p - mean) ** 2 for p in window) / len(window)
        sd = math.sqrt(var)
        if sd == 0.0:
            return 0.0
        return (window[-1] - mean) / sd


@dataclass
class AgentReport:
    """Rapport remonté par un agent à son manager."""

    agent: str
    summary: str
    signals: list[Signal] = field(default_factory=list)
    data_quality: float = 1.0  # [0, 1]
    context: dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """Agent spécialisé sur un périmètre précis.

    Principe : l'agent ne donne pas une opinion,
    il applique des règles quantitatives sur les données et produit des
    signaux normalisés. La couche LLM (phase 4) enrichira l'analyse
    fondamentale/technique mais ne remplace pas la discipline quantitative.
    """

    name: str = "agent"
    scope: str = "général"

    def __init__(self, name: str | None = None, scope: str | None = None) -> None:
        if name:
            self.name = name
        if scope:
            self.scope = scope

    @abstractmethod
    def universe(self) -> list[str]:
        """Tickers suivis par l'agent."""

    @abstractmethod
    def analyze(self, data: dict[str, MarketData]) -> AgentReport:
        """Analyse les données du périmètre et émet des signaux."""

    def report_header(self) -> str:
        return f"[{self.name}] périmètre: {self.scope}"


class QuantAgent(Agent):
    """Agent quantitatif concret : momentum + mean-reversion + vol.

    Utilisé tel quel en mode simulation, ou comme classe de base pour les
    agents réels qui y grefferont des données fines et (phase 4) un LLM.
    """

    def __init__(
        self,
        name: str | None = None,
        scope: str | None = None,
        tickers: list[str] | None = None,
        *,
        mom_lookback: int = 20,
        mr_lookback: int = 30,
        mom_weight: float = 0.5,
        mr_weight: float = 0.5,
    ) -> None:
        super().__init__(name, scope)
        self._tickers = list(tickers or [])
        self.mom_lookback = mom_lookback
        self.mr_lookback = mr_lookback
        self.mom_weight = mom_weight
        self.mr_weight = mr_weight
        self._last_cross_rank: dict[str, float] = {}

    def universe(self) -> list[str]:
        return list(self._tickers)

    def analyze(self, data: dict[str, MarketData]) -> AgentReport:
        """Analyse multi-facteurs calibrée façon analyste quant (Jane Street).

        Facteurs : momentum vol-ajusté, mean-reversion, qualité de tendance
        (R²), régime de vol (percentile glissant) et rang cross-sectional.
        La conviction est calibrée en probabilité (|score| via sigmoïde),
        la confiance pénalise la vol extrême ET les samples courts.
        """
        from .signal import Signal, SignalDirection, TimeHorizon
        from ..backtest.strategies import momentum_score, trend_quality, realized_vol

        import numpy as np

        signals: list[Signal] = []
        summaries: list[str] = []

        raw_scores: dict[str, float] = {}
        vols: dict[str, float] = {}
        tq_by_tk: dict[str, float] = {}
        vol_regime_by_tk: dict[str, float] = {}
        for ticker in self.universe():
            md = data.get(ticker)
            if md is None or len(md.prices) < max(self.mom_lookback, self.mr_lookback, 63) + 1:
                continue
            arr = np.asarray(md.prices, dtype=float)
            momentum = momentum_score(arr, self.mom_lookback)
            # Facteurs élite (niveau desk) : tri-horizon, Sharpe d'actif, drawdown
            mom_fast = momentum_score(arr, max(10, self.mom_lookback // 4))
            mom_slow = momentum_score(arr, min(len(arr) - 1, max(120, self.mom_lookback * 3)))
            tri_horizon = 0.25 * mom_fast + 0.55 * momentum + 0.20 * mom_slow
            rets = np.diff(arr) / arr[:-1]
            sd = float(np.std(rets[-60:], ddof=1)) if len(rets) >= 10 else 0.0
            asset_sharpe = float(np.mean(rets[-60:]) / sd) if sd > 1e-9 else 0.0
            peak = float(np.max(arr))
            cur_dd = max(0.0, 1.0 - float(arr[-1]) / peak) if peak > 0 else 0.0
            zscore = md.zscore(self.mr_lookback)
            vol = realized_vol(arr, 30)
            tq = trend_quality(arr, min(90, len(arr) - 1))
            long_vol = realized_vol(arr, min(252, len(arr) - 1))
            vol_regime = 0.0 if long_vol <= 0 else max(-1.0, min(1.0, (vol - long_vol) / long_vol))
            raw_scores[ticker] = momentum
            vols[ticker] = vol
            tq_by_tk[ticker] = tq
            vol_regime_by_tk[ticker] = vol_regime

        if raw_scores:
            n = len(raw_scores)
            order = sorted(raw_scores, key=lambda t: raw_scores[t])
            self._last_cross_rank = {t: (i - (n - 1) / 2.0) / max(1.0, n - 1) for i, t in enumerate(order)}

        for ticker in self.universe():
            md = data.get(ticker)
            if ticker not in raw_scores:
                continue
            momentum = raw_scores[ticker]
            zscore = md.zscore(self.mr_lookback)
            vol = vols[ticker]
            tq = tq_by_tk[ticker]
            vol_regime = vol_regime_by_tk[ticker]
            rank = self._last_cross_rank.get(ticker, 0.0)

            composite = (
                0.30 * np.tanh(tri_horizon)
                + 0.15 * np.tanh(momentum)
                + 0.10 * np.tanh(asset_sharpe)
                + self.mr_weight * 0.25 * (-np.tanh(zscore / 2.0))
                + 0.20 * tq
                + 0.10 * rank
            )
            composite -= min(cur_dd * 0.5, 0.15)  # pénalité de risque : drawdown en cours
            if vol_regime > 0.5:
                composite *= 0.5
            direction = (
                SignalDirection.LONG
                if composite > 0.02
                else SignalDirection.SHORT
                if composite < -0.02
                else SignalDirection.NEUTRAL
            )
            conviction = 1.0 / (1.0 + np.exp(-6.0 * abs(composite)))
            sample_penalty = min(1.0, len(md.prices) / 252.0)
            confidence = max(0.0, min(1.0, (1.0 - min(vol, 0.60) / 0.60) * sample_penalty))

            signal = Signal(
                agent=self.name,
                ticker=ticker,
                direction=direction,
                conviction=conviction,
                confidence=confidence,
                horizon=TimeHorizon.SWING,
                thesis=(
                    f"momentum vol-aj {momentum:+.2f} ({self.mom_lookback}p), "
                    f"z {zscore:+.2f}, tendance R² {tq:+.2f}, "
                    f"régime vol {vol_regime:+.0%}, rang {rank:+.2f}"
                ),
                metrics={
                    "momentum": momentum,
                    "zscore": zscore,
                    "volatility": vol,
                    "trend_quality": tq,
                    "vol_regime": vol_regime,
                    "cross_rank": rank,
                    "composite": composite,
                },
            )
            if signal.validate():
                raise ValueError(f"signal invalide: {signal.validate()}")
            signals.append(signal)
            summaries.append(f"{ticker}: {signal.thesis}")

        return AgentReport(
            agent=self.name,
            summary="; ".join(summaries) if summaries else "aucune donnée",
            signals=signals,
            data_quality=1.0 if signals else 0.0,
        )
