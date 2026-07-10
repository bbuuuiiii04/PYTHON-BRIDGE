// sim-app.js — LED room simulator page glue (AWR-196).
// Owns all state, fetching, transport, knobs, and calibration edits.
// The view (ledsim-view.js) draws only; profile edits live HERE.

import { createLedSimView } from "./ledsim-view.js";

const $ = (id) => document.getElementById(id);

const state = {
  profile: null,        // local working copy (knobs edit this)
  savedProfile: null,   // last server-confirmed profile
  catalog: null,
  frames: [],
  framesFps: 60,
  playing: false,
  loop: true,
  t0: 0,
  manualIdx: 0,
  display: null,        // slew state: floats per channel
  lastTick: 0,
  calibrating: false,
  drag: null,
};

let view = null;

// --- error banner ------------------------------------------------------------
function showError(message) {
  const el = $("error-banner");
  el.textContent = message;
  el.hidden = !message;
}

function showWarnings() {
  const bits = [];
  if (state.catalog?.profile_error) bits.push(`profile: ${state.catalog.profile_error}`);
  if (state.catalog?.lab_error) bits.push(`lab: ${state.catalog.lab_error}`);
  if (state.catalog?.looks && !state.catalog.looks.ok) bits.push(`looks: ${state.catalog.looks.error}`);
  const el = $("warnings");
  el.textContent = bits.join("  •  ");
  el.hidden = bits.length === 0;
}

async function api(method, path, body) {
  let resp;
  try {
    resp = await fetch(path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    showError(`fetch failed: ${err}`);
    throw err;
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail = data.errors ? data.errors.join("; ") : (data.error || resp.statusText);
    showError(`${path}: ${detail}`);
    throw new Error(detail);
  }
  showError("");
  return data;
}

// --- profile / knobs ------------------------------------------------------------
const KNOBS = [
  ["gamma", "knob-gamma"],
  ["brightness", "knob-brightness"],
  ["diffusion_width_seg", "knob-diffusion"],
  ["bleed", "knob-bleed"],
  ["wash_reach_mm", "knob-wash-reach"],
  ["wash_gain", "knob-wash-gain"],
  ["fps", "knob-fps"],
  ["latency_ms", "knob-latency"],
  ["slew_ms", "knob-slew"],
];

function knobsFromProfile() {
  const p = state.profile;
  for (const [key, id] of KNOBS) {
    $(id).value = p[key];
    $(`${id}-val`).textContent = String(p[key]);
  }
  for (let c = 0; c < 3; c += 1) {
    $(`knob-white-${c}`).value = p.white_point[c];
    $(`knob-white-${c}-val`).textContent = String(p.white_point[c]);
  }
  $("knob-hold").value = p.hold_mode;
  $("bpm").value = p.bpm;
  markDirty();
}

function markDirty() {
  const dirty = JSON.stringify(stripLocal(state.profile)) !== JSON.stringify(state.savedProfile);
  $("profile-dirty").hidden = !dirty;
}

function stripLocal(profile) {
  const copy = { ...profile };
  delete copy._calibrating;
  return copy;
}

function pushProfileToView() {
  const p = { ...state.profile, _calibrating: state.calibrating };
  view.setProfile(p);
  markDirty();
}

function wireKnobs() {
  for (const [key, id] of KNOBS) {
    $(id).addEventListener("input", () => {
      state.profile[key] = Number($(id).value);
      $(`${id}-val`).textContent = $(id).value;
      pushProfileToView();
    });
  }
  for (let c = 0; c < 3; c += 1) {
    $(`knob-white-${c}`).addEventListener("input", () => {
      state.profile.white_point[c] = Number($(`knob-white-${c}`).value);
      $(`knob-white-${c}-val`).textContent = $(`knob-white-${c}`).value;
      pushProfileToView();
    });
  }
  $("knob-hold").addEventListener("change", () => {
    state.profile.hold_mode = $("knob-hold").value;
    pushProfileToView();
  });

  $("profile-save").addEventListener("click", async () => {
    const payload = stripLocal(state.profile);
    const result = await api("POST", "/api/profile", payload);
    state.savedProfile = result.profile;
    markDirty();
  });

  $("profile-revert").addEventListener("click", async () => {
    const result = await api("GET", "/api/profile");
    state.profile = result.profile;
    state.savedProfile = JSON.parse(JSON.stringify(result.profile));
    knobsFromProfile();
    pushProfileToView();
  });
}

// --- sources -------------------------------------------------------------------
function fillSourcePicker() {
  const kind = $("source-kind").value;
  const select = $("source-name");
  select.innerHTML = "";
  $("replay-row").hidden = kind !== "replay";
  select.parentElement.hidden = kind === "replay";
  if (kind === "effect") {
    for (const name of state.catalog.effects) {
      select.add(new Option(name, name));
    }
  } else if (kind === "look") {
    const looks = state.catalog.looks.ok ? state.catalog.looks.looks : {};
    for (const [name, entry] of Object.entries(looks)) {
      select.add(new Option(`${name} → ${entry.effect}`, name));
    }
  } else if (kind === "lab") {
    for (const draft of state.catalog.lab.drafts || []) {
      select.add(new Option(`${draft.name} (${draft.status})`, draft.name));
    }
  }
  syncParamsFromSource();
}

function syncParamsFromSource() {
  const kind = $("source-kind").value;
  const name = $("source-name").value;
  if (kind === "look") {
    const entry = state.catalog.looks.ok ? state.catalog.looks.looks[name] : null;
    $("params").value = entry ? JSON.stringify(entry.params, null, 1) : "{}";
  } else if (kind === "lab") {
    const draft = (state.catalog.lab.drafts || []).find((d) => d.name === name);
    $("params").value = draft ? JSON.stringify(draft.params || {}, null, 1) : "{}";
  }
}

function renderRequestBody() {
  const kind = $("source-kind").value;
  let params;
  try {
    params = JSON.parse($("params").value || "{}");
  } catch (err) {
    showError(`params is not valid JSON: ${err}`);
    return null;
  }
  let source = "effect";
  let name = $("source-name").value;
  if (kind === "look") {
    const entry = state.catalog.looks.ok ? state.catalog.looks.looks[name] : null;
    if (!entry) { showError("unknown look"); return null; }
    name = entry.effect;
  } else if (kind === "lab") {
    source = "lab";
  }
  return {
    source,
    name,
    params,
    seed: Number($("seed").value) || 0,
    fps: Number(state.profile.fps) || 60,
    duration_s: Number($("duration").value) || 4,
    bpm: Number($("bpm").value) || 128,
  };
}

async function doRender() {
  const body = renderRequestBody();
  if (!body) return;
  const result = await api("POST", "/api/render", body);
  loadFrames(result.frames, result.fps);
}

async function doReplayLoad() {
  const path = $("replay-path").value.trim();
  if (!path) { showError("enter a frames-JSONL path (repo-relative or /tmp)"); return; }
  const result = await api("POST", "/api/replay/load", { path });
  loadFrames(result.frames, result.fps);
}

async function doTestCard(kind) {
  const result = await api("POST", "/api/render_card", { kind });
  loadFrames(result.frames, result.fps);
  stopPlayback(); // static card: hold frame 0
}

function loadFrames(frames, fps) {
  state.frames = frames;
  state.framesFps = fps || 60;
  state.manualIdx = 0;
  state.display = null;
  $("scrub").max = String(Math.max(0, frames.length - 1));
  $("scrub").value = "0";
  startPlayback();
}

// --- transport -------------------------------------------------------------------
function startPlayback() {
  if (!state.frames.length) return;
  state.playing = true;
  state.t0 = performance.now();
  $("play-pause").textContent = "Pause";
}

function stopPlayback() {
  state.playing = false;
  $("play-pause").textContent = "Play";
}

function currentIndex(now) {
  const n = state.frames.length;
  if (!n) return 0;
  if (!state.playing) return Math.min(state.manualIdx, n - 1);
  const latency = Number(state.profile.latency_ms) || 0;
  // idx = floor((now - t0 - latency_ms) * fps / 1000), looped or clamped
  const raw = Math.floor(((now - state.t0 - latency) * state.framesFps) / 1000);
  if (raw < 0) return 0;
  if (state.loop) return raw % n;
  if (raw >= n) { stopPlayback(); state.manualIdx = n - 1; return n - 1; }
  return raw;
}

function tick(now) {
  if (view && state.frames.length) {
    const idx = currentIndex(now);
    $("scrub").value = String(idx);
    $("frame-label").textContent = `${idx + 1}/${state.frames.length}`;
    const target = state.frames[idx];
    let shown = target;
    if (state.profile.hold_mode === "slew") {
      // Models unknown IC response: per-channel lerp with time constant slew_ms.
      const tau = Math.max(1, Number(state.profile.slew_ms) || 0);
      const dt = Math.min(200, now - (state.lastTick || now));
      const k = 1 - Math.exp(-dt / tau);
      if (!state.display || state.display.length !== target.length) {
        state.display = target.map((px) => px.slice());
      } else {
        for (let i = 0; i < target.length; i += 1) {
          for (let c = 0; c < 3; c += 1) {
            state.display[i][c] += (target[i][c] - state.display[i][c]) * k;
          }
        }
      }
      shown = state.display.map((px) => px.map(Math.round));
    } else {
      state.display = null;
    }
    view.renderFrame(shown);
  }
  state.lastTick = now;
  requestAnimationFrame(tick);
}

// --- calibration -------------------------------------------------------------------
// mirror of the app-side corner normalization contract described in
// docs/guides/led_sim.md; geometry itself mirrors led_sim_engine.segment_geometry.
function normalizeCorners() {
  const seg = state.profile.segments;
  let cs = state.profile.corner_segments.map((v) => ((v % seg) + seg) % seg);
  // rotate so the list is ascending again; arc k follows wall (start_corner + k)
  let rot = 0;
  for (let i = 1; i < 4; i += 1) {
    if (cs[i] < cs[i - 1]) { rot = i; break; }
  }
  if (rot) {
    cs = cs.slice(rot).concat(cs.slice(0, rot));
    state.profile.start_corner = (state.profile.start_corner + rot) % 4;
  }
  state.profile.corner_segments = cs;
}

function clampCorner(k, next) {
  const seg = state.profile.segments;
  const cs = state.profile.corner_segments;
  const margin = 0.1;
  const prev = k > 0 ? cs[k - 1] + margin : cs[3] - seg + margin;
  const nxt = k < 3 ? cs[k + 1] - margin : cs[0] + seg - margin;
  return Math.max(prev, Math.min(nxt, next));
}

function wireCanvas(canvas) {
  canvas.addEventListener("pointerdown", (ev) => {
    if (!state.calibrating) return;
    const rect = canvas.getBoundingClientRect();
    const x = (ev.clientX - rect.left) * (canvas.width / rect.width);
    const y = (ev.clientY - rect.top) * (canvas.height / rect.height);
    const hit = view.hitTest(x, y);
    if (!hit) return;
    state.drag = { hit, lastX: x, lastY: y, moved: 0 };
    canvas.setPointerCapture(ev.pointerId);
  });

  canvas.addEventListener("pointermove", (ev) => {
    if (!state.drag) return;
    const rect = canvas.getBoundingClientRect();
    const x = (ev.clientX - rect.left) * (canvas.width / rect.width);
    const y = (ev.clientY - rect.top) * (canvas.height / rect.height);
    const dx = x - state.drag.lastX;
    const dy = y - state.drag.lastY;
    state.drag.lastX = x;
    state.drag.lastY = y;
    state.drag.moved += Math.abs(dx) + Math.abs(dy);
    const { hit } = state.drag;
    if (hit.type === "corner") {
      const ds = (dx * hit.tangent[0] + dy * hit.tangent[1]) * hit.segPerPx;
      const cs = state.profile.corner_segments;
      cs[hit.index] = clampCorner(hit.index, cs[hit.index] + ds);
      pushProfileToView();
    } else if (hit.type === "start") {
      // Sliding segment 0 shifts the whole ring mapping.
      const ds = (dx * hit.tangent[0] + dy * hit.tangent[1]) * hit.segPerPx;
      state.profile.corner_segments = state.profile.corner_segments.map((v) => v - ds);
      normalizeCorners();
      pushProfileToView();
    }
  });

  canvas.addEventListener("pointerup", () => {
    if (state.drag && state.drag.hit.type === "direction" && state.drag.moved < 6) {
      state.profile.direction = state.profile.direction === "ccw" ? "cw" : "ccw";
      pushProfileToView();
    }
    state.drag = null;
  });
}

async function slowChasePreset() {
  $("source-kind").value = "effect";
  fillSourcePicker();
  $("source-name").value = "beat_chase";
  $("bpm").value = "60";
  $("duration").value = "8";
  await doRender();
}

// --- boot ------------------------------------------------------------------------
async function boot() {
  const canvas = $("room-canvas");
  const catalog = await api("GET", "/api/catalog");
  state.catalog = catalog;
  state.profile = catalog.profile;
  state.savedProfile = JSON.parse(JSON.stringify(catalog.profile));
  view = createLedSimView(canvas, state.profile);
  showWarnings();
  fillSourcePicker();
  knobsFromProfile();
  pushProfileToView();
  wireKnobs();
  wireCanvas(canvas);

  $("source-kind").addEventListener("change", fillSourcePicker);
  $("source-name").addEventListener("change", syncParamsFromSource);
  $("render").addEventListener("click", doRender);
  $("replay-load").addEventListener("click", doReplayLoad);
  $("play-pause").addEventListener("click", () => (state.playing ? stopPlayback() : startPlayback()));
  $("loop").addEventListener("change", () => { state.loop = $("loop").checked; });
  $("scrub").addEventListener("input", () => {
    stopPlayback();
    state.manualIdx = Number($("scrub").value) || 0;
  });
  $("calibrate-toggle").addEventListener("click", () => {
    state.calibrating = !state.calibrating;
    $("calibrate-panel").hidden = !state.calibrating;
    $("calibrate-toggle").textContent = state.calibrating ? "Exit calibrate" : "Calibrate…";
    pushProfileToView();
  });
  $("preset-slow-chase").addEventListener("click", slowChasePreset);
  for (const button of document.querySelectorAll("[data-card]")) {
    button.addEventListener("click", () => doTestCard(button.dataset.card));
  }

  requestAnimationFrame(tick);
}

boot().catch((err) => showError(`boot failed: ${err}`));
