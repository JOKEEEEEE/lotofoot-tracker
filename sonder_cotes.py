"""Chercher les cotes des vieilles grilles ailleurs que là où on les lisait.

CE QU'ON A MESURÉ. Les cotes 1/N/2 ne sont servies que sur deux plages :
du 24 septembre 2020 au 3 novembre 2021, et depuis le 17 novembre 2025.
Entre les deux — 1 640 grilles, quatre ans — `odds1/oddsX/odds2` sont nuls.
La répartition du public, elle, est servie sans interruption depuis
février 2021. Les deux champs sont donc indépendants : ce n'est pas la
grille entière qui vieillit, c'est ce champ-là.

CE QUE CE SCRIPT VÉRIFIE. Que `odds1/oddsX/odds2` sont bien le seul endroit
où une cote pourrait se trouver. On ne lit que trois clés d'un objet qui en
porte peut-être trente : tant qu'on n'a pas regardé les autres, « Winamax ne
sert plus les cotes » reste une hypothèse, pas un fait.

Il ne suppose rien du nom des champs. Il parcourt TOUTE la trame et signale
tout triplet de nombres qui ressemble à une cote — trois valeurs entre 1,01
et 100 dont les inverses somment à peu près à 1. Un bookmaker prend sa marge,
donc la somme des probabilités implicites vaut 1,05 à 1,20 ; c'est cette
signature qu'on cherche, pas un nom de clé.

    python sonder_cotes.py 4170          # témoin : une grille qui a ses cotes
    python sonder_cotes.py 3000          # le trou : une grille qui n'en a pas

Puis comparer les deux inventaires de clés. Les trames brutes sont écrites
dans diagnostic/, pour pouvoir y revenir sans relancer une visite.
"""

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

import collecter_ws as cw

DIAGNOSTIC = Path(__file__).parent / "diagnostic"

# Une cote payante est supérieure à 1. Au-delà de 100, on est sur un score
# exact ou un buteur, pas sur un 1/N/2.
COTE_MINI, COTE_MAXI = 1.01, 100.0
# La marge d'un opérateur. En dessous de 1, le triplet paierait plus qu'il ne
# collecte : ce n'est pas une cote. Au-dessus de 1,40, ce n'est plus un 1/N/2.
MARGE_MINI, MARGE_MAXI = 1.00, 1.40
# Au-delà, l'objet porte trop de nombres pour qu'un triplet fortuit veuille
# dire quoi que ce soit : on ne le fouille pas.
CANDIDATS_MAXI = 12


def _nombre(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def triplets_suspects(objet, chemin="") -> list:
    """Tout ce qui, dans cet objet, a la forme d'une cote 1/N/2.

    On ne cherche pas un nom de clé mais une signature arithmétique : trois
    nombres dont les inverses somment entre 1,00 et 1,40. C'est ce qui
    distingue une cote d'un montant, d'un compteur ou d'un horodatage.
    """
    trouves = []
    if isinstance(objet, dict):
        valides = [(k, _nombre(v)) for k, v in objet.items()
                   if _nombre(v) is not None and COTE_MINI <= _nombre(v) <= COTE_MAXI]
        # Toutes les combinaisons, pas seulement les clés voisines : rien ne
        # garantit qu'un modèle inconnu range ses trois cotes côte à côte.
        # Au-delà de CANDIDATS_MAXI valeurs numériques, l'objet n'est plus une
        # fiche de match et le tirage produirait surtout du bruit.
        if len(valides) <= CANDIDATS_MAXI:
            for trio in combinations(valides, 3):
                marge = sum(1 / v for _, v in trio)
                if MARGE_MINI <= marge <= MARGE_MAXI:
                    trouves.append((chemin, [k for k, _ in trio],
                                    [v for _, v in trio], round(marge, 4)))
        for k, v in objet.items():
            trouves += triplets_suspects(v, f"{chemin}.{k}" if chemin else k)
    elif isinstance(objet, list):
        for i, v in enumerate(objet):
            trouves += triplets_suspects(v, f"{chemin}[{i}]")
    return trouves


def inventaire(objets: dict) -> Counter:
    """Les clés présentes, et combien portent une valeur non nulle.

    Une clé absente et une clé à `null` ne disent pas la même chose : la
    première a disparu du modèle, la seconde a été vidée. C'est exactement la
    distinction qui nous intéresse ici.
    """
    presentes, remplies = Counter(), Counter()
    for o in objets.values():
        for k, v in o.items():
            presentes[k] += 1
            if v not in (None, "", [], {}):
                remplies[k] += 1
    return presentes, remplies


def sonder(grille_type: str, grille_id: int) -> int:
    pid = cw.pool_id(grille_type, grille_id)
    url = cw.BASE_URL.format(type=grille_type, id=grille_id)
    with cw.sync_playwright() as p:
        nav, page = cw._ouvrir(p)
        trames = cw._ecouter(page)
        essai = cw.visiter(page, trames, url, pid=pid)
        brutes = [t if isinstance(t, str) else t.decode("utf-8", "replace")
                  for t in trames]
        nav.close()

    if not essai:
        print(f"la grille {grille_id} n'est jamais arrivée")
        return 1

    DIAGNOSTIC.mkdir(exist_ok=True)
    brut = DIAGNOSTIC / f"trame-{grille_type}-{grille_id}.json"
    brut.write_text(json.dumps(brutes, ensure_ascii=False, indent=1), encoding="utf-8")

    pools, matchs = cw.extraire(brutes, pid)
    pool = next(iter(pools.values()), {})
    print(f"grille {grille_id} — {len(pool.get('matches') or [])} matchs, "
          f"{len(matchs)} objets match reçus")
    print(f"trame brute : {brut}\n")

    # NE PAS MÉLANGER LES DEUX POPULATIONS. La trame ne porte pas que la
    # grille demandée : elle charrie aussi les matchs des grilles en cours,
    # une quarantaine, et ceux-là ont leurs cotes puisqu'ils sont à venir.
    # Compter tout ensemble donnait « odds1 : 49 présentes, 33 remplies » sur
    # une grille de 2023 dont AUCUN des sept matchs n'a de cote — le chiffre
    # rassurait alors qu'il disait le contraire.
    siens = set(pool.get("matches") or [])
    dedans = {k: v for k, v in matchs.items() if k in siens}
    dehors = {k: v for k, v in matchs.items() if k not in siens}

    print(f"LES {len(dedans)} MATCHS DE LA GRILLE   (présentes / dont remplies)")
    presentes, remplies = inventaire(dedans)
    for k, n in presentes.most_common():
        marque = "  <-- présente mais vide" if remplies[k] == 0 else ""
        print(f"    {k:<28} {n:>3} / {remplies[k]:<3}{marque}")

    if dehors:
        pres_d, rempl_d = inventaire(dehors)
        print(f"\n  (la trame porte aussi {len(dehors)} matchs d'autres grilles, "
              f"dont {rempl_d.get('odds1', 0)} avec cotes — ils ne disent rien "
              f"de celle-ci)")

    print("\nCLÉS DU POOL")
    for k, v in sorted(pool.items()):
        apercu = "null" if v is None else str(v)[:60]
        print(f"    {k:<28} {apercu}")

    suspects = []
    for charge in brutes:
        suspects += triplets_suspects(cw._decoder_trame(charge))
    # Seuls comptent les triplets accrochés aux matchs de CETTE grille.
    # Les autres sont ceux des grilles en cours, et ils sont attendus.
    siens_txt = {str(m) for m in siens}
    suspects = [t for t in suspects
                if not t[0].startswith("matches.")
                or t[0].split(".")[1] in siens_txt]
    # Par marge croissante : un vrai 1/N/2 tourne autour de 1,05 à 1,20, et
    # les triplets fortuits — un score glissé à la place d'une cote — s'en
    # écartent. C'est un ordre de lecture, pas un filtre : rien n'est jeté.
    suspects.sort(key=lambda t: t[3])
    print(f"\nTRIPLETS AYANT LA FORME D'UNE COTE, HORS MATCHS ÉTRANGERS : "
          f"{len(suspects)}")
    for chemin, cles, valeurs, marge in suspects[:20]:
        print(f"    {chemin}\n        {cles} = {valeurs}   marge {marge}")
    if len(suspects) > 20:
        print(f"    ... et {len(suspects) - 20} autres")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Chercher des cotes ailleurs que dans odds1/oddsX/odds2")
    ap.add_argument("id", type=int, help="identifiant de grille, ex : 3000")
    ap.add_argument("--type", default="grille7",
                    choices=["grille7", "grille9", "grille12"])
    args = ap.parse_args()
    return sonder(args.type, args.id)


if __name__ == "__main__":
    raise SystemExit(main())
