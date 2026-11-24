# Spécification - pilotage arbitré de la tortue (geste, voix, objet)

**Objectif.** Compléter six fonctions de décision d'un système qui pilote la
tortue de turtlesim par trois modalités (geste de la main, voix, objet suivi par
YOLO), sous l'autorité d'un arbitre. Les nœuds ROS2 et la plomberie sont fournis
et ne sont pas modifiés. Seules les fonctions de décision sont à écrire.

**Contenu.** Le périmètre, la répartition en lots, le contrat de chaque
fonction, les décisions arrêtées, les contraintes et la définition de terminé.
Relu à chaque appel, il reste complet et ne grossit pas. Ce n'est pas une liste
de tâches : celle-ci est dans les plans et dans `progress/`.

## Le monde

| Élément | Valeur |
|---|---|
| Robot | la tortue de turtlesim, commandée par un twist (vitesse linéaire, vitesse angulaire) |
| Modalités | geste (priorité 30), voix (20), objet (10) |
| Urgence | arrêt d'urgence par paume ouverte, priorité 1000, au-dessus de toute priorité déclarée |
| Unités | unités turtlesim ; angles en radians, positifs vers la gauche |
| Fourni | `arbiter_node.py`, `gesture_node.py`, `object_node.py`, `chemin_sans_nav2.py`, `projet_turtle.py` |
| À compléter | `arbiter.py`, `gesture_commands.py`, `navigator.py`, `object_tracker.py`, `regleur.py` |

## Répartition - trois lots indépendants

Aucune des six fonctions n'en appelle une autre : les lots se codent et se
testent en parallèle, sans attendre un coéquipier.

| Lot | Fichiers | Fonctions |
|---|---|---|
| A | `navigator.py` | `calculer_consigne`, `LisseurCible.mettre_a_jour` |
| B | `arbiter.py`, `gesture_commands.py` | `Arbiter.arbitrer`, `reconnaitre` |
| C | `object_tracker.py`, `regleur.py` | `choisir_meilleure`, `construire_schema` |

## Décisions arrêtées - ne pas les redériver

**Arbitrage.** Une commande périmée est écartée avant tout choix. L'âge d'une
commande est borné à zéro : une commande horodatée après l'instant d'arbitrage
(délai d'un autre fil) est « du futur proche », donc valide, jamais supprimée.
Parmi les commandes valides, la priorité la plus haute gagne ; à priorité égale,
la plus récente. Une urgence l'emporte sur tout. **Sans commande valide, la
sortie est un arrêt** (twist nul, modalité `aucune`) : conserver la dernière
consigne ferait partir la tortue toute seule.

**Gestes.** L'ordre d'évaluation est la règle de sécurité : paume ouverte sur
**toutes** les mains d'abord (arrêt d'urgence), puis avance à deux mains, puis
rotation par inclinaison d'une seule main. La rotation a une zone morte, un gain
et une saturation lus dans la configuration ; une main à peu près droite ne
commande aucune rotation. Le signe de l'inclinaison donne le sens de rotation.

**Navigation.** Trois phases dans cet ordre : arrivée (twist nul), orientation
(on tourne sans avancer si l'erreur de cap dépasse la tolérance), approche (on
avance et on corrige le cap). Toutes les vitesses sont saturées par les
maxima de la configuration. Le lissage de la cible est un filtre exponentiel de
coefficient alpha ; la première mesure est adoptée telle quelle.

**Suivi d'objet.** La détection retenue est celle de plus grande confiance,
jamais la dernière parcourue ; liste vide, résultat `None`.

**Réglage par le LLM.** Le LLM règle des paramètres déclarés du contrôleur, il
ne commande jamais la tortue. L'énumération des paramètres du schéma vient de la
configuration reçue, sans aucune liste écrite en dur.

## Environnement et contraintes

- Python 3. Les fonctions à écrire restent pures : ni caméra, ni micro, ni
  horloge murale, ni ROS2. L'instant est toujours passé en argument.
- Aucune valeur écrite en dur : gains, seuils, tolérances, priorités et
  péremptions viennent de `ihr_config.json`.
- Les signatures publiques et les docstrings (Purpose, Inputs, Outputs) sont
  respectées ; chaque fonction est écrite à l'indentation déjà en place.
- Ne pas supprimer, affaiblir ni réécrire les tests existants. Limiter chaque
  modification aux fonctions du lot et au module de tests correspondant.
- Chaque personne ne modifie que ses propres fichiers : son plan et son fichier
  de progression.
- Après chaque plan, lancer la commande de test ciblée indiquée. En cas
  d'échec, corriger à partir du résultat du test et relancer, **trois fois au
  maximum**. Au-delà, marquer le plan bloqué dans son fichier de progression et
  décrire l'échec restant ; ne pas prétendre que le travail est réussi et ne pas
  recommencer indéfiniment.

## Définition de terminé

Les tests de chaque lot passent, avec leurs cas d'échec. Lorsque les trois lots
sont terminés, la régression combinée passe depuis la racine du projet :

`python -m pytest test/test_arbiter.py test/test_gesture_commands.py test/test_navigator.py test/test_object_tracker.py test/test_regleur.py -q`

Puis la suite complète du dossier `test/` est verte, et la démonstration avec les
nœuds fournis montre qu'une urgence l'emporte sur une commande normale plus
récente.
