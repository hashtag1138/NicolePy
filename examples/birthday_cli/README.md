# birthday_cli

Ce vertical slice montre un flux Nicole executable de bout en bout via `NicoleApplication`:

- lecture d'un prenom et d'une date de naissance depuis des bindings host
- lecture d'une date courante controlee par les tests
- calcul Nicole de l'age courant, de l'age l'annee prochaine, et de la branche anniversaire
- emission du message final via sorties host elementaires

Source Nicole:

- `examples/birthday_cli/main.nic`

Host bindings utilises:

- `host.console.read` (lecture queue d'entree)
- `host.parse.int` (conversion texte vers `Int`, scope etroit)
- `host.now.year`
- `host.now.month`
- `host.now.day`
- `host.out.text`
- `host.out.int`

Comportement I/O controle:

- les tests simulent l'entree console avec une file deterministe
- les tests capturent la sortie dans une liste de segments
- aucune lecture stdin/stdout reelle
- aucune horloge systeme reelle

Scenarios testes:

1. anniversaire aujourd'hui
2. anniversaire pas aujourd'hui (message age annee prochaine)

Logique gardee en Nicole:

- determination anniversaire/pas anniversaire
- calcul de l'age courant
- calcul de l'age l'annee prochaine
- selection de la phrase finale

Limitation actuelle:

- absence de primitives de formatage/concat string dans le noyau: l'exemple emet la phrase en segments (`text`/`int`) via host.
