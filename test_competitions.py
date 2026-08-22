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


def test_le_genre_tient_en_quatre_cases():
    """Neuf genres dont deux avalaient les deux tiers n'aidaient personne.

    « multi-compétition » prenait 39 % des grilles dès qu'elles mélangeaient
    deux familles — même deux familles de championnat — et le reste se
    saupoudrait : deux grilles en Copa Libertadores, cinq en « autre
    championnat européen ».
    """
    assert categoriser(Counter({"top 5": 7}), 7) == "top 5"
    assert categoriser(Counter({"coupe d'Europe": 7}), 7) == "coupes"
    assert categoriser(Counter({"Coupe du monde": 7}), 7) == "coupes"
    assert categoriser(Counter({"deuxième division": 7}), 7) == "autres championnats"
    assert categoriser(Counter({"autre championnat": 7}), 7) == "autres championnats"


def test_une_seule_coupe_suffit_a_classer_la_grille_en_coupe():
    """C'est le choix contraire de la version précédente, où le mélange
    effaçait tout : une Ligue des champions au milieu de six matchs de
    championnat se cherche par la coupe, jamais par le championnat."""
    assert categoriser(Counter({"top 5": 6, "coupe d'Europe": 1}), 7) == "coupes"


def test_un_melange_de_championnats_reste_du_championnat():
    """Six matchs de Ligue 1 et un de Ligue 2, ce sont sept matchs de
    championnat. Les ranger sous « multi-compétition » les rendait
    introuvables sans rien apprendre à personne.

    Le « top 5 » reste exigeant, en revanche : il dit de bout en bout.
    """
    assert categoriser(Counter({"top 5": 6, "deuxième division": 1}), 7) == \
        "autres championnats"
    assert categoriser(Counter({"top 5": 6, "autre championnat européen": 1}), 7) == \
        "autres championnats"


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
