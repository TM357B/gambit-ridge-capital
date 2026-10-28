/* Gambit Ridge Capital — terminal : 99-demarrage.js (scripts classiques, globals partagés, chargés dans l'ordre) */
if (window.innerWidth < 760) { const ci = document.getElementById('cmdInput'); if (ci) ci.placeholder = 'Commande… ex. SPY GP · HELP'; }
// lien direct vers un onglet : /?tab=risk, /?tab=paper…
// panneau de l'espace BLP : /?pane=N&cmd=… (17-pro.js)
const startParams = new URLSearchParams(location.search);
const startTab = startParams.get('tab'), startCmd = startParams.get('cmd');
if (startCmd) runCommand(startCmd);
else if (startTab && document.getElementById('tab-' + startTab)) switchTab(startTab);
else enteteEcran('terminal');
fetchState();
fetchMarket();
if (typeof GRC_PANNEAU === 'undefined' || GRC_PANNEAU === null) { refreshOps(); setInterval(refreshOps, 5 * 60 * 1000); }
