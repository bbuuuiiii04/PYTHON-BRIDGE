(function () {
  const api = window.LedPadApi;
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const state = {entries: [], current: null, playingLook: "", showRejected: false};
  // Raw tracebacks are agent-facing: render the panel only with ?dev=1.
  const DEV = new URLSearchParams(location.search).get("dev") === "1";

  function showError(err) {
    $("errorBanner").hidden = false;
    $("errorBanner").textContent = err && err.message ? err.message : String(err);
  }
  PadModal.setErrorHandler(showError);
  function clearError() { $("errorBanner").hidden = true; $("errorBanner").textContent = ""; }
  function labScene(name) { return `lab_${name}`; }
  function cue() { return Number(($("cueCustom") || {}).value || (state.current || {}).cue_beats || 16); }

  async function refresh() {
    clearError();
    const [cfg, palettes, lab] = await Promise.all([api.config(), api.palettes(), api.labList()]);
    state.entries = lab.entries || [];
    renderSession(cfg.config._pad_meta.ui, palettes.palettes || []);
    renderList();
    if (!state.current && state.entries[0]) selectDraft(state.entries[0].name);
    else if (state.current) {
      const fresh = state.entries.find(e => e.name === state.current.name);
      if (fresh) selectDraft(fresh.name);
    }
    await updateRuntime();
  }

  function renderSession(ui, palettes) {
    $("bpmInput").value = ui.bpm || 128;
    $("paletteSelect").innerHTML = palettes.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
    $("paletteSelect").value = ui.test_palette || palettes[0] || "";
    $("loopToggle").checked = ui.loop !== false;
    $("loopLabel").textContent = $("loopToggle").checked ? "On" : "Off";
  }

  function renderList() {
    const archived = (e) => e.status === "rejected" || e.status === "promoted";
    $("rejectedToggle").textContent = `Archived (${state.entries.filter(archived).length})`;
    const visible = state.entries.filter(e => state.showRejected || !archived(e));
    $("draftList").innerHTML = visible.length ? visible.map(e => `
      <button type="button" class="lab-row ${state.current && state.current.name === e.name ? "active" : ""}" data-name="${esc(e.name)}">
        <span>${esc(e.name)}${e.production_collision && e.status !== "promoted" ? ` <span class="prod-chip">in production</span>` : ""}</span>
        <span class="status-pill ${esc(e.status)}">${esc(e.status)}</span>
        <span class="dim">${esc((e.updated || "").slice(0, 10))}</span>
      </button>`).join("") : `<div class="empty"><span class="panel-label">No drafts</span><span>Create one with New.</span></div>`;
    $("draftList").querySelectorAll("button").forEach(btn => btn.onclick = () => selectDraft(btn.dataset.name));
  }

  function selectDraft(name) {
    stopPreview();
    renderSwatches(null);
    state.current = state.entries.find(e => e.name === name) || null;
    renderList();
    renderDetail();
  }

  function renderDetail() {
    const e = state.current;
    const disabled = !e;
    for (const id of ["briefInput", "notesInput", "paramsInput", "saveDraftBtn", "playDraftBtn", "acceptBtn", "rejectBtn", "previewBtn", "deleteBtn"]) $(id).disabled = disabled;
    if (!e) { $("paramControls").innerHTML = ""; $("collisionBanner").hidden = true; return; }
    $("collisionBanner").hidden = !(e.production_collision && e.status !== "promoted");
    $("draftTitle").textContent = e.name;
    $("draftFn").textContent = `${e.kind} · ${e.fn}`;
    $("briefInput").value = e.brief || "";
    $("notesInput").value = e.notes || "";
    $("kindText").textContent = `${e.kind} · ${e.fn}`;
    $("statusText").textContent = e.status;
    $("statusText").className = `status-pill ${e.status}`;
    $("paramsInput").value = JSON.stringify(e.params || {}, null, 2);
    renderParamControls();
    renderCue();
    renderLive();
    setDirty();
  }

  // Dirty chip (pad-ui.js setDirty pattern): editor params vs saved entry params.
  function setDirty() {
    if (!state.current) { $("labDirtyChip").textContent = ""; return; }
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch { params = null; }
    const dirty = params === null || JSON.stringify(params) !== JSON.stringify(state.current.params || {});
    $("labDirtyChip").textContent = dirty ? "Unsaved tweaks" : "Saved";
    $("labDirtyChip").className = dirty ? "warn-text" : "dim";
  }

  function renderCue() {
    const values = [4, 8, 16, 32];
    const current = Number((state.current || {}).cue_beats || 16);
    document.querySelector(".cue-group").innerHTML = values.map(v => `<button type="button" class="${current === v ? "active" : ""}" data-cue="${v}">${v}</button>`).join("") + `<input id="cueCustom" type="number" min="1" step="1" value="${esc(current)}" aria-label="Custom cue length">`;
    document.querySelectorAll("[data-cue]").forEach(btn => btn.onclick = () => { $("cueCustom").value = btn.dataset.cue; });
  }

  function currentPayload() {
    const params = JSON.parse($("paramsInput").value || "{}");
    return {...state.current, brief:$("briefInput").value, notes:$("notesInput").value, params, cue_beats:cue()};
  }

  async function save() {
    if (!state.current) return;
    const res = await api.labSave(currentPayload());
    state.current = res.entry;
    await refresh();
  }

  async function play(takeover) {
    if (!state.current) return;
    try {
      await save();
    } catch (err) {
      showError(`Save failed: ${(err && err.message) || err}`);
      return;
    }
    try {
      const mine = labScene(state.current.name);
      if (state.playingLook && state.playingLook.startsWith("lab_") && state.playingLook !== mine) {
        const sw = await api.labSwitch({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}")});
        if (sw.ok) {
          renderSwatches(sw.spec && sw.spec.params && sw.spec.params.slot_colors);
          await updateRuntime();
          return;
        }
      }
      const res = await api.labPlay({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}"), cue_beats:cue(), takeover});
      if (!res.ok && res.error === "ownership_required") {
        PadModal.confirm("The bridge owns the LEDs right now. Take over?", "LEDs go dark on the bridge side until you release.", "Take over", () => play(true));
        return;
      }
      if (!res.ok) throw new Error(res.error || "lab play failed");
      renderSwatches(res.spec && res.spec.params && res.spec.params.slot_colors);
      await updateRuntime();
    } catch (err) { showError(err); }
  }

  async function reloadCode() {
    const res = await api.labReload();
    $("traceText").textContent = res.traceback || res.error || `Loaded: ${(res.effects || []).join(", ")}`;
    if (!res.ok) {
      showError(`Your effect code failed to load: ${String(res.error || "").split("\n")[0]}`);
      if (DEV) $("tracePanel").open = true;
    } else {
      $("tracePanel").open = false;
    }
  }

  async function updateRuntime() {
    const rt = await api.runtime();
    const ownership = (rt.ownership || {}).state || "free";
    state.playingLook = (rt.playback || {}).playing ? ((rt.playback || {}).playing_look || "") : "";
    $("ownershipPill").textContent = ownership === "bridge_owned" ? "Bridge owns LEDs" : ownership === "pad_owned" ? "Pad owns LEDs" : "Free";
    $("ownershipPill").className = `pill ${ownership === "bridge_owned" ? "bridge" : ownership === "pad_owned" ? "pad" : ""}`;
    $("ownershipBtn").hidden = ownership === "free";
    $("ownershipBtn").textContent = ownership === "pad_owned" ? "Release" : "Take over";
    renderLive();
  }

  function renderLive() {
    $("labLive").hidden = !(state.current && state.playingLook === labScene(state.current.name));
    $("playDraftBtn").textContent =
      state.current && state.playingLook && state.playingLook.startsWith("lab_") &&
      state.playingLook !== labScene(state.current.name) ? "⇄ Switch" : "▶ Play";
  }

  let applyTimer = 0;
  function queueAutoApply() {
    clearTimeout(applyTimer);
    applyTimer = setTimeout(async () => {
      if (!state.current || state.playingLook !== labScene(state.current.name)) return;
      let params;
      try { params = JSON.parse($("paramsInput").value || "{}"); } catch { showError("Params JSON invalid — live apply paused"); return; }
      try {
        const res = await api.labSave(currentPayload());
        state.current = res.entry;
        await api.labUpdate({name: state.current.name, params});
        clearError();
      } catch (err) { showError(err); }
    }, 400);
  }

  function hexByte(v) { return Math.max(0, Math.min(255, Math.round(Number(v) || 0))).toString(16).padStart(2, "0"); }
  function rgbHex(r, g, b) { return `#${hexByte(r)}${hexByte(g)}${hexByte(b)}`; }

  function renderParamControls() {
    const specs = (state.current && (state.current.effective_param_specs || state.current.param_specs)) || {};
    const conflicts = (state.current && state.current.spec_conflicts) || [];
    const container = $("paramControls");
    const keys = Object.keys(specs);
    if (!keys.length) { container.innerHTML = ""; return; }
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch { params = {}; }
    // Slot-kind drafts audition with palette-injected colors: badge color rows.
    const slotKind = Boolean(state.current && state.current.kind === "slot");
    const badge = `<span class="regime-badge">palette overrides this in the room</span>`;
    // Complete <base>_r/_g/_b slider triplets collapse into one color picker.
    const triplets = {};
    for (const key of keys) {
      const m = /^(.+)_(r|g|b)$/.exec(key);
      if (m && specs[key].kind !== "toggle") (triplets[m[1]] ||= {})[m[2]] = key;
    }
    const bases = Object.keys(triplets).filter(b => triplets[b].r && triplets[b].g && triplets[b].b);
    const tripletKey = new Set(bases.flatMap(b => [triplets[b].r, triplets[b].g, triplets[b].b]));
    const renderedBases = new Set();
    const rows = [];
    if (conflicts.length) rows.push(`<div class="dim">Slider ranges updated from the production controls table</div>`);
    for (const key of keys) {
      const spec = specs[key];
      const m = /^(.+)_(r|g|b)$/.exec(key);
      if (m && tripletKey.has(key)) {
        const base = m[1];
        if (renderedBases.has(base)) continue;
        renderedBases.add(base);
        const t = triplets[base];
        const chan = (c) => params[t[c]] === undefined ? Number(specs[t[c]].min || 0) : Number(params[t[c]]);
        const hex = rgbHex(chan("r"), chan("g"), chan("b"));
        const label = base.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
        rows.push(`<label class="param-row param-color${slotKind ? " palette-fed" : ""}"><span>${esc(label)}${slotKind ? badge : ""}</span><input type="color" data-color-base="${esc(base)}" value="${hex}"><span class="swatch-chip small" data-swatch="${esc(base)}" style="background:${hex}"></span></label>`);
        continue;
      }
      if (spec.kind === "toggle") {
        const checked = params[key] === undefined ? false : Boolean(params[key]);
        rows.push(`<label class="param-row param-toggle"><span>${esc(spec.label)}</span><input type="checkbox" data-param="${esc(key)}" data-kind="toggle" ${checked ? "checked" : ""}></label>`);
        continue;
      }
      const raw = params[key] === undefined ? spec.min : Number(params[key]);
      const colorish = Boolean(m); // incomplete triplet channel stays a slider
      rows.push(`<label class="param-row param-slider${slotKind && colorish ? " palette-fed" : ""}"><span>${esc(spec.label)}${slotKind && colorish ? badge : ""}</span><input type="range" data-param="${esc(key)}" data-kind="slider" min="${esc(spec.min)}" max="${esc(spec.max)}" step="${esc(spec.step)}" value="${esc(raw)}"><output>${esc(raw)}</output></label>`);
    }
    container.innerHTML = rows.join("");
    container.querySelectorAll("[data-param]").forEach(input => { input.oninput = () => applyParamControl(input); });
    container.querySelectorAll("[data-color-base]").forEach(input => { input.oninput = () => applyColorControl(input, triplets[input.dataset.colorBase]); });
  }

  function applyColorControl(input, channels) {
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch (err) { showError(err); return; }
    const hex = input.value;
    params[channels.r] = parseInt(hex.slice(1, 3), 16);
    params[channels.g] = parseInt(hex.slice(3, 5), 16);
    params[channels.b] = parseInt(hex.slice(5, 7), 16);
    const chip = input.closest(".param-row").querySelector("[data-swatch]");
    if (chip) chip.style.background = hex;
    $("paramsInput").value = JSON.stringify(params, null, 2);
    setDirty();
    queueAutoApply();
  }

  function applyParamControl(input) {
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch (err) { showError(err); return; }
    const key = input.dataset.param;
    if (input.dataset.kind === "toggle") {
      params[key] = input.checked;
    } else {
      params[key] = parseFloat(input.value);
      const output = input.closest(".param-row").querySelector("output");
      if (output) output.textContent = input.value;
    }
    $("paramsInput").value = JSON.stringify(params, null, 2);
    setDirty();
    queueAutoApply();
  }

  function renderSwatches(slotColors) {
    const container = $("slotSwatches");
    if (!Array.isArray(slotColors) || !slotColors.length) { container.innerHTML = ""; return; }
    container.innerHTML = slotColors.map((rgb, i) => {
      const [r, g, b] = Array.isArray(rgb) ? rgb : [0, 0, 0];
      const label = i === 5 ? "white" : "";
      return `<div class="swatch-chip" style="background: rgb(${Number(r) || 0},${Number(g) || 0},${Number(b) || 0})" title="slot ${i}${label ? " (" + label + ")" : ""}">${esc(label)}</div>`;
    }).join("");
  }

  const preview = {frames: [], fps: 40, raf: 0};
  function stopPreview() {
    cancelAnimationFrame(preview.raf);
    preview.frames = [];
    const canvas = $("previewStrip");
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  }
  async function previewDraft() {
    if (!state.current) return;
    stopPreview();
    // No implicit save: preview posts the current editor params directly.
    const params = JSON.parse($("paramsInput").value || "{}");
    const res = await api.labPreview({name: state.current.name, params});
    if (!res.ok) {
      $("traceText").textContent = res.traceback || res.error || "preview failed";
      if (DEV) $("tracePanel").open = true;
      throw new Error(`Your effect code failed to load: ${String(res.error || "preview failed").split("\n")[0]}`);
    }
    renderSwatches(res.slot_colors);
    const canvas = $("previewStrip");
    canvas.width = canvas.clientWidth || 600;
    const ctx = canvas.getContext("2d");
    preview.frames = res.frames;
    preview.fps = res.fps;
    let start;
    const step = (ts) => {
      if (!preview.frames.length) return;
      if (start === undefined) start = ts;
      const frame = preview.frames[Math.floor((ts - start) / 1000 * preview.fps) % preview.frames.length];
      const w = canvas.width / frame.length;
      frame.forEach((rgb, i) => {
        ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
        ctx.fillRect(i * w, 0, Math.ceil(w), canvas.height);
      });
      preview.raf = requestAnimationFrame(step);
    };
    preview.raf = requestAnimationFrame(step);
  }
  $("previewBtn").onclick = async () => {
    $("previewBtn").disabled = true;
    try { await previewDraft(); } catch (err) { showError(err); } finally { $("previewBtn").disabled = false; }
  };

  $("newDraftBtn").onclick = () => {
    PadModal.prompt("New draft", "", {label:"Draft name", confirmText:"Create"}, async (name) => {
      if (!name) return;
      await api.labSave({name, kind:"slot", fn:name, params:{}, cue_beats:16, brief:"", notes:"", status:"iterating"});
      await refresh();
      selectDraft(name);
    });
  };
  $("saveDraftBtn").onclick = () => save().catch(showError);
  $("playDraftBtn").onclick = () => play(false);
  $("stopDraftBtn").onclick = () => api.stop().then(updateRuntime).catch(showError);
  $("reloadBtn").onclick = () => reloadCode().catch(showError);
  $("acceptBtn").onclick = () => state.current && api.labAccept(state.current.name).then(refresh).catch(showError);
  $("rejectBtn").onclick = () => state.current && api.labReject(state.current.name).then(refresh).catch(showError);
  $("rejectedToggle").onclick = () => { state.showRejected = !state.showRejected; renderList(); };
  $("archiveBtn").onclick = () => state.current && PadModal.confirm(`Archive draft ${state.current.name}?`, "Marks it promoted and files it under Archived. The drafts.json entry stays for the record.", "Archive", async () => {
    await api.labArchive({name: state.current.name});
    await refresh();
  });
  $("deleteBtn").onclick = () => state.current && PadModal.confirm(`Delete draft ${state.current.name}?`, "Removes the drafts.json entry. Its function in effects_lab.py stays — clean that up separately.", "Delete", async () => {
    try {
      await api.labDelete({name: state.current.name});
    } catch (err) {
      if ((err && err.message) === "stop_playback_first") { showError("Stop playback first."); return; }
      throw err;
    }
    state.current = null;
    await refresh();
  });
  $("paramsInput").onblur = () => { try { JSON.parse($("paramsInput").value || "{}"); clearError(); } catch (err) { showError(err); } };
  $("paramsInput").oninput = () => { setDirty(); queueAutoApply(); };
  $("bpmInput").onchange = ev => api.session({bpm:Number(ev.target.value)}).catch(showError);
  document.querySelectorAll("[data-step]").forEach(btn => btn.onclick = () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); });
  $("paletteSelect").onchange = ev => api.session({test_palette:ev.target.value}).catch(showError);
  $("loopToggle").onchange = ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); };
  $("stopBtn").onclick = () => api.emergencyStop().then(updateRuntime).catch(showError);
  $("ownershipBtn").onclick = async () => { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); };
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && PadModal.isOpen()) PadModal.close(); });
  $("tracePanel").hidden = !DEV;
  const RECONNECT_TEXT = "Pad server unreachable — reconnecting…";
  PadHealth.start({
    poll: updateRuntime,
    refresh,
    banner: (down) => {
      if (down) {
        $("errorBanner").hidden = false;
        $("errorBanner").textContent = RECONNECT_TEXT;
      } else if ($("errorBanner").textContent === RECONNECT_TEXT) {
        clearError();
      }
    },
  });
  refresh().catch(showError);
}());
