"""Audit de la base collectée : cohérence interne, trous, doublons.

À trois grilles on relit les fichiers à l'œil. À cinq cents, non — et c'est
précisément là qu'une erreur d'extraction devient invisible : elle ne se
signale pas, elle se fond. Ce script pose sur toute la base les questions
qu'on posait à la main sur les premières grilles.

    python verifier_base.py                 # tous les types
    python verifier_base.py --type grille7

Il ne touche à rien et ne va sur aucun réseau : il lit les JSON, c'est tout.
Code de sortie 1 s'il trouve quelque chose à regarder, 0 sinon — de quoi
l'enchaîner après une collecte.

CE QU'IL NE PEUT PAS FAIRE : dire si les données correspondent au site. Un
fichier peut être parfaitement cohérent et faux, si le scraper a lu la
mauvaise colonne partout. Seule une comparaison à l'écran répond à ça, et
elle reste à faire sur un échantillon.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "grilles"

# Au-delà de cette longueur, une série d'identifiants manquants n'est plus un
# trou dans une zone collectée mais une plage qu'on n'a pas encore demandée.
SEUIL_TROU = 20

# CE QUI EST TRONQUÉ À L'ÉCRAN NE L'EST PAS DANS LE RAPPORT. Un terminal qui
# déroule quatre mille lignes ne se lit pas ; un fichier, si. L'écran donne la
# forme du problème, le fichier permet de le traiter.
ECRAN_ANOMALIES = 40
ECRAN_TROUS = 20

# L'ARRONDI SE FAIT PAR GAGNANT, PAS SUR LE TOTAL — et c'est toute la
# différence. Winamax divise la part d'un rang par le nombre de gagnants puis
# arrondit au centime : chaque gagnant emporte jusqu'à un demi-centime de trop
# ou de trop peu, et l'écart final se multiplie par leur nombre.
#
# Mesuré sur la grille 3833 : part exacte 2,1730 € affichée 2,17 €, soit trois
# millièmes × 2 065 gagnants = 6,20 € sur ce seul rang, 14,69 € sur la grille.
#
# Un seuil fixe se trompait donc exactement là où il ne faut pas : il laissait
# passer une vraie erreur sur une grille à peu de gagnants, et hurlait sur les
# grosses grilles parfaitement saines. Sur les 507 premières grilles, un seuil
# à 2 € produisait 73 fausses alertes et zéro vraie.
DEMI_CENTIME = 0.005
MARGE_FLOTTANTS = 0.02


def _plafond_arrondi(nombre_gagnants: int) -> float:
    return DEMI_CENTIME * nombre_gagnants + MARGE_FLOTTANTS


def _anomalie(liste, gid, quoi, detail=""):
    liste.append((gid, quoi, detail))


def _dire(rapport, texte="", ecran=True):
    """Une ligne : toujours dans le rapport, à l'écran seulement si demandé."""
    rapport.append(texte)
    if ecran:
        print(texte)


def verifier_grille(d: dict, anomalies: list):
    gid = d.get("grille_id", "?")

    for champ in ("grille_id", "grille_type", "statut", "matches", "rapports"):
        if champ not in d:
            _anomalie(anomalies, gid, f"champ « {champ} » absent")
            return

    if d["statut"] == "annulee":
        # Une grille annulée a des listes vides par construction : la
        # contrôler comme les autres produirait du bruit, pas du signal.
        if d["matches"] or d["rapports"]:
            _anomalie(anomalies, gid, "annulée mais listes non vides")
        return

    for i, m in enumerate(d["matches"]):
        if not m.get("home", "").strip() or not m.get("away", "").strip():
            _anomalie(anomalies, gid, f"match {i} sans nom d'équipe", str(m)[:70])
            continue

        if m.get("resultat") == "annule":
            # Aucun score ne doit avoir été inventé sur un match annulé.
            if m.get("score_home") is not None or m.get("score_away") is not None:
                _anomalie(anomalies, gid, f"match {i} annulé mais avec un score", str(m)[:70])
            if m.get("tous_gagnants") is not True:
                _anomalie(anomalies, gid, f"match {i} annulé sans tous_gagnants", str(m)[:70])
            continue

        dom, ext = m.get("score_home"), m.get("score_away")
        if dom is None or ext is None:
            _anomalie(anomalies, gid, f"match {i} sans score et non annulé", str(m)[:70])
            continue
        attendu = "1" if dom > ext else "2" if ext > dom else "N"
        if m.get("resultat") != attendu:
            _anomalie(anomalies, gid, f"match {i} : résultat {m.get('resultat')} "
                                      f"pour un score {dom}-{ext}")

    md = d.get("montant_distribue")
    if not d["rapports"] or md is None:
        # UNE GRILLE TERMINÉE SANS RAPPORTS EST SUSPECTE. C'est la forme que
        # prend une grille non réglée enregistrée par erreur : des matchs, un
        # statut « terminée », et rien à distribuer. Le contrôle de somme la
        # laissait passer sans un mot, faute d'avoir quoi que ce soit à
        # comparer — c'est précisément pour ça qu'il faut le dire.
        _anomalie(anomalies, gid, "terminée mais sans rapports ni montant",
                  f"{len(d['rapports'])} rapport(s), montant {md}")
        return

    somme, gagnants = 0.0, 0
    for r in d["rapports"]:
        n, montant = r.get("nombre_gagnants"), r.get("montant")
        if n is None or montant is None:
            _anomalie(anomalies, gid, f"rapport incomplet au rang {r.get('rang')}")
            continue
        somme += n * montant
        gagnants += n
    plafond = _plafond_arrondi(gagnants)
    if abs(somme - md) > plafond:
        _anomalie(anomalies, gid, "somme des rapports ≠ montant distribué",
                  f"{somme:.2f} contre {md:.2f}, écart {abs(somme - md):.2f} "
                  f"pour un plafond d'arrondi de {plafond:.2f} ({gagnants} gagnants)")


def verifier_type(grille_type: str, rapport: list) -> int:
    dossier = DATA_DIR / grille_type
    fichiers = sorted(dossier.glob("*.json"), key=lambda f: int(f.stem))
    if not fichiers:
        _dire(rapport, f"  {grille_type} : aucun fichier")
        return 0

    anomalies, statuts, signatures = [], Counter(), {}
    ids, matchs_total, annules, ignorees, mentions = [], 0, 0, 0, 0
    a_relire = {"lignes écartées": [], "mention d'annulation": []}

    for f in fichiers:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            _anomalie(anomalies, f.stem, "fichier illisible", str(e)[:60])
            continue

        ids.append(d.get("grille_id"))
        statuts[d.get("statut", "?")] += 1
        matchs_total += len(d.get("matches", []))
        annules += sum(1 for m in d.get("matches", []) if m.get("resultat") == "annule")
        if d.get("lignes_ignorees"):
            ignorees += len(d["lignes_ignorees"])
            a_relire["lignes écartées"].append(d.get("grille_id"))
        if "mention_annulation" in d:
            mentions += 1
            a_relire["mention d'annulation"].append(d.get("grille_id"))
        verifier_grille(d, anomalies)

        # DEUX GRILLES NE PARTAGENT PAS LEURS MATCHS. Si c'est le cas, le site
        # a servi la même page deux fois — l'échec qui ne ressemble pas à un
        # échec, et que le lot ne détecte que sur des répétitions consécutives.
        if d.get("matches"):
            cle = json.dumps(d["matches"], sort_keys=True, ensure_ascii=False)
            if cle in signatures:
                _anomalie(anomalies, d.get("grille_id"), "matchs identiques à une autre grille",
                          f"déjà vus sur {signatures[cle]}")
            else:
                signatures[cle] = d.get("grille_id")

    _dire(rapport, f"\n=== {grille_type} : {len(fichiers)} fichier(s) ===")
    _dire(rapport, f"  identifiants   : {min(ids)} à {max(ids)}")
    _dire(rapport, f"  statuts        : "
                   f"{', '.join(f'{k} {v}' for k, v in statuts.most_common())}")
    _dire(rapport, f"  matchs         : {matchs_total}  (dont {annules} annulé(s))")
    if ignorees:
        _dire(rapport, f"  lignes écartées: {ignorees}  <-- à relire, "
                       f"le scraper n'a pas su lire")
    if mentions:
        _dire(rapport, f"  mentions d'annulation inexpliquées : {mentions}  <-- à relire")

    # DEUX SORTES DE MANQUES, ET LES CONFONDRE REND LE RAPPORT INUTILE.
    #
    # Après le premier lot, la base contenait dix sondages épars — jusqu'à
    # l'identifiant 1 — et cinq cents grilles contiguës. Compter naïvement les
    # absents entre le minimum et le maximum donnait « 3 663 absents », un
    # chiffre qui ne dit rien : il mélange les milliers d'identifiants jamais
    # demandés avec les trois que le scraper n'a pas su collecter. Or ce sont
    # ces trois-là, et eux seuls, qui méritent un coup d'œil.
    #
    # On distingue donc par la longueur de la série manquante : quelques
    # identifiants isolés au milieu du collecté sont des trous, une plage de
    # centaines est une zone qu'on n'a pas encore explorée.
    manquants = sorted(set(range(min(ids), max(ids) + 1)) - set(ids))
    series, trous, non_explore = [], [], 0
    for m in manquants:
        if series and m == series[-1][-1] + 1:
            series[-1].append(m)
        else:
            series.append([m])
    for serie in series:
        if len(serie) <= SEUIL_TROU:
            trous.extend(serie)
        else:
            non_explore += len(serie)
    if trous:
        apercu = ", ".join(str(m) for m in trous[:ECRAN_TROUS])
        suite = f" … (+{len(trous) - ECRAN_TROUS})" if len(trous) > ECRAN_TROUS else ""
        _dire(rapport, f"  trous          : {len(trous)} identifiant(s) dans une zone "
                       f"collectée — {apercu}{suite}", ecran=False)
        print(f"  trous          : {len(trous)} identifiant(s) dans une zone collectée "
              f"— {apercu}{suite}")
        rapport.append("  liste complète des trous :")
        rapport.append("    " + ", ".join(str(m) for m in trous))
    if non_explore:
        _dire(rapport, f"  non exploré    : {non_explore} identifiant(s) en plages "
                       f"jamais demandées")

    # DE QUOI AGIR, PAS SEULEMENT CONSTATER. Un audit qui liste des problèmes
    # sans dire par quelle commande les reprendre laisse le travail à moitié
    # fait — et sur quatre mille grilles, recopier des identifiants à la main
    # est exactement le genre de tâche où l'on en oublie un.
    reprises = {motif: sorted(gids) for motif, gids in a_relire.items() if gids}
    if trous:
        reprises["trous"] = trous
    if reprises:
        rapport.append("\n  À REPRENDRE, commandes prêtes à coller :")
        for motif, gids in reprises.items():
            drapeau = "--refaire " if motif != "trous" else ""
            rapport.append(f"    # {len(gids)} grille(s) — {motif}")
            rapport.append(f"    python scrape_grille.py --type {grille_type} "
                           f"{drapeau}--ids {','.join(str(g) for g in gids)}")
        print(f"\n  À reprendre : "
              + ", ".join(f"{len(g)} {motif}" for motif, g in reprises.items())
              + " — commandes dans le rapport")

    if anomalies:
        _dire(rapport, f"\n  {len(anomalies)} ANOMALIE(S) :")
        for rang, (gid, quoi, detail) in enumerate(anomalies):
            ligne = f"    [{gid}] {quoi}" + (f" — {detail}" if detail else "")
            _dire(rapport, ligne, ecran=rang < ECRAN_ANOMALIES)
        if len(anomalies) > ECRAN_ANOMALIES:
            print(f"    … et {len(anomalies) - ECRAN_ANOMALIES} autre(s) "
                  f"— tout est dans le rapport, voir --rapport")
    else:
        _dire(rapport, "  aucune anomalie")
    return len(anomalies)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit des grilles collectées")
    ap.add_argument("--type", choices=["grille7", "grille9", "grille12"],
                    help="n'auditer qu'un type (défaut : tous)")
    ap.add_argument("--rapport", nargs="?", const="diagnostic/audit.txt", default=None,
                    metavar="FICHIER",
                    help="écrire le rapport complet, sans troncature "
                         "(défaut : diagnostic/audit.txt)")
    args = ap.parse_args()

    types = [args.type] if args.type else sorted(
        d.name for d in DATA_DIR.iterdir() if d.is_dir()) if DATA_DIR.exists() else []
    if not types:
        print("Aucune donnée dans data/grilles.")
        return 0

    rapport = []
    total = sum(verifier_type(t, rapport) for t in types)
    _dire(rapport, f"\nTotal : {total} anomalie(s).")

    if args.rapport:
        chemin = Path(args.rapport)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("\n".join(rapport) + "\n", encoding="utf-8")
        print(f"Rapport complet : {chemin}  ({len(rapport)} ligne(s))")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
