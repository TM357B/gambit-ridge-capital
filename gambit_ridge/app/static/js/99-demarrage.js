/* Gambit Ridge Capital — terminal : 99-demarrage.js (scripts classiques, globals partagés, chargés dans l'ordre) */
if (window.innerWidth < 760) { const ci = document.getElementById('cmdInput'); if (ci) ci.placeholder = 'Commande… ex. SPY GP · HELP'; }
// lien direct vers un onglet : /?tab=risk, /?tab=paper…
const startTab = new URLSearchParams(location.search).get('tab');
if (startTab && document.getElementById('tab-' + startTab)) switchTab(startTab);
fetchState();
fetchMarket();
refreshOps(); setInterval(refreshOps, 5 * 60 * 1000);
