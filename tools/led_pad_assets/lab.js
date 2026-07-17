(function () {
  const api = window.LedPadApi;
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const ROLE_ABBREV = {ambient:"Amb", groove:"Grv", buildup:"Bld", pre_drop:"Pre", drop:"Drp", post_drop:"Pst", breakdown:"Brk", utility:"Utl"};
  const ROLE_FULL = {ambient:"Ambient", groove:"Groove", buildup:"Buildup", pre_drop:"Pre-drop", drop:"Drop", post_drop:"Post-drop", breakdown:"Breakdown", utility:"Utility"};
  const state = {
    entries: [],
    current: null,
    editorMemory: {}, // per-draft unsaved editor fields (session-local; never auto-written)
    playingLook: "",
    showRejected: false, // kept for archived semantics; driven by Rejected chip
    filters: {search: "", iterating: true, accepted: false, rejected: false, phrase: "all"},
    drawerOpen: false,
    health: {
      serverOkAt: 0,
      serverFailAt: 0,
      labOk: null, // null unknown, true/false
      labTrace: "",
      playingBeat: null,
      playingName: "",
    },
  };
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
  function timingLabel(mode) { return ({beat:"Locks to the beat", mixed:"Beat + clock", time:"Runs on a clock", static:"Still", unknown:"Timing unknown"})[mode] || "Timing unknown"; }
  function roleOf(entry) { return String((entry && entry.target_role) || ""); }
  function phraseChip(role) {
    if (!role) return `<span class="lab-phrase-chip untagged" title="Untagged">—</span>`;
    const abbr = ROLE_ABBREV[role] || "—";
    const full = ROLE_FULL[role] || role;
    return `<span class="lab-phrase-chip role-${esc(role)}" title="${esc(full)}">${abbr}</span>`;
  }
  function relativeDate(iso) {
    if (!iso) return "—";
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return "—";
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (sec < 60) return `${sec}s`;
    const min = Math.round(sec / 60);
    if (min < 60) return `${min}m`;
    const hr = Math.round(min / 60);
    if (hr < 48) return `${hr}h`;
    const days = Math.round(hr / 24);
    return `${days}d`;
  }
  function statusDot(status) {
    return `<span class="lab-status-dot ${esc(status)}" title="${esc(status)}"></span>`;
  }

  // Pure beat → bar/beat-in-bar (frame 0 = bar 1 beat 1). Shared by preview + live.
  function beatParts(beat) {
    const i = Math.max(0, Math.floor(beat));
    return { integer: i, bar: Math.floor(i / 4) + 1, beatInBar: (i % 4) + 1, downbeat: i % 4 === 0 };
  }

  const beatUI = {
    mode: "off", // "preview" | "live" | "off"
    bpm: 128,
    fps: 40,
    frameIndex: 0,
    polledBeat: 0,
    pollTime: 0,
    clickOn: false,
    audioCtx: null,
    lastClick: -1,
    flashTimer: 0,
    raf: 0,
  };

  function currentBeat() {
    if (beatUI.mode === "preview") return beatUI.frameIndex * beatUI.bpm / (60 * beatUI.fps);
    if (beatUI.mode === "live") return beatUI.polledBeat + (performance.now() - beatUI.pollTime) * beatUI.bpm / 60000;
    return null;
  }

  function ensureAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!beatUI.audioCtx) beatUI.audioCtx = new Ctx();
    if (beatUI.audioCtx.state === "suspended") beatUI.audioCtx.resume();
    return beatUI.audioCtx;
  }

  function clickBlip(downbeat) {
    const ctx = ensureAudio();
    if (!ctx) return;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "square";
    osc.frequency.value = downbeat ? 1400 : 880;
    gain.gain.setValueAtTime(downbeat ? 0.12 : 0.06, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.05);
  }

  function stopClicks() { beatUI.lastClick = -1; }

  function renderBeatMeter() {
    const beat = currentBeat();
    const meter = $("beatMeter");
    const dot = $("beatDot");
    if (beat == null) {
      meter.hidden = true;
      dot.className = "beat-dot";
      $("beatCounter").textContent = "—";
      $("beatHonesty").textContent = "";
      return;
    }
    meter.hidden = false;
    const p = beatParts(beat);
    if (beatUI.mode === "preview") {
      $("beatCounter").textContent = `bar ${p.bar} · beat ${p.beatInBar}`;
      $("beatHonesty").textContent = "click: exact";
    } else {
      $("beatCounter").textContent = `beat phase (server) · ${p.beatInBar}/4`;
      $("beatHonesty").textContent = "click: synced to server clock (± poll jitter)";
    }
    if (p.integer !== beatUI._flashAt) {
      beatUI._flashAt = p.integer;
      clearTimeout(beatUI.flashTimer);
      dot.className = "beat-dot flash" + (p.downbeat ? " downbeat" : "");
      beatUI.flashTimer = setTimeout(() => { dot.className = "beat-dot"; }, 80);
      if (beatUI.clickOn && p.integer !== beatUI.lastClick && !document.hidden) {
        beatUI.lastClick = p.integer;
        clickBlip(p.downbeat);
      }
    }
  }

  function beatLoop() {
    renderBeatMeter();
    if (beatUI.mode !== "off") beatUI.raf = requestAnimationFrame(beatLoop);
  }

  function setBeatMode(mode, opts) {
    cancelAnimationFrame(beatUI.raf);
    beatUI.mode = mode;
    if (opts) Object.assign(beatUI, opts);
    if (mode === "off") {
      stopClicks();
      renderBeatMeter();
      return;
    }
    beatUI._flashAt = -1;
    beatUI.raf = requestAnimationFrame(beatLoop);
  }

  function renderHealth() {
    const now = performance.now();
    const ageMs = state.health.serverOkAt ? now - state.health.serverOkAt : Infinity;
    const serverOk = Number.isFinite(ageMs) && ageMs < 3000;
    const serverEl = $("healthServer");
    const serverDot = serverEl.querySelector(".lab-health-dot");
    serverDot.dataset.state = serverOk ? "ok" : "bad";
    const ago = Number.isFinite(ageMs) && ageMs < 1e12 ? Math.max(0, Math.round(ageMs / 1000)) : "?";
    let label = serverEl.querySelector(".lab-health-label");
    if (!label) {
      label = document.createElement("span");
      label.className = "lab-health-label";
      serverEl.appendChild(label);
    }
    label.textContent = serverOk ? "ok" : `stale (${ago}s)`;
    serverEl.title = "Server: green ok (<3s), red stale/error";

    const labEl = $("healthLab");
    const labDot = labEl.querySelector(".lab-health-dot");
    const labLabel = labEl.querySelector(".lab-health-label");
    if (state.health.labOk === true) {
      labDot.dataset.state = "ok";
      if (labLabel) labLabel.textContent = "loaded ✓";
    } else if (state.health.labOk === false) {
      labDot.dataset.state = "bad";
      if (labLabel) labLabel.textContent = "load failed";
    } else {
      labDot.dataset.state = "unknown";
      if (labLabel) labLabel.textContent = "not loaded yet";
    }
    labEl.title = "Lab code: amber not loaded yet, green loaded ✓, red load failed (click for traceback)";

    const pbEl = $("healthPlayback");
    const pbDot = pbEl.querySelector(".lab-health-dot");
    const playing = Boolean(state.health.playingName);
    pbDot.dataset.state = playing ? "ok" : "idle";
    const beat = state.health.playingBeat;
    const playName = playing ? state.health.playingName.replace(/^lab_/, "") : "";
    $("healthPlaybackText").textContent = playing
      ? `playing ${playName}${typeof beat === "number" ? ` · beat ${Math.floor(beat)}` : ""}`
      : "idle";
    pbEl.title = playing ? `Playback: playing ${playName}` : "Playback: green playing <name>, gray idle";
  }

  async function refresh() {
    clearError();
    // AWR-258: stash dirty fields before list rebuild (PadHealth reconnect).
    if (state.current && isEditorDirty()) stashEditor();
    const [cfg, palettes, lab] = await Promise.all([api.config(), api.palettes(), api.labList()]);
    state.entries = lab.entries || [];
    renderSession(cfg.config._pad_meta.ui, palettes.palettes || []);
    renderList();
    if (!state.current) {
      const firstVisible = state.entries.find(matchesFilters) || state.entries[0];
      if (firstVisible) selectDraft(firstVisible.name);
      else {
        $("draftTitle").textContent = state.entries.length
          ? "No drafts match — clear filters or press New."
          : "No drafts yet — press New to make one.";
      }
    } else {
      const fresh = state.entries.find(e => e.name === state.current.name);
      if (fresh) selectDraft(fresh.name);
    }
    await updateRuntime();
  }

  function renderSession(ui, palettes) {
    $("bpmInput").value = ui.bpm || 128;
    $("paletteSelect").innerHTML = palettes.map(p => `<option value="${esc(p)}">${esc(String(p).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase()))}</option>`).join("");
    $("paletteSelect").value = ui.test_palette || palettes[0] || "";
    $("loopToggle").checked = ui.loop !== false;
    $("loopLabel").textContent = $("loopToggle").checked ? "On" : "Off";
  }

  function labDraftSearchHit(entry, rawQuery) {
    // AWR-251 residue: plain case-insensitive SUBSTRING only — never subsequence/fuzzy.
    const q = String(rawQuery || "").trim().toLowerCase();
    if (!q) return true;
    const name = String((entry && entry.name) || "").toLowerCase();
    const brief = String((entry && entry.brief) || "").toLowerCase();
    const notes = String((entry && entry.notes) || "").toLowerCase();
    return name.includes(q) || brief.includes(q) || notes.includes(q);
  }

  function matchesPhrase(e) {
    const role = roleOf(e);
    if (state.filters.phrase === "untagged" && role) return false;
    if (state.filters.phrase !== "all" && state.filters.phrase !== "untagged" && role !== state.filters.phrase) return false;
    return true;
  }

  function matchesStatus(e) {
    if (e.status === "iterating") return state.filters.iterating;
    if (e.status === "accepted") return state.filters.accepted;
    if (e.status === "rejected" || e.status === "promoted") return state.filters.rejected;
    return false;
  }

  function matchesFilters(e) {
    const q = state.filters.search.trim();
    let exactName = false;
    if (q) {
      if (!labDraftSearchHit(e, q)) return false;
      exactName = String(e.name || "").toLowerCase() === q.toLowerCase();
    }
    if (!matchesPhrase(e)) return false;
    // Exact-name search hit surfaces even when its status chip is off (same idea as
    // the selected-draft pin for status — search itself still must hit).
    if (exactName) return true;
    return matchesStatus(e);
  }

  function renderList() {
    // Keep rejectedToggle text in sync for any leftover callers / a11y.
    const archived = (e) => e.status === "rejected" || e.status === "promoted";
    $("rejectedToggle").textContent = `Archived (${state.entries.filter(archived).length})`;
    state.showRejected = state.filters.rejected;

    const selectedName = state.current && state.current.name;
    const q = state.filters.search.trim();
    // Selected draft stays visible across status chips, but NOT across a failed search
    // (otherwise typing a nonsense token still ghosts the open draft).
    let visible = state.entries.filter(e => {
      if (matchesFilters(e)) return true;
      if (!(selectedName && e.name === selectedName)) return false;
      return labDraftSearchHit(e, state.filters.search);
    });

    // C11: when search hits are hidden by status chips, auto-show them with a dim note.
    let relaxedCount = 0;
    const relaxedNames = new Set();
    if (q) {
      const searchHits = state.entries.filter(e => labDraftSearchHit(e, q) && matchesPhrase(e));
      const hiddenByStatus = searchHits.filter(e => !matchesStatus(e) && !visible.some(v => v.name === e.name));
      if (hiddenByStatus.length) {
        relaxedCount = hiddenByStatus.length;
        for (const e of hiddenByStatus) {
          visible.push(e);
          relaxedNames.add(e.name);
        }
      }
    }
    const note = $("searchRelaxNote");
    if (note) {
      if (relaxedCount > 0) {
        note.hidden = false;
        note.textContent = `${relaxedCount} hidden match${relaxedCount === 1 ? "" : "es"} shown (status filters relaxed for this search)`;
      } else {
        note.hidden = true;
        note.textContent = "";
      }
    }

    $("draftsDrawerCount").textContent = String(visible.length);

    const groups = [
      {key: "iterating", label: "Work in progress", items: []},
      {key: "accepted", label: "Accepted", items: []},
      {key: "rejected", label: "Rejected", items: []},
    ];
    for (const e of visible) {
      if (e.status === "iterating") groups[0].items.push(e);
      else if (e.status === "accepted") groups[1].items.push(e);
      else groups[2].items.push(e); // rejected + promoted
    }
    for (const g of groups) {
      g.items.sort((a, b) => String(b.updated || "").localeCompare(String(a.updated || "")));
    }

    const parts = [];
    for (const g of groups) {
      if (!g.items.length) continue;
      parts.push(`<div class="lab-group-head">${esc(g.label)} <span class="dim">${g.items.length}</span></div>`);
      for (const e of g.items) {
        const active = state.current && state.current.name === e.name ? " active" : "";
        const relaxed = relaxedNames.has(e.name) ? " status-relaxed" : "";
        const prod = e.production_collision && e.status !== "promoted" ? ` <span class="prod-chip">prod</span>` : "";
        parts.push(`<button type="button" class="lab-row${active}${relaxed}" data-name="${esc(e.name)}">
          ${phraseChip(roleOf(e))}
          <span class="lab-row-name">${esc(e.name)}${prod}</span>
          ${statusDot(e.status)}
          <span class="lab-row-date dim">${esc(relativeDate(e.updated))}</span>
        </button>`);
      }
    }
    $("draftList").innerHTML = parts.length
      ? parts.join("")
      : `<div class="empty"><span class="panel-label">No drafts</span><span>Press New to make one, or clear the filters above.</span></div>`;
    $("draftList").querySelectorAll("button.lab-row").forEach(btn => {
      btn.onclick = () => {
        selectDraft(btn.dataset.name);
        closeDrawer();
      };
    });
  }

  function openDrawer() {
    state.drawerOpen = true;
    document.body.classList.add("lab-drawer-open");
    $("draftsDrawerBtn").setAttribute("aria-expanded", "true");
  }
  function closeDrawer() {
    state.drawerOpen = false;
    document.body.classList.remove("lab-drawer-open");
    $("draftsDrawerBtn").setAttribute("aria-expanded", "false");
  }

  function stashEditor() {
    if (!state.current) return;
    try {
      state.editorMemory[state.current.name] = {
        params: JSON.parse($("paramsInput").value || "{}"),
        brief: $("briefInput").value,
        notes: $("notesInput").value,
        cue_beats: cue(),
        target_role: $("targetRoleSelect").value,
        // Timing is a read-only design note (not operator-editable); carry the
        // stored value so drafts never lose it.
        timing_mode: (state.current || {}).timing_mode || "unknown",
      };
    } catch (_) { /* invalid JSON — leave prior stash */ }
  }

  function clearEditorMemory(name) {
    if (name) delete state.editorMemory[name];
  }

  function selectDraft(name) {
    // AWR-258: stash when switching drafts, or when reconnecting onto the same
    // dirty draft (old code skipped same-name and wiped tweaks).
    if (state.current && state.current.name !== name) stashEditor();
    else if (state.current && isEditorDirty()) stashEditor();
    stopPreview();
    renderSwatches(null);
    // C10: self-test results belong to the previous draft — clear on switch.
    const selfTest = $("selfTestPanel");
    if (selfTest) { selfTest.hidden = true; selfTest.innerHTML = ""; }
    if (state.current && state.current.name !== name) {
      const note = $("acceptFallbackNote");
      if (note) note.hidden = true;
    }
    state.current = state.entries.find(e => e.name === name) || null;
    renderList();
    renderDetail();
  }

  function notesPreview(text) {
    const line = String(text || "").split(/\r?\n/).find(l => l.trim()) || "";
    return line ? `Notes — ${line.slice(0, 60)}${line.length > 60 ? "…" : ""}` : "Notes";
  }

  function renderDetail() {
    const e = state.current;
    const disabled = !e;
    for (const id of ["briefInput", "notesInput", "paramsInput", "saveDraftBtn", "playDraftBtn", "acceptBtn", "rejectBtn", "previewBtn", "deleteBtn", "targetRoleSelect", "archiveUtilBtn"]) {
      if ($(id)) $(id).disabled = disabled;
    }
    if (!e) {
      $("paramControls").innerHTML = "";
      $("collisionBanner").hidden = true;
      $("appliedHint").hidden = true;
      $("draftTitle").textContent = "Select a draft";
      $("kindText").textContent = "";
      $("statusText").textContent = "";
      $("notesSummary").textContent = "Notes";
      return;
    }
    const mem = state.editorMemory[e.name];
    // F1: banner only when list decoration says so (CSS also honors [hidden]).
    $("collisionBanner").hidden = !e.production_collision;
    $("draftTitle").textContent = e.name;
    $("draftFn").textContent = `${e.kind} · ${e.fn}`;
    $("briefInput").value = mem ? mem.brief : (e.brief || "");
    $("notesInput").value = mem ? mem.notes : (e.notes || "");
    $("notesSummary").textContent = notesPreview($("notesInput").value);
    $("kindText").textContent = e.kind || "";
    $("timingText").textContent = timingLabel(mem ? mem.timing_mode : e.timing_mode);
    $("statusText").textContent = ({iterating: "Work in progress", accepted: "Accepted", rejected: "Rejected", promoted: "Promoted"})[e.status] || e.status;
    $("statusText").className = `status-pill ${e.status}`;
    $("targetRoleSelect").value = mem ? mem.target_role : roleOf(e);
    $("paramsInput").value = JSON.stringify(mem ? mem.params : (e.params || {}), null, 2);
    renderParamControls();
    renderCue();
    renderLive();
    renderBpmScope();
    setDirty();
    sizePreviewCanvas();
  }

  function sizePreviewCanvas() {
    const canvas = $("previewStrip");
    if (!canvas) return;
    const phone = window.matchMedia("(max-width: 900px)").matches;
    canvas.height = phone ? 48 : 64;
  }

  function renderBpmScope() {
    // Timing is a read-only design note; it only tells us whether tempo shapes
    // this cue's motion. beat/mixed → tempo drives it; time/static ignore it;
    // unknown → let the operator set the preview tempo anyway.
    const mode = (state.current || {}).timing_mode || "unknown";
    const enabled = mode !== "time" && mode !== "static";
    $("bpmInput").disabled = !enabled;
    document.querySelectorAll("[data-step]").forEach(btn => { btn.disabled = !enabled; });
    $("bpmScope").textContent =
      mode === "beat" ? "Changes this draft"
      : mode === "mixed" ? "Only affects beat-locked cues"
      : mode === "time" ? "This draft follows seconds; BPM has no effect"
      : mode === "static" ? "This draft does not animate"
      : "Sets the preview tempo";
  }

  function isEditorDirty() {
    if (!state.current) return false;
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch { return true; }
    const roleDirty = $("targetRoleSelect").value !== roleOf(state.current);
    const cueDirty = cue() !== Number(state.current.cue_beats || 16);
    const briefDirty = $("briefInput").value !== (state.current.brief || "");
    const notesDirty = $("notesInput").value !== (state.current.notes || "");
    return JSON.stringify(params) !== JSON.stringify(state.current.params || {})
      || roleDirty || cueDirty || briefDirty || notesDirty;
  }

  // Dirty chip (pad-ui.js setDirty pattern): editor params vs saved entry params.
  function setDirty() {
    if (!state.current) { $("labDirtyChip").textContent = ""; return; }
    const dirty = isEditorDirty();
    $("labDirtyChip").textContent = dirty ? "Unsaved tweaks" : "Saved";
    $("labDirtyChip").className = dirty ? "warn-text" : "dim";
  }

  function renderCue() {
    const values = [4, 8, 16, 32];
    const mem = state.current && state.editorMemory[state.current.name];
    const current = Number(
      (mem && mem.cue_beats != null) ? mem.cue_beats : (state.current || {}).cue_beats || 16
    );
    const isPreset = values.includes(current);
    // Fix P4 duplicate chip: hide the number input when a preset is selected.
    document.querySelector(".cue-group").innerHTML =
      values.map(v => `<button type="button" class="${current === v ? "active" : ""}" data-cue="${v}">${v}</button>`).join("") +
      `<input id="cueCustom" type="number" min="1" step="1" value="${esc(current)}" aria-label="Custom cue length"${isPreset ? " hidden" : ""}>`;
    document.querySelectorAll("[data-cue]").forEach(btn => btn.onclick = () => {
      $("cueCustom").value = btn.dataset.cue;
      $("cueCustom").hidden = true;
      document.querySelectorAll("[data-cue]").forEach(b => b.classList.toggle("active", b.dataset.cue === btn.dataset.cue));
      setDirty();
    });
    $("cueCustom").onchange = () => {
      const v = Number($("cueCustom").value);
      $("cueCustom").hidden = values.includes(v);
      document.querySelectorAll("[data-cue]").forEach(b => b.classList.toggle("active", Number(b.dataset.cue) === v));
      setDirty();
    };
  }

  function currentPayload() {
    const params = JSON.parse($("paramsInput").value || "{}");
    return {
      ...state.current,
      brief: $("briefInput").value,
      notes: $("notesInput").value,
      params,
      cue_beats: cue(),
      target_role: $("targetRoleSelect").value,
      // Read-only design note: preserve the stored value so a Save never strands it.
      timing_mode: (state.current || {}).timing_mode || "unknown",
    };
  }

  async function save(overwrite = false) {
    if (!state.current) return;
    const payload = currentPayload();
    if (overwrite) payload.overwrite = true;
    try {
      const res = await api.labSave(payload);
      clearEditorMemory(state.current.name);
      state.current = res.entry;
      await refresh();
    } catch (err) {
      if (err && err.payload && err.payload.error === "stale_entry") {
        PadModal.show(
          "Draft changed elsewhere",
          "Someone else (or another tab) saved this draft since you opened it. Reload their version, or overwrite with what you see now.",
          [
            {label: "Reload", className: "ghost", run: async () => {
              clearEditorMemory(state.current && state.current.name);
              await refresh();
            }},
            {label: "Overwrite", className: "danger-outline", run: async () => { await save(true); }},
          ],
        );
        return;
      }
      throw err;
    }
  }

  async function acceptDraft() {
    if (!state.current) return;
    const payload = {...currentPayload(), status: "accepted"};
    // Accept-what-you-hear: when editor params match the saved entry, omit them
    // so the server can prefer the last-applied snapshot (survives pad restart).
    let paramsDirty = false;
    try {
      const editorParams = JSON.parse($("paramsInput").value || "{}");
      paramsDirty = JSON.stringify(editorParams) !== JSON.stringify(state.current.params || {});
    } catch (_) {
      paramsDirty = true;
    }
    if (!paramsDirty) delete payload.params;
    try {
      const res = await api.labAccept(payload);
      const showFallback = !!(res && res.snapshot_fallback);
      clearEditorMemory(state.current.name);
      await refresh();
      const note = $("acceptFallbackNote");
      if (note) {
        if (showFallback) {
          note.hidden = false;
          note.textContent = "Accepted saved values — your last live-tuned values weren't available";
          note.className = "lab-applied-hint warn-text";
        } else if (res && res.message) {
          note.hidden = false;
          note.textContent = res.message;
          note.className = "lab-applied-hint";
        } else {
          note.hidden = true;
        }
      }
      flashReloadConfirm(true, (res && res.message) || "Added to your show");
    } catch (err) {
      if (err && err.payload && err.payload.error === "stale_entry") {
        PadModal.show(
          "Draft changed elsewhere",
          "Reload before Accept, or overwrite with what you see now.",
          [
            {label: "Reload", className: "ghost", run: async () => {
              clearEditorMemory(state.current && state.current.name);
              await refresh();
            }},
            {label: "Overwrite & Accept", className: "danger-outline", run: async () => {
              const over = {...payload, overwrite: true};
              const res = await api.labAccept(over);
              const showFallback = !!(res && res.snapshot_fallback);
              clearEditorMemory(state.current.name);
              await refresh();
              const note = $("acceptFallbackNote");
              if (note) {
                if (showFallback) {
                  note.hidden = false;
                  note.textContent = "Accepted saved values — your last live-tuned values weren't available";
                  note.className = "lab-applied-hint warn-text";
                } else if (res && res.message) {
                  note.hidden = false;
                  note.textContent = res.message;
                  note.className = "lab-applied-hint";
                } else {
                  note.hidden = true;
                }
              }
              flashReloadConfirm(true, (res && res.message) || "Added to your show");
            }},
          ],
        );
        return;
      }
      throw err;
    }
  }

  async function rejectDraft() {
    if (!state.current) return;
    try {
      const res = await api.labReject({...currentPayload(), status: "rejected"});
      clearEditorMemory(state.current.name);
      await refresh();
      flashReloadConfirm(true, (res && res.message) || "Rejected — stays out of the show. You can reopen it anytime.");
    } catch (err) {
      if (err && err.payload && err.payload.error === "stale_entry") {
        PadModal.show(
          "Draft changed elsewhere",
          "Reload before Reject, or overwrite with what you see now.",
          [
            {label: "Reload", className: "ghost", run: async () => {
              clearEditorMemory(state.current && state.current.name);
              await refresh();
            }},
            {label: "Overwrite & Reject", className: "danger-outline", run: async () => {
              const res = await api.labReject({...currentPayload(), status: "rejected", overwrite: true});
              clearEditorMemory(state.current.name);
              await refresh();
              flashReloadConfirm(true, (res && res.message) || "Rejected — stays out of the show. You can reopen it anytime.");
            }},
          ],
        );
        return;
      }
      throw err;
    }
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
        try {
          const sw = await api.labSwitch({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}")});
          if (sw.ok) {
            state.health.labOk = true;
            setAppliedHint(false);
            renderSwatches(sw.spec && sw.spec.params && sw.spec.params.slot_colors);
            await updateRuntime();
            return;
          }
        } catch (err) {
          if (err && err.message === "ownership_required") {
            PadModal.confirm("The show is running the lights right now. Take control?", "The show side goes dark until you release.", "Take control", () => play(true));
            return;
          }
          throw err;
        }
      }
      const res = await api.labPlay({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}"), cue_beats:cue(), takeover});
      state.health.labOk = true;
      setAppliedHint(false);
      renderSwatches(res.spec && res.spec.params && res.spec.params.slot_colors);
      await updateRuntime();
    } catch (err) {
      if (err && err.message === "ownership_required") {
        PadModal.confirm("The show is running the lights right now. Take control?", "The show side goes dark until you release.", "Take control", () => play(true));
        return;
      }
      showError(err);
    }
  }

  let reloadConfirmTimer = 0;
  function flashReloadConfirm(ok, text) {
    const el = $("reloadConfirm");
    el.hidden = false;
    el.className = ok ? "lab-reload-confirm" : "lab-reload-confirm bad";
    el.textContent = text;
    clearTimeout(reloadConfirmTimer);
    reloadConfirmTimer = setTimeout(() => { el.hidden = true; el.textContent = ""; }, 2000);
  }

  async function reloadCode() {
    const res = await api.labReload();
    $("traceText").textContent = res.traceback || res.error || `Loaded: ${(res.effects || []).join(", ")}`;
    state.health.labOk = Boolean(res.ok);
    state.health.labTrace = res.traceback || res.error || "";
    renderHealth();
    if (!res.ok) {
      flashReloadConfirm(false, "Reload failed");
      showError(`Your effect code failed to load: ${String(res.error || "").split("\n")[0]}`);
      if (DEV) $("tracePanel").open = true;
    } else {
      flashReloadConfirm(true, `Loaded ${(res.effects || []).length} effects ✓`);
      $("tracePanel").open = false;
    }
    return res;
  }

  async function updateRuntime() {
    try {
      const rt = await api.runtime();
      state.health.serverOkAt = performance.now();
      const ownership = (rt.ownership || {}).state || "free";
      const pb = rt.playback || {};
      state.playingLook = pb.playing ? (pb.playing_look || "") : "";
      state.health.playingName = state.playingLook;
      state.health.playingBeat = typeof pb.beat === "number" ? pb.beat : null;
      $("ownershipPill").textContent = ownership === "bridge_owned" ? "The show is running the lights" : ownership === "pad_owned" ? "This pad is running the lights" : "Lights are free";
      $("ownershipPill").className = `pill ${ownership === "bridge_owned" ? "bridge" : ownership === "pad_owned" ? "pad" : ""}`;
      $("ownershipBtn").hidden = ownership === "free";
      $("ownershipBtn").textContent = ownership === "pad_owned" ? "Release" : "Take control";
      // Live beat: phase-lock to server status.beat; preview owns the meter while its raf runs.
      if (beatUI.mode !== "preview") {
        if (pb.playing && typeof pb.beat === "number") {
          const bpm = Number(pb.bpm) || Number($("bpmInput").value) || 128;
          if (beatUI.mode === "live") {
            // Re-anchor only — keep the raf loop and last-click index.
            beatUI.polledBeat = pb.beat;
            beatUI.pollTime = performance.now();
            beatUI.bpm = bpm;
          } else {
            setBeatMode("live", {polledBeat: pb.beat, pollTime: performance.now(), bpm});
          }
        } else if (beatUI.mode === "live") {
          setBeatMode("off");
        }
      }
      renderLive();
      renderHealth();
      if (window.PadConfigStale) window.PadConfigStale.render($("configStaleBanner"), rt.config_stale);
      // AWR-275: while the live music plays, the tempo follows it (read-only);
      // when it stops, restore this draft's own BPM rule (timing-mode gated).
      const following = window.PadTempoMode ? window.PadTempoMode.render(pb) : false;
      if (!following) renderBpmScope();
    } catch (err) {
      state.health.serverFailAt = performance.now();
      renderHealth();
      throw err;
    }
  }

  function renderLive() {
    const switching = Boolean(
      state.current && state.playingLook && state.playingLook.startsWith("lab_") &&
      state.playingLook !== labScene(state.current.name)
    );
    const liveHere = Boolean(state.current && state.playingLook === labScene(state.current.name));
    $("labLive").hidden = !liveHere;
    $("playDraftBtn").textContent = switching ? "⇄ Switch live lights" : "▶ Play once on lights";
    $("playDraftBtn").classList.toggle("lab-switch-live", switching);
    $("stopDraftBtn").classList.toggle("lab-stop-armed", Boolean(state.playingLook));
    const hint = $("playOnceHint");
    if (hint) hint.hidden = Boolean(state.playingLook);
  }

  let applyTimer = 0;
  let previewTuneTimer = 0;
  const PREVIEW_TUNE_HINT = "Preview updates as you tune — Play once sends to the real lights (one cue, no loop).";
  function previewTuningActive() {
    return beatUI.mode === "preview" && preview.frames.length > 0;
  }
  function setAppliedHint(show, text) {
    const el = $("appliedHint");
    if (!el) return;
    if (text) el.textContent = text;
    el.hidden = !show;
  }
  function queuePreviewRetune() {
    clearTimeout(previewTuneTimer);
    previewTuneTimer = setTimeout(async () => {
      if (!state.current || !previewTuningActive()) return;
      try {
        await previewDraft({keepHint: true});
        setAppliedHint(true, PREVIEW_TUNE_HINT);
        clearError();
      } catch (err) { showError(err); }
    }, 400);
  }
  function queueAutoApply() {
    // AWR-251 M-2: slider/param edits are LIVE-APPLY ONLY + editor-local.
    // Persist only on Save / Accept / Reject — never via this path.
    // AWR-263 C12: while Preview is running, retune the preview strip instead.
    clearTimeout(applyTimer);
    if (previewTuningActive()) {
      setAppliedHint(true, PREVIEW_TUNE_HINT);
      queuePreviewRetune();
      return;
    }
    applyTimer = setTimeout(async () => {
      if (!state.current) return;
      let params;
      try { params = JSON.parse($("paramsInput").value || "{}"); } catch { showError("Params JSON invalid — live apply paused"); return; }
      stashEditor();
      try {
        const upd = await api.labUpdate({name: state.current.name, params});
        if (upd && upd.applied === false) {
          setAppliedHint(true, PREVIEW_TUNE_HINT);
        } else {
          setAppliedHint(false);
        }
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
      if (spec.kind === "select") {
        const options = Array.isArray(spec.options) ? spec.options : [];
        const cur = params[key] === undefined ? (options[0] && options[0].value) : params[key];
        const optsHtml = options.map(o => {
          const selected = String(o.value) === String(cur) ? " selected" : "";
          return `<option value="${esc(o.value)}"${selected}>${esc(o.label)}</option>`;
        }).join("");
        rows.push(`<label class="param-row param-select"><span>${esc(spec.label)}</span><select data-param="${esc(key)}" data-kind="select">${optsHtml}</select></label>`);
        continue;
      }
      const raw = params[key] === undefined ? spec.min : Number(params[key]);
      const colorish = Boolean(m); // incomplete triplet channel stays a slider
      rows.push(`<div class="param-row param-slider${slotKind && colorish ? " palette-fed" : ""}"><span class="param-label">${esc(spec.label)}${slotKind && colorish ? badge : ""}</span><div class="param-slider-col"><input type="range" data-param="${esc(key)}" data-kind="slider" min="${esc(spec.min)}" max="${esc(spec.max)}" step="${esc(spec.step)}" value="${esc(raw)}"><div class="param-range-ends"><span>${esc(spec.min)}</span><span>${esc(spec.max)}</span></div></div><output>${esc(raw)}</output></div>`);
    }
    container.innerHTML = rows.join("");
    container.querySelectorAll("[data-param]").forEach(input => {
      if (input.dataset.kind === "select") input.onchange = () => applyParamControl(input);
      else input.oninput = () => applyParamControl(input);
    });
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
    } else if (input.dataset.kind === "select") {
      const raw = input.value;
      const asNum = Number(raw);
      params[key] = (raw !== "" && Number.isFinite(asNum) && String(asNum) === raw) ? asNum : raw;
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

  const preview = {frames: [], fps: 40, player: null};
  // AWR-247: preview window length (2 bars / 4 bars / full cue). Default full.
  const PREVIEW_LEN_KEY = "labPreviewLength";
  let previewLengthMode = "full"; // "8" | "16" | "full"
  // AWR-245: Strip | Room toggle. Room reuses the sim view module as-is (no fork).
  // AWR-250: profile is re-fetched on Preview + Room toggle (short TTL, not forever).
  const PREVIEW_MODE_KEY = "labPreviewMode";
  const PROFILE_TTL_MS = 2000;
  const roomView = {
    mode: "strip", // "strip" | "room"
    profile: null,
    profileFetchedAt: 0,
    profilePromise: null,
    layoutFingerprint: "",
    view: null,
    unavailable: false,
  };
  // AWR-269: read-only mirror of pad send frames via SSE (same paint path as preview).
  const watchLive = {
    on: false,
    source: null,
  };
  function layoutFingerprint(profile) {
    if (!profile || typeof profile !== "object") return "";
    const name = profile.active_layout;
    const entry = (profile.layouts && typeof profile.layouts === "object")
      ? profile.layouts[name]
      : null;
    try {
      return JSON.stringify({active_layout: name, entry: entry || null});
    } catch (_) {
      return String(name || "");
    }
  }
  function setPreviewHint(show) {
    const hint = $("previewHint");
    if (hint) hint.hidden = !show;
  }
  function syncPreviewModeChrome() {
    const hero = $("labPreviewHero");
    const stripBtn = $("previewModeStrip");
    const roomBtn = $("previewModeRoom");
    const watchBtn = $("watchLiveBtn");
    const caption = $("roomViewCaption");
    const watchCaption = $("watchLiveCaption");
    const note = $("roomViewNote");
    const stripCanvas = $("previewStrip");
    const roomCanvas = $("previewRoom");
    const isRoom = roomView.mode === "room" && !roomView.unavailable;
    if (hero) hero.classList.toggle("room-mode", isRoom);
    if (stripBtn) {
      stripBtn.classList.toggle("on", !isRoom && !watchLive.on);
      stripBtn.setAttribute("aria-pressed", (!isRoom && !watchLive.on) ? "true" : "false");
    }
    if (roomBtn) {
      roomBtn.classList.toggle("on", isRoom && !watchLive.on);
      roomBtn.setAttribute("aria-pressed", (isRoom && !watchLive.on) ? "true" : "false");
      roomBtn.disabled = roomView.unavailable;
    }
    if (watchBtn) {
      watchBtn.classList.toggle("on", watchLive.on);
      watchBtn.setAttribute("aria-pressed", watchLive.on ? "true" : "false");
    }
    if (caption) caption.hidden = !isRoom || watchLive.on;
    if (watchCaption) watchCaption.hidden = !watchLive.on;
    if (note) note.hidden = !roomView.unavailable;
    if (stripCanvas) stripCanvas.hidden = isRoom;
    if (roomCanvas) roomCanvas.hidden = !isRoom;
  }
  function syncPreviewLengthChrome() {
    for (const btn of document.querySelectorAll("[data-preview-len]")) {
      const on = btn.dataset.previewLen === previewLengthMode;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }
  function setPreviewLengthMode(mode) {
    previewLengthMode = (mode === "8" || mode === "16") ? mode : "full";
    try { localStorage.setItem(PREVIEW_LEN_KEY, previewLengthMode); } catch (_) { /* private mode */ }
    syncPreviewLengthChrome();
  }
  function previewBeats() {
    if (previewLengthMode === "8") return 8;
    if (previewLengthMode === "16") return 16;
    // Full cue — editor cue length (capped 32, same as server).
    return Math.max(1, Math.min(32, cue()));
  }
  function destroyRoomView() {
    if (roomView.view && typeof roomView.view.destroy === "function") {
      try { roomView.view.destroy(); } catch (_) { /* fail-soft */ }
    }
    roomView.view = null;
    roomView.layoutFingerprint = "";
  }
  async function fetchRoomProfile() {
    const data = await fetch("/api/sim/profile").then((r) => r.json());
    if (!data || !data.ok || !data.profile) {
      throw new Error((data && data.error) || "sim profile unavailable");
    }
    roomView.profile = data.profile;
    roomView.profileFetchedAt = Date.now();
    roomView.unavailable = false;
    return roomView.profile;
  }
  async function ensureRoomProfile({force = false} = {}) {
    const freshEnough = roomView.profile
      && !force
      && (Date.now() - roomView.profileFetchedAt) < PROFILE_TTL_MS;
    if (freshEnough) return roomView.profile;
    if (!force && roomView.profilePromise) return roomView.profilePromise;
    roomView.profilePromise = fetchRoomProfile()
      .catch((err) => {
        // Fail-soft: keep last good profile when we have one; else mark unavailable.
        roomView.profilePromise = null;
        if (!roomView.profile) {
          roomView.unavailable = true;
          throw err;
        }
        return roomView.profile;
      })
      .finally(() => {
        roomView.profilePromise = null;
      });
    return roomView.profilePromise;
  }
  async function ensureRoomView({refresh = false} = {}) {
    const canvas = $("previewRoom");
    if (!canvas) throw new Error("room canvas missing");
    const [mod, profile] = await Promise.all([
      import("/static/sim/ledsim-view.js"),
      ensureRoomProfile({force: refresh}),
    ]);
    if (!mod || typeof mod.createLedSimView !== "function") {
      throw new Error("createLedSimView missing");
    }
    const fp = layoutFingerprint(profile);
    if (roomView.view && roomView.layoutFingerprint === fp) {
      return roomView.view;
    }
    destroyRoomView();
    // AWR-253: presentation mode hides the sim's editor chrome in this small preview.
    roomView.view = mod.createLedSimView(canvas, profile, {presentation: true});
    roomView.layoutFingerprint = fp;
    return roomView.view;
  }
  function stopWatchLive() {
    if (watchLive.source) {
      try { watchLive.source.close(); } catch (_) { /* fail-soft */ }
      watchLive.source = null;
    }
    watchLive.on = false;
    const hint = $("previewHint");
    if (hint && !preview.frames.length) {
      hint.textContent = "◉ Preview renders here — press Preview";
      hint.hidden = false;
    }
    syncPreviewModeChrome();
  }
  function startWatchLive() {
    stopPreview();
    stopWatchLive();
    watchLive.on = true;
    syncPreviewModeChrome();
    const hint = $("previewHint");
    if (hint) {
      hint.textContent = "Nothing playing right now — press Play on a look to mirror it here";
      hint.hidden = false;
    }
    // Prefer Room canvas when available so the mirror uses the same ledsim-view path.
    if (roomView.mode !== "room" && !roomView.unavailable) {
      setPreviewMode("room").catch(() => { /* keep strip */ });
    }
    const es = new EventSource("/api/mirror/stream");
    watchLive.source = es;
    es.onmessage = (ev) => {
      if (!watchLive.on) return;
      let data;
      try { data = JSON.parse(ev.data); } catch (_) { return; }
      const playing = Boolean(data && data.playing);
      const frame = data && Array.isArray(data.rgb) ? data.rgb : null;
      if (hint) {
        if (!playing || !frame) {
          hint.textContent = "Nothing playing right now — press Play on a look to mirror it here";
          hint.hidden = false;
        } else {
          const name = String(data.playing_look || "").replace(/^lab_/, "") || "look";
          hint.textContent = `Watching live · ${name}`;
          hint.hidden = false;
        }
      }
      if (playing && frame && frame.length) {
        paintPreviewFrame(frame);
      }
    };
    es.onerror = () => {
      // EventSource auto-reconnects; keep calm copy if the stream drops briefly.
      if (hint && watchLive.on) {
        hint.textContent = "Live mirror reconnecting…";
        hint.hidden = false;
      }
    };
  }
  function toggleWatchLive() {
    if (watchLive.on) stopWatchLive();
    else startWatchLive();
  }
  async function setPreviewMode(mode) {
    let next = mode === "room" ? "room" : "strip";
    if (next === "room" && !roomView.unavailable) {
      try {
        // AWR-250: always re-check disk when switching into Room.
        await ensureRoomView({refresh: true});
      } catch (_) {
        next = "strip";
        roomView.unavailable = true;
        destroyRoomView();
      }
    }
    if (next === "strip") destroyRoomView();
    roomView.mode = next;
    try { localStorage.setItem(PREVIEW_MODE_KEY, next); } catch (_) { /* private mode */ }
    syncPreviewModeChrome();
    // Re-paint last preview frame into the newly visible canvas.
    if (preview.frames.length && beatUI.mode === "preview") {
      paintPreviewFrame(preview.frames[beatUI.frameIndex % preview.frames.length]);
    }
  }
  function paintPreviewFrame(frame) {
    if (!Array.isArray(frame) || !frame.length) return;
    if (roomView.mode === "room" && roomView.view) {
      roomView.view.renderFrame(frame);
      return;
    }
    const canvas = $("previewStrip");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width / frame.length;
    frame.forEach((rgb, i) => {
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      ctx.fillRect(i * w, 0, Math.ceil(w), canvas.height);
    });
  }
  // P-4: near-black previews look broken — say when a cue is intentionally subtle.
  function renderPreviewDimNote(frames) {
    const note = $("previewDimNote");
    if (!note) return;
    let peak = 0;
    for (const frame of frames || []) {
      for (const px of frame) {
        for (const ch of px) if (ch > peak) peak = ch;
      }
    }
    if (frames && frames.length && peak < 40) {
      note.textContent = `This cue is intentionally subtle — peak brightness ${peak}/255`;
      note.hidden = false;
    } else {
      note.hidden = true;
    }
  }

  function stopPreview() {
    if (preview.player) {
      try { preview.player.stop(); } catch (_) { /* fail-soft */ }
    }
    preview.frames = [];
    renderPreviewDimNote(null);
    const canvas = $("previewStrip");
    if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    if (roomView.view) {
      try { roomView.view.renderFrame([]); } catch (_) { /* fail-soft */ }
    }
    if (!watchLive.on) setPreviewHint(true);
    if (beatUI.mode === "preview") setBeatMode("off");
  }
  async function ensurePreviewPlayer() {
    if (preview.player) return preview.player;
    const mod = await import("/static/sim/ledsim-player.js");
    if (!mod || typeof mod.createFramePlayer !== "function") {
      throw new Error("createFramePlayer missing");
    }
    preview.player = mod.createFramePlayer({
      onFrame(frame, index) {
        beatUI.frameIndex = index;
        paintPreviewFrame(frame);
      },
    });
    return preview.player;
  }
  async function previewDraft(opts) {
    if (!state.current) return;
    const keepHint = Boolean(opts && opts.keepHint);
    const wasPreview = previewTuningActive();
    const prevFrame = beatUI.frameIndex;
    stopPreview();
    if (!keepHint) setPreviewHint(true);
    // No implicit save: preview posts the current editor params directly.
    const params = JSON.parse($("paramsInput").value || "{}");
    const res = await api.labPreview({name: state.current.name, params, beats: previewBeats()});
    if (!res.ok) {
      $("traceText").textContent = res.traceback || res.error || "preview failed";
      state.health.labOk = false;
      state.health.labTrace = res.traceback || res.error || "";
      renderHealth();
      if (DEV) $("tracePanel").open = true;
      throw new Error(`Your effect code failed to load: ${String(res.error || "preview failed").split("\n")[0]}`);
    }
    state.health.labOk = true;
    renderHealth();
    renderSwatches(res.slot_colors);
    const canvas = $("previewStrip");
    sizePreviewCanvas();
    canvas.width = canvas.clientWidth || 600;
    // Room mode: refresh sim profile so active_layout changes from Sim show up (AWR-250).
    if (roomView.mode === "room" && !roomView.unavailable) {
      try { await ensureRoomView({refresh: true}); } catch (_) {
        roomView.unavailable = true;
        roomView.mode = "strip";
        destroyRoomView();
        syncPreviewModeChrome();
      }
    }
    preview.frames = res.frames;
    preview.fps = res.fps;
    setPreviewHint(false);
    renderPreviewDimNote(res.frames);
    // m-5: room preview sits below a sticky header — bring the animating wall on screen.
    if (roomView.mode === "room" && !keepHint) {
      const hero = document.querySelector(".lab-preview-hero");
      (hero || $("previewRoom"))?.scrollIntoView({block: "nearest", behavior: "smooth"});
    }
    const bpm = Number(res.bpm) || Number($("bpmInput").value) || 128;
    const startFrame = (keepHint && wasPreview && preview.frames.length)
      ? (prevFrame % preview.frames.length)
      : 0;
    setBeatMode("preview", {bpm, fps: preview.fps, frameIndex: startFrame});
    // AWR-266: shared ledsim-player clock (same formula as Sim stage).
    const player = await ensurePreviewPlayer();
    player.setLoop(true);
    player.setFrames(preview.frames, preview.fps);
    player.play({fromFrame: startFrame});
  }
  $("previewBtn").onclick = async () => {
    if (watchLive.on) stopWatchLive();
    $("previewBtn").disabled = true;
    try { await previewDraft(); } catch (err) { showError(err); } finally { $("previewBtn").disabled = false; }
  };
  $("previewModeStrip").onclick = () => { if (watchLive.on) stopWatchLive(); setPreviewMode("strip"); };
  $("previewModeRoom").onclick = () => { if (watchLive.on) stopWatchLive(); setPreviewMode("room"); };
  const watchLiveBtn = $("watchLiveBtn");
  if (watchLiveBtn) watchLiveBtn.onclick = () => { toggleWatchLive(); };
  for (const btn of document.querySelectorAll("[data-preview-len]")) {
    btn.onclick = () => { setPreviewLengthMode(btn.dataset.previewLen); };
  }
  try {
    const savedLen = localStorage.getItem(PREVIEW_LEN_KEY);
    if (savedLen === "8" || savedLen === "16" || savedLen === "full") previewLengthMode = savedLen;
  } catch (_) { /* private mode */ }
  syncPreviewLengthChrome();
  // Restore persisted choice (default Strip). Fail-soft if Room assets are gone.
  (async () => {
    let saved = "strip";
    try { saved = localStorage.getItem(PREVIEW_MODE_KEY) || "strip"; } catch (_) { saved = "strip"; }
    if (saved === "room") await setPreviewMode("room");
    else syncPreviewModeChrome();
  })();

  $("clickToggle").onclick = () => {
    beatUI.clickOn = !beatUI.clickOn;
    $("clickToggle").setAttribute("aria-pressed", beatUI.clickOn ? "true" : "false");
    $("clickToggle").textContent = beatUI.clickOn ? "🔊 on" : "🔊 off";
    if (beatUI.clickOn) ensureAudio(); // gesture unlocks WebAudio
    else stopClicks();
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopClicks();
  });

  function framesNotAllBlack(frames) {
    if (!Array.isArray(frames) || !frames.length) return false;
    for (const frame of frames) {
      for (const rgb of frame) {
        const [r, g, b] = Array.isArray(rgb) ? rgb : [0, 0, 0];
        if ((r || 0) + (g || 0) + (b || 0) > 0) return true;
      }
    }
    return false;
  }

  async function runSelfTest() {
    const panel = $("selfTestPanel");
    panel.hidden = false;
    const lines = [];
    const add = (ok, text) => { lines.push(`${ok ? "✓" : "✗"} ${text}`); panel.innerHTML = lines.map(l => `<div>${esc(l)}</div>`).join(""); };
    let allOk = true;

    let reloadOk = false;
    try {
      const res = await reloadCode();
      reloadOk = Boolean(res.ok);
      add(reloadOk, reloadOk ? "Reload effect code ok" : `Reload failed: ${String(res.error || "").split("\n")[0] || "error"}`);
      if (!reloadOk) allOk = false;
    } catch (err) {
      add(false, `Reload failed: ${(err && err.message) || err}`);
      allOk = false;
    }

    if (!state.current) {
      add(false, "Preview skipped — no draft selected");
      return;
    }
    try {
      const params = JSON.parse($("paramsInput").value || "{}");
      const res = await api.labPreview({name: state.current.name, params, beats: 2});
      const ok = Boolean(res.ok);
      add(ok, ok ? "Preview response ok" : `Preview failed: ${String(res.error || "").split("\n")[0] || "error"}`);
      if (!ok) { allOk = false; return; }
      const hasFrames = Array.isArray(res.frames) && res.frames.length > 0;
      add(hasFrames, hasFrames ? `Frames non-empty (${res.frames.length})` : "Frames empty");
      if (!hasFrames) allOk = false;
      const lit = framesNotAllBlack(res.frames);
      add(lit, lit ? "Frames not all-black" : "Frames are all-black");
      if (!lit) allOk = false;
      if (state.current.kind === "slot") {
        const slots = Array.isArray(res.slot_colors) && res.slot_colors.length > 0;
        add(slots, slots ? "slot_colors non-empty" : "slot_colors empty");
        if (!slots) allOk = false;
      } else {
        add(true, "slot_colors N/A (frame kind)");
      }
    } catch (err) {
      add(false, `Preview failed: ${(err && err.message) || err}`);
      allOk = false;
    }
    if (allOk) {
      state.health.labOk = true;
      renderHealth();
    }
  }

  function slugifyLabName(display, existingNames) {
    const raw = String(display || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    let base = (/^[a-z0-9_]+$/.test(raw) && raw) ? raw : "untitled";
    const taken = new Set(existingNames || []);
    let candidate = base;
    let n = 2;
    while (taken.has(candidate)) {
      candidate = `${base}_${n}`;
      n += 1;
    }
    return candidate;
  }

  $("newDraftBtn").onclick = () => {
    const working = state.entries.filter(e => e.previewable);
    const defaultStarter = (state.current && state.current.previewable)
      ? state.current.name
      : (working[0] && working[0].name) || "";
    const starterOptions = [
      ...working.map(e => ({
        value: e.name,
        label: `${e.name}${e.brief ? " — " + String(e.brief).slice(0, 40) : ""}`,
      })),
      {
        value: "__blank__",
        label: "Empty shell — an AI agent must write its render code before it can preview",
      },
    ];
    if (!starterOptions.length) {
      starterOptions.push({
        value: "__blank__",
        label: "Empty shell — an AI agent must write its render code before it can preview",
      });
    }
    PadModal.fields(
      "New cue",
      "Name it in plain words. Letters/numbers/spaces fine — we'll format it automatically. Start from a working cue so Preview and tuning work right away.",
      [
        {name: "display_name", label: "Display name", type: "text", value: ""},
        {
          name: "starter",
          label: "Start from",
          type: "select",
          value: defaultStarter || "__blank__",
          options: starterOptions,
        },
      ],
      {confirmText: "Create"},
      async (values) => {
        const display = String(values.display_name || "").trim();
        if (!display) { showError("Give the cue a name"); return; }
        const name = slugifyLabName(display, state.entries.map(e => e.name));
        const starterName = values.starter;
        let payload;
        if (starterName && starterName !== "__blank__") {
          const starter = state.entries.find(e => e.name === starterName);
          if (!starter) { showError("Starter draft disappeared — pick again"); return; }
          payload = {
            name,
            kind: starter.kind || "slot",
            fn: starter.fn || starter.name,
            params: JSON.parse(JSON.stringify(starter.params || {})),
            param_specs: JSON.parse(JSON.stringify(starter.param_specs || {})),
            cue_beats: Number(starter.cue_beats) || 16,
            brief: display,
            notes: "",
            status: "iterating",
            target_role: starter.target_role || "",
            timing_mode: starter.timing_mode || "unknown",
          };
        } else {
          payload = {
            name,
            kind: "slot",
            fn: name,
            params: {},
            param_specs: {},
            cue_beats: 16,
            brief: display,
            notes: "Empty shell — an AI agent must write its render code before it can preview.",
            status: "iterating",
            target_role: "",
            timing_mode: "unknown",
          };
        }
        await api.labSave(payload);
        await refresh();
        selectDraft(name);
        closeDrawer();
        if (starterName && starterName !== "__blank__") {
          try { await previewDraft(); } catch (err) { showError(err); }
        }
      }
    );
  };
  $("saveDraftBtn").onclick = () => save().catch(showError);
  $("playDraftBtn").onclick = () => play(false);
  $("stopDraftBtn").onclick = () => api.stop().then(() => { if (beatUI.mode === "live") setBeatMode("off"); return updateRuntime(); }).catch(showError);
  $("reloadBtn").onclick = () => reloadCode().catch(showError);
  $("acceptBtn").onclick = () => acceptDraft().catch(showError);
  $("rejectBtn").onclick = () => rejectDraft().catch(showError);
  $("rejectedToggle").onclick = () => {
    state.filters.rejected = !state.filters.rejected;
    document.querySelector('[data-status-filter="rejected"]').classList.toggle("on", state.filters.rejected);
    renderList();
  };
  function archiveCurrent() {
    if (!state.current) return;
    PadModal.confirm(`Archive draft ${state.current.name}?`, "Marks it promoted and files it under Rejected (archived). The drafts.json entry stays for the record.", "Archive", async () => {
      await api.labArchive({name: state.current.name});
      await refresh();
    });
  }
  $("archiveBtn").onclick = archiveCurrent;
  $("archiveUtilBtn").onclick = archiveCurrent;
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
  $("paramsInput").onblur = () => {
    try {
      JSON.parse($("paramsInput").value || "{}");
      clearError();
      // C9: JSON is the source of truth on blur — rebuild sliders/selects from it.
      renderParamControls();
      queueAutoApply();
    } catch (err) { showError(err); }
  };
  $("paramsInput").oninput = () => { setDirty(); queueAutoApply(); };
  $("briefInput").oninput = () => setDirty();
  $("notesInput").oninput = () => { $("notesSummary").textContent = notesPreview($("notesInput").value); setDirty(); };
  $("targetRoleSelect").onchange = () => setDirty();
  $("draftSearch").oninput = (ev) => { state.filters.search = ev.target.value; renderList(); };
  $("phraseFilter").onchange = (ev) => { state.filters.phrase = ev.target.value; renderList(); };
  document.querySelectorAll("[data-status-filter]").forEach(btn => {
    btn.onclick = () => {
      const key = btn.dataset.statusFilter;
      state.filters[key] = !state.filters[key];
      btn.classList.toggle("on", state.filters[key]);
      renderList();
    };
  });
  $("draftsDrawerBtn").onclick = () => { if (state.drawerOpen) closeDrawer(); else openDrawer(); };
  $("selfTestBtn").onclick = () => runSelfTest().catch(showError);
  // P-5: lab "?" help popover — same toggle/outside-click pattern as the sim's help-btn.
  $("labHelpBtn").onclick = () => {
    const pop = $("labHelpPopover");
    const open = pop.hidden;
    pop.hidden = !open;
    $("labHelpBtn").setAttribute("aria-expanded", open ? "true" : "false");
  };
  document.addEventListener("click", (event) => {
    const pop = $("labHelpPopover");
    if (!pop || pop.hidden) return;
    if (pop.contains(event.target) || $("labHelpBtn").contains(event.target)) return;
    pop.hidden = true;
    $("labHelpBtn").setAttribute("aria-expanded", "false");
  });
  $("healthLab").onclick = () => {
    if (state.health.labOk === false) {
      $("tracePanel").hidden = false;
      $("tracePanel").open = true;
      if (state.health.labTrace) $("traceText").textContent = state.health.labTrace;
    }
  };
  // AWR-271: shared shell owns session/ownership/STOP — pad-ui binds those once.
  const shellShared = Boolean(document.body && document.body.dataset.shell === "lighting");
  if (!shellShared) {
    $("bpmInput").onchange = ev => api.session({bpm:Number(ev.target.value)}).catch(showError);
    document.querySelectorAll("[data-step]").forEach(btn => btn.onclick = () => { $("bpmInput").value = Number($("bpmInput").value || 128) + Number(btn.dataset.step); $("bpmInput").dispatchEvent(new Event("change")); });
    $("paletteSelect").onchange = ev => api.session({test_palette:ev.target.value}).catch(showError);
    $("loopToggle").onchange = ev => { $("loopLabel").textContent = ev.target.checked ? "On" : "Off"; api.session({loop:ev.target.checked}).catch(showError); };
    $("stopBtn").onclick = () => api.emergencyStop().then(() => { setBeatMode("off"); return updateRuntime(); }).catch(showError);
    $("ownershipBtn").onclick = async () => { const rt = await api.runtime(); if ((rt.ownership || {}).state === "pad_owned") await api.release(); else await api.takeover(); await updateRuntime(); };
  }
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") {
      if (PadModal.isOpen()) PadModal.close();
      else if (state.drawerOpen) closeDrawer();
      else if (!$("selfTestPanel").hidden) $("selfTestPanel").hidden = true;
    }
  });
  window.addEventListener("beforeunload", (ev) => {
    if (!isEditorDirty()) return;
    ev.preventDefault();
    ev.returnValue = "";
  });
  window.addEventListener("resize", sizePreviewCanvas);
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
  // Health strip refresh between PadHealth polls (~1s) so "Ns ago" stays honest.
  setInterval(renderHealth, 1000);
  refresh().catch(showError);

  // Shared-component export: one store / one save path for pad-mounted Lab and /lab.
  window.LabEditor = {
    isDirty: isEditorDirty,
    refresh,
    updateRuntime,
    onEmergencyStop: () => { setBeatMode("off"); },
  };
}());
