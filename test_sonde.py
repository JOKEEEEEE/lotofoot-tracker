"""Tests de la sonde à cotes : ce qu'elle reconnaît, et ce qu'elle ignore.

La sonde ne cherche pas un nom de champ mais une signature arithmétique.
Elle doit donc reconnaître une cote nommée n'importe comment, et ne pas
crier au loup devant trois nombres quelconques.

    python test_sonde.py        (ou : pytest test_sonde.py)
"""

from sonder_cotes import inventaire, triplets_suspects


def _chemins(trouves):
    return [(c, tuple(cles)) for c, cles, _, _ in trouves]


def test_reconnait_une_cote_quel_que_soit_le_nom_du_champ():
    """Le jour où Winamax renomme ses champs, la sonde doit tenir.

    C'est toute sa raison d'être : on cherche précisément parce qu'on ne
    sait pas comment ça s'appelle.
    """
    trame = {"matches": {"1": {"a": 2.40, "b": 3.35, "c": 2.70}}}
    trouves = triplets_suspects(trame)
    assert ("matches.1", ("a", "b", "c")) in _chemins(trouves), trouves
    assert abs(trouves[0][3] - 1.0855) < 0.001, trouves


def test_les_cotes_les_plus_vraisemblables_viennent_en_tete():
    """Un score glissé à la place d'une cote produit un triplet valide mais
    à marge plus lourde. L'ordre de lecture doit mettre le vrai devant."""
    trame = {"m": {"odds1": 2.40, "oddsX": 3.35, "odds2": 2.70, "score1": 2}}
    trouves = sorted(triplets_suspects(trame), key=lambda t: t[3])
    assert tuple(trouves[0][1]) == ("odds1", "oddsX", "odds2"), trouves


def test_ignore_ce_qui_ne_paie_rien():
    """Des cotes à null, des entiers de comptage, des montants : rien de
    tout cela ne somme comme un marché 1/N/2."""
    assert triplets_suspects({"m": {"odds1": None, "oddsX": None, "odds2": None}}) == []
    assert triplets_suspects({"m": {"a": 1, "b": 1, "c": 1}}) == []
    assert triplets_suspects({"m": {"a": 11563.5, "b": 10000, "c": 3000}}) == []
    # Trois cotes qui paieraient plus qu'elles ne collectent : pas un marché.
    assert triplets_suspects({"m": {"a": 5.0, "b": 5.0, "c": 5.0}}) == []


def test_ecarte_les_marges_impossibles():
    """Une marge de 1,9 n'est pas un marché : elle rendrait 53 centimes par
    euro misé. C'est un triplet de nombres qui se trouve être dans la bonne
    plage, rien de plus."""
    assert triplets_suspects({"m": {"a": 1.5, "b": 1.5, "c": 1.5}}) == []
    # Une cote de 1,00 ne rapporte rien : ce n'est pas une cote, et elle ne
    # doit pas servir de troisième larron pour valider un triplet. Ici la
    # marge tomberait pile dans la plage sans cette exclusion.
    assert triplets_suspects({"m": {"a": 1.00, "b": 100.0, "c": 100.0}}) == []
    assert triplets_suspects({"m": {"a": 0.9, "b": 0.9, "c": 0.9}}) == []
    # Symétriquement, une valeur à quatre chiffres est un montant, pas une
    # cote : sans plafond elle passerait pour la troisième issue d'un marché.
    assert triplets_suspects({"m": {"a": 1.04, "b": 250.0, "c": 25.0}}) == []


def test_descend_dans_les_listes_et_les_objets_imbriques():
    trame = {"pools": [{"bets": {"x": {"h": 1.55, "d": 4.20, "a": 6.50}}}]}
    assert ("pools[0].bets.x", ("h", "d", "a")) in _chemins(triplets_suspects(trame))


def test_un_objet_trop_riche_en_nombres_n_est_pas_fouille():
    """Vingt nombres produisent 1 140 triplets, dont beaucoup passeraient le
    test de marge par hasard. On préfère ne rien dire que noyer le lecteur."""
    gros = {f"k{i}": 1.5 + i / 10 for i in range(20)}
    assert triplets_suspects({"m": gros}) == []


def test_inventaire_distingue_absente_et_vidée():
    """Une clé disparue du modèle et une clé mise à null ne racontent pas la
    même histoire : la première dit « ça n'existe plus », la seconde « ça
    existe, mais on ne te le sert pas »."""
    presentes, remplies = inventaire({
        1: {"odds1": None, "score1": 2},
        2: {"odds1": 2.4, "score1": 0},
        3: {"score1": 1},
    })
    assert presentes["odds1"] == 2 and remplies["odds1"] == 1
    # Un zéro est une valeur : un match qui finit 0-0 a bien un score.
    assert presentes["score1"] == 3 and remplies["score1"] == 3, remplies


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except Exception as e:
            print(f"  ECHEC  {nom} : {type(e).__name__} {str(e)[:200]}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
