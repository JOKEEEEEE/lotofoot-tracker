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


def test_le_trj_est_le_distribue_sur_les_mises_brutes():
    """À 1 € la grille, les mises brutes sont le nombre de grilles jouées."""
    assert cs._trj(7500, 9253) == round(7500 / 9253, 4)
    assert cs._trj(10000, 3992) > 1.0            # un vrai overlay
    assert cs._trj(None, 9253) is None
    assert cs._trj(7500, None) is None
    assert cs._trj(7500, 0) is None


def test_les_sources_de_cotes_tiennent_en_une_lettre():
    compact = cs.cotes_compactes({
        "1": {"cote_1": 2.4, "cote_N": 3.35, "cote_2": 2.7, "source": "winamax"},
        "2": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "pinnacle_cloture"},
        "3": {"cote_1": 1.5, "cote_N": 4.0, "cote_2": 7.0, "source": "inconnue"},
    })
    assert compact["1"] == [2.4, 3.35, 2.7, "w"]
    assert compact["2"][3] == "p"
    assert compact["3"][3] == "?", "une source inconnue se voit, elle ne se devine pas"


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
