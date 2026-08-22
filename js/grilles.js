/* Ce que les deux pages doivent lire de la même façon.
 *
 * UN DÉCODEUR EN DEUX EXEMPLAIRES FINIT PAR EN FAIRE DEUX. `strPoolResult`
 * s'écrit à l'envers — le premier triplet décrit le DERNIER match — et c'est
 * l'erreur la plus facile à commettre et la plus dure à voir : la page
 * afficherait des résultats plausibles, simplement attribués au mauvais match.
 * Une seule version, testée contre le Python par test_site.py.
 */
const ISSUES = ["1", "N", "2"];

function decoderResultat(code, nb) {
  if (!code || code.length !== 3 * nb) return Array(nb).fill(null);
  const triplets = [];
  for (let i = 0; i < code.length; i += 3) triplets.push(code.slice(i, i + 3));
  return triplets.reverse().map(t => {
    const gagnantes = ISSUES.filter((_, i) => t[i] === "1");
    return gagnantes.length ? gagnantes : null;
  });
}

const eur = (v, d = 2) => v == null ? "—" :
  v.toLocaleString("fr-FR", {minimumFractionDigits: d, maximumFractionDigits: d}) + " €";
/* 2026-08-16 devient 16/08/26 : c'est la forme qu'on lit sur un bulletin. */
const jjmmaa = d => /^\d{4}-\d{2}-\d{2}$/.test(d || "")
  ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(2, 4)}` : "—";
const num = v => v == null ? "—" : v.toLocaleString("fr-FR");

const STATUTS = {CLOSED: "réglée", OPEN: "en cours", CANCELLED: "annulée",
                 SUSPENDED: "suspendue"};
const PROVENANCES = {w: "Winamax", p: "Pinnacle (clôture)", b: "Bet365 (clôture)",
                     f: "Footiqo (clôture)", "?": "source inconnue"};
