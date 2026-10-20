# Fenêtre d'ajout : informations et choix de la qualité avant de télécharger

Date : 2026-10-20 · Première moitié de l'étape 4 de
[2026-10-19-interface-qt-design.md](2026-10-19-interface-qt-design.md) (la fenêtre de
progression, la carte des connexions et la courbe détaillée restent pour plus tard).

## Objectif

Comme IDM : tout lien ajouté (extension du navigateur, champ de lien, Ctrl+V, glisser-déposer)
ouvre une fenêtre PyDM qui montre ce qui va être téléchargé et laisse choisir. Pour une vidéo,
la fenêtre propose la vraie liste des qualités disponibles avec leur taille.

Critère de réussite : sur YouTube, clic sur « ⬇ Télécharger cette vidéo » → la fenêtre PyDM
s'ouvre aussitôt, affiche après analyse « 1080p · MP4 · 412 Mo » dans un menu qui contient aussi
720p, 480p… et « Audio seul · MP3 » ; on choisit 720p ; le fichier obtenu est en 720p.

## Contraintes

- L'extension et le protocole de messagerie native ne changent pas.
- `pydm/analyze.py` : bibliothèque standard (yt-dlp importé à la demande), sans Qt.
- Textes en français ; identifiants en anglais ; Python ≥ 3.9.
- Pas d'ordonnanceur à cette étape : « Plus tard » ajoute la tâche **en pause** (elle passera
  « en file » avec l'étape 2).

## Hors périmètre

Fenêtre de progression, carte des connexions, courbe de vitesse détaillée ; choix de qualité
vidéo par vidéo dans un lot ; choix des sous-titres ; playlists entières.

## 1. Déroulement

1. `MainWindow.add_urls(urls, headers=None, filename=None, kind="auto")` :
   - si `settings["confirm_add"]` est faux : comportement actuel (inchangé) ;
   - sinon : ouvre **immédiatement** un `AddDialog` non modal pour l'ensemble des liens
     (un seul lien → présentation simple ; plusieurs → présentation en liste), affiché au premier
     plan (`show`, `raise_`, `activateWindow`) ; si la fenêtre principale est masquée, le dialogue
     s'ouvre quand même.
2. Le dialogue lance `analyze(...)` dans un thread par lien ; les résultats passent par une
   `queue.Queue` relue par un `QTimer` de 200 ms du dialogue. Aucun objet Qt hors du thread
   principal.
3. Boutons : **Télécharger** (crée les tâches et les démarre), **Plus tard** (crée les tâches en
   pause, statut « En pause »), **Annuler** (rien). Case **Ne plus demander** : met
   `confirm_add` à faux et l'enregistre.
4. Sous Wayland, si le dialogue n'a pas pu passer au premier plan (fenêtre non active 500 ms après
   l'ouverture) et que la barre système existe : notification « Choisissez la qualité dans
   PyDM », dont le clic affiche le dialogue.

Nouveau réglage `confirm_add` (bool, défaut `true`) dans `store.DEFAULTS` ; case « Demander
avant chaque téléchargement » dans Préférences.

## 2. Analyse (`pydm/analyze.py`)

```python
analyze(url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure",
        ffmpeg=None) -> dict
```

`ffmpeg` : `None` → `shutil.which("ffmpeg")` est consulté. Résultat :

| Clé | Contenu |
|---|---|
| `kind` | `"file"`, `"video"` ou `"error"` |
| `name` | nom proposé (fichier : nom de `probe` ; vidéo : titre nettoyé + extension du choix présélectionné) |
| `size` | octets ou `None` (fichier ; vidéo : taille du choix présélectionné) |
| `resumable` | bool (fichier : plages acceptées ; vidéo : `True`) |
| `site`, `title`, `duration`, `thumbnail` | vidéo : domaine, titre, secondes ou `None`, octets de l'image ou `None` |
| `choices` | vidéo : liste de choix (ci-dessous), au moins un ; fichier : `[]` |
| `selected` | index du choix présélectionné |
| `ffmpeg_missing` | vrai si des qualités sont limitées faute de ffmpeg |
| `error` | message lisible (`kind == "error"`) |
| `drm` | vrai si le contenu est protégé |

La détection fichier / vidéo est celle de `make_download` (`kind` explicite, sinon
`looks_like_video`). L'analyse vidéo appelle `extract_info(url, download=False)` avec la même
règle que le téléchargement : d'abord sans cookies, puis, en cas d'échec, avec les cookies
(navigateur choisi, sinon ceux de l'extension en fichier). Cette règle est extraite dans une
fonction partagée `ytdlp_attempts(url, headers, browser) -> iterator[dict]` (options à ajouter
pour chaque essai, avec suppression du fichier de cookies à la fin) utilisée par
`VideoDownload._run` et par `analyze`. Durée maximale : 30 s par lien (`socket_timeout`
yt-dlp 15 s ; au-delà, le dialogue affiche « Analyse trop longue »). Miniature : téléchargée
dans le même thread, 64 Ko et 5 s au plus, sinon `None`.

### Choix d'une vidéo

Un choix : `{"label": str, "format": str, "ext": str, "size": int | None, "approx": bool,
"height": int | None, "audio_only": bool}`.

À partir de `info["formats"]` :

- **Avec ffmpeg** : une entrée par hauteur distincte de flux vidéo (`vcodec != "none"`),
  de la plus haute à la plus basse. Pour chaque hauteur : le flux vidéo de meilleur `tbr`, en
  préférant à `tbr` égal à 10 % près `ext == "mp4"` / `vcodec` commençant par `avc1` ; associé
  au meilleur flux audio seul (`vcodec == "none"`), `m4a` préféré si la vidéo est `mp4`.
  `format = f"{video_id}+{audio_id}"`, `ext` = `mp4` si la vidéo est mp4, sinon `mkv`/`webm`
  selon yt-dlp. Libellé : `"1080p · MP4"`.
  Puis **« Audio seul · MP3 »** : `format = "ba/b"`, conversion MP3 (comme la qualité
  « Audio MP3 » actuelle), `ext = "mp3"`, `audio_only = True`.
- **Sans ffmpeg** : seulement les formats contenant vidéo et audio (`vcodec` et `acodec` ≠
  `"none"`), un par hauteur, puis **« Audio seul · <M4A|WEBM> »** (`format` = id du meilleur
  audio, sans conversion). `ffmpeg_missing = True` si des hauteurs supérieures existaient en
  flux séparés.
- **Aucun format exploitable** (liste vide, flux HLS unique…) : un seul choix
  **« Meilleure disponible »** (`format = "bv*+ba/b"` ou `"b"` sans ffmpeg).
- Taille : `filesize`, sinon `filesize_approx` (`approx = True`), sinon `tbr × duration / 8`
  (`approx = True`), sinon `None` ; pour un couple vidéo + audio, la somme (approx si l'une l'est,
  `None` si l'une manque). Affichage : `"1080p · MP4 · 412 Mo"`, `"720p · MP4 · ≈ 198 Mo"`,
  `"1080p · MP4"` sans taille.

Présélection selon `default_quality` (menu Qualité de la fenêtre principale) : « Meilleure » →
première entrée ; « 1080p » / « 720p » / « 480p » → plus haute hauteur ≤ valeur (sinon la plus
basse) ; « Audio MP3 » → l'entrée audio.

## 3. Moteur

`VideoDownload(url, folder, parts=8, name=None, quality="Meilleure", browser="Aucun",
headers=None, fmt=None, stem=None)` :

- `fmt` (sélecteur yt-dlp) remplace la correspondance `QUALITIES[quality]` s'il est fourni ;
  si `fmt` concerne l'audio MP3 (`quality == "Audio MP3"`), le post-traitement MP3 est conservé.
- `stem` (nom choisi, sans extension) : `outtmpl = <dossier>/<stem>.%(ext)s` au lieu du modèle
  « titre [id] ». Caractères `/` remplacés par `_`.
- Session : `entry_from_task` enregistre `fmt` et `stem` ; `task_from_entry` les relit
  (absents dans les anciennes entrées → `None`).

`Download` : le nom choisi passe par `name_hint` (existant). Le dossier choisi est créé au moment
du clic ; s'il ne peut pas l'être, le dialogue affiche l'erreur et reste ouvert.

## 4. Fenêtre `AddDialog` (`pydm/gui/adddialog.py`)

```python
AddDialog(settings, urls, headers=None, filename=None, kind="auto", parent=None,
          analyzer=analyze)
```

Signal `accepted_tasks(list, bool)` : liste de `dict` `{"url", "kind", "folder", "name",
"fmt", "quality", "headers"}` et `start` (vrai pour Télécharger, faux pour Plus tard).
`MainWindow` crée les tâches (`factory` existant, étendu des paramètres `fmt`/`stem`/nom) et les
démarre ou les laisse en pause.

**Un lien** (maquette retenue « compacte ») : titre « Ajouter une vidéo » ou « Ajouter un
téléchargement » ; en tête, vignette 128 × 72 (vidéo ; neutre avec l'icône vidéo si pas de
miniature) ou icône de type (fichier), titre, ligne d'informations (site · durée, ou
site · taille · type · « reprise possible » / « sans reprise » · N connexions) ; **Qualité**
(`QComboBox` des libellés, vidéo seulement) ; **Nom** (`QLineEdit`, extension mise à jour
quand la qualité change tant que l'utilisateur n'a pas modifié le nom) ; **Dossier**
(`QLineEdit` + bouton icône dossier) ; ligne grisée « Installez ffmpeg pour les meilleures
qualités » si `ffmpeg_missing`. Pendant l'analyse : « Analyse… » à la place des informations,
Qualité désactivée, Télécharger actif (télécharge avec les réglages par défaut).

**Plusieurs liens** : titre « Ajouter N téléchargements » ; tableau (case, icône de type,
nom, taille ou « Analyse… ») ; menu **Vidéos** (valeurs de `QUALITIES`, défaut = menu Qualité
de la fenêtre principale) appliqué à toutes les vidéos du lot ; **Dossier** commun ; bouton
« Télécharger N » où N = lignes cochées (désactivé à 0).

**Erreurs** : analyse en erreur → message dans la ligne d'informations (lot : ligne décochée,
message en info-bulle) et bouton « Télécharger quand même » (lance comme aujourd'hui) ;
DRM → « Contenu protégé par DRM », Télécharger désactivé ; résultat d'analyse arrivant après la
fermeture du dialogue → ignoré.

## 5. Tests

`unittest`, hors écran.

- `test_analyze.py` : faux `yt_dlp` renvoyant des `info` préparées :
  - YouTube type (flux vidéo 1080/720/480 en mp4 et webm, audio m4a/webm) avec ffmpeg → libellés
    et ordre `["1080p · MP4", "720p · MP4", "480p · MP4", "Audio seul · MP3"]`, `format`
    `"<id>+<id>"` avec l'audio m4a, tailles additionnées, `approx` correct ;
  - même info sans ffmpeg → uniquement les formats complets + « Audio seul · M4A »,
    `ffmpeg_missing` vrai ;
  - aucun format → un choix « Meilleure disponible » ;
  - présélection pour « Meilleure », « 720p », « 1080p » sans 1080 disponible, « Audio MP3 » ;
  - cookies : premier essai sans, second avec (réutilise les règles de `test_video.py`) ;
  - erreur yt-dlp → `kind == "error"` et message ; « DRM » → `drm` vrai.
- `test_analyze.py`, fichier : serveur HTTP de test → nom, taille, `resumable` ; serveur absent →
  `kind == "error"`.
- `test_video.py` : `fmt` transmis comme `format` ; `stem` → `outtmpl` ; aller-retour session de
  `fmt`/`stem`.
- `test_gui_adddialog.py` (analyseur factice) : remplissage après analyse ; Télécharger / Plus
  tard / Annuler → signal et contenu ; changement de qualité → extension du nom ; nom modifié
  conservé ; « Ne plus demander » → `confirm_add` faux enregistré ; lot : décocher → « Télécharger
  2 » ; erreur → « Télécharger quand même » ; résultat après fermeture ignoré.
- `test_gui_window.py` : `confirm_add` faux → comportement actuel (tests existants) ;
  `confirm_add` vrai → `add_urls` ouvre un dialogue et ne crée aucune tâche avant validation ;
  Plus tard → tâche « En pause » non démarrée.

Vérification manuelle par l'utilisateur : clic depuis Firefox sur YouTube, dialogue au premier
plan (ou notification), fichier final en 720p.

## 6. Documentation

LISEZMOI.md / README.md (fenêtre d'ajout, « Ne plus demander », réglage dans Préférences),
CHANGELOG.md (« Unreleased »).
