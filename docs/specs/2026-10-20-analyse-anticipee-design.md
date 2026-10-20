# Analyse anticipée des vidéos

Date : 2026-10-20. Complète la fenêtre d'ajout
([2026-10-20-dialogue-ajout-design.md](2026-10-20-dialogue-ajout-design.md)).

## Objectif

Mesure : l'analyse d'une vidéo YouTube prend 3,4 s (dont 2,9 s pour yt-dlp, incompressibles :
aucun autre « client » YouTube n'est à la fois plus rapide et fiable). IDM paraît instantané parce
qu'il connaît la vidéo avant le clic. Critère de réussite : ouvrir une vidéo YouTube dans Firefox,
attendre quelques secondes, cliquer sur « ⬇ Télécharger cette vidéo » → la fenêtre d'ajout s'ouvre
avec le menu Qualité déjà rempli.

## Contraintes

- Le message `add` existant reste compatible (nouveau champ facultatif `title`).
- Un `prefetch` ne lance jamais PyDM ; aucune fenêtre ni notification.
- Bibliothèque standard hors `pydm/gui/` ; textes en français.

## 1. Extension

- `background.js` : sur `tabs.onUpdated` (changement d'URL, y compris la navigation interne de
  YouTube, ou chargement terminé), si le réglage `prefetch` est vrai (défaut) et que l'URL est
  une **page vidéo** — YouTube `/watch?v=…`, `/shorts/…`, `youtu.be/…` ; autres `VIDEO_HOSTS` :
  chemin non vide — envoyer une fois par (onglet, URL) `{"action": "prefetch", "url", "headers"}`
  (en-têtes construits comme pour `add` : User-Agent, Referer, Cookie). Échec silencieux.
- `add` : nouveau champ `title` (titre de l'onglet) pour les envois depuis le bouton vidéo, le
  menu contextuel et le popup.
- Popup : case « Préparer les vidéos à l'avance » (`prefetch`).
- `pydm-extension.zip` reconstruit.

## 2. Connecteur

`pydm_host.py` : pour `prefetch`, une seule tentative de connexion à la socket ; si PyDM n'est pas
ouvert → `{"ok": false, "error": "PyDM fermé"}` sans lancement.

## 3. Mémoire des analyses (`pydm/cache.py`)

```python
video_key(url) -> str          # YouTube : "youtube:<id>" ; sinon l'URL sans fragment
AnalysisCache(analyzer=analyze, ttl=600, max_items=50, workers=2, clock=time.monotonic)
cache.prefetch(url, headers=None, browser="Aucun", kind="video") -> None
cache.get(url, headers=None, browser="Aucun", kind="auto", default_quality="Meilleure") -> dict
```

- `prefetch` : rien si un résultat valide ou une analyse en cours existe pour la clé ; sinon
  analyse en arrière-plan (au plus `workers` simultanées, les autres attendent).
- `get` (même signature que `analyze`, utilisable comme `analyzer` de la fenêtre d'ajout) :
  résultat en mémoire → copie adaptée ; analyse en cours → attend sa fin ; sinon analyse
  synchrone puis mise en mémoire.
- Adaptation : `selected = preselect(choices, default_quality)`, `name` = titre + extension du
  choix, `size` = taille du choix.
- Seuls les résultats `video`/`file` sont gardés (pas les erreurs) ; expiration `ttl` ; au-delà de
  `max_items`, le plus ancien est oublié.

## 4. PyDM

- `MainWindow.cache = AnalysisCache(analyzer=self.analyzer)` ; les fenêtres d'ajout reçoivent
  `analyzer=self.cache.get`.
- Message `prefetch` (thread IPC → file → `tick`) : `cache.prefetch(url, headers,
  settings["browser"])` ; pas d'`show_window`.
- `add_urls(..., title=None)` → `AddDialog(..., title=title)` : le titre s'affiche dès
  l'ouverture ; pour un lien YouTube, la miniature `https://i.ytimg.com/vi/<id>/mqdefault.jpg`
  est chargée tout de suite dans un thread (64 Ko, 5 s) et remplacée par celle de l'analyse si
  elle arrive.

## 5. Tests

`test_cache.py` (analyseur factice, fausse horloge) : `video_key` (watch, `&list=`, shorts,
youtu.be, autre site) ; prefetch puis get → une seule analyse et retour immédiat ; get pendant un
prefetch → une seule analyse ; expiration ; limite de taille ; erreur non gardée ; adaptation à
la qualité par défaut. Fenêtre : `prefetch` reçu → analyse mise en mémoire, aucune fenêtre ;
ajout après prefetch → fenêtre remplie sans nouvelle analyse ; titre affiché avant l'analyse ;
miniature YouTube demandée. Connecteur : `prefetch` sans PyDM → réponse immédiate, aucun
lancement. Extension : `node --check`, zip conforme (CI). Vérification par l'utilisateur dans
Firefox.
