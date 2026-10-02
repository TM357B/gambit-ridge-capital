"""Couche LLM : briefing exécutif du conseil rédigé par une IA.

Utilise l'API Mistral (https://console.mistral.ai — clé gratuite) si
MISTRAL_API_KEY est définie dans l'environnement ou .env. Sinon, produit
un résumé déterministe à partir des synthèses des managers (mode dégradé,
zéro dépendance réseau).

L'IA ne fait que de la rédaction — les chiffres et l'allocation viennent
exclusivement du moteur quantitatif. Elle ne propose jamais de positions.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"  # racine du projet


def _load_env() -> None:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and not key.startswith("#") and key not in os.environ:
                os.environ[key] = val


_load_env()


def _load_keychain(names=("MISTRAL_API_KEY", "POLYGON_API_KEY")) -> None:
    """Clés rangées dans le Trousseau macOS (scripts/move_secrets_to_keychain.sh)."""
    import subprocess

    for name in names:
        if os.environ.get(name):
            continue
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", "gambit-ridge-capital", "-a", name, "-w"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                os.environ[name] = out.stdout.strip()
        except Exception:
            pass


_load_keychain()

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
DEFAULT_MODEL = "mistral-small-latest"


def _build_prompt(briefing_dict: dict) -> str:
    teams = briefing_dict.get("teams", [])
    lines = [
        "Tu es le rédacteur du briefing quotidien d'un hedge fund quantitatif",
        "(Gambit Ridge Capital). Les managers des équipes ont produit les",
        "synthèses ci-dessous. Rédige le briefing exécutif du conseil :",
        "",
        "1. Un paragraphe « Marché » : contexte global en 3-4 phrases,",
        "   déduit des signaux (pas de données externes).",
        "2. Un paragraphe « Équipes » : pour chaque équipe, une phrase",
        "   qui résume son signal le plus important.",
        "3. Un paragraphe « Risque » : les limites touchées ou la",
        "   conformité, et l'exposition IA.",
        "4. Une ligne finale « Action » : la décision du jour en une phrase",
        "   strictement dérivée de l'allocation proposée.",
        "",
        "Contraintes : français, ton professionnel et dense, pas de liste à",
        "puces, pas d'invention de chiffres, maximum 250 mots. Tu ne proposes",
        "jamais de nouvelle position — tu commentes celle du moteur.",
        "",
        "Données :",
        f"Date : {briefing_dict.get('date')}",
        f"Part du thème IA : {briefing_dict.get('ia_share', 0):.0%}",
        f"Alertes risque : {json.dumps(briefing_dict.get('risk_reasons', []), ensure_ascii=False)}",
        f"Allocation proposée : {json.dumps(briefing_dict.get('proposed_allocation', {}), ensure_ascii=False)}",
        "Équipes :",
    ]
    for t in teams:
        sigs = []
        for s in t.get("top_signals", []):
            direction = s.get("direction", "")
            if isinstance(direction, dict):
                direction = direction.get("value", "")
            sigs.append(
                f"{s.get('ticker', '?')} {direction} "
                f"(conviction {s.get('conviction', 0):.0%}, score {s.get('score', 0):+.2f})"
            )
        lines.append(
            f"- {t.get('team')} : {t.get('headline')} ; signaux : {'; '.join(sigs) or 'aucun'}"
        )
    return "\n".join(lines)


def _fallback_briefing(briefing_dict: dict) -> str:
    teams = briefing_dict.get("teams", [])
    alloc = briefing_dict.get("proposed_allocation", {})
    top = sorted(alloc.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    top_str = ", ".join(f"{k} ({v:+.0%})" for k, v in top) or "aucune position"
    heads = [f"{t['team']} : {t['headline']}" for t in teams]
    risk = briefing_dict.get("risk_reasons", [])
    risk_str = (
        " ; ".join(risk) if risk else "allocation conforme aux limites de risque"
    )
    return (
        "BRIEFING DU CONSEIL (mode local, sans IA). "
        "Synthèse des équipes : " + " | ".join(heads) + ". "
        f"Positions principales proposées : {top_str}. "
        f"Risque : {risk_str}. "
        f"Exposition thème IA : {briefing_dict.get('ia_share', 0):.0%}."
    )


def write_briefing(briefing_dict: dict, model: str = DEFAULT_MODEL) -> dict:
    """Retourne {'text': str, 'source': 'mistral' | 'local'}."""
    api_key = os.environ.get("MISTRAL_API_KEY", "")
    prompt = _build_prompt(briefing_dict)
    if not api_key:
        return {"text": _fallback_briefing(briefing_dict), "source": "local"}

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 600,
    }
    req = urllib.request.Request(
        MISTRAL_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        text = body["choices"][0]["message"]["content"].strip()
        if not text:
            return {"text": _fallback_briefing(briefing_dict), "source": "local"}
        return {"text": text, "source": "mistral"}
    except Exception:
        return {"text": _fallback_briefing(briefing_dict), "source": "local"}


def enrich_briefing(briefing_dict: dict) -> dict:
    """Ajoute la clé 'executive' au dict du briefing."""
    briefing_dict["executive"] = write_briefing(briefing_dict)
    return briefing_dict
