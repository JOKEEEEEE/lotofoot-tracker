"""Tests des fonctions pures de scrape_grille.

Ces trois fonctions sont les seules du fichier qui se testent sans le site :
elles ne touchent ni au réseau ni au DOM. C'est aussi là que vivaient les
trois défauts du script de départ, d'où ces cas précis — chacun reproduit
une entrée qui renvoyait autrefois une valeur fausse ou nulle en silence.

    python test_parsing.py        (ou : pytest test_parsing.py)

Ce que ces tests NE couvrent PAS : les sélecteurs CSS, qui n'ont toujours
pas été confrontés au site réel. Un test au vert ici ne dit rien de la
validité du scraping. Voir le README.
"""

from scrape_grille import _parse_montant, _sans_accents, _score_de_ligne

# Les cinq espaces qui circulent dans les pages françaises. La version
# d'origine n'en retirait que deux : « 1<U+00A0>234,56 € », de loin la plus
# courante, repartait en `null` dans le JSON sans que rien ne le signale.
INSECABLE = " "        # NO-BREAK SPACE
FINE_INSEC = " "       # NARROW NO-BREAK SPACE
FINE = " "             # THIN SPACE
CHIFFRE = " "          # FIGURE SPACE

MONTANTS = [
    ("1 234,56 €", 1234.56),                    # espace ordinaire
    (f"1{INSECABLE}234,56 €", 1234.56),         # insécable — le cas qui cassait
    (f"1{FINE_INSEC}234,56 €", 1234.56),
    (f"1{FINE}234,56 €", 1234.56),
    (f"1{CHIFFRE}234,56 €", 1234.56),
    ("1.234,56 €", 1234.56),                    # point = milliers (fr)
    ("1,234.56", 1234.56),                      # virgule = milliers (en)
    ("1234.56", 1234.56),
    ("45 678,90 EUR", 45678.90),
    ("12", 12.0),                               # entier sans décimale
    ("0,00 €", 0.0),                            # zéro n'est pas None
    ("", None),
    (None, None),
    ("n/a", None),
]

SCORES = [
    ("PSG 2 - 1 OM", (2, 1)),
    ("PSG 2 – 1 OM", (2, 1)),                   # tiret demi-cadratin
    ("0 - 0", (0, 0)),                          # 0-0 est un score, pas une absence
    ("Coup d'envoi 15:30 — PSG 2 - 1 OM", (2, 1)),   # l'heure n'est pas candidate
    ("PSG 2 - 1 OM (mi-temps 1 - 0)", None),    # deux candidats : on refuse d'arbitrer
    ("18 - 21", None),                          # créneau horaire : au-delà de 20 buts
    ("PSG 21 - 3 OM", None),
    ("Match reporté", None),
    ("", None),
    (None, None),
]


def test_parse_montant():
    for texte, attendu in MONTANTS:
        obtenu = _parse_montant(texte)
        assert obtenu == attendu, f"_parse_montant({texte!r}) = {obtenu!r}, attendu {attendu!r}"


def test_score_de_ligne():
    for texte, attendu in SCORES:
        obtenu = _score_de_ligne(texte)
        assert obtenu == attendu, f"_score_de_ligne({texte!r}) = {obtenu!r}, attendu {attendu!r}"


def test_sans_accents():
    # Le test d'origine cherchait la chaîne exacte « Terminée » : une casse
    # ou un accent différents sur le site auraient fait passer TOUTES les
    # grilles pour non terminées, et le lot serait ressorti vide.
    for variante in ("Terminée", "TERMINÉE", "terminee", "Terminee", "TERMINEE"):
        assert "terminee" in _sans_accents(variante), variante
    for variante in ("Annulée", "ANNULÉE", "annulee"):
        assert "annul" in _sans_accents(variante), variante
    assert _sans_accents(None) == ""
    # Une grille en cours ne doit surtout pas être prise pour terminée.
    assert "terminee" not in _sans_accents("En cours")


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if not nom.startswith("test_"):
            continue
        try:
            fonction()
            print(f"  OK     {nom}")
        except AssertionError as e:
            print(f"  ECHEC  {nom} : {e}")
            echecs += 1
    print(f"\n{echecs} échec(s)")
    raise SystemExit(1 if echecs else 0)
