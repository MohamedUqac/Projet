"""
arbiter_node.py - Projet, noeud ROS2 : arbitrage entre geste, voix et objet.

`arbiter_node` est le SEUL client de l'action ExecutePlan (plan07.md, « Qui commande
la tortue, et pourquoi un seul ») : `dialogue_manager_node` (Devoir 2, modifie par ce
plan) ne commande plus directement, il publie son intention et c'est ici qu'elle est
arbitree, exactement comme geste et objet. Deux clients de la meme action seraient
deux endroits ou l'arret d'urgence peut etre oublie.

Ce noeud reutilise SANS MODIFICATION `arbiter.Arbitre`/`arbiter.Commande` (la decision
de priorite et de peremption) et `navigator.calculer_consigne`/`navigator.LisseurCible`
(la conversion d'une detection d'objet en consigne de vitesse). La SEULE piece neuve
ici est la conversion d'une consigne continue (Twist) vers l'action discrete du
catalogue devoir2.actions la plus proche (`nom_action_depuis_twist`), necessaire parce
que Step.msg est FIGE et semantique (nom_action/is_forward/is_clockwise), jamais une
vitesse brute : motion_node (Devoir 2, inchange) est le SEUL endroit qui sache commander
la tortue (turtle_io), donc TOUT ce qui gagne l'arbitrage, geste, objet ou voix, doit
passer par une Step pour l'atteindre.

L'horodatage d'arbitrage est relu ICI, AU MOMENT DE DECIDER (`_arbitrer_et_commander`,
`self._horloge()` appele dans le rappel de minuterie), et non plus haut dans une trame
deja perimee : c'est la moitie applicative du defaut mesure le 2026-09-18 (l'autre
moitie, dans `arbiter.arbitrer`, est deja corrigee et inchangee par ce plan).

L'ARRET D'URGENCE (plan07.md) ne traverse aucun code special ici : une commande
d'urgence porte un twist NUL, `nom_action_depuis_twist` la lit donc comme 'arreter'
comme n'importe quelle autre consigne nulle, et le changement d'action declenche le
CANCEL du but courant AVANT tout nouvel envoi. C'est `arbiter.Arbitre`
(PRIORITE_ARRET_URGENCE, inchangee) qui garantit que l'urgence gagne toujours contre
une commande normale plus fraiche : ce fichier ne verifie jamais `commande.urgence`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rclpy  # noqa: E402
from rclpy.action import ActionClient  # noqa: E402
from rclpy.node import Node  # noqa: E402

from ihr_6mig841_interfaces.action import ExecutePlan  # noqa: E402
from ihr_6mig841_interfaces.msg import Cible, Commande as CommandeMsg, Step  # noqa: E402

from ihr_ros import config  # noqa: E402
from ihr_ros.backends.base import Twist  # noqa: E402
from ihr_ros.turtle_io import open_turtle  # noqa: E402

from arbiter import Arbitrage, Arbitre, Commande, JournalArbitrage  # noqa: E402
from navigator import LisseurCible, calculer_consigne  # noqa: E402


def nom_action_depuis_twist(twist: Twist, actions_cfg: dict[str, Any]) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Choisir l'action DISCRETE du catalogue devoir2.actions la plus proche
        d'une consigne continue. Necessaire parce que Step.msg est semantique
        (nom_action), jamais une vitesse brute (en-tete du module). Round-trip
        exact pour une consigne DEJA issue du catalogue (voix, via
        state_machine.signer()) : linear/angular nuls -> 'arreter', rotation
        dominante -> 'tourner' avec le sens du signe, sinon 'avancer'/'reculer'
        selon le signe de la vitesse lineaire. Pour geste et objet (consignes
        proportionnelles, non catalogables), c'est une approximation ASSUMEE :
        la magnitude precise (gain de cap, inclinaison de la main) est perdue,
        seule la NATURE du mouvement (avancer/reculer/tourner/arreter) survit,
        avec la duree et la distance PAR DEFAUT de cette action dans la
        configuration (motion_node.action_depuis_config, inchange).

    Inputs:
        twist (Twist): consigne continue retenue par l'arbitrage
        actions_cfg (dict): section devoir2.actions de la configuration

    Outputs:
        nom (str): 'avancer', 'reculer', 'tourner' ou 'arreter'
    --------------------------------------------------------------------------
    """
    for requis in ("avancer", "reculer", "tourner", "arreter"):
        if requis not in actions_cfg:
            raise KeyError(
                f"Action '{requis}' absente du catalogue devoir2.actions : "
                f"{sorted(actions_cfg)}. nom_action_depuis_twist exige les quatre "
                "actions de base."
            )

    if twist.linear_x == 0.0 and twist.angular_z == 0.0:
        return "arreter"
    if abs(twist.angular_z) > abs(twist.linear_x):
        return "tourner"
    return "avancer" if twist.linear_x > 0.0 else "reculer"


def etape_depuis_nom(nom: str, twist: Twist) -> Any:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire une Step ROS2 pour l'action nommee. distance_m et angle_deg
        restent a 0.0 : motion_node.action_depuis_config retrouve la grandeur
        PAR DEFAUT de cette action dans la configuration, exactement comme le
        fait deja dialogue_manager_node.step_depuis_action (Devoir 2, inchange).

    Inputs:
        nom (str): action du catalogue ('avancer', 'reculer', 'tourner', 'arreter')
        twist (Twist): consigne dont le SIGNE decide is_forward/is_clockwise

    Outputs:
        step (Step): message ROS2 pret pour un but ExecutePlan
    --------------------------------------------------------------------------
    """
    step = Step()
    step.nom_action = nom
    step.distance_m = 0.0
    step.angle_deg = 0.0
    step.is_forward = bool(twist.linear_x >= 0.0)
    step.is_clockwise = bool(twist.angular_z < 0.0)
    return step


class ArbiterNode(Node):
    """Arbitre les trois modalites et commande motion_node, seul client de l'action."""

    def __init__(self,
                 projet_cfg: dict[str, Any] | None = None,
                 devoir2_cfg: dict[str, Any] | None = None,
                 topics: dict[str, Any] | None = None,
                 turtle: Any | None = None,
                 client_execute: Any | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 context: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Construire l'arbitre, ses trois abonnements et son client d'action.
            La tortue (pour la SEULE lecture de la pose courante, jamais pour
            commander : turtle_io reste le seul chemin, motion_node en est
            l'unique appelant) et le client de l'action sont injectables pour
            les tests hors ligne (workflow.md R5).

        Inputs:
            projet_cfg (dict | None): section 'projet' de la configuration
            devoir2_cfg (dict | None): section 'devoir2' de la configuration
                (catalogue d'actions)
            topics (dict | None): section 'topics' de la configuration
            turtle (Any | None): objet portant .pose(), un vrai TurtleClient
                (lecture seule) si absent
            client_execute (Any | None): client de l'action ExecutePlan
            horloge (callable): source de l'instant d'arbitrage, injectee pour
                les tests (workflow.md, determinisme ; c'est ELLE que le
                correctif du 2026-09-18 exige de relire au moment de decider)
            context (Any | None): contexte rclpy, celui par defaut si absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        super().__init__("arbiter_node", context=context)
        self._projet_cfg = projet_cfg if projet_cfg is not None else config.section("projet")
        self._actions_cfg = (
            devoir2_cfg if devoir2_cfg is not None else config.section("devoir2")
        )["actions"]
        self._topics = topics if topics is not None else config.section("topics")
        self._horloge = horloge

        self._arbitre = Arbitre(self._projet_cfg)
        self._journal = JournalArbitrage()
        self._lisseur = LisseurCible(self._projet_cfg)

        self._turtle = turtle if turtle is not None else open_turtle(
            node_name="arbiter_node_pose", announce=self.get_logger().info,
        )
        self._client_execute = (
            client_execute if client_execute is not None
            else ActionClient(self, ExecutePlan, str(self._topics["execute_action"]))
        )
        self._but_courant: Any | None = None
        self._action_en_cours: str | None = None

        profondeur = int(self._topics["queue_depth"])
        self._sub_gesture = self.create_subscription(
            CommandeMsg, str(self._topics["gesture_topic"]), self._on_gesture, profondeur,
        )
        self._sub_target = self.create_subscription(
            Cible, str(self._topics["target_topic"]), self._on_target, profondeur,
        )
        self._sub_voix = self.create_subscription(
            CommandeMsg, str(self._topics["voice_intent_topic"]), self._on_voix, profondeur,
        )

        periode = float(self._projet_cfg["control_period_seconds"])
        self._minuterie = self.create_timer(periode, self._arbitrer_et_commander)

    @property
    def arbitre(self) -> Arbitre:
        """Arbitre courant, lu par les tests et par le diagnostic."""
        return self._arbitre

    @property
    def journal(self) -> JournalArbitrage:
        """Journal des changements de modalite, lu par les tests et l'affichage."""
        return self._journal

    # ------------------------------------------------------------------- perception

    def _soumettre(self, commande: Commande) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Deposer une commande dans l'arbitre. Une commande d'URGENCE efface
            les intentions des AUTRES modalites plutot que de simplement les
            surclasser un instant : sans cela, une intention vocale ou visuelle
            deja soumise et encore fraiche (peremption_s='voix' 5.0 s) RESSURGIT
            des que l'urgence expire (peremption_s='geste' 0.6 s), et la tortue
            repart seule quelques secondes apres un arret d'urgence.

            Mesure en DIRECT le 2026-09-19 (plan07, epreuve reelle de l'etape 5) :
            une intention 'voix' avancer, interrompue a t=0.35s par un geste
            d'urgence, laissait la tortue reprendre sa marche a t=1.6s (des que
            l'entree 'geste' expirait), l'intention 'voix' d'origine (soumise a
            t=0, peremption 5.0 s) redevenant alors la plus fraiche disponible.
            `Arbitre.arbitrer` (arbiter.py) n'est PAS modifie par ce correctif :
            il continue de n'appliquer que priorite et peremption ; c'est
            arbiter_node, seul, qui decide qu'une urgence remet les compteurs a
            zero pour les autres modalites.

        Inputs:
            commande (Commande): intention a deposer (arbiter.Commande)

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        if commande.urgence:
            for autre in self._arbitre.modalites:
                if autre != commande.modalite:
                    self._arbitre.retirer(autre)
        self._arbitre.soumettre(commande)

    def _on_gesture(self, message: Any) -> None:
        """Deposer l'intention geste dans l'arbitre. Reutilise arbiter.Commande tel quel."""
        self._soumettre(Commande(
            modalite="geste",
            twist=Twist(float(message.linear_x), float(message.angular_z)),
            instant=float(message.instant),
            motif=str(message.motif),
            urgence=bool(message.urgence),
        ))

    def _on_target(self, message: Any) -> None:
        """
        Convertir une detection d'objet en consigne de vitesse (navigator.py,
        reutilise tel quel) et la deposer dans l'arbitre. La pose est lue ICI,
        au moment de la reception, jamais mise en cache entre deux detections.
        """
        cible = self._lisseur.mettre_a_jour((float(message.x), float(message.y)))
        pose = self._turtle.pose()
        consigne = calculer_consigne(pose, cible, self._projet_cfg)
        self._soumettre(Commande(
            modalite="objet",
            twist=consigne.twist,
            instant=float(message.instant),
            motif=f"{message.classe} -> {consigne.phase}",
        ))

    def _on_voix(self, message: Any) -> None:
        """Deposer l'intention vocale publiee par dialogue_manager dans l'arbitre."""
        self._soumettre(Commande(
            modalite="voix",
            twist=Twist(float(message.linear_x), float(message.angular_z)),
            instant=float(message.instant),
            motif=str(message.motif),
            urgence=bool(message.urgence),
        ))

    # -------------------------------------------------------------------- decision

    def _arbitrer_et_commander(self) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Arbitrer et commander motion_node. L'instant est relu ICI (voir
            en-tete du module) : jamais celui d'une trame anterieure. Si l'action
            gagnante CHANGE (y compris vers aucune, ou vers 'arreter' porte par
            une urgence), le but courant est ANNULE avant tout nouvel envoi : la
            tortue est arretee, pas seulement le but marque annule
            (garantie deja portee par motion_node.executer_etape, inchange).
            Si l'action gagnante est la MEME qu'au tour precedent, rien n'est
            renvoye : un but re-envoye a chaque periode romprait la progression
            deja en cours pour rien.

        Inputs:
            aucun (rappel de minuterie)

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        instant = self._horloge()
        arbitrage = self._arbitre.arbitrer(instant)
        if self._journal.observer(instant, arbitrage):
            self.get_logger().info(f"[arbitrage] {arbitrage.describe()}")

        nouvelle_action = (
            None if arbitrage.modalite == "aucune"
            else nom_action_depuis_twist(arbitrage.twist, self._actions_cfg)
        )

        if nouvelle_action == self._action_en_cours:
            return

        if self._but_courant is not None:
            self._but_courant.cancel_goal_async()
            self._but_courant = None

        self._action_en_cours = nouvelle_action
        if nouvelle_action is None:
            return

        but = ExecutePlan.Goal()
        but.etapes = [etape_depuis_nom(nouvelle_action, arbitrage.twist)]
        futur = self._client_execute.send_goal_async(but)
        futur.add_done_callback(self._sur_acceptation_but)

    def _sur_acceptation_but(self, futur: Any) -> None:
        """Le serveur a accepte ou refuse le but. Aucune attente bloquante ici."""
        goal_handle = futur.result()
        if goal_handle is None or not getattr(goal_handle, "accepted", True):
            self._but_courant = None
            return
        self._but_courant = goal_handle

    def close(self) -> None:
        """Fermer la lecture de pose. Rappelable sans effet si le collaborateur le permet."""
        fermer = getattr(self._turtle, "close", None)
        if fermer is not None:
            fermer()


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
    node = ArbiterNode()
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
