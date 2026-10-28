/* Gambit Ridge Capital — terminal : 16-bulle.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ BULL : THERMOMÈTRE DE BULLE (CAPE, BUFFETT, LARGEUR, COMPLAISANCE, TITRES IA) ============ */

function bullJauge(p) {
  // barre 0-100 : vert (froid) → ambre → rouge (surchauffe), curseur au percentile
  const W = 1000, H = 34, x = 10 + p * (W - 20);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px"><defs><linearGradient id="bullG"><stop offset="0" stop-color="#00c853"/><stop offset="0.55" stop-color="#ff9900"/><stop offset="1" stop-color="#ff1744"/></linearGradient></defs>`;
  s += `<rect x="10" y="8" width="${W - 20}" height="12" fill="url(#bullG)" opacity="0.85"/>`;
  for (const t of [0, 25, 50, 75, 100]) s += `<text x="${10 + t / 100 * (W - 20)}" y="32" fill="#666" font-size="10" text-anchor="middle">${t}</text>`;
  return s + `<polygon points="${x - 7},2 ${x + 7},2 ${x},10" fill="#fff"/><rect x="${x - 1.5}" y="6" width="3" height="16" fill="#fff"/></svg>`;
}

async function bullRecalculer() {
  for (const k of Object.keys(FN_CACHE)) if (k.startsWith('BULL')) delete FN_CACHE[k];
  await fnFetchQ('BULL', '', { r: '1' });
  for (const k of Object.keys(FN_CACHE)) if (k.startsWith('BULL')) delete FN_CACHE[k];
  renderFn();
}

function bullNiveau(p) { return p >= 0.9 ? ['extrême', 'neg'] : p >= 0.75 ? ['tendu', 'neg'] : p >= 0.5 ? ['au-dessus de la normale', 'amber'] : ['normal', 'pos']; }
function bullMd(v) { return v === null || v === undefined ? '—' : (v / 1e9).toLocaleString('fr-FR', { maximumFractionDigits: 0 }) + ' Md$'; }

function fnBULL(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const C = d.cape, B = d.buffett, L = d.largeur, K = d.complaisance, T = d.thermometre;
  const [niv, cls] = bullNiveau(T.score);
  let h = fnHeader('BULL <span class="muted">Thermomètre de bulle</span>', `valorisation · bourse / économie · largeur · complaisance · titres IA · calculé le ${esc(d.genere_le)}`,
    `<a class="lnk" onclick="bullRecalculer()">Recalculer ›</a>`);

  h += '<div class="kpis">' + kpi('Thermomètre (0-100)', `${(T.score * 100).toFixed(0)} <span class="muted small">${niv}</span>`, cls)
    + kpi(`CAPE de Shiller (${esc(C.date)})`, `${C.actuel.toFixed(1)} <span class="muted small">moy. ${C.moyenne.toFixed(1)}</span>`, C.actuel > 30 ? 'neg' : '')
    + (B ? kpi(`Buffett${B.estime ? ' (estimé)' : ''}`, `${(B.actuel * 100).toFixed(0)} % <span class="muted small">du PIB</span>`, B.actuel > 1.5 ? 'neg' : '') : '')
    + kpi('Équipondéré − S&P 500 (12 mois)', `${L.ecart_12m >= 0 ? '+' : ''}${(L.ecart_12m * 100).toFixed(1)} pt`, L.ecart_12m < -0.05 ? 'neg' : '')
    + kpi('Secteurs au-dessus de la MM200', L.part_secteurs_au_dessus === null ? '—' : `${Math.round(L.part_secteurs_au_dessus * L.secteurs.length)} / ${L.secteurs.length}`)
    + kpi(`VIX (${esc(K.date)})`, `${K.vix.toFixed(1)} <span class="muted small">médiane ${K.vix_mediane.toFixed(1)}</span>`, K.vix < 13 ? 'neg' : '')
    + (d.poids_titres_ia ? kpi('Poids des 11 titres IA', pc(d.poids_titres_ia, 0) + ' <span class="muted small">des actions US</span>') : '') + '</div>';

  // 1. thermomètre
  let tc = bullJauge(T.score) + '<table style="margin-top:6px"><tr><th>Composante</th><th class="num">Percentile historique</th><th>Lecture</th></tr>';
  for (const c of T.composantes) { const [n, k] = bullNiveau(c.percentile); tc += `<tr><td>${esc(c.nom)}</td><td class="num ${k}"><b>${(c.percentile * 100).toFixed(0)}</b></td><td class="${k}">${n}</td></tr>`; }
  tc += '</table><div class="muted small" style="margin:6px">Chaque mesure est classée dans sa propre histoire (CAPE depuis 1871, Buffett depuis 1945, équipondéré depuis 2003, VIX depuis 1990). 100 = jamais vu aussi tendu. Moyenne simple, sans pondération optimisée.</div>';
  h += '<div class="grid g-main">' + pan('Thermomètre', 'moyenne des percentiles', tc);

  // 2. CAPE
  const cm = C.valeurs.map(() => C.moyenne), c30 = C.valeurs.map(() => 30);
  let pics = Object.entries(C.pics).filter(([, v]) => v).map(([a, v]) => `${a} : ${v.toFixed(1)}`).join(' · ');
  h += pan('CAPE de Shiller depuis 1871', `${pc(C.percentile, 1)} de l’histoire est plus bas`,
    lineChart('chBullCape', [{ name: 'CAPE', x: C.dates, y: C.valeurs, color: '#ff9900', area: true }, { name: 'Moyenne', x: C.dates, y: cm, color: '#2979ff', width: 1 }, { name: 'Seuil 30', x: C.dates, y: c30, color: '#ff1744', width: 1 }], { height: 240, yfmt: v => v.toFixed(0) })
    + `<div class="muted small" style="margin:6px">Pics : ${pics}. ${C.mois_au_dessus_30} mois au-dessus de 30 depuis 1871. Le CAPE dit qu’on paie cher, pas quand ça s’arrête : il a passé 30 en 1997, trois ans avant le sommet.</div>`) + '</div>';

  // 3. Buffett + largeur
  h += '<div class="grid g-main" style="margin-top:10px">';
  if (B) h += pan('Indicateur de Buffett', `actions des sociétés US / PIB · ${pc(B.percentile, 0)} percentile`,
    lineChart('chBullBuff', [{ name: 'Capitalisation / PIB', x: B.dates, y: B.valeurs, color: '#ff9900', area: true }, { name: 'Moyenne', x: B.dates, y: B.valeurs.map(() => B.moyenne), color: '#2979ff', width: 1 }], { height: 220, yfmt: v => (v * 100).toFixed(0) + ' %' })
    + `<div class="muted small" style="margin:6px">Dernier point publié (Fed, comptes Z.1) : ${(B.dernier_publie * 100).toFixed(0)} % au ${esc(B.date_publie)}${B.estime ? ` ; prolongé au ${esc(B.date_actuel)} avec le Wilshire 5000 : ${(B.actuel * 100).toFixed(0)} %` : ''}. Pic de 2000 : ${(B.max_2000 * 100).toFixed(0)} %, moyenne depuis 1945 : ${(B.moyenne * 100).toFixed(0)} %. Mesure : sociétés non financières (série FRED NCBEILQ027S) — niveau plus élevé que la version « Wilshire / PIB » souvent citée, mais même lecture.</div>`);
  let ts = '<table><tr><th>Secteur</th><th class="num">Écart MM200</th><th class="num">1 an</th></tr>';
  for (const s of L.secteurs) ts += `<tr><td class="amber">${esc(s.symbole)}</td><td class="num ${s.au_dessus ? 'pos' : 'neg'}">${(s.ecart_mm200 * 100).toFixed(1)} %</td>${pcCell(s.perf_1an, 1)}</tr>`;
  h += pan('Largeur du marché', `équipondéré / pondéré · depuis ${esc(L.debut.slice(0, 4))}`,
    lineChart('chBullLarg', [{ name: 'RSP / SPY (base 1)', x: L.dates, y: L.rsp_spy, color: '#ff9900' }], { height: 160, yfmt: v => v.toFixed(2) })
    + `<div class="muted small" style="margin:6px">La courbe baisse quand une poignée de grosses capitalisations porte l’indice. Recul de ${pc(-L.baisse_depuis_haut, 0)} depuis son plus haut (${esc(L.date_haut)}). Sur 12 mois : équipondéré ${pc(L.rsp_1an, 1)}, S&P 500 ${pc(L.spy_1an, 1)}.</div>`
    + `<div style="overflow-x:auto;max-height:220px">${ts}</table></div>`) + '</div>';

  // 4. complaisance
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan('Complaisance : VIX', 'moyenne 1 mois, depuis 1990',
    lineChart('chBullVix', [{ name: 'VIX (moy. 1 mois)', x: K.dates, y: K.vix_mensuel, color: '#ff9900', area: true }], { height: 180, yfmt: v => v.toFixed(0) })
    + `<div class="muted small" style="margin:6px">VIX moyen du mois ${K.vix_mm1m.toFixed(1)} : plus calme que ${pc(K.percentile_calme, 0)} de l’historique. Un VIX endormi pendant que les valorisations montent = peu de protection achetée.${K.skew ? ` SKEW ${K.skew.toFixed(0)} (médiane ${K.skew_mediane.toFixed(0)}, ${pc(K.skew_percentile, 0)} percentile) : les gros investisseurs paient ${K.skew_percentile > 0.8 ? 'cher' : 'normalement'} la protection contre un krach, même avec un VIX ${K.percentile_calme > 0.5 ? 'calme' : 'normal'}.` : ''} Ratio put/call : le CBOE ne le publie plus gratuitement en historique, il n’est donc pas affiché.</div>`);

  // 5. capex hyperscalers
  let tk = '<table><tr><th>Société</th><th class="num">Capex 12 mois</th><th class="num">Flux d’exploitation</th><th class="num">Capex / flux</th><th>Capex annuels</th></tr>';
  for (const c of d.capex) {
    const an = c.annuel.filter(a => a.capex);
    tk += `<tr><td class="amber">${esc(c.symbole)}</td><td class="num">${bullMd(c.capex_ttm)}</td><td class="num">${bullMd(c.flux_ttm)}</td><td class="num ${c.capex_sur_flux > 0.8 ? 'neg' : c.capex_sur_flux > 0.5 ? 'amber' : ''}">${c.capex_sur_flux === null ? '—' : pc(c.capex_sur_flux, 0)}</td><td>${an.length > 1 ? sparkline(an.map(a => a.capex)) + ` <span class="muted small">${esc(an[0].annee)}→${esc(an[an.length - 1].annee)}</span>` : ''}</td></tr>`;
  }
  const tot = d.capex.reduce((s, c) => s + (c.capex_ttm || 0), 0);
  h += pan('Capex IA des hyperscalers', 'SEC EDGAR, douze derniers mois', `<div style="overflow-x:auto;padding:0">${tk}</table></div><div class="muted small" style="margin:6px">Total ${bullMd(tot)} sur 12 mois. La question de la bulle : ces dépenses seront-elles rentabilisées ? Au-delà de 100 % du flux d’exploitation, la société finance ses data centers par la dette ou sa trésorerie.</div>`) + '</div>';

  // 6. titres IA
  let tt = '<table><tr><th>Titre</th><th>Groupe</th><th class="num">Capitalisation</th><th class="num">PER</th><th class="num">1 an</th><th class="num">3 ans</th><th class="num">Écart MM200</th><th class="num">Depuis plus haut 1 an</th><th>1 an</th></tr>';
  for (const t of d.titres) tt += `<tr><td class="amber">${esc(t.symbole)} <span class="muted small">${esc(t.nom)}</span></td><td class="muted">${esc(t.groupe)}</td><td class="num">${t.capitalisation ? (t.capitalisation / 1e12).toFixed(2) + ' T$' : '—'}</td><td class="num ${t.per > 40 ? 'neg' : ''}">${fx(t.per, 1)}</td>${pcCell(t.perf_1an, 0)}${pcCell(t.perf_3ans, 0)}<td class="num ${t.ecart_mm200 > 0.25 ? 'neg' : ''}">${pc(t.ecart_mm200, 1)}</td>${pcCell(t.baisse_depuis_haut, 0)}<td>${t.historique ? sparkline(t.historique) : ''}</td></tr>`;
  h += `<div style="margin-top:10px">${pan('Titres baromètres de l’IA', 'clic sur un ticker : GP', `<div style="overflow-x:auto;padding:0">${tt.replace(/<td class="amber">([A-Z]+) /g, (m, s) => `<td class="amber"><a class="lnk" onclick="runCommand('${s} GP')">${s}</a> `)}</table></div>`)}</div>`;

  if (d.erreurs && d.erreurs.length) h += `<div class="muted small neg" style="margin:6px 2px">Sources indisponibles : ${d.erreurs.map(esc).join(' · ')}</div>`;
  return h + noteBas('Sources gratuites : CAPE de R. Shiller (table multpl.com), Fed comptes Z.1 et PIB (FRED), Yahoo (ETF, indices, titres, ^W5000, ^VIX, ^SKEW), SEC EDGAR (capex). Outil de lecture du marché : il ne pilote pas le portefeuille et ne date pas un krach — une bulle peut durer des années après que tous ces voyants sont au rouge.');
}

grcEnregistrerFonction({
  code: 'BULL', titre: 'Thermomètre de bulle', categorie: 'Marchés', secteurs: ['EQUITY', 'INDEX'], alias: ['BULLE', 'BUBBLE'],
  description: 'Ampleur d’une bulle : CAPE de Shiller, indicateur de Buffett, largeur (équipondéré vs S&P 500, secteurs), VIX et SKEW, titres IA (Nvidia, TSMC, ASML, Broadcom, big tech, Oracle, Palantir) et capex des hyperscalers.',
  exemple: 'BULL', chargement: 'Calcul du thermomètre (CAPE, Fed, SEC, Yahoo)…',
  rendu: async () => fnBULL(await fnFetchQ('BULL', '', {})),
});
