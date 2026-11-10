"""
object_tracker.py - Detection de l'objet directeur par YOLO.

Projet de session. Enveloppe Ultralytics YOLO et rend la position de l'objet suivi,
convertie en coordonnees turtlesim.

Ce que faisaient les rendus etudiants
-------------------------------------
Les trois rendus appelaient `model.predict(frame)` puis parcouraient toutes les
boites a la recherche d'une etiquette figee dans le code : `'fork'` dans Projet1,
`"banana"` dans Projet2, `'cell phone'` dans le rendu EVIN. Quatre defauts :

  1. L'objet suivi est code en dur. Changer d'objet demande de modifier le code, ce
     qui, en seance, se fait dans la precipitation et casse autre chose.
  2. Aucun seuil de confiance n'est applique. YOLO rend volontiers une detection a
     0,26 de confiance, et la tortue part vers un reflet.
  3. Quand PLUSIEURS objets de la bonne classe sont visibles, le dernier de la
     boucle gagne. Ce n'est pas un choix, c'est l'ordre d'iteration de YOLO.
  4. Projet1 convertissait les pixels en unites turtlesim en divisant par 50, en
     dur. Ce 50 ne vaut que pour l'image de 550 pixels qu'ils configuraient.

Ici : la classe visee et le seuil viennent de la configuration, la detection la PLUS
CONFIANTE est retenue et le choix est explicite, et la conversion passe par
`ihr_ros.geometry.image_to_turtlesim`, qui prend les vraies dimensions de l'image.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ihr_ros import config
from ihr_ros.geometry import box_center, image_to_turtlesim


@dataclass(frozen=True)
class Detection:
    """Un objet detecte, en pixels et en unites turtlesim."""

    classe: str
    confiance: float
    boite: tuple[float, float, float, float]
    centre_px: tuple[float, float]
    centre_turtlesim: tuple[float, float]

    def describe(self) -> str:
        """Ligne courte pour l'affichage tete haute."""
        return (f"{self.classe} {self.confiance:.2f} -> "
                f"({self.centre_turtlesim[0]:.2f}, {self.centre_turtlesim[1]:.2f})")


def choisir_meilleure(detections: Sequence[Detection]) -> Detection | None:
    """
    --------------------------------------------------------------------------
    Purpose:
        Retenir la detection la plus confiante. Explicite, la ou les rendus
        etudiants laissaient gagner la derniere boite parcourue.

    Inputs:
        detections (Sequence): detections candidates

    Outputs:
        detection (Detection | None): la plus confiante, None si la liste est vide
    --------------------------------------------------------------------------
    """
    # Indice : retenir la detection de plus grande confiance, jamais la derniere parcourue
    # Tests : test_choisir_meilleure_retient_la_plus_confiante_pas_la_derniere, test_choisir_meilleure_sur_liste_vide_rend_none
    raise NotImplementedError(
        "fonction 'choisir_meilleure' a implementer (voir l'enonce et les tests cites)"
    )


def detections_depuis_resultat(resultat: Any,
                               noms: dict[int, str],
                               classes_voulues: Sequence[str],
                               confiance_min: float,
                               image_width: int,
                               image_height: int,
                               canvas_width: float,
                               canvas_height: float) -> list[Detection]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Transformer un resultat Ultralytics en detections filtrees et converties.
        Fonction libre, sans etat : c'est elle qui est testee, avec un faux
        resultat, donc sans charger le modele ni ouvrir la camera.

    Inputs:
        resultat (Any): un element de la liste rendue par model.predict
        noms (dict): index de classe -> nom, c'est-a-dire model.names
        classes_voulues (Sequence): noms de classes retenus
        confiance_min (float): confiance minimale acceptee
        image_width (int): largeur de l'image, pixels
        image_height (int): hauteur de l'image, pixels
        canvas_width (float): largeur du canevas turtlesim
        canvas_height (float): hauteur du canevas turtlesim

    Outputs:
        detections (list): detections retenues
    --------------------------------------------------------------------------
    """
    voulues = {str(c).lower() for c in classes_voulues}
    trouvees: list[Detection] = []

    for boite in getattr(resultat, "boxes", None) or []:
        index = int(_scalaire(boite.cls))
        classe = str(noms.get(index, index))
        if classe.lower() not in voulues:
            continue
        confiance = float(_scalaire(boite.conf))
        if confiance < confiance_min:
            continue

        x1, y1, x2, y2 = (float(v) for v in _coordonnees(boite.xyxy))
        centre_px = box_center(x1, y1, x2, y2)
        trouvees.append(Detection(
            classe=classe,
            confiance=confiance,
            boite=(x1, y1, x2, y2),
            centre_px=centre_px,
            centre_turtlesim=image_to_turtlesim(
                centre_px, image_width, image_height, canvas_width, canvas_height
            ),
        ))
    return trouvees


def _scalaire(valeur: Any) -> float:
    """Lire un scalaire, que ce soit un tenseur, un tableau ou un nombre."""
    if hasattr(valeur, "item"):
        try:
            return float(valeur.item())
        except (ValueError, RuntimeError):
            pass
    try:
        return float(valeur[0])
    except (TypeError, IndexError):
        return float(valeur)


def _coordonnees(valeur: Any) -> Sequence[float]:
    """Lire quatre coordonnees, que ce soit un tenseur 1x4 ou une simple suite."""
    if hasattr(valeur, "tolist"):
        donnee = valeur.tolist()
    else:
        donnee = list(valeur)
    if donnee and isinstance(donnee[0], (list, tuple)):
        donnee = donnee[0]
    if len(donnee) != 4:
        raise ValueError(f"Boite attendue au format xyxy, {len(donnee)} valeurs recues.")
    return donnee


class ObjectTracker:
    """Detecteur d'objet directeur, adosse a Ultralytics YOLO."""

    def __init__(self,
                 settings: dict[str, Any] | None = None,
                 model: Any | None = None,
                 classes: Sequence[str] | None = None):
        """
        --------------------------------------------------------------------------
        Purpose:
            Charger le modele YOLO et fixer les classes suivies. Le modele est
            injectable pour que les tests n'aient rien a telecharger.

        Inputs:
            settings (dict | None): section projet, lue si absente
            model (Any | None): modele deja charge, sinon Ultralytics le charge
            classes (Sequence | None): classes suivies, sinon celles de la config

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._cfg = settings if settings is not None else config.section("projet")
        turtle_cfg = config.section("turtlesim")
        self._canvas = (float(turtle_cfg["canvas_width"]),
                        float(turtle_cfg["canvas_height"]))
        self._confiance = float(self._cfg["yolo_confidence"])
        self._imgsz = int(self._cfg["yolo_imgsz"])

        if classes is not None:
            self._classes = [str(c) for c in classes]
        else:
            self._classes = [str(self._cfg["target_class"])]
        if not self._classes:
            raise ValueError(
                "Aucune classe a suivre. Renseigner projet.target_class, ou passer "
                "--classes sur la ligne de commande."
            )

        if model is not None:
            self._model = model
        else:
            from ultralytics import YOLO  # noqa: PLC0415

            chemin = self._resoudre_modele(str(self._cfg["yolo_model"]))
            self._model = YOLO(str(chemin))

    @staticmethod
    def _resoudre_modele(nom: str) -> Path:
        """
        --------------------------------------------------------------------------
        Purpose:
            Chercher le poids YOLO dans le repertoire de modeles du laboratoire
            avant de laisser Ultralytics le telecharger dans le repertoire courant.
            Sans cela, chaque etudiant qui lance le projet depuis un dossier
            different retelecharge le modele a cet endroit.

        Inputs:
            nom (str): nom du fichier de poids, par exemple yolo11n.pt

        Outputs:
            chemin (Path): chemin local s'il existe, sinon le nom tel quel
        --------------------------------------------------------------------------
        """
        from ihr_ros.hands import model_dir  # noqa: PLC0415

        local = model_dir() / nom
        return local if local.is_file() else Path(nom)

    @property
    def classes(self) -> tuple[str, ...]:
        """Classes actuellement suivies."""
        return tuple(self._classes)

    @property
    def noms_modele(self) -> dict[int, str]:
        """Table index -> nom de classe du modele charge."""
        return dict(self._model.names)

    def detecter(self, frame) -> list[Detection]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Detecter les objets suivis dans une trame BGR.

        Inputs:
            frame (ndarray): trame BGR issue d'OpenCV

        Outputs:
            detections (list): detections retenues, non triees
        --------------------------------------------------------------------------
        """
        height, width = frame.shape[:2]
        resultats = self._model.predict(
            frame, imgsz=self._imgsz, conf=self._confiance, verbose=False
        )
        detections: list[Detection] = []
        for resultat in resultats:
            detections.extend(detections_depuis_resultat(
                resultat, self.noms_modele, self._classes, self._confiance,
                width, height, self._canvas[0], self._canvas[1],
            ))
        return detections

    def suivre(self, frame) -> Detection | None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Detecter puis retenir la meilleure detection d'une trame.

        Inputs:
            frame (ndarray): trame BGR issue d'OpenCV

        Outputs:
            detection (Detection | None): la plus confiante, None si aucune
        --------------------------------------------------------------------------
        """
        return choisir_meilleure(self.detecter(frame))
