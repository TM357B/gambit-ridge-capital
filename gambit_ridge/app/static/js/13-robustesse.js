/* Gambit Ridge Capital — terminal : 13-robustesse.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ ROB : ROBUSTESSE (RÉFÉRENCE ALÉATOIRE, PBO, STATISTIQUES DE TRADING) ============ */

// histogramme horizontal avec repères verticaux (fonds, socle…)
function histoReperes(h, reperes, opts = {}) {
  const narrow = window.innerWidth < 760, W = narrow ? 460 : 1000, H = opts.height || 220, L = 10, R = 10, T = 22, B = 24;
  const b = h.bords, c = h.comptes, lo = Math.min(b[0], ...reperes.map(r => r.v)), hi = Math.max(b[b.length - 1], ...reperes.map(r => r.v));
  const pad = (hi - lo) * 0.04, x0 = lo - pad, x1 = hi + pad, mx = Math.max(...c);
  const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => T + (1 - v / mx) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  c.forEach((k, i) => { const col = opts.couleur ? opts.couleur(b[i], b[i + 1]) : '#4A4A52'; s += `<rect x="${X(b[i]) + 0.5}" y="${Y(k)}" width="${Math.max(0.5, X(b[i + 1]) - X(b[i]) - 1)}" height="${H - B - Y(k)}" fill="${col}"/>`; });
  for (const t of niceTicks(x0, x1, 6)) s += `<text x="${X(t)}" y="${H - 8}" fill="#8A867E" font-size="10" text-anchor="middle">${(opts.fmt || (v => v.toFixed(2)))(t)}</text>`;
  reperes.forEach((r, i) => { s += `<line x1="${X(r.v)}" x2="${X(r.v)}" y1="${T - 4}" y2="${H - B}" stroke="${r.c}" stroke-width="2" ${r.pointille ? 'stroke-dasharray="4,3"' : ''}/><text x="${X(r.v) + (X(r.v) > W * 0.8 ? -4 : 4)}" y="${12 + i * 11}" fill="${r.c}" font-size="10" text-anchor="${X(r.v) > W * 0.8 ? 'end' : 'start'}">${esc(r.l)}</text>`; });
  return s + '</svg>';
}

function tableStats(colonnes) {
  const lignes = [['Taux de gain', s => pc(s.taux_gain, 1)], ['Profit factor', s => s.profit_factor === null ? '—' : s.profit_factor.toFixed(2)],
    ['Gain moyen / perte moyenne', s => s.ratio_gain_perte === null ? '—' : s.ratio_gain_perte.toFixed(2)], ['Espérance', s => pc(s.esperance, 3)],
    ['Meilleur', s => pc(s.meilleur, 2)], ['Pire', s => pc(s.pire, 2)], ['Pire série de pertes', s => s.pire_serie_pertes + ' d’affilée']];
  let t = '<table><tr><th></th>' + colonnes.map(([l]) => `<th class="num">${esc(l)}</th>`).join('') + '</tr>';
  for (const [l, f] of lignes) t += `<tr><td>${l}</td>` + colonnes.map(([, s]) => `<td class="num">${s ? f(s) : '—'}</td>`).join('') + '</tr>';
  return t + '</table>';
}

function heatmapMois(mois) {
  const an = {}; for (const m of mois) { const [y, mm] = m.mois.split('-'); (an[y] = an[y] || {})[+mm] = m.rendement; }
  const noms = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
  let t = '<table class="heat"><tr><th>Année</th>' + noms.map(n => `<th class="num">${n}</th>`).join('') + '<th class="num">Année</th></tr>';
  for (const y of Object.keys(an).sort().reverse()) {
    const tot = Object.values(an[y]).reduce((a, v) => a * (1 + v), 1) - 1;
    t += `<tr><td class="amber">${y}</td>` + noms.map((_, i) => { const v = an[y][i + 1]; return v === undefined ? '<td></td>' : `<td class="num" style="background:${heat(v, 0.04)}">${(v * 100).toFixed(1)}</td>`; }).join('')
      + `<td class="num" style="background:${heat(tot, 0.15)}"><b>${(tot * 100).toFixed(1)}</b></td></tr>`;
  }
  return t + '</table>';
}

function fnROB(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const A = d.aleatoire, P = A.periodes, B = d.pbo, T = d.trading, tr = T.trades_tendance;
  let h = fnHeader('ROB <span class="muted">Robustesse de la stratégie</span>', `référence aléatoire (${A.n.toLocaleString('fr-FR')} stratégies) · surapprentissage (PBO) · statistiques de trading · calculé le ${esc(d.genere_le)}`, '');
  h += '<div class="kpis">' + kpi('Bat le hasard (2008-2019)', `${pc(P.developpement.percentile, 1)} <span class="muted small">p = ${P.developpement.p_valeur.toFixed(4)}</span>`, P.developpement.percentile > 0.95 ? 'pos' : '')
    + kpi('Bat le hasard (2020-2026)', `${pc(P.validation.percentile, 1)} <span class="muted small">p = ${P.validation.p_valeur.toFixed(4)}</span>`, P.validation.percentile > 0.95 ? 'pos' : '')
    + kpi('Surapprentissage si on choisit le « meilleur » réglage (PBO)', pc(B.pbo, 1), B.pbo < 0.2 ? 'pos' : B.pbo > 0.5 ? 'neg' : '')
    + kpi(`Rang de la production / ${B.n_variantes} variantes`, `${B.production.rang}e`)
    + kpi('Trades tendance : taux de gain', pc(tr.taux_gain, 1)) + kpi('Profit factor (trades)', tr.profit_factor.toFixed(2)) + '</div>';

  // 1. référence aléatoire
  const c = P.complet;
  h += '<div class="grid g-main">';
  h += pan('Le fonds face à des stratégies aléatoires', `Sharpe 2008-2026 · ${A.n.toLocaleString('fr-FR')} tirages`,
    histoReperes(c.histogramme, [{ v: c.sharpe_fonds, l: `Fonds ${c.sharpe_fonds.toFixed(2)}`, c: '#E3B65C' }, { v: c.sharpe_socle_seul, l: `Socle 60/40 seul ${c.sharpe_socle_seul.toFixed(2)}`, c: '#8AB4FF', pointille: true }, { v: c.quantiles[50], l: `Médiane du hasard ${c.quantiles[50].toFixed(2)}`, c: '#A39F96', pointille: true }]));
  let t = '<table><tr><th>Période</th><th class="num">Fonds</th><th class="num">Socle seul</th><th class="num">Hasard médian</th><th class="num">Hasard 95e pct</th><th class="num">Percentile</th><th class="num">p-valeur</th></tr>';
  for (const [k, l] of [['developpement', 'Développement 2008-2019'], ['validation', 'Validation 2020-2026'], ['complet', 'Complet']]) {
    const x = P[k];
    t += `<tr><td>${l}</td><td class="num amber"><b>${x.sharpe_fonds.toFixed(2)}</b></td><td class="num">${x.sharpe_socle_seul.toFixed(2)}</td><td class="num">${x.quantiles[50].toFixed(2)}</td><td class="num">${x.quantiles[95].toFixed(2)}</td><td class="num ${x.percentile > 0.95 ? 'pos' : ''}">${pc(x.percentile, 1)}</td><td class="num">${x.p_valeur.toFixed(4)}</td></tr>`;
  }
  t += `</table><div class="muted small" style="margin:6px">Mêmes règles que le fonds (socle 60/40, risque égal, vol cible 10 %, filtre, coûts) ; seule la direction de chaque position de la couche tendance est tirée au hasard, avec la même durée moyenne de tenue et la même intensité. Sur 2008-2026, ${pc(A.aleatoires_complet.part_meilleur_cagr, 1)} des tirages font mieux que le fonds en rendement annuel (fonds ${pc(A.fonds_complet.cagr, 1)}, hasard médian ${pc(A.aleatoires_complet.cagr_mediane, 1)}).</div>`;
  h += pan('Sharpe par période', '', `<div style="overflow-x:auto;padding:0">${t}</div>`) + '</div>';

  // 2. PBO
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan('Probabilité de surapprentissage (CSCV)', `${B.n_combinaisons.toLocaleString('fr-FR')} coupes de ${B.blocs} blocs · ${B.n_variantes} variantes`,
    histoReperes({ bords: B.histogramme_logits.bords, comptes: B.histogramme_logits.comptes }, [{ v: 0, l: 'médiane hors échantillon', c: '#E3B65C', pointille: true }], { couleur: (a, b) => (a + b) / 2 < 0 ? '#F08A73' : '#6CCB8F', fmt: v => v.toFixed(1) })
    + `<div class="muted small" style="margin:6px">Chaque barre : rang hors échantillon (logit) de la variante qui était la meilleure en échantillon. Rouge = elle tombe sous la médiane. PBO = part rouge = <b>${pc(B.pbo, 1)}</b>. Sharpe médian de la « meilleure » : ${B.sharpe_is_meilleur_median.toFixed(2)} en échantillon, ${B.sharpe_oos_meilleur_median.toFixed(2)} hors échantillon (pente de dégradation ${B.pente_degradation.toFixed(2)}).<br><b>Lecture :</b> les ${B.n_variantes} réglages se valent presque tous (Sharpe médian ${B.sharpe_variantes.median.toFixed(2)}) ; classer le « meilleur » sur le passé revient donc à classer du bruit, d’où une PBO élevée. Conséquence pratique : ne pas optimiser finement les paramètres — c’est ce que fait le protocole (réglages fixés avant calcul, production ${B.production.rang}e et non 1re). Même la « meilleure » choisie a posteriori garde hors échantillon un Sharpe médian (${B.sharpe_oos_meilleur_median.toFixed(2)}) bien au-dessus du hasard (${P.complet.quantiles[50].toFixed(2)}) : l’avantage vient de la famille de stratégies, pas du réglage.</div>`);
  const top = [...B.variantes].sort((a, b) => b.sharpe - a.sharpe);
  let tv = '<table><tr><th class="num">Rang</th><th>Signal</th><th class="num">Socle</th><th class="num">Vol cible</th><th class="num">Rebal.</th><th class="num">Sharpe</th></tr>';
  top.forEach((v, i) => { const prod = v.signal === 'ensemble' && v.socle === 0.5 && v.vol_cible === 0.1 && v.rebalancement === 5; if (i < 10 || prod) tv += `<tr class="${prod ? 'amber' : ''}"><td class="num">${i + 1}</td><td>${esc(v.signal)}${prod ? ' ← production' : ''}</td><td class="num">${(v.socle * 100).toFixed(0)} %</td><td class="num">${(v.vol_cible * 100).toFixed(0)} %</td><td class="num">${v.rebalancement} j</td><td class="num">${v.sharpe.toFixed(2)}</td></tr>`; });
  h += pan('Grille de variantes 2008-2026', `Sharpe de ${B.sharpe_variantes.min.toFixed(2)} à ${B.sharpe_variantes.max.toFixed(2)}`, `<div style="overflow-x:auto;padding:0;max-height:330px">${tv}</table></div>`) + '</div>';

  // 3. statistiques de trading
  const cols = [['ETF 2008-2026', T.etf_2008_2026], ['Fonds 95/5 2018-2026', T.fonds_95_5_2018_2026]];
  if (d.reel) cols.push([`Réel ${d.reel.debut} → ${d.reel.fin}`, d.reel]);
  h += '<div class="grid g-main" style="margin-top:10px">';
  const per = k => cols.map(([l, s]) => [l, s ? s[k] : null]);
  h += pan('Statistiques par jour', '', `<div style="overflow-x:auto;padding:0">${tableStats(per('jours'))}</div>`);
  h += pan('Statistiques par mois', '', `<div style="overflow-x:auto;padding:0">${tableStats(per('mois'))}</div>`);
  h += '</div>';
  const e = T.etf_2008_2026;
  h += `<div class="muted small" style="margin:6px 2px">Avant / après coûts (ETF 2008-2026) : Sharpe ${T.etf_avant_couts.sharpe.toFixed(2)} → ${e.sharpe.toFixed(2)}, rendement annuel ${pc(T.etf_avant_couts.cagr, 1)} → ${pc(e.cagr, 1)} ; coûts ≈ ${tr.couts_totaux_pb_an.toFixed(0)} pb par an. Asymétrie ${e.asymetrie.toFixed(2)}, kurtosis ${e.kurtosis.toFixed(1)}.${d.reel ? ' Le réel ne compte que ' + d.reel.jours.n + ' jours : trop peu pour conclure.' : ''}</div>`;

  // 4. trades de la couche tendance
  h += '<div class="grid g-main" style="margin-top:10px">';
  let tt = `<div class="kpis" style="margin:0 0 6px">${kpi('Positions', tr.n.toLocaleString('fr-FR'))}${kpi('Durée moyenne', tr.duree_moyenne_jours.toFixed(0) + ' j')}${kpi('Gain / perte moyens', `${tr.gain_moyen_pb.toFixed(1)} / ${tr.perte_moyenne_pb.toFixed(1)} pb`)}${kpi('Pire série', tr.pire_serie_pertes + ' pertes')}</div>`;
  tt += '<div style="overflow-x:auto;max-height:300px"><table><tr><th>Actif</th><th class="num">Positions</th><th class="num">Taux de gain</th><th class="num">P&amp;L cumulé</th></tr>';
  for (const [k, v] of Object.entries(tr.par_actif).sort((a, b) => b[1].pnl_pb - a[1].pnl_pb)) tt += `<tr><td class="amber">${esc(k)}</td><td class="num">${v.n}</td><td class="num">${pc(v.taux_gain, 0)}</td><td class="num ${v.pnl_pb >= 0 ? 'pos' : 'neg'}">${v.pnl_pb.toFixed(0)} pb</td></tr>`;
  h += pan('Positions de la couche tendance', 'un actif tenu dans le même sens = une position', tt + '</table></div>');
  h += pan('Rendements mensuels du fonds (95/5)', 'backtest 2018-2026, coûts inclus', `<div style="overflow-x:auto;padding:0">${heatmapMois(T.fonds_95_5_2018_2026.mois_detail)}</div>`) + '</div>';
  return h + noteBas(`Lecture : un taux de gain par position faible (${pc(tr.taux_gain, 0)}) avec des gains moyens ${tr.ratio_gain_perte.toFixed(1)} fois plus gros que les pertes est la signature d'un suivi de tendance — beaucoup de petites pertes coupées vite, quelques grosses tendances tenues longtemps. Les séries de ${tr.pire_serie_pertes} pertes d’affilée sont donc normales. À l'inverse des systèmes « 99 % de trades gagnants » (grilles, martingales) dont une seule perte non coupée efface tout. Méthodes : Bailey, Borwein, López de Prado & Zhu (2015) pour la PBO ; test de permutation du timing pour la référence aléatoire.`);
}
