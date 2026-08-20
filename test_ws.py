"""Tests du collecteur websocket : décodage des trames et composition.

Les trames réelles pèsent 185 Ko et appartiennent à Winamax ; celle-ci est
une reproduction de leur structure, aux données inventées, avec les deux cas
qui comptent — une grille récente qui porte tout, une grille ancienne dont
Winamax ne sert plus ni les cotes ni la répartition.

    python test_ws.py        (ou : pytest test_ws.py)
"""

import json

from collecter_ws import composer, extraire, pool_id

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
