/* Gambit Ridge Capital — terminal : 10-modeles-ml.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ MODÈLES DE « MACHINE LEARNING IN FINANCE » (Dixon, Halperin & Bilokon) ============ */
const LIVRE = 'Dixon, Halperin & Bilokon, Machine Learning in Finance';
function livre(ch) { return `<span class="muted small">${esc(LIVRE)}, ${esc(ch)}</span>`; }
function noteBas(t) { return `<div class="muted small" style="margin:8px 2px;line-height:1.5">${t}</div>`; }
function pan(titre, droite, corps, style = '') { return `<div class="panel" style="${style}"><div class="panel-h">${titre}${droite ? ` <span class="rt">${droite}</span>` : ''}</div><div class="panel-b">${corps}</div></div>`; }
function symField(sym) { return qf('Sous-jacent', `<input type="text" value="${esc(sym)}" style="width:90px" onchange="FN_STATE.sym=normTicker(this.value)" onkeydown="if(event.key==='Enter'){FN_STATE.sym=normTicker(this.value);renderFn()}">`); }
function fx(v, d = 2) { return v === null || v === undefined || !isFinite(v) ? '—' : v.toFixed(d); }

// barres verticales (ACF, PACF…) avec bande de significativité ±b
function barsSvg(vals, opts = {}) {
  const narrow = window.innerWidth < 760, W = narrow ? 460 : 1000, H = opts.height || 180, L = 40, R = 8, T = 10, B = 22;
  const lo = Math.min(-0.15, ...vals, -(opts.band || 0) * 1.3), hi = Math.max(0.15, ...vals, (opts.band || 0) * 1.3);
  const n = vals.length, bw = (W - L - R) / n, Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let s = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">`;
  if (opts.band) s += `<rect x="${L}" y="${Y(opts.band)}" width="${W - L - R}" height="${Y(-opts.band) - Y(opts.band)}" fill="#8AB4FF" opacity="0.12"/>`;
  for (const t of niceTicks(lo, hi, 4)) s += `<text x="${L - 5}" y="${Y(t) + 3}" fill="#8A867E" font-size="10" text-anchor="end">${t.toFixed(2)}</text>`;
  vals.forEach((v, i) => { const out = opts.band && Math.abs(v) > opts.band; s += `<rect x="${L + i * bw + bw * 0.2}" y="${Math.min(Y(v), Y(0))}" width="${bw * 0.6}" height="${Math.abs(Y(v) - Y(0))}" fill="${opts.colors ? opts.colors[i] : out ? '#E3B65C' : '#8A867E'}"><title>${(opts.labels || [])[i] ?? i} : ${v.toFixed(3)}</title></rect>`; });
  (opts.labels || vals.map((_, i) => i)).forEach((l, i) => { if (i % Math.ceil(n / 20) === 0) s += `<text x="${L + (i + 0.5) * bw}" y="${H - 7}" fill="#8A867E" font-size="10" text-anchor="middle">${l}</text>`; });
  return s + `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="#6E6A63"/></svg>`;
}

/* ---------------- QLBS ---------------- */
FN_STATE.qlbs = { type: 'put', spot: 100, strike: 100, maturite: 1, pas: 24, mu: 5, vol: 15, taux: 3, lambda: 0.001, n: 20000 };
function fnQLBS(d) {
  const st = FN_STATE.qlbs, P = 'FN_STATE.qlbs.';
  let h = '<div class="qform">' + qf('Option', qsel(P + 'type', st.type, [['put', 'Put'], ['call', 'Call']])) + qf('Spot', qnum(P + 'spot', st.spot)) + qf('Strike', qnum(P + 'strike', st.strike))
    + qf('Maturité (ans)', qnum(P + 'maturite', st.maturite, 0.25)) + qf('Recouvertures', qnum(P + 'pas', st.pas, 1)) + qf('Drift μ (%)', qnum(P + 'mu', st.mu, 0.5))
    + qf('Vol σ (%)', qnum(P + 'vol', st.vol, 0.5)) + qf('Taux r (%)', qnum(P + 'taux', st.taux, 0.25)) + qf('Aversion λ', qnum(P + 'lambda', st.lambda, 0.0005))
    + qf('Trajectoires', qsel(P + 'n', st.n, [[10000, '10 000'], [20000, '20 000'], [50000, '50 000']])) + '<button class="btn" onclick="renderFn()">PRICER &lt;GO&gt;</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const x = d.prix, p = d.params, c0 = d.couverture0;
  h += fnHeader(`QLBS <span class="muted">Q-Learner in the Black-Scholes world</span>`, `${p.type === 'put' ? 'Put' : 'Call'} K ${p.strike} · ${p.pas} recouvertures sur ${p.maturite} an · λ = ${p.lambda} · ${p.n.toLocaleString('fr-FR')} trajectoires · ${d.ms} ms`, livre('ch. 10 § 2-4'));
  h += '<div class="kpis">' + kpi('Prix QLBS (ask vendeur)', `<span class="amber">${x.qlbs.toFixed(3)}</span>`) + kpi('Prix équitable E[Π₀]', x.equitable.toFixed(3))
    + kpi('Black-Scholes (temps continu)', x.bs.toFixed(3)) + kpi('Prime de risque de couverture', `${sgn(x.prime_risque, 3)} <span class="muted small">(${sgn(x.prime_risque / x.bs * 100, 1)} %)</span>`)
    + kpi('Couverture t₀ : QLBS / delta BS', `${c0.qlbs.toFixed(3)} / ${c0.bs.toFixed(3)}`) + '</div>';
  const sl = d.sens_lambda, sp = d.sens_pas, cb = d.courbe;
  h += '<div class="grid g-main">';
  h += pan('Prix contre aversion au risque λ', 'la prime rémunère le risque de mauvaise couverture', lineChart('chQL1', [{ name: 'QLBS', x: sl.map(s => 'λ ' + s.lambda), y: sl.map(s => s.prix), color: '#E3B65C', width: 2 }, { name: 'Black-Scholes', x: sl.map(s => 'λ ' + s.lambda), y: sl.map(() => x.bs), color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(2) }));
  h += pan('Prix contre fréquence de recouverture', 'plus de recouvertures : plus de variances pénalisées', lineChart('chQL2', [{ name: 'QLBS', x: sp.map(s => s.pas + ' pas'), y: sp.map(s => s.prix), color: '#E3B65C', width: 2 }, { name: 'Équitable', x: sp.map(s => s.pas + ' pas'), y: sp.map(s => s.equitable), color: '#6CCB8F' }, { name: 'Black-Scholes', x: sp.map(s => s.pas + ' pas'), y: sp.map(() => x.bs), color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(2) }));
  h += '</div><div class="grid g-main" style="margin-top:10px">';
  h += pan('Couverture optimale à mi-vie', `${cb.jours_restants} jours restants · QLBS vs delta BS`, lineChart('chQL3', [{ name: 'QLBS (régression sur B-splines)', x: cb.spot.map(v => v.toFixed(1)), y: cb.dp, color: '#E3B65C', width: 2 }, { name: 'Delta Black-Scholes', x: cb.spot.map(v => v.toFixed(1)), y: cb.bs, color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(2) }));
  const hc = d.cout_couverture;
  h += pan('Distribution du coût de couverture Π₀', `écart-type ${hc.ecart_type.toFixed(2)} : le risque que BS ignore`, barsSvg(hc.comptes.map(c => c / Math.max(...hc.comptes)), { labels: hc.bords.slice(0, -1).map(v => v.toFixed(1)), colors: hc.bords.slice(0, -1).map(v => v > x.qlbs ? '#F08A73' : '#E3B65C'), height: 230 }) + '<div class="legend2"><span style="color:#E3B65C">■</span> coût de couverture réalisé par trajectoire &nbsp; <span style="color:#F08A73">■</span> au-delà du prix QLBS demandé</div>');
  h += '</div>';
  h += noteBas(`Le vendeur couvre l'option en temps discret ; comme on ne recouvre pas en continu, il reste un risque de couverture que Black-Scholes suppose nul. QLBS formule le problème comme un processus de décision markovien : état X<sub>t</sub> (log-prix stationnarisé), action = couverture, récompense = gain de couverture − λ × variance du portefeuille. La couverture optimale et la fonction Q sont obtenues à chaque date par régression transversale sur 12 B-splines (programmation dynamique, éq. 10.45-10.57). Prix QLBS = −Q₀. Contrôles : λ → 0 et μ = r redonnent Black-Scholes ; l'exemple du livre (put à la monnaie, μ 5 %, σ 15 %, r 3 %, λ 0,001, 24 pas) donne 4,90 ± 0,12 contre 4,53 en BS. La variante « apprentissage par renforcement » (Fitted Q Iteration hors politique) n'est pas affichée : testée trajectoire par trajectoire, elle demanderait ~10⁷ trajectoires pour distinguer l'effet de l'action du bruit.`);
  return h;
}

/* ---------------- GPG : prix et grecques appris par processus gaussien ---------------- */
FN_STATE.gpg = { type: 'call', points: 12, strike: 100, maturite: 1, vol: 20, taux: 3 };
function fnGPG(d) {
  const st = FN_STATE.gpg, P = 'FN_STATE.gpg.';
  let h = '<div class="qform">' + qf('Option', qsel(P + 'type', st.type, [['call', 'Call'], ['put', 'Put']])) + qf('Points d’entraînement', qnum(P + 'points', st.points, 1))
    + qf('Strike', qnum(P + 'strike', st.strike)) + qf('Maturité (ans)', qnum(P + 'maturite', st.maturite, 0.25)) + qf('Vol (%)', qnum(P + 'vol', st.vol, 1)) + qf('Taux (%)', qnum(P + 'taux', st.taux, 0.25))
    + '<button class="btn" onclick="renderFn()">APPRENDRE &lt;GO&gt;</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const e = d.erreurs, t = d.test, hy = d.hyper, ml = d.maillage_libre;
  h += fnHeader(`GPG <span class="muted">Prix et grecques appris par processus gaussien</span>`, `${d.params.points} prix Black-Scholes appris · noyau RBF, hyperparamètres par vraisemblance marginale · ${d.ms} ms`, livre('ch. 3 § 5'));
  h += '<div class="kpis">' + kpi('Erreur max sur le prix', e.prix_max.toFixed(4)) + kpi('Erreur max sur le delta', e.delta_max.toFixed(4)) + kpi('Erreur max sur le gamma', `${e.gamma_max.toFixed(5)} <span class="muted small">(${(e.gamma_max / e.gamma_ref * 100).toFixed(1)} % du pic)</span>`)
    + kpi('Longueur de corrélation ℓ', hy.longueur.toFixed(1)) + kpi(`Sans maillage 2D (${ml.points} pts) : erreur moy.`, ml.erreur_moy.toFixed(3)) + '</div>';
  const xs = t.spot.map(v => v.toFixed(1));
  h += '<div class="grid g-main">';
  h += pan('Prix : GP contre Black-Scholes', 'bande : intervalle à 95 % du GP', lineChart('chGPG1', [{ name: 'GP', x: xs, y: t.prix_gp, color: '#E3B65C', width: 2 }, { name: 'GP + IC', x: xs, y: t.prix_gp.map((v, i) => v + t.ic[i]), color: '#5C4A26' }, { name: 'GP − IC', x: xs, y: t.prix_gp.map((v, i) => v - t.ic[i]), color: '#5C4A26' }, { name: 'Black-Scholes', x: xs, y: t.prix_bs, color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(1) }));
  h += pan('Delta : dérivée analytique du GP', 'aucune différence finie', lineChart('chGPG2', [{ name: 'Delta GP', x: xs, y: t.delta_gp, color: '#E3B65C', width: 2 }, { name: 'Delta BS', x: xs, y: t.delta_bs, color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(2) }));
  h += '</div><div class="grid g-main" style="margin-top:10px">';
  h += pan('Gamma : dérivée seconde du GP', '', lineChart('chGPG3', [{ name: 'Gamma GP', x: xs, y: t.gamma_gp, color: '#E3B65C', width: 2 }, { name: 'Gamma BS', x: xs, y: t.gamma_bs, color: '#8AB4FF' }], { height: 230, yfmt: v => v.toFixed(3) }));
  h += pan('Sans maillage : prix appris sur un nuage (S, T)', 'erreur absolue · 3D', surface3d('s3dGPG', ml.spot.map(v => v.toFixed(0)), ml.maturites.map(v => v.toFixed(2) + ' a'), ml.erreur, { xtitle: 'Spot', ytitle: 'Maturité', ztitle: 'Erreur', cmap: 'viridis', zfmt: v => v.toFixed(2), height: 300, tip: (i, j, v) => `S ${ml.spot[j]} · T ${ml.maturites[i]} : erreur <b>${v.toFixed(4)}</b>` }));
  h += '</div>' + noteBas(`Un processus gaussien apprend la fonction prix à partir de quelques évaluations (ici des prix Black-Scholes, en pratique des prix d'un modèle lent : Heston, Monte-Carlo…). Les grecques sont les dérivées analytiques de la moyenne a posteriori : ∂k/∂x = −(x − x')/ℓ² k. L'erreur grandit hors de la zone apprise, et le GP le dit lui-même : l'intervalle s'élargit. C'est l'idée des « substituts » qui accélèrent la valorisation d'un portefeuille de dérivés.`);
  return h;
}

/* ---------------- GPVS : surface de vol lissée par GP ---------------- */
function fnGPVS(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const hy = d.hyper, K = d.moneyness.map(k => Math.round(k * 100) + '%'), J = d.jours.map(j => Math.round(j) + ' j');
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">Surface de vol lissée par processus gaussien</span>`, `GPVS · ${esc(d.asof)} NY · ${d.n_appris} cotations apprises sur ${d.n_points} · ${d.ms} ms`, livre('ch. 3'));
  h += '<div class="kpis">' + kpi('Écart quadratique aux cotations', fx(d.residus.rmse_pts) + ' pt de vol') + kpi('Écart max', fx(d.residus.max_pts) + ' pt')
    + kpi('Longueur en moneyness (log)', fx(hy.longueur_moneyness, 3)) + kpi('Longueur en √T', fx(hy.longueur_racine_T, 3)) + kpi('Bruit estimé', fx(hy.bruit * 100) + ' pt') + '</div>';
  h += '<div class="grid g-main">';
  h += pan('Surface lissée (moyenne a posteriori)', 'vol implicite %', surface3d('s3dGPVS', K, J, d.vol, { xtitle: 'Strike / spot', ytitle: 'Maturité', ztitle: 'Vol %', cmap: 'jet', clip: [0.01, 0.99], zfmt: v => v.toFixed(0) + '%', az: -2.45, el: 0.42, height: 380, tip: (i, j, v) => `${K[j]} · ${J[i]} : <b>${v.toFixed(2)} %</b> ± ${d.incertitude[i][j].toFixed(2)}` }));
  h += pan('Incertitude (intervalle à 95 %)', 'grandit là où il n’y a pas de cotations', surface3d('s3dGPVSu', K, J, d.incertitude, { xtitle: 'Strike / spot', ytitle: 'Maturité', ztitle: '± pts', cmap: 'viridis', clip: [0.0, 0.98], zfmt: v => v.toFixed(1), az: -2.45, el: 0.42, height: 380 }));
  h += '</div>' + noteBas(`Entrées : log(K/S) et √T ; noyau RBF à une longueur par entrée (pertinence automatique), hyperparamètres par maximum de vraisemblance marginale. Contrairement à l'interpolation linéaire d'OVDV, le GP donne une surface lisse partout ET la confiance qu'on peut lui accorder : utile pour pricer hors des strikes cotés en sachant ce qu'on risque.`);
  return h;
}

/* ---------------- SVOL : volatilité stochastique par filtre particulaire ---------------- */
FN_STATE.svol = { ans: 3, sauts: '0' };
function fnSVOL(d, sym) {
  const st = FN_STATE.svol, P = 'FN_STATE.svol.';
  let h = '<div class="qform">' + symField(sym) + qf('Historique (ans)', qnum(P + 'ans', st.ans, 1)) + qf('Modèle', qsel(P + 'sauts', st.sauts, [['0', 'SVL : levier'], ['1', 'SVLJ : levier + sauts']]))
    + '<button class="btn" onclick="renderFn()">FILTRER &lt;GO&gt;</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  const p = d.params, v = d.vraisemblance, l = d.derniere;
  h += fnHeader(`${esc(d.symbol)} <span class="muted">Volatilité stochastique · filtre particulaire</span>`, `SVOL · ${d.sauts ? 'SVLJ' : 'SVL'} · ${d.jours} séances · calibrage par ${d.evaluations} filtres · ${d.ms} ms`, livre('ch. 7 § 3-4'));
  h += '<div class="kpis">' + kpi('Vol filtrée aujourd’hui', `<span class="amber">${pctS(l.sv)}</span>`) + kpi('GARCH(1,1) / réalisée 21 j', `${pctS(l.garch)} / ${pctS(l.realisee)}`)
    + kpi('Levier ρ', `${p.rho.toFixed(2)} <span class="muted small">${p.rho < -0.3 ? 'la vol monte quand le prix baisse' : ''}</span>`) + kpi('Persistance φ · demi-vie', `${p.phi.toFixed(3)} · ${p.demi_vie_jours ? p.demi_vie_jours.toFixed(0) + ' j' : '—'}`)
    + kpi('Vol de long terme', pctS(p.vol_long_terme)) + kpi('AIC : SV / GARCH', `${v.aic_sv.toFixed(0)} / ${v.aic_garch.toFixed(0)} <span class="${v.aic_sv < v.aic_garch ? 'pos' : 'neg'} small">${v.aic_sv < v.aic_garch ? 'SV meilleur' : 'GARCH meilleur'}</span>`) + '</div>';
  h += pan('Volatilité annualisée', 'bande : 5 – 95 % des particules', lineChart('chSV', [{ name: 'SV filtrée', x: d.dates, y: d.vol_sv.map(v => v * 100), color: '#E3B65C', width: 2 }, { name: 'SV 5 %', x: d.dates, y: d.q05.map(v => v * 100), color: '#5C4A26' }, { name: 'SV 95 %', x: d.dates, y: d.q95.map(v => v * 100), color: '#5C4A26' }, { name: 'GARCH(1,1)', x: d.dates, y: d.vol_garch.map(v => v * 100), color: '#8AB4FF', width: 1.2 }, { name: 'Réalisée 21 j', x: d.dates, y: d.vol_realisee.map(v => v === null ? NaN : v * 100), color: '#8A867E', width: 1 }], { height: 320, yfmt: v => v.toFixed(0) + ' %' }));
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan('Prévision de la vol par le modèle', 'retour vers la moyenne de long terme', lineChart('chSVf', [{ name: 'Vol prévue', x: d.prevision.map(f => f.jours + ' j'), y: d.prevision.map(f => f.vol * 100), color: '#E3B65C', width: 2 }, { name: 'Long terme', x: d.prevision.map(f => f.jours + ' j'), y: d.prevision.map(() => p.vol_long_terme * 100), color: '#6E6A63' }], { height: 200, yfmt: v => v.toFixed(1) + ' %' }));
  let t = '<table><tr><th>Paramètre</th><th class="num">Valeur</th><th>Sens</th></tr>';
  const r = (a, b, c) => `<tr><td>${a}</td><td class="num">${b}</td><td class="muted small">${c}</td></tr>`;
  t += r('μ (log-variance moyenne)', p.mu.toFixed(2), 'niveau de vol vers lequel elle revient') + r('φ', p.phi.toFixed(4), 'mémoire des chocs de vol') + r('σ<sub>v</sub>', p.sigma_v.toFixed(3), 'vol de la vol') + r('ρ', p.rho.toFixed(3), 'effet de levier (corrélation rendement / vol)');
  if (d.sauts) t += r('p (sauts)', (p.p_saut * 100).toFixed(2) + ' %/j', 'probabilité quotidienne de saut') + r('σ<sub>J</sub>', (p.sigma_saut * 100).toFixed(2) + ' %', 'taille typique d’un saut');
  t += r('Log-vraisemblance SV / GARCH', `${v.sv.toFixed(1)} / ${v.garch.toFixed(1)}`, `${v.n_params_sv} contre ${v.n_params_garch} paramètres`) + '</table>';
  h += pan('Paramètres calibrés', 'maximum de vraisemblance particulaire', `<div style="padding:0;overflow-x:auto">${t}</div>`) + '</div>';
  h += noteBas(`Modèle : y<sub>t</sub> = ε<sub>t</sub> e<sup>x<sub>t</sub>/2</sup> (+ saut), x<sub>t+1</sub> = μ(1−φ) + φx<sub>t</sub> + σ<sub>v</sub>η<sub>t</sub>, corr(ε, η) = ρ. Contrairement à la GARCH, la vol est un état caché avec son propre bruit ; le filtre SIR la suit avec des particules pondérées par la vraisemblance de chaque rendement, puis rééchantillonnées. Le calibrage maximise la vraisemblance du filtre (Nelder-Mead, nombres aléatoires communs).`);
  return h;
}

/* ---------------- BETA : bêta bayésien ---------------- */
FN_STATE.beta = { indice: 'SPY' };
function fnBETA(d, sym) {
  const st = FN_STATE.beta;
  let h = '<div class="qform">' + symField(sym) + qf('Indice', `<input type="text" value="${esc(st.indice)}" style="width:90px" onchange="FN_STATE.beta.indice=normTicker(this.value)">`) + '<button class="btn" onclick="renderFn()">CALCULER &lt;GO&gt;</button></div>';
  if (d.error) return h + `<div class="loader neg">${esc(d.error)}</div>`;
  h += fnHeader(`${esc(d.symbol)} <span class="muted">Bêta bayésien contre ${esc(d.indice)}</span>`, `BETA · rendements quotidiens · ${esc(d.asof)} · ${d.ms} ms`, livre('ch. 2 § 6, ch. 3 § 2'));
  h += '<div class="kpis">' + kpi('Bêta 1 an', `<span class="amber">${d.beta_1an.toFixed(2)}</span>`) + kpi('Intervalle de crédibilité 95 %', `${d.ic95[0].toFixed(2)} – ${d.ic95[1].toFixed(2)}`)
    + kpi('Bêta 5 ans (séquentiel)', d.beta_5ans.toFixed(2)) + kpi('Alpha annualisé', pctS(d.alpha_an)) + kpi('R²', d.r2.toFixed(2)) + kpi('Vol spécifique', pctS(d.vol_specifique)) + '</div>';
  const g = d.glissant;
  h += '<div class="grid g-main">';
  h += pan('Bêta glissant 1 an', 'bande : crédibilité 95 % · gris : MCO', lineChart('chBETA', [{ name: 'Bêta bayésien', x: g.map(x => x.date), y: g.map(x => x.beta), color: '#E3B65C', width: 2 }, { name: 'Haut', x: g.map(x => x.date), y: g.map(x => x.haut), color: '#5C4A26' }, { name: 'Bas', x: g.map(x => x.date), y: g.map(x => x.bas), color: '#5C4A26' }, { name: 'MCO', x: g.map(x => x.date), y: d.mco, color: '#8A867E', width: 1 }], { height: 260, zero: 1, yfmt: v => v.toFixed(2) }));
  const s = d.sequentiel;
  h += pan('Apprentissage séquentiel', 'chaque mois, la loi a posteriori devient l’a priori', lineChart('chBETAs', [{ name: 'Bêta', x: s.map(x => x.date), y: s.map(x => x.beta), color: '#6CCB8F', width: 2 }, { name: 'Haut', x: s.map(x => x.date), y: s.map(x => x.haut), color: '#2F5E43' }, { name: 'Bas', x: s.map(x => x.date), y: s.map(x => x.bas), color: '#2F5E43' }], { height: 260, zero: 1, yfmt: v => v.toFixed(2) }));
  h += '</div>' + noteBas(`Régression conjuguée Normale-Gamma inverse : a priori bêta ≈ 1 ± 0,5 (un actif moyen bouge comme le marché), puis les données le corrigent. La loi a posteriori est exacte, sans simulation, et l'intervalle de crédibilité se lit comme une probabilité. Avec peu de données, l'a priori stabilise l'estimation ; avec beaucoup, les données dominent.`);
  return h;
}

/* ---------------- REGM : régimes ---------------- */
function fnREGM(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">Régimes de marché : mélanges contre HMM</span>`, `REGM · ${d.n} séances · kurtosis ${d.kurtosis.toFixed(1)} · ${d.ms} ms`, livre('ch. 2 § 7-8, ch. 7 § 2'));
  const best = d.modeles.reduce((a, b) => (a.bic < b.bic ? a : b));
  h += '<div class="grid g-main"><div class="panel"><div class="panel-h">Sélection de modèles <span class="rt">BIC : vraisemblance pénalisée par la complexité</span></div><div class="panel-b" style="padding:4px"><table><tr><th>Modèle</th><th class="num">Paramètres</th><th class="num">Log-vrais.</th><th class="num">BIC</th><th class="num">Poids</th></tr>';
  for (const m of d.modeles) h += `<tr><td class="${m === best ? 'amber' : ''}">${esc(m.nom)}${m === best ? ' ✓' : ''}</td><td class="num">${m.params}</td><td class="num">${m.llh.toFixed(0)}</td><td class="num">${m.bic.toFixed(0)}</td><td class="num">${(m.poids * 100).toFixed(1)} %</td></tr>`;
  h += '</table></div></div>';
  const hm = d.hmm, mx = d.melange;
  let t = `<table><tr><th>État HMM</th><th class="num">Vol</th><th class="num">Rend.</th><th class="num">Persistance</th><th class="num">Durée moy.</th></tr>`;
  hm.vol_an.forEach((v, i) => { t += `<tr><td>${['Calme', 'Normal', 'Stress'].slice(3 - hm.K)[i] || 'État ' + i}</td><td class="num">${pctS(v, 0)}</td><td class="num">${pctS(hm.rend_an[i], 0)}</td><td class="num">${(hm.persistance[i] * 100).toFixed(1)} %</td><td class="num">${hm.duree_jours[i].toFixed(0)} j</td></tr>`; });
  t += `</table><table style="margin-top:8px"><tr><th>Composante (mélange ${mx.K})</th><th class="num">Poids</th><th class="num">Vol</th><th class="num">Rend.</th></tr>`;
  mx.vol_an.forEach((v, i) => { t += `<tr><td>${i + 1}</td><td class="num">${(mx.poids[i] * 100).toFixed(1)} %</td><td class="num">${pctS(v, 0)}</td><td class="num">${pctS(mx.rend_an[i], 0)}</td></tr>`; });
  h += pan('Régimes estimés', 'rendements et vols annualisés', `<div style="overflow-x:auto">${t}</div>`) + '</div>';
  h += '<div class="grid g-main" style="margin-top:10px">';
  h += pan('Probabilité du régime de stress', 'HMM (filtré, causal) vs mélange (sans mémoire)', lineChart('chREGM', [{ name: 'HMM', x: d.dates, y: d.prob_stress_hmm, color: '#F08A73', width: 1.6 }, { name: 'Mélange', x: d.dates, y: d.prob_stress_melange, color: '#8A867E', width: 1 }], { height: 240, yfmt: v => (v * 100).toFixed(0) + ' %' }));
  const hg = d.histogramme;
  h += pan('Distribution des rendements', 'barres : observé · orange : mélange · bleu : loi normale', lineChart('chREGMh', [{ name: 'Observé', x: hg.centres.map(v => (v * 100).toFixed(1) + '%'), y: hg.comptes, color: '#6E6A63', width: 1, area: true }, { name: 'Mélange', x: hg.centres.map(v => (v * 100).toFixed(1) + '%'), y: hg.melange, color: '#E3B65C', width: 2 }, { name: 'Normale', x: hg.centres.map(v => (v * 100).toFixed(1) + '%'), y: hg.normale, color: '#8AB4FF', width: 1.5 }], { height: 240, yfmt: v => v.toFixed(0) }));
  h += '</div>' + noteBas(`Le mélange gaussien (EM) capture les queues épaisses — plusieurs « humeurs » de marché — mais tire chaque jour son régime au hasard. Le HMM ajoute la persistance : les régimes durent (matrice de transition). Le BIC tranche en pénalisant les paramètres (rasoir d'Occam) ; les poids e<sup>−BIC/2</sup> donnent la moyenne de modèles. Rappel honnête : un filtre de régimes HMM a été testé comme stratégie et rejeté (pas de gain de Sharpe).`);
  return h;
}

/* ---------------- TSA : Box-Jenkins ---------------- */
function fnTSA(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const a1 = d.adf_prix, a2 = d.adf_rendements, lb = d.ljung_box;
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">Analyse de série temporelle (Box-Jenkins)</span>`, `TSA · ${d.n} rendements quotidiens · ${esc(d.asof)}`, livre('ch. 6 § 2-4'));
  h += '<div class="kpis">' + kpi('ADF prix (log)', `${a1.stat.toFixed(2)} <span class="small ${a1.stationnaire_5pct ? 'pos' : 'neg'}">${a1.stationnaire_5pct ? 'stationnaire' : 'racine unitaire'}</span>`)
    + kpi('ADF rendements', `${a2.stat.toFixed(2)} <span class="small ${a2.stationnaire_5pct ? 'pos' : 'neg'}">${a2.stationnaire_5pct ? 'stationnaire' : 'racine unitaire'}</span>`)
    + kpi('Ordre AR retenu (BIC / AIC / CV)', `${d.choix.bic} / ${d.choix.aic} / ${d.cv_meilleur_p}`)
    + kpi('Ljung-Box résidus', `p = ${lb.residus.p.toFixed(3)} <span class="small ${lb.residus.p > 0.05 ? 'pos' : 'neg'}">${lb.residus.p > 0.05 ? 'bruit blanc' : 'autocorrélé'}</span>`)
    + kpi('Ljung-Box résidus²', `p = ${lb.residus_carres.p.toExponential(1)} <span class="small ${lb.residus_carres.p > 0.05 ? 'pos' : 'neg'}">${lb.residus_carres.p > 0.05 ? 'pas d’effet ARCH' : 'vol en grappes'}</span>`)
    + kpi('Asymétrie / kurtosis', `${d.asymetrie.toFixed(2)} / ${d.kurtosis.toFixed(1)}`) + '</div>';
  const lags = d.acf.map((_, i) => i);
  h += '<div class="grid g-main">';
  h += pan('ACF des rendements', 'bande : ±1,96/√n', barsSvg(d.acf.slice(1), { band: d.bande, labels: lags.slice(1) }));
  h += pan('PACF des rendements', 'identifie l’ordre AR', barsSvg(d.pacf.slice(1), { band: d.bande, labels: lags.slice(1) }));
  h += '</div><div class="grid g-main" style="margin-top:10px">';
  h += pan('ACF des rendements au carré', 'mémoire de la volatilité → GARCH, SV', barsSvg(d.acf_carres.slice(1), { band: d.bande, labels: lags.slice(1) }));
  h += pan('Validation croisée temporelle', 'erreur hors échantillon à 1 jour, par ordre p', lineChart('chTSAcv', [{ name: 'RMSE', x: d.validation_croisee.map((_, i) => 'AR(' + i + ')'), y: d.validation_croisee.map(v => v * 100), color: '#E3B65C', width: 2 }], { height: 180, yfmt: v => v.toFixed(4) + ' %' }));
  h += '</div>' + noteBas(`Démarche Box-Jenkins : (1) stationnarité — le prix a une racine unitaire, le rendement non ; (2) identification par ACF/PACF et critères AIC/BIC ; (3) estimation ; (4) diagnostic des résidus. Le résultat typique d'un marché liquide : rendements presque imprévisibles (AR d'ordre 0 ou 1), mais carrés très autocorrélés — la volatilité, elle, se prévoit. C'est exactement ce qu'exploite le fonds : il ne prédit pas les rendements, il dimensionne les positions par la volatilité.`);
  return h;
}

/* ---------------- MODL : catalogue ---------------- */
function fnMODL(d) {
  if (d.error) return `<div class="loader neg">${esc(d.error)}</div>`;
  const coul = { production: 'pos', analyse: 'amber', rejeté: 'neg', désactivé: 'muted' };
  let h = fnHeader('MODL <span class="muted">Catalogue des modèles du fonds</span>', esc(d.livre), '');
  for (const s of d.sections) {
    h += `<div class="panel" style="margin-bottom:10px"><div class="panel-h">${esc(s.titre)}</div><div class="panel-b" style="padding:4px;overflow-x:auto"><table><tr><th>Modèle</th><th>Livre</th><th>Statut</th><th>Code</th><th>Commande</th></tr>`;
    for (const m of s.modeles) h += `<tr><td>${esc(m.nom)}</td><td class="muted small">${esc(m.livre)}</td><td class="${coul[m.statut] || ''}">${esc(m.statut)}</td><td class="muted small">${esc(m.fichier)}</td><td><a class="lnk" onclick="runCommand('${esc(m.commande)}')">${esc(m.commande)} ›</a></td></tr>`;
    h += '</table></div></div>';
  }
  return h + noteBas(`Production : ce qui pilote réellement le portefeuille. Rejeté : évalué sur le banc pré-enregistré (sélection sur 2008-2019, validation 2020-2026, échantillon neuf 2001-2007) sans battre la référence. Analyse : outils du terminal qui éclairent les décisions sans passer d'ordres. Un modèle n'entre en production qu'après une campagne pré-enregistrée réussie et l'accord du gérant.`);
}

/* ---------------- GC3D : panneau ACP ---------------- */
function gc3dACP(d) {
  const a = d.acp; if (!a) return '';
  const noms = ['Niveau', 'Pente', 'Courbure'], cols = ['#E3B65C', '#8AB4FF', '#6CCB8F'];
  let h = '<div class="kpis" style="margin-top:10px">' + noms.map((n, k) => kpi(`${n} · part de variance`, `${(a.part[k] * 100).toFixed(1)} % <span class="muted small">${a.vol_pb_jour[k].toFixed(1)} pb/j</span>`)).join('')
    + kpi('3 facteurs ensemble', (a.part.slice(0, 3).reduce((x, y) => x + y, 0) * 100).toFixed(1) + ' %') + '</div>';
  h += '<div class="grid g-main">';
  h += pan('Facteurs de la courbe (ACP)', 'poids de chaque maturité', lineChart('chACP', noms.map((n, k) => ({ name: n, x: a.maturites, y: a.vecteurs[k], color: cols[k], width: 2 })), { height: 220, zero: 0, yfmt: v => v.toFixed(2) }));
  h += pan('Évolution cumulée des facteurs', 'points de base', lineChart('chACPs', noms.map((n, k) => ({ name: n, x: d.dates, y: a.scores[k], color: cols[k], width: 1.6 })), { height: 220, zero: 0, yfmt: v => v.toFixed(0) }));
  return h + '</div>' + noteBas(`ACP des variations quotidiennes des taux de 3 mois à 30 ans (le 1 mois, bruité par les effets propres aux T-bills, est exclu). Trois facteurs expliquent l'essentiel des mouvements de la courbe : un déplacement parallèle (niveau), une rotation (pente) et un creusement du ventre (courbure) — ${LIVRE}, ch. 6 § 5.`);
}
