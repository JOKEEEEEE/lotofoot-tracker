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


class _FauxNav:
    def new_page(self, **kw):
        return object()

    def close(self):
        pass


class _FauxPlaywright:
    chromium = type("_C", (), {"launch": lambda self, **kw: _FauxNav()})()

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

    sg.sync_playwright = lambda: _FauxPlaywright()
    sg.time = temps
    sg.save_grille = lambda data: sauvees.append(data["grille_id"])
    sg._chemin_grille = lambda t, gid: type("_P", (), {"exists": lambda self: gid in deja_en_base})()
    sg.scrape_grille = faux_scrape
    try:
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = sg.run_batch("grille7", list(reponses), **kwargs)
        return code, sauvees, temps.attentes, sortie.getvalue()
    finally:
        (sg.sync_playwright, sg.time, sg.save_grille,
         sg._chemin_grille, sg.scrape_grille) = vrais


def _grille(gid):
    return {"grille_id": gid, "grille_type": "grille7", "matches": [{}]}


def test_reprise_ne_redemande_pas_ce_qui_est_en_base():
    code, sauvees, attentes, texte = _lancer(
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
    code, sauvees, _, texte = _lancer(reponses, arret_erreurs=3)
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
    code, sauvees, _, texte = _lancer(reponses, arret_erreurs=3)
    assert code == 0, texte
    assert sauvees == [4168], sauvees


def test_arret_apres_absences_consecutives():
    reponses = {i: None for i in range(4170, 4150, -1)}
    code, _, _, texte = _lancer(reponses, arret_absences=5)
    assert code == 1, texte
    assert "5 grilles introuvables d'affilée" in texte, texte
    # L'arrêt ne doit pas trancher entre fin d'archive et blocage.
    assert "soit l'accès est coupé" in texte, texte


def test_pause_longue_entre_les_lots():
    reponses = {i: _grille(i) for i in range(4170, 4162, -1)}      # 8 grilles
    code, _, attentes, texte = _lancer(reponses, lot=3, pause_lot=(600.0, 601.0))
    assert code == 0, texte
    longues = [a for a in attentes if a >= 600.0]
    assert len(longues) == 2, attentes          # après la 3e et la 6e
    assert "lot de 3 terminé" in texte, texte


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
