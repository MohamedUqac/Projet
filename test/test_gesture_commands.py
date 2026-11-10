"""
test_gesture_commands.py - Preuves du contrat de gesture_commands.py (Projet, 6MIG841).

Les mains canoniques viennent de fabrique_mains.py (Devoir1/test), REUTILISEES telles
quelles, jamais recopiees (le Devoir 1 est reutilise sans modification par le Projet,
gesture_commands.py, en-tete). Une precision s'impose : `inclinaison_main` mesure le
vecteur PINKY_MCP -> THUMB_TIP (il traverse la paume), alors que thumb_detector mesure
seulement THUMB_IP -> THUMB_TIP pour decider "pouce leve". Ce sont deux segments
DIFFERENTS de la meme main : une main que fabrique_mains construit "pouce vertical"
au sens de thumb_detector n'a donc pas necessairement une inclinaison nulle au sens de
gesture_commands (verifie : main_pouce_leve() donne environ -65,6 deg par ce second
segment, a cause du decalage de l'eventail des doigts). `_main_pouce_incline` ci-dessous
REUTILISE main_pouce_leve() en totalite (extension du pouce, doigts replies : tout ce
que thumb_detector regarde) et deplace SEULEMENT le point PINKY_MCP, qui n'entre dans
AUCUN critere de thumb_detector.count_folded_fingers (seuls PIP et TIP y comptent) ni
dans hand_metrics.scale_px (poignet -> MIDDLE_MCP) : cela donne un controle exact de
l'inclinaison lue par gesture_commands sans jamais changer le verdict "pouce leve" lu
par thumb_detector.

Aucune camera, aucun MediaPipe : voir workflow.md, regle R5.
"""

from __future__ import annotations

import math

import pytest

import fabrique_mains as fm
import gesture_commands
from ihr_ros.backends.base import Twist
from thumb_detector import PINKY_MCP, THUMB_TIP

IMG_W = IMG_H = 480  # image carree : voir Devoir1/test/test_thumb_detector.py.


def _main_pouce_incline(angle_deg: float, rayon: float = 0.25) -> list[tuple[float, float]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Fabriquer une main dont thumb_detector.analyse_hand rend is_up=True (c'est
        toujours fabrique_mains.main_pouce_leve(), inchangee pour tout ce que
        thumb_detector regarde), mais dont gesture_commands.inclinaison_main rend
        EXACTEMENT `angle_deg`, en imposant la direction du vecteur
        PINKY_MCP -> THUMB_TIP. Verifie numeriquement contre le module reel : pour
        angle_deg dans ]-180, 180[, inclinaison_main(_main_pouce_incline(angle_deg))
        == angle_deg (a la precision flottante pres).

    Inputs:
        angle_deg (float): inclinaison signee voulue, degres, convention de
                           gesture_commands.inclinaison_main
        rayon (float): norme du vecteur impose, unites normalisees (n'affecte pas
                       l'angle, seulement pour rester loin de min_vector_norm)

    Outputs:
        points (list): 21 couples (x, y) normalises, pret pour reconnaitre()
    --------------------------------------------------------------------------
    """
    main = list(fm.main_pouce_leve())
    thumb_tip_x, thumb_tip_y = main[THUMB_TIP]
    theta = math.radians(angle_deg)
    # vecteur (pointe - base) impose = rayon * (sin(theta), -cos(theta)), la meme
    # convention que fabrique_mains._point_depuis_poignet (0 deg = vertical ascendant).
    main[PINKY_MCP] = (
        thumb_tip_x - rayon * math.sin(theta),
        thumb_tip_y + rayon * math.cos(theta),
    )
    return main


# ---------------------------------------------------------------------------
# 1. Arret d'urgence : paume ouverte, l'emporte sur tout.
# ---------------------------------------------------------------------------

def test_paume_ouverte_declenche_larret_durgence(devoir1_cfg, projet_cfg):
    """0 doigt replie -> arret d'urgence, urgence=True, twist nul."""
    geste = gesture_commands.reconnaitre(
        [fm.main_ouverte()], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )
    assert geste is not None
    assert geste.urgence is True
    assert geste.twist.linear_x == 0.0
    assert geste.twist.angular_z == 0.0


def test_paume_ouverte_en_deuxieme_main_declenche_quand_meme_larret(devoir1_cfg, projet_cfg):
    """
    L'ORDRE d'evaluation EST la regle de securite (gesture_commands.py, docstring de
    reconnaitre) : la paume ouverte est cherchee sur TOUTES les mains avant tout autre
    geste. Ici la premiere main est un pouce leve (qui commanderait normalement une
    rotation) et la SECONDE est une paume ouverte : l'arret d'urgence doit quand meme
    se declencher, et ne doit pas etre masque par le fait que "deux mains" est aussi
    un geste valide (avance).
    """
    geste = gesture_commands.reconnaitre(
        [fm.main_pouce_leve(), fm.main_ouverte()], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )
    assert geste is not None
    assert geste.urgence is True
    assert geste.twist == Twist(0.0, 0.0)


# ---------------------------------------------------------------------------
# 2. Deux mains (ni l'une ni l'autre ouverte) -> avance.
# ---------------------------------------------------------------------------

def test_deux_mains_ni_ouvertes_donnent_lavance(devoir1_cfg, projet_cfg):
    """Deux mains detectees, aucune paume ouverte -> avance, urgence=False, linear_x > 0."""
    geste = gesture_commands.reconnaitre(
        [fm.main_pouce_leve(), fm.main_pouce_leve()], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )
    assert geste is not None
    assert geste.urgence is False
    assert geste.twist.linear_x > 0.0


# ---------------------------------------------------------------------------
# 3. Une main, pouce leve, orientation droite -> zone morte, angular_z EXACTEMENT nul.
# ---------------------------------------------------------------------------

def test_pouce_leve_main_droite_est_dans_la_zone_morte(devoir1_cfg, projet_cfg):
    """
    Le rendu Projet2 commandait une rotation en PERMANENCE des qu'une main etait vue,
    meme immobile et droite (gesture_commands.py, en-tete). Ici, une main quasi
    verticale (inclinaison ~0 deg, bien en-deca de ZONE_MORTE_DEG=12) doit rendre une
    consigne angulaire EXACTEMENT nulle, pas seulement petite.
    """
    main = _main_pouce_incline(0.0)
    geste = gesture_commands.reconnaitre([main], IMG_W, IMG_H, devoir1_cfg, projet_cfg)
    assert geste is not None
    assert geste.nom == "pouce_leve_neutre"
    assert geste.twist.angular_z == 0.0


# ---------------------------------------------------------------------------
# 4. Inclinaison bien au-dela de la zone morte -> rotation non nulle et saturee.
# ---------------------------------------------------------------------------

def test_inclinaison_forte_donne_une_rotation_non_nulle_et_saturee(devoir1_cfg, projet_cfg):
    """
    Avec le gain PAR DEFAUT (0.5), la plus grande inclinaison possible (proche de 180
    deg) donne gain*pi = 1.57 rad/s, sous vitesse_angulaire_max (2.0) : la saturation
    ne se declenche donc jamais naturellement. Un gain agrandi est utilise ici pour
    l'exercer REELLEMENT, exactement comme pour navigator.calculer_consigne.
    """
    cfg = dict(projet_cfg)
    cfg["angular_gain"] = 50.0
    main = _main_pouce_incline(45.0)

    geste = gesture_commands.reconnaitre([main], IMG_W, IMG_H, devoir1_cfg, cfg)

    assert geste is not None
    assert geste.nom == "pouce_leve_rotation"
    assert geste.twist.angular_z != 0.0
    max_angulaire = float(cfg["vitesse_angulaire_max"])
    assert abs(geste.twist.angular_z) <= max_angulaire
    # Preuve que la borne a reellement clippe : 50.0 * radians(45) = 39.27, tres
    # au-dela de max_angulaire, donc la sortie doit toucher exactement la borne.
    assert abs(geste.twist.angular_z) == pytest.approx(max_angulaire)


# ---------------------------------------------------------------------------
# 5. Inclinaison a gauche vs a droite -> signes OPPOSES.
# ---------------------------------------------------------------------------

def test_inclinaison_a_gauche_et_a_droite_donnent_des_signes_opposes(devoir1_cfg, projet_cfg):
    """
    Le bug d'angle NON SIGNE des rendus etudiants aurait donne le meme signe des deux
    cotes (gesture_commands.py, commentaire dans inclinaison_main). Ici, +45 deg et
    -45 deg doivent produire des vitesses angulaires de signe STRICTEMENT oppose, pas
    seulement non nulles.
    """
    main_gauche = _main_pouce_incline(45.0)
    main_droite = _main_pouce_incline(-45.0)

    geste_gauche = gesture_commands.reconnaitre(
        [main_gauche], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )
    geste_droite = gesture_commands.reconnaitre(
        [main_droite], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )

    assert geste_gauche.twist.angular_z > 0.0
    assert geste_droite.twist.angular_z < 0.0
    assert geste_gauche.twist.angular_z == pytest.approx(-geste_droite.twist.angular_z)


# ---------------------------------------------------------------------------
# 6. Aucune main, ou une main qui n'est ni ouverte ni pouce leve -> None.
# ---------------------------------------------------------------------------

def test_aucune_main_rend_none(devoir1_cfg, projet_cfg):
    """Liste de mains vide -> aucune consigne, la modalite se tait."""
    assert gesture_commands.reconnaitre([], IMG_W, IMG_H, devoir1_cfg, projet_cfg) is None


def test_une_main_ni_ouverte_ni_pouce_leve_rend_none(devoir1_cfg, projet_cfg):
    """Un poing ferme (rien n'est deploye) n'est ni un arret d'urgence ni un pouce
    leve : aucune consigne."""
    geste = gesture_commands.reconnaitre(
        [fm.main_poing_ferme()], IMG_W, IMG_H, devoir1_cfg, projet_cfg
    )
    assert geste is None


# ---------------------------------------------------------------------------
# 7. inclinaison_main sur un cas degenere -> None, jamais une exception ni 0.0.
# ---------------------------------------------------------------------------

def test_inclinaison_main_degeneree_rend_none(devoir1_cfg):
    """
    Pouce et base de l'auriculaire confondus -> vecteur nul -> angle indetermine.
    Doit rendre None explicitement, jamais 0.0 (qui se lirait a tort comme "main
    droite") ni lever d'exception.
    """
    main = list(fm.main_pouce_leve())
    main[PINKY_MCP] = main[THUMB_TIP]

    angle = gesture_commands.inclinaison_main(
        main, IMG_W, IMG_H, float(devoir1_cfg["min_vector_norm"])
    )

    assert angle is None
