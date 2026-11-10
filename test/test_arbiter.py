"""
test_arbiter.py - Preuves du contrat d'arbiter.py (Projet, 6MIG841).

C'est le module le plus important a tester : l'arbitrage entre geste, voix et objet
est la contribution propre du Projet, la ou les rendus etudiants melangeaient deux
modalites au plus par un `if/elif` implicite (arbiter.py, en-tete).

Arbitre.arbitrer(instant) est PUR : aucune horloge n'est jamais lue, chaque instant
est un float choisi explicitement dans le test (workflow.md, regle de determinisme).
"""

from __future__ import annotations

import copy

import pytest

from arbiter import Arbitrage, Arbitre, Commande, JournalArbitrage
from ihr_ros.backends.base import Twist


# ---------------------------------------------------------------------------
# 1. Priorite declaree : geste (30) > voix (20) > objet (10).
# ---------------------------------------------------------------------------

def test_priorite_plus_haute_gagne_entre_deux_commandes_fraiches(projet_cfg):
    """geste (priorite 30) l'emporte sur objet (priorite 10) quand les deux sont fraiches."""
    arbitre = Arbitre(projet_cfg)
    arbitre.soumettre(Commande("objet", Twist(1.0, 0.0), instant=10.0))
    arbitre.soumettre(Commande("geste", Twist(0.0, 1.0), instant=10.0))

    arbitrage = arbitre.arbitrer(10.0)

    assert arbitrage.modalite == "geste"
    assert arbitrage.twist == Twist(0.0, 1.0)


# ---------------------------------------------------------------------------
# 2. Arret d'urgence : l'emporte sur tout, meme une commande normale plus fraiche et
#    de priorite declaree plus haute.
# ---------------------------------------------------------------------------

def test_urgence_bat_une_commande_normale_plus_fraiche_et_plus_prioritaire(projet_cfg):
    """
    Une commande d'urgence l'emporte TOUJOURS, meme sur une commande normale plus
    recente et dont la modalite est declaree avec une priorite plus haute. C'est le
    quatrieme cas ajoute par le solutionnaire, absent des trois rendus etudiants
    (arbiter.py, en-tete) : un arret d'urgence qui devrait attendre son tour de
    priorite n'en est pas un.
    """
    arbitre = Arbitre(projet_cfg)
    # "geste" est la modalite de PLUS haute priorite declaree (30) et sa commande est
    # la plus RECENTE (instant 12.0 > 11.0). Elle doit quand meme perdre.
    arbitre.soumettre(Commande("geste", Twist(0.0, 1.0), instant=12.0, motif="geste normal"))
    # "objet" (priorite declaree la plus basse, 10) porte ici l'urgence : sa priorite
    # effective devient PRIORITE_ARRET_URGENCE (1000), au-dessus de tout.
    arbitre.soumettre(Commande("objet", Twist(0.0, 0.0), instant=11.0,
                               urgence=True, motif="arret d'urgence"))

    arbitrage = arbitre.arbitrer(12.0)

    assert arbitrage.modalite == "objet"
    assert arbitrage.twist == Twist(0.0, 0.0)
    assert arbitrage.motif == "arret d'urgence"


# ---------------------------------------------------------------------------
# 3. Peremption : une commande trop vieille est ecartee ; sans commande valide,
#    arret de securite.
# ---------------------------------------------------------------------------

def test_commande_perimee_est_ecartee_et_la_tortue_sarrete(projet_cfg):
    """
    Sans commande valide, la sortie est un twist EXACTEMENT nul et la modalite
    'aucune' : c'est la seule sortie sure (arbiter.py, docstring d'arbitrer). Les
    rendus etudiants conservaient la derniere consigne, ce qui laissait la tortue
    partir seule vers une position perimee depuis longtemps.
    """
    arbitre = Arbitre(projet_cfg)
    # "objet" perime a 1.5 s (ihr_config.json). Deposee a l'instant 0, arbitree a 2.0 :
    # age = 2.0 > 1.5, perimee.
    arbitre.soumettre(Commande("objet", Twist(1.0, 0.0), instant=0.0))

    arbitrage = arbitre.arbitrer(2.0)

    assert arbitrage.modalite == "aucune"
    assert arbitrage.twist == Twist(0.0, 0.0)
    assert arbitrage.perimees == ("objet",)


# ---------------------------------------------------------------------------
# 4. LE test de non-regression : une commande dont l'instant est dans le FUTUR par
#    rapport a l'instant d'arbitrage doit rester valide.
# ---------------------------------------------------------------------------

def test_commande_du_futur_proche_reste_valide_et_nest_pas_supprimee(projet_cfg):
    """
    Regression mesuree le 2026-09-18 (arbiter.py, commentaire dans `arbitrer`) : quand
    une modalite tourne dans son propre fil (la voix, via FilVocal), elle peut deposer
    une commande horodatee APRES que la boucle video a capture l'instant avec lequel
    elle arbitrera. Une premiere version de l'arbitre traitait cet ecart comme une
    peremption et SUPPRIMAIT la commande : la modalite vocale n'atteignait alors
    jamais la tortue, une commande deposee a 323339.92 disparaissait avant l'arbitrage
    suivant a 323341.79, et le journal n'affichait que "aucune".

    Le correctif borne l'age a 0 au lieu de le laisser negatif
    (age = max(0.0, instant - commande.instant)) : une commande "du futur" a un age nul,
    donc jamais perimee pour cette seule raison. Ce test verifie les DEUX temps du
    defaut mesure : la commande doit survivre au premier arbitrage (l'instant
    d'arbitrage est ANTERIEUR a l'instant de la commande), et elle doit aussi survivre
    a un second arbitrage plus tardif, donc ne pas avoir ete supprimee au passage.
    """
    arbitre = Arbitre(projet_cfg)
    # Commande deposee "dans le futur" relatif : instant=100.0, mais l'arbitrage qui
    # suit immediatement porte un instant plus ancien, 90.0 (le fil video a capture
    # son horodatage avant que le fil vocal ne depose sa commande).
    arbitre.soumettre(Commande("voix", Twist(1.0, 0.0), instant=100.0, motif="avance"))

    premier = arbitre.arbitrer(90.0)
    assert premier.modalite == "voix"
    assert premier.perimees == ()

    # Un second arbitrage, desormais POSTERIEUR a l'instant de la commande (101.0 >
    # 100.0), doit encore la voir : age = max(0, 101.0-100.0) = 1.0, <= peremption_s
    # de "voix" (5.0). Si le premier arbitrage l'avait supprimee a tort, ce second
    # appel ne verrait plus rien.
    second = arbitre.arbitrer(101.0)
    assert second.modalite == "voix"


# ---------------------------------------------------------------------------
# 5. Egalite de priorite : la commande la plus recente gagne.
# ---------------------------------------------------------------------------

def test_a_egalite_de_priorite_la_commande_la_plus_recente_gagne(projet_cfg):
    """
    Les trois modalites declarees ont des priorites toutes distinctes (30/20/10) :
    la seule facon d'obtenir une VRAIE egalite est deux commandes d'urgence, dont la
    priorite effective est toujours PRIORITE_ARRET_URGENCE quelle que soit la
    modalite porteuse. Les deux instants sont choisis assez proches pour que ni l'une
    ni l'autre ne perime (age <= peremption_s de sa propre modalite).
    """
    arbitre = Arbitre(projet_cfg)
    arbitre.soumettre(Commande("geste", Twist(0.0, 1.0), instant=5.9, urgence=True))
    arbitre.soumettre(Commande("objet", Twist(0.0, -1.0), instant=6.0, urgence=True))

    arbitrage = arbitre.arbitrer(6.0)

    assert arbitrage.modalite == "objet"
    assert arbitrage.twist == Twist(0.0, -1.0)


# ---------------------------------------------------------------------------
# 6. retirer() : une modalite retiree n'est plus candidate.
# ---------------------------------------------------------------------------

def test_retirer_une_modalite_la_rend_invisible_a_larbitrage(projet_cfg):
    """Apres retirer('objet'), arbitrer ne voit plus la commande deposee pour 'objet'."""
    arbitre = Arbitre(projet_cfg)
    arbitre.soumettre(Commande("objet", Twist(1.0, 0.0), instant=5.0))
    arbitre.retirer("objet")

    arbitrage = arbitre.arbitrer(5.0)

    assert arbitrage.modalite == "aucune"


# ---------------------------------------------------------------------------
# 7. soumettre() avec une modalite non declaree et non urgente : KeyError explicite.
# ---------------------------------------------------------------------------

def test_soumettre_une_modalite_inconnue_leve_keyerror_nommant_les_connues(projet_cfg):
    """Une modalite absente de projet.modalites et non urgente est un KeyError, avec
    la liste des modalites declarees dans le message (pour corriger la configuration)."""
    arbitre = Arbitre(projet_cfg)

    with pytest.raises(KeyError) as excinfo:
        arbitre.soumettre(Commande("clavier", Twist(0.0, 0.0), instant=0.0))

    message = str(excinfo.value)
    assert "clavier" in message
    for modalite in ("geste", "voix", "objet"):
        assert modalite in message


# ---------------------------------------------------------------------------
# 8. Chemins d'echec de la construction de l'arbitre.
# ---------------------------------------------------------------------------

def test_configuration_vide_est_refusee():
    """Sans aucune cle, il n'y a pas de table de modalites : ValueError."""
    with pytest.raises(ValueError):
        Arbitre({})


def test_configuration_sans_cle_modalites_est_refusee(projet_cfg):
    """La cle 'modalites' absente equivaut a une table vide : ValueError."""
    cfg = copy.deepcopy(projet_cfg)
    del cfg["modalites"]

    with pytest.raises(ValueError):
        Arbitre(cfg)


def test_peremption_nulle_ou_negative_est_refusee_en_nommant_la_modalite(projet_cfg):
    """Une peremption_s <= 0 rendrait la modalite immediatement muette : ValueError qui
    nomme la modalite fautive, pour que l'erreur pointe droit vers ihr_config.json."""
    cfg = copy.deepcopy(projet_cfg)
    cfg["modalites"]["geste"]["peremption_s"] = 0

    with pytest.raises(ValueError, match="geste"):
        Arbitre(cfg)


# ---------------------------------------------------------------------------
# 9. Arbitrage.describe() : modalite retenue ET modalites ecartees.
# ---------------------------------------------------------------------------

def test_describe_nomme_la_modalite_retenue_et_liste_les_ecartees(projet_cfg):
    """
    describe() doit rendre l'arbitrage COMPREHENSIBLE a l'ecran : c'est exactement ce
    que le rendu Projet2 ne montrait pas (arbiter.py, en-tete, defaut n 1).
    """
    arbitre = Arbitre(projet_cfg)
    arbitre.soumettre(Commande("geste", Twist(0.0, 1.0), instant=1.0, motif="m-geste"))
    arbitre.soumettre(Commande("objet", Twist(1.0, 0.0), instant=1.0, motif="m-objet"))

    arbitrage = arbitre.arbitrer(1.0)
    texte = arbitrage.describe()

    assert "geste" in texte
    assert "objet" in texte


# ---------------------------------------------------------------------------
# 10. JournalArbitrage : n'enregistre que les CHANGEMENTS de modalite active.
# ---------------------------------------------------------------------------

def test_journal_nenregistre_quun_seul_changement_pour_cinq_observations_identiques():
    """Cinq observations consecutives de la meme modalite ne produisent qu'UNE entree :
    a 30 images par seconde, journaliser chaque arbitrage remplirait l'ecran pour rien
    (arbiter.py, docstring de JournalArbitrage)."""
    journal = JournalArbitrage()
    arbitrage = Arbitrage(Twist(0.0, 0.0), "geste", "motif", (), ())

    for instant in range(5):
        journal.observer(float(instant), arbitrage)

    assert len(journal.entrees) == 1


def test_journal_ajoute_une_entree_quand_la_modalite_change():
    """Un changement de modalite active produit une SECONDE entree."""
    journal = JournalArbitrage()
    arbitrage_a = Arbitrage(Twist(0.0, 0.0), "geste", "motif", (), ())
    arbitrage_b = Arbitrage(Twist(0.0, 0.0), "objet", "motif2", (), ())

    for instant in range(5):
        journal.observer(float(instant), arbitrage_a)
    journal.observer(5.0, arbitrage_b)

    assert len(journal.entrees) == 2


# ---------------------------------------------------------------------------
# 11. Arbitre.modalites : ordre de priorite decroissante.
# ---------------------------------------------------------------------------

def test_modalites_est_ordonnee_par_priorite_decroissante(projet_cfg):
    """geste (30) avant voix (20) avant objet (10), dans cet ordre exact."""
    arbitre = Arbitre(projet_cfg)
    assert arbitre.modalites == ("geste", "voix", "objet")
