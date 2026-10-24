"""Icônes des applis TBCD, style Zeno : grande lettre claire très grasse + point de couleur, sur fond sombre.

Par défaut (sans argument) : Gambit Ridge « G. », palette Ardoise →
- gambit_ridge/app/static/icons/icon-{180,192,512}.png : carré plein (iOS arrondit lui-même les coins)
- mac/icon.icns (+ mac/icon.svg) : carré arrondi avec marge, au gabarit des icônes macOS 11+

Autre appli : python3 scripts/icones.py --lettre T --point "#E8743B" --fond "#0B0B0B" --sortie DOSSIER
→ DOSSIER/icone.png (1024, gabarit Mac), icone.icns, icone.ico, icone-pleine-512.png.

Police : Inter (licence OFL), variable, graisse 900 — scripts/polices/Inter-variable-latin.woff2.
Nécessite Pillow (python3 système) et iconutil (macOS).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).resolve().parent.parent
POLICE = RACINE / "scripts" / "polices" / "Inter-variable-latin.woff2"
GRAISSE = 900
SUR = 4  # sur-échantillonnage pour l'anticrénelage
ARDOISE = {"lettre": "G", "fond": "#16161A", "bord": "#2C2C33", "texte": "#EEEBE4", "point": "#E3B65C"}


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _police(taille: float) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(POLICE), round(taille))
    f.set_variation_by_axes([GRAISSE])
    return f


def _lettre_point(d: ImageDraw.ImageDraw, cx: float, cy: float, cote: float, s: dict) -> None:
    """Lettre + point centrés en (cx, cy), aux proportions mesurées sur l'icône de l'appli Zeno (24/10) :
    lettre 38,3 % du côté du carré, point 12,1 %, écart 4,7 %, bas du point 2,15 % au-dessus de la ligne de base."""
    essai = _police(cote * 0.5)
    _, y0, _, y1 = d.textbbox((0, 0), s["lettre"], font=essai)
    f = _police(cote * 0.5 * (0.383 * cote) / (y1 - y0))
    x0, y0, x1, y1 = d.textbbox((0, 0), s["lettre"], font=f)
    h = y1 - y0
    r = 0.0605 * cote
    ecart = 0.047 * cote
    largeur = (x1 - x0) + ecart + 2 * r
    gauche = cx - largeur / 2
    d.text((gauche - x0, cy - h / 2 - y0), s["lettre"], font=f, fill=_rgb(s["texte"]))
    px, py = gauche + (x1 - x0) + ecart + r, cy + h / 2 - 0.0215 * cote - r
    d.ellipse([px - r, py - r, px + r, py + r], fill=_rgb(s["point"]))


def icone_pleine(taille: int, s: dict = ARDOISE) -> Image.Image:
    T = taille * SUR
    im = Image.new("RGB", (T, T), _rgb(s["fond"]))
    _lettre_point(ImageDraw.Draw(im), T / 2, T / 2, T, s)
    return im.resize((taille, taille), Image.LANCZOS)


def icone_mac(taille: int, s: dict = ARDOISE) -> Image.Image:
    """Même format que l'icône de Zeno (carré plein, sans marge) : macOS arrondit les coins dans le Dock, et toutes
    les applis TBCD ont exactement la même taille dans le Dock comme sur le Bureau (demande de Tom, 24/10)."""
    return icone_pleine(taille, s).convert("RGBA")


def icns(s: dict, cible: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jeu = Path(tmp) / "icon.iconset"
        jeu.mkdir()
        for base in (16, 32, 128, 256, 512):
            icone_mac(base, s).save(jeu / f"icon_{base}x{base}.png")
            icone_mac(base * 2, s).save(jeu / f"icon_{base}x{base}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(Path(tmp) / "icon.icns")], check=True)
        shutil.copyfile(Path(tmp) / "icon.icns", cible)


def gambit_ridge() -> None:
    web = RACINE / "gambit_ridge" / "app" / "static" / "icons"
    for n in (180, 192, 512):
        icone_pleine(n).save(web / f"icon-{n}.png", optimize=True)
    icns(ARDOISE, RACINE / "mac" / "icon.icns")
    (RACINE / "mac" / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><rect x="100" y="100" width="824" height="824" rx="185" '
        'fill="#16161A" stroke="#2C2C33" stroke-width="4"/><text x="470" y="672" text-anchor="middle" font-family="Inter, Helvetica, sans-serif" '
        'font-weight="900" font-size="590" fill="#EEEBE4">G</text><circle cx="738" cy="626" r="64" fill="#E3B65C"/></svg>\n')
    print("icônes écrites : static/icons/icon-180/192/512.png, mac/icon.icns, mac/icon.svg")


def autre_appli(a: argparse.Namespace) -> None:
    s = {"lettre": a.lettre, "fond": a.fond, "bord": a.bord, "texte": a.texte, "point": a.point}
    out = Path(a.sortie)
    out.mkdir(parents=True, exist_ok=True)
    icone_mac(1024, s).save(out / "icone.png")
    icone_pleine(512, s).save(out / "icone-pleine-512.png")
    icns(s, out / "icone.icns")
    icone_mac(256, s).save(out / "icone.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"icônes écrites dans {out} : icone.png, icone.icns, icone.ico, icone-pleine-512.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lettre")
    ap.add_argument("--point", default="#E8743B")
    ap.add_argument("--fond", default="#0B0B0B")
    ap.add_argument("--bord", default="#262626")
    ap.add_argument("--texte", default="#F2F2F2")
    ap.add_argument("--sortie")
    a = ap.parse_args()
    autre_appli(a) if a.lettre else gambit_ridge()
