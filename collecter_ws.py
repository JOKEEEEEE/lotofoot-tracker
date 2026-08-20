"""Collecter les grilles par le websocket plutôt que par le DOM.

CE QUE LE DOM NE DIT PAS. Le scraper HTML lit ce qui est affiché : équipes,
scores, rapports. Le websocket qui alimente la page transporte bien davantage,
et c'est vérifié sur deux grilles distantes de onze ans :

    poolEnd, matchStart   la date exacte, à la minute
    competitorId          "sr:competitor:2817" — un identifiant Sportradar
    netStakes             les mises collectées
    guaranteedAmount      le montant garanti
    odds1/oddsX/odds2     les cotes de Winamax        (grilles récentes seulement)
    repart                la répartition des grilles jouées selon leur nombre
                          de bons résultats           (grilles récentes seulement)

`repart` est la donnée la plus précieuse du lot : elle donne la performance
COMPLÈTE du public — combien de parieurs ont eu 0, 1, 2… 7 bons résultats —
là où le DOM ne livrait que le nombre de gagnants. Et elle disparaît en
vieillissant : la grille 4168 l'a, la grille 100 ne l'a plus.

D'OÙ DEUX USAGES :

    python collecter_ws.py --recentes 10     # à lancer chaque jour
    python collecter_ws.py --from-id 4170 --to-id 1

Les fichiers partent dans data/pools/, À CÔTÉ de data/grilles/ et non à sa
place : les 4 152 grilles déjà collectées et auditées servent de témoin. Si
les deux sources s'accordent sur les scores et les rapports, le nouveau
collecteur est prouvé ; sinon, on saura lequel croire avant d'effacer quoi
que ce soit.
"""

import argparse
import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

RACINE = Path(__file__).parent
DATA_POOLS = RACINE / "data" / "pools"
BASE_URL = "https://www.winamax.fr/paris-sportifs/grilles/{type}-{id}"
URL_ACCUEIL = "https://www.winamax.fr/paris-sportifs/grilles"

# poolId = préfixe du type × 1 000 000 + numéro de grille. Relevé : la grille 7
# n°4168 porte l'identifiant 7004168, la grille 12 n°402 porte 12000402.
PREFIXE = {"grille7": 7_000_000, "grille9": 9_000_000, "grille12": 12_000_000}

RESSOURCES_IGNOREES = {"image", "media", "font"}

# PLAFOND D'ATTENTE, PAS DURÉE D'ATTENTE. La première version patientait
# 12 secondes par grille, systématiquement : 345 grilles en quatre-vingts
# minutes, et seize heures pour l'archive entière. Or la trame arrive en
# général en une seconde ou deux — il suffisait de s'en apercevoir et de
# passer à la suite. On sonde donc toutes les CADENCE_SONDAGE_MS jusqu'à
# trouver la grille demandée, et le plafond ne sert qu'aux pages qui ne
# répondront jamais.
ATTENTE_TRAME_MS = 12000
CADENCE_SONDAGE_MS = 250


def pool_id(grille_type: str, grille_id: int) -> int:
    return PREFIXE[grille_type] + grille_id


def _decoder_trame(charge) -> dict:
    """Le contenu d'une trame socket.io, ou {} si ce n'en est pas une.

    Le format est `42["m",{...}]` : un préfixe numérique, puis un tableau dont
    le second élément porte les données. Tout le reste — battements de cœur,
    accusés de réception — ne nous concerne pas.
    """
    texte = charge if isinstance(charge, str) else charge.decode("utf-8", "replace")
    m = re.match(r"^\d+(\[.*)$", texte.strip(), re.S)
    if not m:
        return {}
    try:
        corps = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}
    if not (isinstance(corps, list) and len(corps) > 1 and isinstance(corps[1], dict)):
        return {}
    return corps[1]


def extraire(trames: list, pid: int = None) -> tuple:
    """Les pools et les matchs présents dans une liste de trames.

    Les trames arrivent par vagues et se complètent : la première annonce les
    grilles actives, une autre apporte le détail. On accumule donc plutôt que
    de prendre la dernière — c'est aussi ce qui permet de récupérer une grille
    précise noyée parmi les grilles en cours.
    """
    pools, matchs = {}, {}
    for charge in trames:
        etat = _decoder_trame(charge)
        for cle, valeur in etat.get("pools", {}).items():
            pools[int(cle)] = valeur
        for cle, valeur in etat.get("matches", {}).items():
            matchs[int(cle)] = valeur
    if pid is not None:
        pools = {k: v for k, v in pools.items() if k == pid}
    return pools, matchs


def composer(pool: dict, matchs: dict, grille_type: str, grille_id: int) -> dict:
    """Un enregistrement de grille, à partir du pool et de ses matchs.

    L'ordre des matchs est celui que donne le pool, pas celui du dictionnaire :
    c'est lui qui correspond aux lignes affichées et au codage de
    `strPoolResult`.
    """
    lignes = []
    for mid in pool.get("matches", []):
        m = matchs.get(mid)
        if not m:
            lignes.append({"match_id": mid, "absent_de_la_trame": True})
            continue
        debut = m.get("matchStart")
        lignes.append({
            "match_id": mid,
            "debut": datetime.fromtimestamp(debut, timezone.utc).isoformat()
                     if debut else None,
            "home": m.get("competitor1Name"),
            "away": m.get("competitor2Name"),
            # Les identifiants Sportradar sont la vraie clé de jointure : ils
            # rendent inutile tout rapprochement de noms.
            "home_id": m.get("competitor1Id"),
            "away_id": m.get("competitor2Id"),
            "score_home": m.get("regularScore1"),
            "score_away": m.get("regularScore2"),
            "statut": m.get("status"),
            # Absentes des grilles anciennes : Winamax ne les conserve pas.
            "cote_1": m.get("odds1"), "cote_N": m.get("oddsX"),
            "cote_2": m.get("odds2"),
        })

    fin = pool.get("poolEnd")
    return {
        "grille_id": grille_id, "grille_type": grille_type,
        "pool_id": pool.get("poolId"),
        "titre": pool.get("poolTitle"),
        "statut": pool.get("poolStatus"),
        "fin": datetime.fromtimestamp(fin, timezone.utc).isoformat() if fin else None,
        "collecte_le": datetime.now(timezone.utc).isoformat(),
        "mises_nettes": pool.get("netStakes"),
        "montant_distribue": pool.get("prizepoolAmount"),
        "montant_garanti": pool.get("guaranteedAmount"),
        "montant_ajoute": pool.get("addedAmount"),
        "resultat_code": pool.get("strPoolResult"),
        "rapports": pool.get("payout"),
        # La distribution du public. Absente en vieillissant, d'où l'urgence
        # d'une collecte quotidienne.
        "repartition": pool.get("repart"),
        "matches": lignes,
    }


def _ouvrir(playwright):
    nav = playwright.chromium.launch(headless=True)
    page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
    page.route("**/*", lambda r: r.abort()
               if r.request.resource_type in RESSOURCES_IGNOREES else r.continue_())
    return nav, page


def _ecouter(page) -> list:
    trames = []
    page.on("websocket", lambda ws: ws.on(
        "framereceived", lambda charge: trames.append(charge)))
    return trames


def _pool_complet(trames: list, pid: int) -> bool:
    """La grille demandée est-elle arrivée, avec tous ses matchs ?

    Le pool annonce la liste de ses matchs, et le détail de ceux-ci peut
    suivre dans une trame ultérieure. Attendre le pool seul rendrait parfois
    une grille sans équipes ni scores — on exige donc les deux.
    """
    pools, matchs = extraire(trames, pid)
    if not pools:
        return False
    pool = next(iter(pools.values()))
    attendus = pool.get("matches") or []
    return bool(attendus) and all(mid in matchs for mid in attendus)


def visiter(page, trames: list, url: str, attente: int = ATTENTE_TRAME_MS,
            pid: int = None):
    trames.clear()
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    if pid is None:
        page.wait_for_timeout(attente)
        return
    ecoule = 0
    while ecoule < attente:
        if _pool_complet(list(trames), pid):
            return
        page.wait_for_timeout(CADENCE_SONDAGE_MS)
        ecoule += CADENCE_SONDAGE_MS


def sauver(donnees: dict) -> Path:
    dossier = DATA_POOLS / donnees["grille_type"]
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{donnees['grille_id']}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return chemin


def collecter(grille_type: str, ids: list, pause=(1.0, 2.0), refaire=True):
    ok = vides = 0
    with sync_playwright() as p:
        nav, page = _ouvrir(p)
        trames = _ecouter(page)
        for rang, gid in enumerate(ids):
            chemin = DATA_POOLS / grille_type / f"{gid}.json"
            if chemin.exists() and not refaire:
                continue
            pid = pool_id(grille_type, gid)
            visiter(page, trames, BASE_URL.format(type=grille_type, id=gid), pid=pid)
            pools, matchs = extraire(list(trames), pid)
            if not pools:
                print(f"  [{grille_type}-{gid}] aucune trame pour cette grille")
                vides += 1
            else:
                donnees = composer(list(pools.values())[0], matchs, grille_type, gid)
                sauver(donnees)
                r = donnees["repartition"]
                cotes = sum(1 for m in donnees["matches"] if m.get("cote_1"))
                print(f"  [{grille_type}-{gid}] {donnees['statut']:<7} "
                      f"{donnees['fin'][:10] if donnees['fin'] else '?'} | "
                      f"{len(donnees['matches'])} matchs | "
                      f"{cotes} avec cotes | repartition : {'oui' if r else 'non'}")
                ok += 1
            if rang < len(ids) - 1:
                time.sleep(random.uniform(*pause))
        nav.close()
    print(f"\nBilan : {ok} enregistrée(s), {vides} sans trame.")
    return 0


def collecter_recentes(grille_type: str, combien: int, pause=(1.0, 2.0)):
    """Les grilles encore actives, plus celles qui viennent de se clore.

    C'EST LA COURSE CONTRE LA MONTRE. Les cotes et la répartition du public
    n'existent que sur les grilles récentes ; passé un certain âge, Winamax
    cesse de les servir. Une grille par jour bascule ainsi hors de portée, et
    rien ne permettra de la rattraper.
    """
    with sync_playwright() as p:
        nav, page = _ouvrir(p)
        trames = _ecouter(page)
        visiter(page, trames, URL_ACCUEIL)
        pools, _ = extraire(list(trames))
        nav.close()

    prefixe = PREFIXE[grille_type]
    numeros = sorted(pid - prefixe for pid in pools
                     if prefixe <= pid < prefixe + 1_000_000)
    if not numeros:
        print(f"Aucune grille active trouvée pour {grille_type}.")
        return 1
    haut = max(numeros)
    print(f"Grilles actives {grille_type} : {numeros}")
    cibles = list(range(haut, max(0, haut - combien), -1))
    print(f"Collecte de {len(cibles)} grille(s) : {cibles[0]} à {cibles[-1]}\n")
    return collecter(grille_type, cibles, pause, refaire=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Collecte des grilles par websocket")
    ap.add_argument("--type", default="grille7", choices=list(PREFIXE))
    ap.add_argument("--recentes", type=int, metavar="N",
                    help="les N dernières grilles, actives comprises (usage quotidien)")
    ap.add_argument("--ids", type=str, help="ex : 4168,4167")
    ap.add_argument("--from-id", type=int)
    ap.add_argument("--to-id", type=int)
    ap.add_argument("--pause", type=float, nargs=2, default=[1.0, 2.0],
                    metavar=("MIN", "MAX"))
    ap.add_argument("--sauter-existantes", action="store_true",
                    help="ne pas redemander ce qui est déjà collecté")
    args = ap.parse_args()

    pause = tuple(args.pause)
    refaire = not args.sauter_existantes
    if args.recentes:
        return collecter_recentes(args.type, args.recentes, pause)
    if args.ids:
        return collecter(args.type, [int(x) for x in args.ids.split(",")], pause, refaire)
    if args.from_id is not None and args.to_id is not None:
        pas = 1 if args.to_id >= args.from_id else -1
        ids = list(range(args.from_id, args.to_id + pas, pas))
        print(f"{len(ids)} identifiant(s), de {args.from_id} à {args.to_id}")
        return collecter(args.type, ids, pause, refaire)
    ap.error("Utiliser --recentes N, --ids a,b,c, ou --from-id X --to-id Y")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
