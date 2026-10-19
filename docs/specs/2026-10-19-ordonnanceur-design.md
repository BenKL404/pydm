# Ordonnanceur PyDM : file d'attente, limite de vitesse, plage horaire

Date : 2026-10-19 · Devient l'étape 2 de la modernisation décrite dans
[2026-10-19-interface-qt-design.md](2026-10-19-interface-qt-design.md).

> **Révision prévue avant l'étape 2.** Le moteur (§ 1 à 3, 5, 7, 8) reste valable et ira dans
> `pydm/scheduler.py`. Les réglages (§ 4) s'ajoutent à `pydm/store.py` créé à l'étape 1.
> L'interface (§ 6) et les tests (§ 9) seront réécrits pour Qt ; les catégories
> automatiques sont à l'étape 3, la barre système et les notifications à l'étape 1.

## Objectif

Aujourd'hui, tout téléchargement démarre dès qu'il est ajouté, sans plafond de débit,
et les réglages de la fenêtre sont perdus à chaque lancement.

Scénario de réussite : l'utilisateur ajoute 20 liens le soir ; PyDM en télécharge 3 à
la fois entre 01:00 et 07:00, sans dépasser la limite de débit choisie, puis éteint
l'ordinateur quand la file est vide.

## Contraintes

- Bibliothèque standard uniquement (Tkinter pour l'interface ; yt-dlp et ffmpeg restent optionnels).
- Tout reste dans `pydm.py` : `install.sh` et `pydm_host.py` ne changent pas.
- Textes de l'interface et documentation en français ; identifiants du code en anglais.
- La ligne de commande (`run_cli`) n'est pas concernée, sauf qu'elle profite du `RateLimiter` (désactivé par défaut).

## Hors périmètre

- Plusieurs files nommées (comme IDM).
- Limite de vitesse par téléchargement.
- PyDM actif fenêtre fermée : fermer la fenêtre quitte toujours PyDM (relève de l'étape 3).
- Glisser-déposer pour réordonner (les boutons suffisent).

## 1. Modèle de la file

Chaque tâche (`Download`, `VideoDownload`, via `_Task`) reçoit un attribut `want` :

| `want` | Fixé par | Effet |
|---|---|---|
| `"queue"` | ajout (manuel, extension, presse-papiers), bouton ▶ Reprendre | attend son tour dans la file |
| `"force"` | bouton ⏩ Forcer | démarre immédiatement, ignore `max_active` et la plage horaire |
| `"stop"` | bouton ⏸ Pause, ou erreur détectée par le scheduler | le scheduler ne la démarre plus |

Valeur par défaut à la création : `"queue"`.

L'ordre de la file est l'ordre des lignes de la liste (`tree.get_children()`).

## 2. `Scheduler`

Classe indépendante de Tkinter et du réseau.

```python
Scheduler(max_active=3, schedule=None)
    # schedule : None (pas de plage) ou (start, end) en datetime.time
tick(tasks, now) -> bool
    # tasks : liste ordonnée ; now : datetime. Renvoie True une seule fois quand la file se termine.
in_window(now) -> bool
next_start(now) -> datetime | None   # pour l'affichage « reprise à 01:00 »
```

Les tâches ne sont manipulées que via `start()`, `pause()`, `running`, `finished`, `error`,
`want` et `status`.

`tick` applique dans l'ordre :

1. **Erreurs** : une tâche non `running`, non `finished`, avec `error` non vide et `want != "stop"`
   passe à `want = "stop"` (son statut « Erreur : … » est conservé).
2. **Plage horaire** : si `schedule` est défini et que `now` est hors plage, chaque tâche
   `want == "queue"` en cours est mise en pause (`pause()`) et reste `"queue"`. La plage
   peut chevaucher minuit (`start > end`, ex. 23:00–07:00). `start == end` signifie toute la journée.
   Aucune tâche `"queue"` ne démarre hors plage. Les tâches `"force"` ne sont pas concernées.
3. **Places libres** (dans la plage, ou sans plage) : `libres = max_active − nb de tâches
   "queue" running`. Les premières tâches `"queue"` non running et non finished, dans l'ordre
   de la liste, reçoivent `start()` jusqu'à épuisement des places.
4. **Statut d'attente** : une tâche `"queue"` non running, non finished et sans erreur affiche
   « En file », ou « En file (reprise à HH:MM) » hors plage.
5. **Fin de file** : le scheduler retient s'il a démarré au moins une tâche (`armed`). Quand
   `armed` est vrai et qu'aucune tâche `"queue"` n'est en attente ni en cours (et qu'aucune
   `"force"` ne tourne), `tick` renvoie `True` et remet `armed` à faux. Le signal ne revient
   donc qu'après un nouveau démarrage par la file.

Une tâche mise en pause par le scheduler doit avoir fini de s'arrêter (`running` faux) avant
d'être redémarrée ; `start()` ne fait déjà rien si le thread tourne encore.

Changer l'ordre de la liste n'interrompt aucune tâche en cours : l'ordre ne compte qu'à
l'attribution d'une place libre.

## 3. `RateLimiter`

Seau à jetons partagé, thread-safe ; une instance de module `LIMITER = RateLimiter()`.

```python
RateLimiter(rate=0, clock=time.monotonic)
rate              # octets/s, modifiable à chaud ; 0 = illimité
consume(n, stop_evt)   # bloque jusqu'à disposer de n octets ; retourne tôt si stop_evt est levé
```

- Capacité du seau : `max(rate * 0.5, CHUNK)`.
- L'attente se fait par `stop_evt.wait(délai)` : une pause reste instantanée sous une limite basse.
- Passer `rate` à 0 débloque les attentes en cours au prochain réveil (délai d'attente plafonné à 0,25 s).

Branchement :

- `Download._worker` : `LIMITER.consume(len(buf), self.stop_evt)` après chaque `r.read(CHUNK)`.
- `VideoDownload._hook` : calcul de l'écart de `downloaded_bytes` depuis l'appel précédent,
  sous un verrou propre à la tâche (yt-dlp appelle le hook depuis plusieurs threads de
  fragments), puis `LIMITER.consume(écart, self.stop_evt)`. L'écart négatif (nouveau fichier,
  ex. audio après vidéo) remet le compteur à zéro sans consommer.
- Limite connue : quand yt-dlp délègue à ffmpeg (certains flux en direct), le hook n'est pas
  appelé et la limite ne s'applique pas. À indiquer dans LISEZMOI.md.

## 4. Réglages persistants

Fichier `~/.config/pydm/settings.json` (`SETTINGS_FILE`), fonctions `load_settings()` et
`save_settings(d)`. Valeurs par défaut (`DEFAULT_SETTINGS`) utilisées pour toute clé absente
ou de type invalide, et pour tout le fichier s'il est illisible :

| Clé | Défaut |
|---|---|
| `folder` | dossier par défaut actuel (`~/Téléchargements` ou `~/Downloads`) |
| `parts` | 8 |
| `quality` | `"Meilleure"` |
| `browser` | `"Aucun"` |
| `clipboard` | `true` |
| `max_active` | 3 (1 à 10) |
| `speed_on` | `false` |
| `speed_kbps` | 2048 |
| `schedule_on` | `false` |
| `schedule_start` / `schedule_end` | `"01:00"` / `"07:00"` |
| `end_action` | `"none"` (`"quit"`, `"suspend"`, `"poweroff"`) |

- Les options `-o` et `-n` passées explicitement en ligne de commande l'emportent sur `folder`
  et `parts` enregistrés.
- Écriture : à l'OK des Préférences, au changement de la case de limite, et à la fermeture.
  Écriture atomique (fichier temporaire + `os.replace`).

## 5. Session

`session.json` est écrit dans l'ordre de la liste et chaque entrée gagne `"want"`.
Au chargement : `"queue"` et `"force"` → `"queue"` ; `"stop"` → `"stop"` (statut « En pause ») ;
entrée sans `"want"` (ancien format) → `"stop"`, comme le comportement actuel.

## 6. Interface

Fenêtre principale :

- Boutons du bas : `▶ Reprendre` (`want="queue"`), `⏸ Pause` (`want="stop"` + `pause()`),
  `⏩ Forcer` (`want="force"` + `start()`), `▲` / `▼` (déplacer la sélection d'une ligne),
  `⤒` (en tête de file), `✖ Retirer`, `📂 Ouvrir le dossier` ; à droite `⚙ Préférences`.
- Case à cocher « Limiter à X Mo/s » (libellé selon `speed_kbps`) : met à jour `LIMITER.rate`
  et `speed_on`.
- Ligne d'état sous la liste : « N en cours · M en file » suivi, si la plage est active,
  de « · plage 01:00–07:00 » et, hors plage, de « (inactive, reprise à 01:00) ».
- `add()` : la tâche créée reçoit `want="queue"` et n'est plus démarrée directement ; c'est le
  scheduler qui la lance. La détection fichier/vidéo reste immédiate (thread `detect`).
- `refresh()` appelle `scheduler.tick(tâches dans l'ordre de la liste, datetime.now())`.

Fenêtre Préférences (`Toplevel` modal) : téléchargements simultanés (Spinbox 1–10), limite en
Ko/s, case « Plage horaire » avec début/fin HH:MM, liste « Quand la file est terminée » :
Ne rien faire / Quitter PyDM / Mettre en veille / Éteindre l'ordinateur. Un horaire invalide
affiche un avertissement et la fenêtre reste ouverte. OK applique au scheduler et au limiteur,
puis enregistre ; Annuler ne change rien.

## 7. Action finale

Quand `tick` renvoie `True` et que `end_action != "none"` : fenêtre de compte à rebours de 60 s
(« Éteindre l'ordinateur dans 42 s… ») avec un bouton Annuler. À échéance :

- `quit` : `on_close()`.
- `suspend` / `poweroff` : `save_session()`, puis `systemctl suspend` / `systemctl poweroff`.
  En cas d'échec (code de retour non nul, commande absente), message d'erreur ; PyDM reste ouvert.

## 8. Erreurs

- `settings.json` illisible : valeurs par défaut, pas de message ; le fichier est réécrit au prochain enregistrement.
- Tâche en erreur : sortie de la file (`want="stop"`), l'utilisateur peut la relancer par ▶ Reprendre.
- Échec de `systemctl` : voir § 7.

## 9. Tests

`unittest` (bibliothèque standard), dossier `tests/`, lancement :
`python3 -m unittest discover tests`. Les tests importent `pydm` sans ouvrir de fenêtre.

- `test_scheduler.py` (fausses tâches, `now` choisi) : respect de `max_active` ; ordre de la
  file ; tâche forcée hors limite et hors plage ; tâche en erreur passée à `"stop"` ; pause hors
  plage puis reprise ; plage à cheval sur minuit ; `start == end` ; signal de fin émis une seule
  fois et réarmé après un nouveau démarrage.
- `test_ratelimiter.py` (fausse horloge) : débit moyen respecté ; `rate = 0` sans attente ;
  `stop_evt` débloque `consume` ; changement de `rate` à chaud.
- `test_settings.py` : défauts sans fichier ; fichier corrompu ; clé de mauvais type ;
  aller-retour écriture/lecture (dossier de config redirigé vers un dossier temporaire).
- `test_download_throttle.py` (intégration) : serveur HTTP local gérant `Range`, fichier de
  4 Mo, 4 connexions, `LIMITER.rate = 2 Mo/s` : contenu identique et durée ≥ 1,5 s ;
  sans limite : contenu identique.

L'interface Tkinter est vérifiée manuellement : ajout de 5 liens avec `max_active=2`,
Forcer, réordonnancement, case de limite, plage horaire réglée sur les minutes à venir,
action finale `quit` avec annulation puis sans.

## 10. Documentation

- LISEZMOI.md : section « File d'attente, limite de vitesse et planification » ; limite ffmpeg.
- LISEZMOI.md (section développeurs) : commande des tests.
