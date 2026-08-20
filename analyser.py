"""Ce que onze ans de grilles disent du marché et du public.

TROIS QUESTIONS, DANS L'ORDRE OÙ ELLES SE POSENT.

    1. Le marché se trompe-t-il, et où ? — mesuré par le RENDEMENT d'une mise
       plate par tranche de cote. Le rendement ne demande aucune hypothèse :
       on mise un euro, on compte ce qui revient. C'est la seule mesure du
       biais favori/outsider qui ne dépende pas de la façon dont on retire la
       marge du bookmaker.

    2. Le public se trompe-t-il, et où ? — mesuré en confrontant `repart`, la
       distribution réelle des grilles jouées par nombre de bons résultats, à
       ce qu'aurait donné un joueur qui suivrait les cotes.

    3. Les deux erreurs sont-elles les mêmes ? — c'est là qu'un pari mutuel
       devient intéressant : on n'y joue pas contre le bookmaker mais contre
       les autres joueurs.

POURQUOI PAS DE CALIBRATION EN PROBABILITÉS. Convertir une cote en
probabilité oblige à répartir la marge entre les trois issues, et la méthode
proportionnelle — la plus courante — attribue mécaniquement trop de
probabilité aux outsiders. Le biais favori/outsider apparaît alors même sur
des données parfaitement calibrées. On donne quand même la lecture en
probabilités, mais en second, et avec cet avertissement.

    python analyser.py --rapport

"""

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import collecter_ws as cw

RACINE = Path(__file__).parent
DATA_POOLS = RACINE / "data" / "pools"
COTES = RACINE / "data" / "cotes_matchs.json"
COMPETITIONS = RACINE / "data" / "competitions_grilles.json"

# Tranches de cote. Bornes choisies pour garder des effectifs comparables et
# séparer ce que le marché traite différemment : le très gros favori, le
# match équilibré, l'outsider, l'improbable.
TRANCHES = [(1.0, 1.3), (1.3, 1.6), (1.6, 2.0), (2.0, 2.5), (2.5, 3.2),
            (3.2, 4.5), (4.5, 7.0), (7.0, 12.0), (12.0, float("inf"))]
EFFECTIF_MINI = 100
# Rééchantillonnages pour l'intervalle du rendement.
BOOTSTRAP = 4000
ISSUES = ("1", "N", "2")


def charger(source: str = None) -> list:
    """Les matchs exploitables : une issue connue, et trois cotes.

    L'issue vient de `strPoolResult`, pas du score : c'est lui qui distingue
    un vrai 0-0 d'un match annulé payé à toutes les issues. Un match annulé
    n'a pas de résultat, donc il sort de l'analyse.
    """
    cotes = json.loads(COTES.read_text(encoding="utf-8"))
    competitions = json.loads(COMPETITIONS.read_text(encoding="utf-8"))
    vus, retenus = set(), []
    for t in ("grille7", "grille9", "grille12"):
        for f in sorted((DATA_POOLS / t).glob("*.json"), key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            ms = d.get("matches", [])
            issues = cw.decoder_resultat(d.get("resultat_code"), len(ms))
            info = competitions.get(t, {}).get(str(d["grille_id"]), {})
            for m, iss in zip(ms, issues):
                mid = str(m.get("match_id"))
                if mid in vus or mid not in cotes or not iss or len(iss) == 3:
                    continue
                if source and cotes[mid]["source"] != source:
                    continue
                vus.add(mid)
                c = cotes[mid]
                retenus.append({
                    "id": mid,
                    "odds": (c["cote_1"], c["cote_N"], c["cote_2"]),
                    "source": c["source"],
                    "gagnant": ISSUES.index(next(iter(iss))),
                    "annee": (m.get("debut") or "")[:4],
                    "famille": info.get("famille", "indéterminée"),
                })
    return retenus


def rendement(paris: list) -> tuple:
    """Rendement d'une mise de 1 € et son intervalle à 95 %.

    L'écart-type se calcule sur les gains réellement observés, pas sur une
    cote moyenne : dans une tranche ouverte — les cotes au-delà de 12 — la
    moyenne n'a pas de sens et l'intervalle explose.
    """
    n = len(paris)
    if not n:
        return 0.0, 0.0, 0
    gains = [cote if gagne else 0.0 for cote, gagne in paris]
    moyenne = sum(gains) / n
    variance = sum((g - moyenne) ** 2 for g in gains) / n
    return moyenne, 1.96 * math.sqrt(variance / n), n


def par_tranche(matchs: list, filtre=None) -> list:
    """Le rendement d'une mise plate, tranche de cote par tranche de cote."""
    seaux = defaultdict(list)
    for m in matchs:
        if filtre and not filtre(m):
            continue
        for i, cote in enumerate(m["odds"]):
            for borne in TRANCHES:
                if borne[0] <= cote < borne[1]:
                    seaux[borne].append((cote, i == m["gagnant"]))
                    break
    lignes = []
    for borne in TRANCHES:
        r, marge, n = rendement(seaux[borne])
        if n >= EFFECTIF_MINI:
            gagnes = sum(1 for _, g in seaux[borne] if g)
            lignes.append((borne, n, gagnes / n, r, marge))
    return lignes


def probabilites(odds: tuple) -> tuple:
    """Les trois probabilités implicites, marge répartie proportionnellement.

    Méthode connue pour surestimer les outsiders. Elle sert ici à comparer des
    grilles entre elles, pas à mesurer un biais.
    """
    inverses = [1 / o for o in odds]
    total = sum(inverses)
    return tuple(i / total for i in inverses)


def evaluer_grille(ms: list, issues: list, rep: list, rapports: list,
                   cotes: dict) -> dict:
    """Une grille jugée : le public, deux joueurs de référence, et le gain.

    `repart` donne le nombre de grilles jouées par nombre de bons résultats.
    On le confronte à deux joueurs :

        le SUIVEUR DE COTES coche l'issue la plus probable de chaque match —
        la stratégie évidente, celle à battre ;
        le PROBABILISTE coche chaque issue à hauteur de sa probabilité — le
        comportement que la littérature prête aux foules.

    TOUT EST RAMENÉ À UNE FRACTION DES MATCHS. Une grille 12 offre douze
    occasions de tomber juste, une grille 7 en offre sept : moyenner les deux
    en nombre absolu compare des choses qui ne se comparent pas, et faisait
    apparaître un suiveur de cotes à 6,6 bons résultats sur 7.
    """
    favori = probabiliste = 0.0
    for m, iss in zip(ms, issues):
        c = cotes[str(m["match_id"])]
        p = probabilites((c["cote_1"], c["cote_N"], c["cote_2"]))
        gagnant = ISSUES.index(next(iter(iss)))
        favori += (p.index(max(p)) == gagnant)
        probabiliste += p[gagnant]

    joue = sum(rep)
    # CE QUE LA GRILLE DES FAVORIS AURAIT RAPPORTÉ. En pari mutuel, bien
    # pronostiquer ne suffit pas : le rapport se partage entre ceux qui ont
    # trouvé la même chose. Une stratégie évidente l'est pour tout le monde.
    rangs = {r.get("nbCorrectResults"): r.get("winningsPerGrid") or 0
             for r in (rapports or [])}
    return {
        "matchs": len(ms),
        "joue": joue,
        "public": sum(k * n for k, n in enumerate(rep)) / joue / len(ms),
        "favori": favori / len(ms),
        "probabiliste": probabiliste / len(ms),
        "favori_justes": int(favori),
        "gain_favori": rangs.get(int(favori), 0.0),
    }


def public(cotes: dict, source: str = None) -> list:
    """Toutes les grilles jugeables : cotes complètes et répartition connue."""
    grilles = []
    for t in ("grille7", "grille9", "grille12"):
        for f in sorted((DATA_POOLS / t).glob("*.json"), key=lambda f: int(f.stem)):
            d = json.loads(f.read_text(encoding="utf-8"))
            rep, ms = d.get("repartition"), d.get("matches", [])
            issues = cw.decoder_resultat(d.get("resultat_code"), len(ms))
            if not rep or not ms or len(rep) != len(ms) + 1 or not sum(rep):
                continue
            if any(str(m.get("match_id")) not in cotes for m in ms):
                continue
            if source and any(cotes[str(m["match_id"])]["source"] != source
                              for m in ms):
                continue
            if any(not i or len(i) == 3 for i in issues):
                continue
            g = evaluer_grille(ms, issues, rep, d.get("rapports"), cotes)
            g.update({"id": d["grille_id"], "type": t,
                      "annee": (d.get("fin") or "")[:4]})
            grilles.append(g)
    return grilles


def _bloc(titre: str, lignes: list) -> str:
    return "\n".join([f"\n{titre}", "-" * len(titre)] + lignes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tendances et motifs")
    ap.add_argument("--rapport", nargs="?", const="diagnostic/analyse.txt",
                    default=None, metavar="FICHIER")
    # POUVOIR REFAIRE LE CALCUL SUR UNE SEULE SOURCE. Les cotes viennent de
    # quatre origines aux marges très différentes ; si un motif ne tient que
    # sur le mélange, il vient du mélange et pas du marché.
    ap.add_argument("--source", default=None,
                    help="pinnacle_cloture, winamax, footiqo_cloture…")
    args = ap.parse_args()

    matchs = charger(args.source)
    cotes = json.loads(COTES.read_text(encoding="utf-8"))
    sortie = []

    entete = f"{len(matchs)} matchs avec une issue connue et trois cotes"
    sortie.append(entete + (f", source {args.source} uniquement." if args.source else "."))

    lignes = ["cote            paris   gagnés   rendement"]
    for borne, n, taux, r, marge in par_tranche(matchs):
        hi = "∞" if borne[1] == float("inf") else f"{borne[1]:.1f}"
        lignes.append(f"  {borne[0]:>4.1f}–{hi:<5}  {n:>7}   {100*taux:>5.1f}%   "
                      f"{100*r:>6.1f} %  ±{100*marge:.1f}")
    sortie.append(_bloc("1. LE MARCHÉ : rendement d'une mise de 1 € par tranche de cote",
                        lignes))

    # Le même calcul source par source : une cote Winamax porte une marge bien
    # plus lourde qu'une cote Pinnacle de clôture, et mélanger les deux
    # ferait passer une différence de marge pour un biais de marché.
    lignes = []
    for source in ("pinnacle_cloture", "winamax", "footiqo_cloture"):
        sous = [m for m in matchs if m["source"] == source]
        if len(sous) < 500:
            continue
        petites = [(c, i == m["gagnant"]) for m in sous
                   for i, c in enumerate(m["odds"]) if c < 2.5]
        grosses = [(c, i == m["gagnant"]) for m in sous
                   for i, c in enumerate(m["odds"]) if c >= 4.5]
        rp, mp, np_ = rendement(petites)
        rg, mg, ng = rendement(grosses)
        lignes.append(f"  {source:<18} {len(sous):>6} matchs   "
                      f"favoris {100*rp:>5.1f}% ±{100*mp:.1f}   "
                      f"outsiders {100*rg:>5.1f}% ±{100*mg:.1f}")
    sortie.append(_bloc("2. LE MÊME ÉCART, SOURCE PAR SOURCE", lignes))

    lignes = []
    for famille in sorted({m["famille"] for m in matchs}):
        sous = [m for m in matchs if m["famille"] == famille]
        if len(sous) < 400:
            continue
        petites = [(c, i == m["gagnant"]) for m in sous
                   for i, c in enumerate(m["odds"]) if c < 2.5]
        grosses = [(c, i == m["gagnant"]) for m in sous
                   for i, c in enumerate(m["odds"]) if c >= 4.5]
        rp, mp, _ = rendement(petites)
        rg, mg, _ = rendement(grosses)
        domicile = sum(1 for m in sous if m["gagnant"] == 0) / len(sous)
        lignes.append(f"  {famille:<26} {len(sous):>6}   dom {100*domicile:>4.1f}%   "
                      f"favoris {100*rp:>5.1f}%   outsiders {100*rg:>5.1f}% ±{100*mg:.1f}")
    sortie.append(_bloc("3. PAR FAMILLE DE COMPÉTITION", lignes))

    grilles = public(cotes, args.source)
    if grilles:
        n = len(grilles)
        pub = sum(g["public"] for g in grilles) / n
        fav = sum(g["favori"] for g in grilles) / n
        pro = sum(g["probabiliste"] for g in grilles) / n
        taille = sum(g["matchs"] for g in grilles) / n
        joue = sum(g["joue"] for g in grilles)
        lignes = [
            f"  {n} grilles entièrement cotées et dont on connaît la",
            f"  répartition du public, soit {joue:,} grilles jouées.".replace(",", " "),
            "",
            f"  part des matchs correctement pronostiqués "
            f"(grilles de {taille:.1f} matchs en moyenne) :",
            f"      public réel            {100*pub:>5.1f} %",
            f"      suiveur de cotes       {100*fav:>5.1f} %",
            f"      probabiliste           {100*pro:>5.1f} %",
            f"      hasard (1 sur 3)        33.3 %",
            "",
            f"  le public fait {100*(fav - pub):.1f} points de moins que le suiveur de cotes,",
            f"  et {100*(pro - pub):.1f} points de moins que le probabiliste.",
        ]
        sortie.append(_bloc("4. LE PUBLIC, FACE AUX COTES", lignes))

        # L'écart tient-il dans le temps, ou n'est-ce qu'une année ?
        par_an = defaultdict(list)
        for g in grilles:
            par_an[g["annee"]].append(g)
        lignes = ["  année  grilles   public  suiveur    écart"]
        for an in sorted(par_an):
            gs = par_an[an]
            if len(gs) < 20:
                continue
            p = sum(x["public"] for x in gs) / len(gs)
            f = sum(x["favori"] for x in gs) / len(gs)
            lignes.append(f"   {an}   {len(gs):>6}   {100*p:>5.1f}%   {100*f:>5.1f}%   "
                          f"{100*(p-f):>+5.1f} pt")
        sortie.append(_bloc("5. LE MÊME ÉCART, ANNÉE PAR ANNÉE", lignes))

        # Le rendement de la stratégie évidente, mise de 1 € par grille.
        mises = [g for g in grilles if g["gain_favori"] is not None]
        gains = [g["gain_favori"] for g in mises]
        n = len(mises)
        moyen = sum(gains) / n
        gagnantes = sum(1 for x in gains if x > 0)
        # BOOTSTRAP PLUTÔT QUE L'INTERVALLE NORMAL. Les rapports sont très
        # asymétriques : une grille sur dix paie, et le gros du rendement vient
        # d'une poignée de rapports élevés. Sur une telle distribution,
        # l'approximation normale donne un intervalle faussement rassurant et
        # symétrique. On rééchantillonne à la place.
        tirage = random.Random(1789)
        moyennes = sorted(
            sum(tirage.choices(gains, k=n)) / n for _ in range(BOOTSTRAP))
        bas, haut = moyennes[int(0.025 * BOOTSTRAP)], moyennes[int(0.975 * BOOTSTRAP)]
        tries = sorted(gains, reverse=True)
        part_top = sum(tries[:max(1, n // 100)]) / sum(gains) if sum(gains) else 0
        lignes = [
            f"  {n} grilles jouées à 1 €, en cochant chaque fois le favori.",
            "",
            f"      rapportées               {gagnantes} fois ({100*gagnantes/n:.1f} %)",
            f"      rendement                {100*moyen:.1f} %",
            f"      intervalle à 95 %        {100*bas:.1f} à {100*haut:.1f} % "
            f"(bootstrap, {BOOTSTRAP} tirages)",
            f"      plus gros rapport        {tries[0]:.2f} €",
            f"      part du 1 % des grilles  {100*part_top:.0f} % du rendement total",
            "",
            "  Repère : le pari mutuel redistribue 75 % des mises, donc le",
            "  joueur moyen touche 75 %. Au-dessus, la stratégie bat la foule ;",
            "  au-dessus de 100 %, elle gagne de l'argent.",
        ]
        lignes.append("")
        lignes.append("  par type de grille :")
        for t in ("grille7", "grille9", "grille12"):
            sous = [g["gain_favori"] for g in mises if g["type"] == t]
            if len(sous) < 30:
                continue
            paye = sum(1 for x in sous if x > 0)
            lignes.append(f"      {t:<9} {len(sous):>5} grilles   "
                          f"{100*sum(sous)/len(sous):>6.1f} %   "
                          f"payées {100*paye/len(sous):.1f} %")
        sortie.append(_bloc("6. CE QUE LA GRILLE DES FAVORIS AURAIT RAPPORTÉ", lignes))

    texte = "\n".join(sortie)
    print(texte)
    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(texte + "\n", encoding="utf-8")
        print(f"\nRapport : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
