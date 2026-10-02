"""Chargement des fondamentaux avec délai de publication — anti-look-ahead.

Règle n°1 du plan (Dixon, Halperin & Bilokon) : un report publié à la
date t ne doit être visible qu'à t + délai de publication. Le CSV fourni
n'a pas de `date_publication` renseignée : on applique donc un lag
forfaitaire (45 jours par défaut, config.yaml ->
data.fundamentals.publication_lag_days), cohérent avec le calendrier de
publication des résultats annuels US (30-60 jours après clôture).

Interface :
    load_fundamentals(path) -> list[FundamentalRow]
    fundamentals_visible_at(rows, iso_date, lag_days) -> dict[ticker, FundamentalRow]
        ne retourne que les reports dont fin_periode + lag <= date demandée
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DEFAULT_LAG_DAYS = 45

_FLOAT_FIELDS = {
    "revenue", "croissance_revenue_yoy_pct", "cost_of_revenue", "gross_profit",
    "sga", "r_and_d", "operating_expenses", "operating_income",
    "interest_expense", "interest_investment_income", "pretax_income",
    "income_tax_expense", "net_income", "shares_basic", "shares_diluted",
    "eps_basic", "eps_diluted", "ebitda", "da",
    "marge_brute_pct", "marge_operationnelle_pct", "marge_nette_pct",
    "marge_ebitda_pct", "taux_impot_effectif_pct",
    "operating_cash_flow", "capex", "free_cash_flow", "fcf_par_action",
    "marge_fcf_pct", "stock_based_comp", "investing_cash_flow",
    "financing_cash_flow", "rachat_actions", "emission_actions", "net_cash_flow",
    "cash_equivalents", "short_term_investments", "cash_et_placements_ct",
    "receivables", "total_current_assets", "total_assets",
    "total_current_liabilities", "total_liabilities",
    "total_common_equity", "shareholders_equity", "total_debt", "net_cash",
    "working_capital", "book_value_par_action", "tangible_book_value",
    "shares_outstanding_date_depot", "shares_outstanding_total",
}


@dataclass
class FundamentalRow:
    ticker: str
    periode: str
    fin_periode: date
    date_publication: date | None
    values: dict[str, float | None]

    @property
    def visible_from(self) -> date:
        """Première date à laquelle ce report est exploitable."""
        if self.date_publication is not None:
            return self.date_publication
        return self.fin_periode + timedelta(days=DEFAULT_LAG_DAYS)


def _to_float(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_fundamentals(path: str | Path) -> list[FundamentalRow]:
    """Charge le CSV de fondamentaux. Colonnes numériques -> float|None."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV fondamentaux introuvable: {path}")
    rows: list[FundamentalRow] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rec in reader:
            fin = date.fromisoformat(rec["fin_periode"].strip())
            pub_raw = (rec.get("date_publication") or "").strip()
            pub = date.fromisoformat(pub_raw) if pub_raw else None
            values = {k: _to_float(rec.get(k, "")) for k in _FLOAT_FIELDS}
            rows.append(
                FundamentalRow(
                    ticker=rec["ticker"].strip(),
                    periode=rec["periode"].strip(),
                    fin_periode=fin,
                    date_publication=pub,
                    values=values,
                )
            )
    if not rows:
        raise ValueError("aucune ligne de fondamentaux lue")
    return rows


def fundamentals_visible_at(
    rows: list[FundamentalRow],
    iso_date: str,
    lag_days: int = DEFAULT_LAG_DAYS,
) -> dict[str, FundamentalRow]:
    """Reports visibles à la date donnée (anti-look-ahead).

    Un report est visible si date_publication (ou fin_periode + lag)
    est strictement antérieure à la date demandée. En cas de reports
    multiples pour un ticker, le plus récent visible est retenu.
    """
    d = date.fromisoformat(iso_date)
    visible: dict[str, FundamentalRow] = {}
    for row in rows:
        effective_pub = row.date_publication or (row.fin_periode + timedelta(days=lag_days))
        if effective_pub < d and (
            row.ticker not in visible
            or effective_pub > (visible[row.ticker].date_publication
                                or visible[row.ticker].fin_periode + timedelta(days=lag_days))
        ):
            visible[row.ticker] = row
    return visible
