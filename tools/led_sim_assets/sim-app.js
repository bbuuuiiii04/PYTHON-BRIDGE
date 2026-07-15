// sim-app.js — H612D LED Studio lighting-console controller (AWR-244 R3).

import {
  createLedSimView,
  defaultLayout,
  feetToMm,
  formatLengthMm,
  mmToFeet,
  perimeterPresetPoints,
  resolveLayout,
  snakePresetPoints,
} from "./ledsim-view.js";

const $ = (id) => document.getElementById(id);

const LAYOUT_KEYS = ["room_mm", "layout", "layout_locked"];
const CALIBRATION_KEYS = [
  "gamma", "white_point", "brightness", "glow_radius", "glow_gain", "bleed",
  "fps", "latency_ms", "hold_mode", "slew_ms", "bpm",
  "calibration_status", "calibration_domains", "calibration_evidence",
  "calibration_locked",
];
const UNDO_LIMIT = 20;
const LONG_PRESS_MOVE_PX = 6;

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
  layoutUndoStack: [],
  lastChosenPreset: "perimeter",
  dragVertex: -1,
  selectedVertex: -1,
  longPressTimer: null,
  longPressPoint: null,
  longPressStart: null,
  activeTab: "play",
  _labelsUserSet: false,
};

let view = null;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

/** U-10: deep-ish clone for profile POST bodies (no local-only keys today). */
function cloneProfile(profile) {
  return clone(profile);
}

function pickKeys(profile, keys) {
  const out = {};
  for (const key of keys) {
    if (profile && Object.prototype.hasOwnProperty.call(profile, key)) {
      out[key] = profile[key];
    }
  }
  return out;
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

function showLayoutWarnings(list) {
  const element = $("layout-warnings");
  if (!element) return;
  const items = Array.isArray(list) ? list.filter(Boolean) : [];
  element.textContent = items.join("  •  ");
  element.hidden = items.length === 0;
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

function layoutLocked() {
  return state.profile?.layout_locked === true;
}

function calibrationLocked() {
  return state.profile?.calibration_locked === true;
}

function markDirty() {
  // U-3: scope each dirty badge to its subsystem keys.
  const layoutDirty = JSON.stringify(pickKeys(state.profile, LAYOUT_KEYS))
    !== JSON.stringify(pickKeys(state.savedProfile, LAYOUT_KEYS));
  const calibDirty = JSON.stringify(pickKeys(state.profile, CALIBRATION_KEYS))
    !== JSON.stringify(pickKeys(state.savedProfile, CALIBRATION_KEYS));
  $("layout-dirty").hidden = !layoutDirty;
  $("profile-dirty").hidden = !calibDirty;
}

function updateCalibrationBadge() {
  const candidate = String(state.profile.calibration_status);
  const status = ["unmeasured", "relative", "measured"].includes(candidate) ? candidate : "unmeasured";
  const badge = $("calibration-badge");
  badge.textContent = status.toUpperCase();
  badge.classList.toggle("warn", status !== "measured");
}

function calibrationSupportsSlew() {
  const allowed = ["relative", "measured"];
  const status = String(state.profile.calibration_status);
  const timingStatus = state.profile.calibration_domains?.timing;
  return allowed.includes(status) && allowed.includes(String(timingStatus));
}

function invalidateCalibration() {
  state.profile.calibration_status = "unmeasured";
  state.profile.calibration_domains = {color: "unmeasured", timing: "unmeasured", spatial: "unmeasured"};
  state.profile.calibration_evidence = {};
  for (const key of [
    "calibration_evidence_id", "calibration_measured_at",
    "measurement_evidence", "measurement_id", "measured_at", "evidence",
  ]) delete state.profile[key];
  state.display = null;
  state.lastPresentedOrdinal = null;
}

function syncEditGestureClass() {
  const wrap = $("canvas-wrap");
  const editing = state.activeTab === "layout" && !layoutLocked() && view?.getViewMode() === "room";
  wrap.classList.toggle("edit-gestures", Boolean(editing));
}

function syncLockUi() {
  const layoutLock = layoutLocked();
  const calibLock = calibrationLocked();
  const layoutBtn = $("layout-lock");
  layoutBtn.setAttribute("aria-pressed", layoutLock ? "true" : "false");
  layoutBtn.textContent = layoutLock ? "🔒 Locked" : "🔓 Unlock";
  const calibBtn = $("calibration-lock");
  calibBtn.setAttribute("aria-pressed", calibLock ? "true" : "false");
  calibBtn.textContent = calibLock ? "🔒 Locked" : "🔓 Unlock";
  $("lock-chip").hidden = !(layoutLock && view?.getViewMode() === "room");

  for (const id of ["room-width-ft", "room-height-ft", "layout-flip", "layout-reset"]) {
    $(id).disabled = layoutLock;
  }
  for (const button of document.querySelectorAll(".preset-card")) {
    button.disabled = layoutLock;
  }
  const calibRoot = $("calibration-controls");
  if (calibRoot) {
    for (const el of calibRoot.querySelectorAll("input, select, textarea, button")) {
      el.disabled = calibLock;
    }
  }
  $("knob-hold").disabled = calibLock;
  $("profile-save").disabled = calibLock;
  $("profile-revert").disabled = false;

  const roomEditing = view?.getViewMode() === "room" && state.activeTab === "layout" && !layoutLock;
  view?.setEditing(Boolean(roomEditing));
  syncEditGestureClass();
  updateResetLabel();
}

function pushProfileToView() {
  view.setProfile(state.profile);
  markDirty();
  updateCalibrationBadge();
  syncLayoutForm();
  syncLockUi();
}

function ensureProfileLayout() {
  if (!state.profile.room_mm || state.profile.room_mm.length !== 2) {
    state.profile.room_mm = [5216, 2284];
  }
  if (typeof state.profile.layout_locked !== "boolean") state.profile.layout_locked = false;
  if (typeof state.profile.calibration_locked !== "boolean") state.profile.calibration_locked = false;
  state.profile.layout = resolveLayout(state.profile);
  return state.profile.layout;
}

function pushUndo() {
  ensureProfileLayout();
  state.layoutUndoStack.push(clone({
    room_mm: state.profile.room_mm,
    layout: state.profile.layout,
  }));
  if (state.layoutUndoStack.length > UNDO_LIMIT) state.layoutUndoStack.shift();
  syncUndoButton();
}

function syncUndoButton() {
  const button = $("layout-undo");
  button.disabled = state.layoutUndoStack.length === 0 || layoutLocked();
}

function undoLayout() {
  if (!state.layoutUndoStack.length || layoutLocked()) return;
  const previous = state.layoutUndoStack.pop();
  state.profile.room_mm = previous.room_mm;
  state.profile.layout = previous.layout;
  syncUndoButton();
  pushProfileToView();
  refreshPresetThumbs();
}

function markLayoutCustom() {
  ensureProfileLayout();
  state.profile.layout.preset = "custom";
  syncPresetCards();
  updateResetLabel();
}

function updateResetLabel() {
  const name = state.lastChosenPreset === "snake" ? "Snake" : "Perimeter";
  $("layout-reset").textContent = `Reset to ${name}`;
}

function syncPresetCards() {
  const preset = ensureProfileLayout().preset;
  for (const button of document.querySelectorAll(".preset-card")) {
    button.setAttribute("aria-selected", button.dataset.preset === preset ? "true" : "false");
  }
}

function syncLayoutForm() {
  ensureProfileLayout();
  const widthMm = Number(state.profile.room_mm[0]);
  const heightMm = Number(state.profile.room_mm[1]);
  $("room-width-ft").value = String(Math.round(mmToFeet(widthMm) * 10) / 10);
  $("room-height-ft").value = String(Math.round(mmToFeet(heightMm) * 10) / 10);
  $("room-width-mm-hint").textContent = `${Math.round(widthMm)} mm`;
  $("room-height-mm-hint").textContent = `${Math.round(heightMm)} mm`;
  syncPresetCards();
  updatePathLengthStatus();
  markDirty();
  const warnings = state.catalog?.profile_warnings || [];
  showLayoutWarnings(warnings);
  // Client-side soft bounds check mirrors engine profile_warnings.
  const roomW = widthMm;
  const roomH = heightMm;
  const tol = 2;
  let outside = 0;
  for (const point of state.profile.layout.points_mm || []) {
    const x = Number(point[0]);
    const y = Number(point[1]);
    if (x < -tol || y < -tol || x > roomW + tol || y > roomH + tol) outside += 1;
  }
  if (outside) {
    showLayoutWarnings([
      ...warnings,
      `${outside} layout point${outside === 1 ? "" : "s"} outside room bounds (±${tol} mm tolerance)`,
    ]);
  }
}

function updatePathLengthStatus() {
  if (!view) return;
  const layout = view.getLayout();
  const status = $("path-length-status");
  if (layout.unplaced_mm > 0) {
    status.className = "dim-bar warn";
    status.textContent = `Path ${layout.path_label} / Strip ${layout.strip_label} — ${formatLengthMm(layout.unplaced_mm)} unplaced`;
  } else if (layout.excess_path_mm > 0) {
    status.className = "dim-bar ok";
    status.textContent = `Path ${layout.path_label} / Strip ${layout.strip_label} — strip ends at 49.2 ft; extra path is a dashed guide`;
  } else {
    status.className = "dim-bar ok";
    status.textContent = `Path ${layout.path_label} · Strip ${layout.strip_label} · pitch 41.656 mm/LED`;
  }
}

function drawPresetThumb(canvas, points, room) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#06080b";
  ctx.fillRect(0, 0, width, height);
  const [roomW, roomH] = room;
  const pad = 8;
  const scale = Math.min((width - pad * 2) / roomW, (height - pad * 2) / roomH);
  const ox = (width - roomW * scale) / 2;
  const oy = (height - roomH * scale) / 2;
  ctx.strokeStyle = "rgba(255,255,255,.12)";
  ctx.strokeRect(ox, oy, roomW * scale, roomH * scale);
  if (!points?.length) return;
  const toX = (x) => ox + x * scale;
  const toY = (y) => oy + (roomH - y) * scale;
  ctx.strokeStyle = "#4dd8e6";
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(toX(points[0][0]), toY(points[0][1]));
  for (let index = 1; index < points.length; index += 1) {
    ctx.lineTo(toX(points[index][0]), toY(points[index][1]));
  }
  ctx.stroke();
}

function refreshPresetThumbs() {
  const room = state.profile?.room_mm || [5216, 2284];
  drawPresetThumb($("thumb-perimeter"), perimeterPresetPoints(room), room);
  drawPresetThumb($("thumb-snake"), snakePresetPoints(room), room);
}

function applyPreset(preset) {
  if (layoutLocked()) return;
  pushUndo();
  ensureProfileLayout();
  const room = state.profile.room_mm;
  if (preset === "custom") {
    state.profile.layout.preset = "custom";
  } else {
    state.lastChosenPreset = preset;
    state.profile.layout = {
      preset,
      points_mm: preset === "snake" ? snakePresetPoints(room) : perimeterPresetPoints(room),
      flip_chain: typeof state.profile.layout.flip_chain === "boolean"
        ? state.profile.layout.flip_chain
        : false,
    };
  }
  pushProfileToView();
  refreshPresetThumbs();
}

function canvasEventPoint(event) {
  const rect = $("fixture-canvas").getBoundingClientRect();
  const source = event.touches?.[0] || event.changedTouches?.[0] || event;
  return {
    x: source.clientX - rect.left,
    y: source.clientY - rect.top,
  };
}

function setActiveTab(tab) {
  state.activeTab = tab;
  for (const name of ["play", "layout", "calibrate"]) {
    const panelEl = $(`${name}-panel`);
    panelEl.hidden = name !== tab;
    const tabBtn = $(`tab-${name}`);
    tabBtn.classList.toggle("active", name === tab);
    tabBtn.setAttribute("aria-pressed", name === tab ? "true" : "false");
  }
  for (const btn of document.querySelectorAll(".rail-btn[data-tab]")) {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  }
  document.body.classList.remove("sheet-collapsed");
  $("sheet-toggle")?.setAttribute("aria-expanded", "true");
  syncLockUi();
}

function wireShell() {
  for (const btn of document.querySelectorAll("[data-tab]")) {
    btn.addEventListener("click", () => {
      if (btn.dataset.tab) setActiveTab(btn.dataset.tab);
    });
  }
  $("sidecar-collapse").addEventListener("click", () => {
    document.body.classList.toggle("sidecar-collapsed");
    const collapsed = document.body.classList.contains("sidecar-collapsed");
    $("sidecar-collapse").textContent = collapsed ? "›" : "‹";
    $("sidecar-collapse").setAttribute("aria-label", collapsed ? "Expand sidecar" : "Collapse sidecar");
  });
  $("sheet-toggle")?.addEventListener("click", () => {
    document.body.classList.toggle("sheet-collapsed");
    const collapsed = document.body.classList.contains("sheet-collapsed");
    $("sheet-toggle").setAttribute("aria-expanded", collapsed ? "false" : "true");
  });
  // Mobile sheet starts expanded on layout-capable widths; collapse chrome on tiny screens.
  if (window.innerWidth < 900) {
    document.body.classList.add("sheet-collapsed");
    $("sheet-toggle")?.setAttribute("aria-expanded", "false");
  }
  $("help-btn").addEventListener("click", () => {
    const pop = $("help-popover");
    const open = pop.hidden;
    pop.hidden = !open;
    $("help-btn").setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.addEventListener("click", (event) => {
    const pop = $("help-popover");
    if (pop.hidden) return;
    if (pop.contains(event.target) || $("help-btn").contains(event.target)) return;
    pop.hidden = true;
    $("help-btn").setAttribute("aria-expanded", "false");
  });
  $("top-stop").addEventListener("click", () => stopPlayback());
}

function wireLayoutEditor() {
  const labelsDefault = window.innerWidth >= 700;
  $("toggle-labels").setAttribute("aria-pressed", labelsDefault ? "true" : "false");
  view.setLabelsVisible(labelsDefault);

  $("view-room").addEventListener("click", () => {
    view.setViewMode("room");
    $("view-room").classList.add("active");
    $("view-room").setAttribute("aria-pressed", "true");
    $("view-strip").classList.remove("active");
    $("view-strip").setAttribute("aria-pressed", "false");
    syncLockUi();
  });
  $("view-strip").addEventListener("click", () => {
    view.setViewMode("strip");
    $("view-strip").classList.add("active");
    $("view-strip").setAttribute("aria-pressed", "true");
    $("view-room").classList.remove("active");
    $("view-room").setAttribute("aria-pressed", "false");
    view.setEditing(false);
    $("lock-chip").hidden = true;
    syncEditGestureClass();
  });
  $("toggle-labels").addEventListener("click", () => {
    state._labelsUserSet = true;
    const next = $("toggle-labels").getAttribute("aria-pressed") !== "true";
    $("toggle-labels").setAttribute("aria-pressed", next ? "true" : "false");
    view.setLabelsVisible(next);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth < 700 && $("toggle-labels").getAttribute("aria-pressed") === "true" && !state._labelsUserSet) {
      $("toggle-labels").setAttribute("aria-pressed", "false");
      view.setLabelsVisible(false);
    }
  });

  for (const button of document.querySelectorAll(".preset-card")) {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  }

  const onRoomSize = () => {
    if (layoutLocked()) return;
    pushUndo();
    const widthFt = Math.max(1, Number($("room-width-ft").value) || mmToFeet(5216));
    const heightFt = Math.max(1, Number($("room-height-ft").value) || mmToFeet(2284));
    state.profile.room_mm = [feetToMm(widthFt), feetToMm(heightFt)];
    const preset = ensureProfileLayout().preset;
    if (preset === "perimeter" || preset === "snake") {
      state.profile.layout.points_mm = preset === "snake"
        ? snakePresetPoints(state.profile.room_mm)
        : perimeterPresetPoints(state.profile.room_mm);
    }
    pushProfileToView();
    refreshPresetThumbs();
  };
  $("room-width-ft").addEventListener("change", onRoomSize);
  $("room-height-ft").addEventListener("change", onRoomSize);

  $("layout-flip").addEventListener("click", () => {
    if (layoutLocked()) return;
    pushUndo();
    ensureProfileLayout();
    state.profile.layout.flip_chain = !state.profile.layout.flip_chain;
    pushProfileToView();
  });
  $("layout-reset").addEventListener("click", () => {
    if (layoutLocked()) return;
    applyPreset(state.lastChosenPreset === "snake" ? "snake" : "perimeter");
  });
  $("layout-undo").addEventListener("click", undoLayout);
  $("layout-save").addEventListener("click", async () => {
    ensureProfileLayout();
    const result = await api("POST", "/api/profile", cloneProfile(state.profile));
    state.savedProfile = clone(result.profile);
    state.catalog.profile_warnings = result.warnings || [];
    markDirty();
    showLayoutWarnings(result.warnings || []);
  });
  $("layout-lock").addEventListener("click", () => {
    state.profile.layout_locked = !layoutLocked();
    markDirty();
    syncLockUi();
  });

  const canvas = $("fixture-canvas");
  const HIT = 32;

  function clearLongPress() {
    if (state.longPressTimer) {
      clearTimeout(state.longPressTimer);
      state.longPressTimer = null;
    }
    state.longPressPoint = null;
    state.longPressStart = null;
  }

  function editsAllowed() {
    return view.getViewMode() === "room" && state.activeTab === "layout" && !layoutLocked();
  }

  function pointerDown(event) {
    if (!editsAllowed()) return;
    const point = canvasEventPoint(event);
    const vertex = view.hitTestVertex(point.x, point.y, HIT);
    if (vertex >= 0) {
      event.preventDefault();
      pushUndo();
      state.dragVertex = vertex;
      state.selectedVertex = vertex;
      canvas.setPointerCapture?.(event.pointerId);
      return;
    }
    state.longPressPoint = point;
    state.longPressStart = point;
    state.longPressTimer = setTimeout(() => {
      if (state.longPressPoint) mutateAtCanvasPoint(state.longPressPoint);
      clearLongPress();
    }, 550);
  }

  function storedIndex(displayIndex) {
    const count = ensureProfileLayout().points_mm.length;
    return state.profile.layout.flip_chain ? count - 1 - displayIndex : displayIndex;
  }

  function insertIndexForEdge(displayEdgeIndex) {
    const count = ensureProfileLayout().points_mm.length;
    if (!state.profile.layout.flip_chain) return displayEdgeIndex + 1;
    return count - 1 - displayEdgeIndex;
  }

  function mutateAtCanvasPoint(point) {
    if (!editsAllowed()) return;
    const vertexHit = view.hitTestVertex(point.x, point.y, HIT);
    ensureProfileLayout();
    if (vertexHit >= 0) {
      if (state.profile.layout.points_mm.length <= 2) return;
      pushUndo();
      state.profile.layout.points_mm.splice(storedIndex(vertexHit), 1);
      state.selectedVertex = -1;
      markLayoutCustom();
      pushProfileToView();
      return;
    }
    const edge = view.hitTestEdge(point.x, point.y, HIT);
    if (!edge) return;
    pushUndo();
    state.profile.layout.points_mm.splice(insertIndexForEdge(edge.edgeIndex), 0, [edge.mm.x, edge.mm.y]);
    markLayoutCustom();
    pushProfileToView();
  }

  function pointerMove(event) {
    // U-1: cancel long-press insert once movement exceeds ~6px.
    if (state.longPressTimer && state.longPressStart) {
      const point = canvasEventPoint(event);
      const moved = Math.hypot(point.x - state.longPressStart.x, point.y - state.longPressStart.y);
      if (moved > LONG_PRESS_MOVE_PX) clearLongPress();
    }
    if (state.dragVertex < 0 || !editsAllowed()) return;
    event.preventDefault();
    const point = canvasEventPoint(event);
    const mm = view.canvasToMm(point.x, point.y);
    ensureProfileLayout();
    const points = state.profile.layout.points_mm.map((entry) => [entry[0], entry[1]]);
    points[storedIndex(state.dragVertex)] = [mm.x, mm.y];
    state.profile.layout.points_mm = points;
    state.selectedVertex = state.dragVertex;
    markLayoutCustom();
    pushProfileToView();
  }

  function pointerUp(event) {
    clearLongPress();
    if (state.dragVertex >= 0) {
      state.dragVertex = -1;
      try { canvas.releasePointerCapture?.(event.pointerId); } catch (_error) { /* ignore */ }
    }
  }

  canvas.addEventListener("pointerdown", pointerDown);
  canvas.addEventListener("pointermove", pointerMove);
  canvas.addEventListener("pointerup", pointerUp);
  canvas.addEventListener("pointercancel", pointerUp);
  canvas.addEventListener("dblclick", (event) => {
    if (!editsAllowed()) return;
    event.preventDefault();
    mutateAtCanvasPoint(canvasEventPoint(event));
  });
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
  syncLockUi();
}

function wireKnobs() {
  for (const [key, id] of KNOBS) {
    $(id).addEventListener("input", () => {
      if (calibrationLocked()) return;
      state.profile[key] = Number($(id).value);
      $(`${id}-val`).textContent = $(id).value;
      invalidateCalibration();
      pushProfileToView();
    });
  }
  for (let channel = 0; channel < 3; channel += 1) {
    $(`knob-white-${channel}`).addEventListener("input", () => {
      if (calibrationLocked()) return;
      state.profile.white_point[channel] = Number($(`knob-white-${channel}`).value);
      $(`knob-white-${channel}-val`).textContent = $(`knob-white-${channel}`).value;
      invalidateCalibration();
      pushProfileToView();
    });
  }
  $("knob-hold").addEventListener("change", () => {
    if (calibrationLocked()) return;
    state.profile.hold_mode = $("knob-hold").value;
    invalidateCalibration();
    pushProfileToView();
  });

  $("profile-save").addEventListener("click", async () => {
    if (calibrationLocked()) return;
    const result = await api("POST", "/api/profile", cloneProfile(state.profile));
    state.savedProfile = clone(result.profile);
    state.catalog.profile_warnings = result.warnings || [];
    markDirty();
  });
  $("profile-revert").addEventListener("click", async () => {
    const result = await api("GET", "/api/profile");
    state.profile = result.profile;
    state.savedProfile = clone(result.profile);
    state.catalog.profile_warnings = result.profile_warnings || [];
    state.display = null;
    state.lastPresentedOrdinal = null;
    knobsFromProfile();
    pushProfileToView();
  });
  $("calibration-lock").addEventListener("click", () => {
    state.profile.calibration_locked = !calibrationLocked();
    markDirty();
    syncLockUi();
  });
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
    look: "Render configured look",
    effect: "Render effect",
    lab: "Render lab draft",
  }[kind] || "Render";

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
      showError("Choose a configured look first.");
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
  loadFrames(result.frames, result.fps, result.t_ms, [], {
    durationMs: result.duration_ms,
    durationSource: result.duration_source,
    provenance: result.frame_source || result.provenance || result.pipeline || "server render",
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
  loadFrames(result.frames, result.fps, result.t_ms, result.meta?.markers || [], {
    durationMs: result.duration_ms ?? result.meta?.duration_ms,
    durationSource: result.duration_source,
    provenance: result.frame_source || result.provenance || result.meta?.frame_source || result.meta?.provenance || "recorded JSONL",
    timingSource: result.timing_source || result.meta?.timing_source,
  });
}

async function doTestCard(kind) {
  const result = await latestFrameRequest("/api/render_card", {kind});
  if (!result) return;
  loadFrames(result.frames, result.fps, result.t_ms, [{frame: 0, label: kind}], {
    durationMs: result.duration_ms,
    durationSource: result.duration_source,
    provenance: result.frame_source || result.provenance || "generated reference",
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
  loadFrames(result.frames, result.fps, result.t_ms, result.markers, {
    durationMs: result.duration_ms,
    durationSource: result.duration_source,
    provenance: result.frame_source || result.provenance || "generated calibration",
    timingSource: result.timing_source,
  });
}

function buildTimeline(frameCount, fps, supplied, explicitDuration, reportedSource, reportedDurationSource) {
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
    return {
      frameTimes,
      durationMs: explicit,
      timingSource,
      durationSource: reportedDurationSource || "explicit duration",
    };
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
    options.durationSource,
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
  $("fps-chip").textContent = `${state.framesFps} FPS`;
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
  if (!state.frames.length) return {index: 0, ordinal: 0, ended: false, pending: false};
  if (elapsed < 0) return {index: 0, ordinal: null, ended: false, pending: true};
  if (state.loop && state.durationMs > 0) {
    const cycle = Math.floor(elapsed / state.durationMs);
    const local = elapsed - cycle * state.durationMs;
    const index = indexAtTime(local);
    return {index, ordinal: cycle * state.frames.length + index, ended: false, pending: false};
  }
  if (!state.loop && elapsed >= state.durationMs) {
    const index = state.frames.length - 1;
    return {index, ordinal: index, ended: true, pending: false};
  }
  const index = indexAtTime(elapsed);
  return {index, ordinal: index, ended: false, pending: false};
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
  $("paint-health").textContent = `DRAW ${drawRate.toFixed(0)}`;
  $("fps-chip").textContent = `${drawRate.toFixed(0)} FPS`;
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
    if (position.pending) {
      $("marker-label").textContent = "Holding the previous output for measured latency";
      $("time-label").textContent = "LATENCY";
    } else if (state.lastPresentedOrdinal !== position.ordinal || slewing) {
      if (state.lastPresentedOrdinal !== null && position.ordinal > state.lastPresentedOrdinal + 1) {
        state.missedFrames += position.ordinal - state.lastPresentedOrdinal - 1;
      }
      view.renderFrame(applyMeasuredSlew(state.frames[index], now));
      state.drawCount += 1;
      state.lastPresentedOrdinal = position.ordinal;
    }
    if (!position.pending) {
      state.manualIdx = index;
      $("scrub").value = String(index);
      $("frame-label").textContent = `${index + 1} / ${state.frames.length}`;
      $("time-label").textContent = `${((state.frameTimes[index] || 0) / 1000).toFixed(3)} s`;
      $("marker-label").textContent = markerFor(index) || "60 command segments · display calibration applied";
    }
  }
  updatePaintHealth(now);
  state.lastTick = now;
  requestAnimationFrame(tick);
}

function nudgeSelectedVertex(dxMm, dyMm) {
  if (layoutLocked() || state.selectedVertex < 0 || view.getViewMode() !== "room") return;
  ensureProfileLayout();
  const count = state.profile.layout.points_mm.length;
  const displayIndex = state.selectedVertex;
  const stored = state.profile.layout.flip_chain ? count - 1 - displayIndex : displayIndex;
  pushUndo();
  const point = state.profile.layout.points_mm[stored];
  state.profile.layout.points_mm[stored] = [Number(point[0]) + dxMm, Number(point[1]) + dyMm];
  markLayoutCustom();
  pushProfileToView();
}

function wireKeyboard() {
  document.addEventListener("keydown", (event) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      undoLayout();
      return;
    }
    if (event.code === "Space") {
      event.preventDefault();
      state.playing ? stopPlayback() : startPlayback();
      return;
    }
    if (event.key === "l" || event.key === "L") {
      event.preventDefault();
      $("toggle-labels").click();
      return;
    }
    if (event.key === "?" || (event.shiftKey && event.key === "/")) {
      $("help-btn").click();
      return;
    }
    const arrow = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key);
    if (arrow && state.selectedVertex >= 0 && !layoutLocked() && state.activeTab === "layout") {
      event.preventDefault();
      const step = event.shiftKey ? 100 : 10;
      const dx = event.key === "ArrowRight" ? step : event.key === "ArrowLeft" ? -step : 0;
      const dy = event.key === "ArrowUp" ? step : event.key === "ArrowDown" ? -step : 0;
      nudgeSelectedVertex(dx, dy);
      return;
    }
    if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && state.frames.length) {
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
  $("loop").setAttribute("aria-pressed", next ? "true" : "false");
}

async function boot() {
  // U-8: modality-aware gesture copy
  const coarse = window.matchMedia?.("(pointer: coarse)")?.matches;
  $("layout-gesture-copy").textContent = coarse
    ? "Drag vertices on the room. Long-press an edge to add a point, a vertex to remove one. LED spacing is fixed — the path is never stretched."
    : "Drag vertices on the room. Double-click an edge to add a point, a vertex to remove one. On touch devices, long-press does the same. LED spacing is fixed — the path is never stretched.";

  state.catalog = await api("GET", "/api/catalog");
  state.profile = state.catalog.profile;
  if (!state.profile.layout) {
    state.profile.layout = defaultLayout(state.profile.room_mm || [5216, 2284]);
  }
  if (!state.profile.room_mm) state.profile.room_mm = [5216, 2284];
  if (typeof state.profile.layout_locked !== "boolean") state.profile.layout_locked = false;
  if (typeof state.profile.calibration_locked !== "boolean") state.profile.calibration_locked = false;
  const preset = state.profile.layout?.preset;
  if (preset === "snake" || preset === "perimeter") state.lastChosenPreset = preset;
  state.savedProfile = clone(state.catalog.profile);
  view = createLedSimView($("fixture-canvas"), state.profile);
  view.renderFrame(Array.from({length: 60}, () => [0, 0, 0]));
  showWarnings();
  showLayoutWarnings(state.catalog.profile_warnings || []);
  fillSourcePicker();
  knobsFromProfile();
  wireKnobs();
  wireShell();
  wireLayoutEditor();
  syncLayoutForm();
  refreshPresetThumbs();
  wireKeyboard();
  setActiveTab("play");
  syncUndoButton();

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
  $("loop").addEventListener("click", () => setLoop($("loop").getAttribute("aria-pressed") !== "true"));
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
