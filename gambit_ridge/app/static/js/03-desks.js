/* Gambit Ridge Capital — terminal : 03-desks.js (scripts classiques, globals partagés, chargés dans l'ordre) */
/* ============ RH ============ */
async function renderHR() {
  document.getElementById('content').innerHTML = '<div class="loader">Module RH désactivé dans la version publique.</div>';
}

/* ============ ACTUALITÉS ============ */
/* ============ ACTUALITÉS ============ */
let newsFilter = 'TOUS';
async function renderNews() {
  if (!NEWS) {
    document.getElementById('content').innerHTML = '<div class="loader">Chargement des actualités…</div>';
    try { const r = await fetch('/api/news'); NEWS = await r.json(); } catch(e) { NEWS = null; }
  }
  if (!NEWS || !NEWS.items) { document.getElementById('content').innerHTML = '<div class="loader">Actualités indisponibles (hors ligne ?).</div>'; return; }
  const cats = ['TOUS', ...new Set(NEWS.items.map(i=>i.category))];
  if (!cats.includes(newsFilter)) newsFilter = 'TOUS';
  let html = '<div class="news-cats">';
  for (const c of cats) html += `<div class="cat ${newsFilter===c?'active':''}" onclick="setNewsFilter('${esc(c)}')">${esc(c)} ${c==='TOUS'?'('+NEWS.items.length+')':'('+NEWS.items.filter(i=>i.category===c).length+')'}</div>`;
  html += '</div>';
  const items = newsFilter==='TOUS' ? NEWS.items : NEWS.items.filter(i=>i.category===newsFilter);
  html += '<div class="panel"><div class="panel-h">Fil d\u2019actualité <span class="rt">' + items.length + ' dépêches · cache 1 h</span></div><div class="panel-b" style="padding:0">';
  for (const it of items) {
    const dt = it.date ? it.date.replace(/^\w+, */, '').split(' +')[0] : '';
    html += `<div class="news-item"><span class="src">${esc(it.source||it.category)}</span><a href="${esc(it.link)}" target="_blank">${esc(it.title)}</a><span class="dt">${esc(dt)}</span></div>`;
  }
  html += '</div></div>';
  document.getElementById('content').innerHTML = html;
}
function setNewsFilter(c) { newsFilter = c; renderNews(); }

/* ============ STRATÉGIES ============ */
let STRATS = null, MATH_TOPICS = [];
async function renderStrategies() {
  const c = document.getElementById('content');
  if (!STRATS) {
    c.innerHTML = '<div class="loader">Chargement de la documentation des stratégies…</div>';
    let data = null;
    try { data = await (await fetch('/api/strategies')).json(); STRATS = data.strategies || []; MATH_TOPICS = data.math_topics || []; } catch(e) { STRATS = []; MATH_TOPICS = []; }
  }
  let html = '<div class="panel-h">Documentation des stratégies du fonds <span class="rt">' + (STRATS?STRATS.length:0) + ' stratégies · statut d\u2019évaluation OOS honnête</span></div>';
  html += '<div class="muted" style="font-size:11px;margin:6px 0">Règle de la maison : une stratégie n\u2019est activée en production (paper trading) que si elle bat la baseline hors-échantillon (walk-forward purgé). Les autres sont documentées et désactivées.</div>';
  for (const st of STRATS || []) {
    let badge = 'badge-doc', bl = 'DOC';
    if ((st.verdict_oos||'').match(/GAGNANT|branché/i)) { badge='badge-win'; bl='PROD'; }
    else if ((st.verdict_oos||'').match(/DÉSACTIVÉ|ne bat pas|NON RETENU/i)) { badge='badge-off'; bl='OFF'; }
    else if ((st.verdict_oos||'').match(/exploration|AUCUN edge/i)) { badge='badge-explore'; bl='EXPLORATION'; }
    html += `<div class="strat-card"><div class="s-head"><span class="s-name">${esc(st.name)}</span><span class="strat-badge ${badge}">${bl}</span><span class="muted" style="font-size:10px">${esc(st.category)} · ${esc(st.chapter)}</span></div>`;
    html += `<div class="s-body"><div class="s-row"><span class="s-lbl">Principe</span>${esc(st.principle)}</div>`;
    html += `<div class="s-row"><span class="s-lbl">Facteurs</span>${esc((st.factors||[]).join(' · '))}</div>`;
    html += `<div class="s-row"><span class="s-lbl">Règles</span>${esc(st.rules)}</div>`;
    html += `<div class="s-row"><span class="s-lbl">Coûts</span>${esc(st.costs)}</div>`;
    html += `<div class="s-row"><span class="s-lbl">Forces</span><span class="pos">${esc(st.strengths)}</span></div>`;
    html += `<div class="s-row"><span class="s-lbl">Limites</span><span class="neg">${esc(st.limits)}</span></div>`;
    html += `<div class="s-row"><span class="s-lbl">Verdict OOS</span><span class="amber">${esc(st.verdict_oos)}</span></div>`;
    html += '</div></div>';
  }
  // ---- Section MATHS (modèles stochastiques & réseaux, Dixon ch. 7-10) ----
  const MT = MATH_TOPICS || [];
  if (MT.length) {
    html += '<div class="panel-h" style="margin-top:18px">Bibliothèque mathématique <span class="rt">' + MT.length + ' modèles · équations & statut réel</span></div>';
    html += '<div class="muted" style="font-size:11px;margin:6px 0">Markov & HMM (Viterbi, filtrage, lissage) · espaces d\u2019états (Kalman, particulaire, SIR, vol stochastique) · calibration de filtres (ponctuelle, bayésienne) · réseaux récurrents (RNN, mémoire, GRU, LSTM, alpha-RNN, NNETS, LOB) · convolution (smoothers, CNN, pooling, dilated) · autoencodeurs (linéaires ≡ PCA, profonds).</div>';
    for (const mt of MT) {
      let mb = 'badge-doc', ml = 'DOC';
      if ((mt.status||'').match(/IMPLÉMENTÉ|actif/i) && !(mt.status||'').match(/DÉSACTIVÉ|ne bat pas|verdict/i)) { mb='badge-win'; ml='IMPL'; }
      else if ((mt.status||'').match(/DÉSACTIVÉ|ne bat pas|NON RETENU|évalué,|ÉVALUÉ,/i)) { mb='badge-off'; ml='OFF'; }
      else if ((mt.status||'').match(/EXPLORATION|exploration/i)) { mb='badge-explore'; ml='EXPLORATION'; }
      html += `<div class="strat-card"><div class="s-head"><span class="s-name">${esc(mt.name)}</span><span class="strat-badge ${mb}">${ml}</span><span class="muted" style="font-size:10px">${esc(mt.chapter)}</span></div>`;
      html += `<div class="s-body"><div class="s-row"><span class="s-lbl">Principe</span>${esc(mt.principle)}</div>`;
      html += `<div class="s-row"><span class="s-lbl">Équations</span><span style="font-family:ui-monospace,monospace;color:#8ab4f8">${esc(mt.equations)}</span></div>`;
      html += `<div class="s-row"><span class="s-lbl">Entraînement</span>${esc(mt.training)}</div>`;
      html += `<div class="s-row"><span class="s-lbl">Dans le fonds</span>${esc(mt.use_in_fund)}</div>`;
      html += `<div class="s-row"><span class="s-lbl">Statut</span><span class="amber">${esc(mt.status)}</span></div>`;
      html += '</div></div>';
    }
  }
  c.innerHTML = html;
}

/* ============ VOIX ============
   Trois moteurs, choisis automatiquement :
   1. app Mac : pont natif (dictée macOS + voix AVSpeech) via webkit.messageHandlers.grcVoice
   2. navigateur compatible (Safari/Chrome) : Web Speech API
   3. sinon : saisie au clavier (la réponse est quand même lue à voix haute si possible) */
let voiceListening = false, voiceBusy = false, voiceConvo = false, voiceRecog = null, voicePartial = '';
const NATIVE_VOICE = !!(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.grcVoice);
const WEB_SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function voiceEngine() { return NATIVE_VOICE ? 'native' : (WEB_SR ? 'web' : 'none'); }
function nativeVoice(msg) { window.webkit.messageHandlers.grcVoice.postMessage(msg); }
function voiceIndexFor(target) { let h = 0; for (const ch of target) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; }

async function renderVoice() {
  const c = document.getElementById('content');
  if (!ROSTER) { try { const r = await fetch('/api/agents'); ROSTER = (await r.json()).teams; } catch(e) { ROSTER = []; } }
  const eng = voiceEngine();
  const engLabel = { native: 'dictée macOS native · voix système', web: 'reconnaissance vocale du navigateur', none: 'micro indisponible ici — saisie clavier' }[eng];
  let html = '<div class="panel-h">Open space vocal <span class="rt">' + engLabel + '</span></div>';
  html += '<div class="voice-grid" style="margin-top:8px">';
  html += '<div class="voice-side"><div class="hdr-row" style="margin-bottom:6px">Interlocuteur</div><select id="voiceTarget" style="width:100%">';
  for (const t of ROSTER || []) {
    html += `<option value="manager-${esc(t.team)}">Manager ${esc(t.manager)} — ${esc(t.team)}</option>`;
    for (const a of t.agents) html += `<option value="${esc(a.id)}">${esc(a.name||a.id)} — ${esc(t.team)}</option>`;
  }
  html += '</select>';
  html += `<button class="btn mic-btn" id="voiceBtn" onclick="toggleVoice()" ${eng==='none'?'disabled':''}><span class="mic-dot"></span><span id="voiceBtnTxt">${eng==='none'?'MICRO INDISPONIBLE':'PARLER'}</span></button>`;
  html += `<label class="convo"><input type="checkbox" id="voiceConvo" ${voiceConvo?'checked':''} onchange="voiceConvo=this.checked" ${eng==='none'?'disabled':''}> Mode conversation (l’écoute reprend après chaque réponse)</label>`;
  html += `<div id="voiceStatus">${eng==='none' ? 'Ouvre le terminal depuis l’app Gambit Ridge Capital (ou Safari/Chrome) pour utiliser le micro.' : 'Clique sur PARLER ou appuie sur Espace. L’envoi est automatique quand tu fais une pause.'}</div>`;
  html += '<div class="voice-live" id="voiceLive"></div>';
  html += '<div class="chat-input"><input type="text" id="voiceText" placeholder="…ou tape ta question" onkeydown="if(event.key===\'Enter\'){voiceSend(this.value);this.value=\'\'}"><button class="btn" onclick="const i=document.getElementById(\'voiceText\');voiceSend(i.value);i.value=\'\'">ENVOYER</button></div>';
  html += `<div class="muted" style="font-size:10px;margin-top:10px">${eng==='native' ? 'Reconnaissance sur l’appareil quand macOS le permet, sinon via le service de dictée d’Apple. Première utilisation : macOS demande l’accès au micro et à la reconnaissance vocale. Voix plus naturelles : Réglages Système > Accessibilité > Contenu énoncé > Voix système > Gérer les voix > Français (voix « Premium »).' : 'Voix et reconnaissance fournies par le système.'}</div>`;
  html += '</div>';
  html += '<div class="voice-side"><div class="voice-log" id="voiceLog"><span class="muted">Ta conversation apparaîtra ici…</span></div></div>';
  html += '</div>';
  c.innerHTML = html;
  voiceSetState(voiceListening);
}

function voiceSetState(listening) {
  voiceListening = listening;
  const b = document.getElementById('voiceBtn'), t = document.getElementById('voiceBtnTxt'), st = document.getElementById('voiceStatus');
  if (b) b.classList.toggle('live', listening);
  if (t && voiceEngine() !== 'none') t.textContent = listening ? 'J’ÉCOUTE… (clique pour envoyer)' : voiceBusy === 'fetch' ? 'RÉFLEXION…' : voiceBusy === 'speak' ? 'COUPER ET PARLER' : 'PARLER';
  if (st && listening) st.textContent = 'Micro actif — parle, l’envoi part tout seul après une courte pause.';
}

function toggleVoice() {
  const eng = voiceEngine();
  if (eng === 'none' || voiceBusy === 'fetch') return;
  if (voiceBusy === 'speak') { // couper la réponse en cours pour reprendre la parole
    NATIVE_VOICE ? nativeVoice({ cmd: 'silence' }) : ('speechSynthesis' in window && speechSynthesis.cancel());
    voiceBusy = false;
  }
  if (voiceListening) { eng === 'native' ? nativeVoice({ cmd: 'stop' }) : (voiceRecog && voiceRecog.stop()); return; }
  voicePartial = '';
  const live = document.getElementById('voiceLive'); if (live) live.textContent = '';
  if (eng === 'native') { nativeVoice({ cmd: 'start', lang: 'fr-FR' }); return; }
  voiceRecog = new WEB_SR();
  voiceRecog.lang = 'fr-FR'; voiceRecog.continuous = false; voiceRecog.interimResults = true;
  voiceRecog.onstart = () => voiceSetState(true);
  voiceRecog.onresult = ev => {
    voicePartial = Array.from(ev.results).map(r => r[0].transcript).join(' ');
    const live = document.getElementById('voiceLive'); if (live) live.textContent = voicePartial;
  };
  voiceRecog.onerror = ev => { const st = document.getElementById('voiceStatus'); if (st) st.textContent = 'Erreur micro : ' + ev.error; };
  voiceRecog.onend = () => { voiceSetState(false); if (voicePartial.trim()) voiceSend(voicePartial); };
  voiceRecog.start();
}

// événements du pont natif
window.grcVoiceEvent = ev => {
  const live = document.getElementById('voiceLive'), st = document.getElementById('voiceStatus');
  if (ev.type === 'state') voiceSetState(ev.listening);
  else if (ev.type === 'partial') { voicePartial = ev.text; if (live) live.textContent = ev.text; }
  else if (ev.type === 'final') { if (live) live.textContent = ''; if ((ev.text || '').trim()) voiceSend(ev.text); else if (st) st.textContent = 'Je n’ai rien entendu — réessaie.'; }
  else if (ev.type === 'error') { voiceSetState(false); if (st) st.innerHTML = '<span class="neg">' + esc(ev.error) + '</span>'; }
  else if (ev.type === 'speechEnd') voiceAfterSpeech();
};

function voiceAfterSpeech() {
  voiceBusy = false; voiceSetState(false);
  if (voiceConvo && currentTab === 'voice') setTimeout(() => { if (!voiceListening && !voiceBusy) toggleVoice(); }, 350);
}

async function voiceSend(text) {
  text = (text || '').trim();
  if (!text) return;
  const sel = document.getElementById('voiceTarget');
  if (!sel) return;
  const target = sel.value, who = sel.selectedOptions[0].textContent;
  const log = document.getElementById('voiceLog');
  if (log.querySelector('.muted')) log.innerHTML = '';
  log.insertAdjacentHTML('beforeend', `<div class="v-you">❯ TOI : ${esc(text)}</div><div class="v-agent v-pending">${esc(who)} réfléchit…</div>`);
  log.scrollTop = log.scrollHeight;
  voiceBusy = 'fetch'; voiceSetState(false);
  const answer = await converse(target, text);
  const pend = log.querySelector('.v-pending'); if (pend) pend.remove();
  log.insertAdjacentHTML('beforeend', `<div class="v-agent"><span class="amber">${esc(who)}</span> : ${esc(answer)}</div>`);
  log.scrollTop = log.scrollHeight;
  voiceBusy = 'speak'; voiceSetState(false);
  const st = document.getElementById('voiceStatus'); if (st) st.textContent = 'Réponse lue à voix haute — clique sur PARLER (ou Espace) pour couper et répondre.';
  if (NATIVE_VOICE) nativeVoice({ cmd: 'speak', text: answer, voice: voiceIndexFor(target), rate: 0.5 });
  else if ('speechSynthesis' in window) {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(answer);
    u.lang = 'fr-FR'; u.rate = 1.05;
    const fr = speechSynthesis.getVoices().filter(v => v.lang.startsWith('fr'));
    if (fr.length) u.voice = fr[voiceIndexFor(target) % fr.length];
    u.onend = voiceAfterSpeech; speechSynthesis.speak(u);
  } else voiceAfterSpeech();
}

// Espace = parler (hors champ de saisie), Échap = couper la voix
document.addEventListener('keydown', e => {
  if (currentTab !== 'voice' || ['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); toggleVoice(); }
  if (e.code === 'Escape') { NATIVE_VOICE ? nativeVoice({ cmd: 'silence' }) : ('speechSynthesis' in window && speechSynthesis.cancel()); voiceBusy = false; voiceSetState(false); }
});

/* ============ BACKTEST ============ */
async function runBacktest() {
  const btn = document.getElementById('btBtn');
  const strategy = document.getElementById('btStrategy').value;
  const data = document.getElementById('btData').value;
  btn.disabled = true; btn.textContent = 'EN COURS…';
  try {
    const r = await fetch('/api/backtest', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({strategy, data})});
    BT = await r.json();
    renderBacktest();
  } catch(e) {
    document.getElementById('btResult').innerHTML = '<div class="loader">Erreur : '+e+'</div>';
  } finally { btn.disabled = false; btn.textContent = 'EXÉCUTER'; }
}

function renderBacktest() {
  const dataLabels = { synth: 'Synthétique 40 ans', fred: 'FRED réel ~10 ans', 'fred-long': 'FRED réel ~55 ans', real: 'Polygon réel 2 ans', 'fred-fx': 'Forex FRED ~24 ans (6 paires)', binance: 'Crypto Binance ~4 ans (25 paires)', equities: 'Actions du fonds ~6 ans (8 tickers fondamentaux)' };
  const data = (BT && !BT.error) ? BT.data : 'synth';
  const isFx = data === 'fred-fx';
  const isCrypto = data === 'binance';
  const isEq = data === 'equities';
  const stratNames = isFx ? ['fx-carry','fx-statarb','fx-carry-trend'] : isCrypto ? ['crypto-momentum','crypto-regime','crypto-risk-managed'] : isEq ? ['equities-momentum','equities-regime','equities-risk-managed'] : ['momentum','meanrev','multifactor','regime-momentum','risk-managed','pairs-tech','combo'];
  const curStrat = (BT && !BT.error) ? BT.strategy : 'regime-momentum';
  const curData = data;
  let html = '<div class="panel" style="margin-bottom:10px"><div class="panel-b bt-controls">';
  html += '<span class="muted">STRATÉGIE</span><select id="btStrategy">';
  for (const s of stratNames) html += `<option value="${s}"${s===curStrat?' selected':''}>${s}</option>`;
  html += '<option value="all"'+(curStrat==='all'?' selected':'')+'>all (toutes)</option></select>';
  html += '<span class="muted">DONNÉES</span><select id="btData">';
  for (const [v,l] of Object.entries(dataLabels)) html += `<option value="${v}"${v===curData?' selected':''}>${l}</option>`;
  html += '</select>';
  html += '<button class="btn" id="btBtn" onclick="runBacktest()">EXÉCUTER</button>';
  html += '</div></div>';
  html += '<div id="btResult">';
  if (!BT) {
    html += '<div class="loader">Sélectionnez une stratégie et une source, puis EXÉCUTER.</div>';
  } else if (BT.error) {
    html += `<div class="loader neg">ERREUR : ${esc(BT.error)}</div>`;
  } else {
    const colors = ['#ff9900','#00c853','#2979ff','#ff1744','#ffea00','#00e5ff','#e040fb'];
    const names = Object.keys(BT.strategies);
    const allCurves = names.flatMap(n=>BT.strategies[n].equity_curve);
    const min = Math.min(...allCurves), max = Math.max(...allCurves), range = Math.max(max-min,1e-9);
    html += `<div class="panel"><div class="panel-h">Courbes d'equity <span class="rt">${BT.n_periods} périodes · ${BT.n_assets} actifs</span></div><div class="panel-b">`;
    html += `<svg viewBox="0 0 800 240" style="width:100%;height:240px" preserveAspectRatio="none">`;
    html += `<line x1="5" y1="${235-((100-min)/range)*225}" x2="795" y2="${235-((100-min)/range)*225}" stroke="#333" stroke-dasharray="3"/>`;
    names.forEach((n,i)=>{
      const eq = BT.strategies[n].equity_curve;
      const pts = eq.map((e,j)=>`${(j/(eq.length-1))*790+5},${235-((e-min)/range)*225}`).join(' ');
      html += `<polyline points="${pts}" fill="none" stroke="${colors[i%colors.length]}" stroke-width="1.5"/>`;
    });
    html += '</svg>';
    html += '<div class="legend2">'+names.map((n,i)=>`<span style="color:${colors[i%colors.length]}">■</span> ${n}`).join(' · ')+'</div>';
    html += '</div></div>';
    html += '<div class="panel" style="margin-top:10px"><div class="panel-h">Métriques <span class="rt">WF = walk-forward OOS</span></div><div class="panel-b" style="padding:4px"><table>';
    html += '<tr><th>Stratégie</th><th class="num">CAGR</th><th class="num">Sharpe</th><th class="num">Sortino</th><th class="num">Max DD</th><th class="num">Calmar</th><th class="num">Win rate</th><th class="num">WF OOS</th><th class="num">Dég.</th></tr>';
    for (const n of names) {
      const m = BT.strategies[n].metrics, wf = BT.strategies[n].walkforward;
      html += `<tr><td class="amber">${n}</td><td class="num ${m.cagr>=0?'pos':'neg'}">${sgn(m.cagr*100,2)}%</td><td class="num ${m.sharpe>=0?'pos':'neg'}">${sgn(m.sharpe,2)}</td><td class="num">${sgn(m.sortino,2)}</td><td class="num neg">${(m.max_drawdown*100).toFixed(1)}%</td><td class="num">${sgn(m.calmar,2)}</td><td class="num">${(m.win_rate*100).toFixed(0)}%</td><td class="num ${wf.oos_sharpe_mean>=0?'pos':'neg'}">${sgn(wf.oos_sharpe_mean,2)}</td><td class="num ${wf.degradation<=0.3?'pos':'neg'}">${sgn(wf.degradation,2)}</td></tr>`;
    }
    html += '</table><div class="legend2" style="margin-top:6px">WF OOS = Sharpe hors-échantillon (la seule métrique qui compte) · Dég. = dégradation IS→OOS (bas = robuste)</div>';
    html += '</div></div>';
  }
  html += '</div>';
  document.getElementById('content').innerHTML = html;
}

