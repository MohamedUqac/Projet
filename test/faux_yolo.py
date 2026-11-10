"""
faux_yolo.py - Faux resultats Ultralytics YOLO pour les tests d'object_tracker.py.

`object_tracker.detections_depuis_resultat` ne lit que trois attributs d'une boite :
`.cls`, `.conf` et `.xyxy`. Les fonctions privees `_scalaire` et `_coordonnees`
acceptent chacune DEUX formes pour ces valeurs :

  - un nombre nu (ou une simple sequence indexable), comme le rendrait un modele
    charge sans torch, ou une boite deja convertie en nombres Python,
  - un objet porteur de `.item()` (scalaires) ou `.tolist()` (coordonnees), comme le
    rend un vrai tenseur PyTorch pour `boite.cls`, `boite.conf` et `boite.xyxy`.

Ce module fournit les deux formes, SANS jamais importer torch ni ultralytics, pour que
les tests tournent sans GPU, sans poids telecharges et sans reseau (workflow.md R5).

Ce fichier n'est PAS un module de test : aucune fonction ni classe ne s'appelle
`test_*`, pytest ne le collecte donc pas comme suite. Il est importe par
test_object_tracker.py (`import faux_yolo` ou `from faux_yolo import ...`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class FauxScalaireTenseur:
    """
    Imite un tenseur 0-D ou 1-D porteur de `.item()`, comme `boite.cls` ou
    `boite.conf` chez un vrai resultat Ultralytics. `_scalaire` essaie `.item()` en
    premier : c'est cette branche que cette classe exerce.
    """

    valeur: float

    def item(self) -> float:
        return float(self.valeur)


@dataclass
class FauxCoordonneesTenseur:
    """
    Imite un tenseur de forme (1, 4) porteur de `.tolist()`, comme `boite.xyxy` pour
    UNE boite chez un vrai resultat Ultralytics (`.tolist()` rend alors une liste
    imbriquee `[[x1, y1, x2, y2]]`, pas une liste plate). `_coordonnees` deballe
    exactement cette imbrication (`donnee = donnee[0]` quand le premier element est
    lui-meme une liste ou un tuple) : c'est cette branche que cette classe exerce.
    """

    x1: float
    y1: float
    x2: float
    y2: float

    def tolist(self) -> list[list[float]]:
        return [[self.x1, self.y1, self.x2, self.y2]]


@dataclass
class BoiteNombres:
    """Boite au format le plus simple : cls/conf en nombres nus, xyxy en tuple plat.
    Ni `.item()` ni `.tolist()` : exerce la branche « nombre nu » de _scalaire et
    _coordonnees (le `list(valeur)` puis renvoi direct, sans deballage imbrique)."""

    cls: float
    conf: float
    xyxy: tuple[float, float, float, float]


@dataclass
class BoiteTenseur:
    """Boite au format tenseur : cls et conf portent `.item()`, xyxy porte `.tolist()`
    en forme (1, 4). Exerce l'autre branche de _scalaire et _coordonnees."""

    cls: FauxScalaireTenseur
    conf: FauxScalaireTenseur
    xyxy: FauxCoordonneesTenseur


def boite_nombres(classe_index: int, confiance: float,
                  xyxy: tuple[float, float, float, float]) -> BoiteNombres:
    """Construire une boite en nombres nus (aucun `.item()`, aucun `.tolist()`)."""
    return BoiteNombres(cls=float(classe_index), conf=float(confiance), xyxy=xyxy)


def boite_tenseur(classe_index: int, confiance: float,
                  xyxy: tuple[float, float, float, float]) -> BoiteTenseur:
    """Construire une boite au format tenseur (cls/conf via .item(), xyxy via .tolist())."""
    x1, y1, x2, y2 = xyxy
    return BoiteTenseur(
        cls=FauxScalaireTenseur(float(classe_index)),
        conf=FauxScalaireTenseur(float(confiance)),
        xyxy=FauxCoordonneesTenseur(x1, y1, x2, y2),
    )


@dataclass
class FauxResultat:
    """Imite un element de la liste que rend `model.predict(...)` : porte un attribut
    `.boxes`, iterable de boites. Une liste vide simule une trame sans detection."""

    boxes: Sequence = field(default_factory=list)


class FauxResultatSansBoites:
    """
    Resultat degenere qui ne porte MEME PAS l'attribut `boxes`.

    `detections_depuis_resultat` le lit via `getattr(resultat, "boxes", None) or []`,
    justement pour survivre a ce cas sans lever AttributeError. Un vrai resultat
    Ultralytics porte toujours `.boxes`, mais un objet mal forme (erreur amont, faux
    modele incomplet dans un autre test) ne doit pas faire planter le suivi d'objet.
    """
