"""Conversation avec les agents et managers (onglet Voix, chat des agents).

Avec MISTRAL_API_KEY : l'interlocuteur répond comme un collègue, à l'oral,
en s'appuyant UNIQUEMENT sur ses données (signaux, statistiques) et sur le
portefeuille réel du fonds. Règle de la maison inchangée : l'IA explique,
elle ne décide jamais d'une position.
Sans clé ou en cas d'échec réseau : réponses déterministes par mots-clés.
"""

from __future__ import annotations

import json
import os
import urllib.request

from . import llm_briefing  # charge le .env à l'import
from .agents_api import ask_agent, ask_manager, get_agent_details, get_manager_details

MAX_HISTORY = 8


def _fund_context() -> dict:
    """Résumé du portefeuille réel (paper v2), sans calcul ni réseau."""
    try:
        from .paper import summary

        s = summary()
        return {
            "strategie": s["strategy"],
            "equity": s["equity"],
            "performance_depuis_depart": s["total_return"],
            "drawdown": s["current_drawdown"],
            "exposition_nette_par_classe": s["exposure_by_class"],
            "positions": [
                f"{'ACHETEUR' if p['weight'] > 0 else 'VENDEUR'} {p['ticker']} ({p['name']}) : {abs(p['weight']):.1%} du capital"
                for p in s["positions"][:14]
            ],
        }
    except Exception:
        return {}


def _persona(target: str) -> tuple[str, dict]:
    if target.startswith("manager-"):
        d = get_manager_details(target)
        who = f"{d['manager_name']}, manager de l'équipe {d['team']} de Gambit Ridge Capital"
        ctx = {
            "equipe": d["team"],
            "synthese": d["headline"],
            "score_agrege": d["aggregate_score"],
            "signaux_principaux": d["top_signals"][:6],
            "watchlist": d["watchlist"],
            "agents": [{"agent": a["agent"], "perimetre": a["scope"], "n_signaux": a["n_signals"], "resume": a["summary"]} for a in d["agents"]],
        }
        return who, ctx
    d = get_agent_details(target)
    who = f"{d['name']} ({d['specialty']}, {d['school']}), analyste de l'équipe {d['team']} sous la responsabilité de {d['manager']}"
    ctx = {
        "perimetre": d["scope"],
        "actifs_suivis": d["tickers"],
        "signaux": d["signals"][:8],
        "statistiques": d["ticker_stats"][:12],
        "resume": d.get("summary", ""),
    }
    return who, ctx


SYSTEM = """Tu es {who}. Tu parles à Tom, le gérant du fonds, à l'oral (ta réponse sera lue par une voix de synthèse).
Règles :
- Français parlé, naturel : 3 phrases maximum, moins de 70 mots. Pas de listes, pas de markdown, pas d'émojis. Arrondis les chiffres (« environ 12 % »).
- Convention des paires de devises : « XXXYYY long » = acheter XXX contre YYY (USDCNH long = acheter le dollar, vendre le yuan). « short » = l'inverse. Vérifie ce sens avant de parler.
- Le portefeuille réel est décrit position par position (ACHETEUR / VENDEUR) : cite-le exactement, ne le contredis jamais.
- Appuie-toi UNIQUEMENT sur les données JSON ci-dessous. N'invente aucun chiffre, aucune actualité. Si l'info manque, dis-le simplement.
- Les signaux de ton équipe sont calculés sur des prix réels de clôture, mais ce sont des pistes de recherche non validées par le banc d'évaluation. Le portefeuille réel est piloté par la stratégie quantitative validée (section « fonds »). Si Tom te demande d'acheter ou vendre, explique ce que disent les données et rappelle que la décision passe par le moteur quantitatif et ses limites de risque.
- Tu peux donner ton avis d'analyste, en le présentant comme tel.

Données de ton poste :
{ctx}

Portefeuille réel du fonds :
{fund}"""


CONVERSATION_MODELS = ("mistral-large-latest", llm_briefing.DEFAULT_MODEL)


def _mistral(messages: list[dict], max_tokens: int = 220) -> str | None:
    """Modèle le plus fiable d'abord ; repli sur le petit modèle (quota, panne)."""
    key = os.environ.get("MISTRAL_API_KEY", "")
    if not key:
        return None
    for model in CONVERSATION_MODELS:
        req = urllib.request.Request(
            llm_briefing.MISTRAL_URL,
            data=json.dumps({"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                text = json.loads(resp.read())["choices"][0]["message"]["content"].strip()
            if text:
                return text
        except Exception:
            continue
    return None


def converse(target: str, question: str, history: list[dict] | None = None) -> dict:
    """Réponse conversationnelle ; `history` = [{role: user|assistant, content}]."""
    is_manager = target.startswith("manager-") and target != "manager-rh"
    who, ctx = _persona(target) if (is_manager or not target.startswith("manager-")) else (target, {})
    msgs = [{"role": "system", "content": SYSTEM.format(
        who=who,
        ctx=json.dumps(ctx, ensure_ascii=False, default=str)[:6000],
        fund=json.dumps(_fund_context(), ensure_ascii=False, default=str)[:3000],
    )}]
    for h in (history or [])[-MAX_HISTORY:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": str(h["content"])[:1500]})
    msgs.append({"role": "user", "content": question})
    text = _mistral(msgs)
    if text:
        return {"answer": text, "source": "mistral"}
    fallback = ask_manager(target, question) if is_manager else ask_agent(target, question)
    return {"answer": fallback["answer"], "source": "local"}
