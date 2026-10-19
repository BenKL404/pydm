# Nouvelle interface PyDM (Qt 6) : socle et fenêtre principale

Date : 2026-10-19 · Étape 1 sur 4 de la modernisation de l'interface.

| Étape | Contenu |
|---|---|
| **1 (ce document)** | Découpage en paquet, installation par venv, fenêtre principale Qt, confort, barre système, notifications, réglages persistants |
| 2 | Ordonnanceur : moteur selon [2026-10-19-ordonnanceur-design.md](2026-10-19-ordonnanceur-design.md), interface réécrite pour Qt |
| 3 | Barre latérale (filtres par état et par type), tri, rangement automatique par catégorie |
| 4 | Dialogue d'ajout (infos avant lancement, maintenant/plus tard, ajout en lot), fenêtre de progression, carte des connexions, courbe de vitesse |

## Objectif

Donner à PyDM la finition d'une application actuelle en gardant l'esprit d'IDM : un
tableau dense, lisible d'un coup d'œil, avec une identité visuelle propre (logo, icônes
dessinées pour PyDM), un thème clair et sombre, et le confort attendu aujourd'hui
(clic droit, raccourcis, glisser-déposer, barre système, notifications).

Critère de réussite : sur Pop!_OS 24.04 (COSMIC, Wayland), `./install.sh` puis `pydm`
ouvre la nouvelle fenêtre ; tout ce que fait l'interface Tkinter actuelle reste possible ;
fermer la fenêtre laisse PyDM dans la barre système ; l'extension du navigateur
fonctionne sans changement de comportement.

## Contraintes et décisions

- **Qt 6 via PySide6** pour l'interface uniquement. Le moteur, la ligne de commande, l'IPC,
  les réglages et `pydm_host.py` restent en bibliothèque standard (yt-dlp optionnel).
- **Tkinter est supprimé.** Pas d'interface de repli.
- Python 3.9 minimum. Textes de l'interface en français ; identifiants du code en anglais.
- Comportement du moteur inchangé à cette étape (pas de file d'attente : chaque ajout démarre
  immédiatement, comme aujourd'hui).

## Hors périmètre (étapes suivantes)

File d'attente, limite de vitesse, planification (étape 2) ; barre latérale, rangement par
catégorie (étape 3) ; dialogue d'ajout, fenêtre de progression, carte des connexions,
courbe détaillée (étape 4) ; traduction de l'interface.

## 1. Architecture

`pydm.py` devient le paquet `pydm/` :

| Module | Contenu | Dépendances |
|---|---|---|
| `pydm/__init__.py` | `__version__` | — |
| `pydm/__main__.py` | `python -m pydm` → `cli.main()` | — |
| `pydm/util.py` | `human`, `human_time`, `unique_path` | stdlib |
| `pydm/engine.py` | `probe`, `_Task`, `Download`, `_Paused`, `VideoDownload`, `have_ytdlp`, `looks_like_video`, `make_download`, `QUALITIES`, `BROWSERS`, `VIDEO_HOSTS`, constantes du moteur | stdlib, yt-dlp optionnel |
| `pydm/ipc.py` | `CONFIG_DIR`, `SOCKET_PATH`, `start_ipc`, `ipc_send` | stdlib |
| `pydm/store.py` | réglages (`settings.json`) et session (`session.json`) | stdlib |
| `pydm/filetypes.py` | `category(name) -> "video" \| "music" \| "document" \| "archive" \| "program" \| "other"` d'après l'extension (utilisé pour les icônes ; servira à l'étape 3) | stdlib |
| `pydm/cli.py` | `argparse`, `run_cli`, `main` | stdlib ; importe `pydm.gui` seulement pour l'interface |
| `pydm/gui/app.py` | `run(settings, default_dir, parts)` : `QApplication`, instance unique, IPC, barre système, notifications | PySide6 |
| `pydm/gui/window.py` | `MainWindow` : barre d'en-tête, tableau, panneau de détail, barre d'état, actions | PySide6 |
| `pydm/gui/model.py` | `DownloadModel(QAbstractTableModel)` + `DownloadFilter(QSortFilterProxyModel)` | PySide6 |
| `pydm/gui/delegates.py` | rendu de la barre de progression et du statut | PySide6 |
| `pydm/gui/theme.py` | palettes clair/sombre, feuille de style, chargement et recoloration des icônes | PySide6 |
| `pydm/gui/prefs.py` | `PreferencesDialog` | PySide6 |
| `pydm/gui/links.py` | `extract_urls(text_or_mime) -> list[str]` (glisser-déposer, Ctrl+V) | stdlib (testable sans Qt) |
| `pydm/gui/icons/` | icônes SVG (§ 3) et logo | — |

Le code est **déplacé** depuis `pydm.py` sans changement de comportement, sauf ce que
décrit ce document. `pydm.py` à la racine est supprimé.

### Threads

Inchangé dans le principe : les tâches tournent dans leurs threads et mettent à jour leurs
attributs (`status`, `done`, `size`, `speed`, `error`, `name`). Un `QTimer` de 500 ms, dans
le thread principal :

1. vide la `queue.Queue` alimentée par le thread IPC ;
2. rafraîchit le modèle (`dataChanged` sur les colonnes variables des lignes concernées) ;
3. détecte les transitions (→ « Terminé », → erreur) pour les notifications ;
4. enregistre la session si elle a changé.

Aucun objet Qt n'est créé ni modifié hors du thread principal. La détection fichier/vidéo
(`make_download`) reste dans un thread ; son résultat passe par la même file.

### Instance unique

`cli.main()` sans URL : `ipc_send({"action": "show"})` ; si une instance répond, on s'arrête.
Sinon, si PySide6 manque : message « Interface indisponible : PySide6 n'est pas installé.
Relancez ./install.sh » sur stderr, code de sortie 1. Sinon `gui.app.run(...)`.

## 2. Installation

`install.sh` :

1. Vérifie `python3 -m venv` ; sinon message (`sudo apt install python3-venv`) et arrêt.
2. Crée ou réutilise `~/.local/share/pydm/venv`, puis `venv/bin/pip install -U PySide6 yt-dlp`.
   En cas d'échec de pip : message clair et arrêt (code non nul).
3. Copie `pydm/` (remplacé entièrement) et `pydm_host.py` dans `~/.local/share/pydm/`.
4. Écrit le lanceur `~/.local/bin/pydm` :
   `#!/bin/sh` + `exec "$HOME/.local/share/pydm/venv/bin/python" -m pydm "$@"` avec
   `PYTHONPATH` pointant sur `~/.local/share/pydm`.
5. Installe le logo dans `~/.local/share/icons/hicolor/<taille>/apps/pydm.png` (16, 32, 48,
   64, 128, 256, 512) et `scalable/apps/pydm.svg` ; `pydm.desktop` utilise `Icon=pydm`.
6. Écrit les manifestes de messagerie native comme aujourd'hui.

`pydm_host.py` lance l'interface avec le lanceur `~/.local/bin/pydm` (chemin calculé, pas
de dépendance au `PATH`) au lieu de `sys.executable pydm.py`. Il reste exécuté par le Python
système. S'il ne trouve pas le lanceur : réponse `{"ok": false, "error": "PyDM n'est pas
installé (lancez install.sh)"}`.

L'ancienne installation (`~/.local/share/pydm/pydm.py`) est supprimée par `install.sh`.

Développement : `python3 -m venv .venv && .venv/bin/pip install PySide6`, puis
`.venv/bin/python -m pydm`. `.gitignore` ajoute `.venv/`.

## 3. Identité visuelle

- **Logo** : [assets/pydm-logo.svg](assets/pydm-logo.svg). Fond nuit (#0f172a → #1e293b),
  anneau de 8 segments (5 cyan #22d3ee, 3 ardoise #334155), flèche blanche. Utilisé pour
  l'icône d'application, la fenêtre, la barre système, « À propos » et l'extension
  (`extension/icons/icon{16,32,48,128}.png` régénérés, zip reconstruit).
  Les PNG sont générés à partir du SVG par un script de développement
  `tools/render_icons.py` (utilise `QSvgRenderer` de PySide6) ; les PNG produits sont commités.
- **Couleur d'accent** : cyan (#22d3ee en sombre, #0891b2 en clair) : barres de progression
  actives, sélection, bouton principal, focus.
- **Icônes** : style plein monochrome (glyphe plein, pictogramme découpé), dessinées pour
  PyDM, planche de référence [assets/pydm-icons.svg](assets/pydm-icons.svg). Un fichier SVG
  par icône dans `pydm/gui/icons/` (grille 24 × 24) : `add`, `resume`, `pause`, `force`,
  `remove`, `folder`, `search`, `schedule`, `menu`, `type-video`, `type-music`,
  `type-document`, `type-archive`, `type-program`, `type-other`. Les SVG utilisent
  `currentColor` pour le glyphe ; `theme.py` les recolore au chargement (texte du thème pour
  les actions, teinte fixe par type : vidéo #a78bfa, musique #f472b6, document #60a5fa,
  archive #fbbf24, programme #34d399, autre #94a3b8) et produit des `QIcon` nets en HiDPI.
  Le pictogramme découpé est transparent (pas une couleur de fond), pour s'afficher sur
  n'importe quel fond.
- **Thème** : style Qt « Fusion » + deux `QPalette` (clair, sombre) + une feuille de style
  courte (rayons 6 px, espacements, champ de lien, barre de progression). Réglage
  `theme` : `system` (défaut, suit `QStyleHints.colorScheme()` et ses changements),
  `light`, `dark`.
- Police : celle du système ; chiffres tabulaires pour les colonnes numériques si la police
  les propose.

## 4. Fenêtre principale

Disposition retenue (C), de haut en bas :

### 4.1 Barre d'en-tête

`[lien : Coller un lien ou glisser-déposer…] [Qualité ▾] [Cookies ▾] [Télécharger] | resume pause remove folder | search menu`
(noms des icônes du § 3)

- Champ de lien : Entrée = Télécharger. Accepte plusieurs liens collés (un par ligne) :
  chacun est ajouté.
- **Qualité** (`QComboBox` compact, icône vidéo) : valeurs de `QUALITIES` ; info-bulle
  « Qualité des vidéos de streaming ». **Cookies** (icône navigateur) : valeurs de
  `BROWSERS` ; info-bulle « Utiliser les cookies de ce navigateur ». Valeurs appliquées aux
  ajouts suivants (manuels, presse-papiers, extension) et enregistrées dans les réglages.
- Boutons-icônes avec info-bulles et raccourcis : Reprendre, Pause, Retirer, Ouvrir le
  dossier, Rechercher, Menu (Préférences, À propos, Quitter). Reprendre/Pause/Retirer sont
  grisés sans sélection.
- Recherche : un champ apparaît sous la barre (Ctrl+F), filtre en direct sur nom et URL,
  Échap le ferme et vide le filtre.

### 4.2 Tableau

`QTableView` + `DownloadModel` + `DownloadFilter`.

| Colonne | Contenu |
|---|---|
| Fichier | icône de type (`filetypes.category`) + nom (ou URL tant qu'il est inconnu) ; info-bulle = URL |
| Taille | `human(size)` ou « ? » |
| Progression | barre dessinée par délégué (accent ; vert #22c55e si terminé ; ambre #eab308 si en pause ; rouge #ef4444 si erreur) + pourcentage, ou octets reçus si la taille est inconnue |
| Vitesse | `human(speed)/s` si en cours, vide sinon |
| Restant | `human_time` si calculable, vide sinon |
| Statut | `status` ; erreurs en rouge |
| Ajouté le | date et heure d'ajout (nouvel attribut `added`, enregistré dans la session) |

- Tri par clic sur l'en-tête (valeurs brutes : octets, ratio, secondes, date). Ordre et
  largeurs des colonnes enregistrés (`QHeaderView.saveState`).
- Sélection multiple par lignes ; lignes compactes (hauteur ≈ 1,8 × la hauteur de police) ;
  couleurs de lignes alternées discrètes.
- Liste vide : texte centré « Collez un lien ou glissez-le ici pour commencer ».

### 4.3 Panneau de détail

Sous le tableau, dans un `QSplitter` (taille enregistrée), repliable (bouton et double-clic
sur une ligne non terminée). Pour la ligne courante : URL (sélectionnable, bouton Copier),
dossier (lien qui l'ouvre), taille, reçu, connexions actives / prévues (`Download` :
segments en cours ; vidéo : « fragments »), reprise possible (oui/non), message d'erreur
complet. Sans sélection : « Aucun téléchargement sélectionné ». Réservé pour l'étape 4 : carte
des connexions.

### 4.4 Barre d'état

À gauche « N en cours · M terminés · K en erreur » (parties nulles omises). À droite :
mini-courbe (60 dernières secondes, échantillon chaque seconde, dessinée par un petit widget)
et débit total « ↓ 15,6 Mo/s ».

### 4.5 Barre latérale

Non affichée à l'étape 1. La disposition utilise un `QSplitter` horizontal dont le premier
volet sera ajouté à l'étape 3.

## 5. Confort

| Fonction | Comportement |
|---|---|
| Menu clic droit | Reprendre, Pause, Ouvrir le fichier (si terminé), Ouvrir le dossier, Copier le lien, Retirer de la liste, Supprimer le fichier… (confirmation ; supprime aussi `.part` et l'état) |
| Raccourcis | Entrée (champ) : télécharger ; Ctrl+V hors champ : ajoute les liens du presse-papiers ; Suppr : retirer ; Espace : bascule pause/reprise ; Ctrl+F : rechercher ; Ctrl+A : tout sélectionner ; Ctrl+, : Préférences ; Ctrl+Q : quitter ; Ctrl+O : ouvrir le dossier |
| Glisser-déposer | Texte ou URL déposés sur la fenêtre : `extract_urls` garde les liens `http(s)`/`ftp`, sans doublon, et les ajoute tous |
| Double-clic | Terminé : ouvre le fichier (`QDesktopServices.openUrl`) ; sinon : affiche/masque le panneau de détail |
| Presse-papiers | Comme aujourd'hui (un lien copié remplit le champ si vide), via `QClipboard.dataChanged` au lieu d'une scrutation ; réglage `clipboard` |
| Barre système | `QSystemTrayIcon` (logo) si `isSystemTrayAvailable()`. Menu : Afficher, Tout mettre en pause, Tout reprendre, Quitter. Clic : afficher/masquer la fenêtre. Info-bulle : débit total et nombre en cours |
| Fermer la fenêtre | Si barre système disponible et réglage `close_to_tray` vrai (défaut) : masque ; au premier masquage, notification « PyDM continue en arrière-plan ». Sinon : quitte |
| Quitter | Comme `on_close` actuel : enregistre la session, met tout en pause, attend 5 s max, supprime la socket |
| Notifications | Fin de téléchargement : « Téléchargement terminé » + nom ; erreur : « Échec » + nom + début du message. Via `QSystemTrayIcon.showMessage` ; clic sur la notification de fin : ouvre le dossier. Réglage `notify` |
| Démarrer avec la session | Réglage `autostart` : crée/supprime `~/.config/autostart/pydm.desktop` (`Exec=pydm --minimized`) |
| `--minimized` | Nouvelle option : démarre masqué dans la barre système (ignorée sans barre système) |

## 6. Réglages

`pydm/store.py` : `load_settings()`, `save_settings(d)` (écriture atomique : fichier
temporaire + `os.replace`, droits 0600), `load_session()`, `save_session(entries)`.

| Clé | Défaut |
|---|---|
| `folder` | `~/Téléchargements` s'il existe, sinon `~/Downloads` |
| `parts` | 8 (1–32) |
| `quality` | `"Meilleure"` |
| `browser` | `"Aucun"` |
| `clipboard` | `true` |
| `theme` | `"system"` (`"light"`, `"dark"`) |
| `notify` | `true` |
| `close_to_tray` | `true` |
| `autostart` | `false` |
| `window` | `{}` (géométrie, état du tableau et des volets, encodés en base64) |

Toute clé absente ou de type invalide prend sa valeur par défaut. Les options `-o` et `-n`
passées explicitement l'emportent sur `folder` et `parts`. L'ordonnanceur (étape 2) ajoutera
ses clés à ce même fichier.

**Préférences** (`PreferencesDialog`, Ctrl+,) : dossier par défaut (avec sélecteur),
connexions par téléchargement, thème, surveillance du presse-papiers, notifications, fermer
vers la barre système (grisé si indisponible), démarrer avec la session. OK applique
immédiatement et enregistre ; Annuler ne change rien.

**Session** : format actuel conservé, plus `added` (horodatage ISO). Entrées sans `added` :
date de chargement.

## 7. Erreurs

- PySide6 absent : § 1 (instance unique). La ligne de commande avec URL fonctionne.
- `settings.json` illisible : valeurs par défaut, le fichier est renommé `settings.json.bak`.
- `session.json` illisible : liste vide, le fichier est renommé `session.json.bak` (rien n'est
  perdu silencieusement).
- Socket IPC indisponible : l'interface fonctionne, un avertissement s'affiche dans la barre
  d'état (« Extension du navigateur indisponible »).
- Ouvrir un fichier ou dossier inexistant : message « Fichier introuvable ».
- Supprimer un fichier : confirmation listant les fichiers ; erreur d'écriture affichée.

## 8. Tests

`unittest`, dossier `tests/`, lancement `python3 -m unittest discover tests`.

Sans Qt :

- `test_engine.py` : serveur HTTP local (thread, `http.server` étendu pour gérer `Range`),
  fichier aléatoire de 3 Mo : téléchargement avec 4 connexions → contenu identique ; pause
  puis reprise (nouvel objet `Download` sur le même nom) → contenu identique ; serveur sans
  `Range` → 1 connexion, contenu identique.
- `test_store.py` : défauts sans fichier ; fichier corrompu → défauts + `.bak` ; clé de
  mauvais type ; aller-retour ; `CONFIG_DIR` redirigé vers un dossier temporaire.
- `test_filetypes.py` : catégories pour des extensions courantes, majuscules, double
  extension (`.tar.xz` → archive), sans extension → `other`.
- `test_links.py` : `extract_urls` sur texte multiligne, liste `text/uri-list`, doublons,
  schémas refusés (`javascript:`, `file:`).
- `test_cli.py` : `--help` ; sans PySide6 (import simulé en échec) → message et code 1.

Avec Qt (`QT_QPA_PLATFORM=offscreen`, ignorés si PySide6 absent) :

- `test_gui_model.py` : `DownloadModel` sur de fausses tâches : nombre de lignes, valeurs
  affichées, tri par taille et par progression, filtre de recherche (nom et URL),
  `dataChanged` émis au rafraîchissement.
- `test_gui_theme.py` : chaque icône SVG se charge en `QIcon` non nul ; recoloration.

CI : le travail Python installe PySide6 et exporte `QT_QPA_PLATFORM=offscreen` ; un travail
exécute `install.sh` avec un `HOME` temporaire et vérifie le lanceur, les manifestes et
`pydm --help`.

Vérification manuelle avant la fin de l'étape : thèmes clair et sombre, barre système et
notifications sous COSMIC, glisser-déposer depuis le navigateur, extension de bout en bout
(lien, vidéo, clic droit), reprise de session après redémarrage.

## 9. Documentation

- README.md et LISEZMOI.md : installation (venv, PySide6), nouvelles fonctions, captures
  d'écran clair et sombre (`docs/screenshots/`).
- CONTRIBUTING.md : environnement de développement, structure du paquet, tests Qt hors écran,
  régénération des icônes (`tools/render_icons.py`).
- CHANGELOG.md : entrée sous « Unreleased ».
