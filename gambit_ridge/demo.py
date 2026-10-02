"""Démo : réunion quotidienne du conseil des managers.

Sources réelles quand disponibles (Binance crypto, FRED facteurs macro),
repli automatique sur simulation pour le reste (actions, forex...).
"""

from __future__ import annotations

import argparse
import json
import sys

from .council import Council
from .core.agent import MarketData
from .core.risk import RiskLimits
from .data.simulation import all_configured_tickers, simulate_market_data
from .teams import IA_TICKERS, build_commodities_team, build_crypto_team, build_forex_team, build_ia_tech_team, build_macro_team, build_micro_team


def _real_data() -> tuple[dict[str, MarketData], dict[str, list[float]]]:
    """Charge Binance (crypto) et FRED (facteurs macro). Retourne (data, factors)."""
    data: dict[str, MarketData] = {}
    factors: dict[str, list[float]] = {}

    try:
        from .data.binance import BinanceConnector, BINANCE_SYMBOLS

        conn = BinanceConnector()
        for tk in BINANCE_SYMBOLS:
            try:
                data[tk] = conn.fetch(tk, 365)
            except Exception:
                continue
    except Exception:
        pass

    try:
        from .data.fred_loader import load_fred_factors

        factors = {k: list(v[1]) for k, v in load_fred_factors().items()}
    except Exception:
        pass

    return data, factors


def build_fund(factors: dict[str, list[float]] | None = None) -> Council:
    managers = [
        build_macro_team(factors),
        build_micro_team(),
        build_crypto_team(),
        build_forex_team(),
        build_commodities_team(),
        build_ia_tech_team(),
    ]
    return Council(
        managers,
        RiskLimits(),
        ia_tickers=IA_TICKERS,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Journée simulée du fonds")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--periods", type=int, default=90)
    parser.add_argument("--offline", action="store_true", help="simulation pure, aucune source externe")
    args = parser.parse_args()

    factors: dict[str, list[float]] = {}
    real: dict[str, MarketData] = {}
    if not args.offline:
        real, factors = _real_data()

    council = build_fund(factors)

    # Les tickers non couverts par les sources réelles passent en simulation
    simulated = simulate_market_data(all_configured_tickers(), args.periods, args.seed)
    merged = dict(simulated)
    merged.update(real)

    briefing = council.meeting(merged)

    if args.json:
        print(json.dumps(briefing.to_dict(), indent=2, ensure_ascii=False))
        return 0

    src = f"{len(real)} tickers réels" if real else "simulation pure"
    print("=" * 72)
    print(f"  BRIEFING QUOTIDIEN — {briefing.day}  ({src})")
    print("=" * 72)
    for section in briefing.sections:
        print(f"\n[{section.team}] {section.headline}")
        for s in section.top_signals:
            print(
                f"    {s.ticker:<10} {s.direction.value:<8} "
                f"conviction {s.conviction:.0%}  confiance {s.confidence:.0%}  "
                f"score {s.score():+.2f}"
            )
        if section.watchlist:
            print(f"    Surveillance : {', '.join(section.watchlist)}")

    print("\n" + "-" * 72)
    print("ALLOCATION PROPOSÉE (après sizing Kelly + vol-target)")
    for ticker, weight in sorted(briefing.proposed_allocation.items(), key=lambda x: -abs(x[1])):
        tag = "IA" if ticker in IA_TICKERS else "  "
        print(f"  {tag} {ticker:<10} {weight:+.2%}")
    print(f"\nPoids du thème IA dans l'exposition : {briefing.ia_share:.0%}")

    if briefing.risk_reasons:
        print("\n⚠ LIMITES DE RISQUE :")
        for r in briefing.risk_reasons:
            print(f"  - {r}")
    else:
        print("\n✓ Allocation conforme aux limites de risque.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
