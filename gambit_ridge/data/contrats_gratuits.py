"""Univers « contrats à terme » reconstruit avec des données GRATUITES (campagne 10).

Chaque marché est ramené à une série de rendements « en excès du monétaire » (ce que rapporte un contrat à terme,
le dépôt de garantie restant placé au taux sans risque), sur le calendrier de la Bourse de New York :

- Matières premières (24) : contrats continus Yahoo « =F ». Ces séries COLLENT l'échéance proche à la suivante :
  le jour du changement, le saut de prix n'est pas un gain (mesuré avant 2020 contre les ETF qui détiennent
  vraiment les contrats : pétrole +11 %/an, gaz +26 %/an, blé +15 %/an de rendement fictif). Correction : le jour
  de changement de chaque marché est repéré par une règle de calendrier choisie sur les seules données 2000-2019
  (`calage_changements`), et le rendement de ce jour-là est mis à zéro. Pics isolés (> 15 % aussitôt effacés) neutralisés.
  Garde-fous : règle retenue seulement si |t| ≥ 5 ; pour les 12 marchés qui ont un ETF témoin (USO, UNG, UGA, GLD, SLV,
  PPLT, PALL, CORN, WEAT, SOYB, CANE, CPER), la correction n'est gardée que si elle rapproche de l'ETF avant 2020, la
  dérive résiduelle d'avant 2020 est retirée, et DÈS LA CRÉATION DE L'ETF c'est l'ETF qui fait foi (rendement − taux
  sans risque + 0,6 % de frais). Les 11 autres (sans témoin) ont leur dérive mise à zéro : seul le timing compte.
- Taux américains (4) : contrats à 2, 5, 10 et 30 ans reconstruits depuis les rendements FRED (DGS2…DGS30) :
  rendement ≈ − duration × Δtaux + ½ convexité × Δtaux² + (taux − taux à 3 mois) / 252.
- Devises (FRED, cotations quotidiennes de midi) : contrat = variation du change + écart de taux à 3 mois
  (OCDE, mensuel, valeur du MOIS PRÉCÉDENT pour ne rien anticiper).
- Indices actions (13, Yahoo, indices de prix en monnaie locale) : contrat ≈ prix + 2 %/an de dividende −
  taux à 3 mois local (OCDE, mois précédent ; taux américain à défaut).

Limites assumées : pas de vraies séries de contrats (payantes) ; dividendes forfaitaires ; jour de changement
parfois décalé d'un jour ; pas de taux hors États-Unis (pas de séries quotidiennes gratuites).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from .fred_fx import _fetch_csv, _parse_daily, _parse_monthly
from .yahoo import YahooConnector

# symbole Yahoo -> (libellé, mois de contrat cotés)
MATIERES = {
    "CL=F": ("Pétrole WTI", range(1, 13)), "NG=F": ("Gaz naturel", range(1, 13)), "HO=F": ("Fioul", range(1, 13)),
    "RB=F": ("Essence", range(1, 13)), "GC=F": ("Or", (2, 4, 6, 8, 10, 12)), "SI=F": ("Argent", (3, 5, 7, 9, 12)),
    "HG=F": ("Cuivre", (3, 5, 7, 9, 12)), "PL=F": ("Platine", (1, 4, 7, 10)), "PA=F": ("Palladium", (3, 6, 9, 12)),
    "ZC=F": ("Maïs", (3, 5, 7, 9, 12)), "ZW=F": ("Blé tendre", (3, 5, 7, 9, 12)), "KE=F": ("Blé dur", (3, 5, 7, 9, 12)),
    "ZS=F": ("Soja", (1, 3, 5, 7, 8, 9, 11)), "ZM=F": ("Tourteau de soja", (1, 3, 5, 7, 8, 9, 10, 12)),
    "ZL=F": ("Huile de soja", (1, 3, 5, 7, 8, 9, 10, 12)), "KC=F": ("Café", (3, 5, 7, 9, 12)), "SB=F": ("Sucre", (3, 5, 7, 10)),
    "CC=F": ("Cacao", (3, 5, 7, 9, 12)), "CT=F": ("Coton", (3, 5, 7, 10, 12)), "OJ=F": ("Jus d'orange", (1, 3, 5, 7, 9, 11)),
    "LE=F": ("Bovins", (2, 4, 6, 8, 10, 12)), "HE=F": ("Porcs", (2, 4, 5, 6, 7, 8, 10, 12)),
    "GF=F": ("Bovins d'engraissement", (1, 3, 4, 5, 8, 9, 10, 11)),
}
TAUX = {"US2": ("DGS2", 2), "US5": ("DGS5", 5), "US10": ("DGS10", 10), "US30": ("DGS30", 30)}
# paire -> (série FRED, devise étrangère, +1 si FRED cote des dollars par devise, -1 si devises par dollar)
DEVISES = {
    "EURUSD": ("DEXUSEU", "EZ", 1), "GBPUSD": ("DEXUSUK", "GB", 1), "AUDUSD": ("DEXUSAL", "AU", 1), "NZDUSD": ("DEXUSNZ", "NZ", 1),
    "USDJPY": ("DEXJPUS", "JP", -1), "USDCHF": ("DEXSZUS", "CH", -1), "USDCAD": ("DEXCAUS", "CA", -1),
    "USDSEK": ("DEXSDUS", "SE", -1), "USDNOK": ("DEXNOUS", "NO", -1), "USDMXN": ("DEXMXUS", "MX", -1),
    "USDKRW": ("DEXKOUS", "KR", -1), "USDZAR": ("DEXSFUS", "ZA", -1),
}
# indice Yahoo -> (libellé, pays du taux local)
INDICES = {
    "^GSPC": ("S&P 500", "US"), "^NDX": ("Nasdaq 100", "US"), "^RUT": ("Russell 2000", "US"), "^GDAXI": ("DAX", "EZ"),
    "^FCHI": ("CAC 40", "EZ"), "^FTSE": ("FTSE 100", "GB"), "^SSMI": ("SMI", "CH"), "^N225": ("Nikkei 225", "JP"),
    "^HSI": ("Hang Seng", "US"), "^AXJO": ("ASX 200", "AU"), "^GSPTSE": ("TSX", "CA"), "^KS11": ("Kospi", "KR"),
    "^TWII": ("Taïex", "US"),
}
DIVIDENDE_FORFAIT = 0.02
CALAGE_FIN = "2019-12-31"
SEUIL_T = 5.0          # règle de calendrier retenue seulement si |t| >= 5 (le bruit seul dépasse rarement 4 sur 600 candidats)
FRAIS_ETF = 0.006      # frais annuels typiques des ETF de matières premières
ETF_TEMOINS = {"CL=F": "USO", "NG=F": "UNG", "RB=F": "UGA", "GC=F": "GLD", "SI=F": "SLV", "PL=F": "PPLT", "PA=F": "PALL",
               "ZC=F": "CORN", "ZW=F": "WEAT", "ZS=F": "SOYB", "SB=F": "CANE", "HG=F": "CPER"}
_TAUX_PAYS = {"US": "IR3TIB01USM156N", "EZ": "IR3TIB01EZM156N", "GB": "IR3TIB01GBM156N", "AU": "IR3TIB01AUM156N", "NZ": "IR3TIB01NZM156N", "JP": "IR3TIB01JPM156N",
              "CH": "IR3TIB01CHM156N", "CA": "IR3TIB01CAM156N", "SE": "IR3TIB01SEM156N", "NO": "IR3TIB01NOM156N",
              "MX": "IR3TIB01MXM156N", "KR": "IR3TIB01KRM156N", "ZA": "IR3TIB01ZAM156N"}


def classe(nom: str) -> str:
    if nom in MATIERES:
        return "Matières premières"
    if nom in TAUX:
        return "Taux"
    if nom in DEVISES:
        return "Devises"
    return "Actions"


# ---------------------------------------------------------------- jours de changement d'échéance

def _jours_ouvres_par_mois(dates: list[str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, d in enumerate(dates):
        out.setdefault(d[:7], []).append(i)
    return out


def _mois_decale(an: int, mois: int, decalage: int) -> str:
    m = an * 12 + (mois - 1) + decalage
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


def jours_de_changement(dates: list[str], mois_contrat, decalage: int, ancre: str, k: int) -> list[int]:
    """Indices des jours de changement : pour chaque mois de contrat, le jour coté situé à k séances de l'ancre
    (« debut », « j15 », « j25 » ou « fin ») du mois (contrat + decalage)."""
    par_mois = _jours_ouvres_par_mois(dates)
    out = []
    for an in range(int(dates[0][:4]), int(dates[-1][:4]) + 2):
        for mc in mois_contrat:
            idx = par_mois.get(_mois_decale(an, mc, decalage))
            if not idx:
                continue
            if ancre == "debut":
                a = idx[0]
            elif ancre == "fin":
                a = idx[-1]
            else:
                jour = 15 if ancre == "j15" else 25
                a = next((i for i in idx if int(dates[i][8:10]) >= jour), idx[-1])
            j = a + k
            if 0 < j < len(dates):
                out.append(j)
    return sorted(set(out))


def calage_changements(dates: list[str], r: np.ndarray, mois_contrat) -> dict:
    """Règle de calendrier dont les jours portent les rendements moyens les plus anormaux sur 2000-2019 (|t| max).
    Candidats : mois cotés ou les 12 mois ; décalage −2, −1, 0 ; ancre début / 15 / 25 / fin ; k de −12 à +12."""
    cal = np.array([d <= CALAGE_FIN for d in dates])
    rr = r[cal]
    dd = [d for d in dates if d <= CALAGE_FIN]
    sd = float(np.std(rr)) or 1.0
    meilleur = {"t": 0.0}
    for nom_mois, mois in (("cotés", tuple(mois_contrat)), ("tous", tuple(range(1, 13)))):
        for dec in (-2, -1, 0):
            for ancre in ("debut", "j15", "j25", "fin"):
                for k in range(-12, 13):
                    j = jours_de_changement(dd, mois, dec, ancre, k)
                    if len(j) < 20:
                        continue
                    t = float(np.mean(rr[j]) / (sd / np.sqrt(len(j))))
                    if abs(t) > abs(meilleur["t"]):
                        meilleur = {"t": t, "mois": nom_mois, "mois_liste": list(mois), "decalage": dec, "ancre": ancre, "k": k,
                                    "saut_moyen": float(np.mean(rr[j])), "n": len(j)}
    return meilleur


def _pics_isoles(r: np.ndarray, seuil: float = 0.15) -> np.ndarray:
    r = r.copy()
    for t in range(len(r) - 1):
        if abs(r[t]) > seuil and abs(r[t] + r[t + 1]) < 0.3 * abs(r[t]):
            r[t] = r[t + 1] = 0.0
    return r


# ---------------------------------------------------------------- séries

def _mensuel_lag(pays: str) -> dict[str, float]:
    """Taux à 3 mois OCDE (en %) ; la valeur utilisée en mois M est celle du mois M-1 (publiée à temps)."""
    try:
        m = _parse_monthly(_fetch_csv(_TAUX_PAYS[pays]))
    except Exception:
        return {}
    out = {}
    for ym, v in m.items():
        a, mo = int(ym[:4]), int(ym[5:7])
        out[_mois_decale(a, mo, 1)] = v
    return out


def _taux_sur(dates: list[str], pays: str, defaut: np.ndarray | None = None) -> np.ndarray | None:
    m = _mensuel_lag(pays)
    if not m:
        return defaut
    vals, last, mois_last = [], np.nan, None
    for d in dates:
        if d[:7] in m:
            last, mois_last = m[d[:7]], d[:7]
        perime = mois_last is None or (int(d[:4]) * 12 + int(d[5:7])) - (int(mois_last[:4]) * 12 + int(mois_last[5:7])) > 3
        vals.append(np.nan if perime else last)
    v = np.array(vals) / 100.0
    if defaut is not None:
        v = np.where(np.isnan(v), defaut, v)
    return v


def _sur_calendrier(maitre: list[str], dates: list[str], logr: np.ndarray) -> np.ndarray:
    """Somme des log-rendements propres à une série entre deux dates du calendrier maître (NaN avant le début)."""
    out = np.full(len(maitre), np.nan)
    pos = np.searchsorted(maitre, dates, side="left")  # jour maître qui reçoit le rendement
    acc = np.zeros(len(maitre))
    ok = pos < len(maitre)
    np.add.at(acc, pos[ok], logr[ok])
    premier = pos[0] if len(pos) else len(maitre)
    out[premier:] = acc[premier:]
    return out


def _duration_convexite(y: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Obligation au pair à coupon semestriel : duration modifiée et convexité."""
    y = np.maximum(y, 1e-4)
    c, f = y / 2, 2
    t = np.arange(1, n * f + 1)[None, :]
    disc = (1 + c[:, None]) ** (-t)
    flux = np.where(t == n * f, 1 + c[:, None], c[:, None]) * disc
    prix = flux.sum(axis=1)
    dmac = (flux * t / f).sum(axis=1) / prix
    dmod = dmac / (1 + c)
    conv = (flux * t * (t + 1) / f ** 2).sum(axis=1) / (prix * (1 + c) ** 2)
    return dmod, conv


def charger(depuis: str = "2000-01-03", rafraichir: bool = False) -> dict:
    """Retourne {dates, noms, rendements (T×N, excès du monétaire, NaN avant cotation), classes, portage (T×N, annuel),
    taux_us (T), changements (nom -> indices des jours de changement), calage (nom -> règle)}."""
    yc = YahooConnector()
    sp = yc.fetch("^GSPC", refresh=rafraichir)
    maitre = [d for d in sorted(sp) if d >= depuis]
    T = len(maitre)
    rf = _taux_sur(maitre, "US")
    rf = np.where(np.isnan(rf), np.nanmean(rf), rf)
    colonnes, portage, changements, calage = {}, {}, {}, {}

    # matières premières
    for s, (_, mois) in MATIERES.items():
        d = yc.fetch(s, refresh=rafraichir)
        ds = [k for k in sorted(d) if d[k] > 0 and k >= depuis]
        px = np.array([d[k] for k in ds])
        lr = np.concatenate([[0.0], np.diff(np.log(px))])
        lr = _pics_isoles(lr)
        regle = calage_changements(ds, lr, mois)
        jours = []
        if abs(regle["t"]) >= SEUIL_T:
            jours = jours_de_changement(ds, regle["mois_liste"], regle["decalage"], regle["ancre"], regle["k"])
        lr_corr = lr.copy()
        lr_corr[jours] = 0.0
        regle["applique"] = bool(jours)
        if s in ETF_TEMOINS:  # garde-fou : la correction doit rapprocher de l'ETF qui détient les contrats (avant 2020)
            cible = -float(np.nanmean(_taux_sur(ds, "US"))) + FRAIS_ETF
            e_brut = _ecart_etf(yc, ds, lr, ETF_TEMOINS[s]) - cible
            e_corr = _ecart_etf(yc, ds, lr_corr, ETF_TEMOINS[s]) - cible
            if jours and abs(e_corr) > abs(e_brut):
                lr_corr, jours, e_corr, regle["applique"] = lr, [], e_brut, False
            # dérive résiduelle mesurée avant 2020 retirée chaque jour
            lr_corr = lr_corr - e_corr / 252.0
            regle["derive_retiree"] = round(float(e_corr), 4)
        lr = lr_corr
        calage[s] = regle
        if s in ETF_TEMOINS:  # dès sa création, l'ETF qui détient vraiment les contrats fait foi (ramené à l'excès du monétaire)
            e = yc.fetch(ETF_TEMOINS[s], refresh=rafraichir)
            eds = [k for k in sorted(e) if k >= depuis and e[k] > 0]
            if eds:
                elr = np.concatenate([[0.0], np.diff(np.log([e[k] for k in eds]))])
                rf_e = _taux_sur(eds, "US")
                rf_e = np.where(np.isnan(rf_e), 0.0, rf_e)
                jours_e = np.concatenate([[1.0], np.diff([date.fromisoformat(k).toordinal() for k in eds])])
                elr = elr - (np.concatenate([[rf_e[0]], rf_e[:-1]]) - FRAIS_ETF) * jours_e / 365.0
                avant = [i for i, k in enumerate(ds) if k <= eds[0]]
                ds = [ds[i] for i in avant] + eds[1:]
                lr = np.concatenate([lr[avant], elr[1:]])
                jours = [j for j in jours if j in set(avant)]
                regle["etf_depuis"] = eds[0]
        colonnes[s] = _sur_calendrier(maitre, ds, lr)
        changements[s] = sorted(set(np.searchsorted(maitre, [ds[j] for j in jours]).tolist()) - {T})
        portage[s] = np.zeros(T)

    # taux américains
    for nom, (sid, n) in TAUX.items():
        obs = dict(_parse_daily(_fetch_csv(sid)))
        ds = [k for k in sorted(obs) if k >= depuis]
        y = np.array([obs[k] for k in ds]) / 100.0
        dmod, conv = _duration_convexite(y, n)
        rf_ds = _taux_sur(ds, "US")
        rf_ds = np.where(np.isnan(rf_ds), y, rf_ds)
        dy = np.concatenate([[0.0], np.diff(y)])
        jours = np.concatenate([[1.0], np.diff([date.fromisoformat(k).toordinal() for k in ds])])
        ret = -np.concatenate([[0.0], dmod[:-1]]) * dy + 0.5 * np.concatenate([[0.0], conv[:-1]]) * dy ** 2 \
            + (np.concatenate([[y[0]], y[:-1]]) - np.concatenate([[rf_ds[0]], rf_ds[:-1]])) * jours / 365.0
        colonnes[nom] = _sur_calendrier(maitre, ds, np.log1p(ret))
        k = np.searchsorted(ds, maitre, side="right") - 1  # dernier taux connu à chaque date maître
        portage[nom] = np.where(k >= 0, y[np.maximum(k, 0)] - rf, np.nan)
        changements[nom] = []

    # devises
    for paire, (sid, pays, sens) in DEVISES.items():
        r_et = _taux_sur(maitre, pays)
        if r_et is None:
            continue
        obs = dict(_parse_daily(_fetch_csv(sid)))
        ds = [k for k in sorted(obs) if k >= depuis and obs[k] > 0]
        px = np.array([obs[k] for k in ds])
        lr = np.concatenate([[0.0], np.diff(np.log(px))]) * sens  # + = la devise étrangère monte contre le dollar
        lr = _pics_isoles(lr)
        col = _sur_calendrier(maitre, ds, lr)
        ecart = np.nan_to_num(r_et - rf, nan=0.0)  # long devise étrangère : on reçoit son taux, on paie le dollar
        jours = np.concatenate([[1.0], np.diff([date.fromisoformat(k).toordinal() for k in maitre])])
        col = col + np.concatenate([[0.0], ecart[:-1]]) * jours / 365.0
        col[np.isnan(r_et)] = np.nan
        colonnes[paire] = col
        portage[paire] = np.where(np.isnan(r_et), np.nan, ecart)
        changements[paire] = []

    # indices actions
    for s, (_, pays) in INDICES.items():
        d = yc.fetch(s, refresh=rafraichir)
        ds = [k for k in sorted(d) if d[k] > 0 and k >= depuis]
        px = np.array([d[k] for k in ds])
        lr = _pics_isoles(np.concatenate([[0.0], np.diff(np.log(px))]))
        col = _sur_calendrier(maitre, ds, lr)
        r_loc = _taux_sur(maitre, pays, defaut=rf)
        jours = np.concatenate([[1.0], np.diff([date.fromisoformat(k).toordinal() for k in maitre])])
        col = col + (DIVIDENDE_FORFAIT - np.concatenate([[r_loc[0]], r_loc[:-1]])) * jours / 365.0
        colonnes[s] = col
        portage[s] = np.zeros(T)
        changements[s] = []

    noms = list(colonnes)
    # matières sans ETF témoin : dérive inconnue (séries collées) -> dérive mise à zéro, seul le timing compte
    for n in MATIERES:
        if n not in ETF_TEMOINS and n in colonnes:
            ok = ~np.isnan(colonnes[n])
            colonnes[n][ok] -= colonnes[n][ok].mean()
    R = np.column_stack([np.expm1(colonnes[n]) for n in noms])
    return {"dates": maitre, "noms": noms, "rendements": R, "classes": [classe(n) for n in noms],
            "portage": np.column_stack([portage[n] for n in noms]), "taux_us": rf, "changements": changements,
            "calage": calage}


def _ecart_etf(yc, ds: list[str], lr: np.ndarray, etf: str) -> float:
    """Écart de dérive annuel (série − ETF) sur la période de calage, jours communs seulement."""
    e = yc.fetch(etf)
    idx = [i for i in range(1, len(ds)) if ds[i] <= CALAGE_FIN and ds[i] in e and ds[i - 1] in e]
    if len(idx) < 250:
        return 0.0
    a = float(np.sum(lr[idx]))
    b = float(sum(np.log(e[ds[i]] / e[ds[i - 1]]) for i in idx))
    return (a - b) / (len(idx) / 252)


def sans_derive(univers: dict, classe_visee: str = "Matières premières") -> np.ndarray:
    """Test de robustesse : rendements de la classe visée privés de leur dérive moyenne (seul le TIMING reste)."""
    R = univers["rendements"].copy()
    for j, c in enumerate(univers["classes"]):
        if c == classe_visee:
            ok = ~np.isnan(R[:, j])
            lr = np.log1p(R[ok, j])
            R[ok, j] = np.expm1(lr - lr.mean())
    return R


def controle_etf(univers: dict) -> list[dict]:
    """Écart de dérive annuel (série corrigée − ETF qui détient les contrats), avant et après 2020.
    L'ETF place sa trésorerie au taux sans risque et prend des frais : écart attendu ≈ −taux + frais (≈ −3 à +1 %)."""
    paires = ETF_TEMOINS
    yc = YahooConnector()
    d = univers["dates"]
    out = []
    for s, e in paires.items():
        j = univers["noms"].index(s)
        etf = yc.fetch(e)
        lignes = {"marche": s, "etf": e}
        for nom, sel in (("avant_2020", lambda x: x <= CALAGE_FIN), ("depuis_2020", lambda x: x > CALAGE_FIN)):
            idx = [i for i, x in enumerate(d) if sel(x) and x in etf and i > 0 and d[i - 1] in etf and not np.isnan(univers["rendements"][i, j])]
            if len(idx) < 250:
                continue
            a = np.log1p(univers["rendements"][idx, j]).sum()
            b = sum(np.log(etf[d[i]] / etf[d[i - 1]]) for i in idx)
            lignes[nom] = round(float((a - b) / (len(idx) / 252)), 4)
        out.append(lignes)
    return out
