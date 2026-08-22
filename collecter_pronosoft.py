"""Les grilles Loto Foot de la FDJ, telles que Pronosoft les archive.

POURQUOI CETTE SOURCE. Le Loto Foot de la FDJ est un autre produit que les
grilles Winamax, et son historique n'est publié nulle part ailleurs de façon
exploitable. Pronosoft l'archive grille par grille : les affiches, l'issue
sortie, les rapports par rang et les cotes du marché.

CE QU'ON N'EN PREND PAS, ET POURQUOI. Leurs pages portent aussi le pourcentage
de joueurs ayant coché chaque issue. C'est la seule donnée de ces pages qui
soit la PRODUCTION de Pronosoft — l'agrégat des pronostics de leur communauté,
qui n'existe que parce qu'ils l'ont compilé — quand tout le reste est un fait
public : un score, une cote de marché, un rapport de la FDJ. C'est aussi
exactement ce que protège le droit sui generis du producteur de base de
données. On ne l'enregistre donc pas.

C'est ce choix qui permet à data/pronosoft/ d'être versionné comme le reste
plutôt que tenu à l'écart du dépôt. Il a un coût, assumé : la question « où le
public se trompe-t-il exactement » reste sans réponse de ce côté-là.

DEUX PAGES PAR GRILLE, PARCE QU'AUCUNE NE SUFFIT.

    /fr/lotosports/historiques/loto-foot-N/…   les affiches, l'issue sortie et
                                               LES RAPPORTS par rang ;
    /fr/lotofoot/repartition/lf7/…             LES COTES 1/N/2, le pourcentage
                                               de joueurs par issue, et le score.

La première n'a pas de cotes, la seconde pas de rapports. Ne prendre que la
première — ce que faisait la version initiale — revenait à collecter des
grilles sans le seul champ qui justifiait de venir ici.

LA RÉPARTITION EST UNE SÉRIE UNIQUE POUR LES DEUX PRODUITS. L'adresse dit
« lf7 » mais le menu du site dit « Répartition LF 7&8 » : la grille 110 de 2026
y rend huit affiches. La numérotation est globale, et c'est elle qui décide.

LES COTES N'EXISTENT PAS AVANT MARS 2015. Vérifié : la grille 40 de 2015 n'en
a aucune, la 45 en a une partie, la 50 les a toutes. En deçà la page existe
mais ne porte que des pourcentages de joueurs.

CE N'EST PAS UNE RAISON DE S'ARRÊTER, ET IL N'Y A PLUS RIEN POUR LE FAIRE.
Une version antérieure coupait après huit grilles consécutives sans cote —
c'était décider à la place de celui qui collecte, et un pourcentage de
joueurs reste une donnée. La collecte descend jusqu'à ce que Pronosoft n'ait
plus de grille précédente à proposer. Les seules autres sorties sont un
--combien atteint, un --depuis franchi, et une boucle détectée dans les
liens.

CONDITIONS D'UTILISATION — À LIRE AVANT DE LANCER. Le robots.txt de Pronosoft
ne bloque que des robots de référencement nommés, pas les visiteurs ordinaires.
Leurs mentions légales, en revanche, sont explicites : « Il est interdit de
reproduire et rediffuser tout ou partie de ces contenus, sans l'autorisation
préalable et écrite de Pronosoft. »

D'où les deux règles ci-dessus, et une troisième :

    on ne garde que des faits — affiches, scores, cotes de marché, rapports de
    la FDJ — et jamais le pourcentage de joueurs, qui est leur production ;
    le rythme reste lent : une à deux secondes et demie par page, une pause
    tous les cent, et pas d'option pour l'accélérer davantage. Un 429 fait
    lever le pied plus longtemps.

Ces deux règles ne sont pas de même nature. La première est une limite sur ce
qu'on prend ; la seconde, une politesse envers un serveur qu'on n'a pas payé.

    python collecter_pronosoft.py --produit loto-foot-7
    python collecter_pronosoft.py --produit loto-foot-8 --combien 200

"""

import argparse
import itertools
import json
from collections import Counter
import random
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).parent
SORTIE = RACINE / "data" / "pronosoft"
BASE = "https://www.pronosoft.com"
INDEX = BASE + "/fr/lotosports/historiques/{produit}/"

# Le rythme. Ces bornes ne sont pas paramétrables : une option s'oublie, et
# c'est précisément celle-là qu'il ne faut pas oublier.
#
# UNE SECONDE À DEUX ET DEMIE, ET C'EST DÉLIBÉRÉ. Le premier réglage — deux et
# demie à cinq — mettait huit heures à descendre onze ans d'archives, pour une
# collecte personnelle sur un site qui n'interdit rien de tel. À 1,75 s de
# moyenne on reste sous le rythme d'un visiteur pressé, la pause d'un lot sur
# soixante tient toujours, et le tout passe à quatre heures. Ce qui protège
# vraiment le serveur, ce n'est pas la borne : c'est de ralentir QUAND IL LE
# DEMANDE — voir _lire et RALENTIR.
PAUSE = (1.0, 2.5)
# LA PAUSE DE LOT PESAIT PLUS LOURD QUE LA PAUSE DE PAGE. Une minute à deux
# toutes les soixante grilles, cela faisait 1,5 s de plus par grille — presque
# autant que la pause de page elle-même, et c'est ce qui expliquait qu'on ne
# sente pas la première accélération. Trente à soixante secondes toutes les
# cent grilles ramènent cette part à 0,45 s.
LOT = 100
PAUSE_LOT = (30.0, 60.0)
DELAI = 40
# Une coupure réseau n'est pas une fin de collecte. Le 21 août, une résolution
# DNS ratée a tué le script après 88 grilles ; il avait passé vingt minutes à
# les télécharger. On réessaie, en espaçant.
ESSAIS = 4
ATTENTE_ESSAI = (5, 15, 45)
# Quand le serveur dit « trop vite » ou « pas maintenant », on l'écoute plus
# longuement qu'un simple hoquet réseau.
RALENTIR = {429, 503}
ATTENTE_RALENTIR = (30, 120, 300)
ENTETE = {"User-Agent": "lotofoot-tracker (collecte personnelle, rythme lent)"}

ISSUES = ("1", "N", "2")
# LE BON CHEMIN, ET IL EST PROPRE À CHAQUE PRODUIT. /fr/lotofoot/repartition/
# lf7/ ne suit que le Loto Foot 7 et sert la grille en cours dès qu'on lui
# donne un numéro du Loto Foot 8 — c'est ce qui m'a fait conclure à tort que le
# Loto Foot 8 n'avait pas de cotes. Celui-ci nomme le produit, et son archive
# remonte pour les deux.
REPARTITION = BASE + "/fr/lotosports/repartition/{produit}/{annee}-grille-{numero}/"
# La saison en deçà de laquelle --depuis fait s'arrêter. L'adresse d'une
# grille historique porte sa saison — /loto-foot-7/2015-2016/2015-grille-97/ —
# et une comparaison de chaînes suffit à les ordonner. Les cotes n'existent
# pas avant mars 2015 : c'est le plancher à passer à --depuis si l'on ne veut
# que la période cotée. Par défaut il n'y a pas de plancher.
SAISON_PLANCHER = "2015-2016"
# Part des affiches devant concorder entre les deux pages. Pas 100 % : les
# abréviations diffèrent d'une page à l'autre et un nom peut rester
# irréconciliable. Mais très au-dessus de ce qu'un hasard produirait.
# Mesuré : une page de repli — celle que Pronosoft sert pour un numéro hors
# série — concorde sur ZÉRO affiche. Une vraie correspondance concorde sur au
# moins quatre sur sept, les écarts venant des noms traduits : Fribourg contre
# Freiburg, St Trond contre St.Truiden, Étoile Rouge contre Crvena Zvezda. Le
# seuil est donc posé entre les deux, et le contrôle des scores fait le reste.
CONCORDANCE_MINI = 0.4
# LES REFUS QUI MÉRITENT UNE SECONDE CHANCE À LA REPRISE. Une grille dont la
# répartition avait été jugée « absente » l'était parce que le collecteur ne
# savait lire que le tableau des cotes ; il lit maintenant aussi la liste des
# pourcentages, qui existe sur toutes les pages. Repasser dessus coûte une
# requête et récupère la donnée. Les autres motifs — affiches différentes,
# scores contradictoires — disent que la page ne parle pas de cette grille :
# les redemander ne changerait rien.
REFUS_A_REESSAYER = (None, "absente", "désaccord de longueur")
LIEN_GRILLE = r'href="(/fr/lotosports/historiques/{produit}/[^"]*?grille-(\d+)/)"'


def _texte(brut: str) -> str:
    """Le texte d'une cellule, sans balises ni entités ni accents cassés."""
    t = re.sub(r"<[^>]+>", "", brut)
    t = t.replace("&nbsp;", " ").replace("&euro;", "€").replace("&amp;", "&")
    return unicodedata.normalize("NFC", t).strip()


def _nombre(t: str):
    """« 3 092 € » ou « 188,3 € » → un flottant."""
    t = _texte(t).replace("€", "").replace(" ", "").replace("\xa0", "")
    t = t.replace(" ", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def analyser(html: str, produit: str, numero: int) -> dict:
    """Une grille archivée : ses affiches, ses issues, ses rapports.

    L'issue sortie est marquée par `<span class="res">` — c'est le seul
    signal, il n'y a pas de score sur ces pages.
    """
    tables = re.findall(r"<table.*?</table>", html, re.S)
    if not tables:
        return {}

    matchs, date = [], None
    for ligne in re.findall(r"<tr.*?</tr>", tables[0], re.S):
        entete = re.search(r'class="head"[^>]*>(.*?)</t[dh]>', ligne, re.S)
        if entete and date is None:
            date = _texte(entete.group(1))
        dom = re.search(r'class="home"[^>]*>(.*?)</td>', ligne, re.S)
        ext = re.search(r'class="ext"[^>]*>(.*?)</td>', ligne, re.S)
        if not (dom and ext):
            continue
        cellule = re.search(r'class="result"[^>]*>(.*?)</td>', ligne, re.S)
        gagnante = None
        if cellule:
            for i, span in enumerate(re.findall(r"<span([^>]*)>(.*?)</span>",
                                                cellule.group(1), re.S)):
                if "res" in span[0]:
                    gagnante = ISSUES[i] if i < 3 else _texte(span[1])
        matchs.append({"home": _texte(dom.group(1)), "away": _texte(ext.group(1)),
                       "issue": gagnante})

    rapports = []
    for table in tables[1:3]:
        cellules = [_texte(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", table, re.S)]
        # Trois colonnes par rang : bons résultats, gagnants, rapport.
        for i in range(0, len(cellules) - 2, 3):
            rang, gagnants, rapport = cellules[i:i + 3]
            if rang.isdigit() and gagnants.replace(" ", "").isdigit():
                rapports.append({"bons": int(rang),
                                 "gagnants": int(gagnants.replace(" ", "")),
                                 "rapport": _nombre(rapport)})
        if rapports:
            break

    return {"produit": produit, "numero": numero, "date": date,
            "matchs": matchs, "rapports": rapports,
            # UNE GRILLE PAS ENCORE JOUÉE N'EST PAS UNE GRILLE. Ses issues sont
            # vides et ses rapports à zéro ; l'enregistrer telle quelle la
            # figerait, puisque la reprise saute ce qui est déjà en base.
            "reglee": bool(matchs) and all(m["issue"] for m in matchs)}


def _affiches_de_la_liste(html: str) -> list:
    """Les affiches, lues dans la liste et non dans le tableau.

    POURQUOI DEUX LECTURES DE LA MÊME PAGE. Le tableau des cotes disparaît sur
    certaines grilles — la trêve de Noël 2022 en compte une quinzaine
    d'affilée, du 24 décembre au 11 janvier — et avec lui, jusqu'ici, TOUT ce
    que la page disait. Le second bloc, lui, porte les affiches sur toutes les
    grilles, cotées ou non : c'est ce qui permet de reconnaître la grille et de
    ne pas la redemander indéfiniment.

    C'est aussi ce trou qui a fait mentir l'ancien message d'arrêt : huit
    grilles sans cote n'annonçaient pas la fin de la période exploitable, elles
    annonçaient Noël, avec huit ans d'archives cotées en dessous.

    LES POURCENTAGES DE JOUEURS SONT DANS CE BLOC, ET ON NE LES PREND PAS.
    Voir l'entête du module : c'est la seule donnée de ces pages qui soit la
    production de Pronosoft, et la raison pour laquelle tout le reste peut
    être versionné.
    """
    bloc = re.search(r'<ul class="repart">(.*?)</ul>', html, re.S)
    if not bloc:
        return []
    lignes = []
    for item in re.findall(r"<li[^>]*>(.*?)</li>", bloc.group(1), re.S):
        affiche = re.search(r'class="team"[^>]*>(.*?)</span>', item, re.S)
        if not affiche:
            continue
        equipes = [e.strip() for e in _texte(affiche.group(1)).split("-", 1)]
        lignes.append({
            "home": equipes[0], "away": equipes[1] if len(equipes) > 1 else "",
            "debut": None, "cotes": None, "score": None,
        })
    return lignes


def analyser_repartition(html: str) -> list:
    """Cotes, date et score, ligne à ligne.

    ON NE COMPTE PAS LES COLONNES, on lit les classes. Chaque cellule d'issue
    porte le pourcentage de joueurs suivi d'un `<span class="dev_span_1">`,
    `_n` ou `_2` qui contient la cote — vide sur les grilles antérieures à
    mars 2015, où Pronosoft ne publiait que les pourcentages. Le nom de la
    classe dit donc l'issue, ce qu'aucune position de colonne ne garantit.

    ATTENTION À CE QUE SONT CES COTES. Le lien qui les entoure nomme un
    opérateur — ParionsWeb ici, BetClic là : c'est la MEILLEURE cote du
    marché, pas celle d'une maison. La somme des probabilités implicites en
    est donc plus basse que chez un bookmaker réel, et les rendements calculés
    dessus seront optimistes. Pour désigner le favori, en revanche, elle vaut
    n'importe quelle autre.
    """
    tables = re.findall(r"<table.*?</table>", html, re.S)
    lignes = []
    for ligne in re.findall(r"<tr[^>]*>.*?</tr>", tables[-1] if tables else "", re.S):
        affiche = re.search(r'class="match"[^>]*>(.*?)</td>', ligne, re.S)
        if not affiche:
            continue
        # DÉCOUPER D'ABORD, CHERCHER ENSUITE. Une expression qui va d'un
        # `<td>` jusqu'au span voulu traverse les cellules voisines et ramène
        # le pourcentage de la première : les trois issues sortaient à 38 %.
        cellules = re.findall(r"<td[^>]*>.*?</td>", ligne, re.S)
        cotes = []
        for issue in ("1", "n", "2"):
            cellule = next((c for c in cellules
                            if f'dev_span_{issue}"' in c), None)
            if not cellule:
                cotes.append(None); continue
            valeur = re.search(r'dev_span_%s"[^>]*>(.*?)</span>' % issue, cellule, re.S)
            cotes.append(_nombre(valeur.group(1)) if valeur else None)
        quand = re.search(r'data-date-utc="([^"]+)"', ligne)
        score = re.search(r">\s*(\d{1,2})\s*-\s*(\d{1,2})\s*<", ligne[-400:])
        equipes = [e.strip() for e in _texte(affiche.group(1)).split("-", 1)]
        lignes.append({
            "home": equipes[0], "away": equipes[1] if len(equipes) > 1 else "",
            "debut": quand.group(1) if quand else None,
            "cotes": cotes if all(cotes) else None,
            "score": [int(score.group(1)), int(score.group(2))] if score else None,
        })

    # LE TABLEAU N'EST PAS TOUJOURS COMPLET, ET PARFOIS IL EST ABSENT. La
    # liste, elle, porte toujours toutes les affiches : quand elle en compte
    # plus que le tableau, c'est elle qui donne la charpente, et le tableau ne
    # fait plus qu'y verser ses cotes. Sans cela une grille sans cote rendait
    # zéro affiche, et se faisait redemander à chaque reprise.
    parts = _affiches_de_la_liste(html)
    if len(parts) <= len(lignes):
        return lignes
    for entree in parts:
        jumelle = next((l for l in lignes if meme_affiche(l["home"], entree["home"])
                        and meme_affiche(l["away"], entree["away"])), None)
        if not jumelle:
            lignes.append(entree)
    # L'ordre de la liste est celui de la grille : c'est lui qui fait foi,
    # puisque enrichir() apparie ligne à ligne.
    rang = {(l["home"], l["away"]): i for i, l in enumerate(parts)}
    lignes.sort(key=lambda l: next(
        (i for (h, a), i in rang.items()
         if meme_affiche(l["home"], h) and meme_affiche(l["away"], a)), len(parts)))
    return lignes


def _lire(url: str) -> str:
    """La page, en réessayant si le réseau flanche.

    Une erreur de résolution ou une connexion coupée ne dit rien de la page
    demandée : elle dit que le réseau a hoqueté. On patiente et on repose la
    question, plutôt que de perdre une collecte entamée.
    """
    for essai in range(ESSAIS):
        try:
            requete = urllib.request.Request(url, headers=ENTETE)
            with urllib.request.urlopen(requete, timeout=DELAI) as reponse:
                return reponse.read().decode("latin-1", "replace")
        except urllib.error.HTTPError as souci:
            # UNE PAGE ABSENTE N'EST PAS UNE PANNE. Redemander quatre fois un
            # 404 coûtait soixante-cinq secondes d'attente pour rien, et une
            # grille sur dix n'a pas de page de répartition : on rendait la
            # main au bout d'une minute là où la réponse était immédiate.
            if souci.code not in RALENTIR:
                raise
            if essai == ESSAIS - 1:
                raise
            repos = ATTENTE_RALENTIR[min(essai, len(ATTENTE_RALENTIR) - 1)]
            print(f"    {souci.code} — le serveur demande de lever le pied, "
                  f"pause de {repos} s")
            time.sleep(repos)
        except (urllib.error.URLError, TimeoutError, OSError) as souci:
            if essai == ESSAIS - 1:
                raise
            repos = ATTENTE_ESSAI[min(essai, len(ATTENTE_ESSAI) - 1)]
            print(f"    réseau : {souci} — nouvel essai dans {repos} s")
            time.sleep(repos)
    return ""


def _depart(produit: str, dossier: Path) -> str:
    """Par où recommencer : à la suite de ce qu'on a déjà, ou tout en haut.

    REPRENDRE NE VEUT PAS DIRE TOUT RELIRE. La collecte descend le temps ;
    si des grilles sont déjà en base, la suite du travail commence sous la
    PLUS ANCIENNE d'entre elles, et il n'y a aucune raison de repasser par
    les autres. On lit donc une seule page — celle-là — au lieu de quatre-
    vingt-dix.
    """
    connues = sorted(dossier.glob("*.json"))
    if connues:
        plus_ancienne = json.loads(connues[0].read_text(encoding="utf-8"))
        suite = plus_ancienne.get("precedente")
        if suite:
            print(f"  reprise sous la grille {connues[0].stem} "
                  f"({len(connues)} déjà en base)")
            return suite
        # Grille enregistrée par une version antérieure, qui ne notait pas son
        # lien : une requête suffit à le retrouver.
        url = plus_ancienne.get("url")
        if url:
            numero = int(re.search(r"grille-(\d+)", url).group(1))
            print(f"  reprise sous la grille {connues[0].stem} "
                  f"({len(connues)} déjà en base)")
            return _precedente(_lire(url), produit, numero)

    html = _lire(INDEX.format(produit=produit))
    liens = re.findall(LIEN_GRILLE.format(produit=produit), html)
    if not liens:
        return ""
    return BASE + max(liens, key=lambda x: int(x[1]))[0]


def _repartition(produit: str, cle: str) -> list:
    """La page de répartition d'une grille, désignée par sa clé année-numéro."""
    annee, numero = cle.split("-")
    try:
        return analyser_repartition(_lire(REPARTITION.format(
            produit=produit, annee=annee, numero=int(numero))))
    except urllib.error.HTTPError:
        return []


def _precedente(html: str, produit: str, numero: int) -> str:
    """Le lien vers la grille d'avant, qui traverse les changements de saison."""
    liens = [(u, int(n)) for u, n in
             re.findall(LIEN_GRILLE.format(produit=produit), html)]
    avant = [u for u, n in liens if n < numero]
    if avant:
        return BASE + max(avant, key=lambda u: int(re.search(r"grille-(\d+)", u).group(1)))
    # Changement d'année : le numéro repart à 1, donc le plus grand numéro
    # d'une autre saison est la grille précédente.
    autres = [(u, n) for u, n in liens if f"grille-{numero}/" not in u]
    return BASE + max(autres, key=lambda x: x[1])[0] if autres else ""


# Un triplet répété sur une bonne part des affiches n'est pas une
# coïncidence : c'est le remplissage. On exige au moins trois occurrences pour
# ne pas confondre avec deux matchs réellement pronostiqués pareil.


def _mots(nom: str) -> set:
    """Les mots significatifs d'un nom d'équipe, accents et ponctuation ôtés."""
    plie = unicodedata.normalize("NFD", (nom or "").lower())
    plie = "".join(c for c in plie if unicodedata.category(c) != "Mn")
    return {m for m in re.split(r"[^a-z0-9]+", plie) if len(m) >= 4}


def meme_affiche(a: str, b: str) -> bool:
    """« Atl. Madrid » et « Atletico Madrid » désignent-ils la même équipe ?

    Les deux pages n'abrègent pas pareil. On ne demande donc pas l'égalité
    mais un mot significatif en commun — « madrid » ici, « viseu » pour
    « Academico Viseu » contre « Viseu ».
    """
    mots_a, mots_b = _mots(a), _mots(b)
    return bool(mots_a & mots_b) or not (mots_a and mots_b)


def enrichir(grille: dict, lignes: list) -> dict:
    """Coller les cotes, les scores et les dates sur les affiches de la grille.

    LA VÉRIFICATION PAR LES NOMS N'EST PAS UNE PRÉCAUTION, C'EST LA CONDITION.
    Un numéro hors série ne renvoie pas 404 chez Pronosoft : la page sert
    silencieusement LA GRILLE EN COURS. La grille 109 du Loto Foot 8 s'est
    ainsi vu coller les cotes de la 110, et le contrôle de longueur n'y a rien
    vu puisque les deux avaient huit lignes.

    On exige donc que les affiches concordent, faute de quoi on ne colle rien.
    C'est aussi ce qui protège des numéros qui n'existent pas encore dans une
    série : la page répond 200 et sert autre chose.
    """
    matchs = grille.get("matchs", [])
    if not lignes or len(lignes) != len(matchs):
        grille["repartition"] = "désaccord de longueur" if lignes else "absente"
        return grille
    concordent = sum(1 for m, l in zip(matchs, lignes)
                     if meme_affiche(m["home"], l["home"])
                     and meme_affiche(m["away"], l["away"]))
    if concordent < CONCORDANCE_MINI * len(matchs):
        grille["repartition"] = f"affiches différentes ({concordent}/{len(matchs)})"
        return grille

    # LE CONTRÔLE QUI NE MENT PAS. Les deux pages disent le résultat, l'une par
    # un score, l'autre par une issue cochée. Deux matchs qui ne finissent pas
    # pareil ne sont pas le même match — et contrairement aux noms, un score
    # ne se traduit pas.
    for match, ligne in zip(matchs, lignes):
        score, issue = ligne.get("score"), match.get("issue")
        if not score or not issue:
            continue
        attendu = "1" if score[0] > score[1] else ("N" if score[0] == score[1] else "2")
        if attendu != issue:
            grille["repartition"] = "scores en désaccord avec les issues"
            return grille
    # LE PUBLIC N'EST PAS TOUJOURS PUBLIÉ, ET PAS FORCÉMENT POUR TOUTE LA
    # GRILLE. Là où il manque, la page affiche 38 / 29 / 32 et 50/50 en
    # dessous — un remplissage par défaut. Sur la grille 108 de 2026, six
    # affiches sur huit le portent et deux sont réelles. On l'écarte donc
    # ligne à ligne, pas grille par grille. Les COTES, elles, sont réelles
    # dans les deux cas : 1,86 / 3,05 / 3,55 pour Boca-Paranaense.
    for match, ligne in zip(matchs, lignes):
        match["cotes"] = ligne["cotes"]
        match["score"] = ligne["score"]
        match["debut"] = ligne["debut"]
    grille["repartition"] = "ok"
    grille["cotees"] = sum(1 for m in grille["matchs"] if m.get("cotes"))
    return grille


def _saison(url: str) -> str:
    """La saison que porte l'adresse d'une grille, ou une chaîne vide."""
    trouve = re.search(r"/(\d{4}-\d{4})/", url)
    return trouve.group(1) if trouve else ""


def trop_ancienne(url: str, plancher: str) -> bool:
    """Cette grille est-elle antérieure à la saison où l'on veut s'arrêter ?

    Les saisons s'écrivent « 2015-2016 » et s'ordonnent donc comme des
    chaînes. Une adresse sans saison — la page de répartition n'en porte
    pas — ne fait jamais arrêter : on ne devine pas.
    """
    saison = _saison(url)
    return bool(saison and plancher and saison < plancher)


def collecter(produit: str, combien: int, saison_plancher: str = "") -> int:
    dossier = SORTIE / produit
    dossier.mkdir(parents=True, exist_ok=True)
    url = _depart(produit, dossier)
    if not url:
        print(f"aucune grille trouvée pour {produit}")
        return 1

    vus, enregistrees, sautees, attentes = set(), 0, 0, 0
    # --combien 0 : descendre jusqu'au bout. La boucle s'arrête alors d'elle-
    # même quand Pronosoft n'a plus de grille précédente à proposer.
    tours = itertools.count() if combien <= 0 else range(combien)
    for tour in tours:
        if trop_ancienne(url, saison_plancher):
            print(f"  saison {_saison(url)} — on ne descend pas sous "
                  f"{saison_plancher}, on s'arrête")
            break
        numero = int(re.search(r"grille-(\d+)", url).group(1))
        annee = re.search(r"/(\d{4})-grille-", url)
        cle = f"{annee.group(1) if annee else '0000'}-{numero:04d}"
        if url in vus:
            print("  boucle détectée, on s'arrête")
            break
        vus.add(url)

        chemin = dossier / f"{cle}.json"
        if chemin.exists():
            sautees += 1
            # LA REPRISE NE DOIT RIEN RETÉLÉCHARGER. Le lien vers la grille
            # précédente est enregistré avec la grille : sans lui, reprendre
            # une collecte interrompue rechargeait toutes les pages déjà en
            # base pour retrouver son chemin.
            connue = json.loads(chemin.read_text(encoding="utf-8"))
            if connue.get("repartition") in REFUS_A_REESSAYER:
                # Grille collectée avant que le collecteur ne sache lire cette
                # page : on va chercher la seule qui manque, sans retélécharger
                # l'historique.
                enrichir(connue, _repartition(produit, cle))
                chemin.write_text(json.dumps(connue, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                print(f"  [{cle}] complétée — {connue.get('cotees', 0)} matchs cotés")
                enregistrees += 1
                time.sleep(random.uniform(*PAUSE))
            suivante = connue.get("precedente")
            if suivante:
                url = suivante
                continue
            html = _lire(url)
        else:
            html = _lire(url)
            grille = analyser(html, produit, numero)
            if grille.get("matchs") and not grille["reglee"]:
                attentes += 1
                print(f"  [{cle}] pas encore réglée — on repassera")
            elif grille.get("matchs"):
                grille["url"] = url
                grille["precedente"] = _precedente(html, produit, numero)
                enrichir(grille, _repartition(produit, cle))
                chemin.write_text(json.dumps(grille, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                enregistrees += 1
                print(f"  [{cle}] {grille['date']} — {len(grille['matchs'])} matchs, "
                      f"{len(grille['rapports'])} rang(s), "
                      f"{grille.get('cotees', 0)} coté(s)")
            else:
                print(f"  [{cle}] page illisible")

        suivante = _precedente(html, produit, numero)
        if not suivante:
            print("  plus de grille précédente")
            break
        url = suivante
        time.sleep(random.uniform(*PAUSE))
        if (tour + 1) % LOT == 0:
            repos = random.uniform(*PAUSE_LOT)
            print(f"  — lot de {LOT} terminé, pause de {repos:.0f} s —")
            time.sleep(repos)

    print(f"\nBilan : {enregistrees} enregistrée(s), {sautees} déjà en base, "
          f"{attentes} pas encore réglée(s).")
    print(f"-> {dossier}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Archives Loto Foot de Pronosoft")
    ap.add_argument("--produit", default="loto-foot-7",
                    choices=["loto-foot-7", "loto-foot-8", "loto-foot-12",
                             "loto-foot-15"])
    ap.add_argument("--combien", type=int, default=0,
                    help="nombre de grilles à remonter ; 0 = jusqu'au bout")
    ap.add_argument("--depuis", default="", metavar="SAISON",
                    help="ne pas descendre sous cette saison, ex : 2015-2016 ; "
                         "par défaut, pas de plancher")
    args = ap.parse_args()
    return collecter(args.produit, args.combien, args.depuis)


if __name__ == "__main__":
    raise SystemExit(main())
