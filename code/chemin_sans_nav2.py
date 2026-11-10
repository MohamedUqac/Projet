"""
chemin_sans_nav2.py - Le chemin SANS Nav2 : le Lab 1 planifie, le Projet commande.

Complement demande par l'orchestrateur pendant plan07 : l'architecture d'enonce.md
porte l'arete PLAN --> NAV (« un module du Projet qui recopierait le code du Devoir 1
au lieu de l'importer casserait ce graphe »), et le tableau des trois contextes de
plan07.md et spec.md (« Nav2 et SLAM recouvre les planificateurs du Lab 1, et c'est
assume ») dit que sur le substitut et sur turtlesim, ce sont LES PLANIFICATEURS DU
LAB 1 qui planifient et L'ASSERVISSEMENT DU PROJET qui commande. Ce module cable
reellement cette ligne, jusque-la vraie seulement en prose.

`TurtleBackend.goto_pose` (backends/base.py) refuse PAR DEFAUT, en nommant la
dorsale : c'est vrai pour le substitut et pour la dorsale ROS2 ordinaire, qui n'ont
aucun planificateur propre. `aller_a_pose` compense cette absence en appelant un
planificateur du Lab 1 (planif.astar / planif.thetastar, REUTILISES SANS
MODIFICATION), puis en parcourant le chemin rendu avec `navigator.calculer_consigne`
(Projet, REUTILISE SANS MODIFICATION), point de passage par point de passage.

Sur la dorsale Nav2, c'est L'INVERSE, et c'est le CONTROLE NEGATIF explicitement
demande : `goto_pose` reussit (ou echoue) par elle-meme, et le planificateur du Lab 1
n'est JAMAIS appele. Deux planificateurs actifs pour la meme pose serait une source
de divergence, pas un renfort (« turtle_io est le seul chemin vers le robot », meme
principe applique ici a la PLANIFICATION).

Le palier utilise (`astar` ou `theta_star`) vient de la configuration
(projet.planificateur_defaut), jamais d'un litteral. Theta* est retenu PAR DEFAUT
dans ihr_config.json (enonce.md : 4 points de passage contre 18 pour A* sur la meme
grille, donc 14 rotations de moins et autant de derive d'odometrie evitee sur un vrai
robot, l'argument meme que l'enonce avance pour le Projet).

D*-Lite (palier 3) n'est PAS cable ici : sa replanification incrementale exige un
etat maintenu entre deux appels (une instance `DStarLite`, pas la fonction `planifier`
partagee par astar/thetastar), ce qui est une integration differente de celle demandee
par l'orchestrateur (« Theta* est le palier a brancher par defaut »). Limite connue,
documentee plutot que contournee en silence (R8).

Aucune dependance interdite : `planif.astar`, `planif.thetastar` et `planif.world` ne
dependent que de la bibliotheque standard (verifie par lecture des imports), donc les
importer depuis le Projet n'ajoute rien a la contrainte matplotlib+numpy du Lab 1
(spec.md, « Le substitut tkinter et l'application matplotlib du Lab 1 restent separes »).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "Lab1" / "code"))

from ihr_ros.backends.base import Pose, ResultatNavigation  # noqa: E402
from planif import astar, thetastar  # noqa: E402
from planif.world import World  # noqa: E402

from navigator import calculer_consigne  # noqa: E402

#: Un nom de palier -> son module 'planifier(monde, depart, but) -> ResultatPlanification'.
#: D*-Lite est absent : voir la limite documentee en en-tete du module.
PLANIFICATEURS = {"astar": astar, "theta_star": thetastar}


def planifier_chemin(depart: tuple[float, float], but: tuple[float, float],
                     monde: World, nom_planificateur: str) -> list[tuple[float, float]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Calculer un chemin de points de passage, en unites, depart et but etant
        dans les MEMES unites que `monde`. Le planificateur (A* ou Theta*,
        REUTILISES SANS MODIFICATION) est choisi PAR NOM, jamais par un `if`
        ecrit ici sur la geometrie de l'appelant.

    Inputs:
        depart (tuple): (x, y), unites de monde
        but (tuple): (x, y), unites de monde
        monde (World): grille de planification (planif.world), deja
            dimensionnee par l'appelant pour la dorsale visee
        nom_planificateur (str): 'astar' ou 'theta_star'

    Outputs:
        points (list): suite de points de passage (x, y), le BUT inclus, le
            DEPART exclu (deja atteint)
    --------------------------------------------------------------------------
    """
    if nom_planificateur not in PLANIFICATEURS:
        raise KeyError(
            f"Planificateur '{nom_planificateur}' inconnu. Planificateurs "
            f"disponibles : {sorted(PLANIFICATEURS)}."
        )
    module = PLANIFICATEURS[nom_planificateur]
    cellule_depart = monde.vers_cellule(depart)
    cellule_but = monde.vers_cellule(but)

    resultat = module.planifier(monde, cellule_depart, cellule_but)
    if resultat.chemin is None:
        raise ValueError(
            f"Aucun chemin trouve entre {depart} et {but} sur cette grille "
            f"({nom_planificateur}, {resultat.cellules_examinees} cellules examinees)."
        )
    return [monde.vers_unites(cellule) for cellule in resultat.chemin[1:]]


def aller_a_pose(turtle: Any, pose_cible: Pose, projet_cfg: dict[str, Any], monde: World,
                 sleep: Callable[[float], None] = time.sleep) -> ResultatNavigation:
    """
    --------------------------------------------------------------------------
    Purpose:
        Aller a une pose absolue, quelle que soit la dorsale. Essaie D'ABORD
        `turtle.backend.goto_pose` : Nav2 SEUL l'honore directement (controle
        negatif de ce module, plan07.md). Sur NotImplementedError (aucun
        planificateur propre a la dorsale, backends/base.py), planifie un
        chemin avec le Lab 1 (`planifier_chemin`) et le PARCOURT avec
        l'asservissement du Projet (`navigator.calculer_consigne`), point par
        point, jusqu'a la tolerance d'arrivee de chacun.

        Un echec de planification (but inatteignable) est rendu comme un
        ResultatNavigation, jamais leve : meme garantie que Nav2Backend.goto_pose
        (plan07.md, « Nav2 en echec : rend un echec, ne leve pas »), etendue ici
        au chemin sans Nav2 pour que l'appelant n'ait qu'un seul contrat a lire.

    Inputs:
        turtle (TurtleClient): facade de commande (ihr_ros.turtle_io)
        pose_cible (Pose): pose visee, MEMES UNITES que `monde`
        projet_cfg (dict): section 'projet' de la configuration (gains,
            tolerances, 'planificateur_defaut', 'aller_a_pose_max_iterations')
        monde (World): grille de planification, dimensionnee par l'appelant
            pour la dorsale visee (aucune mise a l'echelle automatique ici :
            un monde construit pour le Lab 1 n'a pas necessairement les
            dimensions du canevas turtlesim)
        sleep (callable): fonction d'attente entre deux pas d'asservissement,
            injectee pour les tests (workflow.md, determinisme)

    Outputs:
        resultat (ResultatNavigation): succes, ou echec motive (jamais leve)
    --------------------------------------------------------------------------
    """
    try:
        return turtle.backend.goto_pose(pose_cible)
    except NotImplementedError:
        pass

    try:
        chemin = planifier_chemin(
            (turtle.pose().x, turtle.pose().y), (pose_cible.x, pose_cible.y),
            monde, str(projet_cfg["planificateur_defaut"]),
        )
    except (KeyError, ValueError) as exc:
        return ResultatNavigation(False, str(exc))

    periode = float(projet_cfg["control_period_seconds"])
    max_iterations = int(projet_cfg["aller_a_pose_max_iterations"])

    for point in chemin:
        iterations = 0
        while True:
            consigne = calculer_consigne(turtle.pose(), point, projet_cfg)
            turtle.drive(linear=consigne.twist.linear_x, angular=consigne.twist.angular_z)
            turtle.spin_once(0.0)
            if consigne.arrivee:
                break
            iterations += 1
            if iterations >= max_iterations:
                turtle.stop()
                return ResultatNavigation(
                    False, f"point de passage {point} non atteint apres "
                          f"{max_iterations} iterations (aller_a_pose_max_iterations)."
                )
            sleep(periode)

    turtle.stop()
    return ResultatNavigation(True, "")
