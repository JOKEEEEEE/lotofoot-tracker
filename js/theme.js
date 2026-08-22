/* Le thème, partagé par les deux pages.
 *
 * L'ATTRIBUT SE POSE AVANT LE PREMIER RENDU. Ce script est chargé dans le
 * <head> sans `defer` : si l'on attendait le chargement du document, une page
 * réglée sur sombre s'afficherait clair une fraction de seconde. Les boutons,
 * eux, n'existent pas encore à cet instant — d'où l'attente séparée.
 *
 * localStorage peut lever — fenêtre privée, cookies bloqués — et la page doit
 * alors se contenter du système, pas cesser de fonctionner.
 */
(function () {
  function lire() {
    try { return localStorage.getItem("theme") || ""; } catch (e) { return ""; }
  }
  function appliquer(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    document.querySelectorAll(".theme button").forEach(b =>
      b.setAttribute("aria-pressed", String(b.dataset.theme === t)));
    try { t ? localStorage.setItem("theme", t) : localStorage.removeItem("theme"); }
    catch (e) { /* sans stockage, le choix vaut pour la session */ }
  }
  appliquer(lire());
  document.addEventListener("DOMContentLoaded", () => {
    appliquer(lire());
    document.querySelectorAll(".theme button").forEach(b =>
      b.addEventListener("click", () => appliquer(b.dataset.theme)));
  });
})();
