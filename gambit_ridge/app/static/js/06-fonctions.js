/* Gambit Ridge Capital — terminal : 06-fonctions.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ FONCTIONS « BLOOMBERG » + BARRE DE COMMANDE ============ */
const FN_LIST = [
  ['GP', 'Graphique de prix', 'SPY GP'], ['DES', 'Fiche de l’actif', 'QQQ DES'], ['BQL', 'Langage de requête et API Excel', 'BQL'], ['FA', 'Comptes de la société (SEC)', 'AAPL FA'], ['EQS', 'Screener d’actions', 'EQS'], ['GEW', 'Économie mondiale (FMI, BRI)', 'GEW'],
  ['FXC', 'Matrice des devises', 'FXC'], ['WCRS', 'Classement des devises', 'WCRS'],
  ['ECST', 'Statistiques économiques US', 'ECST'], ['WEI', 'Indices mondiaux', 'WEI'],
  ['GC', 'Courbe des taux US', 'GC'], ['GC3D', 'Courbe des taux en 3D', 'GC3D'], ['OVDV', 'Surface de vol implicite 3D', 'SPY OVDV'],
  ['OVML', 'Pricer d’option et grecques', 'SPY OVML'], ['MC', 'Laboratoire Monte-Carlo', 'SPY MC'], ['ILBE', 'Inflation anticipée US', 'ILBE'],
  ['BUDG', 'Budget fédéral US', 'BUDG'], ['MAC', 'Indice Big Mac (WCRS MAC)', 'WCRS MAC'],
  ['QLBS', 'Pricing d’option par RL (QLBS)', 'QLBS'], ['GPG', 'Grecques par processus gaussien', 'GPG'], ['GPVS', 'Surface de vol lissée (GP)', 'SPY GPVS'],
  ['SVOL', 'Volatilité stochastique (particules)', 'SPY SVOL'], ['BETA', 'Bêta bayésien', 'AAPL BETA'], ['REGM', 'Régimes : mélanges et HMM', 'SPY REGM'],
  ['TSA', 'Série temporelle (Box-Jenkins)', 'SPY TSA'], ['MODL', 'Catalogue des modèles', 'MODL'], ['ROB', 'Robustesse : hasard, PBO, stats', 'ROB'], ['NH', 'Actualités', 'NH'],
  ['PORT', 'Portefeuille papier', 'PORT'], ['RES', 'Recherche / backtests', 'RES'],
];
const TICKER_ALIAS = { BTC: 'BTC-USD', ETH: 'ETH-USD', XRP: 'XRP-USD', LTC: 'LTC-USD', ADA: 'ADA-USD', BNB: 'BNB-USD', DOGE: 'DOGE-USD', SOL: 'SOL-USD',
  SPX: '^GSPC', NDX: '^NDX', VIX: '^VIX', DAX: '^GDAXI', CAC: '^FCHI', NKY: '^N225', GOLD: 'GC=F', OIL: 'CL=F',
  // codes d'indices Bloomberg -> Yahoo
  INDU: '^DJI', CCMP: '^IXIC', RTY: '^RUT', SX5E: '^STOXX50E', SXXP: '^STOXX', UKX: '^FTSE', HSI: '^HSI', SMI: '^SSMI', IBEX: '^IBEX', AS51: '^AXJO', SPTSX: '^GSPTSE', KOSPI: '^KS11',
  // contrats génériques de premier rang (CL1 <CMDTY>, ES1 <INDEX>…) -> continu Yahoo
  CL1: 'CL=F', CO1: 'BZ=F', NG1: 'NG=F', GC1: 'GC=F', SI1: 'SI=F', HG1: 'HG=F', PL1: 'PL=F', HO1: 'HO=F', XB1: 'RB=F',
  C1: 'ZC=F', W1: 'ZW=F', S1: 'ZS=F', KC1: 'KC=F', SB1: 'SB=F', CC1: 'CC=F', CT1: 'CT=F', LC1: 'LE=F',
  ES1: 'ES=F', NQ1: 'NQ=F', DM1: 'YM=F', TY1: 'ZN=F', US1: 'ZB=F', FV1: 'ZF=F', TU1: 'ZT=F', XBT: 'BTC-USD', XBTUSD: 'BTC-USD' };
// touches jaunes (familles d'instruments) : forme saisie -> forme canonique
const GRC_SECTEURS = { GOVT: 'GOVT', CORP: 'CORP', MTGE: 'MTGE', 'M-MKT': 'M-MKT', MMKT: 'M-MKT', MUNI: 'MUNI', PFD: 'PFD', EQUITY: 'EQUITY', EQTY: 'EQUITY',
  CMDTY: 'CMDTY', COMDTY: 'CMDTY', INDEX: 'INDEX', CRNCY: 'CRNCY', CURNCY: 'CRNCY', ALPHA: 'ALPHA', CLIENT: 'ALPHA' };
// codes de place Bloomberg (« IBM US », « AIR FP ») -> suffixe Yahoo
const GRC_MARCHES = { US: '', UN: '', UW: '', UQ: '', UP: '', UA: '', UR: '', FP: '.PA', LN: '.L', GY: '.DE', GR: '.DE', IM: '.MI', SM: '.MC', NA: '.AS',
  SW: '.SW', SE: '.SW', VX: '.SW', BB: '.BR', JT: '.T', JP: '.T', HK: '.HK', CN: '.TO', CT: '.TO', AU: '.AX', AT: '.AX', SS: '.ST', DC: '.CO', NO: '.OL',
  FH: '.HE', ID: '.IR', PL: '.LS', KS: '.KS', IN: '.NS', IB: '.BO', SJ: '.JO', BZ: '.SA', MM: '.MX' };
const GRC_FNS_INTEGREES = ['GP', 'DES', 'FXC', 'WCRS', 'ECST', 'WEI', 'GC', 'GC3D', 'OVDV', 'OVML', 'MC', 'ILBE', 'BUDG', 'MAC', 'QLBS', 'GPG', 'GPVS', 'SVOL', 'BETA', 'REGM', 'TSA', 'MODL', 'FA', 'EQS', 'GEW', 'BQL', 'ROB', 'HELP', 'MENU'];
let FN_STATE = { name: 'GP', sym: 'SPY', range: '1A', log: false, wcrsH: '1 mois' };
const FN_CACHE = {};

function normTicker(t) {
  t = (t || '').toUpperCase().replace(/\s+/g, '');
  if (TICKER_ALIAS[t]) return TICKER_ALIAS[t];
  if (/^[A-Z]{6}$/.test(t)) { // paire de devises : EURUSD -> EURUSD=X, USDJPY -> JPY=X
    const a = t.slice(0, 3), b = t.slice(3);
    if (a === 'USD') return b + '=X';
    return t + '=X';
  }
  return t;
}

/* Syntaxe Bloomberg : TICKER [PLACE] <SECTEUR> FONCTION <GO>
   « SPY US EQUITY GP », « EURUSD CURNCY GP », « EUR <CRNCY> GP », « CL1 COMDTY GP », « AIR FP EQUITY DES ».
   Renvoie { fonction, secteur, ticker (symbole Yahoo), brut (ticker tel que saisi), reste (jetons sans secteur ni fonction) }. */
function grcEstFonction(c) { return GRC_FNS_INTEGREES.includes(c) || !!grcFonction(c); }
function grcAnalyserCommande(raw) {
  const toks = String(raw || '').toUpperCase().replace(/<GO>/g, ' ').replace(/[<>]/g, ' ').split(/\s+/).filter(Boolean);
  const r = { fonction: null, secteur: null, ticker: null, brut: '', reste: [] };
  let t = toks.slice();
  if (t.length && grcEstFonction(t[t.length - 1]) && !(t.length === 1 && GRC_SECTEURS[t[0]])) {
    const c = t.pop(); const f = grcFonction(c);
    r.fonction = GRC_FNS_INTEGREES.includes(c) ? c : (f ? f.code : c);
  }
  t = t.filter(x => { if (GRC_SECTEURS[x]) { r.secteur = GRC_SECTEURS[x]; return false; } return true; });
  r.reste = t.slice();
  if (!t.length) return r;
  let suffixe = '';
  if (t.length >= 2 && GRC_MARCHES[t[t.length - 1]] !== undefined) suffixe = GRC_MARCHES[t.pop()];
  r.brut = t.join(' ');
  let s = t.join('');
  if (r.secteur === 'CRNCY' && /^[A-Z]{3}$/.test(s) && !TICKER_ALIAS[s]) {  // « EUR Curncy » = EURUSD ; « JPY Curncy » = USDJPY
    s = ['EUR', 'GBP', 'AUD', 'NZD'].includes(s) ? s + 'USD=X' : (['BTC', 'ETH', 'SOL', 'XRP'].includes(s) ? s + '-USD' : s + '=X');
    r.ticker = s; return r;
  }
  r.ticker = suffixe ? s + suffixe : normTicker(s);
  return r;
}

function runCommand(raw) {
  const brut = (raw || '').trim().toUpperCase().replace(/<GO>/g, ' ').trim();
  const toks = brut.replace(/[<>]/g, ' ').split(/\s+/).filter(Boolean);
  if (!toks.length) return;
  const msg = m => { if (typeof grcMessage === 'function') grcMessage(m); };
  // menu numéroté façon Bloomberg : sur un écran à lignes numérotées, « n <GO> » ouvre la ligne n ;
  // sinon 1) à 13) changent d'écran ; 96) actualiser, 97) imprimer, 99) aide
  if (toks.length === 1 && /^\d+\)?$/.test(toks[0])) {
    const k = parseInt(toks[0], 10);
    if (GRC_MENU && GRC_MENU.length && k < 96) {
      if (k >= 1 && k <= GRC_MENU.length) return runCommand(GRC_MENU[k - 1]);
      return msg(`Pas de ligne ${k}) dans ce menu (1 à ${GRC_MENU.length})`);
    }
    if (k >= 1 && k <= ONGLETS.length) return switchTab(ONGLETS[k - 1]);
    if (k === 96) { if (currentTab === 'fn') { for (const c in FN_CACHE) delete FN_CACHE[c]; } return switchTab(currentTab); }
    if (k === 97) return window.print();
    if (k === 99) { FN_STATE.name = 'HELP'; FN_STATE.aide = null; FN_STATE.aideFiltre = ''; return switchTab('fn'); }
    return msg(`Aucune action ${k})`);
  }
  // navigation : retour, menu, clavier, impression
  if (toks.length === 1 && ['BACK', 'RETOUR', 'PREC'].includes(toks[0])) return typeof grcRetour === 'function' && grcRetour();
  if (toks.length === 1 && toks[0] === 'MENU') return typeof toucheMenu === 'function' && toucheMenu();
  if (toks.length === 1 && ['KEYS', 'CLAVIER', 'RACCOURCIS', 'KEYB'].includes(toks[0])) return typeof grcClavier === 'function' && grcClavier(true);
  if (toks.length === 1 && ['PRINT', 'IMPRIMER'].includes(toks[0])) return window.print();
  // HELP : HELP seul = liste ; HELP HELP = aide de l'aide ; HELP <code> = aide de la fonction ; HELP/HL <mots> = recherche
  if (toks[0] === 'HELP' || toks[0] === 'HL' || (toks.length === 1 && ['FUNC', 'FUNCS', 'FUNCTIONS', 'FONCTIONS', 'AIDE'].includes(toks[0]))) {
    const rest = toks.slice(1);
    FN_STATE.name = 'HELP'; FN_STATE.aide = null; FN_STATE.aideFiltre = '';
    if (rest.length === 1 && rest[0] === 'HELP') FN_STATE.aide = 'assistance';
    else if (rest.length === 1 && toks[0] === 'HELP' && grcFonction(rest[0])) FN_STATE.aide = grcFonction(rest[0]).code;
    else if (rest.length) FN_STATE.aideFiltre = rest.join(' ');
    return switchTab('fn');
  }
  const p = grcAnalyserCommande(brut);
  // touche jaune seule + <GO> : menu de marché ; ticker + touche jaune + <GO> : menu de l'instrument
  if (p.secteur && !p.fonction && !p.ticker) { FN_STATE.name = 'MENU'; FN_STATE.menu = { type: 'secteur', secteur: p.secteur }; return switchTab('fn'); }
  if (p.secteur && !p.fonction && p.ticker && p.secteur !== 'ALPHA') { FN_STATE.sym = p.ticker; FN_STATE.name = 'MENU'; FN_STATE.menu = { type: 'titre', sym: p.ticker }; return switchTab('fn'); }
  const nav = { NOTE: 'notes', NOTES: 'notes', RISK: 'risk', RISQUE: 'risk', NH: 'news', N: 'news', NEWS: 'news', PORT: 'paper', PT: 'paper', RES: 'research', BT: 'backtest', STRAT: 'strategies', VOIX: 'voice', VOICE: 'voice', AGENTS: 'agents', RH: 'hr', HR: 'hr', MAIN: 'terminal', TERM: 'terminal', RENDUS: 'reports' };
  const cl = p.reste, last = cl[cl.length - 1];
  if (!p.fonction && cl.length === 1) {
    // CAMP : campagnes de recherche · LIVE : panneau En direct · PROJ : projection à un an (onglet Risque)
    if (['CAMP', 'CAMPAGNES'].includes(last)) { RS_SEL = { uni: 'camp' }; return switchTab('research'); }
    if (last === 'LIVE') return switchTab('paper');
    if (['PROJ', 'PROJECTION'].includes(last)) { switchTab('risk'); return setTimeout(() => { const e = document.getElementById('chProj'); if (e) e.closest('.panel').scrollIntoView({ behavior: 'smooth' }); }, 2500); }
    if (['GRQL', 'XLS', 'EXCEL'].includes(last)) { FN_STATE.name = 'BQL'; if (last !== 'GRQL' && FN_STATE.bql) FN_STATE.bql.vue = 'excel'; return switchTab('fn'); }
    if (nav[last]) return switchTab(nav[last]);
  }
  if (p.fonction) {
    const f = grcFonction(p.fonction);
    if (f && f.lancer && !GRC_FNS_INTEGREES.includes(p.fonction)) return f.lancer(p.ticker || FN_STATE.sym, p);
    if (f && f.onglet && !GRC_FNS_INTEGREES.includes(p.fonction)) return switchTab(f.onglet);
    if (p.fonction === 'MENU') return typeof toucheMenu === 'function' && toucheMenu();
    FN_STATE.name = p.fonction;
    if (p.ticker) FN_STATE.sym = p.ticker;  // le titre chargé reste actif pour les fonctions suivantes
    return switchTab('fn');
  }
  // ticker seul -> DES
  FN_STATE.name = 'DES'; FN_STATE.sym = p.ticker || normTicker(toks.join('')); switchTab('fn');
}

async function fnFetch(name, sym) {
  const key = name + ':' + (sym || '');
  if (FN_CACHE[key] && Date.now() - FN_CACHE[key].t < 10 * 60 * 1000) return FN_CACHE[key].d;
  const r = await fetch('/api/fn/' + name.toLowerCase() + (sym ? '?s=' + encodeURIComponent(sym) : ''));
  const d = await r.json();
  if (!d.error) FN_CACHE[key] = { t: Date.now(), d };
  return d;
}

async function renderFn() {
  const c = document.getElementById('content');
  const S = FN_STATE;
  const avecSym = { includes: grcAvecTitre };
  // barre des fonctions : celles de FN_LIST + celles ajoutées au registre par d'autres fichiers (avec un écran « rendu »)
  const extras = grcListeFonctions().filter(f => f.rendu && f.barre !== false && !FN_LIST.some(x => x[0] === f.code)).map(f => [f.code, f.titre || f.code, f.exemple || f.code]);
  let html = '<div class="fn-bar">' + FN_LIST.concat(extras).map(([k, l, ex]) => `<div class="fn-chip ${S.name===k?'active':''}" onclick="runCommand('${(avecSym.includes(k) ? (S.sym||'SPY') + ' ' : '') + k}')" title="${esc(l)} — ex. ${esc(ex)}"><b>${k}</b> <span>${esc(l)}</span></div>`).join('') + '</div>';
  const fReg = grcFonction(S.name);
  c.innerHTML = html + '<div class="loader">Chargement ' + esc(S.name) + (avecSym.includes(S.name) ? ' ' + esc(S.sym) : '') + (fReg && fReg.chargement && !GRC_FNS_INTEGREES.includes(S.name) ? ' — ' + esc(fReg.chargement) : '') + ({ OVDV: ' — toutes les échéances d’options, une dizaine de secondes', OVML: ' — lecture de la surface de vol', MC: ' — simulation en cours', QLBS: ' — programmation dynamique sur les trajectoires', GPVS: ' — apprentissage du processus gaussien', SVOL: ' — calibrage du filtre particulaire, une vingtaine de secondes', REGM: ' — EM et Baum-Welch', FA: ' — comptes SEC EDGAR', EQS: ' — premier chargement de l’univers : une vingtaine de secondes', GEW: ' — FMI, BRI et OCDE' }[S.name] || '') + '…</div>';
  let body = '';
  try {
    if (S.name === 'HELP') body = fnHelp();
    else if (S.name === 'GP') body = fnGP(await fnFetch('GP', S.sym));
    else if (S.name === 'DES') body = await fnDES(S.sym);
    else if (S.name === 'FXC') body = fnFXC(await fnFetch('FXC'));
    else if (S.name === 'WCRS') body = fnWCRS(await fnFetch('WCRS'));
    else if (S.name === 'ECST') body = fnECST(await fnFetch('ECST'));
    else if (S.name === 'WEI') body = fnWEI(await fnFetch('WEI'));
    else if (S.name === 'GC') body = fnGC(await fnFetch('GC'));
    else if (S.name === 'OVDV') body = fnOVDV(await fnFetch('OVDV', S.sym));
    else if (S.name === 'OVML') body = fnOVML(await fnFetchQ('OVML', S.sym, ovmlQuery(FN_STATE.ovml)), S.sym);
    else if (S.name === 'MC') body = fnMC(await fnFetchQ('MC', S.sym, mcQuery(FN_STATE.mc)), S.sym);
    else if (S.name === 'GC3D') body = fnGC3D(await fnFetchQ('GC3D', '', { y: FN_STATE.gc3dY }));
    else if (S.name === 'BUDG') body = fnBUDG(await fnFetch('BUDG'));
    else if (S.name === 'MAC') body = fnMAC(await fnFetch('MAC', ['USD', 'EUR', 'GBP', 'JPY', 'CNY'].includes(S.sym) ? S.sym : 'USD'));
    else if (S.name === 'ILBE') body = fnILBE(await fnFetch('ILBE'));
    else if (S.name === 'QLBS') body = fnQLBS(await fnFetchQ('QLBS', '', FN_STATE.qlbs));
    else if (S.name === 'GPG') body = fnGPG(await fnFetchQ('GPG', '', FN_STATE.gpg));
    else if (S.name === 'GPVS') body = fnGPVS(await fnFetch('GPVS', S.sym));
    else if (S.name === 'SVOL') body = fnSVOL(await fnFetchQ('SVOL', S.sym, FN_STATE.svol), S.sym);
    else if (S.name === 'BETA') body = fnBETA(await fnFetchQ('BETA', S.sym, FN_STATE.beta), S.sym);
    else if (S.name === 'REGM') body = fnREGM(await fnFetch('REGM', S.sym));
    else if (S.name === 'TSA') body = fnTSA(await fnFetch('TSA', S.sym));
    else if (S.name === 'MODL') body = fnMODL(await fnFetch('MODL'));
    else if (S.name === 'FA') body = fnFA(await fnFetch('FA', S.sym));
    else if (S.name === 'EQS') body = fnEQS(await fnFetchQ('EQS', '', eqsQuery()));
    else if (S.name === 'GEW') body = fnGEW(await fnFetch('GEW'));
    else if (S.name === 'BQL') body = await fnBQL();
    else if (S.name === 'ROB') body = fnROB(await fnFetch('ROB'));
    else if (fReg && fReg.rendu) body = await fReg.rendu(S.sym, S);
    else body = `<div class="loader neg">Fonction inconnue : ${esc(S.name)} — tapez HELP &lt;GO&gt;</div>`;
  } catch(e) { body = `<div class="loader neg">Erreur : ${esc(e.message)}</div>`; }
  if (currentTab === 'fn') { c.innerHTML = html + body; if (typeof s3dMount === 'function') s3dMount(); }
}

function fnHeader(title, sub, right) {
  return `<div class="fn-head"><span class="fn-title">${title}</span><span class="fn-sub">${sub || ''}</span><span class="fn-right">${right || ''}</span></div>`;
}

// fnHelp() : écran HELP, défini dans 15-navigation.js (aide contextuelle, recherche, aide de l'aide)

function fnGP(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const S = FN_STATE, n = d.dates.length;
  const lastDate = d.dates[n - 1];
  const start = { '1M': 21, '3M': 63, '6M': 126, '1A': 252, '5A': 1260, 'MAX': n }[S.range];
  let i0 = S.range === 'YTD' ? d.dates.findIndex(x => x.slice(0, 4) === lastDate.slice(0, 4)) : Math.max(0, n - start);
  if (i0 < 0) i0 = 0;
  const cut = a => a.slice(i0);
  const x = cut(d.dates), cl = cut(d.close);
  const last = d.close[n - 1], prev = d.close[n - 2], chg = last / prev - 1, perf = last / cl[0] - 1;
  const series = [{ name: d.symbol, x, y: cl, color: '#ff9900', width: 1.8 }];
  const m50 = cut(d.sma50), m200 = cut(d.sma200);
  if (m50.some(v => v !== null)) series.push({ name: 'Moy. 50 j', x, y: m50.map(v => v ?? NaN), color: '#2979ff', width: 1 });
  if (m200.some(v => v !== null)) series.push({ name: 'Moy. 200 j', x, y: m200.map(v => v ?? NaN), color: '#e040fb', width: 1 });
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">${esc(d.name)}</span>`, `GP · ${esc(lastDate)}`, `<span class="fn-last">${fmtPx(last)}</span> <span class="${chg>=0?'pos':'neg'}">${sgn(chg*100,2)}%</span>`);
  h += '<div class="fn-tools">' + ['1M','3M','6M','YTD','1A','5A','MAX'].map(r => `<span class="rng ${S.range===r?'on':''}" onclick="FN_STATE.range='${r}';renderFn()">${r}</span>`).join('');
  h += `<span class="rng ${S.log?'on':''}" onclick="FN_STATE.log=!FN_STATE.log;renderFn()">LOG</span><span class="muted small" style="margin-left:auto">Performance sur la période : <b class="${perf>=0?'pos':'neg'}">${sgn(perf*100,1)}%</b> · <a class="lnk" onclick="runCommand('${esc(d.symbol)} DES')">fiche DES ›</a></span></div>`;
  h += '<div class="panel"><div class="panel-b">' + lineChart('chGP', series, { height: 380, log: S.log, yfmt: v => fmtPx(v) }) + '</div></div>';
  return h;
}

async function fnDES(sym) {
  const d = await fnFetch('DES', sym);
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const g = await fnFetch('GP', sym);
  const chg = d.returns['1 j'] || 0;
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">${esc(d.name)}</span>`, `DES · ${esc(d.asset_class)} · historique depuis ${esc(d.history_start)}`, `<span class="fn-last">${fmtPx(d.last)}</span> <span class="${chg>=0?'pos':'neg'}">${sgn(chg*100,2)}%</span>`);
  h += '<div class="kpis">';
  h += kpi('Plus haut 52 sem.', fmtPx(d.high_52w)) + kpi('Plus bas 52 sem.', fmtPx(d.low_52w));
  h += kpi('Vol 1 mois / 1 an', fmtPct(d.vol_1m,0) + ' / ' + fmtPct(d.vol_1y,0));
  h += kpi('Drawdown actuel', fmtPct(d.drawdown_now,1), d.drawdown_now < -0.1 ? 'neg' : '');
  h += kpi('Pire drawdown historique', fmtPct(d.max_dd_all,0), 'neg');
  if (d.beta_spy !== undefined) h += kpi('Bêta / corr. S&P 500 (1 an)', d.beta_spy.toFixed(2) + ' / ' + d.corr_spy.toFixed(2));
  h += '</div><div class="grid g-main">';
  if (g && !g.error) {
    const n = g.dates.length, i0 = Math.max(0, n - 252);
    h += '<div class="panel"><div class="panel-h">Cours sur 1 an <span class="rt"><a class="lnk" onclick="runCommand(\'' + esc(d.symbol) + ' GP\')">GP ›</a></span></div><div class="panel-b">' + lineChart('chDES', [{ name: d.symbol, x: g.dates.slice(i0), y: g.close.slice(i0), color: '#ff9900', area: true }], { height: 220, yfmt: v => fmtPx(v) }) + '</div></div>';
  }
  h += '<div class="panel"><div class="panel-h">Performances</div><div class="panel-b" style="padding:4px"><table>';
  for (const [k, v] of Object.entries(d.returns)) h += `<tr><td>${esc(k)}</td>${v === null ? '<td class="num muted">—</td>' : pctCell(v, 1)}</tr>`;
  h += '</table>';
  if (d.fund) {
    const w = d.fund.weight || 0;
    h += '<div class="sub-h">Dans le fonds</div>';
    h += d.fund.in_universe ? `<div>${w ? `<span class="${w>0?'pos':'neg'}">${w>0?'ACHETEUR':'VENDEUR'} ${fmtPct(Math.abs(w),1)}</span> du capital` : 'Pas de position'} · signal tendance <b>${d.fund.signal===null?'—':sgn(d.fund.signal,2)}</b></div>` : '<div class="muted">Hors de l’univers de la stratégie (20 ETF + 7 cryptos).</div>';
  }
  h += '</div></div></div>';
  return h;
}

function heat(v, scale) {
  const a = Math.min(1, Math.abs(v) / scale);
  return v >= 0 ? `rgba(0,200,83,${0.12 + 0.6 * a})` : `rgba(255,23,68,${0.12 + 0.6 * a})`;
}

function fnFXC(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const C = d.currencies;
  let h = fnHeader('FXC', `Matrice des taux croisés · clôtures du ${esc(d.date)}`, '<span class="muted small">case = unités de la devise en colonne pour 1 unité de la devise en ligne · couleur = variation du jour</span>');
  h += '<div class="panel"><div class="panel-b" style="overflow-x:auto"><table class="fxc"><tr><th></th>' + C.map(c => `<th class="num" title="${esc(d.names[c])}">${c}</th>`).join('') + '</tr>';
  for (const r of C) {
    h += `<tr><td class="amber" title="${esc(d.names[r])}"><b>${r}</b></td>`;
    for (const c of C) {
      if (r === c) { h += '<td class="fxc-diag"></td>'; continue; }
      const v = d.matrix[r][c], ch = d.change_1d[r][c];
      h += `<td class="num" style="background:${heat(ch, 0.01)}" title="${r}/${c} : ${sgn(ch*100,2)}% sur le jour">${v >= 100 ? v.toFixed(2) : v >= 1 ? v.toFixed(4) : v.toPrecision(4)}</td>`;
    }
    h += '</tr>';
  }
  h += '</table><div class="fxc-legend">' + [-0.01, -0.005, -0.001, 0.001, 0.005, 0.01].map(v => `<span style="background:${heat(v, 0.01)}">${v > 0 ? '+' : ''}${(v*100).toFixed(1)} %</span>`).join('') + '</div></div></div>';
  return h;
}

function fnWCRS(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const H = FN_STATE.wcrsH;
  const rows = d.rows.filter(r => r[H] !== null).sort((a, b) => b[H] - a[H]);
  const mx = Math.max(...rows.map(r => Math.abs(r[H])), 1e-6);
  let h = fnHeader('WCRS', `Classement des devises contre dollar · ${esc(d.date)}`, '');
  h += '<div class="fn-tools">' + d.horizons.map(k => `<span class="rng ${H===k?'on':''}" onclick="FN_STATE.wcrsH='${k}';renderFn()">${k}</span>`).join('') + '<span class="muted small" style="margin-left:auto">positif = la devise s’est appréciée face au dollar</span></div>';
  h += '<div class="grid g-main"><div class="panel"><div class="panel-b">';
  for (const r of rows) h += barRow(`${r.ccy} · ${r.name}`, r[H], mx);
  h += '</div></div><div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Devise</th>' + d.horizons.map(k => `<th class="num">${k}</th>`).join('') + '<th class="num">Vol 3 m</th></tr>';
  for (const r of rows) h += `<tr><td class="amber">${r.ccy}</td>` + d.horizons.map(k => r[k] === null ? '<td class="num muted">—</td>' : pctCell(r[k], 1)).join('') + `<td class="num muted">${fmtPct(r.vol_3m,1)}</td></tr>`;
  h += '</table></div></div></div>';
  return h;
}

function sparkline(vals) {
  const v = vals.filter(x => x !== null && isFinite(x));
  if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v), W = 110, H = 22;
  const pts = v.map((y, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 2 - (y - lo) / ((hi - lo) || 1) * (H - 4)).toFixed(1)}`).join(' ');
  return `<svg width="${W}" height="${H}" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="#ff9900" stroke-width="1.2"/></svg>`;
}

function fnECST(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const fmtv = (r, x) => x === null ? '—' : (Math.abs(x) >= 1000 ? Math.round(x).toLocaleString('fr-FR') : x.toFixed(2)) + (r.unit === '%' ? ' %' : r.unit === 'pt' ? ' pt' : '');
  let h = fnHeader('ECST', 'Statistiques économiques · États-Unis', `<span class="muted small">source : ${esc(d.source)}</span>`);
  h += '<div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto"><table class="ecst"><tr><th>Indicateur</th><th class="num">Dernier</th><th class="num">Précédent</th><th class="num">Var.</th><th>Date</th><th>24 dernières obs.</th></tr>';
  for (const s of d.sections) {
    h += `<tr><td colspan="6" class="cls-row">${esc(s.title)}</td></tr>`;
    for (const r of s.rows) {
      const dv = r.prev === null ? null : r.last - r.prev;
      h += `<tr class="ecst-row" onclick="ecstChart('${r.id}')"><td>${esc(r.label)}</td><td class="num"><b>${fmtv(r, r.last)}</b></td><td class="num muted">${fmtv(r, r.prev)}</td><td class="num ${dv===null?'':dv>=0?'pos':'neg'}">${dv===null?'':(dv>=0?'+':'')+(Math.abs(dv)>=100?Math.round(dv).toLocaleString('fr-FR'):dv.toFixed(2))}</td><td class="muted">${esc(r.date)}</td><td>${sparkline(r.history)}</td></tr>`;
    }
  }
  h += '</table></div></div><div id="ecstChart"></div>';
  return h;
}
function ecstChart(id) {
  const d = FN_CACHE['ECST:'] && FN_CACHE['ECST:'].d; if (!d) return;
  const r = d.sections.flatMap(s => s.rows).find(x => x.id === id); if (!r) return;
  const el = document.getElementById('ecstChart');
  el.innerHTML = `<div class="panel" style="margin-top:10px"><div class="panel-h">${esc(r.label)} <span class="rt">${esc(r.id)} · 24 dernières observations</span></div><div class="panel-b">` + lineChart('chECST', [{ name: r.label, x: r.history_dates, y: r.history, color: '#ff9900', area: true }], { height: 220, yfmt: v => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString('fr-FR') : v.toFixed(2)) }) + '</div></div>';
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// raccourcis clavier (/, Ctrl+K, F1-F12, Échap, Page préc./suiv.…) : 15-navigation.js

function fnWEI(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  let h = fnHeader('WEI', 'Indices boursiers mondiaux', '<span class="muted small">dernières séances closes · clic = graphique</span>');
  h += '<div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Indice</th><th class="num">Dernier</th><th class="num">1 j</th><th class="num">1 sem.</th><th class="num">1 mois</th><th class="num">YTD</th><th class="num">1 an</th><th>Séance</th></tr>';
  for (const r of d.regions) {
    h += `<tr><td colspan="8" class="cls-row">${esc(r.region)}</td></tr>`;
    for (const x of r.rows) h += `<tr class="ecst-row" onclick="runCommand('${esc(x.symbol)} GP')"><td>${esc(x.name)} <span class="muted small">${esc(x.symbol)}</span></td><td class="num">${fmtPx(x.last)}</td><td class="num" style="background:${heat(x.chg_1d, 0.02)}">${sgn(x.chg_1d*100,2)}%</td>${pctCell(x.chg_1w)}${pctCell(x.chg_1m)}${x.chg_ytd===null?'<td class="num muted">—</td>':pctCell(x.chg_ytd)}${pctCell(x.chg_1y)}<td class="muted small">${esc(x.date)}</td></tr>`;
  }
  h += '</table></div></div>';
  return h;
}

function fnGC(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const cols = ['#ff9900', '#2979ff', '#888'];
  let h = fnHeader('GC', 'Courbe des taux du Trésor américain', `<span class="muted small">${esc(d.source)}</span>`);
  h += '<div class="kpis">' + Object.entries(d.spreads).map(([k, v]) => kpi('Pente ' + k, (v >= 0 ? '+' : '') + v + ' pb', v < 0 ? 'neg' : '')).join('') + '</div>';
  h += '<div class="panel"><div class="panel-b">' + lineChart('chGC', d.curves.map((c, i) => ({ name: c.label, x: d.maturities, y: c.yields, color: cols[i], width: i ? 1.3 : 2.2 })), { height: 300, yfmt: v => v.toFixed(2) + ' %' }) + '</div></div>';
  const now = d.curves[0].yields, m1 = d.curves[1].yields, y1 = d.curves[2].yields;
  h += '<div class="panel" style="margin-top:10px"><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Maturité</th><th class="num">Rendement</th><th class="num">Var. 1 mois</th><th class="num">Var. 1 an</th></tr>';
  d.maturities.forEach((m, i) => {
    const a = Math.round((now[i] - m1[i]) * 100), b = Math.round((now[i] - y1[i]) * 100);
    h += `<tr><td class="amber">${esc(m)}</td><td class="num"><b>${now[i].toFixed(2)} %</b></td><td class="num ${a>=0?'neg':'pos'}">${a>=0?'+':''}${a} pb</td><td class="num ${b>=0?'neg':'pos'}">${b>=0?'+':''}${b} pb</td></tr>`;
  });
  h += '</table><div class="muted small" style="margin:6px">pb = point de base (0,01 %). Pente négative (courbe inversée) = signal historique de ralentissement.</div></div></div>';
  return h;
}

/* ============ OVDV : SURFACE DE VOLATILITÉ IMPLICITE ============ */
const OVDV_COLS = [0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20];
function volColor(v, lo, hi) {  // dégradé façon viridis : violet = vol basse, jaune = vol haute
  const st = [[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]];
  const t = Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))) * (st.length - 1);
  const i = Math.min(st.length - 2, Math.floor(t)), f = t - i;
  return 'rgb(' + st[i].map((a, k) => Math.round(a + (st[i + 1][k] - a) * f)).join(',') + ')';
}

function ovdvHeatmap(d) {
  const narrow = window.innerWidth < 760;
  const K = d.moneyness, J = d.grid.days, V = d.grid.vols;
  const W = narrow ? 460 : 1000, H = narrow ? 240 : 320, L = narrow ? 44 : 58, R = narrow ? 44 : 64, T = 8, B = 24;
  const all = V.flat().filter(v => v !== null).sort((a, b) => a - b);
  if (!all.length) return '<div class="muted" style="padding:20px">Pas de surface.</div>';
  const lo = all[Math.floor(all.length * 0.02)], hi = all[Math.floor(all.length * 0.98)];
  const cw = (W - L - R) / K.length, ch = (H - T - B) / J.length;
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  V.forEach((row, i) => row.forEach((v, j) => {
    if (v === null) return;  // pas de cotation : case vide
    svg += `<rect x="${(L + j * cw).toFixed(1)}" y="${(T + i * ch).toFixed(1)}" width="${(cw + 0.6).toFixed(1)}" height="${(ch + 0.6).toFixed(1)}" fill="${volColor(v, lo, hi)}"><title>${Math.round(K[j] * 100)} % du spot · ${Math.round(J[i])} j : ${(v * 100).toFixed(1)} %</title></rect>`;
  }));
  K.forEach((k, j) => { const p = Math.round(k * 100); if (p % (narrow ? 10 : 5) === 0) svg += `<text x="${L + (j + 0.5) * cw}" y="${H - 8}" fill="#666" font-size="10" text-anchor="middle">${p}%</text>`; });
  for (let q = 0; q <= 5; q++) { const i = Math.round((J.length - 1) * q / 5); svg += `<text x="${L - 6}" y="${T + (i + 0.5) * ch + 3}" fill="#666" font-size="10" text-anchor="end">${Math.round(J[i])} j</text>`; }
  const gx = W - R + 14, gh = H - T - B;
  for (let s = 0; s < 40; s++) svg += `<rect x="${gx}" y="${T + gh * s / 40}" width="12" height="${gh / 40 + 0.6}" fill="${volColor(hi - (hi - lo) * s / 39, lo, hi)}"/>`;
  svg += `<text x="${gx + 16}" y="${T + 9}" fill="#999" font-size="10">${(hi * 100).toFixed(0)}%</text><text x="${gx + 16}" y="${T + gh}" fill="#999" font-size="10">${(lo * 100).toFixed(0)}%</text></svg>`;
  return svg;
}

function fnOVDV(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div><div class="muted small" style="padding:0 10px">OVDV demande un sous-jacent à options cotées aux États-Unis (SPY, QQQ, IWM, AAPL, TSLA…). Ex. : <a class="lnk" onclick="runCommand('SPY OVDV')">SPY OVDV</a></div>`;
  const K = d.moneyness, E = d.expiries, k = d.kpi;
  const pct = v => v === null || v === undefined ? '—' : (v * 100).toFixed(1) + ' %';
  const pt = v => v === null || v === undefined ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + ' pt';
  const iAtm = K.findIndex(m => Math.abs(m - 1) < 1e-9);
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">Surface de volatilité implicite</span>`, `OVDV · ${esc(d.asof)} New York · spot ${fmtPx(d.spot)}`, `<span class="fn-last">${pct(k.atm_1m)}</span> <span class="muted small">vol ATM 1 mois</span>`);
  h += '<div class="kpis">' + kpi('Vol ATM 1 mois', pct(k.atm_1m)) + kpi('Vol ATM 1 an', pct(k.atm_1y))
    + kpi('Pente 1 an − 1 mois', pt(k.slope), k.slope !== null && k.slope < 0 ? 'neg' : '')
    + kpi(`Skew 95 % − 105 % (${esc(k.skew_1m_expiry)})`, pt(k.skew_1m))
    + kpi('Vols calculées', `${d.n_points.toLocaleString('fr-FR')} / ${d.n_quotes.toLocaleString('fr-FR')}`)
    + kpi('Surface remplie', fmtPct(d.filled, 0)) + '</div>';
  h += `<div class="fn-tools"><a class="lnk" onclick="runCommand('${esc(d.symbol)} OVML')">pricer une option sur cette surface (OVML) ›</a><a class="lnk" style="margin-left:16px" onclick="FN_STATE.mc.vol='impl';runCommand('${esc(d.symbol)} MC')">Monte-Carlo à la vol implicite (MC) ›</a></div>`;
  h += '<div class="panel"><div class="panel-h">Surface de volatilité implicite <span class="rt">3D · glisser pour tourner</span></div><div class="panel-b">' + ovdv3d(d) + '</div></div><div style="height:10px"></div>';

  // smiles : jusqu'à 6 échéances représentatives
  const choix = [];
  for (const cible of [7, 30, 91, 182, 365, 730]) {
    const e = E.reduce((a, b) => Math.abs(b.days - cible) < Math.abs(a.days - cible) ? b : a);
    if (!choix.includes(e)) choix.push(e);
  }
  const xk = K.map(m => Math.round(m * 100) + ' %');
  const smiles = choix.map((e, i) => ({ name: `${e.expiry} (${Math.round(e.days)} j)`, x: xk, y: e.smile.map(v => v === null ? NaN : v * 100), color: SERIES_COLORS[i] }));
  const terme = [{ name: 'Vol ATM', x: d.grid.days.map(j => Math.round(j) + ' j'), y: d.grid.vols.map(r => r[iAtm] === null ? NaN : r[iAtm] * 100), color: '#ff9900', width: 2 }];
  h += '<div class="grid g-main">';
  h += '<div class="panel"><div class="panel-h">Smile par maturité <span class="rt">strike / spot · puts à gauche, calls à droite</span></div><div class="panel-b">' + lineChart('chOVDVs', smiles, { height: 280, yfmt: v => v.toFixed(1) + ' %' }) + '</div></div>';
  h += '<div class="panel"><div class="panel-h">Structure par terme ATM <span class="rt">interpolée en variance totale</span></div><div class="panel-b">' + lineChart('chOVDVt', terme, { height: 280, yfmt: v => v.toFixed(1) + ' %' }) + '</div></div>';
  h += '</div>';
  h += '<div class="panel" style="margin-top:10px"><div class="panel-h">Surface vue de dessus <span class="rt">maturité (lignes) × strike / spot (colonnes) · case vide = pas de cotation</span></div><div class="panel-b">' + ovdvHeatmap(d) + '</div></div>';

  // grille façon OVDV : échéances cotées × moneyness
  const col = m => K.findIndex(x => Math.abs(x - m) < 1e-9);
  h += '<div class="panel" style="margin-top:10px"><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Échéance</th><th class="num">Jours</th>' + OVDV_COLS.map(m => `<th class="num">${Math.round(m * 100)} %</th>`).join('') + '<th class="num">Div. implicite</th><th>Forward</th></tr>';
  for (const e of E) {
    h += `<tr><td class="amber">${esc(e.expiry)}</td><td class="num muted">${Math.round(e.days)}</td>` + OVDV_COLS.map(m => { const v = e.smile[col(m)]; return `<td class="num ${m === 1 ? 'amber' : ''}">${v === null ? '<span class="muted">—</span>' : (v * 100).toFixed(1)}</td>`; }).join('') + `<td class="num muted" title="sous 30 jours, le dividende implicite est trop bruité pour être lu (l’effet sur la vol reste négligeable)">${e.days < 30 ? '—' : (e.div * 100).toFixed(2) + ' %'}</td><td class="muted small">${esc(e.source)}</td></tr>`;
  }
  h += '</table><div class="muted small" style="margin:6px">Vol implicite Black-Scholes sur le prix mid, options hors de la monnaie seulement (puts sous le spot, calls au-dessus), strikes 75-125 % du spot, spreads &gt; 25 % rejetés. Forward de chaque échéance tiré de la parité call-put près du spot (options américaines). Interpolation le long du smile puis en variance totale σ²T ; sans cotation, la case reste vide.'
    + (d.calendar_violations ? ` <span class="neg">${d.calendar_violations} arbitrage(s) calendaire(s) apparent(s).</span>` : ' Aucun arbitrage calendaire apparent.')
    + ' Données Yahoo (cache 15 min). Outil d’analyse : ne pilote pas le portefeuille.</div></div></div>';
  return h;
}
