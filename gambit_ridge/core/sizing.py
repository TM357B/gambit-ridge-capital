"""Maths de position sizing : Kelly fractionné et ciblage de volatilité.

Le sizing est purement quantitatif : Kelly (avec recadrage pour tenir
compte de l'incertitude d'estimation) et vol-targeting.
"""

from __future__ import annotations


def kelly_fraction(
    win_rate: float,
    win_loss_ratio: float,
    *,
    fraction: float = 0.25,
) -> float:
    """Kelly recadré (quarter-Kelly par défaut).

    f* = W - (1 - W) / R, recadré par `fraction` car les paramètres
    sont estimés avec bruit. Full Kelly sur paramètres bruités = ruine.
    """
    if win_loss_ratio <= 0:
        return 0.0
    edge = win_rate - (1.0 - win_rate) / win_loss_ratio
    return max(0.0, edge * fraction)


def vol_target_size(
    signal_score: float,
    realized_vol: float,
    target_vol: float = 0.15,
    max_leverage: float = 3.0,
) -> float:
    """Taille = score × (vol cible / vol réalisée), bornée par max_leverage.

    signal_score : [-1, 1] (score composite du signal)
    realized_vol  : vol annualisée de l'actif (ex. 0.40 pour 40%)
    """
    if realized_vol <= 0:
        return 0.0
    raw = signal_score * (target_vol / realized_vol)
    return max(-max_leverage, min(max_leverage, raw))


# ---------------------------------------------------------------------------
# Extensions v15 : Kelly glissant par position
# ---------------------------------------------------------------------------

def rolling_kelly_size(
    signal_score: float,
    trade_returns: "list[float] | tuple",
    *,
    fraction: float = 0.25,
    min_trades: int = 20,
    fallback_vol_target: float = 0.10,
    max_leverage: float = 3.0,
) -> float:
    """Quarter-Kelly estimé sur l'historique glissant des trades de la position.

    trade_returns : rendements (signés) des derniers trades de ce signal.
    Si l'échantillon est trop court (< min_trades), on retombe sur un
    sizing par vol cible, multiplié par la force du signal. L'estimateur
    Kelly est borné : edge négatif => taille nulle (jamais de short Kelly).
    """
    import math

    n = len(trade_returns)
    if n < min_trades:
        est = fallback_vol_target / max(1.0, 1.0 + abs(signal_score))
        return math.copysign(min(max_leverage, est * abs(signal_score) * 3.0), signal_score) if signal_score else 0.0
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    if not wins:
        return 0.0
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    if avg_loss <= 1e-12:
        payoff = 10.0
    else:
        payoff = avg_win / avg_loss
    edge = win_rate - (1.0 - win_rate) / payoff
    if edge <= 0:
        return 0.0
    size = min(max_leverage, edge * fraction * abs(signal_score) * 4.0)
    return math.copysign(size, signal_score) if signal_score else 0.0
