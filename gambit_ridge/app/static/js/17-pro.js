/* Gambit Ridge Capital — terminal : 17-pro.js (scripts classiques, globals partagés, chargés après 15-navigation.js)
   Outils de travail « pro », d'après le guide pratique Bloomberg de Tom :
   - fonctions du mémo en données gratuites réelles : HP, DVD, RG, OMON, CN, FLDS ;
   - DOCS : l'araignée des docs dans le terminal (concepts ↔ pages des livres ↔ code de GRC, recherche plein texte) ;
   - SEARCH : recherche complète par catégories (touche SEARCH = Alt+S ou Maj+Entrée) ;
   - BLP : espace de travail en panneaux indépendants (PANEL = Alt+P passe d'un panneau à l'autre) ;
   - MEMO : le mémo des fonctions du guide, avec ce qui existe ici, l'équivalent ou « payant » ;
   - BU : parcours de formation vérifié automatiquement, routine du matin, questions d'entretien ;
   - GRAB (Alt+G) : copie de l'écran avec son contexte ; EXPORT (Alt+E) : tableaux de l'écran en CSV. */

async function proFetch(name, sym, params) {
  const qs = new URLSearchParams({ ...(sym ? { s: sym } : {}), ...(params || {}) }).toString();
  const key = 'pro:' + name + '?' + qs;
  if (FN_CACHE[key] && Date.now() - FN_CACHE[key].t < 10 * 60 * 1000) return FN_CACHE[key].d;
  const d = await (await fetch('/api/pro/' + name.toLowerCase() + '?' + qs)).json();
  if (!d.error) FN_CACHE[key] = { t: Date.now(), d };
  return d;
}
const proErr = d => `<div class="loader neg">${esc(d.error)}</div>`;
const proPct = (v, d = 1) => v === null || v === undefined || !isFinite(v) ? '—' : sgn(v * 100, d) + ' %';
const proNum = (v, d = 2) => v === null || v === undefined || !isFinite(v) ? '—' : Number(v).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
const proVol = v => !v ? '—' : v >= 1e6 ? (v / 1e6).toFixed(1) + ' M' : v >= 1e3 ? (v / 1e3).toFixed(0) + ' k' : String(v);
const proQ = s => esc(s).replace(/'/g, "\\'");
function proMenu(cmds) { GRC_MENU = cmds; document.body.classList.toggle('grc-menu-actif', cmds.length > 0); }
// contrôle à faire avant d'utiliser le résultat (« Le contrôle DES », guide p. 6, 10, 15, 20)
function proControle(t) { return `<div class="pro-ctrl"><b>À vérifier</b> ${t}</div>`; }

/* ============ HP : PRIX HISTORIQUES EN TABLEAU ============ */
async function fnHP(sym) {
  const per = FN_STATE.hpPer || 'D';
  const d = await proFetch('HP', sym, { per });
  if (d.error) return proErr(d);
  const l0 = d.lignes[0];
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">${esc(d.nom)}</span>`, `HP · prix historiques · ${esc(d.devise || '')}`,
    `<span class="fn-last">${fmtPx(l0.cloture)}</span> <span class="${(l0.variation || 0) >= 0 ? 'pos' : 'neg'}">${proPct(l0.variation, 2)}</span>`);
  h += '<div class="fn-tools">' + [['D', 'Jour'], ['W', 'Semaine'], ['M', 'Mois']].map(([k, l]) => `<span class="rng ${per === k ? 'on' : ''}" onclick="FN_STATE.hpPer='${k}';renderFn()">${l}</span>`).join('')
    + `<span class="muted small" style="margin-left:auto">${d.lignes.length} lignes · <a class="lnk" onclick="runCommand('${proQ(d.symbol)} GP')">graphique GP ›</a> · <a class="lnk" onclick="proExporter()">export CSV (Alt+E)</a></span></div>`;
  let t = '<table class="pro-t"><tr><th>Date</th><th class="num">Ouverture</th><th class="num">Haut</th><th class="num">Bas</th><th class="num">Clôture</th><th class="num">Var.</th><th class="num">Volume</th></tr>';
  for (const l of d.lignes) t += `<tr><td>${esc(l.date)}</td><td class="num">${fmtPx(l.ouverture)}</td><td class="num">${fmtPx(l.haut)}</td><td class="num">${fmtPx(l.bas)}</td><td class="num amber">${fmtPx(l.cloture)}</td><td class="num ${(l.variation || 0) >= 0 ? 'pos' : 'neg'}">${proPct(l.variation, 2)}</td><td class="num">${proVol(l.volume)}</td></tr>`;
  h += pan('Prix historiques', esc(d.source), `<div class="pro-scroll">${t}</table></div>`);
  return h + proControle('la périodicité, la devise et l’unité ; une variation de cours n’est pas un rendement total (dividendes : RG &lt;GO&gt;).');
}

/* ============ DVD : DIVIDENDES ============ */
async function fnDVD(sym) {
  const d = await proFetch('DVD', sym);
  if (d.error) return proErr(d);
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">${esc(d.nom)}</span>`, 'DVD · historique des dividendes', `<span class="fn-last">${fmtPx(d.prix)}</span> ${esc(d.devise || '')}`);
  if (!d.lignes.length) return h + '<div class="loader">Aucun dividende versé sur l’historique disponible.</div>';
  h += '<div class="kpis">' + kpi('Dividendes 12 mois', proNum(d.dividende_12m, 2)) + kpi('Rendement 12 mois', pc(d.rendement_12m, 2), 'amber')
    + kpi('Fréquence', esc(d.frequence || '—')) + kpi('Croissance annuelle 5 ans', proPct(d.croissance_5a, 1), (d.croissance_5a || 0) >= 0 ? 'pos' : 'neg')
    + kpi('Dernier détachement', esc(d.lignes[0].ex_date)) + '</div>';
  const an = d.par_annee.slice(-20);
  h += '<div class="grid g-main">' + pan('Dividendes versés par année civile', 'année en cours incomplète',
    lineChart('chDVD', [{ name: 'Total annuel', x: an.map(a => a.annee), y: an.map(a => a.total), color: '#ff9900', width: 2 }], { height: 220, yfmt: v => v.toFixed(2) }));
  let t = '<table class="pro-t"><tr><th>Date ex</th><th class="num">Montant</th><th class="num">Var.</th></tr>';
  for (const l of d.lignes.slice(0, 60)) t += `<tr><td>${esc(l.ex_date)}</td><td class="num amber">${proNum(l.montant, 4)}</td><td class="num ${(l.variation || 0) >= 0 ? 'pos' : 'neg'}">${l.variation === null ? '—' : proPct(l.variation, 1)}</td></tr>`;
  h += pan('Détachements', 'les plus récents d’abord', `<div class="pro-scroll" style="max-height:260px">${t}</table></div>`) + '</div>';
  return h + noteBas(esc(d.source) + '. Formule Excel : =BDS("' + esc(d.symbol) + ' US Equity";"DVD_HIST_ALL").');
}

/* ============ RG : RENDEMENT TOTAL ============ */
async function fnRG(sym) {
  const S = FN_STATE;
  S.rgListe = S.rgListe || '';
  const liste = S.rgListe || [sym || 'SPY', 'SPY'].filter((x, i, a) => a.indexOf(x) === i).join(',');
  const per = S.rgPer || '1A';
  const d = await proFetch('RG', sym, { l: liste, p: per });
  if (d.error) return proErr(d);
  let h = fnHeader('RG <span class="muted">Rendement total comparé</span>', esc(d.note), '');
  h += '<div class="fn-tools">' + ['1M', '3M', '6M', 'YTD', '1A', '3A', '5A', '10A'].map(r => `<span class="rng ${per === r ? 'on' : ''}" onclick="FN_STATE.rgPer='${r}';renderFn()">${r}</span>`).join('')
    + `<span style="margin-left:auto">${qf('Titres (6 max)', `<input type="text" value="${esc(liste)}" style="width:220px" onkeydown="if(event.key==='Enter'){FN_STATE.rgListe=this.value.toUpperCase();renderFn()}">`)}</span></div>`;
  const couleurs = ['#ff9900', '#2979ff', '#e040fb', '#00e676', '#ffeb3b', '#ff5252'];
  h += pan('Rendement total, dividendes réinvestis', esc(per), lineChart('chRG', d.series.map((s, i) => ({ name: s.symbol, x: s.dates, y: s.total.map(v => v * 100), color: couleurs[i % 6], width: i ? 1.2 : 2 })), { height: 300, zero: 0, yfmt: v => v.toFixed(0) + ' %' }));
  let t = '<table class="pro-t"><tr><th>Titre</th><th>Nom</th><th class="num">Variation du cours</th><th class="num">Rendement total</th><th class="num">Apport des dividendes</th><th class="num">Annualisé</th><th>Période</th></tr>';
  for (const r of d.tableau) t += `<tr><td class="amber"><a class="lnk" onclick="runCommand('${proQ(r.symbol)} DES')">${esc(r.symbol)}</a></td><td class="muted">${esc(r.nom)}</td><td class="num ${r.variation_cours >= 0 ? 'pos' : 'neg'}">${proPct(r.variation_cours)}</td><td class="num ${r.rendement_total >= 0 ? 'pos' : 'neg'}"><b>${proPct(r.rendement_total)}</b></td><td class="num">${proPct(r.apport_dividendes)}</td><td class="num">${r.annualise === null ? '—' : proPct(r.annualise)}</td><td class="muted small">${esc(r.debut)} → ${esc(r.fin)}</td></tr>`;
  h += '<div style="height:6px"></div>' + pan('Tableau', 'clic sur un titre = fiche DES', t + '</table>');
  return h + proControle('mêmes dates et même devise pour tous les titres : la variation du cours et le rendement total ne mesurent pas la même chose.');
}

/* ============ OMON : CHAÎNE D'OPTIONS ============ */
async function fnOMON(sym) {
  const S = FN_STATE;
  const d = await proFetch('OMON', sym, S.omonE && S.omonSym === sym ? { e: S.omonE } : {});
  if (d.error) return proErr(d);
  S.omonSym = sym;
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">chaîne d’options</span>`, `OMON · échéance ${esc(d.echeance)} (${d.jours} j) · relevé ${esc((d.releve || '').replace('T', ' ').slice(0, 16))} UTC`,
    `<span class="fn-last">${fmtPx(d.spot)}</span>`);
  h += '<div class="fn-tools pro-ech">' + d.echeances.slice(0, 24).map(e => `<span class="rng ${e === d.echeance ? 'on' : ''}" onclick="FN_STATE.omonE='${e}';renderFn()">${e.slice(2)}</span>`).join('') + '</div>';
  h += '<div class="kpis">' + kpi('Taux sans risque (T-bill 13 s.)', pc(d.taux, 2)) + kpi('Dividende continu', pc(d.dividende, 2))
    + kpi('Put / call (volume)', d.put_call_volume === null ? '—' : d.put_call_volume.toFixed(2)) + kpi('Put / call (positions ouvertes)', d.put_call_oi === null ? '—' : d.put_call_oi.toFixed(2))
    + kpi('Strike à la monnaie', fmtPx(d.atm), 'amber') + '</div>';
  if (d.hors_seance) h += '<div class="pro-ctrl neg">Hors séance : Yahoo met les fourchettes à zéro, les prix affichés sont les derniers échangés (ils peuvent dater) et la vol implicite en découle.</div>';
  const c = (o, k, f) => o && o[k] !== null && o[k] !== undefined ? f(o[k]) : '—';
  let t = '<table class="pro-t omon"><tr><th colspan="5" class="omon-c">CALLS</th><th class="omon-k">Strike</th><th colspan="5" class="omon-p">PUTS</th></tr>'
    + '<tr><th class="num">Bid</th><th class="num">Ask</th><th class="num">Vol. impl.</th><th class="num">Volume</th><th class="num">Pos. ouv.</th><th class="num">K</th><th class="num">Bid</th><th class="num">Ask</th><th class="num">Vol. impl.</th><th class="num">Volume</th><th class="num">Pos. ouv.</th></tr>';
  for (const l of d.lignes) {
    const itmC = l.strike < d.spot, itmP = l.strike > d.spot, ca = l.call, pu = l.put;
    t += `<tr class="${l.strike === d.atm ? 'omon-atm' : ''}"><td class="num ${itmC ? 'itm' : ''}">${c(ca, 'bid', fmtPx)}</td><td class="num ${itmC ? 'itm' : ''}">${c(ca, 'ask', fmtPx)}</td><td class="num ${itmC ? 'itm' : ''} amber">${c(ca, 'iv', v => (v * 100).toFixed(1))}</td><td class="num ${itmC ? 'itm' : ''}">${c(ca, 'volume', proVol)}</td><td class="num ${itmC ? 'itm' : ''}">${c(ca, 'oi', proVol)}</td>`
      + `<td class="num omon-k"><b>${fmtPx(l.strike)}</b></td>`
      + `<td class="num ${itmP ? 'itm' : ''}">${c(pu, 'bid', fmtPx)}</td><td class="num ${itmP ? 'itm' : ''}">${c(pu, 'ask', fmtPx)}</td><td class="num ${itmP ? 'itm' : ''} amber">${c(pu, 'iv', v => (v * 100).toFixed(1))}</td><td class="num ${itmP ? 'itm' : ''}">${c(pu, 'volume', proVol)}</td><td class="num ${itmP ? 'itm' : ''}">${c(pu, 'oi', proVol)}</td></tr>`;
  }
  h += pan('Calls / puts', 'fond grisé = dans la monnaie · ligne ambre = à la monnaie', `<div class="pro-scroll">${t}</table></div>`);
  setTimeout(() => { const r = document.querySelector('.omon tr.omon-atm'), b = r && r.closest('.pro-scroll'); if (b) b.scrollTop = r.offsetTop - b.clientHeight / 2; }, 0);  // centré sur la monnaie
  h += `<div class="muted small" style="margin:6px 2px">Aller plus loin : <a class="lnk" onclick="runCommand('${proQ(d.symbol)} OVDV')">surface de vol OVDV</a> · <a class="lnk" onclick="runCommand('${proQ(d.symbol)} OVML')">pricer OVML</a> · <a class="lnk" onclick="runCommand('HEDGE')">couverture du fonds HEDGE</a></div>`;
  return h + proControle('sous-jacent, maturité, strike et type ; une cotation n’est pas un prix exécutable. ' + esc(d.source) + '.');
}

/* ============ CN : ACTUALITÉS D'UNE SOCIÉTÉ ============ */
async function fnCN(sym) {
  const d = await proFetch('CN', sym);
  if (d.error) return proErr(d);
  let h = fnHeader(`${esc(d.symbol)} <span class="muted">${esc(d.nom)}</span>`, `CN · actualités de la société · requête « ${esc(d.requete)} »`, '');
  if (!d.items.length) return h + '<div class="loader">Aucune dépêche trouvée (hors ligne ?).</div>';
  let t = '';
  for (const it of d.items) {
    const dt = it.date ? it.date.replace(/^\w+, */, '').split(' +')[0].replace(/ GMT$/, '') : '';
    t += `<div class="news-item"><span class="src">${esc(it.source || '')}</span><a href="${esc(it.link)}" target="_blank" rel="noopener">${esc(it.title)}</a><span class="dt">${esc(dt)}</span></div>`;
  }
  h += pan('Dépêches', d.items.length + ' titres · Google News · cache 30 min', `<div style="padding:0">${t}</div>`);
  return h + proControle('la chronologie : une dépêche peut expliquer un mouvement, une simultanéité ne prouve pas la cause (guide p. 14). Grands titres : TOP &lt;GO&gt;.');
}

/* ============ FLDS : DICTIONNAIRE DES CHAMPS ============ */
async function fnFLDS() {
  const q = FN_STATE.fldsQ || '';
  const d = await proFetch('FLDS', '', q ? { q } : {});
  if (d.error) return proErr(d);
  let h = fnHeader('FLDS <span class="muted">Recherche de champs</span>', 'BDP · BDH · BDS · BQL — définition, unité, disponibilité', '');
  h += `<div class="aide-recherche"><input type="text" id="fldsQ" placeholder="Chercher un champ : PX, VOLATILITY, dividende, marge…" value="${esc(q)}" onkeydown="if(event.key==='Enter'){FN_STATE.fldsQ=this.value;renderFn()}"></div>`;
  let t = '<table class="pro-t"><tr><th>Champ</th><th>Type</th><th>Définition</th><th>Unité</th><th>Disponible</th></tr>';
  for (const c of d.champs) t += `<tr><td class="${c.dispo ? 'amber' : 'muted'}"><b>${esc(c.champ)}</b></td><td class="muted small">${esc(c.type)}</td><td>${esc(c.definition)}</td><td class="muted">${esc(c.unite)}</td><td class="${c.dispo ? 'pos' : 'neg'}">${c.dispo ? 'oui' : 'payant'}</td></tr>`;
  h += pan(d.n + ' champs', 'Entrée = filtrer', `<div class="pro-scroll">${t}</table></div>`);
  setTimeout(() => { const i = document.getElementById('fldsQ'); if (i && q) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }, 0);
  return h + noteBas('Exemples : ' + esc(d.aide) + ' · En Excel français, le séparateur est le point-virgule. Un champ « payant » renvoie #N/A Field Not Available au lieu d’un chiffre inventé. Requêtes : BQL &lt;GO&gt;.');
}

/* ============ DOCS : L'ARAIGNÉE DES DOCS ============ */
async function fnDOCS() {
  const S = FN_STATE, st = S.docs = S.docs || {};
  const params = {};
  if (st.q) params.q = st.q;
  if (st.lire) { params.doc = st.lire.doc; params.page = st.lire.page; }
  const d = await proFetch('DOCS', '', params);
  if (d.error) return proErr(d);
  let h = fnHeader('DOCS <span class="muted">L’araignée des docs</span>', d.disponible ? `toile du ${esc(d.maj)} · ${d.n_pages || '—'} pages de ${d.documents ? d.documents.length : '—'} documents` : '', '<span class="muted small">⌥⌘A sur le Mac : l’araignée sur n’importe quel document</span>');
  if (!d.disponible) return h + `<div class="loader">${esc(d.message)}</div>`;
  h += `<div class="aide-recherche"><input type="text" id="docsQ" placeholder="Chercher dans la bibliothèque : « minimum variance hedge ratio », « Black-Litterman », « Kelly »…" value="${esc(st.q || '')}" onkeydown="if(event.key==='Enter'){FN_STATE.docs.q=this.value;FN_STATE.docs.lire=null;renderFn()}"></div>`;
  const cmds = [];
  if (st.lire && d.lecture) {
    const L = d.lecture;
    const nav = (p, t) => p >= 1 && p <= L.pages ? `<a class="lnk" onclick="FN_STATE.docs.lire={doc:'${proQ(L.doc)}',page:${p}};renderFn()">${t}</a>` : `<span class="muted">${t}</span>`;
    const surl = st.q ? proSurligner(esc(L.texte), st.q) : esc(L.texte);
    h += pan(`${esc(L.doc)} · page ${L.page} / ${L.pages}`, `${nav(L.page - 1, '◂ page préc.')} · ${nav(L.page + 1, 'page suiv. ▸')} · <a class="lnk" onclick="FN_STATE.docs.lire=null;renderFn()">fermer</a>`,
      `<div class="docs-page">${surl}</div>`);
    h += '<div style="height:6px"></div>';
  }
  if (st.q) {
    if (!d.plein_texte) h += '<div class="loader">Recherche plein texte indisponible sur cette machine : les textes des livres restent sur le Mac (data_cache/araignee/textes).</div>';
    else {
      let t = '';
      PRO_DOCS_RES = d.resultats || [];
      for (const r of d.resultats || []) {
        cmds.push(`DOCSPAGE ${cmds.length + 1}`);
        t += `<div class="menu-l" onclick="FN_STATE.docs.lire={doc:'${proQ(r.doc)}',page:${r.page}};renderFn()"><span class="menu-n">${cmds.length})</span><span class="menu-c">p. ${r.page}</span><span class="menu-t">${esc(r.doc.replace(/\.pdf$/i, ''))}</span><span class="menu-d">« …${proSurligner(esc(r.extrait), st.q)}… »</span></div>`;
      }
      h += pan(`Résultats pour « ${esc(st.q)} »`, 'chiffre + &lt;GO&gt; ou clic = lire la page', `<div class="menu-b">${t || '<div class="muted">Rien trouvé : essayez en anglais (les livres sont souvent en anglais).</div>'}</div>`);
      h += '<div style="height:6px"></div>';
    }
  }
  // la toile : concepts, pages où les lire, code de GRC qui les implémente
  let t = '<table class="pro-t"><tr><th>Concept</th><th>Famille</th><th class="num">Mentions</th><th>Où lire</th><th>Dans GRC</th><th class="num">Trou</th></tr>';
  for (const c of d.concepts) {
    const ou = (c.pages || []).slice(0, 3).map(p => `<a class="lnk" onclick="FN_STATE.docs.lire={doc:'${proQ(p.doc)}',page:${p.page}};FN_STATE.docs.q=FN_STATE.docs.q||'';renderFn()">${esc(p.doc.replace(/\.pdf$/i, '').slice(0, 22))} p.${p.page}</a>`).join(' · ');
    const code = (c.commandes || []).map(x => `<a class="lnk amber" onclick="runCommand('${proQ(x)}')">${esc(x)}</a>`).join(' ') || (c.nb_fichiers_code ? `<span class="muted">${c.nb_fichiers_code} fichier(s)</span>` : '<span class="neg">absent</span>');
    t += `<tr><td>${esc(c.titre)}</td><td class="muted">${esc(c.famille)}</td><td class="num">${c.mentions}</td><td class="small">${ou || '—'}</td><td class="small">${code}</td><td class="num ${c.score_trou > 1 ? 'neg' : 'muted'}">${c.score_trou ? c.score_trou.toFixed(1) : '—'}</td></tr>`;
  }
  h += pan('La toile : concepts ↔ pages des livres ↔ code du fonds', 'trou = beaucoup de matière dans les livres, peu de code dans GRC', `<div class="pro-scroll">${t}</table></div>`);
  if (d.documents) h += '<div style="height:6px"></div>' + pan('Bibliothèque lue', d.documents.length + ' documents', '<div class="docs-biblio">' + d.documents.map(x => `<span>${esc(x.doc.replace(/\.pdf$/i, ''))} <i>${x.pages} p.</i></span>`).join('') + '</div>');
  proMenu(cmds);
  setTimeout(() => { const i = document.getElementById('docsQ'); if (i && !st.lire) i.focus(); }, 0);
  return h + noteBas('Les livres sont protégés par le droit d’auteur : leurs textes restent dans data_cache/ (jamais publiés). Retisser la toile : .venv/bin/python scripts/araignee/araignee.py explorer.');
}
function proSurligner(html, q) {
  const mots = String(q).split(/\s+/).filter(m => m.length > 2).map(m => m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return mots.length ? html.replace(new RegExp('(' + mots.join('|') + ')', 'gi'), '<mark>$1</mark>') : html;
}

/* ============ MEMO : LE MÉMO DU GUIDE (p. 24) ET CE QUI EXISTE ICI ============ */
// [code Bloomberg, libellé du guide, ce qu'on a : code GRC | null, note]
const GRC_MEMO = [
  ['Sociétés et actions', [
    ['DES', 'Identité et description', 'DES'], ['FA', 'États financiers et ratios', 'FA', 'comptes SEC, sociétés US'], ['PGEO', 'Ventilation de l’activité', null, 'segments XBRL non normalisés'],
    ['GP', 'Graphique historique', 'GP'], ['GIP', 'Graphique intrajournalier', null, 'données intrajournalières payantes ; GP en séances closes'],
    ['HP', 'Prix historiques en tableau', 'HP'], ['CN', 'Actualités de la société', 'CN'], ['ERN', 'Synthèse des résultats', 'FA', 'résultats publiés (sans consensus)'],
    ['ANR', 'Recommandations d’analystes', null, 'consensus payant'], ['RV', 'Comparables', 'RG', 'RG pour la performance, EQS ou BQL pour les ratios'], ['EQS', 'Filtrage actions', 'EQS'],
    ['DVD', 'Dividendes', 'DVD'], ['RG', 'Rendement total', 'RG']]],
  ['Obligations et devises', [
    ['SRCH', 'Recherche d’obligations', null, 'données obligataires payantes ; menus GOVT / CORP avec ETF témoins'], ['YAS', 'Prix, rendements et sensibilités', 'GC', 'courbe du Trésor ; pas de pricer obligataire'],
    ['ALLQ', 'Sources de cotation', null, 'payant'], ['CRPR', 'Notations de crédit', null, 'payant'], ['DDIS', 'Échéances de dette', null, 'payant'], ['WB', 'Souverains', 'GEW', 'taux 10 ans OCDE, dette FMI'],
    ['FXC', 'Taux de change', 'FXC'], ['FXCA', 'Conversion de devises', 'FXC'], ['FXFC', 'Prévisions de change', null, 'consensus payant'], ['WCRS', 'Classement des devises', 'WCRS']]],
  ['Marchés et économie', [
    ['TOP', 'Actualités', 'NH'], ['GMM', 'Mouvements globaux', 'WEI'], ['WEI', 'Indices', 'WEI'], ['IMAP', 'Carte des mouvements', 'WEI', 'par région, sans carte intrajournalière'],
    ['ECO', 'Calendrier économique', 'ECST', 'séries publiées ; heures et consensus payants'], ['ECST', 'Séries économiques', 'ECST'], ['ECFC', 'Prévisions économiques', 'GEW', 'prévisions du FMI (pas le consensus)'],
    ['FED', 'Fed', 'GC', 'courbe, Fed funds dans ECST'], ['CENB', 'Banques centrales', 'GEW', 'taux directeurs BRI']]],
  ['Outils spécialisés', [
    ['GLCO', 'Matières premières', '<CMDTY>', 'menu de marché CMDTY (F9)'], ['BOIL', 'Pétrole', 'CL1 <CMDTY> GP'], ['NGAS', 'Gaz naturel', 'NG1 <CMDTY> GP'],
    ['OMON', 'Chaîne d’options', 'OMON'], ['OVME', 'Dérivés actions', 'OVML'], ['OVML', 'Options (pricer)', 'OVML'], ['OVDV', 'Surface de volatilité', 'OVDV'],
    ['MA', 'Fusions-acquisitions', null, 'payant'], ['MRGC', 'Scénarios de fusion', null, 'payant'], ['PE', 'Private equity', null, 'payant'], ['BI', 'Analyse sectorielle', null, 'payant']]],
  ['Excel, aide et réglages', [
    ['FLDS', 'Définition des champs', 'FLDS'], ['API', 'Ressources Excel / API', 'BQL', 'BDP / BDH / BDS / BQL dans Excel'], ['XLTP', 'Modèles Excel', 'BQL'],
    ['BMC', 'Parcours de formation', 'BU'], ['BU', 'Formations', 'BU'], ['HELP', 'Aide', 'HELP'], ['DOCS', 'Documentation', 'DOCS', 'l’araignée sur la bibliothèque de Tom'], ['PDF', 'Préférences', 'HELP HELP']]],
  ['Portefeuille et organisation', [
    ['PRTU', 'Positions', 'PORT'], ['PORT', 'Analyse de portefeuille', 'RISK', 'risque, attribution, HEDGE'], ['BLP', 'Espace Launchpad', 'BLP'], ['IB', 'Chat', 'AGENTS', 'questions aux agents'], ['MSG', 'Messages', 'VOIX'], ['GRAB', 'Capture d’écran', 'GRAB']]],
];
function grcMemoCible(code) { for (const [, l] of GRC_MEMO) for (const x of l) if (x[0] === code) return x; return null; }
function proLancerMemo(x, sym) {
  const cible = x[2];
  if (!cible) return null;
  const f = grcFonction(cible.split(' ')[0]);
  return f && f.ticker && !/\s/.test(cible) ? (sym || FN_STATE.sym || 'SPY') + ' ' + cible : cible;
}
function fnMEMO() {
  let h = fnHeader('MEMO <span class="muted">Le mémo des fonctions essentielles</span>', 'guide Bloomberg, p. 24 · ce qui existe ici en données gratuites', '<span class="muted small">chiffre + &lt;GO&gt; = ouvrir</span>');
  const cmds = [];
  h += '<div class="memo">';
  for (const [sec, l] of GRC_MEMO) {
    let b = '';
    for (const x of l) {
      const cmd = proLancerMemo(x);
      const etat = !x[2] ? '<span class="neg">payant</span>' : x[2] === x[0] ? '<span class="pos">✓</span>' : `<span class="amber">≈ ${esc(x[2])}</span>`;
      if (cmd) cmds.push(cmd);
      b += `<div class="menu-l${cmd ? '' : ' off'}" ${cmd ? `onclick="runCommand('${proQ(cmd)}')"` : ''}><span class="menu-n">${cmd ? cmds.length + ')' : ''}</span><span class="menu-c">${esc(x[0])}</span><span class="menu-t">${esc(x[1])}</span><span class="menu-d">${etat}${x[3] ? ' <span class="muted">' + esc(x[3]) + '</span>' : ''}</span></div>`;
    }
    h += pan(esc(sec), '', `<div class="menu-b">${b}</div>`);
  }
  h += '</div>';
  proMenu(cmds);
  return h + noteBas('Un code Bloomberg tapé ici ouvre son équivalent (TOP → NH, GMM → WEI, PRTU → PORT…) ou explique pourquoi il manque. ✓ = même fonction · ≈ = équivalent · payant = données non gratuites, jamais inventées.');
}
// codes du mémo absents du terminal : redirigés vers l'équivalent, ou écran « indisponible » qui le dit
// (appelé après l'enregistrement des fonctions de ce fichier ; MA reste le ticker de Mastercard)
function proRegistrerMemo() {
for (const [, l] of GRC_MEMO) for (const x of l) {
  const [code, libelle, cible, note] = x;
  if (grcFonction(code) || cible === code || code === 'MA') continue;
  const titre = libelle + (cible ? ' (→ ' + cible + ')' : '');
  if (cible) {
    grcEnregistrerFonction({ code, titre, categorie: 'Bloomberg', description: `Code Bloomberg ${code} : ${libelle}. Ici : ${cible}${note ? ' — ' + note : ''}.`, exemple: code, barre: false,
      lancer: sym => { grcMessage(`${code} → ${cible}${note ? ' · ' + note : ''}`); runCommand(proLancerMemo(x, sym)); } }, { sansEcraser: true });
  } else {
    grcEnregistrerFonction({ code, titre: libelle + ' (payant)', categorie: 'Bloomberg', description: `Code Bloomberg ${code} : ${libelle}. Non disponible : ${note || 'données payantes'}.`, exemple: code, barre: false, indispo: true,
      rendu: () => fnHeader(esc(code), esc(libelle)) + `<div class="panel"><div class="panel-b"><div class="aide-d"><b class="neg">Non disponible ici</b> : ${esc(note || 'données payantes')}. Le terminal n’affiche que des données gratuites réelles, jamais de chiffre inventé.</div><div class="aide-k" style="margin-top:6px"><a class="lnk" onclick="runCommand('MEMO')">MEMO : ce qui existe ›</a> · <a class="lnk" onclick="runCommand('HELP')">toutes les fonctions ›</a></div></div></div>` }, { sansEcraser: true });
  }
}
}

/* ============ BU : FORMATION — PARCOURS VÉRIFIÉ, ROUTINE DU MATIN, ENTRETIEN ============ */
// journal des écrans ouverts (code + titre), pour cocher les étapes tout seul
let GRC_JOURNAL = grcLire('grc_journal', []);
if (!Array.isArray(GRC_JOURNAL)) GRC_JOURNAL = [];
function proJournaliser() {
  const e = grcEtatCourant(), code = e.tab === 'fn' ? e.fn : (ECRANS[e.tab] || [''])[0];
  GRC_JOURNAL.push({ c: code, s: e.tab === 'fn' && grcAvecTitre(code) ? e.sym : '', t: Date.now() });
  if (GRC_JOURNAL.length > 300) GRC_JOURNAL = GRC_JOURNAL.slice(-300);
  grcStocker('grc_journal', GRC_JOURNAL);
}
const proSwitchOrig = switchTab;
switchTab = function (tab) { proSwitchOrig(tab); proJournaliser(); if (typeof proPanneauSignaler === 'function') proPanneauSignaler(); };
const BU_PARCOURS = [
  { id: 'action', titre: 'Exercice du guide : une action de bout en bout', aide: 'Choisir une action, vérifier DES, consulter GP et FA, comparer avec ses pairs, extraire une donnée dans Excel (guide p. 23).',
    etapes: [['Charger une action et vérifier son identité', ['DES'], 'AAPL US <EQUITY> DES'], ['Lire sa trajectoire', ['GP', 'HP'], 'GP'], ['Lire ses comptes', ['FA'], 'FA'],
      ['La comparer à des pairs', ['RG', 'EQS'], 'RG'], ['Trouver le bon champ pour Excel', ['FLDS', 'BQL'], 'FLDS'], ['Lire son actualité', ['CN'], 'CN']] },
  { id: 'matin', titre: 'Routine de veille du matin', aide: 'TOP : les grands titres · WEI / GMM : les mouvements · ECO : les annonces · CN : les sociétés suivies (guide p. 14).',
    etapes: [['Grands titres', ['NH'], 'TOP'], ['Mouvements des indices', ['WEI'], 'WEI'], ['Statistiques économiques', ['ECST', 'GEW'], 'ECST'], ['Taux et inflation anticipée', ['GC', 'ILBE'], 'GC'],
      ['Devises', ['FXC', 'WCRS'], 'FXC'], ['Le fonds : positions et risque', ['PORT', 'RISK', 'HEDGE'], 'PORT'], ['Une société suivie', ['CN'], 'NVDA CN']] },
  { id: 'derives', titre: 'Dérivés : du prix à la couverture', aide: 'Sous-jacent, maturité, strike et type avant tout (guide p. 15).',
    etapes: [['Chaîne d’options', ['OMON'], 'SPY OMON'], ['Surface de volatilité', ['OVDV'], 'SPY OVDV'], ['Pricer une option, ses grecques', ['OVML'], 'SPY OVML'], ['Simuler (Monte-Carlo)', ['MC'], 'SPY MC'], ['Couvrir le fonds', ['HEDGE'], 'HEDGE']] },
  { id: 'clavier', titre: 'Le clavier du Terminal', aide: 'Les réflexes qui font gagner du temps.',
    etapes: [['HELP sur un écran (F1)', ['HELP'], 'HELP'], ['MENU des fonctions liées (Origine)', ['MENU'], 'MENU'], ['Recherche complète (Alt+S)', ['SEARCH'], 'SEARCH'], ['Espace en panneaux (BLP)', ['BLP'], 'BLP'], ['Le mémo du guide', ['MEMO'], 'MEMO']] },
];
const BU_ENTRETIEN = [
  ['Comment chargez-vous un titre ?', 'Identifiant ou ticker, marché si nécessaire, touche jaune et GO ; puis vérification dans DES.', 'AAPL US <EQUITY> DES'],
  ['HP ou GP ?', 'HP pour une table de prix ; GP pour visualiser la trajectoire du cours.', 'SPY HP'],
  ['FA ou RV ?', 'FA pour les comptes de la société ; RV pour la comparaison avec ses pairs.', 'AAPL FA'],
  ['À quoi sert EQS ?', 'À construire un univers d’actions à partir de critères explicites et vérifiables.', 'EQS'],
  ['Comment commencez-vous sur une obligation ?', 'DES pour l’identité et les caractéristiques, puis YAS pour le prix et le rendement.', 'GOVT'],
  ['Pourquoi ouvrir ECO chaque matin ?', 'Pour anticiper les publications, leur heure et les attentes du marché.', 'ECST'],
  ['Pourquoi utiliser FLDS ?', 'Pour choisir le bon champ et comprendre sa définition avant une extraction.', 'FLDS'],
  ['BDP, BDH ou BDS ?', 'Une valeur ponctuelle, une série historique ou un ensemble de données.', 'BQL'],
  ['Que faire si une fonction est inconnue ?', 'La recherche, puis HELP ; deux appuis sur HELP pour l’assistance.', 'HELP HELP'],
  ['Comment décrire son niveau sans exagérer ?', 'Citer les tâches que l’on sait réaliser et les contrôles appliqués, avec un exemple réel.', 'BU'],
  ['Variation du cours ou rendement total ?', 'Le rendement total réinvestit les dividendes ; sur 5 ans l’écart dépasse souvent 10 points.', 'SPY RG'],
  ['Que lire dans une chaîne d’options ?', 'Échéance, strike, call / put, fourchette, vol implicite, positions ouvertes ; le smile et le ratio put / call.', 'SPY OMON'],
  ['Comment couvrir un portefeuille actions ?', 'Bêta (et bêta de baisse), ratio à variance minimale h* = ρ σs/σf, nombre de contrats, ou puts / collar selon le coût.', 'HEDGE'],
];
function buFait(codes, depuis) { return GRC_JOURNAL.some(j => j.t >= depuis && codes.includes(j.c)); }
function fnBU() {
  const S = FN_STATE, st = S.bu = S.bu || { vue: 'parcours', q: 0, voir: false };
  const debuts = grcLire('grc_bu_debut', {});
  let h = fnHeader('BU <span class="muted">Formation</span>', 'parcours vérifiés automatiquement · routine du matin · entretien', '');
  h += '<div class="fn-tools">' + [['parcours', 'Parcours'], ['entretien', 'Entretien (flash-cards)']].map(([k, l]) => `<span class="rng ${st.vue === k ? 'on' : ''}" onclick="FN_STATE.bu.vue='${k}';renderFn()">${l}</span>`).join('') + '</div>';
  const cmds = [];
  if (st.vue === 'entretien') {
    const n = BU_ENTRETIEN.length, k = ((st.q % n) + n) % n, [q, r, ex] = BU_ENTRETIEN[k];
    h += `<div class="panel bu-carte"><div class="panel-h">Question ${k + 1} / ${n}<span class="rt">Espace = révéler · → / ← = suivante / précédente</span></div><div class="panel-b">`
      + `<div class="bu-q">${esc(q)}</div>` + (st.voir ? `<div class="bu-r">${esc(r)}</div><div class="aide-k">Le montrer sur le terminal : <a class="lnk" onclick="runCommand('${proQ(ex)}')">${esc(ex)} &lt;GO&gt;</a></div>` : '<div class="muted" style="margin-top:10px">Répondez à voix haute, puis Espace.</div>')
      + `<div style="margin-top:10px"><button class="btn" onclick="FN_STATE.bu.voir=!FN_STATE.bu.voir;renderFn()">${st.voir ? 'MASQUER' : 'RÉVÉLER'}</button> <button class="btn" onclick="FN_STATE.bu.q--;FN_STATE.bu.voir=false;renderFn()">◂</button> <button class="btn" onclick="FN_STATE.bu.q++;FN_STATE.bu.voir=false;renderFn()">▸</button></div></div></div>`;
    h += noteBas('Mini-cas à refaire (guide p. 25) : une action, son activité, un chiffre financier, un graphique, deux comparables, une actualité — et pour chaque élément, la fonction et ses paramètres.');
    proMenu([]);
    return h;
  }
  h += '<div class="bu-grille">';
  for (const p of BU_PARCOURS) {
    const d0 = debuts[p.id] || 0;
    const faits = p.etapes.filter(e => buFait(e[1], d0)).length;
    let b = `<div class="muted small" style="margin-bottom:4px">${esc(p.aide)}</div>`;
    for (const [lib, codes, cmd] of p.etapes) {
      const ok = buFait(codes, d0);
      cmds.push(cmd);
      b += `<div class="menu-l" onclick="runCommand('${proQ(cmd)}')"><span class="menu-n">${cmds.length})</span><span class="menu-c ${ok ? 'pos' : ''}">${ok ? '✓' : '○'} ${esc(codes[0])}</span><span class="menu-t">${esc(lib)}</span><span class="menu-d muted">${esc(cmd)}</span></div>`;
    }
    h += pan(`${esc(p.titre)}`, `<span class="${faits === p.etapes.length ? 'pos' : 'amber'}">${faits}/${p.etapes.length}</span> · <a class="lnk" onclick="buRecommencer('${p.id}')">recommencer</a>`, `<div class="menu-b">${b}</div>`);
  }
  h += '</div>';
  proMenu(cmds);
  return h + noteBas('Chaque étape se coche toute seule quand l’écran correspondant a été ouvert (journal local au navigateur). « Recommencer » remet le parcours à zéro à partir de maintenant.');
}
function buRecommencer(id) { const d = grcLire('grc_bu_debut', {}); d[id] = Date.now(); grcStocker('grc_bu_debut', d); renderFn(); }
document.addEventListener('keydown', e => {  // flash-cards : Espace / flèches
  if (currentTab !== 'fn' || FN_STATE.name !== 'BU' || !FN_STATE.bu || FN_STATE.bu.vue !== 'entretien') return;
  const ae = document.activeElement; if (ae && ['INPUT', 'TEXTAREA', 'SELECT'].includes(ae.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); FN_STATE.bu.voir = !FN_STATE.bu.voir; renderFn(); }
  else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); FN_STATE.bu.q += e.key === 'ArrowRight' ? 1 : -1; FN_STATE.bu.voir = false; renderFn(); }
});

/* ============ SEARCH : RECHERCHE COMPLÈTE PAR CATÉGORIES (HL) ============ */
// les fonctions sont décrites en français, les livres sont surtout en anglais : on cherche dans les deux langues
const PRO_LEXIQUE = [['volatilite', 'volatility'], ['couverture', 'hedge'], ['taux', 'rate'], ['rendement', 'return'], ['risque', 'risk'], ['dividende', 'dividend'],
  ['obligation', 'bond'], ['devise', 'currency'], ['change', 'fx'], ['action', 'stock'], ['contrat a terme', 'futures'], ['matiere premiere', 'commodity'], ['portefeuille', 'portfolio'],
  ['regime', 'regime'], ['correlation', 'correlation'], ['apprentissage par renforcement', 'reinforcement learning'], ['processus gaussien', 'gaussian process'], ['inflation', 'inflation'],
  ['croissance', 'growth'], ['bulle', 'bubble'], ['tendance', 'trend'], ['momentum', 'momentum'], ['prevision', 'forecast'], ['resultat', 'earnings'], ['chaine', 'chain']];
function proTraduire(q) {
  const Q = grcSansAccent(q).toLowerCase();
  let fr = Q, en = Q;
  for (const [f, e] of PRO_LEXIQUE) { en = en.replace(new RegExp('\\b' + f + 's?\\b', 'g'), e); fr = fr.replace(new RegExp('\\b' + e + '\\b', 'g'), f); }
  return { fr, en };
}
async function fnSEARCH() {
  const S = FN_STATE, st = S.search = S.search || { q: '', cat: 'TOUT' };
  const q = (st.q || '').trim(), Q = grcSansAccent(q);
  let h = fnHeader('SEARCH <span class="muted">Recherche complète</span>', 'fonctions · titres · documents · concepts · actualités', '<span class="muted small">mot-clé puis Alt+S (touche SEARCH) depuis n’importe où</span>');
  h += `<div class="aide-recherche"><input type="text" id="searchQ" placeholder="Un sujet : inflation, volatilité, couverture, Apple, Kelly…" value="${esc(q)}" onkeydown="if(event.key==='Enter'){FN_STATE.search.q=this.value;renderFn()}"></div>`;
  if (!q) { setTimeout(() => { const i = document.getElementById('searchQ'); if (i) i.focus(); }, 0); proMenu([]); return h + '<div class="loader">Tapez un sujet puis Entrée.</div>'; }
  const res = { FONCTIONS: [], TITRES: [], DOCUMENTS: [], CONCEPTS: [], ACTUALITÉS: [] };
  const T = proTraduire(q);
  for (const f of grcListeFonctions()) {
    const s = Math.max(grcCorrespond(f, q), grcCorrespond(f, T.fr));
    if (s > 0) res.FONCTIONS.push([s, f.ticker ? (FN_STATE.sym || 'SPY') + ' ' + f.code : f.code, f.code, f.titre, f.description || '']);
  }
  res.FONCTIONS.sort((a, b) => b[0] - a[0]);
  for (const [s, n] of grcTitresConnus()) if (s.startsWith(Q) || (Q.length >= 3 && grcSansAccent(n).includes(Q))) res.TITRES.push([1, s + ' DES', s, n, 'fiche DES']);
  const [docs, news] = await Promise.all([proFetch('DOCS', '', { q: T.en, n: 8 }).catch(() => ({})), (NEWS ? Promise.resolve(NEWS) : fetch('/api/news').then(r => r.json()).then(x => (NEWS = x)).catch(() => null))]);
  for (const r of (docs && docs.resultats) || []) res.DOCUMENTS.push([r.score, `DOCS ${q}`, 'p. ' + r.page, r.doc.replace(/\.pdf$/i, ''), '« …' + r.extrait.slice(0, 160) + '… »', r]);
  for (const c of (docs && docs.concepts) || []) if (grcSansAccent(c.titre + ' ' + c.famille).includes(Q) || Q.split(/\s+/).every(m => grcSansAccent(c.titre).includes(m))) res.CONCEPTS.push([1, (c.commandes || [])[0] || 'DOCS', c.famille, c.titre, `${c.mentions} mentions · ${(c.commandes || []).join(' ') || 'absent de GRC'}`]);
  for (const it of (news && news.items) || []) if (Q.split(/\s+/).every(m => grcSansAccent(it.title).includes(m))) res.ACTUALITÉS.push([1, 'NH', it.source || '', it.title, '', null, it.link]);
  const cats = ['TOUT', ...Object.keys(res)];
  h += '<div class="search-g"><div class="search-cats">' + cats.map(c => `<div class="cat ${st.cat === c ? 'active' : ''}" onclick="FN_STATE.search.cat='${c}';renderFn()">${c} <span class="muted">${c === 'TOUT' ? Object.values(res).reduce((a, l) => a + l.length, 0) : res[c].length}</span></div>`).join('') + '</div><div>';
  const cmds = [];
  for (const c of Object.keys(res)) {
    if (st.cat !== 'TOUT' && st.cat !== c) continue;
    if (!res[c].length) continue;
    h += `<div class="menu-cat">${c}</div>`;
    for (const r of res[c].slice(0, st.cat === 'TOUT' ? 6 : 40)) {
      const [, cmd, code, titre, desc, doc, lien] = r;
      cmds.push(cmd);
      const clic = doc ? `FN_STATE.name='DOCS';FN_STATE.docs={q:'${proQ(q)}',lire:{doc:'${proQ(doc.doc)}',page:${doc.page}}};switchTab('fn')` : lien ? `window.open('${proQ(lien)}','_blank')` : `runCommand('${proQ(cmd)}')`;
      h += `<div class="menu-l" onclick="${clic}"><span class="menu-n">${cmds.length})</span><span class="menu-c">${esc(code)}</span><span class="menu-t">${esc(titre)}</span><span class="menu-d">${proSurligner(esc(desc), q + " " + T.en)}</span></div>`;
    }
  }
  if (!cmds.length) h += '<div class="muted" style="padding:10px">Rien trouvé. Essayez un autre mot, en anglais pour les livres.</div>';
  h += '</div></div>';
  proMenu(cmds);
  return h;
}
function proSearch(q) {
  FN_STATE.search = { q: (q || '').trim(), cat: 'TOUT' };
  FN_STATE.name = 'SEARCH';
  switchTab('fn');
}

/* ============ BLP : ESPACE DE TRAVAIL EN PANNEAUX ============ */
// chaque panneau est un terminal indépendant (iframe /?pane=N&cmd=…) avec sa propre barre de commande ;
// la disposition et la dernière commande de chaque panneau sont gardées dans le navigateur
const BLP_DEFAUT = ['WEI', 'TOP', 'SPY US <EQUITY> GP', 'PORT'];
const BLP_DISPOS = { '2x2': 4, '1+2': 3, '1x2': 2, '3x2': 6 };
let BLP_ACTIF = 0;
function blpEtat() {
  const e = grcLire('grc_blp', null) || {};
  const dispo = BLP_DISPOS[e.dispo] ? e.dispo : '2x2';
  const n = BLP_DISPOS[dispo];
  const cmds = (Array.isArray(e.cmds) ? e.cmds : []).concat(BLP_DEFAUT, ['NH', 'FXC', 'GC', 'HEDGE']).slice(0, Math.max(n, 6));
  return { dispo, n, cmds };
}
function fnBLP() {
  const E = blpEtat();
  let h = fnHeader('BLP <span class="muted">Espace de travail</span>', 'panneaux indépendants : chacun a sa barre de commande', '<span class="muted small">Alt+P = panneau suivant · Échap dans un panneau = son accueil</span>');
  h += '<div class="fn-tools">' + Object.keys(BLP_DISPOS).map(k => `<span class="rng ${E.dispo === k ? 'on' : ''}" onclick="blpDispo('${k}')">${k}</span>`).join('')
    + `<span class="rng" onclick="blpReinitialiser()">RÉINITIALISER</span><span class="muted small" style="margin-left:auto">Composer : une liste de titres, les nouvelles, un graphique, un moniteur (guide p. 18)</span></div>`;
  h += `<div class="blp blp-${E.dispo.replace('+', 'p')}">`;
  for (let i = 0; i < E.n; i++) h += `<div class="blp-p${i === BLP_ACTIF ? ' actif' : ''}" data-i="${i}"><iframe src="/?pane=${i}&cmd=${encodeURIComponent(E.cmds[i])}" title="Panneau ${i + 1}"></iframe></div>`;
  h += '</div>';
  setTimeout(() => { const b = document.querySelector('#content .fn-bar'); if (b) b.style.display = 'none'; blpBrancher(); }, 0);
  proMenu([]);
  return h;
}
function blpBrancher() {
  document.querySelectorAll('.blp-p').forEach(p => {
    const f = p.querySelector('iframe');
    f.addEventListener('load', () => {
      try { f.contentWindow.addEventListener('focus', () => blpActiver(+p.dataset.i, false)); f.contentDocument.addEventListener('mousedown', () => blpActiver(+p.dataset.i, false)); } catch (e) { /* même origine : toujours accessible */ }
      if (+p.dataset.i === BLP_ACTIF) blpActiver(BLP_ACTIF, true);
    });
  });
}
function blpActiver(i, focus) {
  const ps = document.querySelectorAll('.blp-p'); if (!ps.length) return;
  BLP_ACTIF = (i + ps.length) % ps.length;
  ps.forEach(p => p.classList.toggle('actif', +p.dataset.i === BLP_ACTIF));
  if (focus) { const f = ps[BLP_ACTIF].querySelector('iframe'); try { f.contentWindow.focus(); const c = f.contentDocument.getElementById('cmdInput'); if (c) c.focus(); } catch (e) { f.focus(); } }
}
function blpDispo(k) { const e = grcLire('grc_blp', {}) || {}; e.dispo = k; grcStocker('grc_blp', e); renderFn(); }
function blpReinitialiser() { grcStocker('grc_blp', { dispo: '2x2', cmds: BLP_DEFAUT.slice() }); BLP_ACTIF = 0; renderFn(); }
window.addEventListener('message', ev => {
  if (ev.origin !== location.origin || !ev.data || !ev.data.grc) return;
  const m = ev.data;
  if (m.grc === 'cmd') { const e = grcLire('grc_blp', {}) || {}; const E = blpEtat(); e.cmds = E.cmds; e.cmds[m.pane] = m.cmd; e.dispo = E.dispo; grcStocker('grc_blp', e); }
  else if (m.grc === 'panel') blpActiver(BLP_ACTIF + (m.sens || 1), true);
  else if (m.grc === 'actif') blpActiver(m.pane, false);
  else if (m.grc === 'cancel') { switchTab('terminal'); }
});
// dans un panneau : interface allégée, commandes remontées au parent pour être mémorisées
const GRC_PANNEAU = (() => { const p = new URLSearchParams(location.search); return window.parent !== window && p.has('pane') ? +p.get('pane') : null; })();
function proPanneauSignaler() {
  if (GRC_PANNEAU === null) return;
  const e = grcEtatCourant();
  let cmd = e.tab === 'fn' ? (grcAvecTitre(e.fn) ? (e.sym || '') + ' ' + e.fn : e.fn) : (ECRANS[e.tab] || ['MAIN'])[0];
  if (e.fn === 'MENU' || e.fn === 'HELP' || e.fn === 'BLP') return;
  parent.postMessage({ grc: 'cmd', pane: GRC_PANNEAU, cmd: cmd.trim() }, location.origin);
}
if (GRC_PANNEAU !== null) {
  document.body.classList.add('grc-pane');
  window.addEventListener('focus', () => parent.postMessage({ grc: 'actif', pane: GRC_PANNEAU }, location.origin));
}
// PANEL (Alt+P) : dans BLP, panneau suivant ; dans un panneau, demande au parent ; sinon écran suivant
const proTouchePanelOrig = touchePanel;
touchePanel = function (sens) {
  if (GRC_PANNEAU !== null) return parent.postMessage({ grc: 'panel', sens }, location.origin);
  if (currentTab === 'fn' && FN_STATE.name === 'BLP') return blpActiver(BLP_ACTIF + sens, true);
  return proTouchePanelOrig(sens);
};

/* ============ GRAB (Alt+G) ET EXPORT (Alt+E) : GARDER LE CONTEXTE ============ */
// « Le minimum à conserver : le titre, le champ, la période, la devise, l'unité et la date d'extraction » (guide p. 21)
function proContexte() {
  const e = grcEtatCourant();
  return `Gambit Ridge Capital · ${grcLibelle(e)} · ${(document.querySelector('#screenH .sh-titre') || {}).textContent || ''} · extrait le ${new Date().toLocaleString('fr-FR')}`;
}
async function proGrab() {
  const c = document.getElementById('content'); if (!c) return;
  const bar = c.querySelector('.fn-bar');
  const texte = proContexte() + '\n\n' + c.innerText.replace(bar ? bar.innerText : '', '').replace(/\n{3,}/g, '\n\n').trim();
  try { await navigator.clipboard.writeText(texte); grcMessage('GRAB : écran copié avec son contexte (titre, fonction, date)'); }
  catch (e) { grcMessage('Copie refusée par le navigateur'); }
}
function proExporter() {
  const tables = [...document.querySelectorAll('#content table')].filter(t => t.rows.length > 1 && !t.closest('.fn-bar'));
  if (!tables.length) return grcMessage('Aucun tableau à exporter sur cet écran');
  const cel = s => { s = s.replace(/\s+/g, ' ').trim(); return /[;"\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  let csv = '﻿' + cel(proContexte()) + '\n';
  for (const t of tables) { csv += '\n'; for (const r of t.rows) csv += [...r.cells].map(x => cel(x.innerText)).join(';') + '\n'; }
  const e = grcEtatCourant(), nom = ('GRC ' + grcLibelle(e) + ' ' + new Date().toISOString().slice(0, 10)).replace(/[^\w\- ]+/g, '').replace(/\s+/g, '_') + '.csv';
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); a.download = nom; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  grcMessage(`EXPORT : ${tables.length} tableau(x) → ${nom} (séparateur ; pour Excel français)`);
}

/* ============ CLAVIER : SEARCH, GRAB, EXPORT ============ */
document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey) return;
  const cmd = grcCmd();
  // touche SEARCH : mot-clé dans la barre puis Alt+S (ou Maj+Entrée) ; barre vide = écran de recherche
  if ((e.altKey && e.code === 'KeyS') || (e.shiftKey && e.key === 'Enter' && document.activeElement === cmd)) {
    e.preventDefault(); e.stopPropagation();
    const v = cmd ? cmd.value.trim() : '';
    if (cmd) { cmd.value = ''; cmd.blur(); }
    grcSuggFermer();
    return proSearch(v);
  }
  if (e.altKey && e.code === 'KeyG') { e.preventDefault(); return proGrab(); }
  if (e.altKey && e.code === 'KeyE') { e.preventDefault(); return proExporter(); }
}, true);

/* ============ REGISTRE ============ */
const proEcran = (code, titre, cat, desc, rendu, o) => grcEnregistrerFonction(Object.assign({ code, titre, categorie: cat, description: desc, exemple: code, barre: false, rendu }, o || {}));
proEcran('HP', 'Prix historiques en tableau', 'Titres', 'Ouverture, haut, bas, clôture, variation et volume par jour, semaine ou mois. Export CSV (Alt+E).', sym => fnHP(sym),
  { ticker: true, exemple: 'SPY HP', secteurs: ['EQUITY', 'INDEX', 'CRNCY', 'CMDTY'], controle: 'périodicité, devise, unité ; cours bruts (dividendes : RG).' });
proEcran('DVD', 'Dividendes', 'Titres', 'Historique des dividendes (date ex, montant), rendement 12 mois, fréquence, croissance sur 5 ans.', sym => fnDVD(sym),
  { ticker: true, exemple: 'JNJ DVD', secteurs: ['EQUITY'], alias: ['DVDH'] });
proEcran('RG', 'Rendement total comparé', 'Titres', 'Rendement total (dividendes réinvestis) contre variation du cours, jusqu’à 6 titres, de 1 mois à 10 ans.', sym => fnRG(sym),
  { ticker: true, exemple: 'SPY RG', secteurs: ['EQUITY', 'INDEX'], alias: ['TRA', 'COMP'], controle: 'mêmes dates et même devise pour tous les titres.' });
proEcran('OMON', 'Chaîne d’options', 'Dérivés', 'Calls / puts par échéance et strike : fourchettes, vol implicite, volumes, positions ouvertes, ratio put / call.', sym => fnOMON(sym),
  { ticker: true, exemple: 'SPY OMON', secteurs: ['EQUITY'], alias: ['OMST'], chargement: 'toutes les échéances d’options, une dizaine de secondes', controle: 'sous-jacent, maturité, strike et type.' });
proEcran('CN', 'Actualités de la société', 'Titres', 'Dépêches récentes sur la société (Google News), cache 30 minutes.', sym => fnCN(sym),
  { ticker: true, exemple: 'NVDA CN', secteurs: ['EQUITY'] });
proEcran('FLDS', 'Recherche de champs', 'Données', 'Dictionnaire des champs BDP / BDH / BDS / BQL : définition, unité, disponible ou payant.', () => fnFLDS(), { alias: ['FIELDS', 'CHAMPS'] });
proEcran('DOCS', 'L’araignée des docs', 'Recherche', 'Recherche plein texte dans la bibliothèque de Tom (livres de finance, guide Bloomberg, cours) et toile concepts ↔ pages ↔ code du fonds.', () => fnDOCS(),
  { barre: true, alias: ['ARAIGNEE', 'SPIDER', 'BIBLIO'], secteurs: ['ALPHA'] });
proEcran('MEMO', 'Mémo des fonctions du guide', 'Aide', 'Le mémo du guide Bloomberg (p. 24) : pour chaque code, la fonction ici, son équivalent, ou pourquoi elle manque.', () => fnMEMO(), { alias: ['MEMENTO', 'GUIDE'] });
proEcran('BU', 'Formation', 'Aide', 'Parcours vérifiés automatiquement (action de bout en bout, routine du matin, dérivés, clavier) et questions d’entretien en flash-cards.', () => fnBU(), { alias: ['BMC', 'BHL', 'BPS', 'FORMATION', 'ENTRETIEN'] });
proEcran('SEARCH', 'Recherche complète', 'Aide', 'Un sujet dans tout le terminal : fonctions, titres, pages des livres, concepts, actualités. Touche SEARCH : mot-clé puis Alt+S.', () => fnSEARCH(), { alias: ['RECHERCHE', 'SRCHALL'] });
proEcran('BLP', 'Espace de travail en panneaux', 'Aide', 'Launchpad : 2 à 6 panneaux indépendants (liste de titres, nouvelles, graphique, moniteur). Alt+P passe d’un panneau à l’autre.', () => fnBLP(), { alias: ['LAUNCHPAD', 'LP', 'PANELS'] });
grcEnregistrerFonction({ code: 'GRAB', titre: 'Capture de l’écran', categorie: 'Aide', description: 'Copie l’écran dans le presse-papiers avec son contexte (titre, fonction, date). Raccourci Alt+G.', exemple: 'GRAB', barre: false, lancer: () => proGrab() });
grcEnregistrerFonction({ code: 'EXPORT', titre: 'Export des tableaux en CSV', categorie: 'Aide', description: 'Télécharge les tableaux de l’écran en CSV (séparateur ; pour Excel français), avec le contexte. Raccourci Alt+E.', exemple: 'EXPORT', alias: ['EXP', 'CSV'], barre: false, lancer: () => proExporter() });
// contrôles du guide sur les fonctions existantes (affichés dans HELP)
for (const [c, t] of [['DES', 'nom complet, type d’instrument, marché et devise ; un ticker proche ne suffit pas (guide p. 6).'], ['FA', 'devise, unité, période, fréquence, chiffres publiés ou estimés.'],
  ['EQS', 'valeurs absentes et doublons entre lignes de cotation avant d’exploiter la liste.'], ['FXC', 'sens de la paire, devise de base et de contrepartie, spot ou terme.'],
  ['GP', 'période, échelle (log), cours bruts ou ajustés.'], ['WEI', 'univers, indicateur, période ; croiser avec l’actualité.'], ['BQL', 'identifiant, champ, unités, devise, dates et fréquence ; ne pas remplacer une donnée absente par zéro.']]) {
  const f = grcFonction(c); if (f && !f.controle) f.controle = t;
}
// les parcours et le journal : Equity a désormais HP, DVD, RG, OMON, CN dans son menu d'instrument
for (const c of ['HP', 'RG', 'CN']) for (const fam of ['Index', 'Curncy', 'Comdty']) if (c === 'HP' && !GRC_FN_PAR_FAMILLE[fam].includes(c)) GRC_FN_PAR_FAMILLE[fam].splice(1, 0, c);
for (const c of ['HP', 'DVD', 'RG', 'OMON', 'CN']) if (!GRC_FN_PAR_FAMILLE.Equity.includes(c)) GRC_FN_PAR_FAMILLE.Equity.push(c);
proRegistrerMemo();

/* ============ COMMANDES À TEXTE LIBRE : SEARCH mots, DOCS mots, numéros des résultats ============ */
let PRO_DOCS_RES = [];
const proRunOrig = runCommand;
runCommand = function (raw) {
  const brut = String(raw || '').trim(), toks = brut.split(/\s+/), t0 = (toks[0] || '').toUpperCase();
  if (t0 === 'SEARCH' && toks.length > 1) return proSearch(toks.slice(1).join(' '));
  if ((t0 === 'DOCS' || t0 === 'ARAIGNEE') && toks.length > 1) { FN_STATE.docs = { q: toks.slice(1).join(' '), lire: null }; FN_STATE.name = 'DOCS'; return switchTab('fn'); }
  if (t0 === 'DOCSPAGE') { const r = PRO_DOCS_RES[+toks[1] - 1]; if (r) { FN_STATE.docs.lire = { doc: r.doc, page: r.page }; return renderFn(); } return; }
  if (t0 === 'DOCS' && FN_STATE.docs) FN_STATE.docs.lire = null;
  return proRunOrig(raw);
};
// dans un panneau : Échap sur l'accueil du panneau = quitter l'espace BLP
if (GRC_PANNEAU !== null) {
  const proAnnulerOrig = toucheAnnuler;
  toucheAnnuler = function () { if (currentTab === 'terminal') return parent.postMessage({ grc: 'cancel' }, location.origin); return proAnnulerOrig(); };
}
