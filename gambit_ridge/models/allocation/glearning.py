"""G-learning — Dixon, Halperin & Bilokon, chap. 10 (éq. 10.19-10.26).

Extension probabiliste du Q-learning : au lieu de maximiser l'espérance
de récompense, l'agent maximise l'espérance sous une PRIOR de contrôle
gaussienne, ce qui rend le problème semi-analytiquement tractable et
équivaut, pour une récompense quadratique, à un régulateur LQR
probabiliste (éq. 10.26).

Formulation utilisée ici (allocation de richesse à un seul facteur de
risque — le portefeuille du modèle de signaux) :

    état x_t   : [exposition courante a_t, volatilité réalisée, régime]
    contrôle u : levier cible (scalaire, appliqué uniformément aux poids)
    dynamique  : a_{t+1} = u (ré-équilibrage immédiat)
    récompense : r_t = a_t * R_{t+1} - λ_vol * vol_t * |a_t|
                 - η * (coûts de turnover)

La solution G-learning dans ce cas dégénéré (contrôle entièrement
observable, récompense linéaire-quadratique) est analytique :
    u* = (E[R] + η * coût) / (λ_risk * vol_t² + λ_turn)
    tronqué à [-levier_max, levier_max] — plus la volatilité est haute,
    plus le régime est défavorable, plus l'exposition cible baisse :
    c'est exactement un régulateur LQR probabiliste avec contrainte.

Anti-look-ahead : les E[R], vol et probabilités de régime sont estimés
EXCLUSIVEMENT sur la fenêtre de train fournie à fit(). act() ne fait
qu'appliquer ces paramètres estimés à l'état courant.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GLearningAllocator:
    """Régulateur LQR probabiliste pour le levier du portefeuille.

    Paramètres (tous estimés sur le train dans fit()) :
      - mu_by_regime : rendement moyen quotidien par régime HMM
      - vol_by_regime : volatilité quotidienne par régime HMM
      - lambda_risk  : aversion au risque (pénalité quadratique)
      - eta_cost     : pénalité de turnover (coûts de transaction)
      - levier_max   : contrainte dure d'exposition
    """

    lambda_risk: float = 10.0
    eta_cost: float = 0.0007          # ~7 bps par unité de turnover
    levier_max: float = 1.0
    mu_by_regime: np.ndarray = field(default_factory=lambda: np.zeros(3))
    vol_by_regime: np.ndarray = field(default_factory=lambda: np.ones(3))
    fitted: bool = False

    def fit(
        self,
        port_returns: np.ndarray,
        regime_probs: np.ndarray,
    ) -> "GLearningAllocator":
        """Estime mu/vol par régime sur la fenêtre de train uniquement.

        port_returns : (T,) rendements quotidiens du portefeuille de signaux
        regime_probs : (T, n_regimes) probabilités a posteriori filtrées HMM
        """
        r = np.asarray(port_returns, dtype=float)
        P = np.asarray(regime_probs, dtype=float)
        T = min(len(r), len(P))
        r, P = r[:T], P[:T]
        dominant = P.argmax(axis=1) if P.ndim == 2 else np.zeros(T, dtype=int)
        k = P.shape[1] if P.ndim == 2 else 1
        mu = np.zeros(k)
        vol = np.ones(k)
        for j in range(k):
            mask = dominant == j
            if mask.sum() >= 20:
                mu[j] = r[mask].mean()
                vol[j] = max(r[mask].std(ddof=1), 1e-4)
            else:
                # régime peu fréquent dans le train : prior prudent
                mu[j] = 0.0
                vol[j] = max(r.std(ddof=1) if len(r) > 1 else 0.01, 1e-4)
        self.mu_by_regime = mu
        self.vol_by_regime = vol
        self.fitted = True
        return self

    def act(self, regime_probs_t: np.ndarray, current_leverage: float) -> float:
        """Retourne le levier cible pour la date t (politique analytique).

        regime_probs_t : probabilités HMM a posteriori à la date t
        current_leverage : exposition courante (pour la pénalité de turnover)
        """
        if not self.fitted:
            return 0.0
        p = np.asarray(regime_probs_t, dtype=float).ravel()
        p = p / p.sum() if p.sum() > 0 else np.full(len(self.mu_by_regime), 1 / len(self.mu_by_regime))
        # Espérance de rendement et de vol sous le mélange de régimes
        mu_mix = float(np.dot(p, self.mu_by_regime))
        vol_mix = float(np.sqrt(np.dot(p, self.vol_by_regime ** 2)))
        if vol_mix < 1e-6:
            return 0.0
        # Contrôle LQR probabiliste (éq. 10.26 dégénérée, contrainte de levier)
        u_star = mu_mix / (self.lambda_risk * vol_mix ** 2 + self.eta_cost)
        # Pénalité de turnover : coût de dériver de l'exposition courante
        u_star -= self.eta_cost * current_leverage / (
            self.lambda_risk * vol_mix ** 2 + self.eta_cost
        )
        return float(np.clip(u_star, -self.levier_max, self.levier_max))
