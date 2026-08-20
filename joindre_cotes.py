"""Attacher une cote 1/N/2 à chaque match, sans jamais rapprocher au doute.

TROIS SOURCES, DANS CET ORDRE.

    Winamax        la cote de l'opérateur lui-même, quand la grille est assez
                   récente pour qu'il la serve encore
    Pinnacle       la référence de la littérature sur les biais de marché,
                   réputée la plus proche des probabilités réelles
    Bet365         en repli, pour sa couverture plus large

CE QUI EMPÊCHE UN FAUX RAPPROCHEMENT. Les dates exactes venues du websocket
permettent d'exiger beaucoup plus qu'un nom d'équipe ressemblant :

    1. les deux noms doivent correspondre exactement, alias compris — aucune
       ressemblance approximative n'est acceptée ici
    2. la rencontre doit tomber à un jour près de l'heure de coup d'envoi
    3. UN SEUL candidat doit subsister ; deux, et on renonce
    4. LES SCORES DOIVENT CONCORDER — les deux sources connaissent le
       résultat, et deux matchs qui ne finissent pas pareil ne sont pas le
       même match

Ce quatrième contrôle est le plus utile : il ne coûte rien et il élimine les
homonymies qu'aucune règle sur les noms ne rattraperait.

    python joindre_cotes.py --rapport

Le résultat part dans data/cotes_matchs.json, avec la provenance de chaque
cote. Une cote d'opérateur mutuel et une cote de bookmaker ne se mélangent
pas en silence.
"""

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

import dater_grilles as dg

RACINE = Path(__file__).parent
DATA_POOLS = RACINE / "data" / "pools"
SORTIE = RACINE / "data" / "cotes_matchs.json"

# L'ordre de préférence des sources vit dans dater_grilles avec les colonnes :
# Pinnacle d'abord — la référence de la littérature — puis Bet365 en repli.
COLONNES = dg.COLONNES_COTES

# football-data signale que ses cotes Pinnacle ne sont plus fiables depuis
# juillet 2025. On ne les utilise donc pas au-delà, plutôt que de faire
# comme si l'avertissement n'existait pas.
PINNACLE_FIABLE_JUSQUA = date(2025, 6, 30)

# Tolérance sur l'heure de coup d'envoi. Un jour, pas cinq : la date vient du
# websocket, elle est exacte à la minute. La marge ne couvre que les fuseaux
# et les matchs de fin de soirée.
MARGE_JOURS = 1

charger_rencontres = dg.charger_rencontres


def choisir_cote(cotes: dict, jour: date):
    """La meilleure cote disponible, et d'où elle vient."""
    for nom, _ in COLONNES:
        if nom not in cotes:
            continue
        if nom.startswith("pinnacle") and jour > PINNACLE_FIABLE_JUSQUA:
            continue                       # avertissement de football-data
        return cotes[nom], nom
    return None, None


def rapprocher(match: dict, index: dict) -> tuple:
    """La rencontre correspondante, ou None avec le motif du refus."""
    if not match.get("debut"):
        return None, "match sans date"
    jour = date.fromisoformat(match["debut"][:10])
    cle = (dg._cle(match.get("home")), dg._cle(match.get("away")))
    candidates = [r for r in index.get(cle, ())
                  if abs((r["date"] - jour).days) <= MARGE_JOURS]
    if not candidates:
        return None, "affiche absente de football-data"
    if len(candidates) > 1:
        # Deux rencontres entre les mêmes équipes à un jour d'intervalle :
        # invraisemblable, donc c'est l'index qui est ambigu. On renonce.
        return None, "plusieurs candidates"

    trouvee = candidates[0]
    notre_score = (match.get("score_home"), match.get("score_away"))
    if None not in notre_score and trouvee["score"] is not None:
        if tuple(notre_score) != trouvee["score"]:
            # Le contrôle qui vaut tous les autres : deux matchs qui ne
            # finissent pas pareil ne sont pas le même match.
            return None, "scores différents"
    elif (trouvee["date"] - jour).days != 0:
        # Sans score à comparer, on exige la date au jour exact.
        return None, "sans score, et date décalée"
    return trouvee, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Attacher les cotes aux matchs")
    ap.add_argument("--type", default="grille7", choices=["grille7", "grille9",
                                                          "grille12", "tous"])
    ap.add_argument("--rapport", nargs="?", const="diagnostic/cotes.txt",
                    default=None, metavar="FICHIER")
    args = ap.parse_args()

    index = charger_rencontres()
    print(f"football-data : {len(index)} affiches, "
          f"{sum(len(v) for v in index.values())} rencontres")

    types = ["grille7", "grille9", "grille12"] if args.type == "tous" else [args.type]
    resultat, motifs, sources = {}, Counter(), Counter()
    # Un match peut figurer dans deux grilles le même jour — une grille 7 et
    # une grille 12. Sans ce jeu, un match non rapproché serait compté deux
    # fois au dénominateur et son motif de refus autant : le taux de
    # couverture s'en trouvait sous-estimé.
    vus = set()
    for t in types:
        for f in sorted((DATA_POOLS / t).glob("*.json"), key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            for m in d.get("matches", []):
                mid = m.get("match_id")
                if mid is None or mid in vus:
                    continue
                vus.add(mid)
                if m.get("cote_1") and m.get("cote_N") and m.get("cote_2"):
                    resultat[mid] = {"cote_1": m["cote_1"], "cote_N": m["cote_N"],
                                     "cote_2": m["cote_2"], "source": "winamax",
                                     "grille_type": t, "grille_id": d["grille_id"]}
                    sources["winamax"] += 1
                    continue
                trouvee, motif = rapprocher(m, index)
                if trouvee is None:
                    motifs[motif] += 1
                    continue
                jour = date.fromisoformat(m["debut"][:10])
                trio, nom = choisir_cote(trouvee["cotes"], jour)
                if trio is None:
                    motifs["rencontre trouvée mais sans cote"] += 1
                    continue
                resultat[mid] = {"cote_1": trio[0], "cote_N": trio[1],
                                 "cote_2": trio[2], "source": nom,
                                 "division": trouvee["division"],
                                 "grille_type": t, "grille_id": d["grille_id"]}
                sources[nom] += 1

    total = len(vus)
    print(f"\nmatchs distincts : {total}")
    print(f"matchs cotés     : {len(resultat)}  ({100 * len(resultat) / total:.0f} %)")
    for nom, n in sources.most_common():
        print(f"    {nom:<20} {n:>6}")
    print("\nnon rapprochés :")
    for motif, n in motifs.most_common():
        print(f"    {motif:<38} {n:>6}")

    SORTIE.write_text(json.dumps({str(k): v for k, v in sorted(resultat.items())},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {SORTIE}")

    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        lignes = [f"{len(resultat)}/{total} matchs cotés", ""]
        lignes += [f"  {n:>6}  {nom}" for nom, n in sources.most_common()]
        lignes += ["", "Refus :"]
        lignes += [f"  {n:>6}  {motif}" for motif, n in motifs.most_common()]
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"Rapport : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
