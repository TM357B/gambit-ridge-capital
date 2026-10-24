"""Extrait le produit « Gambit Ridge Terminal » (terminal + modèles, SANS le fonds) vers un dépôt séparé.

Le fonds (stratégie, moteur en direct, courtier, agents, campagnes, RH, journal paper) reste ici, privé.
Le produit reçoit les modules communs (fonctions de marché, options, modèles quantitatifs, langage BQL,
complément Excel, actions/macro, interface) renommés `gambit_terminal`, plus des adaptations listées
ci-dessous. Les fichiers propres au produit (serveur, page, cœur de l'interface, licence…) vivent dans
le dépôt produit et ne sont JAMAIS écrasés : relancer ce script resynchronise seulement les modules communs.

Usage : python3 scripts/extraire_terminal.py [DESTINATION]   (défaut : ~/gambit-ridge-terminal)
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
DEST = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "gambit-ridge-terminal"
PKG = "gambit_terminal"

COMMUNS = [
    "gambit_ridge/market_functions.py", "gambit_ridge/news.py",
    "gambit_ridge/query/__init__.py", "gambit_ridge/query/grql.py", "gambit_ridge/query/bloomberg.py",
    "gambit_ridge/options/__init__.py", "gambit_ridge/options/black_scholes.py", "gambit_ridge/options/vol_surface.py",
    "gambit_ridge/options/monte_carlo.py",
    "gambit_ridge/quant/__init__.py", "gambit_ridge/quant/bayes.py", "gambit_ridge/quant/gp.py", "gambit_ridge/quant/optim.py",
    "gambit_ridge/quant/particle.py", "gambit_ridge/quant/qlbs.py", "gambit_ridge/quant/timeseries.py",
    "gambit_ridge/equity/__init__.py", "gambit_ridge/equity/eqs.py", "gambit_ridge/equity/fa.py",
    "gambit_ridge/data/yahoo.py", "gambit_ridge/data/yahoo_ohlc.py", "gambit_ridge/data/yahoo_options.py",
    "gambit_ridge/data/fred.py", "gambit_ridge/data/edgar.py", "gambit_ridge/data/macro_monde.py",
    "gambit_ridge/research/signals.py", "gambit_ridge/models/regimes/hmm.py",
    "gambit_ridge/app/static/app.css", "gambit_ridge/app/static/manifest.webmanifest",
    "gambit_ridge/app/static/js/04-marche-graphiques.js", "gambit_ridge/app/static/js/06-fonctions.js",
    "gambit_ridge/app/static/js/09-quant-3d.js", "gambit_ridge/app/static/js/10-modeles-ml.js",
    "gambit_ridge/app/static/js/11-actions-macro.js", "gambit_ridge/app/static/js/12-requetes.js",
    "tests/test_vol_surface.py", "tests/test_monte_carlo.py", "tests/test_quant_models.py", "tests/test_edgar_macro.py",
    "tests/test_grql.py", "tests/test_bloomberg_excel.py",
    "excel/GambitRidge.bas", "excel/construire_xlam.py", "excel/installer_mac.sh", "excel/recuperer.applescript",
    "excel/LISEZMOI.md", "scripts/icones.py", "scripts/polices/Inter-variable-latin.woff2",
]
DOSSIERS = ["gambit_ridge/app/static/icons"]

# adaptations : (fichier, motif regex, remplacement) — un motif introuvable arrête l'extraction
ADAPTATIONS = [
    ("gambit_ridge/market_functions.py",
     r"\n    # position et signal dans le portefeuille papier\n    try:\n        from \.paper import _load_journal\n.*?        pass\n", "\n"),
    ("gambit_ridge/market_functions.py",
     r'    \("Stratégie de production", \[.*?(?=    \("Options et dérivés", \[)', ""),
    ("gambit_ridge/market_functions.py", r"\n\n# -+ ROB : robustesse\n.*\Z", "\n"),
    ("gambit_ridge/market_functions.py", r'        \("Projection à un an par bootstrap par blocs", "projection\.py", "—", "analyse", "PROJ"\),\n', ""),
    ("gambit_ridge/market_functions.py", r'"""Catalogue de tous les modèles du fonds,', '"""Catalogue de tous les modèles du terminal,'),
    ("gambit_ridge/market_functions.py",
     r'    import json\n    from pathlib import Path\n\n    racine = .*?            pass\n', ""),
    ("gambit_ridge/market_functions.py", r',\n            "lignes_resultats_campagnes": essais', ""),
    ("gambit_ridge/app/static/js/06-fonctions.js", r" \['ROB', 'Robustesse : hasard, PBO, stats', 'ROB'\],", ""),
    ("gambit_ridge/app/static/js/06-fonctions.js", r"\n  \['PORT', 'Portefeuille papier', 'PORT'\], \['RES', 'Recherche / backtests', 'RES'\],", ""),
    ("gambit_ridge/app/static/js/06-fonctions.js", r"'BQL', 'ROB', 'HELP'\]", "'BQL', 'HELP']"),
    ("gambit_ridge/app/static/js/06-fonctions.js", r"    else if \(S\.name === 'ROB'\) body = fnROB\(await fnFetch\('ROB'\)\);\n", ""),
    ("gambit_ridge/app/static/js/06-fonctions.js", r"  // CAMP : campagnes de recherche.*?scrollIntoView\(\{ behavior: 'smooth' \}\); \}, 2500\); \}\n", ""),
    ("gambit_ridge/app/static/js/06-fonctions.js", r"  const nav = \{ NOTE: 'notes'.*?RENDUS: 'reports' \};",
     "  const nav = { NH: 'news', N: 'news', NEWS: 'news', ACTU: 'news' };"),
    # bandeau des cours : pas de moteur du fonds pour remplir le cache, le produit va chercher les cours lui-même
    ("gambit_ridge/data/yahoo.py",
     r"        path = conn\._cache_path\(sym\)\n        if not path\.exists\(\):\n            continue\n        try:\n            data = json\.loads\(path\.read_text\(\)\)\n",
     "        try:\n            data = conn.fetch(sym)\n"),
    ("gambit_ridge/data/yahoo.py", r'"""Dernières clôtures \+ variations, lues UNIQUEMENT depuis le cache disque\n    \(aucun appel réseau : le paper trading rafraîchit le cache chaque jour\)\."""',
     '"""Dernières clôtures + variations (cache disque de 20 h, sinon téléchargement)."""'),
    # textes qui supposent un fonds
    ("gambit_ridge/app/static/js/06-fonctions.js", r"  if \(d\.fund\) \{\n.*?\n  \}\n", ""),
    ("gambit_ridge/app/static/js/12-requetes.js", r"Filtre : ETF du fonds peu volatils", "Filtre : ETF peu volatils"),
    ("gambit_ridge/app/static/js/10-modeles-ml.js", r"Catalogue des modèles du fonds", "Catalogue des modèles"),
    ("gambit_ridge/app/static/js/10-modeles-ml.js", r"noteBas\(`Production : ce qui pilote réellement le portefeuille\..*?l'accord du gérant\.`\)",
     "noteBas(`Analyse : modèles disponibles dans le terminal, chacun avec la commande qui l’affiche. Ils servent à étudier "
     "les marchés et à construire vos propres stratégies ; aucun ne constitue un conseil en investissement.`)"),
    ("gambit_ridge/market_functions.py", r"DES  : fiche d'un actif \(performances, risque, bêta, position du fonds\)",
     "DES  : fiche d'un actif (performances, risque, bêta)"),
    ("gambit_ridge/market_functions.py", r"# Catalogue des modèles du fonds", "# Catalogue des modèles du terminal"),
    # complément Excel : le terminal du produit tourne sur le poste de l'utilisateur (port 8780), pas derrière un tunnel
    ("excel/GambitRidge.bas", r"http://127\.0\.0\.1:8765, le tunnel du Mac", "http://127.0.0.1:8780, le terminal installe sur ce poste"),
    ("excel/GambitRidge.bas", r'"Adresse du terminal Gambit Ridge \(Mac : http://127\.0\.0\.1:8765 ; autre poste : son adresse Tailscale\)"',
     '"Adresse du terminal Gambit Ridge (par defaut http://127.0.0.1:8780)"'),
    ("excel/GambitRidge.bas", r'GetSetting\(APPLI, "Excel", "Serveur", "http://127\.0\.0\.1:8765"\)',
     'GetSetting(APPLI, "Excel", "Serveur", "http://127.0.0.1:8780")'),
    ("excel/GambitRidge.bas", r'Private Const APPLI As String = "GambitRidge"', 'Private Const APPLI As String = "GambitRidgeTerminal"'),
    ("excel/LISEZMOI.md", r"\n  puis la macro \*\*GRC_Configurer\*\* pour donner l'adresse du terminal sur le réseau Tailscale\.",
     " Le terminal doit être lancé sur le même poste."),
    ("excel/LISEZMOI.md", r"http://127\.0\.0\.1:8765, le tunnel du Mac", "http://127.0.0.1:8780, le terminal lancé sur ce poste"),
    ("gambit_ridge/app/static/js/12-requetes.js", r"noteBas\(`L’adresse \$\{esc\(base\)\} est celle du terminal.*?portefeuille\.`\)",
     "noteBas(`L’adresse ${esc(base)} est celle du terminal lancé sur cet ordinateur : Excel doit tourner sur le même poste. "
     "Le terminal n’est jamais exposé sur Internet, donc Google Sheets (qui interroge depuis les serveurs de Google) ne peut pas "
     "l’atteindre. Lecture seule : aucune requête n’envoie d’ordre.`)"),
]
# fichiers propres au produit : créés une fois s'ils manquent, jamais écrasés ensuite
PROPRES_VIDES = [f"{PKG}/__init__.py", f"{PKG}/data/__init__.py", f"{PKG}/research/__init__.py", f"{PKG}/models/__init__.py",
                 "tests/__init__.py"]
PROPRES = {f"{PKG}/models/regimes/__init__.py": "from .hmm import GaussianHMM  # noqa: F401\n"}
TEXTE = {".py", ".js", ".css", ".md", ".sh", ".bas", ".applescript", ".webmanifest", ".json", ".html"}


def cible(rel: str) -> Path:
    return DEST / rel.replace("gambit_ridge/", f"{PKG}/", 1)


def main() -> int:
    textes = {}
    for rel in COMMUNS:
        p = SRC / rel
        if not p.exists():
            raise SystemExit(f"introuvable dans le fonds : {rel}")
        textes[rel] = p.read_text() if p.suffix in TEXTE else None
    for rel, motif, rempl in ADAPTATIONS:
        nouveau, n = re.subn(motif, rempl, textes[rel], count=1, flags=re.S)
        if n != 1:
            raise SystemExit(f"adaptation introuvable dans {rel} : {motif[:60]}…  (le fonds a changé : mettre à jour ADAPTATIONS)")
        textes[rel] = nouveau
    for rel in COMMUNS:
        dst = cible(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if textes[rel] is None:
            shutil.copyfile(SRC / rel, dst)
        else:
            dst.write_text(textes[rel].replace("gambit_ridge", PKG))
    for rel in DOSSIERS:
        dst = cible(rel)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(SRC / rel, dst, ignore=shutil.ignore_patterns("._*", ".DS_Store"))
    for rel in PROPRES_VIDES:
        p = DEST / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")
    for rel, contenu in PROPRES.items():
        p = DEST / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(contenu)
    for p in DEST.rglob("._*"):
        p.unlink()
    fuite = [str(p.relative_to(DEST)) for p in DEST.rglob("*") if p.is_file() and p.suffix in TEXTE
             and ".venv" not in p.parts and p.name != "test_produit.py"
             and re.search(r"paper_journal|alpaca|research_campaign|staff\.json|_load_journal", p.read_text(errors="ignore"))]
    if fuite:
        raise SystemExit(f"référence au fonds restée dans le produit : {fuite}")
    print(f"✓ {len(COMMUNS)} fichiers communs extraits vers {DEST} ({len(ADAPTATIONS)} adaptations, aucune référence au fonds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
