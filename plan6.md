# Plan 6 - construire_schema

Test command: `python -m pytest test/test_regleur.py -q`

1. Lire la docstring complete de `construire_schema` dans `code/regleur.py`, les cles `noms` calculees et la validation de configuration vide qui la precede. Lire les tests existants dans `test/test_regleur.py` : `test_construire_schema_sans_parametre_est_refuse`, `test_construire_schema_enumere_les_noms_declares` et `test_construire_schema_suit_une_configuration_differente_pas_une_liste_figee`. Lire aussi `Regleur._lire_reglages` pour respecter la forme de reponse consommee.
2. Completer uniquement `construire_schema` dans `code/regleur.py`, en conservant la validation existante qui leve `ValueError` quand aucun parametre n'est declare. Construire le schema JSON attendu par Ollama et par le code consommateur ; l'enumeration de `parametre` doit provenir des noms de la configuration recue (la variable `noms` deja calculee), jamais d'une liste de parametres ecrite en dur.
3. Conserver la forme du schema testee : `schema["properties"]["reglages"]["items"]["properties"]["parametre"]["enum"]` contient les noms declares. Ne pas modifier le format des reglages, `Regleur`, les autres fonctions ou les tests.
4. Lancer `python -m pytest test/test_regleur.py -q`. Tous les tests du fichier doivent passer, notamment ceux qui utilisent une configuration alternative disjointe pour verifier que l'enumeration suit reellement l'argument.
5. En cas d'echec, examiner l'assertion et apporter une correction minimale dans `code/regleur.py` uniquement, puis relancer la meme commande. Repeter au maximum trois fois ; si le test echoue encore, signaler le plan comme bloque dans `progress_B.md` et consigner le test en echec et le resultat observe.
