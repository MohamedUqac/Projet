"""
test_perception_nodes.py - Projet, plan07 : gesture_node et object_node.

Scinde de test_noeuds_projet.py (2026-09-19) pour rester sous 400 lignes (workflow.md) :
ce fichier couvre les DEUX noeuds de PERCEPTION minces, l'autre couvre arbiter_node et
les fonctions pures de conversion.

Hors ligne AU SENS FORT (meme protocole que Devoir2/test/test_noeuds.py) : le contexte
rclpy est initialise SANS GRAPHE, les noeuds sont instancies et leurs rappels appeles EN
DIRECT, camera et detecteur/tracker sont des faux injectes. Aucune webcam, aucun
MediaPipe, aucun modele YOLO.

Saute proprement dans le .venv, ou rclpy et le paquet d'interfaces sont absents
(workflow.md R5) : c'est un SAUT ANNONCE, jamais un echec.
"""

from __future__ import annotations

from typing import Any

import pytest

rclpy = pytest.importorskip(
    "rclpy",
    reason="ROS2 (rclpy) absent : suite des noeuds du Projet sautee dans le .venv (workflow.md R5).",
)
pytest.importorskip(
    "ihr_6mig841_interfaces.msg",
    reason="paquet ihr_6mig841_interfaces non construit (colcon build requis, plan01.md).",
)

import fabrique_mains as fm  # noqa: E402
from gesture_node import GestureNode  # noqa: E402
from ihr_ros.hands import TrackedHand  # noqa: E402
from object_node import ObjectNode  # noqa: E402
from object_tracker import Detection  # noqa: E402


@pytest.fixture
def contexte_rclpy():
    """Contexte rclpy isole par test : aucun graphe partage entre deux tests."""
    contexte = rclpy.Context()
    rclpy.init(context=contexte)
    yield contexte
    rclpy.shutdown(context=contexte)


class _EditeurFactice:
    """Faux editeur ROS2 : n'enregistre que les messages publies."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    def publish(self, message: Any) -> None:
        self.messages.append(message)


class _CameraFactice:
    """Fausse camera : rend une seule trame (un objet portant .shape), ou aucune."""

    def __init__(self, largeur: int = 640, hauteur: int = 480, rend_une_trame: bool = True) -> None:
        self._rend_une_trame = rend_une_trame
        self.shape = (hauteur, largeur, 3)

    def read(self) -> tuple[bool, Any]:
        if not self._rend_une_trame:
            return False, None
        return True, self


class _TrackerMainsFactice:
    """Faux HandTracker : rend les mains de `mains`, quelle que soit la trame."""

    def __init__(self, mains: list[list[tuple[float, float]]]) -> None:
        self._mains = mains

    def process(self, frame: Any) -> list[TrackedHand]:
        return [TrackedHand(landmarks=main, handedness="inconnue", score=1.0) for main in self._mains]


class _TrackerObjetFactice:
    """Faux ObjectTracker : rend `detection` a chaque appel, quelle que soit la trame."""

    def __init__(self, detection: Detection | None) -> None:
        self._detection = detection

    def suivre(self, frame: Any) -> Detection | None:
        return self._detection


# ---------------------------------------------------------------------------
# 5. Paume ouverte en SECONDE main : gesture_node publie quand meme l'urgence.
# ---------------------------------------------------------------------------

def test_gesture_node_publie_lurgence_meme_paume_en_seconde_main(contexte_rclpy, devoir1_cfg,
                                                                 projet_cfg, topics_cfg):
    mains = [fm.main_pouce_leve(), fm.main_ouverte()]
    camera = _CameraFactice()
    tracker = _TrackerMainsFactice(mains)
    editeur = _EditeurFactice()
    node = GestureNode(
        camera=camera, tracker=tracker, devoir1_cfg=devoir1_cfg, projet_cfg=projet_cfg,
        topics=topics_cfg, pub_gesture=editeur, horloge=lambda: 7.0, context=contexte_rclpy,
    )
    try:
        node._percevoir_et_publier()

        assert len(editeur.messages) == 1
        message = editeur.messages[0]
        assert message.urgence is True
        assert message.linear_x == 0.0
        assert message.angular_z == 0.0
        assert message.instant == 7.0
    finally:
        node.destroy_node()


def test_gesture_node_ne_publie_rien_sans_trame(contexte_rclpy, devoir1_cfg, projet_cfg, topics_cfg):
    camera = _CameraFactice(rend_une_trame=False)
    editeur = _EditeurFactice()
    node = GestureNode(
        camera=camera, tracker=_TrackerMainsFactice([]), devoir1_cfg=devoir1_cfg,
        projet_cfg=projet_cfg, topics=topics_cfg, pub_gesture=editeur, context=contexte_rclpy,
    )
    try:
        node._percevoir_et_publier()
        assert editeur.messages == []
    finally:
        node.destroy_node()


# ---------------------------------------------------------------------------
# object_node : traversee ROS2 d'une Detection, sans calcul de mouvement.
# ---------------------------------------------------------------------------

def test_object_node_publie_la_detection_convertie(contexte_rclpy, projet_cfg, topics_cfg):
    detection = Detection(classe="cell phone", confiance=0.8, boite=(0.0, 0.0, 10.0, 10.0),
                          centre_px=(5.0, 5.0), centre_turtlesim=(3.0, 4.0))
    editeur = _EditeurFactice()
    node = ObjectNode(
        camera=_CameraFactice(), tracker=_TrackerObjetFactice(detection),
        projet_cfg=projet_cfg, topics=topics_cfg, pub_target=editeur,
        horloge=lambda: 9.0, context=contexte_rclpy,
    )
    try:
        node._percevoir_et_publier()

        assert len(editeur.messages) == 1
        message = editeur.messages[0]
        assert message.classe == "cell phone"
        assert message.x == 3.0
        assert message.y == 4.0
        assert message.instant == 9.0
    finally:
        node.destroy_node()


def test_object_node_ne_publie_rien_sans_detection(contexte_rclpy, projet_cfg, topics_cfg):
    editeur = _EditeurFactice()
    node = ObjectNode(
        camera=_CameraFactice(), tracker=_TrackerObjetFactice(None),
        projet_cfg=projet_cfg, topics=topics_cfg, pub_target=editeur, context=contexte_rclpy,
    )
    try:
        node._percevoir_et_publier()
        assert editeur.messages == []
    finally:
        node.destroy_node()
