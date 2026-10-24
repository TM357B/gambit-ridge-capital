"""Serveur local du dashboard Gambit Ridge Capital.

Zéro dépendance : stdlib uniquement (http.server). Écoute sur 127.0.0.1 et,
si Tailscale est connecté, sur l'adresse Tailscale du Mac (réseau privé chiffré
entre tes appareils : accès depuis l'iPhone). Jamais exposé sur Internet ni sur
le réseau local.

Endpoints :
  GET /            → dashboard HTML
  GET /api/state   → briefing du jour + allocation + risk + prix réels
  GET /api/journal → historique paper-trading + P&L
  GET /api/paper   → portefeuille papier v2 (stratégie retenue)
  GET /api/research → rapport du banc d'évaluation des stratégies
  GET /api/grql?q=…[&format=csv], /api/bdp?s=&f=, /api/bdh?s=&f=&debut=&fin= → langage de requête et API Excel
  GET /api/xl?fn=bdp|bdh|bds|bql&s=&f=&d=&e=&o=Per=W|Dts=H&u=&x= → complément Excel (TSV, syntaxe Bloomberg)
  GET /api/fn/{gp,des,fxc,wcrs,ecst,wei,gc,ovdv,ovml,mc,gc3d,budg,mac,ilbe,qlbs,gpg,gpvs,svol,beta,regm,tsa,modl,fa,eqs,gew}[?s=TICKER&…] → fonctions de marché façon Bloomberg
  GET /api/risk, /api/attribution, /api/ops → risque, attribution, état d'exploitation
  GET /report[/AAAA-MM] → rapport mensuel imprimable
  GET /api/health, /api/tca, /api/notes[/AAAA-Www] ; POST /api/notes/generate
  POST /api/run    → exécute la réunion quotidienne maintenant
  POST /api/converse → conversation avec un agent / manager (LLM si clé Mistral)
  POST /api/tts      → réponse lue par une voix ElevenLabs (MP3), GET /api/tts/status
  POST /api/backtest → backtest interactif (stratégie + source de données)
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import journal
from ..council import Council
from ..core.agent import MarketData
from ..core.risk import RiskLimits
from ..demo import build_fund
from ..teams import IA_TICKERS

APP_DIR = Path(__file__).resolve().parent
STATE_LOCK = threading.Lock()
LAST_BRIEFING: dict | None = None
CACHE_FILE = APP_DIR.parent.parent / "data_cache" / "state_cache.json"


STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
                ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/manifest+json",
                ".webmanifest": "application/manifest+json", ".ico": "image/x-icon"}


def _static_version() -> str:
    """Empreinte des fichiers statiques : change à chaque déploiement -> plus de cache périmé."""
    import hashlib

    h = hashlib.sha1()
    for f in sorted((APP_DIR / "static").rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(str(f.stat().st_mtime_ns).encode())
    return h.hexdigest()[:10]


def _load_cached_state() -> dict | None:
    """État du jour en cache disque (évite 30 s de fetch à chaque lancement)."""
    try:
        if CACHE_FILE.exists():
            cached = json.loads(CACHE_FILE.read_text())
            from datetime import date as _date

            if cached.get("briefing", {}).get("date") == _date.today().isoformat():
                return cached
    except Exception:
        pass
    return None


def _save_cached_state(state: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass


def _fred_factors() -> dict[str, list[float]]:
    try:
        from ..data.fred_loader import load_fred_factors

        return {k: list(v[1]) for k, v in load_fred_factors().items()}
    except Exception:
        return {}


def _current_state() -> dict:
    """Construit l'état complet : données réelles (Yahoo) + briefing."""
    from ..data.real_market import load_agent_market_data

    factors = _fred_factors()
    council = build_fund(factors)
    merged, sources = load_agent_market_data()
    real = {tk: md for tk, md in merged.items() if sources.get(tk) == "yahoo"}
    briefing = council.meeting(merged)

    # Prix du jour pour le journal
    today_prices = {}
    for tk in briefing.proposed_allocation:
        md = merged.get(tk)
        if md and md.prices:
            today_prices[tk] = float(md.prices[-1])
    for tk in ("SPY", "BTC", "ETH", "GLD"):
        md = merged.get(tk)
        if md and md.prices:
            today_prices[tk] = float(md.prices[-1])

    if briefing.proposed_allocation:
        journal.record_briefing(briefing.proposed_allocation, today_prices)

    pnl = journal.compute_pnl(today_prices)
    from ..llm_briefing import enrich_briefing

    briefing_dict = enrich_briefing(briefing.to_dict())
    state = {
        "briefing": briefing_dict,
        "today_prices": today_prices,
        "pnl_history": pnl,
        "real_tickers": sorted(real.keys()),
        "data_sources": sources,
    }
    _save_cached_state(state)
    return state


def _get_state() -> dict:
    """Répond immédiatement : cache si dispo, sinon sync arrière-plan."""
    global LAST_BRIEFING
    with STATE_LOCK:
        if LAST_BRIEFING is not None:
            return LAST_BRIEFING
    cached = _load_cached_state()
    if cached is not None:
        with STATE_LOCK:
            if LAST_BRIEFING is None:
                LAST_BRIEFING = cached
                threading.Thread(target=_refresh, daemon=True).start()
            return LAST_BRIEFING
    # Aucun cache : première synchro en arrière-plan, on signale l'état
    threading.Thread(target=_refresh, daemon=True).start()
    return {"loading": True}


def _refresh() -> dict:
    global LAST_BRIEFING
    with STATE_LOCK:
        LAST_BRIEFING = _current_state()
        return LAST_BRIEFING


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, ctype: str = "text/plain", code: int = 200, nom: str | None = None) -> None:
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if nom:
            self.send_header("Content-Disposition", f'inline; filename="{nom}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _grql(self) -> None:
        """Langage de requête et API Excel : /api/grql?q=…&format=json|csv, /api/bdp?s=&f=, /api/bdh?s=&f=&debut=&fin=."""
        from urllib.parse import parse_qs, urlparse

        from ..query.grql import ErreurRequete, en_csv, executer

        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        route = u.path
        try:
            if route == "/api/grql":
                res = executer(qs.get("q", ""))
                if qs.get("format") == "csv":
                    self._send_text(en_csv(res), "text/csv", nom="grql.csv")
                else:
                    self._send_json(res)
                return
            s, f = qs.get("s", ""), qs.get("f", "px_last")
            if not s or "'" in s or "'" in f or len(f) > 200:
                raise ErreurRequete("paramètres s (titre) et f (champ) attendus")
            if route == "/api/bdp":  # une valeur, en texte brut : =WEBSERVICE(...) dans Excel
                res = executer(f"get({f}) for(['{s}'])")
                v = res["lignes"][0]["valeurs"][0] if res["lignes"] else None
                err = res["erreurs"].get(res["lignes"][0]["id"]) if res["lignes"] else None
                self._send_text("#N/A" if v is None else str(v), code=200 if v is not None or not err else 404)
            else:  # /api/bdh : série datée en CSV
                debut, fin = qs.get("debut", "-1y"), qs.get("fin", "0d")
                for x in (debut, fin):
                    if not (__import__("re").fullmatch(r"-?\d+(\.\d+)?[dwmy]|\d{4}-\d{2}-\d{2}", x)):
                        raise ErreurRequete("debut et fin : durée (-1y, -6m, 0d) ou date AAAA-MM-JJ")
                arg = lambda x: f"'{x}'" if "-" in x[1:] and len(x) == 10 else x
                res = executer(f"get({f}) for(['{s}']) with(dates=range({arg(debut)}, {arg(fin)}))")
                self._send_text(en_csv(res), "text/csv", nom=f"{s}_{f}.csv")
        except ErreurRequete as exc:
            if route == "/api/grql" and qs.get("format") != "csv":
                self._send_json({"error": str(exc)}, 400)
            else:
                self._send_text(f"#ERREUR {exc}", code=400)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": f"données indisponibles ({exc})"}, 502)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, rel: str) -> None:
        """Fichiers de l'interface (CSS, JS, icônes) — uniquement sous app/static/."""
        base = (APP_DIR / "static").resolve()
        target = (base / rel).resolve()
        if base not in target.parents or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # version dans l'URL (?v=…) : on peut garder en cache longtemps
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if "?v=" in self.path else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            self._send_html((APP_DIR / "index.html").read_text().replace("{{V}}", _static_version()))
        elif self.path.startswith("/static/"):
            self._send_static(self.path.split("?", 1)[0][len("/static/"):])
        elif self.path.split("?", 1)[0] in ("/api/grql", "/api/bdp", "/api/bdh"):
            self._grql()
        elif self.path.split("?", 1)[0] == "/api/xl":  # complément Excel : BDP, BDH, BDS, BQL façon Bloomberg
            from urllib.parse import parse_qs, urlparse

            from ..query.bloomberg import repondre

            qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            try:
                self._send_text(repondre(qs.get("fn", ""), qs))
            except Exception as exc:  # noqa: BLE001 — une cellule d'erreur plutôt qu'une page 500
                self._send_text(f"#N/A {type(exc).__name__}: {exc}"[:250])
        elif self.path == "/api/state":
            self._send_json(_get_state())
        elif self.path == "/api/agents":
            from ..agents_api import get_agents_roster

            self._send_json({"teams": get_agents_roster()})
        elif self.path == "/api/paper":
            from ..paper import run_paper_day
            try:
                self._send_json(run_paper_day())
            except Exception as exc:  # noqa: BLE001
                import traceback
                self._send_json({"error": str(exc), "trace": traceback.format_exc()}, 500)
        elif self.path == "/api/paper/refresh":
            from ..paper import run_paper_day

            self._send_json(run_paper_day(force=True))
        elif self.path == "/api/globe":
            from ..agents_api import get_globe_data

            self._send_json(get_globe_data())
        elif self.path == "/api/reports":
            from ..agents_api import get_manager_reports

            self._send_json({"reports": get_manager_reports()})
        elif self.path.startswith("/api/agent/"):
            from ..agents_api import get_agent_details

            from urllib.parse import unquote
            agent_id = unquote(self.path[len("/api/agent/") :].split("?")[0])
            try:
                self._send_json(get_agent_details(agent_id))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
        elif self.path.startswith("/api/manager/"):
            from ..agents_api import get_manager_details
            from urllib.parse import unquote
            mid = unquote(self.path[len("/api/manager/"):].split("?")[0])
            try:
                self._send_json(get_manager_details(mid))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
        elif self.path == "/api/hr":
            from ..agents_api import get_hr_overview
            self._send_json(get_hr_overview())
        elif self.path == "/api/critique":
            from ..critique_service import get_critique_state
            self._send_json(get_critique_state())
        elif self.path == "/api/news":
            from ..news import get_news
            self._send_json(get_news())
        elif self.path == "/api/strategies":
            from ..strategies_math import get_strategies_doc
            self._send_json(get_strategies_doc())
        elif self.path == "/api/risk":
            from ..risk_report import risk_report
            try:
                self._send_json(risk_report())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"calcul du risque impossible ({exc})"}, 500)
        elif self.path.startswith("/api/attribution"):
            from urllib.parse import parse_qs, urlparse
            from ..reporting import attribution
            q = parse_qs(urlparse(self.path).query)
            self._send_json(attribution((q.get("start") or [None])[0], (q.get("end") or [None])[0]))
        elif self.path.startswith("/report"):
            from ..reporting import monthly_report_html
            month = self.path.rstrip("/").split("/")[-1]
            month = month if len(month) == 7 and month[4] == "-" and month.replace("-", "").isdigit() else None
            self._send_html(monthly_report_html(month))
        elif self.path == "/api/health":
            from ..monitoring.health import health
            try:
                self._send_json(health())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
        elif self.path == "/api/tca":
            from ..brokers.alpaca import has_credentials
            if not has_credentials():
                self._send_json({"error": "Alpaca non configuré"}, 404)
            else:
                from ..monitoring.tca import tca
                try:
                    self._send_json(tca())
                except Exception as exc:  # noqa: BLE001
                    self._send_json({"error": str(exc)}, 502)
        elif self.path == "/api/notes":
            from ..research_note import list_notes
            self._send_json({"notes": list_notes()})
        elif self.path.startswith("/api/notes/"):
            from ..research_note import get_note
            n = get_note(self.path.rsplit("/", 1)[-1])
            self._send_json(n if n else {"error": "note introuvable"}, 200 if n else 404)
        elif self.path == "/api/campaigns":
            from ..research.campaigns_api import campaigns
            self._send_json(campaigns())
        elif self.path == "/api/projection":
            from ..projection import projection
            try:
                from ..paper import summary
                self._send_json(projection(summary()["equity"]))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
        elif self.path == "/api/system":
            from ..ops.watchdog import status as system_status
            try:
                self._send_json(system_status())
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
        elif self.path == "/api/tts/status":
            from ..tts import status as tts_status
            self._send_json(tts_status())
        elif self.path == "/api/live":
            from ..live.engine import status as live_status
            self._send_json(live_status())
        elif self.path == "/api/broker":
            from ..brokers.alpaca_mirror import status as broker_status
            self._send_json(broker_status())
        elif self.path == "/api/ops":
            st = APP_DIR.parent.parent / "data_cache" / "ops_status.json"
            self._send_json(json.loads(st.read_text()) if st.exists() else {"run_at": None, "ok": None, "alerts": []})
        elif self.path.startswith("/api/fn/"):
            from urllib.parse import parse_qs, urlparse
            from .. import market_functions as mf

            u = urlparse(self.path)
            name = u.path[len("/api/fn/"):]
            qs = parse_qs(u.query)
            sym = (qs.get("s") or [""])[0]
            handlers = {"gp": lambda: mf.gp(sym), "des": lambda: mf.des(sym), "fxc": mf.fxc, "wcrs": mf.wcrs, "ecst": mf.ecst,
                        "wei": mf.wei, "gc": mf.gc, "ovdv": lambda: mf.ovdv(sym or "SPY"),
                        "mc": lambda: mf.mc(sym or "SPY", qs), "ovml": lambda: mf.ovml(sym or "SPY", qs),
                        "gc3d": lambda: mf.gc3d((qs.get("y") or ["5"])[0]), "budg": mf.budg,
                        "mac": lambda: mf.mac(sym or "USD"), "ilbe": mf.ilbe,
                        "qlbs": lambda: mf.qlbs(qs), "gpg": lambda: mf.gpg(qs), "gpvs": lambda: mf.gpvs(sym or "SPY"),
                        "svol": lambda: mf.svol(sym or "SPY", qs), "beta": lambda: mf.beta(sym or "AAPL", qs),
                        "regm": lambda: mf.regm(sym or "SPY", qs), "tsa": lambda: mf.tsa(sym or "SPY", qs), "modl": mf.modl,
                        "fa": lambda: mf.fa(sym or "AAPL"), "eqs": lambda: mf.eqs(qs), "gew": mf.gew, "rob": mf.rob}
            if name not in handlers:
                self._send_json({"error": f"fonction inconnue : {name}"}, 404)
                return
            try:
                self._send_json(handlers[name]())
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"données indisponibles ({exc})"}, 502)
        elif self.path == "/api/market":
            from ..data.yahoo import market_snapshot
            self._send_json({"assets": market_snapshot()})
        elif self.path == "/api/research":
            report = APP_DIR.parent.parent / "data" / "research_report.json"
            if report.exists():
                self._send_json(json.loads(report.read_text()))
            else:
                self._send_json({"error": "rapport absent — lance python3 -m gambit_ridge.research.evaluate"}, 404)
        elif self.path == "/api/journal":
            entries = journal.load_entries()
            self._send_json({"entries": entries})
        elif self.path == "/api/refresh":
            self._send_json(_refresh())
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        if self.path == "/api/run":
            self._send_json(_refresh())
            return
        if self.path == "/api/critique/run":
            from ..critique_service import start_critiques_async
            self._send_json(start_critiques_async())
            return
        if self.path == "/api/notes/generate":
            from ..research_note import generate
            try:
                self._send_json(generate(force=True))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
            return
        if self.path == "/api/tts":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "JSON invalide"}, 400)
                return
            from ..tts import synthesize
            try:
                audio, info = synthesize(payload.get("text", ""), payload.get("target", ""), payload.get("label", ""),
                                         payload.get("previous_text", ""), payload.get("next_text", ""))
            except Exception as exc:  # noqa: BLE001 — le terminal revient aux voix système
                self._send_json({"error": str(exc)}, 502)
                return
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("X-Voice", info["voice"].encode("ascii", "ignore").decode())
            self.end_headers()
            self.wfile.write(audio)
            return
        if self.path == "/api/converse":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "JSON invalide"}, 400)
                return
            from ..conversation import converse

            try:
                self._send_json(converse(payload.get("target", ""), payload.get("question", ""), payload.get("history") or []))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
            return
        if self.path == "/api/ask":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "JSON invalide"}, 400)
                return
            from ..agents_api import ask_agent

            try:
                self._send_json(
                    ask_agent(payload.get("agent", ""), payload.get("question", ""))
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
            return
        if self.path == "/api/ask_manager":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "JSON invalide"}, 400)
                return
            from ..agents_api import ask_manager
            try:
                self._send_json(
                    ask_manager(payload.get("manager", ""), payload.get("question", ""))
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 404)
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
            return
        if self.path == "/api/backtest":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "JSON invalide"}, 400)
                return
            strategy = payload.get("strategy", "regime-momentum")
            data = payload.get("data", "synth")
            from ..backtest_service import AVAILABLE_DATA, AVAILABLE_STRATEGIES, run_backtest

            from ..backtest_service import FX_STRATEGIES
            crypto_strategies = ["crypto-momentum", "crypto-regime", "crypto-risk-managed"]
            equities_strategies = ["equities-momentum", "equities-regime", "equities-risk-managed"]
            allowed = (AVAILABLE_STRATEGIES + FX_STRATEGIES + crypto_strategies
                       + equities_strategies)
            if strategy not in allowed or data not in AVAILABLE_DATA:
                self._send_json({"error": "stratégie ou source inconnue"}, 400)
                return
            try:
                self._send_json(run_backtest(strategy, data))
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": str(exc)}, 500)
            return
        self.send_error(404)

    def log_message(self, *args):
        pass


def _prewarm() -> None:
    def _run() -> None:
        try:
            from ..paper import run_paper_day
            run_paper_day()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _tailnet_ip() -> str | None:
    """Adresse Tailscale (100.64.0.0/10) de ce Mac, si Tailscale est connecté."""
    import ipaddress
    import socket
    import subprocess

    for cli in ("/Applications/Tailscale.app/Contents/MacOS/Tailscale", "tailscale"):
        try:
            out = subprocess.run([cli, "ip", "-4"], capture_output=True, text=True, timeout=5)
            ip = out.stdout.strip().split("\n")[0]
            if out.returncode == 0 and ip and ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10"):
                return ip
        except Exception:
            continue
    return None


def _serve_tailnet(port: int) -> None:
    """Écoute en plus sur l'adresse Tailscale : joignable UNIQUEMENT depuis les appareils
    du réseau privé Tailscale (iPhone), jamais depuis Internet ni le Wi-Fi local.
    Réessaie toutes les minutes (Tailscale coupé, Mac qui sort de veille…)."""
    import time

    def loop():
        while True:
            ip = _tailnet_ip()
            if ip:
                try:
                    srv = ThreadingHTTPServer((ip, port), Handler)
                    print(f"Accès iPhone (Tailscale) : http://{ip}:{port}")
                    srv.serve_forever()  # ne revient que si l'interface disparaît
                except OSError:
                    pass
            time.sleep(60)

    threading.Thread(target=loop, daemon=True).start()


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    _prewarm()
    if os.environ.get("GRC_NO_TAILNET") != "1" and port == 8765:
        _serve_tailnet(port)
    print(f"Gambit Ridge Capital dashboard : http://{host}:{port}")
    print("Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    run()
