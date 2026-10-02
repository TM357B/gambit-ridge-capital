/* Gambit Ridge Capital — terminal : 06-fonctions.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ FONCTIONS « BLOOMBERG » + BARRE DE COMMANDE ============ */
const FN_LIST = [
  ['GP', 'Graphique de prix', 'SPY GP'], ['DES', 'Fiche de l’actif', 'QQQ DES'],
  ['FXC', 'Matrice des devises', 'FXC'], ['WCRS', 'Classement des devises', 'WCRS'],
  ['ECST', 'Statistiques économiques US', 'ECST'], ['WEI', 'Indices mondiaux', 'WEI'],
  ['GC', 'Courbe des taux US', 'GC'], ['NH', 'Actualités', 'NH'],
  ['PORT', 'Portefeuille papier', 'PORT'], ['RES', 'Recherche / backtests', 'RES'],
];
const TICKER_ALIAS = { BTC: 'BTC-USD', ETH: 'ETH-USD', XRP: 'XRP-USD', LTC: 'LTC-USD', ADA: 'ADA-USD', BNB: 'BNB-USD', DOGE: 'DOGE-USD', SOL: 'SOL-USD',
  SPX: '^GSPC', NDX: '^NDX', VIX: '^VIX', DAX: '^GDAXI', CAC: '^FCHI', NKY: '^N225', GOLD: 'GC=F', OIL: 'CL=F' };
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

function runCommand(raw) {
  const toks = (raw || '').trim().toUpperCase().replace(/<GO>/g, '').split(/\s+/).filter(Boolean);
  if (!toks.length) return;
  const nav = { NOTE: 'notes', NOTES: 'notes', RISK: 'risk', RISQUE: 'risk', NH: 'news', N: 'news', NEWS: 'news', PORT: 'paper', PT: 'paper', RES: 'research', BT: 'backtest', STRAT: 'strategies', VOIX: 'voice', VOICE: 'voice', AGENTS: 'agents', RH: 'hr', HR: 'hr', MAIN: 'terminal', TERM: 'terminal', RENDUS: 'reports' };
  const fns = ['GP', 'DES', 'FXC', 'WCRS', 'ECST', 'WEI', 'GC', 'HELP'];
  const last = toks[toks.length - 1];
  if (toks.length === 1 && nav[last]) return switchTab(nav[last]);
  if (toks.length === 1 && fns.includes(last)) { FN_STATE.name = last; return switchTab('fn'); }
  if (toks.length >= 2 && fns.includes(last)) { FN_STATE.name = last; FN_STATE.sym = normTicker(toks.slice(0, -1).join('')); return switchTab('fn'); }
  // ticker seul -> DES
  FN_STATE.name = 'DES'; FN_STATE.sym = normTicker(toks.join('')); switchTab('fn');
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
  let html = '<div class="fn-bar">' + FN_LIST.map(([k, l, ex]) => `<div class="fn-chip ${S.name===k?'active':''}" onclick="runCommand('${(['GP','DES'].includes(k) ? (S.sym||'SPY') + ' ' : '') + k}')" title="${esc(l)} — ex. ${esc(ex)}"><b>${k}</b> <span>${esc(l)}</span></div>`).join('') + '</div>';
  c.innerHTML = html + '<div class="loader">Chargement ' + esc(S.name) + (['GP','DES'].includes(S.name) ? ' ' + esc(S.sym) : '') + '…</div>';
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
  } catch(e) { body = `<div class="loader neg">Erreur : ${esc(e.message)}</div>`; }
  if (currentTab === 'fn') c.innerHTML = html + body;
}

function fnHeader(title, sub, right) {
  return `<div class="fn-head"><span class="fn-title">${title}</span><span class="fn-sub">${sub || ''}</span><span class="fn-right">${right || ''}</span></div>`;
}

function fnHelp() {
  let h = fnHeader('HELP', 'Barre de commande : tape une fonction puis Entrée (raccourci : touche / )');
  h += '<div class="panel"><div class="panel-b"><table><tr><th>Commande</th><th>Fonction</th><th>Exemple</th></tr>';
  for (const [k, l, ex] of FN_LIST) h += `<tr><td class="amber">${k}</td><td>${esc(l)}</td><td class="muted">${esc(ex)}</td></tr>`;
  h += '<tr><td class="amber">TICKER</td><td>Un ticker seul ouvre sa fiche (DES)</td><td class="muted">NVDA · BTC · EURUSD · ^GSPC</td></tr>';
  h += '</table><div class="muted small" style="margin-top:8px">Tickers Yahoo : actions US (AAPL), ETF (TLT), indices (^GSPC, ^FCHI), devises (EURUSD, USDJPY), cryptos (BTC), futures (GC=F). Non disponibles car nécessitant des consensus d’économistes payants : ECSU, ECFC, FXFC.</div></div></div>';
  return h;
}

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

// barre de commande : « / » pour y aller, Entrée pour exécuter
document.addEventListener('keydown', e => {
  const cmd = document.getElementById('cmdInput');
  if (!cmd) return;
  if (e.key === '/' && !['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)) { e.preventDefault(); cmd.focus(); cmd.select(); }
});



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
