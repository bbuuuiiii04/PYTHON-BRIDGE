---
doc_status: active-spec
truth_level: code-grounded implementation spec plus operator-grilled target behavior
last_verified_commit: 6c51eb8
last_verified_date: 2026-06-29
validation_scope: spec only; docs/code read against current checkout; no bridge run, restart, SoundSwitch, MIDI, serial, Enttec, DMX, laser, LED/Govee, Rekordbox live sampling, or hardware validation
---

# Codex Implementation Spec - Native Autoloop DMX Runtime

Authoritative intended behavior lives in
`docs/architecture/native_autoloop_pack_authority.md`. Implement this spec
against that document and current code. If code and the authority doc disagree,
stop and report the conflict before changing runtime behavior.

**Scope decision (operator, 2026-06-29):** native Autoloop DMX is **greenlit**.
The earlier "blocked by T7d" gating in
`docs/plans/active/soundswitch_exporter_remaining_work.md` (RW item 4) and the
six-scenario `soundswitch_t7d_capture_evidence_plan.md` are **superseded** by an
operator-run all-in two-flight capture. The beat to animation phase mapping in
Task 3 is the working contract. The phase still carries a single
`phase_offset_beats` calibration input (default `0.0`) so the two-flight capture
can tune alignment without a code change; see Task 3 and Part C. Native output
remains `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED` until an
operator-approved rig A/B run, per the authority doc Validation Bar.

## Part A - Context & Root Cause (pre-implementation facts; read, do not implement)

- [superseded gap] Before this native implementation, Autoloop mode cleared the
  player selection and published `autoloop_phase_blocked` instead of calling
  `select_autoloop()`. `_push_tick()` still runs `_push_tick_inner()` then
  `_drive_pack_output()` exactly once per tick when `rt.active`.
- [confirmed] The pure renderer already exists. `render_autoloop_frame()` renders
  a CH1-19 frame, validates non-negative integer `phase_tick`, wraps
  `phase_tick % loop.cycle_ticks`, and returns zero for inactive/unsupported
  looks: `soundswitch_laser_player.py:125-147`. Every Autoloop document is built
  with `cycle_ticks = AUTOLOOP_CYCLE_TICKS = 19_200`:
  `soundswitch_pack_loader.py:26`, `:493-494`.
- [confirmed] The tick-per-beat scale is a fixed `600`. The pinned analysis
  harness uses `TICKS_PER_BEAT = 600` through the **same**
  `render_autoloop_frame`; runtime phase uses the modulo 32-beat formula in Part
  C. `19_200 = 32 * 600`, and `AUTOLOOP_ARM_PHRASE_BEATS = 32`:
  `config.py:7-8`.
- [confirmed] The 32-beat / 19,200-tick Autoloop length is **enforced, not
  assumed**: the decoder fails any catalog entry whose `bars != 8`
  (`soundswitch_project_decoder.py:646`, `:650`); 8 bars * 4 beats = 32 beats.
  A non-8-bar loop fails export rather than mis-wrapping. Caveat: 8 bars = 32
  beats assumes 4/4, and `cycle_ticks = 19_200` is hardcoded onto every loop,
  never cross-checked against a file's own maximum event `time`
  (`soundswitch_project_decoder.py:534` reads `time` as a raw stored int with no
  tempo/PPQ/ms conversion).
- [confirmed] `LaserPackPlayer.select_autoloop(identity, phase_tick, *,
  authority)` exists and routes to `_autoloop_base()`, which reports diagnostic
  codes `unsupported_authority`, `stale_authority`, `ambiguous_authority`,
  `missing_phase`, `autoloop_not_found`, `inactive_autoloop`,
  `unsupported_layout`, and `player_error`:
  `soundswitch_laser_player.py:270-276`, `:352-378`.
- [implemented] The pack loader exposes `LoadedPack.autoloops` and a runtime
  note-to-Autoloop map with display names via `LoadedPack.autoloop_bindings`.
- [confirmed] The exporter writes `selection_map.json` `iac_selections` rows with
  `active`, `channel_zero_based`, `data_byte`, `device_name`, `message_type`,
  `target_identity`, `target_kind`, and `target_name`: `soundswitch_pack.py:223-266`.
  `BRIDGE_SCENES` encodes role notes with `channel == 0` (0-based), e.g.
  `("house_drop_1", 0, 96)`: `soundswitch_pack.py:36-49`.
- [confirmed] **Channel base mismatch.** The laser scene MIDI channel is
  **1-based (1-16)**: `laser_models.py:28-29`, default `channel: int = 1` at
  `:44`; the live config maps `house_drop_1` to `"channel": 1`, `"note": 96`
  (`config/laser_director.json:412`, `:415`); `midi_output.py:251` converts
  `int(msg.channel) - 1` only at the wire. The pack key `channel_zero_based` is
  **0-based**. A scene channel copied straight into the binding lookup is off by
  one and resolves nothing, so native renders dark for **every** look. The
  resolver MUST subtract 1 (Task 3).
- [confirmed] SoundSwitch Autoloop catalog entries have display names
  (`soundswitch_pack_models.py:153-181`), `ResolvedControlBinding.target_name`
  carries the resolved name (`:253-260`), set from the catalog at
  `soundswitch_project_decoder.py:1002-1012`.
- [confirmed] Static Override Press/Toggle is already exported and loaded for
  Static Look bindings: `soundswitch_pack_loader.py:258-297`; must stay unchanged.
- [confirmed] `set_pack_runtime()` already resets pack frame/layer/error counters
  and publishes a software-zero status atomically: `state_manager.py:3582-3610`.
- [confirmed] The pack driver is the sole normal `PackOutputBackend.submit_frame`
  caller and already applies Static Override/masks before rendering/submitting:
  `state_manager.py:3735-3738`, `:3812-3825`; `docs/subsystems/soundswitch_output.md:29-35`.
- [confirmed] **`on_decision` is edge-triggered, not level-triggered.**
  `LaserSceneExecutor.on_decision()` (`laser_executor.py:107`) returns through
  ~7 early exits and the success path falls off the end (`:269`), so today it
  returns `None` on the vast majority of 200 Hz ticks. For the groove/phrase
  role, `_select_scene` returns `""` unless the reason is
  `default_init`/`phrase_boundary` **and** `autoloop_tick_just_fired`
  (`:400-406`), so a scene is emitted only on a (re)select/(re)fire edge, which
  is roughly once per 32-beat phrase. Between edges it is `same_scene_skip`
  (`:213-224`). `_drive_pack_output` runs every tick, so the resolver MUST hold
  the selection across `None` ticks (Task 3); a per-tick clear would flicker the
  look on for one tick every 32 beats.
- [confirmed] A single-look bank re-returns the **same** scene name on a 32-beat
  edge: `_choose_bank_scene_locked` (`laser_executor.py:426-438`). The re-anchor
  signal therefore cannot be "scene name changed"; it must be "the executor
  emitted a scene this tick" (an edge), which it does on both role changes and
  same-look refires.
- [confirmed] The four `on_decision` call sites are all inside `_push_tick_inner`
  (the only method between `state_manager.py:3847` and the next def): `:3902`,
  `:3940`, `:4140`, `:4381`. The native capture must initialize once per tick and
  capture at all four.
- [confirmed] On entering Autoloop mode after a master change, the executor holds
  a blackout mask until the first phrase-relative refire:
  `state_manager.py:3513-3521` (`hold_blackout_mask("master_switch")`). The
  hold-until-first-fire latch (Task 3) reproduces this: native stays software-zero
  until the executor's first emitted scene, identical onset to the lasers.
- [confirmed] `DropLifecycle` is the pure drop/post_drop timing resolver and lives
  in the **director** (`laser_director.py:131`, `:211-214`, reset at `:322-327`);
  `drop_lifecycle.py:13-112`. The director feeds `decision.role`/`decision.reason`
  into the executor, so consuming the executor's emitted scene already reflects
  `DropLifecycle` timing; no parallel drop resolver is needed.
- [confirmed] `post_drop_cycle_beats` is presently **inert** (`drop_lifecycle.py:17`).
  See the [assumed] note below for how native treats it.
- [confirmed] `LaserSceneExecutor.reset_runtime_state()` clears role/scene/bag/
  cooldown (`laser_executor.py:84-98`); `LaserDirector.reset_runtime_state()`
  resets drop lifecycle (`laser_director.py:322-327`).
- [confirmed] **Reset sites are asymmetric.** Master change (`state_manager.py:2896`,
  `:2898`), active-deck change (`:2937`, `:2939`), and active-track load (`:2958`,
  `:2960`) reset **both** director and executor; **stop** (`:4722`, `:4724`) and
  **resume** (`:4753`, `:4755`) reset both; but **scripted** (`:3502`) and **idle**
  (`:3531`) reset **only the director**. Native state must be reset at all of these
  sites explicitly (Task 4) — do not assume an executor reset exists on
  scripted/idle.
- [confirmed] Today `autoloop_phase_blocked = rt.active and lighting_mode ==
  "autoloop"` (`state_manager.py:3820-3822`) and it is the second-highest
  precedence in the operational-state enum (`:137`, `:151-152`). Active native
  rendering must not keep reporting `autoloop_phase_blocked` (Task 5).
- [confirmed] The active-doc classifier hard check fails until this spec is
  indexed: `tools/check_agent_contracts.py:7-8`. This spec and
  `soundswitch_autoloop_equivalence_oracle_spec.md` have been added to
  `docs/architecture/doc_index.md` as part of this revision so Part D is green
  from the first run; confirm before implementing.
- [assumed] The existing laser/bridge personality config is the role-bank and
  timing authority for native scene selection (the authority doc's "Mapping
  Authority"). Native re-uses the executor's post-bank selection; it never
  invents a role classifier or a parallel bank.
- [assumed] Native post_drop cadence uses the executor's existing
  `autoloop_tick_just_fired` 32-beat refire for this implementation, exactly like
  lasers. `post_drop_cycle_beats` remains the named config knob for future
  cadence changes; it is not newly wired here.
- [assumed] Groove/buildup/breakdown/drop role notes resolve to
  `target_kind == "autoloop"` in the canonical pack. Post_drop mappings are
  optional: if none are mapped, the native path must use the executor's existing
  drop-cycle fallback; if post_drop notes are mapped, they must resolve to
  Autoloops. The resolver consumes only autoloop bindings
  (`soundswitch_pack.py:262`); a role note authored as a SoundSwitch Static Look
  has no autoloop binding and fails closed to `missing_binding` for that look.
  **Pre-implementation check (Task 0):** confirm the live pack's role notes.
- [confirmed] `phase_offset_beats` defaults to `0.0`; the two-flight capture may
  later tune the alignment between bridge beat position and SoundSwitch Autoloop
  phase-0. Native phase is a working default, not a hardware-validated contract.
- [unknown] Exact final class/function names are implementation choices; the
  behavior, status fields, tests, and hot-path constraints below are fixed.

Root cause: the bridge can decode and render Autoloops and already decides roles
and selects post-bank scenes, but the pack driver never translates the
bridge-selected role scene/note into a pack Autoloop selection. Native Autoloop
mode therefore remains software-zero.

## Part B - Tasks (implement exactly, in order; commit after each)

### Absolute Rules

- Do not run or restart the bridge.
- Do not open SoundSwitch, Rekordbox, MIDI, serial, Enttec, Art-Net, DMX, laser,
  LED/Govee, or hardware-adjacent paths.
- No blocking I/O in the 200 Hz push loop: no serial, MIDI, socket, file,
  subprocess, sleeps, or config reads inside native selection/rendering.
- No second pack output loop and no second normal
  `PackOutputBackend.submit_frame()` caller.
- Do not change scripted-track priority, Static Override Press/Toggle behavior,
  the SoundSwitch-present auto-switch, or laser/LED/Govee output. The only
  laser-side change permitted is exposing the already-selected scene (Task 2).
- Do not add a separate native-Autoloop dry-run/observe mode.
- The binding lookup MUST convert the 1-based scene channel to 0-based.
- The native selection MUST be latched across `None` executor returns; a `None`
  return is "no new edge", not "clear".
- Do not claim hardware validation.

### Task 0 - Verify role notes are Autoloops (read-only gate; do not edit)

Before implementing, inspect the canonical pack artifact
`local/soundswitch/rbss_canonical_pack/selection_map.json` (or the configured
pack path if the operator overrides it) and confirm:

- required bridge role notes for groove/buildup/breakdown/drop (e.g. channel 0
  notes 32, 64, 1, and 96-111) appear in `iac_selections` with
  `target_kind == "autoloop"`;
- post_drop role notes are optional today; if none appear, record
  `post_drop_source=drop_fallback` and expect drop-bank cycling during post-drop;
- if post_drop notes do appear, each one must be `target_kind == "autoloop"` and
  must cycle inside the post_drop bank every 32 beats.

If any required role note is authored as a Static Look, native cannot render it
via the autoloop path; stop and report which notes. Record the result in the
finish report.

### Task 1 - Pack Runtime Mapping: note -> Autoloop identity/name

Files: `soundswitch_pack_loader.py`; `tests/test_soundswitch_pack.py` and/or a
focused pack-loader test.

Add an immutable runtime model for active IAC Autoloop selections:

```python
@dataclass(frozen=True, slots=True)
class LoadedAutoloopBinding:
    channel_zero_based: int   # as stored in the pack (0-based)
    data_byte: int
    target_identity: str
    target_name: str
```

Add `LoadedPack.autoloop_bindings`, a mapping keyed by
`(channel_zero_based, data_byte)`. Populate from `selection_map.json`
`iac_selections` rows where `active is True`, `device_name == "IAC Driver Bus 1"`,
`message_type == "note"`, `target_kind == "autoloop"`, and `target_identity` is
present.

Validation (fail pack load):

- duplicate active `(channel_zero_based, data_byte)` Autoloop selections;
- `target_identity` not present in `LoadedPack.autoloops`;
- `target_name` missing/empty — fail closed with a clear load error rather than
  hiding a missing display name.

The key is stored 0-based (the pack's native base). The 1-based -> 0-based
conversion happens in the resolver at lookup time (Task 3), not here. Do not
change Static Override Press/Toggle loading.

### Task 2 - Expose the final bridge-selected scene (no new MIDI semantics)

Files: `laser_executor.py`; `laser_models.py` if the dataclass belongs there;
`tests/test_laser_executor.py`.

```python
@dataclass(frozen=True)
class LaserResolvedScene:
    role: str
    reason: str
    scene: str
    channel: int      # 1-based, as carried by scene_def.midi.channel
    note: int
    scene_type: str
```

Refactor `LaserSceneExecutor.on_decision()` to **return** `LaserResolvedScene |
None` with all existing behavior unchanged (gates, cooldown, bank/shuffle, mask,
logging, backend trigger all identical). Precise return contract — build the
result once `selected_scene` and `scene_def` are known and the **selection**
gates have passed (after `laser_executor.py:177` high-impact, `:200-211`
cooldown, `:213-224` same-scene-skip), then:

- return the `LaserResolvedScene` on the **success** path (`:247-269`) **and** on
  the `midi_trigger_rejected` path (`:241-245`). MIDI backend rejection is an
  actuation failure, not proof the role/note mapping is invalid for pack
  rendering — native must still render.
- return `None` on every path where no scene is committed: `decision is None`
  (`:110`), idle/no-scene (`:130`), auto-gate-blocked (`:137-141`), empty
  `selected_scene` (`:158-162`), missing `scene_def` (`:164-172`),
  high-impact-blocked (`:177-181`), role-cooldown-blocked (`:200-211`),
  same-scene-skip (`:213-224`).

`channel`/`note` come from `scene_def.midi` (channel is 1-based). `scene_type`
comes from `scene_def.scene_type`. Existing callers that ignore the return must
keep working.

### Task 3 - Native Autoloop Resolver (I/O-free, latched)

Files: new `native_autoloop_resolver.py`; new `tests/test_native_autoloop_resolver.py`.

Add `AUTOLOOP_TICKS_PER_BEAT = AUTOLOOP_CYCLE_TICKS // AUTOLOOP_ARM_PHRASE_BEATS`
(= 600) as a named runtime constant near the resolver (do NOT import the
`tools/` oracle into runtime). A unit test must assert it equals `600` and equals
the oracle's `TICKS_PER_BEAT`.

Create a deterministic, I/O-free resolver (pure function over explicit
state-in/state-out, or a tiny state object). No file/config reads, no
socket/serial/MIDI, no subprocess, no sleeps, no backend calls.

Inputs:

- pack generation/manifest SHA and `LoadedPack.autoloop_bindings`;
- the captured `LaserResolvedScene | None` for this tick;
- eligibility gates already computed by the pack driver: `lighting_mode`,
  scripted-active, `playing`, `fresh`, `track_changed`, `discont`,
  pack-output-enabled / SoundSwitch-present;
- `abs_beat_pos`;
- `phase_offset_beats` (default `0.0`);
- the prior native state (held identity/role/name/note, `anchor_beat`).

Latched selection model:

1. **Ineligible** (not Autoloop mode, scripted active, not playing/fresh, stale,
   `track_changed`, `discont`): clear native state; status `software_zero_frame`.
2. **SoundSwitch present / pack output disabled**: clear native state; status
   `soundswitch_present_native_suppressed`.
3. Eligible and `LaserResolvedScene is not None` (an edge — a (re)select/(re)fire
   happened):
   - look up `autoloop_bindings[(scene.channel - 1, scene.note)]`;
   - **found**: re-anchor — `anchor_beat = abs_beat_pos`; adopt
     `target_identity`/`target_name`/role/note/scene. Re-anchor on **every** edge
     (covers role change and single-look refire; the executor only emits on an
     edge). Status `rendering_active` (or `empty_dark_look` if the render is all
     zero).
   - **not found otherwise**: clear native identity (do not keep stale output,
     do not guess), status `missing_binding`.
4. Eligible and `LaserResolvedScene is None` (no edge this tick):
   - if a native identity is held: **keep it**, advance phase (do NOT clear);
   - if none is held yet (waiting for the first edge after a reset / master
     switch): status `software_zero_frame` (mirrors `hold_blackout_mask`).

Phase, computed only when an identity is held:

```python
phase_tick = round(((abs_beat_pos - anchor_beat + phase_offset_beats) % 32)
                   * AUTOLOOP_TICKS_PER_BEAT)
```

Decision output: `status` (one of `rendering_active`, `empty_dark_look`,
`missing_binding`, `missing_autoloop_file`, `unsupported_layout`,
`soundswitch_present_native_suppressed`, `software_zero_frame`), `role`, `scene`,
`note`, `soundswitch_name`, `target_identity`, `anchor_beat`, `phase_tick`,
`reason`, `diagnostic`.

Map `player.select_autoloop` diagnostics (Task 4 calls it) to these statuses:
`autoloop_not_found` -> `missing_autoloop_file`; `inactive_autoloop` /
`unsupported_layout` -> `unsupported_layout`; a valid look that renders all zero
-> `empty_dark_look` (not an error).

### Task 4 - Wire StateManager pack driver

Files: `state_manager.py`; `tests/test_state_manager_pack_driver.py`.

Native state fields on `StateManager` (held role/identity/name/note,
`anchor_beat`). Reset them (single GIL-atomic assignments,
matching the `set_pack_runtime` pattern at `:3599-3601`) at **every** site that
resets laser state, remembering the asymmetry:

- master change (`:2896`/`:2898`), active-deck change (`:2937`/`:2939`),
  active-track load (`:2958`/`:2960`), stop (`:4722`), resume (`:4753`);
- **scripted (`:3502`) and idle (`:3531`)** — only the director resets here, so
  add the native reset explicitly at both;
- pack runtime reload/replacement in `set_pack_runtime()` (`:3582-3610`).

In `_push_tick_inner()`: initialize `self._native_captured_scene = None` once at
the top, and at **all four** `on_decision` sites (`:3902`, `:3940`, `:4140`,
`:4381`) capture the return:
`self._native_captured_scene = self._laser_executor.on_decision(decision, ctx)`.
(`self._laser_executor` may be `None`; guard as the existing calls do — when it
is `None` native has no scene source and stays software-zero.)

In `_drive_pack_output()`:

- preserve existing Static Override/mask handling (`:3735-3738`) and scripted
  priority exactly (`:3802-3809`);
- when scripted transport is not active and Autoloop mode is eligible, run the
  native resolver with the captured scene and the already-computed gates
  (`fresh`, `playing`, `track_changed`, `discont`);
- if the resolver yields a held `target_identity` and `phase_tick`, call
  `player.select_autoloop(target_identity, phase_tick, authority="fresh")`;
  otherwise `player.clear_selection()`;
- render once and submit once through the existing path (`:3812-3825`);
- preserve fail-closed ZERO on exceptions (`:3826-3845`).

Layering stays: `native/scripted base -> static layers -> blackout/emergency mask
-> submitted frame`.

### Task 5 - Status and logs

Files: `state_manager.py`; `runtime_status.py`; `scripts/bridge_menubar.py`;
`tests/test_state_manager_pack_driver.py`; `tests/test_bridge_menubar.py`.

Extend the existing `soundswitch_pack` status row — do not create a new surface.
Add a nested sanitized block:

```json
"native_autoloop": {
  "status": "rendering_active",
  "role": "drop",
  "scene": "house_drop_4",
  "note": 123,
  "soundswitch_name": "House Drop 4",
  "target_identity": "autoloops/SSAutoLoop32.ssfile",
  "phase_tick": 1200,
  "reason": "drop_cycle"
}
```

**Migrate `autoloop_phase_blocked`.** It must no longer be `True` while native is
rendering. Change the computation at `state_manager.py:3820-3822` so it reflects
native status (true only when Autoloop mode is eligible but native is NOT
rendering — i.e. `missing_binding` / suppressed / software-zero), and update
`_pack_operational_state` (`:137`, `:151-152`) so the top-line enum agrees with
the nested block. The operational-state enum is a drift-checked surface
(`docs/setup/runtime_commands.md` and `tools/check_docs_drift.py`) and is rendered
by the menubar label map (`scripts/bridge_menubar.py:439`); update the doc string
table, the menubar label, and the tests together (`test_state_manager_pack_driver.py:164-165`,
`:1102-1103`; `test_bridge_menubar.py:488`).

Required statuses surfaced: `soundswitch_present_native_suppressed`,
`rendering_active`, `empty_dark_look`, `missing_binding`, `missing_autoloop_file`,
`unsupported_layout`, `software_zero_frame`.

Logs bounded — only on meaningful status/identity changes, never every 200 Hz
tick.

### Task 6 - Tests

Required focused tests:

- pack loader exposes note -> Autoloop identity/name for active IAC Autoloops;
- pack loader fails on duplicate active Autoloop note bindings;
- pack loader fails when a binding lacks `target_name`;
- `AUTOLOOP_TICKS_PER_BEAT == 600` and matches the oracle `TICKS_PER_BEAT`;
- resolver converts a **1-based** scene channel to the 0-based binding key and
  resolves the identity/name (guards the all-dark off-by-one);
- resolver fails closed on missing binding (no guess, no stale);
- resolver distinguishes missing file, unsupported layout, empty dark, active;
- **latch/no-flicker**: across a 32-beat window of `None` returns the resolver
  keeps the same identity and advances `phase_tick` (never clears mid-phrase);
- **single-look refire**: a `None`-then-edge with the **same** scene name
  re-anchors phase to ~0;
- role change re-anchors phase to ~0;
- phase advances from beat position between edges;
- `phase_offset_beats` shifts the phase deterministically;
- current no-post_drop-map behavior falls back to the executor's drop-cycle
  decision and cycles drop looks every 32 beats, not dark;
- mapped post_drop looks cycle within the post_drop bank every 32 beats;
- scripted mode still beats native Autoloop;
- stop/unload/stale/discontinuity clear native base to zero;
- Static Override remains layered above native Autoloop;
- pack reload clears old native state and allows a one-tick software-zero gap;
- SoundSwitch-present suppression status is visible;
- `autoloop_phase_blocked` is **not** set while `rendering_active`, and the
  operational-state enum agrees with the nested block.

Update/delete the obsolete "`select_autoloop()` is never called" assertions at
`test_state_manager_pack_driver.py:558`/`:563` and `:1095`/`:1105`; replace with
narrower assertions for the ineligible/missing cases.

### Task 7 - Docs and contracts

This change edits `state_manager.py`, `laser_executor.py`, `laser_models.py`,
`soundswitch_pack_loader.py`, `runtime_status.py`, and
`scripts/bridge_menubar.py`, and adds `native_autoloop_resolver.py`, so it
triggers at least these contracts in `docs/agents/change_contracts.yml`:
`soundswitch_pack_player`, `laser`, `core_bridge`, `runtime_commands`, and
`logging_visibility`.

- Add `native_autoloop_resolver.py` and `tests/test_native_autoloop_resolver.py`
  to the `soundswitch_pack_player` contract `code_globs`, and add the module to
  the AGENTS.md §4 source map (SoundSwitch output row).
- Update every doc listed under `docs_update` for every triggered contract that
  this behavior touches. At minimum: `docs/subsystems/soundswitch_output.md`,
  `docs/subsystems/laser.md`, `docs/subsystems/core_bridge.md`,
  `docs/subsystems/runtime_commands.md`, `docs/subsystems/logging.md`,
  `docs/setup/runtime_commands.md` (operational-state enum),
  `docs/architecture/current_architecture.md`,
  `docs/architecture/runtime_invariants.md`,
  `docs/status/feature_status_matrix.md`,
  `docs/status/support_matrix.md`,
  `docs/status/validation_matrix.md`,
  `docs/status/known_limitations.md`,
  `docs/plans/active/soundswitch_exporter_remaining_work.md`,
  `docs/status/active_work_registry.md` (AWR-107),
  `docs/validation/software_test_inventory.md`.
- Reconcile the superseded gating: in `soundswitch_exporter_remaining_work.md`
  (item 4 "Native Autoloop DMX" and acceptance lines) and AWR-107, replace
  "blocked by T7d / unimplemented / software-zero" with the greenlit status and a
  pointer to the two-flight capture for phase calibration. Mark the
  `soundswitch_t7d_capture_evidence_plan.md` six-scenario plan as superseded.
- `docs/architecture/doc_index.md` already lists this spec and
  `soundswitch_autoloop_equivalence_oracle_spec.md` (added during this revision);
  reclassify this spec when implementation lands.
- Run `tools/check_agent_contracts.py`, `check_docs_metadata.py`,
  `check_docs_drift.py`, `check_docs_staleness.py --report` and fix what they flag.

## Part C - Invariants that MUST still hold (live safety)

- `StateManager` remains the only writer of `DeckState`; native fields are reset
  with single GIL-atomic assignments.
- The 200 Hz push loop gains no blocking I/O; the resolver is pure.
- `PackOutputBackend.submit_frame()` keeps exactly one normal caller.
- Scripted tracks beat native Autoloop; Static Override Press/Toggle is
  unchanged; blackout/emergency stay above static, scripted, and Autoloop.
- SoundSwitch present -> native pack DMX suppressed by the existing auto-switch.
- The binding lookup converts the 1-based scene channel to 0-based; a wrong base
  must fail closed (dark), never render a wrong look.
- Native selection is latched: a `None` executor return holds the current look
  and advances phase; only ineligibility and reset boundaries clear it. Native
  never flickers between refires and never lights up before the executor's first
  emitted scene.
- Missing/invalid mappings fail closed and report why; no guessed Autoloop, no
  cross-role fall, no stale output.
- Native uses the exported canonical pack only; runtime never reads the live
  `.ssproj`.
- Phase uses the named `AUTOLOOP_TICKS_PER_BEAT` and the `phase_offset_beats`
  calibration input; native output stays hardware-unvalidated until the
  two-flight capture / rig A/B run proves alignment.

## Part D - Tests

```bash
python3 -m unittest tests/test_soundswitch_pack.py
python3 -m unittest tests/test_soundswitch_laser_player.py
python3 -m unittest tests/test_laser_executor.py
python3 -m unittest tests/test_state_manager_pack_driver.py
python3 -m unittest tests/test_bridge_menubar.py
python3 -m unittest tests/test_native_autoloop_resolver.py
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Run `python3 -m unittest discover tests` before publish when practical; if not,
report which targeted tests ran and why the full suite was skipped.

## Part E - Acceptance

- Native renders from exported pack mappings when SoundSwitch is absent and pack
  output is enabled; the channel lookup is proven 1-based -> 0-based.
- SoundSwitch-present behavior is unchanged and suppresses native pack DMX.
- Role/scene/note selection follows the executor's existing post-bank behavior;
  no parallel classifier or bank.
- Drop/post_drop timing reuses the executor's `DropLifecycle`-driven refire;
  mapped post_drop looks cycle every 32 beats; no-post_drop-map behavior cycles
  drop looks every 32 beats, not dark.
- The selection latches across `None` returns: no per-tick flicker, no onset
  before the first executor edge; a same-role edge (including a single-look bank)
  re-anchors phase to ~0; role changes replace the look on the executor's first
  post-change edge.
- Missing bindings/files/layout failures fail closed with distinct statuses;
  empty authored looks render dark without being errors.
- Static Override layers still apply over the native base; scripted still beats
  native.
- Pack reload clears stale native state before rendering a new mapping.
- Status shows `role`, `scene`, `note`, `soundswitch_name`, `target_identity`,
  `phase_tick`, status/reason; `autoloop_phase_blocked` and the operational-state
  enum agree with the nested block.
- Native phase uses `AUTOLOOP_TICKS_PER_BEAT` + `phase_offset_beats`; no
  hardware-validation claim without operator-approved rig evidence.

## When You Finish

Report: changed files; Task 0 result (role notes Autoloop or not); tests/checks
run and exact outcomes; whether the full suite ran; doc/contract checks status;
current git SHA; any remaining `[unknown]`.

Plain-language operator summary: what the bridge does differently live; what is
unchanged; healthy behavior to watch (SoundSwitch presence, pack status, lasers,
Static Override, Rekordbox active deck, logs); what was software-verified; what is
not hardware-validated; the exact live approval gates before restart, pack
enablement, or a rig A/B / two-flight capture.

## Adversarial self-review

- **Whole show goes dark (highest impact).** If the resolver keys the binding by
  the raw 1-based scene channel, every lookup misses and native renders black.
  Prevented by the mandated `scene.channel - 1` conversion and a dedicated test.
- **Per-tick flicker.** `on_decision` returns `None` on most ticks; a per-tick
  clear flashes the look one tick per 32 beats. Prevented by the latch (hold on
  `None`, clear only on ineligibility/reset) and the no-flicker test.
- **Wrong phase / drift vs SoundSwitch.** The bridge-to-SoundSwitch phase offset
  is not yet capture-proven. Contained by the named `AUTOLOOP_TICKS_PER_BEAT` and
  a `phase_offset_beats` knob the two-flight capture tunes, plus a deterministic
  phase test; native stays hardware-unvalidated until proven.
- **Native diverges from lasers.** Could happen if the pack driver recomputed a
  parallel scene choice. Prevented by consuming the executor's post-bank
  `LaserResolvedScene`, returned even on MIDI rejection so native tracks the same
  selection the lasers got.
- **Stale look after reload.** Prevented by resetting native state in
  `set_pack_runtime()` and a fail-closed one-tick software-zero gap.
- **Status lies.** Active native rendering could still report
  `autoloop_phase_blocked`. Prevented by migrating that flag and the
  operational-state enum and asserting agreement in tests.
- **Drop authored as a Static Look.** If a role note is not an Autoloop, native
  fails closed to `missing_binding` (dark) and the authority doc's drop fallback
  promises cannot hold. Surfaced by the Task 0 pre-check, not hidden by a guess.
