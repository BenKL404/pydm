# Ordonnanceur PyDM : file d'attente, limite de vitesse, plage horaire

Date : 2026-10-19, révisée le 2026-10-20 pour l'interface Qt
([2026-10-19-interface-qt-design.md](2026-10-19-interface-qt-design.md)) et la fenêtre d'ajout
([2026-10-20-dialogue-ajout-design.md](2026-10-20-dialogue-ajout-design.md)).

## Objectif

Aujourd'hui, tout téléchargement démarre dès qu'il est ajouté et rien ne limite le débit.

Scénario de réussite : l'utilisateur ajoute 20 liens avec « Plus tard » ; PyDM en télécharge 3 à
la fois entre 01:00 et 07:00 sans dépasser la limite de débit choisie, puis éteint l'ordinateur
quand la file est vide. Pendant la journée, un lien envoyé avec « Télécharger » démarre aussitôt
(dans la limite des téléchargements simultanés), sans attendre la nuit.

## Contraintes

- `pydm/scheduler.py` et le limiteur : bibliothèque standard, sans Qt.
- Textes en français ; identifiants en anglais ; Python ≥ 3.9.
- L'extension et le protocole de messagerie native ne changent pas.

## Hors périmètre

Plusieurs files nommées ; limite de vitesse par téléchargement ; glisser-déposer pour réordonner.

## 1. États voulus

Chaque tâche (`_Task`) reçoit un attribut `want` :

| `want` | Fixé par | Démarre quand |
|---|---|---|
| `"now"` | Télécharger (fenêtre d'ajout), ajout direct (« Ne plus demander », extension, Ctrl+V, dépôt), Reprendre | une place est libre (`max_active`) ; la plage horaire ne le bloque pas |
| `"later"` | Plus tard (fenêtre d'ajout), clic droit « Mettre dans la file » | la file planifiée est active (§ 2) et une place est libre |
| `"force"` | Forcer | immédiatement, hors `max_active` et hors plage |
| `"stop"` | Pause, erreur | jamais (action de l'utilisateur) |

Défaut à la création : `"now"`. L'ordre de la file est l'ordre des lignes du modèle
(`DownloadModel.tasks()`).

## 2. `Scheduler` (`pydm/scheduler.py`)

```python
Scheduler(max_active=3, window=None)    # window : None ou (datetime.time début, datetime.time fin)
scheduler.queue_started: bool           # file démarrée à la main
start_queue() / stop_queue()
queue_active(now) -> bool               # dans la plage (si définie) ou démarrée à la main
next_start(now) -> datetime | None      # prochain début de plage, pour l'affichage
tick(tasks, now) -> bool                # True une seule fois quand tout est terminé (§ 2.5)
```

Les tâches ne sont manipulées que via `start()`, `pause()`, `running`, `finished`, `error`,
`want`, `status`. `tick` applique dans l'ordre :

1. **Erreurs** : tâche non `running`, non `finished`, `error` non vide et `want != "stop"` →
   `want = "stop"` (statut « Erreur : … » conservé).
2. **Fin de plage** : si la file planifiée n'est pas active, chaque tâche `later` en cours est
   mise en pause (`pause()`) et reste `later`. Plage à cheval sur minuit gérée (début > fin) ;
   début == fin = toute la journée. `stop_queue()` met aussi en pause les `later` en cours.
3. **Places** : `libres = max_active − nb de tâches now/later en cours`. On démarre, dans l'ordre
   de la liste, d'abord les `now` en attente, puis — si la file est active — les `later` en
   attente. Une tâche en cours d'arrêt (`running` encore vrai) n'est pas redémarrée.
   Les `force` sont démarrées immédiatement (une fois) et ne comptent pas dans `max_active`.
4. **Statuts d'attente** (tâche non running, non finished, sans erreur) :
   `now` → « En file » ; `later` → « En file planifiée », ou « En file planifiée (reprise à
   HH:MM) » si une plage est définie et inactive.
5. **Fin** : le scheduler retient s'il a démarré au moins une tâche `later` (`armed`). Quand
   `armed` et qu'aucune tâche `now`/`later` n'est en attente ni en cours (et aucune `force` en
   cours), `tick` renvoie `True`, remet `armed` à faux et `queue_started` à faux.

Changer l'ordre de la liste n'interrompt aucune tâche en cours.

## 3. Limite de vitesse

`RateLimiter(rate=0, clock=time.monotonic)` dans `pydm/scheduler.py`, instance de module
`LIMITER` ; `rate` en octets/s (0 = illimité), modifiable à chaud ; `consume(n, stop_evt)` bloque
jusqu'à disposer de `n` octets, attente par `stop_evt.wait(min(délai, 0.25))` (pause réactive,
changement de `rate` pris en compte) ; capacité du seau `max(rate × 0,5, CHUNK)`.

- `Download._worker` : `LIMITER.consume(len(buf), self.stop_evt)` après chaque lecture.
- `VideoDownload._hook` : écart de `downloaded_bytes` depuis l'appel précédent (verrou propre à
  la tâche ; écart négatif = nouveau fichier, compteur remis à zéro), puis `consume`.
- Limite connue : quand yt-dlp délègue à ffmpeg (certains flux en direct), la limite ne s'applique
  pas (LISEZMOI).

## 4. Réglages (`store.DEFAULTS`)

| Clé | Défaut | Contrôle |
|---|---|---|
| `max_active` | 3 | entier 1–10 |
| `speed_on` | `false` | bool |
| `speed_kbps` | 2048 | entier 16–1 000 000 |
| `schedule_on` | `false` | bool |
| `schedule_start` / `schedule_end` | `"01:00"` / `"07:00"` | chaîne `HH:MM` valide |
| `end_action` | `"none"` | `none`, `quit`, `suspend`, `poweroff` |

Valeur invalide → défaut (règles existantes de `store`).

## 5. Session

`entry_from_task` enregistre `want`. Au chargement : `now`/`force` → `now` (reprennent seuls),
`later` → `later`, `stop` → `stop` (« En pause ») ; entrée sans `want` → `stop`.

## 6. Interface Qt

- **Barre d'en-tête** : boutons-icônes **Forcer** (`force`) et **Planifier** (`schedule`, menu :
  Démarrer la file, Arrêter la file, séparateur, Planification…), entre « Ouvrir le dossier » et
  « Rechercher ».
- **Fenêtre Planification** (`pydm/gui/schedule.py`, `ScheduleDialog(settings)` →
  `result_settings()`) : simultanés (1–10), case + limite en Ko/s, case « Plage horaire » + début
  et fin `HH:MM` (`QTimeEdit`), « Quand la file est terminée » (Ne rien faire / Quitter PyDM /
  Mettre en veille / Éteindre l'ordinateur). OK applique au scheduler et au limiteur puis
  enregistre ; Annuler ne change rien.
- **Barre d'état** : à gauche « N en cours · M en file · plage HH:MM–HH:MM » (+ « (reprise à
  HH:MM) » hors plage ; « · file démarrée » si démarrée à la main) ; à droite, avant la courbe,
  bouton bascule « Limite X Mo/s » (`speed_on`), en surbrillance quand actif.
- **Clic droit** : Reprendre (`now`), Pause (`stop`), Forcer (`force`), Mettre dans la file
  (`later`), séparateur, Monter (Ctrl+↑), Descendre (Ctrl+↓), En tête de file (Ctrl+Origine),
  puis les entrées existantes. Réordonner sur une liste triée par colonne enlève le tri.
  `DownloadModel.move(rows, delta)` / `move_to_top(rows)`.
- **Boutons existants** : Reprendre → `want="now"` ; Pause → `want="stop"` + `pause()` ; Espace →
  bascule `now`/`stop`.
- **Fenêtre d'ajout** : Télécharger → `now` ; Plus tard → `later` (au lieu d'« en pause »).
- **Barre système** : Démarrer la file / Arrêter la file dans le menu.
- `MainWindow.tick()` appelle `scheduler.tick(model.tasks(), datetime.now())`.

## 7. Action finale

Quand `tick` renvoie `True` et `end_action != "none"` : dialogue « Éteindre l'ordinateur dans
60 s… » (libellé selon l'action) avec Annuler, et notification si la fenêtre est masquée. À
échéance : `quit` → `quit_app()` ; `suspend` / `poweroff` → `save_session()` puis `systemctl
suspend` / `systemctl poweroff` (`subprocess.run`, échec → message d'erreur, PyDM reste ouvert).

## 8. Tests

- `test_scheduler.py` (fausses tâches, `now` choisi) : `max_active` ; `now` avant `later` ;
  `later` bloqué hors file, démarré par `start_queue()` ou dans la plage ; plage à cheval sur
  minuit ; début == fin ; pause des `later` en fin de plage et à `stop_queue()` ; `force` hors
  limite et hors plage ; erreur → `stop` ; statuts « En file » / « En file planifiée (reprise à
  01:00) » ; signal de fin une seule fois puis réarmé ; `now` seuls ne déclenchent pas la fin.
- `test_ratelimiter.py` (fausse horloge) : débit respecté ; `rate=0` sans attente ; `stop_evt`
  débloque ; changement de `rate` à chaud ; intégration : serveur de test, 4 Mo, 4 connexions,
  2 Mo/s → durée ≥ 1,5 s, contenu identique.
- `test_store.py` : nouvelles clés et validation (horaire invalide, `max_active` hors bornes).
- Session : aller-retour de `want` et anciennes entrées.
- Interface (hors écran) : Forcer / Mettre dans la file / Reprendre / Pause fixent `want` ;
  réordonnancement ; barre d'état ; bascule de limite → `LIMITER.rate` ; `ScheduleDialog`
  (horaire et valeurs) ; fenêtre d'ajout Plus tard → `later` ; action finale `quit` avec
  annulation (minuteur raccourci dans le test).
- Vérification manuelle par l'utilisateur : plage réglée sur les minutes à venir, action finale.

## 9. Documentation

LISEZMOI / README (file, Forcer, Plus tard, planification, limite, action finale ; limite
ffmpeg), CHANGELOG.
