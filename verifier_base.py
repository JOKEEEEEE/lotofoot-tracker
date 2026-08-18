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

# La somme des rapports doit retomber sur le montant distribué. L'écart tient
# aux arrondis au centime sur chaque gagnant : quelques dizaines de centimes
# sur des milliers d'euros. Au-delà, ce n'est plus de l'arrondi.
TOLERANCE_EUROS = 2.0


def _anomalie(liste, gid, quoi, detail=""):
    liste.append((gid, quoi, detail))


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
    if d["rapports"] and md:
        somme = 0.0
        for r in d["rapports"]:
            n, montant = r.get("nombre_gagnants"), r.get("montant")
            if n is None or montant is None:
                _anomalie(anomalies, gid, f"rapport incomplet au rang {r.get('rang')}")
                continue
            somme += n * montant
        if abs(somme - md) > TOLERANCE_EUROS:
            _anomalie(anomalies, gid, "somme des rapports ≠ montant distribué",
                      f"{somme:.2f} contre {md:.2f}")


def verifier_type(grille_type: str) -> int:
    dossier = DATA_DIR / grille_type
    fichiers = sorted(dossier.glob("*.json"), key=lambda f: int(f.stem))
    if not fichiers:
        print(f"  {grille_type} : aucun fichier")
        return 0

    anomalies, statuts, signatures = [], Counter(), {}
    ids, matchs_total, annules, ignorees, mentions = [], 0, 0, 0, 0

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
        ignorees += len(d.get("lignes_ignorees", []))
        mentions += 1 if "mention_annulation" in d else 0
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

    print(f"\n=== {grille_type} : {len(fichiers)} fichier(s) ===")
    print(f"  identifiants   : {min(ids)} à {max(ids)}")
    print(f"  statuts        : {', '.join(f'{k} {v}' for k, v in statuts.most_common())}")
    print(f"  matchs         : {matchs_total}  (dont {annules} annulé(s))")
    if ignorees:
        print(f"  lignes écartées: {ignorees}  <-- à relire, le scraper n'a pas su lire")
    if mentions:
        print(f"  mentions d'annulation inexpliquées : {mentions}  <-- à relire")

    # Les trous sont attendus — tous les identifiants n'existent pas — mais on
    # les compte pour que « il manque des grilles » ne soit jamais une surprise.
    manquants = sorted(set(range(min(ids), max(ids) + 1)) - set(ids))
    if manquants:
        apercu = ", ".join(str(m) for m in manquants[:12])
        suite = f" … (+{len(manquants) - 12})" if len(manquants) > 12 else ""
        print(f"  absents        : {len(manquants)} identifiant(s) — {apercu}{suite}")

    if anomalies:
        print(f"\n  {len(anomalies)} ANOMALIE(S) :")
        for gid, quoi, detail in anomalies[:40]:
            print(f"    [{gid}] {quoi}" + (f" — {detail}" if detail else ""))
        if len(anomalies) > 40:
            print(f"    … et {len(anomalies) - 40} autre(s)")
    else:
        print("  aucune anomalie")
    return len(anomalies)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit des grilles collectées")
    ap.add_argument("--type", choices=["grille7", "grille9", "grille12"],
                    help="n'auditer qu'un type (défaut : tous)")
    args = ap.parse_args()

    types = [args.type] if args.type else sorted(
        d.name for d in DATA_DIR.iterdir() if d.is_dir()) if DATA_DIR.exists() else []
    if not types:
        print("Aucune donnée dans data/grilles.")
        return 0

    total = sum(verifier_type(t) for t in types)
    print(f"\nTotal : {total} anomalie(s).")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
