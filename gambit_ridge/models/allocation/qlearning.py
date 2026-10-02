"""Q-learning tabulaire — Dixon, Halperin & Bilokon, chap. 9 (éq. 9.75-9.77).

Update : Q(s,a) ← Q(s,a) + α [ r + γ max_{a'} Q(s',a') − Q(s,a) ]
Exploration ε-greedy avec décroissance. En espace continu on discrétise :
    état  : (régime dominant, tranche de vol, tranche d'exposition)
    action: grille de leviers cibles ∈ {-1, -0.5, 0, 0.5, 1}

Baseline RL que le G-learning devra battre. L'entraînement se fait sur
la fenêtre de train UNIQUEMENT (trajectoires passées) ; act() applique
la politique gloutonne apprise à l'état courant. Aucune donnée future
n'entre dans fit().
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

REGIME_BINS = 3
VOL_BINS = 3
LEVIER_ACTIONS = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])


def _state_index(regime_probs_t: np.ndarray, vol_t: float, leverage: float, vol_quantiles: np.ndarray) -> int:
    p = np.asarray(regime_probs_t, dtype=float).ravel()
    regime = int(p.argmax()) if p.sum() > 0 else 0
    v = int(np.searchsorted(vol_quantiles, vol_t, side="right")) if vol_quantiles is not None and len(vol_quantiles) else 0
    v = min(v, VOL_BINS - 1)
    lev = int(min(abs(leverage) / max(1e-9, 1.0) * 2, 1.999))  # 2 tranches : ~0, ~1
    return (regime * VOL_BINS + v) * 2 + lev


@dataclass
class QLearningAllocator:
    """Q-learning tabulaire ε-greedy pour le levier du portefeuille."""

    alpha: float = 0.05
    gamma: float = 0.95
    epsilon: float = 0.10
    lambda_risk: float = 0.0          # pénalité quadratique optionnelle
    eta_cost: float = 0.0007
    levier_max: float = 1.0
    Q: np.ndarray = field(default_factory=lambda: np.zeros((REGIME_BINS * VOL_BINS * 2, len(LEVIER_ACTIONS))))
    vol_quantiles: np.ndarray = field(default_factory=lambda: np.array([0.005, 0.02]))
    fitted: bool = False

    def fit(
        self,
        port_returns: np.ndarray,
        regime_probs: np.ndarray,
        vols: np.ndarray | None = None,
        seed: int = 42,
    ) -> "QLearningAllocator":
        """Apprend Q sur la trajectoire de train (rendements passés).

        port_returns : (T,) rendements quotidiens du portefeuille de signaux
        regime_probs : (T, n_regimes)
        vols         : (T,) volatilité réalisée quotidienne (défaut : |r| lissé)
        """
        r = np.asarray(port_returns, dtype=float)
        P = np.asarray(regime_probs, dtype=float)
        T = min(len(r), len(P))
        r, P = r[:T], P[:T]
        if vols is not None:
            v = np.asarray(vols, dtype=float)[:T]
        else:
            v = np.convolve(np.abs(r), np.ones(10) / 10, mode="same")
        self.vol_quantiles = np.quantile(v, [0.33, 0.66])
        rng = np.random.default_rng(seed)
        lev = 0.0
        for t in range(T - 1):
            s = _state_index(P[t], v[t], lev, self.vol_quantiles)
            # action ε-greedy
            if rng.random() < self.epsilon:
                a = int(rng.integers(len(LEVIER_ACTIONS)))
            else:
                a = int(np.argmax(self.Q[s]))
            u = LEVIER_ACTIONS[a]
            ret = u * r[t + 1]
            cost = abs(u - lev) * self.eta_cost
            rew = ret - cost - self.lambda_risk * (u * v[t]) ** 2
            s2 = _state_index(P[t + 1], v[t + 1], u, self.vol_quantiles)
            target = rew + self.gamma * np.max(self.Q[s2])
            self.Q[s, a] += self.alpha * (target - self.Q[s, a])
            lev = u
        self.fitted = True
        return self

    def act(self, regime_probs_t: np.ndarray, vol_t: float, current_leverage: float) -> float:
        """Politique gloutonne sur l'état courant (après fit)."""
        if not self.fitted:
            return 0.0
        s = _state_index(regime_probs_t, vol_t, current_leverage, self.vol_quantiles)
        a = int(np.argmax(self.Q[s]))
        return float(np.clip(LEVIER_ACTIONS[a], -self.levier_max, self.levier_max))
