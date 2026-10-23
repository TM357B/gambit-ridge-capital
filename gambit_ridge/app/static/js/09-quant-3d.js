/* Gambit Ridge Capital — terminal : 09-quant-3d.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ SURFACE 3D (canvas maison, rotation souris / doigt, sans bibliothèque) ============ */
const S3D = {};
const CMAP_JET = [[0, 0, 140], [0, 40, 255], [0, 220, 255], [40, 230, 70], [255, 235, 0], [255, 60, 0], [150, 0, 0]];
const CMAP_VIRIDIS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];

function cmapRGB(t, map) {
  t = Math.max(0, Math.min(1, t)) * (map.length - 1);
  const i = Math.min(map.length - 2, Math.floor(t)), f = t - i;
  return map[i].map((a, k) => Math.round(a + (map[i + 1][k] - a) * f));
}

function niceTicks(lo, hi, n) {
  const raw = (hi - lo) / Math.max(1, n), p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * p).find(s => s >= raw) || raw;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

// xs : étiquettes des colonnes, ys : étiquettes des lignes, Z[ligne][colonne] (null = pas de donnée)
function surface3d(id, xs, ys, Z, opts = {}) {
  const prev = S3D[id];
  S3D[id] = { xs, ys, Z, opts, az: prev ? prev.az : (opts.az ?? -2.35), el: prev ? prev.el : (opts.el ?? 0.5), zoom: prev ? prev.zoom : 1 };
  const h = window.innerWidth < 760 ? 320 : (opts.height || 460);
  return `<div class="s3d-wrap" style="height:${h}px"><canvas id="${id}" class="s3d"></canvas><div class="s3d-tip" id="${id}-tip"></div>`
    + `<div class="s3d-help">glisser : tourner · molette : zoom · double-clic : vue initiale</div></div>`;
}

function s3dMount() {
  for (const id of Object.keys(S3D)) {
    const cv = document.getElementById(id);
    if (!cv) { delete S3D[id]; continue; }
    if (!cv.dataset.bound) { s3dBind(cv, id); cv.dataset.bound = '1'; }
    s3dDraw(id);
  }
}

function s3dDraw(id) {
  const s = S3D[id], cv = document.getElementById(id);
  if (!s || !cv) return;
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (!W || !H) return;
  if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#060606'; ctx.fillRect(0, 0, W, H);
  const o = s.opts, Z = s.Z, m = Z.length, n = Z[0].length, map = o.cmap === 'viridis' ? CMAP_VIRIDIS : CMAP_JET;
  const vals = Z.flat().filter(v => v !== null && isFinite(v)).sort((a, b) => a - b);
  if (!vals.length) return;
  // o.clip : échelle bornée aux percentiles (un pic isolé n'écrase plus le reste) ; valeurs plafonnées à l'affichage
  const pc = q => vals[Math.min(vals.length - 1, Math.max(0, Math.round(q * (vals.length - 1))))];
  const lo = o.zmin ?? (o.clip ? pc(o.clip[0]) : vals[0]), hi = o.zmax ?? (o.clip ? pc(o.clip[1]) : vals[vals.length - 1]), span = (hi - lo) || 1;
  const clampV = v => Math.max(lo, Math.min(hi, v));
  const narrow = W < 600, H3 = 1.1;
  const X = j => -1 + 2 * j / (n - 1), Y = i => -1 + 2 * i / (m - 1), Zn = v => (clampV(v) - lo) / span * H3;
  const ca = Math.cos(s.az), sa = Math.sin(s.az), ce = Math.cos(s.el), se = Math.sin(s.el);
  // cadrage indépendant de l'azimut : la boîte tient dans le canvas quelle que soit la rotation
  const wDispo = W - (narrow ? 70 : 200), hDispo = H - 56, r2 = Math.SQRT2 * 1.12;
  const sc = Math.min(wDispo / (2 * r2), hDispo / (H3 * ce + 2 * r2 * se)) * s.zoom;
  const cx = narrow ? W * 0.5 : (W - 70) / 2, cy = 22 + hDispo / 2 + sc * (H3 * ce) / 2;
  const P = (x, y, z) => { const xr = x * ca - y * sa, yr = x * sa + y * ca; return [cx + sc * xr, cy - sc * (z * ce + yr * se), yr * ce - z * se]; };
  const font = narrow ? '9px' : '10px';
  ctx.font = `${font} ${getComputedStyle(document.body).fontFamily}`;

  // sol et murs du fond (le coin le plus éloigné porte l'axe vertical)
  const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
  const back = corners.reduce((a, c) => P(c[0], c[1], 0)[2] > P(a[0], a[1], 0)[2] ? c : a);
  const [bx, by] = back, fx = -bx, fy = -by;
  const line = (a, b, col, w = 1) => { ctx.strokeStyle = col; ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); };
  const text = (p, t, col, align = 'center', dx = 0, dy = 0) => { ctx.fillStyle = col; ctx.textAlign = align; ctx.fillText(t, p[0] + dx, p[1] + dy); };
  ctx.fillStyle = 'rgba(255,255,255,0.025)';
  ctx.beginPath(); corners.forEach((c, k) => { const p = P(c[0], c[1], 0); k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); }); ctx.closePath(); ctx.fill();
  const zt = niceTicks(lo, hi, 4);
  for (const t of zt) {
    const z = Zn(t);
    line(P(bx, -by, z), P(bx, by, z), '#262626'); line(P(-bx, by, z), P(bx, by, z), '#262626');
    text(P(bx, -by, z), (o.zfmt || (v => v.toFixed(1)))(t), '#888', P(bx, -by, z)[0] < cx ? 'right' : 'left', P(bx, -by, z)[0] < cx ? -6 : 6, 3);
  }
  line(P(bx, by, 0), P(bx, by, H3), '#333'); line(P(bx, -by, 0), P(bx, -by, H3), '#333'); line(P(-bx, by, 0), P(-bx, by, H3), '#333');
  const xt = [...new Set(Array.from({ length: narrow ? 4 : 6 }, (_, k) => Math.round((n - 1) * k / ((narrow ? 4 : 6) - 1))))];
  const yt = [...new Set(Array.from({ length: narrow ? 4 : 6 }, (_, k) => Math.round((m - 1) * k / ((narrow ? 4 : 6) - 1))))];
  for (const j of xt) {
    line(P(X(j), -1, 0), P(X(j), 1, 0), '#1e1e1e');
    const p = P(X(j), fy * 1.12, 0); text(p, String((o.xfmt || (v => v))(s.xs[j])), '#999', 'center', 0, 4);
  }
  for (const i of yt) {
    line(P(-1, Y(i), 0), P(1, Y(i), 0), '#1e1e1e');
    const p = P(fx * 1.12, Y(i), 0); text(p, String((o.yfmt || (v => v))(s.ys[i])), '#999', p[0] < cx ? 'right' : 'left', 0, 4);
  }
  if (o.xtitle) text(P(0, fy * 1.38, 0), o.xtitle, '#ff9900');
  if (o.ytitle) { const p = P(fx * 1.42, 0, 0); text(p, o.ytitle, '#ff9900', p[0] < cx ? 'right' : 'left'); }
  if (o.ztitle) text(P(bx, by, H3 * 1.1), o.ztitle, '#ff9900');

  // facettes, de la plus éloignée à la plus proche (algorithme du peintre)
  const pts = [];
  for (let i = 0; i < m; i++) { pts.push([]); for (let j = 0; j < n; j++) { const v = Z[i][j]; pts[i].push(v === null || !isFinite(v) ? null : P(X(j), Y(i), Zn(v))); } }
  const quads = [];
  for (let i = 0; i < m - 1; i++) for (let j = 0; j < n - 1; j++) {
    const q = [pts[i][j], pts[i][j + 1], pts[i + 1][j + 1], pts[i + 1][j]];
    if (q.some(p => !p)) continue;
    const v = (clampV(Z[i][j]) + clampV(Z[i][j + 1]) + clampV(Z[i + 1][j + 1]) + clampV(Z[i + 1][j])) / 4;
    quads.push([q, (q[0][2] + q[1][2] + q[2][2] + q[3][2]) / 4, v]);
  }
  quads.sort((a, b) => b[1] - a[1]);
  const dense = quads.length > 2500;
  for (const [q, , v] of quads) {
    const [r, g, b] = cmapRGB((v - lo) / span, map);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.beginPath(); ctx.moveTo(q[0][0], q[0][1]); for (let k = 1; k < 4; k++) ctx.lineTo(q[k][0], q[k][1]); ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = dense ? `rgb(${r},${g},${b})` : 'rgba(0,0,0,0.35)'; ctx.lineWidth = dense ? 0.6 : 0.5; ctx.stroke();
  }
  // points cotés (nuage) par-dessus la surface
  if (o.scatter) for (const [xn, yn, v] of o.scatter) { const p = P(xn, yn, Zn(v)); ctx.fillStyle = 'rgba(255,255,255,0.55)'; ctx.fillRect(p[0] - 1, p[1] - 1, 2, 2); }
  // échelle de couleurs
  if (!narrow) {
    const gx = W - 46, gy = 18, gh = H - 60;
    for (let k = 0; k < 60; k++) { const [r, g, b] = cmapRGB(1 - k / 59, map); ctx.fillStyle = `rgb(${r},${g},${b})`; ctx.fillRect(gx, gy + gh * k / 60, 12, gh / 60 + 1); }
    for (const t of zt) { const y = gy + gh * (1 - (t - lo) / span); text([gx + 16, y + 3], (o.zfmt || (v => v.toFixed(1)))(t), '#999', 'left'); }
  }
  s.pts = pts; s.lo = lo; s.hi = hi;
}

function s3dBind(cv, id) {
  let drag = null, raf = 0;
  const redraw = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; s3dDraw(id); }); };
  const start = (x, y) => { drag = { x, y }; cv.style.cursor = 'grabbing'; };
  const move = (x, y) => {
    const s = S3D[id]; if (!s || !drag) return;
    s.az -= (x - drag.x) * 0.008; s.el = Math.max(0.05, Math.min(1.5, s.el + (y - drag.y) * 0.006));
    drag = { x, y }; redraw();
  };
  cv.addEventListener('mousedown', e => { start(e.clientX, e.clientY); e.preventDefault(); });
  window.addEventListener('mousemove', e => drag ? move(e.clientX, e.clientY) : null);
  window.addEventListener('mouseup', () => { drag = null; cv.style.cursor = 'grab'; });
  cv.addEventListener('touchstart', e => { const t = e.touches[0]; start(t.clientX, t.clientY); }, { passive: true });
  cv.addEventListener('touchmove', e => { const t = e.touches[0]; move(t.clientX, t.clientY); e.preventDefault(); }, { passive: false });
  cv.addEventListener('touchend', () => { drag = null; });
  cv.addEventListener('wheel', e => { const s = S3D[id]; if (!s) return; s.zoom = Math.max(0.5, Math.min(3, s.zoom * Math.exp(-e.deltaY * 0.0015))); redraw(); e.preventDefault(); }, { passive: false });
  cv.addEventListener('dblclick', () => { const s = S3D[id]; if (!s) return; s.az = s.opts.az ?? -2.35; s.el = s.opts.el ?? 0.5; s.zoom = 1; redraw(); });
  cv.addEventListener('mousemove', e => {
    const s = S3D[id], tip = document.getElementById(id + '-tip');
    if (!s || !s.pts || drag) { if (tip) tip.style.display = 'none'; return; }
    const b = cv.getBoundingClientRect(), mx = e.clientX - b.left, my = e.clientY - b.top;
    let best = null, bd = 196;
    s.pts.forEach((row, i) => row.forEach((p, j) => { if (!p) return; const d = (p[0] - mx) ** 2 + (p[1] - my) ** 2; if (d < bd) { bd = d; best = [i, j]; } }));
    if (!best) { tip.style.display = 'none'; return; }
    const [i, j] = best, v = s.Z[i][j];
    tip.innerHTML = s.opts.tip ? s.opts.tip(i, j, v) : `${esc(s.ys[i])} · ${esc(s.xs[j])} : <b>${v.toFixed(2)}</b>`;
    tip.style.display = 'block'; tip.style.left = Math.min(mx + 14, b.width - 200) + 'px'; tip.style.top = (my + 14) + 'px';
  });
  cv.addEventListener('mouseleave', () => { const tip = document.getElementById(id + '-tip'); if (tip) tip.style.display = 'none'; });
}
window.addEventListener('resize', () => { for (const id of Object.keys(S3D)) s3dDraw(id); });

/* ============ OUTILS COMMUNS DES FONCTIONS QUANT ============ */
async function fnFetchQ(name, sym, params) {
  const qs = new URLSearchParams({ ...(sym ? { s: sym } : {}), ...params }).toString();
  const key = name + '?' + qs;
  if (FN_CACHE[key] && Date.now() - FN_CACHE[key].t < 10 * 60 * 1000) return FN_CACHE[key].d;
  const d = await (await fetch('/api/fn/' + name.toLowerCase() + '?' + qs)).json();
  if (!d.error) FN_CACHE[key] = { t: Date.now(), d };
  return d;
}
function qf(label, html) { return `<label class="qf"><span>${label}</span>${html}</label>`; }
function qsel(path, val, opts) { return `<select onchange="${path}=this.value;renderFn()">` + opts.map(([v, l]) => `<option value="${v}" ${String(v) === String(val) ? 'selected' : ''}>${esc(l)}</option>`).join('') + '</select>'; }
function qnum(path, val, step) { return `<input type="number" value="${val}" step="${step || 'any'}" onchange="${path}=+this.value" onkeydown="if(event.key==='Enter'){${path}=+this.value;renderFn()}">`; }
function pctS(v, d = 1) { return v === null || v === undefined ? '—' : (v * 100).toFixed(d) + ' %'; }

/* ============ MC : LABORATOIRE MONTE-CARLO ============ */
const MC_PRODUITS = [['aucun', 'Aucun (projection seule)'], ['call', 'Call européen'], ['put', 'Put européen'], ['asian_call', 'Call asiatique'],
  ['asian_put', 'Put asiatique'], ['uo_call', 'Call up-and-out'], ['do_put', 'Put down-and-out'], ['digital_call', 'Call digital']];
FN_STATE.mc = { modele: 'gbm', vol: 'hist', volv: 20, drift: 'rn', driftv: 6, horizon: 252, n: 50000, produit: 'aucun', strike: 100, barriere: 120, graine: 7, dividende: null };

function mcQuery(st) {
  const p = { modele: st.modele, horizon: st.horizon, n: st.n, produit: st.produit, strike: st.strike, graine: st.graine,
    vol: st.vol === 'fixe' ? st.volv : st.vol, drift: st.drift === 'fixe' ? st.driftv : st.drift };
  if (['uo_call', 'do_put'].includes(st.produit)) p.barriere = st.barriere;
  if (st.dividende !== null && st.dividende !== undefined) p.dividende = st.dividende;
  return p;
}

function mcForm(sym) {
  const st = FN_STATE.mc, P = 'FN_STATE.mc.';
  let h = '<div class="qform">';
  h += qf('Sous-jacent', `<input type="text" value="${esc(sym)}" style="width:90px" onchange="FN_STATE.sym=normTicker(this.value)" onkeydown="if(event.key==='Enter'){FN_STATE.sym=normTicker(this.value);renderFn()}">`);
  h += qf('Modèle', qsel(P + 'modele', st.modele, [['gbm', 'Brownien géométrique'], ['student', 'Student (queues épaisses)'], ['bootstrap', 'Bootstrap historique']]));
  h += qf('Volatilité', qsel(P + 'vol', st.vol, [['hist', 'Historique 1 an'], ['impl', 'Implicite ATM (OVDV)'], ['fixe', 'Fixée →']]) + (st.vol === 'fixe' ? qnum(P + 'volv', st.volv, 0.5) : ''));
  h += qf('Drift', qsel(P + 'drift', st.drift, [['rn', 'Risque-neutre (r − q)'], ['hist', 'Historique 5 ans'], ['fixe', 'Fixé (%/an) →']]) + (st.drift === 'fixe' ? qnum(P + 'driftv', st.driftv, 0.5) : ''));
  h += qf('Horizon (séances)', qnum(P + 'horizon', st.horizon, 1));
  h += qf('Trajectoires', qsel(P + 'n', st.n, [[10000, '10 000'], [50000, '50 000'], [100000, '100 000'], [200000, '200 000']]));
  h += qf('Produit à pricer', qsel(P + 'produit', st.produit, MC_PRODUITS));
  if (st.produit !== 'aucun') h += qf('Strike (% spot)', qnum(P + 'strike', st.strike, 1));
  if (['uo_call', 'do_put'].includes(st.produit)) h += qf('Barrière (% spot)', qnum(P + 'barriere', st.barriere, 1));
  h += qf('Graine', qnum(P + 'graine', st.graine, 1));
  h += `<button class="btn" onclick="renderFn()">LANCER &lt;GO&gt;</button></div>`;
  return h;
}

function mcFanSvg(e, spot) {
  const narrow = window.innerWidth < 760, W = narrow ? 460 : 1000, H = narrow ? 230 : 320, L = narrow ? 46 : 62, R = 10, T = 12, B = 24;
  const allv = [...e.q05, ...e.q95, ...e.trajectoires.flat()].filter(isFinite);
  let lo = Math.min(...allv), hi = Math.max(...allv); const pad = (hi - lo) * 0.05; lo -= pad; hi += pad;
  const N = e.jours.length, X = k => L + k / (N - 1) * (W - L - R), Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const pl = arr => arr.map((v, k) => `${X(k).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
  const band = (a, b) => pl(a) + ' ' + b.map((v, k) => `${X(k).toFixed(1)},${Y(v).toFixed(1)}`).reverse().join(' ');
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  for (const t of niceTicks(lo, hi, 5)) s += `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="#1c1c1c"/><text x="${L - 6}" y="${Y(t) + 3}" fill="#666" font-size="10" text-anchor="end">${fmtPx(t)}</text>`;
  for (let k = 0; k <= 5; k++) { const i = Math.round((N - 1) * k / 5); s += `<text x="${X(i)}" y="${H - 8}" fill="#666" font-size="10" text-anchor="middle">j${e.jours[i]}</text>`; }
  for (const p of e.trajectoires) s += `<polyline points="${pl(p)}" fill="none" stroke="#5a5a5a" stroke-width="0.7" opacity="0.55"/>`;
  s += `<polygon points="${band(e.q05, e.q95)}" fill="#ff9900" opacity="0.13"/><polygon points="${band(e.q25, e.q75)}" fill="#ff9900" opacity="0.22"/>`;
  s += `<line x1="${L}" x2="${W - R}" y1="${Y(spot)}" y2="${Y(spot)}" stroke="#2979ff" stroke-dasharray="4,4"/>`;
  s += `<polyline points="${pl(e.q50)}" fill="none" stroke="#ff9900" stroke-width="2"/></svg>`;
  return s + '<div class="legend2"><span style="color:#ff9900">■</span> médiane · bandes 25–75 % et 5–95 % &nbsp; <span style="color:#5a5a5a">■</span> 25 trajectoires tirées &nbsp; <span style="color:#2979ff">■</span> spot</div>';
}

function mcHistSvg(hg, var95) {
  const narrow = window.innerWidth < 760, W = narrow ? 460 : 1000, H = narrow ? 230 : 320, L = 40, R = 10, T = 12, B = 24;
  const b = hg.bords, c = hg.comptes, mx = Math.max(...c), lo = b[0], hi = b[b.length - 1];
  const X = v => L + (v - lo) / (hi - lo) * (W - L - R), Y = v => T + (1 - v / mx) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  c.forEach((k, i) => { const col = b[i + 1] <= -var95 ? '#ff1744' : b[i] >= 0 ? '#00c853' : '#ff9900'; s += `<rect x="${X(b[i]) + 0.5}" y="${Y(k)}" width="${Math.max(0.5, X(b[i + 1]) - X(b[i]) - 1)}" height="${H - B - Y(k)}" fill="${col}" opacity="0.85"/>`; });
  for (const t of niceTicks(lo, hi, 6)) s += `<text x="${X(t)}" y="${H - 8}" fill="#666" font-size="10" text-anchor="middle">${(t * 100).toFixed(0)}%</text>`;
  s += `<line x1="${X(-var95)}" x2="${X(-var95)}" y1="${T}" y2="${H - B}" stroke="#ff1744" stroke-dasharray="4,3"/><text x="${X(-var95) + 4}" y="${T + 10}" fill="#ff1744" font-size="10">VaR 95 %</text>`;
  s += `<line x1="${X(0)}" x2="${X(0)}" y1="${T}" y2="${H - B}" stroke="#444"/></svg>`;
  return s;
}

function fnMC(d, sym) {
  const st = FN_STATE.mc;
  let h = mcForm(sym);
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const p = d.params, k = d.kpi;
  const nomModele = { gbm: 'brownien géométrique', student: `Student (${p.ddl ? p.ddl.toFixed(1) : '—'} ddl, kurtosis ${p.kurtosis.toFixed(1)})`, bootstrap: 'bootstrap de blocs historiques' }[p.modele];
  h += fnHeader(`${esc(d.symbol)} <span class="muted">Laboratoire Monte-Carlo</span>`, `MC · ${esc(nomModele)} · ${p.n.toLocaleString('fr-FR')} trajectoires × ${p.horizon} séances · ${d.ms} ms`,
    `<span class="fn-last">${fmtPx(d.spot)}</span> <span class="muted small">clôture ${esc(d.asof)}</span>`);
  h += '<div class="kpis">' + kpi('Médiane à l’horizon', `${fmtPx(k.mediane)} <span class="muted small">${sgn((k.mediane / d.spot - 1) * 100, 1)}%</span>`)
    + kpi('Intervalle 5 – 95 %', `${fmtPx(k.q05)} – ${fmtPx(k.q95)}`) + kpi('Probabilité de gain', pctS(k.p_gain, 0))
    + kpi('VaR 95 % / 99 %', `${pctS(k.var95)} / ${pctS(k.var99)}`, 'neg') + kpi('CVaR 95 %', pctS(k.cvar95), 'neg')
    + kpi('Drawdown médian', pctS(k.dd_median), 'neg') + kpi('P(drawdown > 20 %)', pctS(k.p_dd20, 0)) + '</div>';
  h += `<div class="muted small" style="margin:-4px 0 8px">Volatilité utilisée <b class="amber">${pctS(p.sigma)}</b> (${esc({ hist: 'historique 1 an', impl: 'implicite ATM de la surface' }[p.vol] || 'fixée')})`
    + ` · drift <b class="amber">${pctS(p.mu, 2)}</b> (${esc({ rn: 'risque-neutre r − q', hist: 'historique 5 ans' }[p.drift] || 'fixé')}) · taux ${pctS(p.taux, 2)} · dividende ${pctS(p.dividende, 2)}`
    + ` · vol historique 1 an ${pctS(p.vol_hist)} · graine ${p.graine}${p.note_vol ? ` · <span class="neg">${esc(p.note_vol)}</span>` : ''}</div>`;
  h += '<div class="grid g-main">';
  h += '<div class="panel"><div class="panel-h">Trajectoires simulées <span class="rt">éventail des quantiles</span></div><div class="panel-b">' + mcFanSvg(d.eventail, d.spot) + '</div></div>';
  h += '<div class="panel"><div class="panel-h">Distribution du rendement à l’horizon <span class="rt">rouge : au-delà de la VaR 95 %</span></div><div class="panel-b">' + mcHistSvg(d.histogramme, k.var95) + '</div></div>';
  h += '</div>';
  const x = d.pricing;
  if (x) {
    const lib = (MC_PRODUITS.find(([v]) => v === x.produit) || [, x.produit])[1];
    const ecart = x.bs !== null ? (x.prix_cv - x.bs) / x.se_cv : null;
    h += `<div class="grid g-main" style="margin-top:10px"><div class="panel"><div class="panel-h">Pricing · ${esc(lib)} <span class="rt">K ${fmtPx(x.K)}${x.B ? ` · barrière ${fmtPx(x.B)}` : ''} · risque-neutre</span></div><div class="panel-b" style="padding:4px">`;
    h += '<table><tr><th>Méthode</th><th class="num">Prix</th><th class="num">Erreur std</th><th class="num">IC 95 %</th></tr>';
    h += `<tr><td>Monte-Carlo (antithétique)</td><td class="num"><b>${x.prix.toFixed(4)}</b></td><td class="num muted">${x.se.toFixed(4)}</td><td class="num muted">${x.ic95[0].toFixed(3)} – ${x.ic95[1].toFixed(3)}</td></tr>`;
    h += `<tr><td>+ variable de contrôle (S<sub>T</sub>)</td><td class="num amber"><b>${x.prix_cv.toFixed(4)}</b></td><td class="num muted">${x.se_cv.toFixed(4)}</td><td class="num muted">${(x.prix_cv - 1.96 * x.se_cv).toFixed(3)} – ${(x.prix_cv + 1.96 * x.se_cv).toFixed(3)}</td></tr>`;
    if (x.bs !== null) h += `<tr><td>Black-Scholes exact</td><td class="num"><b>${x.bs.toFixed(4)}</b></td><td class="num muted" colspan="2">écart MC : ${ecart >= 0 ? '+' : ''}${ecart.toFixed(2)} erreur(s) std ${Math.abs(ecart) < 2 ? '<span class="pos">✓ cohérent</span>' : '<span class="neg">à vérifier</span>'}</td></tr>`;
    h += `</table><div class="muted small" style="margin:6px">Variance divisée par <b>${x.gain_variance ? x.gain_variance.toFixed(1) : '—'}</b> grâce à la variable de contrôle (même précision avec ${x.gain_variance ? Math.round(x.gain_variance) : '—'} fois moins de trajectoires). Barrières surveillées chaque séance.</div></div></div>`;
    const cv = x.convergence, series = [{ name: 'Estimation', x: cv.n, y: cv.prix, color: '#ff9900', width: 2 }, { name: 'IC 95 % bas', x: cv.n, y: cv.bas, color: '#555' }, { name: 'IC 95 % haut', x: cv.n, y: cv.haut, color: '#555' }];
    if (x.bs !== null) series.push({ name: 'Black-Scholes', x: cv.n, y: cv.n.map(() => x.bs), color: '#2979ff' });
    h += '<div class="panel"><div class="panel-h">Convergence <span class="rt">l’intervalle se resserre en 1/√N</span></div><div class="panel-b">' + lineChart('chMCconv', series, { height: 240, yfmt: v => v.toFixed(2) }) + '</div></div></div>';
  }
  h += `<div class="muted small" style="margin:8px 2px">Modèles calibrés sur l’historique réel de ${esc(d.symbol)} (Yahoo, ajusté des dividendes). Le bootstrap rejoue des blocs de 5 séances réelles, recentrés : krachs et regroupements de volatilité conservés. Projection ≠ prévision : elle montre la dispersion compatible avec les hypothèses choisies. Le pricing est toujours fait en risque-neutre, quel que soit le drift de la projection.</div>`;
  return h;
}

/* ============ OVML : PRICER D'OPTION ============ */
FN_STATE.ovml = { type: 'call', strike: 100, jours: 91, vol: 'surface', volv: 20, quantite: 10 };
function ovmlQuery(st) { return { type: st.type, strike: st.strike, jours: st.jours, quantite: st.quantite, vol: st.vol === 'fixe' ? st.volv : 'surface' }; }

function fnOVML(d, sym) {
  const st = FN_STATE.ovml, P = 'FN_STATE.ovml.';
  let h = '<div class="qform">';
  h += qf('Sous-jacent', `<input type="text" value="${esc(sym)}" style="width:90px" onchange="FN_STATE.sym=normTicker(this.value)" onkeydown="if(event.key==='Enter'){FN_STATE.sym=normTicker(this.value);renderFn()}">`);
  h += qf('Call / Put', qsel(P + 'type', st.type, [['call', 'Call'], ['put', 'Put']]));
  h += qf('Strike (% spot)', qnum(P + 'strike', st.strike, 1)) + qf('Maturité (jours)', qnum(P + 'jours', st.jours, 1));
  h += qf('Volatilité', qsel(P + 'vol', st.vol, [['surface', 'Surface OVDV'], ['fixe', 'Fixée →']]) + (st.vol === 'fixe' ? qnum(P + 'volv', st.volv, 0.5) : ''));
  h += qf('Contrats (×100)', qnum(P + 'quantite', st.quantite, 1));
  h += '<button class="btn" onclick="renderFn()">PRICER &lt;GO&gt;</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const g = d.grecques, ps = d.position;
  h += fnHeader(`${esc(d.symbol)} <span class="muted">Option ${d.type === 'call' ? 'Call' : 'Put'} européenne · Black-Scholes</span>`, `OVML · K ${fmtPx(d.strike)} (${(d.strike_pct * 100).toFixed(0)} %) · ${Math.round(d.jours)} jours`,
    `<span class="fn-last">${g.prix.toFixed(2)}</span> <span class="muted small">par action</span>`);
  h += '<div class="grid g-main"><div class="panel"><div class="panel-h">Données de marché</div><div class="panel-b" style="padding:4px"><table>';
  const row = (l, v, c = '') => `<tr><td>${l}</td><td class="num ${c}">${v}</td></tr>`;
  h += row('Spot', fmtPx(d.spot)) + row('Strike', `${fmtPx(d.strike)} <span class="muted">(${(d.strike_pct * 100).toFixed(1)} %)</span>`)
    + row('Maturité', `${Math.round(d.jours)} jours (${(d.jours / 365).toFixed(3)} an)`)
    + row('Volatilité', `${pctS(d.vol, 2)} <span class="muted">${d.vol_source === 'surface' ? 'lue sur la surface' : 'fixée'}</span>`, 'amber')
    + row('Taux sans risque', pctS(d.taux, 2)) + row('Dividende implicite', pctS(d.dividende, 2)) + row('Forward', fmtPx(d.forward));
  h += '</table>' + (d.note ? `<div class="muted small" style="margin:6px">${esc(d.note)}</div>` : '') + '</div></div>';
  h += `<div class="panel"><div class="panel-h">Prix et grecques <span class="rt">position : ${d.quantite} contrat(s) × 100</span></div><div class="panel-b" style="padding:4px"><table><tr><th></th><th class="num">Par action</th><th class="num">Position</th></tr>`;
  const gr = [['Prix (prime)', 'prix', 4, 2], ['Delta', 'delta', 4, 1], ['Gamma', 'gamma', 5, 3], ['Vega (1 pt de vol)', 'vega', 4, 2], ['Theta (par jour)', 'theta', 4, 2], ['Rho (1 pt de taux)', 'rho', 4, 2]];
  for (const [l, kk, d1, d2] of gr) h += `<tr><td>${l}</td><td class="num">${g[kk].toFixed(d1)}</td><td class="num ${ps[kk] < 0 ? 'neg' : ''}">${ps[kk].toLocaleString('fr-FR', { maximumFractionDigits: d2 })}</td></tr>`;
  h += `</table><div style="margin:8px"><a class="lnk" onclick="ovmlVersMC()">Vérifier ce prix par Monte-Carlo ›</a></div></div></div></div>`;
  const pr = d.profil;
  h += '<div class="panel" style="margin-top:10px"><div class="panel-h">Profil de P&amp;L par action <span class="rt">aujourd’hui et à l’échéance, prime déduite</span></div><div class="panel-b">'
    + lineChart('chOVML', [{ name: 'Aujourd’hui', x: pr.spot.map(v => fmtPx(v)), y: pr.aujourdhui, color: '#ff9900', width: 2 }, { name: 'À l’échéance', x: pr.spot.map(v => fmtPx(v)), y: pr.echeance, color: '#2979ff' }], { height: 260, zero: 0, yfmt: v => v.toFixed(2) })
    + '</div></div>';
  FN_STATE.ovmlDernier = d;
  return h;
}

function ovmlVersMC() {
  const d = FN_STATE.ovmlDernier; if (!d) return;
  Object.assign(FN_STATE.mc, { modele: 'gbm', vol: 'fixe', volv: +(d.vol * 100).toFixed(4), drift: 'rn', horizon: Math.max(5, Math.round(d.jours * 252 / 365)),
    produit: d.type, strike: +(d.strike_pct * 100).toFixed(4), n: 100000, dividende: +(d.dividende * 100).toFixed(4) });
  FN_STATE.name = 'MC'; renderFn();
}

/* ============ OVDV 3D ============ */
function ovdv3d(d) {
  const Z = d.grid.vols.map(r => r.map(v => v === null ? null : v * 100));
  return surface3d('s3dOVDV', d.moneyness.map(k => Math.round(k * 100) + '%'), d.grid.days.map(j => Math.round(j) + ' j'), Z,
    { xtitle: 'Strike / spot', ytitle: 'Maturité', ztitle: 'Vol %', cmap: 'jet', clip: [0.01, 0.99], zfmt: v => v.toFixed(0) + '%', az: -2.45, el: 0.42,
      tip: (i, j, v) => `${Math.round(d.moneyness[j] * 100)} % du spot · ${Math.round(d.grid.days[i])} jours : <b>${v.toFixed(2)} %</b>` });
}

/* ============ GC3D : COURBE DES TAUX DANS LE TEMPS ============ */
FN_STATE.gc3dY = 5;
function fnGC3D(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const M = d.maturities, last = d.last, first = d.first, ix = l => M.indexOf(l);
  const bp = (a, b) => Math.round((a - b) * 100);
  let h = fnHeader('GC3D', `Courbe des taux du Trésor américain dans le temps · ${esc(d.dates[0])} → ${esc(d.dates[d.dates.length - 1])}`, `<span class="muted small">${esc(d.source)}</span>`);
  h += '<div class="fn-tools">' + [1, 2, 5, 10, 20].map(y => `<span class="rng ${FN_STATE.gc3dY === y ? 'on' : ''}" onclick="FN_STATE.gc3dY=${y};renderFn()">${y} A</span>`).join('') + '<span class="muted small" style="margin-left:auto">couleur = niveau du taux · une courbe par date</span></div>';
  h += '<div class="kpis">' + ['3 M', '2 A', '10 A', '30 A'].map(l => kpi(`${l} · var. période`, `${last[ix(l)].toFixed(2)} % <span class="${bp(last[ix(l)], first[ix(l)]) >= 0 ? 'neg' : 'pos'} small">${bp(last[ix(l)], first[ix(l)]) >= 0 ? '+' : ''}${bp(last[ix(l)], first[ix(l)])} pb</span>`)).join('')
    + kpi('Pente 2 A – 10 A', `${bp(last[ix('10 A')], last[ix('2 A')])} pb`, bp(last[ix('10 A')], last[ix('2 A')]) < 0 ? 'neg' : '') + '</div>';
  h += '<div class="panel"><div class="panel-b">' + surface3d('s3dGC3D', M, d.dates, d.yields, { xtitle: 'Maturité', ytitle: 'Date', ztitle: 'Taux %', cmap: 'jet', yfmt: s => String(s).slice(0, 7), zfmt: v => v.toFixed(1), az: -0.75, el: 0.45, height: 500,
    tip: (i, j, v) => `${esc(d.dates[i])} · ${esc(M[j])} : <b>${v.toFixed(2)} %</b>` }) + '</div></div>';
  h += '<div class="panel" style="margin-top:10px"><div class="panel-h">Courbe : début vs fin de période</div><div class="panel-b">' + lineChart('chGC3D', [{ name: `Aujourd’hui (${d.dates[d.dates.length - 1]})`, x: M, y: last, color: '#ff9900', width: 2 }, { name: `Début (${d.dates[0]})`, x: M, y: first, color: '#2979ff' }], { height: 220, yfmt: v => v.toFixed(2) + ' %' }) + '</div></div>';
  return h;
}

/* ============ BUDG : BUDGET FÉDÉRAL AMÉRICAIN ============ */
function budgBars(d) {
  const narrow = window.innerWidth < 760, W = narrow ? 460 : 1000, H = narrow ? 200 : 240, L = 50, R = 10, T = 10, B = 24;
  const v = d.balance, N = v.length, lo = Math.min(0, ...v) * 1.08, hi = Math.max(0.1, ...v) * 1.08, rec = new Set(d.recession_years);
  const X = i => L + i / N * (W - L - R), Y = x => T + (1 - (x - lo) / (hi - lo)) * (H - T - B), bw = (W - L - R) / N;
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  d.years.forEach((y, i) => { if (rec.has(y)) s += `<rect x="${X(i)}" y="${T}" width="${bw}" height="${H - T - B}" fill="#ff1744" opacity="0.08"/>`; });
  for (const t of niceTicks(lo, hi, 4)) s += `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" stroke="#1c1c1c"/><text x="${L - 6}" y="${Y(t) + 3}" fill="#666" font-size="10" text-anchor="end">${t.toFixed(1)}</text>`;
  v.forEach((x, i) => { s += `<rect x="${X(i) + 0.5}" y="${Math.min(Y(x), Y(0))}" width="${Math.max(0.6, bw - 1)}" height="${Math.abs(Y(x) - Y(0))}" fill="${x >= 0 ? '#00c853' : '#ff1744'}"><title>${d.years[i]} : ${x.toFixed(3)} T$</title></rect>`; });
  for (let k = 0; k < N; k += Math.ceil(N / 10)) s += `<text x="${X(k) + bw / 2}" y="${H - 8}" fill="#666" font-size="10" text-anchor="middle">${d.years[k]}</text>`;
  return s + `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="#555"/></svg>`;
}
function fnBUDG(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const n = d.years.length - 1, T = v => v.toFixed(2) + ' T$';
  let h = fnHeader('BUDG', `Budget fédéral américain · exercices ${d.years[0]} – ${d.years[n]}`, `<span class="muted small">${esc(d.source)}</span>`);
  h += '<div class="kpis">' + kpi(`Recettes ${d.years[n]}`, T(d.receipts[n])) + kpi(`Dépenses ${d.years[n]}`, T(d.outlays[n]))
    + kpi(`Solde ${d.years[n]}`, T(d.balance[n]), d.balance[n] < 0 ? 'neg' : 'pos') + kpi('Solde / PIB', d.balance_gdp[n] === null ? '—' : d.balance_gdp[n].toFixed(1) + ' %', 'neg')
    + kpi('Dépenses, var. sur 10 ans', sgn((d.outlays[n] / d.outlays[n - 10] - 1) * 100, 0) + '%') + '</div>';
  h += '<div class="panel"><div class="panel-h">Dépenses et recettes fédérales <span class="rt">milliers de milliards de dollars</span></div><div class="panel-b">'
    + lineChart('chBUDG', [{ name: 'Dépenses', x: d.years, y: d.outlays, color: '#ff9900', width: 2 }, { name: 'Recettes fiscales', x: d.years, y: d.receipts, color: '#e8e8e8', width: 1.6 }], { height: 300, yfmt: v => v.toFixed(1) + ' T' })
    + '</div></div>';
  h += '<div class="panel" style="margin-top:10px"><div class="panel-h">Excédent / déficit <span class="rt">fond rouge : année de récession (NBER)</span></div><div class="panel-b">' + budgBars(d) + '</div></div>';
  return h;
}

/* ============ MAC : INDICE BIG MAC (WCRS MAC) ============ */
FN_STATE.macAdj = false;
function fnMAC(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const adj = FN_STATE.macAdj, cle = adj ? 'ajuste' : 'brut';
  const rows = d.rows.filter(r => r[cle] !== null).sort((a, b) => b[cle] - a[cle]);
  const mx = Math.max(...rows.map(r => Math.abs(r[cle])));
  let h = fnHeader('WCRS MAC', `Parité de pouvoir d’achat · indice Big Mac du ${esc(d.date)} · base ${esc(d.base)}`, `<span class="muted small">${esc(d.source)}</span>`);
  h += '<div class="fn-tools">' + ['USD', 'EUR', 'GBP', 'JPY', 'CNY'].map(b => `<span class="rng ${d.base === b ? 'on' : ''}" onclick="FN_STATE.sym='${b}';renderFn()">${b}</span>`).join('')
    + `<span class="rng ${adj ? '' : 'on'}" style="margin-left:14px" onclick="FN_STATE.macAdj=false;renderFn()">BRUT</span><span class="rng ${adj ? 'on' : ''}" onclick="FN_STATE.macAdj=true;renderFn()">AJUSTÉ DU PIB</span>`
    + '<span class="muted small" style="margin-left:auto">positif = devise surévaluée face à la base</span></div>';
  h += '<div class="grid g-main"><div class="panel"><div class="panel-b">';
  for (const r of rows) h += barRow(`${r.devise} · ${r.pays}`, r[cle], mx);
  h += '</div></div><div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Pays</th><th class="num">Prix local</th><th class="num">Prix $</th><th class="num">Brut</th><th class="num">Ajusté</th><th class="num">Var. 6 mois</th></tr>';
  for (const r of rows) {
    const dv = r.brut_precedent === null ? null : (r.brut - r.brut_precedent) * 100;
    h += `<tr><td>${esc(r.pays)} <span class="muted small">${esc(r.devise)}</span></td><td class="num">${r.prix_local.toLocaleString('fr-FR')}</td><td class="num">${r.prix_usd.toFixed(2)}</td>${pctCell(r.brut, 1)}${r.ajuste === null ? '<td class="num muted">—</td>' : pctCell(r.ajuste, 1)}<td class="num ${dv === null ? 'muted' : dv >= 0 ? 'pos' : 'neg'}">${dv === null ? '—' : (dv >= 0 ? '+' : '') + dv.toFixed(1) + ' pt'}</td></tr>`;
  }
  h += '</table><div class="muted small" style="margin:6px">Brut : écart entre le prix du Big Mac converti au change du marché et son prix dans le pays de base. Ajusté : corrigé du PIB par habitant (les pays riches ont des prix plus élevés).</div></div></div></div>';
  return h;
}

/* ============ ILBE : INFLATION ANTICIPÉE (ÉTATS-UNIS) ============ */
function fnILBE(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const k = d.kpi, ch = (o, key) => { const v = Math.round((o.now - o[key]) * 100); return `<span class="small ${v >= 0 ? 'neg' : 'pos'}">${v >= 0 ? '+' : ''}${v} pb</span>`; };
  let h = fnHeader('ILBE', `Inflation anticipée par le marché · États-Unis · ${esc(d.date)}`, `<span class="muted small">${esc(d.source)}</span>`);
  h += '<div class="kpis">' + kpi('Point mort 5 ans', `${k.be5.now.toFixed(2)} % ${ch(k.be5, 'm1')}`) + kpi('Point mort 10 ans', `${k.be10.now.toFixed(2)} % ${ch(k.be10, 'm1')}`)
    + kpi('Forward 5 ans dans 5 ans', `${k.fwd5y5y.now.toFixed(2)} % ${ch(k.fwd5y5y, 'm1')}`) + kpi('10 ans nominal', `${k.dgs10.now.toFixed(2)} %`)
    + kpi('10 ans réel (TIPS)', `${k.tips10.now.toFixed(2)} % ${ch(k.tips10, 'y1')}`) + kpi(`Inflation réalisée (${esc(k.cpi.date.slice(0, 7))})`, `${k.cpi.now.toFixed(2)} %`) + '</div>';
  h += '<div class="muted small" style="margin:-4px 0 8px">Variations sur 1 mois (sur 1 an pour le taux réel). Point mort = rendement nominal − rendement TIPS : l’inflation moyenne que le marché anticipe. Nominal = réel + point mort.</div>';
  h += '<div class="panel"><div class="panel-h">Points morts d’inflation · 10 ans <span class="rt">ligne pointillée : cible de 2 % de la Fed</span></div><div class="panel-b">'
    + lineChart('chILBE', [{ name: '5 ans', x: d.dates, y: d.be5, color: '#ff9900', width: 1.8 }, { name: '10 ans', x: d.dates, y: d.be10, color: '#2979ff', width: 1.6 }, { name: '5 ans dans 5 ans', x: d.dates, y: d.fwd5y5y, color: '#00c853', width: 1.3 }], { height: 280, zero: 2, yfmt: v => v.toFixed(2) + ' %' })
    + '</div></div>';
  h += '<div class="panel" style="margin-top:10px"><div class="panel-h">Inflation réalisée (CPI, sur un an)</div><div class="panel-b">'
    + lineChart('chILBEcpi', [{ name: 'CPI', x: d.cpi_dates, y: d.cpi_yoy, color: '#e040fb', width: 1.8, area: true }], { height: 200, zero: 2, yfmt: v => v.toFixed(1) + ' %' }) + '</div></div>';
  return h;
}
