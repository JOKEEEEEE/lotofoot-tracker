"""Banc d'essai : ce qu'une façon de cocher aurait rapporté.

CE QUE MESURE CE FICHIER. Une stratégie est une fonction qui, pour une grille,
rend une ou plusieurs combinaisons — une par euro misé. On compte les bons
résultats de chacune, on lit le rapport du rang atteint, et on divise par le
nombre de combinaisons. Le rendement obtenu est donc par euro misé, comparable
d'une stratégie à l'autre quel que soit son coût.

CE QU'IL FAUT SAVOIR AVANT DE LIRE UN RÉSULTAT. Une grille sur dix rapporte
quelque chose, et le gros du rendement vient d'une poignée de grilles. Sur une
distribution pareille, un rendement moyen ne veut rien dire seul. Trois garde-
fous accompagnent donc chaque chiffre :

    l'INTERVALLE par bootstrap, parce que l'approximation normale ment sur une
    distribution aussi asymétrique ;
    la VALIDATION CROISÉE sur deux périodes disjointes, parce qu'une stratégie
    choisie après coup se valide toujours sur les données qui l'ont inspirée ;
    la CONCENTRATION, c'est-à-dire ce que devient le rendement quand on retire
    les trois meilleures grilles. Une stratégie qui s'effondre alors n'est pas
    une stratégie, c'est un billet de loterie qui a gagné.

Le mécanisme qui donne un sens à tout ceci se mesure indépendamment de toute
stratégie : quand le favori le plus évident d'une grille tombe, il reste 4
gagnants au rang 7 au lieu de 22, et le rapport moyen passe de 528 € à 1 767 €.
Le public se concentre sur l'évidence ; s'en écarter, c'est acheter de la
solitude. Voir --mecanisme.

    python strategies.py
    python strategies.py --mecanisme

Grille 7 seulement : les rangs et la répartition du pot n'ont pas le même
sens sur les autres formats.
"""

import argparse
import json
import random
import statistics
from pathlib import Path

import collecter_ws as cw

RACINE = Path(__file__).parent
DATA_POOLS = RACINE / "data" / "pools" / "grille7"
COTES = RACINE / "data" / "cotes_matchs.json"

MATCHS = 7
BOOTSTRAP = 3000
GRAINE = 1789
# Combien de grilles on retire pour éprouver la concentration.
TETE = 3


def charger(source: str = None) -> list:
    """Les grilles jouables : sept matchs cotés, un résultat, des rapports."""
    cotes = json.loads(COTES.read_text(encoding="utf-8"))
    grilles = []
    for f in sorted(DATA_POOLS.glob("*.json"), key=lambda f: int(f.stem)):
        d = json.loads(f.read_text(encoding="utf-8"))
        ms = d.get("matches", [])
        issues = cw.decoder_resultat(d.get("resultat_code"), len(ms))
        if len(ms) != MATCHS or any(not i or len(i) == 3 for i in issues):
            continue
        odds, probas = [], []
        for m in ms:
            c = cotes.get(str(m.get("match_id")))
            if not c or (source and c["source"] != source):
                break
            trio = (c["cote_1"], c["cote_N"], c["cote_2"])
            inverses = [1 / o for o in trio]
            total = sum(inverses)
            odds.append(trio)
            probas.append([i / total for i in inverses])
        else:
            grilles.append({
                "id": d["grille_id"], "fin": (d.get("fin") or "")[:10],
                "odds": odds, "p": probas,
                "vrai": [("1", "N", "2").index(next(iter(i))) for i in issues],
                "rangs": {r["nbCorrectResults"]: r.get("winningsPerGrid") or 0
                          for r in (d.get("rapports") or [])},
                "gagnants": {r["nbCorrectResults"]: r.get("winningGrids") or 0
                             for r in (d.get("rapports") or [])},
            })
    return grilles


# --- les briques dont les stratégies sont faites ------------------------------

def favori(g: dict) -> list:
    """L'issue la plus probable de chaque match."""
    return [max(range(3), key=lambda i: p[i]) for p in g["p"]]


def rang_issue(g: dict, j: int, place: int) -> int:
    """L'issue de rang `place` du match j — 0 le favori, 1 le second."""
    return sorted(range(3), key=lambda i: -g["p"][j][i])[place]


def plus_nets(g: dict, combien: int) -> list:
    """Les matchs dont le favori est le plus net, du plus net au moins net.

    C'est là que le public se concentre le plus, donc c'est là que s'en
    écarter rapporte le plus quand ça marche.
    """
    return sorted(range(MATCHS), key=lambda j: max(g["p"][j]), reverse=True)[:combien]


def gain(g: dict, combinaison: list) -> float:
    bons = sum(1 for a, b in zip(combinaison, g["vrai"]) if a == b)
    return g["rangs"].get(bons, 0.0)


# --- les stratégies -----------------------------------------------------------

def tout_favori(g):
    return [favori(g)]


def casser(combien: int):
    """Cocher le second favori sur les `combien` matchs les plus nets."""
    def strategie(g):
        picks = favori(g)
        for j in plus_nets(g, combien):
            picks[j] = rang_issue(g, j, 1)
        return [picks]
    return strategie


def doubler(combien: int):
    """Jouer les deux premières issues des `combien` matchs les plus nets.

    C'est la réponse à la variance : au lieu de parier que le grand favori
    tombe, on couvre les deux cas. Le coût double à chaque match doublé —
    2 combinaisons pour un, 4 pour deux — et le rendement par euro est la
    moyenne des combinaisons couvertes.
    """
    def strategie(g):
        cles = plus_nets(g, combien)
        jeux = [favori(g)]
        for j in cles:
            jeux = [c for base in jeux
                    for c in (base, [*base[:j], rang_issue(g, j, 1), *base[j + 1:]])]
        return jeux
    return strategie


def doubler_le_plus_serre(g):
    """L'intuition inverse : doubler là où le marché hésite le plus."""
    j = min(range(MATCHS), key=lambda k: max(g["p"][k]))
    base = favori(g)
    return [base, [*base[:j], rang_issue(g, j, 1), *base[j + 1:]]]


STRATEGIES = [
    ("tout favori", tout_favori, 1),
    ("casser le favori le plus net", casser(1), 1),
    ("casser les 2 favoris les plus nets", casser(2), 1),
    ("doubler le favori le plus net", doubler(1), 2),
    ("doubler les 2 favoris les plus nets", doubler(2), 4),
    ("doubler les 3 favoris les plus nets", doubler(3), 8),
    ("doubler le match le plus serré", doubler_le_plus_serre, 2),
]


# --- l'évaluation -------------------------------------------------------------

def rendements(strategie, grilles: list) -> list:
    """Le rendement par euro misé, grille par grille."""
    sortie = []
    for g in grilles:
        jeux = strategie(g)
        sortie.append(sum(gain(g, c) for c in jeux) / len(jeux))
    return sortie


def intervalle(valeurs: list) -> tuple:
    """L'intervalle à 95 % du rendement moyen, par bootstrap."""
    n = len(valeurs)
    tirage = random.Random(GRAINE)
    moyennes = sorted(sum(tirage.choices(valeurs, k=n)) / n for _ in range(BOOTSTRAP))
    return moyennes[int(0.025 * BOOTSTRAP)], moyennes[int(0.975 * BOOTSTRAP)]


def sans_la_tete(valeurs: list, combien: int = TETE) -> float:
    """Le rendement une fois les meilleures grilles retirées."""
    if len(valeurs) <= combien:
        return 0.0
    return sum(sorted(valeurs)[:-combien]) / len(valeurs)


def mecanisme(grilles: list) -> dict:
    """Ce que devient le rang 7 selon que le grand favori passe ou tombe.

    Mesure indépendante de toute stratégie : c'est le fait sur lequel les
    stratégies s'appuient, et il se vérifie sans en jouer aucune.
    """
    passe, tombe = [], []
    for g in grilles:
        j = plus_nets(g, 1)[0]
        if 7 not in g["rangs"]:
            continue
        cible = passe if g["vrai"][j] == favori(g)[j] else tombe
        cible.append((g["rangs"][7], g["gagnants"].get(7, 0)))
    return {"passe": passe, "tombe": tombe}


def main() -> int:
    ap = argparse.ArgumentParser(description="Banc d'essai des façons de cocher")
    ap.add_argument("--source", default=None, help="n'utiliser qu'une source de cotes")
    ap.add_argument("--mecanisme", action="store_true",
                    help="mesurer la solitude au lieu des stratégies")
    args = ap.parse_args()

    grilles = charger(args.source)
    if len(grilles) < 50:
        print(f"seulement {len(grilles)} grilles jouables — trop peu pour conclure")
        return 1
    grilles.sort(key=lambda g: g["fin"])
    coupe = len(grilles) // 2
    tot = f"{grilles[0]['fin']} → {grilles[-1]['fin']}"
    print(f"{len(grilles)} grilles jouables, {tot}\n")

    if args.mecanisme:
        m = mecanisme(grilles)
        print("Quand le favori le plus net d'une grille…")
        for nom, ens in (("passe", m["passe"]), ("TOMBE", m["tombe"])):
            r = [x for x, _ in ens]
            w = [n for _, n in ens]
            print(f"  …{nom:<6} {len(ens):>4} grilles   rang 7 moyen "
                  f"{statistics.mean(r):>9.2f} €   médian {statistics.median(r):>8.2f} €"
                  f"   gagnants médians {statistics.median(w):>5.0f}")
        n = len(m["passe"]) + len(m["tombe"])
        if n and m["passe"]:
            part = 100 * len(m["tombe"]) / n
            facteur = statistics.mean(x for x, _ in m["tombe"]) / \
                statistics.mean(x for x, _ in m["passe"])
            print(f"\nLe grand favori tombe {part:.0f} % du temps, et le rapport est "
                  f"alors multiplié par {facteur:.2f}.")
            print(f"S'écarter de lui coûte un facteur {(1-part/100)/(part/100):.2f} en "
                  f"chances et rapporte {facteur:.2f} en gain :")
            print(f"    espérance relative {facteur * (part/100) / (1-part/100):.2f}")
        return 0

    entete = (f"  {'stratégie':<38}{'coût':>6}{'rendement':>11}"
              f"{'période A':>11}{'période B':>11}{'IC 95 %':>17}{'sans top 3':>12}")
    print(entete)
    print("  " + "-" * (len(entete) - 2))
    for nom, strategie, cout in STRATEGIES:
        tous = rendements(strategie, grilles)
        a = rendements(strategie, grilles[:coupe])
        b = rendements(strategie, grilles[coupe:])
        bas, haut = intervalle(tous)
        print(f"  {nom:<38}{cout:>4} €{100*statistics.mean(tous):>9.0f} %"
              f"{100*statistics.mean(a):>9.0f} %{100*statistics.mean(b):>9.0f} %"
              f"{100*bas:>9.0f} – {100*haut:<5.0f}{100*sans_la_tete(tous):>10.0f} %")
    print(f"\n  période A : {grilles[0]['fin']} → {grilles[coupe-1]['fin']}")
    print(f"  période B : {grilles[coupe]['fin']} → {grilles[-1]['fin']}")
    print("\n  Repère : le joueur moyen touche 75 %, le prélèvement étant de 25 %.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
