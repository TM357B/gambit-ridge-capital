"""Modèles baseline économétriques (Dixon, Halperin & Bilokon, chap. 6).

AR(p) et GARCH(p,q) implémentés en numpy pur : ce sont les benchmarks
qu tout modèle ML devra battre hors échantillon (règle n°5).
"""
from .ar_garch import ARModel, GARCHModel, evaluate_baselines

__all__ = ["ARModel", "GARCHModel", "evaluate_baselines"]
