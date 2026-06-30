---
doc_status: active-spec
truth_level: code-grounded implementation spec plus operator-grilled target behavior
last_verified_commit: 74706f4
last_verified_date: 2026-06-29
validation_scope: spec only; docs/code read against current checkout; no bridge run, restart, SoundSwitch, MIDI, serial, Enttec, DMX, laser, LED/Govee, Rekordbox live sampling, or hardware validation
---

# Codex Implementation Spec - Native Autoloop DMX Runtime

Authoritative intended behavior lives in
`docs/architecture/native_autoloop_pack_authority.md`. Implement this spec
against that document and current code. If code and the authority doc disagree,
stop and report the conflict before changing runtime behavior.

## Part A - Context & Root Cause (verified; read, do not implement)

- [confirmed] The current pack runtime intentionally leaves native Autoloop DMX
  unimplemented. In Autoloop mode, `StateManager._drive_pack_output()` clears
  the pack player selection and publishes `autoloop_phase_blocked` instead of
  calling `select_autoloop()`: `state_manager.py:3808-3823`.
- [confirmed] The pure renderer already exists. `render_autoloop_frame()` renders
  a CH1-19 frame, validates non-negative integer `phase_tick`, wraps
  `phase_tick % loop.cycle_ticks`, and returns zero for inactive/unsupported
  looks: `soundswitch_laser_player.py:125-147`.
- [confirmed] `LaserPackPlayer.select_autoloop()` exists and routes to
  `_autoloop_base()`, which reports diagnostic codes for stale/ambiguous/missing
  phase, missing identity, inactive Autoloop, unsupported layout, and player
  errors: `soundswitch_laser_player.py:270-276`, `:352-378`.
- [confirmed] The pack loader exposes `LoadedPack.autoloops` but not yet an
  operator-facing runtime note-to-Autoloop map with display names:
  `soundswitch_pack_loader.py:146-156`, `:611-627`, `:672-684`.
- [confirmed] The exporter writes `selection_map.json` rows with MIDI event
  fields, `target_identity`, `target_kind`, and `target_name`:
  `soundswitch_pack.py:223-265`.
- [confirmed] SoundSwitch Autoloop catalog entries have display names:
  `soundswitch_pack_models.py:153-181`; `ResolvedControlBinding.target_name`
  carries the resolved display name: `soundswitch_pack_models.py:253-260`;
  the decoder sets it from the catalog entry at
  `soundswitch_project_decoder.py:1002-1012`.
- [confirmed] Static Override Press/Toggle is already exported and loaded for
  Static Look bindings: `soundswitch_pack_loader.py:258-297`; this behavior must
  remain unchanged.
- [confirmed] The bridge already has the 32-beat SoundSwitch refire edge:
  `AUTOLOOP_ARM_PHRASE_BEATS = 32` in `config.py:7-8`, and `StateManager`
  computes marker/phrase-anchor/interval/fallback-grid refires in
  `state_manager.py:4277-4328`.
- [confirmed] The menubar auto-switch already enables pack output when
  SoundSwitch is disconnected and disables it when connected:
  `scripts/bridge_menubar.py:388-402`, `:895-922`.
- [confirmed] The pack runtime is published atomically, and `set_pack_runtime()`
  already resets pack frame/status counters and publishes a software-zero status:
  `state_manager.py:3582-3610`.
- [confirmed] The pack driver is the sole normal `PackOutputBackend.submit_frame`
  caller and already applies Static Override/masks before rendering/submitting:
  `docs/subsystems/soundswitch_output.md:29-35`.
- [confirmed] `DropLifecycle` is the pure resolver for drop/post_drop role
  timing and configurable windows/caps: `drop_lifecycle.py:13-112`.
- [confirmed] `LaserSceneExecutor` owns the post-bank selected scene and
  shuffle-bag semantics for drop/post_drop cycle decisions:
  `laser_executor.py:184-192`, `:408-412`, `:440-471`.
- [confirmed] `LaserSceneExecutor.reset_runtime_state()` clears role, scene,
  trigger, bag, and cooldown state across lifecycle changes:
  `laser_executor.py:84-98`.
- [confirmed] `LaserDirector.reset_runtime_state()` resets drop lifecycle and
  smart observation state: `laser_director.py:322-327`, `:764-770`.
- [confirmed] `StateManager` resets laser director/executor on active-deck,
  track, scripted/idle, stop, and resume transitions; native Autoloop state must
  follow those same lifecycle boundaries.
- [assumed] The existing laser/bridge personality config is the intended timing
  and role-bank authority for native pack Autoloop scene selection.
- [assumed] `post_drop_cycle_beats` should become real for native DMX cadence,
  while remaining documented as inert for current laser MIDI cadence until a
  later laser change explicitly consumes it.
- [unknown] The exact final class/function names are implementation choices, but
  the behavior, status fields, tests, and hot-path constraints below are fixed.

Root cause: the bridge can decode and render SoundSwitch Autoloops, and it can
already decide musical roles and maintain SoundSwitch containment edges, but the
pack driver never translates the bridge-selected role scene/note into a pack
Autoloop selection. Native Autoloop mode therefore remains software-zero.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- Do not run or restart the bridge.
- Do not open SoundSwitch, Rekordbox, MIDI, serial, Enttec, Art-Net, DMX, laser,
  LED/Govee, or hardware-adjacent paths.
- Do not add blocking I/O to the 200 Hz push loop.
- Do not add a second pack output loop or a second normal
  `PackOutputBackend.submit_frame()` caller.
- Do not change scripted-track priority, Static Override Press/Toggle behavior,
  or SoundSwitch-present auto-switch semantics.
- Do not add a separate native-Autoloop dry-run/observe mode.
- Do not claim hardware validation.

### Task 1 - Pack Runtime Mapping: note -> Autoloop identity/name

Files:

- `soundswitch_pack_loader.py`
- `tests/test_soundswitch_pack.py` and/or a focused pack-loader test

Add an immutable runtime model for active IAC Autoloop selections. Minimal shape:

```python
@dataclass(frozen=True, slots=True)
class LoadedAutoloopBinding:
    device_name: str
    channel_zero_based: int
    data_byte: int
    target_identity: str
    target_name: str
```

Add a `LoadedPack.autoloop_bindings` mapping keyed by
`(channel_zero_based, data_byte)` or by a small immutable event-key dataclass.
Populate it from `selection_map.json` `iac_selections` rows where:

- `active is True`
- `device_name == "IAC Driver Bus 1"`
- `message_type == "note"`
- `target_kind == "autoloop"`
- `target_identity` is present

Validation:

- duplicate active `(channel_zero_based, data_byte)` Autoloop selections fail
  pack load
- target identity must exist in `LoadedPack.autoloops`
- `target_name` must be a non-empty string; if an old pack lacks it, fail closed
  with a clear load error rather than hiding the missing display name

Do not change Static Override Press/Toggle loading.

### Task 2 - Expose The Final Bridge-Selected Scene Without New MIDI Semantics

Files:

- `laser_executor.py`
- `laser_models.py` if a shared dataclass belongs there
- `tests/test_laser_executor.py`

Add a small immutable selection result that represents the scene the executor
selected after existing bank/cooldown/same-scene/refire rules, before or
independent of physical MIDI transport success. Minimal fields:

```python
@dataclass(frozen=True)
class LaserResolvedScene:
    role: str
    reason: str
    scene: str
    channel: int
    note: int
    scene_type: str
```

Refactor `LaserSceneExecutor.on_decision()` so existing behavior is unchanged
and callers may also receive the resolved scene:

- keep all existing gates, cooldown behavior, role-bank/shuffle behavior, mask
  behavior, logging, and backend trigger behavior
- return `LaserResolvedScene | None`
- return `None` when no scene is selected or an existing policy gate blocks the
  scene
- do not make native DMX depend on physical MIDI delivery success; MIDI backend
  rejection is a MIDI actuation failure, not proof the role/note mapping is
  invalid for pack rendering

StateManager will capture this return value on each tick. Existing callers that
ignore the return must continue to work.

### Task 3 - Native Autoloop Resolver

Files:

- new `native_autoloop_resolver.py`
- new `tests/test_native_autoloop_resolver.py`

Create an I/O-free resolver. It may be a pure function over explicit state
in/state out, or a tiny state object with deterministic inputs. Keep it boring.

Inputs must include:

- current pack generation/hash or manifest SHA
- `LoadedPack.autoloop_bindings`
- current `LaserResolvedScene | None`
- current deck/load identity
- `lighting_mode`, `scripted_id`, playing/fresh/stale/track_changed/discontinuity
  gates from the existing pack driver
- current `abs_beat_pos`
- current `autoloop_tick_just_fired`
- configured cadence/timing constants: `AUTOLOOP_ARM_PHRASE_BEATS`,
  `drop_impact_beats`, `max_drops_in_a_row`, and native `post_drop_cycle_beats`
  where applicable

Decision output must include:

- `status`: one of `rendering_active`, `empty_dark_look`, `missing_binding`,
  `missing_autoloop_file`, `unsupported_layout`, `soundswitch_present_native_suppressed`,
  `software_zero_frame`, or another documented short reason
- `role`
- `scene`
- `note`
- `soundswitch_name`
- `target_identity`
- `anchor_beat`
- `phase_tick`
- `reason`
- `diagnostic`

Behavior:

- If pack output is disabled because SoundSwitch is present, report
  `soundswitch_present_native_suppressed`.
- If not in eligible Autoloop mode, clear state and report software-zero.
- If scripted is active, do not select Autoloop.
- On role change, select the new role scene immediately and anchor phase at `0`.
- On same-role 32-beat edge, reselect/restart within the role bank semantics
  already applied by `LaserSceneExecutor`.
- Between reselect edges, compute `phase_tick` from bridge beat position:
  `round((abs_beat_pos - anchor_beat) * 600)`, clamped to non-negative int.
- Missing note binding fails closed with `missing_binding`.
- Missing pack identity fails closed with `missing_autoloop_file`.
- Unsupported player/layout diagnostics fail closed with `unsupported_layout`.
- A valid mapped look that renders all zero is `empty_dark_look`, not an error.

No file reads, config reads, socket/serial/MIDI calls, subprocesses, sleeps, or
backend calls are allowed in this resolver.

### Task 4 - Wire StateManager Pack Driver

Files:

- `state_manager.py`
- `tests/test_state_manager_pack_driver.py`

Add native state fields on `StateManager` for the resolver. Reset them wherever
current laser director/executor state resets:

- active deck/master change
- active track load
- scripted/idle transition
- stop/resume
- pack runtime reload/replacement via `set_pack_runtime()`

In `_push_tick_inner()`, capture the `LaserResolvedScene | None` returned by
`self._laser_executor.on_decision(decision, ctx)` and store it for the following
pack-driver call in the same tick.

In `_drive_pack_output()`:

- preserve existing Static Override/mask handling
- preserve scripted priority exactly
- when scripted transport is not active and Autoloop mode is eligible, call the
  native resolver
- if the resolver returns a valid `target_identity` and `phase_tick`, call
  `player.select_autoloop(target_identity, phase_tick, authority="fresh")`
- otherwise call `player.clear_selection()`
- render once and submit once through the existing backend path
- preserve fail-closed ZERO on exceptions

The pack player layering should remain:

`native/scripted base -> static layers -> blackout/emergency mask -> submitted frame`

### Task 5 - Status And Logs

Files:

- `state_manager.py`
- `runtime_status.py` only if command/status schema validation needs it
- `scripts/bridge_menubar.py` only if row rendering truncation/status text needs it
- `tests/test_state_manager_pack_driver.py`
- `tests/test_bridge_menubar.py` if touched

Extend the existing `soundswitch_pack` status row. Do not create a new status
surface.

Add a nested sanitized block, for example:

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

Required statuses:

- `soundswitch_present_native_suppressed`
- `rendering_active`
- `empty_dark_look`
- `missing_binding`
- `missing_autoloop_file`
- `unsupported_layout`
- `software_zero_frame`

Logs should be bounded and only on meaningful status/identity changes, not every
200 Hz tick.

### Task 6 - Tests

Required focused tests:

- pack loader exposes note -> Autoloop identity/name for active IAC Autoloops
- pack loader fails on duplicate active Autoloop note bindings
- pack loader fails when a binding lacks `target_name`
- native resolver maps final scene/note to target identity/name
- native resolver fails closed on missing binding
- native resolver distinguishes missing file, unsupported layout, empty dark,
  and active render
- native resolver resets phase on role change
- native resolver resets phase on same-role 32-beat edge
- phase advances from beat position between cycle edges
- scripted mode still beats native Autoloop
- stop/unload/stale/discontinuity clear native base to zero
- Static Override remains layered above native Autoloop
- pack reload clears old native state and allows a one-tick software-zero gap
- SoundSwitch-present auto-switch suppression status is visible

Update or delete obsolete assertions that `select_autoloop()` is never called;
replace them with narrower assertions for unsupported/ineligible cases.

### Task 7 - Docs And Contracts

This implementation changes SoundSwitch pack runtime behavior. Update the
matching `soundswitch_pack_player` contract docs listed in
`docs/agents/change_contracts.yml` where behavior/status changes are described.

At minimum, implementation must update:

- `docs/subsystems/soundswitch_output.md`
- `docs/status/active_work_registry.md`
- `docs/architecture/doc_index.md`
- `docs/plans/active/soundswitch_exporter_remaining_work.md`
- `docs/validation/software_test_inventory.md` if tests are added

Move this spec to completed or classify it according to the repo's doc lifecycle
when implementation lands. Do not leave an active doc unclassified.

## Part C - Invariants That MUST Still Hold

- `StateManager` remains the central runtime owner and only writer of
  `DeckState`.
- The 200 Hz push loop gains no blocking I/O: no serial, MIDI, socket, file,
  subprocess, sleeps, or config reads inside native selection/rendering.
- `PackOutputBackend.submit_frame()` still has only the existing pack-driver
  caller in normal operation.
- Scripted tracks remain higher priority than native Autoloop.
- Static Override Press/Toggle behavior remains exported-pack authority.
- Blackout/emergency remain above static, scripted, and Autoloop.
- SoundSwitch present means native pack DMX is suppressed by the existing
  auto-switch behavior.
- Missing/invalid mappings fail closed and report why.
- Native Autoloop uses the exported canonical pack only; runtime does not read
  the live `.ssproj`.
- Hardware status remains hardware-unvalidated until operator-approved rig
  evidence exists.

## Part D - Tests

Run, at minimum:

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

Run `python3 -m unittest discover tests` when practical before publish. If it is
not practical, report exactly which targeted tests were run and why the full
suite was skipped.

## Part E - Acceptance

Implementation is acceptable only when:

- Native Autoloop renders from exported pack mappings when SoundSwitch is absent
  and pack output is enabled.
- SoundSwitch-present behavior remains unchanged and suppresses native pack DMX.
- Role/scene/note selection follows existing bridge/laser role-bank behavior.
- Drop/post_drop timing reuses existing configurable timing knobs and
  `DropLifecycle`.
- Same-role 32-beat cycle/reselect restarts phase at `0`.
- Role changes replace the old Autoloop immediately and anchor the new one at
  `0`.
- Missing bindings/files/layout support failures fail closed with distinct
  statuses.
- Empty authored looks render dark without being treated as errors.
- Static Override layers still apply over the automatic base.
- Scripted tracks still beat native Autoloop.
- Pack reload clears stale native state before rendering a new mapping.
- Status shows `role`, `scene`, `note`, `soundswitch_name`, `target_identity`,
  `phase_tick`, and short status/reason.
- No live/hardware validation claim is made without operator-approved evidence.

## When You Finish

Report:

- changed files
- tests/checks run and exact outcomes
- whether full test suite ran
- whether docs checks passed or which doc lifecycle entries still need updates
- current git SHA
- any remaining `[unknown]` claims

Plain-language operator summary must include:

- what the bridge should do differently live
- what remains unchanged
- healthy behavior to watch for in SoundSwitch presence, pack status, lasers,
  Static Override, Rekordbox active deck, and bridge logs
- what was software-verified
- what was not hardware-validated
- exact live approval gates before restart, pack enablement, or rig A/B checks

Adversarial self-review:

- Main failure mode: native DMX could drift from the scene the bridge actually
  selected for lasers, causing SoundSwitch pack output to show one role while
  laser output shows another. The spec prevents this by requiring the final
  post-bank/post-gate selected scene from `LaserSceneExecutor` to be exposed and
  consumed, instead of recomputing a parallel scene choice in the pack driver.
- Second failure mode: the pack driver could keep rendering an old Autoloop
  after export/reload. The spec prevents this by requiring native state reset on
  `set_pack_runtime()` and a fail-closed gap until the new mapping is proven.
- Third failure mode: missing Laser Pad/SoundSwitch mapping drift could be
  hidden by a fallback. The spec prevents this by requiring `missing_binding`
  and no guessed Autoloop.
