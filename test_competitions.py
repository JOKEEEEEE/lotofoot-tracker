"""Tests de la catégorisation : ce qui nomme une grille, et ce qui la laisse
sans nom.

    python test_competitions.py        (ou : pytest test_competitions.py)
"""

from collections import Counter

from categoriser_grilles import COUVERTURE_MINI, categoriser, famille, lisible


def test_les_familles_regroupent_les_codes():
    assert famille("F1") == famille("E0") == famille("I1") == "top 5"
    assert famille("Champions League") == "coupe d'Europe"
    assert famille("Europa League") == famille("Conference League") == "coupe d'Europe"
    assert famille("E1") == "deuxième division"
    assert famille("N1") == "autre championnat européen"
    assert famille("World Cup - Final phase") == "Coupe du monde"
    # Un championnat qu'on ne classe pas reste un championnat, pas un trou.
    assert famille("Brazil · Serie A") == "autre championnat"
    assert famille(None) is None and famille("") is None


def test_le_bresil_ne_devient_pas_l_italie():
    """« Serie A » désigne le Brésil chez football-data et l'Italie ailleurs.

    Sans le pays en préfixe, les deux championnats fusionneraient sous une
    même étiquette et une grille brésilienne passerait pour une grille du
    top 5.
    """
    assert famille("I1") == "top 5"
    assert famille("Brazil · Serie A") == "autre championnat"
    assert lisible("I1") == "Serie A" and lisible("Brazil · Serie A") == "Brazil · Serie A"


def test_une_seule_famille_nomme_la_grille():
    assert categoriser(Counter({"top 5": 7}), 7) == "top 5"
    assert categoriser(Counter({"coupe d'Europe": 7}), 7) == "coupe d'Europe"


def test_un_seul_intrus_suffit_a_faire_une_grille_multi():
    """Six matchs de Ligue 1 et un de Bundesliga font une grille mélangée.

    Prendre la majorité effacerait exactement ce qu'on veut mesurer : une
    grille panachée ne se parie pas comme une journée de championnat.
    """
    assert categoriser(Counter({"top 5": 6, "deuxième division": 1}), 7) == \
        "multi-compétition"


def test_trop_peu_de_matchs_nommes_ne_qualifie_rien():
    """Deux matchs sur sept ne disent pas de quoi la grille est faite."""
    assert categoriser(Counter({"top 5": 2}), 7) == "indéterminée"
    assert categoriser(Counter(), 7) == "indéterminée"
    # Le seuil est une proportion, pas un nombre : il doit tenir sur une
    # grille de 12 matchs comme sur une grille de 7.
    juste_assez = round(COUVERTURE_MINI * 12 + 0.5)
    assert categoriser(Counter({"top 5": juste_assez}), 12) == "top 5"
    assert categoriser(Counter({"top 5": juste_assez - 2}), 12) == "indéterminée"


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except Exception as e:
            print(f"  ECHEC  {nom} : {type(e).__name__} {str(e)[:200]}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
