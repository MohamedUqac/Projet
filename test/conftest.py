"""
conftest.py - Amorce des tests du Projet (6MIG841).

Trois responsabilites :
  1. Rendre `navigator`, `arbiter`, `object_tracker` et `gesture_commands` importables
     depuis `Projet/code`, sans dependre du repertoire d'ou pytest est lance.
  2. Rendre `fabrique_mains` (Devoir1/test) importable, pour REUTILISER ses mains
     synthetiques plutot que d'en recrire une copie ici (gesture_commands reutilise
     thumb_detector du Devoir 1 sans le modifier ; les tests suivent la meme regle).
  3. Exposer trois fixtures de configuration, chacune une COPIE independante de la
     section correspondante de ihr_config.json : `projet_cfg`, `devoir1_cfg`,
     `turtlesim_cfg`. Une copie profonde, jamais le dict partage rendu par
     `ihr_ros.config` (qui le met en cache), pour qu'un test qui degrade un seuil
     (gain agrandi pour forcer une saturation, peremption mise a zero pour une
     ValueError) ne contamine jamais le test suivant ni le fichier
     Lab1/code/ihr_config.json lui-meme.

`ihr_ros` est deja installe en mode editable dans le venv du laboratoire (voir
Lab1/code/pyproject.toml) : seuls les repertoires `code/` et le `test/` du Devoir 1
doivent etre ajoutes a sys.path ici.

Aucune camera, aucun MediaPipe, aucun modele YOLO, aucun ROS2 : voir workflow.md,
regle R5.
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import pytest

_RACINE = Path(__file__).resolve().parent.parent.parent
_PROJET_CODE = _RACINE / "Projet" / "code"
_DEVOIR1_CODE = _RACINE / "Devoir1" / "code"
_DEVOIR1_TEST = _RACINE / "Devoir1" / "test"

# Insere une seule fois chacun, avant tout import de module de test. L'ordre importe
# peu ici : aucun de ces trois repertoires ne porte de module de meme nom qu'un autre.
for _chemin in (_PROJET_CODE, _DEVOIR1_CODE, _DEVOIR1_TEST):
    if str(_chemin) not in sys.path:
        sys.path.insert(0, str(_chemin))

from ihr_ros import config  # noqa: E402  (import volontairement apres sys.path)

_VARIABLES_ENV_A_RESTAURER = ("IHR_CONFIG", "IHR_BACKEND")


@pytest.fixture(autouse=True)
def _restaurer_environnement_ihr():
    """
    Sauvegarde IHR_CONFIG et IHR_BACKEND avant chaque test et les restaure apres, puis
    force un rechargement de la configuration pour purger le cache de ihr_ros.config.

    Meme protocole que Lab1/test/conftest.py et Devoir2/test/conftest.py (workflow.md
    R5 : un test doit pouvoir tourner seul ou dans la suite complete, avec le meme
    resultat).
    """
    valeurs_avant = {nom: os.environ.get(nom) for nom in _VARIABLES_ENV_A_RESTAURER}
    yield
    for nom, valeur in valeurs_avant.items():
        if valeur is None:
            os.environ.pop(nom, None)
        else:
            os.environ[nom] = valeur
    config.load(force_reload=True)


@pytest.fixture
def projet_cfg() -> dict:
    """
    --------------------------------------------------------------------------
    Purpose:
        Fournir une copie profonde de la section 'projet' de ihr_config.json.
        Profonde et non superficielle : 'modalites' est un dict de dicts, et un
        test d'arbitrage (peremption mise a zero, priorite modifiee) doit pouvoir
        muter une sous-entree sans toucher au dict mis en cache par ihr_ros.config.

    Inputs:
        aucun

    Outputs:
        section (dict): copie de la section 'projet'
    --------------------------------------------------------------------------
    """
    return copy.deepcopy(config.section("projet"))


@pytest.fixture
def devoir1_cfg() -> dict:
    """Copie profonde de la section 'devoir1' de ihr_config.json (seuils du Devoir 1,
    reutilises tels quels par gesture_commands.reconnaitre)."""
    return copy.deepcopy(config.section("devoir1"))


@pytest.fixture
def turtlesim_cfg() -> dict:
    """Copie profonde de la section 'turtlesim' de ihr_config.json (dimensions du
    canevas, pose de depart)."""
    return copy.deepcopy(config.section("turtlesim"))


@pytest.fixture
def devoir2_cfg() -> dict:
    """Copie profonde de la section 'devoir2' de ihr_config.json (plan07 : catalogue
    d'actions pour arbiter_node, connexion Ollama pour regleur.Regleur)."""
    return copy.deepcopy(config.section("devoir2"))


@pytest.fixture
def topics_cfg() -> dict:
    """Copie profonde de la section 'topics' de ihr_config.json (plan07 : noms de
    canal pour gesture_node, object_node et arbiter_node)."""
    return copy.deepcopy(config.section("topics"))
