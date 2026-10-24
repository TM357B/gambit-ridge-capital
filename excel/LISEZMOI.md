# Complément Excel Gambit Ridge — BDP, BDH, BDS, BQL

Les mêmes formules que le complément Bloomberg, branchées sur le terminal Gambit Ridge
(`/api/xl`, `gambit_ridge/query/bloomberg.py`). Une feuille écrite pour Bloomberg fonctionne
telle quelle pour les champs disponibles gratuitement.

```
=BDP("AAPL US Equity"; "PX_LAST")
=BDH("SPY US Equity"; "PX_LAST"; "20240101"; ""; "Per=W"; "Dts=S")
=BDS("AAPL US Equity"; "DVD_HIST_ALL")
=BQL("members('MAG7')"; "px_last")        =BQL("get(px_last) for(['AAPL'])")
```

(`;` dans un Excel en français, `,` dans un Excel en anglais.) Les tableaux (BDH, BDS, BQL)
se déversent tout seuls dans Excel 365 / 2021.

## Champs

- **Cours** : PX_LAST, LAST_PRICE, PX_OPEN, PX_HIGH, PX_LOW, PX_CLOSE_1D, PX_VOLUME, HIGH_52WEEK, LOW_52WEEK
- **Variations (%)** : CHG_PCT_1D, _5D, _1M, _3M, _6M, _YTD, _1YR
- **Risque et technique** : VOLATILITY_10D … _260D (%), MOV_AVG_20D … _200D, RSI_9D/14D/30D, BETA_RAW_OVERRIDABLE (2 ans hebdo contre le S&P 500)
- **Société** : NAME, CRNCY, CUR_MKT_CAP (millions), EQY_DVD_YLD_12M (%)
- **Fondamentaux SEC (sociétés US)** : PE_RATIO, PX_TO_BOOK_RATIO, PX_TO_SALES_RATIO, CURRENT_EV_TO_T12M_EBIT, RETURN_COM_EQY, PROF_MARGIN, OPER_MARGIN, SALES_GROWTH, TOT_DEBT_TO_TOT_EQY, FREE_CASH_FLOW_YIELD (%), SALES_REV_TURN, NET_INCOME (millions)
- **BDH** : PX_LAST, PX_OPEN, PX_HIGH, PX_LOW, PX_VOLUME, TOT_RETURN_INDEX_GROSS_DVDS ; options Per=D/W/M/Q/S/Y, Dts=S/H, Sort=A/D, Dir=V/H, CshAdjNormal=Y ; dates AAAAMMJJ, date Excel, -1Y, -6M, -3W, -10D, -1CY
- **BDS** : DVD_HIST_ALL (colonnes Bloomberg, date ex et montant renseignés), OPT_CHAIN, INDX_MEMBERS (MAG7, ETF, CRYPTO) ; Headers=Y
- Tout autre champ de BDP est essayé comme expression du langage BQL du terminal : `=BDP("AAPL US Equity"; "sharpe(1y)")`.

Champs payants (consensus BEST_*, notations, CDS, BVAL, bid/ask…) : « #N/A Field Not Available »,
jamais un chiffre inventé. Composition du S&P 500 : non disponible gratuitement.

## Installation

- **Mac** : `bash excel/installer_mac.sh` (installe le script de transport — Excel pour Mac ne sait
  pas lire le web en VBA — et copie le complément), puis Excel › Outils › Compléments Excel › GambitRidge.
- **Windows** : Fichier › Options › Compléments › Compléments Excel › Parcourir › GambitRidge.xlam,
  puis la macro **GRC_Configurer** pour donner l'adresse du terminal sur le réseau Tailscale.
- Construire le .xlam à partir de la source : Excel › Outils › Macro › Visual Basic Editor ›
  Fichier › Importer `GambitRidge.bas`, puis Enregistrer sous › Complément Excel (.xlam).

Installation en une fois : ouvrir GambitRidge.xlam, activer les macros, lancer la macro **GRC_Installer**
(Outils › Macro › Macros… dans la barre de menus du Mac, ou par script).

Macros : **GRC_Actualiser** (vide le cache d'une minute et recalcule tout, comme Refresh),
**GRC_Configurer** (adresse du terminal, par défaut http://127.0.0.1:8765, le tunnel du Mac).

Le .xlam est fabriqué sans Excel par `python3 excel/construire_xlam.py` (projet VBA écrit selon
[MS-OVBA] / [MS-CFB], sans p-code : Excel recompile la source à l'ouverture). Relancer après
toute modification de GambitRidge.bas.
