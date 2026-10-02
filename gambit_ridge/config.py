"""Utilitaires de configuration : chargement du .env sans fuite de secret."""

from __future__ import annotations

import os
from pathlib import Path


def load_env() -> dict[str, str]:
    """Charge .env (CLÉ=VALEUR) sans écraser l'environnement existant."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def get_polygon_key() -> str | None:
    """Clé Polygon : variable d'environnement prioritaire, sinon .env."""
    from . import llm_briefing  # noqa: F401  (charge .env puis Trousseau)

    return os.environ.get("POLYGON_API_KEY") or load_env().get("POLYGON_API_KEY")
