"""
test_chemin_sans_nav2.py - Preuves du chemin SANS Nav2 (plan07.md, complement de
l'orchestrateur : cabler reellement l'arete PLAN --> NAV d'enonce.md).

Deux preuves attendues explicitement :
  1. sur une dorsale SANS planificateur propre (substitut ou ROS2 ordinaire), une
     pose absolue produit bien un parcours de points de passage ISSU d'un
     planificateur du Lab 1 (theta_star ici, le palier par defaut) ;
  2. controle negatif : sur la dorsale Nav2, c'est NAV2 qui planifie, jamais le
     Lab 1 (planifier_chemin n'est alors jamais appele).

Aucun ROS2, aucune camera : seuls `planif.world`/`planif.thetastar` (stdlib pur) et
`ihr_ros.backends.sim.integrate` (deja teste, reutilise ici comme moteur de
simulation du move) sont necessaires (workflow.md R5).
"""

from __future__ import annotations

import copy

import pytest

from ihr_ros.backends.base import Pose, ResultatNavigation, Twist
from ihr_ros.backends.sim import integrate

import chemin_sans_nav2 as csn  # noqa: E402  (insere Lab1/code sur sys.path a l'import)
from chemin_sans_nav2 import aller_a_pose, planifier_chemin  # noqa: E402

from planif.world import World  # noqa: E402  (disponible seulement apres l'import ci-dessus)


def _monde_avec_mur() -> World:
    """
    Grille 5x3, cellules de 1.0. Un mur occupe la colonne 2 aux lignes 0 et 1,
    laissant la ligne 2 libre : la ligne de vue directe depart(0,0)->but(4,0) est
    bloquee, ce qui force un detour et prouve un VRAI parcours de plusieurs points
    de passage plutot qu'un segment direct.
    """
    return World({
        "grille": {"largeur_cellules": 5, "hauteur_cellules": 3, "taille_cellule": 1.0,
                  "origine_x": 0.0, "origine_y": 0.0},
        "obstacle_initial": {"colonne_min": 2, "colonne_max": 2,
                             "ligne_min": 0, "ligne_max": 1},
    })


def _monde_but_enferme() -> World:
    """
    Grille 3x3 dont le but, la cellule de COIN (2, 2), est enferme par ses trois
    seuls voisins possibles (1,1), (1,2) et (2,1), occupes individuellement pour
    ne jamais occuper le but lui-meme : aucun chemin possible.
    """
    monde = World({
        "grille": {"largeur_cellules": 3, "hauteur_cellules": 3, "taille_cellule": 1.0,
                  "origine_x": 0.0, "origine_y": 0.0},
    })
    monde.definir_occupation([(1, 1), (1, 2), (2, 1)], True)
    return monde


class _DorsaleNav2Factice:
    """Imite Nav2Backend : goto_pose reussit par elle-meme, sans jamais planifier ailleurs."""

    name = "Nav2 (nav2_simple_commander + rclpy)"

    def __init__(self, resultat: ResultatNavigation) -> None:
        self._resultat = resultat
        self.appels: list[Pose] = []

    def goto_pose(self, pose: Pose) -> ResultatNavigation:
        self.appels.append(pose)
        return self._resultat


class _DorsaleSansPlanificateurFactice:
    """Imite le refus PAR DEFAUT de TurtleBackend.goto_pose (substitut, ROS2 ordinaire)."""

    name = "dorsale-de-test-sans-planificateur"

    def goto_pose(self, pose: Pose) -> ResultatNavigation:
        raise NotImplementedError(f"La dorsale '{self.name}' n'a pas de planificateur.")


class _TortueSubstitutFactice:
    """
    Simule le substitut par integration unicycle REELLE (ihr_ros.backends.sim.integrate,
    deja teste), pour prouver que aller_a_pose CONVERGE vraiment point par point plutot
    que de se contenter d'appeler drive() une fois. Aucun thread, aucune horloge murale :
    c'est le `sleep` injecte qui fait AVANCER la simulation d'un pas.
    """

    def __init__(self, pose_depart: Pose, canvas: tuple[float, float] = (50.0, 50.0)) -> None:
        self._pose = pose_depart
        self._twist = Twist(0.0, 0.0)
        self._canvas = canvas
        self.backend = _DorsaleSansPlanificateurFactice()
        self.consignes: list[Twist] = []
        self.arrets = 0

    def pose(self) -> Pose:
        return self._pose

    def drive(self, linear: float = 0.0, angular: float = 0.0) -> None:
        self._twist = Twist(float(linear), float(angular))
        self.consignes.append(self._twist)

    def spin_once(self, timeout_seconds: float = 0.0) -> None:
        pass

    def stop(self) -> None:
        self._twist = Twist(0.0, 0.0)
        self.arrets += 1

    def avancer(self, dt_seconds: float) -> None:
        """Effet de bord du `sleep` injecte : integre un pas de temps reel."""
        self._pose = integrate(self._pose, self._twist, dt_seconds, *self._canvas)


def _config_projet(projet_cfg: dict) -> dict:
    """Copie de projet_cfg, saturation elargie pour converger vite sur une grande grille."""
    cfg = copy.deepcopy(projet_cfg)
    cfg["linear_speed"] = 4.0
    cfg["vitesse_lineaire_max"] = 8.0
    cfg["vitesse_angulaire_max"] = 8.0
    cfg["goal_tolerance"] = 0.3
    return cfg


# ---------------------------------------------------------------------------
# 1. planifier_chemin : delegue REELLEMENT au planificateur du Lab 1.
# ---------------------------------------------------------------------------

def test_planifier_chemin_theta_star_detourne_un_obstacle():
    """Theta*, palier par defaut : detour a un seul point de passage intermediaire."""
    monde = _monde_avec_mur()

    chemin = planifier_chemin((0.5, 0.5), (4.5, 0.5), monde, "theta_star")

    assert chemin == [(2.5, 2.5), (4.5, 0.5)]  # le but est inclus, le depart exclu


def test_planifier_chemin_astar_rend_un_escalier_plus_long():
    """
    Controle : A* (l'autre palier disponible) rend un chemin PLUS LONG que Theta*
    sur la MEME grille (enonce.md, l'argument mesure du Lab 1 : Theta* reduit le
    nombre de points de passage, donc les rotations, par rapport a A*).
    """
    monde = _monde_avec_mur()

    chemin_theta = planifier_chemin((0.5, 0.5), (4.5, 0.5), monde, "theta_star")
    chemin_astar = planifier_chemin((0.5, 0.5), (4.5, 0.5), monde, "astar")

    assert len(chemin_astar) > len(chemin_theta)


def test_planifier_chemin_nom_inconnu_est_refuse():
    with pytest.raises(KeyError, match="astar"):
        planifier_chemin((0.5, 0.5), (0.5, 0.5), _monde_avec_mur(), "d_star_lite")


def test_planifier_chemin_but_enferme_est_un_echec_motive():
    monde = _monde_but_enferme()
    with pytest.raises(ValueError, match="Aucun chemin"):
        planifier_chemin((0.5, 0.5), (2.5, 2.5), monde, "theta_star")


# ---------------------------------------------------------------------------
# 2. Controle negatif : sur Nav2, c'est NAV2 qui planifie, jamais le Lab 1.
# ---------------------------------------------------------------------------

def test_aller_a_pose_sur_nav2_ne_planifie_jamais_avec_le_lab1(monkeypatch, projet_cfg):
    """
    Sur une dorsale dont goto_pose REUSSIT (Nav2), aller_a_pose ne doit JAMAIS
    appeler planifier_chemin : deux planificateurs actifs pour la meme pose
    serait une source de divergence, pas un renfort.
    """
    def _echoue_si_appele(*args, **kwargs):
        raise AssertionError("planifier_chemin ne doit jamais etre appele sur Nav2.")

    monkeypatch.setattr(csn, "planifier_chemin", _echoue_si_appele)

    class _Turtle:
        backend = _DorsaleNav2Factice(ResultatNavigation(True, ""))

        def pose(self) -> Pose:
            return Pose(0.0, 0.0, 0.0)

    resultat = aller_a_pose(_Turtle(), Pose(3.0, 4.0, 0.0), projet_cfg, _monde_avec_mur())

    assert resultat.succes is True
    assert len(_Turtle.backend.appels) == 1


def test_aller_a_pose_relaye_un_echec_nav2_sans_lever(monkeypatch, projet_cfg):
    """Un echec Nav2 (backend.goto_pose) traverse tel quel, sans jamais lever ni planifier."""
    monkeypatch.setattr(csn, "planifier_chemin",
                        lambda *a, **k: pytest.fail("jamais appele sur Nav2"))

    class _Turtle:
        backend = _DorsaleNav2Factice(ResultatNavigation(False, "controleur bloque"))

        def pose(self) -> Pose:
            return Pose(0.0, 0.0, 0.0)

    resultat = aller_a_pose(_Turtle(), Pose(1.0, 1.0, 0.0), projet_cfg, _monde_avec_mur())

    assert resultat.succes is False
    assert "controleur bloque" in resultat.raison


# ---------------------------------------------------------------------------
# 3. Sans planificateur propre : le Lab 1 planifie, le Projet commande, en VRAI.
# ---------------------------------------------------------------------------

def test_aller_a_pose_sans_planificateur_suit_le_chemin_du_lab1(projet_cfg):
    """
    Preuve integrale demandee par l'orchestrateur : sur une dorsale SANS
    planificateur, aller_a_pose plani[fie] REELLEMENT avec Theta* (le mur de
    _monde_avec_mur force un detour) puis fait REELLEMENT converger la tortue
    (integration unicycle reelle) jusqu'a la tolerance d'arrivee du dernier
    point de passage.
    """
    cfg = _config_projet(projet_cfg)
    turtle = _TortueSubstitutFactice(Pose(0.5, 0.5, 0.0))
    pas_de_temps: list[float] = []

    def _sleep(duree: float) -> None:
        pas_de_temps.append(duree)
        turtle.avancer(duree)

    resultat = aller_a_pose(turtle, Pose(4.5, 0.5, 0.0), cfg, _monde_avec_mur(), sleep=_sleep)

    assert resultat.succes is True
    assert len(pas_de_temps) > 0  # l'asservissement a reellement boucle, pas un seul drive()
    assert len(turtle.consignes) > 1
    assert turtle.pose().x == pytest.approx(4.5, abs=cfg["goal_tolerance"] + 0.05)
    assert turtle.pose().y == pytest.approx(0.5, abs=cfg["goal_tolerance"] + 0.05)
    assert turtle.arrets >= 1  # arret final (voir goto_pose/executer_etape, meme garantie)


def test_aller_a_pose_but_inatteignable_rend_un_echec_sans_lever(projet_cfg):
    turtle = _TortueSubstitutFactice(Pose(0.5, 0.5, 0.0))

    resultat = aller_a_pose(
        turtle, Pose(2.5, 2.5, 0.0), projet_cfg, _monde_but_enferme(), sleep=lambda _: None,
    )

    assert resultat.succes is False
    assert "Aucun chemin" in resultat.raison


def test_aller_a_pose_abandonne_apres_max_iterations_sans_boucler_indefiniment(projet_cfg):
    """
    Si la tortue ne converge JAMAIS (ici : sleep() n'avance rien), aller_a_pose doit
    quand meme RENDRE LA MAIN apres un nombre borne d'iterations (R10), jamais
    boucler indefiniment.
    """
    cfg = copy.deepcopy(projet_cfg)
    cfg["aller_a_pose_max_iterations"] = 3
    turtle = _TortueSubstitutFactice(Pose(0.5, 0.5, 0.0))

    resultat = aller_a_pose(
        turtle, Pose(4.5, 0.5, 0.0), cfg, _monde_avec_mur(), sleep=lambda _: None,
    )

    assert resultat.succes is False
    assert "iterations" in resultat.raison
    assert turtle.arrets >= 1  # meme un abandon arrete la tortue
