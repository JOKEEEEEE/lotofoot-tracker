"""Retirer des grilles Pronosoft déjà collectées le pourcentage de joueurs.

POURQUOI. C'est la seule donnée de ces pages qui soit la PRODUCTION de
Pronosoft — l'agrégat des pronostics de leur communauté, qui n'existe que
parce qu'ils l'ont compilé — quand tout le reste est un fait public : un
score, une cote de marché, un rapport de la FDJ. Ne pas la garder est ce qui
permet de versionner data/pronosoft/ dans le dépôt comme le reste, au lieu de
le tenir à l'écart.

Le collecteur ne l'enregistre plus. Cet outil s'occupe des fichiers écrits
avant ce changement. Il est idempotent : un second passage ne trouve rien.

    python outils/retirer_public.py            # nettoie
    python outils/retirer_public.py --verifier # ne touche rien, dit ce qui reste
"""

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "data" / "pronosoft"

# Les clés à faire disparaître, où qu'elles soient. `public_connu` est le
# compte que la grille portait ; il ne survit pas à ce qu'il comptait.
CLES_GRILLE = ("public_connu",)
CLES_MATCH = ("public",)


def nettoyer(grille: dict) -> int:
    """Ôte les pourcentages d'une grille. Rend le nombre de champs retirés."""
    otes = 0
    for cle in CLES_GRILLE:
        otes += grille.pop(cle, None) is not None
    for match in grille.get("matchs", []):
        for cle in CLES_MATCH:
            if cle in match:
                del match[cle]
                otes += 1
    return otes


def restants(grille: dict) -> int:
    """Combien de champs de pourcentage cette grille porte encore."""
    return (sum(1 for c in CLES_GRILLE if c in grille)
            + sum(1 for m in grille.get("matchs", []) for c in CLES_MATCH if c in m))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verifier", action="store_true",
                    help="ne rien modifier, seulement compter ce qui reste")
    args = ap.parse_args()

    if not DOSSIER.exists():
        print(f"{DOSSIER} n'existe pas — rien à faire.")
        return 0

    fichiers = sorted(DOSSIER.glob("*/*.json"))
    touches = champs = porteurs = 0
    for chemin in fichiers:
        try:
            grille = json.loads(chemin.read_text(encoding="utf-8"))
        except ValueError:
            print(f"  illisible, laissé tel quel : {chemin}")
            continue
        if args.verifier:
            reste = restants(grille)
            if reste:
                porteurs += 1
                champs += reste
            continue
        otes = nettoyer(grille)
        if otes:
            chemin.write_text(json.dumps(grille, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            touches += 1
            champs += otes

    if args.verifier:
        if porteurs:
            print(f"{porteurs} grille(s) sur {len(fichiers)} portent encore "
                  f"{champs} champ(s) de pourcentage.")
            return 1
        print(f"{len(fichiers)} grille(s) vérifiée(s) : aucun pourcentage.")
        return 0
    print(f"{len(fichiers)} grille(s) lue(s), {touches} nettoyée(s), "
          f"{champs} champ(s) retiré(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
