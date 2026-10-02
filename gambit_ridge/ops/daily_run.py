"""Passage quotidien automatique (lancé par launchd, même app fermée).

1. Exécute le paper trading si une nouvelle séance est close
2. Rafraîchit le briefing du conseil des agents (données réelles)
3. Sauvegarde le journal (60 derniers jours conservés)
4. Écrit l'état d'exploitation (data_cache/ops_status.json) et notifie macOS :
   problème de données, erreur, drawdown ou perte du jour anormaux, résumé.

Usage : python3 -m gambit_ridge.ops.daily_run [--quiet]
Installation de la tâche : bash scripts/install_daily_job.sh
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data_cache"
STATUS = CACHE / "ops_status.json"
LOG = CACHE / "ops.log"
BACKUPS = CACHE / "backups"
KEEP_BACKUPS = 60

# seuils d'alerte
ALERT_DRAWDOWN = 0.08
ALERT_DAY_LOSS = 0.02


def log(msg: str) -> None:
    CACHE.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def notify(title: str, message: str) -> None:
    """Notification macOS (silencieuse si osascript indisponible)."""
    script = f'display notification {json.dumps(message)} with title {json.dumps(title)}'
    try:
        subprocess.run(["osascript", "-e", script], timeout=10, check=False, capture_output=True)
    except Exception:
        pass


def _ntfy_topic() -> str | None:
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", "gambit-ridge-capital", "-a", "NTFY_TOPIC", "-w"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def notify_phone(title: str, message: str, urgent: bool = False, tags: str = "chart_with_upwards_trend") -> bool:
    """Notification iPhone via ntfy (canal privé au nom aléatoire, rangé dans le Trousseau)."""
    import urllib.request

    topic = _ntfy_topic()
    if not topic:
        return False
    from urllib.parse import urlencode

    # titre passé en paramètre d'URL (les en-têtes HTTP n'acceptent pas les accents)
    q = urlencode({"title": title, "priority": "high" if urgent else "default", "tags": "warning" if urgent else tags})
    req = urllib.request.Request(f"https://ntfy.sh/{topic}?{q}", data=message.encode("utf-8"), method="POST")
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception:
        return False


def backup_journal() -> None:
    src = CACHE / "paper_journal_v2.json"
    if not src.exists():
        return
    BACKUPS.mkdir(exist_ok=True)
    shutil.copy2(src, BACKUPS / f"paper_journal_{datetime.now():%Y-%m-%d}.json")
    for old in sorted(BACKUPS.glob("paper_journal_*.json"))[:-KEEP_BACKUPS]:
        old.unlink()


def main(quiet: bool = False) -> int:
    status = {"run_at": datetime.now().isoformat(timespec="seconds"), "ok": True, "alerts": [], "steps": {}}
    try:
        import time

        from ..paper import _load_journal, run_paper_day

        before = dict(_load_journal().get("last_price_dates") or {})
        s = run_paper_day()
        waited = 0
        while s.get("loading") and waited < 600:  # calcul déjà en cours (serveur de l'app) : on attend
            time.sleep(10)
            waited += 10
            s = run_paper_day()
        ran = (s.get("last_price_dates") or {}) != before
        status["steps"]["paper"] = "séance traitée" if ran else "rien de nouveau"
        last = s["equity_history"][-1] if s["equity_history"] else None
        status["equity"] = s["equity"]
        status["drawdown"] = s["current_drawdown"]
        status["last_session"] = s.get("last_price_dates")
        for kind, issues in (s.get("quality") or {}).items():
            for i in issues:
                status["alerts"].append(f"Données {kind} : {i}")
        if s.get("blocked"):
            status["alerts"].append(f"Rebalancement suspendu sur {len(s['blocked'])} lignes (contrôle qualité)")
        for k, v in (s.get("errors") or {}).items():
            status["alerts"].append(f"Erreur {k} : {v}")
        if s["current_drawdown"] > ALERT_DRAWDOWN:
            status["alerts"].append(f"Drawdown de {s['current_drawdown']:.1%} (seuil {ALERT_DRAWDOWN:.0%})")
        if ran and last and last["equity"] - last["day_pnl"] > 0:
            day = last["day_pnl"] / (last["equity"] - last["day_pnl"])
            status["day_return"] = day
            if day < -ALERT_DAY_LOSS:
                status["alerts"].append(f"Perte de {day:.1%} sur la séance")
    except Exception as exc:
        status["ok"] = False
        status["alerts"].append(f"Échec du paper trading : {exc}")
        log(traceback.format_exc())

    try:  # santé de la stratégie (réel vs zone normale du backtest)
        from ..monitoring.health import health

        h = health()
        status["health"] = h["status"]
        if h["status"] == "hors norme":
            bad = [f"{x['h']} séances : {x['return']:+.1%}" for x in h["horizons"] if x["verdict"] == "hors norme"]
            status["alerts"].append("Stratégie HORS NORME par rapport au backtest (" + ", ".join(bad) + ") — à réexaminer")
    except Exception as exc:
        status["steps"]["santé"] = f"échec : {exc}"

    try:  # réplication sur le compte paper Alpaca (si les clés sont configurées)
        from ..brokers.alpaca import has_credentials
        from ..brokers.alpaca_mirror import run as alpaca_run

        if has_credentials():
            r = alpaca_run()
            n_sent = sum(1 for o in r["results"] if o["status"] == "envoyé")
            refused = [o for o in r["results"] if o["status"] == "refusé"]
            status["steps"]["alpaca"] = f"{'envoi' if r['live'] else 'essai'} : {len(r['results'])} ordres, {n_sent} envoyés"
            for o in refused:
                status["alerts"].append(f"Alpaca a refusé {o['side']} {o['symbol']} : {o.get('error', '')[:80]}")
        else:
            status["steps"]["alpaca"] = "non configuré"
    except Exception as exc:
        status["steps"]["alpaca"] = f"échec : {exc}"
        status["alerts"].append(f"Réplication Alpaca : {exc}")
        log(traceback.format_exc())

    try:  # briefing du conseil (agents sur données réelles)
        from ..app.server import _refresh

        _refresh()
        status["steps"]["briefing"] = "ok"
    except Exception as exc:
        status["steps"]["briefing"] = f"échec : {exc}"
        log(traceback.format_exc())

    try:  # note de recherche hebdomadaire (le week-end) + référence du backtest mensuelle
        from datetime import date

        from ..research_note import NOTES, generate, week_id

        if date.today().weekday() >= 5 and not (NOTES / f"{week_id()}.json").exists():
            from ..monitoring.health import REF_PATH, build_reference

            if not REF_PATH.exists() or (datetime.now().timestamp() - REF_PATH.stat().st_mtime) > 30 * 86400:
                build_reference()
            n = generate()
            status["steps"]["note"] = f"{n['id']} ({n['source']})"
            first = n["markdown"].split("## Marchés")[0].replace("## Synthèse", "").strip()
            notify_phone(f"Note de recherche {n['id']}", first[:900], tags="memo")
    except Exception as exc:
        status["steps"]["note"] = f"échec : {exc}"
        log(traceback.format_exc())

    try:
        backup_journal()
        status["steps"]["sauvegarde"] = "ok"
    except Exception as exc:
        status["steps"]["sauvegarde"] = f"échec : {exc}"

    CACHE.mkdir(exist_ok=True)
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1))
    log(f"ok={status['ok']} alertes={len(status['alerts'])} étapes={status['steps']}")

    if status["alerts"]:
        msg = " · ".join(status["alerts"])
        notify("Gambit Ridge Capital — alerte", msg[:240])
        notify_phone("GRC - alerte", msg[:1000], urgent=True)
    elif not quiet and "day_return" in status:
        msg = f"Séance {status['day_return']:+.2%} · équity {status['equity'] / 1e6:.3f} M$ · drawdown {status['drawdown']:.1%}"
        if status.get("health"):
            msg += f" · santé : {status['health']}"
        notify("Gambit Ridge Capital", msg)
        notify_phone("Gambit Ridge Capital", msg)
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(quiet="--quiet" in sys.argv))
