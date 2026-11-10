"""
test_navigator.py - Preuves du contrat de navigator.py (Projet, 6MIG841).

navigator.calculer_consigne est une fonction PURE (pose, cible, configuration) ->
consigne : aucune camera, aucun ROS2, aucune horloge, donc chaque scenario est fabrique
a la main avec une pose et une cible explicites (workflow.md R5, regle de determinisme).

Les valeurs numeriques attendues sont calculees dans les commentaires a partir des
memes formules que le module (gain proportionnel, saturation), jamais recopiees de la
sortie d'une execution.
"""

from __future__ import annotations

import copy
import math

import pytest

from ihr_ros.backends.base import Pose, Twist
from navigator import LisseurCible, calculer_consigne


# ---------------------------------------------------------------------------
# 1. Trois phases de calculer_consigne : arrivee, approche, orientation.
# ---------------------------------------------------------------------------

def test_tortue_deja_a_la_cible_rend_un_twist_nul(projet_cfg):
    """A moins de goal_tolerance de la cible, la tortue est declaree arrivee, twist nul."""
    pose = Pose(5.0, 5.0, 0.0)
    # distance((5.0,5.0), (5.2,5.0)) = 0.2 < goal_tolerance (0.5) : deja arrivee.
    consigne = calculer_consigne(pose, (5.2, 5.0), projet_cfg)
    assert consigne.twist == Twist(0.0, 0.0)
    assert consigne.arrivee is True
    assert consigne.phase == "arrivee"


def test_cible_droit_devant_et_loin_donne_la_phase_approche(projet_cfg):
    """Cap deja bon et cible loin -> phase approche, avance strictement positive."""
    # Pose face a +x (theta=0). Cible (8,5) : cap requis = atan2(0,3) = 0 = theta.
    # erreur de cap nulle, donc <= heading_tolerance_rad : pas de phase orientation.
    pose = Pose(5.0, 5.0, 0.0)
    consigne = calculer_consigne(pose, (8.0, 5.0), projet_cfg)
    assert consigne.phase == "approche"
    assert consigne.twist.linear_x > 0.0
    # vitesse_lineaire saturee : min(linear_speed=1.0, vitesse_lineaire_max=2.0) = 1.0.
    assert consigne.twist.linear_x == pytest.approx(1.0)


def test_cible_derriere_la_tortue_impose_une_rotation_avant_toute_avance(projet_cfg):
    """
    Cap oppose (erreur > heading_tolerance_rad) -> phase orientation : la tortue
    tourne, elle n'avance PAS encore. C'est la correction du defaut mesure sur les
    rendus etudiants (navigator.py, en-tete) : sans cette condition, une tortue mal
    orientee avance en spirale au lieu de faire face a sa cible d'abord.
    """
    # Pose face a +x (theta=0). Cible (2,5), derriere : cap requis = atan2(0,-3) = pi.
    # erreur = normalize_angle(pi - 0) = pi > heading_tolerance_rad (0.1745) : orientation.
    pose = Pose(5.0, 5.0, 0.0)
    consigne = calculer_consigne(pose, (2.0, 5.0), projet_cfg)
    assert consigne.phase == "orientation"
    assert consigne.twist.linear_x == 0.0
    assert consigne.twist.angular_z != 0.0


def test_erreur_de_cap_extreme_ne_depasse_jamais_vitesse_angulaire_max(projet_cfg):
    """
    LE defaut mesure sur le rendu Projet1 (navigator.py, en-tete) : publier
    `angular.z = angle_diff` sans saturation fait tourner la tortue a 3,14 rad/s pour
    une erreur de pi radians. Ici, meme avec un gain enorme, la vitesse angulaire
    rendue reste bornee. Le gain est agrandi expres pour que la saturation soit
    REELLEMENT exercee (avec le gain par defaut 0.5, gain*pi = 1.57 < 2.0, la
    saturation ne se declencherait jamais et le test passerait par accident).
    """
    cfg = copy.deepcopy(projet_cfg)
    cfg["angular_gain"] = 100.0
    pose = Pose(5.0, 5.0, 0.0)
    # Cible derriere : erreur de cap = pi. gain*erreur = 100*pi = 314.16, tres au-dela
    # de vitesse_angulaire_max (2.0) : la saturation DOIT s'activer.
    consigne = calculer_consigne(pose, (2.0, 5.0), cfg)
    max_angulaire = float(cfg["vitesse_angulaire_max"])
    assert abs(consigne.twist.angular_z) <= max_angulaire
    # Preuve que la saturation a reellement clippe (et pas juste ete respectee) :
    # la sortie doit toucher exactement la borne.
    assert abs(consigne.twist.angular_z) == pytest.approx(max_angulaire)


# ---------------------------------------------------------------------------
# 2. Signe de la rotation.
# ---------------------------------------------------------------------------

def test_cible_a_gauche_donne_une_vitesse_angulaire_positive(projet_cfg):
    """Cible au-dessus de la tortue (a sa gauche, theta=0) -> angular_z positif."""
    # Cap requis vers (5,8) depuis (5,5) : atan2(3,0) = +pi/2. erreur = +pi/2.
    # angular = gain * (+pi/2) = 0.5 * 1.5708 = +0.7854 (non sature, < max 2.0).
    pose = Pose(5.0, 5.0, 0.0)
    consigne = calculer_consigne(pose, (5.0, 8.0), projet_cfg)
    assert consigne.twist.angular_z > 0.0
    assert consigne.twist.angular_z == pytest.approx(0.5 * (math.pi / 2.0))


def test_cible_a_droite_donne_une_vitesse_angulaire_negative(projet_cfg):
    """Cible en dessous de la tortue (a sa droite, theta=0) -> angular_z negatif."""
    # Cap requis vers (5,2) depuis (5,5) : atan2(-3,0) = -pi/2. erreur = -pi/2.
    # angular = gain * (-pi/2) = -0.7854.
    pose = Pose(5.0, 5.0, 0.0)
    consigne = calculer_consigne(pose, (5.0, 2.0), projet_cfg)
    assert consigne.twist.angular_z < 0.0
    assert consigne.twist.angular_z == pytest.approx(-0.5 * (math.pi / 2.0))


# ---------------------------------------------------------------------------
# 3. LisseurCible : filtre exponentiel sur la position de la cible.
# ---------------------------------------------------------------------------

def test_premiere_mesure_est_adoptee_telle_quelle_sans_lissage():
    """
    La toute premiere mesure n'est PAS lissee, elle est adoptee telle quelle :
    filtrer depuis zero ferait partir la cible du coin du canevas (navigator.py,
    docstring de LisseurCible). Egalite exacte exigee, pas un pytest.approx qui
    tolererait un debut de lissage.
    """
    lisseur = LisseurCible(alpha=0.4)
    assert lisseur.valeur is None
    resultat = lisseur.mettre_a_jour((3.0, 4.0))
    assert resultat == (3.0, 4.0)
    assert lisseur.valeur == (3.0, 4.0)


def test_deuxieme_mesure_se_deplace_de_exactement_alpha_vers_la_nouvelle_valeur():
    """
    A partir de la deuxieme mesure, la formule est
    valeur = alpha * mesure + (1 - alpha) * ancienne_valeur (moyenne mobile exponentielle).
    Ici alpha=0.4 : x = 0.4*5.0 + 0.6*3.0 = 2.0 + 1.8 = 3.8 ;
                    y = 0.4*8.0 + 0.6*4.0 = 3.2 + 2.4 = 5.6.
    """
    lisseur = LisseurCible(alpha=0.4)
    lisseur.mettre_a_jour((3.0, 4.0))
    resultat = lisseur.mettre_a_jour((5.0, 8.0))
    assert resultat == pytest.approx((3.8, 5.6))


def test_reset_oublie_la_cible():
    """reset() ramene valeur a None, comme si aucune mesure n'etait jamais arrivee."""
    lisseur = LisseurCible(alpha=0.4)
    lisseur.mettre_a_jour((1.0, 1.0))
    lisseur.reset()
    assert lisseur.valeur is None


# ---------------------------------------------------------------------------
# 4. Chemins d'echec de LisseurCible.
# ---------------------------------------------------------------------------

def test_alpha_zero_est_refuse():
    """alpha=0 figerait la cible a sa premiere valeur pour toujours : ValueError."""
    with pytest.raises(ValueError):
        LisseurCible(alpha=0)


def test_alpha_superieur_a_un_est_refuse():
    """alpha=1.5 ferait diverger le filtre : ValueError."""
    with pytest.raises(ValueError):
        LisseurCible(alpha=1.5)


def test_ni_configuration_ni_alpha_est_refuse():
    """Sans configuration ET sans alpha explicite, il n'y a rien a lire : ValueError."""
    with pytest.raises(ValueError):
        LisseurCible()
