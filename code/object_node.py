"""
object_node.py - Projet, noeud ROS2 : perception de l'objet directeur (YOLO).

Mince (plan07.md, table des trois noeuds ajoutes) : il percoit une trame webcam,
appelle `object_tracker.ObjectTracker.suivre` (Projet, REUTILISE SANS MODIFICATION)
et publie la detection sur `topics.target_topic`. Il ne calcule AUCUN mouvement :
la conversion detection -> consigne de vitesse est le travail de `navigator.py`,
reutilise par `arbiter_node` seul (plan07.md, table des trois noeuds ajoutes), une
fois la position de l'objet ET la pose courante de la tortue toutes deux disponibles.

La camera et le suivi d'objet sont injectables pour les tests hors ligne
(workflow.md R5) : aucune webcam ni modele YOLO reel n'est requis pour prouver que
ce noeud publie le bon message a partir d'une detection donnee.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402

from ihr_6mig841_interfaces.msg import Cible  # noqa: E402

from ihr_ros import config  # noqa: E402

from object_tracker import ObjectTracker  # noqa: E402


class ObjectNode(Node):
    """Perception de l'objet : une trame en entree, une Cible en sortie."""

    def __init__(self,
                 camera: Any | None = None,
                 tracker: Any | None = None,
                 projet_cfg: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 pub_target: Any | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire le noeud. Camera et suivi d'objet sont injectables : quand
            camera ET tracker sont fournis, aucune webcam ni modele YOLO reel
            n'est ouvert (chemin de test).

        Inputs:
            camera (Any | None): objet portant .read() -> (ok, frame), une vraie
                cv2.VideoCapture si absente (chemin de production)
            tracker (Any | None): objet portant .suivre(frame) -> Detection|None,
                un vrai ObjectTracker (YOLO) si absent
            projet_cfg (dict | None): section 'projet' de la configuration
            topics (dict | None): section 'topics' de la configuration
            pub_target (Any | None): editeur du topic 'target_topic'
            horloge (callable): source de l'instant publie, injectee pour les
                tests (workflow.md, determinisme)
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("object_node", context=context)
        self._projet_cfg = projet_cfg if projet_cfg is not None else config.section("projet")
        self._topics = topics if topics is not None else config.section("topics")
        self._horloge = horloge

        self._pub = pub_target if pub_target is not None else self.create_publisher(
            Cible, str(self._topics["target_topic"]), int(self._topics["queue_depth"]),
        )

        if camera is not None and tracker is not None:
            self._camera = camera
            self._tracker = tracker
        else:
            self._camera = camera if camera is not None else self._ouvrir_camera_reelle()
            self._tracker = tracker if tracker is not None else ObjectTracker(self._projet_cfg)

        periode = float(self._projet_cfg["control_period_seconds"])
        self._minuterie = self.create_timer(periode, self._percevoir_et_publier)

    def _ouvrir_camera_reelle(self) -> Any:
        """Ouvrir la vraie webcam (chemin de production)."""
        import cv2  # noqa: PLC0415

        camera_cfg = config.section("camera")
        camera = cv2.VideoCapture(int(camera_cfg["index"]))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera_cfg["frame_width"]))
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera_cfg["frame_height"]))
        if not camera.isOpened():
            raise RuntimeError(
                f"Camera '{camera_cfg['index']}' impossible a ouvrir. "
                "Verifier avec : python Lab1/code/check_env.py --camera"
            )
        return camera

    def _percevoir_et_publier(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Lire une trame, detecter l'objet directeur, publier. Ne publie RIEN
            si la trame est absente ou si aucun objet n'est detecte (suivre rend
            None dans ce cas) : une minuterie qui publierait une cible fantome
            laisserait l'arbitre naviguer vers une position perimee.

        Inputs:
            aucun (rappel de minuterie)

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        ok, frame = self._camera.read()
        if not ok or frame is None:
            return

        detection = self._tracker.suivre(frame)
        if detection is None:
            return

        message = Cible()
        message.classe = str(detection.classe)
        message.confiance = float(detection.confiance)
        message.x = float(detection.centre_turtlesim[0])
        message.y = float(detection.centre_turtlesim[1])
        message.instant = float(self._horloge())
        self._pub.publish(message)

    def close(self) -> None:
        """Fermer la camera. Rappelable sans effet si absente."""
        fermer_camera = getattr(self._camera, "release", None)
        if fermer_camera is not None:
            fermer_camera()


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
    node = ObjectNode()
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
