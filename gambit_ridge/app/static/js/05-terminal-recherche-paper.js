/* Gambit Ridge Capital — terminal : 05-terminal-recherche-paper.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ TERMINAL ============ */
async function render() {
  const c = document.getElementById('content');
  if (!PAPER) {
    c.innerHTML = '<div class="loader">Chargement du portefeuille…</div>';
    try { PAPER = await (await fetch('/api/paper')).json(); } catch(e) { PAPER = null; }
  }
  if (!MARKET) await fetchMarket();
  if (currentTab !== 'terminal') return;
  const d = PAPER && !PAPER.loading && !PAPER.error ? PAPER : null;
  let html = '';
  if (d) {
    html += '<div class="kpis">';
    html += kpi('Équity', fmtM(d.equity));
    html += kpi('P&L depuis le départ', sgn(d.total_return*100,2)+'%', d.total_return>=0?'pos':'neg');
    html += kpi('Drawdown', fmtPct(d.current_drawdown,2), d.current_drawdown>0.05?'neg':'');
    html += kpi('Exposition brute / nette', fmtPct(d.gross,0)+' / '+fmtPct(d.net,0));
    html += kpi('Positions', String(d.positions.length));
    html += kpi('Jours suivis', String(d.n_days));
    html += '</div>';
  }
  html += '<div class="grid g-main">';
  // colonne gauche : courbe + expositions
  html += '<div class="panel"><div class="panel-h">Portefeuille papier <span class="rt">' + esc(d ? d.strategy : '') + '</span></div><div class="panel-b">';
  if (d && d.equity_history.length > 1) {
    html += lineChart('chTermEq', [{ name: 'Équity', x: d.equity_history.map(h=>h.date), y: d.equity_history.map(h=>h.equity), color: '#ff9900', area: true }], { height: 200, zero: d.initial_capital, yfmt: v => (v/1e6).toFixed(3)+' M$' });
  } else html += '<div class="muted" style="padding:10px 4px 4px">Premier jour du nouveau portefeuille — la courbe réelle apparaîtra dès demain.</div>';
  if (d && d.equity_history.length < 20) html += await backtestPreview('chTermBt');
  if (d) {
    const ex = d.exposure_by_class, mx = Math.max(...Object.values(ex).map(Math.abs), 0.01);
    html += '<div class="sub-h">Exposition nette par classe d’actifs</div>';
    for (const cl of CLASS_ORDER) if (ex[cl] !== undefined) html += barRow(cl, ex[cl], mx);
  }
  html += '</div></div>';
  // colonne droite : marchés
  html += '<div class="panel"><div class="panel-h">Marchés <span class="rt">clôtures réelles · ' + esc(MARKET && MARKET[0] ? MARKET[0].date : '') + '</span></div><div class="panel-b" style="padding:4px"><table>';
  html += '<tr><th>Actif</th><th class="num">Dernier</th><th class="num">1 j</th><th class="num">1 m</th><th class="num">YTD</th></tr>';
  for (const cl of CLASS_ORDER) {
    const rows = (MARKET || []).filter(a => a.asset_class === cl);
    if (!rows.length) continue;
    html += `<tr><td colspan="5" class="cls-row">${esc(cl)}</td></tr>`;
    for (const a of rows) html += `<tr title="${esc(a.name)}"><td><span class="amber">${esc(a.symbol.replace('-USD',''))}</span> <span class="muted small">${esc(a.name)}</span></td><td class="num">${fmtPx(a.last)}</td>${pctCell(a.chg_1d,2)}${pctCell(a.chg_1m)}${pctCell(a.chg_ytd)}</tr>`;
  }
  html += '</table></div></div>';
  html += '</div>';

  // Conseil des agents (simulation)
  if (STATE && STATE.briefing) {
    const b = STATE.briefing;
    const src = STATE.data_sources || {}, nReal = Object.values(src).filter(v => v === 'yahoo').length, nAll = Object.keys(src).length;
    html += '<div class="sim-banner">CONSEIL DES AGENTS — prix réels (Yahoo) sur ' + (nAll ? nReal + '/' + nAll : '—') + ' actifs suivis · leurs signaux sont des <b>pistes de recherche</b> : ils ne pilotent PAS le portefeuille, seule la stratégie validée le fait.</div>';
    html += '<div class="grid" style="grid-template-columns:1fr 1fr">';
    html += '<div class="panel"><div class="panel-h">Briefing exécutif <span class="rt">'+(b.executive? (b.executive.source==='mistral'?'IA':'local'):'')+'</span></div><div class="panel-b exec">';
    if (b.executive) for (const p of b.executive.text.split(/\n\n+|\s\|\s/).filter(x=>x.trim())) html += `<p>${esc(p.trim())}</p>`;
    html += '</div></div>';
    html += '<div class="panel"><div class="panel-h">Synthèses des équipes</div><div class="panel-b" style="padding:4px"><table>';
    html += '<tr><th>Équipe</th><th>Headline</th><th class="num">Score</th></tr>';
    for (const t of b.teams) html += `<tr><td class="amber">${esc(t.team)}</td><td>${esc(t.headline)}</td><td class="num">${sgn(t.aggregate_score,2)}</td></tr>`;
    html += '</table></div></div></div>';
  }
  c.innerHTML = html;
}
function kpi(l, v, cls) { return `<div class="kpi"><div class="l">${l}</div><div class="v ${cls||''}">${v}</div></div>`; }

/* ============ RECHERCHE ============ */
async function renderResearch() {
  const c = document.getElementById('content');
  if (!RESEARCH) {
    c.innerHTML = '<div class="loader">Chargement du banc d’évaluation…</div>';
    try { RESEARCH = await (await fetch('/api/research')).json(); } catch(e) { RESEARCH = { error: 'serveur injoignable' }; }
  }
  if (RESEARCH.error) { c.innerHTML = `<div class="loader neg">${esc(RESEARCH.error)}</div>`; return; }
  const R = RESEARCH, uni = RS_SEL && RS_SEL.uni || 'etf';
  const res = R[uni], keyRet = R[uni + '_retenue'];
  if (!RS_SEL || !RS_SEL.shown) RS_SEL = { uni, shown: new Set([keyRet, Object.keys(res).find(n => res[n].famille === 'benchmark' && /60\/40|Bitcoin/.test(n)), Object.keys(res).find(n => /Ridge|Crypto regime/.test(n))].filter(Boolean)) };
  const P = R.protocole, U = R[uni + '_univers'];
  let html = '<div class="seg">' + ['etf','crypto'].filter(k => R[k]).map(k => `<div class="seg-i ${k===uni?'active':''}" onclick="RS_SEL={uni:'${k}'};renderResearch()">${k==='etf'?'Univers ETF (20 actifs)':'Crypto (7 actifs)'}</div>`).join('') + '</div>';
  const r = res[keyRet];
  html += `<div class="verdict"><div class="v-t">STRATÉGIE RETENUE</div><div class="v-n">${esc(keyRet)}</div><div class="v-d">${esc(r.description)}</div>`;
  html += `<div class="v-k">${kpi('Sharpe développement', r.developpement.sharpe.toFixed(2))}${kpi('Sharpe validation', r.validation.sharpe.toFixed(2), r.validation.sharpe>0?'pos':'neg')}${kpi('CAGR validation', fmtPct(r.validation.cagr,1))}${kpi('Max drawdown validation', fmtPct(r.validation.max_dd,1), 'neg')}${kpi('Deflated Sharpe', fmtPct(r.dsr_developpement,0), r.dsr_developpement>0.9?'pos':'')}${r.cagr_risque_egal&&r.cagr_risque_egal.val!==undefined?kpi('CAGR à risque égal ('+esc((r.reference_risque||'').replace('Benchmark — ',''))+')', fmtPct(r.cagr_risque_egal.val,1)+' <span class="muted small">vs '+fmtPct(res[r.reference_risque].validation.cagr,1)+'</span>'):''}</div></div>`;
  html += `<div class="muted small proto">Protocole figé : sélection sur la période de <b>développement</b> (${esc(U.debut)} → ${esc(uni==='etf'?P.dev_fin:P.crypto_dev_fin)}) uniquement ; la période de <b>validation</b> (jusqu’au ${esc(U.fin)}) n’a servi à aucun choix. Coûts ${uni==='etf'?P.couts_bps.etf:P.couts_bps.crypto} bps par unité de turnover, rebalancement ${esc(P.rebalancement)}, dérive des poids modélisée. Deflated Sharpe = probabilité que le Sharpe soit réel compte tenu du nombre de stratégies testées (Bailey & López de Prado).</div>`;
  // courbes
  const names = Object.keys(res).filter(n => RS_SEL.shown.has(n)).sort((a, b) => (b === keyRet) - (a === keyRet));
  const others = ['#e040fb','#00e5ff','#ffea00','#ff1744','#8d6e63','#9e9e9e','#00c853'];
  let oi = 0;
  const colorOf = n => n === keyRet ? '#ff9900' : n === r.reference_risque ? '#2979ff' : others[oi++ % others.length];
  const series = names.map(n => ({ name: n, x: res[n].courbe.dates, y: res[n].courbe.equity, color: colorOf(n), width: n === keyRet ? 2.2 : 1.3 }));
  html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Courbes de capital <span class="rt">échelle log · base 1 · coche les stratégies dans le tableau</span></div><div class="panel-b">';
  const split = res[keyRet].courbe.dates.findIndex(dt => dt > (uni==='etf'?P.dev_fin:P.crypto_dev_fin));
  html += lineChart('chResearch', series, { log: true, height: 300, zero: 1, yfmt: v => v.toFixed(2) + '×', marker: split, markerLabel: 'VALIDATION →' });
  if (split > 0) html += `<div class="legend2">Zone orangée = validation : aucune donnée à droite du trait n’a servi à choisir la stratégie.</div>`;
  html += '</div></div>';
  // tableau
  html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Toutes les stratégies testées <span class="rt">' + Object.keys(res).length + ' essais</span></div><div class="panel-b" style="padding:4px;overflow-x:auto"><table class="rs-table">';
  html += '<tr><th></th><th>Stratégie</th><th>Famille</th><th class="num">Sharpe dév.</th><th class="num">Max DD dév.</th><th class="num">DSR</th><th class="num sep">Sharpe valid.</th><th class="num">CAGR valid.</th><th class="num">Max DD valid.</th><th class="num" title="CAGR en validation si la stratégie avait le même risque que la référence">CAGR à risque égal</th><th class="num">Turnover/an</th><th class="num">Coûts/an</th></tr>';
  const fam = { benchmark: 'Référence', existant: 'Première version (v1)', nouveau: 'Nouveau' };
  for (const [n, x] of Object.entries(res)) {
    const dv = x.developpement, va = x.validation;
    html += `<tr class="${n===keyRet?'row-win':''}" title="${esc(x.description)}"><td><input type="checkbox" ${RS_SEL.shown.has(n)?'checked':''} onchange="toggleRS(${JSON.stringify(n).replace(/"/g,'&quot;')})"></td><td class="${n===keyRet?'amber':''}">${n===keyRet?'★ ':''}${esc(n)}</td><td class="muted">${fam[x.famille]||x.famille}</td><td class="num ${dv.sharpe>=0?'pos':'neg'}">${dv.sharpe.toFixed(2)}</td><td class="num neg">${fmtPct(dv.max_dd,1)}</td><td class="num">${fmtPct(x.dsr_developpement,0)}</td><td class="num sep ${va.sharpe>=0?'pos':'neg'}">${va.sharpe.toFixed(2)}</td>${pctCell(va.cagr)}<td class="num neg">${fmtPct(va.max_dd,1)}</td><td class="num">${x.cagr_risque_egal&&x.cagr_risque_egal.val!==undefined?fmtPct(x.cagr_risque_egal.val,1):'—'}</td><td class="num muted">${(va.turnover_annuel||0).toFixed(1)}×</td><td class="num muted">${fmtPct(va.couts_annuels||0,2)}</td></tr>`;
  }
  html += '</table></div></div>';
  if (uni === 'etf' && R.carry) {
    const K = R.carry;
    html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Essai : carry de change G10 <span class="rt">' + esc(K.debut) + ' → ' + esc(K.fin) + '</span></div><div class="panel-b" style="padding:4px">';
    html += `<div class="${/REJET/.test(K.verdict) ? 'neg' : 'amber'}" style="margin:4px 6px 8px">${esc(K.verdict)}</div><table><tr><th>Variante</th><th class="num">Sharpe dév.</th><th class="num">Max DD dév.</th><th class="num sep">Sharpe valid.</th><th class="num">CAGR valid.</th></tr>`;
    for (const [n, x] of Object.entries(K.resultats)) html += `<tr><td>${esc(n)}</td><td class="num">${x.developpement.sharpe.toFixed(2)}</td><td class="num neg">${fmtPct(x.developpement.max_dd,1)}</td><td class="num sep">${x.validation.sharpe.toFixed(2)}</td>${pctCell(x.validation.cagr)}</tr>`;
    html += `</table><div class="muted small" style="margin:6px">${esc(K.methode)}</div></div></div>`;
  }
  c.innerHTML = html;
}
function toggleRS(n) { if (RS_SEL.shown.has(n)) RS_SEL.shown.delete(n); else RS_SEL.shown.add(n); renderResearch(); }

/* ============ PAPER TRADING ============ */
async function renderPaper() {
  const c = document.getElementById('content');
  if (!PAPER || PAPER.loading) {
    const t0 = Date.now();
    c.innerHTML = '<div class="loader" id="paperLoader">Calcul du portefeuille du jour (prix Yahoo + modèles GARCH/Kalman : ~20 s)…</div>';
    const timer = setInterval(() => { const el = document.getElementById('paperLoader'); if (el) el.textContent = 'Calcul du portefeuille du jour… ' + Math.round((Date.now()-t0)/1000) + ' s'; }, 1000);
    try { PAPER = await (await fetch('/api/paper')).json(); }
    catch(e) { PAPER = null; c.innerHTML = '<div class="loader neg">Connexion perdue — réessaie dans un instant.</div>'; return; }
    finally { clearInterval(timer); }
    if (PAPER.loading) { setTimeout(() => { if (currentTab==='paper') { PAPER = null; renderPaper(); } }, 5000); }
  }
  if (currentTab !== 'paper') return;
  if (PAPER.loading) { c.innerHTML = '<div class="loader">Le serveur calcule les positions du jour… actualisation automatique.</div>'; return; }
  if (PAPER.error) { c.innerHTML = '<div class="loader neg">Erreur : ' + esc(PAPER.error) + '</div>'; return; }
  if (PAPER.warning) { c.innerHTML = '<div class="loader neg">' + esc(PAPER.warning) + '</div>'; return; }
  const d = PAPER;
  let html = '<div class="kpis">';
  html += kpi('Capital initial', fmtM(d.initial_capital));
  html += kpi('Équity', fmtM(d.equity));
  html += kpi('P&L total', sgn(d.total_return*100,2)+'%', d.total_return>=0?'pos':'neg');
  html += kpi('Drawdown courant', fmtPct(d.current_drawdown,2), d.current_drawdown>0.05?'neg':'');
  html += kpi('Coûts payés', (d.costs_paid/1e3).toFixed(1)+' k$');
  html += kpi('Sharpe annualisé', d.sharpe_annualized===null?'<span class="muted">dès 20 j</span>':d.sharpe_annualized.toFixed(2));
  html += '</div>';
  html += '<div class="fn-tools"><span class="muted small">Dernière séance traitée : ETF ' + esc((d.last_price_dates||{}).etf || '—') + ' · crypto ' + esc((d.last_price_dates||{}).crypto || '—') + '</span><span style="margin-left:auto"></span><a class="btn" style="text-decoration:none;padding:5px 12px" href="/report" target="_blank">RAPPORT MENSUEL (PDF)</a></div>';
  const xc = Object.values(d.crosscheck || {}).flat().filter(x => /gelée/.test(x));
  if (xc.length) html += '<div class="sim-banner neg">⚠ Contrôle croisé Yahoo / Alpaca : ' + esc(xc.join(' · ')) + '</div>';
  if (d.quality && Object.values(d.quality).some(x => x.length)) html += '<div class="sim-banner neg">⚠ Contrôle qualité des données : ' + esc(Object.values(d.quality).flat().join(' · ')) + (d.blocked && d.blocked.length ? ' — rebalancement suspendu sur ' + d.blocked.length + ' lignes, positions conservées.' : '') + '</div>';
  html += '<div class="grid g-main">';
  html += '<div class="panel"><div class="panel-h">Équity <span class="rt">' + esc(d.strategy) + '</span></div><div class="panel-b">';
  if (d.equity_history.length > 1) {
    const h = d.equity_history;
    html += lineChart('chPaperEq', [{ name: 'Équity', x: h.map(e=>e.date), y: h.map(e=>e.equity), color: '#ff9900', area: true }], { height: 220, zero: d.initial_capital, yfmt: v => (v/1e6).toFixed(3)+' M$' });
    html += '<div class="sub-h">Drawdown</div>';
    html += lineChart('chPaperDD', [{ name: 'Drawdown', x: h.map(e=>e.date), y: h.map(e=>-e.drawdown*100), color: '#ff1744', area: true }], { height: 90, zero: 0, yfmt: v => v.toFixed(1)+'%' });
  } else html += '<div class="muted" style="padding:10px 4px 4px">Portefeuille démarré le ' + esc(d.started || '') + ' — la courbe réelle apparaîtra dès le prochain jour de marché.</div>';
  if (d.equity_history.length < 20) html += await backtestPreview('chPaperBt');
  html += '</div></div>';
  html += '<div class="panel"><div class="panel-h">Exposition <span class="rt">brute ' + fmtPct(d.gross,0) + ' · nette ' + fmtPct(d.net,0) + '</span></div><div class="panel-b">';
  const ex = d.exposure_by_class, mx = Math.max(...Object.values(ex).map(Math.abs), 0.01);
  for (const cl of CLASS_ORDER) if (ex[cl] !== undefined) html += barRow(cl, ex[cl], mx);
  html += '<div class="muted small" style="margin-top:10px">90 % du capital : socle 27 % S&P 500 + 18 % Treasuries 7-10 ans, plus une couche tendance (long ou short) à 10 % de volatilité cible. 10 % : crypto, tendance long-only, cash quand le signal est négatif.</div>';
  html += '</div></div></div>';
  // positions par classe
  html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Positions <span class="rt">' + d.positions.length + ' lignes · signal = moyenne TSMOM / EWMA / Kalman dans [-1, 1]</span></div><div class="panel-b" style="padding:4px;overflow-x:auto"><table>';
  html += '<tr><th>Actif</th><th>Sens</th><th class="num">Poids</th><th class="num">dont socle</th><th class="num">Valeur</th><th class="num">Signal</th><th class="num">Vol prévue</th><th class="num">Dernier prix</th><th class="num">Rdt dernier jour</th><th>Depuis</th></tr>';
  for (const cl of CLASS_ORDER) {
    const rows = d.positions.filter(p => p.asset_class === cl);
    if (!rows.length) continue;
    html += `<tr><td colspan="10" class="cls-row">${esc(cl)} <span class="muted">· net ${sgn((ex[cl]||0)*100,1)}%</span></td></tr>`;
    for (const p of rows) {
      const sigW = Math.min(100, Math.abs(p.signal||0)*100);
      html += `<tr><td><span class="amber">${esc(p.ticker.replace('-USD',''))}</span> <span class="muted small">${esc(p.name)}</span></td><td class="${p.weight>=0?'pos':'neg'}">${p.weight>=0?'▲ LONG':'▼ SHORT'}</td><td class="num">${sgn(p.weight*100,1)}%</td><td class="num muted">${p.core?fmtPct(p.core,0):''}</td><td class="num">${fmtM(Math.abs(p.value))}</td><td class="num"><span class="sigbar"><span class="${(p.signal||0)>=0?'up':'dn'}" style="width:${sigW}%"></span></span> ${p.signal===null||p.signal===undefined?'—':sgn(p.signal,2)}</td><td class="num muted">${p.vol?fmtPct(p.vol,0):'—'}</td><td class="num">${p.last_price?fmtPx(p.last_price):'—'}</td>${pctCell(p.last_return||0,2)}<td class="muted">${esc(p.entry_date||'')}</td></tr>`;
    }
  }
  html += '</table></div></div>';
  html += await attributionPanel();
  html += await brokerPanel();
  if (currentTab !== 'paper') return;
  // trades
  html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Trades récents <span class="rt">filtre anti micro-trades : on ne bouge une ligne que si l’écart dépasse 25 % de la cible</span></div><div class="panel-b" style="padding:4px"><table><tr><th>Date</th><th>Actif</th><th>Poche</th><th class="num">Avant</th><th class="num">Après</th></tr>';
  for (const t of d.recent_trades.slice(-20).reverse()) html += `<tr><td class="muted">${esc(t.date)}</td><td class="amber">${esc(t.ticker)}</td><td class="muted">${esc(t.kind)}</td><td class="num">${sgn(t.old_weight*100,1)}%</td><td class="num ${t.new_weight>=0?'pos':'neg'}">${sgn(t.new_weight*100,1)}%</td></tr>`;
  html += '</table></div></div>';
  if (d.errors && Object.keys(d.errors).length) html += '<div class="neg small" style="margin:8px 0">⚠ ' + esc(Object.values(d.errors).join(' · ')) + '</div>';
  html += '<div class="muted small" style="margin:10px 0">Portefeuille virtuel 100 % local — aucune connexion courtier. Prix de clôture réels (Yahoo), barre du jour exclue tant qu’elle n’est pas close. Coûts déduits : 5 bps ETF, 20 bps crypto.' + (d.legacy_journal ? ' L’ancien journal (v1) est archivé dans data_cache/paper_journal.json.' : '') + '</div>';
  c.innerHTML = html;
}

