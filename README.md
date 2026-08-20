# lotofoot-tracker

Historique des grilles Loto Foot (Winamax), pour un usage personnel : constituer
une base de résultats et de rapports en vue d'un futur calcul Elo et d'une étude
du biais du public sur le pari mutuel.

**Le cadrage du projet est dans [ROADMAP.md](ROADMAP.md)** : l'objectif, ce qui
est volontairement écarté, et les étapes dans l'ordre. À relire avant d'ouvrir
un nouveau chantier.

Rien n'est revendu. **En revanche, ce dépôt est public à ce jour**, et les JSON
de grilles y sont versionnés : ils sont donc lisibles, clonables et indexables
par tout le monde. Le passage en privé est prévu mais pas fait — tant qu'il ne
l'est pas, autant que ce soit écrit noir sur blanc plutôt que sous-entendu.

---

## État : validé sur trois grilles `grille7`, le 18 août 2026

Le diagnostic a tourné depuis une machine en France sur `grille7-4168`, et la
page a été rejouée hors ligne, élément par élément. Les trois sélecteurs
trouvent leurs éléments : 7 lignes de match, 14 noms d'équipes, 3 lignes de
rapport.

**Un bug bloquant est ressorti de cette confrontation.** Les sélecteurs
matchaient, et pourtant le scraper n'aurait produit aucun match : `inner_text()`
colle le nom de l'équipe au score, `Reims1N2Dunkerque3 - 3`, et le motif exigeait
une frontière de mot avant le chiffre — il n'y en a pas entre `e` et `3`. Sept
lignes, sept scores illisibles. Le garde-fou « AUCUN match extrait » aurait
arrêté le lot, donc l'échec était bruyant, mais il était total. C'est
exactement ce qu'une inspection à l'œil ne pouvait pas voir.

Corrigé de deux façons, qui ne meurent pas des mêmes causes : le score est
d'abord lu dans son élément dédié (`SEL_SCORE`), et à défaut dans le texte de la
ligne avec un motif qui tolère une lettre collée mais toujours pas un chiffre.

Les montants se recoupent, ce qui est le meilleur signe que les colonnes sont
lues dans le bon ordre : 7 × 946,13 € + 128 × 51,74 € = 13 245,63 €, contre
13 245,75 € affichés comme montant distribué — l'écart est de l'arrondi.

Le lot `--ids 4167,4166` a ensuite tourné pour de bon. Trois grilles, 21 matchs,
**zéro ligne écartée, zéro résultat incohérent avec son score, zéro nom d'équipe
vide.**

Et un contrôle qu'on n'avait pas prévu s'est mis à parler tout seul : sur les
trois grilles, la répartition entre les rangs tombe sur **50,0 % / 50,0 %** du
montant distribué.

| Grille | 7/7 | 6/7 | Distribué | Écart |
|---|---|---|---|---|
| 4166 | 4 × 660,75 € | 63 × 41,95 € | 5 286,00 € | 0,15 € |
| 4167 | 9 × 271,08 € | 114 × 21,40 € | 4 879,50 € | 0,18 € |
| 4168 | 7 × 946,13 € | 128 × 51,74 € | 13 245,75 € | 0,12 € |

C'est la règle du pari mutuel qui ressort des chiffres. Une lecture de colonnes
décalée ne produirait jamais trois fois cette symétrie : c'est la vérification
la plus solide dont on dispose, et elle ne coûte rien puisque les données la
portent en elles.

**Ce qui reste non vérifié :** la comparaison écran par écran d'une deuxième et
d'une troisième grille ; les types `grille9` et `grille12`, jamais ouverts ; une
grille annulée, dont aucune page n'a encore été vue — la détection cherche
« annul » dans tout le texte, ce qu'un bouton « Annuler » suffirait à déclencher,
alors le contexte est désormais enregistré dans le JSON pour qu'un faux positif
se voie.

## Pourquoi la validation n'a pas pu se faire d'ici

Trois voies essayées depuis l'environnement distant le 18 août 2026, trois
échecs :

| Voie | Résultat |
|---|---|
| `curl` simple | **403** CloudFront |
| `curl` avec en-têtes de navigateur complets | **403** CloudFront |
| Chromium headless, locale fr-FR, fuseau Europe/Paris | **ERR_CONNECTION_RESET** |

L'IP de sortie était à Columbus, Ohio (centre de données). Le blocage tombe à la
périphérie CloudFront, avant d'atteindre le serveur : c'est un filtrage
géographique d'opérateur agréé ANJ, pas une protection anti-robot qu'un en-tête
contournerait.

## Conséquence : ce projet tourne en local, pas dans GitHub Actions

C'est la différence structurelle avec `factxi-sportlab`, où toute la collecte
passe par des workflows. **Les runners GitHub sont eux aussi des IP de centre de
données américaines** et se feront bloquer exactement pareil. Il n'y aura donc
pas de collecte automatisée côté serveur : le scraper se lance depuis une
machine en France, et seuls les JSON produits sont poussés ici.

## Marche à suivre, dans cet ordre

```bash
pip install -r requirements.txt
playwright install chromium

python scrape_grille.py --diagnostic 4168
```

Le mode diagnostic imprime un rapport : pour chaque sélecteur, combien
d'éléments il trouve et ce qu'ils contiennent. Il sauve aussi le HTML brut et
une capture dans `diagnostic/`.

1. **Si les trois sélecteurs trouvent des éléments** et que l'extrait imprimé
   ressemble à ce que la page affiche, passer à l'étape suivante.
2. **Si l'un est à zéro, ne rien deviner.** Envoyer le fichier
   `diagnostic/*.html` — les sélecteurs se corrigent dessus, pas au jugé. Un
   scraper qui tourne et extrait n'importe quoi est pire qu'un scraper arrêté.
3. Tester sur deux ou trois grilles et **comparer le JSON à ce qu'affiche le
   site**, équipe par équipe et montant par montant.
4. Seulement ensuite, lancer un lot :

```bash
python scrape_grille.py --from-id 4150 --to-id 4168
```

## Ce que le scraper produit

Un fichier par grille, `data/grilles/{type}/{id}.json` :

```json
{
  "grille_id": 4168, "grille_type": "grille7",
  "statut": "terminee",
  "matches": [{"home": "...", "away": "...", "score_home": 2,
               "score_away": 1, "resultat": "1"},
              {"home": "...", "away": "...", "score_home": null,
               "score_away": null, "resultat": "annule",
               "tous_gagnants": true}],
  "rapports": [{"rang": "7/7", "nombre_gagnants": 3, "montant": 12345.6}],
  "montant_distribue": 45678.9
}
```

**Un match annulé n'est pas une grille annulée, ni une ligne illisible.** La
grille 4170 en contient un : Celta Vigo – Osasuna, dont la cellule de score
affiche « Annulé » — forfait ou report, l'issue est donnée gagnante pour tout le
monde. Le DOM le confirme deux fois : sur une ligne normale un seul des trois
boutons 1/N/2 porte la classe des issues gagnantes, sur celle-là les trois la
portent.

Ce cas a fait tomber deux versions successives. La première jetait la grille
entière : le mot « annulé » était cherché dans toute la page avant même qu'on
ait regardé les matchs, et six scores lisibles partaient sous une étiquette
fausse. La seconde, plus discrète, rangeait la ligne parmi les `lignes_ignorees`
faute de score — on y perdait les deux équipes, et surtout on confondait « pas
de score parce que tout le monde a gagné » avec « pas de score parce qu'on n'a
pas su lire ». La première est une donnée, la seconde un aveu d'échec ; une base
ne peut pas les ranger au même endroit.

Le match annulé est donc un match à part entière, avec ses deux équipes,
`resultat: "annule"`, `tous_gagnants: true` et **aucun score inventé**. Ni 0-0,
ni un 1/N/2 arbitraire : lui attribuer une issue fausserait un futur calcul Elo
comme une étude de biais.

**Une cellule de score vide, ou portant une icône « i », vaut aussi
annulation.** Relevé sur les grilles 1152, 1749, 1751 et 3580, vérifié sur le
site : ces grilles se règlent normalement, avec des rangs sur 7 matchs — ces
lignes ont donc bien compté, comme des matchs annulés.

Mais la conclusion ne se prend qu'**après avoir lu toute la grille, et à
condition qu'au moins un vrai score y figure**. Sans ce témoin, on ne tranche
pas. Deux raisons, et la seconde est la plus sérieuse : la grille 1848 n'a
aucune cellule de score dans son DOM — Winamax n'a pas conservé les scores de
cette journée de Ligue des champions dont un match fut interrompu — et la règle
seule en aurait fait sept matchs annulés « gagnants pour tous », soit sept
résultats inventés. Le même piège se refermerait si la classe de la cellule
changeait au prochain redéploiement : toutes les grilles deviendraient annulées,
silencieusement. Une panne doit rester bruyante.

Le champ `annulation_deduite_de` conserve ce qui a mené à la conclusion —
`"Annulé"` écrit noir sur blanc n'a pas la même force qu'une cellule vide, et le
jour où une cellule vide voudra dire autre chose, elles se retrouvent toutes
d'une recherche.

Quand le mot « annulé » apparaît dans la page **sans qu'aucun match ne
l'explique** — un bouton de bannière, ou une vraie annulation mal lue — le
contexte part dans `mention_annulation`. Une mention expliquée n'y est pas
notée : elle noierait le seul cas qui mérite un coup d'œil.

**Une grille n'est terminée que si la page le dit.** La grille 3836 affiche un
match sans résultat, un autre annulé, aucune mention « Terminée », et en bas
« Montant **garanti** » au lieu de « Montant distribué » — ce qu'affiche une
grille avant son règlement. Le mot « annulé » de l'autre ligne suffisait à
franchir le premier filtre, et six matchs lisibles à conclure « terminée » : on
aurait enregistré une grille non réglée comme réglée, rapports vides, sans
qu'aucun contrôle puisse s'en apercevoir faute de montant à comparer. La
présence de matchs prouve l'existence de la grille, pas son règlement.

`statut` vaut `terminee` ou `annulee`. **Une grille annulée est enregistrée**,
avec ses listes vides : Winamax annule une liste quand trop de matchs sont
donnés gagnants par forfait ou report, et confondre une annulation avec un trou
fausserait plus tard toute étude de biais. Une annulation est une information.

Une ligne dont le score est introuvable ou ambigu n'est pas devinée : elle part
dans `lignes_ignorees`, avec son texte brut, à l'intérieur du JSON de la grille.
La taire donnerait un fichier d'apparence complète auquel il manque un match.

## Trois défauts corrigés par rapport au script de départ

**Les montants revenaient à `null` en silence.** `_parse_montant` ne retirait
que deux des cinq espaces qui circulent dans les pages françaises : mesuré,
`1<U+00A0>234,56 €` — l'espace insécable la plus courante — renvoyait `None`. Et
`1.234,56 €`, où le point sépare les milliers, aussi. Le séparateur décimal se
décide maintenant d'après le dernier symbole rencontré. Neuf formats testés,
neuf corrects.

**Le plafond de 20 buts ne vaut que pour le texte libre.** Il distingue un score
d'un créneau horaire là où les deux se côtoient. Dans la cellule dédiée, qui ne
contient que le score, il n'y a rien à distinguer — et l'appliquer y perdait des
données : grille 3740, « Western Bulldogs 29 - 52 Hawthorn Hawks », du football
australien sur une grille Winamax, écarté comme implausible.

**Le score pouvait être lu sur le mauvais nombre.** Le motif d'origine
`(\d+)-(\d+)` prenait le premier couple venu dans la ligne, sans distinguer un
score d'un créneau horaire ou d'une date. Le motif est borné à deux chiffres et
à 20 buts, et **refuse de trancher quand plusieurs candidats coexistent** — la
ligne remonte alors comme ambiguë plutôt que de produire un JSON plausible et
faux.

**« Terminée » était cherché à la casse et à l'accent près.** Une variante
d'écriture sur le site aurait fait passer toutes les grilles pour non terminées,
et le lot serait ressorti vide sans qu'on comprenne pourquoi. La comparaison se
fait désormais sans accents ni casse.

Trois points mineurs au passage : `inner_text()` remplace `text_content()`, qui
colle les textes de deux balises voisines et cassait la recherche de « Montant
distribué » ; `--diagnostic 0` tombait dans la branche d'erreur parce que zéro
est faux en booléen ; un intervalle inversé produisait un lot vide en silence.

## Collecter tout l'historique

### D'abord sonder, avant d'engager une nuit entière

**Rien ne dit que les archives descendent jusqu'à l'identifiant 1.** Dix
requêtes, une minute, et on connaît la borne au lieu de la supposer :

```bash
python scrape_grille.py --ids 4000,3500,3000,2500,2000,1500,1000,500,100,1
```

Chaque identifiant introuvable est annoncé. Là où ça s'arrête de répondre, on
tient le plancher réel — et peut-être dix heures de requêtes évitées.

### Puis descendre, par lots

```bash
python scrape_grille.py --from-id 4170 --to-id 1 --lot 50 --pause-lot 120 300
```

Le sens décroissant n'est pas cosmétique : les grilles récentes sont celles qui
comptent le plus, et si le lot s'interrompt on s'est arrêté du bon côté.

| Réglage | Défaut | Ce qu'il fait |
|---|---|---|
| `--pause MIN MAX` | 3 6 | attente entre deux grilles, tirée au hasard |
| `--lot N` | 0 | pause longue toutes les N grilles |
| `--pause-lot MIN MAX` | 90 240 | durée de cette pause longue |
| `--arret-erreurs N` | 5 | arrêt après N erreurs d'affilée |
| `--arret-absences N` | 40 | arrêt après N grilles introuvables d'affilée |
| `--arret-identiques N` | 3 | arrêt après N grilles d'affilée aux matchs identiques |
| `--renouveler N` | 500 | rouvrir le navigateur toutes les N pages (0 = jamais) |
| `--refaire` | — | redemander aussi ce qui est déjà en base |

### La reprise est gratuite, donc il n'y a rien à noter

**Une grille déjà en base n'est jamais redemandée** — aucune requête, aucune
attente. Relancer exactement la même commande après une coupure reprend là où
ça s'était arrêté, sans qu'on ait à retenir quoi que ce soit. C'est aussi ce qui
rend un `Ctrl+C` sans conséquence.

Et quand un arrêt se déclenche, la commande de reprise est imprimée, prête à
coller.

### Deux arrêts, pour deux dangers différents

**Cinq erreurs d'affilée arrêtent tout.** Sans ça, un site qui coupe à la
centième grille laisserait les quatre mille suivantes défiler en pure perte, et
le bilan final ne dirait qu'un grand nombre.

**Quarante absences d'affilée arrêtent aussi.** Descendre jusqu'au début des
archives finit par ne plus rien trouver — mais un blocage qui renvoie une page
vide ressemble *exactement* à une fin d'archive. Les deux se traitent donc
pareil : arrêt, et vérification humaine dans un navigateur. Continuer
reviendrait à choisir la plus optimiste des deux lectures.

Les compteurs se remettent à zéro dès qu'une grille passe : ce sont des séries
consécutives, pas des totaux.

**Trois grilles identiques d'affilée arrêtent aussi.** C'est le seul échec qui
ne ressemble pas à un échec : si le site se met à servir la même page quel que
soit l'identifiant — repli après un excès de requêtes, redirection — il n'y a ni
erreur ni absence, juste des fichiers qui s'écrivent. Au matin, des milliers de
copies du même match. Deux grilles différentes ne partagent pas sept matchs
*et* sept scores : trois répétitions suffisent à conclure.

### Après chaque nuit, auditer

```bash
python verifier_base.py --rapport
```

L'écran donne la forme du problème, le fichier permet de le traiter. Sur quatre
mille grilles, un terminal tronqué à quarante lignes ne sert à rien — le rapport
complet part dans `diagnostic/audit.txt` (dossier déjà ignoré par git), sans
troncature, avec la liste intégrale des trous.

Il finit par **les commandes de reprise, prêtes à coller** : les identifiants à
recollecter, groupés par motif. Un audit qui liste des problèmes sans dire par
quelle commande les reprendre laisse le travail à moitié fait, et recopier des
identifiants à la main est exactement le genre de tâche où l'on en oublie un.

À trois grilles on relit les fichiers à l'œil ; à cinq cents, non — et c'est
précisément là qu'une erreur d'extraction devient invisible, parce qu'elle ne se
signale pas, elle se fond. Le script repose sur toute la base les questions
qu'on posait à la main sur les premières grilles : résultat cohérent avec le
score, aucun score inventé sur un match annulé, somme des rapports retombant sur
le montant distribué, deux grilles ne partageant pas leurs matchs. Il compte
aussi les identifiants absents et les lignes que le scraper n'a pas su lire.

**L'écart toléré sur les rapports croît avec le nombre de gagnants**, parce que
l'arrondi se fait par gagnant et non sur le total. Winamax divise la part d'un
rang par le nombre de gagnants puis arrondit au centime : chacun emporte jusqu'à
un demi-centime de trop ou de trop peu. Sur la grille 3833, la part exacte
valait 2,1730 € affichée 2,17 € — trois millièmes × 2 065 gagnants = 6,20 € sur
ce seul rang. Un seuil fixe se trompait donc exactement là où il ne faut pas :
sur les 507 premières grilles, un plafond à 2 € produisait **73 fausses alertes
et zéro vraie**.

Le rapport distingue aussi les **trous** — quelques identifiants manquants au
milieu d'une zone collectée, qui méritent un coup d'œil — des **plages jamais
demandées**. Les confondre donnait « 3 663 absents », un chiffre qui noyait les
trois seuls qui comptaient.

Il ne va sur aucun réseau et ne modifie rien. Il **ne dit pas** si les données
correspondent au site : une base peut être parfaitement cohérente et fausse si
le scraper a lu la mauvaise colonne partout. Seule une comparaison à l'écran
répond à ça, sur un échantillon.

### Où passe le temps

Le premier lot — 500 identifiants, aucune erreur — a montré que l'essentiel du
temps ne partait pas dans les pauses mais dans le chargement des pages. Or on ne
lit que du texte : images, polices et vidéos sont téléchargées pour rien.

Elles ne le sont plus. `--tout-charger` rétablit l'ancien comportement si jamais
ça posait problème. Le gain va dans les deux sens, ce qui est assez rare pour
être noté : **moins de requêtes pour Winamax, moins d'attente pour nous.** Et
`goto` ne patiente plus jusqu'au dernier traceur : c'est la présence des lignes
de match qui décide que la page est prête, pas un critère de navigateur.

Les feuilles de style, elles, restent chargées. `inner_text()` ne rend que ce qui
est visible ; sans CSS, des éléments masqués referaient surface et le texte lu ne
serait plus celui de la page. Quelques dixièmes de seconde ne valent pas ce
risque.

### Une page lente n'est pas une page absente

Les deux se ressemblent **exactement** : aucune ligne n'apparaît et le site
affiche « Chargement en cours » indéfiniment. Rien ne les distingue sur un seul
essai.

Le scraper recharge donc une fois avant de conclure. Ce n'est pas de la
prudence gratuite : sur un lot de 3 669 identifiants, 140 grilles avaient été
déclarées introuvables ; redemandées telles quelles, **117 sont revenues**. Un
essai de plus valait 117 grilles.

### Le renouvellement du navigateur ne suit plus les lots

Il y était accroché — donc toutes les cent pages — et c'est lui qui avait causé
ces 140 pertes : elles se groupaient juste après chaque relance, 86 % d'entre
elles tombant au même endroit de chaque centaine. Un navigateur qui vient de
démarrer n'est pas prêt tout de suite, et les pages suivantes le payaient.

| Lot | Réglages | Grilles perdues |
|---|---|---|
| 4169→3670 | `--lot 50`, sans renouvellement | 3 sur 500 — 0,6 % |
| 3669→1 | `--lot 100`, renouvellement à chaque lot | 137 sur 3 669 — 3,7 % |

La précaution coûtait six fois plus cher que le risque qu'elle couvrait. Elle
reste utile sur la durée, mais `--renouveler` la règle séparément — toutes les
500 pages par défaut, `0` pour ne jamais relancer.

### Mesurer plutôt que d'estimer

Les durées ci-dessous sont des ordres de grandeur, pas des promesses. Vingt
grilles suffisent à connaître le vrai rythme d'une machine et d'une connexion :

```bash
time python scrape_grille.py --from-id 3669 --to-id 3650 --pause 1 2
```

Divise le temps total par 20, multiplie par ce qui reste. C'est plus fiable que
n'importe quel tableau.

Mesuré le 18 août 2026 sur un MacBook Air : **46 s pour 20 grilles**, soit 2,3 s
par grille dont 1,5 s de pause volontaire. Le chargement réel d'une page tient
donc en **0,8 s** une fois les images et les polices écartées — dix fois moins
que l'estimation faite avant de mesurer, qui figurait ici même.

### Trois rythmes, à toi de choisir

| | Pauses | ~3 660 grilles |
|---|---|---|
| Prudent | `--pause 3 6 --lot 50 --pause-lot 120 300` | une dizaine d'heures |
| Intermédiaire | `--pause 1 2 --lot 100 --pause-lot 60 120` | 4 à 5 h |
| Rapide | `--pause 0.5 1.5` | 2 à 3 h |

Le premier lot n'a produit **aucune erreur sur 500 requêtes** : rien n'indique
qu'on approche d'une limite. Ce n'est pas une garantie qu'il n'y en a pas, c'est
une absence de signal contraire — et les arrêts automatiques sont précisément là
pour le cas où elle se manifesterait. Une reprise ne coûte rien.

Le rythme est ton arbitrage, pas le mien. Ce qui est écrit ici est ce qu'on
sait : où passe le temps, ce qu'on a mesuré, et ce qu'on ignore.

### Ce que l'aléatoire ne fait pas

Les attentes tirées au hasard évitent la signature d'un métronome et étalent la
charge. **Elles ne dissimulent pas le volume.** Quatre mille pages depuis une
seule IP restent quatre mille pages, quel que soit l'espacement, et personne ne
devrait se convaincre du contraire en lisant ce README.

Ce qui protège réellement, c'est le reste : une seule requête à la fois, un
rythme lent, aucune authentification en jeu — ce sont des pages publiques, donc
il n'y a pas de compte à suspendre — et un arrêt propre au premier signe de
refus plutôt qu'un acharnement. Le risque résiduel est un blocage d'IP
temporaire, et il se constate au lieu de se subir.

## Ce qui est testé, et ce qui ne l'est pas

```bash
python test_parsing.py        # fonctions pures, aucune dépendance
python test_selecteurs.py     # sélecteurs rejoués sur une page figée
python test_lot.py            # reprise et arrêts d'un lot, sans réseau
python test_dates.py          # ancrage, chronologie, interpolation
python test_ws.py             # décodage des trames websocket
```

`test_selecteurs.py` rejoue le vrai `scrape_grille()` sur `fixture_grille.html`,
une reproduction de la structure du DOM aux données inventées — aucune donnée du
site n'est republiée ici. Il va jusqu'au JSON, et c'est ce qui compte : un test
qui se contente de compter les éléments trouvés aurait laissé passer le bug de
lecture du score, puisque les sélecteurs matchaient. Il demande Chromium, là où
`test_parsing.py` tourne sans rien.

Trente-huit cas sur les trois fonctions pures — les montants dans cinq
espaces et deux conventions décimales, la lecture du score, le pliage des
accents. Chacun a été vérifié contre le défaut d'origine qu'il couvre : en
remettant l'ancienne version de la fonction, le test correspondant casse. Un
test qui ne casse jamais ne teste rien.

**Cela ne dit rien du scraping.** Les sélecteurs CSS restent non validés, et
aucun test ne peut les couvrir sans accès au site. Le vert ici ne vaut que
pour l'analyse de texte.

## Collecter par le websocket, pas par le DOM

```bash
python collecter_ws.py --type grille7 --recentes 10      # chaque jour
python collecter_ws.py --from-id 4170 --to-id 1          # l'historique
```

Le scraper HTML lit ce qui est affiché. **Le websocket qui alimente la page
transporte bien davantage**, et c'est vérifié sur deux grilles distantes de
onze ans :

| Champ | Ce que c'est |
|---|---|
| `poolEnd`, `matchStart` | la date exacte, à la minute |
| `competitorId` | `sr:competitor:2817` — un identifiant **Sportradar** |
| `netStakes`, `guaranteedAmount` | les mises collectées, le montant garanti |
| `odds1/oddsX/odds2` | les cotes de Winamax |
| `repart` | la répartition des grilles jouées selon leur nombre de bons résultats |

`repart` est la donnée la plus précieuse : elle livre la performance
**complète** du public — combien de parieurs ont eu 0, 1, 2… 7 bons résultats
— là où le DOM ne donnait que le nombre de gagnants. Sur la grille 4168 :
`[285, 2530, 5619, 5513, 2799, 780, 128, 7]`, dont la somme, 17 661, tombe
exactement sur le nombre de mises déduit du prélèvement de 25 %. Deux chemins
indépendants, même chiffre.

### Ce qui s'efface avec le temps

**Les cotes et `repart` ne sont servies que sur les grilles récentes.** La
grille 4168 les a, la grille 100 — du 30 décembre 2015 — ne les a plus. Une
grille par jour bascule ainsi hors de portée, définitivement. C'est la seule
partie du projet qui court après le temps, d'où la collecte quotidienne.

Le reste — dates, identifiants, scores, rapports, mises — est servi quel que
soit l'âge de la grille. L'historique est donc entièrement re-collectable.

### Pourquoi pas un workflow GitHub

Winamax bloque les IP de centre de données, runners GitHub compris. La
collecte quotidienne passe donc par `launchd`, l'ordonnanceur de macOS :
`quotidien.sh` fait le travail, `fr.lotofoot.quotidien.plist` le déclenche à
9 h — après le règlement des grilles de la veille.

### Ce que la collecte complète a donné

| | |
|---|---|
| Grilles collectées | **4 175** (l'archive entière, plus les grilles ouvertes) |
| Datées à la minute | **4 174 sur 4 175** |
| Matchs | 29 218, **tous** avec leur identifiant Sportradar |
| Équipes distinctes | 1 956, identifiées par clé et non par nom |
| **Grilles avec les cotes** | **783**, jusqu'à la n°1751 du 24 septembre 2020 |
| **Grilles avec `repart`** | **2 155**, jusqu'à la n°1948 du 27 février 2021 |

Les deux dernières lignes sont bien meilleures que ce qu'on redoutait. En
comparant seulement les grilles 4168 et 100, on avait conclu que cotes et
répartition ne survivaient qu'aux grilles récentes. En réalité elles
remontent à **cinq ans** pour les cotes et à **plus de la moitié de
l'archive** pour la répartition : 2 155 grilles portent la performance
complète du public, ce qui suffit largement à l'étude de biais.

### Les deux sources se contrôlent l'une l'autre

Les fichiers partent dans `data/pools/`, **à côté** de `data/grilles/` et non à
sa place : les 4 152 grilles déjà collectées et auditées servent de témoin.
**Confronté sur les 4 152 grilles du témoin : zéro montant divergent, zéro
rapport divergent.** Quarante-deux scores diffèrent, et ils s'expliquent tous
— ce sont des matchs annulés, dont le DOM n'affichait que la mention tandis
que le websocket conserve le score réellement joué. Il en dit davantage, il ne
dit pas autre chose.

Le nouveau collecteur est donc validé à l'échelle, pas sur deux exemples.

## Dater les grilles

```bash
python dater_grilles.py --rapport      # --telecharger la première fois
```

**Aucune date n'existe sur les pages de Winamax** — vérifié sur trois grilles
d'époques différentes, ni dans le texte, ni dans un attribut, ni dans un bloc
JSON. Il faut donc les reconstruire, à partir de deux sources.

**Les affiches.** Les sept matchs d'une grille l'identifient dans une base de
rencontres datée — [football-data.co.uk](https://www.football-data.co.uk/data.php),
libre et gratuite. C'est ainsi que la grille 1848 s'est révélée être le
8 décembre 2020, sixième journée de Ligue des champions.

**L'ordre des numéros.** Les identifiants croissent avec le temps, donc une
grille prise entre deux grilles datées est encadrée.

Ce qu'on ne fait **pas** : déduire la date du seul numéro. Testé et réfuté —
2 322 numéros pour 2 078 jours entre deux ancrages, et une erreur de huit mois
sur la grille 1848.

### Un squelette sûr, puis des ancres d'appoint

Trois affiches concordantes sont fiables, deux ne le sont pas : mesuré sur les
4 030 grilles, le taux d'incohérence chronologique passe de 0,7 % à 4,8 %. Mais
exiger trois affiches fait tomber la datation à sept jours près de 86 % à 77 %.

D'où la construction en deux temps : le squelette est bâti à trois affiches, et
une ancre à deux n'est admise que si elle tombe **dans l'intervalle que le
squelette autorise déjà**. Résultat : 2 048 ancres — autant qu'en acceptant tout
— mais **une seule** incohérence résiduelle au lieu de 103.

Une ancre fausse ne se contente pas d'être fausse : elle contamine par
interpolation toutes ses voisines. D'où aussi le contrôle final, qui ne retient
que la plus longue sous-suite chronologiquement croissante plutôt que d'écarter
naïvement toute ancre en désaccord avec la précédente — ce qui supprimerait la
bonne une fois sur deux.

### Le dictionnaire des noms, validé par les dates

```bash
python apparier_equipes.py --rapport
```

**Winamax écrit en français, football-data en anglais.** « FC Barcelone » contre
`Barcelona`, « Manchester United » contre `Man United`, « Naples » contre
`Napoli`. Sur les quinze noms les plus fréquemment introuvables, **quinze**
étaient présents sous un autre libellé : ce qui ressemblait à un trou de
couverture de 68 % était un dictionnaire manquant.

Ce qui rend ce dictionnaire fiable n'est pas la ressemblance des chaînes — elle
ne fait que proposer des candidats — mais **la date**. Un alias n'est retenu que
si, une fois substitué, la rencontre tombe dans la fenêtre de la grille, et il
faut deux confirmations. « Milan » ressemble autant à « Milan AC » qu'à « Inter
Milan » ; seule la date tranche. **Aucun alias n'est écrit à la main.**

Les deux étapes se nourrissent l'une l'autre : les dates valident les noms, et
les noms ainsi validés produisent de nouvelles ancres qui resserrent les dates.
270 alias confirmés, 14 697 apparitions récupérées, convergence en une passe.

### Ce que ça donne

| | Sans dictionnaire | **Avec** |
|---|---|---|
| Ancres | 2 048 | **2 825** |
| Incohérences résiduelles | 1 | **0** |
| Incertitude médiane des interpolations | 5 jours | **4 jours** |
| Grilles datées à 7 jours près ou mieux | 86 % | **95 %** |
| **Matchs liables à une cote** | 29 % | **57 %** |

Grilles datées : **4 029 sur 4 030**. Période : **11 septembre 2015 → 17 août
2026**.

### Le plafond, et d'où il vient

Les 43 % de matchs non liés ne le sont pas par manque d'astuce mais par manque
de source : parmi eux, 21 % opposent **deux équipes pourtant connues** — Real
Madrid – Chelsea, Seattle Sounders – Paris SG — parce que football-data ne
publie que des championnats nationaux, jamais les coupes ni les compétitions
internationales. Les 49 % restants relèvent de championnats hors périmètre et
de sélections.

Aller au-delà demandera une autre source, pas un meilleur appariement.

Les dates vivent dans `data/dates_grilles.json`, **à côté** des grilles et non
dedans : un `--refaire` du scraper réécrit un fichier de grille en entier et
effacerait tout travail logé à l'intérieur.

Chaque entrée porte `date`, `date_min`, `date_max` et `source` — `affiches`,
`interpolation` ou `hors_ancrage`. Une estimation à dix-neuf jours près et une
date confirmée par six affiches ne doivent pas se ressembler dans le JSON.

## Attacher une cote à chaque match

`joindre_cotes.py` produit `data/cotes_matchs.json` : une cote 1/N/2 par match,
avec sa provenance. Trois sources, dans cet ordre.

| Source | Pourquoi elle vient d'abord | Matchs |
|---|---|---|
| **Winamax** | c'est la cote de l'opérateur lui-même, celle que le parieur voyait | 5 070 |
| **Pinnacle** (clôture) | la référence de la littérature sur les biais de marché | 15 304 |
| **Bet365** (clôture) | en repli, pour sa couverture plus large | 438 |

**20 812 matchs cotés sur 29 941**, soit 70 % — bien au-dessus des 57 % que la
seule datation laissait espérer, parce que Winamax sert encore ses propres
cotes sur certaines périodes.

Le dénominateur compte les matchs **distincts** : un même match peut figurer
dans une grille 7 et une grille 12 le même jour. Le compter deux fois
sous-estimait la couverture et doublait ses motifs de refus.

### Ce qui empêche un faux rapprochement

Les dates exactes venues du websocket permettent d'exiger beaucoup plus qu'un
nom d'équipe ressemblant :

1. **les deux noms correspondent exactement**, alias compris — aucune
   ressemblance approximative n'est acceptée ;
2. **le sens de l'affiche compte** : Lyon–Nantes n'est pas Nantes–Lyon, sans
   quoi la cote 1 désignerait l'équipe adverse ;
3. la rencontre tombe **à un jour près** du coup d'envoi ;
4. **un seul candidat** subsiste ; deux, et on renonce ;
5. **les scores concordent** — les deux sources connaissent le résultat, et
   deux matchs qui ne finissent pas pareil ne sont pas le même match.

Le cinquième contrôle ne coûte rien et a écarté **4 rapprochements** que les
quatre premiers laissaient passer. Ils se ressemblent tous : Winamax a laissé
**0-0** sur un match qui n'est pas allé au bout. Bastia–Lyon du 16 avril 2017,
abandonné après envahissement du terrain, est chez football-data à 0-3 sur
tapis vert. Attacher une cote à ces matchs, c'est attacher une cote à un
résultat qu'on ne sait pas lire.

Refus, par motif :

| | |
|---|---|
| affiche absente de football-data | 9 038 |
| rencontre trouvée mais sans cote | 88 |
| scores différents | 3 |

### Ce qui reste vraiment hors d'atteinte

« Il ne manque que les sélections et les coupes » était une hypothèse commode,
et elle était fausse. En la vérifiant, on a trouvé 1 133 matchs qui ne
manquaient que d'un alias — voir plus bas. Une fois ceux-là récupérés, il
reste 9 038 matchs, et **ceux-là sont bien ce qu'on croyait** :

| | | |
|---|---|---|
| 3 965 | 44 % | **aucune des deux équipes** n'est dans football-data — sélections nationales, championnats hors périmètre |
| 3 782 | 42 % | **les deux clubs y sont** mais pas cette rencontre — Ligue des champions, Europa League, coupes nationales |
| 1 291 | 14 % | **un seul des deux** — l'adversaire vient d'un championnat non couvert : Shakhtar Donetsk, Maccabi Tel-Aviv, Dinamo Zagreb |

Aucun appariement plus astucieux ne les rattrapera : football-data ne publie
que des championnats nationaux, et ces rencontres n'y sont pas. Il faut une
autre source.

### Winamax garde ses cotes par fenêtres, pas par ancienneté

On croyait les cotes de Winamax simplement périssables. Les identifiants disent
autre chose : elles sont présentes sur **deux plages continues** et absentes
partout ailleurs.

| Type | Plages où les cotes existent |
|---|---|
| grille 7 | 1751 → 2261, puis 3902 → 4175 |
| grille 12 | 183 → 228, puis 373 → 402 |
| grille 9 | 1 → 21 (toutes) |

Soit environ septembre 2020 – décembre 2021, puis novembre 2025 – aujourd'hui.
Entre les deux, rien : 0 % en 2022, 2023 et 2024, contre 75 % en 2021. Un
vieillissement produirait une décroissance, pas deux blocs.

Ce n'est pas un défaut de collecte — les deux blocs sont contigus dans le
**temps**, pas dans l'ordre où on les a visités. Reste à savoir si Winamax
range les cotes de la période intermédiaire sous une autre clé. Une capture
brute d'une grille de 2023 le dira ; elle ne peut se faire que depuis la
France.

### 1 133 matchs qui ne manquaient que d'un nom

`apparier_equipes.py` a désormais **deux passes**, et la seconde a trouvé
68 alias que la première ne pouvait pas voir.

La première propose des candidats par ressemblance de chaîne, puis les fait
valider par la fenêtre de dates de la grille. Ce filtre était nécessaire tant
que les dates étaient approximatives — mais il élimine les traductions avant
même de les soumettre au test : « Mayence »/« Mainz », « Majorque »/« Mallorca »,
« AS Rome »/« Roma » ne se ressemblent pas assez.

Les dates exactes du websocket permettent d'inverser le raisonnement. Quand la
grille dit que Schalke 04 reçoit « Mayence » le 13 septembre 2015, et que
football-data ne connaît **qu'une seule** rencontre à domicile de Schalke ce
jour-là, l'adversaire est nommé sans qu'aucune ressemblance n'intervienne. Une
équipe ne joue jamais deux fois le même jour : c'est ce qui rend l'inférence
sûre. Le score sert de contre-épreuve, et il faut deux confirmations, chacune
devançant sa concurrente d'un facteur trois.

| | Avant | **Après** |
|---|---|---|
| Alias | 270 | **338** |
| Matchs cotés | 19 679 (66 %) | **20 812 (70 %)** |

Les plus fréquents : AS Rome (221 matchs), Wolverhampton (161), Sporting
Portugal (138), Hellas Vérone (99), Majorque (83), Real Saragosse (81),
Mayence (64).

**Le script relisait sa propre sortie.** La seconde passe partait du
dictionnaire trouvé sur le disque ; les noms qu'il contenait n'étaient donc
plus proposés, et la réécriture les perdait. Deux exécutions de suite ne
donnaient pas le même fichier. Elle part maintenant de ce que la première
passe vient de construire, et le résultat ne dépend que des données.

### Une cote Pinnacle qu'on n'utilise pas

football-data signale ses cotes Pinnacle comme **peu fiables depuis juillet
2025**. On s'arrête donc au 30 juin 2025 et on retombe sur Bet365, plutôt que
de faire comme si l'avertissement n'existait pas — c'est ce qui explique
l'essentiel des 402 matchs cotés par Bet365.

### `strPoolResult` s'écrit à l'envers

Trois caractères par match — un par issue, `100` pour le 1, `010` pour le nul,
`001` pour le 2, `111` pour un match annulé qui paie tout le monde. Mais **le
premier triplet décrit le dernier match de la grille**.

Ce n'est pas une supposition : sur les 4 467 grilles réglées de la base,
**4 293 ne s'accordent avec les scores que dans le sens inversé**, 174 dans les
deux — ce sont les grilles palindromiques — et 4 dans aucun. Ces quatre-là
portent un triplet `000` ou un score aberrant ; `decoder_resultat()` y rend
`None` plutôt que d'inventer une issue.

Lu dans le sens de la lecture, le code attribue l'annulation au mauvais match
et un `1` à une rencontre qui n'a pas eu lieu. C'est le genre d'erreur qui ne
se voit jamais dans un total.

### Ce que `repart` est, et ce qu'il n'est pas

`repart` est l'**histogramme des bulletins par nombre de bons résultats** :
`repart[k]` compte les grilles jouées qui ont obtenu k bons pronostics, de 0
jusqu'au nombre de matchs. Pour la grille 7 n°1948 :

    [72, 711, 2669, 5279, 6330, 4261, 1320, 139]
      0    1     2     3     4     5     6    7  bons résultats

Les deux dernières valeurs sont les rangs qui paient — 139 gagnants à 7 bons,
1 320 à 6 — et le reste, 20 642 bulletins, n'a rien gagné.

Deux contrôles, sur les 2 354 grilles qui portent le champ :

| | |
|---|---|
| `repart[k]` = gagnants du rang « k bons » | **4 870 rangs vérifiés**, 54 écarts |
| somme de `repart` × 1 € × 75 % = mises nettes | **2 290 exactes**, 26 à moins de 1 %, 26 au-delà, 12 grilles à zéro |

Le second contrôle confirme d'un coup trois choses mesurées séparément : la
mise unitaire vaut 1 €, le prélèvement est de 25 %, et `repart` compte bien
des bulletins et non des euros.

**Ce n'est donc PAS la répartition des mises par issue.** On ne sait pas
combien de parieurs ont coché le 1 plutôt que le N sur tel match — Winamax ne
sert pas cette donnée. On sait seulement à quel point la foule a eu raison
dans l'ensemble, ce qui reste la moitié du sujet : la distribution observée se
compare à celle qu'on obtiendrait au hasard, ou en suivant les cotes.

### Deux fenêtres, et un trou de quatre ans

Les cotes de Winamax ne sont pas servies partout. Relevé le 20 août 2026, sur
les 4 175 grilles 7 :

| Période | Grilles | Cotes | Répartition |
|---|---|---|---|
| avant le 24 septembre 2020 | 1 → 1750 | non | non |
| **24 sept. 2020 → 3 nov. 2021** | 1751 → 2261 | **oui** | à partir de fév. 2021 |
| 3 nov. 2021 → 17 nov. 2025 | 2262 → 3901 | non | oui |
| **depuis le 17 novembre 2025** | 3902 → 4175 | **oui** | oui |

Ce n'est donc pas la grille entière qui vieillit : `repart` est servi sans
interruption depuis février 2021, pendant que les cotes du même enregistrement
sont vides. Les deux champs sont indépendants.

La fenêtre récente ressemble à une rétention glissante d'environ neuf mois —
raison de plus pour que la collecte quotidienne tourne. Le bloc de 2020-2021,
lui, ne s'explique pas par une rétention : c'est un vestige, probablement un
changement de stockage en novembre 2021.

`sonder_cotes.py` sert à vérifier que `odds1/oddsX/odds2` sont bien le seul
endroit où une cote pourrait se trouver. On ne lit que trois clés d'un objet
qui en porte peut-être trente ; tant qu'on n'a pas regardé les autres,
« Winamax ne sert plus les cotes » reste une hypothèse.

La sonde ne suppose rien du nom des champs : elle parcourt toute la trame et
signale **tout triplet de nombres dont les inverses somment entre 1,00 et
1,40** — la signature arithmétique d'un marché 1/N/2 avec sa marge. Un nom de
clé peut changer, pas cette somme.

    python sonder_cotes.py 4170     # témoin : une grille qui a ses cotes
    python sonder_cotes.py 3000     # le trou : une grille qui n'en a pas

Puis comparer les deux inventaires de clés. Trois issues possibles :

1. **la clé existe et vaut `null`** — Winamax a vidé le champ, il n'y a rien à
   aller chercher, et il faut une source tierce ;
2. **la clé a disparu** — le modèle a changé, les cotes sont peut-être ailleurs
   dans la trame, et la sonde le dira ;
3. **un triplet inattendu apparaît** — c'est la piste, et elle vaut le détour.

## Conditions d'utilisation

L'accès automatisé est probablement contraire aux CGU de Winamax. Le rythme est
volontairement lent — 3 à 6 secondes entre deux grilles, aléatoire — et l'usage
est personnel : ni revente, ni service construit dessus.

**Mais les données sont republiées de fait**, puisque le dépôt est public. C'est
la partie de l'arbitrage qui pèse le plus lourd, et elle disparaîtra au passage
en privé. Elle est notée ici parce qu'un arbitrage tacite n'en est pas un.

Aucune donnée personnelle n'est collectée : ces pages ne contiennent que des
résultats sportifs et des montants agrégés, rien qui se rapporte à un parieur.

## Points signalés, non tranchés

- **Fréquence de collecte** : rien n'est programmé. Une grille terminée ne
  change plus, donc un rattrapage ponctuel suffit — inutile de repasser sur ce
  qui est déjà en base.
- **Changement de format d'URL** : non géré. Si Winamax change ses adresses, le
  diagnostic le dira par un 404 ou une page vide, et `BASE_URL` se corrige en
  une ligne.
- **Plage d'identifiants** : inconnue. Le premier lot devra tâtonner autour d'un
  ID connu pour trouver les bornes.
