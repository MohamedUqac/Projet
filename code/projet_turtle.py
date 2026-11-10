"""
projet_turtle.py - Projet de session : commander la tortue par objet, geste et voix.

Integration des trois travaux du cours :

    Lab1     -> socle ihr_ros : configuration, geometrie, dorsale ROS2 ou substitut
    Devoir 1 -> thumb_detector, reutilise tel quel pour les gestes
    Devoir 2 -> llm_interpreter et state_machine, reutilises pour la voix
    Projet   -> YOLO, asservissement, et surtout l'ARBITRAGE entre les trois

Ce que le Projet ajoute aux rendus etudiants
---------------------------------------------
Les trois rendus melangeaient deux modalites au plus, par un `if/elif` implicite.
Ici, les modalites sont trois, elles sont declarees dans la configuration avec leur
priorite et leur duree de validite, l'arbitrage est visible a l'ecran, et un geste
d'arret d'urgence l'emporte sur tout.

La voix tourne dans un FIL SEPARE. C'est necessaire : la reconnaissance vocale bloque
plusieurs secondes, et la mettre dans la boucle video gelerait l'image et le suivi
d'objet. Le fil ne commande jamais la tortue directement, il depose une commande
horodatee dans l'arbitre, qui reste seul a decider.

Usage :
    python Projet/code/projet_turtle.py
    python Projet/code/projet_turtle.py --classes banana fork
    python Projet/code/projet_turtle.py --no-voice --backend sim
    python Projet/code/projet_turtle.py --headless --max-frames 60 --json
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

_ICI = Path(__file__).resolve().parent
_RACINE = _ICI.parent.parent
sys.path.insert(0, str(_ICI))
sys.path.insert(0, str(_RACINE / "Devoir1" / "code"))
sys.path.insert(0, str(_RACINE / "Devoir2" / "code"))

from ihr_ros import config  # noqa: E402
from ihr_ros.backends.base import Twist  # noqa: E402
from ihr_ros.hands import HandTracker, hand_connections  # noqa: E402
from ihr_ros.overlay import AMBER, CYAN, GREEN, RED, WHITE, draw_box, draw_hand, draw_lines, put_text  # noqa: E402
from ihr_ros.turtle_io import open_turtle  # noqa: E402

import gesture_commands  # noqa: E402
from arbiter import Arbitre, Commande, JournalArbitrage  # noqa: E402
from navigator import LisseurCible, calculer_consigne  # noqa: E402
from object_tracker import ObjectTracker  # noqa: E402


def configure_streams() -> None:
    """Forcer utf-8 sur stdout et stderr, sans jamais lever (console cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


class FilVocal(threading.Thread):
    """
    Modalite vocale, dans son propre fil.

    Reutilise le Devoir 2 sans le modifier. Le fil ne touche JAMAIS a la tortue : il
    depose une commande horodatee dans l'arbitre. Une modalite qui commanderait
    directement court-circuiterait l'arbitrage et l'arret d'urgence.
    """

    def __init__(self, arbitre: Arbitre, settings: dict[str, Any],
                 mode_entree: str, phrases: list[str] | None):
        super().__init__(name="ihr-voix", daemon=True)
        self._arbitre = arbitre
        self._cfg = settings
        self._mode = mode_entree
        self._phrases = phrases
        self._stop = threading.Event()
        self.erreur: str = ""
        self.commandes_emises: list[str] = []

    def demander_arret(self) -> None:
        """Demander l'arret du fil. Il se termine apres l'ecoute en cours."""
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - teste par ses parties, pas en fil
        try:
            from llm_interpreter import LlmInterpreter
            from state_machine import Etat, MachineDialogue
            from voice import ouvrir_entree

            entree = ouvrir_entree(self._mode, self._cfg, self._phrases)
            interprete = LlmInterpreter(self._cfg)
            machine = MachineDialogue(
                mots_accord=self._cfg["affirmative_words"],
                mots_refus=self._cfg["negative_words"],
                mots_sortie=self._cfg["quit_words"],
            )

            while not self._stop.is_set() and machine.etat is not Etat.ARRET:
                etat = machine.etat
                if etat is Etat.ECOUTE:
                    machine.entendu(entree.ecouter("Commande ?"))
                elif etat in (Etat.CONFIRMATION_COMMANDE, Etat.CONFIRMATION_ACTION):
                    machine.repondu(entree.ecouter("oui ou non ?"))
                elif etat is Etat.INTERPRETATION:
                    resultat = interprete.interpreter(machine.commande)
                    if resultat.ok:
                        machine.interprete(resultat.action)
                    else:
                        machine.echec_interpretation(resultat.erreur)
                elif etat is Etat.EXECUTION:
                    action = machine.action
                    self._arbitre.soumettre(Commande(
                        modalite="voix",
                        twist=Twist(action.linear, action.angular),
                        instant=time.monotonic(),
                        motif=f"commande vocale « {action.nom} »",
                    ))
                    self.commandes_emises.append(action.nom)
                    machine.execute()
            entree.close()
        except Exception as exc:
            self.erreur = f"{type(exc).__name__}: {exc}"


def construire_lignes(arbitrage, geste, detection, consigne, fps: float,
                      pose) -> list[tuple[str, tuple[int, int, int]]]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Composer l'affichage tete haute. La modalite retenue ET les modalites
        ecartees y figurent : c'est ce que le rendu Projet2 ne montrait pas, et
        c'est ce qui rend l'arbitrage comprehensible pendant la demonstration.

    Inputs:
        arbitrage (Arbitrage): decision de l'arbitre
        geste (Geste | None): geste reconnu sur la trame
        detection (Detection | None): objet suivi sur la trame
        consigne (Consigne | None): consigne de navigation
        fps (float): cadence mesuree
        pose (Pose): pose courante de la tortue

    Outputs:
        lignes (list): couples (texte, couleur BGR)
    --------------------------------------------------------------------------
    """
    couleur = RED if arbitrage.modalite == "aucune" else GREEN
    if geste is not None and geste.urgence:
        couleur = RED

    lignes = [
        (f"arbitrage : {arbitrage.describe()}", couleur),
        (f"tortue    : x={pose.x:5.2f} y={pose.y:5.2f} th={pose.theta:+6.3f}   "
         f"{fps:4.1f} ips", WHITE),
    ]
    lignes.append((f"geste     : {geste.describe() if geste else 'aucun'}",
                   CYAN if geste else WHITE))
    lignes.append((f"objet     : {detection.describe() if detection else 'aucun'}",
                   AMBER if detection else WHITE))
    if consigne is not None:
        lignes.append((f"navigation: {consigne.describe()}", WHITE))
    return lignes


def run(args: argparse.Namespace) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Boucle principale du Projet : percevoir, arbitrer, commander, afficher.

    Inputs:
        args (Namespace): arguments de la ligne de commande

    Outputs:
        resume (dict): trames, cadence, journal d'arbitrage, modalites vues
    --------------------------------------------------------------------------
    """
    import cv2

    devoir1_cfg = config.section("devoir1")
    devoir2_cfg = config.section("devoir2")
    projet_cfg = config.section("projet")
    camera_cfg = config.section("camera")

    # --- perception ------------------------------------------------------------
    source: str | int = args.source if args.source else int(
        args.camera_index if args.camera_index is not None else camera_cfg["index"]
    )
    capture = cv2.VideoCapture(source)
    if isinstance(source, int):
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(camera_cfg["frame_width"]))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(camera_cfg["frame_height"]))
    if not capture.isOpened():
        raise SystemExit(
            f"ERREUR : source '{source}' impossible a ouvrir. "
            "Verifier avec : python Lab1/code/check_env.py --camera"
        )

    if args.classes:
        classes = [str(c) for c in args.classes]
    elif args.toutes_classes:
        classes = [str(projet_cfg["target_class"])] + [
            str(c) for c in projet_cfg["fallback_classes"]
        ]
    else:
        classes = [str(projet_cfg["target_class"])]

    tracker_mains = HandTracker(
        max_hands=int(devoir1_cfg["max_num_hands"]),
        min_detection_confidence=float(devoir1_cfg["min_detection_confidence"]),
        min_tracking_confidence=float(devoir1_cfg["min_tracking_confidence"]),
    )
    tracker_objets = ObjectTracker(projet_cfg, classes=classes)
    connexions = hand_connections()

    # --- decision --------------------------------------------------------------
    arbitre = Arbitre(projet_cfg)
    journal = JournalArbitrage()
    lisseur = LisseurCible(projet_cfg)

    turtle = open_turtle(args.backend, node_name="projet_turtle",
                         with_window=not args.no_window)

    fil_voix: FilVocal | None = None
    if not args.no_voice:
        fil_voix = FilVocal(arbitre, devoir2_cfg, args.input or "clavier", args.phrases)
        fil_voix.start()

    print(f"Projet - classes suivies : {', '.join(classes)}")
    print(f"Modalites (priorite decroissante) : {', '.join(arbitre.modalites)}")
    print(f"Voix : {'active' if fil_voix else 'desactivee'}")

    quit_keys = {int(code) for code in devoir1_cfg["quit_key_codes"]}
    frames = 0
    started = time.monotonic()
    fps = 0.0
    dernier_arbitrage = None

    try:
        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                if args.source:
                    break
                continue
            if bool(camera_cfg["flip_horizontal"]) and not args.source:
                frame = cv2.flip(frame, 1)

            maintenant = time.monotonic()
            height, width = frame.shape[:2]

            # --- modalite GESTE ------------------------------------------------
            mains = tracker_mains.process(frame)
            geste = gesture_commands.reconnaitre(
                [m.landmarks for m in mains], width, height, devoir1_cfg, projet_cfg
            )
            if geste is not None:
                arbitre.soumettre(Commande(
                    modalite="geste", twist=geste.twist, instant=maintenant,
                    motif=geste.describe(), urgence=geste.urgence,
                ))
            else:
                arbitre.retirer("geste")

            # --- modalite OBJET ------------------------------------------------
            detection = tracker_objets.suivre(frame)
            consigne = None
            if detection is not None:
                cible = lisseur.mettre_a_jour(detection.centre_turtlesim)
                turtle.spin_once(0.0)
                consigne = calculer_consigne(turtle.pose(), cible, projet_cfg)
                arbitre.soumettre(Commande(
                    modalite="objet", twist=consigne.twist, instant=maintenant,
                    motif=f"{detection.classe} -> {consigne.phase}",
                ))
            else:
                lisseur.reset()
                arbitre.retirer("objet")

            # --- arbitrage et commande -----------------------------------------
            # Horodatage RELU ici, et non celui pris en haut de la trame : entre les
            # deux, MediaPipe et YOLO ont consomme plusieurs dizaines de
            # millisecondes, pendant lesquelles le fil vocal a pu deposer une
            # commande. Arbitrer avec un instant perime la ferait paraitre venue du
            # futur. C'est la moitie applicative du defaut mesure le 2026-09-18,
            # l'autre moitie etant corrigee dans arbiter.arbitrer.
            instant_decision = time.monotonic()
            arbitrage = arbitre.arbitrer(instant_decision)
            dernier_arbitrage = arbitrage
            if journal.observer(instant_decision, arbitrage):
                print(f"[arbitrage] {arbitrage.describe()}")

            turtle.drive(linear=arbitrage.twist.linear_x,
                         angular=arbitrage.twist.angular_z)
            turtle.spin_once(0.0)

            frames += 1
            ecoule = time.monotonic() - started
            if ecoule > 0:
                fps = frames / ecoule

            if not args.headless:
                for main in mains:
                    draw_hand(frame, main.landmarks, connexions)
                if detection is not None:
                    x1, y1, x2, y2 = detection.boite
                    draw_box(frame, x1, y1, x2, y2,
                             f"{detection.classe} {detection.confiance:.2f}")
                draw_lines(frame, construire_lignes(arbitrage, geste, detection,
                                                    consigne, fps, turtle.pose()))
                put_text(frame, "q / Echap : quitter", (12, height - 14), WHITE, 0.45, 1)
                cv2.imshow("Projet - objet, geste et voix", frame)
                if (cv2.waitKey(1) & 0xFF) in quit_keys:
                    break

            if args.max_frames and frames >= args.max_frames:
                break
    finally:
        if fil_voix is not None:
            fil_voix.demander_arret()
        tracker_mains.close()
        capture.release()
        if not args.headless:
            cv2.destroyAllWindows()
        turtle.close()

    return {
        "trames": frames,
        "ips": round(fps, 2),
        "classes_suivies": classes,
        "modalites_declarees": list(arbitre.modalites),
        "derniere_modalite": dernier_arbitrage.modalite if dernier_arbitrage else "aucune",
        "journal_arbitrage": [(round(t - started, 2), m, r) for t, m, r in journal.entrees],
        "commandes_vocales": fil_voix.commandes_emises if fil_voix else [],
        "erreur_fil_vocal": fil_voix.erreur if fil_voix else "",
    }


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    parser = argparse.ArgumentParser(
        description="Projet - commander la tortue par objet, geste et voix."
    )
    parser.add_argument("--camera-index", type=int, default=None)
    parser.add_argument("--source", default=None, help="fichier video au lieu de la camera")
    parser.add_argument("--classes", nargs="*", default=None,
                        help="classes YOLO suivies (defaut : projet.target_class)")
    parser.add_argument("--toutes-classes", action="store_true",
                        help="suivre aussi les classes de repli de la configuration")
    parser.add_argument("--backend", default=None, choices=["ros2", "sim", "auto"])
    parser.add_argument("--no-window", action="store_true",
                        help="ne pas ouvrir la fenetre du substitut de tortue")
    parser.add_argument("--no-voice", action="store_true",
                        help="desactiver la modalite vocale")
    parser.add_argument("--input", default=None,
                        choices=["micro", "clavier", "script", "auto"],
                        help="source des phrases pour la modalite vocale")
    parser.add_argument("--phrases", nargs="*", default=None,
                        help="phrases du mode script de la modalite vocale")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    resume = run(args)

    if args.json:
        print(json.dumps(resume, indent=2, ensure_ascii=False))
    else:
        print(f"\n{resume['trames']} trames, {resume['ips']} ips, "
              f"derniere modalite : {resume['derniere_modalite']}")
        for instant, modalite, motif in resume["journal_arbitrage"]:
            print(f"  {instant:6.2f}s  {modalite:8s} {motif}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
