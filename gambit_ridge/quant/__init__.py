"""Modèles mathématiques de Dixon, Halperin & Bilokon, « Machine Learning in Finance » (Springer, 2020).

Complète les modèles déjà présents (HMM, Kalman, AR/GARCH, ridge, réseaux, Q/G-learning) :
- qlbs        : QLBS (ch. 10) — pricing et couverture d'options par programmation dynamique
                et par apprentissage par renforcement (Fitted Q Iteration)
- gp          : processus gaussiens (ch. 3) — pricing et grecques appris, lissage de la surface de vol
- particle    : filtre particulaire SIR (ch. 7) — volatilité stochastique avec levier et sauts
- bayes       : régression linéaire bayésienne, mélanges gaussiens (EM), sélection et moyenne de modèles (ch. 2-3)
- timeseries  : Box-Jenkins (ACF, PACF, AR par AIC/BIC, Ljung-Box, ADF) et ACP (ch. 6)
- optim       : Nelder-Mead (calibrages), numpy seul

Outils d'analyse : ils ne pilotent pas le portefeuille ; tout candidat-stratégie passe par une
campagne de recherche pré-enregistrée (research/campaign6.py).
"""
