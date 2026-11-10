"""
arbiter.py - Arbitrage entre les modalites de commande du Projet.

Le Projet fait converger trois facons de commander la tortue :

  - le GESTE   (Devoir 1, reutilise tel quel),
  - la VOIX    (Devoir 2, reutilise tel quel),
  - l'OBJET    (nouveaute du Projet : YOLO suit un objet, la tortue va vers lui).

Quand deux modalites parlent en meme temps, il faut decider. Ce module ne fait que
cela, et il est PUR : aucune camera, aucun micro, aucune horloge murale. L'instant
est toujours passe en argument, de sorte que le comportement est reproductible
(workflow.md R7 et regle de determinisme).

Ce que faisaient les rendus etudiants
-------------------------------------
`banano.py` (Projet2) arbitrait par un `if results.multi_hand_landmarks: ... elif
bananeoupas: ...`. Deux defauts en decoulent, tous deux observables a l'ecran :

  1. L'arbitrage est INVISIBLE. La main coupe le suivi d'objet, mais rien ne le dit
     ni a l'ecran ni dans le journal. Un utilisateur qui passe la main devant la
     camera par hasard voit la tortue changer de comportement sans comprendre.
  2. Rien ne PERIME. La variable `banane_tracker_destroyer` garde la derniere
     position vue, et la branche `elif` continue de piloter la tortue vers cette
     position meme si la banane a quitte le champ depuis dix secondes.

Ici, chaque commande porte son instant et sa duree de validite. Une commande perimee
n'est plus candidate, et la modalite retenue est TOUJOURS nommee dans le resultat,
donc affichable.

Un quatrieme cas est ajoute, absent des trois rendus : l'ARRET D'URGENCE. Une main
grande ouverte devant la camera arrete la tortue et l'emporte sur tout le reste. En
interaction humain-robot, un geste d'arret qui doit attendre son tour de priorite
n'est pas un arret d'urgence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ihr_ros.backends.base import Twist

#: Priorite attribuee a l'arret d'urgence. Superieure a toute priorite declaree
#: dans la configuration, par construction : c'est une regle de securite, pas un
#: reglage. La mettre dans ihr_config.json permettrait de la baisser par megarde.
PRIORITE_ARRET_URGENCE = 1000


@dataclass(frozen=True)
class Commande:
    """Une intention emise par une modalite, horodatee."""

    modalite: str
    twist: Twist
    instant: float
    motif: str = ""
    urgence: bool = False


@dataclass(frozen=True)
class Arbitrage:
    """Decision d'arbitrage : ce qui est retenu, et ce qui a ete ecarte."""

    twist: Twist
    modalite: str
    motif: str
    candidates: tuple[str, ...] = ()
    perimees: tuple[str, ...] = ()

    def describe(self) -> str:
        """Ligne courte pour l'affichage tete haute."""
        ecartees = [m for m in self.candidates if m != self.modalite]
        suffixe = f" (ecarte : {', '.join(ecartees)})" if ecartees else ""
        return f"{self.modalite} -> {self.motif}{suffixe}"


class Arbitre:
    """Arbitre a priorites, avec peremption par modalite."""

    def __init__(self, settings: dict[str, Any]):
        """
        --------------------------------------------------------------------------
        Purpose:
            Charger la table des modalites : priorite et duree de validite.

        Inputs:
            settings (dict): section projet de la configuration

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        modalites = settings.get("modalites")
        if not modalites:
            raise ValueError(
                "La table projet.modalites est vide ou absente. Sans elle, aucune "
                "modalite ne pourrait etre arbitree, et la tortue n'obeirait a rien."
            )
        self._priorite: dict[str, int] = {}
        self._peremption: dict[str, float] = {}
        for nom, entree in modalites.items():
            self._priorite[nom] = int(entree["priorite"])
            peremption = float(entree["peremption_s"])
            if peremption <= 0:
                raise ValueError(
                    f"peremption_s de la modalite '{nom}' vaut {peremption}. "
                    "Une peremption nulle ou negative rendrait toute commande "
                    "immediatement perimee, donc la modalite muette."
                )
            self._peremption[nom] = peremption

        self._commandes: dict[str, Commande] = {}

    @property
    def modalites(self) -> tuple[str, ...]:
        """Noms des modalites declarees, par priorite decroissante."""
        return tuple(sorted(self._priorite, key=lambda n: -self._priorite[n]))

    def soumettre(self, commande: Commande) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Enregistrer l'intention courante d'une modalite. Une modalite ne peut
            avoir qu'une intention a la fois : la nouvelle remplace l'ancienne.

        Inputs:
            commande (Commande): intention horodatee

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        if not commande.urgence and commande.modalite not in self._priorite:
            raise KeyError(
                f"Modalite '{commande.modalite}' non declaree. Modalites connues : "
                f"{sorted(self._priorite)}. Ajouter une entree dans projet.modalites."
            )
        self._commandes[commande.modalite] = commande

    def retirer(self, modalite: str) -> None:
        """Retirer l'intention d'une modalite, par exemple quand l'objet sort du champ."""
        self._commandes.pop(modalite, None)

    def _priorite_de(self, commande: Commande) -> int:
        if commande.urgence:
            return PRIORITE_ARRET_URGENCE
        return self._priorite[commande.modalite]

    def _peremption_de(self, commande: Commande) -> float:
        # Une commande d'urgence perime selon sa propre modalite si elle en a une,
        # sinon selon la peremption la plus courte declaree : un arret d'urgence ne
        # doit pas rester colle indefiniment apres la disparition du geste.
        if commande.modalite in self._peremption:
            return self._peremption[commande.modalite]
        return min(self._peremption.values())

    def arbitrer(self, instant: float) -> Arbitrage:
        """
        --------------------------------------------------------------------------
        Purpose:
            Choisir la commande qui pilote la tortue a cet instant.

            Trois regles, dans cet ordre : une commande perimee est ecartee ; une
            commande d'urgence l'emporte sur tout ; a egalite de priorite, la plus
            recente gagne. Sans commande valide, la tortue est ARRETEE, ce qui est
            la seule sortie sure : conserver la derniere consigne, comme le
            faisaient les rendus etudiants, laisse la tortue partir toute seule.

        Inputs:
            instant (float): instant courant, meme base de temps que les commandes

        Outputs:
            arbitrage (Arbitrage): consigne retenue et modalites ecartees
        --------------------------------------------------------------------------
        """
        valides: list[Commande] = []
        perimees: list[str] = []
        for commande in self._commandes.values():
            # L'age est borne a zéro : une commande horodatee apres l'instant
            # d'arbitrage est "du futur proche", donc valide, jamais perimee.
            age = max(0.0, instant - commande.instant)
            if age > self._peremption_de(commande):
                perimees.append(commande.modalite)
            else:
                valides.append(commande)

        if not valides:
            return Arbitrage(
                twist=Twist(0.0, 0.0),
                modalite="aucune",
                motif="sans commande valide",
                candidates=(),
                perimees=tuple(perimees),
            )

        # Priorite la plus haute d'abord ; a priorite egale, la plus recente gagne.
        gagnante = max(
            valides,
            key=lambda c: (self._priorite_de(c), c.instant),
        )

        return Arbitrage(
            twist=gagnante.twist,
            modalite=gagnante.modalite,
            motif=gagnante.motif,
            candidates=tuple(c.modalite for c in valides),
            perimees=tuple(perimees),
        )


@dataclass
class JournalArbitrage:
    """
    Journal des changements de modalite.

    N'enregistre QUE les changements, pas chaque trame : a trente images par
    seconde, journaliser chaque arbitrage remplirait l'ecran sans rien apprendre.
    """

    entrees: list[tuple[float, str, str]] = field(default_factory=list)
    _derniere: str = ""

    def observer(self, instant: float, arbitrage: Arbitrage) -> bool:
        """
        --------------------------------------------------------------------------
        Purpose:
            Enregistrer l'arbitrage s'il change la modalite active.

        Inputs:
            instant (float): instant courant
            arbitrage (Arbitrage): decision rendue

        Outputs:
            change (bool): vrai si la modalite active a change
        --------------------------------------------------------------------------
        """
        if arbitrage.modalite == self._derniere:
            return False
        self._derniere = arbitrage.modalite
        self.entrees.append((instant, arbitrage.modalite, arbitrage.motif))
        return True
