"""
regleur.py - Le LLM regle le controleur, il ne commande jamais la tortue.

Idee reprise du MPCxLLM de ForzaETH (spec.md, « Le LLM regle le controleur ») :
plutot que d'emettre un mouvement, le modele ajuste des PARAMETRES DECLARES du
controleur de navigation (navigator.py), qui lui seul emet le mouvement. Le reglage
ne passe jamais par l'arbitre (arbiter.py) : il ne peut donc pas contourner l'arret
d'urgence, qui vit entierement ailleurs, inchange par ce module.

Cinq exigences (plan07.md, tableau du regleur), toutes tenues ici :
  1. seuls les parametres DECLARES dans projet.regleur.parametres sont reglables ;
  2. chaque parametre porte ses bornes et sa description dans cette meme table ;
  3. la valeur est bornee DEUX FOIS : le schema JSON impose deja un minimum et un
     maximum au modele (R9, une contrainte), et `_lire_reglages` re-borne CE CODE
     (une garantie) ;
  4. un parametre hors enumeration est REJETE, jamais cree ;
  5. une reponse illisible ne regle RIEN : `regler` rend une liste vide plutot que
     de lever, le controleur restant intact, seule issue sure.

`appliquer` rend toujours une COPIE de la configuration recue : l'appelant doit
pouvoir revenir en arriere si le comportement empire (plan07.md).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reglage:
    """Un parametre regle, avec sa valeur re-bornee et la valeur brute rendue par le modele."""

    parametre: str
    valeur: float
    valeur_brute: float
    justification: str = ""


@dataclass(frozen=True)
class ResultatReglage:
    """Resultat d'une tentative de reglage."""

    reglages: tuple[Reglage, ...]
    brut: str
    tentatives: int
    erreur: str = ""

    @property
    def ok(self) -> bool:
        return self.erreur == ""


def construire_schema(parametres_cfg: dict[str, Any]) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Construire le schema JSON impose au modele. L'enumeration des noms de
        parametre est derivee de la configuration : aucun nom de parametre
        reglable n'est ecrit en dur ici, et un parametre absent de cette table
        ne peut structurellement pas apparaitre dans une reponse valide.

    Inputs:
        parametres_cfg (dict): section projet.regleur.parametres de la
            configuration (chaque entree porte 'min', 'max', 'description')

    Outputs:
        schema (dict): schema JSON au format attendu par Ollama
    --------------------------------------------------------------------------
    """
    noms = sorted(parametres_cfg)
    if not noms:
        raise ValueError(
            "projet.regleur.parametres est vide ou absent. Sans parametre declare, "
            "aucun reglage ne pourrait jamais etre propose."
        )
    # Indice : l'enumeration 'enum' vient de noms, jamais d'une liste ecrite en dur
    # Tests : test_construire_schema_enumere_les_noms_declares
    raise NotImplementedError(
        "fonction 'construire_schema' a implementer (voir l'enonce et les tests cites)"
    )


def construire_prompt(consigne: str, parametres_cfg: dict[str, Any]) -> str:
    """
    --------------------------------------------------------------------------
    Purpose:
        Composer l'invite. Le catalogue de parametres, avec ses bornes et sa
        description, vient de la configuration : le vocabulaire reglable se
        change sans toucher au code.

    Inputs:
        consigne (str): phrase de l'utilisateur
        parametres_cfg (dict): section projet.regleur.parametres

    Outputs:
        prompt (str): texte envoye au modele
    --------------------------------------------------------------------------
    """
    lignes = []
    for nom in sorted(parametres_cfg):
        entree = parametres_cfg[nom]
        lignes.append(
            f"- {nom} [{entree['min']} .. {entree['max']}] : {entree['description']}"
        )
    catalogue = "\n".join(lignes)

    return (
        "Tu regles les parametres d'un controleur de navigation pour un robot "
        "tortue. Tu ne commandes JAMAIS le robot directement : tu choisis "
        "UNIQUEMENT parmi les parametres declares ci-dessous, chacun avec ses "
        "bornes.\n\n"
        f"Parametres reglables :\n{catalogue}\n\n"
        f"Consigne de l'utilisateur : « {consigne} »\n\n"
        "Si la consigne ne concerne AUCUN de ces parametres (une question hors "
        "sujet, une plaisanterie, une demande de conversation), reponds avec une "
        "liste 'reglages' VIDE plutot que d'inventer un reglage sans rapport.\n"
        "Reponds uniquement par l'objet JSON demande."
    )


class Regleur:
    """Regleur de controleur, adosse a Ollama."""

    def __init__(self, parametres_cfg: dict[str, Any], connexion_cfg: dict[str, Any],
                 client: Any | None = None) -> None:
        """
        --------------------------------------------------------------------------
        Purpose:
            Preparer le regleur. Le client Ollama est injectable pour que les
            tests tournent sans demon reel. La connexion (modele, hote, delais)
            vient de la section 'devoir2' de la configuration : c'est deja
            l'unique proprietaire de ces identifiants (code-style.md, R2), le
            regleur ne les redeclare pas.

        Inputs:
            parametres_cfg (dict): section projet.regleur.parametres
            connexion_cfg (dict): section devoir2 de la configuration
                (llm_model, llm_host, llm_timeout_seconds, llm_max_attempts)
            client (Any | None): client Ollama, cree ici s'il est absent

        Outputs:
            aucun
        --------------------------------------------------------------------------
        """
        self._parametres_cfg = parametres_cfg
        self._schema = construire_schema(parametres_cfg)
        self._modele = str(connexion_cfg["llm_model"])
        self._timeout = float(connexion_cfg["llm_timeout_seconds"])
        self._max_tentatives = int(connexion_cfg["llm_max_attempts"])
        if self._max_tentatives < 1:
            raise ValueError(
                f"llm_max_attempts vaut {self._max_tentatives}. Il faut au moins "
                "une tentative, sinon le regleur echoue sans avoir rien demande."
            )

        if client is not None:
            self._client = client
        else:
            import ollama  # noqa: PLC0415

            self._client = ollama.Client(host=str(connexion_cfg["llm_host"]),
                                         timeout=self._timeout)

    @property
    def schema(self) -> dict[str, Any]:
        """Schema JSON impose au modele."""
        return self._schema

    def regler(self, consigne: str) -> ResultatReglage:
        """
        --------------------------------------------------------------------------
        Purpose:
            Proposer des reglages pour une consigne. Nombre de tentatives BORNE :
            un modele qui ne repond jamais lisiblement ne doit pas geler
            l'appelant. Une reponse illisible, apres toutes les tentatives, rend
            une liste VIDE et une erreur motivee : le controleur reste intact,
            seule issue sure (plan07.md).

        Inputs:
            consigne (str): phrase de l'utilisateur

        Outputs:
            resultat (ResultatReglage): reglages retenus, ou liste vide motivee
        --------------------------------------------------------------------------
        """
        if not consigne or not consigne.strip():
            return ResultatReglage((), "", 0, "consigne vide")

        prompt = construire_prompt(consigne, self._parametres_cfg)
        derniere_erreur = "aucune tentative"
        brut = ""

        for tentative in range(1, self._max_tentatives + 1):
            try:
                reponse = self._client.generate(
                    model=self._modele, prompt=prompt, format=self._schema,
                    options={"temperature": 0.0, "seed": 1},
                )
            except Exception as exc:
                derniere_erreur = f"{type(exc).__name__}: {exc}"
                continue

            brut = self._extraire_texte(reponse)
            reglages, erreur = self._lire_reglages(brut)
            if erreur:
                derniere_erreur = erreur
                continue

            return ResultatReglage(tuple(reglages), brut, tentative)

        return ResultatReglage((), brut, self._max_tentatives, derniere_erreur)

    @staticmethod
    def _extraire_texte(reponse: Any) -> str:
        """Lire le champ 'response', que le client rende un objet ou un dict."""
        if isinstance(reponse, dict):
            return str(reponse.get("response", "")).strip()
        return str(getattr(reponse, "response", "")).strip()

    def _lire_reglages(self, brut: str) -> tuple[list[Reglage], str]:
        """
        --------------------------------------------------------------------------
        Purpose:
            Extraire les reglages d'une reponse JSON. Un parametre hors
            enumeration est REJETE (jamais cree, exigence 4) ; une valeur hors
            borne est RAMENEE a la borne (exigence 3, second bornage cote code).
            Une reponse totalement illisible (pas de JSON, pas d'objet, pas de
            champ 'reglages') est un ECHEC motive, jamais une liste partielle
            devinee.

        Inputs:
            brut (str): texte rendu par le modele

        Outputs:
            reglages (list): reglages retenus (peut etre vide, ce n'est pas un echec)
            erreur (str): motif d'echec, vide si la reponse etait au moins lisible
        --------------------------------------------------------------------------
        """
        if not brut:
            return [], "reponse vide du modele"
        try:
            charge = json.loads(brut)
        except json.JSONDecodeError as exc:
            return [], f"reponse non JSON ({exc}) : {brut[:120]}"

        if not isinstance(charge, dict):
            return [], f"JSON qui n'est pas un objet : {brut[:120]}"

        bruts = charge.get("reglages")
        if not isinstance(bruts, list):
            return [], f"champ 'reglages' absent ou invalide : {brut[:120]}"

        reglages: list[Reglage] = []
        for entree in bruts:
            if not isinstance(entree, dict):
                continue
            nom = entree.get("parametre")
            if not isinstance(nom, str) or nom.strip() not in self._parametres_cfg:
                # Rejete, jamais cree (exigence 4) : le schema contraint deja
                # l'enumeration, mais un appelant direct (ou un modele qui s'en
                # affranchit) peut fournir un nom hors catalogue.
                continue
            nom = nom.strip()
            try:
                valeur_brute = float(entree.get("valeur"))
            except (TypeError, ValueError):
                continue

            bornes = self._parametres_cfg[nom]
            valeur = max(float(bornes["min"]), min(float(bornes["max"]), valeur_brute))
            reglages.append(Reglage(
                parametre=nom, valeur=valeur, valeur_brute=valeur_brute,
                justification=str(entree.get("justification", "")),
            ))

        return reglages, ""


def appliquer(reglages: tuple[Reglage, ...], projet_cfg: dict[str, Any]) -> dict[str, Any]:
    """
    --------------------------------------------------------------------------
    Purpose:
        Appliquer des reglages a une COPIE de la configuration du controleur.
        Jamais a l'original : l'appelant doit pouvoir revenir en arriere si le
        comportement empire (plan07.md, « appliquer rend une copie »).

    Inputs:
        reglages (tuple): reglages a appliquer (deja bornes par Regleur.regler)
        projet_cfg (dict): section 'projet' de la configuration, jamais mutee

    Outputs:
        copie (dict): copie profonde de projet_cfg, avec les reglages appliques
    --------------------------------------------------------------------------
    """
    copie = copy.deepcopy(projet_cfg)
    for reglage in reglages:
        copie[reglage.parametre] = reglage.valeur
    return copie
