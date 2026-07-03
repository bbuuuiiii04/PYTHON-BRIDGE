(function () {
  const bankOrder = ["drafts", "ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility"];
  const moveBanks = ["ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility"];
  const bankLabels = {drafts:"Drafts", ambient:"Ambient", groove:"Groove", buildup:"Buildup", pre_drop:"Pre-Drop", drop:"Drop", post_drop:"Post-Drop", breakdown:"Breakdown", utility:"Utility", other:"Other"};
  const bankColors = {drafts:"var(--lab)", ambient:"#4cc9c0", groove:"#35b6ff", buildup:"#e8b13f", drop:"#f25f5c", post_drop:"#b48cff", breakdown:"#6f9bd1", utility:"#8b98a5", other:"var(--border)"};
  const state = {config:null, banks:{}, renders:[], renderMap:new Map(), palettes:[], activeBank:"drafts", editor:null, openSnapshot:null, cleanSnapshot:null, updateTimer:null, lastFocus:null, playingLook:"", modalOpen:false};
  const $ = (id) => document.getElementById(id);
  const api = window.LedPadApi;
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

  function showError(err) {
    $("errorBanner").hidden = false;
    $("errorBanner").textContent = err && err.message ? err.message : String(err);
  }
  function clearError() { $("errorBanner").hidden = true; $("errorBanner").textContent = ""; $("errorBanner").classList.remove("warn-banner"); }
  function toast(text) {
    $("toast").textContent = text;
    $("toast").hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4000);
  }
  function human(name) { return String(name).replace(/^rt_/, "").replaceAll("_", " ").replace("post drop", "post-drop").replace(/\b\w/g, c => c.toUpperCase()); }
  function lookBank(name) {
    for (const [bank, names] of Object.entries(state.banks || {})) if ((names || []).includes(name)) return bank;
    return "other";
  }
  function lookDirty(name) { return (state.config.dirty.looks || []).includes(name); }
  function currentSession() { return (((state.config || {}).config || {})._pad_meta || {}).ui || {}; }
  function editorPayload() {
    const e = state.editor;
    return {look: e.look, params: e.params, cue_beats: e.cue_beats, slot_fill: e.slot_fill, mono_chance: e.mono_chance};
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
    const playing = state.playingLook === name;
    const label = render ? render.label : human(look.scene_ref || look.action);
    return `<article class="look-card ${esc(bank)} ${playing ? "playing" : ""}" style="--bank-color:${bankColors[bank]}">
      <div class="card-title"><span>${esc(name)}</span>${dirty ? "<span class='dirty-dot' title='Unsaved changes'>●</span>" : ""}</div>
      <div class="dim">${esc(label)} · ${render && render.slot_based ? "<span class='gradient-dot'></span>show-colored" : "<span class='fixed-dot'></span>fixed colors"} ${render && render.strobe ? "<span class='badge strobe'>⚡ strobe</span>" : ""}${!realtime ? "<span class='badge'>☁ cloud</span>" : ""}</div>
      <div><span class="badge">${cue} beats</span>${playing ? " <span class='live-chip'>LIVE</span>" : ""}</div>
      <footer class="card-footer">
        <button type="button" class="primary" data-action="play" data-name="${esc(name)}" ${!realtime ? "disabled title='Cloud scene - not previewable in the pad'" : ""}>▶ Play</button>
        <button type="button" class="icon" data-action="edit" data-name="${esc(name)}" aria-label="Edit" title="Edit">✎</button>
        <button type="button" class="icon" data-action="duplicate" data-name="${esc(name)}" aria-label="Duplicate" title="Duplicate">⧉</button>
        <button type="button" class="icon" data-action="move" data-name="${esc(name)}" aria-label="Move" title="Move">⇄</button>
        <button type="button" class="icon delete" data-action="delete" data-name="${esc(name)}" aria-label="Delete" title="Delete">🗑</button>
      </footer>
    </article>`;
  }
  async function saveCurrentEditor() {
    const e = state.editor;
    const res = await api.saveLook({name:e.name, look:e.look, params:e.params, cue_beats:e.cue_beats, slot_fill:e.slot_fill, mono_chance:e.mono_chance});
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
        const newName = prompt("Duplicate name", `${name}_copy`);
        if (newName) { await api.duplicate({source:name, new_name:newName}); await refresh(); await openEditor(newName, false); }
        return;
      }
      if (action === "move") { moveModal(name); return; }
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
    $("rendererSelect").innerHTML = Object.entries(groups).map(([group, renders]) => `<optgroup label="${esc(group)}">${renders.map(r => `<option value="${esc(r.name)}">${esc(r.label)}</option>`).join("")}</optgroup>`).join("");
    $("rendererSelect").value = state.editor.look.scene_ref;
  }
  function renderControls(render) {
    const basic = $("controlRows"), adv = $("advancedRows");
    basic.innerHTML = ""; adv.innerHTML = "";
    if (!render) return;
    for (const control of render.controls || []) {
      if (control.kind === "rgb") continue;
      (control.advanced ? adv : basic).insertAdjacentHTML("beforeend", controlRow(control));
    }
    $("advancedDetails").hidden = !adv.innerHTML;
    document.querySelectorAll("[data-param]").forEach(input => input.addEventListener("input", ev => {
      const key = ev.currentTarget.dataset.param;
      let value = ev.currentTarget.type === "checkbox" ? ev.currentTarget.checked : ev.currentTarget.value;
      if (ev.currentTarget.type === "number" || ev.currentTarget.type === "range") value = Number(value);
      state.editor.params[key] = value;
      const out = document.querySelector(`[data-output="${CSS.escape(key)}"]`);
      if (out) out.textContent = String(value);
      setDirty(); liveUpdate();
    }));
  }
  function controlRow(c) {
    const value = state.editor.params[c.key] ?? (c.kind === "bool" ? false : c.min ?? "");
    let input = "";
    if (c.kind === "bool") input = `<input data-param="${esc(c.key)}" type="checkbox" ${value ? "checked" : ""}>`;
    else if (c.kind === "choice") input = `<select data-param="${esc(c.key)}">${(c.choices || []).map(v => `<option value="${esc(v)}" ${String(v)===String(value)?"selected":""}>${esc(v)}</option>`).join("")}</select>`;
    else input = `<input data-param="${esc(c.key)}" type="number" min="${esc(c.min ?? "")}" max="${esc(c.max ?? "")}" step="${esc(c.step ?? 1)}" value="${esc(value)}">`;
    return `<label class="control-row"><span>${esc(c.label)}</span>${input}<output data-output="${esc(c.key)}">${esc(value)}</output></label>`;
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
    $("modal").hidden = true;
    state.modalOpen = false;
  }
  function modal(title, text, actions) {
    $("modalTitle").textContent = title;
    $("modalText").textContent = text;
    $("modalActions").innerHTML = actions.map((a, i) => `<button type="button" class="${esc(a.className || "ghost")}" data-modal-action="${i}">${esc(a.label)}</button>`).join("");
    $("modal").hidden = false;
    state.modalOpen = true;
    $("modalActions").querySelector("button").focus();
    $("modalActions").querySelectorAll("button").forEach((btn, i) => btn.onclick = async () => {
      closeModal();
      try { await actions[i].run(); } catch (err) { showError(err); }
    });
  }
  function confirmModal(title, text, actionText, onConfirm) {
    modal(title, text, [
      {label:"Cancel", className:"ghost", run:() => {}},
      {label:actionText, className:"danger-outline", run:onConfirm},
    ]);
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
      } else if ($("errorBanner").classList.contains("warn-banner")) {
        clearError();
      }
      if (changed) { renderCards(); renderEditorLive(); }
    } catch (_) {}
  }
  document.addEventListener("keydown", ev => {
    if (ev.key !== "Escape") return;
    if (state.modalOpen) closeModal();
    else if (!$("editorDrawer").hidden) closeEditor(false);
  });
  $("bpmInput").addEventListener("change", ev => api.session({bpm:Number(ev.target.value)}).catch(showError));
  document.querySelectorAll("[data-step]").forEach(btn => btn.addEventListener("click", () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); }));
  $("paletteSelect").addEventListener("change", ev => api.session({test_palette:ev.target.value}).catch(showError));
  $("loopToggle").addEventListener("change", ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); });
  $("stopBtn").addEventListener("click", () => api.emergencyStop().then(refresh).catch(showError));
  $("ownershipBtn").addEventListener("click", async () => { try { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); } catch (err) { showError(err); } });
  $("commitBtn").addEventListener("click", () => confirmModal("Commit LED Pad draft", `Commit writes the draft to live config - ${($("commitCount").textContent || "0")} looks affected.`, "Commit", async () => { const res = await api.commit(); if (!res.ok) throw new Error((res.errors || []).join("\n")); toast(res.restart_note || "Committed - bridge restart required to take effect live."); await refresh(); }));
  $("discardBtn").addEventListener("click", () => confirmModal("Discard LED Pad draft", "Discard reloads the live config and deletes your draft changes.", "Discard", async () => { await api.discard(); await refresh(); }));
  $("closeEditorBtn").addEventListener("click", () => closeEditor(false));
  $("cancelBtn").addEventListener("click", () => closeEditor(false));
  $("undoBtn").addEventListener("click", () => confirmModal("Undo editor changes", "Undo reverts this editor to the last saved or opened state.", "Undo", () => { const data = JSON.parse(state.cleanSnapshot); state.editor.look = data.look; state.editor.params = data.params; state.editor.cue_beats = data.cue_beats; state.editor.slot_fill = data.slot_fill; state.editor.mono_chance = data.mono_chance; renderEditor(); liveUpdate(); }));
  $("saveLookBtn").addEventListener("click", async () => { try { await saveCurrentEditor(); await refresh(); setDirty(); } catch (err) { showError(err); } });
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
