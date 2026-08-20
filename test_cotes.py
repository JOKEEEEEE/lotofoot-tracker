"""Tests de la jointure des cotes : ce qui est refusé, et pourquoi.

Un joiner ne se juge pas au nombre de matchs qu'il rapproche mais au nombre
de faux rapprochements qu'il refuse. Chaque test ci-dessous fabrique une
situation où un joiner naïf se tromperait.

    python test_cotes.py        (ou : pytest test_cotes.py)
"""

import tempfile
from datetime import date, timedelta
from pathlib import Path

import dater_grilles as dg
import joindre_cotes as jc
from joindre_cotes import PINNACLE_FIABLE_JUSQUA, choisir_cote, rapprocher


def _index(*rencontres):
    """Un index football-data minuscule, clé pliée comme dans le vrai."""
    index = {}
    for dom, ext, jour, score, cotes in rencontres:
        index.setdefault((dg._cle(dom), dg._cle(ext)), []).append(
            {"date": jour, "score": score, "cotes": cotes, "division": "F1"})
    return index


def _match(**kw):
    base = {"home": "Lyon", "away": "Nantes", "debut": "2023-04-15T19:00:00",
            "score_home": 2, "score_away": 1}
    base.update(kw)
    return base


COTES = {"pinnacle_cloture": (1.8, 3.5, 4.2)}


def test_rapprochement_nominal():
    index = _index(("Lyon", "Nantes", date(2023, 4, 15), (2, 1), COTES))
    trouvee, motif = rapprocher(_match(), index)
    assert motif is None and trouvee["date"] == date(2023, 4, 15)


def test_refus_si_les_scores_different():
    """Le contrôle qui vaut tous les autres.

    Même affiche, même jour, mais le match ne finit pas pareil : ce n'est pas
    le même match, quelle que soit la ressemblance des noms.
    """
    index = _index(("Lyon", "Nantes", date(2023, 4, 15), (0, 0), COTES))
    trouvee, motif = rapprocher(_match(), index)
    assert trouvee is None and motif == "scores différents", motif


def test_refus_si_deux_candidates():
    """Deux rencontres à un jour d'écart : c'est l'index qui est ambigu."""
    index = _index(("Lyon", "Nantes", date(2023, 4, 15), (2, 1), COTES),
                   ("Lyon", "Nantes", date(2023, 4, 16), (2, 1), COTES))
    trouvee, motif = rapprocher(_match(), index)
    assert trouvee is None and motif == "plusieurs candidates", motif


def test_refus_si_affiche_absente():
    index = _index(("Lyon", "Rennes", date(2023, 4, 15), (2, 1), COTES))
    trouvee, motif = rapprocher(_match(), index)
    assert trouvee is None and motif == "affiche absente de football-data"


def test_le_sens_domicile_exterieur_compte():
    """Lyon-Nantes n'est pas Nantes-Lyon : la cote 1 ne désigne pas la même
    équipe. Une clé non ordonnée rapprocherait les deux."""
    index = _index(("Nantes", "Lyon", date(2023, 4, 15), (1, 2), COTES))
    trouvee, motif = rapprocher(_match(), index)
    assert trouvee is None and motif == "affiche absente de football-data"


def test_marge_dun_jour_acceptee_mais_pas_deux():
    for ecart, attendu in ((1, True), (2, False)):
        jour = date(2023, 4, 15) + timedelta(days=ecart)
        index = _index(("Lyon", "Nantes", jour, (2, 1), COTES))
        trouvee, _ = rapprocher(_match(), index)
        assert (trouvee is not None) is attendu, (ecart, trouvee)


def test_sans_score_la_date_doit_tomber_juste():
    """Faute de score à comparer, on n'a plus que la date pour trancher :
    on exige alors le jour exact, sans la marge d'un jour."""
    index = _index(("Lyon", "Nantes", date(2023, 4, 16), None, COTES))
    trouvee, motif = rapprocher(_match(score_home=None, score_away=None), index)
    assert trouvee is None and motif == "sans score, et date décalée", motif

    index = _index(("Lyon", "Nantes", date(2023, 4, 15), None, COTES))
    trouvee, motif = rapprocher(_match(score_home=None, score_away=None), index)
    assert motif is None, motif


# Les octets EF BB BF qui ouvrent les fichiers récents, tels qu'ils
# apparaissent une fois le fichier lu en latin-1.
CSV = """ï»¿Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA,B365H,B365D,B365A
F1,15/04/2023,Lyon,Nantes,2,1,1.80,3.50,4.20,1.75,3.55,4.40
F1,22/04/2023,Nantes,Lyon,0,0,,,,1.00,15.0,3.10
"""


def test_lecture_de_football_data():
    """L'index doit garder le sens de l'affiche, et jeter les cotes vides.

    Une clé non ordonnée confondrait le match aller et le match retour, et
    la cote 1 se retrouverait attribuée à l'équipe adverse.
    """
    with tempfile.TemporaryDirectory() as rep:
        (Path(rep) / "F1.csv").write_text(CSV, encoding="latin-1")
        # Le chargement de football-data vit dans dater_grilles : c'est le
        # seul module qui parle à cette source.
        ancien, dg.CACHE_FD = dg.CACHE_FD, Path(rep)
        try:
            index = jc.charger_rencontres()
        finally:
            dg.CACHE_FD = ancien

    aller = index[(dg._cle("Lyon"), dg._cle("Nantes"))]
    retour = index[(dg._cle("Nantes"), dg._cle("Lyon"))]
    assert len(aller) == len(retour) == 1, index
    assert aller[0]["score"] == (2, 1) and retour[0]["score"] == (0, 0)
    assert aller[0]["cotes"]["pinnacle_cloture"] == (1.8, 3.5, 4.2)
    # La colonne Div doit survivre à la marque d'ordre des octets qui ouvre
    # les fichiers récents de football-data. Sans quoi la compétition se perd
    # en silence — les autres colonnes, elles, arrivent intactes.
    assert aller[0]["division"] == "F1"
    # Colonnes vides ou aberrantes : le trio entier est écarté plutôt que
    # complété à moitié. Pinnacle manque sur le retour, et le trio Bet365
    # porte une cote de 1.00 — une cote qui ne paie rien n'est pas une cote.
    assert retour[0]["cotes"] == {}, retour[0]["cotes"]


def test_un_fichier_vide_ne_fait_pas_tomber_le_chargement():
    """Un téléchargement interrompu laisse un CSV de zéro octet. Il ne doit
    pas emporter les 258 autres fichiers avec lui."""
    with tempfile.TemporaryDirectory() as rep:
        (Path(rep) / "vide.csv").write_text("", encoding="latin-1")
        (Path(rep) / "F1.csv").write_text(CSV, encoding="latin-1")
        ancien, dg.CACHE_FD = dg.CACHE_FD, Path(rep)
        try:
            index = jc.charger_rencontres()
        finally:
            dg.CACHE_FD = ancien
    assert len(index) == 2, index


def test_refuse_un_marche_deja_regle():
    """Le piège le plus coûteux rencontré dans ce projet.

    Turquie - Italie du 11 juin 2021, finale de poule perdue 0-3, est servie
    par Winamax avec les cotes 250 / 250 / 1,00. L'issue réalisée y vaut 1,00 :
    ces cotes CONTIENNENT le résultat. 3 092 matchs sur 5 070 sont dans ce cas,
    et une analyse qui les garde retrouve le résultat qu'elle croit prédire —
    le « suiveur de cotes » y trouvait 6,6 bons résultats sur 7.
    """
    assert not dg.cote_plausible((250.0, 250.0, 1.0))
    assert not dg.cote_plausible((225.0, 6.5, 1.01))
    assert not dg.cote_plausible((1.0, 7.0, 250.0))
    # Un marché réel, même très déséquilibré, reste dans les bornes.
    assert dg.cote_plausible((1.06, 12.0, 30.0))
    assert dg.cote_plausible((1.15, 8.0, 50.9))     # le plus court vu chez Pinnacle
    assert dg.cote_plausible((2.4, 3.35, 2.7))


def test_chaque_borne_arrete_quelque_chose_a_elle_seule():
    """Les deux bornes se couvraient l'une l'autre dans le test précédent.

    Un marché réglé viole les deux à la fois, si bien qu'en supprimer une
    n'échouait nulle part. Il faut donc un cas par borne.
    """
    # Plancher seul : 1,04 est trop court, le reste est ordinaire.
    assert not dg.cote_plausible((1.04, 8.0, 30.0))
    # Plafond seul : 150 n'existe pas sur un 1/N/2, le reste est ordinaire.
    assert not dg.cote_plausible((1.5, 8.0, 150.0))


def test_un_triplet_incomplet_n_est_pas_un_marche():
    assert not dg.cote_plausible((2.4, None, 2.7))
    assert not dg.cote_plausible((2.4, 3.35))
    assert not dg.cote_plausible(None)


def test_match_sans_date_jamais_rapproche():
    index = _index(("Lyon", "Nantes", date(2023, 4, 15), (2, 1), COTES))
    trouvee, motif = rapprocher(_match(debut=None), index)
    assert trouvee is None and motif == "match sans date"


def test_ordre_de_preference_des_sources():
    cotes = {"pinnacle_cloture": (1.8, 3.5, 4.2), "pinnacle": (1.9, 3.4, 4.0),
             "bet365_cloture": (1.7, 3.6, 4.5), "bet365": (1.75, 3.55, 4.4)}
    jour = date(2023, 4, 15)
    assert choisir_cote(cotes, jour) == ((1.8, 3.5, 4.2), "pinnacle_cloture")
    del cotes["pinnacle_cloture"]
    assert choisir_cote(cotes, jour)[1] == "pinnacle"
    del cotes["pinnacle"]
    assert choisir_cote(cotes, jour)[1] == "bet365_cloture"


def test_pinnacle_ecarte_apres_lavertissement():
    """football-data signale ses cotes Pinnacle comme peu fiables passé
    juin 2025. On retombe sur Bet365 plutôt que de faire comme si de rien."""
    cotes = {"pinnacle_cloture": (1.8, 3.5, 4.2), "bet365_cloture": (1.7, 3.6, 4.5)}
    apres = PINNACLE_FIABLE_JUSQUA + timedelta(days=1)
    assert choisir_cote(cotes, apres)[1] == "bet365_cloture"
    assert choisir_cote(cotes, PINNACLE_FIABLE_JUSQUA)[1] == "pinnacle_cloture"
    # Sans repli, on ne renvoie rien plutôt qu'une cote suspecte.
    assert choisir_cote({"pinnacle_cloture": (1.8, 3.5, 4.2)}, apres) == (None, None)


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
