"""Phase 3 — allocation dynamique par renforcement (chap. 9-10).

Deux contrôleurs, entraînés sur le passé uniquement :
- GLearningAllocator : G-learning (chap. 10) — probabiliste, semi-analytique,
  équivalent d'un régulateur LQR probabiliste. Stable et interprétable :
  priorité d'implémentation selon le plan validé.
- QLearningAllocator : Q-learning tabulaire (chap. 9, éq. 9.75-9.77) avec
  exploration ε-greedy — baseline RL à battre.

Les deux partagent la même interface fit/act et le même espace d'états :
    état = (régime HMM dominant, tranche de volatilité réalisée, niveau d'exposition)
    action = exposition cible (levier discret appliqué aux poids du modèle de signaux)
"""

from .glearning import GLearningAllocator
from .qlearning import QLearningAllocator

__all__ = ["GLearningAllocator", "QLearningAllocator"]
