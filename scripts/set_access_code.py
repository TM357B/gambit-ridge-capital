"""Change le code d'accès de l'écran de verrouillage du terminal.

Usage : python3 scripts/set_access_code.py [dossier_du_projet ...]
Le code est saisi en masqué ; seul son hash djb2 est écrit dans
gambit_ridge/app/index.html. Rappel : ce verrou est cosmétique (vérifié dans
le navigateur, l'API locale n'est pas protégée) — il évite un regard indiscret,
pas une attaque.
"""
import getpass
import re
import sys
from pathlib import Path


def djb2(s: str) -> int:
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


def main() -> int:
    roots = [Path(p).expanduser() for p in sys.argv[1:]] or [Path(__file__).resolve().parent.parent]
    code = getpass.getpass("Nouveau code d'accès : ")
    if len(code) < 6 or code != getpass.getpass("Confirme le code : "):
        print("Codes différents ou trop courts (6 caractères minimum). Rien n'a été modifié.")
        return 1
    for root in roots:
        page = root / "gambit_ridge" / "app" / "static" / "js" / "01-core.js"
        text = page.read_text()
        new, n = re.subn(r"const GRC_PASS_HASH = \d+;", f"const GRC_PASS_HASH = {djb2(code)};", text, count=1)
        if n != 1:
            print(f"Introuvable dans {page}")
            return 1
        page.write_text(new)
        print(f"Code mis à jour : {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
