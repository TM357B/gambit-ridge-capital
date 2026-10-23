# Incident : allers-retours crypto du moteur live (5 au 10 octobre 2026)

## Ce qui s'est passé

Première semaine du moteur live sur le compte paper Alpaca (100 000 $ fictifs) :

| | Compte Alpaca | Paper de référence |
|---|---|---|
| 2 → 9 octobre | −0,68 % | −0,29 % |

- 95 ordres exécutés pour 186 500 $, soit 1,9 fois le compte en une semaine (norme du backtest :
  environ 15 rotations par an, 0,3 par semaine).
- 77 de ces ordres portaient sur la crypto (10 % du fonds) : vente de ~2 000 $ de LTC et achat
  de ~1 000 $ de BTC, puis l'inverse, toutes les 5 à 10 minutes. 111 600 $ échangés en crypto.
- Le 5 octobre, le paper gagnait 0,5 % pendant que le compte restait à zéro (107 000 $ échangés).
- Du 8 au 10 octobre, 996 ordres de vente BTC/ETH refusés par Alpaca (voir cause n° 2), ce qui a
  saturé le journal d'ordres de l'état (1 000 entrées) et effacé l'historique du début de semaine.

## Causes

1. **Signaux recalculés sur les prix en cours de séance.** Le moteur ajoutait le prix du moment
   comme barre du jour et recalculait la stratégie toutes les 5 minutes. Le TSMOM vaut +1 ou −1
   selon le signe du rendement sur un an : quand le prix oscille autour de son niveau d'il y a un
   an, le signal bascule à chaque passage, et la poche crypto (vol cible commune) se réajuste en
   entier. Sur clôtures quotidiennes, ce signal change au plus une fois par jour. La campagne n° 4
   avait validé le rebalancement quotidien, pas le recalcul des signaux en séance.
2. **Arrondi au-dessus de la quantité détenue.** Vente de 0,004575 BTC pour 0,004574925 détenus :
   refus « solde insuffisant » (HTTP 403), représenté toutes les 5 minutes. Le client traduisait
   tout 403 en « clés refusées », ce qui masquait la vraie cause.
3. **Aucune surveillance.** Le suivi compte / paper était alimenté par la réplication quotidienne,
   désactivée quand le moteur live est actif. Personne n'était prévenu.

## Correctifs (10 octobre 2026)

- Les cibles sont décidées une fois par séance sur les clôtures quotidiennes, comme dans le
  backtest (`live/engine.py`, `daily_targets`). Les prix en direct servent à la valorisation, au
  risque et au rééquilibrage de la dérive.
- Solde complet par « fermer la position », quantités arrondies vers le bas, poussières ignorées.
- Garde-fous : 3 ordres par actif et 60 % de rotation par jour ; une heure d'attente après un refus.
- Message d'erreur 403 fidèle à Alpaca ; journal permanent des ordres (`live_orders.jsonl`).
- Surveillance toutes les 10 minutes avec alertes iPhone (`ops/watchdog.py`) : moteur figé,
  service arrêté, rotation anormale, décrochage par rapport au paper, ordres refusés.
- Ligne quotidienne compte / paper / activité dans l'état du moteur, affichée dans le terminal.

## À retenir

- Un changement d'exécution est un changement de stratégie : il se valide comme un signal.
- Tout moteur qui passe des ordres doit avoir un plafond d'activité et une alerte d'écart avec
  sa référence dès le premier jour.
- Pour juger le live contre le backtest, ne compter qu'à partir du 12 octobre 2026.
