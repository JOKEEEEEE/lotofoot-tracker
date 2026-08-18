# lotofoot-tracker

Historique des grilles Loto Foot (Winamax), pour un usage personnel : constituer
une base de résultats et de rapports en vue d'un futur calcul Elo et d'une étude
du biais du public sur le pari mutuel.

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
python verifier_base.py
```

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

### Mesurer plutôt que d'estimer

Les durées ci-dessous sont des ordres de grandeur, pas des promesses. Vingt
grilles suffisent à connaître le vrai rythme d'une machine et d'une connexion :

```bash
time python scrape_grille.py --from-id 3669 --to-id 3650 --pause 1 2
```

Divise le temps total par 20, multiplie par ce qui reste. C'est plus fiable que
n'importe quel tableau.

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
