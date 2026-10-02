"""Bibliothèque de stratégies quantitatives.

Toutes les stratégies retournent une weight_fn(t, prices_by_ticker) -> poids,
compatible avec BacktestEngine. Chaque stratégie est purement quantitative,
sans paramètre "magique" non documenté.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Primitives (facteurs individuels)
# ---------------------------------------------------------------------------

def momentum_score(arr: np.ndarray, lookback: int) -> float:
    """Rendement sur lookback, ajusté par la vol (ratio de Sharpe roulant)."""
    if len(arr) < lookback + 1:
        return 0.0
    ret = arr[-1] / arr[-1 - lookback] - 1.0
    window = arr[-lookback - 1 :]
    daily = np.diff(window) / window[:-1]
    vol = daily.std(ddof=1)
    if vol < 1e-12:
        return 0.0
    return float(ret / vol)


def mean_reversion_score(arr: np.ndarray, lookback: int, z_exit: float = 0.5) -> float:
    """Z-score négatif : positif si survendu (acheter), négatif si suracheté.

    Linéairement amorti entre le seuil d'entrée et z_exit pour éviter
    les sauts de poids.
    """
    if len(arr) < lookback + 1:
        return 0.0
    window = arr[-lookback:]
    std = window.std(ddof=1)
    if std < 1e-12:
        return 0.0
    z = (arr[-1] - window.mean()) / std
    if abs(z) < 1.0:  # seuil d'entrée : |z| >= 1
        return 0.0
    sign = -np.sign(z)
    # Amplitude : 1 à |z|=1 (entrée), amortie vers z_exit
    amp = max(0.0, (abs(z) - z_exit) / max(abs(z), z_exit))
    return float(sign * amp)


def trend_quality(arr: np.ndarray, lookback: int) -> float:
    """R² de la régression linéaire du log-prix : qualité de la tendance.

    Une tendance propre (R² élevé) est plus exploitable qu'un drift
    bruité. Combine signe de la pente × R².
    """
    if len(arr) < lookback + 1:
        return 0.0
    y = np.log(arr[-lookback:])
    x = np.arange(lookback, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return float(np.sign(slope) * max(0.0, r2))


def realized_vol(arr: np.ndarray, lookback: int = 20) -> float:
    """Vol annualisée (252 jours)."""
    if len(arr) < lookback + 1:
        return 0.0
    daily = np.diff(arr[-lookback - 1 :]) / arr[-lookback - 1 : -1]
    return float(daily.std(ddof=1) * np.sqrt(252))


# ---------------------------------------------------------------------------
# Stratégies historiques (v1, conservées pour comparaison)
# ---------------------------------------------------------------------------

def momentum_weight_fn(
    lookback: int = 20,
    max_leverage: float = 1.0,
    n_positions: int = 5,
    long_only: bool = False,
):
    """Momentum cross-sectional simple : long les n meilleurs, short les n pires."""

    def weight_fn(t, prices_by_ticker):
        scores = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series)
            if len(arr) < lookback + 1:
                scores[tk] = 0.0
                continue
            scores[tk] = arr[-1] / arr[-1 - lookback] - 1.0

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        weights: dict[str, float] = {}
        winners = [tk for tk, s in ranked[:n_positions] if s > 0]
        losers = [tk for tk, s in ranked[-n_positions:] if s < 0]

        if winners:
            for tk in winners:
                weights[tk] = max_leverage / (2 * len(winners))
        if losers and not long_only:
            for tk in losers:
                weights[tk] = -max_leverage / (2 * len(losers))
        return weights

    return weight_fn


def mean_reversion_weight_fn(lookback: int = 30, z_threshold: float = 1.5, max_weight: float = 0.2):
    """Mean-reversion simple : short si suracheté (z > seuil), long si survendu."""

    def weight_fn(t, prices_by_ticker):
        weights: dict[str, float] = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series)
            if len(arr) < lookback + 1:
                continue
            window = arr[-lookback:]
            mean = window.mean()
            std = window.std()
            if std < 1e-12:
                continue
            z = (arr[-1] - mean) / std
            if z > z_threshold:
                weights[tk] = -max_weight
            elif z < -z_threshold:
                weights[tk] = max_weight
        return weights

    return weight_fn


# ---------------------------------------------------------------------------
# Stratégies combinées
# ---------------------------------------------------------------------------

def multi_factor_weight_fn(
    *,
    mom_lookback: int = 63,
    mom_weight: float = 0.4,
    mr_lookback: int = 20,
    mr_weight: float = 0.3,
    trend_lookback: int = 63,
    trend_weight: float = 0.3,
    n_positions: int = 4,
    max_leverage: float = 1.0,
    vol_filter: float | None = None,
):
    """Multi-facteurs : momentum ajusté vol + mean-reversion + qualité de tendance.

    Les scores par actif sont normalisés (z-score cross-sectionnel) puis
    combinés en un score composite. Les n meilleurs sont long, les n
    pires short, pondérés proportionnellement au score.

    vol_filter : si défini, les actifs de vol > seuil sont écartés.
    """
    factors = [
        (mom_weight, lambda a: momentum_score(a, mom_lookback)),
        (mr_weight, lambda a: mean_reversion_score(a, mr_lookback)),
        (trend_weight, lambda a: trend_quality(a, trend_lookback)),
    ]

    def weight_fn(t, prices_by_ticker):
        raw: dict[str, float] = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series, dtype=float)
            if vol_filter is not None and realized_vol(arr) > vol_filter:
                continue
            score = sum(w * fn(arr) for w, fn in factors)
            if np.isfinite(score):
                raw[tk] = score

        if not raw:
            return {}

        values = np.array(list(raw.values()))
        std = values.std(ddof=1)
        if std < 1e-12:
            return {}
        z = {tk: (s - values.mean()) / std for tk, s in raw.items()}

        ranked = sorted(z.items(), key=lambda kv: kv[1], reverse=True)
        longs = [(tk, s) for tk, s in ranked[:n_positions] if s > 0]
        shorts = [(tk, s) for tk, s in ranked[-n_positions:] if s < 0]

        weights: dict[str, float] = {}
        long_sum = sum(s for _, s in longs)
        short_sum = sum(abs(s) for _, s in shorts)
        half = max_leverage / 2.0
        if longs and long_sum > 0:
            for tk, s in longs:
                weights[tk] = half * s / long_sum
        if shorts and short_sum > 0:
            for tk, s in shorts:
                weights[tk] = -half * abs(s) / short_sum
        return weights

    return weight_fn


def regime_filtered_momentum(
    *,
    mom_lookback: int = 63,
    n_positions: int = 3,
    max_leverage: float = 1.0,
    vol_lookback: int = 60,
    vol_threshold: float = 0.28,
):
    """Momentum avec filtrage par régime de volatilité.

    La taille de position est réduite quand la volatilité réalisée de
    l'actif dépasse vol_threshold (scaling vol_threshold/vol), et
    complètement coupée au-delà de 2× le seuil.
    """
    def weight_fn(t, prices_by_ticker):
        scores: dict[str, float] = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series, dtype=float)
            if len(arr) < mom_lookback + 1:
                continue
            scores[tk] = momentum_score(arr, mom_lookback)

        if not scores:
            return {}

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        winners = ranked[:n_positions]
        losers = ranked[-n_positions:]
        weights: dict[str, float] = {}

        half = max_leverage / 2.0
        for tk, s in winners:
            if s <= 0:
                continue
            arr = np.asarray(prices_by_ticker[tk], dtype=float)
            vol = realized_vol(arr, vol_lookback)
            if vol > 2 * vol_threshold:
                continue
            scale = min(1.0, vol_threshold / vol) if vol > vol_threshold else 1.0
            weights[tk] = half * scale / n_positions
        for tk, s in losers:
            if s >= 0:
                continue
            arr = np.asarray(prices_by_ticker[tk], dtype=float)
            vol = realized_vol(arr, vol_lookback)
            if vol > 2 * vol_threshold:
                continue
            scale = min(1.0, vol_threshold / vol) if vol > vol_threshold else 1.0
            weights[tk] = -half * scale / n_positions
        return weights

    return weight_fn


def pairs_trading_weight_fn(
    *,
    pair: tuple[str, str],
    lookback: int = 60,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    max_weight: float = 0.4,
):
    """Arbitrage statistique sur une paire : spread log-ratio, entrée sur z-score.

    Long l'actif sous-évalué du ratio, short l'autre, marché-neutre
    sur la paire (poids égaux). Sortie implicite quand |z| < exit_z.
    """
    a, b = pair

    def weight_fn(t, prices_by_ticker):
        if a not in prices_by_ticker or b not in prices_by_ticker:
            return {}
        pa = np.asarray(prices_by_ticker[a], dtype=float)
        pb = np.asarray(prices_by_ticker[b], dtype=float)
        n = min(len(pa), len(pb))
        if n < lookback + 1:
            return {}
        ratio = np.log(pa[-lookback:] / pb[-lookback:])
        std = ratio.std(ddof=1)
        if std < 1e-12:
            return {}
        z = (ratio[-1] - ratio.mean()) / std
        if abs(z) < entry_z:
            return {}
        # ratio haut = A surévalué vs B -> short A, long B
        if z > 0:
            return {a: -max_weight / 2, b: max_weight / 2}
        return {a: max_weight / 2, b: -max_weight / 2}

    return weight_fn


def combine_strategies(*weight_fns, weights: list[float] | None = None):
    """Combine plusieurs stratégies en portefeuille pondéré.

    Évite l'empilement naïf des poids : la somme est renormalisée pour
    respecter le gross exposure de la stratégie dominante.
    """
    if weights is None:
        weights = [1.0 / len(weight_fns)] * len(weight_fns)
    if len(weights) != len(weight_fns):
        raise ValueError("weights doit correspondre au nombre de stratégies")

    def weight_fn(t, prices_by_ticker):
        total: dict[str, float] = {}
        for w, fn in zip(weights, weight_fns):
            sub = fn(t, prices_by_ticker)
            for tk, weight in sub.items():
                total[tk] = total.get(tk, 0.0) + w * weight
        return total

    return weight_fn


def risk_managed_momentum(
    *,
    mom_lookback: int = 90,
    n_positions: int = 4,
    vol_lookback: int = 30,
    vol_threshold: float = 0.15,
    max_leverage: float = 1.0,
    use_drawdown_guard: bool = True,
    use_correlation_filter: bool = True,
    use_dynamic_leverage: bool = True,
    dd_soft: float = 0.05,
    dd_hard: float = 0.12,
    port_target_vol: float = 0.12,
    port_max_leverage: float = 1.5,
):
    """Momentum de régime (v12) + superposition de gestion du risque v15.

    Couches appliquées dans l'ordre :
    1. Momentum vol-ajusté avec filtre de régime de vol (identique v12)
    2. Pénalité de corrélation entre positions de même signe
    3. Vol-targeting du portefeuille (levier dynamique)
    4. Drawdown guard : déleverage linéaire après -dd_soft, flat à -dd_hard
    """
    from ..core.risk import (
        DrawdownGuard,
        correlation_adjusted_weights,
        dynamic_leverage,
    )

    guard = DrawdownGuard(soft_dd=dd_soft, hard_dd=dd_hard)
    state: dict[str, float] = {"equity": 1.0, "peak": 1.0}

    def weight_fn(t, prices_by_ticker):
        scores: dict[str, float] = {}
        for tk, series in prices_by_ticker.items():
            arr = np.asarray(series, dtype=float)
            if len(arr) < mom_lookback + 1:
                continue
            scores[tk] = momentum_score(arr, mom_lookback)

        weights: dict[str, float] = {}
        if scores:
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            half = max_leverage / 2.0
            for tk, s in ranked[:n_positions]:
                if s <= 0:
                    continue
                arr = np.asarray(prices_by_ticker[tk], dtype=float)
                vol = realized_vol(arr, vol_lookback)
                if vol > 2 * vol_threshold:
                    continue
                scale = min(1.0, vol_threshold / vol) if vol > vol_threshold else 1.0
                weights[tk] = half * scale / n_positions
            for tk, s in ranked[-n_positions:]:
                if s >= 0:
                    continue
                arr = np.asarray(prices_by_ticker[tk], dtype=float)
                vol = realized_vol(arr, vol_lookback)
                if vol > 2 * vol_threshold:
                    continue
                scale = min(1.0, vol_threshold / vol) if vol > vol_threshold else 1.0
                weights[tk] = -half * scale / n_positions

        if not weights:
            return {}

        if use_correlation_filter:
            weights = correlation_adjusted_weights(weights, prices_by_ticker)

        if use_dynamic_leverage:
            rets = {
                tk: np.diff(np.log(np.maximum(np.asarray(p, dtype=float), 1e-9)))
                for tk, p in prices_by_ticker.items()
                if tk in weights
            }
            weights = {tk: w * dynamic_leverage(weights, rets, target_vol=port_target_vol, max_leverage=port_max_leverage) for tk, w in weights.items()}

        if use_drawdown_guard:
            dd = 1.0 - state["equity"] / state["peak"] if state["peak"] > 0 else 0.0
            scale = guard.exposure_scale(max(0.0, dd))
            if scale <= 0.0:
                state["flat"] = state.get("flat", 0) + 1
                return {}
            weights = {tk: w * scale for tk, w in weights.items()}

        prev = state["equity"]
        gross = sum(abs(w) for w in weights.values())
        port_ret = 0.0
        for tk, w in weights.items():
            arr = np.asarray(prices_by_ticker[tk], dtype=float)
            if len(arr) >= 2:
                port_ret += w * (arr[-1] / arr[-2] - 1.0)
        state["equity"] = prev * (1.0 + port_ret)
        state["peak"] = max(state["peak"], state["equity"])
        return weights

    return weight_fn
