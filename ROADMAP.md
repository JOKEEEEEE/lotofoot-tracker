# Cadrage

**Destination : une brique Loto Foot dans le projet Fact XI**, qui s'élargit aux
cotes des paris sportifs.

Ce dépôt n'est donc pas un projet autonome : il produit et entretient un jeu de
données. Ce qu'on en fera — analyses de biais de marché, notes d'après-match,
études ponctuelles — vit ailleurs.

**Le sujet de fond reste le même** : les biais d'une foule qui parie —
favourite-longshot bias, sagesse des foules, efficience d'un marché. Le pari
mutuel en est un observatoire privilégié, parce qu'on y voit la répartition
brute de l'argent du public et non un prix déjà corrigé par un professionnel.

Environ dix heures par semaine.

## L'ordre décidé

1. **Tout l'historique Winamax d'abord** — grilles 7, 9 et 12. On ne construit
   rien tant que la matière n'est pas complète.
2. **Les dates ensuite.**
3. **Les cotes enfin.**

Cet ordre n'est pas négociable en cours de route : c'est le remède au défaut
identifié plus bas.

Ce cadrage a été écrit le 18 août 2026, après deux jours de collecte, parce que
le risque principal de ce projet n'est pas technique : c'est de partir dans
quatre directions à la fois. Il est ici pour être relu quand l'envie prendra.

## La règle

**Une étape à la fois, et on finit avant d'ouvrir la suivante.** Chaque étape
ci-dessous a un livrable et un critère de fin explicite. Tant que le critère
n'est pas atteint, la suivante n'existe pas.

Une idée qui surgit en cours de route ne se code pas : elle se note en bas de ce
fichier, dans « Envies en attente ». Elle sera toujours là dans trois semaines,
et elle aura peut-être perdu son urgence — c'est même le but.

## Ce qui est acquis

| | |
|---|---|
| Grilles collectées | 4 152, identifiants 1 à 4170 |
| Matchs | 28 205, dont 149 annulés |
| Anomalies détectées par l'audit | 0 |
| Validation externe | 43,8 % de victoires à domicile — la signature de l'avantage du terrain |
| Prélèvement du pari mutuel | **25 %** (distribué = 75 % des mises, mesuré sur 3 617 grilles) |
| Grilles à montant garanti | 413, soit une sur dix |

## Pourquoi ce jeu de données vaut mieux qu'il n'en a l'air

**Le pari mutuel est un meilleur laboratoire que la cote fixe.** Chez un
bookmaker on observe un prix, déjà corrigé par un professionnel qui connaît le
longshot bias et le facture. En pari mutuel on observe **la répartition brute de
l'argent du public**, sans intermédiaire : la matière première, pas le produit
transformé.

Deux mesures directes, à partir de ce qui est déjà collecté :

- **Sagesse des foules** — le nombre de gagnants à 7/7 comparé à celui
  qu'on attendrait si les mises suivaient les vraies probabilités. Coïncidence
  = foule bien calibrée.
- **Favourite-longshot bias** — les grilles gagnées par des combinaisons
  improbables comptent-elles proportionnellement moins de gagnants que la
  théorie ne le prévoit ? C'est la signature d'un public qui sur-parie
  l'improbable.

**Sortir du football se fait en gardant la question, pas en changeant de
données.** Le longshot bias a été documenté d'abord sur les courses hippiques,
en pari mutuel — le PMU en France. Même mécanique, données publiques,
littérature abondante pour confronter ses résultats. C'est l'extension
naturelle, bien avant les données joueurs.

## Ce qui est écarté, et pourquoi

**Le gain financier.** Non par principe, mais par arithmétique : le prélèvement
de 25 % impose de battre la foule de plus de vingt-cinq points, et surtout,
miser sur une faille la referme — sur la grille 4168, sept gagnants se
partageaient 946 € chacun ; jouer sept combinaisons identiques aurait ramené
chacun à environ 473 €. L'avantage est plafonné par sa propre exploitation.

C'est noté ici pour ne pas y revenir tous les deux mois.

**Publier — ce qui n'est PAS écarté, contrairement à une première version de ce
fichier.** La distinction n'est pas « produit ou pas », elle est « quoi
publier » :

| | |
|---|---|
| Ses propres analyses, graphiques, conclusions | rien ne s'y oppose |
| Les données brutes de Winamax | contraire à leurs CGU |
| Des pronostics ou conseils de mise | relève du cadre ANJ |

Le blocage géographique contraint la **collecte**, pas la publication : le
scraper tourne en France, le site peut vivre n'importe où. Un site d'analyses de
biais de marché est du contenu de recherche, pas un service de pronostics.

Rien n'oblige à publier, et ce n'est pas un objectif d'étape. Mais c'est
possible, et l'étape 3 en fournirait la matière.

## Étape 0 — Compléter l'historique

**Grilles 9 et 12.** Les compteurs sont séparés de celui des grilles 7 : relevé
le 18 août 2026 sur la barre latérale du site, la grille 9 en est à son numéro
21 et la grille 12 à son numéro 402. Une vingtaine de grilles d'un côté, quatre
cents de l'autre — une vingtaine de minutes de collecte, pas une nuit.

**Le code ne présuppose rien sur le nombre de matchs** : les rangs de rapports
sont lus tels quels sur la page, et rien n'est codé en dur. Mais la structure du
DOM n'a jamais été vue sur autre chose qu'une grille 7 — donc `--diagnostic`
avant tout lot, comme d'habitude. C'est cette discipline qui a évité d'enregistrer
4 000 grilles sans un seul score lisible.

**Critère de fin :** les trois types collectés, `verifier_base.py --rapport`
sans anomalie, et les trous expliqués.

## Étape 1 — Dater les grilles ✅ faite le 18 août 2026

**Pourquoi d'abord :** rien de chronologique n'est possible sans dates, et il
n'y en a aucune sur les pages de Winamax — ni visible, ni cachée. Vérifié.

**Comment :** par les équipes. Les sept matchs d'une grille identifient sa date
dans une base de rencontres datée. Fait à la main sur la grille 1848, qui s'est
révélée être le 8 décembre 2020 par ses seules affiches.

**Ce qu'on ne fait pas :** déduire la date du numéro de grille. Testé, réfuté :
2 322 numéros pour 2 078 jours entre deux points d'ancrage, et une erreur de
huit mois sur la grille 1848.

**Compétence travaillée :** rapprochement d'entités — normalisation, variantes,
mesure de couverture. C'est le cœur de tout projet de données, et le plus
sous-estimé. 2 053 noms d'équipes distincts attendent.

**Livrable :** `dater_grilles.py`, et un rapport de couverture honnête.

**Mesuré le 18 août 2026, avant d'écrire une ligne :** sur 11 saisons de
football-data (20 championnats), 27 % des affiches et 13 % des équipes se
retrouvent — la couverture est structurellement limitée parce que football-data
ne couvre que les championnats nationaux, ni coupes d'Europe ni sélections.
Seules 24 % des grilles sont datables directement.

**Mais l'ordre des numéros sauve la mise.** Les 965 grilles ancrées ainsi
s'ordonnent chronologiquement à 99,7 % — trouvées indépendamment, par des
affiches différentes, et pourtant cohérentes entre elles. L'écart médian entre
deux ancres est d'**une grille et d'un jour** : l'interpolation encadrera donc
la grande majorité des autres à quelques jours près. Période couverte par les
ancres : à partir du 11 septembre 2015.

**Résultat : 4 029 grilles datées sur 4 030**, dont 2 047 par les affiches et
1 982 par interpolation avec une incertitude médiane de 5 jours. 86 % de la base
est datée à 7 jours près ou mieux. Période couverte : 11 septembre 2015 au
17 août 2026. Voir le README pour la méthode en deux temps.

**Critère de fin (atteint) :** une date pour au moins 70 % des grilles, chacune validée
par la règle des trois jours — les sept matchs d'une grille doivent tenir dans
une fenêtre de trois jours — et par la croissance des dates avec les numéros.
Les 30 % restants sont listés, pas cachés.

## Étape 2 — Un classement Elo

**Livrable :** un Elo par équipe, calculé chronologiquement sur onze ans.

**Compétence travaillée :** modélisation, et surtout évaluation. Un modèle qui
ne se mesure pas ne vaut rien.

**Critère de fin :** le modèle bat une base de référence — prédire toujours la
victoire à domicile — sur une métrique choisie d'avance (log loss ou Brier), et
sur des données qu'il n'a pas vues. Aucune information postérieure au match ne
doit entrer dans son calcul ; c'est le piège classique, et il faut le vérifier
explicitement.

## Étape 3 — Les biais du public (le cœur du sujet)

C'est l'étape pour laquelle les deux précédentes existent. Les autres sont des
prérequis ; celle-ci est la raison d'être du projet.

**Livrable :** la réponse à la question du README initial — le public se
trompe-t-il, et où ? — traitée sous l'angle des deux biais documentés par la
littérature, de sorte que les résultats soient comparables à ce qui est publié
ailleurs.

**Comment :** comparer le nombre de gagnants observés à chaque rang avec celui
qu'on attendrait si les mises suivaient les probabilités du modèle. L'écart est
le biais.

**Critère de fin :** un texte qui tient en deux pages, avec ses chiffres et ses
réserves. Y compris la réserve principale : un biais mesuré n'est pas un biais
exploitable, à cause du prélèvement.

## Étape 4 — Explorer

C'est ici que le côté Football Manager devient légitime : une interface pour
naviguer dans onze ans de grilles, d'équipes et de classements. Données joueurs
si l'envie tient — Transfermarkt pour les valeurs et les blessures, Understat
pour les xG, StatsBomb Open Data pour l'événementiel.

Volontairement non cadrée. On la cadrera en y arrivant, avec ce qu'on aura
appris des trois premières.

## À faire tout de suite, hors étapes

**Collecter les mises des grilles en cours.** Le montant collecté s'affiche sur
une grille ouverte et disparaît à son règlement. Chaque jour sans le lire est
perdu définitivement — l'historique de 4 152 grilles ne l'aura jamais. C'est une
heure de travail et ça ne bloque rien.

## Envies en attente

**Catégoriser les grilles par compétition** — « grille Ligue 1 » quand les sept
matchs en relèvent, « multi-compétition » sinon.

Vérifié le 20 août 2026 : les matchs d'une grille ne portent **aucun champ de
compétition** dans le websocket. Ni `tournamentId`, ni `categoryId`, ni
`sportId` — seulement les équipes, la date, le score et les cotes. Les tables de
tournois sont pourtant dans la trame, mais rien n'y relie un match de grille.

La voie praticable passe donc par les dates exactes : la colonne `Div` de
football-data donne la compétition réelle d'une rencontre — `F1`, `E0`, `SP1` —
dès lors qu'on la rapproche par équipes et date. Sept `F1` font une grille
Ligue 1 ; des `Div` mêlés font une grille multi-compétition ; une affiche
introuvable alors que les deux équipes sont connues est un match de coupe, car
football-data ne publie jamais les coupes. On avait mesuré 2 205 affiches dans
ce cas.

Ce qu'on ne saura pas : **quelle** coupe. Ligue des champions, Europa League et
Coupe de France se ressembleront. Les nommer demande une source qui couvre les
coupes — la même conclusion qu'ailleurs, atteinte par un troisième chemin.

**Piste pour les grilles futures, à tester :** les matchs d'une grille encore
ouverte sont aussi proposés au pari classique, où l'état applicatif de la page
les accompagne d'un `tournamentId`. La collecte quotidienne pourrait donc
enregistrer la compétition tant que la grille est à venir. Même logique que
`repart` : ce qui est facile aujourd'hui devient impossible demain.
