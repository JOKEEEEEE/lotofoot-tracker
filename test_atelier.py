"""Tests du moteur de l'atelier, sur les exemples de la documentation.

POURQUOI LES EXEMPLES DU MANUEL. Les mesures d'une grille — alternances,
symétries, diagonales, paires distinctes — se définissent de plusieurs façons
défendables, et la seule qui compte est celle de PronoFoot Expert, puisque
c'est à elle que les habitués comparent. La documentation en donne des
exemples chiffrés : ce sont eux qui font foi ici, pas mon intuition.

Le moteur étant écrit en JavaScript pour tourner dans le navigateur, ces
tests l'exécutent avec node.

    python test_atelier.py        (ou : pytest test_atelier.py)
"""

import json
import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).parent
MOTEUR = RACINE / "js" / "atelier.js"
SIGNES = {"1": 0, "N": 1, "2": 2}


def g(texte):
    """« 1N2 » devient [0, 1, 2 »]."""
    return [SIGNES[c] for c in texte]


def js(corps: str):
    """Exécute un bout de JavaScript avec le moteur importé, rend son JSON."""
    script = (f'import * as A from "{MOTEUR}";\n'
              f"{corps}\n")
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(script)
        chemin = fh.name
    try:
        r = subprocess.run(["node", chemin], capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, r.stderr[:600]
        return json.loads(r.stdout)
    finally:
        Path(chemin).unlink(missing_ok=True)


def test_le_compte_ne_passe_pas_par_l_enumeration():
    """Quinze triples font 14,3 millions de grilles : on doit savoir le dire
    sans essayer de les construire."""
    r = js("""
      const quinzeTriples = Array.from({length: 15}, () => [0,1,2]);
      console.log(JSON.stringify({
        compte: A.compter(quinzeTriples),
        enumere: A.enumerer(quinzeTriples),
        petit: A.compter([[0],[0,1],[0,1,2]]),
      }));""")
    assert r["compte"] == 3 ** 15
    assert r["enumere"] is None, "au-delà du plafond, on rend null, pas une liste vide"
    assert r["petit"] == 6


def test_les_mesures_suivent_les_exemples_du_manuel():
    r = js(f"""
      const g = t => [...t].map(c => ({{"1":0,"N":1,"2":2}})[c]);
      console.log(JSON.stringify({{
        alternances: A.alternances(g("111N2212N11111")),
        symetries: A.symetries(g("1111N2212N11111")),
        paires: A.suitesDistinctes(g("1N21N211NN1122"), 2),
      }}));""")
    # « La grille 111N2212N11111 comporte 6 alternances »
    assert r["alternances"] == 6, r
    # « La grille 1111N2212N11111 comporte 5 symétries »
    assert r["symetries"] == 5, r
    # « on compte plus que 8 paires différentes »
    assert r["paires"] == 8, r


def test_une_diagonale_est_un_1N2_ou_un_2N1():
    r = js("""
      const g = t => [...t].map(c => ({"1":0,"N":1,"2":2})[c]);
      console.log(JSON.stringify({
        montante: A.diagonales(g("1N2")),
        descendante: A.diagonales(g("2N1")),
        // « La suite 1N2N1 constitue 2 diagonales »
        deux: A.diagonales(g("1N2N1")),
        aucune: A.diagonales(g("1N1")) + A.diagonales(g("122")),
      }));""")
    assert (r["montante"], r["descendante"], r["deux"], r["aucune"]) == (1, 1, 2, 0), r


def test_la_reduction_du_manuel_tombe_a_deux_grilles():
    """L'exemple des trois doubles : huit grilles, garantie N-1, deux suffisent.

    « on peut remarquer que pour chacune des 8 grilles, la grille 1 ou la
    grille 8 couvre au moins 2 bons pronostics. »
    """
    r = js("""
      const trois = [[0,1],[0,1],[0,1]];
      const toutes = A.enumerer(trois);
      const n = A.reduire(toutes, 3, 1);      // garantie N : rien à réduire
      const n1 = A.reduire(toutes, 2, 1);     // garantie N-1
      console.log(JSON.stringify({
        total: toutes.length,
        garantieN: n.jeu.length, tauxN: n.taux,
        garantieN1: n1.jeu.length, tauxN1: n1.taux,
        jeuN1: n1.jeu.map(g => g.map(i => "1N2"[i]).join("")),
      }));""")
    assert r["total"] == 8
    assert r["garantieN"] == 8 and r["tauxN"] == 1, "sans erreur tolérée, rien ne se réduit"
    assert r["garantieN1"] == 2 and r["tauxN1"] == 1, r
    # Et ce sont bien les grilles 1 et 8 du manuel : « la grille 1 ou la
    # grille 8 couvre au moins 2 bons pronostics » pour chacune des huit.
    assert sorted(r["jeuN1"]) == ["111", "NNN"], r


def test_la_couverture_partielle_coute_moins_cher():
    """« pour obtenir une réduction à 100 %, le nombre de grilles augmente
    vite sur les derniers pour-cent à couvrir. »"""
    r = js("""
      const six = Array.from({length: 6}, () => [0,1,2]);
      const toutes = A.enumerer(six);
      const plein = A.reduire(toutes, 5, 1);
      const partiel = A.reduire(toutes, 5, 0.64);
      console.log(JSON.stringify({
        total: toutes.length,
        plein: plein.jeu.length, tauxPlein: plein.taux,
        partiel: partiel.jeu.length, tauxPartiel: partiel.taux,
      }));""")
    assert r["total"] == 729
    assert r["tauxPlein"] == 1
    assert r["partiel"] < r["plein"], r
    assert r["tauxPartiel"] >= 0.64, r


def test_les_filtres_sur_les_signes():
    r = js("""
      const g = t => [...t].map(c => ({"1":0,"N":1,"2":2})[c]);
      const gr = g("1112N2N");    // trois 1, deux N, deux 2
      console.log(JSON.stringify({
        signes: A.compteSignes(gr),
        borne: A.retenue(gr, {un:{min:3,max:4}}),
        horsBorne: A.retenue(gr, {un:{min:5}}),
        suite: A.retenue(gr, {suiteUn:{max:2}}),      // il y a trois 1 d'affilée
        combi: A.retenue(gr, {combinaisons:["3-2-2"]}),
        combiFausse: A.retenue(gr, {combinaisons:["5-1-1"]}),
        sansRegle: A.retenue(gr, {}),
      }));""")
    assert r["signes"] == [3, 2, 2]
    assert r["borne"] is True and r["horsBorne"] is False
    assert r["suite"] is False, "trois 1 consécutifs dépassent le maximum de 2"
    assert r["combi"] is True and r["combiFausse"] is False
    assert r["sansRegle"] is True, "sans règle, tout passe"


def test_la_synthese_ne_confond_pas_double_et_triple():
    """Le coût s'affiche à partir de cette ligne : 2^doubles x 3^triples. Un
    double rangé parmi les triples et l'atelier annonce une mise et demie."""
    r = js("""
      console.log(JSON.stringify({
        melange: A.synthese([[0],[0,1],[0,1,2],[],[0,1],[0,1,2],[0,1,2]]),
        suite: A.consecutifsMax([0,0,1,0,0,0], 0),
        symetrie: A.symetries([0,1,2,2,0]),
      }));""")
    assert r["melange"] == {"simples": 1, "doubles": 2, "triples": 3, "vides": 1}
    # Le N du milieu remet le compteur à zéro : trois d'affilée, pas cinq.
    assert r["suite"] == 3
    # Les extrêmes se répondent, la deuxième paire non : une symétrie.
    assert r["symetrie"] == 1


def test_les_bons_resultats_se_comptent_sur_les_places_identiques():
    """C'est la mesure sur laquelle repose toute la réduction : deux grilles
    à N-1 l'une de l'autre couvrent les mêmes rangs."""
    r = js("""
      const ref = [0,1,2,0,1,2,0];
      console.log(JSON.stringify({
        pareil: A.bonsResultats(ref, ref),
        deuxEcarts: A.bonsResultats(ref, [1,1,2,0,1,2,2]),
        rien: A.bonsResultats([0,0,0], [1,1,1]),
      }));""")
    assert r["pareil"] == 7
    assert r["deuxEcarts"] == 5
    assert r["rien"] == 0


def test_un_groupe_borne_ses_propres_matchs_et_pas_la_grille():
    """La demande, mot pour mot : « j'ai un groupe de trois matchs où j'ai mis
    1 pour le favori et N pour couvrir la surprise ; j'en attends au plus deux
    nuls, pas trois ».

    Ce n'est PAS un maximum de deux nuls sur la grille : celui-là laisserait
    passer trois nuls groupés dès qu'il y en a zéro ailleurs, et écarterait
    des grilles saines dont les nuls sont ailleurs.
    """
    r = js("""
      const g = A.enumerer([[0,1],[0,1],[0,1],[0,1],[0,1],[0],[0]]);
      const groupe = {matchs: [0, 1, 2], nul: {max: 2}};
      const nnn = [1,1,1,0,0,0,0], ailleurs = [0,0,0,1,1,1,0];
      const surLaGrille = A.filtrer(g, {nul: {max: 2}});
      const surLeGroupe = A.filtrer(g, {groupes: [groupe]});
      console.log(JSON.stringify({
        total: g.length,
        grille: surLaGrille.length,
        groupe: surLeGroupe.length,
        // NNN sur le groupe, rien ailleurs : le filtre de grille le laisse
        // passer, celui de groupe l'écarte. C'est tout l'écart entre les deux.
        grilleGardeNNN: A.retenue(nnn, {nul: {max: 2}}),
        groupeEcarteNNN: A.retenue(nnn, {groupes: [groupe]}),
        // Trois nuls, mais hors du groupe : le groupe s'en moque.
        groupeGardeAilleurs: A.retenue(ailleurs, {groupes: [groupe]}),
      }));""")
    assert r["total"] == 32
    assert r["grilleGardeNNN"] is False
    assert r["groupeEcarteNNN"] is False
    assert r["groupeGardeAilleurs"] is True
    # Le filtre de groupe ne touche qu'aux trois premiers matchs : il garde
    # donc strictement plus de grilles que le même maximum sur la grille.
    assert r["groupe"] > r["grille"], (r["groupe"], r["grille"])


def test_la_cote_plausible_tranche_comme_le_python():
    """L'atelier écarte les cotes déjà réglées comme le fait la collecte. Deux
    implémentations d'une même règle finissent par diverger si rien ne les
    compare : voici ce qui les compare."""
    import dater_grilles as dg
    cas = [[1.54, 4.3, 5.1], [250.0, 250.0, 1.0], [1.05, 12.0, 30.0],
           [1.2, 4.0, 101.0], [1.06, 4.0, 100.0], [2.0, None, 3.0],
           [1.0, 1.0, 1.0], [3.0, 3.0]]
    r = js(f"""
      const cas = {json.dumps(cas)};
      console.log(JSON.stringify(cas.map(A.cotePlausible)));""")
    attendu = [dg.cote_plausible(c) for c in cas]
    assert r == attendu, list(zip(cas, r, attendu))


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except Exception as e:
            print(f"  ECHEC  {nom} : {type(e).__name__} {str(e)[:280]}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
