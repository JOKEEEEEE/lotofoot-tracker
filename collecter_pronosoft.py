"""Les grilles Loto Foot de la FDJ, telles que Pronosoft les archive.

POURQUOI CETTE SOURCE. Winamax ne dit pas comment le public a réparti ses
mises entre le 1, le N et le 2 — seulement combien de grilles ont fait k bons
résultats. Pronosoft, lui, publie le pourcentage de joueurs par issue et par
match. C'est la donnée qui manque pour répondre à « où le public se trompe-t-il
exactement », et pas seulement « de combien ».

CE QUE CHAQUE PAGE DONNE. Les sept ou huit affiches, l'issue sortie, et les
rapports par rang avec le nombre de gagnants. De quoi rejouer sur le Loto Foot
de la FDJ le banc d'essai écrit pour la grille 7 de Winamax.

CONDITIONS D'UTILISATION — À LIRE AVANT DE LANCER. Le robots.txt de Pronosoft
ne bloque que des robots de référencement nommés, pas les visiteurs ordinaires.
En revanche leurs mentions légales sont explicites : « Il est interdit de
reproduire et rediffuser tout ou partie de ces contenus, sans l'autorisation
préalable et écrite de Pronosoft. »

D'où deux règles, non négociables dans ce dépôt :

    la collecte va dans data/pronosoft/, qui est IGNORÉ PAR GIT — la donnée
    reste sur la machine et n'est jamais republiée, exactement comme le cache
    football-data et la collecte Footiqo ;
    le rythme est lent et il n'y a pas d'option pour l'accélérer.

Ce qu'on publie, ce sont des résultats d'analyse — des moyennes, des écarts —
et non le contenu de leurs pages. Si le projet devait un jour diffuser cette
donnée, il faudrait leur autorisation écrite, et il vaudrait mieux la demander
que de l'espérer.

    python collecter_pronosoft.py --produit loto-foot-7
    python collecter_pronosoft.py --produit loto-foot-8 --combien 200

"""

import argparse
import json
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
PAUSE = (2.5, 5.0)
LOT = 60
PAUSE_LOT = (60.0, 120.0)
DELAI = 40
# Une coupure réseau n'est pas une fin de collecte. Le 21 août, une résolution
# DNS ratée a tué le script après 88 grilles ; il avait passé vingt minutes à
# les télécharger. On réessaie, en espaçant.
ESSAIS = 4
ATTENTE_ESSAI = (5, 15, 45)
ENTETE = {"User-Agent": "lotofoot-tracker (collecte personnelle, rythme lent)"}

ISSUES = ("1", "N", "2")
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
        except (urllib.error.URLError, TimeoutError, OSError) as souci:
            if essai == ESSAIS - 1:
                raise
            repos = ATTENTE_ESSAI[min(essai, len(ATTENTE_ESSAI) - 1)]
            print(f"    réseau : {souci} — nouvel essai dans {repos} s")
            time.sleep(repos)
    return ""


def _depart(produit: str) -> str:
    """L'adresse de la grille la plus récente, d'où l'on remontera."""
    html = _lire(INDEX.format(produit=produit))
    liens = re.findall(LIEN_GRILLE.format(produit=produit), html)
    if not liens:
        return ""
    return BASE + max(liens, key=lambda x: int(x[1]))[0]


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


def collecter(produit: str, combien: int) -> int:
    dossier = SORTIE / produit
    dossier.mkdir(parents=True, exist_ok=True)
    url = _depart(produit)
    if not url:
        print(f"aucune grille trouvée pour {produit}")
        return 1

    vus, enregistrees, sautees, attentes = set(), 0, 0, 0
    for tour in range(combien):
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
                chemin.write_text(json.dumps(grille, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                enregistrees += 1
                print(f"  [{cle}] {grille['date']} — {len(grille['matchs'])} matchs, "
                      f"{len(grille['rapports'])} rang(s)")
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
    ap.add_argument("--combien", type=int, default=100,
                    help="nombre de grilles à remonter")
    args = ap.parse_args()
    return collecter(args.produit, args.combien)


if __name__ == "__main__":
    raise SystemExit(main())
