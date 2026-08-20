"""Tests du banc d'essai : l'arithmétique d'une combinaison multiple.

    python test_strategies.py        (ou : pytest test_strategies.py)
"""

import strategies as S

# Une grille fabriquée : sept matchs, des favoris de netteté décroissante.
def _grille(vrai=None, rangs=None):
    p = []
    for k in range(7):
        fort = 0.85 - 0.07 * k                   # de 0,85 à 0,43
        reste = (1 - fort) / 2
        p.append([fort, reste, reste])
    return {"id": 1, "fin": "2026-01-01", "p": p,
            "odds": [(1 / x[0], 1 / x[1], 1 / x[2]) for x in p],
            "vrai": vrai if vrai is not None else [0] * 7,
            "rangs": rangs if rangs is not None else {7: 100.0, 6: 5.0},
            "gagnants": {7: 10, 6: 200}}


def test_le_favori_est_lissue_la_plus_probable():
    assert S.favori(_grille()) == [0] * 7


def test_les_plus_nets_viennent_en_tete():
    """L'ordre compte : c'est sur le favori le plus net que le public se
    concentre le plus, donc c'est là que s'en écarter paie le mieux."""
    assert S.plus_nets(_grille(), 3) == [0, 1, 2]
    assert S.plus_nets(_grille(), 1) == [0]


def test_doubler_k_matchs_coute_deux_puissance_k():
    g = _grille()
    for k in (1, 2, 3):
        jeux = S.doubler(k)(g)
        assert len(jeux) == 2 ** k, (k, len(jeux))
        assert len({tuple(c) for c in jeux}) == 2 ** k, "combinaisons en double"
        assert all(len(c) == 7 for c in jeux)


def test_le_double_vaut_la_moyenne_des_deux_simples():
    """L'identité qui explique tout : couvrir deux issues, c'est jouer les
    deux grilles simples correspondantes. Le rendement par euro est donc
    exactement leur moyenne — un double ne crée pas de valeur, il étale."""
    grilles = [_grille(vrai=v) for v in ([0]*7, [1]+[0]*6, [2]+[0]*6, [1,1]+[0]*5)]
    simple = S.rendements(S.tout_favori, grilles)
    casse = S.rendements(S.casser(1), grilles)
    double = S.rendements(S.doubler(1), grilles)
    for a, b, d in zip(simple, casse, double):
        assert abs(d - (a + b) / 2) < 1e-9, (a, b, d)


def test_le_gain_lit_le_rang_atteint():
    g = _grille(vrai=[0] * 7)
    assert S.gain(g, [0] * 7) == 100.0            # 7 bons
    assert S.gain(g, [1] + [0] * 6) == 5.0        # 6 bons
    assert S.gain(g, [1, 1] + [0] * 5) == 0.0     # 5 bons, rang non payé


def test_casser_prend_le_second_pas_loutsider():
    """Le second favori, pas l'issue la moins probable : on cherche à
    s'écarter du public, pas à jouer l'improbable."""
    g = _grille()
    g["p"][0] = [0.85, 0.10, 0.05]
    assert S.casser(1)(g)[0][0] == 1              # le N, deuxième issue


def test_sans_la_tete_retire_bien_les_meilleures():
    """Le garde-fou anti-loterie : si retirer trois grilles fait tout
    tomber, le rendement moyen ne décrivait qu'elles."""
    valeurs = [0.0] * 97 + [100.0, 200.0, 300.0]
    assert abs(sum(valeurs) / len(valeurs) - 6.0) < 1e-9
    assert S.sans_la_tete(valeurs, 3) == 0.0
    assert abs(S.sans_la_tete(valeurs, 1) - 3.0) < 1e-9


def test_intervalle_encadre_la_moyenne():
    valeurs = [1.0] * 50 + [0.0] * 50
    bas, haut = S.intervalle(valeurs)
    assert bas < 0.5 < haut, (bas, haut)
    # Une distribution sans dispersion n'a pas d'incertitude.
    assert S.intervalle([2.0] * 100) == (2.0, 2.0)


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
