"""Tests du déroulement d'un lot : reprise, arrêts, sens de parcours.

Ces garde-fous n'existent que pour les gros lots — plusieurs milliers
d'identifiants, plusieurs heures, sans personne devant l'écran. C'est
précisément le moment où on ne peut pas les vérifier à la main : un arrêt
qui ne s'enclenche pas laisse le script tourner dans le vide toute la nuit,
et un arrêt trop zélé coupe une collecte saine.

Aucun réseau, aucun navigateur : Playwright, l'attente et l'écriture sur
disque sont remplacés par des doublures. On ne teste ici que l'enchaînement
des décisions.

    python test_lot.py        (ou : pytest test_lot.py)
"""

import io
import sys
from contextlib import redirect_stdout

import scrape_grille as sg


class _FaussePage:
    """Une page qui expose ce que run_batch attend d'elle, et rien de plus."""

    def __init__(self):
        self.filtres = []

    def route(self, motif, gestionnaire):
        self.filtres.append((motif, gestionnaire))


class _FauxNav:
    def new_page(self, **kw):
        return _FaussePage()

    def close(self):
        pass


class _FauxChromium:
    def __init__(self):
        self.lancements = 0

    def launch(self, **kw):
        self.lancements += 1
        return _FauxNav()


class _FauxPlaywright:
    def __init__(self):
        self.chromium = _FauxChromium()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FauxTemps:
    """Enregistre les attentes au lieu de les subir."""

    def __init__(self):
        self.attentes = []

    def sleep(self, secondes):
        self.attentes.append(secondes)


def _lancer(reponses, deja_en_base=(), **kwargs):
    """Joue un lot où scrape_grille renvoie/lève ce que dit `reponses`.

    `reponses` associe un id à : un dict (grille trouvée), None (introuvable)
    ou une instance d'Exception (à lever).
    """
    vrais = (sg.sync_playwright, sg.time, sg.save_grille, sg._chemin_grille, sg.scrape_grille)
    temps, sauvees = _FauxTemps(), []

    def faux_scrape(page, grille_type, gid):
        r = reponses.get(gid)
        if isinstance(r, Exception):
            raise r
        return r

    playwright = _FauxPlaywright()
    sg.sync_playwright = lambda: playwright
    sg.time = temps
    sg.save_grille = lambda data: sauvees.append(data["grille_id"])
    sg._chemin_grille = lambda t, gid: type("_P", (), {"exists": lambda self: gid in deja_en_base})()
    sg.scrape_grille = faux_scrape
    try:
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = sg.run_batch("grille7", list(reponses), **kwargs)
        return code, sauvees, temps.attentes, sortie.getvalue(), playwright
    finally:
        (sg.sync_playwright, sg.time, sg.save_grille,
         sg._chemin_grille, sg.scrape_grille) = vrais


def _grille(gid, matches=None):
    """Une grille plausible : ses matchs la distinguent des autres.

    La première version renvoyait `matches: [{}]` pour tout le monde. C'était
    commode et faux : deux grilles réelles ne partagent jamais les mêmes sept
    matchs, et le garde-fou des grilles identiques prenait ces doublures pour
    la panne qu'il surveille. Une doublure qui ne ressemble pas à la réalité
    finit toujours par mentir sur le code.
    """
    return {"grille_id": gid, "grille_type": "grille7",
            "matches": matches or [{"home": f"Club {gid}", "away": f"Club {gid + 1}",
                                    "score_home": gid % 4, "score_away": gid % 3,
                                    "resultat": "1"}]}


def test_reprise_ne_redemande_pas_ce_qui_est_en_base():
    code, sauvees, attentes, texte, _ = _lancer(
        {4170: _grille(4170), 4169: _grille(4169), 4168: _grille(4168)},
        deja_en_base=(4169,))
    assert code == 0, texte
    assert sauvees == [4170, 4168], sauvees            # 4169 jamais redemandée
    assert "1 déjà en base" in texte, texte
    # Une grille sautée ne coûte pas d'attente : sinon reprendre un lot de
    # 4000 identifiants déjà collectés prendrait des heures pour ne rien faire.
    assert len(attentes) == 1, attentes


def test_arret_apres_erreurs_consecutives():
    reponses = {i: RuntimeError("coupé") for i in range(4170, 4160, -1)}
    code, sauvees, _, texte, _ = _lancer(reponses, arret_erreurs=3)
    assert code == 1, texte
    assert sauvees == []
    assert "3 erreurs d'affilée" in texte, texte
    # Le message doit donner la commande de reprise, sinon l'arrêt n'aide pas.
    assert "--from-id 4168" in texte, texte
    assert "python scrape_grille.py" in texte, texte


def test_une_reussite_remet_le_compteur_a_zero():
    # erreur, erreur, succès, erreur, erreur : jamais trois d'affilée.
    reponses = {4170: RuntimeError("x"), 4169: RuntimeError("x"),
                4168: _grille(4168), 4167: RuntimeError("x"), 4166: RuntimeError("x")}
    code, sauvees, _, texte, _ = _lancer(reponses, arret_erreurs=3)
    assert code == 0, texte
    assert sauvees == [4168], sauvees


def test_arret_apres_absences_consecutives():
    reponses = {i: None for i in range(4170, 4150, -1)}
    code, _, _, texte, _ = _lancer(reponses, arret_absences=5)
    assert code == 1, texte
    assert "5 grilles introuvables d'affilée" in texte, texte
    # L'arrêt ne doit pas trancher entre fin d'archive et blocage.
    assert "soit l'accès est coupé" in texte, texte


def test_pause_longue_entre_les_lots():
    reponses = {i: _grille(i) for i in range(4170, 4162, -1)}      # 8 grilles
    code, _, attentes, texte, _ = _lancer(reponses, lot=3, pause_lot=(600.0, 601.0))
    assert code == 0, texte
    longues = [a for a in attentes if a >= 600.0]
    assert len(longues) == 2, attentes          # après la 3e et la 6e
    assert "lot de 3 terminé" in texte, texte


def test_arret_sur_grilles_identiques():
    # Le site se met à servir la même page quel que soit l'ID : aucune erreur,
    # aucune absence, des fichiers qui s'écrivent — et tout est faux.
    memes = [{"home": "Alpha", "away": "Beta", "score_home": 1,
              "score_away": 0, "resultat": "1"}]
    reponses = {i: _grille(i, matches=memes) for i in range(4170, 4160, -1)}
    code, sauvees, _, texte, _ = _lancer(reponses, arret_identiques=3)
    assert code == 1, texte
    assert len(sauvees) == 3, sauvees                  # arrêt à la troisième
    assert "mêmes matchs" in texte, texte
    assert "AVANT de reprendre" in texte, texte


def test_grilles_differentes_ne_declenchent_pas_l_arret():
    reponses = {i: _grille(i) for i in range(4170, 4150, -1)}
    code, sauvees, _, texte, _ = _lancer(reponses, arret_identiques=3)
    assert code == 0, texte
    assert len(sauvees) == 20, len(sauvees)


def test_ressources_inutiles_bloquees():
    """On lit du texte : images, polices et vidéos ne sont pas téléchargées.

    Les feuilles de style, si — inner_text() ne rend que ce qui est visible,
    et sans CSS des éléments masqués referaient surface. On gagnerait quelques
    dixièmes de seconde contre le risque de lire une autre page que celle
    affichée.
    """
    abandonnees, poursuivies = [], []

    class _FausseRequete:
        def __init__(self, type_):
            self.resource_type = type_

    class _FausseRoute:
        def __init__(self, type_):
            self.request = _FausseRequete(type_)
            self._type = type_

        def abort(self):
            abandonnees.append(self._type)

        def continue_(self):
            poursuivies.append(self._type)

    for type_ in ("image", "media", "font", "stylesheet", "document",
                  "script", "xhr", "fetch"):
        sg._bloquer_ressources_inutiles(_FausseRoute(type_))

    assert sorted(abandonnees) == ["font", "image", "media"], abandonnees
    assert "stylesheet" in poursuivies, poursuivies
    assert "xhr" in poursuivies and "script" in poursuivies, poursuivies


def test_navigateur_renouvele_a_chaque_lot():
    """Un Chromium neuf à chaque lot, plutôt qu'un seul sur 3 660 pages.

    Les premiers lots tenaient sur 500 navigations. La collecte complète en
    demande sept fois plus, et rien ne dit que le même navigateur encaisse.
    On le referme pendant la pause de lot : deux secondes de relance contre
    le risque de retrouver la collecte arrêtée au matin.
    """
    reponses = {i: _grille(i) for i in range(4170, 4160, -1)}      # 10 grilles
    code, sauvees, _, _, playwright = _lancer(reponses, lot=3, pause_lot=(0.0, 0.1))
    assert code == 0
    assert len(sauvees) == 10, sauvees
    # Un lancement au départ, puis un après chacune des pauses de lot
    # (après la 3e, la 6e et la 9e grille).
    assert playwright.chromium.lancements == 4, playwright.chromium.lancements


def test_sens_de_parcours():
    captures = {}
    vrai = sg.run_batch
    sg.run_batch = lambda t, ids, **kw: captures.setdefault("ids", ids) and 0 or 0
    vrais_argv = sys.argv
    try:
        for depart, arrivee, attendu in ((4170, 4168, [4170, 4169, 4168]),
                                         (4168, 4170, [4168, 4169, 4170])):
            captures.clear()
            sys.argv = ["scrape_grille.py", "--from-id", str(depart), "--to-id", str(arrivee)]
            with redirect_stdout(io.StringIO()):
                sg.main()
            assert captures["ids"] == attendu, (depart, arrivee, captures["ids"])
    finally:
        sg.run_batch, sys.argv = vrai, vrais_argv


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
