(function () {
  const bankOrder = ["drafts", "ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility"];
  const bankLabels = {drafts:"Drafts", ambient:"Ambient", groove:"Groove", buildup:"Buildup", drop:"Drop", post_drop:"Post-Drop", breakdown:"Breakdown", utility:"Utility", other:"Other"};
  const bankColors = {drafts:"var(--lab)", ambient:"#4cc9c0", groove:"#35b6ff", buildup:"#e8b13f", drop:"#f25f5c", post_drop:"#b48cff", breakdown:"#6f9bd1", utility:"#8b98a5", other:"var(--border)"};
  const state = {config:null, banks:{}, renders:[], renderMap:new Map(), palettes:[], activeBank:"drafts", editor:null, openSnapshot:null, cleanSnapshot:null, updateTimer:null, lastFocus:null};
  const $ = (id) => document.getElementById(id);
  const api = window.LedPadApi;

  function showError(err) {
    $("errorBanner").hidden = false;
    $("errorBanner").textContent = err && err.message ? err.message : String(err);
  }
  function clearError() { $("errorBanner").hidden = true; $("errorBanner").textContent = ""; }
  function human(name) { return String(name).replace(/^rt_/, "").replaceAll("_", " ").replace("post drop", "post-drop").replace(/\b\w/g, c => c.toUpperCase()); }
  function lookBank(name) {
    for (const [bank, names] of Object.entries(state.banks || {})) if ((names || []).includes(name)) return bank;
    return "other";
  }
  function lookDirty(name) { return (state.config.dirty.looks || []).includes(name); }
  function currentSession() { return (((state.config || {}).config || {})._pad_meta || {}).ui || {}; }
  function editorPayload() {
    const e = state.editor;
    return {look: e.look, params: e.params, cue_beats: e.cue_beats};
  }
  function snapshotEditor() { return JSON.stringify(editorPayload()); }
  function setDirty() {
    const dirty = state.editor && snapshotEditor() !== state.cleanSnapshot;
    $("saveLookBtn").disabled = !dirty;
    $("dirtyText").textContent = dirty ? "Unsaved changes" : "Saved";
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
    renderSession();
    renderBanks();
    renderCards();
    updateRuntime();
  }
  function renderSession() {
    const ui = currentSession();
    $("bpmInput").value = ui.bpm || 128;
    $("paletteSelect").innerHTML = state.palettes.map(p => `<option value="${p}">${p}</option>`).join("");
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
      return `<button type="button" class="${bank} ${bank === state.activeBank ? "active" : ""}" style="--bank-color:${bankColors[bank]}" data-bank="${bank}">${bankLabels[bank]} ${count} ${dirty ? "<span class='dirty-dot'>●</span>" : ""}</button>`;
    }).join("");
    tabs.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => { state.activeBank = btn.dataset.bank; renderBanks(); renderCards(); }));
  }
  function renderCards() {
    const names = state.banks[state.activeBank] || [];
    const grid = $("lookGrid");
    if (!names.length) {
      grid.innerHTML = `<div class="empty">${state.activeBank === "drafts" ? "New looks land here. Automation never plays drafts." : "Empty bank."}</div>`;
      return;
    }
    grid.innerHTML = names.map(name => cardHtml(name)).join("");
    grid.querySelectorAll("[data-action]").forEach(btn => btn.addEventListener("click", onCardAction));
  }
  function cardHtml(name) {
    const look = state.config.config.looks[name] || {};
    const render = state.renderMap.get(look.scene_ref);
    const bank = lookBank(name);
    const realtime = Boolean(render);
    const dirty = lookDirty(name);
    const cue = (((state.config.config._pad_meta || {}).looks || {})[name] || {}).cue_beats || 16;
    return `<article class="look-card ${bank} ${state.editor && state.editor.name === name ? "playing" : ""}" style="--bank-color:${bankColors[bank]}">
      <div class="card-title"><span>${name}</span>${dirty ? "<span class='dirty-dot' title='Unsaved changes'>●</span>" : ""}</div>
      <div class="dim">${render ? render.label : human(look.scene_ref || look.action)} · ${render && render.slot_based ? "<span class='gradient-dot'></span>show-colored" : "<span class='fixed-dot'></span>fixed colors"} ${render && render.strobe ? "<span class='badge strobe'>⚡ strobe</span>" : ""}${!realtime ? "<span class='badge'>☁ cloud</span>" : ""}</div>
      <div><span class="badge">${cue} beats</span>${state.editor && state.editor.name === name ? " <span class='live-chip'>LIVE</span>" : ""}</div>
      <footer class="card-footer">
        <button type="button" class="primary" data-action="play" data-name="${name}" ${!realtime ? "disabled title='Cloud scene - not previewable in the pad'" : ""}>▶ Play</button>
        <button type="button" class="icon" data-action="edit" data-name="${name}" aria-label="Edit" title="Edit">✎</button>
        <button type="button" class="icon" data-action="duplicate" data-name="${name}" aria-label="Duplicate" title="Duplicate">⧉</button>
        <button type="button" class="icon" data-action="move" data-name="${name}" aria-label="Move" title="Move">⇄</button>
        <button type="button" class="icon delete" data-action="delete" data-name="${name}" aria-label="Delete" title="Delete">🗑</button>
      </footer>
    </article>`;
  }
  async function onCardAction(ev) {
    const {action, name} = ev.currentTarget.dataset;
    state.lastFocus = ev.currentTarget;
    try {
      if (action === "play") { await openEditor(name, true); return; }
      if (action === "edit") { await openEditor(name, false); return; }
      if (action === "duplicate") {
        const newName = prompt("Duplicate name", `${name}_copy`);
        if (newName) { await api.duplicate({source:name, new_name:newName}); await refresh(); await openEditor(newName, false); }
        return;
      }
      if (action === "move") {
        const bank = prompt("Move to bank", "drafts");
        if (bank) { const res = await api.move({name, bank}); if (!res.ok) throw new Error((res.errors || []).join("\n")); await refresh(); }
        return;
      }
      if (action === "delete") confirmModal("Delete look", `Delete removes ${name} from the LED Pad draft.`, "Delete", async () => { const res = await api.deleteLook({name}); if (!res.ok) throw new Error((res.errors || []).join("\n")); await refresh(); });
    } catch (err) { showError(err); }
  }
  async function openEditor(name, play) {
    const look = JSON.parse(JSON.stringify(state.config.config.looks[name] || {}));
    const meta = (((state.config.config._pad_meta || {}).looks || {})[name] || {});
    state.editor = {name, look, params: JSON.parse(JSON.stringify(look.params || {})), cue_beats: meta.cue_beats || 16, slot_fill: (((state.config.config.color_engine || {}).slot_fill_strategy_by_look || {})[name] || "gradient_even"), mono_chance: (((state.config.config.color_engine || {}).slot_mono_chance_by_look || {})[name] || 0)};
    state.openSnapshot = snapshotEditor();
    state.cleanSnapshot = snapshotEditor();
    renderEditor();
    $("editorDrawer").hidden = false;
    trapFocus();
    if (play) await playEditor(false);
  }
  function renderEditor() {
    const e = state.editor, render = state.renderMap.get(e.look.scene_ref);
    $("editorTitle").textContent = e.name;
    $("editorRegistry").textContent = e.look.scene_ref || "";
    $("editorLive").hidden = false;
    renderCue();
    renderRendererSelect();
    $("rendererDescription").textContent = render ? render.description || "" : "";
    $("brightnessInput").value = e.look.brightness ?? 100;
    $("brightnessOutput").textContent = `${$("brightnessInput").value}%`;
    $("strobeInput").checked = Boolean(e.look.allow_strobe);
    $("strobeLabel").textContent = $("strobeInput").checked ? "On" : "Off";
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
  function renderCue() {
    const values = [4, 8, 16, 32];
    $("editorDrawer").querySelector(".cue-group").innerHTML = values.map(v => `<button type="button" class="${state.editor.cue_beats === v ? "active" : ""}" data-cue="${v}">${v}</button>`).join("") + `<button type="button" data-cue="custom">✎</button>`;
    $("editorDrawer").querySelectorAll("[data-cue]").forEach(btn => btn.addEventListener("click", () => {
      state.editor.cue_beats = btn.dataset.cue === "custom" ? Number(prompt("Cue beats", state.editor.cue_beats) || state.editor.cue_beats) : Number(btn.dataset.cue);
      renderCue(); setDirty(); liveUpdate();
    }));
  }
  function renderRendererSelect() {
    const groups = {};
    for (const render of state.renders) (groups[render.group] ||= []).push(render);
    $("rendererSelect").innerHTML = Object.entries(groups).map(([group, renders]) => `<optgroup label="${group}">${renders.map(r => `<option value="${r.name}">${r.label}</option>`).join("")}</optgroup>`).join("");
    $("rendererSelect").value = state.editor.look.scene_ref;
  }
  function renderControls(render) {
    const basic = $("controlRows"), adv = $("advancedRows");
    basic.innerHTML = ""; adv.innerHTML = "";
    if (!render) return;
    for (const control of render.controls || []) {
      if (control.kind === "rgb") continue;
      const row = controlRow(control);
      (control.advanced ? adv : basic).insertAdjacentHTML("beforeend", row);
    }
    $("advancedDetails").hidden = !adv.innerHTML;
    document.querySelectorAll("[data-param]").forEach(input => input.addEventListener("input", ev => {
      const key = ev.currentTarget.dataset.param;
      let value = ev.currentTarget.type === "checkbox" ? ev.currentTarget.checked : ev.currentTarget.value;
      if (ev.currentTarget.type === "number" || ev.currentTarget.type === "range") value = Number(value);
      state.editor.params[key] = value;
      const out = document.querySelector(`[data-output="${key}"]`);
      if (out) out.textContent = String(value);
      setDirty(); liveUpdate();
    }));
  }
  function controlRow(c) {
    const value = state.editor.params[c.key] ?? (c.kind === "bool" ? false : c.min ?? "");
    let input = "";
    if (c.kind === "bool") input = `<input data-param="${c.key}" type="checkbox" ${value ? "checked" : ""}>`;
    else if (c.kind === "choice") input = `<select data-param="${c.key}">${(c.choices || []).map(v => `<option value="${v}" ${String(v)===String(value)?"selected":""}>${v}</option>`).join("")}</select>`;
    else input = `<input data-param="${c.key}" type="number" min="${c.min ?? ""}" max="${c.max ?? ""}" step="${c.step ?? 1}" value="${value}">`;
    return `<label class="control-row"><span>${c.label}</span>${input}<output data-output="${c.key}">${value}</output></label>`;
  }
  async function playEditor(takeover) {
    try {
      const res = await api.play({name: state.editor.name, editor: editorPayload(), takeover});
      if (!res.ok && res.error === "ownership_required") {
        ownershipDialog();
        return;
      }
      if (!res.ok) throw new Error(res.error || (res.errors || []).join("\n"));
      await refresh();
    } catch (err) { showError(err); }
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
  function confirmModal(title, text, actionText, onConfirm) {
    $("modalTitle").textContent = title; $("modalText").textContent = text;
    $("modalActions").innerHTML = `<button type="button" class="ghost" data-modal="cancel">Cancel</button><button type="button" class="danger-outline" data-modal="confirm">${actionText}</button>`;
    $("modal").hidden = false;
    $("modalActions").querySelector("[data-modal='cancel']").focus();
    $("modalActions").querySelector("[data-modal='cancel']").onclick = () => $("modal").hidden = true;
    $("modalActions").querySelector("[data-modal='confirm']").onclick = async () => { try { await onConfirm(); $("modal").hidden = true; } catch (err) { showError(err); } };
  }
  function ownershipDialog() {
    confirmModal("The bridge owns the LEDs right now. Take over?", "LEDs go dark on the bridge side until you release.", "Take over", () => playEditor(true));
  }
  function trapFocus() {
    $("closeEditorBtn").focus();
  }
  function closeEditor(force) {
    if (!force && snapshotEditor() !== state.openSnapshot) {
      confirmModal("Discard editor changes?", "Cancel discards changes since opening this editor.", "Discard", () => closeEditor(true));
      return;
    }
    $("editorDrawer").hidden = true; state.editor = null; if (state.lastFocus) state.lastFocus.focus(); renderCards();
  }
  async function updateRuntime() {
    try {
      const rt = await api.runtime();
      const stateName = ((rt.ownership || {}).state || "free");
      $("ownershipPill").textContent = stateName === "bridge_owned" ? "Bridge owns LEDs" : stateName === "pad_owned" ? "Pad owns LEDs" : "Free";
      $("ownershipPill").className = `pill ${stateName === "bridge_owned" ? "bridge" : stateName === "pad_owned" ? "pad" : ""}`;
      $("ownershipBtn").textContent = stateName === "pad_owned" ? "Release" : "Take over";
    } catch (_) {}
  }
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && !$("editorDrawer").hidden) closeEditor(false); });
  $("bpmInput").addEventListener("change", ev => api.session({bpm:Number(ev.target.value)}).catch(showError));
  document.querySelectorAll("[data-step]").forEach(btn => btn.addEventListener("click", () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); }));
  $("paletteSelect").addEventListener("change", ev => api.session({test_palette:ev.target.value}).catch(showError));
  $("loopToggle").addEventListener("change", ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); });
  $("stopBtn").addEventListener("click", () => api.emergencyStop().then(refresh).catch(showError));
  $("ownershipBtn").addEventListener("click", async () => { try { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); } catch (err) { showError(err); } });
  $("commitBtn").addEventListener("click", () => confirmModal("Commit LED Pad draft", `Commit writes the draft to live config - ${($("commitCount").textContent || "0")} looks affected.`, "Commit", async () => { const res = await api.commit(); if (!res.ok) throw new Error((res.errors || []).join("\n")); alert(res.restart_note || "Committed - bridge restart required to take effect live."); await refresh(); }));
  $("discardBtn").addEventListener("click", () => confirmModal("Discard LED Pad draft", "Discard reloads the live config and deletes your draft changes.", "Discard", async () => { await api.discard(); await refresh(); }));
  $("closeEditorBtn").addEventListener("click", () => closeEditor(false));
  $("cancelBtn").addEventListener("click", () => closeEditor(false));
  $("undoBtn").addEventListener("click", () => confirmModal("Undo editor changes", "Undo reverts this editor to the last saved or opened state.", "Undo", () => { const data = JSON.parse(state.cleanSnapshot); state.editor.look = data.look; state.editor.params = data.params; state.editor.cue_beats = data.cue_beats; renderEditor(); liveUpdate(); }));
  $("saveLookBtn").addEventListener("click", async () => { try { const e = state.editor; const res = await api.saveLook({name:e.name, look:e.look, params:e.params, cue_beats:e.cue_beats, slot_fill:e.slot_fill, mono_chance:e.mono_chance}); if (!res.ok) throw new Error((res.errors || []).join("\n")); state.cleanSnapshot = snapshotEditor(); await refresh(); setDirty(); } catch (err) { showError(err); } });
  $("editorPlayBtn").addEventListener("click", () => playEditor(false));
  $("editorStopBtn").addEventListener("click", () => api.stop().then(refresh).catch(showError));
  $("rendererSelect").addEventListener("change", ev => { const render = state.renderMap.get(ev.target.value); const allowed = new Set((render.controls || []).map(c => c.key)); state.editor.look.scene_ref = ev.target.value; state.editor.params = Object.fromEntries(Object.entries(state.editor.params).filter(([k]) => allowed.has(k))); renderEditor(); liveUpdate(); });
  $("brightnessInput").addEventListener("input", ev => { state.editor.look.brightness = Number(ev.target.value); $("brightnessOutput").textContent = `${ev.target.value}%`; setDirty(); });
  $("strobeInput").addEventListener("change", ev => { state.editor.look.allow_strobe = ev.target.checked; $("strobeLabel").textContent = ev.target.checked ? "On" : "Off"; setDirty(); });
  $("slotFillSelect").addEventListener("change", ev => { state.editor.slot_fill = ev.target.value; $("monoChanceWrap").hidden = state.editor.slot_fill !== "random_with_mono_chance"; setDirty(); liveUpdate(); });
  $("monoChanceInput").addEventListener("input", ev => { state.editor.mono_chance = Number(ev.target.value); $("monoChanceOutput").textContent = ev.target.value; setDirty(); liveUpdate(); });
  refresh().catch(showError);
  setInterval(updateRuntime, 2000);
}());
