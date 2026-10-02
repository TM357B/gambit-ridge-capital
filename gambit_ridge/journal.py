"""Journal de paper-trading : enregistre les briefings et suit le P&L.

Chaque enregistrement stocke l'allocation proposée + les prix du moment.
Au rechargement suivant, le P&L réalisé est calculé avec les prix actuels.
Format : JSON Lines dans journal/trackrecord.jsonl.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

JOURNAL_DIR = Path(__file__).resolve().parent.parent / "journal"
JOURNAL_FILE = JOURNAL_DIR / "trackrecord.jsonl"


def record_briefing(allocation: dict[str, float], prices: dict[str, float], day: date | None = None) -> dict:
    """Enregistre une entrée dans le journal (une par jour maximum)."""
    JOURNAL_DIR.mkdir(exist_ok=True)
    entry = {
        "date": (day or date.today()).isoformat(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "allocation": allocation,
        "prices": prices,
    }
    entries = load_entries()
    entries = [e for e in entries if e["date"] != entry["date"]]
    entries.append(entry)
    entries.sort(key=lambda e: e["date"])
    JOURNAL_FILE.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n"
    )
    return entry


def load_entries() -> list[dict]:
    if not JOURNAL_FILE.exists():
        return []
    entries = []
    for line in JOURNAL_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return sorted(entries, key=lambda e: e["date"])


def compute_pnl(current_prices: dict[str, float]) -> list[dict]:
    """P&L réalisé de chaque entrée, et courbe cumulée du paper portfolio.

    Le portefeuille papier : chaque jour enregistré, on ouvre l'allocation
    proposée. Le P&L d'un jour = somme pondérée des rendements prix d'entrée
    -> maintenant. La courbe cumulée enchaîne ces jours de façon simplifiée
    (base 100, chaque enregistrement est une "journée" de trading).
    """
    entries = load_entries()
    results = []
    equity = 100.0
    for e in entries:
        pnl = 0.0
        gross = sum(abs(w) for w in e["allocation"].values())
        if gross > 0 and e["prices"]:
            for tk, w in e["allocation"].items():
                p0 = e["prices"].get(tk)
                p1 = current_prices.get(tk)
                if p0 and p1 and p0 > 0:
                    pnl += w * (p1 / p0 - 1.0)
        equity *= 1.0 + pnl
        results.append(
            {
                "date": e["date"],
                "allocation": e["allocation"],
                "pnl": round(pnl, 6),
                "equity": round(equity, 4),
                "gross_exposure": round(gross, 4),
            }
        )
    return results
