# Port natif persistant : rafraîchir un lien ou une session depuis le navigateur

Date : 2026-11-20. Implémenté (branche `feat/ipc-refresh`) ; cette page reste la référence
du protocole.

## Objectif

PyDM ne peut pas renouveler seul une session ni une URL signée : seul le navigateur a l'état
vivant (cookies à jour, page capable de reconstruire le lien en JavaScript). Aujourd'hui
l'extension utilise `runtime.sendNativeMessage` — un aller-retour unique à l'initiative de
l'extension — donc l'hôte natif ne peut rien demander.

Critère de réussite : un lien signé expiré pendant l'attente en file est rafraîchi sans que
l'utilisateur recharge la page lui-même ; si le navigateur est fermé, le téléchargement échoue
avec le message actuel, sans attente perceptible.

## Contraintes

- `pydm_host.py` reste autonome (il ne doit pas importer `pydm`) et duplique déjà le transport de
  `pydm/ipc.py` : les deux évoluent ensemble.
- Linux : socket Unix, une ligne JSON par sens. Windows : tube nommé `multiprocessing.connection`
  avec authentification mutuelle. Le protocole doit être identique sur les deux.
- Les en-têtes reçus sont des identifiants de session : jamais journalisés.
- Une demande non satisfaite ne doit jamais bloquer `MainWindow.tick()` (500 ms).

## Protocole

Hôte → extension (par le port) :

```json
{"id": "7f3c…", "action": "refresh", "url": "https://…", "referer": "https://…"}
```

Extension → hôte :

```json
{"id": "7f3c…", "headers": {"User-Agent": "…", "Referer": "…", "Cookie": "…"}}
{"id": "7f3c…", "error": "unsupported"}
```

- `id` : identifiant opaque généré par PyDM, renvoyé tel quel ; toute réponse dont l'`id` est
  inconnu est ignorée.
- `action` : `refresh` seulement dans cette version. Un `action` inconnu reçoit
  `{"id": …, "error": "unsupported"}`.
- `error` : `unsupported` (action inconnue), `bad-url` (lien non http(s)), sinon le message de
  l'erreur rencontrée. Pas de `no-tab` : les cookies viennent du magasin du navigateur, aucun
  onglet n'est nécessaire.
- Délai : 5 s côté PyDM, puis échec de la demande (pas de la tâche, qui applique sa règle de
  relance).

## Conception

- `extension/background.js` : `hostPort()` ouvre `runtime.connectNative(HOST)` et le garde ;
  `onDisconnect` remet la variable à zéro (réouverture paresseuse) ; `onMessage` répond aux
  demandes `refresh` avec `headersFor(url, referer)`. Les envois ponctuels existants ne changent
  pas.
- `pydm_host.py` : relaie dans les deux sens sans interpréter, en conservant la correspondance
  `id` → connexion.
- `pydm/ipc.py` : `request(action, **payload)` côté PyDM, routage des réponses par `id`, table des
  demandes en attente purgée par délai.
- `engine.Download` : une seule demande de rafraîchissement par tâche
  (`self._refreshed = True`), déclenchée quand `DomainPolicy.floor_hit` est vrai et qu'aucun octet
  n'a été reçu, ou quand `signed.freshness(url)` vaut `expired`. Les en-têtes reçus remplacent
  `self.headers` et le lien éventuellement renvoyé remplace `self.url` **si l'état `.pydm` reste
  valide** (même taille, mêmes segments) ; sinon le téléchargement redémarre à zéro.
- Garde-fou : sans ce compteur, un lien mort transforme PyDM en boucle de requêtes.

## Tests

- `ipc` : réponse hors délai, `id` inconnu, deux demandes simultanées, port fermé en cours de
  demande.
- Hôte natif : relais dans les deux sens, extension absente, message tronqué.
- `Download` : une seule demande par tâche ; en-têtes remplacés ; nouveau lien accepté si l'état
  reste valide, rejeté sinon.
- Extension : `tests/test_extension.py` vérifie la présence du port et de la réponse `no-tab`.
- Windows : le tube nommé supporte le même échange (couvert par la CI).

## Hors périmètre

- Demander au navigateur de rouvrir ou recharger une page.
- Toute autre `action` que `refresh`.
