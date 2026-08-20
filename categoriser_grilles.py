"""Nommer la compétition de chaque match, puis le genre de chaque grille.

CE QU'ON CHERCHE. « Grille Ligue 1 » quand les sept matchs en relèvent,
« grille coupe d'Europe », « grille multi-compétition » sinon. C'est ce qui
permettra de comparer ce qui est comparable : le public ne se trompe
probablement pas de la même façon sur une journée de Ligue 1 et sur un
mercredi de Ligue des champions.

D'OÙ VIENT LA COMPÉTITION. De nulle part, chez Winamax : vérifié le 20 août
2026, les matchs d'une grille ne portent AUCUN champ de compétition dans le
websocket — ni `tournamentId`, ni `categoryId`. Elle se déduit donc des deux
sources de cotes, qui la publient toutes les deux :

    football-data   la colonne `Div` — F1, E0, SP1 — pour les championnats
    Footiqo         le nom de la ligue pour les coupes

Le rapprochement est celui de `joindre_cotes`, aux mêmes conditions : noms
exacts, sens de l'affiche, un jour de marge, un seul candidat, scores
concordants. Un match qu'on ne sait pas nommer reste sans compétition plutôt
que d'en recevoir une plausible.

CE QU'ON NE SAURA PAS. Quelle coupe nationale : Coupe de France, Copa del Rey
et DFB-Pokal se ressemblent, et aucune des deux sources ne les publie. Elles
tombent donc dans « compétition inconnue », avec les sélections nationales.

    python categoriser_grilles.py --rapport
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import collecter_footiqo as fq
import dater_grilles as dg
import joindre_cotes as jc

RACINE = Path(__file__).parent
SORTIE = RACINE / "data" / "competitions_grilles.json"

# Les codes de football-data, regroupés par famille. Le regroupement est le
# but même de l'exercice : « E0 » et « SP1 » ne veulent rien dire pour un
# lecteur, « top 5 » si.
TOP5 = {"E0": "Premier League", "SP1": "LaLiga", "D1": "Bundesliga",
        "I1": "Serie A", "F1": "Ligue 1"}
DEUXIEMES = {"E1": "Championship", "SP2": "LaLiga 2", "D2": "Bundesliga 2",
             "I2": "Serie B", "F2": "Ligue 2", "E2": "League One",
             "E3": "League Two", "EC": "National League",
             "SC1": "Scottish Championship", "SC2": "Scottish League One",
             "SC3": "Scottish League Two"}
AUTRES_EUROPE = {"N1": "Eredivisie", "B1": "Jupiler Pro League",
                 "P1": "Liga Portugal", "T1": "Süper Lig", "G1": "Super League Grèce",
                 "SC0": "Scottish Premiership"}
COUPES_EUROPE = {"Champions League", "Europa League", "Conference League"}

# Les codes lisibles, pour l'affichage et pour le fichier de sortie. « F1 »
# ne dit rien à personne, « Ligue 1 » si.
NOMS = {**TOP5, **DEUXIEMES, **AUTRES_EUROPE}


def lisible(competition):
    return NOMS.get(competition, competition)


FAMILLES = [
    ("top 5", lambda c: c in TOP5),
    ("coupe d'Europe", lambda c: c in COUPES_EUROPE),
    ("deuxième division", lambda c: c in DEUXIEMES),
    ("autre championnat européen", lambda c: c in AUTRES_EUROPE),
    ("Copa Libertadores", lambda c: c == "Copa Libertadores"),
    ("Coupe du monde", lambda c: c and c.startswith("World Cup")),
]

# En dessous de cette proportion de matchs nommés, on ne qualifie pas la
# grille : deux matchs sur sept ne disent pas de quoi la grille est faite.
COUVERTURE_MINI = 0.6


def famille(competition):
    if not competition:
        return None
    for nom, teste in FAMILLES:
        if teste(competition):
            return nom
    return "autre championnat"


def competition_du_match(m: dict, index: dict, index_fq: dict, table_fq: dict):
    """La compétition d'un match, ou None si aucune source ne la connaît."""
    trouvee, _ = jc.rapprocher(m, index)
    if trouvee is None:
        trouvee, _ = jc.rapprocher(m, index_fq, table_fq)
    return trouvee["division"] if trouvee else None


def categoriser(compte: Counter, nb_matchs: int) -> str:
    """Le genre d'une grille, à partir des familles de ses matchs.

    Une grille est dite d'une compétition quand TOUS ses matchs nommés en
    relèvent — pas la majorité. Six matchs de Ligue 1 et un de Bundesliga
    font une grille multi-compétition : c'est le mélange qui la caractérise,
    et le noyer dans une majorité ferait disparaître ce qu'on veut mesurer.
    """
    nommes = sum(compte.values())
    if not nommes or nommes < COUVERTURE_MINI * nb_matchs:
        return "indéterminée"
    if len(compte) == 1:
        return next(iter(compte))
    return "multi-compétition"


def main() -> int:
    ap = argparse.ArgumentParser(description="Catégoriser les grilles")
    ap.add_argument("--rapport", nargs="?", const="diagnostic/competitions.txt",
                    default=None, metavar="FICHIER")
    args = ap.parse_args()

    index = dg.charger_rencontres()
    index_fq = fq.charger()
    chemin_alias = RACINE / "data" / "alias_footiqo.json"
    table_fq = {k: v["vers"] for k, v in
                json.loads(chemin_alias.read_text(encoding="utf-8")).items()} \
        if chemin_alias.exists() else {}
    print(f"football-data : {len(index)} affiches   "
          f"footiqo : {len(index_fq)} affiches, {len(table_fq)} alias")

    resultat, genres, detail, exactes = {}, Counter(), Counter(), Counter()
    nommes = manques = 0
    for t in ("grille7", "grille9", "grille12"):
        dossier = jc.DATA_POOLS / t
        for f in sorted(dossier.glob("*.json"), key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            matchs = d.get("matches", [])
            compte, precis = Counter(), Counter()
            for m in matchs:
                comp = competition_du_match(m, index, index_fq, table_fq)
                fam = famille(comp)
                if fam:
                    compte[fam] += 1
                    precis[comp] += 1
                    nommes += 1
                else:
                    manques += 1
            genre = categoriser(compte, len(matchs))
            # Quand une grille tient dans une seule compétition, on la nomme
            # par cette compétition plutôt que par sa famille : « Ligue 1 »
            # dit ce que « top 5 » cache.
            precision = lisible(next(iter(precis))) if len(precis) == 1 else None
            genres[genre] += 1
            exactes[precision or genre] += 1
            for c in precis:
                detail[c] += precis[c]
            resultat.setdefault(t, {})[str(d["grille_id"])] = {
                "categorie": precision if precision and genre != "indéterminée"
                             else genre,
                "famille": genre,
                "familles": dict(compte),
                "competitions": {lisible(k): v for k, v in precis.items()},
                "matchs": len(matchs),
                "nommes": sum(compte.values()),
            }

    total = nommes + manques
    print(f"\nmatchs nommés : {nommes}/{total}  ({100 * nommes / total:.0f} %)")
    print("\nGENRES DE GRILLE")
    for genre, n in genres.most_common():
        print(f"  {n:>5}  ({100 * n / sum(genres.values()):>2.0f} %)  {genre}")
    print("\nGRILLES D'UNE SEULE COMPÉTITION")
    for comp, n in exactes.most_common(18):
        if comp in genres:
            continue                        # déjà listé au-dessus
        print(f"  {n:>5}  {comp}")
    print("\nLES COMPÉTITIONS LES PLUS PRÉSENTES, EN MATCHS")
    for comp, n in detail.most_common(15):
        print(f"  {n:>6}  {lisible(comp)}")

    SORTIE.write_text(json.dumps(resultat, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"\n-> {SORTIE}")

    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        lignes = [f"{nommes}/{total} matchs nommés", ""]
        lignes += [f"  {n:>5}  {g}" for g, n in genres.most_common()]
        lignes += ["", "Grilles d'une seule compétition :"]
        lignes += [f"  {n:>5}  {c}" for c, n in exactes.most_common()
                   if c not in genres]
        lignes += ["", "Compétitions, en matchs :"]
        lignes += [f"  {n:>6}  {lisible(c)}" for c, n in detail.most_common()]
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"Rapport : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
