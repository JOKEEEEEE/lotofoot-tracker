"""Tests du parseur Pronosoft, sur du HTML figé.

Aucun réseau : le HTML ci-dessous reproduit la structure réelle d'une page
d'archive, y compris ses pièges — l'issue marquée par une classe et non par un
score, les entités HTML dans les montants, et la grille pas encore jouée.

    python test_pronosoft.py        (ou : pytest test_pronosoft.py)
"""

import urllib.error

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
