# Installation en un clic : AppImage

Date : 2026-10-21. Premier des deux sous-projets « installation sans terminal » ; le second (version
Windows) réutilisera la même base PyInstaller.

## Objectif

Aujourd'hui, installer PyDM demande un terminal (`git clone`, `./install.sh`, téléchargement de
PySide6 et yt-dlp). Critère de réussite : sur une distribution Linux récente sans Python de
développement, télécharger `PyDM-1.3.0-x86_64.AppImage` depuis la page des versions GitHub, le
rendre exécutable, l'ouvrir → PyDM démarre, apparaît dans le menu des applications, et l'extension
(installée séparément) lui envoie les téléchargements, y compris quand PyDM est fermé.

## Contraintes

- `pydm/` reste en bibliothèque standard hors `pydm/gui/` ; `pydm_host.py` reste autonome.
- `install.sh` continue de marcher (développeurs) ; les deux modes d'installation coexistent.
- Construction reproductible dans la CI GitHub, sur Ubuntu 22.04 (glibc 2.35 : distributions de
  2022 et plus récentes).
- La configuration PyInstaller doit pouvoir servir plus tard à Windows (aucun chemin Linux codé
  en dur dans `packaging/pydm.spec` hors des sections propres à la plateforme).
- Textes visibles en français ; aucune mention d'outil d'IA.

## 1. Programme figé (PyInstaller)

- `packaging/pydm.spec` : mode « dossier » (onedir), un exécutable `pydm` construit à partir de
  `pydm/__main__.py`. Contenu : le paquet `pydm` (icônes SVG comprises), `pydm_host.py`, PySide6
  limité aux modules utilisés (QtCore, QtGui, QtWidgets, QtSvg, QtNetwork si utilisé ; plugins
  plate-forme `xcb` et `wayland`, formats d'image), yt-dlp, et un **ffmpeg statique** (binaires
  `ffmpeg` et `ffprobe`, licence GPL compatible) placé à côté de l'exécutable.
- ffmpeg : au démarrage, si PyDM est figé (`sys.frozen`), le dossier de l'exécutable est ajouté en
  tête de `PATH`, de sorte que `shutil.which("ffmpeg")` et yt-dlp le trouvent sans autre
  changement.
- Nouveau mode `pydm --native-host [arguments du navigateur…]` : traité dans `pydm/cli.py` avant
  `argparse` (le navigateur ajoute ses propres arguments : chemin du manifeste et identifiant pour
  Firefox, origine et `--parent-window=…` pour Chrome) ; exécute `pydm_host.main()`.

## 2. Hôte natif

`pydm_host.py` :

- Commande de lancement de PyDM quand il n'est pas ouvert : `[$APPIMAGE, "--minimized"]` si la
  variable `APPIMAGE` est définie (hôte exécuté depuis l'AppImage), sinon `~/.local/bin/pydm` comme
  aujourd'hui. Message d'erreur sans mention d'`install.sh` dans le premier cas.
- `ping` : `ytdlp` vaut vrai si PyDM est figé (yt-dlp est inclus), sinon test actuel du venv.
- Comportement `prefetch` inchangé (jamais de lancement).

## 3. Intégration au système (`pydm/integrate.py`, bibliothèque standard)

```python
appimage_path() -> str | None          # $APPIMAGE s'il désigne un fichier existant, sinon None
integrate(appimage, home=None) -> str  # "new" (première fois), "updated" (chemin changé), "same"
remove(home=None) -> None              # désintégration
```

Fichiers écrits par `integrate` (tous atomiques, sous `home`, par défaut `~`) :

| Fichier | Contenu |
|---|---|
| `~/.local/share/pydm/pydm-host` (0755) | `#!/bin/sh` + `exec <chemin AppImage protégé> --native-host "$@"` |
| manifestes `com.pydm.host.json` | mêmes dossiers et contenu qu'`install.sh` (Firefox, Chrome, Chromium, Brave, Edge, Vivaldi, Opera), `path` = l'enveloppe ci-dessus |
| `~/.local/share/applications/pydm.desktop` | copie de `pydm.desktop` avec `Exec="<AppImage>" %U` (règles de protection des `.desktop`, comme `install.sh`) |
| `~/.local/share/icons/hicolor/<n>x<n>/apps/pydm.png` | icônes 16 à 256 |

- Le résultat dépend du contenu de l'enveloppe : absente → `"new"` ; présente mais autre chemin →
  `"updated"` ; identique → `"same"` (rien n'est réécrit, sauf un manifeste ou l'entrée de menu
  manquants, recréés).
- Les manifestes d'une installation `install.sh` existante sont remplacés : la dernière
  installation lancée gagne.
- `remove` supprime l'enveloppe, les manifestes **dont `path` est l'enveloppe** (ceux d'`install.sh`
  sont laissés), l'entrée de menu si son `Exec` pointe vers une AppImage, et les icônes ; garde
  `~/.config/pydm` (réglages, liste) et les fichiers téléchargés.

Appel : au démarrage de l'interface (`gui/app.py`), si `appimage_path()` n'est pas `None`. Toute
exception (`OSError`) est attrapée : PyDM démarre quand même, avec dans la barre d'état
« Intégration au système impossible : <raison> ». Hors AppImage, rien n'est fait.

## 4. Interface

- Résultat `"new"` → message unique « **PyDM est installé** — Il est dans le menu des
  applications, et l'extension du navigateur peut maintenant lui envoyer vos téléchargements. »
  Boutons : « Installer l'extension Firefox » (ouvre
  `https://github.com/BenKL404/pydm/releases/latest`), « Chrome / Chromium… » (ouvre la section
  Chrome du LISEZMOI sur GitHub), « Fermer ». `"updated"` et `"same"` : rien d'affiché.
- Préférences, visible seulement depuis une AppImage : bouton « Retirer PyDM du système » →
  confirmation → `remove()` → « PyDM a été retiré du menu et du navigateur. Supprimez le fichier
  <nom>.AppImage pour terminer. » puis fermeture de PyDM.

## 5. Construction et publication

- `packaging/build-appimage.sh` : PyInstaller → AppDir (`usr/bin/` = dossier figé, `AppRun`,
  `pydm.desktop`, `pydm.png`) → `appimagetool` (version actuelle du projet AppImage, runtime
  statique : fonctionne avec FUSE 3, sans `libfuse2`) → `dist/PyDM-<version>-x86_64.AppImage`.
  Le script télécharge ffmpeg statique et appimagetool à des URL figées, vérifiées par SHA-256.
- CI : job `appimage` (ubuntu-22.04) qui construit, puis teste l'AppImage produite :
  `--help` ; `ping` via `--native-host` ; intégration dans un HOME temporaire (enveloppe et
  manifestes présents). Sur un tag `v*`, l'AppImage est jointe à la version GitHub.
- Version 1.3.0. README et LISEZMOI : « Télécharger l'AppImage » devient la première méthode
  d'installation ; `install.sh` passe en « depuis les sources ». Note de repli si l'AppImage ne
  démarre pas (FUSE absent) : `./PyDM-….AppImage --appimage-extract-and-run`.

## Tests

- `tests/test_integrate.py` (HOME temporaire, `$APPIMAGE` simulé) : première intégration →
  `"new"`, enveloppe exécutable, manifestes valides pointant vers l'enveloppe, `.desktop` avec
  `Exec` protégé (chemin avec espace et guillemet) ; second appel → `"same"` sans réécriture ;
  AppImage déplacée → `"updated"` ; manifeste supprimé à la main → recréé ; `remove` laisse un
  manifeste d'`install.sh` ; dossier en lecture seule → `OSError` levée (attrapée par l'appelant).
- `tests/test_host.py` : avec `APPIMAGE` défini, la commande de lancement est l'AppImage ;
  `ping` figé → `ytdlp` vrai.
- `tests/test_cli` : `--native-host` avec arguments Firefox et Chrome appelle `pydm_host.main`
  sans erreur `argparse`.
- Interface : message affiché seulement pour `"new"` ; bouton de retrait absent hors AppImage.

## Hors sujet

Version Windows (sous-projet suivant), mise à jour automatique de yt-dlp ou de l'AppImage,
paquet `.deb`, publication de l'extension sur addons.mozilla.org.
