"""Bibliothèque mathématique quantitative du fonds.

Catalogue des modèles stochastiques et réseaux de neurones utilisés (ou
documentés) par Gambit Ridge Capital, avec les équations réelles — pas de marketing.
Source : Dixon, Halperin & Bilokon, "Machine Learning in Finance"
(Springer 2020), chapitres 7-10 ; et Chap. 8 de JPMorgan "Deep Learning
in Finance" pour le calibration de filtres stochastiques.

C'est la section « Maths » de l'onglet Stratégies : chaque entrée dit
ce que c'est, l'équation, l'algorithme d'entraînement, ce qu'on en fait
dans le fonds (implémenté, validé, ou documenté sans edge), et le statut
honnête de son évaluation OOS."""

MATH_TOPICS = [
    # ============ CHAPITRE 7 : MARKOV, HMM, FILTRAGE ============
    {
        "id": "markov-chains",
        "name": "Chaînes de Markov",
        "chapter": "Chap. 7 — processus markoviens",
        "principle": "Un processus où le futur ne dépend que de l'état présent, pas du passé : P(X_t | X_{t-1}, ..., X_1) = P(X_t | X_{t-1}).",
        "equations": "Matrice de transition P = [p_ij], p_ij = P(X_t = j | X_{t-1} = i) · somme des lignes = 1 · distribution stationnaire π vérifiant π = πP",
        "training": "Estimation par comptage des transitions observées (MLE) sur la série discrétisée (rendements up/flat/down)",
        "use_in_fund": "Base théorique du HMM de régime : on modélise la transition bull → bear → choppy comme une chaîne de Markov à états cachés",
        "status": "IMPLÉMENTÉ (fondation du HMM de régime)",
    },
    {
        "id": "hmm",
        "name": "Hidden Markov Models (HMM)",
        "chapter": "Chap. 7 — états cachés",
        "principle": "Le marché a des régimes cachés (bull / bear / choppy) qu'on n'observe pas directement : on observe les rendements, qui en sont une preuve bruitée.",
        "equations": "λ = (A, B, π) : A = matrice de transition d'états, B = densités d'émission (rendements ~ N(μ_k, σ_k) selon l'état k) · P(λ | observations) maximisée par Baum-Welch (EM)",
        "training": "Baum-Welch : itération E (forward-backward pour les probabilités a posteriori des états) puis M (ré-estimation de A, B, π) jusqu'à convergence",
        "use_in_fund": "HMM 3 états sur les rendements agrégés : probabilité a posteriori de chaque régime, recalculée chaque jour de trading",
        "status": "IMPLÉMENTÉ — actif dans la stratégie régime-momentum",
    },
    {
        "id": "viterbi",
        "name": "Algorithme de Viterbi",
        "chapter": "Chap. 7 — décodage MAP",
        "principle": "Retrouver la séquence d'états cachés la plus probable a posteriori (le « chemin » de régimes qui explique le mieux l'historique observé).",
        "equations": "δ_t(j) = max over paths P(observations 1..t, état_t = j | λ) · récursion δ_t(j) = max_i [δ_{t-1}(i) a_ij] b_j(y_t) · backpointers pour reconstruire le chemin",
        "training": "Pas d'entraînement : décodage a posteriori sur un modèle déjà estimé (complexité O(T·K²), K = nombre d'états)",
        "use_in_fund": "Décodage du chemin de régimes le plus probable sur la fenêtre d'estimation — utile pour vérifier que le HMM identifie bien les régimes historiques",
        "status": "IMPLÉMENTÉ — diagnostic du HMM",
    },
    {
        "id": "hmm-filtering",
        "name": "Filtrage et lissage avec HMM (forward-backward)",
        "chapter": "Chap. 7 — inférence en ligne",
        "principle": "Filtrage = probabilité de l'état caché au temps t sachant les observations jusqu'à t (temps réel). Lissage = probabilité au temps t sachant TOUTES les observations (rétrospectif).",
        "equations": "Forward : α_t(j) = b_j(y_t) · Σ_i α_{t-1}(i) a_ij (filtrage : P(état_t | y_1..t)) · Backward : β_t(i) = Σ_j a_ij b_j(y_{t+1}) β_{t+1}(j) · Lissage : γ_t(j) ∝ α_t(j)β_t(j)",
        "training": "Forward en ligne pour le trading (le filtrage ne regarde jamais le futur) ; le backward est utilisé uniquement pour l'analyse hors-ligne",
        "use_in_fund": "Le filtre forward (α) donne la probabilité de régime du jour — c'est ce qui conditionne la stratégie momentum. Le lissage sert aux études de recherche",
        "status": "IMPLÉMENTÉ — le filtrage est ce qui tourne en production",
    },
    {
        "id": "ssm",
        "name": "State Space Models (modèles à espace d'états)",
        "chapter": "Chap. 7 — dynamique latente",
        "principle": "Un vecteur d'état latent x_t évolue (équation d'état) et est observé indirectement avec du bruit (équation d'observation). Généralise le HMM aux états continus.",
        "equations": "x_t = A x_{t-1} + u + w_t, w_t ~ N(0, Q) (état) · y_t = H x_t + v_t, v_t ~ N(0, R) (observation)",
        "training": "Estimation de (A, H, Q, R) par maximum de vraisemblance via le filtre de Kalman (la vraisemblance se calcule comme produit des densités prédictives d'innovation)",
        "use_in_fund": "Modélisation de la dynamique latente du momentum : tendance = état caché, prix = observation bruitée",
        "status": "IMPLÉMENTÉ (Kalman du fonds = un SSM)",
    },
    {
        "id": "kalman",
        "name": "Filtre de Kalman",
        "chapter": "Chap. 7 — filtrage optimal gaussien",
        "principle": "Filtre optimal récursif pour un SSM linéaire gaussien : il combine prédiction et observation pour estimer l'état latent avec la variance minimale.",
        "equations": "Prédiction : x̂_{t|t-1} = A x̂_{t-1} + u · P_{t|t-1} = A P_{t-1} A' + Q · Gain : K_t = P_{t|t-1} H' (H P H' + R)^{-1} · Update : x̂_t = x̂_{t|t-1} + K_t (y_t - H x̂_{t|t-1})",
        "training": "Pas d'entraînement à proprement parler : le filtre tourne récursivement ; les matrices (A, H, Q, R) sont estimées par MLE sur données d'entraînement uniquement",
        "use_in_fund": "Estimation de la tendance latente (slope) des séries : la version régime-momentum l'utilise pour lisser le signal avant décision",
        "status": "IMPLÉMENTÉ (phase 1)",
    },
    {
        "id": "particle-filter",
        "name": "Filtre particulaire",
        "chapter": "Chap. 7 — filtrage non gaussien",
        "principle": "Approximation de la distribution de filtrage par un nuage de particules (échantillons pondérés) : gère les modèles non-linéaires, non-gaussiens où Kalman échoue.",
        "equations": "Chaque particule : (x^i_t, w^i_t) · Propagation : x^i_t ~ p(x_t | x^i_{t-1}) · Poids : w^i_t ∝ w^i_{t-1} · p(y_t | x^i_t) (likelihood) · Normalisation : W^i = w^i / Σ_j w^j · Estimation : E[x_t | y_1..t] ≈ Σ_i W^i x^i_t",
        "training": "Récursif en ligne, comme Kalman ; le dégénérescence des poids (une seule particule domine) impose le resampling",
        "use_in_fund": "Recherche : alternative au HMM quand les rendements ont des queues épaisses (student-t au lieu de gaussien)",
        "status": "DOCUMENTÉ — pas encore implémenté (le HMM gaussien suffit pour l'instant)",
    },
    {
        "id": "sir",
        "name": "Sequential Importance Resampling (SIR)",
        "chapter": "Chap. 7 — algorithme particulaire",
        "principle": "L'algorithme particulaire de référence : à chaque étape, propager les particules, pondérer par la vraisemblance, puis resampler pour éviter le dégénérescence.",
        "equations": "Effective Sample Size : ESS = 1 / Σ_i (W^i)² · Si ESS < seuil (typiquement N/2) → resample : tirer N particules parmi les existantes avec probabilité W^i (remise)",
        "training": "Le resampling remet toutes les poids à 1/N : il élimine les particules à poids négligeable et duplique les informatives",
        "use_in_fund": "Composant obligatoire du filtre particulaire — documenté avec lui",
        "status": "DOCUMENTÉ — suit le filtre particulaire",
    },
    {
        "id": "multinomial-resampling",
        "name": "Resampling multinomial",
        "chapter": "Chap. 7 — variance du SIR",
        "principle": "La méthode de resampling la plus simple : tirer chaque nouvelle particule indépendamment selon la distribution des poids normalisés.",
        "equations": "Indices resamplés : i_k ~ Categorical(W^1, ..., W^N) iid, k = 1..N · Variance plus élevée que resampling systématique ou stratifié",
        "training": "Alternatives documentées : systématique (1 tirage + pas régulier, variance minimale) et stratifié (1 tirage par strate) — toutes deux préférables en pratique",
        "use_in_fund": "Recherche : on utiliserait le resampling systématique pour sa variance plus faible",
        "status": "DOCUMENTÉ — choix technique documenté, pas de gain mesuré à ce stade",
    },
    {
        "id": "stochastic-vol",
        "name": "Modèles de volatilité stochastique",
        "chapter": "Chap. 7 — volatilité latente",
        "principle": "La volatilité n'est pas observée et évolue elle-même aléatoirement : un SSM logarithmique la traite comme un état latent.",
        "equations": "y_t = exp(h_t/2) ε_t, ε_t ~ N(0,1) (rendement) · h_t = φ h_{t-1} + η_t, η_t ~ N(0, σ_η²) (log-vol latente, AR(1))",
        "training": "Vraisemblance non-tractable → estimation par filtre particulaire (approche Kim-Shephard-Chib : mixture d'approximations gaussiennes) ou MCMC (méthode ancillaire)",
        "use_in_fund": "Alternative à GARCH (phase 0) : la vol latente en AR(1) correspond mieux aux changements de régime qu'une équation de variance observable",
        "status": "DOCUMENTÉ — GARCH validé en phase 0 suffit ; le gain marginal n'est pas démontré",
    },
    {
        "id": "point-calibration",
        "name": "Calibration ponctuelle de filtres stochastiques",
        "chapter": "Chap. 8 — point estimates",
        "principle": "Estimer les paramètres du modèle latent (θ du SSM/HMM) par maximum de vraisemblance : un seul vecteur de paramètres, sans incertitude dessus.",
        "equations": "θ̂ = argmax_θ L(θ) = argmax_θ p(y_1, ..., y_T | θ) · pour un SSM, L se calcule par le filtre de Kalman : L = Π_t N(y_t ; ŷ_{t|t-1}, S_t) où S_t = variance d'innovation",
        "training": "Optimisation numérique (L-BFGS ou EM) ; le risque : ignorer l'incertitude sur θ̂ → surconfiance dans les probabilités de régime",
        "use_in_fund": "C'est ce que fait le HMM actuel (Baum-Welch = MLE) : les probabilités de régime sont conditionnelles à θ̂, pas marginales",
        "status": "IMPLÉMENTÉ — c'est la calibration du HMM",
    },
    {
        "id": "bayesian-calibration",
        "name": "Calibration bayésienne de filtres stochastiques",
        "chapter": "Chap. 8 — full posteriors",
        "principle": "Traiter les paramètres θ comme aléatoires avec une distribution a posteriori complète : les probabilités de régime intègrent l'incertitude de calibration, pas juste un point estimate.",
        "equations": "p(θ | y) ∝ p(y | θ) p(θ) (Bayes) · probabilité de régime marginale : P(régime | y) = ∫ P(régime | y, θ) p(θ | y) dθ — l'intégrale se fait par échantillonnage",
        "training": "Particle MCMC (PMCMC), SMC² ou méthode ancillaire ; coûteux mais capture le risque d'erreurs de calibration",
        "use_in_fund": "Amélioration théorique du HMM : au lieu de « p(bull) = 0.7, c'est sûr », on saurait « p(bull) = 0.7 ± 0.15 selon la calibration »",
        "status": "DOCUMENTÉ — pas encore nécessaire, le HMM est assez contraint pour être stable",
    },

    # ============ CHAPITRE 9 : RNN ============
    {
        "id": "rnn",
        "name": "Recurrent Neural Networks (RNN)",
        "chapter": "Chap. 9 — réseaux récurrents",
        "principle": "Réseau qui traite une séquence en gardant un état caché mémoire : la sortie au temps t dépend de l'entrée au temps t ET de l'état caché accumulé.",
        "equations": "h_t = tanh(W_x x_t + W_h h_{t-1} + b) · ŷ_t = W_y h_t + b_y · entraînement par BPTT (Backpropagation Through Time)",
        "training": "Descente de gradient avec BPTT sur fenêtres séquentielles ; les séquences longues souffrent de vanishing/exploding gradients",
        "use_in_fund": "Famille complète des modèles séquentiels de la phase 2 (RNN simple, GRU, LSTM) — implémentés en numpy pur, testés walk-forward",
        "status": "IMPLÉMENTÉ — évalué OOS, verdict par variante ci-dessous",
    },
    {
        "id": "rnn-memory",
        "name": "Mémoire RNN : autocovariance partielle, stabilité, stationnarité, half-life",
        "chapter": "Chap. 9 — théorie de la mémoire",
        "principle": "La « mémoire » d'un RNN est quantifiable : jusqu'à quel lag le modèle retient l'information ? Formalisé par l'autocovariance partielle de l'état caché.",
        "equations": "Autocovariance : γ_h(k) = Cov(h_t, h_{t-k}) · Stabilité : rayon spectral de W_h < 1 (sinon exploding gradient) · Half-life : τ tel que γ_h(τ) = γ_h(0)/2 — τ détermine le lookback effectif du modèle",
        "training": "Analyse du modèle entraîné (pas une méthode d'entraînement) : mesurer γ_h(k) sur données de validation pour vérifier que la mémoire correspond à l'horizon visé",
        "use_in_fund": "Diagnostic : avant d'évaluer un RNN sur des données financières, on vérifie que sa half-life mémoire est réaliste (jours-semaines, pas mois)",
        "status": "IMPLÉMENTÉ — diagnostic de la phase 2",
    },
    {
        "id": "alpha-rnn",
        "name": "alpha-RNN et dynamic alpha1-RNN",
        "chapter": "Chap. 9 — Guiver & Wilson",
        "principle": "Le RNN le plus simple : pas de cellule de mémoire dédiée, l'état caché EST la mémoire. alpha1-RNN = variante dynamique où l'alpha (le poids du signal) s'adapte au temps.",
        "equations": "h_t = tanh(W_x x_t + W_h h_{t-1} + b) — identique au RNN, mais avec un alpha de régularisation : h_t = α tanh(...) + (1-α) h_{t-1} (mélange état/résidu) · dynamic alpha : α_t = f(x_t) appris",
        "training": "BPTT standard ; la variante dynamique apprend α en fonction de l'entrée (régule la mémoire selon le régime)",
        "use_in_fund": "Baseline de la famille récurrente : plus léger que GRU/LSTM, sert de contrôle pour mesurer l'apport réel des cellules de mémoire",
        "status": "IMPLÉMENTÉ — évalué, pas mieux que la baseline de phase 2",
    },
    {
        "id": "nn-exponential-smoothing",
        "name": "Neural Network Exponential Smoothing (NNETS)",
        "chapter": "Chap. 9 — lissage exponentiel appris",
        "principle": "Remplacer le lissage exponentiel classique (EWMA à alpha fixe) par un réseau qui APPREND la fonction de lissage — équivalent à un alpha-rnn où le réseau apprend α dynamiquement.",
        "equations": "EWMA classique : s_t = α y_t + (1-α) s_{t-1} (α constant) · NNETS : s_t = α(y_t, s_{t-1}) y_t + (1-α(y_t, s_{t-1})) s_{t-1} avec α = σ(network) appris",
        "training": "BPTT sur séquences ; le modèle apprend quand faire confiance à la nouvelle observation vs la mémoire",
        "use_in_fund": "Alternative directe au filtre de Kalman pour l'estimation de tendance : le filtre optimal appris au lieu d'imposé par hypothèses gaussiennes",
        "status": "IMPLÉMENTÉ — validé en exploration, pas déployé",
    },
    {
        "id": "gru",
        "name": "Gated Recurrent Units (GRU)",
        "chapter": "Chap. 9 — cellules à portes",
        "principle": "Cellule récurrente avec deux portes (update, reset) qui contrôlent ce qui est retenu ou oublié de la mémoire : corrige le vanishing gradient sans la complexité complète du LSTM.",
        "equations": "z_t = σ(W_z x_t + U_z h_{t-1}) (update gate) · r_t = σ(W_r x_t + U_r h_{t-1}) (reset gate) · h̃_t = tanh(W x_t + U (r_t ⊙ h_{t-1})) · h_t = (1-z_t) ⊙ h_{t-1} + z_t ⊙ h̃_t",
        "training": "BPTT, les portes apprennent à garder l'information longue-distance",
        "use_in_fund": "Variante évaluée en phase 2 : moins de paramètres que LSTM, souvent équivalent sur données financières bruitées",
        "status": "IMPLÉMENTÉ — évalué OOS, verdict ci-dessous (LSTM)",
    },
    {
        "id": "lstm",
        "name": "Long Short-Term Memory (LSTM)",
        "chapter": "Chap. 9 — mémoire longue",
        "principle": "Cellule avec trois portes (forget, input, output) et un cell state séparé : la mémoire peut traverser des centaines de pas de temps sans être écrasée.",
        "equations": "f_t = σ(W_f x_t + U_f h_{t-1}) (forget) · i_t = σ(...) · c̃_t = tanh(...) · c_t = f_t ⊙ c_{t-1} + i_t ⊙ c̃_t (cell state) · o_t = σ(...) · h_t = o_t ⊙ tanh(c_t)",
        "training": "BPTT avec les portes qui régulent le gradient",
        "use_in_fund": "Évalué en phase 2 sur FRED : sous la baseline en OOS (les rendements financiers ont trop peu de signal séquentiel apprenable vs le bruit)",
        "status": "IMPLÉMENTÉ — ÉVALUÉ, NE BAT PAS LA BASELINE OOS (documenté)",
    },
    {
        "id": "lob-prediction",
        "name": "Predicting from the Limit Order Book (LOB)",
        "chapter": "Chap. 9 — microstructure",
        "principle": "Prédire le mid-price à court terme à partir de l'état du carnet d'ordres (10 meilleurs niveaux bid/ask, volumes, queues).",
        "equations": "Features par niveau : prix, volumes bid/ask, queue imbalance = (V_bid - V_ask)/(V_bid + V_ask) · labels : direction du mid-price à h pas d'avance (classification, pas régression)",
        "training": "Deep LSTM ou CNN sur snapshots du LOB ; les labels sont très bruités à courte échéance (d'où l'importance du horizon de prédiction)",
        "use_in_fund": "EXPLORATION : pertinent pour du HFT (échéance milliseconde) mais nos stratégies tournent à horizon jours-semaines — hors périmètre pour l'instant",
        "status": "DOCUMENTÉ — pas de données LOB accessibles dans le fonds",
    },

    # ============ CHAPITRE 10 : CNN, SMOOTHERS, AUTOENCODEURS ============
    {
        "id": "weighted-ma-smoothers",
        "name": "Weighted Moving Average Smoothers",
        "chapter": "Chap. 10 — lissage pré-CNN",
        "principle": "La brique de base de tout CNN : une fenêtre glissante pondérée (filtre) appliquée à la série — le CNN généralise ce concept en apprenant les poids.",
        "equations": "y_smooth(t) = Σ_k w_k · y_{t-k}, k = -K..K · cas particuliers : box filter (w_k uniformes), gaussien (w_k ∝ exp(-k²/2σ²)), filtres de Savitzky-Golay",
        "training": "Pas d'entraînement (poids fixes) — mais c'est le point de départ conceptuel du CNN : un filtre à poids APPRIS",
        "use_in_fund": "Étape de prétraitement des features (dérivées lissées du prix) ; le ridge utilise des smoothers gaussiens pour ses features",
        "status": "IMPLÉMENTÉ — prétraitement standard du fonds",
    },
    {
        "id": "cnn",
        "name": "Convolutional Neural Networks (CNN)",
        "chapter": "Chap. 10 — convolution temporelle",
        "principle": "Appliquer des filtres appris à des fenêtres de la série temporelle : détecte des motifs locaux (comme des figures chartistes apprises automatiquement).",
        "equations": "Convolution : s(t) = Σ_k w_k · x_{t-k} + b (1D, stride = pas de déplacement) · activation ReLU · la 2D convolution généralise : s(i,j) = Σ_m Σ_n w_{m,n} · x_{i-m, j-n}",
        "training": "Descente de gradient ; les poids du filtre sont partagés le long de la série (invariance par translation) — moins de paramètres qu'un dense",
        "use_in_fund": "Phase 2 : CNN 1D sur fenêtres de rendements, évalué walk-forward",
        "status": "IMPLÉMENTÉ — évalué, verdict pas mieux que la baseline (documenté)",
    },
    {
        "id": "pooling-dilated",
        "name": "Pooling et dilated convolution",
        "chapter": "Chap. 10 — architecture",
        "principle": "Pooling : sous-échantillonner pour réduire la taille et capter des motifs à plus grande échelle. Dilated convolution : trous dans le filtre pour voir plus loin sans plus de paramètres.",
        "equations": "Max pooling : s = max(x dans la fenêtre) · dilated : s(t) = Σ_k w_k · x_{t - k·d} avec d = dilatation (d=1 : conv classique ; d=2 : saute un point sur deux)",
        "training": "Composés : dilatations exponentielles (d=1, 2, 4, 8) donnent un champ réceptif énorme avec peu de couches (architecture WaveNet)",
        "use_in_fund": "Architecture de recherche si on explore le CNN plus loin (champ réceptif multi-échelles pour capter les dépendances longues)",
        "status": "DOCUMENTÉ — pas implémenté, le CNN simple n'a pas montré d'edge",
    },
    {
        "id": "autoencoder",
        "name": "Autoencodeurs",
        "chapter": "Chap. 10 — représentation latente",
        "principle": "Réseau qui apprend à compresser puis reconstruire son entrée : la couche centrale (code) est une représentation latente qui retire le bruit.",
        "equations": "Code : z = σ(W_enc x + b_enc) · Reconstruction : x̂ = W_dec z + b_dec · Loss : ||x - x̂||² (erreur de reconstruction) — on force ||x - x̂||² petit avec dim(z) << dim(x)",
        "training": "Descente de gradient sur l'erreur de reconstruction, sans label (apprentissage non-supervisé)",
        "use_in_fund": "Phase 2 : autoencodeur pour extraire une représentation débruitée des features avant le ridge — évalué walk-forward",
        "status": "IMPLÉMENTÉ — ÉVALUÉ, DÉSACTIVÉ (ne bat pas le ridge direct en OOS)",
    },
    {
        "id": "linear-autoencoder-pca",
        "name": "Autoencodeurs linéaires ≡ PCA",
        "chapter": "Chap. 10 — cas particulier",
        "principle": "Théorème : un autoencodeur linéaire (activations identités) apprend exactement la projection PCA de ses données d'entraînement.",
        "equations": "z = W_enc x (sans activation) · x̂ = W_dec z · la minimisation de ||x - x̂||² pousse W_dec W_enc vers la projection sur les k premières composantes principales (k = dim(z))",
        "training": "Conséquence pratique : pour des features linéaires, un autoencodeur n'apporte rien de plus qu'une PCA (calculée en closed form avec SVD)",
        "use_in_fund": "Vérification de cohérence : le code appris par l'autoencodeur linéaire doit reproduire les composantes PCA du bureau des features",
        "status": "IMPLÉMENTÉ — vérification théorique passée (le code ≈ PCA)",
    },
    {
        "id": "deep-autoencoder",
        "name": "Deep Autoencoders",
        "chapter": "Chap. 10 — non-linéarité",
        "principle": "Empiler plusieurs couches encodeur/décodeur avec activations non-linéaires : généralise la PCA à des réductions non-linéaires (variétés, pas juste hyperplans).",
        "equations": "Encodeur : z = σ_k(W_k ... σ_1(W_1 x)) · Decodeur symétrique · Loss reconstruction, éventuellement + régularisation (sparse AE : pénalité L1 sur z ; denoising AE : bruit gaussien en entrée)",
        "training": "Pré-entraînement couche par couite ou descente jointe ; le denoising apprend une représentation robuste au bruit (adapté aux features financières)",
        "use_in_fund": "Phase 2 : deep AE sur les features du ridge, code non-linéaire en entrée du modèle final",
        "status": "IMPLÉMENTÉ — évalué, pas d'edge mesurable sur nos données (documenté)",
    },
]


def get_math_topics() -> list[dict]:
    return MATH_TOPICS


def get_strategies_doc() -> dict:
    """Le bundle complet de l'onglet Stratégies : stratégies + bibliothèque maths."""
    from .strategies_doc import get_strategies

    return {
        "strategies": get_strategies(),
        "math_topics": MATH_TOPICS,
    }
