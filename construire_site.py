"""L'index du site : ce qu'il faut pour lister 4 600 grilles sans les charger.

POURQUOI UN INDEX. Les grilles pèsent vingt mégaoctets, une par fichier. Les
charger toutes pour afficher une liste serait absurde ; les charger une par une
pour filtrer le serait encore plus. On produit donc un index compact qui porte
ce qu'une liste doit montrer et ce qu'un filtre doit trancher, et le détail
d'une grille reste dans son fichier, chargé quand on l'ouvre.

LE SITE NE DUPLIQUE RIEN. GitHub Pages sert le dépôt tel quel : la page va
chercher data/pools/grille7/4170.json là où il est déjà. C'est aussi ce qui
garantit qu'on ne publiera jamais une donnée qui n'est pas censée l'être —
data/pronosoft/ est ignoré par git, donc absent du dépôt, donc absent du site.

FORMAT. Un tableau de tableaux plutôt qu'un tableau d'objets : sur 4 600
entrées, répéter les noms de champs triple le poids pour rien. L'ordre des
colonnes est décrit dans « champs », et la page le lit.

    python construire_site.py
"""

import argparse
import json
from pathlib import Path

import collecter_ws as cw

RACINE = Path(__file__).parent
DATA_POOLS = RACINE / "data" / "pools"
SORTIE = RACINE / "data" / "index_site.json"
SORTIE_COTES = RACINE / "data" / "cotes_site.json"
COMPETITIONS = RACINE / "data" / "competitions_grilles.json"
COTES = RACINE / "data" / "cotes_matchs.json"

TYPES = ("grille7", "grille9", "grille12")
CHAMPS = ["type", "id", "date", "famille", "matchs", "cotees",
          "mises", "garanti", "distribue", "jouees", "trj", "rapports", "affiches",
          "debut", "statut", "surprises", "grosses"]

ISSUES = ("1", "N", "2")
# Ce qui sépare une surprise d'une GROSSE surprise. Mesuré, pas décrété : sur
# les 21 574 matchs cotés des grilles 7, l'issue sortie n'est pas le favori
# une fois sur deux (47,1 %) — c'est banal. Elle paie au moins trois fois la
# cote du favori dans 6,3 % des cas, soit un match sur seize, soit à peu près
# une grille de sept sur deux. Un seuil plus bas ne trierait plus rien ; un
# seuil plus haut ne laisserait presque aucune grille.
GROSSE_SURPRISE = 3.0


# Les sources de cotes, réduites à une lettre. Sur vingt mille matchs, écrire
# « pinnacle_cloture » en toutes lettres pèse plus que les cotes elles-mêmes.
#
# QUATRE MAISONS, PAS UNE DE PLUS. Winamax, Pinnacle, Bet365 et la FDJ pour le
# Loto Foot. Footiqo est sorti de la liste avec les 2 624 cotes qu'il portait :
# décision du propriétaire du dépôt, qui préfère une couverture plus faible
# mais homogène. Une cote d'une autre provenance ne se range plus sous « ? » —
# elle ne franchit pas cette porte du tout.
SOURCES = {"winamax": "w", "pinnacle_cloture": "p", "pinnacle": "p",
           "bet365_cloture": "b", "bet365": "b", "fdj": "d"}


def cotes_compactes(cotes: dict) -> dict:
    """Les cotes réduites au strict nécessaire pour l'affichage.

    3,4 Mo deviennent quelques centaines de kilo-octets : on ne garde que le
    triplet et une lettre de provenance, le reste — type de grille, numéro —
    étant déjà connu de celui qui affiche le match.
    """
    return {mid: [c["cote_1"], c["cote_N"], c["cote_2"], SOURCES[c["source"]]]
            for mid, c in cotes.items() if c["source"] in SOURCES}


def surprises(matchs, issues, cotes):
    """Combien de fois le marché s'est trompé sur cette grille, et lourdement.

    UNE SURPRISE SE MESURE CONTRE LES COTES, PAS CONTRE L'INTUITION. Le favori
    d'un match est l'issue la moins chère ; une surprise, c'est autre chose qui
    sort. Une grosse surprise, c'est une issue qui paie au moins
    GROSSE_SURPRISE fois la cote du favori — un rapport, pas une cote absolue,
    parce qu'un 4.00 dans un match serré et un 4.00 face à un archi-favori ne
    racontent pas la même histoire.

    UN MATCH ANNULÉ N'EST PAS UNE SURPRISE. Ses trois issues sont gagnantes :
    il ne dit rien du marché et ne compte ni au numérateur ni au dénominateur.

    Rend (surprises, grosses). Sans résultat ou sans aucune cote, (None, None) :
    on ne compte pas une absence comme un zéro.
    """
    vus = petites = grosses = 0
    for m, iss in zip(matchs, issues):
        if not iss:
            return None, None          # grille non réglée : rien à mesurer
        if len(iss) == 3:
            continue                   # annulé
        trio = cotes.get(str(m.get("match_id")))
        if not trio:
            continue
        v = [trio["cote_1"], trio["cote_N"], trio["cote_2"]]
        # decoder_resultat rend des ENSEMBLES, pas des listes : hors du cas
        # annulé il n'y en a qu'un, et c'est celui-là qu'on lit.
        sortie = v[ISSUES.index(next(iter(iss)))]
        favori = min(v)
        vus += 1
        if sortie > favori:
            petites += 1
            if sortie >= GROSSE_SURPRISE * favori:
                grosses += 1
    return (petites, grosses) if vus else (None, None)


def _trj(distribue, jouees):
    """Ce que les joueurs ont récupéré, par euro misé.

    Les mises brutes se déduisent du nombre de grilles jouées, l'unité étant
    de 1 €. Sans répartition connue, on ne devine pas : on rend None.
    """
    if not (distribue and jouees):
        return None
    return round(distribue / jouees, 4)


def construire() -> dict:
    competitions = json.loads(COMPETITIONS.read_text(encoding="utf-8")) \
        if COMPETITIONS.exists() else {}
    cotes = json.loads(COTES.read_text(encoding="utf-8")) if COTES.exists() else {}
    lignes = []
    for t in TYPES:
        dossier = DATA_POOLS / t
        if not dossier.exists():
            continue
        for f in sorted(dossier.glob("*.json"), key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            ms = d.get("matches", [])
            rep = d.get("repartition")
            jouees = sum(rep) if rep else None
            info = competitions.get(t, {}).get(str(d["grille_id"]), {})
            issues = cw.decoder_resultat(d.get("resultat_code"), len(ms))
            surp, gros = surprises(ms, issues, cotes)
            debuts = sorted(m["debut"] for m in ms if m.get("debut"))
            rapports = [[r.get("nbCorrectResults"), r.get("winningGrids"),
                         r.get("winningsPerGrid")]
                        for r in (d.get("rapports") or [])]
            lignes.append([
                int(t.replace("grille", "")),
                d["grille_id"],
                (d.get("fin") or "")[:10],
                info.get("famille", ""),
                len(ms),
                sum(1 for m in ms if str(m.get("match_id")) in cotes),
                d.get("mises_nettes"),
                d.get("montant_garanti"),
                d.get("montant_distribue"),
                jouees,
                _trj(d.get("montant_distribue"), jouees),
                rapports,
                # Les affiches en une chaîne : c'est ce qui rend la recherche
                # par équipe possible sans ouvrir 4 600 fichiers.
                " · ".join(f"{m.get('home','?')}-{m.get('away','?')}" for m in ms),
                # Le coup d'envoi du PREMIER match : c'est lui qui décide
                # qu'une grille est encore travaillable, pas la fin.
                debuts[0] if debuts else None,
                d.get("statut"),
                surp,
                gros,
            ])
    return {"champs": CHAMPS, "grilles": lignes}


def main() -> int:
    ap = argparse.ArgumentParser(description="Index du site de consultation")
    ap.add_argument("--sortie", default=str(SORTIE))
    args = ap.parse_args()

    index = construire()
    if COTES.exists():
        brutes = json.loads(COTES.read_text(encoding="utf-8"))
        SORTIE_COTES.write_text(
            json.dumps(cotes_compactes(brutes), separators=(",", ":")),
            encoding="utf-8")
        print(f"{len(brutes)} cotes — "
              f"{SORTIE_COTES.stat().st_size/1024:.0f} Ko "
              f"(contre {COTES.stat().st_size/1024:.0f} Ko en brut)")
    chemin = Path(args.sortie)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    n = len(index["grilles"])
    poids = chemin.stat().st_size / 1024
    cotees = sum(1 for g in index["grilles"] if g[5])
    datees = sum(1 for g in index["grilles"] if g[2])
    print(f"{n} grilles indexées — {poids:.0f} Ko")
    print(f"   datées {datees}   avec au moins une cote {cotees}")
    print(f"-> {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
