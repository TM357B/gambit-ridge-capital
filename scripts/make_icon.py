"""Génère mac/icon.icns depuis mac/icon.svg — sans dépendance.

Implémentation minimale : un .icns est un conteneur de PNG bruts
(ic07=128x128, ic08=256x256, ic09=512x512, ic10=1024x1024 / ic11/ic12/ic13).
On dessine le logo (monogramme GRC + courbe) en PNG RGBA via des
primitives maison (pas de PIL), en SVG on réutilise les mêmes formes.
Sortie : ic10 (512x512 pour Retina 1024) suffit pour macOS 11+.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "mac" / "icon.icns"

W = H = 512
BG = (10, 12, 18, 255)        # fond sombre du terminal
AMBER = (255, 153, 0, 255)
WHITE = (240, 240, 240, 255)
DIM = (70, 80, 100, 255)


def _px(x: int, y: int, buf: list, color, size=512) -> None:
    if 0 <= x < size and 0 <= y < size:
        i = (y * size + x) * 4
        buf[i:i + 4] = list(color)


def _disc(cx, cy, r, buf, color, size=512):
    for y in range(max(0, int(cy - r) - 1), min(size, int(cy + r) + 2)):
        for x in range(max(0, int(cx - r) - 1), min(size, int(cx + r) + 2)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                _px(x, y, buf, color, size)


def _ring(cx, cy, r, width, buf, color, size=512):
    for y in range(max(0, int(cy - r - width)), min(size, int(cy + r + width) + 1)):
        for x in range(max(0, int(cx - r - width)), min(size, int(cx + r + width) + 1)):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if (r - width / 2) ** 2 <= d2 <= (r + width / 2) ** 2:
                _px(x, y, buf, color, size)


def _line(x0, y0, x1, y1, width, buf, color, size=512):
    length = int(max(abs(x1 - x0), abs(y1 - y0)))
    for i in range(length + 1):
        t = i / max(length, 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        half = width / 2
        for dy in range(-int(half) - 1, int(half) + 2):
            for dx in range(-int(half) - 1, int(half) + 2):
                if dx * dx + dy * dy <= half * half:
                    _px(int(x) + dx, int(y) + dy, buf, color, size)


def _text(buf, size=512):
    """Monogramme GRC en pseudo-7-segments dessinés à la main."""
    c = AMBER
    # G
    _line(60, 140, 60, 280, 22, buf, c, size); _line(60, 140, 130, 140, 22, buf, c, size)
    _line(60, 210, 115, 210, 18, buf, c, size); _line(130, 210, 130, 280, 20, buf, c, size)
    _line(90, 280, 130, 280, 22, buf, c, size)
    # R
    _line(160, 140, 160, 280, 22, buf, c, size); _line(160, 140, 230, 140, 22, buf, c, size)
    _line(230, 140, 250, 160, 22, buf, c, size); _line(250, 160, 250, 190, 22, buf, c, size)
    _line(250, 190, 230, 210, 22, buf, c, size); _line(160, 210, 235, 210, 22, buf, c, size)
    _line(180, 210, 250, 280, 22, buf, c, size)
    # C
    _line(310, 150, 280, 180, 22, buf, c, size); _line(280, 180, 280, 240, 22, buf, c, size)
    _line(280, 240, 310, 270, 22, buf, c, size); _line(320, 140, 280, 140, 22, buf, c, size)
    _line(280, 280, 320, 280, 22, buf, c, size)
    _line(310, 140, 280, 140, 22, buf, c, size)


def render(size: int) -> bytes:
    """Rend le logo à `size`x`size` et renvoie les octets PNG."""
    buf = [0] * (size * size * 4)
    s = size / 512.0
    # fond : carré arrondi
    r = int(100 * s)
    for y in range(size):
        for x in range(size):
            in_x = r if y < r or y >= size - r else 0
            if x >= in_x and x < size - in_x:
                _px(x, y, buf, BG, size)
            elif (x < r and (r - x) ** 2 + (r - y if y < size / 2 else size - 1 - y - r) ** 2 <= r * r):
                _px(x, y, buf, BG, size)
    # coins arrondis corrects (4 quarts)
    for cy, cx, sx, sy in ((r, r, 1, 1), (r, size - r, -1, 1), (size - r, r, 1, -1), (size - r, size - r, -1, -1)):
        for y in range(int(cy - r), int(cy + r)):
            for x in range(int(cx - r), int(cx + r)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    _px(x, y, buf, BG, size)
    # courbe de performance
    pts = [(60, 330), (120, 318), (180, 322), (240, 300), (300, 310), (360, 280), (420, 288), (470, 250)]
    for i in range(len(pts) - 1):
        _line(pts[i][0] * s, pts[i][1] * s, pts[i + 1][0] * s, pts[i + 1][1] * s, 8 * s, buf, DIM, size)
    _disc(470 * s, 250 * s, 12 * s, buf, AMBER, size)
    _text(buf, size)
    return encode_png(buf, size)


def encode_png(rgba: list, size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b""
    for y in range(size):
        raw += b"\x00" + bytes(rgba[y * size * 4:(y + 1) * size * 4])
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def main() -> None:
    entries = []
    for code, size in ((b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)):
        png = render(size)
        entries.append(code + struct.pack(">I", len(png)) + png)
    body = b"".join(entries)
    payload = b"icns" + struct.pack(">I", 8 + len(body)) + body
    OUT.write_bytes(payload)
    print(f"OK {OUT} ({len(payload)} octets)")


if __name__ == "__main__":
    main()
