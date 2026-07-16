(function () {
  const bankOrder = ["drafts", "ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility"];
  const moveBanks = ["ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility"];
  const bankLabels = {drafts:"Drafts", ambient:"Ambient", groove:"Groove", buildup:"Buildup", pre_drop:"Pre-Drop", drop:"Drop", post_drop:"Post-Drop", breakdown:"Breakdown", utility:"Utility", other:"Other"};
  const bankColors = {drafts:"var(--lab)", ambient:"var(--role-ambient)", groove:"var(--role-groove)", buildup:"var(--role-buildup)", drop:"var(--role-drop)", post_drop:"var(--role-postdrop)", breakdown:"var(--role-breakdown)", utility:"var(--role-utility)", other:"var(--border)"};
  const state = {config:null, banks:{}, renders:[], renderMap:new Map(), palettes:[], activeBank:"drafts", editor:null, cleanSnapshot:null, updateTimer:null, lastFocus:null, playingLook:""};
  const $ = (id) => document.getElementById(id);
  const api = window.LedPadApi;
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const RECONNECT_TEXT = "Pad server unreachable — reconnecting…";

  function showError(err) {
    $("errorBanner").hidden = false;
    $("errorBanner").textContent = err && err.message ? err.message : String(err);
  }
  PadModal.setErrorHandler(showError);
  function clearError() { $("errorBanner").hidden = true; $("errorBanner").textContent = ""; $("errorBanner").classList.remove("warn-banner"); }
  function toast(text) {
    $("toast").textContent = text;
    $("toast").hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4000);
  }
  function human(name) { return String(name).replace(/^rt_/, "").replaceAll("_", " ").replace("post drop", "post-drop").replace(/\b\w/g, c => c.toUpperCase()); }
  function timingBadge(render) {
    const label = ({beat:"♫ beat sync", mixed:"♫ beat + time", time:"◷ time driven", static:"static"})[(render || {}).timing_mode];
    return label ? `<span class="badge">${label}</span>` : "";
  }
  function lookBank(name) {
    for (const [bank, names] of Object.entries(state.banks || {})) if ((names || []).includes(name)) return bank;
    return "other";
  }
  function lookDirty(name) { return (state.config.dirty.looks || []).includes(name); }
  function currentSession() { return (((state.config || {}).config || {})._pad_meta || {}).ui || {}; }
  function editorPayload() {
    const e = state.editor;
    return {look: e.look, params: e.params, cue_beats: e.cue_beats, slot_fill: e.slot_fill, mono_chance: e.mono_chance, locked_palette: e.locked_palette || ""};
  }
  function snapshotEditor() { return JSON.stringify(editorPayload()); }
  function setDirty() {
    const dirty = state.editor && snapshotEditor() !== state.cleanSnapshot;
    $("saveLookBtn").disabled = !dirty;
    $("dirtyText").textContent = dirty ? "Unsaved changes" : "Draft saved";
    $("dirtyText").className = dirty ? "warn-text" : "dim";
  }
  async function refresh() {
    clearError();
    const [cfg, renders, palettes] = await Promise.all([api.config(), api.renders(), api.palettes()]);
    state.config = cfg;
    state.banks = cfg.banks || {};
    state.renders = renders.renders || [];
    state.renderMap = new Map(state.renders.map(r => [r.name, r]));
    state.palettes = palettes.palettes || [];
    $("liveChangedBanner").hidden = !cfg.live_changed;
    renderSession();
    renderBanks();
    renderCards();
    await updateRuntime();
  }
  function renderSession() {
    const ui = currentSession();
    $("bpmInput").value = ui.bpm || 128;
    $("paletteSelect").innerHTML = state.palettes.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
    $("paletteSelect").value = ui.test_palette || state.palettes[0] || "";
    $("loopToggle").checked = ui.loop !== false;
    $("loopLabel").textContent = $("loopToggle").checked ? "On" : "Off";
    $("commitCount").textContent = (state.config.dirty.looks || []).length;
  }
  function renderBanks() {
    const tabs = $("bankTabs");
    const banks = bankOrder.slice();
    if ((state.banks.other || []).length) banks.push("other");
    tabs.innerHTML = banks.map(bank => {
      const dirty = state.config.dirty.banks && state.config.dirty.banks[bank];
      const count = (state.banks[bank] || []).length;
      return `<button type="button" class="${esc(bank)} ${bank === state.activeBank ? "active" : ""}" style="--bank-color:${bankColors[bank]}" data-bank="${esc(bank)}">${esc(bankLabels[bank])} ${count} ${dirty ? "<span class='dirty-dot'>●</span>" : ""}</button>`;
    }).join("");
    tabs.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => { state.activeBank = btn.dataset.bank; renderBanks(); renderCards(); }));
  }
  function renderCards() {
    const names = state.banks[state.activeBank] || [];
    const grid = $("lookGrid");
    if (!names.length) {
      grid.innerHTML = state.activeBank === "drafts"
        ? `<div class="empty"><span class="panel-label">No drafts</span><span>New looks land here. Automation never plays drafts.</span></div>`
        : `<div class="empty"><span class="panel-label">Empty bank</span><span>Move or duplicate looks into this bank.</span></div>`;
      return;
    }
    grid.innerHTML = names.map(name => cardHtml(name)).join("");
    grid.querySelectorAll(".look-card").forEach((card, i) => { card.style.animationDelay = `${Math.min(i * 20, 300)}ms`; });
    grid.querySelectorAll("[data-action]").forEach(btn => btn.addEventListener("click", onCardAction));
  }
  function cardHtml(name) {
    const look = state.config.config.looks[name] || {};
    const render = state.renderMap.get(look.scene_ref);
    const bank = lookBank(name);
    const realtime = Boolean(render);
    const dirty = lookDirty(name);
    const cue = (((state.config.config._pad_meta || {}).looks || {})[name] || {}).cue_beats || 16;
    const playing = state.playingLook === name;
    const label = render ? render.label : human(look.scene_ref || look.action);
    return `<article class="look-card ${esc(bank)} ${playing ? "playing" : ""}" style="--bank-color:${bankColors[bank]}">
      <div class="card-title"><span>${esc(name)}</span>${dirty ? "<span class='dirty-dot' title='Unsaved changes'>●</span>" : ""}</div>
      <div class="card-sub">${esc(label)} · ${render && render.slot_based ? "<span class='gradient-dot'></span>show-colored" : "<span class='fixed-dot'></span>fixed colors"}</div>
      <div class="card-ref">${esc(look.scene_ref || look.action || "")}</div>
      <div class="badge-row"><span class="badge">${cue} beats</span>${timingBadge(render)}${render && render.strobe ? "<span class='badge strobe'>⚡ strobe</span>" : ""}${!realtime ? "<span class='badge'>☁ cloud</span>" : ""}${playing ? "<span class='live-chip'>LIVE</span>" : ""}</div>
      <footer class="card-footer">
        <button type="button" class="primary" data-action="play" data-name="${esc(name)}" ${!realtime ? "disabled title='Cloud scene - not previewable in the pad'" : ""}>▶ Play</button>
        <div class="icon-actions">
          <button type="button" class="icon" data-action="edit" data-name="${esc(name)}" aria-label="Edit" title="Edit">✎</button>
          <button type="button" class="icon" data-action="duplicate" data-name="${esc(name)}" aria-label="Duplicate" title="Duplicate">⧉</button>
          <button type="button" class="icon" data-action="move" data-name="${esc(name)}" aria-label="Move" title="Move">⇄</button>
          <button type="button" class="icon delete" data-action="delete" data-name="${esc(name)}" aria-label="Delete" title="Delete">🗑</button>
        </div>
      </footer>
    </article>`;
  }
  async function saveCurrentEditor() {
    const e = state.editor;
    const res = await api.saveLook({
      name: e.name,
      look: e.look,
      params: e.params,
      cue_beats: e.cue_beats,
      slot_fill: e.slot_fill,
      mono_chance: e.mono_chance,
      locked_palette: e.locked_palette || "",
    });
    if (!res.ok) throw new Error((res.errors || []).join("\n"));
    state.cleanSnapshot = snapshotEditor();
  }
  async function switchEditor(name, play) {
    if (state.editor && state.editor.name !== name && snapshotEditor() !== state.cleanSnapshot) {
      threeWaySwitch(name, play);
      return;
    }
    await openEditor(name, play);
  }
  async function onCardAction(ev) {
    const {action, name} = ev.currentTarget.dataset;
    state.lastFocus = ev.currentTarget;
    try {
      if (action === "play") { await switchEditor(name, true); return; }
      if (action === "edit") { await switchEditor(name, false); return; }
      if (action === "duplicate") {
        promptModal("Duplicate look", "", {label:"Duplicate name", value:`${name}_copy`, confirmText:"Duplicate"}, async (newName) => {
          if (!newName) return;
          try { await api.duplicate({source:name, new_name:newName}); await refresh(); await openEditor(newName, false); }
          catch (err) { showError(err); }
        });
        return;
      }
      if (action === "move") { moveModal(name); return; }
      if (action === "delete") confirmModal("Delete look", `Delete removes ${name} from the LED Pad draft.`, "Delete", async () => { const res = await api.deleteLook({name}); if (!res.ok) throw new Error((res.errors || []).join("\n")); await refresh(); });
    } catch (err) { showError(err); }
  }
  async function openEditor(name, play) {
    const look = JSON.parse(JSON.stringify(state.config.config.looks[name] || {}));
    const meta = (((state.config.config._pad_meta || {}).looks || {})[name] || {});
    const engine = state.config.config.color_engine || {};
    state.editor = {name, look, params: JSON.parse(JSON.stringify(look.params || {})), cue_beats: meta.cue_beats || 16, slot_fill: ((engine.slot_fill_strategy_by_look || {})[name] || "gradient_even"), mono_chance: ((engine.slot_mono_chance_by_look || {})[name] || 0), locked_palette: ((engine.locked_palette_by_look || {})[name] || "")};
    state.cleanSnapshot = snapshotEditor();
    renderEditor();
    $("editorDrawer").hidden = false;
    $("closeEditorBtn").focus();
    if (play) await playEditor(false);
  }
  function renderEditor() {
    const e = state.editor, render = state.renderMap.get(e.look.scene_ref);
    $("editorTitle").textContent = e.name;
    $("editorRegistry").textContent = e.look.scene_ref || "";
    renderEditorLive();
    renderCue();
    renderRendererSelect();
    $("rendererDescription").textContent = render ? render.description || "" : "";
    $("brightnessInput").value = e.look.brightness ?? 100;
    $("brightnessOutput").textContent = `${$("brightnessInput").value}%`;
    $("strobeInput").checked = Boolean(e.look.allow_strobe);
    $("strobeLabel").textContent = $("strobeInput").checked ? "On" : "Off";
    $("lockedPaletteSelect").innerHTML = state.palettes.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
    $("lockedPaletteSelect").value = e.locked_palette || state.palettes[0] || "";
    $("lockedPaletteWrap").hidden = !e.locked_palette;
    $("followColorBtn").classList.toggle("active", !e.locked_palette);
    $("lockedPaletteBtn").classList.toggle("active", Boolean(e.locked_palette));
    const safety = !!((state.config.config.safety || {}).allow_strobe);
    $("strobeInput").disabled = !safety;
    $("strobeWarning").textContent = !safety ? "Disabled because safety.allow_strobe is false." : (render && render.strobe && !e.look.allow_strobe ? "Strobe-class renderer requires Strobe allowed before Play." : "");
    $("slotSection").hidden = !(render && render.slot_based);
    $("slotFillSelect").value = e.slot_fill;
    $("monoChanceInput").value = e.mono_chance;
    $("monoChanceOutput").textContent = e.mono_chance;
    $("monoChanceWrap").hidden = e.slot_fill !== "random_with_mono_chance";
    renderControls(render);
    $("loopHint").textContent = `Loop is ${$("loopToggle").checked ? "on" : "off"} (session)`;
    setDirty();
  }
  function renderEditorLive() {
    $("editorLive").hidden = !(state.editor && state.playingLook === state.editor.name);
  }
  function renderCue() {
    const values = [4, 8, 16, 32];
    const custom = values.includes(Number(state.editor.cue_beats)) ? "" : "active";
    $("editorDrawer").querySelector(".cue-group").innerHTML =
      values.map(v => `<button type="button" class="${Number(state.editor.cue_beats) === v ? "active" : ""}" data-cue="${v}">${v}</button>`).join("") +
      `<input id="customCueInput" class="${custom}" type="number" min="1" step="1" value="${esc(state.editor.cue_beats)}" aria-label="Custom cue length">`;
    $("editorDrawer").querySelectorAll("[data-cue]").forEach(btn => btn.addEventListener("click", () => {
      state.editor.cue_beats = Number(btn.dataset.cue);
      renderCue(); setDirty(); liveUpdate();
    }));
    $("customCueInput").addEventListener("change", ev => {
      state.editor.cue_beats = Number(ev.target.value || state.editor.cue_beats);
      renderCue(); setDirty(); liveUpdate();
    });
  }
  function renderRendererSelect() {
    const groups = {};
    for (const render of state.renders) (groups[render.group] ||= []).push(render);
    let html = Object.entries(groups).map(([group, renders]) => `<optgroup label="${esc(group)}">${renders.map(r => `<option value="${esc(r.name)}">${esc(r.label)}</option>`).join("")}</optgroup>`).join("");
    const sceneRef = state.editor.look.scene_ref;
    if (sceneRef && !state.renderMap.has(sceneRef)) {
      html = `<option value="${esc(sceneRef)}" selected disabled>☁ ${esc(sceneRef)} — cloud scene (not previewable)</option>` + html;
    }
    $("rendererSelect").innerHTML = html;
    $("rendererSelect").value = sceneRef;
  }
  function renderControls(render) {
    const basic = $("controlRows"), adv = $("advancedRows");
    basic.innerHTML = ""; adv.innerHTML = "";
    if (!render) return;
    // Engine-colored looks audition with palette-injected colors: badge
    // rgb-kind and color-signature rows.
    const engineColored = String((state.editor.look || {}).color_source || "engine") === "engine";
    for (const control of render.controls || []) {
      const badged = engineColored && (control.kind === "rgb" || Boolean(control.color_sig));
      (control.advanced ? adv : basic).insertAdjacentHTML("beforeend", controlRow(control, badged));
    }
    $("advancedDetails").hidden = !adv.innerHTML;
    document.querySelectorAll("[data-param]").forEach(input => input.addEventListener("input", ev => {
      const key = ev.currentTarget.dataset.param;
      let value = ev.currentTarget.type === "checkbox" ? ev.currentTarget.checked : ev.currentTarget.value;
      if (ev.currentTarget.type === "number" || ev.currentTarget.type === "range") value = Number(value);
      if (ev.currentTarget.type === "color") {
        const hex = ev.currentTarget.value;
        value = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
        const chip = ev.currentTarget.closest(".control-row").querySelector("[data-swatch-for]");
        if (chip) chip.style.background = hex;
      }
      state.editor.params[key] = value;
      const out = document.querySelector(`[data-output="${CSS.escape(key)}"]`);
      if (out) out.textContent = ev.currentTarget.type === "color" ? ev.currentTarget.value : String(value);
      const resetBtn = document.querySelector(`[data-reset="${CSS.escape(key)}"]`);
      if (resetBtn) { resetBtn.style.visibility = "visible"; resetBtn.removeAttribute("tabindex"); }
      setDirty(); liveUpdate();
    }));
    document.querySelectorAll("[data-reset]").forEach(btn => btn.addEventListener("click", ev => {
      const key = ev.currentTarget.dataset.reset;
      delete state.editor.params[key];
      renderControls(render);
      setDirty(); liveUpdate();
    }));
  }
  function controlRow(c, badged) {
    const isSet = Object.prototype.hasOwnProperty.call(state.editor.params, c.key);
    const hasDefault = c.default !== null && c.default !== undefined;
    const value = isSet ? state.editor.params[c.key] : (hasDefault ? c.default : (c.kind === "bool" ? false : c.min ?? ""));
    let outputText = isSet ? String(value) : (hasDefault ? String(c.default) : "auto");
    let input = "";
    if (c.kind === "bool") input = `<input data-param="${esc(c.key)}" type="checkbox" ${value ? "checked" : ""}>`;
    else if (c.kind === "choice") input = `<select data-param="${esc(c.key)}">${(c.choices || []).map(v => `<option value="${esc(v)}" ${String(v)===String(value)?"selected":""}>${esc(v)}</option>`).join("")}</select>`;
    else if (c.kind === "rgb") {
      const rgb = Array.isArray(value) && value.length === 3 ? value : [0, 0, 0];
      const hex = `#${rgb.map(v => Math.max(0, Math.min(255, Math.round(Number(v) || 0))).toString(16).padStart(2, "0")).join("")}`;
      input = `<span class="color-cell"><input data-param="${esc(c.key)}" type="color" value="${hex}"><span class="swatch-chip small" data-swatch-for="${esc(c.key)}" style="background:${hex}"></span></span>`;
      outputText = isSet ? hex : "auto";
    }
    else input = `<input data-param="${esc(c.key)}" type="number" min="${esc(c.min ?? "")}" max="${esc(c.max ?? "")}" step="${esc(c.step ?? 1)}" value="${esc(value)}">`;
    const tag = isSet ? "" : `<span class="default-tag">default</span>`;
    const badge = badged ? `<span class="regime-badge">palette overrides this in the room</span>` : "";
    const resetHidden = isSet ? "" : ` style="visibility:hidden" tabindex="-1"`;
    const reset = `<button type="button" class="icon ghost reset-param" data-reset="${esc(c.key)}" aria-label="Reset to default" title="Reset to default"${resetHidden}>↺</button>`;
    return `<label class="control-row${badged ? " palette-fed" : ""}"><span>${esc(c.label)}${badge}</span>${input}<output data-output="${esc(c.key)}">${esc(outputText)}${tag}</output>${reset}</label>`;
  }
  async function playEditor(takeover) {
    try {
      const res = await api.play({name: state.editor.name, editor: editorPayload(), takeover});
      if (!res.ok) throw new Error(res.error || (res.errors || []).join("\n"));
      await refresh();
    } catch (err) {
      if ((err && err.message) === "ownership_required") ownershipDialog();
      else showError(err);
    }
  }
  function liveUpdate() {
    clearTimeout(state.updateTimer);
    state.updateTimer = setTimeout(async () => {
      if (!$("editorDrawer").hidden && state.editor) {
        try { await api.update({name: state.editor.name, editor: editorPayload()}); }
        catch (err) { showError(err); }
      }
    }, 150);
  }
  function closeModal() {
    PadModal.close();
  }
  function modal(title, text, actions) {
    PadModal.show(title, text, actions);
  }
  function confirmModal(title, text, actionText, onConfirm) {
    PadModal.confirm(title, text, actionText, onConfirm);
  }
  function promptModal(title, message, options, onConfirm) {
    PadModal.prompt(title, message, options, onConfirm);
  }
  function threeWaySwitch(name, play) {
    modal("Unsaved changes", "Save this look before switching?", [
      {label:"Save and switch", className:"primary", run:async () => { await saveCurrentEditor(); await refresh(); await openEditor(name, play); }},
      {label:"Discard and switch", className:"danger-outline", run:async () => { await openEditor(name, play); }},
      {label:"Stay", className:"ghost", run:() => {}},
    ]);
  }
  function moveModal(name) {
    const current = lookBank(name);
    modal("Move look", `Move ${name} to another bank.`, moveBanks.map(bank => ({
      label: bankLabels[bank],
      className: bank === current ? "ghost" : "primary",
      run: async () => {
        if (bank === current) return;
        const res = await api.move({name, bank});
        if (!res.ok) throw new Error((res.errors || []).join("\n"));
        await refresh();
      },
    })));
    $("modalActions").querySelectorAll("button").forEach((btn, i) => { btn.disabled = moveBanks[i] === current; });
  }
  function ownershipDialog() {
    confirmModal("The bridge owns the LEDs right now. Take over?", "LEDs go dark on the bridge side until you release.", "Take over", () => playEditor(true));
  }
  async function openAccessModal() {
    modal("Open on another device", "Checking network access…", [{label:"Close", className:"ghost", run:() => {}}]);
    try {
      const info = await api.access();
      renderAccessModal(info);
    } catch (err) {
      $("modalText").textContent = `Could not check network access: ${(err && err.message) || String(err)}`;
    }
  }
  function renderAccessModal(info) {
    let html = "";
    if (info.lan_url) {
      let svg = "";
      try {
        const qr = qrcode(0, "M");
        qr.addData(info.lan_url);
        qr.make();
        svg = qr.createSvgTag({cellSize: 4, margin: 4});
      } catch (err) { svg = ""; }
      html += `<div class="qr-wrap">${svg}</div>`;
      html += `<p class="mono" style="user-select:all">${esc(info.lan_url)}</p>`;
      html += `<p class="warn-text">Anyone on this Wi-Fi can edit config through this page.</p>`;
    } else if (info.loopback_only) {
      html += `<p class="dim">This pad is only reachable from this Mac right now.</p>`;
      html += `<p class="dim">To allow access from another device on this Wi-Fi, restart the pad with <span class="mono">--host lan</span>, or edit the LaunchAgent plist at <span class="mono">~/Library/LaunchAgents/com.bbui.led-pad.plist</span> and run <span class="mono">launchctl kickstart -k gui/$UID/com.bbui.led-pad</span>.</p>`;
      html += `<p class="warn-text">Doing so exposes pad control to the whole network.</p>`;
    } else {
      html += `<p class="warn-text">No LAN address detected — check Wi-Fi.</p>`;
    }
    $("modalText").innerHTML = html;
  }
  function closeEditor(force) {
    if (!force && snapshotEditor() !== state.cleanSnapshot) {
      confirmModal("Discard unsaved changes?", "You have edits since your last save. Discard them and close?", "Discard", () => closeEditor(true));
      return;
    }
    $("editorDrawer").hidden = true; state.editor = null; if (state.lastFocus) state.lastFocus.focus(); renderCards();
  }
  // Failures propagate to callers: PadHealth's poll counts them toward the
  // reconnect banner, and direct calls surface them via showError.
  async function updateRuntime() {
    const rt = await api.runtime();
    const stateName = ((rt.ownership || {}).state || "free");
    const warning = (rt.ownership || {}).warning || "";
    const playing = (rt.playback || {}).playing ? (rt.playback.playing_look || rt.playing_look || "") : "";
    const changed = playing !== state.playingLook;
    state.playingLook = playing;
    $("ownershipPill").textContent = stateName === "bridge_owned" ? "Bridge owns LEDs" : stateName === "pad_owned" ? "Pad owns LEDs" : "Free";
    $("ownershipPill").className = `pill ${stateName === "bridge_owned" ? "bridge" : stateName === "pad_owned" ? "pad" : ""}`;
    $("ownershipBtn").hidden = stateName === "free";
    $("ownershipBtn").textContent = stateName === "pad_owned" ? "Release" : "Take over";
    if (warning) {
      $("errorBanner").hidden = false;
      $("errorBanner").textContent = "Bridge reappeared - pad re-asserted control.";
      $("errorBanner").classList.add("warn-banner");
    } else if ($("errorBanner").classList.contains("warn-banner") && $("errorBanner").textContent !== RECONNECT_TEXT) {
      clearError();
    }
    if (changed) { renderCards(); renderEditorLive(); }
    if (window.PadConfigStale) window.PadConfigStale.render($("configStaleBanner"), rt.config_stale);
  }
  document.addEventListener("keydown", ev => {
    if (ev.key !== "Escape") return;
    if (PadModal.isOpen()) closeModal();
    else if (!$("editorDrawer").hidden) closeEditor(false);
  });
  $("bpmInput").addEventListener("change", ev => api.session({bpm:Number(ev.target.value)}).catch(showError));
  document.querySelectorAll("[data-step]").forEach(btn => btn.addEventListener("click", () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); }));
  $("paletteSelect").addEventListener("change", ev => api.session({test_palette:ev.target.value}).catch(showError));
  $("loopToggle").addEventListener("change", ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); });
  $("stopBtn").addEventListener("click", () => api.emergencyStop().then(refresh).catch(showError));
  $("ownershipBtn").addEventListener("click", async () => { try { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); } catch (err) { showError(err); } });
  $("qrBtn").addEventListener("click", openAccessModal);
  $("commitBtn").addEventListener("click", () => confirmModal("Apply draft to live config", `Apply writes the draft to live config - ${($("commitCount").textContent || "0")} looks affected. Bridge restart required to take effect live.${(state.config || {}).live_changed ? "\nLive config changed underneath this draft (bridge or agent edit). Review before Apply — Discard reloads live." : ""}`, "Apply", async () => { const res = await api.commit(); if (!res.ok) throw new Error((res.errors || []).join("\n")); toast(res.restart_note || "Applied - bridge restart required to take effect live."); await refresh(); }));
  $("discardBtn").addEventListener("click", () => confirmModal("Discard draft", "Discard reloads the live config and deletes your draft changes.", "Discard", async () => { await api.discard(); await refresh(); }));
  $("closeEditorBtn").addEventListener("click", () => closeEditor(false));
  $("cancelBtn").addEventListener("click", () => closeEditor(false));
  $("undoBtn").addEventListener("click", () => confirmModal("Undo editor changes", "Undo reverts this editor to the last saved or opened state.", "Undo", () => { const data = JSON.parse(state.cleanSnapshot); state.editor.look = data.look; state.editor.params = data.params; state.editor.cue_beats = data.cue_beats; state.editor.slot_fill = data.slot_fill; state.editor.mono_chance = data.mono_chance; state.editor.locked_palette = data.locked_palette || ""; renderEditor(); liveUpdate(); }));
  $("saveLookBtn").addEventListener("click", async () => { try { await saveCurrentEditor(); await refresh(); setDirty(); } catch (err) { showError(err); } });
  $("editorPlayBtn").addEventListener("click", () => playEditor(false));
  $("editorStopBtn").addEventListener("click", () => api.stop().then(refresh).catch(showError));
  $("rendererSelect").addEventListener("change", ev => { const render = state.renderMap.get(ev.target.value); const allowed = new Set((render.controls || []).map(c => c.key)); state.editor.look.scene_ref = ev.target.value; state.editor.params = Object.fromEntries(Object.entries(state.editor.params).filter(([k]) => allowed.has(k))); renderEditor(); liveUpdate(); });
  $("followColorBtn").addEventListener("click", () => { state.editor.locked_palette = ""; renderEditor(); setDirty(); liveUpdate(); });
  $("lockedPaletteBtn").addEventListener("click", () => { state.editor.locked_palette = state.editor.locked_palette || state.palettes[0] || ""; renderEditor(); setDirty(); liveUpdate(); });
  $("lockedPaletteSelect").addEventListener("change", ev => { state.editor.locked_palette = ev.target.value; setDirty(); liveUpdate(); });
  $("brightnessInput").addEventListener("input", ev => { state.editor.look.brightness = Number(ev.target.value); $("brightnessOutput").textContent = `${ev.target.value}%`; setDirty(); });
  $("strobeInput").addEventListener("change", ev => { state.editor.look.allow_strobe = ev.target.checked; $("strobeLabel").textContent = ev.target.checked ? "On" : "Off"; setDirty(); });
  $("slotFillSelect").addEventListener("change", ev => { state.editor.slot_fill = ev.target.value; $("monoChanceWrap").hidden = state.editor.slot_fill !== "random_with_mono_chance"; setDirty(); liveUpdate(); });
  $("monoChanceInput").addEventListener("input", ev => { state.editor.mono_chance = Number(ev.target.value); $("monoChanceOutput").textContent = ev.target.value; setDirty(); liveUpdate(); });
  window.addEventListener("beforeunload", (ev) => {
    if (!(state.editor && snapshotEditor() !== state.cleanSnapshot)) return;
    ev.preventDefault();
    ev.returnValue = "";
  });
  refresh().catch(showError);
  PadHealth.start({
    poll: updateRuntime,
    refresh,
    banner: (down) => {
      if (down) {
        $("errorBanner").hidden = false;
        $("errorBanner").textContent = RECONNECT_TEXT;
        $("errorBanner").classList.add("warn-banner");
      } else if ($("errorBanner").textContent === RECONNECT_TEXT) {
        clearError();
      }
    },
  });
}());
