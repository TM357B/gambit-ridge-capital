/* Gambit Ridge Capital — terminal : 14-hedge.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ HEDGE : COUVERTURE DU FONDS (BÊTA, VARIANCE MINIMALE, CVaR, CONTRATS, OPTIONS) ============ */

const eur0 = v => (v === null || v === undefined || !isFinite(v)) ? '—' : Math.round(v).toLocaleString('fr-FR') + ' $';

async function hedgeCharger(capital) {
  const el = document.getElementById('hedgeRoot');
  if (el) el.innerHTML = '<div class="loader">Calcul de la couverture…</div>';
  const d = await fnFetchQ('HEDGE', '', capital ? { c: capital } : {});
  const cible = document.getElementById('hedgeRoot');
  if (cible) cible.outerHTML = fnHEDGE(d);
  return d;
}

function fnHEDGE(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const b = d.beta, R = d.risque, o = d.options, mes = d.contrats.MES, es = d.contrats.ES, tx = d.taux;
  let h = fnHeader('HEDGE <span class="muted">Couverture du fonds</span>',
    `positions réelles du ${esc(d.date_positions)} · ${d.n_lignes} lignes · risque mesuré sur ${d.n_jours} séances (${esc(d.periode[0])} → ${esc(d.periode[1])})`, '');
  const caps = [['Actif réel', ''], ['100 k$', 100000], ['250 k$', 250000], ['1 M$', 1000000]];
  h += `<div class="muted small" style="margin:0 2px 8px">Capital couvert : <b class="amber">${eur0(d.capital)}</b> · `
    + caps.map(([l, v]) => `<a class="lnk" onclick="hedgeCharger(${v || 0})">${l}</a>`).join(' · ') + '</div>';

  h += '<div class="kpis">'
    + kpi('Bêta EWMA (63 j) vs S&amp;P 500', b.ewma.toFixed(2))
    + kpi('Bêta de baisse (jours de baisse)', b.baisse.toFixed(2), b.baisse > b.mco + 0.05 ? 'neg' : '')
    + kpi('Corrélation au S&amp;P 500', b.rho.toFixed(2))
    + kpi('Variance retirée par la couverture', pc(b.efficacite, 0), 'pos')
    + kpi('CVaR 95 % / jour', `${pc(R.avant['95'].cvar, 2)} → <span class="pos">${pc(R.variance_min['95'].cvar, 2)}</span>`)
    + kpi('À vendre aujourd’hui', `<span class="amber">${mes.contrats} MES</span>`) + '</div>';

  // 1. bêtas
  h += '<div class="grid g-main">';
  const S = d.serie, i0 = Math.max(0, S.ewma.findIndex(v => v !== null));
  h += pan('Bêta du fonds au S&amp;P 500 dans le temps', 'EWMA 63 j et filtre de Kalman, causaux',
    lineChart('chHedgeBeta', [{ name: 'EWMA', x: S.dates.slice(i0), y: S.ewma.slice(i0), color: '#ff9900', width: 2 }, { name: 'Kalman', x: S.dates.slice(i0), y: S.kalman.slice(i0), color: '#2979ff' }], { height: 220, zero: 0, yfmt: v => v.toFixed(2) }));
  let t = '<table><tr><th>Estimateur</th><th class="num">Bêta</th><th>Lecture</th></tr>';
  t += `<tr><td>MCO sur 2 ans</td><td class="num">${b.mco.toFixed(2)}</td><td class="muted small">h* = Cov/Var, moyenne de la période</td></tr>`;
  t += `<tr><td class="amber">EWMA 63 j</td><td class="num amber"><b>${b.ewma.toFixed(2)}</b></td><td class="muted small">retenu pour les contrats : suit les rotations de la couche tendance</td></tr>`;
  t += `<tr><td>Kalman</td><td class="num">${b.kalman.toFixed(2)}</td><td class="muted small">bêta en marche aléatoire, filtré</td></tr>`;
  t += `<tr><td>De baisse</td><td class="num ${b.baisse > b.mco + 0.05 ? 'neg' : ''}">${b.baisse.toFixed(2)}</td><td class="muted small">${b.baisse > b.mco + 0.05 ? 'le fonds est plus exposé quand le marché baisse : corrélations de crise' : 'pas d’asymétrie marquée'}</td></tr>`;
  t += `<tr><td>CVaR minimale</td><td class="num">${d.cvar_optimal.h.toFixed(2)}</td><td class="muted small">h qui minimise la perte moyenne des 5 % pires jours</td></tr></table>`;
  h += pan('Ratio de couverture', 'u* = Cov(ΔΠ, ΔS) / Var(ΔS)', `<div style="overflow-x:auto;padding:0">${t}</div>`) + '</div>';

  // 2. risque avant / après
  const lig = [['Volatilité annuelle', x => pc(x.vol, 1)], ['VaR 95 % / jour', x => pc(x['95'].var, 2)], ['CVaR 95 % / jour', x => pc(x['95'].cvar, 2)],
    ['VaR 99 % / jour', x => pc(x['99'].var, 2)], ['CVaR 99 % / jour', x => pc(x['99'].cvar, 2)], ['VaR 95 % Cornish-Fisher', x => pc(x['95'].var_cf, 2)],
    ['Pire baisse (2 ans)', x => pc(x.pire_baisse, 1)], ['Rendement annuel (2 ans)', x => pc(x.rendement_annuel, 1)]];
  let tr = '<table><tr><th></th><th class="num">Sans couverture</th><th class="num">Variance min.</th><th class="num">CVaR min.</th></tr>';
  for (const [l, f] of lig) tr += `<tr><td>${l}</td><td class="num">${f(R.avant)}</td><td class="num amber">${f(R.variance_min)}</td><td class="num">${f(R.cvar_min)}</td></tr>`;
  tr += '</table>';
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan('Risque avant / après couverture', 'portefeuille du jour rejoué sur 2 ans', `<div style="overflow-x:auto;padding:0">${tr}</div>`);

  // 3. exécution : contrats
  let tc = '<table><tr><th>Instrument</th><th class="num">Prix</th><th class="num">Notionnel</th><th class="num">Exact</th><th class="num">Ordre</th><th class="num">Bêta résiduel</th></tr>';
  for (const [k, c] of [['MES', mes], ['ES', es]]) tc += `<tr><td class="amber">${k} <span class="muted small">${esc(c.nom)}</span></td><td class="num">${c.prix.toFixed(2)}</td><td class="num">${eur0(c.notionnel_contrat)}</td><td class="num">${c.exact.toFixed(2)}</td><td class="num"><b>${c.contrats >= 0 ? 'vendre' : 'acheter'} ${Math.abs(c.contrats)}</b></td><td class="num">${c.beta_residuel.toFixed(3)}</td></tr>`;
  tc += `<tr><td class="amber">ZN <span class="muted small">Treasury 10 ans</span></td><td class="num">${tx.prix_zn.toFixed(2)}</td><td class="num">DV01 ${tx.dv01_zn.toFixed(0)} $/pb</td><td class="num">${(tx.dv01_fonds / tx.dv01_zn).toFixed(2)}</td><td class="num"><b>${tx.contrats_zn >= 0 ? 'vendre' : 'acheter'} ${Math.abs(tx.contrats_zn)}</b></td><td class="num">—</td></tr></table>`;
  tc += `<div class="muted small" style="margin:6px">Contrats ≈ bêta × valeur / (prix × multiplicateur). DV01 du fonds : <b>${tx.dv01_fonds.toFixed(0)} $/pb</b> (duration ${tx.duration_fonds.toFixed(2)}) — ${tx.dv01_fonds < 0 ? 'le fonds est vendeur de duration : il gagne si les taux montent ; la couverture rachète des ZN' : 'le fonds perd si les taux montent ; la couverture vend des ZN'}. La couverture laisse le risque propre, la base future-cash et l’erreur d’estimation du bêta.</div>`;
  h += pan('Ce qu’il faudrait vendre', `capital ${eur0(d.capital)}`, `<div style="overflow-x:auto;padding:0">${tc}</div>`) + '</div>';

  // 4. options + chocs
  h += '<div class="grid g-main" style="margin-top:10px">';
  let to = `<table><tr><th></th><th class="num">Strike</th><th class="num">Prix / action</th><th class="num">Coût / mois</th><th class="num">Coût / an (% actif)</th></tr>`;
  to += `<tr><td class="amber">Put 1 mois −5 %</td><td class="num">${o.put.strike.toFixed(1)}</td><td class="num">${o.put.prix.toFixed(2)}</td><td class="num">${eur0(o.put.cout_mois)}</td><td class="num neg">${pc(o.put.cout_an_pct_actif, 2)}</td></tr>`;
  to += `<tr><td class="amber">Collar −5 % / +5 %</td><td class="num">${o.collar.strike_call.toFixed(1)}</td><td class="num">${(o.put.prix - o.collar.prix_call).toFixed(2)}</td><td class="num">${eur0(o.collar.cout_mois)}</td><td class="num">${pc(o.collar.cout_an_pct_actif, 2)}</td></tr></table>`;
  to += `<div class="muted small" style="margin:6px">Black-Scholes, SPY ${o.spy.toFixed(2)}, VIX ${o.vix.toFixed(2)} (${esc(o.date_vix)}) + 3 pts de skew pour le put, − 2 pts pour le call, taux 3 mois ${pc(o.taux, 2)}. Notionnel = bêta × capital, soit ≈ ${o.put.contrats_spy} contrats d’options SPY (100 titres). Delta du put ${o.put.delta.toFixed(2)}. Hors frais (≈ 5 % de la prime).</div>`;
  h += pan('Protection par options au VIX du jour', 'puts et collar SPY', `<div style="overflow-x:auto;padding:0">${to}</div>`);
  let ts = '<table><tr><th>Choc instantané</th><th class="num">Sans couverture</th><th class="num">+ MES</th><th class="num">+ MES + ZN</th></tr>';
  for (const c of d.chocs) ts += `<tr><td>${esc(c.scenario)}</td>${[c.sans, c.avec_mes, c.avec_mes_zn].map(v => `<td class="num ${v >= 0 ? 'pos' : 'neg'}">${eur0(v)}</td>`).join('')}</tr>`;
  ts += '</table><div class="muted small" style="margin:6px">Premier ordre : bêta EWMA pour les actions, DV01 pour les taux, sensibilités constantes, pas de base ni de convexité.</div>';
  h += pan('Chocs de marché', 'perte ou gain en dollars', `<div style="overflow-x:auto;padding:0">${ts}</div>`) + '</div>';

  // 5. campagne 12
  if (d.campagne12) {
    let tk = '<table><tr><th>Essai</th><th class="num">Sharpe dév.</th><th class="num">Sharpe val.</th><th class="num">Pire baisse val.</th><th class="num">Sharpe 01-07</th><th class="num">CVaR val.</th><th class="num">2008</th><th class="num">Covid</th><th class="num">2022</th><th>Verdict</th></tr>';
    for (const e of d.campagne12.essais) {
      const c = k => e.crises[k] ? `<td class="num ${e.crises[k].rendement >= 0 ? 'pos' : 'neg'}">${pc(e.crises[k].rendement, 1)}</td>` : '<td class="num">—</td>';
      tk += `<tr class="${e.cle === 'REF' ? 'amber' : ''}"><td>${esc(e.nom)}</td><td class="num">${e.sharpe_dev.toFixed(2)}</td><td class="num">${e.sharpe_val.toFixed(2)}</td><td class="num">${pc(e.dd_val, 1)}</td><td class="num">${e.sharpe_0107.toFixed(2)}</td><td class="num">${pc(e.cvar_val, 2)}</td>${c('2008')}${c('covid')}${c('2022')}<td class="${e.verdict === 'ACCEPTÉ' ? 'pos' : e.verdict === 'REJETÉ' ? 'neg' : ''}">${esc(e.verdict)}</td></tr>`;
    }
    h += `<div style="margin-top:10px">${pan('Campagne 12 : ces couvertures auraient-elles amélioré le fonds ?', `pré-enregistrée · calculée le ${esc(d.campagne12.genere_le)}`, `<div style="overflow-x:auto;padding:0">${tk}</table></div>`)}</div>`;
  }
  return `<div id="hedgeRoot">${h}${noteBas('Sources trouvées par l’araignée des docs : ' + d.sources.map(esc).join(' · ') + '. Outil d’analyse : aucun ordre n’est passé, la stratégie de production ne change pas.')}</div>`;
}

grcEnregistrerFonction({
  code: 'HEDGE', titre: 'Couverture du fonds', categorie: 'Risque', alias: ['HDG', 'COUV'],
  description: 'Bêta du fonds (EWMA, Kalman, de baisse), ratio à variance minimale, CVaR, contrats MES/ES/ZN à vendre, puts et collar au VIX du jour, chocs, campagne 12.',
  exemple: 'HEDGE', chargement: 'Calcul de la couverture…',
  rendu: async () => fnHEDGE(await fnFetchQ('HEDGE', '', {})),
});
