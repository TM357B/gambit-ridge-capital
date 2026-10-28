/* Gambit Ridge Capital — terminal : 15-navigation.js (scripts classiques, globals partagés, chargés dans l'ordre)
   Aide à la navigation façon clavier Bloomberg (guide pratique de Tom) :
   - registre des fonctions intégrées (descriptions pour HELP, l'autocomplétion et les menus) ;
   - touches : Échap = CANCEL, F1 = HELP (deux appuis = aide de l'aide), F2-F12 = touches jaunes, Entrée = <GO>,
     Page préc./suiv. = PAGE BACK/FWD, Origine = MENU, ⌫ / Alt+← = retour, / ou Ctrl/Cmd+K = barre de commande,
     Alt+K ou ? = carte du clavier, Alt+P = PANEL (écran suivant) ;
   - autocomplétion de la barre de commande, historique des commandes (flèches), historique des écrans (BACK),
     fil d'Ariane, menus de marché et menus d'instrument numérotés (« chiffre + <GO> »). */

/* ============ REGISTRE : FONCTIONS INTÉGRÉES ============ */
// [code, catégorie, s'applique au titre actif, description, secteurs, alias]
const GRC_DESCRIPTIONS = [
  ['GP', 'Titres', true, 'Graphique du cours (séances closes), moyennes 50 et 200 jours, échelle log, périodes 1M à MAX.', ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY', 'CORP', 'GOVT']],
  ['DES', 'Titres', true, 'Fiche d’identité : nom, type, place, devise, performances et volatilité. Le contrôle à faire avant toute analyse.', ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY']],
  ['FA', 'Titres', true, 'Comptes de la société publiés à la SEC (EDGAR, XBRL) : résultat, bilan, flux, ratios, TTM. Actions US seulement.', ['EQUITY']],
  ['BETA', 'Titres', true, 'Bêta bayésien séquentiel contre le marché, avec son incertitude.', ['EQUITY']],
  ['EQS', 'Actions', false, 'Screener d’actions : univers, critères explicites (taille, ratios, croissance), résultats triables.', ['EQUITY']],
  ['WEI', 'Marchés', false, 'Indices boursiers mondiaux par région : niveau, variations 1 j à 1 an. Clic = graphique.', ['EQUITY', 'INDEX']],
  ['GEW', 'Économie', false, 'Économie mondiale : croissance, inflation, dette, taux par pays (FMI, BRI, OCDE).', ['GOVT']],
  ['ECST', 'Économie', false, 'Statistiques économiques US (FRED) : activité, emploi, prix, taux et conditions financières.', ['GOVT', 'M-MKT', 'CORP']],
  ['ILBE', 'Taux', false, 'Points morts d’inflation US (inflation anticipée par le marché, FRED).', ['GOVT']],
  ['BUDG', 'Économie', false, 'Budget fédéral américain : recettes, dépenses, solde (FRED).', ['GOVT']],
  ['GC', 'Taux', false, 'Courbe des taux du Trésor américain : aujourd’hui, il y a 1 mois et 1 an, pentes.', ['GOVT', 'M-MKT', 'MTGE']],
  ['GC3D', 'Taux', false, 'Courbe des taux US en 3D dans le temps, et ACP niveau / pente / courbure.', ['GOVT']],
  ['FXC', 'Devises', false, 'Matrice des taux de change croisés. Vérifier devise de base et de contrepartie.', ['CRNCY']],
  ['WCRS', 'Devises', false, 'Classement des devises par performance sur plusieurs horizons.', ['CRNCY']],
  ['MAC', 'Devises', false, 'Indice Big Mac (The Economist) : sur/sous-évaluation des devises. WCRS MAC <GO>.', ['CRNCY']],
  ['OVDV', 'Dérivés', true, 'Surface de volatilité implicite 3D (options US cotées) : smiles, structure par terme, grille.', ['EQUITY']],
  ['OVML', 'Dérivés', true, 'Pricer d’option et grecques, vol lue sur la surface du sous-jacent.', ['EQUITY']],
  ['MC', 'Dérivés', true, 'Laboratoire Monte-Carlo : GBM, Student, bootstrap ; européennes, asiatiques, barrières, digitales.', ['EQUITY']],
  ['QLBS', 'Modèles', false, 'Pricing d’option par apprentissage par renforcement (QLBS, programmation dynamique).'],
  ['GPG', 'Modèles', false, 'Prix et grecques appris par processus gaussien.'],
  ['GPVS', 'Modèles', true, 'Surface de vol lissée par processus gaussien, avec incertitude.', ['EQUITY']],
  ['SVOL', 'Modèles', true, 'Volatilité stochastique (levier, sauts) par filtre particulaire.', ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY']],
  ['REGM', 'Modèles', true, 'Régimes de marché : mélanges gaussiens (EM, BIC) et HMM.', ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY']],
  ['TSA', 'Modèles', true, 'Série temporelle Box-Jenkins : ADF, ACF/PACF, AR, Ljung-Box.', ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY']],
  ['MODL', 'Recherche', false, 'Catalogue de tous les modèles du fonds, leur statut et la commande qui les montre.', ['ALPHA']],
  ['ROB', 'Recherche', false, 'Robustesse : 2 000 timings au hasard, probabilité de surapprentissage (PBO), stats de trading.', ['ALPHA']],
  ['BQL', 'Données', false, 'Langage de requête façon BQL et formules Excel BDP / BDH / BDS.', [], ['GRQL', 'XLS', 'EXCEL', 'BDP', 'BDH', 'BDS']],
  ['HELP', 'Aide', false, 'Aide : liste des fonctions avec recherche. F1 = aide de l’écran actif ; F1 deux fois = aide de l’aide.', [], ['FUNC', 'FUNCTIONS', 'FONCTIONS', 'AIDE', 'HL']],
  ['MENU', 'Aide', false, 'Fonctions liées à l’écran, puis remonter : instrument → touche jaune → menu principal → MAIN.', []],
];
const GRC_ECRANS_REG = [
  ['MAIN', 'Vue d’ensemble du fonds', 'terminal', 'Fonds', 'Écran d’accueil : performance, positions, marchés, conseil des agents. Échap (CANCEL) y ramène.', ['TERM']],
  ['PORT', 'Portefeuille papier · en direct', 'paper', 'Fonds', 'Positions, ordres, valorisation en direct (paper trading).', ['PT'], ['ALPHA']],
  ['LIVE', 'Moteur en direct', 'paper', 'Fonds', 'Panneau « En direct » : prix toutes les 15 s, cibles décidées sur les clôtures.', [], ['ALPHA']],
  ['RISK', 'Risque du portefeuille', 'risk', 'Fonds', 'Volatilité, VaR, expositions, contributions au risque.', ['RISQUE'], ['ALPHA']],
  ['PROJ', 'Projection à un an', 'risk', 'Fonds', 'Projection du fonds à un an par bootstrap par blocs (onglet Risque).', ['PROJECTION'], ['ALPHA']],
  ['RES', 'Recherche · banc d’évaluation', 'research', 'Recherche', 'Banc des stratégies : développement ≤ 2019, validation ≥ 2020.', [], ['ALPHA']],
  ['CAMP', 'Campagnes pré-enregistrées', 'research', 'Recherche', '11 campagnes, 62 essais, protocole figé avant tout calcul.', ['CAMPAGNES'], ['ALPHA']],
  ['BT', 'Backtest', 'backtest', 'Recherche', 'Lancer un backtest sur données synthétiques, FRED ou réelles.', []],
  ['STRAT', 'Stratégies', 'strategies', 'Recherche', 'Documentation et mathématiques des stratégies.', []],
  ['NOTE', 'Notes de recherche', 'notes', 'Recherche', 'Notes rédigées par la recherche.', ['NOTES'], ['ALPHA']],
  ['NH', 'Actualités', 'news', 'Marchés', 'Fil d’actualités par catégorie.', ['N', 'NEWS']],
  ['AGENTS', 'Conseil des agents', 'agents', 'Fonds', '8 équipes, 50 agents : signaux (pistes de recherche) et questions.', []],
  ['RENDUS', 'Rendus des équipes', 'reports', 'Fonds', 'Rapports des managers.', []],
  ['HR', 'Ressources humaines', 'hr', 'Fonds', 'Effectifs et évaluations des agents.', ['RH']],
  ['VOIX', 'Salle de marché vocale', 'voice', 'Fonds', 'Parler aux agents. Espace = parler, Échap = couper.', ['VOICE']],
];
for (const [code, cat, tk, desc, secteurs, alias] of GRC_DESCRIPTIONS) {
  const l = FN_LIST.find(x => x[0] === code);
  grcEnregistrerFonction({ code, titre: l ? l[1] : (code === 'MENU' ? 'Menu des fonctions liées' : code), description: desc, exemple: l ? l[2] : code,
    ticker: tk, categorie: cat, secteurs: secteurs || [], alias: alias || [], integree: true }, { sansEcraser: true });
}
for (const [code, titre, onglet, cat, desc, alias, secteurs] of GRC_ECRANS_REG)
  grcEnregistrerFonction({ code, titre, onglet, categorie: cat, description: desc, exemple: code, alias: alias || [], secteurs: secteurs || [], ecran: true, integree: true }, { sansEcraser: true });
// fonctions de FN_LIST sans description ci-dessus (ajouts futurs dans 06) : au moins le titre
for (const [code, titre, ex] of FN_LIST) grcEnregistrerFonction({ code, titre, exemple: ex, description: titre, categorie: 'Autres', integree: true }, { sansEcraser: true });

/* ============ TOUCHES JAUNES : FAMILLES D'INSTRUMENTS ============ */
const GRC_TOUCHES = [  // [secteur, touche F, libellé]
  ['GOVT', 'F2', 'Emprunts d’État'], ['CORP', 'F3', 'Obligations d’entreprises'], ['MTGE', 'F4', 'Prêts hypothécaires / titrisation'],
  ['M-MKT', 'F5', 'Marché monétaire'], ['MUNI', 'F6', 'Collectivités locales (munis)'], ['PFD', 'F7', 'Titres préférentiels'],
  ['EQUITY', 'F8', 'Actions'], ['CMDTY', 'F9', 'Matières premières'], ['INDEX', 'F10', 'Indices'], ['CRNCY', 'F11', 'Devises'],
  ['ALPHA', 'F12', 'Portefeuille du fonds (CLIENT)'],
];
// menus de marché : [commande, libellé]. Données gratuites réelles ; les ETF servent de témoins quand le marché lui-même est payant.
const GRC_MENUS_SECTEUR = {
  GOVT: [['GC', 'Courbe des taux du Trésor US'], ['GC3D', 'Courbe des taux en 3D, ACP'], ['ILBE', 'Points morts d’inflation'], ['ECST', 'Statistiques économiques US (taux, Fed funds)'],
    ['BUDG', 'Budget fédéral US'], ['GEW', 'Économie mondiale'], ['SHY GP', 'Trésor 1-3 ans (ETF témoin)'], ['IEF GP', 'Trésor 7-10 ans (ETF témoin)'],
    ['TLT GP', 'Trésor 20 ans et plus (ETF témoin)'], ['TIP GP', 'Trésor indexé inflation (ETF témoin)'], ['TY1 <CMDTY> GP', 'Future 10 ans US, générique de 1er rang']],
  CORP: [['LQD GP', 'Crédit investment grade (ETF témoin)'], ['LQD DES', 'Fiche LQD'], ['HYG GP', 'Crédit high yield (ETF témoin)'], ['HYG DES', 'Fiche HYG'],
    ['ECST', 'Spread high yield et conditions financières']],
  MTGE: [['MBB GP', 'Titrisations hypothécaires d’agences (ETF témoin)'], ['MBB DES', 'Fiche MBB'], ['GC', 'Courbe des taux (référence des prêts)']],
  'M-MKT': [['BIL GP', 'Bons du Trésor 1-3 mois (ETF témoin)'], ['SHV GP', 'Trésor court terme (ETF témoin)'], ['ECST', 'Fed funds effectif et taux courts'], ['GC', 'Courbe des taux']],
  MUNI: [['MUB GP', 'Obligations municipales US (ETF témoin)'], ['MUB DES', 'Fiche MUB']],
  PFD: [['PFF GP', 'Actions de préférence US (ETF témoin)'], ['PFF DES', 'Fiche PFF']],
  EQUITY: [['WEI', 'Indices mondiaux'], ['EQS', 'Screener d’actions'], ['SPY US <EQUITY> DES', 'Fiche du S&P 500 (SPY)'], ['SPY US <EQUITY> GP', 'Graphique SPY'],
    ['QQQ US <EQUITY> GP', 'Graphique Nasdaq 100 (QQQ)'], ['AAPL US <EQUITY> FA', 'Comptes d’Apple (SEC)'], ['AAPL US <EQUITY> BETA', 'Bêta d’Apple'],
    ['SPY US <EQUITY> OVDV', 'Surface de vol de SPY'], ['SPY US <EQUITY> OVML', 'Pricer d’option sur SPY'], ['SPY US <EQUITY> MC', 'Monte-Carlo sur SPY']],
  CMDTY: [['GC1 <CMDTY> GP', 'Or, générique de 1er rang'], ['CL1 <CMDTY> GP', 'Pétrole WTI'], ['CO1 <CMDTY> GP', 'Pétrole Brent'], ['NG1 <CMDTY> GP', 'Gaz naturel'],
    ['SI1 <CMDTY> GP', 'Argent'], ['HG1 <CMDTY> GP', 'Cuivre'], ['C1 <CMDTY> GP', 'Maïs'], ['W1 <CMDTY> GP', 'Blé'], ['S1 <CMDTY> GP', 'Soja'], ['GLD US <EQUITY> DES', 'ETF or (GLD)']],
  INDEX: [['WEI', 'Indices mondiaux'], ['SPX <INDEX> GP', 'S&P 500'], ['INDU <INDEX> GP', 'Dow Jones'], ['CCMP <INDEX> GP', 'Nasdaq composite'], ['RTY <INDEX> GP', 'Russell 2000'],
    ['VIX <INDEX> GP', 'VIX'], ['SX5E <INDEX> GP', 'Euro Stoxx 50'], ['CAC <INDEX> GP', 'CAC 40'], ['DAX <INDEX> GP', 'DAX'], ['UKX <INDEX> GP', 'FTSE 100'],
    ['NKY <INDEX> GP', 'Nikkei 225'], ['HSI <INDEX> GP', 'Hang Seng']],
  CRNCY: [['FXC', 'Matrice des devises'], ['WCRS', 'Classement des devises'], ['WCRS MAC', 'Indice Big Mac'], ['EUR <CRNCY> GP', 'EUR/USD'], ['JPY <CRNCY> GP', 'USD/JPY'],
    ['GBP <CRNCY> GP', 'GBP/USD'], ['CHF <CRNCY> GP', 'USD/CHF'], ['XBT <CRNCY> GP', 'Bitcoin'], ['EURUSD <CRNCY> TSA', 'Série EUR/USD (Box-Jenkins)']],
  ALPHA: [['PORT', 'Portefeuille papier'], ['LIVE', 'Moteur en direct'], ['RISK', 'Risque'], ['PROJ', 'Projection à un an'], ['ROB', 'Robustesse'],
    ['RES', 'Recherche'], ['CAMP', 'Campagnes'], ['MODL', 'Catalogue des modèles'], ['NOTE', 'Notes de recherche'], ['BT', 'Backtest']],
};
// fonctions d'un instrument selon sa famille (menu « Ticker + touche jaune + <GO> »)
const GRC_FN_PAR_FAMILLE = {
  Equity: ['DES', 'GP', 'FA', 'BETA', 'TSA', 'REGM', 'SVOL', 'OVDV', 'OVML', 'MC', 'GPVS'],
  Curncy: ['GP', 'DES', 'TSA', 'REGM', 'SVOL'], Index: ['GP', 'DES', 'TSA', 'REGM', 'SVOL'], Comdty: ['GP', 'DES', 'TSA', 'REGM', 'SVOL'],
};
const GRC_FAMILLE_SECT = { Equity: 'EQUITY', Curncy: 'CRNCY', Index: 'INDEX', Comdty: 'CMDTY' };

/* ============ TITRES CONNUS (autocomplétion) ============ */
const GRC_TITRES = [
  ['AAPL', 'Apple'], ['MSFT', 'Microsoft'], ['NVDA', 'Nvidia'], ['AMZN', 'Amazon'], ['GOOGL', 'Alphabet'], ['META', 'Meta Platforms'], ['TSLA', 'Tesla'],
  ['JPM', 'JPMorgan Chase'], ['BRK-B', 'Berkshire Hathaway'], ['XOM', 'Exxon Mobil'], ['IBM', 'IBM'], ['T', 'AT&T'],
  ['SPY', 'S&P 500 (ETF)'], ['QQQ', 'Nasdaq 100 (ETF)'], ['IWM', 'Russell 2000 (ETF)'], ['TLT', 'Trésor 20 ans+ (ETF)'], ['IEF', 'Trésor 7-10 ans (ETF)'],
  ['LQD', 'Crédit IG (ETF)'], ['HYG', 'High yield (ETF)'], ['GLD', 'Or (ETF)'], ['MBB', 'Titrisations hypothécaires (ETF)'], ['MUB', 'Munis (ETF)'], ['PFF', 'Préférentielles (ETF)'],
  ['SPX', 'S&P 500 (indice)'], ['INDU', 'Dow Jones (indice)'], ['CCMP', 'Nasdaq composite'], ['NDX', 'Nasdaq 100 (indice)'], ['RTY', 'Russell 2000 (indice)'], ['VIX', 'Volatilité S&P 500'],
  ['SX5E', 'Euro Stoxx 50'], ['CAC', 'CAC 40'], ['DAX', 'DAX'], ['UKX', 'FTSE 100'], ['NKY', 'Nikkei 225'], ['HSI', 'Hang Seng'],
  ['EURUSD', 'Euro / dollar'], ['USDJPY', 'Dollar / yen'], ['GBPUSD', 'Livre / dollar'], ['USDCHF', 'Dollar / franc suisse'], ['AUDUSD', 'Dollar australien / dollar'],
  ['BTC', 'Bitcoin'], ['ETH', 'Ether'], ['SOL', 'Solana'],
  ['CL1', 'Pétrole WTI (générique)'], ['CO1', 'Pétrole Brent (générique)'], ['GC1', 'Or (générique)'], ['NG1', 'Gaz naturel (générique)'], ['SI1', 'Argent (générique)'], ['HG1', 'Cuivre (générique)'],
];
function grcTitresConnus() {
  const vus = new Set(), out = [];
  const add = (s, n) => { if (!s || vus.has(s)) return; vus.add(s); out.push([s, n || '']); };
  for (const a of (typeof MARKET !== 'undefined' && MARKET) || []) add(a.symbol.replace(/-USD$/, ''), a.name);
  for (const [s, n] of GRC_TITRES) add(s, n);
  for (const k of Object.keys(TICKER_ALIAS)) add(k, TICKER_ALIAS[k]);
  return out;
}

/* ============ PETITS OUTILS ============ */
function grcSansAccent(s) { return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase(); }
let grcMsgT = null;
function grcMessage(txt) {
  let el = document.getElementById('grcMsg');
  if (!el) { el = document.createElement('div'); el.id = 'grcMsg'; document.body.appendChild(el); }
  el.textContent = txt; el.classList.add('on');
  clearTimeout(grcMsgT); grcMsgT = setTimeout(() => el.classList.remove('on'), 2600);
}
function grcCmd() { return document.getElementById('cmdInput'); }
function grcStocker(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* stockage indisponible */ } }
function grcLire(k, def) { try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? def : v; } catch (e) { return def; } }

/* ============ HISTORIQUE DES ÉCRANS, RETOUR, FIL D'ARIANE ============ */
const GRC_HIST = [{ tab: 'terminal' }];
let grcEnRetour = false;
function grcEtatCourant() {
  const e = { tab: currentTab };
  if (currentTab === 'fn') { e.fn = FN_STATE.name; e.sym = FN_STATE.sym; e.menu = FN_STATE.menu ? Object.assign({}, FN_STATE.menu) : null; e.aide = FN_STATE.aide || null; e.filtre = FN_STATE.aideFiltre || ''; }
  return e;
}
function grcCle(e) { return [e.tab, e.fn || '', e.fn && grcAvecTitre(e.fn) ? e.sym : '', e.fn === 'MENU' && e.menu ? JSON.stringify(e.menu) : '', e.fn === 'HELP' ? (e.aide || '') + '/' + (e.filtre || '') : ''].join('|'); }
function grcLibelle(e) {
  if (e.tab !== 'fn') return (ECRANS[e.tab] || [e.tab.toUpperCase()])[0];
  if (e.fn === 'MENU' && e.menu) return e.menu.type === 'secteur' ? e.menu.secteur : e.menu.type === 'principal' ? 'MENU' : ((e.menu.sym || '') + ' MENU').trim();
  if (e.fn === 'HELP') return e.aide === 'assistance' ? 'HELP HELP' : e.aide ? 'HELP ' + e.aide : 'HELP';
  return (grcAvecTitre(e.fn) ? (e.sym || '') + ' ' : '') + e.fn;
}
const grcSwitchTabOrig = switchTab;
switchTab = function (tab) {
  GRC_MENU = null;  // l'écran qui s'ouvre redéfinit ses lignes numérotées s'il en a
  document.body.classList.remove('grc-menu-actif');
  grcSwitchTabOrig(tab);
  if (!grcEnRetour) {
    const e = grcEtatCourant();
    if (grcCle(GRC_HIST[GRC_HIST.length - 1] || {}) !== grcCle(e)) { GRC_HIST.push(e); if (GRC_HIST.length > 60) GRC_HIST.shift(); }
  }
  enteteEcran(tab);
};
function grcAller(e) {
  if (e.tab === 'fn') { FN_STATE.name = e.fn; if (e.sym) FN_STATE.sym = e.sym; FN_STATE.menu = e.menu ? Object.assign({}, e.menu) : null; FN_STATE.aide = e.aide; FN_STATE.aideFiltre = e.filtre || ''; }
  grcEnRetour = true;
  try { switchTab(e.tab); } finally { grcEnRetour = false; }
}
function grcRetour(n) {
  n = n || 1;
  if (GRC_HIST.length <= 1) return grcMessage('Début de l’historique des écrans');
  for (let i = 0; i < n && GRC_HIST.length > 1; i++) GRC_HIST.pop();
  grcAller(GRC_HIST[GRC_HIST.length - 1]);
}
function grcFilAriane() {
  const h = GRC_HIST.slice(-5), n = GRC_HIST.length;
  const crumbs = h.map((e, i) => {
    const recul = h.length - 1 - i;
    return recul === 0 ? `<b>${esc(grcLibelle(e))}</b>` : `<a onclick="grcRetour(${recul})" title="Revenir à cet écran">${esc(grcLibelle(e))}</a>`;
  }).join(' › ');
  return `<span class="sh-back${n > 1 ? '' : ' off'}" onclick="grcRetour()" title="Écran précédent (⌫ ou Alt+←)">◂ BACK</span><span class="sh-fil">${n > 5 ? '… › ' : ''}${crumbs}</span>`;
}

/* ============ TOUCHES : CANCEL, MENU, HELP, JAUNES, PAGE, PANEL ============ */
function toucheAnnuler() {
  const i = grcCmd();
  if (i) { i.value = ''; i.blur(); }
  grcSuggFermer();
  switchTab('terminal');
}
function grcCodeCourant() {
  if (currentTab === 'fn') return FN_STATE.name;
  return (ECRANS[currentTab] || ['MAIN'])[0];
}
// MENU : fonctions liées à l'écran, puis remonter la hiérarchie (instrument -> touche jaune -> menu principal -> MAIN)
function toucheMenu() {
  if (currentTab === 'fn' && FN_STATE.name === 'MENU' && FN_STATE.menu) {
    const m = FN_STATE.menu;
    if (m.type === 'principal') return switchTab('terminal');
    if (m.type === 'secteur') FN_STATE.menu = { type: 'principal' };
    else if (m.sym) FN_STATE.menu = { type: 'secteur', secteur: GRC_FAMILLE_SECT[grcSecteurDe(m.sym)] || 'EQUITY' };
    else FN_STATE.menu = { type: 'principal' };
    return switchTab('fn');
  }
  const code = grcCodeCourant();
  if (code === 'MAIN') FN_STATE.menu = { type: 'principal' };
  else if (currentTab === 'fn' && grcAvecTitre(code)) FN_STATE.menu = { type: 'liees', code, sym: FN_STATE.sym };
  else FN_STATE.menu = { type: 'liees', code };
  FN_STATE.name = 'MENU';
  switchTab('fn');
}
// HELP : un appui = aide de l'écran actif ; deuxième appui (sur l'écran d'aide) = aide de l'aide / assistance
function toucheAide() {
  if (currentTab === 'fn' && FN_STATE.name === 'HELP' && FN_STATE.aide !== 'assistance') { FN_STATE.aide = 'assistance'; return switchTab('fn'); }
  const code = grcCodeCourant();
  FN_STATE.aide = code === 'HELP' ? null : code; FN_STATE.aideFiltre = '';
  FN_STATE.name = 'HELP';
  switchTab('fn');
}
// touche jaune : avec un ticker dans la barre -> l'ajoute (« AAPL US <EQUITY> ») ; clic sur barre vide -> menu de marché
function toucheSecteur(sect, viaClavier) {
  const i = grcCmd(), v = (i && i.value || '').trim();
  if (v && i) {
    i.value = v.replace(/\s*<?(GOVT|CORP|MTGE|M-MKT|MMKT|MUNI|PFD|EQUITY|EQTY|CMDTY|COMDTY|INDEX|CRNCY|CURNCY|ALPHA|CLIENT)>?\s*$/i, '') + ' <' + sect + '> ';
    if (!viaClavier) return grcSoumettre();
    i.focus(); i.setSelectionRange(i.value.length, i.value.length); grcSuggMaj();
    return;
  }
  if (viaClavier && i) { i.value = '<' + sect + '> '; i.focus(); grcSuggMaj(); return grcMessage(`<${sect}> : <GO> = menu ${sect} · ou tapez d’abord un ticker`); }
  runCommand(sect);
}
function touchePage(sens) {
  const h = Math.max(200, window.innerHeight - 140);
  window.scrollBy({ top: sens * h, behavior: 'smooth' });
}
function touchePanel(sens) {
  const k = ONGLETS.indexOf(currentTab);
  switchTab(ONGLETS[(k + sens + ONGLETS.length) % ONGLETS.length]);
}

/* ============ ÉCRAN MENU (menu principal, menus de marché, d'instrument, fonctions liées) ============ */
function grcTitreMenu() {
  const m = FN_STATE.menu || { type: 'principal' };
  if (m.type === 'principal') return 'Menu principal';
  if (m.type === 'secteur') { const t = GRC_TOUCHES.find(x => x[0] === m.secteur); return 'Menu ' + m.secteur + (t ? ' · ' + t[2] : ''); }
  if (m.type === 'titre') return 'Menu de l’instrument ' + (m.sym || '');
  return 'Fonctions liées à ' + (m.code || '') + (m.sym ? ' · ' + m.sym : '');
}
function grcLigneMenu(n, cmd, libelle, note) {
  const p = grcAnalyserCommande(cmd), f = p.fonction ? grcFonction(p.fonction) : (p.reste.length === 1 ? grcFonction(p.reste[0]) : null);
  return `<div class="menu-l" onclick="runCommand('${esc(cmd).replace(/'/g, "\\'")}')"><span class="menu-n">${n})</span><span class="menu-c">${esc(cmd)}</span>`
    + `<span class="menu-t">${esc(libelle || (f ? f.titre : ''))}</span><span class="menu-d">${esc(note != null ? note : (f && f.description) || '')}</span></div>`;
}
function grcRenduMenu() {
  const m = FN_STATE.menu = FN_STATE.menu || { type: 'principal' };
  let lignes = [];  // [cmd, libellé, note]
  let sous = '';
  if (m.type === 'principal') {
    lignes = GRC_TOUCHES.map(([s, fk, l]) => [s, l, `Menu de marché — touche jaune ${s} (${fk})`]);
    lignes.push(['PORT', 'Portefeuille papier', null], ['RISK', 'Risque', null], ['RES', 'Recherche', null], ['NH', 'Actualités', null],
      ['BLP', 'Espace de travail en panneaux', null], ['DOCS', 'L’araignée des docs', null], ['SEARCH', 'Recherche complète', null], ['MEMO', 'Mémo des fonctions du guide', null],
      ['BU', 'Formation et entretien', null], ['HELP', 'Toutes les fonctions', null]);
    sous = 'Touche jaune + &lt;GO&gt; : menu de marché · Ticker + touche jaune + &lt;GO&gt; : menu de l’instrument';
  } else if (m.type === 'secteur') {
    lignes = (GRC_MENUS_SECTEUR[m.secteur] || []).map(([c, l]) => [c, l, null]);
    const ext = grcListeFonctions().filter(f => !f.integree && (f.secteurs || []).includes(m.secteur)).map(f => [f.ticker ? (f.exemple || f.code) : f.code, f.titre, null]);
    lignes = lignes.concat(ext);
    sous = m.secteur === 'ALPHA' ? 'Écrans du fonds' : 'Saisir un ticker puis &lt;' + esc(m.secteur) + '&gt; et une fonction, ex. ' + esc((GRC_MENUS_SECTEUR[m.secteur] || [['']])[0][0]);
  } else {
    const sym = m.sym;
    if (sym) {
      const fam = grcSecteurDe(sym);
      let codes = (GRC_FN_PAR_FAMILLE[fam] || GRC_FN_PAR_FAMILLE.Equity).slice();
      for (const f of grcListeFonctions()) if (!f.integree && f.ticker && !codes.includes(f.code)) codes.push(f.code);
      if (m.type === 'liees' && m.code) codes = [m.code].concat(codes.filter(c => c !== m.code));
      lignes = codes.map(c => [sym + ' ' + c, null, null]);
      sous = `Fonctions applicables à ${esc(sym)} &lt;${fam}&gt; · le titre reste actif : tapez juste un code (GP, DES…) puis &lt;GO&gt;`;
    }
    if (m.type === 'liees' && m.code) {
      const f0 = grcFonction(m.code), cat = f0 && f0.categorie;
      const memes = grcListeFonctions().filter(f => f.categorie && f.categorie === cat && f.code !== m.code && !(sym && f.ticker) && f.code !== 'MENU');
      lignes = lignes.concat(memes.map(f => [f.ticker ? (f.exemple || f.code) : f.code, null, null]));
      if (!sym && f0 && !lignes.length) lignes.push([m.code, null, null]);
      if (!sous) sous = 'Fonctions de la même famille (' + esc(cat || '—') + ')';
    }
  }
  GRC_MENU = lignes.map(l => l[0]);
  document.body.classList.toggle('grc-menu-actif', GRC_MENU.length > 0);
  let h = fnHeader('MENU', esc(grcTitreMenu()), '<span class="muted small">chiffre + &lt;GO&gt; · MENU = remonter · Échap = accueil</span>');
  h += '<div class="panel"><div class="panel-h">' + esc(grcTitreMenu()) + '<span class="rt">' + sous + '</span></div><div class="panel-b menu-b">';
  h += lignes.map((l, i) => grcLigneMenu(i + 1, l[0], l[1], l[2])).join('') || '<div class="muted">Aucune fonction.</div>';
  h += '</div></div>';
  return h;
}
grcEnregistrerFonction({ code: 'MENU', rendu: () => grcRenduMenu(), barre: false });

/* ============ ÉCRAN HELP : aide de la fonction, liste avec recherche, aide de l'aide ============ */
function grcCarteClavier() {
  const k = (cls, t, fk) => `<span class="key ${cls}">${t}${fk ? `<i class="fk">${fk}</i>` : ''}</span>`;
  let h = '<div class="kb">';
  h += '<div class="kb-r">' + k('k-red', 'CANCEL', 'Échap') + k('k-green', 'HELP', 'F1') + GRC_TOUCHES.map(([s, fk]) => k('k-yel', s, fk)).join('') + '</div>';
  h += '<div class="kb-r">' + k('k-green', 'MENU', 'Origine') + k('k-grey', 'PG BACK', 'Pg ↑') + k('k-grey', 'PG FWD', 'Pg ↓') + k('k-grey', 'PANEL', 'Alt+P') + k('k-grey', 'BACK', '⌫ · Alt+←') + k('k-grey', 'SEARCH', 'Alt+S') + k('k-grey', 'GRAB', 'Alt+G') + k('k-grey', 'EXPORT', 'Alt+E') + k('k-green', '&lt;GO&gt;', 'Entrée') + '</div></div>';
  const lignes = [
    ['Entrée', '<GO> : exécuter la commande'], ['Échap', 'CANCEL : ferme la liste, vide la saisie, puis revient à l’accueil (MAIN)'],
    ['F1', 'HELP : aide de l’écran actif'], ['F1 deux fois', 'HELP HELP : aide de l’aide (raccourcis, syntaxe, signaler un problème)'],
    ['F2 … F12', 'Touches jaunes GOVT, CORP, MTGE, M-MKT, MUNI, PFD, EQUITY, CMDTY, INDEX, CRNCY, ALPHA (CLIENT) : ajoutées après le ticker ; seules + <GO> = menu de marché'],
    ['Origine (fn+←)', 'MENU : fonctions liées, puis remonter les menus'], ['Pg ↑ / Pg ↓', 'PAGE BACK / FWD : page précédente / suivante'],
    ['⌫ ou Alt+←', 'Retour à l’écran précédent (hors saisie)'], ['Alt+P / Alt+Maj+P', 'PANEL : écran suivant / précédent'],
    ['/ ou Ctrl/Cmd+K', 'Aller dans la barre de commande ; taper une lettre hors saisie y va aussi'],
    ['↑ / ↓', 'Barre vide : commandes précédentes · en cours de frappe : choisir une suggestion'], ['Tab', 'Compléter avec la suggestion'],
    ['chiffre + <GO>', 'Ligne numérotée du menu affiché ; sinon écrans 1) à 13)'], ['96 / 97 / 99 + <GO>', 'Actualiser / imprimer / aide'],
    ['Alt+S · Maj+Entrée', 'SEARCH : recherche complète du mot-clé tapé (fonctions, titres, pages des livres, concepts, actualités)'],
    ['Alt+G', 'GRAB : copier l’écran avec son contexte (titre, fonction, date)'], ['Alt+E', 'EXPORT : tableaux de l’écran en CSV pour Excel'],
    ['BLP + <GO>', 'Espace en panneaux ; Alt+P y passe d’un panneau à l’autre, Échap sur l’accueil d’un panneau en sort'],
    ['? ou Alt+K', 'Afficher ou masquer cette carte du clavier'],
  ];
  h += '<table class="kb-t">' + lignes.map(([a, b]) => `<tr><td class="amber">${esc(a)}</td><td>${esc(b)}</td></tr>`).join('') + '</table>';
  h += '<div class="muted small" style="margin-top:6px">Sur Mac, les touches F demandent souvent fn (fn+F8). Les touches colorées du haut de l’écran se cliquent aussi.</div>';
  return h;
}
function grcSyntaxe() {
  const ex = [['WEI <GO>', 'fonction de marché, sans titre'], ['IBM US <EQUITY> DES <GO>', 'ticker, place, famille, fonction'], ['SPY US <EQUITY> <GO>', 'menu de l’instrument'],
    ['GP <GO>', 'puis une autre fonction : le titre reste actif'], ['SPX <INDEX> GP', 'indice'], ['EUR <CRNCY> GP', 'devise (EUR/USD)'], ['EURUSD CURNCY GP', 'paire complète'],
    ['CL1 <CMDTY> GP', 'future générique de 1er rang'], ['AIR FP <EQUITY> DES', 'place étrangère (FP = Paris, LN = Londres, GY = Xetra…)'], ['<EQUITY> <GO>', 'menu de marché']];
  return '<table class="kb-t">' + ex.map(([a, b]) => `<tr><td><a class="lnk" onclick="runCommand('${a.replace(/'/g, "\\'")}')">${esc(a)}</a></td><td class="muted">${esc(b)}</td></tr>`).join('') + '</table>';
}
function fnHelp() {
  const S = FN_STATE;
  if (S.aide === 'assistance') {
    let h = fnHeader('HELP HELP', 'Aide de l’aide : clavier, syntaxe, signaler un problème');
    h += '<div class="grid g-main"><div class="panel"><div class="panel-h">Carte du clavier<span class="rt">? ou Alt+K partout</span></div><div class="panel-b">' + grcCarteClavier() + '</div></div>';
    h += '<div><div class="panel"><div class="panel-h">Syntaxe d’une commande<span class="rt">clic = essayer</span></div><div class="panel-b">' + grcSyntaxe() + '</div></div>';
    const e = GRC_HIST.length > 1 ? GRC_HIST[GRC_HIST.length - 2] : null;
    const titre = e && e.tab === 'fn' && grcAvecTitre(e.fn) ? e.sym : '—', fct = e ? grcLibelle(e) : '—';
    h += `<div class="panel" style="margin-top:6px"><div class="panel-h">Signaler un problème<span class="rt">le titre, la fonction, le résultat attendu, le problème constaté</span></div><div class="panel-b">`
      + `<textarea id="aideSignal" class="aide-signal" spellcheck="false">Titre : ${esc(titre)}\nFonction : ${esc(fct)}\nRésultat attendu : \nProblème constaté : </textarea>`
      + `<button class="btn" style="margin-top:4px" onclick="const t=document.getElementById('aideSignal');t.select();try{navigator.clipboard.writeText(t.value);grcMessage('Copié')}catch(e){document.execCommand('copy')}">COPIER</button></div></div></div></div>`;
    return h;
  }
  let h = '';
  const f = S.aide ? grcFonction(S.aide) : null;
  if (f) {
    const cmdEx = f.exemple || f.code;
    h += fnHeader('HELP ' + esc(f.code), esc(f.titre || ''), '<span class="muted small">F1 encore = aide de l’aide · Échap = accueil</span>');
    h += `<div class="panel aide-carte"><div class="panel-b"><div class="aide-d">${esc(f.description || f.titre || '')}</div>`
      + `<div class="aide-k"><span>Exemple</span> <a class="lnk" onclick="runCommand('${esc(cmdEx).replace(/'/g, "\\'")}')">${esc(cmdEx)} &lt;GO&gt;</a></div>`
      + (f.ticker ? `<div class="aide-k"><span>Titre</span> s’applique au titre actif (${esc(S.sym || '—')}) ; changer : « TICKER &lt;FAMILLE&gt; ${esc(f.code)} &lt;GO&gt; »</div>` : '')
      + (f.controle ? `<div class="aide-k"><span>À vérifier</span> ${esc(f.controle)}</div>` : '')
      + (f.indispo ? `<div class="aide-k"><span>État</span> <b class="neg">non disponible</b> (données payantes) · <a class="lnk" onclick="runCommand('MEMO')">MEMO</a></div>` : '')
      + (f.categorie ? `<div class="aide-k"><span>Famille</span> ${esc(f.categorie)} · <a class="lnk" onclick="toucheMenu()">fonctions liées (MENU)</a></div>` : '')
      + (f.alias && f.alias.length ? `<div class="aide-k"><span>Aussi</span> ${f.alias.map(esc).join(', ')}</div>` : '')
      + '</div></div><div style="height:6px"></div>';
  } else {
    h += fnHeader('HELP', 'Toutes les fonctions · tapez pour filtrer · chiffre + &lt;GO&gt; pour ouvrir', '<span class="muted small">F1 = aide de l’écran · F1 F1 = aide de l’aide · ? = clavier</span>');
  }
  h += `<div class="aide-recherche"><input type="text" id="aideFiltre" placeholder="Chercher une fonction : code, mot-clé (ex. INFLA, volatilité, devises)…" value="${esc(S.aideFiltre || '')}" oninput="FN_STATE.aideFiltre=this.value;grcAideListe()" onkeydown="if(event.key==='Enter'&&GRC_MENU&&GRC_MENU.length){runCommand(GRC_MENU[0])}"></div>`;
  h += '<div class="panel"><div class="panel-b menu-b" id="aideListe"></div></div>';
  h += '<div class="muted small" style="margin:6px 2px">Tickers Yahoo et codes Bloomberg : actions US (AAPL), place étrangère (AIR FP), ETF (TLT), indices (SPX &lt;INDEX&gt;, ^GSPC), devises (EUR &lt;CRNCY&gt;, EURUSD), cryptos (BTC, XBT), génériques (CL1 &lt;CMDTY&gt;). Non disponibles car exigeant des consensus payants : ECSU, ECFC, FXFC. <a class="lnk" onclick="runCommand(\'HELP HELP\')">Aide de l’aide ›</a></div>';
  setTimeout(() => { grcAideListe(); const i = document.getElementById('aideFiltre'); if (i && S.aideFiltre) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 0);
  return h;
}
function grcCorrespond(f, q) {
  if (!q) return 2;
  const code = f.code, hay = grcSansAccent([f.code, f.titre, f.description, (f.alias || []).join(' '), f.categorie].join(' '));
  const mots = grcSansAccent(q).split(/\s+/).filter(Boolean);
  if (mots.length === 1 && (code.startsWith(mots[0]) || (f.alias || []).some(a => a.startsWith(mots[0])))) return 3;
  return mots.every(m => hay.includes(m)) ? 1 : 0;
}
function grcAideListe() {
  const el = document.getElementById('aideListe'); if (!el) return;
  const q = (FN_STATE.aideFiltre || '').trim();
  const ordreCat = ['Titres', 'Actions', 'Marchés', 'Devises', 'Taux', 'Économie', 'Dérivés', 'Modèles', 'Données', 'Recherche', 'Fonds', 'Risque', 'Aide', 'Autres', 'Bloomberg'];
  let fs = grcListeFonctions().map(f => [f, grcCorrespond(f, q)]).filter(x => x[1] > 0);
  fs.sort((a, b) => (q ? b[1] - a[1] : 0) || (ordreCat.indexOf(a[0].categorie) + 99 * (ordreCat.indexOf(a[0].categorie) < 0)) - (ordreCat.indexOf(b[0].categorie) + 99 * (ordreCat.indexOf(b[0].categorie) < 0)) || a[0].code.localeCompare(b[0].code));
  const cmds = [];
  let h = '', cat = null;
  for (const [f] of fs) {
    if (!q && f.categorie !== cat) { cat = f.categorie; h += `<div class="menu-cat">${esc(cat === 'Bloomberg' ? 'Codes Bloomberg : équivalents ici ou payants' : cat || 'Autres')}</div>`; }
    const cmd = f.ticker ? (FN_STATE.sym || 'SPY') + ' ' + f.code : f.code;
    cmds.push(cmd);
    h += `<div class="menu-l" onclick="runCommand('${esc(cmd).replace(/'/g, "\\'")}')"><span class="menu-n">${cmds.length})</span><span class="menu-c">${esc(f.code)}</span><span class="menu-t">${esc(f.titre || '')}</span><span class="menu-d">${esc(f.description || '')}${f.ticker ? ' <span class="amber">[titre]</span>' : ''}</span></div>`;
  }
  // tickers correspondants (recherche par nom)
  if (q.length >= 2) {
    const Q = grcSansAccent(q);
    const tks = grcTitresConnus().filter(([s, n]) => s.startsWith(Q) || (Q.length >= 3 && grcSansAccent(n).includes(Q))).slice(0, 8);
    if (tks.length) h += '<div class="menu-cat">Titres</div>';
    for (const [s, n] of tks) { cmds.push(s + ' DES'); h += `<div class="menu-l" onclick="runCommand('${esc(s)} DES')"><span class="menu-n">${cmds.length})</span><span class="menu-c">${esc(s)}</span><span class="menu-t">${esc(n)}</span><span class="menu-d">ouvrir la fiche DES</span></div>`; }
  }
  el.innerHTML = h || '<div class="muted">Aucune fonction ne correspond. Essayez un mot-clé (taux, devises, volatilité…).</div>';
  if (currentTab === 'fn' && FN_STATE.name === 'HELP') { GRC_MENU = cmds; document.body.classList.toggle('grc-menu-actif', cmds.length > 0); }
}

/* ============ CARTE DU CLAVIER EN SURIMPRESSION ( ? / Alt+K ) ============ */
function grcClavier(ouvrir) {
  let el = document.getElementById('grcClavier');
  const vis = el && el.classList.contains('on');
  if (ouvrir === undefined) ouvrir = !vis;
  if (!ouvrir) { if (el) el.classList.remove('on'); return; }
  if (!el) {
    el = document.createElement('div'); el.id = 'grcClavier';
    el.onclick = ev => { if (ev.target === el) grcClavier(false); };
    document.body.appendChild(el);
  }
  el.innerHTML = '<div class="kb-box"><div class="panel-h">Raccourcis clavier · clavier Bloomberg<span class="rt"><span class="sh-act" onclick="grcClavier(false)">Échap) Fermer</span></span></div><div class="panel-b">' + grcCarteClavier() + '</div></div>';
  el.classList.add('on');
}

/* ============ AUTOCOMPLÉTION ET HISTORIQUE DE LA BARRE DE COMMANDE ============ */
let GRC_SUGG = [], grcSuggI = -1, grcHistI = -1, grcSansSugg = false;
let GRC_CMD_HIST = grcLire('grc_cmd_hist', []);
if (!Array.isArray(GRC_CMD_HIST)) GRC_CMD_HIST = [];
function grcSuggEl() {
  let el = document.getElementById('cmdSugg');
  if (!el) {
    const form = grcCmd() && grcCmd().form; if (!form) return null;
    el = document.createElement('div'); el.id = 'cmdSugg'; el.className = 'cmd-sugg';
    form.appendChild(el);
  }
  return el;
}
function grcSuggFermer() { GRC_SUGG = []; grcSuggI = -1; const el = document.getElementById('cmdSugg'); if (el) el.classList.remove('on'); }
function grcSuggestions(val) {
  const v = val.toUpperCase();
  if (!v.trim()) return [];
  const fin = /\s$/.test(v);
  const toks = v.replace(/[<>]/g, ' ').trim().split(/\s+/).filter(Boolean);
  const partiel = fin ? '' : toks.pop() || '';
  const prefixe = (fin ? v : v.replace(/\S+$/, '')).trim();
  const pre = prefixe ? prefixe + ' ' : '';
  const out = [], vus = new Set();
  const add = (cmd, code, cat, titre, desc, score) => { if (vus.has(cmd)) return; vus.add(cmd); out.push({ cmd, code, cat, titre, desc, score }); };
  const P = grcSansAccent(partiel);
  if (toks.length) {
    // déjà un ticker (et peut-être une place / famille) : familles puis fonctions applicables au titre
    const p = grcAnalyserCommande(prefixe);
    if (p.fonction && !p.reste.length) return [];
    if (!p.secteur) for (const [s, fk, l] of GRC_TOUCHES) if (P && s.startsWith(P) && s !== 'ALPHA') add(pre + '<' + s + '>', '<' + s + '>', 'FAMILLE', l, `touche jaune ${fk}`, 5);
    if (!P && p.ticker && !p.fonction) add(pre.trim(), '<GO>', 'MENU', 'Menu de l’instrument ' + p.ticker, 'toutes les fonctions applicables', 1);
    for (const f of grcListeFonctions()) {
      if (!f.ticker) continue;
      if (P && !(f.code.startsWith(P) || (P.length >= 3 && grcSansAccent(f.titre + ' ' + f.description).includes(P)))) continue;
      add(pre + f.code, f.code, 'FONCTION', f.titre, f.description, f.code.startsWith(P) ? 4 : 2);
    }
    if (p.secteur === 'CRNCY' || p.secteur === 'INDEX' || p.secteur === 'CMDTY') out.sort((a, b) => (a.code === 'GP' ? -1 : 0) - (b.code === 'GP' ? -1 : 0));
    return out.sort((a, b) => b.score - a.score).slice(0, 9);
  }
  // un seul mot : fonctions et écrans (code puis mot-clé), familles, tickers
  for (const f of grcListeFonctions()) {
    const al = (f.alias || []).find(a => a.startsWith(P));
    if (f.code.startsWith(P)) add(f.ticker ? f.code : f.code, f.code, f.ecran ? 'ÉCRAN' : 'FONCTION', f.titre, f.description, f.code === P ? 10 : 8);
    else if (al) add(al, al, f.ecran ? 'ÉCRAN' : 'FONCTION', f.titre + ' (' + f.code + ')', f.description, 7);
  }
  for (const [s, fk, l] of GRC_TOUCHES) if (s.startsWith(P) || s.replace('-', '').startsWith(P)) add('<' + s + '>', '<' + s + '>', 'FAMILLE', 'Menu ' + l, `touche jaune ${fk}`, 6);
  for (const [s, n] of grcTitresConnus()) {
    if (s.startsWith(P)) add(s, s, 'TITRE', n, 'Tab = compléter puis choisir une fonction · <GO> = fiche DES', s === P ? 9 : 5);
    else if (P.length >= 3 && grcSansAccent(n).includes(P)) add(s, s, 'TITRE', n, 'Tab = compléter · <GO> = fiche DES', 3);
  }
  if (P.length >= 3) for (const f of grcListeFonctions()) if (grcSansAccent(f.titre + ' ' + f.description + ' ' + (f.categorie || '')).includes(P)) add(f.ticker ? (FN_STATE.sym || 'SPY') + ' ' + f.code : f.code, f.code, f.ecran ? 'ÉCRAN' : 'FONCTION', f.titre, f.description, 2);
  return out.sort((a, b) => b.score - a.score).slice(0, 9);
}
function grcSuggMaj() {
  const i = grcCmd(), el = grcSuggEl(); if (!i || !el) return;
  if (grcSansSugg) { grcSansSugg = false; return grcSuggFermer(); }
  GRC_SUGG = grcSuggestions(i.value); grcSuggI = -1;
  if (!GRC_SUGG.length) return grcSuggFermer();
  el.innerHTML = GRC_SUGG.map((s, k) => `<div class="sg" data-k="${k}"><span class="sg-cat">${esc(s.cat)}</span><span class="sg-code">${esc(s.code)}</span><span class="sg-t">${esc(s.titre || '')}</span><span class="sg-d">${esc(s.desc || '')}</span></div>`).join('')
    + '<div class="sg-pied">↑↓ choisir · Tab compléter · Entrée &lt;GO&gt; · Échap fermer</div>';
  el.classList.add('on');
}
function grcSuggSurligner() {
  const el = document.getElementById('cmdSugg'); if (!el) return;
  el.querySelectorAll('.sg').forEach(n => n.classList.toggle('sel', +n.dataset.k === grcSuggI));
}
function grcSuggChoisir(k, executer) {
  const i = grcCmd(), s = GRC_SUGG[k]; if (!i || !s) return;
  i.value = s.cmd + (s.cat === 'TITRE' || s.cat === 'FAMILLE' ? ' ' : '');
  if (executer) { grcSuggFermer(); grcSoumettre(); }
  else { i.focus(); i.setSelectionRange(i.value.length, i.value.length); grcSuggMaj(); }
}
function grcSoumettre() {
  const i = grcCmd(); if (!i) return;
  const v = i.value.trim();
  grcSuggFermer();
  if (v && !/^\d+\)?$/.test(v)) {  // les numéros de menu ne vont pas dans l'historique
    GRC_CMD_HIST = GRC_CMD_HIST.filter(x => x !== v); GRC_CMD_HIST.push(v);
    if (GRC_CMD_HIST.length > 50) GRC_CMD_HIST = GRC_CMD_HIST.slice(-50);
    grcStocker('grc_cmd_hist', GRC_CMD_HIST);
  }
  grcHistI = -1;
  i.value = '';  // comme sur le Terminal : la ligne de commande se vide, l'en-tête montre l'écran chargé (↑ rappelle la commande)
  runCommand(v); i.blur();
}
(function grcBrancherBarre() {
  const i = grcCmd(); if (!i) return;
  const form = i.form;
  // la saisie passe désormais par grcSoumettre (historique + autocomplétion) ; Entrée et clic sur <GO> y mènent
  form.removeAttribute('onsubmit');
  form.addEventListener('submit', ev => { ev.preventDefault(); if (grcSuggI >= 0 && GRC_SUGG[grcSuggI]) return grcSuggChoisir(grcSuggI, true); grcSoumettre(); });
  i.addEventListener('input', () => { grcHistI = -1; grcSuggMaj(); });
  i.addEventListener('focus', () => { if (i.value.trim()) grcSuggMaj(); });
  i.addEventListener('blur', () => setTimeout(grcSuggFermer, 150));
  i.addEventListener('keydown', ev => {
    const ouvert = GRC_SUGG.length > 0;
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      const sens = ev.key === 'ArrowDown' ? 1 : -1;
      ev.preventDefault();
      if (ouvert && i.value.trim() && grcHistI < 0) { grcSuggI = (grcSuggI + sens + GRC_SUGG.length + 1) % (GRC_SUGG.length + 1); if (grcSuggI === GRC_SUGG.length) grcSuggI = -1; return grcSuggSurligner(); }
      // historique des commandes (comme un shell)
      if (!GRC_CMD_HIST.length) return;
      if (grcHistI < 0) { if (sens > 0) return; grcHistI = GRC_CMD_HIST.length - 1; }
      else grcHistI = Math.min(GRC_CMD_HIST.length, Math.max(0, grcHistI + sens));
      i.value = grcHistI >= GRC_CMD_HIST.length ? '' : GRC_CMD_HIST[grcHistI];
      if (grcHistI >= GRC_CMD_HIST.length) grcHistI = -1;
      grcSuggFermer();
      return;
    }
    if (ev.key === 'Tab' && ouvert && !ev.shiftKey) { ev.preventDefault(); return grcSuggChoisir(grcSuggI >= 0 ? grcSuggI : 0, false); }
  });
  const el = grcSuggEl();
  el.addEventListener('mousedown', ev => { const n = ev.target.closest('.sg'); if (!n) return; ev.preventDefault(); grcSuggChoisir(+n.dataset.k, true); });
})();

/* ============ CLAVIER GLOBAL ============ */
const GRC_FK = { F2: 'GOVT', F3: 'CORP', F4: 'MTGE', F5: 'M-MKT', F6: 'MUNI', F7: 'PFD', F8: 'EQUITY', F9: 'CMDTY', F10: 'INDEX', F11: 'CRNCY', F12: 'ALPHA' };
document.addEventListener('keydown', e => {
  const lock = document.getElementById('lockScreen');
  if (lock && lock.style.display !== 'none' && getComputedStyle(lock).display !== 'none') return;
  const cmd = grcCmd(), ae = document.activeElement;
  const enSaisie = ae && (['INPUT', 'SELECT', 'TEXTAREA'].includes(ae.tagName) || ae.isContentEditable);
  const dansCmd = ae === cmd;
  const clavierOuvert = document.getElementById('grcClavier') && document.getElementById('grcClavier').classList.contains('on');
  const mod = e.ctrlKey || e.metaKey;
  // Ctrl/Cmd+K : barre de commande
  if (mod && !e.altKey && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); grcClavier(false); cmd.focus(); cmd.select(); return; }
  if (mod) return;  // laisser Cmd+C, Cmd+R, etc. au navigateur
  // touches de fonction (aussi depuis la barre de commande)
  if (e.key === 'F1') { e.preventDefault(); grcClavier(false); return toucheAide(); }
  if (GRC_FK[e.key] && !e.altKey) { e.preventDefault(); grcClavier(false); return toucheSecteur(GRC_FK[e.key], true); }
  // Échap = CANCEL, par étapes
  if (e.key === 'Escape') {
    if (clavierOuvert) { e.preventDefault(); return grcClavier(false); }
    if (dansCmd && GRC_SUGG.length) { e.preventDefault(); return grcSuggFermer(); }
    if (dansCmd && cmd.value) { e.preventDefault(); cmd.value = ''; return; }
    if (enSaisie) { ae.blur(); return; }
    if (currentTab === 'voice') return;  // Échap coupe la voix (03-desks.js)
    e.preventDefault(); return toucheAnnuler();
  }
  // Page préc. / suiv. = PAGE BACK / FWD
  if ((e.key === 'PageDown' || e.key === 'PageUp') && !(enSaisie && ae.tagName === 'TEXTAREA')) { e.preventDefault(); return touchePage(e.key === 'PageDown' ? 1 : -1); }
  // Alt+K : clavier · Alt+P : PANEL · Alt+← : retour
  if (e.altKey && e.code === 'KeyK') { e.preventDefault(); return grcClavier(); }
  if (e.altKey && e.code === 'KeyP') { e.preventDefault(); return touchePanel(e.shiftKey ? -1 : 1); }
  if (e.altKey && e.key === 'ArrowLeft' && !enSaisie) { e.preventDefault(); return grcRetour(); }
  if (enSaisie) return;
  if (clavierOuvert && e.key !== '?') { grcClavier(false); }
  if (e.key === '?') { e.preventDefault(); return grcClavier(); }
  if (e.key === '/') { e.preventDefault(); cmd.focus(); cmd.select(); return; }
  if (e.key === 'Home') { e.preventDefault(); return toucheMenu(); }
  if (e.key === 'Backspace') { e.preventDefault(); return grcRetour(); }
  // comme sur le Terminal : on tape directement, la saisie part dans la barre de commande
  if (!e.altKey && e.key.length === 1 && /[A-Za-z0-9<^=.\-]/.test(e.key) && !(currentTab === 'voice' && e.code === 'Space')) {
    e.preventDefault();
    cmd.focus(); cmd.value = e.key.toUpperCase(); grcHistI = -1; grcSuggMaj();  // nouvelle saisie
  }
});

/* ============ TOUCHES À L'ÉCRAN ============ */
(function grcHabillerTouches() {
  const hint = document.querySelector('#keyrow .key-hint');
  if (hint) { hint.style.cursor = 'pointer'; hint.onclick = () => grcClavier(true); }
})();
