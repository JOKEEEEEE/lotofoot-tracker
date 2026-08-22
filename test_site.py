"""Tests du site : l'index, et surtout la logique dupliquée en JavaScript.

LE VRAI RISQUE D'UN SITE STATIQUE. La page rejoue en JavaScript ce que
collecter_ws fait en Python : décoder `strPoolResult`, qui s'écrit à l'envers.
Deux implémentations d'une même règle divergent tôt ou tard, et l'erreur serait
invisible — le site afficherait des résultats plausibles mais faux.

Ce fichier extrait donc la fonction JavaScript de la page, l'exécute avec node,
et exige qu'elle rende exactement ce que rend la fonction Python, sur des codes
réels tirés de la base.

    python test_site.py        (ou : pytest test_site.py)
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import collecter_ws as cw
import construire_site as cs

RACINE = Path(__file__).parent
PAGE = RACINE / "index.html"
ATELIER = RACINE / "atelier.html"
PARTAGE = RACINE / "js" / "grilles.js"


def _fonction_js() -> str:
    """La fonction de décodage, telle qu'elle vit dans le site.

    Elle a quitté index.html pour js/grilles.js le jour où l'atelier a eu
    besoin d'elle : un décodeur en deux exemplaires finit par en faire deux.
    """
    texte = PARTAGE.read_text(encoding="utf-8")
    debut = texte.index("function decoderResultat")
    fin = texte.index("\n}", debut) + 2
    return 'const ISSUES = ["1","N","2"];\n' + texte[debut:fin]


def _codes_reels(combien: int = 60) -> list:
    """Des codes tirés des vraies grilles, pas fabriqués."""
    codes = []
    for t in ("grille7", "grille9", "grille12"):
        dossier = RACINE / "data" / "pools" / t
        if not dossier.exists():
            continue
        for f in sorted(dossier.glob("*.json"), key=lambda f: int(f.stem))[-20:]:
            d = json.loads(f.read_text(encoding="utf-8"))
            codes.append((d.get("resultat_code"), len(d.get("matches", []))))
    return codes[:combien]


def test_le_javascript_decode_comme_le_python():
    cas = _codes_reels() + [
        ("100001100100100100111", 7),      # la grille 521, un match annulé
        ("000100", 2),                     # un triplet vide
        (None, 3),
        ("1001", 2),                       # longueur fausse
        ("010100", 2),
    ]
    script = _fonction_js() + f"""
const cas = {json.dumps(cas)};
console.log(JSON.stringify(cas.map(([c, n]) => decoderResultat(c, n))));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(script)
        chemin = fh.name
    try:
        sortie = subprocess.run(["node", chemin], capture_output=True, text=True,
                                timeout=60)
        assert sortie.returncode == 0, sortie.stderr[:400]
        cotes_js = json.loads(sortie.stdout)
    finally:
        Path(chemin).unlink(missing_ok=True)

    for (code, n), js in zip(cas, cotes_js):
        py = cw.decoder_resultat(code, n)
        attendu = [sorted(x) if x else None for x in py]
        obtenu = [sorted(x) if x else None for x in js]
        assert attendu == obtenu, (code, n, attendu, obtenu)
    print(f"         ({len(cas)} codes comparés)")


def test_l_index_porte_ce_qu_une_liste_doit_montrer():
    index = cs.construire()
    assert index["champs"][:3] == ["type", "id", "date"]
    assert len(index["grilles"]) > 100
    ligne = dict(zip(index["champs"], index["grilles"][0]))
    assert ligne["type"] in (7, 9, 12)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ligne["date"] or "")
    assert ligne["matchs"] >= 7
    assert "-" in ligne["affiches"], "les affiches servent à la recherche"


def test_une_surprise_se_mesure_contre_les_cotes():
    """Le favori est l'issue la moins chère ; une surprise, c'est autre chose.

    Une grosse surprise paie au moins trois fois la cote du favori — un
    rapport, pas une cote absolue : un 4.00 dans un match serré et un 4.00
    face à un archi-favori ne racontent pas la même histoire.
    """
    cotes = {
        "1": {"cote_1": 1.40, "cote_N": 4.40, "cote_2": 8.00},   # archi-favori
        "2": {"cote_1": 2.40, "cote_N": 3.35, "cote_2": 2.70},   # match serré
        "3": {"cote_1": 1.98, "cote_N": 3.10, "cote_2": 3.20},
    }
    ms = [{"match_id": 1}, {"match_id": 2}, {"match_id": 3}]

    # Les trois favoris sortent : aucune surprise.
    assert cs.surprises(ms, [{"1"}, {"1"}, {"1"}], cotes) == (0, 0)

    # Le nul à 4.40 contre un favori à 1.40, c'est 3,14 fois : grosse.
    # Le nul à 3.35 contre 2.40, c'est 1,40 fois : surprise, mais pas grosse.
    assert cs.surprises(ms, [{"N"}, {"N"}, {"1"}], cotes) == (2, 1)

    # Un match annulé paie sur les trois issues : il ne dit rien du marché,
    # ni au numérateur ni au dénominateur.
    assert cs.surprises(ms, [{"1", "N", "2"}, {"N"}, {"1"}], cotes) == (1, 0)

    # Une grille non réglée ne se mesure pas — et une absence n'est pas un zéro.
    assert cs.surprises(ms, [None, {"N"}, {"1"}], cotes) == (None, None)
    assert cs.surprises(ms, [{"1"}, {"1"}, {"1"}], {}) == (None, None)


def test_l_index_dit_quand_une_grille_commence():
    """L'atelier ne propose que des grilles pas encore commencées : c'est le
    coup d'envoi du PREMIER match qui en décide, pas la fin de la grille."""
    index = cs.construire()
    lignes = [dict(zip(index["champs"], g)) for g in index["grilles"]]
    avec = [g for g in lignes if g["debut"]]
    assert len(avec) > 100, "le début manque partout"
    for g in avec[:200]:
        assert g["debut"][:10] <= g["date"], (g["id"], g["debut"], g["date"])


def test_le_trj_est_le_distribue_sur_les_mises_brutes():
    """À 1 € la grille, les mises brutes sont le nombre de grilles jouées."""
    assert cs._trj(7500, 9253) == round(7500 / 9253, 4)
    assert cs._trj(10000, 3992) > 1.0            # un vrai overlay
    assert cs._trj(None, 9253) is None
    assert cs._trj(7500, None) is None
    assert cs._trj(7500, 0) is None


def test_seules_les_quatre_maisons_retenues_sont_publiees():
    """Winamax, Pinnacle, Bet365, FDJ — et rien d'autre.

    Une cote dont on ne sait plus d'où elle vient ne se range pas sous « ? » :
    elle ne franchit pas cette porte. Le site montre un logo pour chacune, et
    un logo qu'on ne saurait pas dessiner est le signe qu'il ne fallait pas
    garder la cote.
    """
    compact = cs.cotes_compactes({
        "1": {"cote_1": 2.4, "cote_N": 3.35, "cote_2": 2.7, "source": "winamax"},
        "2": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "pinnacle_cloture"},
        "3": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "footiqo_cloture"},
        "4": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "inconnue"},
        "5": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "fdj"},
    })
    assert compact["1"] == [2.4, 3.35, 2.7, "w"]
    assert compact["2"][3] == "p"
    assert compact["5"][3] == "d"
    assert "3" not in compact, "Footiqo est sorti de la liste, ses cotes aussi"
    assert "4" not in compact, "une source inconnue ne se publie pas"


def test_chaque_source_publiee_a_son_logo():
    """Le tableau des affiches montre un logo, pas une lettre. Une lettre sans
    logo laisserait une case vide là où le lecteur cherche la provenance."""
    lettres = set(cs.SOURCES.values())
    fichiers = {f.stem for f in (RACINE / "img").glob("*.svg")}
    page = (RACINE / "js" / "grilles.js").read_text(encoding="utf-8")
    for lettre in sorted(lettres):
        motif = re.search(rf'"?{lettre}"?:\s*\{{[^}}]*logo:\s*"([^"]+)"', page)
        assert motif, f"la lettre {lettre} n'a pas de logo déclaré"
        assert motif.group(1) in fichiers, (lettre, motif.group(1), fichiers)


def test_la_page_ne_charge_rien_hors_du_depot():
    """Le site ne doit servir que ce que le dépôt contient : c'est ce qui
    garantit qu'aucune donnée ignorée par git ne sera publiée."""
    for page in (PAGE, ATELIER):
        texte = page.read_text(encoding="utf-8")
        for cible in re.findall(r'fetch\(\s*[`"\']([^`"\']+)', texte):
            assert not cible.startswith(("http://", "https://", "//")), cible
        externes = re.findall(r'(?:src|href)="(https?://[^"]+)"', texte)
        assert all("fonts.googleapis.com" in u or "fonts.gstatic.com" in u
                   for u in externes), (page.name, externes)
    # Les fichiers séparés comptent autant que les pages : une dépendance
    # externe s'y cache tout aussi bien.
    for f in sorted((RACINE / "js").glob("*.js")) + sorted((RACINE / "css").glob("*.css")):
        texte = f.read_text(encoding="utf-8")
        for cible in re.findall(r'(?:fetch\(\s*|@import\s+|url\()[`"\']([^`"\']+)', texte):
            assert not cible.startswith(("http://", "https://", "//")), (f.name, cible)


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except Exception as e:
            print(f"  ECHEC  {nom} : {type(e).__name__} {str(e)[:250]}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
