# Téléchargement HLS natif (progression par segment et reprise)

Date : 2026-11-20. Spécification à valider ; rien n'est implémenté.

## Objectif

yt-dlp télécharge déjà les fragments en parallèle (`concurrent_fragment_downloads` = `parts`) et
exige désormais tous les fragments. Ce qu'il n'expose pas : la progression segment par segment, le
`RateLimiter` de PyDM, la politique de concurrence par domaine (`netpolicy`) et une reprise `.pydm`
sur un flux HLS. Un téléchargeur natif n'a de sens que pour ça.

Critère de réussite : un m3u8 de plusieurs centaines de segments affiche une progression exacte,
se met en pause et reprend là où il s'était arrêté, en respectant la limite de vitesse et le
plafond de connexions de l'hôte.

## Contraintes

- `pydm/` en bibliothèque standard : **pas d'AES** → le déchiffrement AES-128 est délégué.
- ffmpeg est déjà empaqueté (AppImage, installeur Windows) ; `shutil.which` sinon.
- Les en-têtes (UA, Referer, Cookie) doivent accompagner **la clé** comme les segments.
- Flux chiffrés en `SAMPLE-AES` / `SAMPLE-AES-CTR` : ce sont des DRM, refus explicite, message
  existant « contenu protégé par DRM ».

## Conception

`pydm/hls.py` :

- `parse(text, base)` → `(variantes, segments)`. Variantes non vides = playlist maître.
  Pièges à traiter, chacun source de fichier corrompu silencieux :
  - **IV implicite** : sans attribut `IV`, l'IV est le numéro de séquence du segment sur 128 bits
    gros-boutiste (RFC 8216 §5.2), d'où le suivi de `#EXT-X-MEDIA-SEQUENCE`. Un IV nul corrompt
    les 16 premiers octets, ce que ffmpeg avale avec un simple avertissement.
  - `#EXT-X-BYTERANGE` : `Range` sur une URL partagée ; sans `@début`, l'offset est la fin du
    segment précédent de la même URL.
  - `#EXT-X-MAP` : segment d'initialisation fMP4, à concaténer avant tout le reste.
  - `#EXT-X-KEY` qui change en cours de playlist, et clé mise en cache par URI.
- `load(url, headers, height=None)` : résolution de la playlist maître vers la variante choisie
  (récursive : une variante peut pointer une autre maître).
- Téléchargement : un segment par connexion, `netpolicy.policy_for` pour le plafond,
  `_throttle` pour la vitesse, état `.pydm` étendu (liste des segments obtenus).
- Déchiffrement et fusion : **ffmpeg fait tout**. On écrit une playlist locale pointant les
  fichiers et la clé locale, puis
  `ffmpeg -allowed_extensions ALL -protocol_whitelist file,crypto,data -i local.m3u8 -c copy
  -bsf:a aac_adtstoasc`. Les deux premières options sont obligatoires, sinon ffmpeg refuse de lire
  une playlist locale référençant une clé.
- Repli si ffmpeg est absent : `VideoDownload` (yt-dlp), comportement actuel.
- Vérification finale : durée `ffprobe` comparée à la somme des `#EXTINF` ; un écart de plus de
  quelques pourcents signale des segments manquants, et doit produire une erreur, pas un succès.

## Tests

- `parse` : playlist maître, variante simple, `EXT-X-KEY` avec et sans `IV`, changement de clé en
  cours, `EXT-X-BYTERANGE` avec et sans `@début`, `EXT-X-MAP`, `SAMPLE-AES` → refus,
  `#EXT-X-ENDLIST` absent → flux live.
- IV implicite : vecteur de test avec séquence de départ non nulle.
- Faux serveur : segments servis avec vérification du `Referer` et du `Cookie`, clé servie sur une
  autre origine, un segment en 403 → erreur, pas de fichier troué.
- Pause/reprise au milieu des segments.

## Hors périmètre

- Flux **live** (`#EXT-X-ENDLIST` absent) : réinterrogation toutes `TARGETDURATION/2`, file de
  segments nouveaux — assez différent pour mériter son propre chemin de code.
- DASH (`.mpd`), qui reste à yt-dlp.
- Tout contournement de DRM.
