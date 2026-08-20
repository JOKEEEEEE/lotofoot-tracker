"""Construire le dictionnaire des noms d'équipes, et le faire valider par les dates.

WINAMAX ÉCRIT EN FRANÇAIS, FOOTBALL-DATA EN ANGLAIS. « FC Barcelone » contre
« Barcelona », « Manchester United » contre « Man United », « Naples » contre
« Napoli ». Sur les quinze noms les plus fréquemment introuvables, quinze
étaient présents sous un autre libellé : ce qui ressemblait à un trou de
couverture de 68 % était un dictionnaire manquant.

CE QUI REND CE DICTIONNAIRE FIABLE, ce n'est pas la ressemblance des chaînes —
elle ne fait que proposer des candidats — mais LA DATE. Les grilles étant
datées à quelques jours près, un alias n'est retenu que si, une fois substitué,
la rencontre tombe dans la fenêtre de la grille. « Milan » et « Milan AC » se
ressemblent autant que « Milan » et « Inter Milan » ; seule la date tranche.

Aucun alias n'est donc écrit à la main, et aucun n'est cru sur sa mine.

    python apparier_equipes.py --rapport

Le dictionnaire part dans data/alias_equipes.json, avec pour chaque entrée le
nombre de rencontres qui l'ont confirmé.
"""

import argparse
import json
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import dater_grilles as dg

RACINE = Path(__file__).parent
SORTIE = RACINE / "data" / "alias_equipes.json"

# Un candidat en dessous de ce seuil de ressemblance n'est même pas soumis à la
# validation par les dates : c'est un filtre de débroussaillage, pas un critère.
SIMILARITE_MINI = 0.55
# Nombre de rencontres devant confirmer un alias. Deux plutôt qu'une, parce
# qu'une coïncidence isolée arrive — deux équipes homonymes jouant le même jour.
CONFIRMATIONS_MINI = 2
# Marge ajoutée à la fenêtre de la grille, les matchs pouvant s'étaler.
MARGE_JOURS = 3


def _sans_accents(texte: str) -> str:
    plie = unicodedata.normalize("NFD", texte or "")
    return "".join(c for c in plie if unicodedata.category(c) != "Mn").lower()


def _mots(nom: str) -> set:
    """Les mots signifiants d'un nom, sans les préfixes de club."""
    bruit = {"fc", "ac", "as", "sc", "cf", "sv", "afc", "cd", "ca", "rc", "us",
             "ss", "ssc", "aj", "og", "fk", "sk", "bk", "if", "de", "la", "le"}
    return {m for m in _sans_accents(nom).replace("-", " ").split() if m not in bruit}


def candidats(nom_wina: str, noms_fd: dict) -> list:
    """Les noms football-data qui pourraient désigner la même équipe.

    Deux signaux, parce qu'aucun ne suffit : la ressemblance de chaîne attrape
    « Barcelone »/« Barcelona », le partage de mots attrape « Borussia
    Dortmund »/« Dortmund ». On propose large, la date fera le tri.
    """
    cible, mots_cible = _sans_accents(nom_wina), _mots(nom_wina)
    trouves = []
    for plie, brut in noms_fd.items():
        mots_fd = _mots(brut)
        partage = bool(mots_cible & mots_fd)
        ratio = SequenceMatcher(None, cible, _sans_accents(brut)).ratio()
        if partage or ratio >= SIMILARITE_MINI:
            trouves.append((plie, brut, ratio + (0.3 if partage else 0)))
    trouves.sort(key=lambda x: -x[2])
    return trouves[:12]


def apparier(grilles: list, fixtures: dict, dates: dict, noms_fd: dict) -> tuple:
    """Le dictionnaire, validé rencontre par rencontre.

    Pour chaque nom introuvable, on essaie ses candidats sur toutes les grilles
    où il apparaît : un candidat compte une confirmation quand la rencontre
    ainsi reconstituée tombe dans la fenêtre de dates de la grille. Le candidat
    le plus confirmé gagne, à condition d'atteindre le seuil.
    """
    connus = set(noms_fd)
    # Où chaque nom inconnu apparaît, et contre qui.
    apparitions = defaultdict(list)
    for gid, matchs in grilles:
        info = dates.get(str(gid), {})
        if not info.get("date_min") or not info.get("date_max"):
            continue
        lo = date.fromisoformat(info["date_min"]) - timedelta(days=MARGE_JOURS)
        hi = date.fromisoformat(info["date_max"]) + timedelta(days=MARGE_JOURS)
        for m in matchs:
            dom, ext = dg._plier(m["home"]), dg._plier(m["away"])
            if dom not in connus:
                apparitions[m["home"]].append((dom, ext, lo, hi, "dom"))
            if ext not in connus:
                apparitions[m["away"]].append((dom, ext, lo, hi, "ext"))

    alias, refuses = {}, []
    for nom_brut, contextes in sorted(apparitions.items(), key=lambda x: -len(x[1])):
        scores = Counter()
        for plie_fd, brut_fd, _ in candidats(nom_brut, noms_fd):
            for dom, ext, lo, hi, cote in contextes:
                paire = (plie_fd, ext) if cote == "dom" else (dom, plie_fd)
                if any(lo <= j <= hi for j in fixtures.get(paire, ())):
                    scores[(plie_fd, brut_fd)] += 1
        if not scores:
            refuses.append((nom_brut, len(contextes), None, 0))
            continue
        (plie_fd, brut_fd), n = scores.most_common(1)[0]
        if n >= CONFIRMATIONS_MINI:
            alias[dg._plier(nom_brut)] = {"vers": plie_fd, "nom_football_data": brut_fd,
                                          "confirmations": n,
                                          "apparitions": len(contextes)}
        else:
            refuses.append((nom_brut, len(contextes), brut_fd, n))
    return alias, refuses


# La seconde passe n'a pas besoin de la ressemblance des chaînes, donc elle
# n'en veut pas : « Mayence »/« Mainz » et « Majorque »/« Mallorca » ne se
# ressemblent pas assez pour franchir SIMILARITE_MINI, et la première passe les
# perd toutes les deux. Deux confirmations suffisent ici parce que chacune vaut
# beaucoup plus cher : jour exact ET score identique.
CONFIRMATIONS_DATE_EXACTE = 2
# Un candidat n'est retenu que s'il devance nettement son suivant. Trois fois,
# et non « strictement plus » : deux noms qui se disputent un alias à une voix
# près sont un signe d'ambiguïté, pas un vainqueur.
AVANCE_MINI = 3


def apparier_par_date_exacte(grilles: list, rencontres: dict, table: dict = None) -> tuple:
    """Le dictionnaire déduit des dates exactes du websocket.

    LA DATE APPROXIMATIVE OBLIGEAIT À DEVINER, LA DATE EXACTE PERMET DE
    DÉDUIRE. Quand une grille dit que Schalke 04 reçoit « Mayence » le
    13 septembre 2015, et que football-data ne connaît qu'une seule rencontre
    à domicile de Schalke ce jour-là, l'adversaire est nommé sans qu'aucune
    ressemblance de chaîne n'intervienne. Le score sert de contre-épreuve :
    même jour, même équipe, même orientation, même score.

    Une équipe ne joue jamais deux fois le même jour : c'est ce qui rend
    l'inférence sûre, et c'est pourquoi on exige qu'il n'y ait qu'un seul
    candidat — sans quoi c'est l'index qui est ambigu, et on renonce.

    `table` porte les alias déjà acquis. Elle n'est pas un confort : sans elle
    « Manchester United » reste inconnu, donc le match où il affronte
    « Mayence » a ses deux côtés inconnus et ne sert à rien. Chaque alias
    connu en débloque d'autres — la seconde passe se nourrit de la première.
    """
    table = dg.ALIAS if table is None else table

    def resoudre(nom):
        plie = dg._plier(nom)
        return table.get(plie, plie)

    par_jour = defaultdict(list)
    connues = set()
    for (dom, ext), liste in rencontres.items():
        connues.update((dom, ext))
        for r in liste:
            par_jour[(dom, r["date"], "dom")].append((ext, r["score"]))
            par_jour[(ext, r["date"], "ext")].append((dom, r["score"]))

    propositions, apparitions = defaultdict(Counter), Counter()
    for _, matchs in grilles:
        for m in matchs:
            if not m.get("debut"):
                continue
            notre = (m.get("score_home"), m.get("score_away"))
            if None in notre:
                continue                    # sans score, pas de contre-épreuve
            dom, ext = resoudre(m["home"]), resoudre(m["away"])
            if (dom, ext) in rencontres:
                continue                    # déjà rapprochable en l'état
            jour = date.fromisoformat(m["debut"][:10])
            for connu, inconnu, brut, role in ((dom, ext, m["away"], "dom"),
                                               (ext, dom, m["home"], "ext")):
                if connu not in connues or inconnu in connues:
                    continue
                apparitions[brut] += 1
                cands = par_jour.get((connu, jour, role), [])
                if len(cands) != 1:
                    continue                # zéro ou deux : on ne tranche pas
                adverse, score = cands[0]
                if score is None or score != tuple(notre):
                    continue                # la contre-épreuve échoue
                propositions[brut][adverse] += 1

    alias, refuses = {}, []
    for brut, scores in propositions.items():
        (gagnant, n), = scores.most_common(1)
        suivant = scores.most_common(2)[1][1] if len(scores) > 1 else 0
        if n < CONFIRMATIONS_DATE_EXACTE:
            refuses.append((brut, apparitions[brut], gagnant, n))
        elif n < AVANCE_MINI * suivant:
            refuses.append((brut, apparitions[brut], f"{gagnant} ?", n))
        else:
            alias[dg._plier(brut)] = {"vers": gagnant, "nom_football_data": gagnant,
                                      "confirmations": n,
                                      "apparitions": apparitions[brut],
                                      "par": "date_exacte"}
    return alias, refuses


def main() -> int:
    ap = argparse.ArgumentParser(description="Dictionnaire des noms d'équipes")
    ap.add_argument("--type", default="grille7",
                    choices=["grille7", "grille9", "grille12"])
    ap.add_argument("--rapport", nargs="?", const="diagnostic/alias.txt", default=None,
                    metavar="FICHIER")
    args = ap.parse_args()

    fixtures = dg.charger_fixtures()
    noms_fd = {}
    for chemin in sorted((RACINE / "data" / "football-data").glob("*.csv")):
        import csv
        with open(chemin, encoding="latin-1", newline="") as fh:
            for ligne in csv.DictReader(fh):
                for cle in ("HomeTeam", "AwayTeam", "Home", "Away"):
                    v = ligne.get(cle)
                    if v:
                        noms_fd.setdefault(dg._plier(v), v.strip())
    print(f"football-data : {len(noms_fd)} noms d'équipes")

    dates = json.loads((RACINE / "data" / "dates_grilles.json")
                       .read_text(encoding="utf-8")).get(args.type, {})
    grilles = []
    for f in sorted((dg.DATA_DIR / args.type).glob("*.json"), key=lambda f: int(f.stem)):
        d = json.loads(f.read_text(encoding="utf-8"))
        grilles.append((d["grille_id"], d.get("matches", [])))
    print(f"grilles : {len(grilles)}, datées : {sum(1 for v in dates.values() if v.get('date'))}")

    alias, refuses = apparier(grilles, fixtures, dates, noms_fd)

    # SECONDE PASSE, sur les grilles du websocket : elles portent le jour et
    # le score exacts, là où data/grilles n'a qu'une fenêtre de dates.
    pools = []
    for t in ("grille7", "grille9", "grille12"):
        for f in sorted((RACINE / "data" / "pools" / t).glob("*.json"),
                        key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            pools.append((d["grille_id"], d.get("matches", [])))
    if pools:
        # La table de départ est celle que la première passe VIENT de
        # construire, jamais le dictionnaire déjà sur le disque : celui-ci est
        # le résultat de la veille, et s'en servir rendrait le script non
        # reproductible — il relirait sa propre sortie, ne re-proposerait pas
        # ce qu'il y trouve, et le perdrait en réécrivant le fichier.
        table = {k: v["vers"] for k, v in alias.items()}
        neufs, refuses_date = apparier_par_date_exacte(
            pools, dg.charger_rencontres(), table)
        conflits = [(k, alias[k]["vers"], v["vers"]) for k, v in neufs.items()
                    if k in alias and alias[k]["vers"] != v["vers"]]
        ajoutes = {k: v for k, v in neufs.items() if k not in alias}
        alias.update(ajoutes)
        refuses += [r for r in refuses_date if dg._plier(r[0]) not in alias]
        print(f"\nseconde passe (date exacte) sur {len(pools)} grilles : "
              f"{len(neufs)} alias, dont {len(ajoutes)} inédits")
        for k, a, b in conflits:
            # Un désaccord entre les deux passes n'est pas arbitré en silence.
            print(f"    CONFLIT  {k} : première passe {a}, seconde {b} — "
                  f"la première est conservée")

    couverts = sum(a["apparitions"] for a in alias.values())
    perdus = sum(n for _, n, _, _ in refuses)
    print(f"\nalias confirmés par les dates : {len(alias)}")
    print(f"   apparitions ainsi récupérées : {couverts}")
    print(f"noms restés sans alias : {len(refuses)}  ({perdus} apparitions)")

    print("\n  les 12 alias les plus utiles :")
    for plie, a in sorted(alias.items(), key=lambda x: -x[1]["apparitions"])[:12]:
        print(f"    {a['apparitions']:>4} fois  ->  {a['nom_football_data']:<18} "
              f"({a['confirmations']} confirmation(s))")

    SORTIE.write_text(json.dumps(alias, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding="utf-8")
    print(f"\n-> {SORTIE}")

    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        lignes = [f"{len(alias)} alias confirmés", ""]
        for plie, a in sorted(alias.items(), key=lambda x: -x[1]["apparitions"]):
            lignes.append(f"  {plie:<28} -> {a['nom_football_data']:<22} "
                          f"{a['apparitions']:>4} apparitions, "
                          f"{a['confirmations']} confirmations")
        lignes += ["", f"{len(refuses)} noms sans alias :"]
        for nom, n, propose, conf in sorted(refuses, key=lambda x: -x[1]):
            suite = f" (meilleur candidat {propose}, {conf} confirmation(s))" if propose else ""
            lignes.append(f"  {nom:<34} {n:>4} apparitions{suite}")
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        print(f"Rapport : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
