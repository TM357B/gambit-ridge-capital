"""Chargeur de config.yaml (sans dépendance PyYAML si absent).

Fallback minimal : lecture des paires clé: valeur par indentation,
suffisante pour les scalaires utilisés ici. Priorité : PyYaml > fallback.
"""
from __future__ import annotations

from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    """Charge la configuration en dictionnaire imbriqué."""
    p = path or CONFIG_PATH
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _parse_minimal(text)


def _parse_minimal(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        v = value.strip()
        if not v:
            child: dict = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = _scalar(v)
    return root


def _scalar(v: str):
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~"):
        return None
    try:
        return int(v.replace("_", ""))
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v.strip("'\"")


def get_backtest_config():
    """Construit un BacktestConfig depuis config.yaml (fallback : défauts)."""
    from .backtest.engine import BacktestConfig

    cfg = load_config().get("backtest", {})
    return BacktestConfig(
        initial_capital=float(cfg.get("initial_capital", 1_000_000)),
        commission_bps=float(cfg.get("commission_bps", 2.0)),
        slippage_bps=float(cfg.get("slippage_bps", 5.0)),
        periods_per_year=int(cfg.get("periods_per_year", 252)),
        risk_free_rate=float(cfg.get("risk_free_rate", 0.02)),
    )
