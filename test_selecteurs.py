"""Rejoue les sélecteurs sur une page figée, sans réseau.

POURQUOI CE TEST EXISTE. Le 18 août 2026, les sélecteurs ont été confrontés
au site pour la première fois. Les trois trouvaient bien leurs éléments —
et pourtant le scraper n'aurait produit AUCUN match : inner_text() colle le
nom de l'équipe au score, « Alpha FC1N2Beta SC3 - 3 », et le motif exigeait
une frontière de mot avant le chiffre. Sept lignes, sept scores illisibles.

Un test de sélecteurs qui se contente de compter les éléments n'aurait rien
vu. Celui-ci va jusqu'au JSON.

Il demande Chromium (« playwright install chromium ») là où test_parsing.py
tourne sans rien. Il ne touche pas au réseau : la page vient de
fixture_grille.html, une reproduction de structure aux données inventées.

    python test_selecteurs.py        (ou : pytest test_selecteurs.py)

CE QU'IL NE PEUT PAS FAIRE : dire si le site a changé depuis. La fixture est
un instantané. Quand Winamax redéploie, c'est --diagnostic sur une vraie
grille qui le dira, pas ce fichier.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

import scrape_grille as sg

FIXTURE = Path(__file__).parent / "fixture_grille.html"


def _grille_depuis_html(html: str):
    """Le scrape_grille() du dépôt, mais sur un HTML donné au lieu du site."""
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
        # Seule la navigation est remplacée : tout le reste est le vrai code.
        page.goto = lambda url, **kw: None
        page.set_content(html)
        try:
            return sg.scrape_grille(page, "grille7", 4168)
        finally:
            nav.close()


def _grille_depuis_fixture():
    return _grille_depuis_html(FIXTURE.read_text(encoding="utf-8"))


def test_extraction_complete():
    data = _grille_depuis_fixture()
    assert data is not None, "aucune grille extraite de la fixture"
    assert data["statut"] == sg.STATUT_TERMINEE

    # Deux lignes lisibles sur trois. La troisième n'a pas de score : elle
    # doit être écartée ET signalée, jamais devinée ni tue.
    assert len(data["matches"]) == 2, data["matches"]
    assert len(data.get("lignes_ignorees", [])) == 1, data.get("lignes_ignorees")

    premier = data["matches"][0]
    assert premier["home"] == "Alpha FC", premier          # l'ordre domicile/extérieur
    assert premier["away"] == "Beta SC", premier
    assert (premier["score_home"], premier["score_away"]) == (3, 3), premier
    assert premier["resultat"] == "N", premier             # déduit du score, pas d'une couleur

    # Ligne dont la classe de score a changé, comme après un redéploiement :
    # la lecture doit retomber sur le texte de la ligne.
    second = data["matches"][1]
    assert (second["score_home"], second["score_away"]) == (0, 1), second
    assert second["resultat"] == "2", second


def test_rapports_et_montant():
    data = _grille_depuis_fixture()

    # La ligne d'en-tête « Résultat / Nombre / Montant » n'est pas un rapport.
    assert len(data["rapports"]) == 2, data["rapports"]
    assert data["rapports"][0] == {"rang": "7 / 7", "nombre_gagnants": 4,
                                   "montant": 1500.50}, data["rapports"][0]
    assert data["rapports"][1] == {"rang": "6 / 7", "nombre_gagnants": 112,
                                   "montant": 25.25}, data["rapports"][1]

    # Montant en espace insécable, lu ailleurs que dans le tableau.
    assert data["montant_distribue"] == 8830.00, data["montant_distribue"]

    # Cohérence : la somme des rapports doit approcher le montant distribué.
    somme = sum(r["nombre_gagnants"] * r["montant"] for r in data["rapports"])
    assert abs(somme - data["montant_distribue"]) < 1.0, (somme, data["montant_distribue"])


def test_un_match_annule_devient_un_match_a_part_entiere():
    """UN match annulé n'est pas UNE grille annulée, ni une ligne illisible.

    Relevé sur la grille 4170 : Celta Vigo - Osasuna, cellule de score
    « Annulé ». Deux erreurs se sont succédé sur ce cas.

    La première jetait toute la grille : le mot « annulé » était cherché dans
    la page entière avant qu'on ait regardé les matchs, et six scores
    parfaitement lisibles partaient sous une étiquette fausse.

    La seconde, plus discrète, rangeait cette ligne parmi les lignes écartées
    faute de score. On y perdait les deux équipes, et surtout on confondait
    « pas de score parce que tout le monde a gagné » avec « pas de score
    parce qu'on n'a pas su lire ». La première est une donnée, la seconde un
    aveu d'échec.
    """
    html = FIXTURE.read_text(encoding="utf-8").replace(
        '<span class="sc-jAZUkk sc-ccHeIS jAoxrH iuBVCj">Zeta AC</span></div>',
        '<span class="sc-jAZUkk sc-ccHeIS jAoxrH iuBVCj">Zeta AC</span>'
        '<span class="sc-jYPihs dyByel">Annulé</span></div>')
    data = _grille_depuis_html(html)

    assert data is not None, "grille perdue à cause d'une seule ligne annulée"
    assert data["statut"] == sg.STATUT_TERMINEE, data["statut"]
    assert len(data["matches"]) == 3, data["matches"]
    assert data.get("lignes_ignorees", []) == [], data.get("lignes_ignorees")

    annule = data["matches"][2]
    assert annule["home"] == "Epsilon" and annule["away"] == "Zeta AC", annule
    assert annule["resultat"] == sg.RESULTAT_ANNULE, annule
    assert annule["tous_gagnants"] is True, annule
    # Pas de score inventé : ni 0-0, ni un 1/N/2 arbitraire.
    assert annule["score_home"] is None and annule["score_away"] is None, annule

    # La mention de la page est expliquée par ce match : la signaler en plus
    # noierait le seul cas qui mérite un coup d'œil.
    assert "mention_annulation" not in data, data


def test_mention_inexpliquee_est_signalee():
    """« annul » sans aucun match annulé : là, il faut regarder.

    Le test porte sur toute la page — un bouton « Annuler » d'une bannière
    cookies suffirait. On ne peut pas resserrer le motif sans avoir vu le
    cas, alors on garde le contexte pour qu'un faux positif se voie au lieu
    de se fondre dans la base.
    """
    html = FIXTURE.read_text(encoding="utf-8").replace(
        "<body>", "<body><button>Annuler</button>")
    data = _grille_depuis_html(html)

    assert data["statut"] == sg.STATUT_TERMINEE, data["statut"]
    assert len(data["matches"]) == 2, data["matches"]
    assert "mention_annulation" in data, data
    assert "annul" in data["mention_annulation"]


def test_grille_entierement_annulee_reste_enregistree():
    """Aucun match lisible ET la mention : là, l'annulation est la lecture.

    Une grille annulée n'est pas un trou. Winamax annule une liste quand trop
    de matchs sont donnés gagnants par forfait ou report ; la confondre avec
    une grille absente fausserait plus tard toute étude de biais.
    """
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace("Statut : Terminée", "Statut : Annulée")
    for score in ('<span class="sc-jYPihs dyByel">3 - 3</span>',
                  '<span class="sc-zzzzzz apresRedeploiement">0 - 1</span>'):
        html = html.replace(score, "")
    data = _grille_depuis_html(html)

    assert data is not None, "une grille annulée doit être enregistrée, pas ignorée"
    assert data["statut"] == sg.STATUT_ANNULEE, data["statut"]
    assert data["matches"] == []
    assert data["montant_distribue"] is None
    assert "annulation_indice" in data, data


def test_grille_non_reglee_n_est_pas_terminee():
    """Des matchs lisibles ne prouvent pas qu'une grille est réglée.

    Relevé sur la grille 3836 : un match sans résultat, un autre annulé,
    aucune mention « Terminée », et « Montant garanti » au lieu de « Montant
    distribué » — la page d'une grille avant son règlement.

    Le mot « annulé » de l'autre ligne suffisait à franchir le filtre d'entrée,
    et les matchs lisibles à conclure « terminée ». On aurait enregistré une
    grille non réglée comme réglée, rapports vides, sans qu'aucun contrôle de
    cohérence puisse s'en apercevoir faute de montant à comparer.
    """
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace("Statut : Terminée", "")           # pas encore réglée
    html = html.replace("Montant distribué :", "Montant garanti :")
    html = html.replace(
        '<span class="sc-jAZUkk sc-ccHeIS jAoxrH iuBVCj">Zeta AC</span></div>',
        '<span class="sc-jAZUkk sc-ccHeIS jAoxrH iuBVCj">Zeta AC</span>'
        '<span class="sc-jYPihs dyByel">Annulé</span></div>')

    assert _grille_depuis_html(html) is None, (
        "une grille non réglée ne doit pas être enregistrée comme terminée")


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except AssertionError as e:
            print(f"  ECHEC  {nom} : {e}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
