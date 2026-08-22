#!/bin/sh
# Sauvegarder les collectes qu'on n'a pas le droit de publier.
#
# POURQUOI UN SECOND DÉPÔT, ET PAS UN SECOND DOSSIER. La demande était de
# pousser les grilles Pronosoft comme celles de Winamax, dans deux dossiers du
# même dépôt. Trois faits l'interdisent, et le troisième est le décisif :
#
#   1. les mentions légales de Pronosoft disent « il est interdit de reproduire
#      et rediffuser tout ou partie de ces contenus » — un dépôt public est
#      une rediffusion, indexée et clonable ;
#   2. lotofoot-tracker est public, et doit le rester : sur le plan gratuit,
#      « GitHub Pages in public repositories » — le site meurt si le dépôt
#      passe en privé ;
#   3. et même en payant, cela ne suffirait pas. La doc GitHub est explicite :
#      « GitHub Pages sites are publicly available on the internet, even if the
#      repository for the site is private ». Vérifié sur le nôtre :
#      data/index_site.json répond 200 depuis l'adresse Pages. Une grille
#      Pronosoft posée sous data/ serait donc téléchargeable par tout le monde,
#      dépôt privé ou non.
#
# Les dépôts privés, eux, sont gratuits et illimités. D'où ce montage : un
# dépôt privé par dossier à sauvegarder, niché dans le dossier lui-même. Le
# dépôt principal les ignore — ils sont dans son .gitignore — donc les deux ne
# se voient jamais.
#
# INSTALLATION, UNE FOIS PAR DOSSIER. Créer un dépôt PRIVÉ sur
# https://github.com/new, sans README ni .gitignore, puis :
#
#     cd data/pronosoft
#     git init && git add -A
#     git commit -m "Sauvegarde des grilles Pronosoft"
#     git branch -M main
#     git remote add origin https://github.com/<vous>/lotofoot-donnees.git
#     git push -u origin main
#
# Ensuite ce script s'en occupe, et quotidien.sh l'appelle. Un dossier sans
# .git est simplement ignoré : rien à configurer pour ne pas s'en servir.
cd "$(dirname "$0")" || exit 1
mkdir -p diagnostic
JOURNAL="diagnostic/quotidien.log"

trouve=0
for dossier in data/*/; do
    [ -d "$dossier/.git" ] || continue
    trouve=1
    nom=$(basename "$dossier")
    # Le sous-shell isole le cd : sans lui, un échec laisserait le script
    # dans le mauvais dossier pour le tour suivant.
    (
        cd "$dossier" || exit 1
        git add -A
        if git diff --cached --quiet; then
            echo "  $nom : rien de nouveau" >> "../../$JOURNAL"
            exit 0
        fi
        combien=$(git diff --cached --numstat | wc -l | tr -d ' ')
        git commit -q -m "Collecte du $(date '+%Y-%m-%d')" >> "../../$JOURNAL" 2>&1
        if git push -q origin HEAD >> "../../$JOURNAL" 2>&1; then
            echo "  $nom : $combien fichier(s) sauvegardé(s)" >> "../../$JOURNAL"
        else
            # UN PUSH RATÉ N'EST PAS UNE PERTE. Le commit est fait : la donnée
            # est versionnée en local et repartira au prochain passage.
            echo "  $nom : push impossible, $combien fichier(s) commités en local" \
                >> "../../$JOURNAL"
        fi
    )
done

if [ "$trouve" = 0 ]; then
    echo "  aucune sauvegarde configurée (voir l'entête de sauver_donnees.sh)" \
        >> "$JOURNAL"
fi
