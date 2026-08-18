"""Scraper des grilles Winamax (Loto Foot 7 / 9 / 12).

Pages publiques, aucune connexion requise.

ÉTAT DE VALIDATION — À LIRE AVANT DE S'EN SERVIR
================================================
Les sélecteurs ci-dessous N'ONT JAMAIS ÉTÉ CONFRONTÉS AU SITE RÉEL. Ils
viennent d'une inspection manuelle d'une seule grille (grille7-4168), et
personne n'a encore vérifié qu'ils matchent.

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
    1. python scrape_grille.py --diagnostic 4168
    2. lire le rapport imprimé : il dit, sélecteur par sélecteur, combien
       d'éléments matchent et ce qu'ils contiennent
    3. si un sélecteur matche 0 élément, NE PAS deviner : envoyer le
       fichier diagnostic/*.html produit, les sélecteurs se corrigent
       dessus
    4. une fois validés, tester sur 2 ou 3 grilles et comparer le JSON à
       l'écran avant tout lot

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

# HYPOTHÈSE, PAS CERTITUDE. Les classes "sc-XXXXXX" viennent de
# styled-components et changent à chaque redéploiement du site ; ce sont les
# plus fragiles qui soient. Les classes littérales ("grid-line") sont écrites
# à la main dans le source et tiennent mieux.
SEL_MATCH_ROW = ".grid-line"
SEL_TEAM_NAME = "[class*='sc-jAZUkk']"
SEL_RAPPORT_ROW = "p[class*='sc-rnDvD']"

# Un score de football tient en un ou deux chiffres. Exiger cette borne évite
# de confondre le score avec une heure (« 18 - 21 »), une date ou une cote.
RE_SCORE = re.compile(r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\b")

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
        print(f"  [{grille_type}-{grille_id}] ANNULÉE par Winamax")
        return {"grille_id": grille_id, "grille_type": grille_type, "url": url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "statut": STATUT_ANNULEE, "matches": [], "rapports": [],
                "montant_distribue": None}

    if "terminee" not in plie:
        print(f"  [{grille_type}-{grille_id}] pas encore terminée")
        return None

    matches, lignes_ignorees = [], []
    rows = page.locator(SEL_MATCH_ROW)
    for i in range(rows.count()):
        texte = rows.nth(i).inner_text() or ""
        score = _score_de_ligne(texte)
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


def run_batch(grille_type: str, ids: list, pause: tuple = (3.0, 6.0)):
    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
        ok = ignorees = erreurs = 0
        for rang, gid in enumerate(ids):
            print(f"[{grille_type}-{gid}]")
            try:
                data = scrape_grille(page, grille_type, gid)
            except Exception as e:                       # noqa: BLE001
                print(f"  ERREUR {type(e).__name__} : {str(e)[:120]}")
                erreurs += 1
                continue
            if data is None:
                ignorees += 1
            else:
                save_grille(data)
                ok += 1
            if rang < len(ids) - 1:                      # pas d'attente après la dernière
                time.sleep(random.uniform(*pause))
        nav.close()
        print(f"\nBilan : {ok} sauvée(s), {ignorees} ignorée(s), {erreurs} en erreur.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Scraper de grilles Winamax (Loto Foot)")
    ap.add_argument("--type", choices=["grille7", "grille9", "grille12"], default="grille7")
    ap.add_argument("--from-id", type=int)
    ap.add_argument("--to-id", type=int)
    ap.add_argument("--ids", type=str, help="ex: 4168,4167,4166")
    ap.add_argument("--diagnostic", type=int, metavar="ID",
                    help="dump + rapport de sélecteurs sur un seul ID (à faire en premier)")
    args = ap.parse_args()

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
        return run_batch(args.type, [int(x) for x in args.ids.split(",")]) or 0
    if args.from_id is not None and args.to_id is not None:
        if args.to_id < args.from_id:
            ap.error("--to-id est inférieur à --from-id : l'intervalle serait vide.")
        return run_batch(args.type, list(range(args.from_id, args.to_id + 1))) or 0
    ap.error("Utiliser --diagnostic ID, --ids a,b,c, ou --from-id X --to-id Y")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
