/* Gambit Ridge Capital — terminal : 01-core.js (scripts classiques, globals partagés, chargés dans l'ordre) */
let STATE = null, BT = null, ROSTER = null, REPORTS = null, HROV = null, NEWS = null, selectedManager = null;
let currentTab = 'terminal';
let selectedAgent = null;
const CONVOS = {}; const chatHistory = CONVOS, managerChatHistory = CONVOS; // mémoire partagée chat écrit / voix

function switchTab(tab) {
  currentTab = tab;
  for (const t of ['terminal','research','risk','fn','agents','reports','backtest','hr','news','strategies','notes','voice','paper'])
    { const el = document.getElementById('tab-'+t); if (el) el.classList.toggle('active', tab===t); }
  if (tab==='terminal') render();
  else if (tab==='research') renderResearch();
  else if (tab==='fn') renderFn();
  else if (tab==='risk') { RISK = null; renderRisk(); }
  else if (tab==='agents') renderAgents();
  else if (tab==='reports') renderReports();
  else if (tab==='hr') renderHR();
  else if (tab==='news') renderNews();
  else if (tab==='strategies') renderStrategies();
  else if (tab==='voice') renderVoice();
  else if (tab==='notes') renderNotes();
  else if (tab==='paper') renderPaper();
  else renderBacktest();
}

/* ============ LOCK SCREEN ============ */
const GRC_PASS_HASH = 0; // 0 = pas de verrou ; définir un code : python3 scripts/set_access_code.py
function djb2(s) { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return h; }
function tryUnlock() {
  const inp = document.getElementById('lockInput');
  const msg = document.getElementById('lockMsg');
  if (djb2(inp.value) === GRC_PASS_HASH) {
    sessionStorage.setItem('grc_unlocked', '1');
    document.getElementById('lockScreen').style.display = 'none';
    inp.value = '';
  } else {
    msg.textContent = 'CODE REFUSÉ — TENTATIVE JOURNALISÉE';
    document.getElementById('lockScreen').classList.remove('lock-shake');
    void document.getElementById('lockScreen').offsetWidth;
    document.getElementById('lockScreen').classList.add('lock-shake');
  }
}
if (GRC_PASS_HASH === 0 || sessionStorage.getItem('grc_unlocked') === '1') document.getElementById('lockScreen').style.display = 'none';
document.addEventListener('DOMContentLoaded', () => { const i = document.getElementById('lockInput'); if (i) i.focus(); });

function fmtPct(x, d=1) { return (x*100).toFixed(d)+'%'; }
function sgn(x, d=2) { return (x>=0?'+':'')+x.toFixed(d); }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function updateClock() {
  const n = new Date();
  document.getElementById('clock').textContent = n.toLocaleDateString('fr-FR')+' '+n.toLocaleTimeString('fr-FR');
}
setInterval(updateClock, 1000); updateClock();

async function fetchState() {
  try {
    const r = await fetch('/api/state');
    STATE = await r.json();
    if (STATE.loading) {
      document.getElementById('content').innerHTML = '<div class="loader">Première synchronisation des données en cours… (une fois par jour)</div>';
      setTimeout(fetchState, 3000);
      return;
    }
    renderTape();
    if (currentTab==='terminal') render();
  } catch(e) {
    document.getElementById('connDot').textContent = '● OFFLINE';
    document.getElementById('connDot').style.color = 'var(--red)';
  }
}

async function renderAgents() {
  if (!ROSTER) {
    document.getElementById('content').innerHTML = '<div class="loader">Chargement de l\u2019open space…</div>';
    try { const r = await fetch('/api/agents'); ROSTER = (await r.json()).teams; } catch(e) { ROSTER = []; }
  }
  let html = '';
  for (const team of ROSTER || []) {
    html += `<div class="team-block"><div class="panel-h" style="padding:5px 10px">Équipe ${esc(team.team)} <span class="manager-tag" style="cursor:pointer" onclick="selectManager('manager-${esc(team.team)}')">Manager: ${esc(team.manager)} ▸</span> <span class="rt">${team.n_agents} agents</span></div>`;
    html += '<div class="agent-grid" style="padding:8px">';
    for (const a of team.agents) {
      html += `<div class="agent-card ${selectedAgent===a.id?'sel':''}" onclick="selectAgent('${esc(a.id)}')">
        <div class="nm">${esc(a.name||a.id)}</div>
        <div class="sc" style="height:auto;margin:2px 0"><span class="muted" style="font-size:9px">${esc(a.school||'')} · ${esc(a.specialty||'')}</span></div>
        <div class="sig muted">${a.tickers.slice(0,4).map(esc).join(' ')}${a.tickers.length>4?'…':''}</div>
      </div>`;
    }
    html += '</div></div>';
  }
  document.getElementById('content').innerHTML = html;
}

async function selectAgent(id) {
  selectedAgent = id;
  renderAgents();
  let d;
  try { const r = await fetch('/api/agent/'+encodeURIComponent(id)); d = await r.json(); } catch(e) { alert('Connexion perdue vers le serveur.'); return; }
  if (d.error) { alert('Agent introuvable : ' + d.error); return; }
  let html = `<div class="panel" style="margin-top:10px" id="agentDetail"><div class="panel-h">${esc(d.id)} <span class="rt">${esc(d.team)} · Manager: ${esc(d.manager)}</span></div><div class="panel-b">`;
  html += '<div class="grid" style="grid-template-columns:1fr 1fr">';
  // signaux + stats
  html += '<div><table><tr><th>Ticker</th><th class="num">Prix</th><th class="num">20j</th><th class="num">60j</th><th class="num">Vol</th></tr>';
  for (const s of d.ticker_stats) {
    html += `<tr><td class="amber">${s.ticker}</td><td class="num">${(s.price||0).toFixed(2)}</td><td class="num ${(s.ret_20d||0)>=0?'pos':'neg'}">${sgn((s.ret_20d||0)*100,1)}%</td><td class="num ${(s.ret_60d||0)>=0?'pos':'neg'}">${sgn((s.ret_60d||0)*100,1)}%</td><td class="num">${((s.vol_annual||0)*100).toFixed(0)}%</td></tr>`;
  }
  html += '</table>';
  html += '<table style="margin-top:8px"><tr><th>Signaux</th><th>Sens</th><th class="num">Conviction</th><th class="num">Score</th></tr>';
  for (const s of d.signals) {
    html += `<tr><td class="amber">${esc(s.ticker)}</td><td class="${s.direction==='long'?'pos':'neg'}">${s.direction==='long'?'▲':'▼'}</td><td class="num">${fmtPct(s.conviction,0)}</td><td class="num">${sgn(s.score,2)}</td></tr>`;
  }
  html += '</table></div>';
  // chat
  html += `<div><div class="chat-log" id="chatLog">${(chatHistory[id]||[]).map(m=>`<div class="q">❯ ${esc(m.q)}</div><div class="a">${esc(m.a)}</div>`).join('')||'<span class="muted">Posez une question à cet agent…</span>'}</div>`;
  html += `<div class="chat-input"><input type="text" id="askInput" placeholder="Question : signaux, performance, volatilité…" onkeydown="if(event.key==='Enter')askAgent('${esc(id)}')"><button class="btn" onclick="askAgent('${esc(id)}')">ENVOYER</button></div></div>`;
  html += '</div></div></div>';
  document.querySelectorAll('#agentDetail, #managerDetail').forEach(n => n.remove());
  const el = document.getElementById('content');
  el.insertAdjacentHTML('beforeend', html);
  const det = document.getElementById('agentDetail');
  if (det) det.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* conversation unifiée (chat écrit des onglets Agents/Rendus + voix) */
async function converse(target, q) {
  const hist = (CONVOS[target] || []).slice(-4).flatMap(m => [{ role: 'user', content: m.q }, { role: 'assistant', content: m.a }]);
  let a;
  try {
    const r = await fetch('/api/converse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target, question: q, history: hist }) });
    const resp = await r.json();
    a = resp.error ? ('Erreur : ' + resp.error) : resp.answer;
  } catch(e) { a = 'Connexion au serveur perdue.'; }
  (CONVOS[target] = CONVOS[target] || []).push({ q, a });
  return a;
}
async function askAgent(id) {
  const input = document.getElementById('askInput');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  const log = document.getElementById('chatLog');
  log.insertAdjacentHTML('beforeend', `<div class="q">❯ ${esc(q)}</div><div class="a muted">…</div>`);
  await converse(id, q);
  log.innerHTML = (CONVOS[id]||[]).map(m=>`<div class="q">❯ ${esc(m.q)}</div><div class="a">${esc(m.a)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}
async function askManager(mid) {
  const input = document.getElementById('mgrAskInput');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  const target = mid.startsWith('manager-') ? mid : 'manager-' + mid;
  const log = document.getElementById('mgrChatLog');
  log.insertAdjacentHTML('beforeend', `<div class="q">❯ ${esc(q)}</div><div class="a muted">…</div>`);
  await converse(target, q);
  log.innerHTML = (CONVOS[target]||[]).map(m=>`<div class="q">❯ ${esc(m.q)}</div><div class="a">${esc(m.a)}</div>`).join('');
  log.scrollTop = log.scrollHeight;
}

