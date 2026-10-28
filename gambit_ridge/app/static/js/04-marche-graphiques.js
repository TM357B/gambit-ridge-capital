/* Gambit Ridge Capital — terminal : 04-marche-graphiques.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ DONNÉES DE MARCHÉ RÉELLES ============ */
let MARKET = null, RESEARCH = null, RS_SEL = null;
const CLASS_ORDER = ['Actions','Obligations','Matières premières','Devises','Crypto'];
const SERIES_COLORS = ['#ff9900','#00c853','#2979ff','#e040fb','#00e5ff','#ffea00','#ff1744','#8d6e63','#9e9e9e'];

async function fetchMarket() {
  try { MARKET = (await (await fetch('/api/market')).json()).assets || []; } catch(e) { MARKET = []; }
  renderTape();
}

function renderTape() {
  if (!MARKET || !MARKET.length) return;
  const items = MARKET.map(a => `<span class="tape-item"><span class="sym">${esc(a.symbol.replace('-USD',''))}</span> ${fmtPx(a.last)} <span class="${a.chg_1d>=0?'flash-up':'flash-down'}">${sgn(a.chg_1d*100,2)}%</span></span>`).join('');
  document.getElementById('tapeInner').innerHTML = items + items;
}

function fmtPx(p) { return p >= 1000 ? p.toLocaleString('fr-FR',{maximumFractionDigits:0}) : p >= 1 ? p.toFixed(2) : p.toPrecision(3); }
function pctCell(x, d=1) { return `<td class="num ${x>=0?'pos':'neg'}">${sgn(x*100,d)}%</td>`; }

/* ============ GRAPHIQUE LIGNE (axes, grille, survol) ============ */
const CHARTS = {};
function lineChart(id, series, opts={}) {
  // largeur de dessin proche de la largeur réelle : textes lisibles sur iPhone comme sur Mac
  const narrow = window.innerWidth < 760;
  const W = narrow ? 460 : 1000, H = Math.min(opts.height || 260, narrow ? 220 : 9999), L = narrow ? 46 : 58, R = 8, T = 12, B = 24;
  const log = !!opts.log;
  const tf = v => log ? Math.log(v) : v;
  const all = series.flatMap(s => s.y).filter(v => isFinite(v) && (!log || v > 0));
  if (!all.length) return '<div class="muted" style="padding:20px">Pas encore de données.</div>';
  let lo = Math.min(...all.map(tf)), hi = Math.max(...all.map(tf));
  if (opts.zero !== undefined) { lo = Math.min(lo, tf(opts.zero)); hi = Math.max(hi, tf(opts.zero)); }
  const pad = (hi - lo) * 0.06 || 0.01; lo -= pad; hi += pad;
  const n = Math.max(...series.map(s => s.y.length));
  const X = i => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - R);
  const Y = v => T + (1 - (tf(v) - lo) / (hi - lo)) * (H - T - B);
  const fmt = opts.yfmt || (v => v.toFixed(2));
  let svg = `<svg class="chart" id="${id}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  for (let k = 0; k <= 4; k++) {
    const tv = lo + (hi - lo) * k / 4, v = log ? Math.exp(tv) : tv, y = Y(v);
    svg += `<line x1="${L}" x2="${W-R}" y1="${y}" y2="${y}" stroke="#1c1c1c"/><text x="${L-6}" y="${y+3}" fill="#666" font-size="10" text-anchor="end">${fmt(v)}</text>`;
  }
  const xs = series[0].x || [];
  if (xs.length) for (let k = 0; k <= 5; k++) {
    if (narrow && k % 2) continue;  // moins d'étiquettes de date sur mobile
    const i = Math.round((xs.length - 1) * k / 5);
    svg += `<text x="${X(i)}" y="${H-8}" fill="#666" font-size="10" text-anchor="middle">${esc(String(xs[i]).slice(0, 7))}</text>`;
  }
  if (opts.zero !== undefined) svg += `<line x1="${L}" x2="${W-R}" y1="${Y(opts.zero)}" y2="${Y(opts.zero)}" stroke="#444" stroke-dasharray="4,4"/>`;
  if (opts.marker > 0) {
    const mx = X(opts.marker);
    svg += `<rect x="${mx}" y="${T}" width="${W-R-mx}" height="${H-T-B}" fill="#ff9900" opacity="0.04"/><line x1="${mx}" x2="${mx}" y1="${T}" y2="${H-B}" stroke="#b36b00" stroke-dasharray="3,3"/><text x="${mx+6}" y="${T+12}" fill="#b36b00" font-size="10">${esc(opts.markerLabel || '')}</text>`;
  }
  series.forEach((s, si) => {
    const pts = s.y.map((v, i) => isFinite(v) && (!log || v > 0) ? `${X(i).toFixed(1)},${Y(v).toFixed(1)}` : null).filter(Boolean).join(' ');
    if (s.area) svg += `<polygon points="${X(0)},${Y(opts.zero ?? lo)} ${pts} ${X(s.y.length-1)},${Y(opts.zero ?? lo)}" fill="${s.color}" opacity="0.12"/>`;
    svg += `<polyline points="${pts}" fill="none" stroke="${s.color || SERIES_COLORS[si]}" stroke-width="${s.width || 1.5}"/>`;
  });
  svg += `<line class="xh" x1="0" x2="0" y1="${T}" y2="${H-B}" stroke="#555" visibility="hidden"/></svg>`;
  svg += `<div class="chart-tip" id="${id}-tip"></div>`;
  CHARTS[id] = { series, X, n, L, R, W, fmt };
  const legend = series.length > 1 ? '<div class="legend2">' + series.map((s, si) => `<span style="color:${s.color || SERIES_COLORS[si]}">■</span> ${esc(s.name)}`).join(' &nbsp; ') + '</div>' : '';
  return `<div class="chart-wrap">${svg}</div>${legend}`;
}
document.addEventListener('mousemove', e => {
  const svg = e.target.closest && e.target.closest('svg.chart');
  document.querySelectorAll('.chart-tip').forEach(t => { if (!svg || t.id !== svg.id + '-tip') t.style.display = 'none'; });
  if (!svg || !CHARTS[svg.id]) return;
  const c = CHARTS[svg.id], box = svg.getBoundingClientRect();
  const vx = (e.clientX - box.left) / box.width * c.W;
  const i = Math.max(0, Math.min(c.n - 1, Math.round((vx - c.L) / (c.W - c.L - c.R) * (c.n - 1))));
  const xh = svg.querySelector('.xh'); xh.setAttribute('x1', c.X(i)); xh.setAttribute('x2', c.X(i)); xh.setAttribute('visibility', 'visible');
  const tip = document.getElementById(svg.id + '-tip');
  const date = (c.series[0].x || [])[i] || '';
  tip.innerHTML = `<div class="muted">${esc(date)}</div>` + c.series.map((s, si) => (s.y[i] === undefined || s.y[i] === null || !isFinite(s.y[i])) ? '' : `<div><span style="color:${s.color || SERIES_COLORS[si]}">■</span> ${esc(s.name)} <b>${c.fmt(s.y[i])}</b></div>`).join('');
  tip.style.display = 'block';
  const left = e.clientX - box.left;
  tip.style.left = (left > box.width - 230 ? left - 220 : left + 14) + 'px';
});

function barRow(label, v, maxAbs, sub) {
  const w = Math.min(100, Math.abs(v) / Math.max(maxAbs, 1e-9) * 50);
  return `<div class="xbar"><div class="xbar-l">${esc(label)}${sub ? ` <span class="muted">${esc(sub)}</span>` : ''}</div><div class="xbar-t"><div class="xbar-mid"></div><div class="xbar-f ${v>=0?'up':'dn'}" style="${v>=0?'left:50%':'right:50%'};width:${w}%"></div></div><div class="xbar-v ${v>=0?'pos':'neg'}">${sgn(v*100,1)}%</div></div>`;
}

async function backtestPreview(id) {
  if (!RESEARCH) { try { RESEARCH = await (await fetch('/api/research')).json(); } catch(e) { return ''; } }
  const ret = RESEARCH && RESEARCH.etf && RESEARCH.etf[RESEARCH.etf_retenue];
  const ref = RESEARCH && RESEARCH.etf && RESEARCH.etf['Benchmark — 60/40'];
  if (!ret || !ref) return '';
  const split = ret.courbe.dates.findIndex(dt => dt > RESEARCH.protocole.dev_fin);
  let h = `<div class="sub-h">En attendant l’historique réel : backtest de la stratégie retenue (poche ETF, coûts inclus)</div>`;
  h += lineChart(id, [{ name: RESEARCH.etf_retenue, x: ret.courbe.dates, y: ret.courbe.equity, color: '#ff9900', width: 2 }, { name: '60/40', x: ref.courbe.dates, y: ref.courbe.equity, color: '#2979ff' }], { log: true, height: 180, zero: 1, yfmt: v => v.toFixed(2) + '×', marker: split, markerLabel: 'VALIDATION →' });
  const er = ret.cagr_risque_egal && ret.cagr_risque_egal.val;
  if (er !== undefined) h += `<div class="legend2">La stratégie vise moins de risque que le 60/40 (vol ${fmtPct(ret.validation.vol,1)} contre ${fmtPct(ref.validation.vol,1)}). Au même niveau de risque, son rendement annuel en validation aurait été de ${fmtPct(er,1)} contre ${fmtPct(ref.validation.cagr,1)} pour le 60/40.</div>`;
  return h;
}


// Écrans tactiles : le doigt joue le rôle du survol pour les infobulles des graphiques
['touchstart', 'touchmove'].forEach(type => document.addEventListener(type, e => {
  const t = e.touches && e.touches[0];
  if (!t) return;
  const target = document.elementFromPoint(t.clientX, t.clientY);
  if (target && target.closest && target.closest('svg.chart'))
    target.dispatchEvent(new MouseEvent('mousemove', { clientX: t.clientX, clientY: t.clientY, bubbles: true }));
}, { passive: true }));
