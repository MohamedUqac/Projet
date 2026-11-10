"""
test_object_tracker.py - Preuves du contrat d'object_tracker.py (Projet, 6MIG841).

`detections_depuis_resultat` est une fonction PURE et sans etat : elle recoit un faux
resultat Ultralytics (faux_yolo.py) et rend des Detection, jamais de modele charge ni
de camera ouverte (workflow.md R5). `ObjectTracker` lui-meme n'est jamais construit
sans y injecter un `model=` factice : charger de vrais poids YOLO dans un test est
interdit par la consigne de ce chantier.
"""

from __future__ import annotations

import pytest

import faux_yolo as fy
from ihr_ros.geometry import image_to_turtlesim
from object_tracker import (
    Detection,
    ObjectTracker,
    _coordonnees,
    choisir_meilleure,
    detections_depuis_resultat,
)

NOMS = {0: "cell phone", 1: "banana"}
IMG_W, IMG_H = 640, 480
CANVAS = 10.0  # canevas carre arbitraire : simplifie l'arithmetique de conversion.


# ---------------------------------------------------------------------------
# 1. Filtrage par classe et par confiance : deux controles negatifs distincts.
# ---------------------------------------------------------------------------

def test_boite_de_la_bonne_classe_sous_le_seuil_est_ecartee():
    """
    Une boite de la classe VOULUE mais sous confiance_min doit disparaitre : c'est le
    deuxieme defaut des rendus etudiants (object_tracker.py, en-tete) qui laissait
    passer des detections a 0,26 de confiance.
    """
    boite = fy.boite_nombres(classe_index=0, confiance=0.10,
                             xyxy=(300.0, 220.0, 340.0, 260.0))
    resultat = fy.FauxResultat(boxes=[boite])

    detections = detections_depuis_resultat(
        resultat, NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H,
        canvas_width=CANVAS, canvas_height=CANVAS,
    )

    assert detections == []


def test_boite_confiante_de_la_mauvaise_classe_est_ecartee():
    """Une boite AU-DESSUS du seuil mais d'une classe non voulue ne doit pas passer
    (l'ancien code cherchait une etiquette figee en dur, object_tracker.py, defaut n 1)."""
    boite = fy.boite_nombres(classe_index=1, confiance=0.90,
                             xyxy=(300.0, 220.0, 340.0, 260.0))
    resultat = fy.FauxResultat(boxes=[boite])

    detections = detections_depuis_resultat(
        resultat, NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H,
        canvas_width=CANVAS, canvas_height=CANVAS,
    )

    assert detections == []


# ---------------------------------------------------------------------------
# 2. Conversion de coordonnees : le centre de l'image tombe au centre du canevas, et
#    l'axe y est INVERSE (haut de l'image -> y ELEVE en turtlesim).
# ---------------------------------------------------------------------------

def test_boite_centree_dans_limage_tombe_au_centre_du_canevas():
    """
    Boite centree en (320, 240) sur une image 640x480 -> centre exact de l'image.
    x_unit = (320/640)*10 = 5.0 ; y_unit = ((480-240)/480)*10 = 5.0 : le milieu du
    canevas carre de cote 10.
    """
    boite = fy.boite_nombres(classe_index=0, confiance=0.90,
                             xyxy=(300.0, 220.0, 340.0, 260.0))  # centre (320, 240)
    resultat = fy.FauxResultat(boxes=[boite])

    detections = detections_depuis_resultat(
        resultat, NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H,
        canvas_width=CANVAS, canvas_height=CANVAS,
    )

    assert len(detections) == 1
    assert detections[0].centre_turtlesim == pytest.approx((5.0, 5.0))


def test_boite_en_haut_de_limage_donne_un_y_eleve_en_turtlesim():
    """
    C'est LA source d'erreur la plus frequente du Projet (ihr_ros.geometry.
    image_to_turtlesim, docstring) : l'origine image est en haut a gauche, celle de
    turtlesim en bas a gauche. Boite centree en (320, 10), proche du haut de l'image :
    x_unit = (320/640)*10 = 5.0 ;
    y_unit = ((480-10)/480)*10 = (470/480)*10 = 9.791666... , PRES DU MAXIMUM du
    canevas (10.0), et non pres de zero comme le donnerait une conversion non inversee.
    """
    boite = fy.boite_nombres(classe_index=0, confiance=0.90,
                             xyxy=(300.0, 0.0, 340.0, 20.0))  # centre (320, 10)
    resultat = fy.FauxResultat(boxes=[boite])

    detections = detections_depuis_resultat(
        resultat, NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H,
        canvas_width=CANVAS, canvas_height=CANVAS,
    )

    assert len(detections) == 1
    x_unit, y_unit = detections[0].centre_turtlesim
    assert x_unit == pytest.approx(5.0)
    assert y_unit == pytest.approx(470.0 / 480.0 * 10.0)
    assert y_unit > 9.0  # nettement au-dessus du centre (5.0), pres du bord haut.


def test_image_to_turtlesim_est_coherente_avec_object_tracker():
    """Controle croise direct sur ihr_ros.geometry.image_to_turtlesim, la fonction que
    detections_depuis_resultat appelle pour chaque boite retenue."""
    assert image_to_turtlesim((320.0, 240.0), IMG_W, IMG_H, CANVAS, CANVAS) == \
        pytest.approx((5.0, 5.0))


# ---------------------------------------------------------------------------
# 3. choisir_meilleure : la plus confiante gagne, jamais la derniere de la liste.
# ---------------------------------------------------------------------------

def test_choisir_meilleure_retient_la_plus_confiante_pas_la_derniere():
    """
    Le troisieme defaut des rendus etudiants (object_tracker.py, en-tete) : quand
    plusieurs objets de la bonne classe sont visibles, le DERNIER de la boucle
    gagnait, ce qui n'est pas un choix mais l'ordre d'iteration de YOLO. La detection
    la moins confiante est placee EN DERNIER ici, pour qu'une implementation qui
    renverrait le dernier element echoue ce test.
    """
    plus_confiante = Detection("cell phone", 0.91, (0, 0, 1, 1), (0.5, 0.5), (5.0, 5.0))
    moins_confiante = Detection("cell phone", 0.20, (0, 0, 1, 1), (0.5, 0.5), (5.0, 5.0))

    resultat = choisir_meilleure([plus_confiante, moins_confiante])

    assert resultat is plus_confiante


def test_choisir_meilleure_sur_liste_vide_rend_none():
    """Aucune detection sur la trame -> None, jamais une exception."""
    assert choisir_meilleure([]) is None


# ---------------------------------------------------------------------------
# 4. Les deux formes de boite (nombres nus, tenseur) rendent des resultats identiques.
# ---------------------------------------------------------------------------

def test_boite_nombres_et_boite_tenseur_donnent_les_memes_detections():
    """
    _scalaire et _coordonnees acceptent un nombre nu OU un objet porteur de
    .item()/.tolist() (un vrai tenseur PyTorch). Les deux formes de boite doivent
    produire exactement la meme Detection : ni l'une ni l'autre n'est un cas special.
    """
    xyxy = (300.0, 220.0, 340.0, 260.0)
    boite_plate = fy.boite_nombres(classe_index=0, confiance=0.83, xyxy=xyxy)
    boite_tenseur = fy.boite_tenseur(classe_index=0, confiance=0.83, xyxy=xyxy)

    detections_plates = detections_depuis_resultat(
        fy.FauxResultat(boxes=[boite_plate]), NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H, canvas_width=CANVAS, canvas_height=CANVAS,
    )
    detections_tenseur = detections_depuis_resultat(
        fy.FauxResultat(boxes=[boite_tenseur]), NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H, canvas_width=CANVAS, canvas_height=CANVAS,
    )

    assert detections_plates == detections_tenseur
    assert len(detections_plates) == 1


# ---------------------------------------------------------------------------
# 5. Chemin d'echec : une boite xyxy mal formee leve ValueError.
# ---------------------------------------------------------------------------

def test_coordonnees_a_trois_valeurs_leve_valueerror():
    """_coordonnees exige exactement 4 valeurs (xyxy) : 3 valeurs est un format invalide."""
    with pytest.raises(ValueError):
        _coordonnees((1.0, 2.0, 3.0))


# ---------------------------------------------------------------------------
# 6. Un resultat sans boites du tout ne fait pas planter la fonction.
# ---------------------------------------------------------------------------

def test_resultat_sans_attribut_boxes_rend_une_liste_vide():
    """
    `getattr(resultat, "boxes", None) or []` : un resultat qui ne porte MEME PAS
    l'attribut boxes rend une liste vide, jamais une AttributeError.
    """
    detections = detections_depuis_resultat(
        fy.FauxResultatSansBoites(), NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H, canvas_width=CANVAS, canvas_height=CANVAS,
    )
    assert detections == []


def test_resultat_avec_liste_de_boites_vide_rend_une_liste_vide():
    """Meme comportement quand .boxes existe mais est une liste vide (trame sans rien
    a suivre)."""
    detections = detections_depuis_resultat(
        fy.FauxResultat(boxes=[]), NOMS, ["cell phone"], confiance_min=0.45,
        image_width=IMG_W, image_height=IMG_H, canvas_width=CANVAS, canvas_height=CANVAS,
    )
    assert detections == []


# ---------------------------------------------------------------------------
# 7. ObjectTracker : jamais construit sans modele injecte (consigne du chantier).
# ---------------------------------------------------------------------------

class _FauxModele:
    """Modele YOLO factice : porte .names et .predict(), jamais de poids reels."""

    def __init__(self, resultats):
        self.names = NOMS
        self._resultats = resultats

    def predict(self, frame, imgsz, conf, verbose=False):
        return self._resultats


class _FauxFrame:
    """Trame factice : seul `.shape` est lu par ObjectTracker.detecter."""

    shape = (IMG_H, IMG_W, 3)


def test_object_tracker_avec_modele_injecte_detecte_et_choisit(projet_cfg):
    """
    Construction complete d'ObjectTracker avec un modele FACTICE (jamais de vrais
    poids YOLO, consigne explicite de ce chantier) : verifie que .detecter() et
    .suivre() sont correctement cables sur detections_depuis_resultat et
    choisir_meilleure, avec les classes et le seuil de la configuration.
    """
    boite = fy.boite_nombres(classe_index=0, confiance=0.90,
                             xyxy=(300.0, 220.0, 340.0, 260.0))
    modele = _FauxModele(resultats=[fy.FauxResultat(boxes=[boite])])

    tracker = ObjectTracker(settings=projet_cfg, model=modele, classes=["cell phone"])

    assert tracker.classes == ("cell phone",)
    detections = tracker.detecter(_FauxFrame())
    assert len(detections) == 1
    assert detections[0].classe == "cell phone"
    assert tracker.suivre(_FauxFrame()) == detections[0]


def test_object_tracker_sans_classes_explicites_utilise_target_class_de_la_config(projet_cfg):
    """Sans `classes=`, ObjectTracker retombe sur projet.target_class ('cell phone')."""
    modele = _FauxModele(resultats=[fy.FauxResultat(boxes=[])])
    tracker = ObjectTracker(settings=projet_cfg, model=modele)
    assert tracker.classes == (str(projet_cfg["target_class"]),)
