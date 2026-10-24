/* Gambit Ridge Capital — terminal : 11-actions-macro.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ ACTIONS (SEC EDGAR) ET MACRO MONDIALE (FMI, BRI, OCDE) ============ */
function md(v, d = 1) { if (v === null || v === undefined || !isFinite(v)) return '—'; const a = Math.abs(v); return a >= 1e12 ? (v / 1e12).toFixed(2) + ' T' : a >= 1e9 ? (v / 1e9).toFixed(d) + ' Md' : a >= 1e6 ? (v / 1e6).toFixed(d) + ' M' : v.toLocaleString('fr-FR', { maximumFractionDigits: 0 }); }
function xx(v, d = 1) { return v === null || v === undefined || !isFinite(v) ? '—' : v.toFixed(d) + '×'; }
function pc(v, d = 1) { return v === null || v === undefined || !isFinite(v) ? '—' : (v * 100).toFixed(d) + ' %'; }
function pcCell(v, d = 1, inverse = false) { if (v === null || v === undefined || !isFinite(v)) return '<td class="num muted">—</td>'; const bon = inverse ? v < 0 : v >= 0; return `<td class="num ${bon ? 'pos' : 'neg'}">${(v * 100).toFixed(d)} %</td>`; }
function lienExterne(url, texte) { return `<a class="lnk" href="${esc(url)}" target="_blank" rel="noopener">${texte}</a>`; }

/* ---------------- FA : fiche financière ---------------- */
function fnFA(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div><div class="muted small" style="padding:0 10px">FA couvre les sociétés qui déposent à la SEC (cotées aux États-Unis). Ex. : <a class="lnk" onclick="runCommand('AAPL FA')">AAPL FA</a> · <a class="lnk" onclick="runCommand('EQS')">EQS</a> pour en trouver.</div>`;
  const r = d.ratios, p = d.profil, a = d.annuel, tt = d.ttm;
  const ch = d.variation_jour;
  let h = fnHeader(`${esc(d.ticker)} <span class="muted">${esc(d.nom)}</span>`, `FA · ${esc(p.secteur || '')} · ${esc([...new Set(p.bourses || [])].join(', '))} · exercice clos le ${esc((p.fin_exercice || '').replace(/(\d\d)(\d\d)/, '$2/$1'))} · ${esc(p.ville || '')}`,
    d.cours ? `<span class="fn-last">${fmtPx(d.cours)}</span> ${ch !== null && ch !== undefined ? `<span class="${ch >= 0 ? 'pos' : 'neg'}">${sgn(ch, 2)}%</span>` : ''}` : '');
  h += '<div class="kpis">' + kpi('Capitalisation', md(d.capitalisation)) + kpi('PER (12 mois)', xx(r.per)) + kpi('Cours / valeur comptable', xx(r.prix_valeur_comptable))
    + kpi('Rendement FCF', pc(r.rendement_fcf)) + kpi('VE / EBIT', xx(r.ve_ebit)) + kpi('ROE', pc(r.roe, 0)) + kpi('Marge opérationnelle', pc(r.marge_operationnelle))
    + kpi('Dette / fonds propres', xx(r.dette_fp, 2)) + '</div>';
  if (d.historique_court) h += `<div class="loader" style="margin-bottom:8px">Historique XBRL court pour cette entité déclarante (nouvelle structure ou société récente) : ratios partiels.</div>`;
  const ans = a.map(x => x.annee);
  h += '<div class="grid g-main">';
  h += pan('Chiffre d’affaires et résultat net', 'milliards de dollars', lineChart('chFA1', [{ name: 'Chiffre d’affaires', x: ans, y: a.map(x => x.chiffre_affaires === null ? NaN : x.chiffre_affaires / 1e9), color: '#ff9900', width: 2 }, { name: 'Résultat net', x: ans, y: a.map(x => x.resultat_net === null ? NaN : x.resultat_net / 1e9), color: '#00c853', width: 1.8 }, { name: 'Free cash flow', x: ans, y: a.map(x => x.fcf === null ? NaN : x.fcf / 1e9), color: '#2979ff', width: 1.4 }], { height: 240, zero: 0, yfmt: v => v.toFixed(0) }));
  h += pan('Marges', '', lineChart('chFA2', [{ name: 'Brute', x: ans, y: a.map(x => x.marge_brute === null ? NaN : x.marge_brute * 100), color: '#2979ff' }, { name: 'Opérationnelle', x: ans, y: a.map(x => x.marge_operationnelle === null ? NaN : x.marge_operationnelle * 100), color: '#ff9900', width: 2 }, { name: 'Nette', x: ans, y: a.map(x => x.marge_nette === null ? NaN : x.marge_nette * 100), color: '#00c853' }], { height: 240, zero: 0, yfmt: v => v.toFixed(0) + ' %' }));
  h += '</div>';
  let t = '<table><tr><th>Exercice</th><th class="num">CA</th><th class="num">Croiss.</th><th class="num">Marge op.</th><th class="num">Marge nette</th><th class="num">Résultat net</th><th class="num">BPA</th><th class="num">FCF</th><th class="num">ROE</th><th class="num">Dette</th><th class="num">Trésorerie</th></tr>';
  for (const x of a.slice(-10).reverse()) t += `<tr><td class="amber">${esc(x.annee)} <span class="muted small">${esc(x.fin)}</span></td><td class="num">${md(x.chiffre_affaires)}</td>${pcCell(x.croissance_ca)}<td class="num">${pc(x.marge_operationnelle)}</td><td class="num">${pc(x.marge_nette)}</td><td class="num">${md(x.resultat_net)}</td><td class="num">${x.bpa === null || x.bpa === undefined ? '—' : x.bpa.toFixed(2)}</td><td class="num">${md(x.fcf)}</td><td class="num">${pc(x.roe, 0)}</td><td class="num">${md(x.dette)}</td><td class="num">${md(x.tresorerie)}</td></tr>`;
  if (tt && tt.chiffre_affaires) t += `<tr><td class="pos">12 derniers mois <span class="muted small">→ ${esc(tt.fin || '')}</span></td><td class="num">${md(tt.chiffre_affaires)}</td><td></td><td class="num">${pc(r.marge_operationnelle)}</td><td class="num">${pc(r.marge_nette)}</td><td class="num">${md(tt.resultat_net)}</td><td></td><td class="num">${md(tt.fcf)}</td><td class="num">${pc(r.roe, 0)}</td><td class="num">${md(r.dette)}</td><td class="num">${md(r.liquidite)}</td></tr>`;
  h += pan('Comptes annuels', 'normalisés depuis les 10-K (XBRL)', `<div style="overflow-x:auto;padding:0">${t}</table></div>`, 'margin-top:10px');
  const s = d.dirigeants_6m;
  h += '<div class="grid g-main" style="margin-top:10px">';
  let ti = `<div class="kpis" style="margin:0 0 6px">${kpi('Achats en bourse (6 mois)', md(s.achats))}${kpi('Ventes en bourse (6 mois)', md(s.ventes))}${kpi('Acheteurs / vendeurs', `${s.acheteurs} / ${s.vendeurs}`)}</div><div style="overflow-x:auto;max-height:340px"><table><tr><th>Date</th><th>Dirigeant</th><th>Type</th><th class="num">Actions</th><th class="num">Prix</th><th class="num">Montant</th></tr>`;
  for (const x of d.dirigeants.slice(0, 30)) ti += `<tr><td class="muted">${esc(x.date)}</td><td>${esc(x.nom)} <span class="muted small">${esc(x.role)}</span></td><td class="${x.code === 'P' ? 'pos' : x.code === 'S' ? 'neg' : 'muted'}">${esc(x.type)}</td><td class="num">${Math.round(x.actions).toLocaleString('fr-FR')}</td><td class="num">${x.prix ? x.prix.toFixed(2) : '—'}</td><td class="num">${x.prix ? md(x.montant) : '—'}</td></tr>`;
  h += pan('Transactions des dirigeants', 'formulaires 4 · INS', ti + '</table></div>');
  let tf = '<div style="overflow-x:auto;max-height:420px"><table><tr><th>Date</th><th>Type</th><th>Document</th></tr>';
  for (const x of d.depots) tf += `<tr><td class="muted">${esc(x.date)}</td><td class="amber">${esc(x.type)}</td><td>${lienExterne(x.lien, esc(x.description || x.document).slice(0, 70))}${x.items ? ` <span class="muted small">items ${esc(x.items)}</span>` : ''}</td></tr>`;
  h += pan('Dépôts à la SEC', '10-K, 10-Q, 8-K… · CF', tf + '</table></div>') + '</div>';
  return h + noteBas(`${esc(d.source)}. Ratios sur les 12 derniers mois (dernier exercice + trimestres publiés depuis − mêmes trimestres un an plus tôt) et le dernier bilan. FCF = flux opérationnel − investissements corporels ; sans signification pour les banques et assureurs. Les dirigeants : achats et ventes en bourse (codes P et S) ; attributions, exercices d'options et retenues fiscales listés à part.`);
}

/* ---------------- EQS : screener ---------------- */
FN_STATE.eqs = { preset: 'qualite', per_max: '', roe_min: '', marge_op_min: '', croissance_ca_min: '', rendement_fcf_min: '', dette_fp_max: '', cap_min: 2, tri: '', sens: '' };
function eqsQuery() {
  const s = FN_STATE.eqs, q = { cap_min: s.cap_min, n: 100 };
  if (s.preset) q.preset = s.preset;
  for (const k of ['per_max', 'roe_min', 'marge_op_min', 'croissance_ca_min', 'rendement_fcf_min', 'dette_fp_max']) if (s[k] !== '' && s[k] !== null) q[k] = ['per_max', 'dette_fp_max'].includes(k) ? s[k] : s[k] / 100;
  if (s.tri) { q.tri = s.tri; q.sens = s.sens || 'desc'; }
  return q;
}
function eqsTri(k) { const s = FN_STATE.eqs; s.sens = s.tri === k && s.sens === 'desc' ? 'asc' : 'desc'; s.tri = k; renderFn(); }
function fnEQS(d) {
  const s = FN_STATE.eqs, P = 'FN_STATE.eqs.';
  let h = '<div class="fn-tools">' + [['', 'Sans préréglage'], ['valeur', 'Valeur'], ['qualite', 'Qualité'], ['croissance', 'Croissance'], ['fcf', 'Rendement FCF'], ['geants', 'Géants']].map(([k, l]) => `<span class="rng ${s.preset === k ? 'on' : ''}" onclick="FN_STATE.eqs.preset='${k}';FN_STATE.eqs.tri='';renderFn()">${l}</span>`).join('') + '</div>';
  const champ = (lab, k, step) => qf(lab, `<input type="number" value="${s[k]}" step="${step}" placeholder="—" onchange="${P}${k}=this.value" onkeydown="if(event.key==='Enter'){${P}${k}=this.value;renderFn()}">`);
  h += '<div class="qform">' + champ('PER max', 'per_max', 1) + champ('ROE min (%)', 'roe_min', 1) + champ('Marge op. min (%)', 'marge_op_min', 1) + champ('Croissance CA min (%)', 'croissance_ca_min', 1)
    + champ('Rendement FCF min (%)', 'rendement_fcf_min', 0.5) + champ('Dette/FP max', 'dette_fp_max', 0.1) + champ('Capitalisation min (Md$)', 'cap_min', 1)
    + '<button class="btn" onclick="renderFn()">FILTRER &lt;GO&gt;</button><button class="btn" style="background:#333;color:#ccc" onclick="Object.assign(FN_STATE.eqs,{preset:\'\',per_max:\'\',roe_min:\'\',marge_op_min:\'\',croissance_ca_min:\'\',rendement_fcf_min:\'\',dette_fp_max:\'\',tri:\'\'});renderFn()">EFFACER</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  h = fnHeader('EQS <span class="muted">Screener d’actions américaines</span>', `${d.resultats} sociétés retenues sur ${d.eligibles} (capitalisation ≥ ${d.cap_min_md} Md$) · univers ${d.univers} sociétés · ${d.ms} ms`, '') + h;
  const cols = [['capitalisation', 'Capi.', v => md(v)], ['per', 'PER', v => xx(v)], ['prix_vc', 'C/VC', v => xx(v)], ['rendement_fcf', 'Rdt FCF', v => pc(v)], ['ve_ebit', 'VE/EBIT', v => xx(v)],
    ['roe', 'ROE', v => pc(v, 0)], ['marge_op', 'Marge op.', v => pc(v, 0)], ['croissance_ca', 'Croiss. CA', v => pc(v, 0)], ['dette_fp', 'Dette/FP', v => xx(v, 2)]];
  let t = '<table><tr><th>Société</th>' + cols.map(([k, l]) => `<th class="num" style="cursor:pointer" onclick="eqsTri('${k}')">${l}${d.tri === k ? (d.sens === 'desc' ? ' ▼' : ' ▲') : ''}</th>`).join('') + '</tr>';
  for (const r of d.lignes) t += `<tr class="ecst-row" onclick="runCommand('${esc(r.ticker)} FA')"><td><span class="amber">${esc(r.ticker)}</span> <span class="muted small">${esc(r.nom.slice(0, 34))}</span></td>` + cols.map(([k, , f]) => `<td class="num">${f(r[k])}</td>`).join('') + '</tr>';
  h += `<div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto">${t}</table></div></div>`;
  return h + noteBas(`${esc(d.source)}. Clic sur une ligne : fiche FA ; clic sur un en-tête : tri. Univers : sociétés déposant à la SEC avec au moins 1 Md$ de chiffre d'affaires. Valeurs non plausibles masquées (PER &lt; 1, rendement FCF &gt; 40 % : banques, assureurs, sociétés sous tutelle).`);
}

/* ---------------- GEW : économie mondiale ---------------- */
function fnGEW(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const A = d.annees, n1 = v => v === null || v === undefined ? '—' : v.toFixed(1);
  let h = fnHeader('GEW <span class="muted">Économie mondiale</span>', esc(d.note), `<span class="muted small">${esc(d.source)}</span>`);
  let t = `<table><tr><th rowspan="2">Pays</th><th class="num" colspan="3">Croissance du PIB (%)</th><th class="num" colspan="3">Inflation (%)</th><th class="num" rowspan="2">Chômage</th><th class="num" rowspan="2">Dette / PIB</th><th class="num" rowspan="2">Solde public</th><th class="num" rowspan="2">Bal. courante</th><th class="num" rowspan="2">Taux directeur</th><th class="num" rowspan="2">Var. 1 an</th><th class="num" rowspan="2">Taux réel</th><th class="num" rowspan="2">10 ans</th><th class="num" rowspan="2">Pente</th></tr><tr>${A.map(a => `<th class="num">${a}</th>`).join('')}${A.map(a => `<th class="num">${a}</th>`).join('')}</tr>`;
  const row = l => `<tr><td>${esc(l.pays)}</td>${l.croissance.map((v, i) => `<td class="num ${i ? 'amber' : ''}">${n1(v)}</td>`).join('')}${l.inflation.map((v, i) => `<td class="num ${i ? 'amber' : ''}">${n1(v)}</td>`).join('')}`
    + `<td class="num">${n1(l.chomage)}</td><td class="num">${n1(l.dette)}</td><td class="num ${l.solde_public < 0 ? 'neg' : ''}">${n1(l.solde_public)}</td><td class="num">${n1(l.balance_courante)}</td>`
    + `<td class="num"><b>${l.taux_directeur === null ? '—' : l.taux_directeur.toFixed(2)}</b></td><td class="num ${l.taux_directeur_var_1a > 0 ? 'neg' : l.taux_directeur_var_1a < 0 ? 'pos' : ''}">${l.taux_directeur_var_1a === null ? '—' : (l.taux_directeur_var_1a >= 0 ? '+' : '') + Math.round(l.taux_directeur_var_1a * 100) + ' pb'}</td>`
    + `<td class="num ${l.taux_reel === null ? '' : l.taux_reel >= 0 ? 'neg' : 'pos'}">${n1(l.taux_reel)}</td><td class="num">${l.taux_10a === null ? '—' : l.taux_10a.toFixed(2)}</td><td class="num">${l.pente === null ? '—' : (l.pente >= 0 ? '+' : '') + l.pente.toFixed(2)}</td></tr>`;
  let region = '';
  for (const l of d.lignes) { if (l.region !== region) { region = l.region; t += `<tr><td colspan="17" class="cls-row">${esc(region)}</td></tr>`; } t += row(l); }
  t += `<tr><td colspan="17" class="cls-row">Agrégats FMI</td></tr>` + d.agregats.map(row).join('');
  h += `<div class="panel"><div class="panel-b" style="padding:4px;overflow-x:auto">${t}</table></div></div>`;
  const cr = d.lignes.filter(l => l.croissance[1] !== null).sort((a, b) => b.croissance[1] - a.croissance[1]);
  const tr = d.lignes.filter(l => l.taux_reel !== null && l.pays !== 'Allemagne' && l.pays !== 'France' && l.pays !== 'Italie' && l.pays !== 'Espagne' && l.pays !== 'Pays-Bas').sort((a, b) => b.taux_reel - a.taux_reel);
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan(`Croissance ${A[1]} (prévision FMI)`, '', cr.map(l => barRow(l.pays, l.croissance[1] / 100, Math.max(...cr.map(x => Math.abs(x.croissance[1]))) / 100)).join(''));
  h += pan('Taux directeur réel', 'taux directeur − inflation de l’année : positif = politique restrictive', tr.map(l => barRow(l.pays, l.taux_reel / 100, Math.max(...tr.map(x => Math.abs(x.taux_reel))) / 100)).join(''));
  h += '</div>';
  return h + noteBas(`Dette, solde public et balance courante en % du PIB, pour ${A[1]}. Taux directeurs mensuels de la BRI (la BCE pour la zone euro et ses membres). Taux à 10 ans de l'OCDE via FRED (moyenne mensuelle, non disponible pour quelques émergents). Pente = 10 ans − taux directeur.`);
}
