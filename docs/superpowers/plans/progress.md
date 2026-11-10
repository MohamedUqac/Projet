# Progression — lot B (Arbiter.arbitrer, reconnaitre)

Utiliser `[x]` uniquement lorsque l'étape et ses tests ciblés réussissent. Si
trois tentatives de correction ne résolvent pas un échec, marquer l'étape
d'implémentation `[!]` et consigner le test en échec ainsi que le résultat
observé. Ne modifier que ce fichier.

## plan3.md
- [ ] Lire le contrat de `arbitrer` et ses tests
- [ ] Implémenter `arbitrer` dans `code/arbiter.py`
- [ ] Réussir `test/test_arbiter.py`

## plan4.md
- [ ] Lire le contrat de `reconnaitre`, `thumb_detector` et les tests de gestes
- [ ] Implémenter `reconnaitre` dans `code/gesture_commands.py`
- [ ] Réussir `test/test_gesture_commands.py`

## Régression du lot
- [ ] `python -m pytest test/test_arbiter.py test/test_gesture_commands.py -q` sans échec
