# Version Windows (expérimentale)

Date : 2026-10-21. Second sous-projet « installation sans terminal » ; réutilise la base PyInstaller
et l'intégration de l'AppImage ([2026-10-21-appimage-design.md](2026-10-21-appimage-design.md)).

## Objectif

Critère de réussite : sur Windows 10 ou 11 (x64), télécharger `PyDM-1.4.0-Setup.exe` depuis la page
des versions GitHub, l'exécuter (sans droits administrateur) → PyDM s'ouvre, est dans le menu
Démarrer, et l'extension (Firefox, Chrome, Edge, Brave…) lui envoie les téléchargements, y compris
quand PyDM est fermé. Aucun PC Windows n'est disponible pour les essais : la version est publiée
comme **expérimentale**, vérifiée par la CI (tests unitaires et essai de bout en bout sur une
machine Windows), avec un appel aux retours.

## Contraintes

- `pydm/` reste en bibliothèque standard hors `pydm/gui/` ; `pydm_host.py` reste autonome (sa
  partie transport recopie celle de `pydm/ipc.py`, comme aujourd'hui pour `CONFIG_DIR`).
- Comportement sous Linux inchangé (y compris les noms de fichiers).
- `winreg` n'est importé que sous Windows ; les tests Windows n'écrivent que sous
  `HKCU\Software\PyDM-tests`.
- Python ≥ 3.9 ; textes visibles en français ; aucune mention d'outil d'IA.

## 1. Transport et dossiers

- `CONFIG_DIR` : `%APPDATA%\PyDM` sous Windows (`$PYDM_CONFIG_DIR` reste prioritaire).
- `pydm/ipc.py` : sous Windows, canal nommé `\\.\pipe\pydm-<nom d'utilisateur>` (préfixé par le
  nom de `$PYDM_CONFIG_DIR` s'il est défini, pour isoler les tests) via
  `multiprocessing.connection.Listener(address, family="AF_PIPE")` / `Client` ; un message = un
  JSON en octets (`send_bytes`/`recv_bytes`, jamais `pickle`). Mêmes fonctions publiques
  (`start_ipc`, `ipc_send`, `instance_running`), même format de messages. Linux : socket Unix
  inchangée.
- `pydm_host.py` : même transport selon la plateforme.

## 2. Programmes et hôte natif

- Le dossier figé contient `pydm.exe` (fenêtré) et `pydm-host.exe` (console, point d'entrée
  `pydm_host.main`), partageant `_internal`.
- Hôte figé sous Windows : lancement de PyDM = `<dossier>\pydm.exe --minimized`, détaché
  (`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, sans console) ; `ping` → `ytdlp` vrai.
- `pydm --remove-integration` : appelle `integrate.remove()` puis quitte (utilisé par le
  désinstalleur ; fonctionne aussi depuis l'AppImage).

## 3. Intégration (`pydm/integrate.py`, partie Windows)

Active quand PyDM est figé sous Windows (`installed_exe()` = `sys.executable`). À chaque lancement
de l'interface, comme pour l'AppImage :

| Élément | Contenu |
|---|---|
| `%LOCALAPPDATA%\PyDM\hosts\firefox.json`, `chrome.json` | manifestes, `path` = `pydm-host.exe` |
| `HKCU\Software\Mozilla\NativeMessagingHosts\com.pydm.host` | (défaut) = chemin de `firefox.json` |
| `HKCU\Software\Google\Chrome\…`, `…\Chromium\…`, `…\Microsoft\Edge\NativeMessagingHosts\com.pydm.host` | (défaut) = chemin de `chrome.json` (Brave, Vivaldi, Opera lisent la clé de Chrome) |
| `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, valeur `PyDM` | `"<pydm.exe>" --minimized`, seulement si le démarrage avec la session est activé |

- Résultat `"new"` (clé Mozilla absente), `"updated"` (pointe ailleurs : PyDM déplacé), `"same"` ;
  tout élément différent de l'attendu est réécrit (la dernière installation lancée gagne). Même
  message d'accueil, même bouton « Retirer PyDM du système » (§4 de la spec AppImage).
- `remove()` : supprime les clés et la valeur `Run` qui pointent vers cette installation, et le
  dossier `hosts` ; garde `%APPDATA%\PyDM` (réglages, liste).
- `set_autostart` passe par la valeur `Run` sous Windows.
- Les fonctions prennent un paramètre `root` (clé racine, défaut `HKCU\Software`) pour les tests.

## 4. Différences de comportement sous Windows

- **Noms de fichiers** : `util.safe_filename(name)` — sous Windows, remplace `< > : " / \ | ? *`
  et les caractères de contrôle par `_`, retire les points et espaces finaux, préfixe `_` aux noms
  réservés (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, avec ou sans extension) ;
  nom vide → `téléchargement`. Sous Linux : seulement `/` → `_` (comportement actuel). Appliqué à
  tout nom de fichier construit par PyDM (URL, `Content-Disposition`, nom saisi, titre de vidéo).
- **Fin de file** (`gui/schedule.py`) : éteindre = `shutdown /s /t 0` ; mettre en veille =
  `SetSuspendState(False, False, False)` de `powrprof.dll` via `ctypes`.
- **Cookies** : si yt-dlp échoue à déchiffrer les cookies de Chrome, Edge ou Brave sous Windows,
  message « Chrome chiffre ses cookies sous Windows d'une façon que PyDM ne peut pas lire :
  choisissez Firefox dans « Cookies ». » (via `friendly_error`).

## 5. Construction et publication

- `packaging/pydm.spec` : second `EXE` `pydm-host` (console) sous Windows ; ffmpeg et ffprobe de
  `ffmpeg-9.0.2-essentials_build.zip` (github.com/GyanD/codexffmpeg, version 9.0.2, SHA-256 figé).
- `packaging/build-windows.ps1` : PyInstaller → `dist\pydm\` → `PyDM-<version>-windows-portable.zip`
  et, avec Inno Setup 6, `PyDM-<version>-Setup.exe`.
- `packaging/windows/pydm.iss` : `PrivilegesRequired=lowest`, dossier
  `{localappdata}\Programs\PyDM`, raccourci menu Démarrer (icône de bureau en option), lancement
  de PyDM en fin d'installation, `[UninstallRun]` `pydm.exe --remove-integration`, version et
  éditeur affichés dans « Applications installées ».
- CI, job `windows` (`windows-latest`, après les jobs de tests) : suite de tests complète ;
  construction ; essai de bout en bout — installation silencieuse (`/VERYSILENT`), premier
  lancement (intégration), clés et manifestes vérifiés, `ping` et `add` envoyés à `pydm-host.exe`
  comme le ferait le navigateur (PyDM démarre, le téléchargement d'un fichier local servi en HTTP
  se termine), désinstallation silencieuse → clés retirées. Sur un tag `v*`, `Setup.exe` et
  `.zip` sont joints à la version.
- Version 1.4.0. README et LISEZMOI : section « Windows (expérimental) » (installateur, version
  portable, avertissement SmartScreen « Informations complémentaires → Exécuter quand même »,
  limite des cookies Chrome, appel aux retours par les issues GitHub).

## Tests

- `test_util` : `safe_filename` (caractères interdits, noms réservés avec extension, points
  finaux, nom vide) avec la plateforme forcée à Windows ; Linux inchangé.
- `test_ipc` / `test_host` : sous Windows, aller-retour par canal nommé ; tests POSIX sautés.
- `test_integrate` (Windows seulement, racine `HKCU\Software\PyDM-tests`) : `"new"`, `"same"`,
  `"updated"`, retrait sélectif, démarrage avec la session.
- `test_schedule` : commandes de fin de file choisies selon la plateforme (sans les exécuter).
- `test_cli` : `--remove-integration` appelle `integrate.remove`.

## Hors sujet

Signature de code, Windows ARM, Microsoft Store, mise à jour automatique, essais manuels de
l'interface sous Windows.
