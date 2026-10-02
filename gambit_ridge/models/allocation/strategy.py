"""Stratégie hybride signaux + allocation RL — Phase 3.

Le modèle de signaux ridge (Phase 2, validé OOS) choisit QUEL actif
acheter/vendre ; l'allocateur RL (G-learning ou Q-learning, chap. 9-10)
choisit COMBIEN de risque prendre (levier), conditionné au régime de
marché (HMM Phase 1), à la volatilité et à l'exposition courante.

Anti-look-ahead : les deux modèles sont entraînés dans weight_fn
uniquement sur les données <= t (fenêtre glissante), avec embargo
de `horizon` jours sur les cibles forward du ridge.
"""

from __future__ import annotations

import numpy as np

from ..regimes.hmm import GaussianHMM
from ..signals.strategy import ml_ranking_strategy


def _portfolio_returns(weights_fn, prices, t_start, t_end):
    """Rendements quotidiens du portefeuille de signaux entre t_start et t_end."""
    tickers = sorted(prices)
    rets = []
    for t in range(t_start, t_end):
        w = weights_fn(t, {tk: prices[tk][: t + 1] for tk in tickers})
        if not w:
            rets.append(0.0)
            continue
        r = np.array([
            prices[tk][t + 1] / prices[tk][t] - 1.0 if t + 1 < len(prices[tk]) else 0.0
            for tk in tickers
        ])
        wv = np.array([w.get(tk, 0.0) for tk in tickers])
        rets.append(float(np.dot(wv, r)))
    return np.array(rets)


def rl_ranking_strategy(
    *,
    allocator: str = "glearning",     # "glearning" | "qlearning" | "fixed"
    horizon: int = 21,
    train_window: int = 750,
    rebalance_every: int = 5,
    n_positions: int = 3,
    lam: float = 10.0,
    fixed_leverage: float = 1.0,
    seed: int = 42,
):
    """Ridge (signaux) + G/Q-learning (levier), ré-entraînés sur fenêtre passée.

    allocator="fixed" : baseline sans RL (levier constant) pour comparaison.
    """
    from .glearning import GLearningAllocator
    from .qlearning import QLearningAllocator

    signals_fn = ml_ranking_strategy(
        model="ridge", horizon=horizon, train_window=train_window,
        rebalance_every=rebalance_every, n_positions=n_positions, lam=lam, seed=seed,
    )
    state: dict = {
        "allocator": None,
        "hmm": None,
        "last_train": -(10**9),
        "leverage": fixed_leverage if allocator == "fixed" else 0.0,
        "last_rebalance": -(10**9),
    }
    retrain_every = max(train_window // 4, 60)

    def _train_all(prices, t):
        tickers = sorted(prices)
        train_end = t - horizon
        if train_end < 300:
            return
        window = {tk: np.asarray(v, dtype=float) for tk, v in prices.items()}
        # Rendements agrégés pour l'HMM (régime de l'univers)
        arrs = [np.diff(window[tk]) / window[tk][:-1] for tk in tickers]
        n = min(len(a) for a in arrs)
        agg = np.mean(np.vstack([a[-n:] for a in arrs]), axis=0)
        hmm = GaussianHMM(n_states=3, seed=seed)
        try:
            hmm.fit(agg[-min(len(agg), train_window):])
            probs = hmm.filtered_posteriors(agg[-min(len(agg), train_window):])
        except Exception:
            return
        # Rendements du portefeuille de signaux sur la fenêtre passée
        start_t = max(130, train_end - 250)
        sig = ml_ranking_strategy(
            model="ridge", horizon=horizon, train_window=train_window,
            rebalance_every=rebalance_every, n_positions=n_positions, lam=lam, seed=seed,
        )
        pr = _portfolio_returns(sig, window, start_t, train_end - 1)
        if len(pr) < 100:
            return
        # Aligner probs sur la fin des rendements du portefeuille
        probs_al = probs[-len(pr):] if len(probs) >= len(pr) else probs
        if allocator == "glearning":
            alloc = GLearningAllocator()
            alloc.fit(pr, probs_al)
        elif allocator == "qlearning":
            alloc = QLearningAllocator()
            alloc.fit(pr, probs_al, seed=seed)
        else:
            alloc = None
        state["allocator"] = alloc
        state["hmm"] = hmm
        state["probs"] = probs
        state["agg"] = agg

    def weight_fn(t, prices_by_ticker):
        prices = {tk: np.asarray(v, dtype=float) for tk, v in prices_by_ticker.items()}
        if allocator != "fixed" and t - state["last_train"] >= retrain_every:
            try:
                _train_all(prices, t)
            except Exception:
                pass
            state["last_train"] = t
            # Échec d'entraînement : réessayer au prochain appel plutôt
            # que de rester sans allocateur pendant retrain_every jours.
            if state.get("allocator") is None:
                state["last_train"] = t - retrain_every + 1
        # Poids de signaux (ridge)
        base = signals_fn(t, prices_by_ticker)
        if not base or allocator == "fixed":
            if allocator == "fixed" and base:
                return {tk: w * fixed_leverage for tk, w in base.items()}
            return base
        # Levier RL : régime HMM a posteriori à t
        try:
            agg_recent = state.get("agg")
            hmm = state["hmm"]
            if hmm is None or agg_recent is None:
                return base
            probs_t = hmm.filtered_posteriors(agg_recent[-min(len(agg_recent), 250):])[-1]
            vols = np.convolve(np.abs(agg_recent[-250:]), np.ones(10) / 10, mode="same")
            if isinstance(state["allocator"], GLearningAllocator):
                lev = state["allocator"].act(probs_t, state["leverage"])
            else:
                lev = state["allocator"].act(probs_t, float(vols[-1]), state["leverage"])
        except Exception:
            lev = 1.0
        state["leverage"] = lev
        return {tk: w * lev for tk, w in base.items()}

    return weight_fn
