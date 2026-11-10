# Identité visuelle : icônes d'action et illustrations

Date : 2026-11-10. Choix validés sur maquettes (compagnon visuel) : style **à plat**, direction
**B « une couleur par action »** pour les icônes, famille **B « objets emblèmes »** pour les
illustrations. Le logo (anneau de 8 segments et flèche), les icônes de types de fichiers et les
pastilles d'état ne changent pas.

## Objectif

Donner à PyDM une identité propre et des repères visuels explicites : chaque action de la barre
d'outils est un petit dessin qui montre ce qu'elle fait, et les écrans vides parlent par une
illustration plutôt qu'une phrase grise. Critère de réussite : en thème clair comme sombre, les 9
actions se reconnaissent sans lire leur infobulle, et aucun état vide n'est un simple texte.

## Palette

| Rôle | Clair | Sombre |
|---|---|---|
| corps (ardoise) | `#334155` | `#cbd5e1` |
| détail (blanc) | `#ffffff` | `#0f172a` |
| cyan (marque, ajouter, rechercher, document) | `#06b6d4` | idem |
| vert (reprendre, réussite, musique) | `#22c55e` | idem |
| ambre (pause, dossier, DRM) | `#f59e0b` | idem |
| violet (forcer, planifier, vidéo) | `#8b5cf6` | idem |
| rouge (supprimer, erreur) | `#ef4444` | idem |
| neutre (menu) | `#64748b` | idem |

## 1. Icônes d'action (`pydm/gui/icons/`)

Les 9 SVG `add`, `resume`, `pause`, `force`, `remove`, `folder`, `schedule`, `search`, `menu`
sont remplacés par les dessins de la maquette (grille 32×32) :

| Fichier | Dessin | Accent |
|---|---|---|
| `add` | feuille au coin plié, rond « + » | cyan |
| `resume` | rond plein, triangle lecture | vert |
| `pause` | rond plein, deux barres (détail) — rond ambre, comme « reprendre » est vert (la maquette le montrait ardoise, son accent ne se voyait pas) | ambre |
| `force` | fusée (corps), hublot et flammes | violet |
| `remove` | corbeille, couvercle soulevé | rouge |
| `folder` | dossier, fichier qui dépasse | ambre |
| `schedule` | réveil, aiguilles | violet |
| `search` | page et loupe | cyan |
| `menu` | trois curseurs de réglage | neutre |

Convention dans les fichiers : le corps est écrit `#010101`, le détail `#fefefe` ; l'accent est
écrit en clair (couleur fixe). `theme.icon(name)` remplace `#010101` et `#fefefe` par les valeurs
du thème courant (tableau ci-dessus) — les fichiers restent des SVG valides affichables tels quels.
Les icônes monochromes restantes (types de fichiers, logo) gardent `currentColor`. L'état
désactivé reste généré par Qt (grisé). `refresh_icons()` recharge les icônes au changement de thème
comme aujourd'hui.

## 2. Illustrations (`pydm/gui/illustrations/`, nouveau)

SVG à plat, mêmes repères `#010101` / `#fefefe` :

| Fichier | Dessin | Utilisé pour |
|---|---|---|
| `vide.svg` (220×140) | plateau où tombent vidéo (violet), document (cyan), musique (vert), flèche cyan | liste sans aucun téléchargement |
| `filtre-vide.svg` (160×100) | plateau vide | vue filtrée sans élément |
| `recherche-vide.svg` (160×100) | loupe cyan au-dessus du plateau vide | recherche sans résultat |
| `installe.svg` (150×110) | anneau du logo, flèche, coche verte | message « PyDM est installé » |
| `lien-brise.svg` (128×72) | maillons séparés, rouge | fenêtre d'ajout : analyse impossible |
| `cadenas.svg` (128×72) | cadenas ambre | fenêtre d'ajout : contenu DRM |

`theme.illustration(name, size=None) -> QPixmap` rend le SVG aux couleurs du thème (cache par
thème, densité d'écran prise en compte).

## 3. Composant « état vide » (`pydm/gui/widgets.py`)

`EmptyState(QWidget)` : illustration centrée, titre (gras), sous-titre (gris, retour à la ligne),
méthode `show_state(illustration, title, subtitle)`. Il remplace le `QLabel` `self.empty` posé sur
la liste (`window.py`), avec les mêmes règles d'affichage (`_update_empty`) :

| Situation | Illustration | Titre | Sous-titre |
|---|---|---|---|
| aucun téléchargement | `vide` | Aucun téléchargement pour l'instant | Collez un lien, glissez-le ici, ou cliquez sur ⬇ dans le navigateur |
| recherche active sans résultat | `recherche-vide` | Aucun résultat pour « <texte> » | Essayez un autre mot, ou videz la recherche |
| vue filtrée vide | `filtre-vide` | Rien ici pour l'instant | Les téléchargements de cette vue apparaîtront ici |

Si la zone est trop basse pour l'illustration (< 220 px de haut), seuls le titre et le sous-titre
s'affichent.

## 4. Autres écrans

- `welcome.py` : l'icône du message devient `installe` (au lieu du logo).
- `adddialog.py` : la vignette affiche `lien-brise` quand l'analyse échoue, `cadenas` pour un
  contenu DRM, au lieu de l'icône de type.

## Tests

- `theme.icon` : un SVG contenant `#010101`/`#fefefe` sort aux couleurs du thème clair puis sombre
  (pixel du corps vérifié) ; l'accent fixe ne change pas.
- Les 9 icônes et 6 illustrations existent, sont des SVG valides (rendu non vide) et ne contiennent
  plus `currentColor`.
- `EmptyState` / `_update_empty` : les trois situations donnent le bon titre et la bonne
  illustration ; zone basse → illustration masquée.
- Accueil et fenêtre d'ajout : illustration attendue selon le cas (installé, erreur, DRM).
- Vérification visuelle par captures hors écran, thèmes clair et sombre.

## Hors sujet

Logo, icônes de types de fichiers, icône de l'application, de l'extension et de l'installateur,
pastilles d'état, mise en page générale.
