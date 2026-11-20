# Cookies du navigateur pour les téléchargements directs

Date : 2026-11-20. Spécification à valider ; rien n'est implémenté.

## Objectif

Aujourd'hui les cookies ne servent qu'aux vidéos (`ytdlp_attempts`, via `cookiesfrombrowser` ou un
fichier Netscape temporaire). Un fichier direct n'a que l'en-tête `Cookie` capturé par l'extension
**au moment de l'ajout** : une tâche lancée par la file planifiée des heures plus tard part avec
une session périmée.

Critère de réussite : un fichier protégé par session, ajouté puis démarré après rotation du
cookie, aboutit sans intervention ; le choix « Cookies » des préférences s'applique aussi aux
fichiers.

## Contraintes

- `pydm/` en bibliothèque standard : **aucun AES dans la stdlib**, donc Chromium est hors de
  portée sans yt-dlp (v10 : clé PBKDF2 « peanuts » ; v11 : Secret Service ; Windows : DPAPI puis
  chiffrement lié à l'application depuis Chrome 127).
- Ce sont des identifiants de session : en mémoire, fichiers `0600` (comme `_cookie_file`), jamais
  dans un log, un message d'erreur ou un rapport.
- yt-dlp reste importé paresseusement : sans lui, PyDM garde le comportement actuel.

## Conception

`pydm/cookies.py` :

- `jar_for(browser, profile=None)` → `http.cookiejar.CookieJar`, en cache par (navigateur,
  profil), délégué à `yt_dlp.cookies.extract_cookies_from_browser` avec un logger muet.
  API interne de yt-dlp : l'appel est enveloppé dans un `try/except` qui retombe sur l'en-tête
  `Cookie` de l'extension si la signature change.
- `cookie_header(url, browser, profile=None)` : construit l'en-tête via
  `jar.add_cookie_header(urllib.request.Request(url))` — domaine, chemin, `Secure` et expiration
  respectés, contrairement à la concaténation faite côté extension et à `_cookie_file`, qui écrit
  `expiry=0` et `path=/` pour tout le monde.
- `invalidate(browser=None, profile=None)` : relecture forcée, appelée une fois par tâche après un
  refus de rythme au plancher (`DomainPolicy.floor_hit`).
- Lecture Firefox en stdlib (`cookies_ff.py`, optionnelle) : `profiles.ini` (`Install*/Default`
  avant `Profile*/Default=1`), chemins Snap et Flatpak, copie de `cookies.sqlite` **avec ses `-wal`
  et `-shm`** avant lecture (base verrouillée quand Firefox tourne), cookies expirés écartés.
- `Download` reçoit `browser` comme `VideoDownload`, et pose l'en-tête `Cookie` au démarrage de la
  tâche, pas à son ajout.

## Tests

- `cookie_header` : domaine et sous-domaine, chemin, `Secure` sur http vs https, cookie expiré
  écarté, hôte sans cookie → en-tête vide.
- `cookies_ff` : `profiles.ini` des trois formes, base avec WAL non fusionné, droits du fichier
  copié, nettoyage du dossier temporaire même en cas d'erreur.
- `jar_for` : yt-dlp absent et yt-dlp dont l'API a changé → repli sur l'en-tête de l'extension.
- Aucun test ne touche le vrai profil de l'utilisateur : `HOME` est redirigé.

## Hors périmètre

- Déchiffrement Chromium écrit à la main.
- Rafraîchissement demandé au navigateur : voir `2026-11-20-ipc-refresh-design.md`.
