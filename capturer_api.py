"""Écouter ce que la page demande au serveur, pour trouver l'API des grilles.

POURQUOI. Les noms d'équipes n'apparaissent qu'UNE FOIS dans le HTML d'une
grille, dans le DOM déjà rendu : la grille n'est pas dans la page, elle y
arrive par une requête réseau. Or l'état applicatif que la page embarque
(PRELOADED_STATE) montre que le modèle de données de Winamax porte, pour
chaque match, un `matchStart` en horodatage Unix, des identifiants d'équipes,
et des références Sportradar (`sr:tournament:`, `sr:season:`).

Si la réponse de cette requête a la même forme, elle contient la DATE EXACTE
de chaque match et des IDENTIFIANTS STABLES. Ce serait mieux que tout ce qu'on
a construit jusqu'ici : plus d'interpolation à quatre jours près, plus de
dictionnaire français-anglais à valider — des clés.

Ce script n'invente rien : il ouvre une grille, enregistre toutes les
requêtes qu'elle déclenche, et signale celles dont la réponse contient les
équipes affichées. Rien n'est envoyé nulle part, tout reste dans diagnostic/.

    python capturer_api.py 4168
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.winamax.fr/paris-sportifs/grilles/{type}-{id}"
DIAGNOSTIC = Path(__file__).parent / "diagnostic"

# Ce qu'on ne veut pas voir défiler : images, polices, feuilles de style.
INTERESSANT = {"xhr", "fetch", "document", "script"}


def capturer(grille_type: str, grille_id: int, attente_ms: int = 8000):
    DIAGNOSTIC.mkdir(exist_ok=True)
    url = BASE_URL.format(type=grille_type, id=grille_id)
    echanges = []

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        page = nav.new_page(locale="fr-FR", timezone_id="Europe/Paris")

        def sur_reponse(reponse):
            if reponse.request.resource_type not in INTERESSANT:
                return
            try:
                corps = reponse.body()
            except Exception:                            # noqa: BLE001
                return                                   # réponse déjà libérée
            echanges.append({"url": reponse.url, "statut": reponse.status,
                             "type": reponse.request.resource_type,
                             "taille": len(corps), "corps": corps})

        # LES WEBSOCKETS AUSSI. Un site de paris pousse ses cotes en continu,
        # et rien n'oblige la grille à voyager autrement. La première version
        # de ce script n'écoutait que les requêtes classiques : sur 50
        # réponses, les plus grosses étaient un hymne et un jingle en MP3.
        trames = []

        def sur_websocket(ws):
            trames.append(("ouverture", ws.url))
            ws.on("framereceived", lambda charge: trames.append(("recu", charge)))
            ws.on("framesent", lambda charge: trames.append(("envoye", charge)))

        page.on("websocket", sur_websocket)
        page.on("response", sur_reponse)
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(attente_ms)

        # Les équipes réellement affichées : c'est elles qu'on va chercher
        # dans les réponses, plutôt que de deviner à quoi ressemble l'API.
        equipes = []
        try:
            lignes = page.locator(".grid-line")
            for i in range(min(lignes.count(), 3)):
                noms = lignes.nth(i).locator("[class*='sc-jAZUkk']")
                for j in range(noms.count()):
                    texte = (noms.nth(j).inner_text() or "").strip()
                    if texte:
                        equipes.append(texte)
        except Exception:                                # noqa: BLE001
            pass
        nav.close()

    print(f"\n{len(echanges)} réponse(s) enregistrée(s)")
    ouvertures = [u for genre, u in trames if genre == "ouverture"]
    echangees = [c for genre, c in trames if genre != "ouverture"]
    print(f"{len(ouvertures)} websocket(s), {len(echangees)} trame(s) échangée(s)")
    for u in ouvertures:
        print(f"    ws : {u}")
    print(f"équipes lues à l'écran : {equipes[:6] or 'aucune'}\n")

    # Les trames qui nomment les équipes de la grille sont la piste directe.
    if equipes and echangees:
        porteuses_ws = []
        for i, charge in enumerate(echangees):
            texte = charge if isinstance(charge, str) else charge.decode("utf-8", "replace")
            trouvees = [q for q in equipes if q in texte]
            if len(trouvees) >= 2:
                porteuses_ws.append((i, texte, trouvees))
        if porteuses_ws:
            print(f"{len(porteuses_ws)} TRAME(S) WEBSOCKET CONTENANT LES ÉQUIPES :")
            for i, texte, trouvees in porteuses_ws[:3]:
                dest = DIAGNOSTIC / f"ws-{grille_type}-{grille_id}-{i}.txt"
                dest.write_text(texte, encoding="utf-8")
                print(f"    trame {i} | {len(texte)} caractères | "
                      f"{len(trouvees)} équipe(s) -> {dest}")
                print(f"    aperçu : {texte[:300]}")
        else:
            print("Aucune trame websocket ne nomme les équipes non plus.")
            gros = sorted(echangees, key=lambda c: -len(c))[:5]
            for c in gros:
                texte = c if isinstance(c, str) else c.decode("utf-8", "replace")
                print(f"    trame de {len(texte)} caractères : {texte[:160]}")

    porteuses = []
    for e in echanges:
        if not equipes:
            continue
        texte = e["corps"].decode("utf-8", "replace")
        trouvees = [q for q in equipes if q in texte]
        if len(trouvees) >= 2 and e["type"] in {"xhr", "fetch"}:
            porteuses.append((e, trouvees))

    if porteuses:
        print("RÉPONSES CONTENANT LES ÉQUIPES DE LA GRILLE :")
        for i, (e, trouvees) in enumerate(porteuses):
            dest = DIAGNOSTIC / f"api-{grille_type}-{grille_id}-{i}.json"
            dest.write_bytes(e["corps"])
            print(f"\n  {e['url']}")
            print(f"    statut {e['statut']} | {e['taille']} octets | "
                  f"{len(trouvees)} équipe(s) trouvée(s)")
            print(f"    -> {dest}")
            try:
                donnees = json.loads(e["corps"])
                apercu = json.dumps(donnees, ensure_ascii=False)[:400]
                print(f"    aperçu : {apercu}")
            except json.JSONDecodeError:
                print("    (réponse non JSON)")
    else:
        print("Aucune réponse XHR ne contient les équipes affichées.")
        print("Les requêtes vues, par taille décroissante (tous types) :")
        for e in sorted(echanges, key=lambda x: -x["taille"])[:15]:
            print(f"    {e['taille']:>8} o  {e['statut']}  {e['type']:<9} {e['url'][:100]}")

    journal = DIAGNOSTIC / f"reseau-{grille_type}-{grille_id}.txt"
    lignes = [f"{e['statut']:>4} {e['type']:<9} {e['taille']:>9} {e['url']}"
              for e in echanges]
    if trames:
        lignes.append("")
        lignes.append(f"--- {len(trames)} événement(s) websocket ---")
        for genre, charge in trames:
            texte = charge if isinstance(charge, str) else str(charge)
            lignes.append(f"{genre:<10} {len(texte):>8} {texte[:200]}")
    journal.write_text("\n".join(lignes), encoding="utf-8")
    print(f"\nJournal complet des requêtes : {journal}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Trouver l'API des grilles Winamax")
    ap.add_argument("id", type=int, help="identifiant de grille, ex : 4168")
    ap.add_argument("--type", default="grille7",
                    choices=["grille7", "grille9", "grille12"])
    ap.add_argument("--attente", type=int, default=8000,
                    help="millisecondes d'observation après chargement")
    args = ap.parse_args()
    capturer(args.type, args.id, args.attente)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
