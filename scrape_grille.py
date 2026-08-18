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

# Un match annulé — forfait, report — est donné gagnant sur les trois issues.
# Ce n'est ni un 1, ni un N, ni un 2 : lui en attribuer un fausserait un futur
# calcul Elo comme une étude de biais. Il lui faut sa propre valeur.
RESULTAT_ANNULE = "annule"

# Attente d'un signe de règlement avant de conclure qu'il n'y en a pas. Elle
# ne coûte QUE sur les grilles qui en semblent dépourvues : dès que le mot
# paraît, on repart. Voir _texte_regle().
# CE QU'ON NE TÉLÉCHARGE PAS. On lit du texte : images, polices et vidéos ne
# servent à rien ici, et ce sont elles qui pèsent. Les bloquer accélère la
# collecte ET allège le site d'autant de requêtes — les deux vont dans le même
# sens, ce qui est assez rare pour être noté.
#
# LES FEUILLES DE STYLE, EN REVANCHE, RESTENT. inner_text() ne rend que ce qui
# est visible : sans CSS, des éléments masqués referaient surface et le texte
# lu ne serait plus celui de la page. On gagnerait quelques dixièmes de seconde
# contre le risque de tout fausser.
RESSOURCES_IGNOREES = {"image", "media", "font"}

REGLEMENT_ESSAIS = 5
REGLEMENT_PAUSE_MS = 1000

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


# Plafond du texte libre : un score de football tient sous 20 buts, et cette
# borne est ce qui distingue « 2 - 1 » d'un créneau « 18 - 21 ». Elle ne vaut
# QUE pour le texte d'une ligne entière, où l'un et l'autre se côtoient.
MAX_BUTS_TEXTE = 20

# Plafond de la cellule dédiée : elle ne contient que le score, il n'y a donc
# rien à en distinguer. Mesuré sur la grille 3740 : « Western Bulldogs 29 - 52
# Hawthorn Hawks », du football australien sur une grille Winamax. Le plafond
# à 20 l'écartait comme implausible — une donnée parfaitement lisible perdue
# par une prudence appliquée au mauvais endroit.
MAX_BUTS_CELLULE = 99


def _score_de_ligne(texte: str, maximum: int = MAX_BUTS_TEXTE):
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
    plausibles = [(int(a), int(b)) for a, b in trouves
                  if int(a) <= maximum and int(b) <= maximum]
    if len(plausibles) != 1:
        return None
    return plausibles[0]


def _match_annule(row) -> bool:
    """Le match de cette ligne a-t-il été annulé ?

    Observé sur grille7-4170 : la cellule qui porte d'habitude « 3 - 0 »
    contient « Annulé ». Le DOM le confirme d'une deuxième façon — sur une
    ligne normale un seul des trois boutons 1/N/2 porte la classe des issues
    gagnantes, sur celle-ci les trois la portent. On lit quand même le texte
    plutôt que ces classes : « Annulé » restera écrit ainsi au prochain
    redéploiement du site, « hsGWid » non.
    """
    cellule = row.locator(SEL_SCORE)
    if cellule.count() == 1:
        return "annul" in _sans_accents(cellule.inner_text() or "")
    return "annul" in _sans_accents(row.inner_text() or "")


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
        score = _score_de_ligne(cellule.inner_text() or "", maximum=MAX_BUTS_CELLULE)
        if score is not None:
            return score
    return _score_de_ligne(row.inner_text() or "")


def _texte_regle(page) -> str:
    """Le texte de la page, une fois les résultats arrivés — ou après attente.

    wait_for_selector() REND LA MAIN DÈS LA PREMIÈRE LIGNE, pas quand la page
    est prête. Les lignes de match arrivent avec la structure de la grille ;
    les scores, le statut et les mentions d'annulation viennent après, d'un
    second rendu. Lire le texte dans cet intervalle donne une page à moitié
    peuplée — et, faute d'y trouver « Terminée », la conclusion « pas encore
    terminée » sur une grille qui l'était depuis des mois.

    Mesuré : sur 500 grilles collectées, 3 sont tombées dans cet intervalle —
    3836, 4008 et 4157 — et sont ressorties comme des trous. Le navigateur,
    lui, affiche bien leurs scores.

    On attend donc un signe de règlement plutôt qu'un délai fixe : les grilles
    déjà prêtes ne paient rien, et seules celles qui semblent vides coûtent
    quelques secondes.
    """
    plie = ""
    for essai in range(REGLEMENT_ESSAIS):
        plie = _sans_accents(page.locator("body").inner_text() or "")
        if "terminee" in plie or "annul" in plie:
            return plie
        if essai < REGLEMENT_ESSAIS - 1:
            page.wait_for_timeout(REGLEMENT_PAUSE_MS)
    return plie


def scrape_grille(page, grille_type: str, grille_id: int):
    """Une grille terminée, ou None avec un motif imprimé."""
    url = BASE_URL.format(type=grille_type, id=grille_id)
    # « domcontentloaded » et non « load » : inutile d'attendre la dernière
    # image ou le dernier traceur pour commencer à chercher les lignes de
    # match. C'est wait_for_selector, juste après, qui décide que la page est
    # prête — sur un critère qui nous concerne, au lieu d'un critère de
    # navigateur.
    page.goto(url, timeout=20000, wait_until="domcontentloaded")

    try:
        page.wait_for_selector(SEL_MATCH_ROW, timeout=10000)
    except PlaywrightTimeoutError:
        print(f"  [{grille_type}-{grille_id}] absente : aucun élément « {SEL_MATCH_ROW} »")
        return None

    # inner_text() et non text_content() : le second colle les textes de deux
    # éléments voisins sans séparateur, ce qui casse la recherche de « Montant
    # distribué » dès que le libellé et la valeur vivent dans deux balises.
    plie = _texte_regle(page)

    # « annul » quelque part dans la page suffit à passer la grille en revue,
    # mais ne conclut plus rien : voir plus bas, après l'extraction.
    terminee = "terminee" in plie
    mention_annul = "annul" in plie
    if not terminee and not mention_annul:
        print(f"  [{grille_type}-{grille_id}] pas encore terminée")
        return None

    matches, lignes_ignorees = [], []
    rows = page.locator(SEL_MATCH_ROW)
    for i in range(rows.count()):
        texte = rows.nth(i).inner_text() or ""
        equipes = rows.nth(i).locator(SEL_TEAM_NAME)
        if equipes.count() < 2:
            lignes_ignorees.append({"ligne": i, "motif": f"{equipes.count()} équipe(s) lue(s)",
                                    "texte": texte[:120]})
            continue
        dom_nom = (equipes.nth(0).inner_text() or "").strip()
        ext_nom = (equipes.nth(1).inner_text() or "").strip()

        # L'ANNULATION SE TESTE AVANT LE SCORE, sinon ce match partirait dans
        # les lignes écartées faute de score lisible. Ce serait dommage deux
        # fois : on perdrait les deux équipes, et surtout on confondrait « pas
        # de score parce que tout le monde a gagné » avec « pas de score parce
        # qu'on n'a pas su lire ». La première est une donnée, la seconde un
        # aveu d'échec, et une base ne peut pas les ranger au même endroit.
        if _match_annule(rows.nth(i)):
            matches.append({
                "home": dom_nom, "away": ext_nom,
                "score_home": None, "score_away": None,
                "resultat": RESULTAT_ANNULE, "tous_gagnants": True,
            })
            print(f"    match annulé : {dom_nom} - {ext_nom} (toutes issues gagnantes)")
            continue

        score = _score_de_row(rows.nth(i))
        if score is None:
            lignes_ignorees.append({"ligne": i, "motif": "score introuvable ou ambigu",
                                    "texte": texte[:120]})
            continue
        dom, ext = score
        matches.append({
            "home": dom_nom, "away": ext_nom,
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

    # ON DÉCIDE APRÈS AVOIR VU LES MATCHS, PAS AVANT.
    #
    # La version précédente concluait « grille annulée » dès que le mot
    # « annul » apparaissait quelque part dans la page, et rendait aussitôt
    # des listes vides. Or un SEUL match annulé — forfait, report, tout le
    # monde gagnant sur cette ligne — écrit ce mot dans une page par ailleurs
    # parfaitement normale. La grille entière partait alors à la poubelle avec
    # ses six autres scores, sous une étiquette fausse.
    #
    # Une grille dont on a su extraire des matchs n'est pas une grille
    # annulée : la présence de matchs prime sur la présence d'un mot. La
    # mention est conservée à part, parce qu'elle reste une information — et
    # parce qu'un jour elle signalera peut-être une vraie annulation.
    # UNE GRILLE N'EST TERMINÉE QUE SI LA PAGE LE DIT.
    #
    # Relevé sur la grille 3836 : un match sans résultat (icône « i »), un
    # autre annulé, aucune mention « Terminée », et en bas « Montant GARANTI »
    # au lieu de « Montant distribué » — c'est ce qu'affiche une grille avant
    # son règlement. Rien n'a encore été payé, il n'y a donc pas de rapports.
    #
    # Or le mot « annulé » de l'autre ligne suffisait à franchir le filtre du
    # haut, et six matchs lisibles suffisaient ensuite à conclure « terminée ».
    # On aurait enregistré une grille non réglée comme réglée, avec des
    # rapports vides — et le contrôle de cohérence n'aurait rien pu en dire,
    # faute de montant à comparer. Le pire des cas : faux, et silencieux.
    #
    # La présence de matchs ne prouve donc que l'existence de la grille, pas
    # son règlement. Les deux se constatent séparément.
    if matches and not terminee:
        print(f"  [{grille_type}-{grille_id}] existe mais NON RÉGLÉE : "
              f"{len(matches)} match(s) lisible(s), aucune mention « Terminée » "
              f"— probablement un match sans résultat")
        return None

    indice = None
    if matches:
        # UNE MENTION EXPLIQUÉE N'EST PLUS UN SIGNAL. Si un match annulé a été
        # relevé, le mot « annulé » dans la page est justement son fait : le
        # noter en plus noierait le seul cas qui mérite un coup d'œil, celui
        # d'une mention qu'aucun match n'explique — un bouton de bannière, ou
        # une vraie annulation qu'on aurait mal lue.
        explique = any(m["resultat"] == RESULTAT_ANNULE for m in matches)
        if mention_annul and not explique:
            pos = plie.find("annul")
            indice = " ".join(plie[max(0, pos - 60):pos + 60].split())
            print(f"    mention d'annulation inexpliquée, {len(matches)} match(s) "
                  f"extrait(s) — conservée dans le JSON")
    elif mention_annul:
        # Aucun match lisible ET le mot est là : c'est le cas où l'annulation
        # de toute la liste est l'explication la plus probable. Winamax annule
        # une liste quand trop de matchs sont donnés gagnants par forfait ou
        # report, et une annulation est une information : la confondre avec un
        # trou fausserait plus tard toute étude de biais.
        pos = plie.find("annul")
        indice = " ".join(plie[max(0, pos - 60):pos + 60].split())
        print(f"  [{grille_type}-{grille_id}] ANNULÉE par Winamax — indice : {indice}")
        return {"grille_id": grille_id, "grille_type": grille_type, "url": url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "statut": STATUT_ANNULEE, "matches": [], "rapports": [],
                "montant_distribue": None, "annulation_indice": indice}
    else:
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
    if indice:
        resultat["mention_annulation"] = indice
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


def _bloquer_ressources_inutiles(route):
    if route.request.resource_type in RESSOURCES_IGNOREES:
        route.abort()
    else:
        route.continue_()


def _chemin_grille(grille_type: str, grille_id: int) -> Path:
    return DATA_DIR / grille_type / f"{grille_id}.json"


def run_batch(grille_type: str, ids: list, pause: tuple = (3.0, 6.0),
              lot: int = 0, pause_lot: tuple = (90.0, 240.0),
              arret_erreurs: int = 5, arret_absences: int = 40,
              arret_identiques: int = 3, refaire: bool = False,
              alleger: bool = True):
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

    4. UNE SÉRIE DE GRILLES IDENTIQUES ARRÊTE AUSSI. C'est le seul échec qui
       ne ressemble pas à un échec : si le site se met à servir la même page
       quel que soit l'identifiant demandé — repli après un excès de
       requêtes, redirection — tout se passe bien en apparence. Aucune
       erreur, aucune absence, des fichiers qui s'écrivent. Au matin, des
       milliers de copies du même match, et rien pour les distinguer d'une
       collecte saine. Trois extractions consécutives rigoureusement
       identiques suffisent à arrêter : deux grilles différentes ne
       partagent pas sept matchs ET sept scores.

    Les compteurs se remettent à zéro dès qu'une grille passe : ce sont bien
    des séries consécutives, pas des totaux.
    """
    ok = absentes = erreurs = deja = 0
    erreurs_suite = absences_suite = 0
    signature_precedente, identiques_suite = None, 0
    motif_arret, rang_arret = None, len(ids)

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")
        if alleger:
            page.route("**/*", _bloquer_ressources_inutiles)
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
                    # Une grille annulée a des listes vides, donc toutes se
                    # ressemblent : on ne compare que des grilles pleines.
                    signature = json.dumps(data["matches"], sort_keys=True,
                                           ensure_ascii=False)
                    if data["matches"] and signature == signature_precedente:
                        identiques_suite += 1
                    else:
                        identiques_suite = 1
                    signature_precedente = signature
                    if identiques_suite >= arret_identiques:
                        motif_arret = (f"{identiques_suite} grilles d'affilée avec "
                                       f"exactement les mêmes matchs — le site sert "
                                       f"probablement la même page quel que soit l'ID "
                                       f"demandé. Vérifier les derniers fichiers écrits "
                                       f"AVANT de reprendre : ils sont sans doute faux")
                        rang_arret = rang
                        break
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
    ap.add_argument("--arret-identiques", type=int, default=3, metavar="N",
                    help="arrêter après N grilles d'affilée aux matchs identiques")
    ap.add_argument("--refaire", action="store_true",
                    help="redemander aussi les grilles déjà en base")
    ap.add_argument("--tout-charger", action="store_true",
                    help="télécharger aussi images, polices et vidéos (plus lent)")
    args = ap.parse_args()

    reglages = dict(pause=tuple(args.pause), lot=args.lot, pause_lot=tuple(args.pause_lot),
                    arret_erreurs=args.arret_erreurs, arret_absences=args.arret_absences,
                    arret_identiques=args.arret_identiques, refaire=args.refaire,
                    alleger=not args.tout_charger)

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
