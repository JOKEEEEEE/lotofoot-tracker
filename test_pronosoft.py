"""Tests du parseur Pronosoft, sur du HTML figé.

Aucun réseau : le HTML ci-dessous reproduit la structure réelle d'une page
d'archive, y compris ses pièges — l'issue marquée par une classe et non par un
score, les entités HTML dans les montants, et la grille pas encore jouée.

    python test_pronosoft.py        (ou : pytest test_pronosoft.py)
"""

import json
import tempfile
import urllib.error
from pathlib import Path

import collecter_pronosoft as cp
from collecter_pronosoft import analyser

def _page(res=("res", "", ""), rapports=True):
    lignes = "".join(
        f'<tr><td>{i+1}</td><td class="home">Équipe {i+1}</td>'
        f'<td class="result"><span class="{res[0]}">1</span>'
        f'<span class="{res[1]}">N</span><span class="{res[2]}">2</span></td>'
        f'<td class="ext">Adverse {i+1}</td></tr>'
        for i in range(7))
    tableau_rapports = (
        '<table><tr><td>7</td><td>15</td><td>3 092&nbsp;&euro;</td>'
        '<td>6</td><td>301</td><td>188,3&nbsp;&euro;</td></tr></table>'
        if rapports else "")
    return ('<table><tr><td class="head">Dimanche 16 Août à 15h55</td></tr>'
            + lignes + "</table>" + tableau_rapports)


def test_lit_les_affiches_et_lissue():
    """L'issue n'est marquée que par une classe : il n'y a pas de score."""
    g = analyser(_page(), "loto-foot-7", 103)
    assert len(g["matchs"]) == 7
    assert g["matchs"][0] == {"home": "Équipe 1", "away": "Adverse 1", "issue": "1"}
    assert g["date"] == "Dimanche 16 Août à 15h55"
    assert g["reglee"] is True


def test_reconnait_le_nul_et_le_deux():
    assert analyser(_page(("", "res", "")), "loto-foot-7", 1)["matchs"][0]["issue"] == "N"
    assert analyser(_page(("", "", "res")), "loto-foot-7", 1)["matchs"][0]["issue"] == "2"


def test_lit_les_montants_avec_leurs_entites():
    """« 3 092&nbsp;&euro; » est un nombre, pas une chaîne à recopier."""
    g = analyser(_page(), "loto-foot-7", 103)
    assert g["rapports"] == [{"bons": 7, "gagnants": 15, "rapport": 3092.0},
                             {"bons": 6, "gagnants": 301, "rapport": 188.3}]


def test_une_grille_pas_encore_jouee_n_est_pas_reglee():
    """Le piège : la reprise saute ce qui est déjà en base. Enregistrer une
    grille aux issues vides la figerait pour toujours."""
    g = analyser(_page(("", "", ""), rapports=False), "loto-foot-8", 110)
    assert len(g["matchs"]) == 7
    assert all(m["issue"] is None for m in g["matchs"])
    assert g["reglee"] is False


def test_une_page_sans_tableau_ne_casse_pas():
    assert analyser("<html><body>404</body></html>", "loto-foot-7", 1) == {}


def test_le_reseau_qui_hoquette_ne_tue_pas_la_collecte():
    """Le 21 août, une résolution DNS ratée a tué le script après 88 grilles.

    Une erreur réseau ne dit rien de la page demandée : elle dit que le
    réseau a hoqueté. On repose la question.
    """
    appels = []

    def faux_urlopen(requete, timeout=None):
        appels.append(requete.full_url)
        if len(appels) < 3:
            raise urllib.error.URLError("nodename nor servname provided")
        class Reponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"<html>ok</html>"
        return Reponse()

    vrais = (cp.urllib.request.urlopen, cp.time.sleep)
    cp.urllib.request.urlopen = faux_urlopen
    cp.time.sleep = lambda s: None
    try:
        assert cp._lire("https://exemple.fr/x") == "<html>ok</html>"
        assert len(appels) == 3, appels
    finally:
        cp.urllib.request.urlopen, cp.time.sleep = vrais


def test_une_panne_qui_dure_finit_par_remonter():
    """Réessayer n'est pas s'obstiner : au bout des essais, l'erreur sort."""
    def toujours_ko(requete, timeout=None):
        raise urllib.error.URLError("réseau coupé")

    vrais = (cp.urllib.request.urlopen, cp.time.sleep)
    cp.urllib.request.urlopen = toujours_ko
    cp.time.sleep = lambda s: None
    try:
        leve = False
        try:
            cp._lire("https://exemple.fr/x")
        except urllib.error.URLError:
            leve = True
        assert leve, "l'erreur doit remonter après les essais"
    finally:
        cp.urllib.request.urlopen, cp.time.sleep = vrais


def test_la_reprise_ne_relit_pas_ce_qui_est_deja_en_base():
    """Reprendre ne veut pas dire tout relire.

    La collecte descend le temps : la suite du travail commence sous la plus
    ancienne grille en base, et il n'y a aucune raison de repasser par les
    quatre-vingt-neuf autres.
    """
    appels = []
    vrai = cp._lire
    cp._lire = lambda url: appels.append(url) or "<html></html>"
    try:
        with tempfile.TemporaryDirectory() as rep:
            d = Path(rep)
            for cle, prec in (("2026-0110", "/fr/…/2026-grille-109/"),
                              ("2026-0109", "/fr/…/2026-grille-108/"),
                              ("2023-0022", "/fr/…/2023-grille-21/")):
                (d / f"{cle}.json").write_text(json.dumps(
                    {"url": f"https://x/{cle}/", "precedente": prec}))
            # La plus ancienne est 2023-0022 : c'est sous elle qu'on reprend,
            # et sans aucune requête.
            assert cp._depart("loto-foot-7", d) == "/fr/…/2023-grille-21/"
            assert appels == [], appels
    finally:
        cp._lire = vrai


def test_une_base_vide_repart_de_la_grille_la_plus_recente():
    vrai = cp._lire
    cp._lire = lambda url: ('<a href="/fr/lotosports/historiques/loto-foot-7/'
                            '2026-2027/2026-grille-105/">x</a>'
                            '<a href="/fr/lotosports/historiques/loto-foot-7/'
                            '2026-2027/2026-grille-103/">y</a>')
    try:
        with tempfile.TemporaryDirectory() as rep:
            depart = cp._depart("loto-foot-7", Path(rep))
            assert depart.endswith("2026-grille-105/"), depart
    finally:
        cp._lire = vrai


REPART = """<table><tr><th>1</th><th>N</th><th>2</th></tr>
<tr id="m1"><td><span data-date-utc="2026-08-16 13:55:00">15h55</span></td>
<td class="match">Lens-Paris SG</td>
<td class="cote-d"><a href="/click.php?book=Winamax">38%<span class="dev_span_1">1,96</span></a></td>
<td class="cote-d">29%<span class="dev_span_n">3,70</span></td>
<td class="cote-d">33%<span class="dev_span_2">3,90</span></td>
<td class="dev_s">2-0</td></tr></table>"""


def test_la_repartition_donne_cotes_public_date_et_score():
    ligne = cp.analyser_repartition(REPART)[0]
    assert ligne["home"] == "Lens" and ligne["away"] == "Paris SG"
    assert ligne["cotes"] == [1.96, 3.70, 3.90], ligne
    # Le piège : une expression qui traverse les cellules ramenait 38 % trois
    # fois. Les trois parts doivent être distinctes.
    assert ligne["public"] == [38.0, 29.0, 33.0], ligne
    assert ligne["score"] == [2, 0] and ligne["debut"] == "2026-08-16 13:55:00"


def test_une_page_de_repli_ne_se_colle_pas_sur_la_mauvaise_grille():
    """Le piège qui a réellement mordu.

    Un numéro hors série ne renvoie pas 404 chez Pronosoft : la page sert
    silencieusement la grille en cours. La grille 109 du Loto Foot 8 s'est vu
    coller les cotes de la 110, et le contrôle de longueur n'y a rien vu
    puisque les deux avaient huit lignes.
    """
    grille = {"matchs": [{"home": "Atl. Madrid", "away": "Malaga", "issue": "1"},
                         {"home": "Celtic", "away": "Lask Linz", "issue": "1"}]}
    repli = [{"home": "Marseille", "away": "Strasbourg", "cotes": [1.68, 4.25, 4.4],
              "public": None, "score": None, "debut": None},
             {"home": "Sochaux", "away": "Guingamp", "cotes": [3.0, 3.2, 2.35],
              "public": None, "score": None, "debut": None}]
    resultat = cp.enrichir(dict(grille), repli)
    assert resultat["repartition"].startswith("affiches différentes"), resultat
    assert "cotes" not in resultat["matchs"][0]


def test_les_noms_traduits_ne_font_pas_refuser_la_bonne_grille():
    """Fribourg / Freiburg, St Trond / St.Truiden, Étoile Rouge / Crvena
    Zvezda : trois affiches sur sept ne concordent pas, et c'est pourtant la
    bonne grille."""
    assert cp.meme_affiche("Atl. Madrid", "Atletico Madrid")
    assert cp.meme_affiche("Academico Viseu", "Viseu")
    assert cp.meme_affiche("OFI Crète", "OFI Crete")
    assert not cp.meme_affiche("Marseille", "Atl. Madrid")


def test_le_score_doit_concorder_avec_lissue():
    """Un nom se traduit, un score non. C'est le contrôle qui ne ment pas."""
    grille = {"matchs": [{"home": "Lens", "away": "Paris SG", "issue": "1"}]}
    bonne = [{"home": "Lens", "away": "Paris SG", "cotes": [1.9, 3.5, 4.0],
              "public": [40.0, 30.0, 30.0], "score": [2, 0], "debut": None}]
    assert cp.enrichir(dict(grille), bonne)["repartition"] == "ok"

    fausse = [dict(bonne[0], score=[0, 2])]      # le 2 a gagné, pas le 1
    r = cp.enrichir({"matchs": [dict(grille["matchs"][0])]}, fausse)
    assert r["repartition"] == "scores en désaccord avec les issues", r


def test_la_saison_borne_la_descente():
    def u(saison):
        return f"/fr/…/loto-foot-7/{saison}/2015-grille-97/"
    assert cp._saison(u("2015-2016")) == "2015-2016"
    assert cp.trop_ancienne(u("2014-2015"), "2015-2016")
    assert not cp.trop_ancienne(u("2015-2016"), "2015-2016")   # la borne est incluse
    assert not cp.trop_ancienne(u("2020-2021"), "2015-2016")
    # Une adresse sans saison ne fait jamais arrêter : on ne devine pas.
    assert not cp.trop_ancienne("/fr/…/lf7/2026-grille-104/", "2015-2016")
    assert not cp.trop_ancienne(u("2010-2011"), "")


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
