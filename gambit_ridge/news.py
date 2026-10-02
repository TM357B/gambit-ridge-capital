"""Actualités : RSS financiers gratuits + journal interne du fond.

Sources publiques sans clé. Timeout court, cache disque 1h.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

NEWS_CACHE = Path(__file__).resolve().parent.parent / "data_cache" / "news_cache.json"
CACHE_TTL = 3600  # 1h

RSS_SOURCES = [
    {"name": "Reuters Business", "url": "https://news.google.com/rss/search?q=markets+OR+stocks+OR+federal+reserve&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Crypto", "url": "https://news.google.com/rss/search?q=cryptocurrency+OR+bitcoin+OR+ethereum&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Macro/Hedge funds", "url": "https://news.google.com/rss/search?q=hedge+fund+OR+macroeconomics+OR+central+bank&hl=en-US&gl=US&ceid=US:en"},
]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _fetch_rss(source: dict, limit: int = 8) -> list[dict]:
    try:
        req = urllib.request.Request(source["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8, context=_CTX) as r:
            tree = ElementTree.fromstring(r.read())
        items = []
        for item in tree.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source_tag = (item.findtext("source") or "").strip()
            if title:
                items.append({
                    "title": re.sub(r"\s+-\s+[^-]+$", "", title)[:160],
                    "link": link,
                    "date": pub,
                    "category": source["name"],
                    "source": source_tag or source["name"],
                })
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


def get_news(force: bool = False) -> dict:
    """Récupère les news (cache 1h)."""
    if not force and NEWS_CACHE.exists():
        try:
            cached = json.loads(NEWS_CACHE.read_text())
            if time.time() - cached.get("ts", 0) < CACHE_TTL:
                return cached
        except Exception:
            pass
    all_items: list[dict] = []
    for src in RSS_SOURCES:
        all_items.extend(_fetch_rss(src))
    payload = {"ts": time.time(), "items": all_items[:24]}
    try:
        NEWS_CACHE.parent.mkdir(exist_ok=True, parents=True)
        NEWS_CACHE.write_text(json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass
    return payload
