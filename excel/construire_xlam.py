"""Construit excel/GambitRidge.xlam à partir de GambitRidge.bas, sans Excel.

Le projet VBA (xl/vbaProject.bin) est écrit selon les spécifications publiques de Microsoft :
[MS-OVBA] (flux dir, PROJECT, PROJECTwm, compression, chiffrement des champs CMG/DPB/GC) et
[MS-CFB] (fichier composé). Le flux _VBA_PROJECT ne contient pas de p-code (version 0xFFFF) :
Excel recompile le module depuis la source à l'ouverture, sous Windows comme sur Mac.

Usage : python3 excel/construire_xlam.py   ->   excel/GambitRidge.xlam
"""

from __future__ import annotations

import io
import random
import struct
import sys
import uuid
import zipfile
from pathlib import Path

ICI = Path(__file__).resolve().parent

# ---------------------------------------------------------------- [MS-OVBA] 2.4.1 compression


def _compresser_bloc(d: bytes) -> bytes:
    out = bytearray()
    i, n = 0, len(d)
    index: dict[bytes, list[int]] = {}
    while i < n:
        pos_drapeaux = len(out)
        out.append(0)
        drapeaux = 0
        for bit in range(8):
            if i >= n:
                break
            nb = 4
            while (1 << nb) < i:
                nb += 1
            longueur_max = (0xFFFF >> nb) + 3
            meilleur, decal = 0, 0
            for c in reversed(index.get(d[i:i + 3], [])[-64:]):
                if i - c > (1 << nb):
                    break
                l = 0
                while i + l < n and l < longueur_max and d[c + l] == d[i + l]:
                    l += 1
                if l > meilleur:
                    meilleur, decal = l, i - c
            if meilleur >= 3:
                out += struct.pack("<H", ((decal - 1) << (16 - nb)) | (meilleur - 3))
                drapeaux |= 1 << bit
                pas = meilleur
            else:
                out.append(d[i])
                pas = 1
            for k in range(i, i + pas):
                index.setdefault(d[k:k + 3], []).append(k)
            i += pas
        out[pos_drapeaux] = drapeaux
    return bytes(out)


def compresser(d: bytes) -> bytes:
    out = bytearray(b"\x01")
    for p in range(0, len(d), 4096):
        bloc = d[p:p + 4096]
        c = _compresser_bloc(bloc)
        if len(bloc) == 4096 and len(c) >= 4096:  # bloc brut : toujours 4096 octets
            out += struct.pack("<H", 0x3FFF) + bloc
        elif len(c) > 4096:
            raise ValueError("bloc final incompressible")
        else:
            out += struct.pack("<H", 0xB000 | (len(c) - 1)) + c
    return bytes(out)


def decompresser(d: bytes) -> bytes:
    """Vérification : décompression [MS-OVBA] 2.4.1.3.1."""
    assert d[0] == 1
    out = bytearray()
    p = 1
    while p < len(d):
        tete = struct.unpack("<H", d[p:p + 2])[0]
        taille = (tete & 0x0FFF) + 3
        debut_bloc = len(out)
        if not tete & 0x8000:
            out += d[p + 2:p + 2 + 4096]
            p += taille
            continue
        q, fin = p + 2, p + taille
        while q < fin:
            drapeaux = d[q]
            q += 1
            for bit in range(8):
                if q >= fin:
                    break
                if not drapeaux >> bit & 1:
                    out.append(d[q])
                    q += 1
                else:
                    jeton = struct.unpack("<H", d[q:q + 2])[0]
                    q += 2
                    nb = 4
                    while (1 << nb) < len(out) - debut_bloc:
                        nb += 1
                    decal = (jeton >> (16 - nb)) + 1
                    longueur = (jeton & (0xFFFF >> nb)) + 3
                    for _ in range(longueur):
                        out.append(out[-decal])
        p = fin
    return bytes(out)


# ---------------------------------------------------------------- [MS-OVBA] 2.4.3 chiffrement des champs du flux PROJECT


def chiffrer(donnees: bytes, clsid: str, graine: int) -> str:
    cle_projet = sum(clsid.encode("ascii")) & 0xFF
    version = 2
    v1 = graine ^ version
    v2 = graine ^ cle_projet
    out = bytearray([graine, v1, v2])
    ignores = (graine & 6) // 2
    unenc1, enc1, enc2 = cle_projet, v2, v1
    for _ in range(ignores):
        b = random.randrange(256)
        e = (b ^ ((enc2 + unenc1) & 0xFF)) & 0xFF
        out.append(e)
        enc2, enc1, unenc1 = enc1, e, b
    lng = struct.pack("<I", len(donnees))
    for b in lng + donnees:
        e = (b ^ ((enc2 + unenc1) & 0xFF)) & 0xFF
        out.append(e)
        enc2, enc1, unenc1 = enc1, e, b
    return out.hex().upper()


# ---------------------------------------------------------------- flux du projet VBA


def _rec(ident: int, data: bytes) -> bytes:
    return struct.pack("<HI", ident, len(data)) + data


DOC_TETE = ('Attribute VB_Name = "{nom}"\r\nAttribute VB_Base = "0{{{guid}}}"\r\nAttribute VB_GlobalNameSpace = False\r\n'
            'Attribute VB_Creatable = False\r\nAttribute VB_PredeclaredId = True\r\nAttribute VB_Exposed = True\r\n'
            'Attribute VB_TemplateDerived = False\r\nAttribute VB_Customizable = True\r\n')


def flux_vba(source_module: str, nom_module: str) -> dict[str, bytes]:
    modules = [("ThisWorkbook", 0x22, DOC_TETE.format(nom="ThisWorkbook", guid="00020819-0000-0000-C000-000000000046")),
               ("Feuil1", 0x22, DOC_TETE.format(nom="Feuil1", guid="00020820-0000-0000-C000-000000000046")),
               (nom_module, 0x21, source_module)]
    cp = 1252
    d = bytearray()
    d += _rec(0x0001, struct.pack("<I", 1))                   # SYSKIND : Win32 (Excel Mac l'accepte aussi)
    d += _rec(0x0002, struct.pack("<I", 0x409))               # LCID
    d += _rec(0x0014, struct.pack("<I", 0x409))               # LCIDINVOKE
    d += _rec(0x0003, struct.pack("<H", cp))                  # CODEPAGE
    d += _rec(0x0004, b"VBAProject")
    d += _rec(0x0005, b"") + _rec(0x0040, b"")                # DOCSTRING
    d += _rec(0x0006, b"") + _rec(0x003D, b"")                # HELPFILEPATH
    d += _rec(0x0007, struct.pack("<I", 0))                   # HELPCONTEXT
    d += _rec(0x0008, struct.pack("<I", 0))                   # LIBFLAGS
    d += struct.pack("<HIIH", 0x0009, 4, 1, 0)                # VERSION (Reserved=4, major, minor)
    d += _rec(0x000C, b"") + _rec(0x003C, b"")                # CONSTANTS
    # référence stdole (comme tout projet Excel ; VBA et Excel sont implicites)
    libid = b"*\\G{00020430-0000-0000-C000-000000000046}#2.0#0#C:\\Windows\\System32\\stdole2.tlb#OLE Automation"
    d += _rec(0x0016, b"stdole") + _rec(0x003E, "stdole".encode("utf-16-le"))
    d += _rec(0x000D, struct.pack("<I", len(libid)) + libid + struct.pack("<IH", 0, 0))
    d += struct.pack("<HIH", 0x000F, 2, len(modules))         # MODULES
    d += struct.pack("<HIH", 0x0013, 2, 0xFFFF)               # PROJECTCOOKIE
    for nom, genre, _ in modules:
        b, u = nom.encode("ascii"), nom.encode("utf-16-le")
        d += _rec(0x0019, b) + _rec(0x0047, u)
        d += _rec(0x001A, b) + _rec(0x0032, u)
        d += _rec(0x001C, b"") + _rec(0x0048, b"")
        d += _rec(0x0031, struct.pack("<I", 0))               # MODULEOFFSET : pas de p-code
        d += _rec(0x001E, struct.pack("<I", 0))
        d += struct.pack("<HIH", 0x002C, 2, 0xFFFF)
        d += struct.pack("<HI", genre, 0)                     # 0x21 standard, 0x22 document
        d += struct.pack("<HI", 0x002B, 0)
    d += struct.pack("<HI", 0x0010, 0)
    flux = {"VBA/_VBA_PROJECT": bytes([0xCC, 0x61, 0xFF, 0xFF, 0x00, 0x00, 0x00]), "VBA/dir": compresser(bytes(d))}
    for nom, _, src in modules:
        flux[f"VBA/{nom}"] = compresser(src.encode("cp1252"))
    clsid = "{" + str(uuid.uuid4()).upper() + "}"
    graine = random.randrange(256)
    projet = (f'ID="{clsid}"\r\nDocument=ThisWorkbook/&H00000000\r\nDocument=Feuil1/&H00000000\r\nModule={nom_module}\r\n'
              f'Name="VBAProject"\r\nHelpContextID="0"\r\nVersionCompatible32="393222000"\r\n'
              f'CMG="{chiffrer(struct.pack("<I", 0), clsid, graine)}"\r\nDPB="{chiffrer(bytes([0]), clsid, (graine + 1) & 0xFF)}"\r\n'
              f'GC="{chiffrer(bytes([0xFF]), clsid, (graine + 2) & 0xFF)}"\r\n\r\n[Host Extender Info]\r\n'
              '&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;&H00000000\r\n\r\n[Workspace]\r\n'
              f'ThisWorkbook=0, 0, 0, 0, C\r\nFeuil1=0, 0, 0, 0, C\r\n{nom_module}=0, 0, 0, 0, C\r\n')
    flux["PROJECT"] = projet.encode("cp1252")
    flux["PROJECTwm"] = b"".join(n.encode("ascii") + b"\x00" + n.encode("utf-16-le") + b"\x00\x00" for n, _, _ in modules) + b"\x00\x00"
    return flux


# ---------------------------------------------------------------- [MS-CFB] fichier composé (version 3, secteurs de 512 octets)

FIN, LIBRE, SECT_FAT, PAS_DE_FLUX = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD, 0xFFFFFFFF


def fichier_compose(flux: dict[str, bytes]) -> bytes:
    # arborescence : racine -> stockages / flux
    noeuds = [{"nom": "Root Entry", "type": 5, "enfants": [], "donnees": b""}]
    stockages = {"": 0}
    for chemin in sorted(flux):
        parent = ""
        morceaux = chemin.split("/")
        for k, m in enumerate(morceaux[:-1]):
            cle = "/".join(morceaux[:k + 1])
            if cle not in stockages:
                stockages[cle] = len(noeuds)
                noeuds.append({"nom": m, "type": 1, "enfants": [], "donnees": b""})
                noeuds[stockages[parent]]["enfants"].append(stockages[cle])
            parent = cle
        noeuds.append({"nom": morceaux[-1], "type": 2, "enfants": [], "donnees": flux[chemin]})
        noeuds[stockages[parent]]["enfants"].append(len(noeuds) - 1)

    ordre = lambda i: (len(noeuds[i]["nom"]), noeuds[i]["nom"].upper())
    for n in noeuds:
        n["gauche"] = n["droite"] = n["enfant"] = PAS_DE_FLUX

    def arbre(ids):  # arbre binaire de recherche équilibré (tous les noeuds noirs)
        if not ids:
            return PAS_DE_FLUX
        m = len(ids) // 2
        r = ids[m]
        noeuds[r]["gauche"], noeuds[r]["droite"] = arbre(ids[:m]), arbre(ids[m + 1:])
        return r

    for n in noeuds:
        if n["enfants"]:
            n["enfant"] = arbre(sorted(n["enfants"], key=ordre))

    # petits flux (< 4096 octets) dans le mini-flux, gros flux en secteurs normaux
    mini, minifat = bytearray(), []
    for n in noeuds[1:]:
        if n["type"] == 2 and len(n["donnees"]) < 4096:
            n["debut"] = len(mini) // 64 if n["donnees"] else FIN
            k = (len(n["donnees"]) + 63) // 64
            minifat += [len(minifat) + j + 1 for j in range(k)]
            if k:
                minifat[-1] = FIN
            mini += n["donnees"] + b"\x00" * (k * 64 - len(n["donnees"]))
    gros = [n for n in noeuds[1:] if n["type"] == 2 and len(n["donnees"]) >= 4096]
    sect = lambda x: (x + 511) // 512
    n_minifat = sect(len(minifat) * 4)
    n_rep = sect(len(noeuds) * 128)
    n_mini = sect(len(mini))
    n_gros = sum(sect(len(n["donnees"])) for n in gros)
    n_fat = 1
    while n_fat * 128 < n_fat + n_minifat + n_rep + n_mini + n_gros:
        n_fat += 1
    assert n_fat <= 109
    fat = [SECT_FAT] * n_fat
    def chaine(k):
        debut = len(fat)
        fat.extend(range(debut + 1, debut + k))
        fat.append(FIN)
        return debut
    debut_minifat = chaine(n_minifat) if n_minifat else FIN
    debut_rep = chaine(n_rep)
    debut_mini = chaine(n_mini) if n_mini else FIN
    for n in gros:
        n["debut"] = chaine(sect(len(n["donnees"])))
    fat += [LIBRE] * (n_fat * 128 - len(fat))
    noeuds[0]["debut"], noeuds[0]["donnees"] = debut_mini, bytes(mini)

    rep = bytearray()
    for n in noeuds:
        nom = n["nom"].encode("utf-16-le") + b"\x00\x00"
        taille = len(n["donnees"]) if n["type"] in (2, 5) else 0
        debut = n.get("debut", FIN) if n["type"] != 1 else 0
        rep += nom.ljust(64, b"\x00") + struct.pack("<HBB", len(nom), n["type"], 1)
        rep += struct.pack("<III", n["gauche"], n["droite"], n["enfant"]) + b"\x00" * 16 + struct.pack("<I", 0)
        rep += b"\x00" * 16 + struct.pack("<IQ", debut, taille)
    while len(rep) % 512:
        rep += b"\x00" * 64 + struct.pack("<HBB", 0, 0, 0) + struct.pack("<III", PAS_DE_FLUX, PAS_DE_FLUX, PAS_DE_FLUX) + b"\x00" * 36 + struct.pack("<IQ", 0, 0)

    def pad(b):
        return b + b"\x00" * ((-len(b)) % 512)

    tete = bytearray(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 16)
    tete += struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\x00" * 6
    tete += struct.pack("<IIIIIIIII", 0, n_fat, debut_rep, 0, 4096, debut_minifat, n_minifat, FIN, 0)
    difat = list(range(n_fat)) + [LIBRE] * (109 - n_fat)
    tete += struct.pack("<109I", *difat)
    corps = b"".join(struct.pack("<I", x) for x in fat)
    if n_minifat:
        mf = b"".join(struct.pack("<I", x) for x in minifat)
        corps += mf + b"\xFF" * (n_minifat * 512 - len(mf))
    corps += bytes(rep) + pad(bytes(mini))
    for n in gros:
        corps += pad(n["donnees"])
    return bytes(tete) + corps


# ---------------------------------------------------------------- classeur .xlam


XML = {
    "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.ms-excel.addin.macroEnabled.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
    "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
    "docProps/core.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Gambit Ridge — BDP, BDH, BDS, BQL</dc:title><dc:description>Fonctions façon Bloomberg branchées sur le terminal Gambit Ridge Capital.</dc:description><dc:creator>Gambit Ridge Capital</dc:creator></cp:coreProperties>',
    "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr codeName="ThisWorkbook"/><sheets><sheet name="Feuil1" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId3" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>',
    "xl/worksheets/sheet1.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr codeName="Feuil1"/><sheetData/></worksheet>',
    "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>',
}


def construire(bas: Path, sortie: Path, classeur: str = "addin") -> Path:
    texte = bas.read_bytes().decode("ascii").replace("\r\n", "\n").replace("\n", "\r\n")
    nom = next(l.split('"')[1] for l in texte.splitlines() if l.startswith("Attribute VB_Name"))
    vba = fichier_compose(flux_vba(texte, nom))
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for chemin, contenu in XML.items():
            if classeur != "addin" and chemin == "[Content_Types].xml":
                contenu = contenu.replace("application/vnd.ms-excel.addin.macroEnabled.main+xml", "application/vnd.ms-excel.sheet.macroEnabled.main+xml")
            z.writestr(chemin, contenu)
        z.writestr("xl/vbaProject.bin", vba)
    sortie.write_bytes(tampon.getvalue())
    return sortie


if __name__ == "__main__":
    xlam = construire(ICI / "GambitRidge.bas", ICI / "GambitRidge.xlam")
    print(f"{xlam} ({xlam.stat().st_size} octets)")
    if len(sys.argv) > 1 and sys.argv[1] == "--xlsm":
        print(construire(ICI / "GambitRidge.bas", ICI.parent / "data_cache" / "GambitRidge-essai.xlsm", "xlsm"))
