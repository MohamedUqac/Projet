# Plan 1 - LisseurCible.mettre_a_jour

Test command: python -m pytest test/test_navigator.py -k mesure -q

1. Lire la docstring complète de `LisseurCible.mettre_a_jour` et de la classe `LisseurCible` dans `code/navigator.py`, ainsi que les deux tests `test_premiere_mesure_est_adoptee_telle_quelle_sans_lissage` et `test_deuxieme_mesure_se_deplace_de_exactement_alpha_vers_la_nouvelle_valeur` dans `test/test_navigator.py`.
2. Implémenter uniquement `LisseurCible.mettre_a_jour` dans `code/navigator.py`. Si aucune valeur n'est encore mémorisée (`self._valeur` vaut `None`), adopter la mesure telle quelle, sans lissage. Sinon appliquer le filtre exponentiel sur x et y séparément : `alpha * mesure + (1 - alpha) * ancienne_valeur`, avec `self._alpha`. Mémoriser le résultat dans `self._valeur` et le retourner sous forme de tuple `(x, y)`. Ne pas modifier `__init__`, `reset` ni les autres fonctions.
3. Lancer `python -m pytest test/test_navigator.py -k mesure -q`.
4. En cas d'échec, utiliser le résultat du test pour apporter une correction minimale dans `code/navigator.py`, puis relancer la même commande. Répéter au maximum trois fois; si les tests échouent encore, indiquer dans `progress.md` que le plan est bloqué et consigner l'échec.
