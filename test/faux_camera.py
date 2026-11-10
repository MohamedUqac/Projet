"""
faux_camera.py - Fausse camera pour les tests des noeuds de perception du Projet.

`gesture_node` et `object_node` ne lisent qu'une chose sur la trame recue :
`frame.shape[:2]` (hauteur, largeur), pour convertir des coordonnees normalisees en
pixels (gesture_commands.reconnaitre) ou pour connaitre la taille de l'image
(object_tracker, non appele directement ici puisque le tracker est LUI AUSSI
injecte). Une fausse trame n'a donc besoin que d'un attribut `.shape`, jamais d'un
vrai tableau numpy : aucune camera, aucun OpenCV (workflow.md R5).

Ce fichier n'est PAS un module de test : aucune fonction ni classe ne s'appelle
`test_*`, pytest ne le collecte donc pas comme suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FauxCadre:
    """Imite une trame OpenCV : seul `.shape` est lu par les noeuds de ce plan."""

    largeur: int = 640
    hauteur: int = 480

    @property
    def shape(self) -> tuple[int, int, int]:
        return (self.hauteur, self.largeur, 3)


@dataclass
class FauxCamera:
    """
    Fausse cv2.VideoCapture : `.read()` rend les trames de `sequence`, dans
    l'ordre, puis repete indefiniment la derniere. Une sequence vide simule une
    camera qui ne rend jamais de trame valide (`ok=False`).
    """

    sequence: list[Any] = field(default_factory=lambda: [FauxCadre()])
    lectures: int = field(default=0, init=False)

    def read(self) -> tuple[bool, Any | None]:
        if not self.sequence:
            return False, None
        index = min(self.lectures, len(self.sequence) - 1)
        self.lectures += 1
        return True, self.sequence[index]

    def release(self) -> None:
        pass
