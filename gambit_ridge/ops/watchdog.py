"""Surveillance de l'exploitation (serveur) : lancée toutes les 10 minutes par systemd.

Chaque contrôle qui échoue déclenche UNE notification iPhone par jour (pas de rafale), et le
résultat complet est exposé au terminal (/api/system). Contrôles :
- moteur live figé (état non mis à jour) ou services arrêtés ;
- activité anormale : rotation sur 5 jours très au-dessus de la norme du backtest ;
- décrochage du compte Alpaca par rapport au portefeuille paper de référence ;
- ordres refusés dans la dernière heure ;
- disque presque plein.

La semaine du 2026-10-05 (allers-retours crypto, 1,9 rotation en une semaine, -0,4 point
contre le paper) aurait été signalée dès le premier jour par les contrôles 2 et 3.

Usage : python3 -m gambit_ridge.ops.watchdog [--quiet]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data_cache"
STATE = CACHE / "watchdog.json"
SERVICES = ("gambit-server", "gambit-live", "gambit-daily.timer", "tailscaled")

STALE_LIVE_S = 300          # moteur live sans mise à jour depuis 5 min
TURNOVER_5D = 0.60          # rotation cumulée sur 5 jours (norme backtest quotidien : ~0,30)
GAP_5D = -0.004             # compte Alpaca moins paper sur 5 jours (en rendement)
REFUSED_RECENT = 2          # ordres refusés sur la dernière heure
REFUSED_WINDOW_S = 3600
DISK_MIN_FREE = 0.10


def _service_states() -> dict[str, str]:
    out = {}
    for name in SERVICES:
        try:
            r = subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=5)
            out[name] = r.stdout.strip() or "inconnu"
        except Exception:
            out[name] = "indisponible"  # Mac de développement : pas de systemd
    return out


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def check(baseline: str = "") -> dict:
    """État complet + liste des anomalies (chacune : clé stable, message).
    `baseline` : les jours antérieurs ne comptent pas dans la rotation ni le décrochage
    (date de mise en service de la surveillance, ou du dernier correctif)."""
    from ..live.engine import enabled as live_enabled

    live = _load(CACHE / "live_state.json")
    issues: list[dict] = []
    services = _service_states()
    on_server = any(v not in ("indisponible", "inconnu") for v in services.values())
    for name, st in services.items():
        if on_server and st != "active":
            issues.append({"key": f"service-{name}", "msg": f"Service {name} : {st}"})

    age = None
    if live.get("updated"):
        age = (datetime.now() - datetime.fromisoformat(live["updated"])).total_seconds()
    if live_enabled() and on_server and (age is None or age > STALE_LIVE_S):
        issues.append({"key": "live-fige", "msg": f"Moteur live figé : dernière mise à jour il y a {int((age or 0) / 60)} min"})

    daily = [d for d in live.get("daily", []) if d.get("alpaca_equity") and d["date"] >= baseline]
    last5 = daily[-5:]
    turnover = gap = None
    if last5:
        eq = last5[-1]["alpaca_equity"]
        turnover = sum(d.get("notional") or 0 for d in last5) / eq if eq else 0.0
        if turnover > TURNOVER_5D:
            issues.append({"key": "rotation", "msg": f"Rotation anormale : {turnover:.0%} du compte échangé sur {len(last5)} jours (norme ~30 %)"})
        pair = [d for d in daily[-6:] if d.get("paper_equity")]
        if len(pair) >= 2:
            a0, a1, p0, p1 = pair[0]["alpaca_equity"], pair[-1]["alpaca_equity"], pair[0]["paper_equity"], pair[-1]["paper_equity"]
            gap = a1 / a0 - p1 / p0
            if gap < GAP_5D:
                issues.append({"key": "decrochage", "msg": f"Le compte Alpaca décroche du paper : {gap:+.2%} sur {len(pair) - 1} jours"})
    # refus récents seulement : un problème réglé ne doit pas rester en alerte jusqu'à minuit
    recent = [o for o in live.get("orders", []) if o.get("status") == "refusé" and o.get("at")
              and (datetime.now() - datetime.fromisoformat(o["at"])).total_seconds() < REFUSED_WINDOW_S]
    if len(recent) >= REFUSED_RECENT:
        issues.append({"key": "refus", "msg": f"{len(recent)} ordres refusés par Alpaca depuis une heure ({recent[-1].get('symbol', '')} : {str(recent[-1].get('error', ''))[:80]})"})
    if live.get("halted") == datetime.now().date().isoformat():
        issues.append({"key": "coupe-circuit", "msg": "Coupe-circuit actif : plus aucun ordre aujourd'hui"})

    du = shutil.disk_usage(str(ROOT))
    if du.free / du.total < DISK_MIN_FREE:
        issues.append({"key": "disque", "msg": f"Disque presque plein : {du.free / 1e9:.1f} Go libres"})

    ops = _load(CACHE / "ops_status.json")
    mem = None
    try:
        info = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        mem = {"used_mb": round((int(info["MemTotal"].split()[0]) - int(info["MemAvailable"].split()[0])) / 1024),
               "total_mb": round(int(info["MemTotal"].split()[0]) / 1024)}
    except Exception:
        pass
    uptime = None
    try:
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        pass
    return {"at": datetime.now().isoformat(timespec="seconds"), "on_server": on_server, "services": services,
            "live_age_s": None if age is None else round(age), "live_enabled": live_enabled(),
            "turnover_5d": None if turnover is None else round(turnover, 4), "gap_5d": None if gap is None else round(gap, 5),
            "disk_free_gb": round(du.free / 1e9, 1), "disk_total_gb": round(du.total / 1e9, 1), "memory": mem,
            "uptime_s": uptime, "last_daily_run": ops.get("run_at"), "daily_ok": ops.get("ok"),
            "issues": issues, "ok": not issues,
            "thresholds": {"turnover_5d": TURNOVER_5D, "gap_5d": GAP_5D, "stale_live_s": STALE_LIVE_S}}


def run(quiet: bool = False) -> dict:
    from .daily_run import notify_phone

    today = datetime.now().date().isoformat()
    st = _load(STATE)
    baseline = st.get("baseline") or today
    res = check(baseline)
    res["baseline"] = baseline
    notified = {k: v for k, v in (st.get("notified") or {}).items() if v == today}  # une fois par jour et par anomalie
    for issue in res["issues"]:
        if issue["key"] not in notified:
            if notify_phone("Gambit Ridge — surveillance", issue["msg"], urgent=True):
                notified[issue["key"]] = today
    # retour à la normale après une anomalie : un message, pour savoir que c'est réglé
    if st.get("had_issues") and not res["issues"]:
        notify_phone("Gambit Ridge — surveillance", "Retour à la normale : tous les contrôles sont au vert.")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"baseline": baseline, "notified": notified, "had_issues": bool(res["issues"]), "last": res}, ensure_ascii=False))
    if not quiet:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return res


def status() -> dict:
    """Pour le terminal : dernier passage de la surveillance (ou contrôle à la volée s'il est ancien)."""
    st = _load(STATE)
    last = st.get("last")
    if last and time.time() - datetime.fromisoformat(last["at"]).timestamp() < 900:
        return last
    return check(st.get("baseline") or "")


if __name__ == "__main__":
    run(quiet="--quiet" in sys.argv)
    sys.exit(0)
