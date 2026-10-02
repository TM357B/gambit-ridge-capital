"""Limites de risque globales : le contrôle indépendant des agents."""

from __future__ import annotations

from dataclasses import dataclass

from .signal import Signal


@dataclass
class RiskVerdict:
    approved: bool
    reasons: list[str]


@dataclass
class RiskLimits:
    """Garde-fous appliqués à toute allocation proposée par le conseil."""

    max_position: float = 0.10        # 10% max par position
    max_team: float = 0.35           # 35% max par équipe
    max_total_gross: float = 2.0     # exposition brute max
    max_total_net: float = 1.0       # exposition nette max
    ia_theme_floor: float = 0.25     # surpondération voulue du thème IA
    ia_theme_cap: float = 0.50       # plafond malgré l'appétit

    def check(self, proposed: dict[str, float]) -> RiskVerdict:
        """proposed : ticker -> poids signé (négatif = short)."""
        reasons: list[str] = []

        if proposed:
            total_gross = sum(abs(w) for w in proposed.values())
            total_net = sum(proposed.values())
            if total_gross > self.max_total_gross:
                reasons.append(f"brute {total_gross:.2f} > {self.max_total_gross}")
            if abs(total_net) > self.max_total_net:
                reasons.append(f"nette {total_net:+.2f} hors bornes")
            for ticker, weight in proposed.items():
                if abs(weight) > self.max_position:
                    reasons.append(
                        f"{ticker}: {weight:.2f} > {self.max_position:.0%} position"
                    )

        return RiskVerdict(approved=not reasons, reasons=reasons)

    def ia_theme_weight(self, proposed: dict[str, float], ia_tickers: set[str]) -> float:
        ia_gross = sum(abs(w) for t, w in proposed.items() if t in ia_tickers)
        total_gross = sum(abs(w) for w in proposed.values())
        if total_gross <= 0:
            return 0.0
        return ia_gross / total_gross


# ---------------------------------------------------------------------------
# Extensions v15 : gestion du risque professionnelle
# ---------------------------------------------------------------------------

@dataclass
class DrawdownGuard:
    """Limite de drawdown global : déleverage progressif quand l'équity chute.

    Le fonds réduit son exposition de façon linéaire entre `soft_dd`
    (début du déleverage) et `hard_dd` (exposition nulle). Un drawdown
    qui remonte au-dessus du seuil mou rétablit progressivement le levier.
    """

    soft_dd: float = 0.05   # -5% : on commence à couper
    hard_dd: float = 0.12   # -12% : exposition nulle

    def exposure_scale(self, current_dd: float) -> float:
        """current_dd : drawdown courant en valeur positive (0.04 = -4%)."""
        if current_dd <= self.soft_dd:
            return 1.0
        if current_dd >= self.hard_dd:
            return 0.0
        span = self.hard_dd - self.soft_dd
        return max(0.0, 1.0 - (current_dd - self.soft_dd) / span)


def portfolio_realized_vol(
    weights: dict[str, float],
    returns_by_ticker: dict[str, "list[float] | tuple"],
    lookback: int = 60,
) -> float:
    """Vol annualisée du portefeuille (variance pondérée + covariances)."""
    import numpy as np

    names = [t for t in weights if weights[t] != 0.0 and t in returns_by_ticker]
    if not names:
        return 0.0
    w = np.array([abs(weights[t]) for t in names])
    R = np.array([np.asarray(returns_by_ticker[t])[-lookback:] for t in names])
    if R.shape[1] < 5:
        return 0.0
    cov = np.atleast_2d(np.cov(R)) * 252.0
    var = float(w @ cov @ w)
    return float(np.sqrt(max(0.0, var)))


def dynamic_leverage(
    weights: dict[str, float],
    returns_by_ticker: dict[str, "list[float] | tuple"],
    *,
    target_vol: float = 0.12,
    max_leverage: float = 1.5,
    lookback: int = 60,
) -> float:
    """Facteur de vol-targeting du portefeuille : target_vol / vol réalisée.

    Renvoie un scalaire multiplicatif à appliquer à tous les poids,
    borné par max_leverage. Vol réalisée > 2× cible => facteur < 0.5.
    """
    pv = portfolio_realized_vol(weights, returns_by_ticker, lookback)
    if pv <= 1e-6:
        return 1.0
    return max(0.0, min(max_leverage, target_vol / pv))


def correlation_adjusted_weights(
    weights: dict[str, float],
    prices_by_ticker: dict[str, "list[float] | tuple"],
    *,
    max_pair_corr: float = 0.85,
    lookback: int = 60,
) -> dict[str, float]:
    """Pénalise les positions trop corrélées entre elles.

    Pour chaque paire de positions longues (ou courtes) dont la corrélation
    dépasse max_pair_corr, chaque position est réduite d'un facteur
    (1 - (corr - seuil)) — deux actifs quasi identiques ne comptent plus
    double dans le budget de risque.
    """
    import numpy as np

    active = [t for t, w in weights.items() if abs(w) > 1e-9]
    if len(active) < 2:
        return dict(weights)
    rets = {}
    for t in active:
        arr = np.asarray(prices_by_ticker.get(t, []), dtype=float)
        if len(arr) < lookback + 2:
            return dict(weights)
        rets[t] = np.diff(np.log(np.maximum(arr[-lookback - 1 :], 1e-9)))
    penalty = {t: 1.0 for t in active}
    for i, a in enumerate(active):
        for b in active[i + 1 :]:
            if np.sign(weights[a]) != np.sign(weights[b]):
                continue
            if len(rets[a]) != len(rets[b]):
                continue
            if rets[a].std() < 1e-12 or rets[b].std() < 1e-12:
                continue
            corr = float(np.corrcoef(rets[a], rets[b])[0, 1])
            if corr > max_pair_corr:
                cut = 1.0 - (corr - max_pair_corr)
                penalty[a] *= cut
                penalty[b] *= cut
    return {t: w * penalty.get(t, 1.0) for t, w in weights.items()}
