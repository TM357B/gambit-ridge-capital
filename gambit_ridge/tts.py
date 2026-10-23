"""Synthèse vocale ElevenLabs pour le terminal (onglet Voix).

La clé reste côté serveur (variable ELEVENLABS_API_KEY du fichier d'environnement du
service, ou Trousseau macOS) : le navigateur ne la voit jamais. Chaque interlocuteur
reçoit une voix fixe, choisie de façon déterministe parmi les voix du compte.
Les réponses déjà prononcées sont gardées en cache disque (même texte + même voix =
aucun crédit consommé). Sans clé ou en cas d'échec, le terminal revient aux voix
système (macOS / navigateur).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1"
MODEL = "eleven_flash_v2_5"        # conversation : latence minimale, 0,5 crédit par caractère
SPEED = 1.12                        # débit (1,0 = normal ; ElevenLabs accepte 0,7 à 1,2)
VOICE_SETTINGS = {"stability": 0.4, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True, "speed": SPEED}
MAX_CHARS = 2500                    # une réponse d'agent dépasse rarement 1 000 caractères
CACHE = Path(__file__).resolve().parent.parent / "data_cache" / "tts"
VOICES_CACHE = CACHE / "voices_v2.json"  # v2 : genre des voix
CACHE_MAX_FILES = 400


def api_key() -> str | None:
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if k:
        return k
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", "gambit-ridge-capital", "-a", "ELEVENLABS_API_KEY", "-w"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def _get(path: str, key: str) -> dict:
    req = urllib.request.Request(API + path, headers={"xi-api-key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def voices(key: str) -> list[dict]:
    """Voix utilisables, voix « françaises » en premier (rafraîchi une fois par jour)."""
    if VOICES_CACHE.exists() and time.time() - VOICES_CACHE.stat().st_mtime < 86400:
        try:
            return json.loads(VOICES_CACHE.read_text())
        except Exception:
            pass
    raw = _get("/voices", key).get("voices", [])

    def native(v: dict) -> bool:  # voix française d'origine (accent français)
        labels = {k: str(x).lower() for k, x in (v.get("labels") or {}).items()}
        return labels.get("language") == "fr" or any(w in labels.get("accent", "") for w in ("french", "parisian", "français"))

    def speaks_fr(v: dict) -> bool:  # voix étrangère certifiée en français (accent étranger)
        return any(x.get("language") == "fr" for x in (v.get("verified_languages") or []))

    def gender(v: dict) -> str | None:
        g = str((v.get("labels") or {}).get("gender", "")).lower()
        return "f" if g == "female" else "m" if g == "male" else None

    out = sorted(({"id": v["voice_id"], "name": v.get("name", ""), "fr": native(v), "fr_ok": native(v) or speaks_fr(v),
                   "gender": gender(v)} for v in raw),
                 key=lambda v: (not v["fr"], not v["fr_ok"], v["name"]))
    CACHE.mkdir(parents=True, exist_ok=True)
    VOICES_CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


def voice_for(target: str, pool: list[dict], gender: str | None = None) -> dict:
    """Même interlocuteur -> toujours la même voix, du genre du personnage s'il est connu.
    Voix françaises natives s'il y en a au moins 3 (du bon genre), sinon toutes les voix
    certifiées en français (accent étranger pour les voix anglophones)."""
    if gender and any(v.get("gender") == gender for v in pool):
        pool = [v for v in pool if v.get("gender") == gender]
    native = [v for v in pool if v["fr"]]
    capable = [v for v in pool if v.get("fr_ok")]
    candidates = native if len(native) >= 3 else (capable or pool)
    h = int(hashlib.sha1(target.encode()).hexdigest(), 16)
    return candidates[h % len(candidates)]


def status() -> dict:
    key = api_key()
    if not key:
        return {"configured": False}
    try:
        pool = voices(key)
        return {"configured": True, "voices": len(pool), "french_native": sum(v["fr"] for v in pool),
                "french_capable": sum(bool(v.get("fr_ok")) for v in pool), "model": MODEL}
    except urllib.error.HTTPError as exc:
        return {"configured": True, "error": f"ElevenLabs HTTP {exc.code}"}
    except Exception as exc:
        return {"configured": True, "error": str(exc)[:120]}


def synthesize(text: str, target: str, label: str = "", previous_text: str = "", next_text: str = "") -> tuple[bytes, dict]:
    """Audio MP3 de `text` avec la voix de `target` (`label` = nom affiché, pour le genre de la voix).
    `previous_text` / `next_text` : phrases voisines, pour une intonation continue quand la réponse
    est lue phrase par phrase. Lève RuntimeError si indisponible."""
    from .staff import voice_gender

    key = api_key()
    if not key:
        raise RuntimeError("clé ElevenLabs absente")
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        raise RuntimeError("texte vide")
    voice = voice_for(target or "terminal", voices(key), voice_gender(label))
    previous_text, next_text = (previous_text or "")[-300:], (next_text or "")[:300]
    digest = hashlib.sha1(f"{MODEL}|{SPEED}|{voice['id']}|{previous_text}|{text}|{next_text}".encode()).hexdigest()
    path = CACHE / f"{digest}.mp3"
    if path.exists():
        return path.read_bytes(), {"voice": voice["name"], "cached": True}
    payload = {"text": text, "model_id": MODEL, "voice_settings": VOICE_SETTINGS, "language_code": "fr"}
    # previous_text / next_text ne sont transmis qu'aux modèles qui les traitent comme contexte :
    # le modèle Flash en prononce une partie (mesuré le 2026-10-04).
    if not MODEL.startswith("eleven_flash"):
        if previous_text:
            payload["previous_text"] = previous_text
        if next_text:
            payload["next_text"] = next_text
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API}/text-to-speech/{voice['id']}?output_format=mp3_44100_128", data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            audio = r.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise RuntimeError(f"ElevenLabs HTTP {exc.code} : {detail}") from None
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    files = sorted(CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    for old in files[:-CACHE_MAX_FILES]:
        old.unlink(missing_ok=True)
    return audio, {"voice": voice["name"], "cached": False}
