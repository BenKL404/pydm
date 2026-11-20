# Empreinte de requête cohérente (Sec-Fetch-*, Accept, client hints)

Date : 2026-11-20. Spécification à valider ; rien n'est implémenté.

## Objectif

Faire ressembler une requête de PyDM à une sous-ressource chargée par une page, pour les serveurs
qui vérifient autre chose que le `Referer` : `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`,
`Accept`, `Accept-Language` et les *client hints* `sec-ch-ua*`.

Critère de réussite : sur un hôte qui refuse une requête sans `Sec-Fetch-Site`, le téléchargement
aboutit ; aucun en-tête annoncé ne contredit un autre (plateforme, navigateur, origine).

## Contraintes

- `pydm/` en bibliothèque standard ; Python ≥ 3.9 ; textes en français.
- L'en-tête fourni par l'extension reste prioritaire : il vient du vrai navigateur.
- Aucune valeur inventée : `Sec-Fetch-Site` se **déduit** du `Referer` réel. Annoncer
  `same-origin` avec un `Referer` d'un autre domaine est une incohérence qu'aucun navigateur ne
  produit — c'est pire que de ne rien envoyer.

## Conception

`pydm/fingerprint.py` (existant, UA et épinglage par domaine) gagne :

- `browser_headers(url, referer=None, dest="empty", ua=None, ranged=False)` → dict.
  - `Sec-Fetch-Site` : `none` sans referer, sinon `same-origin` / `same-site` / `cross-site`
    calculé sur (schéma, hôte, port) puis sur les deux derniers labels du domaine.
  - `Sec-Fetch-Mode` : `navigate` pour `dest="document"`, `cors` pour `empty`, sinon `no-cors`.
  - `Sec-Fetch-Dest` : `empty`, `video`, `audio`, `document`, `image` selon l'usage.
  - `Accept` : table par `dest` (celles de Chrome).
  - `Referer` réduit à l'origine en cross-site (politique par défaut des navigateurs).
  - `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform` uniquement si l'UA retenu est un
    Chrome, et `sec-ch-ua-platform` **dérivé de `platform_key()`**, jamais écrit en dur.
  - `Accept-Encoding` : `identity` si `ranged`, sinon `gzip, deflate`. Attention :
    `engine` impose déjà `identity` sur toute requête de plage, après les en-têtes du navigateur.
    Cette règle reste la dernière à s'appliquer.
- Appels : `probe`, `Download._worker`, `looks_like_video`, la miniature de `analyze`.
- La version de Chrome annoncée (`fingerprint.CHROME`) devient un point de maintenance : à revoir
  à chaque version de PyDM, comme la liste `VIDEO_HOSTS`.

## Tests

- `Sec-Fetch-Site` pour les quatre cas (sans referer, même origine, même site, site tiers), port
  et schéma différents compris.
- `sec-ch-ua-platform` suit `platform.system()` simulé (Windows, Linux, Darwin) et n'apparaît pas
  avec un UA Firefox.
- `Referer` cross-site réduit à l'origine, `Referer` same-origin conservé entier.
- Faux serveur refusant toute requête sans `Sec-Fetch-Site` : téléchargement complet.
- Non-régression : `Accept-Encoding: identity` toujours présent sur une requête de plage, même si
  l'extension a transmis `gzip`.

## Hors périmètre

- Ordre des en-têtes (`urllib` normalise et réordonne) : exigerait de descendre sur `http.client`
  et de réécrire `putheader` dans l'ordre de Chrome.
- `Connection: keep-alive` : `urllib` ferme chaque connexion ; une connexion persistante par
  worker est un autre chantier (voir « limites connues » ci-dessous).
- Empreinte TLS (JA3/JA4) et ordre des trames HTTP/2 : hors d'atteinte sans dépendance externe
  type `curl_cffi`. À documenter comme limite, pas à contourner.

## Limites connues (à documenter, pas à corriger ici)

Une requête `urllib` ouvre une connexion TCP+TLS neuve et l'annonce `Connection: close` : huit
connexions par fichier plus une par reprise de segment, ce qu'aucun navigateur ne fait. Les
serveurs qui comptent les connexions le voient, quels que soient les en-têtes.
