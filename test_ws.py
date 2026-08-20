"""Tests du collecteur websocket : décodage des trames et composition.

Les trames réelles pèsent 185 Ko et appartiennent à Winamax ; celle-ci est
une reproduction de leur structure, aux données inventées, avec les deux cas
qui comptent — une grille récente qui porte tout, une grille ancienne dont
Winamax ne sert plus ni les cotes ni la répartition.

    python test_ws.py        (ou : pytest test_ws.py)
"""

import json

from collecter_ws import composer, decoder_resultat, extraire, pool_id

# Le format socket.io : un préfixe numérique, puis ["m", {données}].
def _trame(charge: dict) -> str:
    return "42" + json.dumps(["m", charge], ensure_ascii=False)


RECENTE = _trame({
    "pools": {"7004168": {
        "poolId": 7004168, "poolStatus": "CLOSED", "poolTitle": "Grille 7 n°4168",
        "nbMatches": 2, "poolEnd": 1786733100, "prizepoolAmount": 13245.75,
        "guaranteedAmount": 3000, "netStakes": 13245.75, "addedAmount": None,
        "matches": [72037254, 72037258], "strPoolResult": "010100",
        "payout": [{"nbCorrectResults": 2, "winningGrids": 7,
                    "winningsPerGrid": 946.13}],
        "repart": [285, 2530, 7]}},
    "matches": {
        "72037254": {"matchId": 72037254, "status": "ENDED",
                     "matchStart": 1786733100,
                     "competitor1Id": "sr:competitor:234888", "competitor1Name": "Alpha FC",
                     "competitor2Id": "sr:competitor:6925", "competitor2Name": "Beta SC",
                     "regularScore1": 2, "regularScore2": 0,
                     "odds1": 2.4, "oddsX": 3.35, "odds2": 2.7},
        "72037258": {"matchId": 72037258, "status": "ENDED",
                     "matchStart": 1786736700,
                     "competitor1Id": "sr:competitor:11", "competitor1Name": "Gamma",
                     "competitor2Id": "sr:competitor:42", "competitor2Name": "Delta",
                     "regularScore1": 1, "regularScore2": 1,
                     "odds1": 1.7, "oddsX": 3.7, "odds2": 4.4}}})

ANCIENNE = _trame({
    "pools": {"7000100": {
        "poolId": 7000100, "poolStatus": "CLOSED", "poolTitle": "Grille 7 n°100",
        "nbMatches": 1, "poolEnd": 1451495700, "prizepoolAmount": 10285.5,
        "guaranteedAmount": 5100, "netStakes": 10285.5, "addedAmount": None,
        "matches": [51], "strPoolResult": "001",
        "payout": [{"nbCorrectResults": 1, "winningGrids": 184,
                    "winningsPerGrid": 27.95}]}},
    "matches": {"51": {"matchId": 51, "status": "ENDED", "matchStart": 1451495700,
                       "competitor1Id": "sr:competitor:41", "competitor1Name": "Epsilon",
                       "competitor2Id": "sr:competitor:44", "competitor2Name": "Zeta",
                       "regularScore1": 0, "regularScore2": 1,
                       "odds1": None, "oddsX": None, "odds2": None}}})

# Ce que le websocket échange par ailleurs, et qui ne doit rien casser.
BRUIT = ["2", "3", "40", 'not json at all', b"42[\"autre\",{}]"]


def test_pool_id():
    # Relevé sur le site : la grille 7 n°4168 porte l'identifiant 7004168,
    # la grille 12 n°402 porte 12000402. Les compteurs sont séparés.
    assert pool_id("grille7", 4168) == 7004168
    assert pool_id("grille9", 21) == 9000021
    assert pool_id("grille12", 402) == 12000402


def test_le_bruit_ne_casse_rien():
    """Battements de cœur et accusés de réception traversent le même canal."""
    pools, matchs = extraire(BRUIT)
    assert pools == {} and matchs == {}


def test_pool_nul_est_ignore():
    """Une grille inexistante répond `null`, ce qui n'est pas un pool.

    Relevé en attaquant les grilles 9 et 12 : demander la n°30 quand le
    compteur en est à 22 fait répondre le serveur `"pools": {"9000030":
    null}`. Il dit explicitement « rien » au lieu de se taire, comme le
    faisaient les identifiants absents de la grille 7 — si bien que le cas
    n'était jamais apparu, et que la collecte s'arrêtait sur une erreur au
    premier numéro trop élevé.
    """
    nul = _trame({"pools": {"9000030": None}, "matches": {"7": None}})
    pools, matchs = extraire([nul])
    assert pools == {} and matchs == {}, (pools, matchs)
    # Et le sondage doit conclure « pas encore là » plutôt que planter.
    from collecter_ws import _pool_complet
    assert _pool_complet([nul], 9000030) is False
    assert _pool_complet([nul]) is False


def test_extraction_accumule_les_trames():
    """Les trames se complètent : la grille demandée peut arriver après."""
    pools, matchs = extraire(BRUIT + [RECENTE] + BRUIT + [ANCIENNE])
    assert sorted(pools) == [7000100, 7004168], sorted(pools)
    assert len(matchs) == 3, matchs
    # Et le filtre par identifiant isole la grille voulue.
    pools, _ = extraire([RECENTE, ANCIENNE], pool_id("grille7", 100))
    assert list(pools) == [7000100], list(pools)


def test_grille_recente_porte_cotes_et_repartition():
    pools, matchs = extraire([RECENTE])
    d = composer(pools[7004168], matchs, "grille7", 4168)

    assert d["fin"] == "2026-08-14T18:45:00+00:00", d["fin"]
    assert d["mises_nettes"] == 13245.75 and d["montant_garanti"] == 3000
    assert d["repartition"] == [285, 2530, 7], d["repartition"]

    # L'ordre des matchs est celui du pool, pas celui du dictionnaire : c'est
    # lui qui correspond aux lignes affichées et au codage de strPoolResult.
    assert [m["match_id"] for m in d["matches"]] == [72037254, 72037258]

    premier = d["matches"][0]
    assert premier["home"] == "Alpha FC" and premier["away"] == "Beta SC"
    assert (premier["score_home"], premier["score_away"]) == (2, 0)
    assert premier["debut"] == "2026-08-14T18:45:00+00:00"
    # L'identifiant Sportradar est la clé de jointure : sans lui il faudrait
    # rapprocher « FC Barcelone » de « Barcelona » à la main.
    assert premier["home_id"] == "sr:competitor:234888"
    assert (premier["cote_1"], premier["cote_N"], premier["cote_2"]) == (2.4, 3.35, 2.7)


def test_grille_ancienne_garde_dates_et_identifiants():
    """Ce que Winamax cesse de servir, et ce qu'il sert toujours.

    Vérifié sur la grille 100, du 30 décembre 2015 : ni cotes ni répartition,
    mais la date exacte, les identifiants Sportradar, les scores et les
    rapports. C'est ce qui rend l'historique re-collectable — et ce qui rend
    la collecte quotidienne irremplaçable pour le reste.
    """
    pools, matchs = extraire([ANCIENNE])
    d = composer(pools[7000100], matchs, "grille7", 100)

    assert d["fin"] == "2015-12-30T17:15:00+00:00", d["fin"]
    assert d["rapports"][0]["winningGrids"] == 184
    assert d["repartition"] is None, "les vieilles grilles n'ont pas de répartition"

    m = d["matches"][0]
    assert m["cote_1"] is None and m["cote_N"] is None
    assert m["home_id"] == "sr:competitor:41", m
    assert m["debut"] == "2015-12-30T17:15:00+00:00"


def test_match_absent_de_la_trame_est_signale():
    """Un match annoncé par le pool mais absent ne doit pas disparaître."""
    trame = _trame({"pools": {"7000001": {"poolId": 7000001, "poolEnd": None,
                                          "matches": [999], "payout": []}},
                    "matches": {}})
    pools, matchs = extraire([trame])
    d = composer(pools[7000001], matchs, "grille7", 1)
    assert d["matches"] == [{"match_id": 999, "absent_de_la_trame": True}], d["matches"]


def test_attente_s_arrete_des_que_la_grille_est_complete():
    """On sonde jusqu'à ce que la grille soit là, on ne patiente pas au forfait.

    La première version attendait douze secondes par grille, quoi qu'il
    arrive : seize heures pour l'archive entière, là où la trame arrive en
    une seconde ou deux. Le plafond ne doit servir qu'aux pages muettes.

    Et il ne suffit pas que le pool soit arrivé : il annonce la liste de ses
    matchs, dont le détail peut suivre dans une trame ultérieure. S'arrêter
    trop tôt rendrait une grille sans équipes ni scores.
    """
    from collecter_ws import _pool_complet

    pool_seul = _trame({"pools": {"7004168": {"poolId": 7004168, "poolEnd": None,
                                              "matches": [72037254, 72037258]}},
                        "matches": {}})
    assert _pool_complet([pool_seul], 7004168) is False, "pool sans ses matchs"
    assert _pool_complet([pool_seul, RECENTE], 7004168) is True
    assert _pool_complet([RECENTE], 7000100) is False, "autre grille"
    assert _pool_complet(BRUIT, 7004168) is False


def test_rechargement_quand_la_trame_manque():
    """Une trame ratée se rattrape en rechargeant, pas en attendant plus.

    Mesuré : les grilles déclarées « aucune trame » coûtaient le plafond
    entier, et un second passage du lot les récupérait presque toutes.
    L'échec était donc transitoire — ce qui manquait était un nouvel
    abonnement au flux, pas de la patience.
    """
    import collecter_ws as cw

    class _FaussePage:
        """Muette au premier chargement, bavarde après rechargement."""

        def __init__(self, trames, muette_jusqua):
            self.trames, self.muette_jusqua = trames, muette_jusqua
            self.chargements, self.rechargements, self.attentes = 0, 0, 0

        def goto(self, url, **kw):
            self.chargements += 1
            self._peut_etre_pousser()

        def reload(self, **kw):
            self.rechargements += 1
            self._peut_etre_pousser()

        def wait_for_timeout(self, ms):
            self.attentes += ms

        def _peut_etre_pousser(self):
            if self.chargements + self.rechargements > self.muette_jusqua:
                self.trames.append(RECENTE)

    # Muette au premier chargement : le rechargement doit sauver la grille.
    trames = []
    page = _FaussePage(trames, muette_jusqua=1)
    assert cw.visiter(page, trames, "url", pid=7004168) == 2
    assert page.rechargements == 1, vars(page)

    # Muette quoi qu'il arrive : on abandonne après ESSAIS_TRAME, sans boucler.
    trames = []
    page = _FaussePage(trames, muette_jusqua=99)
    assert cw.visiter(page, trames, "url", pid=7004168) == 0
    assert page.rechargements == cw.ESSAIS_TRAME - 1, vars(page)
    # Et le coût total reste borné par le plafond, essais compris.
    assert page.attentes <= cw.ATTENTE_TRAME_MS * cw.ESSAIS_TRAME + cw.CADENCE_SONDAGE_MS

    # Disponible tout de suite : aucun rechargement, aucune attente inutile.
    trames = []
    page = _FaussePage(trames, muette_jusqua=0)
    assert cw.visiter(page, trames, "url", pid=7004168) == 1
    assert page.rechargements == 0 and page.attentes == 0, vars(page)


class _FauxTemps:
    def __init__(self):
        self.attentes = []

    def sleep(self, secondes):
        self.attentes.append(secondes)


def _lancer_collecte(reponses, **kwargs):
    """Joue un lot où `visiter` livre ce que dit `reponses` : id -> trame ou None."""
    import collecter_ws as cw

    vrais = (cw.sync_playwright, cw._ouvrir, cw._ecouter, cw.visiter,
             cw.sauver, cw.time)
    temps, sauvees, lancements = _FauxTemps(), [], []

    class _Faux:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def close(self): pass

    trames_courantes = []

    def faux_visiter(page, trames, url, attente=None, pid=None):
        """Reproduit le vrai visiter() : réussi seulement si la grille est
        complète, pool ET matchs. Une doublure plus indulgente que le code
        qu'elle imite ne prouve rien."""
        trames.clear()
        gid = int(url.rsplit("-", 1)[1])
        trame = reponses.get(gid)
        if not trame:
            return 0
        trames.append(trame)
        return 1 if cw._pool_complet(list(trames), pid) else 0

    cw.sync_playwright = lambda: _Faux()
    cw._ouvrir = lambda p: (lancements.append(1), (_Faux(), object()))[1]
    cw._ecouter = lambda page: trames_courantes
    cw.visiter = faux_visiter
    cw.sauver = lambda d: sauvees.append(d["grille_id"])
    cw.time = temps
    try:
        import io
        from contextlib import redirect_stdout
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = cw.collecter("grille7", list(reponses), **kwargs)
        return code, sauvees, temps.attentes, sortie.getvalue(), len(lancements)
    finally:
        (cw.sync_playwright, cw._ouvrir, cw._ecouter, cw.visiter,
         cw.sauver, cw.time) = vrais


def test_arret_apres_grilles_muettes_consecutives():
    """Quinze grilles muettes d'affilée : on s'arrête au lieu d'insister.

    Sans ce garde-fou, une coupure d'accès en pleine collecte laissait le
    script taper dans le vide pendant des heures, en signalant simplement
    « aucune trame » des milliers de fois. C'est arrivé.
    """
    reponses = {i: None for i in range(4170, 4150, -1)}
    code, sauvees, _, texte, _ = _lancer_collecte(reponses, arret_vides=5, lot=0)
    assert code == 1, texte
    assert sauvees == []
    assert "5 grilles muettes d'affilée" in texte, texte
    # L'arrêt doit dire comment reprendre, sinon il ne sert qu'à moitié.
    assert "--sauter-existantes" in texte and "--from-id 4166" in texte, texte


def test_une_grille_trouvee_remet_le_compteur_a_zero():
    reponses = {4170: None, 4169: None, 4168: RECENTE, 4167: None, 4166: None}
    code, sauvees, _, texte, _ = _lancer_collecte(reponses, arret_vides=3, lot=0)
    assert code == 0, texte
    assert sauvees == [4168], sauvees


def test_trame_incomplete_n_est_pas_enregistree():
    """Un pool amputé de ses matchs ne doit pas produire de fichier.

    Relevé sur la grille 4174 : le pool était arrivé, ses matchs non. Le
    fichier écrit portait un statut nul, aucune date et aucun match — et
    --sauter-existantes l'aurait tenu pour acquis, si bien qu'il n'aurait
    jamais été recollecté. L'affichage plantait en prime sur ce statut nul,
    arrêtant net une collecte de plusieurs heures.

    Mieux vaut déclarer la grille muette : elle sera redemandée.
    """
    import collecter_ws as cw

    ampute = _trame({"pools": {"7004174": {"poolId": 7004174, "poolStatus": None,
                                           "poolEnd": None, "matches": [999]}},
                     "matches": {}})
    code, sauvees, _, texte, _ = _lancer_collecte({4174: ampute}, arret_vides=99, lot=0)
    assert sauvees == [], sauvees
    assert "aucune trame" in texte, texte


def test_accueil_a_droit_au_second_essai():
    """La page d'accueil ratait sa trame sans jamais réessayer.

    Observé le 20 août : à 18 h 18 la collecte quotidienne annonçait « aucune
    grille active » et s'arrêtait là ; à 18 h 19 elle fonctionnait. Un matin
    sur cinq ou dix, elle n'aurait donc rien collecté — et comme les cotes et
    la répartition s'effacent avec le temps, c'est une perte définitive.

    Sans identifiant, la seule présence de grilles actives suffit à conclure :
    on ne cherche pas leur détail depuis l'accueil.
    """
    import collecter_ws as cw

    actives = _trame({"pools": {"7004173": {"poolId": 7004173, "poolEnd": None,
                                            "matches": [1]}}, "matches": {}})
    assert cw._pool_complet([actives]) is True, "l'accueil se contente des pools"
    assert cw._pool_complet([actives], 7004173) is False, "le détail manque"
    assert cw._pool_complet(BRUIT) is False

    class _PageMuetteUneFois:
        def __init__(self, trames):
            self.trames, self.n = trames, 0

        def goto(self, url, **kw):
            self.n += 1

        def reload(self, **kw):
            self.n += 1
            self.trames.append(actives)

        def wait_for_timeout(self, ms):
            pass

    trames = []
    page = _PageMuetteUneFois(trames)
    assert cw.visiter(page, trames, "url") == 2, "l'accueil doit réessayer"


def test_pause_longue_entre_les_lots():
    reponses = {4170 - i: RECENTE for i in range(8)}
    code, _, attentes, texte, _ = _lancer_collecte(
        reponses, lot=3, pause_lot=(600.0, 601.0), pause=(0.0, 0.0), renouveler=0)
    assert code == 0, texte
    assert len([a for a in attentes if a >= 600]) == 2, attentes
    assert "lot de 3 terminé" in texte, texte


def test_le_code_resultat_se_lit_a_lenvers():
    """La grille 521 du 16 avril 2017, relevée dans la base.

    Bastia-Lyon, match abandonné après envahissement du terrain : Winamax le
    paie à toutes les issues et laisse le score à 0-0. Il est en PREMIÈRE
    ligne de la grille, et son triplet « 111 » est en DERNIÈRE position du
    code. Lu dans le sens de la lecture, on attribuerait l'annulation à
    Marseille-Saint-Étienne, et un « 1 » à un match qui n'a pas eu lieu.
    """
    issues = decoder_resultat("100001100100100100111", 7)
    #        Bastia-Lyon    MU-Chelsea  Darmstadt  Betis  Spartak  Grenade  OM
    #        annulé         2-0         2-1        2-0    2-1      0-3      4-0
    assert issues[0] == {"1", "N", "2"}, issues[0]
    assert [i for i in issues[1:]] == [{"1"}, {"1"}, {"1"}, {"1"}, {"2"}, {"1"}], issues


def test_code_resultat_incomplet_rendu_None():
    """Quatre grilles de la base portent des triplets « 000 » ou un score
    aberrant : on rend None plutôt qu'une issue inventée."""
    assert decoder_resultat("000100", 2) == [{"1"}, None]
    assert decoder_resultat(None, 3) == [None, None, None]
    assert decoder_resultat("1001", 2) == [None, None]     # longueur fausse


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
