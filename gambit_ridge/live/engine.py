"""Moteur live : la stratégie de production exécutée et surveillée en continu.

Boucle permanente (service systemd gambit-live sur le serveur) :
- toutes les 15 s : prix en direct (Alpaca IEX / crypto), valeur du compte paper Alpaca,
  courbe intrajournalière, coupe-circuit ;
- toutes les 5 min : comparaison du compte aux CIBLES DU JOUR et rééquilibrage si une
  position a dérivé au-delà du filtre anti micro-trades.

Les cibles sont décidées une fois par séance sur les clôtures quotidiennes (ETF : clôture de
New York ; crypto : minuit UTC), exactement comme dans le backtest. Elles ne sont pas
recalculées sur les prix en cours de séance (voir daily_targets : bascule des signaux).

Heures de bourse : ETF uniquement pendant la séance New York (pas dans les 2 premières ni
les 5 dernières minutes : enchères) ; crypto 24 h/24, long seulement.
Garde-fous : coupe-circuit si la perte du jour dépasse MAX_DAY_LOSS ; plus d'ordre si les
prix ne sont plus frais ; plafond d'ordres par actif et de rotation par jour ; délai après refus.

Compte PAPER uniquement (garde-fou dans brokers/alpaca.py). Activation :
`python -m gambit_ridge.live.engine enable` ; la réplication quotidienne
(brokers/alpaca_mirror.py) s'efface alors pour ne pas piloter le compte à deux.
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..brokers.alpaca import AlpacaClient, AlpacaError
from . import feed

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "data_cache" / "broker.json"
STATE = ROOT / "data_cache" / "live_state.json"

MARK_EVERY = 15          # s : prix + valeur du compte
REBALANCE_EVERY = 300    # s : recalcul de la stratégie et ordres
CURVE_EVERY = 60         # s : un point de courbe intrajournalière
CURVE_KEEP = 7 * 24 * 60 # points conservés (~ une semaine à la minute)
MAX_DAY_LOSS = 0.03      # coupe-circuit : perte du jour en fraction du compte
STALE_ETF = 120          # s : prix ETF plus vieux pendant la séance = flux arrêté
STALE_CRYPTO = 300       # s : par actif ; au-delà, pas d'ordre sur cet actif
OPEN_DELAY = timedelta(minutes=2)
CLOSE_GUARD = timedelta(minutes=5)

# identiques au paper trading / backtest de sélection
BUFFER_REL = 0.25
BUFFER_ABS = 0.005
ORDER_PREFIX = "grl-"
MAX_DAY_TURNOVER = 0.60  # garde-fou : montant échangé dans la journée / compte ; au-delà, plus d'ordre
MAX_ORDERS_PER_ASSET = 3 # garde-fou : ordres par actif et par jour (un aller-retour est déjà anormal)
DUST_USD = 1.0           # position résiduelle sous ce montant : ignorée (trop petite pour un ordre)
REFUSAL_COOLDOWN = 3600  # s : après un refus, on ne représente pas le même actif avant ce délai
ORDERS_LOG = ROOT / "data_cache" / "live_orders.jsonl"  # journal permanent de tous les ordres


def _floor(x: float, decimals: int) -> float:
    """Arrondi vers le bas : on ne demande jamais plus que la quantité visée ou détenue."""
    f = 10 ** decimals
    return math.floor(x * f + 1e-9) / f


# ---------------------------------------------------------------- configuration
def enabled() -> bool:
    try:
        return bool(json.loads(CONFIG.read_text()).get("live", {}).get("enabled"))
    except Exception:
        return False


def set_enabled(on: bool) -> None:
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    cfg.setdefault("live", {})["enabled"] = on
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"curve": [], "orders": [], "events": []}


def _save_state(s: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, default=str))
    tmp.replace(STATE)


def _event(s: dict, msg: str) -> None:
    s.setdefault("events", []).append({"at": datetime.now().isoformat(timespec="seconds"), "msg": msg})
    s["events"] = s["events"][-200:]
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


# ---------------------------------------------------------------- stratégie live
class History:
    """Historique quotidien Yahoo (séances closes), rechargé quand une séance se clôt."""

    def __init__(self) -> None:
        self.data: dict[str, tuple[list[str], dict[str, np.ndarray]]] = {}
        self.tried: dict[str, float] = {}

    def get(self, kind: str):
        from ..data.yahoo import CRYPTO_UNIVERSE, YahooConnector, all_etf_symbols, complete_cutoff, load_aligned
        from ..research.production import _complete_bars

        symbols = all_etf_symbols() if kind == "etf" else list(CRYPTO_UNIVERSE)
        cut = complete_cutoff("SPY" if kind == "etf" else "BTC-USD")
        cur = self.data.get(kind)
        if cur is None:
            self.data[kind] = cur = _complete_bars(*load_aligned(symbols, refresh=False))
        # une séance vient de se clore : on retélécharge sans attendre l'expiration du cache (20 h),
        # au plus toutes les 30 minutes tant que la source n'a pas publié la clôture
        if cur[0][-1] < cut and time.time() - self.tried.get(kind, 0) > 1800:
            self.tried[kind] = time.time()
            try:
                self.data[kind] = _complete_bars(*load_aligned(symbols, refresh=True, connector=YahooConnector(max_age_hours=0.4)))
            except Exception:
                pass  # hors ligne : on garde les dernières clôtures connues
        return self.data[kind]


def daily_targets(hist: History) -> dict:
    """Poids cibles (fraction du compte) décidés sur les clôtures quotidiennes — comme le backtest.

    Les signaux ne sont PAS recalculés sur les prix en cours de séance : le TSMOM vaut +1 ou -1
    selon le signe du rendement sur un an, et basculait à chaque oscillation autour du seuil
    (semaine du 2026-10-05 : 77 allers-retours crypto, 1,9 fois le compte échangé, ~0,4 % de frais).
    Les prix en direct servent à valoriser, surveiller le risque et rééquilibrer la dérive.
    """
    from ..research.production import CRYPTO_SHARE, ETF_SHARE, crypto_sleeve, etf_sleeve
    from ..research.quality import check_sleeve

    out = {"weights": {}, "kind": {}, "signals": {}, "dates": {}, "notes": [], "blocked": []}
    for kind, builder, share in (("etf", etf_sleeve, ETF_SHARE), ("crypto", crypto_sleeve, CRYPTO_SHARE)):
        d, p = hist.get(kind)
        out["dates"][kind] = d[-1]
        issues, _ = check_sleeve(kind, d, p)
        if issues:
            out["blocked"].append(kind)
            out["notes"] += [f"{kind} gelée : {x}" for x in issues]
            continue
        res = builder(d, p)
        for tk, w in res["weights"].items():
            out["weights"][tk] = share * w
            out["kind"][tk] = kind
            out["signals"][tk] = res["detail"][tk]["signal"]
    return out


def paper_drift(positions: dict, live: dict[str, float]) -> float:
    """Rendement du portefeuille paper depuis son dernier enregistrement, aux prix du moment.
    Sert à comparer le paper et le compte Alpaca AU MÊME INSTANT : le journal paper n'est mis à
    jour qu'aux clôtures (et la crypto y entre avec un jour de retard), alors que le compte est
    valorisé en direct. Sans prix live fiable pour une ligne, elle est supposée inchangée."""
    total = 0.0
    for tk, pos in positions.items():
        last, px = pos.get("last_price"), live.get(tk)
        if not last or not px:
            continue
        r = px / last - 1.0
        if abs(r) < 0.25:  # au-delà : prix aberrant ou détachement, on n'en tient pas compte
            total += pos.get("weight", 0.0) * r
    return total


# ---------------------------------------------------------------- ordres
def plan_orders(weights: dict[str, float], kinds: dict[str, str], prices: dict[str, float | None],
                held: dict[str, float], equity: float, assets: dict[str, dict], can_trade: dict[str, bool],
                pending: set[str]) -> tuple[list[dict], list[str]]:
    """Ordres pour amener le compte vers la cible. Fonction pure (testée).

    weights : ticker (format Yahoo, BTC-USD) -> poids cible ; held : ticker -> quantité détenue ;
    assets : ticker -> {tradable, shortable, easy_to_borrow} ; can_trade : kind -> marché ouvert ;
    pending : tickers ayant déjà un ordre en attente.
    """
    orders, skipped = [], []
    for tk in sorted(set(weights) | set(held)):
        kind = kinds.get(tk, "crypto" if tk.endswith("-USD") else "etf")
        crypto = kind == "crypto"
        if not can_trade.get(kind):
            continue
        if tk in pending:
            skipped.append(f"{tk} : ordre déjà en attente")
            continue
        price = prices.get(tk)
        if not price:
            if held.get(tk) or abs(weights.get(tk, 0.0)) > BUFFER_ABS:
                skipped.append(f"{tk} : pas de prix live récent (ou absent chez Alpaca)")
            continue
        a = assets.get(tk) or {}
        tgt_w = weights.get(tk, 0.0)
        if tgt_w and not a.get("tradable"):
            skipped.append(f"{tk} : non négociable chez Alpaca")
            tgt_w = 0.0
        if tgt_w < 0 and (crypto or not (a.get("shortable") and a.get("easy_to_borrow"))):
            skipped.append(f"{tk} : vente à découvert impossible")
            tgt_w = 0.0
        cur = held.get(tk, 0.0)
        if cur and abs(cur) * price < DUST_USD and not tgt_w:
            continue  # poussière laissée par une vente précédente
        cur_w = cur * price / equity if equity > 0 else 0.0
        closing = tgt_w == 0.0 and cur != 0.0
        if not closing and abs(tgt_w - cur_w) <= max(BUFFER_REL * abs(tgt_w), BUFFER_ABS):
            continue
        tgt = _floor(tgt_w * equity / price, 9) if crypto else int(round(tgt_w * equity / price))
        note = ""
        if cur and tgt and (cur > 0) != (tgt > 0):
            tgt, note = 0.0, "changement de sens : solde d'abord"
        diff = tgt - cur
        if abs(diff) < (1e-9 if crypto else 1):
            continue
        close = tgt == 0 and cur != 0  # solde complet : passe par « fermer la position » (quantité exacte)
        if diff < 0 and cur > 0:       # vente d'une position longue : jamais plus que détenu
            qty = abs(cur) if close else min(_floor(-diff, 9 if crypto else 0), abs(cur))
        else:
            qty = _floor(abs(diff), 9) if crypto else abs(diff)
        if qty <= 0 or qty * price < DUST_USD:
            continue
        orders.append({"ticker": tk, "symbol": feed._alpaca_symbol(tk), "kind": kind,
                       "side": "buy" if diff > 0 else "sell", "qty": qty, "close": close,
                       "current": cur, "target": tgt, "target_weight": round(tgt_w, 4),
                       "price": price, "notional": round(qty * price, 2), "note": note})
    orders.sort(key=lambda o: o["side"] != "sell")  # ventes d'abord : libèrent du pouvoir d'achat
    return orders, skipped


# ---------------------------------------------------------------- boucle
class Engine:
    def __init__(self) -> None:
        self.c = AlpacaClient()
        self.hist = History()
        self.state = load_state()
        self.assets: dict[str, dict] = {}
        self.assets_day = ""
        self.clock: dict = {}
        self.clock_at = 0.0
        self.last_rebalance = 0.0
        self.last_curve = 0.0
        self.snaps: dict[str, dict] = {}
        self.closed_notified = ""
        self.targets: dict | None = None
        self.targets_key: tuple | None = None

    # -- marché
    def _clock(self) -> dict:
        if time.time() - self.clock_at > 60:
            self.clock = self.c.clock()
            self.clock_at = time.time()
        return self.clock

    def _etf_window(self, clock: dict) -> bool:
        if not clock.get("is_open"):
            return False
        from zoneinfo import ZoneInfo

        now = datetime.now(timezone.utc)
        nxt_close = datetime.fromisoformat(clock["next_close"]).astimezone(timezone.utc)
        ny_close = nxt_close.astimezone(ZoneInfo("America/New_York"))
        open_today = ny_close.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(timezone.utc)
        return open_today + OPEN_DELAY <= now <= nxt_close - CLOSE_GUARD

    def _asset_info(self, tickers: list[str]) -> dict[str, dict]:
        today = datetime.now().date().isoformat()
        if self.assets_day != today:
            self.assets, self.assets_day = {}, today
        for tk in tickers:
            if tk not in self.assets:
                try:
                    self.assets[tk] = self.c.asset(feed._alpaca_symbol(tk))
                except AlpacaError:
                    self.assets[tk] = {"tradable": False}
        return self.assets

    # -- un passage
    def mark(self) -> dict:
        from ..data.yahoo import CRYPTO_UNIVERSE, all_etf_symbols

        s = self.state
        clock = self._clock()
        acct = self.c.account()
        equity, last_eq = float(acct["equity"]), float(acct.get("last_equity") or acct["equity"])
        positions = self.c.positions()
        try:
            self.snaps = feed.snapshots("etf", all_etf_symbols()) | feed.snapshots("crypto", list(CRYPTO_UNIVERSE))
        except Exception as exc:
            _event(s, f"flux de prix indisponible : {str(exc)[:120]}")
        day_pnl = equity - last_eq
        now = datetime.now()
        s.update({
            "updated": now.isoformat(timespec="seconds"),
            "enabled": enabled(),
            "market_open": bool(clock.get("is_open")),
            "next_open": clock.get("next_open"), "next_close": clock.get("next_close"),
            "equity": equity, "last_equity": last_eq, "day_pnl": round(day_pnl, 2),
            "day_return": round(day_pnl / last_eq, 6) if last_eq else 0.0,
            "positions": [{"symbol": p["symbol"], "qty": float(p["qty"]), "price": float(p["current_price"]),
                           "value": float(p["market_value"]), "day_pnl": float(p.get("unrealized_intraday_pl") or 0),
                           "pnl": float(p.get("unrealized_pl") or 0)} for p in positions],
            "prices": {tk: {"price": v["price"], "at": v["at"]} for tk, v in self.snaps.items()},
        })
        if time.time() - self.last_curve >= CURVE_EVERY:
            s.setdefault("curve", []).append({"t": now.isoformat(timespec="seconds"), "equity": round(equity, 2),
                                              "open": bool(clock.get("is_open"))})
            s["curve"] = s["curve"][-CURVE_KEEP:]
            self.last_curve = time.time()
        self._daily_snapshot(equity, now)
        # coupe-circuit : perte du jour
        today = now.date().isoformat()
        if s.get("day_return", 0) <= -MAX_DAY_LOSS and s.get("halted") != today:
            s["halted"] = today
            msg = f"COUPE-CIRCUIT : perte du jour {s['day_return']:+.2%} (seuil -{MAX_DAY_LOSS:.0%}) — plus aucun ordre aujourd'hui"
            _event(s, msg)
            _phone("Gambit Ridge — coupe-circuit", msg, urgent=True)
        # résumé à la clôture
        if not clock.get("is_open") and s.get("was_open") and self.closed_notified != today:
            self.closed_notified = today
            _phone("Gambit Ridge — clôture", f"Compte paper : {equity:,.0f} $ · séance {day_pnl:+,.0f} $ ({s['day_return']:+.2%})")
        s["was_open"] = bool(clock.get("is_open"))
        return s

    def _daily_snapshot(self, equity: float, now: datetime) -> None:
        """Une ligne par jour : compte Alpaca, paper de référence, ordres et rotation du jour.
        Alimente le suivi live / paper du terminal (rafraîchi toutes les 10 minutes)."""
        if time.time() - getattr(self, "_snap_at", 0) < 600:
            return
        self._snap_at = time.time()
        s, today = self.state, now.date().isoformat()
        paper_equity = paper_close = None
        try:
            from ..paper import _load_journal

            j = _load_journal()
            hist = j.get("equity_history") or []
            paper_close = hist[-1]["equity"] if hist else j.get("initial_capital")
            paper_equity = round(paper_close * (1.0 + paper_drift(j.get("positions") or {}, {t: v["price"] for t, v in self.snaps.items()})), 2)
        except Exception:
            pass
        sent = [o for o in s.get("orders", []) if o.get("at", "")[:10] == today and o.get("status") == "envoyé"]
        # paper_equity = paper revalorisé aux prix du moment (même instant que le compte Alpaca) ;
        # paper_close = dernière valeur du journal (clôtures ; la crypto y entre avec un jour de retard)
        row = {"date": today, "alpaca_equity": round(equity, 2), "paper_equity": paper_equity, "paper_close": paper_close,
               "orders": len(sent), "refused": sum(1 for o in s.get("orders", []) if o.get("at", "")[:10] == today and o.get("status") == "refusé"),
               "notional": round(sum(o.get("notional") or 0 for o in sent), 2)}
        daily = [d for d in s.get("daily", []) if d["date"] != today] + [row]
        s["daily"] = sorted(daily, key=lambda d: d["date"])[-400:]

    def _fresh_price(self, tk: str) -> float | None:
        """Prix live du ticker s'il est assez récent, sinon None (pas d'ordre sur un prix périmé)."""
        snap = self.snaps.get(tk)
        if not snap:
            return None
        age = feed.age_seconds(snap["at"])
        limit = STALE_CRYPTO if tk.endswith("-USD") else STALE_ETF
        return snap["price"] if age is not None and age <= limit else None

    def _fresh(self, kind: str, tickers: list[str]) -> bool:
        """Le flux de la poche vit : au moins un prix récent."""
        return any(self._fresh_price(t) for t in tickers)

    def _targets(self) -> dict:
        """Cibles du jour : recalculées quand l'historique gagne une séance close (ou au démarrage)."""
        key = tuple(self.hist.get(k)[0][-1] for k in ("etf", "crypto"))
        if self.targets is None or key != self.targets_key:
            t0 = time.time()
            self.targets, self.targets_key = daily_targets(self.hist), key
            t = self.targets
            self.state["targets"] = {"at": datetime.now().isoformat(timespec="seconds"), "compute_s": round(time.time() - t0, 1),
                                     "dates": t["dates"], "weights": {k: round(v, 4) for k, v in t["weights"].items()},
                                     "signals": t["signals"], "notes": t["notes"][:30], "blocked": t["blocked"]}
            _event(self.state, f"cibles recalculées sur les clôtures ETF {t['dates'].get('etf')} / crypto {t['dates'].get('crypto')}")
        return self.targets

    def _day_guard(self, orders: list[dict], today: str) -> tuple[list[dict], list[str]]:
        """Garde-fous d'activité : plafond d'ordres par actif et de rotation par jour."""
        s, notes = self.state, []
        sent = [o for o in s.get("orders", []) if o.get("at", "")[:10] == today and o.get("status") == "envoyé"]
        count: dict[str, int] = {}
        for o in sent:
            count[o["ticker"]] = count.get(o["ticker"], 0) + 1
        turnover = sum(o.get("notional") or 0 for o in sent) / s["equity"] if s.get("equity") else 0.0
        s["day_turnover"] = round(turnover, 4)
        kept = []
        for o in orders:
            if count.get(o["ticker"], 0) >= MAX_ORDERS_PER_ASSET:
                notes.append(f"{o['ticker']} : déjà {count[o['ticker']]} ordres aujourd'hui (plafond {MAX_ORDERS_PER_ASSET})")
                continue
            if turnover + (o.get("notional") or 0) / s["equity"] > MAX_DAY_TURNOVER:
                notes.append(f"{o['ticker']} : plafond de rotation du jour atteint ({turnover:.0%} du compte)")
                continue
            turnover += (o.get("notional") or 0) / s["equity"]
            count[o["ticker"]] = count.get(o["ticker"], 0) + 1
            kept.append(o)
        if notes and s.get("guard_notified") != today:
            s["guard_notified"] = today
            _event(s, "GARDE-FOU d'activité : " + " ; ".join(notes[:4]))
            _phone("Gambit Ridge — activité anormale", "Ordres retenus : " + " ; ".join(notes[:4]), urgent=True)
        return kept, notes

    def rebalance(self) -> None:
        s = self.state
        clock = self._clock()
        etf_open = self._etf_window(clock)
        tgt = self._targets()
        today = datetime.now().date().isoformat()
        etf_tk = [t for t, k in tgt["kind"].items() if k == "etf"]
        crypto_tk = [t for t, k in tgt["kind"].items() if k == "crypto"]
        can = {"etf": etf_open and self._fresh("etf", etf_tk) and "etf" not in tgt["blocked"],
               "crypto": self._fresh("crypto", crypto_tk) and "crypto" not in tgt["blocked"]}
        why = []
        if not enabled():
            why.append("moteur en mode observation (non activé)")
        if s.get("halted") == today:
            why.append("coupe-circuit actif")
        if etf_open and not can["etf"]:
            why.append("ETF : prix pas frais ou poche gelée")
        s["trading"] = {"etf": can["etf"] and not why, "crypto": can["crypto"] and not why, "why": why}
        if why or not (can["etf"] or can["crypto"]):
            return
        held = {}
        for p in s.get("positions", []):
            sym = p["symbol"]
            tk = sym[:-3] + "-USD" if sym.endswith("USD") and len(sym) > 5 else sym
            held[tk] = p["qty"]
        prices = {tk: self._fresh_price(tk) for tk in set(tgt["weights"]) | set(held)}
        pending = set()
        for o in self.c.open_orders():
            sym = o["symbol"].replace("/", "")
            pending.add(sym[:-3] + "-USD" if sym.endswith("USD") and len(sym) > 5 else sym)
        orders, skipped = plan_orders(tgt["weights"], tgt["kind"], prices, held, s["equity"],
                                      self._asset_info(sorted(set(tgt["weights"]) | set(held))), can, pending)
        # un actif refusé n'est pas représenté toutes les 5 minutes : délai d'attente, puis nouvel essai
        cool = {tk: t for tk, t in (s.get("cooldown") or {}).items() if time.time() - t < REFUSAL_COOLDOWN}
        for o in [o for o in orders if o["ticker"] in cool]:
            skipped.append(f"{o['ticker']} : refusé récemment, nouvel essai dans {int((REFUSAL_COOLDOWN - (time.time() - cool[o['ticker']])) / 60) + 1} min")
        orders = [o for o in orders if o["ticker"] not in cool]
        orders, guard_notes = self._day_guard(orders, today)
        skipped += guard_notes
        s["skipped"] = skipped
        for o in orders:
            cid = f"{ORDER_PREFIX}{o['symbol'].replace('/', '')}-{o['side']}-{datetime.now():%y%m%d%H%M%S}"[:48]
            tif = "gtc" if o["kind"] == "crypto" else "day"
            try:
                if o.get("close"):
                    r = self.c.close_position(o["symbol"])
                else:
                    r = self.c.submit(o["symbol"], o["qty"], o["side"], tif, cid)
                o.update(status="envoyé", order_id=r.get("id"))
            except AlpacaError as exc:
                o.update(status="refusé", error=str(exc)[:300])
                cool[o["ticker"]] = time.time()
                _phone("Gambit Ridge — ordre refusé", f"{'Achat' if o['side'] == 'buy' else 'Vente'} {o['qty']} {o['symbol']} : {str(exc)[:160]}", urgent=True)
            o["at"] = datetime.now().isoformat(timespec="seconds")
            s.setdefault("orders", []).append(o)
            try:  # journal permanent (l'état ne garde que les derniers ordres)
                with ORDERS_LOG.open("a") as f:
                    f.write(json.dumps(o, ensure_ascii=False, default=str) + "\n")
            except OSError:
                pass
            _event(s, f"{o['status']} : {'achat' if o['side'] == 'buy' else 'vente'} {o['qty']} {o['symbol']} ~{o['notional']:,.0f} $"
                      + (f" ({o.get('error', '')[:140]})" if o["status"] == "refusé" else ""))
        s["cooldown"] = cool
        s["orders"] = s.get("orders", [])[-300:]

    def step(self) -> None:
        self.mark()
        if time.time() - self.last_rebalance >= REBALANCE_EVERY:
            self.last_rebalance = time.time()
            self.rebalance()
        _save_state(self.state)

    def run_forever(self) -> None:
        _event(self.state, f"démarrage du moteur live ({'ACTIF' if enabled() else 'observation'})")
        errors = 0
        while True:
            t = time.time()
            try:
                self.step()
                errors = 0
            except Exception as exc:  # réseau, API : on continue, on prévient si ça dure
                errors += 1
                _event(self.state, f"erreur : {str(exc)[:200]}")
                if errors == 1:
                    traceback.print_exc()
                if errors == 20:  # ~ 5 min d'échecs consécutifs
                    _phone("Gambit Ridge — moteur live en échec", str(exc)[:200], urgent=True)
                try:
                    _save_state(self.state)
                except Exception:
                    pass
            time.sleep(max(1.0, MARK_EVERY - (time.time() - t)))


def _phone(title: str, msg: str, urgent: bool = False) -> None:
    try:
        from ..ops.daily_run import notify_phone

        notify_phone(title, msg, urgent=urgent)
    except Exception:
        pass


def status() -> dict:
    s = load_state()
    s["enabled"] = enabled()
    s["curve"] = s.get("curve", [])[-1440:]
    s["daily"] = s.get("daily", [])[-120:]
    s["orders"] = s.get("orders", [])[-60:]
    s["events"] = s.get("events", [])[-40:]
    age = None
    if s.get("updated"):
        age = (datetime.now() - datetime.fromisoformat(s["updated"])).total_seconds()
    s["running"] = age is not None and age < 3 * MARK_EVERY + 30
    return s


def backfill(since: str = "2026-10-04") -> dict:
    """Reconstruit le journal permanent des ordres et les lignes quotidiennes d'activité à partir
    de l'historique Alpaca (ordres exécutés du moteur, préfixe « grl- »). Idempotent."""
    c = AlpacaClient()
    orders, after = [], f"{since}T00:00:00Z"
    while True:
        page = c._req("GET", "/v2/orders", {"status": "closed", "limit": 500, "after": after, "direction": "asc"})
        orders += page
        if len(page) < 500:
            break
        after = page[-1]["submitted_at"]
    known = set()
    if ORDERS_LOG.exists():
        known = {json.loads(line).get("order_id") for line in ORDERS_LOG.read_text().splitlines() if line.strip()}
    rows = []
    for o in orders:
        if o.get("status") != "filled" or o["id"] in known or not (o.get("client_order_id") or "").startswith(ORDER_PREFIX):
            continue
        qty, px = float(o["filled_qty"]), float(o["filled_avg_price"])
        crypto = "/" in o["symbol"]
        at = datetime.fromisoformat(o["filled_at"].replace("Z", "+00:00")[:19] + "+00:00").astimezone().replace(tzinfo=None)
        rows.append({"ticker": o["symbol"].replace("/", "-") if crypto else o["symbol"], "symbol": o["symbol"],
                     "kind": "crypto" if crypto else "etf", "side": o["side"], "qty": qty, "price": px,
                     "notional": round(qty * px, 2), "status": "envoyé", "order_id": o["id"],
                     "at": at.isoformat(timespec="seconds"), "note": "reconstitué depuis Alpaca"})
    rows.sort(key=lambda r: r["at"])
    if rows:
        ORDERS_LOG.parent.mkdir(exist_ok=True)
        old = ORDERS_LOG.read_text() if ORDERS_LOG.exists() else ""
        merged = sorted([json.loads(x) for x in old.splitlines() if x.strip()] + rows, key=lambda r: r["at"])
        ORDERS_LOG.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in merged))
    # lignes quotidiennes : compte Alpaca (historique du courtier) + activité du journal
    s = load_state()
    hist = c.portfolio_history("1M")
    from zoneinfo import ZoneInfo

    # horodatage Alpaca = fin de séance New York : daté en UTC, il tombe le lendemain
    ny = ZoneInfo("America/New_York")
    eq = {(datetime.fromtimestamp(t, ny) - timedelta(hours=12)).date().isoformat(): e for t, e in zip(hist["timestamp"], hist["equity"]) if e}
    try:
        from ..paper import _load_journal

        paper = {e["date"]: e["equity"] for e in _load_journal().get("equity_history", [])}
    except Exception:
        paper = {}
    log = [json.loads(x) for x in ORDERS_LOG.read_text().splitlines() if x.strip()] if ORDERS_LOG.exists() else []
    daily = {d["date"]: d for d in s.get("daily", [])}
    last_paper = None
    for day in sorted(set(eq) | {r["at"][:10] for r in log}):
        if day < since:
            continue
        last_paper = paper.get(day, last_paper)
        sent = [r for r in log if r["at"][:10] == day and r.get("status") == "envoyé"]
        base = daily.get(day, {"date": day, "refused": 0})
        past = day < datetime.now().date().isoformat()  # jour clos : la valeur de clôture du courtier fait foi
        base.update({"alpaca_equity": (eq.get(day) if past else None) or base.get("alpaca_equity") or eq.get(day),
                     "paper_equity": (last_paper if past else None) or base.get("paper_equity") or last_paper,
                     "orders": max(base.get("orders", 0), len(sent)),
                     "notional": max(base.get("notional", 0), round(sum(r["notional"] for r in sent), 2))})
        daily[day] = base
    s["daily"] = [daily[k] for k in sorted(daily)][-400:]
    _save_state(s)
    return {"ordres_ajoutes": len(rows), "jours": len(s["daily"])}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "enable":
        set_enabled(True)
        print("✓ Moteur live ACTIF : il passe les ordres en continu sur le compte paper Alpaca.")
        return 0
    if cmd == "disable":
        set_enabled(False)
        print("✓ Moteur live en observation : il calcule mais n'envoie plus d'ordres.")
        return 0
    if cmd == "backfill":
        print(json.dumps(backfill(argv[2] if len(argv) > 2 else "2026-10-04"), ensure_ascii=False))
        return 0
    if cmd == "once":
        e = Engine()
        e.step()
        print(json.dumps({k: e.state.get(k) for k in ("equity", "day_pnl", "market_open", "trading", "targets")},
                         ensure_ascii=False, indent=1, default=str)[:3000])
        return 0
    Engine().run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
