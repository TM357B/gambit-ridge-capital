"""Construction de features cross-sectionnelles — Phase 2
(Dixon, Halperin & Bilokon, chap. 4, 7, 8).

À chaque date de rebalancement t (et pour chaque actif), on construit un
vecteur de features STRICTEMENT CAUSALES (calculées sur les prix <= t) :

    prix       : momentum 21/63/126j (rendements), vol réalisée 20/60j,
                 z-score 20j, tendance (R² log-prix 63j), distance au
                 max 252j, drawdown courant
    régimes    : probabilités a posteriori FILTRÉES de l'HMM 3 états
                 (Phase 1) — mêmes pour tous les actifs (régime de
                 l'univers agrégé)
    kalman     : bêta et alpha dynamiques de l'actif vs l'univers agrégé

Les features sont normalisées cross-sectionnellement (z-score par date,
tronqué à ±3) : la normalisation n'utilise que la coupe transversale à
la date t, jamais la série future (règle anti-look-ahead n°1).

La cible du modèle : le rendement de l'actif sur l'horizon H après t
(périodes t+1..t+H), uniquement pour l'entraînement sur fenêtre passée.
"""
from __future__ import annotations

import numpy as np

from ..regimes.hmm import GaussianHMM
from ..regimes.kalman import KalmanBeta


FEATURE_NAMES = [
    "mom_21", "mom_63", "mom_126",
    "vol_20", "vol_60",
    "zscore_20", "trend_r2_63",
    "dist_max_252", "drawdown",
    "hmm_p0", "hmm_p1", "hmm_p2",
    "kalman_beta", "kalman_alpha",
]


def _price_features(arr: np.ndarray) -> list[float]:
    """Features de prix pour UNE série, calculées à la fin de arr (causal)."""
    if len(arr) < 130:
        return [0.0] * 9
    out = []
    for lb in (21, 63, 126):
        out.append(float(arr[-1] / arr[-1 - lb] - 1.0))
    for lb in (20, 60):
        r = np.diff(arr[-lb - 1 :]) / arr[-lb - 1 : -1]
        out.append(float(np.std(r, ddof=1) * np.sqrt(252)))
    w = arr[-20:]
    sd = w.std(ddof=1)
    out.append(float((arr[-1] - w.mean()) / sd) if sd > 1e-12 else 0.0)
    y = np.log(arr[-63:])
    x = np.arange(63, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    out.append(float(np.sign(slope) * max(0.0, r2)))
    mx = arr[-252:] if len(arr) >= 252 else arr
    out.append(float(arr[-1] / mx.max() - 1.0))
    peak = mx.max()
    out.append(float(arr[-1] / peak - 1.0))
    return out


def _aggregate_returns(prices: dict[str, np.ndarray]) -> np.ndarray:
    arrs = [np.asarray(v, dtype=float) for v in prices.values() if len(v) > 1]
    rets = [np.diff(a) / a[:-1] for a in arrs]
    n = min(len(r) for r in rets)
    return np.mean(np.vstack([r[-n:] for r in rets]), axis=0)


class FeatureBuilder:
    """Construit la matrice de features (dates x actifs x features).

    Usage :
        fb = FeatureBuilder().fit(prices)          # estime HMM/Kalman sur le train
        X = fb.build(prices, t)                    # features à la date t
    """

    def __init__(self, n_states: int = 3, seed: int = 42) -> None:
        self.hmm = GaussianHMM(n_states=n_states, seed=seed, max_iter=50)
        self.kalmans: dict[str, KalmanBeta] = {}
        self.fitted = False

    def fit(self, prices: dict[str, np.ndarray]) -> "FeatureBuilder":
        """Estime HMM (sur rendements agrégés) et Kalman (par actif)
        sur la fenêtre fournie — jamais de données futures."""
        agg = _aggregate_returns(prices)
        if len(agg) >= 250:
            try:
                self.hmm.fit(agg)
            except Exception:
                pass
        for tk, arr in prices.items():
            arr = np.asarray(arr, dtype=float)
            if len(arr) < 60:
                continue
            r = np.diff(arr) / arr[:-1]
            n = min(len(r), len(agg))
            kb = KalmanBeta()
            kb.initialize(r[: max(n // 4, 30)], agg[len(agg) - n : len(agg) - n + max(n // 4, 30)])
            self.kalmans[tk] = kb
        self.fitted = True
        return self

    def build(self, prices: dict[str, np.ndarray], t: int) -> dict[str, np.ndarray]:
        """Features par actif à la date t. Les prix fournis doivent être
        la fenêtre complète (le builder ne lit que [:t+1])."""
        tickers = sorted(prices)
        rows: dict[str, np.ndarray] = {}
        post = None
        if self.hmm.fitted:
            agg = _aggregate_returns({tk: np.asarray(prices[tk])[: t + 1] for tk in tickers})
            if len(agg) >= 30:
                try:
                    post = self.hmm.filtered_posteriors(agg)
                except Exception:
                    post = None
        p_now = post[-1] if post is not None else np.full(self.hmm.n_states, 1.0 / max(self.hmm.n_states, 1))
        agg = _aggregate_returns({tk: np.asarray(prices[tk])[: t + 1] for tk in tickers})
        for tk in tickers:
            arr = np.asarray(prices[tk], dtype=float)[: t + 1]
            feats = _price_features(arr)
            feats.extend(float(p) for p in p_now)
            kb = self.kalmans.get(tk)
            if kb is not None and len(arr) >= 60 and len(agg) >= 60:
                r = np.diff(arr) / arr[:-1]
                n = min(len(r), len(agg))
                r_w = r[-n:]
                agg_w = agg[-n:]
                try:
                    beta, alpha = kb.filter_path(r_w[-252:], agg_w[-252:])
                    feats.extend([float(beta[-1]), float(alpha[-1])])
                except Exception:
                    feats.extend([0.0, 0.0])
            else:
                feats.extend([0.0, 0.0])
            rows[tk] = np.array(feats, dtype=float)
        # normalisation cross-sectionnelle (z-score tronqué ±3) par feature
        mat = np.vstack([rows[tk] for tk in tickers])
        mu = mat.mean(axis=0)
        sd = mat.std(axis=0, ddof=1)
        sd = np.where(sd < 1e-12, 1.0, sd)
        z = np.clip((mat - mu) / sd, -3.0, 3.0)
        return {tk: z[i] for i, tk in enumerate(tickers)}

    def target(
        self, prices: dict[str, np.ndarray], t: int, horizon: int = 21
    ) -> dict[str, float] | None:
        """Rendement forward sur l'horizon H (t+1..t+H). None si futur indisponible."""
        out: dict[str, float] = {}
        for tk, arr in prices.items():
            arr = np.asarray(arr, dtype=float)
            if t + horizon >= len(arr):
                return None
            out[tk] = float(arr[t + horizon] / arr[t] - 1.0)
        return out
