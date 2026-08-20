"""Tests de l'analyse : les pièges qui font dire le contraire de la vérité.

Chaque test ci-dessous reproduit une erreur réellement commise sur ces
données, et qui produisait un résultat crédible mais faux.

    python test_analyse.py        (ou : pytest test_analyse.py)
"""

from analyser import (evaluer_grille, probabilites, rendement,
                      retention_combine)

COTES = {"1": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "x"},
         "2": {"cote_1": 3.0, "cote_N": 3.3, "cote_2": 2.5, "source": "x"}}


def _grille(n=2):
    return [{"match_id": i + 1} for i in range(n)]


def test_probabilites_somment_a_un():
    p = probabilites((1.5, 4.0, 7.0))
    assert abs(sum(p) - 1.0) < 1e-9
    assert p[0] > p[1] > p[2]


def test_rendement_ne_suppose_aucune_cote_moyenne():
    """Sur une tranche ouverte — les cotes au-delà de 12 — il n'y a pas de
    cote moyenne qui vaille. L'écart-type doit venir des gains observés."""
    r, marge, n = rendement([(1000.0, False)] * 99 + [(1000.0, True)])
    assert n == 100 and abs(r - 10.0) < 1e-9
    assert 0 < marge < 30, marge          # fini, et pas absurde

    r, marge, n = rendement([])
    assert (r, marge, n) == (0.0, 0.0, 0)

    # Une tranche où TOUT gagne n'a aucune incertitude : la marge doit être
    # nulle. Un écart-type calculé sur la cote plutôt que sur les gains
    # observés en inventerait une.
    r, marge, n = rendement([(2.0, True)] * 50)
    assert abs(r - 2.0) < 1e-9 and marge == 0.0, (r, marge)


def test_tout_est_ramene_a_une_fraction_des_matchs():
    """Le bug qui donnait un suiveur de cotes à 6,6 bons résultats sur 7.

    Mélanger des grilles de 7 et de 12 matchs en valeur absolue compare des
    choses incomparables. Ici, deux grilles où TOUT est deviné juste doivent
    donner 100 % l'une comme l'autre, quelle que soit leur taille.
    """
    cotes = {str(i): {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0} for i in range(1, 13)}
    for n in (2, 12):
        issues = [{"1"}] * n
        rep = [0] * n + [10]              # les 10 joueurs ont tout trouvé
        g = evaluer_grille(_grille(n), issues, rep, [], cotes)
        assert abs(g["favori"] - 1.0) < 1e-9, (n, g)
        assert abs(g["public"] - 1.0) < 1e-9, (n, g)


def test_le_public_se_lit_dans_repart():
    """repart[k] est le nombre de grilles jouées ayant k bons résultats."""
    issues = [{"1"}, {"1"}]
    rep = [1, 0, 1]                       # une grille à 0, une à 2
    g = evaluer_grille(_grille(), issues, rep, [], COTES)
    assert g["joue"] == 2
    assert abs(g["public"] - 0.5) < 1e-9, g   # 1 bon résultat sur 2 en moyenne


def test_le_gain_est_celui_du_rang_atteint():
    """Le suiveur de cotes touche le rapport de SON rang, pas le meilleur."""
    issues = [{"1"}, {"2"}]               # le favori gagne les deux
    rapports = [{"nbCorrectResults": 2, "winningsPerGrid": 50.0},
                {"nbCorrectResults": 1, "winningsPerGrid": 2.0}]
    g = evaluer_grille(_grille(), issues, rapports=rapports, rep=[0, 0, 1], cotes=COTES)
    assert g["favori_justes"] == 2 and g["gain_favori"] == 50.0

    # Un seul favori gagnant : rang 1, donc 2 €, pas 50.
    issues = [{"1"}, {"1"}]               # sur le match 2, le favori est le 2
    g = evaluer_grille(_grille(), issues, rapports=rapports, rep=[0, 0, 1], cotes=COTES)
    assert g["favori_justes"] == 1 and g["gain_favori"] == 2.0


def test_un_rang_non_paye_rapporte_zero():
    """Ne rien toucher n'est pas une donnée manquante : c'est zéro."""
    issues = [{"N"}, {"N"}]               # le favori se trompe partout
    rapports = [{"nbCorrectResults": 2, "winningsPerGrid": 50.0}]
    g = evaluer_grille(_grille(), issues, rapports=rapports, rep=[1, 0, 0], cotes=COTES)
    assert g["favori_justes"] == 0 and g["gain_favori"] == 0.0


def test_la_marge_du_combine_se_multiplie():
    """L'erreur naturelle : croire qu'un combiné à sept jambes coûte 12 %.

    Chaque jambe subit le prélèvement, et les prélèvements se composent. À
    12,3 % la jambe, il reste 0,877 puissance 7, soit 40 % — et non 88 %.
    """
    # Trois cotes égales à 3 / 1,140 : la surcote vaut exactement 1,140.
    jambe = (3 / 1.140,) * 3
    assert abs(sum(1 / o for o in jambe) - 1.140) < 1e-9
    une = retention_combine([jambe])
    sept = retention_combine([jambe] * 7)
    assert abs(une - 1 / 1.140) < 1e-6, une
    assert abs(sept - (1 / 1.140) ** 7) < 1e-9, sept
    assert 0.39 < sept < 0.41, sept          # 40 %, pas 88 %
    # Un marché sans marge rendrait tout, quel que soit le nombre de jambes.
    assert abs(retention_combine([(3.0, 3.0, 3.0)] * 7) - 1.0) < 1e-9


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
