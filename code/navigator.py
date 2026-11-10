"""
navigator.py - Asservissement de la tortue vers un point du canevas.

Projet de session. Fonction PURE : elle recoit une pose et une cible, elle rend une
consigne de vitesse. Aucune camera, aucun ROS2, aucune horloge. C'est ce qui permet
de prouver le comportement de navigation sans rien lancer (workflow.md R5).

Ce que faisaient les rendus etudiants
-------------------------------------
Projet1 (`projetYOLO...py`) separait la rotation et l'avance en deux fonctions
appelees l'une apres l'autre avec un `time.sleep(0.5)` entre les deux, et publiait
`twist.angular.z = angle_diff` directement, sans gain et sans saturation. Trois
consequences :

  1. Une erreur de cap de pi radians produit une vitesse angulaire de 3,14 rad/s,
     la tortue depasse sa cible et oscille.
  2. Le `sleep(0.5)` bloque la boucle video : la position de la cible n'est plus
     rafraichie pendant la rotation, donc la tortue vise ou l'objet ETAIT.
  3. `turn_turtle` divisait les pixels par 50 en dur pour passer en unites
     turtlesim. Ce 50 ne vaut que pour une image de 550 pixels de large ; sur une
     camera 640x480, la cible tombe hors canevas.

Projet2 (`banano.py`) faisait mieux, avec un gain `k = 0.5` et une conversion
proportionnelle a la taille de l'image, mais ne saturait toujours pas la vitesse et
ne s'arretait qu'a un seuil de distance de 1 unite, code en dur.

Le solutionnaire regle les trois : gain et tolerances lus dans la configuration,
vitesses saturees, et une seule fonction qui rend LES DEUX vitesses a la fois, sans
jamais dormir. Tourner et avancer ne sont plus deux phases, ce sont deux composantes
de la meme consigne.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ihr_ros.backends.base import Pose, Twist
from ihr_ros.geometry import distance, heading_error


@dataclass(frozen=True)
class Consigne:
    """Consigne calculee, avec la raison qui l'explique."""

    twist: Twist
    erreur_cap_rad: float
    distance_restante: float
    arrivee: bool
    phase: str

    def describe(self) -> str:
        """Ligne courte pour l'affichage tete haute."""
        return (f"{self.phase} | cap {math.degrees(self.erreur_cap_rad):+6.1f} deg | "
                f"dist {self.distance_restante:5.2f}")


def _saturer(valeur: float, maximum: float) -> float:
    """Borner une vitesse en gardant son signe."""
    return max(-maximum, min(maximum, valeur))


def calculer_consigne(pose: Pose,
                      cible: tuple[float, float],
                      settings: dict[str, Any]) -> Consigne:
    """
    --------------------------------------------------------------------------
    Purpose:
        Calculer la consigne de vitesse qui rapproche la tortue de la cible.

        La loi est un proportionnel sur le cap, avec une avance conditionnee au
        cap : tant que la tortue ne regarde pas assez pres de sa cible, elle
        tourne sans avancer. Sans cette condition, une tortue mal orientee decrit
        une spirale autour de sa cible au lieu d'y aller. Le rendu Projet2
        appliquait deja cette idee, avec un seuil code en dur de pi/18 ; ici elle
        vient de `heading_tolerance_rad`.

    Inputs:
        pose (Pose): pose courante de la tortue, unites turtlesim
        cible (tuple): (x, y) visee, unites turtlesim
        settings (dict): section projet de la configuration

    Outputs:
        consigne (Consigne): vitesses saturees et justification
    --------------------------------------------------------------------------
    """
    # Indice : arrivee d'abord, puis tourner sans avancer hors tolerance de cap, sinon avancer et corriger le cap
    # Tests : test_cible_droit_devant_et_loin_donne_la_phase_approche, test_cible_derriere_la_tortue_impose_une_rotation_avant_toute_avance, test_erreur_de_cap_extreme_ne_depasse_jamais_vitesse_angulaire_max
    raise NotImplementedError(
        "fonction 'calculer_consigne' a implementer (voir l'enonce et les tests cites)"
    )


class LisseurCible:
    """
    Filtre exponentiel sur la position de la cible.

    YOLO redetecte l'objet a chaque trame, et le centre de la boite saute de
    quelques pixels d'une trame a l'autre meme quand l'objet ne bouge pas. Sans
    filtre, ce bruit se retrouve tel quel dans l'erreur de cap et la tortue
    fremit sur place. Aucun rendu etudiant ne filtrait.

    La constante `suivi_lisse_alpha` regle le compromis : 1.0 ne filtre rien et
    suit instantanement, une valeur proche de 0 est tres lisse mais repond avec
    retard.
    """

    def __init__(self, settings: dict[str, Any] | None = None, alpha: float | None = None):
        if alpha is None:
            if settings is None:
                raise ValueError("Fournir soit une configuration, soit un alpha explicite.")
            alpha = float(settings["suivi_lisse_alpha"])
        if not 0.0 < alpha <= 1.0:
            raise ValueError(
                f"suivi_lisse_alpha vaut {alpha}, attendu dans ]0, 1]. "
                "Zero figerait la cible a sa premiere valeur, au-dela de 1 le filtre diverge."
            )
        self._alpha = float(alpha)
        self._valeur: tuple[float, float] | None = None

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def valeur(self) -> tuple[float, float] | None:
        """Derniere position lissee, None tant qu'aucune mesure n'est arrivee."""
        return self._valeur

    def mettre_a_jour(self, mesure: tuple[float, float]) -> tuple[float, float]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Incorporer une nouvelle mesure et rendre la position lissee. La
            premiere mesure est adoptee telle quelle : filtrer depuis zero ferait
            partir la cible du coin du canevas.

        Inputs:
            mesure (tuple): (x, y) mesure, unites turtlesim

        Outputs:
            lissee (tuple): (x, y) apres filtrage
        --------------------------------------------------------------------------
        """
        # Indice : premiere mesure adoptee telle quelle, ensuite filtre exponentiel avec alpha
        # Tests : test_premiere_mesure_est_adoptee_telle_quelle_sans_lissage, test_deuxieme_mesure_se_deplace_de_exactement_alpha_vers_la_nouvelle_valeur
        raise NotImplementedError(
            "fonction 'LisseurCible.mettre_a_jour' a implementer (voir l'enonce et les tests cites)"
        )

    def reset(self) -> None:
        """Oublier la cible, par exemple quand l'objet sort du champ."""
        self._valeur = None
