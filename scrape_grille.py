"""Scraper des grilles Winamax (Loto Foot 7 / 9 / 12).

Pages publiques, aucune connexion requise.

ÉTAT DE VALIDATION — À LIRE AVANT DE S'EN SERVIR
================================================
Sélecteurs confrontés au site le 18 août 2026 sur grille7-4168, depuis une
machine en France, puis rejoués hors ligne élément par élément. Les trois
trouvent leurs éléments et le JSON produit est cohérent : 7 matchs, et la
somme des rapports retombe sur le montant distribué à l'arrondi près.

Cette confrontation a révélé un bug bloquant que l'inspection à l'œil ne
pouvait pas voir : les sélecteurs matchaient, mais AUCUN score n'était lu
(voir le commentaire de RE_SCORE). Corrigé, avec un test de non-régression
dans test_selecteurs.py.

RESTE NON VÉRIFIÉ : grille9 et grille12, jamais ouverts ; une grille
annulée, dont aucune page n'a encore été vue ; la comparaison écran par
écran d'une deuxième grille.

La vérification n'a pas pu se faire depuis un environnement d'exécution
distant : winamax.fr répond 403 CloudFront à toute requête venant d'une IP
de centre de données hors de France, et un vrai Chromium headless s'y fait
couper la connexion. Ce n'est pas un blocage anti-robot contournable par un
en-tête : c'est le filtrage géographique d'un opérateur agréé ANJ.

CONSÉQUENCE POUR L'ARCHITECTURE : ce script tourne SUR TA MACHINE, en
France. Il ne peut pas tourner dans GitHub Actions — les runners sont eux
aussi des IP de centre de données américaines et se font bloquer pareil.
Contrairement au dépôt factxi-sportlab, il n'y aura donc pas de collecte
automatisée côté serveur.

MARCHE À SUIVRE, DANS CET ORDRE
    1. python test_parsing.py && python test_selecteurs.py
    2. python scrape_grille.py --diagnostic 4168
    3. lire le rapport imprimé : il dit, sélecteur par sélecteur, combien
       d'éléments matchent et ce qu'ils contiennent
    4. si un sélecteur matche 0 élément, NE PAS deviner : envoyer le
       fichier diagnostic/*.html produit, les sélecteurs se corrigent
       dessus
    5. tester sur 2 ou 3 grilles et comparer le JSON à l'écran avant tout
       lot — les sélecteurs peuvent matcher et extraire faux, c'est
       précisément ce qui s'est produit le 18 août

CONDITIONS D'UTILISATION : l'accès automatisé est probablement contraire
aux CGU de Winamax. Usage strictement personnel, sans republication, et
avec un rythme volontairement lent. C'est ton arbitrage, il est noté ici
pour qu'il soit explicite.
"""

import argparse
import json
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.winamax.fr/paris-sportifs/grilles/{type}-{id}"
DATA_DIR = Path(__file__).parent / "data" / "grilles"
DIAGNOSTIC_DIR = Path(__file__).parent / "diagnostic"

# CONFRONTÉS AU SITE LE 18 AOÛT 2026 sur grille7-4168, et vérifiés élément par
# élément : 7 lignes, 14 noms d'équipes, 3 lignes de rapport. Les classes
# "sc-XXXXXX" viennent de styled-components et changent à chaque redéploiement
# du site ; ce sont les plus fragiles qui soient. La classe littérale
# ("grid-line") est écrite à la main dans le source et tient mieux.
SEL_MATCH_ROW = ".grid-line"
SEL_TEAM_NAME = "[class*='sc-jAZUkk']"
SEL_RAPPORT_ROW = "p[class*='sc-rnDvD']"
# Le score a son propre élément. Le lire là plutôt que dans le texte de la
# ligne évite d'avoir à le distinguer des cotes et du numéro de match.
SEL_SCORE = "[class*='sc-jYPihs']"

# Un score de football tient en un ou deux chiffres. Exiger cette borne évite
# de confondre le score avec une heure (« 18 - 21 »), une date ou une cote.
#
# PAS DE \b À GAUCHE. Mesuré sur la vraie page : inner_text() colle le nom de
# l'équipe au score, « Reims1N2Dunkerque3 - 3 ». Entre « e » et « 3 » il n'y a
# pas de frontière de mot, donc \b ne matchait rien et AUCUN score n'était lu
# — sur les sept lignes de la grille testée, sept échecs. On interdit donc un
# chiffre adjacent, ce qui protège toujours de « 123 - 4 », mais on tolère une
# lettre collée.
RE_SCORE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})(?!\d)")

STATUT_TERMINEE = "terminee"
STATUT_EN_COURS = "en_cours"
STATUT_ANNULEE = "annulee"


def _sans_accents(texte: str) -> str:
    """« Terminée », « TERMINÉE » et « terminee » doivent se valoir.

    Le test d'origine cherchait la chaîne exacte « Terminée » : une casse ou
    un accent différents sur le site auraient fait passer toutes les grilles
    pour non terminées, silencieusement, et le lot serait ressorti vide sans
    qu'on comprenne pourquoi.
    """
    plie = unicodedata.normalize("NFD", texte or "")
    return "".join(c for c in plie if unicodedata.category(c) != "Mn").lower()


def _parse_montant(text: str):
    """Un montant français vers un float, ou None si vraiment illisible.

    QUATRE ESPACES DIFFÉRENTES CIRCULENT dans les pages françaises, et la
    version d'origine n'en retirait que deux. Mesuré : « 1<U+00A0>234,56 € »,
    l'espace insécable la plus courante, renvoyait None. Le montant partait
    alors dans le JSON en `null` sans que rien ne le signale.

    DEUX CONVENTIONS DÉCIMALES COEXISTENT aussi. « 1.234,56 » (point pour les
    milliers) devenait « 1.234.56 » puis None. On décide donc du séparateur
    décimal d'après le dernier symbole rencontré, plutôt que de supposer.
    """
    if text is None:
        return None
    net = str(text)
    for espace in (" ", " ", " ", " ", " "):
        net = net.replace(espace, "")
    net = net.replace("€", "").replace("EUR", "").strip()
    if not net:
        return None

    dernier_point, derniere_virgule = net.rfind("."), net.rfind(",")
    if dernier_point > derniere_virgule:
        net = net.replace(",", "")                      # virgule = milliers
    elif derniere_virgule > dernier_point:
        net = net.replace(".", "").replace(",", ".")    # point = milliers
    try:
        return float(net)
    except ValueError:
        return None


def _score_de_ligne(texte: str):
    """Le score d'une ligne, ou None.

    ON NE PREND PAS LE PREMIER NOMBRE VENU. Le texte d'une ligne contient
    aussi l'heure du match, parfois une date, et les cotes. Un motif large
    comme (\\d+)-(\\d+) attrapait « 18 - 21 » d'un créneau horaire aussi bien
    qu'un score, et rien ne distinguait ensuite le bon du mauvais : le JSON
    sortait plausible et faux, ce qui est le pire des deux mondes.

    On borne donc à deux chiffres et on refuse d'arbitrer quand plusieurs
    candidats coexistent — l'ambiguïté remonte, elle ne se tranche pas ici.
    """
    trouves = RE_SCORE.findall(texte or "")
    plausibles = [(int(a), int(b)) for a, b in trouves if int(a) <= 20 and int(b) <= 20]
    if len(plausibles) != 1:
        return None
    return plausibles[0]


def _score_de_row(row):
    """Le score d'une ligne du DOM : l'élément dédié d'abord, le texte ensuite.

    DEUX CHEMINS PLUTÔT QU'UN, parce qu'ils ne meurent pas de la même chose.
    L'élément dédié (SEL_SCORE) est sans ambiguïté — il ne contient que le
    score — mais sa classe est un « sc-XXXXXX » de styled-components, qui
    changera au prochain redéploiement du site. Le texte de la ligne, lui,
    survit aux changements de classes mais demande d'écarter les cotes et le
    numéro de match.

    On prend donc le précis quand il est là, et on retombe sur le robuste
    quand il a disparu, plutôt que de tout arrêter.
    """
    cellule = row.locator(SEL_SCORE)
    if cellule.count() == 1:
        score = _score_de_ligne(cellule.inner_text() or "")
        if score is not None:
            return score
    return _score_de_ligne(row.inner_text() or "")


def scrape_grille(page, grille_type: str, grille_id: int):
    """Une grille terminée, ou None avec un motif imprimé."""
    url = BASE_URL.format(type=grille_type, id=grille_id)
    page.goto(url, timeout=20000)

    try:
        page.wait_for_selector(SEL_MATCH_ROW, timeout=10000)
    except PlaywrightTimeoutError:
        print(f"  [{grille_type}-{grille_id}] absente : aucun élément « {SEL_MATCH_ROW} »")
        return None

    # inner_text() et non text_content() : le second colle les textes de deux
    # éléments voisins sans séparateur, ce qui casse la recherche de « Montant
    # distribué » dès que le libellé et la valeur vivent dans deux balises.
    plein = page.locator("body").inner_text() or ""
    plie = _sans_accents(plein)

    # LA GRILLE ANNULÉE N'EST PAS UNE GRILLE ABSENTE, et le brief le demandait
    # explicitement. Winamax annule une liste quand trop de matchs sont donnés
    # gagnants par forfait ou report. La confondre avec un trou fausserait plus
    # tard toute étude de biais : une annulation est une information.
    if "annul" in plie:
        # L'INDICE VOYAGE AVEC LA CONCLUSION. Ce test cherche « annul » dans
        # TOUT le texte de la page : un bouton « Annuler » d'une bannière
        # cookies suffirait à faire passer une grille normale pour annulée, et
        # le JSON n'en garderait aucune trace. Aucune page de grille annulée
        # n'ayant encore été observée, on ne peut pas resserrer le motif sans
        # deviner — alors on enregistre le contexte, et un faux positif se
        # verra en relisant le fichier au lieu de se fondre dans la base.
        pos = plie.find("annul")
        indice = " ".join(plie[max(0, pos - 60):pos + 60].split())
        print(f"  [{grille_type}-{grille_id}] ANNULÉE par Winamax — indice : {indice}")
        return {"grille_id": grille_id, "grille_type": grille_type, "url": url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "statut": STATUT_ANNULEE, "matches": [], "rapports": [],
                "montant_distribue": None, "annulation_indice": indice}

    if "terminee" not in plie:
        print(f"  [{grille_type}-{grille_id}] pas encore terminée")
        return None

    matches, lignes_ignorees = [], []
    rows = page.locator(SEL_MATCH_ROW)
    for i in range(rows.count()):
        texte = rows.nth(i).inner_text() or ""
        score = _score_de_row(rows.nth(i))
        if score is None:
            lignes_ignorees.append({"ligne": i, "motif": "score introuvable ou ambigu",
                                    "texte": texte[:120]})
            continue
        equipes = rows.nth(i).locator(SEL_TEAM_NAME)
        if equipes.count() < 2:
            lignes_ignorees.append({"ligne": i, "motif": f"{equipes.count()} équipe(s) lue(s)",
                                    "texte": texte[:120]})
            continue
        dom, ext = score
        matches.append({
            "home": (equipes.nth(0).inner_text() or "").strip(),
            "away": (equipes.nth(1).inner_text() or "").strip(),
            "score_home": dom, "score_away": ext,
            # 1/N/2 déduit du SCORE, jamais d'un indice visuel : les classes de
            # couleur changent à chaque redéploiement du site.
            "resultat": "1" if dom > ext else "2" if ext > dom else "N",
        })

    rapports = []
    rap = page.locator(SEL_RAPPORT_ROW)
    for i in range(rap.count()):
        texte = rap.nth(i).inner_text() or ""
        if "nombre" in _sans_accents(texte) and "resultat" in _sans_accents(texte):
            continue                                   # ligne d'en-tête
        cellules = rap.nth(i).locator("span")
        if cellules.count() < 3:
            continue
        brut = (cellules.nth(1).inner_text() or "").strip()
        nombre = None
        chiffres = re.sub(r"[^\d]", "", brut)
        if chiffres:
            nombre = int(chiffres)
        rapports.append({
            "rang": (cellules.nth(0).inner_text() or "").strip(),
            "nombre_gagnants": nombre,
            "montant": _parse_montant((cellules.nth(2).inner_text() or "").strip()),
        })

    montant = None
    m = re.search(r"montant distribue\s*:?\s*([\d\s  .,]+)", plie)
    if m:
        montant = _parse_montant(m.group(1))

    if not matches:
        print(f"  [{grille_type}-{grille_id}] AUCUN match extrait alors que la page "
              f"existe — sélecteurs probablement périmés, relancer --diagnostic")
        return None

    resultat = {
        "grille_id": grille_id, "grille_type": grille_type, "url": url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "statut": STATUT_TERMINEE,
        "matches": matches, "rapports": rapports, "montant_distribue": montant,
    }
    # LES LIGNES ÉCARTÉES VOYAGENT AVEC LA GRILLE. Les taire donnerait un JSON
    # d'apparence complète auquel il manque un match, et personne ne s'en
    # apercevrait en relisant le fichier six mois plus tard.
    if lignes_ignorees:
        resultat["lignes_ignorees"] = lignes_ignorees
        print(f"    {len(lignes_ignorees)} ligne(s) écartée(s), conservées dans le JSON")
    return resultat


def save_grille(data: dict):
    dossier = DATA_DIR / data["grille_type"]
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{data['grille_id']}.json"
    chemin.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {chemin}")


def diagnostic_dump(page, grille_type: str, grille_id: int):
    """Dump le HTML ET teste chaque sélecteur, en imprimant ce qu'il trouve.

    La version d'origine sauvait le HTML et laissait comparer à l'œil. C'est
    faisable mais long, et surtout ça ne se transmet pas : pour qu'un tiers
    corrige les sélecteurs il faudrait lui faire relire toute la page. Le
    rapport ci-dessous tient en vingt lignes et suffit à dire lequel est mort
    et par quoi le remplacer.
    """
    url = BASE_URL.format(type=grille_type, id=grille_id)
    page.goto(url, timeout=25000)
    page.wait_for_timeout(3500)
    DIAGNOSTIC_DIR.mkdir(exist_ok=True)
    html = DIAGNOSTIC_DIR / f"{grille_type}-{grille_id}.html"
    html.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(DIAGNOSTIC_DIR / f"{grille_type}-{grille_id}.png"), full_page=True)

    print(f"\n  URL       : {url}")
    print(f"  HTML      : {html}  ({html.stat().st_size // 1024} Ko)")
    print(f"  capture   : {DIAGNOSTIC_DIR / f'{grille_type}-{grille_id}.png'}")

    plie = _sans_accents(page.locator("body").inner_text() or "")
    for mot, libelle in (("terminee", "« Terminée »"), ("annul", "« annulée »"),
                         ("montant distribue", "« Montant distribué »")):
        print(f"  {libelle:<22} {'présent' if mot in plie else 'ABSENT'}")

    print("\n  SÉLECTEURS")
    for nom, sel in (("SEL_MATCH_ROW", SEL_MATCH_ROW),
                     ("SEL_TEAM_NAME", SEL_TEAM_NAME),
                     ("SEL_RAPPORT_ROW", SEL_RAPPORT_ROW)):
        loc = page.locator(sel)
        n = loc.count()
        etat = "OK" if n else "AUCUN ÉLÉMENT — sélecteur à corriger"
        print(f"    {nom:<16} {sel:<26} {n:>4} élément(s)   {etat}")
        for j in range(min(n, 2)):
            extrait = " ".join((loc.nth(j).inner_text() or "").split())[:90]
            print(f"        [{j}] {extrait}")

    if page.locator(SEL_MATCH_ROW).count():
        premiere = page.locator(SEL_MATCH_ROW).first.inner_text() or ""
        print("\n  LECTURE DU SCORE sur la première ligne")
        print(f"    texte  : {' '.join(premiere.split())[:110]}")
        print(f"    score  : {_score_de_ligne(premiere) or 'introuvable ou ambigu'}")

    print("\n  Si un sélecteur est à zéro, ne pas deviner : envoyer le fichier HTML.\n")


def _chemin_grille(grille_type: str, grille_id: int) -> Path:
    return DATA_DIR / grille_type / f"{grille_id}.json"


def run_batch(grille_type: str, ids: list, pause: tuple = (3.0, 6.0),
              lot: int = 0, pause_lot: tuple = (90.0, 240.0),
              arret_erreurs: int = 5, arret_absences: int = 40,
              refaire: bool = False):
    """Un lot de grilles, interruptible et reprenable.

    TROIS GARDE-FOUS, parce qu'un lot de plusieurs milliers d'identifiants ne
    se surveille pas à l'œil pendant des heures.

    1. CE QUI EST DÉJÀ EN BASE N'EST PAS REDEMANDÉ. Une grille terminée ne
       change plus : la relire coûterait une requête pour un fichier
       identique. C'est aussi ce qui rend une reprise gratuite — relancer la
       même commande ne refait que ce qui manque. `refaire=True` force.

    2. UNE SÉRIE D'ERREURS ARRÊTE TOUT. La version d'origine comptait les
       erreurs et continuait : si le site coupait à la centième grille, les
       quatre mille suivantes défilaient en pure perte, et le bilan final
       n'aurait dit qu'un grand nombre. On s'arrête au bout de
       `arret_erreurs` erreurs d'affilée, en disant où reprendre.

    3. UNE SÉRIE D'ABSENCES ARRÊTE AUSSI. Descendre jusqu'au début des
       archives finit forcément par ne plus rien trouver. Mais un blocage
       renvoyant une page vide ressemble EXACTEMENT à une fin d'archive :
       les deux se traitent donc pareil, arrêt et vérification humaine.
       Continuer serait choisir la plus optimiste des deux lectures.

    Les compteurs se remettent à zéro dès qu'une grille passe : ce sont bien
    des séries consécutives, pas des totaux.
    """
    ok = absentes = erreurs = deja = 0
    erreurs_suite = absences_suite = 0
    motif_arret, rang_arret = None, len(ids)

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
        demandees = 0                        # grilles réellement allées chercher
        for rang, gid in enumerate(ids):
            if not refaire and _chemin_grille(grille_type, gid).exists():
                deja += 1
                continue                     # aucune requête, donc aucune attente

            print(f"[{grille_type}-{gid}]")
            try:
                data = scrape_grille(page, grille_type, gid)
            except Exception as e:           # noqa: BLE001
                print(f"  ERREUR {type(e).__name__} : {str(e)[:120]}")
                erreurs += 1
                erreurs_suite += 1
                absences_suite = 0
                if erreurs_suite >= arret_erreurs:
                    motif_arret = f"{erreurs_suite} erreurs d'affilée"
                    rang_arret = rang
                    break
            else:
                if data is None:
                    absentes += 1
                    absences_suite += 1
                    if absences_suite >= arret_absences:
                        motif_arret = (f"{absences_suite} grilles introuvables d'affilée — "
                                       f"soit les archives s'arrêtent ici, soit l'accès est "
                                       f"coupé. Ouvrir une URL dans un navigateur pour trancher")
                        rang_arret = rang
                        break
                else:
                    save_grille(data)
                    ok += 1
                    absences_suite = 0
                erreurs_suite = 0

            demandees += 1
            if rang == len(ids) - 1:
                continue                     # pas d'attente après la dernière
            if lot and demandees % lot == 0:
                repos = random.uniform(*pause_lot)
                print(f"  --- lot de {lot} terminé, pause de {repos / 60:.1f} min ---")
                time.sleep(repos)
            else:
                time.sleep(random.uniform(*pause))
        nav.close()

    print(f"\nBilan : {ok} sauvée(s), {deja} déjà en base, "
          f"{absentes} introuvable(s), {erreurs} en erreur.")

    restants = ids[rang_arret:] if motif_arret else []
    if motif_arret:
        print(f"\nARRÊT : {motif_arret}.")
        print(f"Il reste {len(restants)} identifiant(s), de {restants[0]} à {restants[-1]}.")
        print("Reprendre avec :")
        print(f"  python scrape_grille.py --type {grille_type} "
              f"--from-id {restants[0]} --to-id {restants[-1]}")
        print("Ce qui est déjà en base ne sera pas redemandé.")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Scraper de grilles Winamax (Loto Foot)")
    ap.add_argument("--type", choices=["grille7", "grille9", "grille12"], default="grille7")
    ap.add_argument("--from-id", type=int)
    ap.add_argument("--to-id", type=int)
    ap.add_argument("--ids", type=str, help="ex: 4168,4167,4166")
    ap.add_argument("--diagnostic", type=int, metavar="ID",
                    help="dump + rapport de sélecteurs sur un seul ID (à faire en premier)")
    ap.add_argument("--lot", type=int, default=0, metavar="N",
                    help="pause longue toutes les N grilles (0 = pas de lots)")
    ap.add_argument("--pause", type=float, nargs=2, default=[3.0, 6.0],
                    metavar=("MIN", "MAX"), help="attente entre deux grilles, en secondes")
    ap.add_argument("--pause-lot", type=float, nargs=2, default=[90.0, 240.0],
                    metavar=("MIN", "MAX"), help="attente entre deux lots, en secondes")
    ap.add_argument("--arret-erreurs", type=int, default=5, metavar="N",
                    help="arrêter après N erreurs d'affilée")
    ap.add_argument("--arret-absences", type=int, default=40, metavar="N",
                    help="arrêter après N grilles introuvables d'affilée")
    ap.add_argument("--refaire", action="store_true",
                    help="redemander aussi les grilles déjà en base")
    args = ap.parse_args()

    reglages = dict(pause=tuple(args.pause), lot=args.lot, pause_lot=tuple(args.pause_lot),
                    arret_erreurs=args.arret_erreurs, arret_absences=args.arret_absences,
                    refaire=args.refaire)

    # `is not None` et non la valeur : un ID valant 0 est faux en booléen et
    # aurait fait tomber la commande dans la branche d'erreur.
    if args.diagnostic is not None:
        with sync_playwright() as p:
            nav = p.chromium.launch(headless=True)
            diagnostic_dump(nav.new_page(locale="fr-FR", timezone_id="Europe/Paris"),
                            args.type, args.diagnostic)
            nav.close()
        return 0
    if args.ids:
        return run_batch(args.type, [int(x) for x in args.ids.split(",")], **reglages)
    if args.from_id is not None and args.to_id is not None:
        # UN INTERVALLE DÉCROISSANT EST UNE DEMANDE, PAS UNE FAUTE DE FRAPPE.
        # Le garde-fou d'avant refusait --from-id 4170 --to-id 1, alors que
        # commencer par les grilles récentes est le sens naturel d'un
        # rattrapage : ce qui vient d'être joué intéresse plus que 2011, et si
        # le lot s'interrompt, on s'est arrêté au bon bout. Le défaut qu'on
        # voulait éviter était un lot vide EN SILENCE : le sens du parcours est
        # donc annoncé, et il n'y a plus rien de muet.
        if args.to_id < args.from_id:
            ids = list(range(args.from_id, args.to_id - 1, -1))
            print(f"Parcours décroissant : {args.from_id} vers {args.to_id}, "
                  f"{len(ids)} identifiant(s).")
        else:
            ids = list(range(args.from_id, args.to_id + 1))
            print(f"Parcours croissant : {args.from_id} vers {args.to_id}, "
                  f"{len(ids)} identifiant(s).")
        return run_batch(args.type, ids, **reglages)
    ap.error("Utiliser --diagnostic ID, --ids a,b,c, ou --from-id X --to-id Y")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
