"""Carry de change G10 — candidat de diversification (banc d'évaluation).

Rendement d'une position longue devise c contre dollar, par jour :
    r_t = variation du cours (USD par unité de c) + (taux_c - taux_USD) / 252
(c'est le rendement d'un contrat à terme de change roulé : parité des taux
couverte). Taux : 3 mois interbancaire OCDE (FRED), publiés avec retard ->
on n'utilise à la date t que la valeur du mois t - 2 (aucune anticipation).

Signal (classique, fixé a priori) : on classe les 9 devises selon leur
différentiel de taux contre le dollar, achat des 3 plus rémunératrices,
vente des 3 moins rémunératrices, positions à risque égal.
Variante « filtrée » : on ne garde une jambe que si la tendance de la devise
(ensemble TSMOM / EWMA / Kalman) ne la contredit pas — protection connue
contre les krachs du carry (2008).
"""

from __future__ import annotations

import numpy as np

RATE_SERIES = {
    "USD": "IR3TIB01USM156N", "EUR": "IR3TIB01EZM156N", "JPY": "IR3TIB01JPM156N",
    "GBP": "IR3TIB01GBM156N", "CHF": "IR3TIB01CHM156N", "CAD": "IR3TIB01CAM156N",
    "AUD": "IR3TIB01AUM156N", "NZD": "IR3TIB01NZM156N", "SEK": "IR3TIB01SEM156N",
    "NOK": "IR3TIB01NOM156N",
}
PUBLICATION_LAG_MONTHS = 2


def _month_shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m -= k
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def load_carry_data():
    """Retourne (dates, spot USD/unité par devise, taux connus à chaque date en %)."""
    from ..data.fred import FredConnector
    from ..data.yahoo import YahooConnector
    from ..market_functions import FX

    conn = YahooConnector()
    spot_raw = {}
    for ccy, (sym, usd_per) in FX.items():
        if ccy not in RATE_SERIES:
            continue
        data = conn.fetch(sym, refresh=False)
        spot_raw[ccy] = {d: (v if usd_per else 1.0 / v) for d, v in data.items() if v > 0}
    dates = sorted(set.intersection(*(set(v) for v in spot_raw.values())))
    fred = FredConnector()
    monthly = {}
    for ccy, sid in RATE_SERIES.items():
        ds, vals = fred.fetch_series(sid)
        monthly[ccy] = {d[:7]: float(v) for d, v in zip(ds, vals)}

    def known_rate(ccy: str, d: str):
        ym = _month_shift(d[:7], PUBLICATION_LAG_MONTHS)
        m = monthly[ccy]
        # dernière valeur publiée au plus tard au mois ym (les séries arrêtées restent figées)
        for k in range(0, 12):
            v = m.get(_month_shift(ym, k))
            if v is not None:
                return v
        return np.nan

    first_ok = next(i for i, d in enumerate(dates) if all(np.isfinite(known_rate(c, d)) for c in RATE_SERIES))
    dates = dates[first_ok:]
    ccys = [c for c in RATE_SERIES if c != "USD"]
    spot = np.column_stack([[spot_raw[c][d] for d in dates] for c in ccys])
    rates = np.column_stack([[known_rate(c, d) for d in dates] for c in RATE_SERIES])
    return dates, ccys, spot, rates  # rates[:, 0] = USD


def carry_total_return_index(spot: np.ndarray, rates: np.ndarray) -> np.ndarray:
    """Indice de rendement total d'un terme roulé long devise / court USD."""
    diff = (rates[:, 1:] - rates[:, [0]]) / 100.0
    r = np.zeros_like(spot)
    r[1:] = spot[1:] / spot[:-1] - 1.0 + diff[:-1] / 252.0
    return np.cumprod(1.0 + r, axis=0)


def carry_signal(rates: np.ndarray, n_long: int = 3, n_short: int = 3) -> np.ndarray:
    diff = rates[:, 1:] - rates[:, [0]]
    S = np.zeros_like(diff)
    order = np.argsort(diff, axis=1)
    for t in range(len(diff)):
        S[t, order[t, -n_long:]] = 1.0
        S[t, order[t, :n_short]] = -1.0
    return S
