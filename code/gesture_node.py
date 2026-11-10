"""
gesture_node.py - Projet, noeud ROS2 : perception des gestes de la main.

Mince (plan07.md, table des trois noeuds ajoutes) : il percoit une trame webcam,
appelle `gesture_commands.reconnaitre` (Devoir 1 + Projet, REUTILISES SANS
MODIFICATION) et publie le geste reconnu sur `topics.gesture_topic`. La DECISION
reste entierement dans `gesture_commands.py` : ce noeud ne fait que la traversee
ROS2 de son resultat, exactement comme `dialogue_manager_node.py` fait la traversee
ROS2 de `state_machine.py`.

La camera et le detecteur de mains sont injectables pour les tests hors ligne
(workflow.md R5) : aucune webcam ni MediaPipe reel n'est requis pour prouver que ce
noeud publie le bon message a partir d'une trame et d'un suivi donnes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "Devoir1" / "code"))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402

from ihr_6mig841_interfaces.msg import Commande  # noqa: E402

from ihr_ros import config  # noqa: E402

import gesture_commands  # noqa: E402


class GestureNode(Node):
    """Perception du geste : une trame en entree, une Commande en sortie."""

    def __init__(self,
                 camera: Any | None = None,
                 tracker: Any | None = None,
                 devoir1_cfg: dict[str, Any] | None = None,
                 projet_cfg: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 pub_gesture: Any | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud. Camera, detecteur de mains et editeur sont
            injectables : quand camera ET tracker sont fournis, aucune webcam ni
            MediaPipe reel n'est ouvert (chemin de test).

        Inputs:
            camera (Any | None): objet portant .read() -> (ok, frame), une vraie
                cv2.VideoCapture si absente (chemin de production)
            tracker (Any | None): objet portant .process(frame) -> liste de mains
                avec un attribut .landmarks, un vrai HandTracker si absent
            devoir1_cfg (dict | None): section 'devoir1' de la configuration
            projet_cfg (dict | None): section 'projet' de la configuration
            topics (dict | None): section 'topics' de la configuration
            pub_gesture (Any | None): editeur du topic 'gesture_topic'
            horloge (callable): source de l'instant publie, injectee pour les
                tests (workflow.md, determinisme)
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("gesture_node", context=context)
        self._devoir1_cfg = devoir1_cfg if devoir1_cfg is not None else config.section("devoir1")
        self._projet_cfg = projet_cfg if projet_cfg is not None else config.section("projet")
        self._topics = topics if topics is not None else config.section("topics")
        self._horloge = horloge

        self._pub = pub_gesture if pub_gesture is not None else self.create_publisher(
            Commande, str(self._topics["gesture_topic"]), int(self._topics["queue_depth"]),
        )

        if camera is not None and tracker is not None:
            self._camera = camera
            self._tracker = tracker
        else:
            self._camera, self._tracker = self._ouvrir_perception_reelle()

        periode = float(self._projet_cfg["control_period_seconds"])
        self._minuterie = self.create_timer(periode, self._percevoir_et_publier)

    def _ouvrir_perception_reelle(self) -> tuple[Any, Any]:
        """Ouvrir la vraie webcam et le vrai HandTracker (chemin de production)."""
        import cv2  # noqa: PLC0415

        from ihr_ros.hands import HandTracker  # noqa: PLC0415

        camera_cfg = config.section("camera")
        camera = cv2.VideoCapture(int(camera_cfg["index"]))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera_cfg["frame_width"]))
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera_cfg["frame_height"]))
        if not camera.isOpened():
            raise RuntimeError(
                f"Camera '{camera_cfg['index']}' impossible a ouvrir. "
                "Verifier avec : python Lab1/code/check_env.py --camera"
            )
        tracker = HandTracker(
            max_hands=int(self._devoir1_cfg["max_num_hands"]),
            min_detection_confidence=float(self._devoir1_cfg["min_detection_confidence"]),
            min_tracking_confidence=float(self._devoir1_cfg["min_tracking_confidence"]),
        )
        return camera, tracker

    def _percevoir_et_publier(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Lire une trame, reconnaitre un geste, publier. Ne publie RIEN si la
            trame est absente ou si aucun geste n'est reconnu (gesture_commands
            rend None dans ce cas) : une minuterie qui publierait un geste
            inexistant inonderait l'arbitre de commandes vides.

        Inputs:
            aucun (rappel de minuterie)

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        ok, frame = self._camera.read()
        if not ok or frame is None:
            return
        hauteur, largeur = frame.shape[:2]

        mains = self._tracker.process(frame)
        geste = gesture_commands.reconnaitre(
            [main.landmarks for main in mains], largeur, hauteur,
            self._devoir1_cfg, self._projet_cfg,
        )
        if geste is None:
            return

        message = Commande()
        message.modalite = "geste"
        message.linear_x = float(geste.twist.linear_x)
        message.angular_z = float(geste.twist.angular_z)
        message.instant = float(self._horloge())
        message.motif = geste.describe()
        message.urgence = bool(geste.urgence)
        self._pub.publish(message)

    def close(self) -> None:
        """Fermer la camera et le detecteur. Rappelable sans effet si absents."""
        fermer_camera = getattr(self._camera, "release", None)
        if fermer_camera is not None:
            fermer_camera()
        fermer_tracker = getattr(self._tracker, "close", None)
        if fermer_tracker is not None:
            fermer_tracker()


def main(argv: list[str] | None = None) -> int:
    """
    --------------------------------------------------------------------------
    Purpose:
        Point d'entree du noeud.

    Inputs:
        argv (list[str] | None): arguments rclpy, ceux de la ligne de commande
            si absents

    Outputs:
        code (int): code de sortie du processus
    --------------------------------------------------------------------------
    """
    rclpy.init(args=argv)
    node = GestureNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
