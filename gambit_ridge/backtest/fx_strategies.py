"""Stratégies forex quantitatives : carry et stat-arb multi-paires.

Carry : long la paire dont la devise longue a le taux le plus élevé,
court celle dont la devise longue a le taux le plus faible. Poids
proportionnels au différentiel de taux, normalisés, avec filtre de vol.

Stat-arb : chaque paire vs USD est modélisée en z-score sur son log-prix
résiduel après écart à la moyenne mobile longue. Entrée à ±entry_z,
sortie à ±exit_z. Les poids sont bornés par max_weight.
"""

from __future__ import annotations

import numpy as np


def carry_weight_fn(
    pairs_legs: dict[str, tuple[str, str]],
    rates: dict[str, np.ndarray],
    vol_lookback: int = 60,
    vol_threshold: float = 15.0,
    max_weight: float = 0.5,
):
    """Construit la fonction de poids carry.

    rates : devise -> taux 3M (en %) aligné sur les prix.
    Le carry théorique d'une paire = taux(devise longue) - taux(devise courte).
    """
    pair_names = sorted(pairs_legs)

    def weight_fn(t: int, prices_until_t: dict[str, np.ndarray]) -> dict[str, float]:
        if t < vol_lookback:
            return {}
        ref = prices_until_t[pair_names[0]]
        if len(ref) < vol_lookback + 1:
            return {}
        log_ret = np.diff(np.log(ref[-(vol_lookback + 1):]))
        vol_annual = float(np.std(log_ret, ddof=1)) * np.sqrt(252) * 100
        if vol_annual > vol_threshold:
            return {}

        carries = {}
        for p in pair_names:
            long_ccy, short_ccy = pairs_legs[p]
            carries[p] = float(rates[long_ccy][t] - rates[short_ccy][t])

        ranked = sorted(carries.items(), key=lambda kv: kv[1])
        weights = {}
        # Short : carry le plus négatif ; Long : carry le plus positif
        for p, c in ranked[:2]:
            if c < 0:
                weights[p] = -max_weight * min(abs(c) / 5.0, 1.0)
        for p, c in reversed(ranked[-2:]):
            if c > 0:
                weights[p] = max_weight * min(c / 5.0, 1.0)

        gross = sum(abs(w) for w in weights.values())
        if gross > 1.0 and gross > 0:
            weights = {p: w / gross for p, w in weights.items()}
        return weights

    return weight_fn


def carry_trend_weight_fn(
    pairs_legs: dict[str, tuple[str, str]],
    rates: dict[str, np.ndarray],
    trend_lookback: int = 126,
    smooth: int = 63,
    max_weight: float = 0.5,
):
    """Carry filtré par tendance : on ne prend la paire que si son momentum
    à ``trend_lookback`` confirme le signe du différentiel de taux lissé.
    """
    pair_names = sorted(pairs_legs)

    def weight_fn(t: int, prices_until_t: dict[str, np.ndarray]) -> dict[str, float]:
        if t < max(trend_lookback, smooth) + 1:
            return {}
        weights = {}
        for p in pair_names:
            s = prices_until_t[p]
            if len(s) < trend_lookback + 1:
                continue
            long_ccy, short_ccy = pairs_legs[p]
            lo = max(0, t - smooth + 1)
            diff = float(
                np.mean(rates[long_ccy][lo : t + 1] - rates[short_ccy][lo : t + 1])
            )
            trend = 1.0 if s[-1] > s[-trend_lookback] else -1.0
            if diff > 0 and trend > 0:
                weights[p] = max_weight * min(diff / 4.0, 1.0)
            elif diff < 0 and trend < 0:
                weights[p] = -max_weight * min(-diff / 4.0, 1.0)
        return weights

    return weight_fn


def stat_arb_fx_weight_fn(
    lookback: int = 120,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    max_weight: float = 0.4,
    vol_lookback: int = 60,
    vol_threshold: float = 15.0,
):
    """Stat-arb mean-reversion multi-paires sur z-score du log-prix."""

    def weight_fn(t: int, prices_until_t: dict[str, np.ndarray]) -> dict[str, float]:
        if t < lookback:
            return {}
        weights = {}
        for pair, series in prices_until_t.items():
            if len(series) < lookback:
                continue
            logp = np.log(series[-lookback:])
            mean = np.mean(logp)
            std = np.std(logp, ddof=1)
            if std <= 1e-9:
                continue
            z = (logp[-1] - mean) / std
            if z > entry_z:
                weights[pair] = -max_weight
            elif z < -entry_z:
                weights[pair] = max_weight
            elif abs(z) < exit_z:
                weights[pair] = 0.0

        # Filtre de vol global sur la moyenne des paires
        if vol_lookback > 0 and weights:
            first = sorted(prices_until_t)[0]
            ref = prices_until_t[first]
            if len(ref) >= vol_lookback + 1:
                log_ret = np.diff(np.log(ref[-(vol_lookback + 1):]))
                vol_annual = float(np.std(log_ret, ddof=1)) * np.sqrt(252) * 100
                if vol_annual > vol_threshold:
                    return {}
        return weights

    return weight_fn
