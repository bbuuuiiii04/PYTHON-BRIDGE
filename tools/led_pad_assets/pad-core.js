(function () {
  async function request(path, options = {}) {
    const init = {headers: {"Content-Type": "application/json"}, ...options};
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    const res = await fetch(path, init);
    const json = await res.json();
    if (!json.ok && json.error) {
      const err = new Error(json.error);
      err.payload = json;
      throw err;
    }
    return json;
  }
  // Shared modal used by both the pad page and Template Lab, so neither page
  // needs to fall back to blocking browser prompt()/confirm() dialogs (which
  // iOS Safari renders inconsistently and which block the JS event loop).
  // Lazily builds its own backdrop DOM on first use, reusing the pad page's
  // original static markup IDs (#modal, #modalTitle, #modalText,
  // #modalActions) so pad-ui.js's existing direct $("modal...") lookups
  // (the "Open on another device" QR panel, and the move-look button
  // disabling) keep working unchanged.
  window.PadModal = (function () {
    const state = {open: false, dom: null, lastFocus: null, errorHandler: null};
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

    function ensureDom() {
      if (state.dom) return state.dom;
      const backdrop = document.createElement("div");
      backdrop.id = "modal";
      backdrop.className = "modal-backdrop";
      backdrop.hidden = true;
      backdrop.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
          <h2 id="modalTitle"></h2>
          <div id="modalText"></div>
          <form id="modalForm" class="modal-fields" hidden></form>
          <div id="modalActions" class="modal-actions"></div>
        </div>`;
      document.body.appendChild(backdrop);
      state.dom = {
        backdrop,
        title: backdrop.querySelector("#modalTitle"),
        text: backdrop.querySelector("#modalText"),
        form: backdrop.querySelector("#modalForm"),
        actions: backdrop.querySelector("#modalActions"),
      };
      return state.dom;
    }

    function setErrorHandler(fn) { state.errorHandler = typeof fn === "function" ? fn : null; }
    function reportError(err) { if (state.errorHandler) state.errorHandler(err); else console.error(err); }
    function isOpen() { return state.open; }

    function close() {
      if (!state.dom) return;
      state.dom.backdrop.hidden = true;
      state.dom.form.hidden = true;
      state.dom.form.innerHTML = "";
      state.open = false;
      const focusTarget = state.lastFocus;
      state.lastFocus = null;
      if (focusTarget && typeof focusTarget.focus === "function") focusTarget.focus();
    }

    // Generic N-action modal (used for confirm dialogs and the move-bank
    // picker). `actions` is [{label, className, disabled, run}]; clicking a
    // button closes the modal, then awaits run() and reports any failure.
    function show(title, text, actions) {
      const dom = ensureDom();
      state.lastFocus = document.activeElement;
      dom.title.textContent = title;
      dom.text.textContent = text;
      dom.form.hidden = true;
      dom.form.innerHTML = "";
      dom.actions.innerHTML = actions.map((a, i) => `<button type="button" class="${esc(a.className || "ghost")}" data-modal-action="${i}" ${a.disabled ? "disabled" : ""}>${esc(a.label)}</button>`).join("");
      dom.backdrop.hidden = false;
      state.open = true;
      const buttons = dom.actions.querySelectorAll("button");
      buttons.forEach((btn, i) => {
        btn.onclick = async () => {
          close();
          try { await actions[i].run(); } catch (err) { reportError(err); }
        };
      });
      if (buttons[0]) buttons[0].focus();
      return dom;
    }

    function confirm(title, text, actionText, onConfirm) {
      show(title, text, [
        {label: "Cancel", className: "ghost", run: () => {}},
        {label: actionText, className: "danger-outline", run: onConfirm},
      ]);
    }

    // Single-text-input variant. Enter (native form submit) confirms; the
    // page's own Escape handler is expected to call close() (see
    // pad-ui.js/lab.js), which cancels without invoking onConfirm.
    function prompt(title, message, options, onConfirm) {
      const opts = options || {};
      const dom = ensureDom();
      state.lastFocus = document.activeElement;
      dom.title.textContent = title;
      dom.text.textContent = message || "";
      dom.form.hidden = false;
      dom.form.innerHTML = `<label>${esc(opts.label || "")}<input id="modalPromptInput" type="text" value="${esc(opts.value ?? "")}"></label>`;
      dom.actions.innerHTML = `
        <button type="button" class="ghost" data-modal-cancel>${esc(opts.cancelText || "Cancel")}</button>
        <button type="submit" form="modalForm" class="primary" data-modal-confirm>${esc(opts.confirmText || "Save")}</button>`;
      dom.backdrop.hidden = false;
      state.open = true;
      const input = dom.form.querySelector("#modalPromptInput");
      const submit = async () => {
        const value = input.value;
        close();
        try { await onConfirm(value); } catch (err) { reportError(err); }
      };
      dom.form.onsubmit = (ev) => { ev.preventDefault(); submit(); };
      dom.actions.querySelector("[data-modal-cancel]").onclick = () => close();
      input.focus();
      input.select();
    }

    return {show, confirm, prompt, close, isOpen, setErrorHandler};
  }());

  // Shared reconnect helper for both pages' runtime polls: after >=2
  // consecutive poll failures show a persistent "reconnecting" banner and back
  // off (2s -> 5s cap); on the first success after downtime run the page's
  // full refresh() and clear the banner, so pages heal instead of corpsing
  // when the pad server restarts.
  window.PadHealth = (function () {
    const state = {fails: 0, down: false, timer: 0, delay: 2000, poll: null, refresh: null, banner: null};
    function schedule() { clearTimeout(state.timer); state.timer = setTimeout(tick, state.delay); }
    async function tick() {
      let ok = true;
      try { await state.poll(); } catch (_) { ok = false; }
      if (ok && state.down) {
        try { await state.refresh(); } catch (_) { ok = false; }
      }
      if (ok) {
        if (state.down) { state.down = false; state.banner(false); }
        state.fails = 0;
        state.delay = 2000;
      } else {
        state.fails += 1;
        if (state.fails >= 2 && !state.down) { state.down = true; state.banner(true); }
        if (state.down) state.delay = Math.min(5000, state.delay + 1500);
      }
      schedule();
    }
    function start(hooks) {
      state.poll = hooks.poll;
      state.refresh = hooks.refresh;
      state.banner = hooks.banner;
      state.delay = 2000;
      schedule();
    }
    return {start};
  }());

  // AWR-255: shared config-stale banner for pad + lab. Non-dismissable while
  // stale; quiet green when we positively know the running bridge loaded the
  // current live file; hidden when we cannot tell.
  window.PadConfigStale = (function () {
    function formatLag(seconds) {
      const s = Math.max(0, Number(seconds) || 0);
      if (s < 60) return "less than a minute";
      if (s < 3600) {
        const m = Math.round(s / 60);
        return m === 1 ? "1 minute" : `${m} minutes`;
      }
      if (s < 86400) {
        const h = Math.round(s / 3600);
        return h === 1 ? "1 hour" : `${h} hours`;
      }
      const d = Math.round(s / 86400);
      return d === 1 ? "1 day" : `${d} days`;
    }

    function render(el, payload) {
      if (!el) return;
      const info = payload && typeof payload === "object" ? payload : {};
      if (info.stale) {
        el.hidden = false;
        el.dataset.state = "stale";
        if (info.signal === "bridge_start" && typeof info.lag_s === "number") {
          el.textContent =
            `Your applied changes aren't live yet — the bridge started ${formatLag(info.lag_s)} before the last config change. Restart the bridge (menubar) to load them.`;
        } else {
          el.textContent =
            "Your applied changes aren't live yet — restart the bridge (menubar) to load them. (Can't tell when the bridge last started.)";
        }
        return;
      }
      if (info.signal === "bridge_start") {
        el.hidden = false;
        el.dataset.state = "fresh";
        el.textContent = "Live config matches the running bridge.";
        return;
      }
      el.hidden = true;
      el.dataset.state = "";
      el.textContent = "";
    }

    return {formatLag, render};
  }());

  window.LedPadApi = {
    config: () => request("/api/config"),
    renders: () => request("/api/renders"),
    palettes: () => request("/api/palettes"),
    runtime: () => request("/api/runtime_status"),
    play: (body) => request("/api/play", {method: "POST", body}),
    update: (body) => request("/api/update", {method: "POST", body}),
    stop: () => request("/api/stop", {method: "POST", body: {}}),
    emergencyStop: () => request("/api/emergency_stop", {method: "POST", body: {}}),
    takeover: () => request("/api/takeover", {method: "POST", body: {}}),
    release: () => request("/api/release", {method: "POST", body: {}}),
    session: (body) => request("/api/session", {method: "POST", body}),
    saveLook: (body) => request("/api/look/save", {method: "POST", body}),
    duplicate: (body) => request("/api/look/duplicate", {method: "POST", body}),
    move: (body) => request("/api/look/move", {method: "POST", body}),
    deleteLook: (body) => request("/api/look/delete", {method: "POST", body}),
    commit: () => request("/api/commit", {method: "POST", body: {}}),
    discard: () => request("/api/discard", {method: "POST", body: {}}),
    labList: () => request("/api/lab/list"),
    labSave: (body) => request("/api/lab/save", {method: "POST", body}),
    labPlay: (body) => request("/api/lab/play", {method: "POST", body}),
    labUpdate: (body) => request("/api/lab/update", {method: "POST", body}),
    labSwitch: (body) => request("/api/lab/switch", {method: "POST", body}),
    labPreview: (body) => request("/api/lab/preview", {method: "POST", body}),
    labReload: () => request("/api/lab/reload", {method: "POST", body: {}}),
    labAccept: (body) => request("/api/lab/accept", {method: "POST", body: typeof body === "string" ? {name: body} : body}),
    labReject: (body) => request("/api/lab/reject", {method: "POST", body: typeof body === "string" ? {name: body} : body}),
    labArchive: (body) => request("/api/lab/archive", {method: "POST", body}),
    labDelete: (body) => request("/api/lab/delete", {method: "POST", body}),
    access: () => request("/api/access")
  };
}());
