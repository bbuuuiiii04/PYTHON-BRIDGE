(function () {
  const api = window.LedPadApi;
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const state = {entries: [], current: null, playingLook: ""};

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
    $("draftList").innerHTML = state.entries.length ? state.entries.map(e => `
      <button type="button" class="lab-row ${state.current && state.current.name === e.name ? "active" : ""}" data-name="${esc(e.name)}">
        <span>${esc(e.name)}</span>
        <span class="status-pill ${esc(e.status)}">${esc(e.status)}</span>
        <span class="dim">${esc((e.updated || "").slice(0, 10))}</span>
      </button>`).join("") : `<div class="empty"><span class="panel-label">No drafts</span><span>Create one with New.</span></div>`;
    $("draftList").querySelectorAll("button").forEach(btn => btn.onclick = () => selectDraft(btn.dataset.name));
  }

  function selectDraft(name) {
    stopPreview();
    state.current = state.entries.find(e => e.name === name) || null;
    renderList();
    renderDetail();
  }

  function renderDetail() {
    const e = state.current;
    const disabled = !e;
    for (const id of ["briefInput", "notesInput", "paramsInput", "saveDraftBtn", "playDraftBtn", "acceptBtn", "rejectBtn", "previewBtn"]) $(id).disabled = disabled;
    if (!e) return;
    $("draftTitle").textContent = e.name;
    $("draftFn").textContent = `${e.kind} · ${e.fn}`;
    $("briefInput").value = e.brief || "";
    $("notesInput").value = e.notes || "";
    $("kindText").textContent = `${e.kind} · ${e.fn}`;
    $("statusText").textContent = e.status;
    $("statusText").className = `status-pill ${e.status}`;
    $("paramsInput").value = JSON.stringify(e.params || {}, null, 2);
    renderCue();
    renderLive();
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
      const mine = labScene(state.current.name);
      if (state.playingLook && state.playingLook.startsWith("lab_") && state.playingLook !== mine) {
        const sw = await api.labSwitch({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}")});
        if (sw.ok) { await updateRuntime(); return; }
      }
      const res = await api.labPlay({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}"), cue_beats:cue(), takeover});
      if (!res.ok && res.error === "ownership_required") {
        PadModal.confirm("The bridge owns the LEDs right now. Take over?", "LEDs go dark on the bridge side until you release.", "Take over", () => play(true));
        return;
      }
      if (!res.ok) throw new Error(res.error || "lab play failed");
      await updateRuntime();
    } catch (err) { showError(err); }
  }

  async function reloadCode() {
    const res = await api.labReload();
    $("traceText").textContent = res.traceback || res.error || `Loaded: ${(res.effects || []).join(", ")}`;
    $("tracePanel").open = !res.ok;
    if (!res.ok) showError(res.error);
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
    await save();
    const res = await api.labPreview({name: state.current.name});
    if (!res.ok) {
      $("traceText").textContent = res.traceback || res.error || "preview failed";
      $("tracePanel").open = true;
      throw new Error(res.error || "preview failed");
    }
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
  $("paramsInput").onblur = () => { try { JSON.parse($("paramsInput").value || "{}"); clearError(); } catch (err) { showError(err); } };
  let applyTimer = 0;
  $("paramsInput").oninput = () => {
    clearTimeout(applyTimer);
    applyTimer = setTimeout(async () => {
      if (!state.current || state.playingLook !== labScene(state.current.name)) return;
      let params;
      try { params = JSON.parse($("paramsInput").value || "{}"); } catch { return; }
      try {
        const res = await api.labSave(currentPayload());
        state.current = res.entry;
        await api.labUpdate({name: state.current.name, params});
        clearError();
      } catch (err) { showError(err); }
    }, 400);
  };
  $("bpmInput").onchange = ev => api.session({bpm:Number(ev.target.value)}).catch(showError);
  document.querySelectorAll("[data-step]").forEach(btn => btn.onclick = () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); });
  $("paletteSelect").onchange = ev => api.session({test_palette:ev.target.value}).catch(showError);
  $("loopToggle").onchange = ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); };
  $("stopBtn").onclick = () => api.emergencyStop().then(updateRuntime).catch(showError);
  $("ownershipBtn").onclick = async () => { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); };
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && PadModal.isOpen()) PadModal.close(); });
  setInterval(updateRuntime, 2000);
  refresh().catch(showError);
}());
