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


def _grille_depuis_fixture():
    """Le scrape_grille() du dépôt, mais sur la fixture au lieu du site."""
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
        # Seule la navigation est remplacée : tout le reste est le vrai code.
        page.goto = lambda url, **kw: None
        page.set_content(FIXTURE.read_text(encoding="utf-8"))
        try:
            return sg.scrape_grille(page, "grille7", 4168)
        finally:
            nav.close()


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
