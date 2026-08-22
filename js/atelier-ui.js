/* L'atelier : composer une grille génératrice, la filtrer, la réduire.
 *
 * TROIS GESTES, DANS CET ORDRE. C'est la logique de PronoFoot Expert et elle
 * est bonne : on ouvre des doubles et des triples là où l'on hésite (la grille
 * génératrice), on écarte ce qui ne ressemble pas à une grille jouable (les
 * filtres), puis on ne garde que le plus petit jeu qui garantit encore N-1 ou
 * N-2 bons résultats (la réduction). Le premier geste décide du coût, le
 * deuxième de sa forme, le troisième de la facture.
 *
 * LA MOITIÉ DU TRAVAIL SE FAIT AILLEURS. Le moteur est dans atelier.js, sans
 * une ligne de DOM, pour que test_atelier.py puisse le passer au crible avec
 * node ; le calcul lourd part dans atelier-worker.js pour que la page ne gèle
 * pas. Ce fichier ne fait que montrer et écouter.
 */
import * as A from "./atelier.js";

const ISSUES = ["1", "N", "2"];
const TAILLES = [7, 8, 9, 12, 15];
const APERCU_LISTE = 600;      // grilles proposées au chargement

/* Chaque réglage est une borne basse et une borne haute sur une mesure. La
 * table dit son nom et ce qu'il compte : sans cette dernière colonne, personne
 * ne devine ce qu'est une « diagonale ».
 *
 * DEUX RANGS, PARCE QU'ON N'EN UTILISE QUE TROIS. Le nombre de 1, de N et de 2
 * décide de la forme d'une grille ; les suites la lissent. Le reste — hérité
 * de PronoFoot — sert rarement et encombrait la moitié du panneau : il passe
 * derrière un dépliant. */
const REGLAGES = [
  {cle: "un",          nom: "Nombre de 1",       aide: "Combien de matchs joués en 1 dans la grille."},
  {cle: "nul",         nom: "Nombre de N",       aide: "Combien de matchs joués en nul."},
  {cle: "deux",        nom: "Nombre de 2",       aide: "Combien de matchs joués en 2."},
  {cle: "suiteUn",     nom: "Suite de 1",        aide: "La plus longue série de 1 consécutifs."},
  {cle: "suiteNul",    nom: "Suite de N",        aide: "La plus longue série de nuls consécutifs."},
  {cle: "suiteDeux",   nom: "Suite de 2",        aide: "La plus longue série de 2 consécutifs."},
];
const REGLAGES_RARES = [
  {cle: "alternances", nom: "Alternances",       aide: "Combien de fois le signe change d'un match au suivant."},
  {cle: "symetries",   nom: "Symétries",         aide: "Combien de paires de matchs se répondent d'un bout à l'autre de la grille."},
  {cle: "diagonales",  nom: "Diagonales",        aide: "Combien de suites 1-N-2 ou 2-N-1 sur trois matchs consécutifs."},
  {cle: "paires",      nom: "Paires distinctes", aide: "Combien de couples de signes différents apparaissent (11, 1N, N2…)."},
  {cle: "tierces",     nom: "Tiercés distincts", aide: "Idem sur trois matchs consécutifs."},
  {cle: "quartes",     nom: "Quartés distincts", aide: "Idem sur quatre matchs consécutifs."},
];
const TOUS_REGLAGES = [...REGLAGES, ...REGLAGES_RARES];


let IDX = [], COTES = {};
let matchs = [];            // {nom, cotes:[c1,cN,c2]|null, source, sortie}
let choix = [];             // pour chaque match, les issues retenues
let groupes = [];           // bornes portant sur un sous-ensemble de matchs
let jeton = 0, travailleur = null, dernier = null;

const $ = id => document.getElementById(id);
const nb = v => v == null ? "—" : v.toLocaleString("fr-FR");

/* --- chargement ----------------------------------------------------------- */

async function demarrer() {
  const [idx, cotes] = await Promise.all([
    fetch("data/index_site.json").then(r => r.json()),
    fetch("data/cotes_site.json").then(r => r.json()).catch(() => ({})),
  ]);
  const c = idx.champs;
  IDX = idx.grilles.map(g => Object.fromEntries(c.map((n, i) => [n, g[i]])));
  COTES = cotes;
  const ouvertes = remplirSources();
  construireReglages();
  brancher();
  if (!depuisAdresse()) {
    if (ouvertes.length) charger(ouvertes[0].type, ouvertes[0].id);
    else vierge(7);
  }
}

/* SEULES LES GRILLES PAS ENCORE COMMENCÉES SE TRAVAILLENT. L'atelier prépare
 * un jeu ; une grille dont le premier match a été joué ne se prépare plus, elle
 * s'analyse — et ce n'est pas le même outil. C'est le coup d'envoi du PREMIER
 * match qui tranche, pas la fin de la grille : dès qu'une affiche est lancée,
 * la grille est partie. */
function aVenir(g) {
  return g.debut && new Date(g.debut) > new Date();
}

function remplirSources() {
  const s = $("f-source");
  const ouvertes = IDX.filter(aVenir)
    .sort((a, b) => a.debut.localeCompare(b.debut));
  if (ouvertes.length) {
    const reelles = document.createElement("optgroup");
    reelles.label = "Grilles à venir";
    for (const g of ouvertes) {
      const o = document.createElement("option");
      o.value = `${g.type}/${g.id}`;
      o.textContent = `Grille ${g.type} n°${g.id} — ${jjmmaa(g.date)}`;
      reelles.appendChild(o);
    }
    s.appendChild(reelles);
  }
  const vierges = document.createElement("optgroup");
  vierges.label = "Partir d'une grille vide";
  for (const t of TAILLES) {
    const o = document.createElement("option");
    o.value = `vierge:${t}`;
    o.textContent = `${t} matchs`;
    vierges.appendChild(o);
  }
  s.appendChild(vierges);
  $("dispo").textContent = ouvertes.length
    ? `${ouvertes.length} grille${ouvertes.length > 1 ? "s" : ""} pas encore commencée${
        ouvertes.length > 1 ? "s" : ""}`
    : "aucune grille à venir dans la base — lancez la collecte, ou partez d'une grille vide";
  return ouvertes;
}

function construireReglages() {
  poserReglages($("reglages"), REGLAGES);
  poserReglages($("reglages-rares"), REGLAGES_RARES);
}

function poserReglages(hote, liste) {
  for (const r of liste) {
    const ligne = document.createElement("div");
    ligne.className = "reglage";
    ligne.innerHTML =
      `<label for="min-${r.cle}" title="${r.aide}">${r.nom}</label>
       <input type="number" id="min-${r.cle}" placeholder="min" step="${r.pas || 1}"
              min="0" aria-label="${r.nom}, minimum">
       <input type="number" id="max-${r.cle}" placeholder="max" step="${r.pas || 1}"
              min="0" aria-label="${r.nom}, maximum">`;
    hote.appendChild(ligne);
  }
}

function brancher() {
  $("f-source").addEventListener("change", () => {
    const v = $("f-source").value;
    if (v.startsWith("vierge:")) { location.hash = ""; vierge(+v.slice(7)); }
    else location.hash = v;
  });
  $("reglages").addEventListener("input", relancer);
  $("garantie").addEventListener("change", relancer);
  $("couverture").addEventListener("change", relancer);
  $("rapide").addEventListener("click", e => {
    const b = e.target.closest("button[data-appliquer]");
    if (b) appliquerPartout(b.dataset.appliquer);
  });
  $("ajouter-groupe").addEventListener("click", () => {
    groupes.push({matchs: []});
    dessinerGroupes();
  });
  $("copier").addEventListener("click", copier);
  $("telecharger").addEventListener("click", telecharger);
  window.addEventListener("hashchange", depuisAdresse);
}

function depuisAdresse() {
  const m = /^#(\d+)\/(\d+)$/.exec(location.hash);
  if (!m) return false;
  charger(+m[1], +m[2]);
  return true;
}

function vierge(taille) {
  matchs = Array.from({length: taille}, (_, i) => ({nom: `Match ${i + 1}`}));
  choix = matchs.map(() => []);
  $("titre").textContent = `Grille vierge — ${taille} matchs`;
  $("origine").textContent = "à composer";
  dessiner();
}

/* LES COTES DU FICHIER NE SONT PRISES QU'EN DERNIER RECOURS, ET FILTRÉES.
 * data/cotes_site.json est la source vérifiée ; le fichier de la grille porte
 * aussi des cotes, mais certaines ont été relevées le match fini — un 1.00 y
 * dit le résultat plutôt que de le prévoir. D'où le passage par
 * cotePlausible, la même règle qu'à la collecte. */
function cotesDuMatch(m) {
  const vues = COTES[String(m.match_id)];
  if (vues) return {cotes: vues.slice(0, 3), source: vues[3]};
  const trio = [m.cote_1, m.cote_N, m.cote_2];
  if (A.cotePlausible(trio)) return {cotes: trio, source: "?"};
  return {cotes: null, source: null};
}

async function charger(type, id) {
  $("titre").textContent = `Grille ${type} n°${id}`;
  $("origine").textContent = "chargement…";
  let d;
  try {
    d = await fetch(`data/pools/grille${type}/${id}.json`).then(r => {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  } catch (e) {
    $("origine").textContent = "grille introuvable";
    return;
  }
  const sorties = decoderResultat(d.resultat_code, d.matches.length);
  matchs = d.matches.map((m, i) => ({
    nom: `${m.home || "?"} — ${m.away || "?"}`,
    sortie: sorties[i],
    ...cotesDuMatch(m),
  }));
  choix = matchs.map(() => []);
  const cotees = matchs.filter(m => m.cotes).length;
  $("titre").textContent = `Grille ${type} n°${id}`;
  $("origine").textContent =
    `${jjmmaa((d.fin || "").slice(0, 10))} · ${matchs.length} matchs · ` +
    `${cotees}/${matchs.length} cotés`;
  $("f-source").value = `${type}/${id}`;
  dessiner();
}

/* --- la grille génératrice ------------------------------------------------ */

function dessiner() {
  const corps = $("matchs");
  corps.innerHTML = "";
  matchs.forEach((m, i) => {
    const tr = document.createElement("tr");
    const nom = document.createElement("td");
    // Le numéro n'est pas décoratif : c'est lui que portent les jetons d'un
    // groupe, et sans lui personne ne sait quel match il vient de cocher.
    nom.innerHTML = `<b class="rang">${i + 1}</b>${m.nom}`;
    tr.appendChild(nom);
    ISSUES.forEach((issue, j) => {
      const td = document.createElement("td");
      td.className = "case";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "signe";
      b.setAttribute("aria-pressed", String(choix[i].includes(j)));
      if (m.sortie && m.sortie.includes(issue)) b.classList.add("sorti");
      b.innerHTML = `<b>${issue}</b><i>${m.cotes ? m.cotes[j].toFixed(2) : "—"}</i>`;
      b.title = m.cotes
        ? `${issue} à ${m.cotes[j].toFixed(2)} — cote ${
            (PROVENANCES[m.source] || {}).nom || "de provenance inconnue"}`
        : `${issue} — pas de cote connue`;
      b.addEventListener("click", () => basculer(i, j));
      td.appendChild(b);
      tr.appendChild(td);
    });
    const outils = document.createElement("td");
    outils.className = "outils";
    outils.innerHTML =
      `<button type="button" class="mini" data-ligne="${i}" data-quoi="favori"
               title="Ne garder que le favori de ce match">Cor.</button>
       <button type="button" class="mini" data-ligne="${i}" data-quoi="tout"
               title="Ouvrir ce match en triple">1N2</button>
       <button type="button" class="mini" data-ligne="${i}" data-quoi="rien"
               title="Vider ce match">×</button>`;
    outils.addEventListener("click", e => {
      const b = e.target.closest("button[data-quoi]");
      if (!b) return;
      const l = +b.dataset.ligne;
      if (b.dataset.quoi === "favori") choix[l] = favori(l) == null ? [] : [favori(l)];
      else if (b.dataset.quoi === "tout") choix[l] = [0, 1, 2];
      else choix[l] = [];
      dessiner();
    });
    tr.appendChild(outils);
    corps.appendChild(tr);
  });
  legender();
  resumerGrille();
  dessinerGroupes();
  relancer();
}

function basculer(i, j) {
  const dedans = choix[i].indexOf(j);
  if (dedans >= 0) choix[i].splice(dedans, 1);
  else choix[i] = [...choix[i], j].sort();
  dessiner();
}

/** Le favori d'un match : la cote la plus basse. Sans cote, pas de favori —
 *  on ne devine pas à la place de celui qui joue. */
function favori(i) {
  const c = matchs[i].cotes;
  if (!c) return null;
  return c.indexOf(Math.min(...c));
}

function appliquerPartout(quoi) {
  matchs.forEach((_, i) => {
    if (quoi === "favori") { const f = favori(i); choix[i] = f == null ? [] : [f]; }
    else if (quoi === "") choix[i] = [];
    else choix[i] = [...quoi].map(c => ISSUES.indexOf(c)).sort();
  });
  dessiner();
}

function legender() {
  // Une issue sortie et un match annulé portent le même liseré mais ne disent
  // pas la même chose : sur une grille à venir, le seul liseré possible est
  // celui d'un match déjà annulé, et annoncer « ce qui est sorti » là-dessus
  // laisserait croire que la grille est jouée.
  const sortis = matchs.filter(m => m.sortie && m.sortie.length === 1).length;
  const annules = matchs.filter(m => m.sortie && m.sortie.length === 3).length;
  const cotees = matchs.filter(m => m.cotes).length;
  const bouts = [];
  if (sortis) bouts.push("le liseré vert marque ce qui est sorti");
  if (annules) bouts.push(
    `${annules === 1 ? "un match est annulé" : `${annules} matchs sont annulés`} — ` +
    "les trois signes y sont gagnants, quoi que vous cochiez");
  bouts.push(cotees
    ? `« Cor. » retient le favori aux cotes (${cotees}/${matchs.length} matchs cotés)`
    : "aucune cote connue sur cette grille : « Cor. » ne peut rien retenir");
  $("legende").textContent = bouts.join(" · ") + ".";
}

function resumerGrille() {
  const s = A.synthese(choix);
  const total = s.vides ? 0 : A.compter(choix);
  $("synthese").innerHTML = tuiles([
    ["Simples", nb(s.simples)],
    ["Doubles", nb(s.doubles)],
    ["Triples", nb(s.triples)],
    ["Combinaisons", nb(total), "accent"],
    ["Coût à 1 €", total ? eur(total, 0) : "—"],
  ]);
  $("avert-grille").textContent = s.vides
    ? `${s.vides} match${s.vides > 1 ? "s" : ""} sans aucun signe : la grille ne produit rien.`
    : "";
}

const tuiles = liste => liste.map(([lab, val, classe]) =>
  `<div class="tuile"><span class="lab">${lab}</span>
     <span class="val chiffres ${classe || ""}">${val}</span></div>`).join("");

/* --- les groupes de matchs ------------------------------------------------ */

function dessinerGroupes() {
  // Changer de grille peut raccourcir la liste : un groupe qui désignait le
  // match 12 d'une grille 12 ne désigne rien sur une grille 7.
  for (const g of groupes)
    g.matchs = g.matchs.filter(j => j < matchs.length);
  const hote = $("groupes");
  hote.innerHTML = groupes.map((g, i) => `
    <div class="groupe-filtre">
      <div class="tete-groupe">Groupe ${i + 1}
        <button type="button" data-suppr="${i}" title="Supprimer ce groupe">×</button></div>
      <div class="jetons" data-groupe="${i}">${matchs.map((m, j) =>
        `<button type="button" data-match="${j}" title="${m.nom}"
          aria-pressed="${g.matchs.includes(j)}">${j + 1}</button>`).join("")}</div>
      <div class="bornes">${[["un", "1"], ["nul", "N"], ["deux", "2"]].map(([cle, sig]) => `
        <span>${sig}</span>
        <input type="number" min="0" placeholder="min" data-groupe="${i}"
          data-cle="${cle}" data-borne="min" aria-label="Groupe ${i + 1}, ${sig} minimum"
          value="${g[cle] && g[cle].min != null ? g[cle].min : ""}">
        <input type="number" min="0" placeholder="max" data-groupe="${i}"
          data-cle="${cle}" data-borne="max" aria-label="Groupe ${i + 1}, ${sig} maximum"
          value="${g[cle] && g[cle].max != null ? g[cle].max : ""}">`).join("")}</div>
    </div>`).join("");

  hote.querySelectorAll("[data-suppr]").forEach(b => b.addEventListener("click", () => {
    groupes.splice(+b.dataset.suppr, 1);
    dessinerGroupes();
    relancer();
  }));
  hote.querySelectorAll(".jetons button").forEach(b => b.addEventListener("click", () => {
    const g = groupes[+b.parentElement.dataset.groupe], j = +b.dataset.match;
    const dedans = g.matchs.indexOf(j);
    dedans >= 0 ? g.matchs.splice(dedans, 1) : g.matchs.push(j);
    g.matchs.sort((a, b) => a - b);
    dessinerGroupes();
    relancer();
  }));
  // Les bornes s'écrivent dans le modèle sans redessiner : redessiner à
  // chaque frappe ferait perdre le curseur au bout du premier chiffre.
  hote.querySelectorAll(".bornes input").forEach(inp => inp.addEventListener("input", () => {
    const g = groupes[+inp.dataset.groupe], cle = inp.dataset.cle;
    g[cle] = g[cle] || {};
    if (inp.value === "") delete g[cle][inp.dataset.borne];
    else g[cle][inp.dataset.borne] = Number(inp.value);
    if (!Object.keys(g[cle]).length) delete g[cle];
    relancer();
  }));
}

/* --- filtres et réduction, sous-traités au travailleur -------------------- */

function reglesLues() {
  const r = {};
  for (const {cle} of TOUS_REGLAGES) {
    const min = $(`min-${cle}`).value, max = $(`max-${cle}`).value;
    if (min === "" && max === "") continue;
    r[cle] = {};
    if (min !== "") r[cle].min = +min;
    if (max !== "") r[cle].max = +max;
  }
  // Un groupe sans match sélectionné ou sans borne ne filtre rien : l'envoyer
  // au travailleur ne coûterait qu'un tour de boucle par grille.
  const actifs = groupes.filter(g => g.matchs.length &&
    (g.un || g.nul || g.deux));
  if (actifs.length) r.groupes = actifs;
  return r;
}

function relancer() {
  if (!travailleur) {
    travailleur = new Worker("js/atelier-worker.js", {type: "module"});
    travailleur.onmessage = e => { if (e.data.jeton === jeton) afficher(e.data); };
    travailleur.onerror = () => {
      $("etat").textContent = "le calcul n'a pas pu démarrer dans cet onglet";
    };
  }
  const g = $("garantie").value;
  $("etat").textContent = "calcul…";
  travailleur.postMessage({
    jeton: ++jeton,
    choix,
    regles: reglesLues(),
    garantie: g === "" ? null : matchs.length - +g,
    couverture: +$("couverture").value,
  });
}

function afficher(r) {
  dernier = r;
  $("etat").textContent = "";
  if (r.vides) {
    $("compte").textContent = "grille incomplète";
    $("synthese-jeu").innerHTML = "";
    $("sortie").value = "";
    return;
  }
  if (r.trop) {
    $("compte").textContent =
      `${nb(r.total)} combinaisons — au-delà de ${nb(r.trop)}, il faut resserrer la grille avant de filtrer`;
    $("synthese-jeu").innerHTML = "";
    $("sortie").value = "";
    return;
  }
  const part = r.total ? r.retenues / r.total : 0;
  const s1 = r.retenues > 1 ? "s" : "";
  $("compte").textContent =
    `${nb(r.retenues)} grille${s1} retenue${s1} sur ${nb(r.total)} ` +
    `(${(part * 100).toFixed(1)} %)`;

  if (r.tropPourReduire) {
    $("synthese-jeu").innerHTML = tuiles([
      ["Jeu réduit", "—"],
      ["Trop de grilles", `> ${nb(r.tropPourReduire)}`, "trop"],
    ]);
    $("avert-jeu").textContent =
      `La réduction compare chaque grille à toutes les autres : au-delà de ` +
      `${nb(r.tropPourReduire)} grilles elle prendrait une demi-minute. ` +
      `Resserrez les filtres, ou fermez un triple.`;
    $("sortie").value = r.apercu.join("\n");
    return;
  }
  $("avert-jeu").textContent = "";
  if (!r.reduction) {
    $("synthese-jeu").innerHTML = tuiles([
      ["Grilles à jouer", nb(r.retenues), "accent"],
      ["Coût à 1 €", r.retenues ? eur(r.retenues, 0) : "—"],
      ["Réduction", "aucune"],
    ]);
    $("sortie").value = r.apercu.join("\n") +
      (r.retenues > r.apercu.length
        ? `\n… ${nb(r.retenues - r.apercu.length)} autres — choisissez une garantie pour réduire`
        : "");
    return;
  }
  const red = r.reduction;
  $("synthese-jeu").innerHTML = tuiles([
    ["Grilles à jouer", nb(red.n), "accent"],
    ["Coût à 1 €", eur(red.n, 0)],
    ["Économie", red.n < r.retenues
       ? `${eur(r.retenues - red.n, 0)} (−${
           (100 - 100 * red.n / r.retenues).toFixed(0)} %)` : "—", "bien"],
    ["Couverture", `${(red.taux * 100).toFixed(1)} %`],
  ]);
  $("sortie").value = red.texte;
}

/* --- sortie --------------------------------------------------------------- */

function copier() {
  const t = $("sortie");
  t.select();
  navigator.clipboard.writeText(t.value).then(
    () => flash("copier", "Copié"),
    () => flash("copier", "Copie refusée"));
}

function flash(id, texte) {
  const b = $(id), avant = b.textContent;
  b.textContent = texte;
  setTimeout(() => { b.textContent = avant; }, 1400);
}

function telecharger() {
  const nom = ($("titre").textContent || "grilles").replace(/[^\w-]+/g, "-");
  const blob = new Blob([$("sortie").value + "\n"], {type: "text/plain"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${nom}.txt`;
  a.click();
  URL.revokeObjectURL(a.href);
}

demarrer().catch(e => { $("origine").textContent = "erreur de chargement : " + e.message; });
