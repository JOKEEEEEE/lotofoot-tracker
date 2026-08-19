"""Tests de la datation : normalisation, chronologie, interpolation.

Aucun réseau, aucun fichier : des ancres fabriquées à la main, choisies pour
reproduire les pièges rencontrés sur les vraies données.

    python test_dates.py        (ou : pytest test_dates.py)
"""

from datetime import date

from dater_grilles import (_plier, ancrer_en_deux_temps, filtrer_chronologie,
                           interpoler)


def test_plier():
    # « Paris SG » chez Winamax, « Paris SG » chez football-data, et toutes
    # les variantes d'accent et de ponctuation doivent se rejoindre.
    assert _plier("Saint-Étienne") == _plier("saint etienne") == "saintetienne"
    assert _plier("Paris SG") == _plier("PARIS-SG") == "parissg"
    assert _plier("Bayer Leverkusen") == "bayerleverkusen"
    assert _plier(None) == "" and _plier("  ") == ""
    # Deux clubs différents ne doivent pas fusionner.
    assert _plier("Milan") != _plier("Inter Milan")


def test_filtrer_chronologie_garde_le_plus_grand_ensemble_sain():
    """Une ancre fausse ne doit pas en emporter de bonnes avec elle.

    Écarter toute ancre en désaccord avec la précédente supprimerait la bonne
    une fois sur deux. On cherche la plus longue sous-suite croissante.
    """
    ancres = {
        10: (date(2020, 1, 1), 3),
        20: (date(2020, 1, 5), 3),
        30: (date(2015, 6, 1), 3),      # intruse : cinq ans trop tôt
        40: (date(2020, 1, 9), 3),
        50: (date(2020, 1, 12), 3),
    }
    gardees, rejetees = filtrer_chronologie(ancres)
    assert rejetees == [30], rejetees
    assert sorted(gardees) == [10, 20, 40, 50], sorted(gardees)


def test_filtrer_chronologie_cas_vide():
    assert filtrer_chronologie({}) == ({}, [])


def test_interpolation_encadre_et_dit_son_incertitude():
    ancres = {10: (date(2020, 1, 1), 3), 20: (date(2020, 1, 11), 3)}
    res = interpoler(ancres, [10, 15, 20])

    assert res[10]["source"] == "affiches"
    assert res[10]["date"] == res[10]["date_min"] == "2020-01-01"

    milieu = res[15]
    assert milieu["source"] == "interpolation"
    assert milieu["date"] == "2020-01-06"                 # à mi-chemin
    assert (milieu["date_min"], milieu["date_max"]) == ("2020-01-01", "2020-01-11")
    # L'incertitude voyage avec la date : une estimation à dix jours près et
    # une date confirmée ne doivent pas se ressembler dans le JSON.
    assert milieu["incertitude_jours"] == 10


def test_hors_ancrage_ne_produit_pas_de_date():
    """Au-delà des ancres, on donne la borne connue et rien de plus.

    Extrapoler reviendrait à déduire la date du numéro de grille — méthode
    testée et réfutée : entre deux points d'ancrage réels on compte 2 322
    numéros pour 2 078 jours, et l'erreur atteint huit mois.
    """
    ancres = {10: (date(2020, 1, 1), 3), 20: (date(2020, 1, 11), 3)}
    res = interpoler(ancres, [5, 25])
    assert res[5]["date"] is None and res[5]["source"] == "hors_ancrage"
    assert res[5]["date_max"] == "2020-01-01" and res[5]["date_min"] is None
    assert res[25]["date"] is None
    assert res[25]["date_min"] == "2020-01-11" and res[25]["date_max"] is None


def _grille(gid, affiches):
    return (gid, [{"home": h, "away": a} for h, a in affiches])


def test_appoint_admis_seulement_dans_l_intervalle_du_squelette():
    """Deux affiches ne suffisent que si le squelette est d'accord.

    Mesuré sur les 4 030 grilles : à trois affiches concordantes, 0,7 % des
    ancres sont chronologiquement incohérentes ; à deux, 4,8 %. Le squelette
    sert de filtre — les candidates hors de l'intervalle permis sont écartées
    avant de pouvoir polluer l'interpolation voisine.
    """
    fixtures = {
        # Squelette : trois affiches concordantes sur les grilles 10 et 30.
        ("a", "b"): [date(2020, 1, 1)], ("c", "d"): [date(2020, 1, 1)],
        ("e", "f"): [date(2020, 1, 1)],
        ("g", "h"): [date(2020, 2, 1)], ("i", "j"): [date(2020, 2, 1)],
        ("k", "l"): [date(2020, 2, 1)],
        # Deux affiches plausibles pour la grille 20 : dans l'intervalle.
        ("m", "n"): [date(2020, 1, 15)], ("o", "p"): [date(2020, 1, 15)],
        # Deux affiches aberrantes pour la grille 25 : hors intervalle.
        ("q", "r"): [date(2010, 5, 5)], ("s", "t"): [date(2010, 5, 5)],
    }
    grilles = [_grille(10, [("a", "b"), ("c", "d"), ("e", "f")]),
               _grille(20, [("m", "n"), ("o", "p")]),
               _grille(25, [("q", "r"), ("s", "t")]),
               _grille(30, [("g", "h"), ("i", "j"), ("k", "l")])]

    ancres, rejetees, detail = ancrer_en_deux_temps(grilles, fixtures, {})
    assert detail["squelette"] == 2, detail
    assert detail["appoint_admis"] == 1, detail        # la 20
    assert detail["appoint_refuse"] == 1, detail       # la 25
    assert sorted(ancres) == [10, 20, 30], sorted(ancres)
    assert 25 not in ancres


def test_ancre_manuelle_prime_et_signale_son_desaccord():
    fixtures = {("a", "b"): [date(2020, 1, 1)], ("c", "d"): [date(2020, 1, 1)],
                ("e", "f"): [date(2020, 1, 1)]}
    grilles = [_grille(10, [("a", "b"), ("c", "d"), ("e", "f")])]
    manuelles = {10: (date(2021, 6, 6), "relevé à la main")}

    ancres, _, detail = ancrer_en_deux_temps(grilles, fixtures, manuelles)
    assert ancres[10][0] == date(2021, 6, 6), ancres
    # Un désaccord entre l'humain et les affiches se signale, il ne se tait pas.
    assert len(detail["desaccords"]) == 1, detail["desaccords"]
    gid, auto, main_, _motif = detail["desaccords"][0]
    assert (gid, auto, main_) == (10, date(2020, 1, 1), date(2021, 6, 6))


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except AssertionError as e:
            print(f"  ECHEC  {nom} : {str(e)[:200]}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
