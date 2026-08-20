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


def systeme(doubles: int, triples: int, ordre: str = "nets",
            triples_sur: str = None):
    """Un système : des doubles et des triples posés sur certains matchs.

    LA QUESTION N'EST PAS COMBIEN, C'EST OÙ. À budget identique, poser ses
    doubles sur les matchs les plus SÛRS ou sur les plus INCERTAINS ne donne
    pas le même résultat, et l'écart va de 10 à 52 points de rendement.

        ordre = "nets"   les favoris les plus nets d'abord — les matchs qu'on
                         croit joués d'avance, et sur lesquels tout le monde
                         coche pareil ;
        ordre = "serres" les matchs les plus incertains d'abord — l'instinct
                         habituel, celui qui couvre là où l'on hésite.

    ET LES TRIPLES VONT AILLEURS QUE LES DOUBLES. `triples_sur` les place
    séparément, et la mesure est nette : à configuration identique, 4 doubles
    et 2 triples rapportent 23,38 € par grille quand les triples sont sur les
    matchs serrés, et 1,91 € quand ils sont sur les nets.

    La raison tient en une phrase. Un double sur un favori net achète de la
    SOLITUDE — l'issue rare que personne ne coche. Un triple n'achète aucune
    solitude puisqu'il prend tout, il achète de la SÉCURITÉ ; or on ne
    sécurise pas ce qui est déjà sûr. Chacun sert donc à l'autre bout de la
    grille.

    Par défaut les triples suivent `ordre`, pour que le comportement reste
    lisible ; c'est aux appelants de demander "serres" en connaissance.
    """
    def strategie(g):
        rang = sorted(range(MATCHS), key=lambda j: max(g["p"][j]),
                      reverse=(ordre == "nets"))
        ou_t = ordre if triples_sur is None else triples_sur
        cibles_t = (rang[:triples] if ou_t == ordre
                    else rang[::-1][:triples])
        # Les doubles prennent les meilleurs matchs restants, dans leur ordre.
        cibles_d = [j for j in rang if j not in cibles_t][:doubles]
        jeux = [favori(g)]
        for j in cibles_t:
            jeux = [[*c[:j], i, *c[j + 1:]] for c in jeux for i in range(3)]
        for j in cibles_d:
            jeux = [[*c[:j], i, *c[j + 1:]] for c in jeux
                    for i in (rang_issue(g, j, 0), rang_issue(g, j, 1))]
        return jeux
    return strategie


# Le seuil de netteté au-delà duquel un favori mérite d'être doublé. Balayé
# de 45 à 70 % : 45 % double presque tout et coûte 29 combinaisons pour 115 % ;
# 70 % ne double presque rien et retombe à 96 %. Entre les deux, 55 % est le
# seul réglage dont l'intervalle à 95 % reste au-dessus de 100.
SEUIL_NETTETE = 0.55


def adaptative(seuil: float = SEUIL_NETTETE, triples: int = 0):
    """Doubler tout match dont le favori dépasse le seuil — sans en fixer le nombre.

    LA TAILLE FIXE EST UN CONTRESENS. « Trois doubles » impose d'en poser trois
    même sur une grille où un seul favori est vraiment net, et d'en poser trois
    seulement là où cinq le mériteraient. Le seuil s'adapte : certaines grilles
    reçoivent un double, d'autres cinq, et le coût moyen tombe à huit
    combinaisons pour un meilleur rendement qu'un système fixe du même prix.

    Mesuré sur 2 093 grilles : 150 % de rendement, intervalle 101 à 209, et
    115 % en retirant les trois meilleures grilles — la robustesse la plus
    élevée de tout ce qui a été essayé.
    """
    def strategie(g):
        cibles_t = sorted(range(MATCHS), key=lambda j: max(g["p"][j]))[:triples]
        cibles_d = [j for j in range(MATCHS)
                    if max(g["p"][j]) >= seuil and j not in cibles_t]
        jeux = [favori(g)]
        for j in cibles_t:
            jeux = [[*c[:j], i, *c[j + 1:]] for c in jeux for i in range(3)]
        for j in cibles_d:
            jeux = [[*c[:j], i, *c[j + 1:]] for c in jeux
                    for i in (rang_issue(g, j, 0), rang_issue(g, j, 1))]
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
    ("adaptative : favori ≥ 55 %", adaptative(), 8),
    ("adaptative : favori ≥ 60 %", adaptative(0.60), 5),
    ("1 triple sur le plus net", systeme(0, 1), 3),
    ("1 triple + 2 doubles sur les plus nets", systeme(2, 1), 12),
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
    ap.add_argument("--systemes", action="store_true",
                    help="comparer où poser doubles et triples, à budget égal")
    ap.add_argument("--taille", action="store_true",
                    help="rendement par euro contre gain espéré en euros")
    ap.add_argument("--configs", action="store_true",
                    help="balayer toutes les configurations base/double/triple")
    ap.add_argument("--mise-max", type=int, default=400,
                    help="ne pas montrer les configurations plus chères")
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

    if args.systemes:
        # À BUDGET ÉGAL, seule la place change. C'est le seul tableau où la
        # comparaison est honnête : comparer un système à 8 € et un pari à 1 €
        # ne dit rien, puisque le premier achète huit fois plus de chances.
        print(f"  {'système':<26}{'combi.':>7}{'sur les NETS':>15}"
              f"{'sur les SERRÉS':>16}{'écart':>9}")
        print("  " + "-" * 73)
        for triples, doubles in ((0, 0), (0, 1), (0, 2), (1, 0), (0, 3),
                                 (1, 1), (0, 4), (1, 2), (2, 0), (1, 3)):
            if doubles + triples > MATCHS:
                continue
            valeurs = [statistics.mean(rendements(systeme(doubles, triples, o), grilles))
                       for o in ("nets", "serres")]
            nom = (f"{triples} triple{'s' if triples > 1 else ''} + "
                   f"{doubles} double{'s' if doubles > 1 else ''}" if triples
                   else (f"{doubles} double{'s' if doubles > 1 else ''}" if doubles
                         else "aucun (tout favori)"))
            print(f"  {nom:<26}{2**doubles * 3**triples:>6}€"
                  f"{100*valeurs[0]:>13.0f} %{100*valeurs[1]:>14.0f} %"
                  f"{valeurs[0]*100 - valeurs[1]*100:>+8.0f}")
        print("\n  « Nets » : doubles posés sur les favoris les plus courts.")
        print("  « Serrés » : posés sur les matchs les plus incertains.")
        return 0

    if args.taille:
        # DEUX MESURES QUI NE DISENT PAS LA MÊME CHOSE. Le rendement par euro
        # dit quelle mise travaille le mieux ; le gain espéré en euros dit
        # combien on ramène. Ils ne culminent pas au même endroit, et c'est
        # tout le sujet pour qui joue des grilles chères.
        print(f"  {'système (sur les plus nets)':<26}{'mise':>7}{'rend.':>8}"
              f"{'gain espéré':>13}{'marginal':>10}{'période A':>11}{'période B':>11}"
              f"{'sans top3':>11}")
        print("  " + "-" * 97)
        precedent = None
        for doubles, triples in ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0),
                                 (6, 0), (7, 0)):
            fn = systeme(doubles, triples, "nets")
            mise = 2 ** doubles * 3 ** triples
            tous = rendements(fn, grilles)
            moyen = statistics.mean(tous)
            espere = (moyen - 1) * mise
            # Ce que rapportent les euros AJOUTÉS par ce double de plus.
            marge = "—"
            if precedent is not None:
                sup = mise - precedent[0]
                marge = f"{100 * (1 + (espere - precedent[1]) / sup):.0f} %" if sup else "—"
            precedent = (mise, espere)
            nom = (f"{doubles} double{'s' if doubles > 1 else ''}" if doubles
                   else "tout favori")
            print(f"  {nom:<26}{mise:>6}€{100*moyen:>7.0f} %{espere:>+11.2f} €"
                  f"{marge:>10}"
                  f"{100*statistics.mean(rendements(fn, grilles[:coupe])):>10.0f} %"
                  f"{100*statistics.mean(rendements(fn, grilles[coupe:])):>10.0f} %"
                  f"{100*sans_la_tete(tous):>10.0f} %")
        print("\n  « Marginal » : ce que rendent les euros ajoutés par ce double "
              "de plus,")
        print("  et non le système entier. En dessous de 100 %, le double "
              "supplémentaire coûte.")
        return 0

    if args.configs:
        # TOUTES LES FAÇONS DE DÉCOUPER SEPT MATCHS en bases, doubles et
        # triples. Les doubles vont toujours sur les favoris les plus nets ;
        # seul le placement des triples varie, parce que c'est la seule chose
        # qui restait à trancher.
        resultats = []
        for triples in range(4):
            for doubles in range(MATCHS + 1 - triples):
                mise = 2 ** doubles * 3 ** triples
                if mise > args.mise_max:
                    continue
                for ou in (("nets",) if triples == 0 else ("serres", "nets")):
                    fn = systeme(doubles, triples, "nets", ou)
                    tous = rendements(fn, grilles)
                    moyen = statistics.mean(tous)
                    resultats.append((
                        MATCHS - doubles - triples, doubles, triples,
                        ou if triples else "—", mise, moyen, (moyen - 1) * mise,
                        statistics.mean(rendements(fn, grilles[:coupe])),
                        statistics.mean(rendements(fn, grilles[coupe:])),
                        sans_la_tete(tous)))
        resultats.sort(key=lambda r: -r[6])
        print(f"  {'base':>5}{'dbl':>5}{'trp':>5}  {'triples sur':<12}{'mise':>7}"
              f"{'rend.':>8}{'gain espéré':>13}{'période A':>11}{'période B':>11}"
              f"{'sans top3':>11}")
        print("  " + "-" * 88)
        for base, d, t, ou, mise, moyen, esp, a, b, st in resultats:
            print(f"  {base:>5}{d:>5}{t:>5}  {ou:<12}{mise:>6}€{100*moyen:>7.0f} %"
                  f"{esp:>+11.2f} €{100*a:>10.0f} %{100*b:>10.0f} %{100*st:>10.0f} %")
        print(f"\n  Trié par gain espéré. {len(resultats)} configurations, "
              f"mise plafonnée à {args.mise_max} €.")
        print("  Doubles toujours sur les favoris les plus nets ; la colonne "
              "dit où vont les triples.")
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
