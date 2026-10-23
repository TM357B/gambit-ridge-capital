/* ============ CAMPAGNES DE RECHERCHE (onglet Recherche) ============ */
let CAMPAIGNS = null, CAMP_SEL = null;
function researchSeg(active) {
  const R = RESEARCH || {};
  const items = [['etf', 'Univers ETF (20 actifs)'], ['crypto', 'Crypto (7 actifs)']].filter(([k]) => R[k] || k === active);
  let h = '<div class="seg">' + items.map(([k, l]) => `<div class="seg-i ${k===active?'active':''}" onclick="RS_SEL={uni:'${k}'};renderResearch()">${l}</div>`).join('');
  h += `<div class="seg-i ${active==='camp'?'active':''}" onclick="RS_SEL={uni:'camp'};renderResearch()">Campagnes de recherche${CAMPAIGNS ? ' (' + CAMPAIGNS.total_essais + ' essais)' : ''}</div></div>`;
  return h;
}
async function renderCampaigns() {
  const c = document.getElementById('content');
  if (!CAMPAIGNS) {
    c.innerHTML = '<div class="loader">Chargement des campagnes…</div>';
    try { CAMPAIGNS = await (await fetch('/api/campaigns')).json(); } catch(e) { c.innerHTML = '<div class="loader neg">Serveur injoignable.</div>'; return; }
  }
  if (currentTab !== 'research') return;
  const K = CAMPAIGNS;
  const sel = K.campagnes.find(x => x.n === CAMP_SEL) || K.campagnes[K.campagnes.length - 1];
  let h = researchSeg('camp');
  h += '<div class="kpis">' + kpi('Campagnes', K.campagnes.length) + kpi('Essais jugés', K.total_essais) + kpi('Acceptés', K.total_acceptes, K.total_acceptes ? 'pos' : '')
     + kpi('Rejetés', K.total_essais - K.total_acceptes) + kpi('Stratégie de production', K.total_acceptes ? 'à réviser' : 'inchangée', K.total_acceptes ? 'amber' : 'pos') + '</div>';
  h += '<div class="muted small" style="margin:-4px 0 10px">Chaque campagne a son protocole — liste des essais, paramètres, règle d’acceptation — <b>commité avant tout calcul</b>. Un essai n’est accepté que s’il gagne sur la période de développement <b>et</b> n’est pas contredit par la validation. Rejeter 39 idées raisonnables n’est pas un échec : c’est ce qui distingue une stratégie robuste d’une stratégie ajustée au passé.</div>';
  h += '<div class="seg">' + K.campagnes.map(x => `<div class="seg-i ${x.n===sel.n?'active':''}" onclick="CAMP_SEL=${x.n};renderCampaigns()">N° ${x.n} · ${esc(x.titre)}</div>`).join('') + '</div>';
  h += `<div class="verdict"><div class="v-t">CAMPAGNE N° ${sel.n} · ${esc(sel.date || '')}</div><div class="v-n">${esc(sel.titre)}</div><div class="v-d">${esc(sel.question)}</div>`;
  h += `<div class="v-k">${kpi('Essais', sel.n_essais)}${kpi('Acceptés', sel.n_acceptes, sel.n_acceptes ? 'pos' : '')}${kpi('Enseignement', '<span style="font-size:12px;font-weight:400;line-height:1.35;display:block">' + esc(sel.lecon) + '</span>')}</div></div>`;
  if (sel.courbes && sel.courbes.length) {
    const cols = ['#ff9900', '#2979ff', '#00e5ff', '#e040fb', '#ffea00', '#00c853', '#9e9e9e'];
    const base = sel.courbes[0].dates;
    h += `<div class="panel" style="margin-top:10px"><div class="panel-h">Courbes de capital <span class="rt">${esc(sel.debut || base[0])} → ${esc(sel.fin || base[base.length-1])} · base 1</span></div><div class="panel-b">`;
    h += lineChart('chCamp', sel.courbes.map((s, i) => ({ name: s.nom, x: s.dates, y: s.equity, color: s.ref ? '#ff9900' : cols[(i % (cols.length - 1)) + 1], width: s.ref ? 2.2 : 1.2 })), { log: true, height: 280, zero: 1, yfmt: v => v.toFixed(2) + '×' });
    h += '</div></div>';
  }
  const one = sel.periode_unique;
  const sh = (m, ref) => !m || m.sharpe === null || m.sharpe === undefined ? '<td class="num muted">—</td>' : `<td class="num ${ref && ref.sharpe !== undefined ? (m.sharpe >= ref.sharpe + 0.05 ? 'pos' : m.sharpe < ref.sharpe - 0.05 ? 'neg' : '') : ''}">${m.sharpe.toFixed(2)}</td>`;
  const refc = m => !m ? '<td class="num muted">—</td>' : `<td class="num muted">${m.sharpe.toFixed(2)}</td>`;
  h += `<div class="panel" style="margin-top:10px"><div class="panel-h">Essais <span class="rt">Sharpe = rendement par unité de risque · vert : gagne plus de 0,05 sur la référence · rouge : perd plus de 0,05</span></div><div class="panel-b" style="padding:4px;overflow-x:auto"><table class="rs-table"><tr><th>Essai</th>`;
  h += one ? '<th class="num">Sharpe</th><th class="num">Réf.</th><th class="num">CAGR</th><th class="num">Pire baisse</th>'
           : '<th class="num">Sharpe dév.</th><th class="num">Réf.</th><th class="num sep">Sharpe valid.</th><th class="num">Réf.</th><th class="num">CAGR valid.</th><th class="num">Pire baisse valid.</th>';
  h += '<th class="num">Rotation/an</th><th>Critères manqués</th><th>Verdict</th></tr>';
  const crit = { gain_developpement: 'gain en développement', gain: 'gain', dsr: 'tests multiples (DSR)', validation_non_contredite: 'validation', drawdown_validation: 'pire baisse', drawdown: 'pire baisse' };
  for (const t of sel.essais) {
    const isRef = !t.verdict, last = one ? t.dev : t.val;
    const missed = t.criteres ? Object.entries(t.criteres).filter(([, ok]) => !ok).map(([k]) => crit[k] || k).join(', ') : '';
    h += `<tr class="${isRef && t.role !== 'repère' ? 'row-win' : ''}" title="${esc(t.description)}"><td class="${isRef ? 'amber' : ''}">${esc(t.nom)}</td>`;
    h += sh(t.dev, isRef ? null : t.ref_dev) + (isRef ? '<td></td>' : refc(t.ref_dev));
    if (!one) h += `<td class="num sep ${t.val && t.ref_val && !isRef ? (t.val.sharpe >= t.ref_val.sharpe + 0.05 ? 'pos' : t.val.sharpe < t.ref_val.sharpe - 0.05 ? 'neg' : '') : ''}">${t.val ? t.val.sharpe.toFixed(2) : '—'}</td>` + (isRef ? '<td></td>' : refc(t.ref_val));
    h += last && last.cagr !== undefined && last.cagr !== null ? pctCell(last.cagr) : '<td class="num muted">—</td>';
    h += last && last.max_dd !== undefined && last.max_dd !== null ? `<td class="num neg">${fmtPct(last.max_dd, 1)}</td>` : '<td class="num muted">—</td>';
    h += `<td class="num muted">${last && last.turnover ? last.turnover.toFixed(1) : '—'}</td><td class="muted small">${esc(missed)}</td>`;
    h += `<td class="${t.verdict === 'ACCEPTÉ' ? 'pos' : t.verdict ? 'neg' : 'muted'}">${t.verdict || esc(t.role)}</td></tr>`;
  }
  h += '</table></div></div>';
  h += costPanel(K.couts);
  h += `<details style="margin-top:10px"><summary class="muted small" style="cursor:pointer">Protocole pré-enregistré de la campagne n° ${sel.n} (texte commité avant calcul)</summary><pre class="muted small" style="white-space:pre-wrap;margin:8px 0;padding:10px;border:1px solid var(--border)">${esc(sel.protocole)}</pre></details>`;
  c.innerHTML = h;
}

function costPanel(C) {
  if (!C) return '';
  const M = C.mesure;
  let h = `<div class="panel" style="margin-top:10px"><div class="panel-h">Robustesse aux coûts réels <span class="rt">coûts mesurés sur les ordres exécutés du ${esc(M.periode)}</span></div><div class="panel-b">`;
  h += `<div class="muted small" style="margin-bottom:8px">Sur ${M.ordres_crypto} ordres crypto (${Math.round(M.montant_crypto).toLocaleString('fr-FR')} $), Alpaca a prélevé <b>${M.crypto_frais_bps} bps</b> de frais, et l’écart achat-vente a coûté environ <b>${M.crypto_ecart_bps} bps</b> de plus : <b>≈ ${M.crypto_total_bps} bps par transaction</b>, contre 20 supposés dans le banc. La stratégie est rejouée telle quelle avec des coûts croissants (rien n’est choisi ici).</div>`;
  h += '<div class="grid" style="grid-template-columns:1fr 1fr 1.2fr;gap:12px">';
  const tab = (title, T, real) => {
    let t = `<div><div class="sub-h">${title}</div><table><tr><th>Coût</th><th class="num">Sharpe valid.</th><th class="num">CAGR valid.</th><th class="num">Coûts/an</th></tr>`;
    for (const [c, x] of Object.entries(T)) t += `<tr class="${+c === real ? 'row-win' : ''}"><td>${c} bps${+c === real ? ' ← réel' : ''}</td><td class="num">${x.val_sharpe.toFixed(2)}</td>${pctCell(x.val_cagr)}<td class="num muted">${fmtPct(x.couts_annuels || 0, 2)}</td></tr>`;
    return t + '</table></div>';
  };
  h += tab('Poche ETF', C.etf, 5) + tab('Poche crypto', C.crypto, 50);
  h += `<div><div class="sub-h">Fonds complet (${Math.round((C.repartition || {}).etf * 100) || 95} % ETF / ${Math.round((C.repartition || {}).crypto * 100) || 5} % crypto)</div><table><tr><th>Hypothèse</th><th class="num">Sharpe</th><th class="num">CAGR</th><th class="num">Pire baisse</th></tr>`;
  for (const [n, x] of Object.entries(C.fonds)) h += `<tr class="${/réels/.test(n) ? 'row-win' : ''}"><td>${esc(n)}</td><td class="num">${x.sharpe.toFixed(2)}</td>${pctCell(x.cagr)}<td class="num neg">${fmtPct(x.max_dd, 1)}</td></tr>`;
  h += '</table></div></div>';
  h += '<div class="muted small" style="margin-top:8px">Lecture : aux coûts réellement mesurés, le fonds perd environ 0,3 point de rendement par an et garde l’essentiel de son Sharpe. La perte de la semaine du 5 octobre venait du <b>nombre</b> de transactions (allers-retours), pas de leur prix unitaire.</div></div></div>';
  return h;
}

/* ============ PROJECTION À UN AN (onglet Risque) ============ */
async function projectionPanel() {
  let p;
  try { p = await (await fetch('/api/projection')).json(); } catch(e) { return ''; }
  if (p.error) return '';
  const eq = p.equity || 1, usd = v => (v >= 0 ? '+' : '−') + Math.abs(Math.round(v)).toLocaleString('fr-FR') + ' $';
  const pc = (v, d = 1) => sgn(v * 100, d) + ' %';
  const x = p.jours.map(j => j === 0 ? 'auj.' : 'mois ' + Math.round(j / 21));
  const S = (q, name, color, width) => ({ name, x, y: p.quantiles[q].map(v => v * 100), color, width });
  let h = `<div class="panel" style="margin-top:10px"><div class="panel-h">Projection à un an <span class="rt">${esc(p.methode)} · source : backtest du fonds ${esc(p.source.debut)} → ${esc(p.source.fin)}</span></div><div class="panel-b">`;
  h += '<div class="kpis">' + kpi('Résultat médian', pc(p.rendement['50']) + ` <span class="muted small">${usd(p.rendement['50'] * eq)}</span>`, 'pos')
     + kpi('Mauvaise année (1 sur 20)', pc(p.rendement['5']) + ` <span class="muted small">${usd(p.rendement['5'] * eq)}</span>`, 'neg')
     + kpi('Bonne année (1 sur 20)', pc(p.rendement['95']), 'pos')
     + kpi('Probabilité de perdre', fmtPct(p.prob_perte, 0), p.prob_perte > 0.25 ? 'neg' : '')
     + kpi('Baisse à prévoir en route', '−' + fmtPct(p.baisse_max['50'], 1) + ` <span class="muted small">jusqu’à −${fmtPct(p.baisse_max['95'], 1)}</span>`, 'amber') + '</div>';
  h += lineChart('chProj', [S('95', 'Très favorable (95 %)', '#1b5e20', 1), S('75', 'Favorable (75 %)', '#2e7d32', 1.2), S('50', 'Médiane', '#ff9900', 2.4), S('25', 'Défavorable (25 %)', '#b71c1c', 1.2), S('5', 'Très défavorable (5 %)', '#7f0000', 1)], { height: 230, zero: 100, yfmt: v => v.toFixed(0) });
  const P = p.prudent;
  h += '<table style="margin-top:8px"><tr><th>Scénario</th><th class="num">Médiane</th><th class="num">1 an sur 20, pire</th><th class="num">1 an sur 20, meilleur</th><th class="num">Probabilité de perdre</th><th class="num">Perte &gt; 5 %</th><th class="num">Baisse &gt; 10 % en route</th></tr>';
  const row = (n, q, cls) => `<tr><td class="${cls}">${n}</td><td class="num">${pc(q.rendement['50'])}</td><td class="num neg">${pc(q.rendement['5'])}</td><td class="num pos">${pc(q.rendement['95'])}</td><td class="num">${fmtPct(q.prob_perte, 0)}</td><td class="num">${fmtPct(q.prob_perte_5, 0)}</td><td class="num">${fmtPct(q.prob_baisse_10, 0)}</td></tr>`;
  h += row('Comme le backtest', p, 'amber') + row('Prudent : rendement moyen divisé par deux', P, '') + '</table>';
  h += '<div class="muted small" style="margin-top:6px">Ce n’est pas une prévision : la projection rejoue des morceaux du passé (2018-2026, période favorable à la stratégie). Le scénario prudent est le plus réaliste pour fixer ses attentes — un backtest surestime presque toujours le rendement futur. À retenir : même si la stratégie fonctionne, une année sur quatre environ peut finir en perte, et une baisse de 5 à 13 % en cours d’année est normale.</div></div></div>';
  return h;
}

/* ============ SUIVI LIVE / PAPER ET ÉTAT DU SERVEUR (panneau En direct) ============ */
function liveTrackingBlock(s) {
  const D = (s.daily || []).filter(d => d.alpaca_equity && d.paper_equity);
  if (D.length < 2) return '';
  const a0 = D[0].alpaca_equity, p0 = D[0].paper_equity, last = D[D.length - 1];
  const gap = last.alpaca_equity / a0 - last.paper_equity / p0;
  const all = s.daily || [], tot = all.reduce((x, d) => x + (d.notional || 0), 0), n = all.reduce((x, d) => x + (d.orders || 0), 0);
  const perYear = all.length ? tot / last.alpaca_equity / all.length * 252 : 0;
  let h = '<div class="sub-h">Compte réel simulé contre portefeuille de référence</div>';
  h += lineChart('chTrack', [
    { name: 'Paper de référence (revalorisé au même instant que le compte)', x: D.map(d => d.date), y: D.map(d => d.paper_equity / p0 * 100), color: '#ff9900', width: 2 },
    { name: 'Compte Alpaca (ordres réellement exécutés)', x: D.map(d => d.date), y: D.map(d => d.alpaca_equity / a0 * 100), color: '#2979ff', width: 2 }], { height: 150, yfmt: v => v.toFixed(2) });
  h += `<div class="legend2">Écart cumulé depuis le ${esc(D[0].date)} : <b class="${gap >= 0 ? 'pos' : 'neg'}">${sgn(gap * 100, 2)} point</b> · ${n} ordres, ${Math.round(tot).toLocaleString('fr-FR')} $ échangés · rythme sur ${all.length} jours : <b class="${perYear > 25 ? 'neg' : 'pos'}">${perYear.toFixed(0)} rotations/an</b> (attendu ≈ 15). Du 5 au 9 octobre, le moteur recalculait ses signaux en séance et multipliait les allers-retours crypto : corrigé le 10 octobre.</div>`;
  h += '<div style="overflow-x:auto"><table style="margin-top:6px"><tr><th>Jour</th><th class="num">Compte Alpaca</th><th class="num">Paper (base 100)</th><th class="num">Ordres</th><th class="num">Refusés</th><th class="num">Montant échangé</th><th class="num">Rotation</th></tr>';
  for (const d of all.slice(-10).reverse()) {
    const to = d.alpaca_equity ? (d.notional || 0) / d.alpaca_equity : 0;
    h += `<tr><td class="muted">${esc(d.date)}</td><td class="num">${d.alpaca_equity ? Math.round(d.alpaca_equity).toLocaleString('fr-FR') + ' $' : '—'}</td><td class="num muted">${d.paper_equity ? (d.paper_equity / p0 * 100).toFixed(2) : '—'}</td><td class="num">${d.orders || 0}</td><td class="num ${d.refused ? 'neg' : 'muted'}">${d.refused || 0}</td><td class="num">${Math.round(d.notional || 0).toLocaleString('fr-FR')} $</td><td class="num ${to > 0.2 ? 'neg' : ''}">${(to * 100).toFixed(1)} %</td></tr>`;
  }
  h += '</table></div>';
  return h;
}
async function systemBlock() {
  let y;
  try { y = await (await fetch('/api/system')).json(); } catch(e) { return ''; }
  if (y.error) return '';
  const chip = (label, ok, title) => `<span title="${esc(title || '')}" style="display:inline-block;margin:2px 6px 2px 0;padding:1px 8px;border:1px solid ${ok ? '#1b5e20' : 'var(--red)'};color:${ok ? 'var(--green)' : 'var(--red)'};font-size:10px">${ok ? '●' : '▲'} ${esc(label)}</span>`;
  const names = { 'gambit-server': 'Terminal', 'gambit-live': 'Moteur live', 'gambit-daily.timer': 'Passage quotidien', 'tailscaled': 'Réseau privé' };
  let h = '<div class="sub-h">Serveur et surveillance</div><div>';
  for (const [k, v] of Object.entries(y.services || {})) if (v !== 'indisponible') h += chip(names[k] || k, v === 'active', v);
  if (y.live_age_s !== null && y.live_age_s !== undefined) h += chip('Prix à jour (' + y.live_age_s + ' s)', y.live_age_s < 300);
  if (y.turnover_5d !== null && y.turnover_5d !== undefined) h += chip('Rotation 5 j : ' + (y.turnover_5d * 100).toFixed(0) + ' %', y.turnover_5d <= y.thresholds.turnover_5d, 'alerte au-delà de ' + y.thresholds.turnover_5d * 100 + ' %');
  if (y.gap_5d !== null && y.gap_5d !== undefined) h += chip('Écart live/paper 5 j : ' + sgn(y.gap_5d * 100, 2) + ' pt', y.gap_5d >= y.thresholds.gap_5d);
  if (y.memory) h += chip('Mémoire ' + y.memory.used_mb + '/' + y.memory.total_mb + ' Mo', y.memory.used_mb / y.memory.total_mb < 0.9);
  h += chip('Disque ' + y.disk_free_gb + ' Go libres', y.disk_free_gb / y.disk_total_gb > 0.1);
  if (y.uptime_s) h += chip('Allumé depuis ' + Math.floor(y.uptime_s / 86400) + ' j', true);
  h += '</div>';
  if (y.issues && y.issues.length) h += '<div class="neg small" style="margin-top:4px">⚠ ' + y.issues.map(i => esc(i.msg)).join(' · ') + '</div>';
  else h += '<div class="muted small" style="margin-top:4px">Surveillance automatique toutes les 10 minutes : alerte iPhone si le moteur se fige, si un service s’arrête, si la rotation ou l’écart avec le paper sortent de la norme.</div>';
  return h;
}
