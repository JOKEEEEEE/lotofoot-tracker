#!/bin/sh
# Collecte quotidienne des grilles encore récentes.
#
# POURQUOI CHAQUE JOUR. Les cotes 1/N/2 et `repart` ne sont
# servies que sur les grilles récentes : la grille 4168 les a, la grille 100
# ne les a plus. Une grille par jour bascule ainsi hors de portée, sans
# rattrapage possible. C'est la seule partie du projet qui court après le
# temps.
#
# POURQUOI PAS GITHUB ACTIONS. Winamax bloque les IP de centre de données,
# runners GitHub compris. Ce script tourne donc sur la machine, par launchd.
#
# Installation. `launchctl load` est déprécié et répond « Load failed: 5 » sur
# macOS récent ; c'est `bootstrap` qu'il faut, et `bootout` d'abord pour
# écarter un reliquat.
#     chmod +x quotidien.sh
#     cp fr.lotofoot.quotidien.plist ~/Library/LaunchAgents/
#     launchctl bootout gui/$(id -u)/fr.lotofoot.quotidien 2>/dev/null
#     launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/fr.lotofoot.quotidien.plist
#
# Vérification :
#     launchctl print gui/$(id -u)/fr.lotofoot.quotidien | head -15
#     tail -20 diagnostic/quotidien.log

# PAS DE `set -e`. Il faisait mourir le script en silence : le 20 août, la
# page d'accueil n'ayant pas répondu, la collecte sortait en erreur et le
# script s'arrêtait sans écrire une ligne expliquant pourquoi. Un travail
# programmé qui échoue sans le dire est pire qu'un travail qui n'existe pas.
cd "$(dirname "$0")" || exit 1
mkdir -p diagnostic
JOURNAL="diagnostic/quotidien.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$JOURNAL"

# shellcheck disable=SC1091
. .venv/bin/activate

# Dix grilles : les actives, plus celles qui viennent de se clore et dont la
# répartition n'arrive qu'après le règlement. Redemander une grille déjà
# collectée est voulu — c'est ainsi que `repart` se remplit quand il paraît.
# LES TROIS TYPES, PAS SEULEMENT LA GRILLE 7. Les cotes et la répartition
# s'effacent aussi vite sur les grilles 9 et 12 — et celles-ci sont bien plus
# rares : 22 et 403 grilles contre 4 175. Chaque grille 9 manquée pèse donc
# cinquante fois plus lourd dans son historique qu'une grille 7.
#
# Un type qui échoue n'empêche pas les autres : on note et on continue.
echec=0
for type in grille7 grille9 grille12; do
    if ! python collecter_ws.py --type "$type" --recentes 6 >> "$JOURNAL" 2>&1; then
        echo "collecte $type en échec — on réessaiera demain" >> "$JOURNAL"
        echec=1
    fi
done
if [ "$echec" = 1 ] && ! ls data/pools/*/*.json >/dev/null 2>&1; then
    exit 0
fi

# L'INDEX DU SITE SE REFAIT AVEC LA COLLECTE. Sans cette ligne, le site
# publié par GitHub Pages afficherait indéfiniment la base d'hier alors que
# les fichiers de grille, eux, seraient à jour — l'incohérence la plus
# pénible à diagnostiquer, puisque tout paraît fonctionner.
python construire_site.py >> "$JOURNAL" 2>&1 || \
    echo "index du site non refait" >> "$JOURNAL"

# Le dépôt d'abord à jour, sinon le push sera refusé et la collecte du
# lendemain repartirait sur un dépôt divergent.
git pull --rebase --autostash -q origin main >> "$JOURNAL" 2>&1 || {
    echo "pull impossible, on garde la collecte en local" >> "$JOURNAL"
    exit 0
}

# LE GARDE-FOU AVANT DE PUBLIER. data/pronosoft/ est versionné parce qu'il ne
# porte que des faits — affiches, cotes de marché, rapports de la FDJ — et
# jamais le pourcentage de joueurs, qui est la production de Pronosoft. Un
# fichier ancien oublié suffirait à rompre cette règle sans que personne ne
# le voie : on vérifie, et on n'ajoute pas ce dossier si ça coince.
A_PUBLIER="data/pools data/index_site.json data/cotes_site.json"
if python outils/retirer_public.py --verifier >> "$JOURNAL" 2>&1; then
    A_PUBLIER="$A_PUBLIER data/pronosoft"
else
    echo "des pourcentages traînent dans data/pronosoft — dossier NON publié," \
         "lancer : python outils/retirer_public.py" >> "$JOURNAL"
fi

# shellcheck disable=SC2086
git add $A_PUBLIER
if git diff --cached --quiet; then
    echo "rien de nouveau" >> "$JOURNAL"
    exit 0
fi
git commit -q -m "Collecte quotidienne $(date '+%Y-%m-%d')" >> "$JOURNAL" 2>&1
if git push -q origin main >> "$JOURNAL" 2>&1; then
    # DIRE QUE ÇA A MARCHÉ. Toutes les commandes git étant en -q, un run
    # réussi n'écrivait rien après le bilan de collecte — indiscernable d'un
    # script mort en route. On a cherché la panne une demi-heure avant de
    # constater que les commits étaient bien sur le serveur.
    echo "commité et poussé" >> "$JOURNAL"
else
    echo "push impossible — les données restent commitées en local" >> "$JOURNAL"
fi

