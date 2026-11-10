"""
test_noeuds_projet.py - Projet, plan07 : arbiter_node et ses conversions pures.

Scinde le 2026-09-19 (workflow.md, fichier sous 400 lignes) : gesture_node et
object_node vivent desormais dans test_perception_nodes.py. Ce fichier couvre
arbiter_node, seul client de l'action ExecutePlan, et les cinq premiers des six
premiers cas du tableau des tests de plan07.md (le sixieme, la paume en seconde
main, est prouve dans test_perception_nodes.py).

Hors ligne AU SENS FORT (meme protocole que Devoir2/test/test_noeuds.py) : le
contexte rclpy est initialise SANS GRAPHE, le noeud est instancie et ses rappels
appeles EN DIRECT, tortue et client d'action sont des faux injectes. Aucun
turtlesim reel.

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

from ihr_6mig841_interfaces.msg import Cible, Commande as CommandeMsg  # noqa: E402

from arbiter_node import ArbiterNode, etape_depuis_nom, nom_action_depuis_twist  # noqa: E402
from ihr_ros.backends.base import Pose, Twist  # noqa: E402


@pytest.fixture
def contexte_rclpy():
    """Contexte rclpy isole par test : aucun graphe partage entre deux tests."""
    contexte = rclpy.Context()
    rclpy.init(context=contexte)
    yield contexte
    rclpy.shutdown(context=contexte)


class _TortuePoseFactice:
    """Fausse tortue : ne rend qu'une pose fixe, jamais commandee (lecture seule)."""

    def __init__(self, pose: Pose) -> None:
        self._pose = pose

    def pose(self) -> Pose:
        return self._pose

    def close(self) -> None:
        pass


class _HorlogeFactice:
    """Horloge pilotee a la main : aucun appel a time.monotonic."""

    def __init__(self, depart: float = 0.0) -> None:
        self.temps = depart

    def __call__(self) -> float:
        return self.temps


class _FuturFactice:
    """Faux futur rclpy : resout son rappel IMMEDIATEMENT (hors ligne, pas de spin)."""

    def __init__(self, resultat: Any) -> None:
        self._resultat = resultat

    def result(self) -> Any:
        return self._resultat

    def add_done_callback(self, callback: Any) -> None:
        callback(self)


class _GoalHandleFactice:
    """Faux but ExecutePlan : accepte toujours, compte ses annulations."""

    def __init__(self) -> None:
        self.accepted = True
        self.annulations = 0

    def cancel_goal_async(self) -> _FuturFactice:
        self.annulations += 1
        return _FuturFactice(None)


class _ClientExecuteFactice:
    """Faux client de l'action ExecutePlan : enregistre chaque but, accepte toujours."""

    def __init__(self) -> None:
        self.buts_envoyes: list[Any] = []
        self.goal_handles: list[_GoalHandleFactice] = []

    def send_goal_async(self, but: Any) -> _FuturFactice:
        self.buts_envoyes.append(but)
        goal_handle = _GoalHandleFactice()
        self.goal_handles.append(goal_handle)
        return _FuturFactice(goal_handle)


def _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg,
                        pose: Pose = Pose(0.0, 0.0, 0.0),
                        horloge: _HorlogeFactice | None = None) -> tuple[ArbiterNode, _ClientExecuteFactice, _HorlogeFactice]:
    horloge = horloge if horloge is not None else _HorlogeFactice()
    client = _ClientExecuteFactice()
    node = ArbiterNode(
        projet_cfg=projet_cfg, devoir2_cfg=devoir2_cfg, topics=topics_cfg,
        turtle=_TortuePoseFactice(pose), client_execute=client,
        horloge=horloge, context=contexte_rclpy,
    )
    return node, client, horloge


def _commande_msg(modalite: str, linear_x: float, angular_z: float, instant: float,
                  urgence: bool = False, motif: str = "") -> CommandeMsg:
    message = CommandeMsg()
    message.modalite = modalite
    message.linear_x = linear_x
    message.angular_z = angular_z
    message.instant = instant
    message.urgence = urgence
    message.motif = motif
    return message


# ---------------------------------------------------------------------------
# nom_action_depuis_twist / etape_depuis_nom : conversion pure.
# ---------------------------------------------------------------------------

def test_nom_action_depuis_twist_round_trip_le_catalogue(devoir2_cfg):
    actions = devoir2_cfg["actions"]
    assert nom_action_depuis_twist(Twist(0.0, 0.0), actions) == "arreter"
    assert nom_action_depuis_twist(Twist(2.0, 0.0), actions) == "avancer"
    assert nom_action_depuis_twist(Twist(-2.0, 0.0), actions) == "reculer"
    assert nom_action_depuis_twist(Twist(0.0, 1.6), actions) == "tourner"


def test_etape_depuis_nom_porte_le_signe_du_twist():
    step = etape_depuis_nom("tourner", Twist(0.0, -1.6))
    assert step.nom_action == "tourner"
    assert step.is_clockwise is True  # angular_z negatif -> horaire (convention signer())


# ---------------------------------------------------------------------------
# 1. Priorite : geste (30) l'emporte sur objet (10) quand les deux sont frais.
# ---------------------------------------------------------------------------

def test_priorite_geste_bat_objet_dans_larbitre_du_noeud(contexte_rclpy, projet_cfg,
                                                          devoir2_cfg, topics_cfg):
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 10.0

    node._on_target(Cible(classe="banana", confiance=0.9, x=5.0, y=5.0, instant=10.0))
    node._on_gesture(_commande_msg("geste", 0.0, 1.6, instant=10.0))

    node._arbitrer_et_commander()

    assert len(client.buts_envoyes) == 1
    assert client.buts_envoyes[0].etapes[0].nom_action == "tourner"  # decision du GESTE
    node.destroy_node()


# ---------------------------------------------------------------------------
# 2. Urgence : l'emporte sur tout, meme une commande normale plus fraiche.
# ---------------------------------------------------------------------------

def test_urgence_bat_une_commande_plus_fraiche_et_plus_prioritaire(contexte_rclpy, projet_cfg,
                                                                    devoir2_cfg, topics_cfg):
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 12.0

    node._on_gesture(_commande_msg("geste", 0.0, 1.6, instant=12.0))  # normal, tres frais
    node._on_voix(_commande_msg("voix", 0.0, 0.0, instant=11.0, urgence=True))  # urgence, un peu plus vieille

    node._arbitrer_et_commander()

    assert client.buts_envoyes[0].etapes[0].nom_action == "arreter"


# ---------------------------------------------------------------------------
# 3. Peremption : sans commande valide, aucune action n'est commandee.
# ---------------------------------------------------------------------------

def test_sans_commande_valide_aucun_but_nest_envoye(contexte_rclpy, projet_cfg,
                                                     devoir2_cfg, topics_cfg):
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 100.0
    node._on_gesture(_commande_msg("geste", 1.0, 0.0, instant=0.0))  # deja perimee (0.6 s)

    node._arbitrer_et_commander()

    assert client.buts_envoyes == []


# ---------------------------------------------------------------------------
# 4. Commande venue du futur proche : acceptee, non ecartee (correctif 2026-09-18,
#    moitie applicative : l'horloge est relue AU MOMENT DE DECIDER).
# ---------------------------------------------------------------------------

def test_commande_du_futur_proche_est_acceptee(contexte_rclpy, projet_cfg,
                                                devoir2_cfg, topics_cfg):
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 90.0
    # deposee avec un instant POSTERIEUR a l'horloge d'arbitrage : le fil percepteur a
    # capture son horodatage apres que la minuterie a demarre son tour.
    node._on_voix(_commande_msg("voix", 2.0, 0.0, instant=100.0))

    node._arbitrer_et_commander()

    assert len(client.buts_envoyes) == 1
    assert client.buts_envoyes[0].etapes[0].nom_action == "avancer"


# ---------------------------------------------------------------------------
# 6. Annulation du but : la tortue est ARRETEE, pas seulement le but marque annule.
# ---------------------------------------------------------------------------

def test_annulation_du_but_annule_reellement_le_but_courant(contexte_rclpy, projet_cfg,
                                                              devoir2_cfg, topics_cfg):
    """
    Un but 'avancer' est deja en cours (voix). Un geste d'urgence arrive : le tour
    d'arbitrage suivant doit ANNULER le but courant (goal_handle.cancel_goal_async
    reellement appele, pas seulement une modalite qui change de nom) avant d'envoyer
    le nouveau but 'arreter'. La garantie qu'une consigne nulle est PUBLIEE avant que
    le serveur ne rende son resultat reste celle, deja prouvee, de
    motion_node.executer_etape (Devoir 2, inchange) : ce test prouve la moitie qui
    revient a arbiter_node, l'appel d'annulation lui-meme.
    """
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 1.0
    node._on_voix(_commande_msg("voix", 2.0, 0.0, instant=1.0))
    node._arbitrer_et_commander()
    assert len(client.buts_envoyes) == 1
    premier_but = client.goal_handles[0]
    assert premier_but.annulations == 0

    horloge.temps = 1.05
    node._on_gesture(_commande_msg("geste", 0.0, 0.0, instant=1.05, urgence=True,
                                   motif="main ouverte"))
    node._arbitrer_et_commander()

    assert premier_but.annulations == 1
    assert len(client.buts_envoyes) == 2
    assert client.buts_envoyes[1].etapes[0].nom_action == "arreter"


def test_urgence_efface_lintention_vocale_qui_ne_ressurgit_pas_a_son_expiration(
        contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg):
    """
    Regression mesuree EN DIRECT le 2026-09-19 (plan07, epreuve reelle de
    l'etape 5) : sans ce correctif, une intention 'voix' encore fraiche (5.0 s
    de peremption) redevenait la plus fraiche disponible des que l'urgence
    'geste' qui l'avait interrompue expirait (0.6 s), et la tortue repartait
    seule. L'urgence doit effacer 'voix', pas seulement la surclasser un instant.
    """
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 1.0
    node._on_voix(_commande_msg("voix", 2.0, 0.0, instant=1.0))
    node._arbitrer_et_commander()
    assert client.buts_envoyes[0].etapes[0].nom_action == "avancer"

    horloge.temps = 1.05
    node._on_gesture(_commande_msg("geste", 0.0, 0.0, instant=1.05, urgence=True))
    node._arbitrer_et_commander()
    assert client.buts_envoyes[1].etapes[0].nom_action == "arreter"

    # L'urgence elle-meme perime a son tour (peremption_s='geste' = 0.6 s) : sans
    # commande vocale a ressusciter (elle a ete effacee au moment de l'urgence),
    # l'arbitrage doit rendre 'aucune', PAS 'avancer' a nouveau.
    horloge.temps = 1.75
    node._arbitrer_et_commander()

    assert len(client.buts_envoyes) == 2  # aucun troisieme but envoye
    assert node.arbitre.arbitrer(1.75).modalite == "aucune"


def test_action_inchangee_ne_renvoie_pas_de_nouveau_but(contexte_rclpy, projet_cfg,
                                                        devoir2_cfg, topics_cfg):
    """Deux tours d'arbitrage qui rendent la MEME action ne renvoient qu'UN seul but :
    un but re-envoye a chaque periode romprait la progression deja en cours pour rien."""
    node, client, horloge = _construire_arbiter(contexte_rclpy, projet_cfg, devoir2_cfg, topics_cfg)
    horloge.temps = 1.0
    node._on_voix(_commande_msg("voix", 2.0, 0.0, instant=1.0))
    node._arbitrer_et_commander()

    horloge.temps = 1.05
    node._on_voix(_commande_msg("voix", 2.0, 0.0, instant=1.05))
    node._arbitrer_et_commander()

    assert len(client.buts_envoyes) == 1
