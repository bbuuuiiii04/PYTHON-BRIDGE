/**
 * AWR-271 R9a — one lighting shell: Pad|Lab view switch without a full page reload.
 * Same header instance, same session/ownership controls, shared lab editor component.
 * /lab still serves this document (not a redirect — that is R9c).
 */
(function () {
  const TITLE = {pad: "LED Pad", lab: "Template Lab"};
  const PATH = {pad: "/", lab: "/lab"};

  function $(id) {
    return document.getElementById(id);
  }

  function pathView() {
    const path = (location.pathname || "/").replace(/\/+$/, "") || "/";
    return path === "/lab" ? "lab" : "pad";
  }

  function setView(view, opts) {
    const next = view === "lab" ? "lab" : "pad";
    const options = opts || {};
    const padPanel = $("view-pad");
    const labPanel = $("view-lab");
    if (!padPanel || !labPanel) return;

    const isLab = next === "lab";
    padPanel.hidden = isLab;
    labPanel.hidden = !isLab;

    document.body.classList.toggle("lab-route", isLab);
    document.body.dataset.shellView = next;

    const transport = $("shellTransport");
    if (transport) transport.classList.toggle("lab-transport", isLab);

    const bankRow = $("padBankRow");
    if (bankRow) bankRow.hidden = isLab;

    const health = $("healthStrip");
    if (health) health.hidden = !isLab;
    const selfTest = $("selfTestPanel");
    if (selfTest && !isLab) selfTest.hidden = true;
    const helpBtn = $("labHelpBtn");
    if (helpBtn) helpBtn.hidden = !isLab;
    const helpPop = $("labHelpPopover");
    if (helpPop && !isLab) {
      helpPop.hidden = true;
      if (helpBtn) helpBtn.setAttribute("aria-expanded", "false");
    }
    const bpmScope = $("bpmScope");
    if (bpmScope) bpmScope.hidden = !isLab;
    const qrBtn = $("qrBtn");
    if (qrBtn) qrBtn.hidden = isLab;

    const title = $("shellTitle");
    if (title) {
      title.textContent = TITLE[next];
      if (isLab) {
        const badge = document.createElement("span");
        badge.className = "lab-badge";
        badge.textContent = "LAB";
        title.appendChild(document.createTextNode(" "));
        title.appendChild(badge);
      }
    }
    document.title = TITLE[next];

    document.querySelectorAll("[data-shell-view]").forEach((link) => {
      const active = link.getAttribute("data-shell-view") === next;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });

    if (options.push !== false && location.pathname !== PATH[next]) {
      history.pushState({shellView: next}, TITLE[next], PATH[next]);
    } else if (options.replace) {
      history.replaceState({shellView: next}, TITLE[next], PATH[next]);
    }

    window.LightingShell.view = next;
    window.dispatchEvent(new CustomEvent("lighting-shell-view", {detail: {view: next}}));
  }

  function onNavClick(ev) {
    const link = ev.target.closest("a[data-shell-view]");
    if (!link || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;
    const view = link.getAttribute("data-shell-view");
    if (view !== "pad" && view !== "lab") return;
    ev.preventDefault();
    if (window.LightingShell.view === view) return;
    setView(view, {push: true});
  }

  function init() {
    if (!document.body || document.body.dataset.shell !== "lighting") return;
    const initial = pathView();
    setView(initial, {push: false, replace: true});
    const nav = document.querySelector(".route-tabs");
    if (nav) nav.addEventListener("click", onNavClick);
    window.addEventListener("popstate", () => {
      setView(pathView(), {push: false});
    });
  }

  window.LightingShell = {
    view: "pad",
    setView,
    pathView,
    init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}());
