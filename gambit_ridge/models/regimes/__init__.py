"""Détection de régimes de marché — Dixon, Halperin & Bilokon, chap. 7."""
from .hmm import GaussianHMM
from .kalman import KalmanBeta
from .strategy import regime_conditioned_momentum

__all__ = ["GaussianHMM", "KalmanBeta", "regime_conditioned_momentum"]
