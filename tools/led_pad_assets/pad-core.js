(function () {
  async function request(path, options = {}) {
    const init = {headers: {"Content-Type": "application/json"}, ...options};
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    const res = await fetch(path, init);
    const json = await res.json();
    if (!json.ok && json.error) {
      const err = new Error(json.message || json.error);
      err.payload = json;
      err.status = res.status;
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
      fields(title, message, [
        {name: "value", label: opts.label || "", type: "text", value: opts.value ?? ""},
      ], opts, (values) => onConfirm(values.value));
    }

    // Multi-field form (AWR-263 New-draft dialog). fieldSpecs:
    // [{name, label, type:'text'|'select'|'checkbox', options?, value?, help?}]
    // onConfirm receives {name: value, ...}.
    function fields(title, message, fieldSpecs, options, onConfirm) {
      const opts = options || {};
      const specs = Array.isArray(fieldSpecs) ? fieldSpecs : [];
      const dom = ensureDom();
      state.lastFocus = document.activeElement;
      dom.title.textContent = title;
      dom.text.textContent = message || "";
      dom.form.hidden = false;
      dom.form.innerHTML = specs.map((f, i) => {
        const id = `modalField_${i}`;
        const label = esc(f.label || f.name || "");
        const help = f.help ? `<div class="dim" style="font-size:11px;margin-top:4px">${esc(f.help)}</div>` : "";
        if (f.type === "select") {
          const optionsHtml = (f.options || []).map(o => {
            const selected = String(o.value) === String(f.value ?? "") ? " selected" : "";
            return `<option value="${esc(o.value)}"${selected}>${esc(o.label)}</option>`;
          }).join("");
          return `<label>${label}<select id="${id}" name="${esc(f.name)}" data-field-type="select">${optionsHtml}</select>${help}</label>`;
        }
        if (f.type === "checkbox") {
          return `<label class="modal-check"><span>${label}</span><input id="${id}" name="${esc(f.name)}" type="checkbox" data-field-type="checkbox" ${f.value ? "checked" : ""}>${help}</label>`;
        }
        return `<label>${label}<input id="${id}" name="${esc(f.name)}" type="text" data-field-type="text" value="${esc(f.value ?? "")}">${help}</label>`;
      }).join("");
      dom.actions.innerHTML = `
        <button type="button" class="ghost" data-modal-cancel>${esc(opts.cancelText || "Cancel")}</button>
        <button type="submit" form="modalForm" class="primary" data-modal-confirm>${esc(opts.confirmText || "Save")}</button>`;
      dom.backdrop.hidden = false;
      state.open = true;
      const readValues = () => {
        const out = {};
        specs.forEach((f, i) => {
          const el = dom.form.querySelector(`#modalField_${i}`);
          if (!el) return;
          if (f.type === "checkbox") out[f.name] = el.checked;
          else out[f.name] = el.value;
        });
        return out;
      };
      const submit = async () => {
        const values = readValues();
        close();
        try { await onConfirm(values); } catch (err) { reportError(err); }
      };
      dom.form.onsubmit = (ev) => { ev.preventDefault(); submit(); };
      dom.actions.querySelector("[data-modal-cancel]").onclick = () => close();
      const first = dom.form.querySelector("input, select");
      if (first) {
        first.focus();
        if (first.select) first.select();
      }
    }

    return {show, confirm, prompt, fields, close, isOpen, setErrorHandler};
  }());

  // Shared reconnect helper for both pages' runtime polls: after >=2
  // consecutive poll failures show a persistent "reconnecting" banner and back
  // off (2s -> 5s cap); on the first success after downtime run the page's
  // full refresh() and clear the banner, so pages heal instead of corpsing
  // when the pad server restarts.
  window.PadHealth = (function () {
    // AWR-271: pad + lab share one shell — multiple subscribers, one reconnect loop.
    const state = {fails: 0, down: false, timer: 0, delay: 2000, subs: []};
    function schedule() { clearTimeout(state.timer); state.timer = setTimeout(tick, state.delay); }
    async function tick() {
      if (!state.subs.length) {
        schedule();
        return;
      }
      let ok = true;
      for (const sub of state.subs) {
        try { await sub.poll(); } catch (_) { ok = false; }
      }
      if (ok && state.down) {
        for (const sub of state.subs) {
          try { await sub.refresh(); } catch (_) { ok = false; }
        }
      }
      if (ok) {
        if (state.down) {
          state.down = false;
          for (const sub of state.subs) {
            if (sub.banner) sub.banner(false);
          }
        }
        state.fails = 0;
        state.delay = 2000;
      } else {
        state.fails += 1;
        if (state.fails >= 2 && !state.down) {
          state.down = true;
          for (const sub of state.subs) {
            if (sub.banner) sub.banner(true);
          }
        }
        if (state.down) state.delay = Math.min(5000, state.delay + 1500);
      }
      schedule();
    }
    function start(hooks) {
      state.subs.push({
        poll: hooks.poll,
        refresh: hooks.refresh,
        banner: hooks.banner,
      });
      if (state.subs.length === 1) {
        state.delay = 2000;
        schedule();
      }
    }
    return {start};
  }());

  // AWR-255/261: shared config-stale banner for pad + lab.
  // not_running (calm): status missing/stale — bridge isn't writing.
  // stale: fresh status + config newer than process start (or can't-tell).
  // fresh/green: fresh status + config older than process start.
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
      if (info.signal === "not_running") {
        el.hidden = false;
        el.dataset.state = "not_running";
        el.textContent =
          "The bridge isn't running — your applied changes will load when it next starts.";
        return;
      }
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

  // AWR-275: shared tempo-mode chip for pad + lab. When the bridge heartbeat is
  // fresh, pad/lab playback follows the live music's bpm — the manual Preview
  // tempo is read-only while that lasts. render() shows the chip and disables the
  // tempo controls when following; each page re-enables per its own rule when not.
  // Returns true when following, false otherwise.
  window.PadTempoMode = (function () {
    function render(playback) {
      const chip = document.getElementById("tempoModeChip");
      const input = document.getElementById("bpmInput");
      const steps = document.querySelectorAll("[data-step]");
      const following = !!(playback && playback.following);
      if (following) {
        const raw = playback.follow_bpm != null ? playback.follow_bpm : playback.bpm;
        const bpm = Math.round(Number(raw) || 0);
        const shown = bpm > 0 ? bpm : "—";
        if (chip) {
          chip.hidden = false;
          chip.textContent = `Following your music · ${shown} · tempo set by the live mix`;
        }
        if (input) input.disabled = true;
        steps.forEach(btn => { btn.disabled = true; });
      } else if (chip) {
        chip.hidden = true;
        chip.textContent = "";
      }
      return following;
    }
    return {render};
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
    rename: (body) => request("/api/look/rename", {method: "POST", body}),
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
