/* Gambit Ridge Capital — terminal : 12-requetes.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ BQL : LANGAGE DE REQUÊTE (GRQL) ET API EXCEL ============ */
const BQL_EXEMPLES = [
  ['Performance et risque des Magnificent 7', "get(name, px_last, return(1y), volatility(1y), sharpe(1y), max_drawdown(1y))\nfor(members('MAG7'))"],
  ['Variables let() : rendement par unité de risque', "let(#perf = return(1y); #risque = volatility(1y);)\nget(name, #perf, #risque, #perf / #risque)\nfor(members('ETF'))"],
  ['Filtre : ETF du fonds peu volatils et en hausse', "get(name, return(6m), volatility(1y))\nfor(filter(members('ETF'), volatility(1y) < 0.15 and return(6m) > 0))"],
  ['Top 10 rendement FCF parmi les « valeur »', "get(name, market_cap, pe_ratio, fcf_yield, roe)\nfor(top(screen('valeur'), fcf_yield, 10))"],
  ['Série de cours sur 3 mois, en euros', "get(px_last)\nfor(['AAPL US Equity', 'MSFT US Equity', 'GOOGL US Equity'])\nwith(dates = range(-3m, 0d), currency = 'EUR')"],
  ['Bêta et corrélation au S&P 500', "get(beta('SPY', 2y), correlation('SPY', 2y), volatility(2y))\nfor(['TLT', 'GLD', 'BTC', 'QQQ', 'EEM'])"],
  ['Techniques : moyennes, RSI, plus haut / bas', "get(px_last, sma(50), sma(200), px_last / sma(200) - 1, rsi(14), high(1y), low(1y))\nfor(members('MAG7'))"],
];
FN_STATE.bql = FN_STATE.bql || { q: BQL_EXEMPLES[0][1], vue: 'resultat' };

function bqlCellule(v) {
  if (v === null || v === undefined) return '<td class="num muted">—</td>';
  if (typeof v === 'boolean') return `<td class="num ${v ? 'pos' : 'neg'}">${v ? 'vrai' : 'faux'}</td>`;
  if (typeof v === 'string') return `<td>${esc(v)}</td>`;
  const a = Math.abs(v);
  const txt = a >= 1e9 ? md(v) : a >= 1000 ? v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) : a >= 1 ? v.toFixed(2) : v.toFixed(4);
  return `<td class="num">${txt}</td>`;
}

async function bqlLancer(texte) {
  const ta = document.getElementById('bqlTexte');
  if (texte !== undefined) { FN_STATE.bql.q = texte; if (ta) ta.value = texte; }  // exemple cliqué
  else if (ta) FN_STATE.bql.q = ta.value;
  FN_STATE.bql.vue = 'resultat';
  renderFn();
}

function bqlEditeur() {
  const st = FN_STATE.bql;
  let h = `<div class="bql-editeur"><textarea id="bqlTexte" spellcheck="false" onkeydown="if((event.metaKey||event.ctrlKey)&&event.key==='Enter'){event.preventDefault();bqlLancer()}">${esc(st.q)}</textarea>`;
  h += '<div class="bql-actions"><button class="btn" onclick="bqlLancer()">EXÉCUTER &lt;GO&gt;</button><span class="muted small">Ctrl / ⌘ + Entrée</span>'
    + `<span class="rng ${st.vue === 'resultat' ? 'on' : ''}" style="margin-left:auto" onclick="FN_STATE.bql.vue='resultat';renderFn()">RÉSULTAT</span>`
    + `<span class="rng ${st.vue === 'champs' ? 'on' : ''}" onclick="FN_STATE.bql.q=document.getElementById('bqlTexte').value;FN_STATE.bql.vue='champs';renderFn()">CHAMPS</span>`
    + `<span class="rng ${st.vue === 'excel' ? 'on' : ''}" onclick="FN_STATE.bql.q=document.getElementById('bqlTexte').value;FN_STATE.bql.vue='excel';renderFn()">EXCEL</span></div></div>`;
  h += '<div class="fn-tools">' + BQL_EXEMPLES.map(([l], i) => `<span class="rng" onclick="bqlLancer(BQL_EXEMPLES[${i}][1])">${esc(l)}</span>`).join('') + '</div>';
  return h;
}

async function fnBQL() {
  const st = FN_STATE.bql;
  let h = fnHeader('BQL <span class="muted">Langage de requête</span>', 'let() · get() · for() · with() — syntaxe de =BQL.Query', '<span class="muted small">GRQL, sur les données du terminal</span>') + bqlEditeur();
  const base = location.origin;
  if (st.vue === 'champs') return h + bqlChamps();
  if (st.vue === 'excel') return h + bqlExcel(base);
  let d;
  try { d = await (await fetch('/api/grql?q=' + encodeURIComponent(st.q))).json(); } catch (e) { d = { error: e.message }; }
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const nErr = Object.keys(d.erreurs).length;
  h += `<div class="muted small" style="margin:0 0 6px">${d.n} titre(s) · fenêtre ${esc(d.fenetre[0])} → ${esc(d.fenetre[1])}${d.devise ? ' · en ' + esc(d.devise) : ''} · ${d.ms} ms`
    + ` · <a class="lnk" href="/api/grql?format=csv&q=${encodeURIComponent(st.q)}" target="_blank">CSV ›</a> · <a class="lnk" onclick="navigator.clipboard.writeText('${base}/api/grql?format=csv&q=' + encodeURIComponent(FN_STATE.bql.q));this.textContent='URL copiée ✓'">copier l’URL pour Excel</a></div>`;
  let t = '<table><tr><th>ID</th>' + d.colonnes.map(c => `<th class="num" title="${esc(c)}">${esc(c.length > 28 ? c.slice(0, 27) + '…' : c)}</th>`).join('') + '</tr>';
  for (const l of d.lignes) t += `<tr><td class="amber">${esc(l.id)}${d.erreurs[l.id] ? ` <span class="neg small" title="${esc(d.erreurs[l.id])}">⚠</span>` : ''}</td>` + l.valeurs.map(bqlCellule).join('') + '</tr>';
  h += `<div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto">${t}</table></div></div>`;
  for (const [lab, s] of Object.entries(d.series)) {
    const ids = Object.keys(s.par_id);
    h += pan(esc(lab), `${s.dates.length} dates`, lineChart('chBQL' + lab.length, ids.map((id, i) => ({ name: id, x: s.dates, y: s.par_id[id].map(v => v === null ? NaN : v), color: SERIES_COLORS[i % SERIES_COLORS.length], width: 1.6 })), { height: 260, yfmt: v => fmtPx(v) }), 'margin-top:10px');
  }
  if (nErr) h += `<div class="muted small" style="margin:6px 2px">⚠ ${Object.entries(d.erreurs).map(([k, v]) => `${esc(k)} : ${esc(v)}`).join(' · ')}</div>`;
  return h;
}

function bqlChamps() {
  const c = { 'Marché': ['px_last', 'return(1y)', 'volatility(1y)', 'max_drawdown(1y)', 'sharpe(1y)', "beta('SPY', 1y)", "correlation('SPY', 1y)", 'sma(50)', 'rsi(14)', 'high(1y)', 'low(1y)', 'market_cap', 'name'],
    'Fondamentaux (SEC : dernière année civile complète, sociétés US ≥ 1 Md$ de CA ; la fiche FA, elle, utilise les 12 derniers mois)': ['pe_ratio', 'pb_ratio', 'ps_ratio', 'fcf_yield', 'roe', 'net_margin', 'oper_margin', 'sales_growth', 'debt_to_equity', 'ev_to_ebit', 'sales', 'net_income'],
    'Univers — for()': ["['AAPL', 'MSFT']", "['AAPL US Equity', 'SPX Index', 'EURUSD Curncy']", "members('ETF') · members('CRYPTO') · members('MAG7')", "screen('valeur' | 'qualite' | 'croissance' | 'fcf' | 'geants')", 'filter(univers, condition)', "top(univers, expression, 10, 'desc')"],
    'Paramètres — with()': ['dates = range(-1y, 0d)', "dates = range('2024-01-01', '2024-12-31')", "currency = 'EUR'"],
    'Opérations': ['+ − × ÷', '< > <= >= == !=', 'and · or · not', 'abs(x) · round(x, 2) · min(a, b) · max(a, b)', 'let(#x = expression;) puis #x dans get()'] };
  let h = '<div class="grid g-main">';
  for (const [t, l] of Object.entries(c)) h += pan(esc(t), '', '<div style="padding:4px 8px;line-height:1.9">' + l.map(x => `<code class="amber">${esc(x)}</code>`).join('<br>') + '</div>');
  return h + '</div>' + noteBas('Durées : d (jours), w (semaines), m (mois), y (années). Sans with(dates=…), la fenêtre est d’un an et px_last renvoie le dernier cours ; avec, il renvoie la série. Les erreurs d’un titre n’arrêtent pas la requête : elles s’affichent sous le tableau.');
}

function bqlExcel(base) {
  const ex = (u) => `<code class="amber" style="user-select:all">${esc(u)}</code>`;
  let h = '<div class="grid g-main">';
  h += pan('Dans une cellule (Excel Windows)', '=WEBSERVICE', `<div style="padding:6px 10px;line-height:2">
    Une valeur, comme <b>BDP</b> :<br>${ex(`=WEBSERVICE("${base}/api/bdp?s=AAPL&f=pe_ratio")`)}<br>
    Avec une référence de cellule :<br>${ex(`=WEBSERVICE("${base}/api/bdp?s="&A2&"&f="&B1)`)}<br>
    Champs utilisables dans f : tous ceux du langage (px_last, return(1y), roe…).<br>
    <span class="muted small">WEBSERVICE n’existe pas dans Excel pour Mac : utiliser Power Query (ci-contre).</span></div>`);
  h += pan('Tableaux et séries (Excel Mac et Windows)', 'Power Query', `<div style="padding:6px 10px;line-height:2">
    Excel → <b>Données</b> → <b>À partir du web</b> (ou « Obtenir des données » → « Web »), puis coller :<br>
    Série, comme <b>BDH</b> :<br>${ex(`${base}/api/bdh?s=SPY&f=px_last&debut=-1y&fin=0d`)}<br>
    Requête complète, en CSV :<br>${ex(`${base}/api/grql?format=csv&q=` + encodeURIComponent(FN_STATE.bql.q))}<br>
    <b>Actualiser tout</b> (Données) remet les chiffres à jour.</div>`);
  h += '</div>';
  h += pan('Complément Gambit Ridge : la syntaxe Bloomberg', 'excel/GambitRidge.xlam', `<div style="padding:6px 10px;line-height:2">
    Mêmes fonctions et mêmes mnémoniques que le complément Bloomberg, Windows et Mac :<br>
    ${ex('=BDP("AAPL US Equity"; "PX_LAST")')} · ${ex('=BDP("AAPL US Equity"; "PE_RATIO")')}<br>
    ${ex('=BDH("SPY US Equity"; "PX_LAST"; "20240101"; ""; "Per=W")')} · ${ex('=BDH(A2; B1:D1; "-1Y")')}<br>
    ${ex('=BDS("AAPL US Equity"; "DVD_HIST_ALL")')} · ${ex('=BDS("SPY US Equity"; "OPT_CHAIN")')}<br>
    ${ex(`=BQL("members('MAG7')"; "px_last")`)} · ${ex(`=BQL("get(px_last) for(['AAPL'])")`)}<br>
    Unités Bloomberg (%, millions). Champs payants (consensus, notations, CDS…) : « #N/A Field Not Available ».
    Macros : <b>GRC_Actualiser</b> (recalcul, comme Refresh) et <b>GRC_Configurer</b> (adresse du terminal).</div>`, 'margin-top:10px');
  return h + noteBas(`L’adresse ${esc(base)} est celle du terminal : sur le Mac, le tunnel vers le serveur ; sur un autre appareil du réseau Tailscale, l’adresse Tailscale. Le serveur n’est jamais exposé sur Internet, donc Google Sheets (qui interroge depuis les serveurs de Google) ne peut pas l’atteindre. Lecture seule : aucune requête ne modifie le portefeuille.`);
}
