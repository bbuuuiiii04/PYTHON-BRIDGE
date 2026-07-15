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
  durationMs: 0,
  durationSource: "unknown",
  timingSource: "unknown",
  provenance: "unknown",
  playing: false,
  loop: true,
  t0: 0,
  pausedElapsedMs: 0,
  manualIdx: 0,
  lastPresentedOrdinal: null,
  display: null,
  lastTick: 0,
  healthWindowAt: 0,
  rafCount: 0,
  drawCount: 0,
  missedFrames: 0,
  frameRequestToken: 0,
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

async function api(method, path, body, frameToken = null) {
  const current = () => frameToken === null || frameToken === state.frameRequestToken;
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    if (current()) showError(`Could not reach the simulator: ${error}`);
    throw error;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.errors ? data.errors.join("; ") : (data.error || response.statusText);
    if (current()) showError(detail);
    throw new Error(detail);
  }
  if (current()) showError("");
  return data;
}

async function latestFrameRequest(path, body) {
  const token = ++state.frameRequestToken;
  try {
    const result = await api("POST", path, body, token);
    return token === state.frameRequestToken ? result : null;
  } catch (_error) {
    return null;
  }
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
  const allowed = ["relative", "measured"];
  const statuses = [String(state.profile.calibration_status)];
  if (state.profile.calibration_domains) {
    statuses.push(...["color", "timing", "spatial"].map((key) => String(state.profile.calibration_domains[key])));
  }
  const status = statuses.every((value) => allowed.includes(value))
    ? (statuses.includes("relative") ? "relative" : "measured")
    : "unmeasured";
  const badge = $("calibration-badge");
  badge.textContent = status.toUpperCase();
  badge.classList.toggle("warning", status !== "measured");
}

function calibrationSupportsSlew() {
  const allowed = ["relative", "measured"];
  const status = String(state.profile.calibration_status);
  const timingStatus = state.profile.calibration_domains?.timing;
  return allowed.includes(status) && (timingStatus === undefined || allowed.includes(String(timingStatus)));
}

function invalidateCalibration() {
  state.profile.calibration_status = "unmeasured";
  state.profile.calibration_domains = {color: "unmeasured", timing: "unmeasured", spatial: "unmeasured"};
  for (const key of [
    "calibration_evidence", "calibration_evidence_id", "calibration_measured_at",
    "measurement_evidence", "measurement_id", "measured_at", "evidence",
  ]) delete state.profile[key];
  state.display = null;
  state.lastPresentedOrdinal = null;
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
      invalidateCalibration();
      pushProfileToView();
    });
  }
  for (let channel = 0; channel < 3; channel += 1) {
    $(`knob-white-${channel}`).addEventListener("input", () => {
      state.profile.white_point[channel] = Number($(`knob-white-${channel}`).value);
      $(`knob-white-${channel}-val`).textContent = $(`knob-white-${channel}`).value;
      invalidateCalibration();
      pushProfileToView();
    });
  }
  $("knob-hold").addEventListener("change", () => {
    state.profile.hold_mode = $("knob-hold").value;
    invalidateCalibration();
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
    state.display = null;
    state.lastPresentedOrdinal = null;
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
  const renderButton = $("render");
  select.innerHTML = "";
  $("replay-row").hidden = kind !== "replay";
  $("source-name-row").hidden = kind === "replay";
  renderButton.hidden = kind === "replay";
  renderButton.textContent = {
    look: "Render look",
    effect: "Render effect",
    lab: "Render lab draft",
  }[kind] || "Render preview";

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
  const result = await latestFrameRequest("/api/render", body);
  if (!result) return;
  $("view-title").textContent = $("source-name").selectedOptions[0]?.textContent || body.name;
  loadFrames(result.frames, result.fps, result.t_ms, [], {
    durationMs: result.duration_ms,
    provenance: result.provenance || result.pipeline || "server render",
    timingSource: result.timing_source,
  });
}

async function doReplayLoad() {
  const path = $("replay-path").value.trim();
  if (!path) {
    showError("Enter a frames JSONL path.");
    return;
  }
  const result = await latestFrameRequest("/api/replay/load", {path});
  if (!result) return;
  $("view-title").textContent = result.meta?.name || "Recorded frames";
  loadFrames(result.frames, result.fps, result.t_ms, result.meta?.markers || [], {
    durationMs: result.duration_ms ?? result.meta?.duration_ms,
    provenance: result.provenance || result.meta?.provenance || "recorded JSONL",
    timingSource: result.timing_source || result.meta?.timing_source,
  });
}

async function doTestCard(kind) {
  const result = await latestFrameRequest("/api/render_card", {kind});
  if (!result) return;
  $("view-title").textContent = `Reference · ${kind}`;
  loadFrames(result.frames, result.fps, result.t_ms, [{frame: 0, label: kind}], {
    durationMs: result.duration_ms,
    provenance: result.provenance || "generated reference",
    timingSource: result.timing_source,
  });
  stopPlayback();
}

async function doCalibration(name) {
  const result = await latestFrameRequest("/api/calibration", {
    name,
    fps: Number(state.profile.fps) || 60,
  });
  if (!result) return;
  $("view-title").textContent = `Calibration · ${name.replaceAll("_", " ")}`;
  loadFrames(result.frames, result.fps, result.t_ms, result.markers, {
    durationMs: result.duration_ms,
    provenance: result.provenance || "generated calibration",
    timingSource: result.timing_source,
  });
}

function buildTimeline(frameCount, fps, supplied, explicitDuration, reportedSource) {
  const suppliedTimes = Array.isArray(supplied) ? supplied.map(Number) : [];
  const suppliedValid = suppliedTimes.length === frameCount && suppliedTimes.every((value, index) => (
    Number.isFinite(value) && value >= 0 && (!index || value >= suppliedTimes[index - 1])
  ));
  const frameTimes = suppliedValid
    ? suppliedTimes
    : Array.from({length: frameCount}, (_, index) => Math.round(index * 1000 / fps));
  const timingSource = reportedSource || (
    suppliedValid ? "server timestamps" : (Array.isArray(supplied) ? "invalid timestamps · FPS fallback" : "FPS grid")
  );
  if (!frameCount) return {frameTimes, durationMs: 0, timingSource, durationSource: "empty"};

  const lastTimestamp = frameTimes[frameTimes.length - 1];
  const explicit = Number(explicitDuration);
  if (explicitDuration !== undefined && explicitDuration !== null && Number.isFinite(explicit) && explicit > lastTimestamp) {
    return {frameTimes, durationMs: explicit, timingSource, durationSource: "explicit duration"};
  }

  const idealGrid = frameTimes.every((value, index) => value === Math.round(index * 1000 / fps));
  const durationMs = idealGrid ? frameCount * 1000 / fps : lastTimestamp + 1000 / fps;
  const invalid = explicitDuration !== undefined && explicitDuration !== null ? "invalid duration_ms · " : "";
  return {frameTimes, durationMs, timingSource, durationSource: `${invalid}legacy inferred duration`};
}

function loadFrames(frames, fps, tMs, markers = [], options = {}) {
  state.frames = frames || [];
  state.framesFps = Number(fps) || 60;
  const timeline = buildTimeline(
    state.frames.length,
    state.framesFps,
    tMs,
    options.durationMs,
    options.timingSource,
  );
  state.frameTimes = timeline.frameTimes;
  state.durationMs = timeline.durationMs;
  state.durationSource = timeline.durationSource;
  state.timingSource = timeline.timingSource;
  state.provenance = String(options.provenance || "not reported");
  state.markers = Array.isArray(markers) ? markers : [];
  state.manualIdx = 0;
  state.pausedElapsedMs = -(Number(state.profile.latency_ms) || 0);
  state.lastPresentedOrdinal = null;
  state.display = null;
  state.healthWindowAt = 0;
  state.rafCount = 0;
  state.drawCount = 0;
  state.missedFrames = 0;
  $("scrub").max = String(Math.max(0, state.frames.length - 1));
  $("scrub").value = "0";
  $("pipeline-badge").textContent = `SOURCE · ${state.provenance.toUpperCase()}`;
  $("timing-readout").textContent = `${state.framesFps} FPS · ${state.timingSource.toUpperCase()} · ${state.durationSource.toUpperCase()}`;
  $("paint-health").textContent = "WAITING";
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

function positionForElapsed(elapsed) {
  if (!state.frames.length) return {index: 0, ordinal: 0, ended: false};
  if (elapsed < 0) return {index: 0, ordinal: 0, ended: false};
  if (state.loop && state.durationMs > 0) {
    const cycle = Math.floor(elapsed / state.durationMs);
    const local = elapsed - cycle * state.durationMs;
    const index = indexAtTime(local);
    return {index, ordinal: cycle * state.frames.length + index, ended: false};
  }
  if (!state.loop && elapsed >= state.durationMs) {
    const index = state.frames.length - 1;
    return {index, ordinal: index, ended: true};
  }
  const index = indexAtTime(elapsed);
  return {index, ordinal: index, ended: false};
}

function currentPosition(now) {
  const elapsed = state.playing ? now - state.t0 : state.pausedElapsedMs;
  const position = positionForElapsed(elapsed);
  if (state.playing && position.ended) {
    state.playing = false;
    state.pausedElapsedMs = state.durationMs;
    state.manualIdx = position.index;
    $("play-pause").textContent = "Play";
  }
  return position;
}

function startPlayback() {
  if (!state.frames.length) return;
  if (!state.loop && state.pausedElapsedMs >= state.durationMs) {
    state.manualIdx = 0;
    state.pausedElapsedMs = -(Number(state.profile.latency_ms) || 0);
  }
  state.playing = true;
  state.t0 = performance.now() - state.pausedElapsedMs;
  state.lastPresentedOrdinal = null;
  $("play-pause").textContent = "Pause";
}

function stopPlayback(now = performance.now()) {
  if (state.playing && state.frames.length) {
    state.pausedElapsedMs = now - state.t0;
    const position = positionForElapsed(state.pausedElapsedMs);
    state.manualIdx = position.index;
    if (position.ended) state.pausedElapsedMs = state.durationMs;
  }
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
  if (
    !calibrationSupportsSlew()
    || state.profile.hold_mode !== "slew"
    || Number(state.profile.slew_ms) <= 0
  ) {
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
  if (!state.healthWindowAt) state.healthWindowAt = now;
  const span = now - state.healthWindowAt;
  if (span < 1000) return;
  const rafRate = state.rafCount * 1000 / span;
  const drawRate = state.drawCount * 1000 / span;
  $("paint-health").textContent = `DRAW ${drawRate.toFixed(1)} · RAF ${rafRate.toFixed(1)} · MISSED ${state.missedFrames}`;
  state.healthWindowAt = now;
  state.rafCount = 0;
  state.drawCount = 0;
  state.missedFrames = 0;
}

function tick(now) {
  state.rafCount += 1;
  if (view && state.frames.length) {
    const position = currentPosition(now);
    const index = position.index;
    const slewing = (
      calibrationSupportsSlew()
      && state.profile.hold_mode === "slew"
      && Number(state.profile.slew_ms) > 0
    );
    if (state.lastPresentedOrdinal !== position.ordinal || slewing) {
      if (state.lastPresentedOrdinal !== null && position.ordinal > state.lastPresentedOrdinal + 1) {
        state.missedFrames += position.ordinal - state.lastPresentedOrdinal - 1;
      }
      view.renderFrame(applyMeasuredSlew(state.frames[index], now));
      state.drawCount += 1;
      state.lastPresentedOrdinal = position.ordinal;
    }
    state.manualIdx = index;
    $("scrub").value = String(index);
    $("frame-label").textContent = `${index + 1} / ${state.frames.length}`;
    $("time-label").textContent = `${((state.frameTimes[index] || 0) / 1000).toFixed(3)} s`;
    $("marker-label").textContent = markerFor(index) || "60 command segments · six repeated emitters per segment";
  }
  updatePaintHealth(now);
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
      state.pausedElapsedMs = state.frameTimes[state.manualIdx];
      state.lastPresentedOrdinal = null;
    }
  });
}

function setLoop(next, now = performance.now()) {
  let elapsed = state.playing ? now - state.t0 : state.pausedElapsedMs;
  if (elapsed >= 0 && state.durationMs > 0) elapsed %= state.durationMs;
  state.loop = next;
  state.pausedElapsedMs = elapsed;
  if (state.playing) state.t0 = now - elapsed;
  state.manualIdx = positionForElapsed(elapsed).index;
  state.lastPresentedOrdinal = null;
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
  $("source-kind").addEventListener("change", () => {
    state.frameRequestToken += 1;
    fillSourcePicker();
  });
  $("source-name").addEventListener("change", () => {
    state.frameRequestToken += 1;
    syncParamsFromSource();
  });
  $("render").addEventListener("click", doRender);
  $("replay-load").addEventListener("click", doReplayLoad);
  $("play-pause").addEventListener("click", () => (state.playing ? stopPlayback() : startPlayback()));
  $("loop").addEventListener("change", () => setLoop($("loop").checked));
  $("scrub").addEventListener("input", () => {
    stopPlayback();
    state.manualIdx = Number($("scrub").value) || 0;
    state.pausedElapsedMs = state.frameTimes[state.manualIdx] || 0;
    state.lastPresentedOrdinal = null;
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
