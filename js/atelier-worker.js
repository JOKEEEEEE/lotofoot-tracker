/* Le calcul lourd, hors du fil qui dessine.
 *
 * POURQUOI UN TRAVAILLEUR. Réduire 6 500 grilles prend près de quatre
 * secondes, et pendant ce temps un onglet qui calcule dans le fil principal
 * ne répond plus : ni défilement, ni clic, ni curseur. L'utilisateur ne voit
 * pas « ça calcule », il voit « c'est cassé ». Le travail part donc ici, et la
 * page reste vivante — elle peut même annoncer qu'elle travaille.
 *
 * ON NE RENVOIE JAMAIS LES GRILLES RETENUES EN ENTIER. Un filtre large en
 * laisse passer cent mille : les recopier d'un fil à l'autre coûterait plus
 * cher que de les avoir calculées. On renvoie des comptes, un aperçu, et le
 * jeu réduit — le seul qu'on joue vraiment.
 */
import * as A from "./atelier.js";

const APERCU = 40;

self.onmessage = (e) => {
  const {jeton, choix, regles, garantie, couverture} = e.data;
  const total = A.compter(choix);
  const vides = choix.some(m => !m.length);
  if (vides) {
    self.postMessage({jeton, total: 0, vides: true});
    return;
  }
  const toutes = A.enumerer(choix);
  if (toutes === null) {
    self.postMessage({jeton, total, trop: A.PLAFOND_ENUMERATION});
    return;
  }
  const retenues = A.filtrer(toutes, regles);
  const reponse = {
    jeton, total, retenues: retenues.length,
    apercu: A.versTexte(retenues.slice(0, APERCU)).split("\n").filter(Boolean),
  };
  if (garantie != null && retenues.length) {
    const r = A.reduire(retenues, garantie, couverture);
    if (r === null) reponse.tropPourReduire = A.PLAFOND_REDUCTION;
    else reponse.reduction = {n: r.jeu.length, couvertes: r.couvertes,
                              taux: r.taux, texte: A.versTexte(r.jeu)};
  }
  self.postMessage(reponse);
};
