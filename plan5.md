# Plan 5 - choisir_meilleure

Test command: `python -m pytest test/test_object_tracker.py -q`

1. Lire la docstring complete de `choisir_meilleure` dans `code/object_tracker.py`, ainsi que la dataclass `Detection`. Lire les deux tests existants dans `test/test_object_tracker.py` : `test_choisir_meilleure_retient_la_plus_confiante_pas_la_derniere` et `test_choisir_meilleure_sur_liste_vide_rend_none`.
2. Implementer uniquement `choisir_meilleure` dans `code/object_tracker.py`. Pour une sequence non vide, retourner l'objet `Detection` dont `confiance` est la plus elevee. Ne pas retourner systematiquement la derniere detection parcourue. Pour une sequence vide, retourner `None`.
3. Ne modifier ni `detections_depuis_resultat`, ni `ObjectTracker`, ni les tests. La fonction reste pure et ne doit pas trier ou modifier la sequence recue.
4. Lancer `python -m pytest test/test_object_tracker.py -q`. Tous les tests du fichier doivent passer, y compris les tests de filtrage, de conversion et de chemins d'echec.
5. En cas d'echec, examiner l'assertion et apporter une correction minimale dans `code/object_tracker.py` uniquement, puis relancer la meme commande. Repeter au maximum trois fois ; si le test echoue encore, signaler le plan comme bloque dans `progress_B.md` et consigner le test en echec et le resultat observe.
