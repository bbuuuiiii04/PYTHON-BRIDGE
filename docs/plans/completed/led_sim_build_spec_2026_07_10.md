---
doc_status: superseded-spec
truth_level: historical-build-spec
last_verified_commit: f800912
last_verified_date: 2026-07-15
validation_scope: >
  Historical room-layout simulator build spec for AWR-196. The operator
  replaced this goal on 2026-07-15 with fixture-level H612D parity and removed
  room geometry from scope. Do not execute; current truth is the code,
  docs/guides/led_sim.md, and the AWR-196 registry row.
---

# Implementation Spec — LED room simulator (AWR-196)

> **SUPERSEDED 2026-07-15. Do not execute this room-layout spec.** It is kept
> only as provenance for the first simulator build.

Build a standalone, near-real-life simulator of the operator's Govee H612D
perimeter LED strip: a local web page that renders what the real room does when
the real renderer plays an effect. The sim is OFFLINE TOOLING — it never talks
to the device, never touches the bridge runtime, never touches the pad lane's
files.

## Part A — Context & ground truth (verified; read, do not implement)

All claims [confirmed] at HEAD `20329d7` unless labeled otherwise.

**Hardware (operator-supplied, charter §"Hardware ground truth"):**
- Govee H612D strip, 15 m install, **360 LEDs → 60 controllable segments × 6
  LEDs**, mounted top-of-wall around the FULL perimeter of a rectangular room.
- One room dimension supplied: `2284` (unit unconfirmed; treat as mm ⇒ short
  wall ≈ 2.284 m; full perimeter 2(a+b) = 15 m ⇒ long wall ≈ 5.216 m). This is
  the DEFAULT geometry only — the whole point of self-calibration is that the
  operator's dragging overrides it. [assumed: mm]
- Device photometrics (response latency, IC fade behavior, diffusion width,
  bleed) are [unknown] → every one becomes a persisted calibration knob, never
  a hardcoded "correct" value. Reference material only:
  `experiments/govee_h612d_highres_discovery/` (fuzz scripts + README).

**The real frame pipeline (what "data-true" means):**
- `Frame = list[RGB]` (govee_frame_renderer.py:~17 region); effects are pure
  seeded functions `(beat, local_t, frame_index, params, segments, seed) ->
  Frame`; slot effects return `MotionField = list[list[float]]`
  (govee_frame_renderer.py:17) and are colorized by
  `universal_colorizer(field, slot_colors)` (govee_frame_renderer.py:1327).
- **`GoveeFrameRenderer.render(name, *, beat_pos, local_t, frame_index,
  params, segments, seed) -> Frame`** (govee_frame_renderer.py:2372 class) is
  the single stateless entry point; unknown names fail dark. This is the sim's
  ONLY render path — no reimplemented effects, ever.
- Effect catalog: module-level `REALTIME_EFFECT_NAMES`
  (govee_frame_renderer.py:1232) + `SLOT_EFFECTS` (…:2207).
- Live cadence: production fps = 60 (`config/led_look_director.example.json:610`
  `"fps": 60`; segments = 60 at line 600). The runner
  (`govee_realtime_runner.py`) tracks achieved-fps EMA (AWR-156) — real cadence
  jitters; the sim models cadence with knobs, not ideal-grid assumptions.
- Existing offline preview precedent: `render_preview_frames`
  (tools/led_pad_lab.py:192) — the builder MUST read it and mirror its
  beat/local_t/frame_index derivation so sim frames match lab-preview frames
  for the same (effect, params, seed, bpm, fps).
- Lab draft effects: `load_lab_effects(path)` (tools/led_pad_lab.py, directly
  above render_preview_frames) loads a gitignored Python module exposing
  `LAB_EFFECTS: dict[name, (kind, fn)]`; `LabRenderer` wraps the production
  renderer + those functions. Lab data lives in `config/led_lab/` (gitignored,
  .gitignore:36).
- Session recorder records PRE-TICK INPUTS (events/positions/bpm), NOT rendered
  frames (session_recorder.py docstring/lines 1–35). There is no existing frame
  log for Govee frames (only the Art-Net DMX sidecar, artnet_truth.py:30, which
  is lasers, not LEDs). ⇒ "replay" in this round = a frames-JSONL format the
  sim defines, plays, and can generate offline; capturing frames from a LIVE
  session would need a runtime tap and is OUT OF SCOPE (executive decision
  later).

**Fence (parallel lane, ACTIVE right now):** the pad lane (AWR-193, session
`padbuild`) owns `tools/led_pad_web.py`, `tools/led_pad_lab.py`,
`led_pad_controls.py`, `tools/led_pad_assets/**`. This round MUST NOT edit any
of those files. Read-only IMPORTS of `tools.led_pad_lab` are allowed but must
be guarded (that file is being rewritten in parallel — see Task 3's
degradation contract). Port 8766 is the pad server (tools/led_pad_web.py:979);
the sim takes **8767** (grep-confirmed free).

**Config conventions:** live configs are gitignored with committed
`.example.json` siblings (.gitignore:32–37).

## Part B — Tasks (implement exactly, in order; ONE commit per task, explicit paths, never `-a`)

### Absolute rules
- Touch ONLY: `tools/led_sim_engine.py`, `tools/led_sim_web.py`,
  `tools/led_sim_assets/**` (new dir), `config/led_sim_profile.example.json`,
  `.gitignore` (one line), `tests/test_led_sim_engine.py`,
  `tests/test_led_sim_service.py`, `docs/guides/led_sim.md`,
  `docs/agents/change_contracts.yml`, `docs/architecture/doc_index.md`,
  `docs/status/active_work_registry.md` (status cell of the AWR-196 row only).
- NEVER touch: anything in the pad fence above; any bridge runtime module
  (`state_manager.py`, `govee_realtime_*`, `led_dispatch_*`,
  `led_look_director.py`, …); `config/led_look_director.json` (live) — the sim
  READS live/example config, never writes it; no launchagents; no scripts/.
- The sim NEVER opens a socket except its own HTTP listener on
  **127.0.0.1:8767** — no UDP, no device transport imports
  (`govee_realtime_transport`, `govee_lan_discovery` are FORBIDDEN imports),
  no subprocesses that contact hardware.
- Error handling: fail closed and SURFACE. Bad profile JSON → serve defaults +
  `"profile_error"` in the API payload, never silently reset a saved file.
  Lab-module import failure → catalog still serves production effects with
  `"lab_error"` set. No broad try/except around render calls — a render
  exception returns HTTP 500 with the traceback in the JSON body (this is a
  local operator tool; hiding errors costs calibration trust).
- An improvement you notice = a NOTE in your report, never an edit.
- You report evidence; the manager reviews; the executive gates. You never
  declare the round shipped.
- Do not pause at checkpoints for acknowledgment; run straight through unless
  genuinely blocked. If reality diverges from this spec (unknown name, missing
  file, unexpected state): STOP, write the .blocked signal with one line of
  evidence, and wait. Blocking is a success mode; invention is the failure mode.
- Verify every cite at HEAD immediately before relying on it — the tree moves
  under you (auto-sync, parallel lanes).

### Task 1 — contract + config scaffolding (contract-first, before any code)
- `docs/agents/change_contracts.yml`: add key `led_sim` mirroring the `led_pad`
  key's shape (change_contracts.yml:230–244):
  - `code_globs`: `tools/led_sim_*.py`, `tools/led_sim_assets/**`,
    `config/led_sim_profile.example.json`
  - `inspect`: `docs/guides/led_sim.md`, `docs/architecture/doc_index.md`,
    `docs/status/active_work_registry.md`
  - `tests`: `python3 -m unittest discover tests` + the three hard doc checks.
  If the yml has a human-readable sibling section in
  `docs/agents/change_contracts.md`, add the matching row.
- **Stub the referenced docs in this same commit** so
  `check_agent_contracts.py` (which validates that contract references resolve
  to real files) passes at Task 1, not only at Task 6: create
  `docs/guides/led_sim.md` as a stub (proper frontmatter, status `planned`,
  one line "being built under AWR-196") and add its `doc_index.md` row now;
  Task 6 fills it in. Run the three hard checks after this commit; if
  `check_agent_contracts.py` ALSO requires the `code_globs` targets to exist
  already, report that in one line and fold the yml addition into Task 2's
  commit instead (note it — do not fight the checker).
- `.gitignore`: add `config/led_sim_profile.json` next to the other live-config
  ignores (lines 32–37).
- `config/led_sim_profile.example.json`: the committed default device profile —
  schema v1:
  ```json
  {
    "schema": 1,
    "segments": 60,
    "room_mm": [5216, 2284],
    "corner_segments": [0.0, 20.9, 30.0, 50.9],
    "start_corner": 0,
    "direction": "cw",
    "gamma": 1.0,
    "white_point": [1.0, 1.0, 1.0],
    "brightness": 1.0,
    "diffusion_width_seg": 1.0,
    "bleed": 0.15,
    "wash_reach_mm": 800,
    "wash_gain": 1.0,
    "fps": 60,
    "latency_ms": 0,
    "hold_mode": "zoh",
    "slew_ms": 0,
    "bpm": 128
  }
  ```
  `corner_segments` = fractional strip positions (units of segments, 0–60,
  strictly ascending, first ≥ 0, last < 60) where the room's four corners sit;
  defaults derived from wall lengths (15 m / 60 seg = 0.25 m per segment:
  long wall ≈ 20.9 seg, short ≈ 9.1 seg). All photometric/temporal values are
  CALIBRATION DEFAULTS, labeled assumed — the operator's calibration overrides
  them; none of them is a claim about the real hardware.
- Commit: `AWR-196 Task 1: led_sim contract + device-profile scaffolding`.

### Task 2 — `tools/led_sim_engine.py` (pure engine, no HTTP)
Pure-Python module; every algorithm below is a pure function (the test seam).
- **Profile**: `load_profile(path) -> dict` / `validate_profile(dict) ->
  list[str]` (error strings; empty = valid) / `save_profile(path, dict)`
  (atomic: tmp + rename). Validation: schema==1, segments==60 allowed range
  1–1000, corner_segments strictly ascending within [0, segments), direction
  in {cw, ccw}, numeric ranges sane (gamma 0.2–5, bleed 0–1, fps 1–120).
  Unknown keys preserved (forward compat).
- **Geometry**: `segment_geometry(profile) -> list[dict]` — for each of the 60
  segments: center `x_mm, y_mm` on the rectangle perimeter, unit inward normal
  `nx, ny`, wall index 0–3, and segment span endpoints. Mapping: the strip is a
  closed 60-segment ring; `corner_segments` splits the ring into 4 arcs; arc k
  maps linearly onto wall k's length, walls ordered from `start_corner`
  following `direction`. This function is THE calibration target — dragging
  corners/start/direction in the UI just edits the profile and re-runs it.
- **Bleed kernel**: `apply_bleed(frame, bleed) -> frame` — ring-wrapped
  3-tap mix `out[i] = (1-bleed)·f[i] + (bleed/2)·(f[i-1]+f[i+1])`, channels
  clamped 0–255. (Server-side reference implementation + unit tests; the JS
  view mirrors it — see Task 4 note on the deliberate JS seam.)
- **Render adapter**: `render_frames(name, params, seed, fps, duration_s, bpm,
  segments) -> list[Frame]` — drives `GoveeFrameRenderer.render` with
  beat/local_t/frame_index derived EXACTLY as `render_preview_frames`
  (tools/led_pad_lab.py:192) derives them (read it first; do not invent a
  parallel derivation). Deterministic: same args → identical frames.
- **Lab bridge (guarded)**: `lab_catalog()` / `render_lab_frames(...)` —
  import `tools.led_pad_lab` INSIDE the function bodies; any exception →
  `{"ok": False, "error": str(exc)}` and production rendering stays fully
  functional. The pad lane is rewriting that module in parallel: degradation
  is a CONTRACT, not a nicety.
- **Production looks source**: `look_params_catalog() -> dict` — read
  `config/led_look_director.json` if present else the example; extract each
  look's effect name + params (incl. `slot_colors`); verify the actual schema
  at read time against the example file and fail closed (error string in the
  payload) if the shape surprises you — do NOT guess key names: check them
  against `config/led_look_director.example.json` around lines 595–615 first.
- **Frames-JSONL codec**: `write_frames_jsonl(path, frames, fps, meta)` /
  `read_frames_jsonl(path)` — line schema
  `{"v": 1, "t_ms": <int>, "frame": [[r,g,b] × segments]}` with a header line
  `{"v": 1, "kind": "header", "fps": .., "segments": .., "meta": {..}}`.
  Reader fails closed per file (raise with line number), not per line.
- **Test cards**: `test_card_frames(kind, segments) -> list[Frame]` for kinds
  `white|red|green|blue|gray50|single_segment` (static, 1 frame each) — the
  photometric calibration references.
- CLI (`python3 -m tools.led_sim_engine render-jsonl --name .. --out ..`):
  render any effect to a frames-JSONL so the replay path is exercisable
  end-to-end offline. Stdlib argparse only.
- Commit: `AWR-196 Task 2: led_sim engine (geometry/profile/adapter/codec)`.

### Task 3 — `tools/led_sim_web.py` (stdlib server, port 8767)
Mirror the PATTERN of the pad server (stdlib `ThreadingHTTPServer`,
`http.server`) — do not import from `tools.led_pad_web`. Bind 127.0.0.1 only.
- Static: serve `tools/led_sim_assets/` at `/` with `Cache-Control: no-cache`.
- JSON API (POST bodies, JSON responses; GET where noted):
  - `GET /api/catalog` → `{effects: [names from REALTIME_EFFECT_NAMES sorted],
    looks: look_params_catalog(), lab: lab_catalog() result, profile: current,
    profile_error, lab_error}`.
  - `POST /api/render` `{source: "effect"|"lab", name, params, seed, fps,
    duration_s, bpm}` → `{frames, fps, segments}` (frames RAW from the
    renderer — photometrics are the client's job; duration capped at 30 s,
    fps capped at 120: 8 GB machine, bounded payloads).
  - `POST /api/render_card` `{kind}` → 1-frame payload.
  - `GET /api/profile` / `POST /api/profile` (validate; on errors return them,
    write nothing).
  - `POST /api/replay/load` `{path}` → read_frames_jsonl payload (path must be
    inside the repo or /tmp — reject absolute paths elsewhere; this is a local
    tool but don't serve arbitrary files).
- `--port` (default 8767) and `--profile` (default
  `config/led_sim_profile.json`, falling back to the example) flags.
- No background threads beyond the HTTP server. No renderer state cached
  across requests (renderer is stateless).
- Commit: `AWR-196 Task 3: led_sim server (:8767)`.

### Task 4 — `tools/led_sim_assets/` (the room view + app)
Files: `index.html`, `sim.css`, `ledsim-view.js`, `sim-app.js`. Plain ES
modules, ZERO external deps (no CDN — offline tool), canvas 2D (no WebGL this
round: 60 radial gradients × 60 fps is comfortably cheap; WebGL is the
labeled upgrade path if profiling ever disagrees).
- **`ledsim-view.js` — THE SWAPPABLE SEAM.** Self-contained module, no imports:
  `createLedSimView(canvas, profile) -> {renderFrame(frame), setProfile(p),
  hitTest(x, y), destroy()}`. Draws, top-down:
  1. dark room rectangle (scaled to fit canvas, preserving room aspect);
  2. **strip pass**: per segment, a glow stroke along its wall span — linear
     gradient across `diffusion_width_seg`, after applying the photometric
     transform: `out_c = 255·(gain_c·brightness·(in_c/255))^gamma` per channel
     (mirror of the engine formula) and the ring bleed kernel (mirror of
     `apply_bleed`);
  3. **wash pass**: `globalCompositeOperation = "lighter"`; per segment a
     radial gradient centered `wash_reach_mm·0.35` inward along the segment
     normal, radius `wash_reach_mm` (room scale), color = transformed segment
     color, peak alpha ∝ perceived intensity × `wash_gain`. This is the
     indirect ceiling/wall glow the operator actually sees — the charter's
     critical axis: the room must read as WASHED light, not 60 dots.
  4. corner/start/direction affordances when `profile._calibrating` is truthy:
     draggable corner handles (positions from `segment_geometry`-equivalent JS
     mapping), a start-segment handle, direction arrow. `hitTest` supports the
     app's drag wiring; the VIEW never fetches or persists anything itself.
  Header comment documents the seam contract for the future pad-round
  integration (pad lane mounts this module + feeds frames; nothing else).
  JS mirrors of the engine's bleed/photometric/geometry formulas are a
  DELIBERATE seam decision (interactive knobs must not round-trip the server
  per slider tick); the Python twins carry the unit tests, the JS twins carry
  a `// mirror of led_sim_engine.<fn> — keep in lockstep` comment each.
- **`sim-app.js`** — page glue:
  - source pickers (effect / production look / lab draft / replay file), BPM,
    seed, duration; fetch `/api/render`, hold frames client-side;
  - transport: play/pause/loop/scrub; frame selection by wall clock:
    `idx = floor((now - t0 - latency_ms)·fps/1000) mod n`; `hold_mode` zoh =
    hard switch, `slew` = per-channel lerp toward the target frame with time
    constant `slew_ms` (models unknown IC response — a knob, not a claim);
  - knob panel (gamma, white RGB gains, brightness, diffusion, bleed, wash
    reach/gain, fps, latency, hold/slew) — all live, all LOCAL until "Save
    profile" POSTs;
  - **Calibrate mode**: geometry step (instructions: "play the same effect on
    the real strip from the Pad, drag corners/start/flip direction until the
    sim moves like your room"; slow `beat_chase` preset button) + photometric
    step (test-card buttons + knob panel + "hold your phone photo next to the
    canvas" hint); Save persists the profile;
  - reconnect-tolerant polling is NOT needed (no live polling loop; render is
    on-demand) — one clear error banner on failed fetches.
- Commit: `AWR-196 Task 4: led_sim room view + app (self-calibrating UI)`.

### Task 5 — tests
- `tests/test_led_sim_engine.py`:
  - geometry: default profile → 4 arcs land on 4 walls, all 60 centers lie ON
    the rectangle perimeter, normals point inward (dot with center-to-room-
    center > 0); direction flip reverses travel order; start_corner rotation
    shifts the mapping; degenerate/invalid corner lists rejected by
    `validate_profile` (non-ascending, out of range, wrong count);
  - bleed kernel: ring wrap exact values on a hand-computed 4-segment frame;
    bleed=0 identity; clamping;
  - render adapter: known effect (`beat_chase`) — determinism (two calls
    identical), frame count == fps·duration, width == segments; unknown name
    fails dark (all-black frames or raised — assert whichever
    `render_preview_frames` parity dictates, and pin it);
  - codec: roundtrip equality; corrupt line → raise with line number; header
    mismatch (segments) → raise;
  - profile: save/load roundtrip preserves unknown keys; invalid saves
    rejected with named errors;
  - test cards: exact expected pixels.
- `tests/test_led_sim_service.py`: start the server on an ephemeral port with
  a tmp profile path; assert catalog shape (effects non-empty, contains
  `beat_chase`), render returns fps·duration frames × 60 wide, render caps
  enforced (duration 31 s → 400), profile POST validate-reject writes nothing,
  lab degradation (patch the lab import to raise → catalog still 200 with
  `lab_error` set), replay path rejection outside repo//tmp.
  Follow the existing pad service test pattern for server setup/teardown if
  one exists in `tests/` (check `tests/test_led_pad_service.py` first; reuse
  its harness style, not its files).
- Commit: `AWR-196 Task 5: led_sim tests`.

### Task 6 — docs + registry
- `docs/guides/led_sim.md`: operator-facing guide (doc frontmatter header,
  §10 status language): what the sim is, how to start it
  (`python3 -m tools.led_sim_web`), the calibration procedure (geometry step,
  photometric step), every knob's plain-language meaning, the frames-JSONL
  format, the `ledsim-view.js` seam contract for the pad round, and the hard
  line: the sim never touches the device or the bridge.
- `docs/architecture/doc_index.md`: classify the new guide.
- `docs/status/active_work_registry.md` AWR-196 row: update the STATUS CELL
  ONLY with what you actually did + test counts (report language, not "done").
- Run the three hard checks + full suite (see acceptance).
- Commit: `AWR-196 Task 6: led_sim guide + doc index + registry status`.

## Part C — Invariants that MUST still hold (live safety)

- The sim NEVER contacts the H612D or any Govee device: no UDP sends, no
  transport/discovery imports, no keepalive interaction. The live device is
  owned by the running bridge alone. (A sim that accidentally streams frames
  to the strip during a live mix is the catastrophic failure of this round —
  the import ban + no-socket rule exists for that scenario.)
- Zero bridge-runtime edits; zero pad-fence edits (AWR-193 lane is mid-flight
  in the same tree). Imports of pad files are read-only and exception-guarded.
- The sim reads live configs (`config/led_look_director.json`), never writes
  any config except `config/led_sim_profile.json` via validated POST.
- Port 8767 only, loopback only — never 8766.
- No background CPU burn: render on demand, bounded payloads (8 GB machine
  shared with the live bridge + DJ software).
- Secrets/live config stay uncommitted: nothing under `config/led_sim_profile
  .json`, `config/led_lab/`, or any live JSON is ever `git add`ed.

## Part D — Tests

Covered by Task 5. Seam rule honored: geometry, bleed, adapter determinism,
codec, profile validation are pure functions tested without HTTP or disk
(profile tests use tmp paths). The JS photometric/bleed mirrors are
deliberately untested-by-unittest (taste-calibrated by the operator's eye —
the calibration loop IS their verification); the lockstep comments + Python
twins keep them reviewable. State this trade in your report.

## Part E — Acceptance (definition of done)

- [ ] All six commits present, each touching ONLY its listed files (explicit
      `git add` paths; never `-a`).
- [ ] `python3 -m unittest tests.test_led_sim_engine tests.test_led_sim_service -v`
      green.
- [ ] Full suite from repo root: reds reconcile BY NAME against the five-red
      baseline (`test_drop_slot_color_smoke_and_snap` error, both
      `test_export_pack_parity_self_heal` fails,
      `test_ddj_slots_8_16_17_24_exact_ch1_ch19`, parity-oracle
      `test_autoloop_capture_rows_identify_passes_and_blockers`) — any OTHER
      red: reproduce in isolation ×3 before attributing; report names either
      way. "N reds" without names is an invalid report.
- [ ] `python3 tools/check_docs_metadata.py`, `python3
      tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py` all
      green.
- [ ] Server smoke at your desk: start on 8767, `curl` catalog + one render +
      profile roundtrip; kill it after (`pkill -f led_sim_web` and verify with
      a bracketed pgrep). Never touch port 8766 or any running process you
      didn't start.
- [ ] Browser-facing behavior verified as far as headless allows (server smoke
      + JS syntax pass e.g. `node --check` IF node exists locally — if not,
      note it; the manager review covers the visual pass).
- [ ] Report written to `/tmp/rbss_lane_signals/<session>.<TAG>.report.md`:
      per-task commits, test counts, suite reconcile by name, the JS-mirror
      trade note, anything you noticed but did not touch.

## When you finish

Report evidence (commits, test names/counts, red names, curl transcript
essentials) in the report file; print your sentinel on its own line; write the
signal file. Plain-language operator summary at the top of the report: what
the sim shows, what it deliberately does NOT do (no device contact), what only
his eyes can validate (the five accuracy axes land only after HIS calibration
pass against the real room).
