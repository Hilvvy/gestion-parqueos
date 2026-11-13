const navigationToggle = document.querySelector("#navigation-toggle");
const sidebar = document.querySelector("#app-sidebar");
const backdrop = document.querySelector("#navigation-backdrop");
if (navigationToggle && sidebar) {
  const mobile = matchMedia("(max-width: 900px)");
  const main = document.querySelector("main");
  function setNavigation(open, focus = true) {
    document.body.classList.toggle("navigation-open", open);
    navigationToggle.setAttribute("aria-expanded", String(open));
    sidebar.inert = mobile.matches && !open;
    main.inert = mobile.matches && open;
    if (focus) (open ? sidebar.querySelector("a") : navigationToggle).focus();
  }
  navigationToggle.addEventListener("click", () => setNavigation(navigationToggle.getAttribute("aria-expanded") !== "true"));
  backdrop.addEventListener("click", () => setNavigation(false));
  document.addEventListener("keydown", event => { if (event.key === "Escape" && navigationToggle.getAttribute("aria-expanded") === "true") setNavigation(false); });
  mobile.addEventListener("change", () => setNavigation(false, false));
  setNavigation(false, false);
}
