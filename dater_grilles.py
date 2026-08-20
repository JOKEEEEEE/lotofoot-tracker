"""Dater les grilles par leurs affiches, puis par l'ordre des numéros.

AUCUNE DATE N'EXISTE SUR LES PAGES DE WINAMAX. Vérifié le 18 août 2026 sur
trois grilles d'époques différentes : ni dans le texte visible, ni dans un
attribut, ni dans un bloc JSON. Les seuls horodatages du HTML appartiennent
aux cotes de la barre latérale et datent du jour du scraping.

Il faut donc les reconstruire, et deux sources d'information s'y prêtent.

LES AFFICHES. Les sept matchs d'une grille l'identifient dans une base de
rencontres datée — football-data.co.uk, libre et gratuite. C'est vérifiable
grille par grille, et c'est ainsi que la grille 1848 s'est révélée être le
8 décembre 2020, sixième journée de Ligue des champions.

L'ORDRE DES NUMÉROS. Les identifiants croissent avec le temps. Une grille
prise entre deux grilles datées est donc encadrée, et l'écart médian entre
deux ancres n'est que d'un jour.

CE QU'ON NE FAIT PAS : déduire la date du seul numéro. Testé et réfuté —
entre deux points d'ancrage on compte 2 322 numéros pour 2 078 jours, donc
plus d'une grille par jour en moyenne, et la soustraction naïve place la
grille 1848 huit mois trop tôt.

    python dater_grilles.py --rapport

Les dates sont écrites dans data/dates_grilles.json, À CÔTÉ des grilles et
non dedans : un `--refaire` du scraper réécrit un fichier de grille en
entier et effacerait tout travail logé à l'intérieur.
"""

import argparse
import csv
import glob
import json
import os
import re
import ssl
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).parent
DATA_DIR = RACINE / "data" / "grilles"
CACHE_FD = RACINE / "data" / "football-data"
SORTIE = RACINE / "data" / "dates_grilles.json"

BASE_FD = "https://www.football-data.co.uk"
LIGUES = ("E0 E1 E2 E3 EC SC0 SC1 SC2 SC3 D1 D2 I1 I2 SP1 SP2 "
          "F1 F2 N1 B1 P1 T1 G1").split()
SAISONS = ["1516", "1617", "1718", "1819", "1920", "2021",
           "2122", "2223", "2324", "2425", "2526"]
EXTRA = "ARG AUT BRA CHN DNK FIN IRL JPN MEX NOR POL ROU RUS SWE SWZ USA".split()

# Une grille est ancrée si au moins AFFICHES_MINI de ses matchs se retrouvent
# dans une même fenêtre de FENETRE_JOURS. Le second seuil vient d'une
# observation de terrain : les matchs d'une grille se jouent le même jour, ou
# au plus sur trois jours. Le premier est un compromis — deux affiches
# suffiraient rarement à distinguer deux saisons d'une même rencontre.
AFFICHES_MINI = 3
AFFICHES_APPOINT = 2
FENETRE_JOURS = 3

# ANCRES RELEVÉES À LA MAIN, avec leur provenance. Elles rejoignent le
# squelette de confiance parce qu'elles sont vérifiées par un humain — mais
# elles subissent le même contrôle chronologique que les autres, et une
# désaccord avec une ancre automatique est signalé plutôt qu'arbitré en
# silence.
ANCRES_MANUELLES = {
    "grille7": {
        4170: (date(2026, 8, 17), "indiqué par l'utilisateur le 18/08/2026 : "
                                  "« la 4170 était hier »"),
        1848: (date(2020, 12, 8), "Ligue des champions J6 — PSG-Basaksehir "
                                  "interrompu ce soir-là, rejoué le lendemain"),
    },
}


def _plier(nom: str) -> str:
    """« Paris SG », « paris-sg » et « PARIS SG » doivent se valoir."""
    s = unicodedata.normalize("NFD", (nom or "").strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


# LE DICTIONNAIRE DES NOMS, s'il a été construit. Winamax écrit en français,
# football-data en anglais : sans lui, « FC Barcelone » et « Barcelona » sont
# deux équipes différentes. Il est produit par apparier_equipes.py, et chacune
# de ses entrées a été confirmée par une date — jamais écrite à la main.
_FICHIER_ALIAS = RACINE / "data" / "alias_equipes.json"
ALIAS = {}
if _FICHIER_ALIAS.exists():
    ALIAS = {k: v["vers"] for k, v in
             json.loads(_FICHIER_ALIAS.read_text(encoding="utf-8")).items()}


def _cle(nom: str) -> str:
    """Le nom d'une équipe de grille, ramené au vocabulaire de football-data."""
    plie = _plier(nom)
    return ALIAS.get(plie, plie)


def _date_fr(texte: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime((texte or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def telecharger(force: bool = False) -> int:
    """Le cache football-data, une fois pour toutes.

    Ces fichiers ne sont pas versionnés : ce sont les données d'un tiers, elles
    pèsent une vingtaine de mégaoctets, et elles se retéléchargent en deux
    minutes. Le dépôt n'a pas à les porter.
    """
    CACHE_FD.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    urls = [(f"{BASE_FD}/mmz4281/{s}/{l}.csv", CACHE_FD / f"{s}_{l}.csv")
            for s in SAISONS for l in LIGUES]
    urls += [(f"{BASE_FD}/new/{p}.csv", CACHE_FD / f"extra_{p}.csv") for p in EXTRA]

    pris = 0
    for url, dest in urls:
        if dest.exists() and dest.stat().st_size > 500 and not force:
            pris += 1
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            contenu = urllib.request.urlopen(req, timeout=30, context=ctx).read()
            if len(contenu) > 500:
                dest.write_bytes(contenu)
                pris += 1
        except Exception:                                # noqa: BLE001
            continue                                     # saison ou pays absent
    return pris


# Les colonnes de cotes de football-data, par ordre de préférence. La clôture
# avant l'ouverture : elle reflète le marché une fois informé, ce que la
# littérature sur le longshot bias prend pour référence.
COLONNES_COTES = [
    ("pinnacle_cloture", ("PSCH", "PSCD", "PSCA")),
    ("pinnacle", ("PSH", "PSD", "PSA")),
    ("bet365_cloture", ("B365CH", "B365CD", "B365CA")),
    ("bet365", ("B365H", "B365D", "B365A")),
]


def _flottant(valeur):
    """Une cote, ou rien. Une cote de 1.00 ne paie pas : ce n'est pas une cote."""
    try:
        f = float(valeur)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _competition(ligne: dict):
    """Le nom de la compétition, désambiguïsé par son pays.

    Les fichiers de championnats portent un code — F1, E0 — qui suffit. Les
    fichiers « extra » portent un nom de ligue qui ne suffit pas : « Serie A »
    désigne le Brésil chez eux et l'Italie chez les autres, « Premier League »
    la Russie autant que l'Angleterre. Sans le pays, deux championnats
    différents se confondraient sous une même étiquette.
    """
    code = ligne.get("Div")
    if code:
        return code.strip()
    ligue, pays = (ligne.get("League") or "").strip(), (ligne.get("Country") or "").strip()
    if ligue and pays:
        return f"{pays} · {ligue}"
    return ligue or None


def charger_rencontres() -> dict:
    """Les rencontres de football-data, avec leurs scores et leurs cotes.

    Même source que charger_fixtures, mais tout est gardé : c'est la vue dont
    ont besoin ceux qui rapprochent par le score — le joiner des cotes, et
    l'appariement des noms par date exacte.
    """
    index = defaultdict(list)
    for chemin in sorted(CACHE_FD.glob("*.csv")):
        with open(chemin, encoding="latin-1", newline="") as fh:
            for ligne in _lecteur(fh):
                dom = ligne.get("HomeTeam") or ligne.get("Home")
                ext = ligne.get("AwayTeam") or ligne.get("Away")
                jour = _date_fr(ligne.get("Date"))
                if not (dom and ext and jour):
                    continue
                cotes = {}
                for nom, (h, x, a) in COLONNES_COTES:
                    trio = (_flottant(ligne.get(h)), _flottant(ligne.get(x)),
                            _flottant(ligne.get(a)))
                    if all(trio):
                        cotes[nom] = trio
                buts = (ligne.get("FTHG") or ligne.get("HG"),
                        ligne.get("FTAG") or ligne.get("AG"))
                try:
                    score = (int(buts[0]), int(buts[1]))
                except (TypeError, ValueError):
                    score = None
                index[(_plier(dom), _plier(ext))].append(
                    {"date": jour, "score": score, "cotes": cotes,
                     "division": _competition(ligne)})
    return index


def _lecteur(fh) -> csv.DictReader:
    """Un DictReader dont la première colonne s'appelle vraiment comme elle
    s'affiche.

    Les fichiers récents de football-data commencent par une marque d'ordre
    des octets. Lus en latin-1 — ce qu'il faut bien faire, leurs noms d'équipes
    sont accentués en latin-1 — le premier en-tête devient « ï»¿Div » et
    `ligne.get("Div")` rend None. Rien ne casse : la date, les équipes et les
    cotes sont dans les colonnes suivantes et arrivent intactes. Seule la
    compétition disparaît, en silence, sur 16 394 rencontres des saisons
    2024/25 et 2025/26 — c'est-à-dire au moment précis où on a voulu s'en
    servir pour catégoriser les grilles.
    """
    lecteur = csv.DictReader(fh)
    if lecteur.fieldnames:
        lecteur.fieldnames = [c.removeprefix("ï»¿").removeprefix("\ufeff")
                              for c in lecteur.fieldnames]
    return lecteur


def charger_fixtures() -> dict:
    """Les rencontres datées, indexées par (domicile, extérieur) plié.

    DEUX FORMATS COEXISTENT chez football-data : les championnats européens
    nomment leurs colonnes HomeTeam/AwayTeam, les autres Home/Away. Les deux
    sont lus, sinon on perdrait l'Amérique du Sud — d'où viennent une bonne
    part des affiches de Coupe Libertadores des grilles.
    """
    fixtures = defaultdict(list)
    for chemin in sorted(CACHE_FD.glob("*.csv")):
        with open(chemin, encoding="latin-1", newline="") as fh:
            for ligne in _lecteur(fh):
                dom = ligne.get("HomeTeam") or ligne.get("Home")
                ext = ligne.get("AwayTeam") or ligne.get("Away")
                jour = _date_fr(ligne.get("Date"))
                if dom and ext and jour:
                    fixtures[(_plier(dom), _plier(ext))].append(jour)
    return fixtures


def ancrer(grilles: list, fixtures: dict, mini: int = None) -> dict:
    """Les grilles dont les affiches donnent une date. {id: (date, concordances)}"""
    mini = AFFICHES_MINI if mini is None else mini
    ancres = {}
    for gid, matchs in grilles:
        listes = [fixtures[(_cle(m["home"]), _cle(m["away"]))]
                  for m in matchs
                  if (_cle(m["home"]), _cle(m["away"])) in fixtures]
        candidats = sorted({j for liste in listes for j in liste})
        meilleur, jour = 0, None
        for ref in candidats:
            n = sum(1 for liste in listes
                    if any(0 <= (j - ref).days <= FENETRE_JOURS for j in liste))
            if n > meilleur:
                meilleur, jour = n, ref
        if meilleur >= mini:
            ancres[gid] = (jour, meilleur)
    return ancres


def ancrer_en_deux_temps(grilles: list, fixtures: dict, manuelles: dict) -> tuple:
    """Un squelette sûr d'abord, des ancres d'appoint validées par lui ensuite.

    TROIS AFFICHES CONCORDANTES SONT SÛRES, DEUX NE LE SONT PAS. Mesuré sur les
    4 030 grilles : à trois affiches, 0,7 % des ancres se révèlent
    chronologiquement incohérentes ; à deux, 4,8 %. Or une rencontre qui s'est
    jouée deux saisons de suite suffit à faire pointer une grille sur la
    mauvaise année, et l'erreur se propage ensuite par interpolation à toutes
    ses voisines.

    Mais exiger trois affiches coûte cher : 1 507 ancres au lieu de 2 149, et
    la datation à sept jours près tombe de 86 % à 77 %.

    On prend donc les deux. Le squelette est bâti à trois affiches, et une
    ancre à deux n'est admise QUE si elle tombe dans l'intervalle que le
    squelette autorise déjà pour cette grille. Résultat mesuré : 2 045 ancres
    — autant qu'en acceptant tout — mais une seule incohérence résiduelle au
    lieu de 103, les 99 mauvaises candidates ayant été écartées avant de
    pouvoir nuire.
    """
    squelette, rejetees_sq = filtrer_chronologie(ancrer(grilles, fixtures, AFFICHES_MINI))

    # Les ancres humaines entrent dans le squelette et priment.
    desaccords = []
    for gid, (jour, motif) in manuelles.items():
        if gid in squelette and squelette[gid][0] != jour:
            desaccords.append((gid, squelette[gid][0], jour, motif))
        squelette[gid] = (jour, 99)

    ids_sq = sorted(squelette)
    candidats = ancrer(grilles, fixtures, AFFICHES_APPOINT)
    admises, refusees = dict(squelette), 0
    for gid, (jour, n) in candidats.items():
        if gid in squelette:
            continue
        avant = [a for a in ids_sq if a < gid]
        apres = [a for a in ids_sq if a > gid]
        if not (avant and apres):
            continue
        if squelette[avant[-1]][0] <= jour <= squelette[apres[0]][0]:
            admises[gid] = (jour, n)
        else:
            refusees += 1

    finales, rejetees = filtrer_chronologie(admises)
    detail = {"squelette": len(squelette), "rejet_squelette": len(rejetees_sq),
              "appoint_admis": len(admises) - len(squelette),
              "appoint_refuse": refusees, "rejet_final": len(rejetees),
              "desaccords": desaccords, "candidates": admises}
    return finales, rejetees, detail


def filtrer_chronologie(ancres: dict) -> tuple:
    """Ne garder que le plus grand sous-ensemble d'ancres chronologiquement sain.

    UNE SEULE ANCRE FAUSSE EMPOISONNE TOUT CE QU'ELLE ENCADRE. Une rencontre
    qui s'est jouée deux saisons de suite peut faire pointer une grille sur la
    mauvaise année, et l'interpolation propagerait ensuite l'erreur aux
    dizaines de grilles voisines.

    Écarter naïvement toute ancre en désaccord avec la précédente supprimerait
    la bonne une fois sur deux. On cherche donc la plus longue sous-suite
    croissante — celle qui garde le maximum d'ancres tout en garantissant que
    les dates montent avec les numéros. Ce qui n'y entre pas est rejeté, et
    compté.
    """
    ids = sorted(ancres)
    if not ids:
        return {}, []
    # Plus longue sous-suite non décroissante, en O(n²) : quelques milliers
    # d'ancres au plus, la simplicité vaut mieux que la vitesse ici.
    longueur = [1] * len(ids)
    parent = [-1] * len(ids)
    for i in range(len(ids)):
        for j in range(i):
            if ancres[ids[j]][0] <= ancres[ids[i]][0] and longueur[j] + 1 > longueur[i]:
                longueur[i], parent[i] = longueur[j] + 1, j
    fin = max(range(len(ids)), key=lambda i: longueur[i])
    gardes, i = [], fin
    while i != -1:
        gardes.append(ids[i])
        i = parent[i]
    gardes.reverse()
    rejetes = [g for g in ids if g not in set(gardes)]
    return {g: ancres[g] for g in gardes}, rejetes


def interpoler(ancres: dict, tous: list) -> dict:
    """Encadrer chaque grille non ancrée entre les deux ancres qui l'entourent.

    Une grille entre deux ancres distantes de trois jours a sa date à trois
    jours près, et c'est écrit dans le résultat plutôt que masqué : `date_min`
    et `date_max` disent l'incertitude, `source` dit d'où vient la conclusion.
    Une date interpolée sur un intervalle de quarante jours ne doit pas
    ressembler à une date confirmée par cinq affiches.
    """
    ids_ancres = sorted(ancres)
    resultat = {}
    for gid in tous:
        if gid in ancres:
            jour, n = ancres[gid]
            resultat[gid] = {"date": jour.isoformat(), "date_min": jour.isoformat(),
                             "date_max": jour.isoformat(), "source": "affiches",
                             "affiches_concordantes": n}
            continue
        avant = [a for a in ids_ancres if a < gid]
        apres = [a for a in ids_ancres if a > gid]
        if avant and apres:
            a, b = avant[-1], apres[0]
            da, db = ancres[a][0], ancres[b][0]
            part = (gid - a) / (b - a)
            estimee = da + timedelta(days=round((db - da).days * part))
            resultat[gid] = {"date": estimee.isoformat(), "date_min": da.isoformat(),
                             "date_max": db.isoformat(), "source": "interpolation",
                             "incertitude_jours": (db - da).days}
        elif avant or apres:
            # Hors de la plage ancrée : on donne la borne connue et rien de
            # plus. Extrapoler ici reviendrait à réintroduire la déduction par
            # les numéros, précisément celle qu'on a réfutée.
            connu = ancres[avant[-1]][0] if avant else ancres[apres[0]][0]
            resultat[gid] = {"date": None,
                             "date_min": connu.isoformat() if avant else None,
                             "date_max": None if avant else connu.isoformat(),
                             "source": "hors_ancrage"}
    return resultat


def main() -> int:
    ap = argparse.ArgumentParser(description="Dater les grilles Loto Foot")
    ap.add_argument("--type", default="grille7",
                    choices=["grille7", "grille9", "grille12"])
    ap.add_argument("--telecharger", action="store_true",
                    help="rafraîchir le cache football-data avant de dater")
    ap.add_argument("--rapport", nargs="?", const="diagnostic/dates.txt", default=None,
                    metavar="FICHIER", help="écrire le détail sans troncature")
    args = ap.parse_args()

    if args.telecharger or not CACHE_FD.exists():
        print("Téléchargement du cache football-data…")
        print(f"  {telecharger()} fichier(s) disponibles")

    fixtures = charger_fixtures()
    total_rencontres = sum(len(v) for v in fixtures.values())
    print(f"Index : {len(fixtures)} affiches distinctes, {total_rencontres} rencontres datées")

    fichiers = sorted((DATA_DIR / args.type).glob("*.json"), key=lambda f: int(f.stem))
    grilles = []
    for f in fichiers:
        d = json.loads(f.read_text(encoding="utf-8"))
        grilles.append((d["grille_id"], d.get("matches", [])))
    print(f"Grilles : {len(grilles)}")

    manuelles = ANCRES_MANUELLES.get(args.type, {})
    ancres, rejetees, detail = ancrer_en_deux_temps(grilles, fixtures, manuelles)
    print(f"\nAncrage")
    print(f"  squelette (>= {AFFICHES_MINI} affiches, ancres manuelles comprises) : "
          f"{detail['squelette']}")
    print(f"  appoint (= {AFFICHES_APPOINT} affiches) : {detail['appoint_admis']} admis, "
          f"{detail['appoint_refuse']} refusés car hors de l'intervalle permis")
    print(f"  ancres retenues : {len(ancres)}  (incohérences résiduelles écartées : "
          f"{len(rejetees)})")
    for gid, auto, main_, motif in detail["desaccords"]:
        print(f"  DÉSACCORD grille {gid} : affiches {auto}, à la main {main_} — {motif}")
    candidates = detail["candidates"]

    dates = interpoler(ancres, [g for g, _ in grilles])
    par_source = defaultdict(int)
    for v in dates.values():
        par_source[v["source"]] += 1
    datees = sum(1 for v in dates.values() if v["date"])
    print(f"\nGrilles datées : {datees} / {len(grilles)} "
          f"({100 * datees / len(grilles):.0f} %)")
    for src, n in sorted(par_source.items(), key=lambda x: -x[1]):
        print(f"    {src:<16} {n}")

    serrees = [v for v in dates.values()
               if v["source"] == "interpolation" and v["incertitude_jours"] <= 3]
    interp = par_source["interpolation"]
    if interp:
        print(f"    dont interpolations à 3 jours près : {len(serrees)} "
              f"({100 * len(serrees) / interp:.0f} % des interpolations)")

    if datees:
        connues = sorted(v["date"] for v in dates.values() if v["date"])
        print(f"\nPériode couverte : {connues[0]} -> {connues[-1]}")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    ancien = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    ancien[args.type] = {str(k): v for k, v in sorted(dates.items())}
    SORTIE.write_text(json.dumps(ancien, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {SORTIE}")

    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        lignes = [f"{args.type} : {datees}/{len(grilles)} datées", ""]
        if rejetees:
            lignes.append(f"Ancres rejetées ({len(rejetees)}) — date incompatible "
                          f"avec l'ordre des numéros :")
            for gid in rejetees:
                jour, n = candidates[gid]
                lignes.append(f"    grille {gid} : {jour} ({n} affiches)")
            lignes.append("")
        lignes.append("Grilles sans date :")
        for gid, v in sorted(dates.items()):
            if not v["date"]:
                lignes.append(f"    grille {gid} : {v['source']}")
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"Rapport : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
