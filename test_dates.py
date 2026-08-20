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


def test_alias_refuse_sans_confirmation_par_les_dates():
    """La ressemblance propose, la date dispose.

    « Milan » ressemble autant à « Milan AC » qu'à « Inter Milan ». Retenir le
    plus ressemblant reviendrait à inventer un alias une fois sur deux : seule
    la date de la rencontre tranche, et un candidat que les dates ne
    confirment pas est rejeté même s'il est le seul en lice.
    """
    from datetime import date as _d
    import apparier_equipes as ae

    noms_fd = {"milan": "Milan", "inter": "Inter"}
    fixtures = {("milan", "juventus"): [_d(2021, 5, 9)],
                ("inter", "juventus"): [_d(2019, 3, 3)]}
    grilles = [(10, [{"home": "Milan AC", "away": "juventus"}]),
               (11, [{"home": "Milan AC", "away": "juventus"}])]
    dates = {"10": {"date_min": "2021-05-08", "date_max": "2021-05-10"},
             "11": {"date_min": "2021-05-08", "date_max": "2021-05-10"}}

    alias, refuses = ae.apparier(grilles, fixtures, dates, noms_fd)
    assert "milanac" in alias, alias
    assert alias["milanac"]["nom_football_data"] == "Milan", alias
    assert alias["milanac"]["confirmations"] == 2, alias

    # Mêmes noms, mais des fenêtres de dates qui ne correspondent à rien :
    # aucun alias ne doit sortir.
    dates_fausses = {"10": {"date_min": "2010-01-01", "date_max": "2010-01-02"},
                     "11": {"date_min": "2010-01-01", "date_max": "2010-01-02"}}
    alias2, refuses2 = ae.apparier(grilles, fixtures, dates_fausses, noms_fd)
    assert alias2 == {}, alias2
    assert refuses2 and refuses2[0][0] == "Milan AC", refuses2


def test_alias_exige_deux_confirmations():
    """Une coïncidence isolée ne fait pas un alias."""
    from datetime import date as _d
    import apparier_equipes as ae

    noms_fd = {"barcelona": "Barcelona"}
    fixtures = {("barcelona", "getafe"): [_d(2021, 4, 22)]}
    grilles = [(10, [{"home": "FC Barcelone", "away": "getafe"}])]
    dates = {"10": {"date_min": "2021-04-21", "date_max": "2021-04-23"}}

    alias, refuses = ae.apparier(grilles, fixtures, dates, noms_fd)
    assert alias == {}, alias                      # une seule confirmation
    assert refuses[0][3] == 1, refuses             # elle est comptée, pas ignorée


def _rencontres(*lignes):
    """Un index football-data minuscule : (dom, ext) -> [{date, score}]."""
    index = {}
    for dom, ext, jour, score in lignes:
        index.setdefault((dom, ext), []).append(
            {"date": jour, "score": score, "cotes": {}, "division": "D1"})
    return index


def _m(home, away, jour, sh, sa):
    return {"home": home, "away": away, "debut": f"{jour.isoformat()}T18:30:00+00:00",
            "score_home": sh, "score_away": sa}


def test_date_exacte_nomme_sans_ressemblance():
    """« Mayence » et « Mainz » ne se ressemblent pas — la date les relie.

    C'est tout l'intérêt de cette seconde passe : la première ne propose que
    des candidats qui se ressemblent, et perd donc les traductions.
    """
    import apparier_equipes as ae
    j1, j2 = date(2015, 9, 13), date(2015, 10, 4)
    rencontres = _rencontres(("schalke04", "mainz", j1, (1, 2)),
                             ("schalke04", "mainz", j2, (3, 0)))
    grilles = [(1, [_m("Schalke 04", "Mayence", j1, 1, 2)]),
               (2, [_m("Schalke 04", "Mayence", j2, 3, 0)])]

    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias["mayence"]["vers"] == "mainz", alias
    assert alias["mayence"]["confirmations"] == 2, alias


def test_le_score_est_la_contre_epreuve():
    """Même jour, même équipe, mais pas le même score : on ne conclut pas.

    Sans ce contrôle, un match de coupe joué le jour d'un match de
    championnat suffirait à baptiser la mauvaise équipe.
    """
    import apparier_equipes as ae
    j1, j2 = date(2015, 9, 13), date(2015, 10, 4)
    rencontres = _rencontres(("schalke04", "mainz", j1, (1, 2)),
                             ("schalke04", "mainz", j2, (3, 0)))
    grilles = [(1, [_m("Schalke 04", "Mayence", j1, 0, 0)]),
               (2, [_m("Schalke 04", "Mayence", j2, 0, 0)])]

    alias, refuses = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias == {}, alias


def test_une_seule_confirmation_ne_suffit_pas():
    import apparier_equipes as ae
    j = date(2015, 9, 13)
    rencontres = _rencontres(("schalke04", "mainz", j, (1, 2)))
    grilles = [(1, [_m("Schalke 04", "Mayence", j, 1, 2)])]

    alias, refuses = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias == {}, alias
    assert refuses and refuses[0][0] == "Mayence", refuses


def test_deux_rencontres_le_meme_jour_ne_tranchent_pas():
    """Si l'index propose deux rencontres, c'est lui qui est ambigu."""
    import apparier_equipes as ae
    j = date(2015, 9, 13)
    rencontres = _rencontres(("schalke04", "mainz", j, (1, 2)),
                             ("schalke04", "koln", j, (1, 2)))
    grilles = [(1, [_m("Schalke 04", "Mayence", j, 1, 2)]),
               (2, [_m("Schalke 04", "Mayence", j, 1, 2)])]

    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias == {}, alias


def test_la_table_des_alias_debloque_les_deux_cotes():
    """Un alias connu en débloque d'autres.

    « Manchester United » n'est pas le nom de football-data ; sans la table,
    ce match a ses deux côtés inconnus et n'apprend rien.
    """
    import apparier_equipes as ae
    j1, j2 = date(2015, 9, 13), date(2015, 10, 4)
    rencontres = _rencontres(("manunited", "mainz", j1, (1, 2)),
                             ("manunited", "mainz", j2, (3, 0)))
    grilles = [(1, [_m("Manchester United", "Mayence", j1, 1, 2)]),
               (2, [_m("Manchester United", "Mayence", j2, 3, 0)])]

    assert ae.apparier_par_date_exacte(grilles, rencontres, table={})[0] == {}
    table = {"manchesterunited": "manunited"}
    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table=table)
    assert alias["mayence"]["vers"] == "mainz", alias


def test_deux_candidats_a_egalite_ne_departagent_pas():
    """Deux noms qui se disputent un alias à égalité sont un signe
    d'ambiguïté, pas un vainqueur. Il en faut trois fois plus, pas un de plus.
    """
    import apparier_equipes as ae
    jours = [date(2015, 9, 13 + i) for i in range(4)]
    # Schalke reçoit alternativement Mainz et Cologne ; la grille appelle les
    # deux « Mayence », ce qui ne peut pas être vrai des deux.
    rencontres = _rencontres(*[("schalke04", "mainz" if i % 2 else "koln",
                                jours[i], (1, 0)) for i in range(4)])
    grilles = [(i, [_m("Schalke 04", "Mayence", jours[i], 1, 0)]) for i in range(4)]
    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias == {}, alias

    # Deux contre une : c'est une majorité, ce n'est pas une preuve.
    rencontres = _rencontres(*[("schalke04", "mainz" if i < 2 else "koln",
                                jours[i], (1, 0)) for i in range(3)])
    trois = grilles[:3]
    alias, _ = ae.apparier_par_date_exacte(trois, rencontres, table={})
    assert alias == {}, alias

    # Trois contre une : l'écart suffit, et c'est exactement le seuil.
    rencontres = _rencontres(*[("schalke04", "mainz" if i else "koln",
                                jours[i], (1, 0)) for i in range(4)])
    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias["mayence"]["vers"] == "mainz", alias


def test_le_sens_de_laffiche_est_respecte():
    """Le domicile reste le domicile : une équipe qui reçoit ne peut pas être
    nommée par une rencontre où elle se déplace."""
    import apparier_equipes as ae
    j1, j2 = date(2015, 9, 13), date(2015, 10, 4)
    rencontres = _rencontres(("mainz", "schalke04", j1, (1, 2)),
                             ("mainz", "schalke04", j2, (3, 0)))
    grilles = [(1, [_m("Schalke 04", "Mayence", j1, 1, 2)]),
               (2, [_m("Schalke 04", "Mayence", j2, 3, 0)])]

    alias, _ = ae.apparier_par_date_exacte(grilles, rencontres, table={})
    assert alias == {}, alias


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
