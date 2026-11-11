# Plan 2 - calculer_consigne

Test command: python -m pytest test/test_navigator.py -q

1. Lire la docstring complète de `calculer_consigne` dans `code/navigator.py`, les fonctions utilitaires `_saturer`, `distance` et `heading_error`, la classe `Consigne`, et les six tests de `calculer_consigne` dans `test/test_navigator.py` (arrivée, approche, orientation, saturation, cible à gauche, cible à droite).
2. Implémenter uniquement `calculer_consigne` dans `code/navigator.py`. Lire `angular_gain`, `linear_speed`, `goal_tolerance`, `heading_tolerance_rad`, `vitesse_lineaire_max` et `vitesse_angulaire_max` dans `settings`, sans aucune valeur écrite en dur. Calculer la distance et l'erreur de cap, puis traiter dans cet ordre : (a) arrivée si la distance est inférieure à `goal_tolerance` : twist nul, `arrivee=True`, phase `"arrivee"`; (b) orientation si la valeur absolue de l'erreur de cap dépasse `heading_tolerance_rad` : `linear_x = 0`, `angular_z = _saturer(gain * erreur, vitesse_angulaire_max)`, phase `"orientation"`; (c) sinon approche : `linear_x = _saturer(linear_speed, vitesse_lineaire_max)` et la même vitesse angulaire saturée, phase `"approche"`. Retourner un `Consigne` avec l'erreur de cap et la distance restante.
3. Lancer `python -m pytest test/test_navigator.py -q`.
4. En cas d'échec, utiliser le résultat du test pour apporter une correction minimale dans `code/navigator.py`, puis relancer la même commande. Répéter au maximum trois fois; si les tests échouent encore, indiquer dans `progress.md` que le plan est bloqué et consigner l'échec.
