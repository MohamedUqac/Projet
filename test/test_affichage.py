"""
Tests de `projet_turtle.construire_lignes`, l'affichage tete haute du Projet.

Cette fonction est la seule partie testable de `projet_turtle.py` : tout le reste ouvre
la camera, charge des modeles ou lance un fil. Son import est sur, mesure le 2026-09-18 :
`import projet_turtle` ne charge ni cv2, ni mediapipe, ni ultralytics, ni rclpy, tous
importes paresseusement dans les fonctions qui en ont besoin.

Ce qu'elle porte n'est pas cosmetique. Le rendu etudiant `banano.py` arbitrait entre la
main et la banane par un `if/elif` dont l'ecran ne disait rien : un spectateur voyait la
tortue changer de comportement sans pouvoir savoir pourquoi. Ces lignes sont la reponse a
ce defaut, donc elles font partie de la solution et sont testees comme telles.
"""

from __future__ import annotations

import pytest

from arbiter import Arbitrage
from gesture_commands import Geste
from ihr_ros.backends.base import Pose, Twist
from ihr_ros.overlay import GREEN, RED
from navigator import Consigne
from object_tracker import Detection
from projet_turtle import construire_lignes

# Deux lignes d'en-tete sont toujours presentes : l'arbitrage et l'etat de la tortue.
LIGNES_ENTETE = 2
# Puis une ligne geste et une ligne objet, toujours emises meme quand il n'y a rien.
LIGNES_TOUJOURS = LIGNES_ENTETE + 2


@pytest.fixture
def pose():
    """Pose de depart de turtlesim, au centre du canevas."""
    return Pose(x=5.544, y=5.544, theta=0.0)


@pytest.fixture
def arbitrage_voix():
    """Arbitrage nominal : la voix commande, l'objet est ecarte."""
    return Arbitrage(Twist(2.0, 0.0), "voix", "commande vocale « avancer »",
                     candidates=("objet", "voix"), perimees=())


def texte(lignes) -> str:
    """Concatener le texte des lignes, sans les couleurs."""
    return "\n".join(t for t, _couleur in lignes)


def test_sans_geste_sans_objet_les_quatre_lignes_sont_la(pose, arbitrage_voix):
    """Une trame sans geste et sans objet produit quand meme ses quatre lignes."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    assert len(lignes) == LIGNES_TOUJOURS
    assert "aucun" in texte(lignes)


def test_la_ligne_arbitrage_nomme_la_modalite_retenue(pose, arbitrage_voix):
    """La premiere ligne dit qui commande, ce que banano.py ne disait jamais."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    assert "voix" in lignes[0][0]


def test_la_ligne_arbitrage_nomme_aussi_les_modalites_ecartees(pose, arbitrage_voix):
    """Savoir QUI a ete ecarte est ce qui rend l'arbitrage comprehensible en demo."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    assert "objet" in lignes[0][0]


def test_aucune_commande_valide_est_affichee_en_rouge(pose):
    """L'arret de securite doit sauter aux yeux, pas se confondre avec un etat normal."""
    arret = Arbitrage(Twist(0.0, 0.0), "aucune",
                      "aucune commande valide, arret par securite")
    lignes = construire_lignes(arret, None, None, None, 13.0, pose)
    assert lignes[0][1] == RED


def test_une_modalite_active_est_affichee_en_vert(pose, arbitrage_voix):
    """Controle negatif du test precedent : sans lui, un rouge constant passerait."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    assert lignes[0][1] == GREEN


def test_un_geste_d_urgence_repasse_la_ligne_en_rouge(pose):
    """Un arret d'urgence est rouge meme si une modalite commande effectivement."""
    urgence = Arbitrage(Twist(0.0, 0.0), "geste", "URGENCE paume_ouverte")
    geste = Geste("paume_ouverte", Twist(0.0, 0.0), urgence=True,
                  detail="main ouverte devant la camera")
    lignes = construire_lignes(urgence, geste, None, None, 13.0, pose)
    assert lignes[0][1] == RED


def test_la_pose_de_la_tortue_est_affichee(pose, arbitrage_voix):
    """Sans la pose a l'ecran, on ne peut pas juger si l'asservissement converge."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    # La pose est formatee avec deux decimales : 5.544 s'affiche donc 5.54.
    assert "5.54" in lignes[1][0]


def test_la_cadence_est_affichee(pose, arbitrage_voix):
    """La cadence est le premier symptome d'une machine qui n'arrive plus a suivre."""
    lignes = construire_lignes(arbitrage_voix, None, None, None, 13.0, pose)
    assert "13.0" in lignes[1][0]


def test_une_detection_ajoute_sa_classe_et_sa_confiance(pose, arbitrage_voix):
    """La ligne objet doit nommer ce qui est suivi, pas seulement dire qu'il y a un objet."""
    detection = Detection(
        classe="cell phone", confiance=0.87, boite=(10.0, 20.0, 110.0, 220.0),
        centre_px=(60.0, 120.0), centre_turtlesim=(1.04, 8.31),
    )
    lignes = construire_lignes(arbitrage_voix, None, detection, None, 13.0, pose)
    contenu = texte(lignes)
    assert "cell phone" in contenu
    assert "0.87" in contenu


def test_une_consigne_ajoute_une_cinquieme_ligne(pose, arbitrage_voix):
    """La navigation n'apparait que lorsqu'une cible est poursuivie."""
    consigne = Consigne(Twist(1.0, 0.2), erreur_cap_rad=0.05,
                        distance_restante=3.2, arrivee=False, phase="approche")
    lignes = construire_lignes(arbitrage_voix, None, None, consigne, 13.0, pose)
    assert len(lignes) == LIGNES_TOUJOURS + 1
    assert "approche" in lignes[-1][0]


def test_un_geste_est_decrit_par_son_propre_describe(pose, arbitrage_voix):
    """L'affichage ne reformule pas le geste : une seule facon de le nommer."""
    geste = Geste("pouce_leve_rotation", Twist(0.0, 0.4), detail="inclinaison +45 deg")
    lignes = construire_lignes(arbitrage_voix, geste, None, None, 13.0, pose)
    assert geste.describe() in texte(lignes)


def test_chaque_ligne_est_un_couple_texte_couleur(pose, arbitrage_voix):
    """Contrat de la fonction : le dessinateur attend (str, (b, g, r))."""
    consigne = Consigne(Twist(1.0, 0.0), 0.0, 1.0, False, "approche")
    geste = Geste("avance_deux_mains", Twist(1.0, 0.0), detail="2 mains detectees")
    detection = Detection("fork", 0.5, (0.0, 0.0, 10.0, 10.0), (5.0, 5.0), (1.0, 1.0))
    lignes = construire_lignes(arbitrage_voix, geste, detection, consigne, 13.0, pose)
    for contenu, couleur in lignes:
        assert isinstance(contenu, str) and contenu
        assert isinstance(couleur, tuple) and len(couleur) == 3
        assert all(isinstance(canal, int) and 0 <= canal <= 255 for canal in couleur)
