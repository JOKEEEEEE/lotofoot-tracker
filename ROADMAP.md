# Cadrage

**Objectif : apprendre.** La donnée Loto Foot est le terrain, pas la finalité.
Environ dix heures par semaine.

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

## Ce qui est écarté, et pourquoi

**Le gain financier.** Non par principe, mais par arithmétique : le prélèvement
de 25 % impose de battre la foule de plus de vingt-cinq points, et surtout,
miser sur une faille la referme — sur la grille 4168, sept gagnants se
partageaient 946 € chacun ; jouer sept combinaisons identiques aurait ramené
chacun à environ 473 €. L'avantage est plafonné par sa propre exploitation.

C'est noté ici pour ne pas y revenir tous les deux mois.

**Un service pour d'autres.** Le scraper ne tourne que depuis une machine en
France, republier les données contredirait les CGU de Winamax, et diffuser des
conseils de pari relève du cadre ANJ. Trois obstacles, aucun technique.

## Étape 1 — Dater les grilles

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

**Critère de fin :** une date pour au moins 70 % des grilles, chacune validée
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

## Étape 3 — L'étude du biais

**Livrable :** la réponse à la question du README initial — le public se
trompe-t-il, et où ?

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

Rien pour l'instant. Ce fichier est fait pour se remplir.
