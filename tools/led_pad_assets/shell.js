/**
 * AWR-271 R9a — one lighting shell: Pad|Lab view switch without a full page reload.
 * AWR-273 R9c — /lab is a 302 to /?view=lab; in-shell nav uses ?view= (never /lab as a page).
 */
(function () {
  const TITLE = {pad: "LED Pad", lab: "Template Lab"};
  const PATH = {pad: "/", lab: "/?view=lab"};

  function $(id) {
    return document.getElementById(id);
  }

  function pathView() {
    const params = new URLSearchParams(location.search || "");
    if ((params.get("view") || "").toLowerCase() === "lab") return "lab";
    const path = (location.pathname || "/").replace(/\/+$/, "") || "/";
    // Legacy path only matters if a stale client somehow lands here before redirect.
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

    const diag = $("diagnostics");
    if (diag) {
      diag.hidden = !isLab;
      // Cold Lab screen: telemetry stays collapsed until opened.
      if (!isLab) diag.open = false;
    }
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

    const targetUrl = PATH[next];
    if (options.push !== false && pathView() !== next) {
      history.pushState({shellView: next}, TITLE[next], targetUrl);
    } else if (options.replace) {
      history.replaceState({shellView: next}, TITLE[next], targetUrl);
    }

    window.LightingShell.view = next;
    window.dispatchEvent(new CustomEvent("lighting-shell-view", {detail: {view: next}}));
  }

  // AWR-279 #7: ONE shell-level Escape owner. Previously pad-ui.js and lab.js each
  // ran their own document keydown handler, both calling PadModal.close() — so the
  // Escape that OPENED a dirty-editor "Discard?" confirm was instantly closed again
  // by the sibling handler (net nothing). Now the shell owns Escape: a modal (the
  // topmost surface) closes first; otherwise the ACTIVE view's registered handler
  // runs. Each view registers what to do when no modal is open.
  const escapeHandlers = {pad: null, lab: null};
  function registerEscape(view, fn) {
    if (view === "pad" || view === "lab") escapeHandlers[view] = typeof fn === "function" ? fn : null;
  }
  function onEscape(ev) {
    if (ev.key !== "Escape") return;
    if (window.PadModal && window.PadModal.isOpen()) { window.PadModal.close(); return; }
    const fn = escapeHandlers[window.LightingShell.view];
    if (fn) fn(ev);
  }

  function isPhone() {
    return window.matchMedia("(max-width: 700px)").matches;
  }

  function onNavClick(ev) {
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || ev.button !== 0) return;
    // AWR-280: the Sim is localhost-bound (:8767). On the phone the device can't
    // reach its own localhost, so a tap on Sim is a dead hop — show a one-line
    // note instead of navigating. Remove this when the sim goes LAN.
    const simLink = ev.target.closest("a[data-sim-tab]");
    if (simLink && isPhone()) {
      ev.preventDefault();
      showPhoneNote("Sim runs on the Mac for now");
      return;
    }
    const link = ev.target.closest("a[data-shell-view]");
    if (!link) return;
    const view = link.getAttribute("data-shell-view");
    if (view !== "pad" && view !== "lab") return;
    ev.preventDefault();
    if (window.LightingShell.view === view) return;
    setView(view, {push: true});
  }

  // AWR-280: one-line note on the shared #toast surface. Uses its own timer so it
  // never fights pad-ui.js's toast state.
  let phoneNoteTimer = null;
  function showPhoneNote(text) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = text;
    el.hidden = false;
    clearTimeout(phoneNoteTimer);
    phoneNoteTimer = setTimeout(() => { el.hidden = true; }, 3200);
  }

  // AWR-280: the session controls fold into a tap-to-open row on the phone. The
  // markup ships `open` so desktop is correct even if this never runs (there the
  // summary is display:none and the fold renders inline). Here we collapse it on
  // the phone and re-open it if the viewport crosses back to desktop width.
  function trackSessionFold() {
    const fold = document.getElementById("sessionFold");
    if (!fold) return;
    const phone = window.matchMedia("(max-width: 700px)");
    const apply = () => { fold.open = !phone.matches; };
    apply();
    if (phone.addEventListener) phone.addEventListener("change", apply);
    else if (phone.addListener) phone.addListener(apply);
  }

  // AWR-280: on the phone, banners show as one truncated line; a tap expands the
  // full message. Presentation only — banner text/visibility stays owned by
  // pad-ui.js / PadConfigStale.
  function wireBannerExpand() {
    document.addEventListener("click", (ev) => {
      if (!isPhone()) return;
      const banner = ev.target.closest(".error-banner, .config-stale-banner");
      if (!banner) return;
      banner.classList.toggle("banner-open");
    });
  }

  function init() {
    if (!document.body || document.body.dataset.shell !== "lighting") return;
    const initial = pathView();
    setView(initial, {push: false, replace: true});
    const nav = document.querySelector(".route-tabs");
    if (nav) nav.addEventListener("click", onNavClick);
    document.addEventListener("keydown", onEscape);
    trackTopbarHeight();
    trackSessionFold();
    wireBannerExpand();
    window.addEventListener("popstate", () => {
      setView(pathView(), {push: false});
    });
  }

  // AWR-279 #1: expose the live topbar height so the fixed look-editor drawer can
  // start BELOW it (never covering the STOP button). Measured, because the topbar
  // is one row in Lab and two in Pad and wraps on narrow screens.
  function trackTopbarHeight() {
    const topbar = document.querySelector(".topbar");
    if (!topbar) return;
    const apply = () => {
      const h = Math.round(topbar.getBoundingClientRect().height);
      if (h > 0) document.documentElement.style.setProperty("--topbar-h", `${h}px`);
    };
    apply();
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(apply).observe(topbar);
    }
    window.addEventListener("resize", apply);
  }

  window.LightingShell = {
    view: "pad",
    setView,
    pathView,
    registerEscape,
    init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}());
