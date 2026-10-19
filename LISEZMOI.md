# PyDM — gestionnaire de téléchargement pour Linux (style IDM)

🇬🇧 [Read in English](README.md)

## 1. Installer PyDM

Il faut Python 3.9 ou plus récent.

```bash
sudo apt install python3-tk ffmpeg        # Fedora : sudo dnf install python3-tkinter ffmpeg
pip install -U yt-dlp                     # ou : pipx install yt-dlp  (vidéos de streaming)
git clone https://github.com/BenKL404/pydm.git && cd pydm
./install.sh
```

`install.sh` installe PyDM dans `~/.local/share/pydm`, ajoute la commande `pydm`
et l'entrée dans le menu des applications. Il déclare aussi PyDM auprès de
Firefox, Chrome, Chromium, Brave, Edge, Vivaldi et Opera. Si vous installez un
navigateur plus tard, relancez simplement `./install.sh`.

## 2. Installer l'extension

### Chrome, Chromium, Brave, Edge, Vivaldi, Opera
1. Ouvrez `chrome://extensions` (ou `brave://extensions`, `edge://extensions`…).
2. Activez le **Mode développeur** (en haut à droite).
3. Cliquez sur **Charger l'extension non empaquetée** et choisissez le dossier `extension/`.
4. Redémarrez le navigateur.

Laissez le dossier `extension/` à sa place : le navigateur le lit à chaque démarrage.

### Firefox
Firefox n'installe de façon permanente que les extensions signées par Mozilla.
Il y a trois possibilités :

- **Pour essayer** : ouvrez `about:debugging#/runtime/this-firefox`, cliquez sur
  **Charger un module complémentaire temporaire** et choisissez `pydm-extension.zip`.
  L'extension disparaît quand Firefox se ferme.
- **Firefox Developer Edition / Nightly / ESR** : dans `about:config`, mettez
  `xpinstall.signatures.required` à `false`, puis ouvrez `pydm-extension.zip`
  dans `about:addons` → ⚙ → *Installer un module depuis un fichier*.
- **Firefox normal, de façon permanente** : faites signer l'extension
  gratuitement en distribution privée (« unlisted ») :
  `npx web-ext sign --channel=unlisted --api-key=… --api-secret=…`
  (clés gratuites sur addons.mozilla.org → Outils de développement).

Les navigateurs installés en **Flatpak** ne peuvent pas lancer PyDM : utilisez la
version `.deb` ou `.rpm` du navigateur. Firefox en Snap (Ubuntu) fonctionne.

## 3. Utilisation (comme IDM)

| Action | Résultat |
|---|---|
| Cliquer sur un lien de téléchargement | Le navigateur s'efface et PyDM télécharge avec 8 connexions |
| Survoler une vidéo | Un bouton **⬇ Télécharger cette vidéo** apparaît en haut à droite du lecteur |
| Clic droit sur un lien / une vidéo / une page | **Télécharger avec PyDM** |
| Icône PyDM de la barre d'outils | État de la connexion, médias détectés sur la page (le chiffre sur l'icône), réglages |

- Les cookies et la page d'origine sont transmis à PyDM : les téléchargements
  qui demandent d'être connecté fonctionnent.
- Les fichiers de moins de 100 Ko restent au navigateur.
- Si PyDM n'est pas joignable, le navigateur télécharge normalement (point rouge sur l'icône).
- PyDM s'ouvre tout seul s'il est fermé.

## Limites
- Les vidéos protégées par DRM (Netflix, Disney+, Prime Video, Spotify…) ne
  peuvent pas être téléchargées.
- Les téléchargements produits par un formulaire (POST) sont redemandés par
  simple lien et peuvent échouer. Désactivez alors l'interception dans l'icône PyDM.
- Mettez yt-dlp à jour régulièrement (`pip install -U yt-dlp`) : les sites changent souvent.

## Contribuer

Signalements de bugs, idées et pull requests sont les bienvenus, en français ou en
anglais : voir [CONTRIBUTING.md](CONTRIBUTING.md) et le [code de conduite](CODE_OF_CONDUCT.md).
Pour une faille de sécurité, suivez [SECURITY.md](SECURITY.md) (jamais d'issue publique).

## Licence

PyDM est un logiciel libre distribué sous licence
[GNU GPL version 3 ou ultérieure](LICENSE).
