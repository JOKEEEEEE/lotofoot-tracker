# lotofoot-tracker

Historique des grilles Loto Foot (Winamax), pour un usage personnel : constituer
une base de résultats et de rapports en vue d'un futur calcul Elo et d'une étude
du biais du public sur le pari mutuel.

Rien n'est publié. Rien n'est revendu.

---

## État : le scraper n'est pas validé

**Les sélecteurs n'ont jamais été confrontés au site réel.** Ils viennent d'une
inspection manuelle d'une seule grille (`grille7-4168`) et personne n'a encore
vérifié qu'ils matchent.

La validation n'a pas pu se faire depuis un environnement distant. Trois voies
essayées le 18 août 2026, trois échecs :

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
               "score_away": 1, "resultat": "1"}],
  "rapports": [{"rang": "7/7", "nombre_gagnants": 3, "montant": 12345.6}],
  "montant_distribue": 45678.9
}
```

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

## Ce qui est testé, et ce qui ne l'est pas

```bash
python test_parsing.py        # ou : pytest test_parsing.py
```

Trente-quatre cas sur les trois fonctions pures — les montants dans cinq
espaces et deux conventions décimales, la lecture du score, le pliage des
accents. Chacun a été vérifié contre le défaut d'origine qu'il couvre : en
remettant l'ancienne version de la fonction, le test correspondant casse. Un
test qui ne casse jamais ne teste rien.

**Cela ne dit rien du scraping.** Les sélecteurs CSS restent non validés, et
aucun test ne peut les couvrir sans accès au site. Le vert ici ne vaut que
pour l'analyse de texte.

## Conditions d'utilisation

L'accès automatisé est probablement contraire aux CGU de Winamax. L'usage ici
est strictement personnel, sans republication des données, et le rythme est
volontairement lent (3 à 6 secondes entre deux grilles, aléatoire). C'est un
arbitrage assumé, noté ici pour qu'il soit explicite.

## Points signalés, non tranchés

- **Fréquence de collecte** : rien n'est programmé. Une grille terminée ne
  change plus, donc un rattrapage ponctuel suffit — inutile de repasser sur ce
  qui est déjà en base.
- **Changement de format d'URL** : non géré. Si Winamax change ses adresses, le
  diagnostic le dira par un 404 ou une page vide, et `BASE_URL` se corrige en
  une ligne.
- **Plage d'identifiants** : inconnue. Le premier lot devra tâtonner autour d'un
  ID connu pour trouver les bornes.
