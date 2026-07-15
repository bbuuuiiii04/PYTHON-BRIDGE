// sim-app.js — H612D LED Studio page controller.

import { createLedSimView } from "./ledsim-view.js";

const $ = (id) => document.getElementById(id);

const state = {
  profile: null,
  savedProfile: null,
  catalog: null,
  frames: [],
  frameTimes: [],
  markers: [],
  framesFps: 60,
  cycleMs: 0,
  playing: false,
  loop: true,
  t0: 0,
  manualIdx: 0,
  lastPaintedIdx: -1,
  display: null,
  lastTick: 0,
  paintWindowAt: 0,
  paintCount: 0,
  skippedPaints: 0,
};

let view = null;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function showError(message) {
  const element = $("error-banner");
  element.textContent = message;
  element.hidden = !message;
}

function showWarnings() {
  const warnings = [];
  if (state.catalog?.profile_error) warnings.push(`profile: ${state.catalog.profile_error}`);
  if (state.catalog?.lab_error) warnings.push(`lab: ${state.catalog.lab_error}`);
  if (state.catalog?.looks && !state.catalog.looks.ok) warnings.push(`looks: ${state.catalog.looks.error}`);
  const element = $("warnings");
  element.textContent = warnings.join("  •  ");
  element.hidden = warnings.length === 0;
}

async function api(method, path, body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    showError(`Could not reach the simulator: ${error}`);
    throw error;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.errors ? data.errors.join("; ") : (data.error || response.statusText);
    showError(detail);
    throw new Error(detail);
  }
  showError("");
  return data;
}

const KNOBS = [
  ["gamma", "knob-gamma"],
  ["brightness", "knob-brightness"],
  ["glow_radius", "knob-glow-radius"],
  ["glow_gain", "knob-glow-gain"],
  ["bleed", "knob-bleed"],
  ["fps", "knob-fps"],
  ["latency_ms", "knob-latency"],
  ["slew_ms", "knob-slew"],
];

function stripLocal(profile) {
  return {...profile};
}

function markDirty() {
  const dirty = JSON.stringify(stripLocal(state.profile)) !== JSON.stringify(state.savedProfile);
  $("profile-dirty").hidden = !dirty;
}

function updateCalibrationBadge() {
  const status = String(state.profile.calibration_status || "unmeasured");
  const badge = $("calibration-badge");
  badge.textContent = status.toUpperCase();
  badge.classList.toggle("warning", status !== "measured");
}

function pushProfileToView() {
  view.setProfile(state.profile);
  markDirty();
  updateCalibrationBadge();
}

function knobsFromProfile() {
  for (const [key, id] of KNOBS) {
    $(id).value = state.profile[key];
    $(`${id}-val`).textContent = String(state.profile[key]);
  }
  for (let channel = 0; channel < 3; channel += 1) {
    $(`knob-white-${channel}`).value = state.profile.white_point[channel];
    $(`knob-white-${channel}-val`).textContent = String(state.profile.white_point[channel]);
  }
  $("knob-hold").value = state.profile.hold_mode;
  $("bpm").value = state.profile.bpm;
  markDirty();
  updateCalibrationBadge();
}

function wireKnobs() {
  for (const [key, id] of KNOBS) {
    $(id).addEventListener("input", () => {
      state.profile[key] = Number($(id).value);
      $(`${id}-val`).textContent = $(id).value;
      pushProfileToView();
    });
  }
  for (let channel = 0; channel < 3; channel += 1) {
    $(`knob-white-${channel}`).addEventListener("input", () => {
      state.profile.white_point[channel] = Number($(`knob-white-${channel}`).value);
      $(`knob-white-${channel}-val`).textContent = $(`knob-white-${channel}`).value;
      pushProfileToView();
    });
  }
  $("knob-hold").addEventListener("change", () => {
    state.profile.hold_mode = $("knob-hold").value;
    state.display = null;
    pushProfileToView();
  });

  $("profile-save").addEventListener("click", async () => {
    const result = await api("POST", "/api/profile", stripLocal(state.profile));
    state.savedProfile = clone(result.profile);
    markDirty();
  });
  $("profile-revert").addEventListener("click", async () => {
    const result = await api("GET", "/api/profile");
    state.profile = result.profile;
    state.savedProfile = clone(result.profile);
    knobsFromProfile();
    pushProfileToView();
  });
}

function setMode(mode) {
  const calibrate = mode === "calibrate";
  $("author-panel").hidden = calibrate;
  $("calibrate-panel").hidden = !calibrate;
  $("tab-author").classList.toggle("active", !calibrate);
  $("tab-calibrate").classList.toggle("active", calibrate);
}

function fillSourcePicker() {
  const kind = $("source-kind").value;
  const select = $("source-name");
  select.innerHTML = "";
  $("replay-row").hidden = kind !== "replay";
  $("source-name-row").hidden = kind === "replay";

  if (kind === "effect") {
    for (const name of state.catalog.effects) select.add(new Option(name, name));
  } else if (kind === "look") {
    const looks = state.catalog.looks.ok ? state.catalog.looks.looks : {};
    for (const [name, entry] of Object.entries(looks)) select.add(new Option(name, name));
  } else if (kind === "lab") {
    for (const draft of state.catalog.lab.drafts || []) select.add(new Option(draft.name, draft.name));
  }
  syncParamsFromSource();
}

function syncParamsFromSource() {
  const kind = $("source-kind").value;
  const name = $("source-name").value;
  $("seed").disabled = kind === "look";
  if (kind === "look") {
    const entry = state.catalog.looks.ok ? state.catalog.looks.looks[name] : null;
    $("params").value = entry ? JSON.stringify(entry.params, null, 2) : "{}";
    if (entry) $("seed").value = entry.seed;
  } else if (kind === "lab") {
    const draft = (state.catalog.lab.drafts || []).find((item) => item.name === name);
    $("params").value = draft ? JSON.stringify(draft.params || {}, null, 2) : "{}";
  } else if (kind === "effect") {
    $("params").value = "{}";
  }
}

function renderRequestBody() {
  let params;
  try {
    params = JSON.parse($("params").value || "{}");
  } catch (error) {
    showError(`Effect parameters are not valid JSON: ${error}`);
    return null;
  }
  const kind = $("source-kind").value;
  let name = $("source-name").value;
  let source = "effect";
  let seed = Number($("seed").value) || 0;
  let syncMode = "";
  let beatDivision = 0;
  if (kind === "look") {
    const entry = state.catalog.looks.ok ? state.catalog.looks.looks[name] : null;
    if (!entry) {
      showError("Choose a production look first.");
      return null;
    }
    name = entry.effect;
    seed = entry.seed;
    syncMode = entry.sync_mode;
    beatDivision = entry.beat_division;
  } else if (kind === "lab") {
    source = "lab";
  }
  return {
    source,
    name,
    params,
    seed,
    sync_mode: syncMode,
    beat_division: beatDivision,
    fps: Number(state.profile.fps) || 60,
    duration_s: Number($("duration").value) || 8,
    bpm: Number($("bpm").value) || 128,
  };
}

async function doRender() {
  const body = renderRequestBody();
  if (!body) return;
  const result = await api("POST", "/api/render", body);
  $("view-title").textContent = $("source-name").selectedOptions[0]?.textContent || body.name;
  loadFrames(result.frames, result.fps, result.t_ms, [], result.pipeline);
}

async function doReplayLoad() {
  const path = $("replay-path").value.trim();
  if (!path) {
    showError("Enter a frames JSONL path.");
    return;
  }
  const result = await api("POST", "/api/replay/load", {path});
  $("view-title").textContent = result.meta?.name || "Recorded frames";
  loadFrames(result.frames, result.fps, result.t_ms, result.meta?.markers || [], "recorded");
}

async function doTestCard(kind) {
  const result = await api("POST", "/api/render_card", {kind});
  $("view-title").textContent = `Reference · ${kind}`;
  loadFrames(result.frames, result.fps, result.t_ms, [{frame: 0, label: kind}], "reference");
  stopPlayback();
}

async function doCalibration(name) {
  const result = await api("POST", "/api/calibration", {
    name,
    fps: Number(state.profile.fps) || 60,
  });
  $("view-title").textContent = `Calibration · ${name.replaceAll("_", " ")}`;
  loadFrames(result.frames, result.fps, result.t_ms, result.markers, "calibration");
}

function normalizeTimes(frameCount, fps, supplied) {
  if (Array.isArray(supplied) && supplied.length === frameCount) return supplied.map(Number);
  return Array.from({length: frameCount}, (_, index) => Math.round(index * 1000 / fps));
}

function loadFrames(frames, fps, tMs, markers = [], pipeline = "runtime") {
  state.frames = frames || [];
  state.framesFps = Number(fps) || 60;
  state.frameTimes = normalizeTimes(state.frames.length, state.framesFps, tMs);
  state.markers = Array.isArray(markers) ? markers : [];
  state.cycleMs = state.frames.length
    ? state.frameTimes[state.frameTimes.length - 1] + (1000 / state.framesFps)
    : 0;
  state.manualIdx = 0;
  state.lastPaintedIdx = -1;
  state.display = null;
  state.skippedPaints = 0;
  $("scrub").max = String(Math.max(0, state.frames.length - 1));
  $("scrub").value = "0";
  $("pipeline-badge").textContent = `${String(pipeline).toUpperCase()} PIPELINE`;
  $("timing-readout").textContent = `${state.framesFps} FPS TARGET`;
  startPlayback();
}

function indexAtTime(timeMs) {
  let low = 0;
  let high = state.frameTimes.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (state.frameTimes[middle] <= timeMs) low = middle + 1;
    else high = middle;
  }
  return Math.max(0, Math.min(state.frames.length - 1, low - 1));
}

function currentIndex(now) {
  if (!state.frames.length) return 0;
  if (!state.playing) return Math.min(state.manualIdx, state.frames.length - 1);
  const latency = Number(state.profile.latency_ms) || 0;
  let elapsed = now - state.t0 - latency;
  if (elapsed < 0) return 0;
  if (state.loop && state.cycleMs > 0) elapsed %= state.cycleMs;
  if (!state.loop && elapsed >= state.cycleMs) {
    state.playing = false;
    state.manualIdx = state.frames.length - 1;
    $("play-pause").textContent = "Play";
    return state.manualIdx;
  }
  return indexAtTime(elapsed);
}

function startPlayback() {
  if (!state.frames.length) return;
  if (!state.loop && state.manualIdx >= state.frames.length - 1) state.manualIdx = 0;
  const latency = Number(state.profile.latency_ms) || 0;
  state.playing = true;
  state.t0 = performance.now() - state.frameTimes[state.manualIdx] - latency;
  state.lastPaintedIdx = -1;
  $("play-pause").textContent = "Pause";
}

function stopPlayback(now = performance.now()) {
  if (state.playing && state.frames.length) state.manualIdx = currentIndex(now);
  state.playing = false;
  $("play-pause").textContent = "Play";
}

function markerFor(index) {
  let label = "";
  for (const marker of state.markers) {
    if (Number(marker.frame) > index) break;
    label = marker.label || label;
  }
  return label;
}

function applyMeasuredSlew(target, now) {
  if (state.profile.hold_mode !== "slew" || Number(state.profile.slew_ms) <= 0) {
    state.display = null;
    return target;
  }
  const tau = Math.max(1, Number(state.profile.slew_ms));
  const dt = Math.min(200, now - (state.lastTick || now));
  const amount = 1 - Math.exp(-dt / tau);
  if (!state.display || state.display.length !== target.length) {
    state.display = target.map((pixel) => pixel.slice());
  } else {
    for (let index = 0; index < target.length; index += 1) {
      for (let channel = 0; channel < 3; channel += 1) {
        state.display[index][channel] += (target[index][channel] - state.display[index][channel]) * amount;
      }
    }
  }
  return state.display.map((pixel) => pixel.map(Math.round));
}

function updatePaintHealth(now) {
  state.paintCount += 1;
  if (!state.paintWindowAt) state.paintWindowAt = now;
  const span = now - state.paintWindowAt;
  if (span < 1000) return;
  const rate = state.paintCount * 1000 / span;
  $("paint-health").textContent = `PAINT ${rate.toFixed(1)} · SKIP ${state.skippedPaints}`;
  state.paintWindowAt = now;
  state.paintCount = 0;
  state.skippedPaints = 0;
}

function tick(now) {
  if (view && state.frames.length) {
    const index = currentIndex(now);
    const slewing = state.profile.hold_mode === "slew" && Number(state.profile.slew_ms) > 0;
    if (index !== state.lastPaintedIdx || slewing) {
      if (!slewing && state.lastPaintedIdx >= 0) {
        const expected = (state.lastPaintedIdx + 1) % state.frames.length;
        if (index !== expected && index !== state.lastPaintedIdx) state.skippedPaints += 1;
      }
      view.renderFrame(applyMeasuredSlew(state.frames[index], now));
      state.lastPaintedIdx = index;
      updatePaintHealth(now);
    }
    state.manualIdx = index;
    $("scrub").value = String(index);
    $("frame-label").textContent = `${index + 1} / ${state.frames.length}`;
    $("time-label").textContent = `${((state.frameTimes[index] || 0) / 1000).toFixed(3)} s`;
    $("marker-label").textContent = markerFor(index) || "Exact command frame · six physical LEDs per segment";
  }
  state.lastTick = now;
  requestAnimationFrame(tick);
}

function wireKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (event.code === "Space") {
      event.preventDefault();
      state.playing ? stopPlayback() : startPlayback();
    } else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && state.frames.length) {
      event.preventDefault();
      stopPlayback();
      state.manualIdx = Math.max(0, Math.min(
        state.frames.length - 1,
        state.manualIdx + (event.key === "ArrowRight" ? 1 : -1),
      ));
      state.lastPaintedIdx = -1;
    }
  });
}

async function boot() {
  state.catalog = await api("GET", "/api/catalog");
  state.profile = state.catalog.profile;
  state.savedProfile = clone(state.catalog.profile);
  view = createLedSimView($("fixture-canvas"), state.profile);
  view.renderFrame(Array.from({length: 60}, () => [0, 0, 0]));
  showWarnings();
  fillSourcePicker();
  knobsFromProfile();
  wireKnobs();
  wireKeyboard();

  $("tab-author").addEventListener("click", () => setMode("author"));
  $("tab-calibrate").addEventListener("click", () => setMode("calibrate"));
  $("source-kind").addEventListener("change", fillSourcePicker);
  $("source-name").addEventListener("change", syncParamsFromSource);
  $("render").addEventListener("click", doRender);
  $("replay-load").addEventListener("click", doReplayLoad);
  $("play-pause").addEventListener("click", () => (state.playing ? stopPlayback() : startPlayback()));
  $("loop").addEventListener("change", () => { state.loop = $("loop").checked; });
  $("scrub").addEventListener("input", () => {
    stopPlayback();
    state.manualIdx = Number($("scrub").value) || 0;
    state.lastPaintedIdx = -1;
  });
  for (const button of document.querySelectorAll("[data-card]")) {
    button.addEventListener("click", () => doTestCard(button.dataset.card));
  }
  for (const button of document.querySelectorAll("[data-sequence]")) {
    button.addEventListener("click", () => doCalibration(button.dataset.sequence));
  }

  requestAnimationFrame(tick);
  await doRender();
}

boot().catch((error) => showError(`Simulator failed to start: ${error}`));
