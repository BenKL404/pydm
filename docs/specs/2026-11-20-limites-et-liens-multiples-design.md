# Limites de vitesse (globale et par téléchargement) et collage de plusieurs liens

Date : 2026-11-20. Conception validée en conversation.

## Objectif

1. Régler la vitesse comme dans IDM : une limite **globale** qu'on active, coupe et modifie d'un
   clic, et une limite **propre à chaque téléchargement**, réglable pendant qu'il tourne.
2. Ajouter **plusieurs liens d'un coup** de façon visible.

Critères de réussite : depuis la barre d'état, passer de « Vitesse illimitée » à « Limité à 1 Mo/s »
en deux clics ; limiter une ISO à 512 Ko/s pendant qu'une vidéo garde toute la vitesse, et retrouver
cette limite après redémarrage de PyDM ; coller trois liens dans le champ ouvre directement la
fenêtre d'ajout avec les trois.

## Contraintes

- `pydm/` en bibliothèque standard hors `pydm/gui/` ; Python ≥ 3.9 ; textes en français.
- Sessions existantes relues sans erreur (champ nouveau facultatif).
- Comportement inchangé quand aucune limite n'est active.

## 1. Moteur

- `scheduler.RateLimiter` inchangé ; `LIMITER` reste la limite globale.
- `Download` et `VideoDownload` gagnent `limiter` (un `RateLimiter` propre, débit 0 = illimité) et
  la propriété `limit_kbps` (lecture / écriture ; 0 = sans limite ; écrire met à jour
  `limiter.rate` immédiatement, sans relancer). Chaque bloc reçu passe par le limiteur de la tâche
  **puis** par `LIMITER` (fichiers : chaque connexion ; vidéos : crochet de progression de yt-dlp).
- Session : `entry_from_task` écrit `limit_kbps` s'il est > 0 ; `task_from_entry` le relit
  (absent ou invalide → 0).

## 2. Valeurs proposées

`LIMIT_PRESETS = (256, 512, 1024, 2048, 5120, 10240)` Ko/s, affichées « 256 Ko/s », « 512 Ko/s »,
« 1 Mo/s », « 2 Mo/s », « 5 Mo/s », « 10 Mo/s » ; plus « Autre… » (boîte de saisie en Ko/s, bornes
de `store.RANGES["speed_kbps"]`, 16 à 1 000 000).

## 3. Limite globale (barre d'état)

Le bouton `limit_btn` devient un bouton à menu (`MenuButtonPopup`) :

- **Texte** : « Vitesse illimitée » quand `speed_on` est faux ; « Limité à <valeur>/s » quand il est
  vrai (bouton enfoncé, couleur d'accent). Infobulle : « Cliquer pour activer ou couper la limite
  de vitesse totale ; flèche : choisir la valeur ».
- **Clic** : bascule `speed_on` (comme aujourd'hui).
- **Flèche** : menu des valeurs (la valeur courante cochée) et « Autre… » ; choisir une valeur
  l'enregistre (`speed_kbps`) **et** active la limite. Entrée « Sans limite » : coupe.
- La fenêtre Planification garde son réglage, cohérent avec le bouton.

## 4. Limite par téléchargement

- **Menu contextuel** du tableau : sous-menu « Limiter la vitesse » avec « Sans limite », les
  valeurs, « Autre… » ; s'applique à toute la sélection ; la valeur commune est cochée.
- **Fenêtre de progression** : ligne « Limite » avec une case « Limiter ce téléchargement à » et
  un champ numérique en Ko/s (bornes ci-dessus, défaut 1024) ; cocher ou changer la valeur
  applique aussitôt ; décocher = sans limite. Rafraîchie si la limite change ailleurs.
- **Repérage** : colonne Vitesse « <vitesse> ⏱ » quand la tâche a une limite (infobulle
  « Limité à … ») ; panneau de détails : ligne « Limite » (« sans limite » ou la valeur).

## 5. Plusieurs liens

- **Champ de lien** : quand un collage (Ctrl+V, menu, clic du milieu) amène un texte contenant au
  moins deux liens, PyDM appelle `add_urls(liens)` aussitôt et vide le champ (fenêtre d'ajout en lot
  si « Demander avant chaque téléchargement », sinon file d'attente). Un seul lien : comportement
  actuel (le lien reste dans le champ).
- **« Ajouter plusieurs liens… »** (Ctrl+Maj+V ; entrée du menu ☰) : fenêtre `MultiLinksDialog`
  avec une grande zone de texte, un compteur « N liens trouvés » (doublons ignorés, texte mêlé
  accepté, via `extract_urls`), boutons « Annuler » et « Continuer » (inactif à 0 lien) →
  `add_urls(liens)`.

## Tests

- Moteur : un fichier servi localement, limite de tâche 64 Ko/s → débit mesuré ≤ ~1,3× la limite ;
  changer `limit_kbps` en cours prend effet ; les deux limiteurs sont consultés ; session aller-retour
  avec et sans `limit_kbps`, ancienne entrée sans champ.
- Barre d'état : textes « Vitesse illimitée » / « Limité à 2 Mo/s », choix d'une valeur → réglage
  enregistré et actif, « Sans limite ».
- Menu contextuel : application à la sélection, coche de la valeur commune ; progression : case et
  champ appliquent la limite ; colonne Vitesse et panneau de détails affichent la limite.
- Liens : collage de 1, 2, 3 liens, doublons, texte mêlé, mode sans confirmation ; fenêtre
  « Ajouter plusieurs liens… » (compteur, bouton inactif à 0, Continuer).
