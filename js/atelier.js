/* Le moteur de l'atelier : combinatoire, filtres, réduction.
 *
 * AUCUN DOM ICI. Ce fichier ne touche pas à la page, ce qui permet de
 * l'exécuter avec node et de tester ses règles au lieu de les regarder
 * marcher. Une grille multiple est un tableau de tableaux d'issues, chaque
 * issue valant 0 pour le 1, 1 pour le N et 2 pour le 2 :
 *
 *     [[0], [0,1], [0,1,2]]   un simple, un double, un triple
 *
 * Une grille simple est un tableau d'entiers de la même longueur.
 */

export const ISSUES = ["1", "N", "2"];
/* Au-delà, on n'énumère pas : quinze triples font 4,7 millions de grilles et
 * le navigateur s'arrête avant nous. Le compte, lui, reste exact — il se
 * calcule sans rien énumérer. */
export const PLAFOND_ENUMERATION = 300000;
/* La réduction compare chaque grille à toutes les autres. Au-delà, le carré
 * devient déraisonnable et il vaut mieux filtrer davantage en amont. */
export const PLAFOND_REDUCTION = 20000;

export function compter(grille) {
  return grille.reduce((n, m) => n * (m.length || 1), 1);
}

export function synthese(grille) {
  const s = {simples: 0, doubles: 0, triples: 0, vides: 0};
  for (const m of grille) {
    if (m.length === 1) s.simples++;
    else if (m.length === 2) s.doubles++;
    else if (m.length === 3) s.triples++;
    else s.vides++;
  }
  return s;
}

export function enumerer(grille, plafond = PLAFOND_ENUMERATION) {
  const total = compter(grille);
  if (grille.some(m => !m.length)) return [];
  if (total > plafond) return null;          // null : trop, pas « aucune »
  let sortie = [[]];
  for (const m of grille) {
    const suite = [];
    for (const debut of sortie) for (const i of m) suite.push([...debut, i]);
    sortie = suite;
  }
  return sortie;
}

/* --- les mesures d'une grille simple, telles que les nomme PronoFoot ------ */

export function compteSignes(g) {
  const c = [0, 0, 0];
  for (const x of g) c[x]++;
  return c;
}

export function consecutifsMax(g, signe) {
  let record = 0, suite = 0;
  for (const x of g) { suite = x === signe ? suite + 1 : 0; if (suite > record) record = suite; }
  return record;
}

/** Un changement de signe entre le match m et le match m+1. */
export function alternances(g) {
  let n = 0;
  for (let i = 1; i < g.length; i++) if (g[i] !== g[i - 1]) n++;
  return n;
}

/** Un même signe sur le match m et le match (longueur+1-m), compté par paires. */
export function symetries(g) {
  let n = 0;
  for (let i = 0, j = g.length - 1; i < j; i++, j--) if (g[i] === g[j]) n++;
  return n;
}

/** Une suite 1-N-2 ou 2-N-1 sur trois matchs consécutifs. */
export function diagonales(g) {
  let n = 0;
  for (let i = 0; i + 2 < g.length; i++) {
    const [a, b, c] = [g[i], g[i + 1], g[i + 2]];
    if (b === 1 && ((a === 0 && c === 2) || (a === 2 && c === 0))) n++;
  }
  return n;
}

/** Le nombre de suites DIFFÉRENTES de `taille` signes consécutifs. */
export function suitesDistinctes(g, taille) {
  const vues = new Set();
  for (let i = 0; i + taille <= g.length; i++) vues.add(g.slice(i, i + taille).join(""));
  return vues.size;
}

/** Le produit des cotes de la grille : ce que rapporterait un euro si elle sort. */
export function produitCotes(g, cotes) {
  let p = 1;
  for (let i = 0; i < g.length; i++) {
    const trio = cotes[i];
    if (!trio || !trio[g[i]]) return null;   // une cote manquante ne vaut pas 1
    p *= trio[g[i]];
  }
  return p;
}

/* --- les filtres ---------------------------------------------------------- */

const DANS = (v, borne) => v >= (borne.min ?? -Infinity) && v <= (borne.max ?? Infinity);

/**
 * `regles` regroupe ce que l'atelier sait conditionner. Chaque entrée est
 * facultative, et une entrée absente ne filtre rien — c'est ce qui permet
 * d'ajouter un critère sans toucher aux autres.
 */
export function retenue(g, regles = {}, cotes = null) {
  const c = compteSignes(g);
  for (const [k, i] of [["un", 0], ["nul", 1], ["deux", 2]])
    if (regles[k] && !DANS(c[i], regles[k])) return false;
  for (const [k, i] of [["suiteUn", 0], ["suiteNul", 1], ["suiteDeux", 2]])
    if (regles[k] && !DANS(consecutifsMax(g, i), regles[k])) return false;
  if (regles.alternances && !DANS(alternances(g), regles.alternances)) return false;
  if (regles.symetries && !DANS(symetries(g), regles.symetries)) return false;
  if (regles.diagonales && !DANS(diagonales(g), regles.diagonales)) return false;
  for (const [k, t] of [["paires", 2], ["tierces", 3], ["quartes", 4]])
    if (regles[k] && !DANS(suitesDistinctes(g, t), regles[k])) return false;
  if (regles.cote && cotes) {
    const p = produitCotes(g, cotes);
    // Sans cote complète, on ne peut ni retenir ni écarter sur ce critère :
    // on laisse passer plutôt que d'exclure sur une donnée manquante.
    if (p !== null && !DANS(p, regles.cote)) return false;
  }
  if (regles.combinaisons && regles.combinaisons.length) {
    const signature = c.join("-");
    if (!regles.combinaisons.includes(signature)) return false;
  }
  return true;
}

export function filtrer(grilles, regles = {}, cotes = null) {
  return grilles.filter(g => retenue(g, regles, cotes));
}

/* --- la réduction --------------------------------------------------------- */

export function bonsResultats(a, b) {
  let n = 0;
  for (let i = 0; i < a.length; i++) if (a[i] === b[i]) n++;
  return n;
}

/**
 * Le plus petit ensemble de grilles garantissant `garantie` bons résultats
 * pour au moins `couverture` des grilles visées.
 *
 * ALGORITHME GLOUTON, ET C'EST ASSUMÉ. Trouver l'ensemble minimal exact est un
 * problème de couverture, NP-difficile ; le glouton en donne un à un facteur
 * logarithmique près, en une fraction du temps. On prend à chaque tour la
 * grille qui couvre le plus de grilles encore découvertes.
 */
export function reduire(grilles, garantie, couverture = 1) {
  if (!grilles.length) return {jeu: [], couvertes: 0, taux: 0};
  if (grilles.length > PLAFOND_REDUCTION) return null;
  const n = grilles.length;
  const seuil = Math.ceil(couverture * n);
  // Qui couvre qui : calculé une fois, relu à chaque tour.
  const couvre = grilles.map(a =>
    grilles.reduce((s, b, j) => (bonsResultats(a, b) >= garantie ? s.add(j) : s), new Set()));
  const restantes = new Set(grilles.map((_, i) => i));
  const jeu = [];
  while (n - restantes.size < seuil) {
    let meilleur = -1, gain = 0;
    for (let i = 0; i < n; i++) {
      let g = 0;
      for (const j of couvre[i]) if (restantes.has(j)) g++;
      if (g > gain) { gain = g; meilleur = i; }
    }
    if (meilleur < 0) break;                 // plus rien à gagner
    jeu.push(grilles[meilleur]);
    for (const j of couvre[meilleur]) restantes.delete(j);
  }
  return {jeu, couvertes: n - restantes.size, taux: (n - restantes.size) / n};
}

export function versTexte(grilles) {
  return grilles.map(g => g.map(i => ISSUES[i]).join("")).join("\n");
}
