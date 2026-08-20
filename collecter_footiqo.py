"""Les cotes des coupes, que football-data ne publie pas.

POURQUOI CETTE SOURCE. Sur les 8 979 matchs de la base sans cote,
37 % sont des coupes d'Europe : football-data ne publie que des championnats
nationaux, et c'est structurel. Footiqo publie les cotes de clôture 1xBet pour
la Ligue des champions, l'Europa League, la Conference League, la Copa
Libertadores et la Coupe du monde, à partir de la saison 2015/2016 —
c'est-à-dire exactement notre période, qui commence en septembre 2015.

CE QU'ON S'AUTORISE, ET CE QU'ON NE S'AUTORISE PAS. Leur `robots.txt`
n'interdit que `/wp-admin/`, et autorise explicitement `admin-ajax.php`, par
lequel passent leurs propres tableaux. Leurs CGU ne prohibent que le scraping
« at abusive rates » — d'où une pause franche entre deux requêtes et des
pages de 400 lignes plutôt que de 10. En revanche l'article 8 interdit la
redistribution sans autorisation écrite : ces fichiers vont donc dans
`data/footiqo/`, IGNORÉ PAR GIT. Le dépôt est public, il ne republiera pas la
donnée d'un tiers — même règle que pour football-data.

COMMENT ÇA MARCHE. Les tableaux sont des wpDataTables en mode serveur. La
page porte, pour chaque tableau, un jeton `wdtNonceFrontendServerSide_<id>`
que le script relit et renvoie sous le nom `wdtNonce` — c'est ce que fait leur
propre JavaScript. Sans lui, l'endpoint répond 200 avec un corps vide, ce qui
ressemble à un blocage et n'en est pas un.

    python collecter_footiqo.py                 # les cinq coupes
    python collecter_footiqo.py --tout          # championnats compris

Les championnats des cinq grands pays sont disponibles aussi, mais on ne les
prend pas : football-data les couvre déjà avec Pinnacle, qui vaut mieux qu'un
opérateur unique pour mesurer un biais de marché.
"""

import argparse
import json
import random
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path

RACINE = Path(__file__).parent
SORTIE = RACINE / "data" / "footiqo"
BASE = "https://footiqo.com/database/leagues/{slug}/"
AJAX = "https://footiqo.com/wp-admin/admin-ajax.php?action=get_wdtable&table_id={tid}"

# Ce qui manque à football-data. Les cinq championnats nationaux que Footiqo
# publie aussi sont volontairement absents de cette liste.
COUPES = ["europe-champions-league", "europe-europa-league",
          "europe-conference-league", "copa-libertadores", "world-cup"]
CHAMPIONNATS = ["england-premier-league", "france-ligue-1", "germany-bundesliga",
                "italy-serie-a", "spain-laliga"]

# On reconnaît un tableau à ses colonnes, pas à son numéro : celui-ci change
# d'une page à l'autre. Deux tableaux nous intéressent, et il faut LES DEUX :
# celui des cotes, et celui des scores. Le second n'est pas un luxe — sans
# score, la jointure ne peut plus vérifier qu'elle a rapproché le bon match,
# et la règle du projet est qu'au moindre doute on ne rapproche pas. Les deux
# tableaux partagent la colonne `id`, ce qui les recolle sans ambiguïté.
COLONNES_COTES = ("H", "D", "A")
COLONNES_SCORES = ("FTHG", "FTAG")
LIGNES_PAR_PAGE = 400
PAUSE = (3.0, 6.0)
NAVIGATEUR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _ouvrir():
    """Un client qui garde ses cookies, comme un navigateur."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar()))


def _lire(client, url, donnees=None, referer=None) -> str:
    req = urllib.request.Request(url, data=donnees)
    req.add_header("User-Agent", NAVIGATEUR)
    if referer:
        req.add_header("Referer", referer)
        req.add_header("X-Requested-With", "XMLHttpRequest")
    with client.open(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def tableaux_utiles(html: str) -> list:
    """Les tableaux de la page qui portent des cotes ou des scores.

    Chaque genre existe en deux exemplaires : la saison en cours et les
    saisons passées. On prend les deux — la frontière bouge d'un jour à
    l'autre, un match compté deux fois se dédoublonne par son `id`, un match
    manquant ne se rattrape pas.
    """
    trouves = []
    for m in re.finditer(r'data-wpdatatable_id="(\d+)"', html):
        tid = m.group(1)
        entetes = [e.strip() for e in
                   re.findall(r'wdtheader[^>]*>\s*([A-Za-z0-9_ ]+?)</th>',
                              html[m.start():m.start() + 4000])]
        if all(c in entetes for c in COLONNES_COTES):
            genre = "cotes"
        elif all(c in entetes for c in COLONNES_SCORES):
            genre = "scores"
        else:
            continue
        jeton = re.search(rf'name="wdtNonceFrontendServerSide_{tid}" value="([^"]+)"',
                          html)
        if jeton:
            trouves.append((tid, jeton.group(1), entetes, genre))
    return trouves


def _formulaire(colonnes: list, jeton: str, debut: int, combien: int) -> bytes:
    champs = [("draw", "1"), ("start", str(debut)), ("length", str(combien)),
              ("search[value]", ""), ("search[regex]", "false"),
              ("order[0][column]", "1"), ("order[0][dir]", "asc"),
              ("wdtNonce", jeton)]
    for i, c in enumerate(colonnes):
        champs += [(f"columns[{i}][data]", str(i)), (f"columns[{i}][name]", c),
                   (f"columns[{i}][searchable]", "true"),
                   (f"columns[{i}][orderable]", "true"),
                   (f"columns[{i}][search][value]", ""),
                   (f"columns[{i}][search][regex]", "false")]
    return urllib.parse.urlencode(champs).encode()


def collecter_page(slug: str) -> list:
    client = _ouvrir()
    url = BASE.format(slug=slug)
    html = _lire(client, url)
    tables = tableaux_utiles(html)
    if not tables:
        print(f"  [{slug}] aucun tableau exploitable sur la page")
        return []

    # Un seul dictionnaire par `id` : les colonnes des deux genres de tableaux
    # se complètent sur la même ligne plutôt que de se remplacer.
    lignes = {}
    for tid, jeton, colonnes, genre in tables:
        debut, total = 0, None
        while total is None or debut < total:
            corps = _lire(client, AJAX.format(tid=tid),
                          _formulaire(colonnes, jeton, debut, LIGNES_PAR_PAGE), url)
            try:
                rep = json.loads(corps)
            except json.JSONDecodeError:
                print(f"  [{slug}/{tid}] réponse illisible à la ligne {debut}")
                break
            total = int(rep.get("recordsFiltered") or 0)
            paquet = rep.get("data") or []
            if not paquet:
                break
            for r in paquet:
                lignes.setdefault(r[0], {}).update(zip(colonnes, r))
            debut += len(paquet)
            print(f"  [{slug}/{tid} {genre}] {min(debut, total)}/{total}")
            if debut < total:
                time.sleep(random.uniform(*PAUSE))
        time.sleep(random.uniform(*PAUSE))
    return list(lignes.values())


def charger() -> dict:
    """Les matchs collectés, dans la forme que la jointure attend.

    Même structure que `dater_grilles.charger_rencontres` — clé (domicile,
    extérieur) pliée, liste de rencontres portant date, score, cotes et
    compétition — pour que `rapprocher` fonctionne sans rien savoir de la
    source. Une cote de clôture 1xBet et une cote Pinnacle ne se mélangeront
    pas pour autant : la provenance suit chaque match jusqu'au bout.
    """
    import dater_grilles as dg
    index = defaultdict(list)
    for chemin in sorted(SORTIE.glob("*.json")):
        for l in json.loads(chemin.read_text(encoding="utf-8")):
            jour = _jour(l.get("matchDate"))
            if not jour:
                continue
            trio = tuple(dg._flottant(l.get(c)) for c in COLONNES_COTES)
            try:
                score = (int(l["FTHG"]), int(l["FTAG"]))
            except (KeyError, TypeError, ValueError):
                score = None
            index[(dg._plier(l["homeTeam"]), dg._plier(l["awayTeam"]))].append(
                {"date": jour, "score": score,
                 "cotes": {"footiqo_cloture": trio} if all(trio) else {},
                 "division": l.get("League")})
    return index


def _jour(texte):
    """« 15-09-15 20:45 » : jour, mois, année sur deux chiffres.

    L'heure est locale et on ne s'en sert pas — la jointure travaille au jour
    près, et une heure locale confrontée à un horodatage UTC ferait plus de
    dégâts qu'elle n'en éviterait.
    """
    try:
        return datetime.strptime((texte or "").strip(), "%d-%m-%y %H:%M").date()
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Cotes de coupe chez Footiqo")
    ap.add_argument("--tout", action="store_true",
                    help="ajouter les cinq championnats (redondant avec football-data)")
    ap.add_argument("--slug", action="append",
                    help="une compétition précise, répétable")
    args = ap.parse_args()

    slugs = args.slug or (COUPES + CHAMPIONNATS if args.tout else COUPES)
    SORTIE.mkdir(parents=True, exist_ok=True)
    total = 0
    for slug in slugs:
        lignes = collecter_page(slug)
        if not lignes:
            continue
        chemin = SORTIE / f"{slug}.json"
        chemin.write_text(json.dumps(lignes, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        cotes = sum(1 for l in lignes if l.get("H"))
        scores = sum(1 for l in lignes if l.get("FTHG") not in (None, ""))
        print(f"  -> {chemin}  ({len(lignes)} matchs, {cotes} avec cotes, "
              f"{scores} avec score)\n")
        total += len(lignes)
    print(f"{total} matchs enregistrés dans {SORTIE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
