"""
test_regleur.py - Preuves du contrat de regleur.py (Projet, 6MIG841, plan07.md).

Le LLM regle le controleur, il ne le commande jamais : ces tests prouvent les
quatre exigences testables hors ligne (paramètre hors enumeration rejete, valeur
hors borne ramenee a la borne, consigne sans rapport -> aucun reglage, appliquer
rend une copie), avec un faux client Ollama, jamais de demon reel (workflow.md R5).
L'epreuve contre le VRAI modele (plan07.md, etape 7) est manuelle, hors de cette
suite : voir .sdd/6mig841-ameliorations/plan07-report.md.
"""

from __future__ import annotations

import copy
import json

import pytest

from regleur import Reglage, Regleur, ResultatReglage, appliquer, construire_schema


class _FauxOllama:
    """Faux client Ollama : rend les reponses de `reponses`, dans l'ordre."""

    def __init__(self, reponses: list[str]) -> None:
        self._reponses = list(reponses)
        self.appels: list[dict] = []

    def generate(self, **kwargs) -> dict:
        self.appels.append(kwargs)
        index = min(len(self.appels) - 1, len(self._reponses) - 1)
        return {"response": self._reponses[index]}


class _OllamaQuiEchoue:
    """Faux client Ollama qui leve a chaque appel."""

    def generate(self, **kwargs):
        raise RuntimeError("demon Ollama injoignable (simule)")


@pytest.fixture
def parametres_cfg(projet_cfg) -> dict:
    """Table projet.regleur.parametres (plan07.md), copie profonde independante."""
    return copy.deepcopy(projet_cfg["regleur"]["parametres"])


# ---------------------------------------------------------------------------
# 1. Parametre hors enumeration : rejete, jamais cree.
# ---------------------------------------------------------------------------

def test_parametre_hors_enumeration_est_rejete(parametres_cfg, devoir2_cfg):
    client = _FauxOllama([json.dumps({
        "reglages": [
            {"parametre": "angular_gain", "valeur": 0.8},
            {"parametre": "vitesse_de_la_lumiere", "valeur": 300000.0},
        ]
    })])
    regleur = Regleur(parametres_cfg, devoir2_cfg, client=client)

    resultat = regleur.regler("tourne plus serre")

    assert resultat.ok
    noms = [r.parametre for r in resultat.reglages]
    assert noms == ["angular_gain"]
    assert "vitesse_de_la_lumiere" not in noms


# ---------------------------------------------------------------------------
# 2. Valeur hors borne : ramenee a la borne (double bornage, R9).
# ---------------------------------------------------------------------------

def test_valeur_hors_borne_est_ramenee_a_la_borne(parametres_cfg, devoir2_cfg):
    borne_max = float(parametres_cfg["angular_gain"]["max"])
    client = _FauxOllama([json.dumps({
        "reglages": [{"parametre": "angular_gain", "valeur": borne_max + 10.0}]
    })])
    regleur = Regleur(parametres_cfg, devoir2_cfg, client=client)

    resultat = regleur.regler("tourne beaucoup plus vite")

    assert len(resultat.reglages) == 1
    reglage = resultat.reglages[0]
    assert reglage.valeur == pytest.approx(borne_max)
    assert reglage.valeur_brute == pytest.approx(borne_max + 10.0)


def test_valeur_sous_la_borne_min_est_ramenee_a_la_borne(parametres_cfg, devoir2_cfg):
    borne_min = float(parametres_cfg["suivi_lisse_alpha"]["min"])
    client = _FauxOllama([json.dumps({
        "reglages": [{"parametre": "suivi_lisse_alpha", "valeur": borne_min - 1.0}]
    })])
    regleur = Regleur(parametres_cfg, devoir2_cfg, client=client)

    resultat = regleur.regler("lisse beaucoup plus")

    assert resultat.reglages[0].valeur == pytest.approx(borne_min)


# ---------------------------------------------------------------------------
# 3. Consigne sans rapport : aucun reglage, controle negatif.
# ---------------------------------------------------------------------------

def test_consigne_sans_rapport_ne_regle_rien(parametres_cfg, devoir2_cfg):
    """Le controle negatif qui compte (plan07.md) : « raconte une blague » rend une
    liste de reglages VIDE, jamais un reglage invente sans rapport."""
    client = _FauxOllama([json.dumps({"reglages": []})])
    regleur = Regleur(parametres_cfg, devoir2_cfg, client=client)

    resultat = regleur.regler("raconte une blague")

    assert resultat.ok
    assert resultat.reglages == ()


# ---------------------------------------------------------------------------
# 4. Appliquer rend une COPIE : l'appelant ne mute jamais.
# ---------------------------------------------------------------------------

def test_appliquer_ne_mute_pas_lappelant(projet_cfg):
    original = copy.deepcopy(projet_cfg)
    reglages = (Reglage(parametre="angular_gain", valeur=0.9, valeur_brute=0.9),)

    resultat = appliquer(reglages, projet_cfg)

    assert projet_cfg == original  # l'appelant n'a pas change
    assert resultat["angular_gain"] == 0.9
    assert resultat is not projet_cfg


# ---------------------------------------------------------------------------
# 5. Chemins d'echec.
# ---------------------------------------------------------------------------

def test_reponse_illisible_ne_regle_rien_apres_toutes_les_tentatives(parametres_cfg, devoir2_cfg):
    """Une reponse illisible, apres toutes les tentatives : liste vide ET erreur motivee,
    jamais une exception (le controleur reste intact, seule issue sure)."""
    cfg = copy.deepcopy(devoir2_cfg)
    cfg["llm_max_attempts"] = 2
    client = _FauxOllama(["ceci n'est pas du JSON", "encore illisible"])

    resultat = regleur_avec(client, parametres_cfg, cfg)

    assert resultat.ok is False
    assert resultat.reglages == ()
    assert resultat.erreur != ""
    assert len(client.appels) == 2


def test_client_qui_leve_est_rattrape_et_motive(parametres_cfg, devoir2_cfg):
    cfg = copy.deepcopy(devoir2_cfg)
    cfg["llm_max_attempts"] = 1
    regleur = Regleur(parametres_cfg, cfg, client=_OllamaQuiEchoue())

    resultat = regleur.regler("regle le gain")  # ne doit lever aucune exception

    assert resultat.ok is False
    assert "injoignable" in resultat.erreur or "RuntimeError" in resultat.erreur


def test_consigne_vide_ne_contacte_pas_le_modele(parametres_cfg, devoir2_cfg):
    client = _FauxOllama(["ignore"])
    regleur = Regleur(parametres_cfg, devoir2_cfg, client=client)

    resultat = regleur.regler("   ")

    assert resultat.reglages == ()
    assert client.appels == []


def test_max_tentatives_sous_un_est_refuse(parametres_cfg, devoir2_cfg):
    cfg = copy.deepcopy(devoir2_cfg)
    cfg["llm_max_attempts"] = 0

    with pytest.raises(ValueError):
        Regleur(parametres_cfg, cfg, client=_FauxOllama([]))


def test_construire_schema_sans_parametre_est_refuse():
    with pytest.raises(ValueError):
        construire_schema({})


def test_construire_schema_enumere_les_noms_declares(parametres_cfg):
    schema = construire_schema(parametres_cfg)
    enum = schema["properties"]["reglages"]["items"]["properties"]["parametre"]["enum"]
    assert set(enum) == set(parametres_cfg)


def test_construire_schema_suit_une_configuration_differente_pas_une_liste_figee(parametres_cfg):
    """
    Revue finale (constat Important) : `parametres_cfg` est TOUJOURS une copie de la
    meme configuration de production (ihr_config.json) dans ce fichier, donc
    `set(enum) == set(parametres_cfg)` serait vrai aussi bien pour une implementation
    qui lit reellement l'argument que pour une implementation qui contiendrait la liste
    ACTUELLE des cles ecrite en dur (l'indice du trou le dit explicitement : « jamais
    une liste ecrite en dur »). Ce test appelle `construire_schema` avec un second jeu
    de noms de parametres, DISJOINT du premier, pour prouver que l'enumeration suit
    reellement l'argument recu et non une liste figee au moment de l'ecriture.
    """
    autre_configuration = {
        "vitesse_exploration": {"min": 0.0, "max": 1.0, "description": "vitesse de test"},
        "rayon_detection": {"min": 0.0, "max": 5.0, "description": "rayon de test"},
    }
    assert set(autre_configuration).isdisjoint(parametres_cfg), (
        "la configuration alternative doit etre disjointe de la configuration de "
        "production, sinon ce test ne distingue rien du test existant"
    )

    schema = construire_schema(autre_configuration)
    enum = schema["properties"]["reglages"]["items"]["properties"]["parametre"]["enum"]

    assert set(enum) == set(autre_configuration)
    assert set(enum).isdisjoint(parametres_cfg)


def regleur_avec(client, parametres_cfg, connexion_cfg) -> ResultatReglage:
    """Petite fabrique pour eviter de repeter la construction dans les tests d'echec."""
    regleur = Regleur(parametres_cfg, connexion_cfg, client=client)
    return regleur.regler("regle le gain plus fort")
