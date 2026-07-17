(function () {
  const bankOrder = ["drafts", "ambient", "groove", "buildup", "drop", "post_drop", "breakdown", "utility", "legacy_color_suffix"];
  const moveBanks = ["ambient", "groove", "buildup", "pre_drop", "drop", "post_drop", "breakdown", "utility"];
  const bankLabels = {
    drafts: "Untagged",
    ambient: "Ambient",
    groove: "Groove",
    buildup: "Buildup",
    pre_drop: "Pre-Drop",
    drop: "Drop",
    post_drop: "Post-Drop",
    breakdown: "Breakdown",
    utility: "Utility",
    legacy_color_suffix: "Legacy — replaced by palette-driven cues, removed after live verify",
    other: "Other",
  };
  const bankColors = {
    drafts: "var(--lab)",
    ambient: "var(--role-ambient)",
    groove: "var(--role-groove)",
    buildup: "var(--role-buildup)",
    drop: "var(--role-drop)",
    post_drop: "var(--role-postdrop)",
    breakdown: "var(--role-breakdown)",
    utility: "var(--role-utility)",
    legacy_color_suffix: "var(--border)",
    other: "var(--border)",
  };
  // AWR-259: single source for dirty-tracked editor fields (save payload must match).
  const EDITOR_FIELDS = ["look", "params", "cue_beats", "slot_fill", "mono_chance", "locked_palette"];
  const state = {config:null, banks:{}, renders:[], renderMap:new Map(), palettes:[], activeBank:"drafts", editor:null, cleanSnapshot:null, updateTimer:null, lastFocus:null, playingLook:"", landingPicked:false};
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
  // Accepted Template Lab cues store scene_ref "lab:<draft>". They are real,
  // playable looks — not "cloud scenes" — so the pad names them honestly.
  function isLabScene(sceneRef) { return String(sceneRef || "").startsWith("lab:"); }
  function labCueName(sceneRef) { return human(String(sceneRef || "").slice(4)); }
  function titleCaseWords(value) {
    return String(value || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()).trim();
  }
  function timingBadge(render) {
    const label = ({
      beat: "Locks to the beat",
      mixed: "Beat + clock",
      time: "Runs on a clock",
      static: "Still",
    })[(render || {}).timing_mode];
    return label ? `<span class="badge">${label}</span>` : "";
  }
  function rgbTuple(value) {
    if (Array.isArray(value) && value.length >= 3) {
      return [Number(value[0]) || 0, Number(value[1]) || 0, Number(value[2]) || 0];
    }
    return null;
  }
  function nearestColorName(rgb) {
    const [r, g, b] = rgb;
    const named = [
      ["White", [255, 255, 255]],
      ["Black", [0, 0, 0]],
      ["Red", [220, 40, 40]],
      ["Orange", [240, 140, 40]],
      ["Yellow", [240, 220, 60]],
      ["Green", [40, 200, 80]],
      ["Cyan", [40, 200, 220]],
      ["Blue", [40, 80, 240]],
      ["Purple", [160, 60, 220]],
      ["Pink", [240, 80, 180]],
    ];
    let best = named[0][0];
    let bestDist = Infinity;
    for (const [label, [nr, ng, nb]] of named) {
      const dist = (r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2;
      if (dist < bestDist) { bestDist = dist; best = label; }
    }
    return best;
  }
  function colorwayChip(look) {
    const params = (look && look.params) || {};
    const a = rgbTuple(params.color_a) || rgbTuple(params.color);
    const b = rgbTuple(params.color_b);
    if (!a) return "";
    const hex = (rgb) => `#${rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("")}`;
    const names = [nearestColorName(a)];
    const swatches = [`<span class="colorway-swatch" style="background:${hex(a)}"></span>`];
    if (b && (b[0] !== a[0] || b[1] !== a[1] || b[2] !== a[2])) {
      names.push(nearestColorName(b));
      swatches.push(`<span class="colorway-swatch" style="background:${hex(b)}"></span>`);
    }
    return `<span class="colorway-chip" title="Colorway">${swatches.join("")}${esc(names.join(" + "))}</span>`;
  }
  function slugifyLookName(display, existingNames) {
    const raw = String(display || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    let base = (/^[a-z0-9_]+$/.test(raw) && raw) ? raw : "untitled";
    base = base.slice(0, 57); // AWR-279 #8: keep ids bounded (room for _N suffix)
    const taken = new Set(existingNames || []);
    let candidate = base;
    let n = 2;
    while (taken.has(candidate)) {
      candidate = `${base}_${n}`;
      n += 1;
    }
    return candidate;
  }
  const NAME_HINT = "Letters/numbers/spaces fine — we'll format it automatically";
  function allLookNames() { return Object.keys(((state.config || {}).config || {}).looks || {}); }
  function lookBank(name) {
    for (const [bank, names] of Object.entries(state.banks || {})) if ((names || []).includes(name)) return bank;
    return "other";
  }
  function inLegacyColorSuffixBank(name) {
    const legacy = (((state.config || {}).config || {}).banks || {}).legacy_color_suffix;
    if (!legacy || typeof legacy !== "object") return false;
    return Object.values(legacy).some(list => Array.isArray(list) && list.includes(name));
  }
  function lookDirty(name) { return (state.config.dirty.looks || []).includes(name); }
  function currentSession() { return (((state.config || {}).config || {})._pad_meta || {}).ui || {}; }
  function editorPayload() {
    const e = state.editor;
    const out = {};
    for (const key of EDITOR_FIELDS) {
      out[key] = key === "locked_palette" ? (e.locked_palette || "") : e[key];
    }
    return out;
  }
  function snapshotEditor() { return JSON.stringify(editorPayload()); }
  function setDirty() {
    const dirty = state.editor && snapshotEditor() !== state.cleanSnapshot;
    $("saveLookBtn").disabled = !dirty;
    $("dirtyText").textContent = dirty ? "Unsaved changes" : "Draft saved";
    $("dirtyText").className = dirty ? "warn-text" : "dim";
  }
  // AWR-270 I5: first paint should show looks, not an empty Untagged shelf.
  function pickLandingBank() {
    const phraseFirst = bankOrder.filter((bank) => bank !== "drafts" && bank !== "legacy_color_suffix");
    for (const bank of phraseFirst) {
      if ((state.banks[bank] || []).length) return bank;
    }
    if ((state.banks.drafts || []).length) return "drafts";
    if ((state.banks.other || []).length) return "other";
    if ((state.banks.legacy_color_suffix || []).length) return "legacy_color_suffix";
    return "drafts";
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
    if (!state.landingPicked) {
      state.activeBank = pickLandingBank();
      state.landingPicked = true;
    }
    renderSession();
    renderBanks();
    renderCards();
    await updateRuntime();
  }
  function renderSession() {
    const ui = currentSession();
    $("bpmInput").value = ui.bpm || 128;
    $("paletteSelect").innerHTML = state.palettes.map(p => `<option value="${esc(p)}">${esc(titleCaseWords(p))}</option>`).join("");
    $("paletteSelect").value = ui.test_palette || state.palettes[0] || "";
    $("loopToggle").checked = ui.loop !== false;
    $("loopLabel").textContent = $("loopToggle").checked ? "On" : "Off";
    const pendingLooks = (state.config.dirty.looks || []).length;
    $("commitCount").textContent = pendingLooks;
    // AWR-280: mirror the count onto the disclosure so the phone can hide the
    // "Pad look edits" control when there is nothing pending, yet keep it (and the
    // count) visible the moment there is unsaved work. Presentation only.
    const more = $("padMoreActions");
    if (more) more.dataset.count = String(pendingLooks);
  }
  function renderBanks() {
    const tabs = $("bankTabs");
    const banks = bankOrder.slice().filter(bank => {
      // AWR-265 FINAL: hide Legacy tab when the bank is gone / empty — never error.
      if (bank === "legacy_color_suffix") {
        return ((state.banks && state.banks.legacy_color_suffix) || []).length > 0;
      }
      return true;
    });
    if ((state.banks.other || []).length) banks.push("other");
    if (state.activeBank === "legacy_color_suffix" && !banks.includes("legacy_color_suffix")) {
      state.activeBank = "drafts";
    }
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
      const anyLooks = Object.values(state.banks).some((list) => (list || []).length);
      if (!anyLooks) {
        grid.innerHTML = `<div class="empty"><span class="panel-label">No looks yet</span><span>Accept a Lab draft into a phrase, or duplicate a look once you have one.</span></div>`;
      } else if (state.activeBank === "drafts") {
        grid.innerHTML = `<div class="empty"><span class="panel-label">No untagged looks</span><span>Accepted lab cues without a phrase tag land here. Open a phrase tab above, or tag a draft in Lab.</span></div>`;
      } else {
        grid.innerHTML = `<div class="empty"><span class="panel-label">Nothing in this shelf</span><span>Move or duplicate a look into this phrase tab, or open another tab that already has looks.</span></div>`;
      }
      return;
    }
    grid.innerHTML = names.map(name => cardHtml(name)).join("");
    grid.querySelectorAll(".look-card").forEach((card, i) => { card.style.animationDelay = `${Math.min(i * 20, 300)}ms`; });
    grid.querySelectorAll("[data-action]").forEach(btn => btn.addEventListener("click", onCardAction));
  }
  function cardHtml(name) {
    const look = state.config.config.looks[name] || {};
    const render = state.renderMap.get(look.scene_ref);
    const labScene = isLabScene(look.scene_ref);
    const bank = lookBank(name);
    const realtime = Boolean(render);
    // Lab cues play in the pad through the same renderer as the Lab live-fire.
    const playable = realtime || labScene;
    const engineColored = String(look.color_source || "engine") === "engine";
    const dirty = lookDirty(name);
    // AWR-278 B3: show the stored cue length as-is (server clamps it to >=1);
    // only fall back to 16 when a look has no cue length saved at all.
    const cueMeta = ((state.config.config._pad_meta || {}).looks || {})[name] || {};
    const cue = cueMeta.cue_beats != null ? cueMeta.cue_beats : 16;
    const playing = state.playingLook === name;
    // AWR-264 J2: human effect name leads; machine id is one small mono line.
    // AWR-278 A3: a lab cue's title follows its LOOK name (survives rename),
    // not the scene_ref draft id which stays frozen at accept time.
    const title = render ? render.label : (labScene ? human(name) : human(look.scene_ref || look.action || name));
    const colorMode = (render && render.slot_based) || (labScene && engineColored)
      ? "<span class='gradient-dot'></span>Uses show colors"
      : "<span class='fixed-dot'></span>Set colors";
    const colorway = inLegacyColorSuffixBank(name) ? colorwayChip(look) : "";
    const classBadge = labScene
      ? "<span class='badge'>Lab cue</span>"
      : (!realtime ? "<span class='badge'>Cloud scene</span>" : "");
    return `<article class="look-card ${esc(bank)} ${playing ? "playing" : ""}" style="--bank-color:${bankColors[bank]}">
      <div class="card-title"><span>${esc(title)}</span>${dirty ? "<span class='dirty-dot' title='Unsaved changes'>●</span>" : ""}</div>
      <div class="card-id mono">${esc(name)}</div>
      <div class="card-sub">${colorMode}${colorway ? ` · ${colorway}` : ""}</div>
      <div class="badge-row"><span class="badge">${cue} beats</span>${timingBadge(render)}${render && render.strobe ? "<span class='badge strobe'>⚡ strobe</span>" : ""}${classBadge}${playing ? "<span class='live-chip'>LIVE</span>" : ""}</div>
      <footer class="card-footer">
        <button type="button" class="primary" data-action="play" data-name="${esc(name)}" ${!playable ? "disabled title='Cloud scene - not previewable in the pad'" : ""}>▶ Play</button>
        <div class="icon-actions">
          <button type="button" class="icon" data-action="edit" data-name="${esc(name)}" aria-label="Edit" title="Edit">✎</button>
          <button type="button" class="icon" data-action="duplicate" data-name="${esc(name)}" aria-label="Duplicate" title="Duplicate">⧉</button>
          <button type="button" class="icon" data-action="rename" data-name="${esc(name)}" aria-label="Rename" title="Rename">Aa</button>
          <button type="button" class="icon" data-action="move" data-name="${esc(name)}" aria-label="Move" title="Move">⇄</button>
          <button type="button" class="icon delete" data-action="delete" data-name="${esc(name)}" aria-label="Delete" title="Delete">🗑</button>
        </div>
      </footer>
    </article>`;
  }
  async function saveCurrentEditor() {
    const e = state.editor;
    const body = {name: e.name, updated: e.updated || ""};
    for (const key of EDITOR_FIELDS) {
      body[key] = key === "locked_palette" ? (e.locked_palette || "") : e[key];
    }
    try {
      const res = await api.saveLook(body);
      if (!res.ok) throw new Error((res.errors || []).join("\n"));
      if (res.updated) e.updated = res.updated;
      state.cleanSnapshot = snapshotEditor();
      return true;
    } catch (err) {
      if (err && err.payload && err.payload.error === "stale_look") {
        const name = e.name;
        PadModal.show(
          "Look changed elsewhere",
          "Someone else edited this look — reload to get the latest, then re-apply",
          [
            {label: "Reload", className: "primary", run: async () => {
              await refresh();
              await openEditor(name, false);
            }},
            {label: "Cancel", className: "ghost", run: () => {}},
          ],
        );
        return false;
      }
      throw err;
    }
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
        promptModal("Duplicate look", NAME_HINT, {label:"New name", value: human(name), confirmText:"Duplicate", maxlength: 60, validate: (v) => String(v.value || "").trim() ? null : "Give the look a name"}, async (display) => {
          if (!display) { showError("Give the look a name"); return; }
          const newName = slugifyLookName(display, allLookNames());
          // AWR-278 B4: a config-validation failure returns {ok:false, errors:[…]}
          // with no `error` key, so pad-core doesn't throw — check res.ok before
          // opening an editor for a look that never got created.
          try { const res = await api.duplicate({source:name, new_name:newName}); if (!res.ok) throw new Error((res.errors || []).join("\n")); await refresh(); await openEditor(newName, false); }
          catch (err) { showError(err); }
        });
        return;
      }
      if (action === "rename") {
        promptModal("Rename look", NAME_HINT, {label:"New name", value: human(name), confirmText:"Rename", maxlength: 60, validate: (v) => String(v.value || "").trim() ? null : "Give the look a name"}, async (display) => {
          if (!display) { showError("Give the look a name"); return; }
          const newName = slugifyLookName(display, allLookNames().filter(n => n !== name));
          if (newName === name) return;
          // AWR-278 B4: same res.ok guard as duplicate — {ok:false, errors:[…]}
          // won't throw on its own, so don't openEditor a look that wasn't renamed.
          try { const res = await api.rename({name, new_name:newName}); if (!res.ok) throw new Error((res.errors || []).join("\n")); await refresh(); await openEditor(newName, false); }
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
    state.editor = {
      name,
      look,
      params: JSON.parse(JSON.stringify(look.params || {})),
      cue_beats: meta.cue_beats || 16,
      slot_fill: ((engine.slot_fill_strategy_by_look || {})[name] || "gradient_even"),
      mono_chance: ((engine.slot_mono_chance_by_look || {})[name] || 0),
      locked_palette: ((engine.locked_palette_by_look || {})[name] || ""),
      updated: meta.updated || "",
    };
    state.cleanSnapshot = snapshotEditor();
    renderEditor();
    $("editorDrawer").hidden = false;
    $("closeEditorBtn").focus();
    if (play) await playEditor(false);
  }
  function renderEditor() {
    const e = state.editor, render = state.renderMap.get(e.look.scene_ref);
    const labScene = isLabScene(e.look.scene_ref);
    // AWR-278 A3: lab cue editor title tracks the look name (rename-safe).
    $("editorTitle").textContent = render ? render.label : human(e.name);
    $("editorRegistry").textContent = e.name;
    renderEditorLive();
    renderCue();
    renderRendererSelect();
    $("rendererDescription").textContent = render
      ? (render.description || "")
      : (labScene ? "Lab cue — built in Template Lab. Change how it moves and its own colors in the Lab view; the pad plays it and sets its show colors." : "");
    $("brightnessInput").value = e.look.brightness ?? 100;
    $("brightnessOutput").textContent = `${$("brightnessInput").value}%`;
    $("strobeInput").checked = Boolean(e.look.allow_strobe);
    $("strobeLabel").textContent = $("strobeInput").checked ? "On" : "Off";
    $("lockedPaletteSelect").innerHTML = state.palettes.map(p => `<option value="${esc(p)}">${esc(titleCaseWords(p))}</option>`).join("");
    $("lockedPaletteSelect").value = e.locked_palette || state.palettes[0] || "";
    const locked = Boolean(e.locked_palette);
    $("lockedPaletteWrap").hidden = !locked;
    $("followColorBtn").classList.toggle("active", !locked);
    $("lockedPaletteBtn").classList.toggle("active", locked);
    const safety = !!((state.config.config.safety || {}).allow_strobe);
    $("strobeInput").disabled = !safety;
    $("strobeWarning").textContent = !safety ? "Strobe effects are switched off in safety settings." : (render && render.strobe && !e.look.allow_strobe ? "This effect flashes — turn on Strobe allowed before Play." : "");
    $("slotSection").hidden = !(render && render.slot_based);
    $("slotFillSelect").value = e.slot_fill;
    $("monoChanceInput").value = e.mono_chance;
    $("monoChanceOutput").textContent = e.mono_chance;
    // AWR-262 C3: Solid-chance only when Use set colors is active.
    $("monoChanceWrap").hidden = !(locked && e.slot_fill === "random_with_mono_chance");
    if (labScene) renderLabCueControls();
    else renderControls(render);
    $("loopHint").textContent = `Loop is ${$("loopToggle").checked ? "on" : "off"} (session)`;
    setDirty();
  }
  // Lab cues have no pad-editable motion controls (their motion + colors are
  // authored in Template Lab). Show the saved settings read-only and point edits
  // at the Lab view — no new editing pipeline in the pad.
  function renderLabCueControls() {
    const basic = $("controlRows"), adv = $("advancedRows");
    adv.innerHTML = "";
    $("advancedDetails").hidden = true;
    const params = state.editor.params || {};
    const keys = Object.keys(params);
    const rows = keys.length
      ? keys.map(k => `<div class="control-row"><span class="control-label">${esc(titleCaseWords(k))}</span><span class="mono dim">${esc(JSON.stringify(params[k]))}</span></div>`).join("")
      : "<p class='dim'>No saved settings.</p>";
    basic.innerHTML = `<p class="dim">Change this cue's motion and colors in the <a href="/?view=lab">Lab view</a>. Brightness, strobe, and palette above still apply here.</p>${rows}`;
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
      // AWR-278 B3: respect the min=1. A typed 0 / blank / negative is not a real
      // cue length (it would never auto-stop) — fall back to the last good value.
      const typed = Number(ev.target.value);
      state.editor.cue_beats = Number.isFinite(typed) && typed >= 1
        ? typed
        : Math.max(1, Number(state.editor.cue_beats) || 16);
      renderCue(); setDirty(); liveUpdate();
    });
  }
  function renderRendererSelect() {
    const groups = {};
    for (const render of state.renders) (groups[render.group] ||= []).push(render);
    let html = Object.entries(groups).map(([group, renders]) => `<optgroup label="${esc(group)}">${renders.map(r => `<option value="${esc(r.name)}">${esc(r.label)}</option>`).join("")}</optgroup>`).join("");
    const sceneRef = state.editor.look.scene_ref;
    if (sceneRef && !state.renderMap.has(sceneRef)) {
      const label = isLabScene(sceneRef)
        ? `Lab cue — ${esc(labCueName(sceneRef))}`
        : `☁ ${esc(human(sceneRef))} — cloud scene (not previewable)`;
      html = `<option value="${esc(sceneRef)}" selected disabled>${label}</option>` + html;
    }
    $("rendererSelect").innerHTML = html;
    $("rendererSelect").value = sceneRef;
  }
  function renderControls(render) {
    const basic = $("controlRows"), adv = $("advancedRows");
    basic.innerHTML = ""; adv.innerHTML = "";
    if (!render) {
      $("advancedDetails").hidden = true;
      return;
    }
    // Engine-colored looks audition with palette-injected colors: badge
    // rgb-kind and color-signature rows. Color A/B literals only when
    // color_source=literal actually applies (AWR-262 C3).
    const colorSource = String((state.editor.look || {}).color_source || "engine");
    const engineColored = colorSource === "engine";
    const showLiteralAB = colorSource === "literal" || !(render && render.slot_based);
    for (const control of render.controls || []) {
      // Slot looks: Color A/B only when color_source=literal. Non-slot looks
      // keep their own rgb params (e.g. drop_strobe_colorway).
      if ((control.key === "color_a" || control.key === "color_b") && !showLiteralAB) {
        continue;
      }
      const badged = engineColored && (control.kind === "rgb" || Boolean(control.color_sig));
      (control.advanced ? adv : basic).insertAdjacentHTML("beforeend", controlRow(control, badged));
    }
    // AWR-262: Advanced motion disappears entirely when empty.
    $("advancedDetails").hidden = !adv.innerHTML;
    document.querySelectorAll("[data-param]").forEach(input => input.addEventListener("input", ev => {
      const key = ev.currentTarget.dataset.param;
      let value = ev.currentTarget.type === "checkbox" ? ev.currentTarget.checked : ev.currentTarget.value;
      if (ev.currentTarget.type === "number" || ev.currentTarget.type === "range") value = Number(value);
      if (ev.currentTarget.tagName === "SELECT" && ev.currentTarget.dataset.kind === "int-choice") {
        value = Number(value);
      }
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
    else if (c.kind === "choice") {
      const options = (c.choice_options && c.choice_options.length)
        ? c.choice_options
        : (c.choices || []).map((v, i) => ({value: v, label: `Style ${i + 1}`}));
      const intChoices = options.every(o => typeof o.value === "number" || /^-?\d+(\.\d+)?$/.test(String(o.value)));
      input = `<select data-param="${esc(c.key)}"${intChoices ? ' data-kind="int-choice"' : ""}>${options.map(o => {
        const selected = String(o.value) === String(value) ? "selected" : "";
        return `<option value="${esc(o.value)}" ${selected}>${esc(o.label)}</option>`;
      }).join("")}</select>`;
      const selectedOpt = options.find(o => String(o.value) === String(value));
      if (selectedOpt) outputText = isSet ? selectedOpt.label : (hasDefault ? selectedOpt.label : "auto");
    }
    else if (c.kind === "rgb") {
      const rgb = Array.isArray(value) && value.length === 3 ? value : [0, 0, 0];
      const hex = `#${rgb.map(v => Math.max(0, Math.min(255, Math.round(Number(v) || 0))).toString(16).padStart(2, "0")).join("")}`;
      input = `<span class="color-cell"><input data-param="${esc(c.key)}" type="color" value="${hex}"><span class="swatch-chip small" data-swatch-for="${esc(c.key)}" style="background:${hex}"></span></span>`;
      outputText = isSet ? hex : "auto";
    }
    else input = `<input data-param="${esc(c.key)}" type="number" min="${esc(c.min ?? "")}" max="${esc(c.max ?? "")}" step="${esc(c.step ?? 1)}" value="${esc(value)}">`;
    const tag = isSet ? "" : `<span class="default-tag">auto</span>`;
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
      {label:"Save and switch", className:"primary", run:async () => { if (!(await saveCurrentEditor())) return; await refresh(); await openEditor(name, play); }},
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
    confirmModal("The show is running the lights right now. Take control?", "The show side goes dark until you release.", "Take control", () => playEditor(true));
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
      html += `<p class="dim">To open it on another device on this Wi-Fi, restart the pad in LAN mode with the command below.</p>`;
      html += `<p class="mono" id="lanRestartCmd" style="user-select:all">python3 scripts/led_pad.py --host lan</p>`;
      html += `<p><button type="button" class="primary" id="copyLanCmdBtn">Copy command</button></p>`;
      html += `<p class="warn-text">Doing so exposes pad control to the whole network.</p>`;
    } else {
      html += `<p class="warn-text">No LAN address detected — check Wi-Fi.</p>`;
    }
    $("modalText").innerHTML = html;
    const copyBtn = document.getElementById("copyLanCmdBtn");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        const text = ($("lanRestartCmd") && $("lanRestartCmd").textContent) || "python3 scripts/led_pad.py --host lan";
        try {
          await navigator.clipboard.writeText(text);
          toast("Command copied");
        } catch (err) {
          showError(err);
        }
      });
    }
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
    $("ownershipPill").textContent = stateName === "bridge_owned" ? "The show is running the lights" : stateName === "pad_owned" ? "This pad is running the lights" : "Lights are free";
    $("ownershipPill").className = `pill ${stateName === "bridge_owned" ? "bridge" : stateName === "pad_owned" ? "pad" : ""}`;
    $("ownershipBtn").hidden = stateName === "free";
    $("ownershipBtn").textContent = stateName === "pad_owned" ? "Release" : "Take control";
    if (warning) {
      $("errorBanner").hidden = false;
      $("errorBanner").textContent = "Bridge reappeared - pad re-asserted control.";
      $("errorBanner").classList.add("warn-banner");
    } else if ($("errorBanner").classList.contains("warn-banner") && $("errorBanner").textContent !== RECONNECT_TEXT) {
      clearError();
    }
    if (changed) { renderCards(); renderEditorLive(); }
    if (window.PadConfigStale) window.PadConfigStale.render($("configStaleBanner"), rt.config_stale);
    // AWR-275: follow the live music's tempo when the bridge is fresh; when it
    // stops, the pad's manual Preview tempo is always editable again.
    const following = window.PadTempoMode ? window.PadTempoMode.render((rt || {}).playback) : false;
    if (!following) {
      $("bpmInput").disabled = false;
      document.querySelectorAll("[data-step]").forEach(btn => { btn.disabled = false; });
    }
  }
  // AWR-279 #7: the shell owns Escape (closes a modal FIRST, else calls the active
  // view's handler) so a dirty-editor "Discard?" confirm can't be instantly
  // re-closed by a sibling view's handler. Register the pad view's behavior; fall
  // back to a local handler only when there is no shell.
  function padEscape() {
    if (!$("editorDrawer").hidden) closeEditor(false);
  }
  if (document.body && document.body.dataset.shell === "lighting"
      && window.LightingShell && typeof window.LightingShell.registerEscape === "function") {
    window.LightingShell.registerEscape("pad", padEscape);
  } else {
    document.addEventListener("keydown", ev => {
      if (ev.key !== "Escape") return;
      if (PadModal.isOpen()) closeModal();
      else padEscape();
    });
  }
  $("bpmInput").addEventListener("change", ev => api.session({bpm:Number(ev.target.value)}).then(res => {
    // AWR-279 #10: reflect the server-clamped tempo and clear a stale invalid-bpm
    // banner once a valid value lands (leave the reconnect / ownership banners be).
    if (res && res.session && res.session.bpm != null) $("bpmInput").value = res.session.bpm;
    const banner = $("errorBanner");
    if (!banner.hidden && banner.textContent !== RECONNECT_TEXT && !banner.classList.contains("warn-banner")) clearError();
  }).catch(showError));
  document.querySelectorAll("[data-step]").forEach(btn => btn.addEventListener("click", () => {
    // Floor/cap client-side so the − button can't walk below the declared range.
    $("bpmInput").value = Math.max(60, Math.min(200, Number($("bpmInput").value || 128) + Number(btn.dataset.step)));
    $("bpmInput").dispatchEvent(new Event("change"));
  }));
  $("paletteSelect").addEventListener("change", ev => api.session({test_palette:ev.target.value}).catch(showError));
  $("loopToggle").addEventListener("change", ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); });
  $("stopBtn").addEventListener("click", () => api.emergencyStop().then(async () => {
    // AWR-271: shared STOP also clears Lab beat meter when Lab is mounted in-shell.
    if (window.LabEditor && typeof window.LabEditor.onEmergencyStop === "function") {
      window.LabEditor.onEmergencyStop();
    }
    await refresh();
    if (window.LabEditor && typeof window.LabEditor.updateRuntime === "function") {
      await window.LabEditor.updateRuntime();
    }
  }).catch(showError));
  $("ownershipBtn").addEventListener("click", async () => { try { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); if (window.LabEditor && window.LabEditor.updateRuntime) await window.LabEditor.updateRuntime(); } catch (err) { showError(err); } });

  $("qrBtn").addEventListener("click", openAccessModal);
  $("commitBtn").addEventListener("click", () => {
    const n = $("commitCount").textContent || "0";
    const staleNote = (state.config || {}).live_changed
      ? "\nSomeone changed the lighting file while you were editing — review before pushing, or use Undo all changes to reload."
      : "";
    confirmModal(
      "Push Pad look edits?",
      `This writes ${n} Pad look edit(s) into your lighting file. Your lights will use them at the next bridge start. Lab drafts are not touched.${staleNote}`,
      "Push pad edits",
      async () => {
        const res = await api.commit();
        if (!res.ok) throw new Error((res.errors || []).join("\n"));
        toast(res.restart_note || "Pad edits saved — your lights will use them at the next bridge start.");
        await refresh();
      },
    );
  });
  $("discardBtn").addEventListener("click", () => {
    // AWR-260 E: count from live dirty state at modal-open (editor + draft), not a stale DOM badge.
    const fromServer = ((state.config || {}).dirty || {}).looks || [];
    const names = new Set(Array.isArray(fromServer) ? fromServer : []);
    if (state.editor && snapshotEditor() !== state.cleanSnapshot) {
      names.add(state.editor.name);
    }
    const count = names.size;
    confirmModal(
      "Undo all Pad look edits?",
      `This throws away every unsaved Pad look edit across ${count} look(s) and reloads the lighting file. Looks already in the show stay as they are. Lab drafts are not touched.`,
      "Undo all changes",
      async () => { await api.discard(); await refresh(); },
    );
  });
  $("closeEditorBtn").addEventListener("click", () => closeEditor(false));
  $("cancelBtn").addEventListener("click", () => closeEditor(false));
  $("undoBtn").addEventListener("click", () => confirmModal("Undo editor changes", "Undo reverts this editor to the last saved or opened state.", "Undo", () => { const data = JSON.parse(state.cleanSnapshot); state.editor.look = data.look; state.editor.params = data.params; state.editor.cue_beats = data.cue_beats; state.editor.slot_fill = data.slot_fill; state.editor.mono_chance = data.mono_chance; state.editor.locked_palette = data.locked_palette || ""; renderEditor(); liveUpdate(); }));
  $("saveLookBtn").addEventListener("click", async () => { try { if (!(await saveCurrentEditor())) return; await refresh(); setDirty(); } catch (err) { showError(err); } });
  $("editorPlayBtn").addEventListener("click", () => playEditor(false));
  $("editorStopBtn").addEventListener("click", () => api.stop().then(refresh).catch(showError));
  $("rendererSelect").addEventListener("change", ev => {
    const select = ev.target;
    const previous = state.editor.look.scene_ref;
    const next = select.value;
    const render = state.renderMap.get(next);
    if (!render) return;
    const allowed = new Set((render.controls || []).map(c => c.key));
    const dropped = Object.keys(state.editor.params).filter(k => !allowed.has(k));
    const applySwitch = () => {
      state.editor.look.scene_ref = next;
      state.editor.params = Object.fromEntries(Object.entries(state.editor.params).filter(([k]) => allowed.has(k)));
      renderEditor();
      setDirty();
      liveUpdate();
    };
    if (!dropped.length) {
      applySwitch();
      return;
    }
    const labels = dropped.map(key => {
      const control = (state.renderMap.get(previous)?.controls || []).find(c => c.key === key);
      return control ? control.label : key;
    });
    // Revert the select until the operator confirms (AWR-262 C13).
    select.value = previous;
    confirmModal(
      "Switch effect?",
      `These settings don't apply to ${render.label} and will be dropped: ${labels.join(", ")}.`,
      "Switch",
      () => {
        select.value = next;
        applySwitch();
      },
    );
  });
  $("followColorBtn").addEventListener("click", () => { state.editor.locked_palette = ""; renderEditor(); setDirty(); liveUpdate(); });
  $("lockedPaletteBtn").addEventListener("click", () => { state.editor.locked_palette = state.editor.locked_palette || state.palettes[0] || ""; renderEditor(); setDirty(); liveUpdate(); });
  $("lockedPaletteSelect").addEventListener("change", ev => { state.editor.locked_palette = ev.target.value; setDirty(); liveUpdate(); });
  $("brightnessInput").addEventListener("input", ev => { state.editor.look.brightness = Number(ev.target.value); $("brightnessOutput").textContent = `${ev.target.value}%`; setDirty(); });
  $("strobeInput").addEventListener("change", ev => { state.editor.look.allow_strobe = ev.target.checked; $("strobeLabel").textContent = ev.target.checked ? "On" : "Off"; setDirty(); });
  $("slotFillSelect").addEventListener("change", ev => {
    state.editor.slot_fill = ev.target.value;
    const locked = Boolean(state.editor.locked_palette);
    $("monoChanceWrap").hidden = !(locked && state.editor.slot_fill === "random_with_mono_chance");
    setDirty();
    liveUpdate();
  });
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
