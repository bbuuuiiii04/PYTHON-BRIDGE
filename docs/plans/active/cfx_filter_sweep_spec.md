---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 02588d7
last_verified_date: 2026-07-09
validation_scope: >
  AWR-173 implementation spec, authored from current-code inspection at 02588d7 plus the
  committed Rekordbox 7.2.11 mixer RE evidence. Every file:line below was re-read at HEAD
  on 2026-07-09. No code has been implemented; no process-memory sampling, bridge restart,
  or hardware output happened while authoring. SOFTWARE-VALIDATED ONLY targets;
  HARDWARE-UNVALIDATED until the operator desk session.
---

# Codex Implementation Spec - CFX Filter-Sweep LED Behavior (AWR-173)

Operator-confirmed feature (final ruling, binding): when the CFX FILTER knob sweeps
**low-to-high (clockwise / high-pass) only**, the Govee strips flood quick-but-not-instant
with the track's **darkest v2 palette hue**. **Crossing an ear-calibrated bloom threshold
TRIGGERS a one-shot timed drain** — the flood swells, then the room dims from 1.0 to
`dim_floor` over `drain_ms` and holds there; **the dim is NOT knob-tracked, and holding the
knob past the bloom does nothing extra** (peak-then-drain, operator re-ruled at the desk
2026-07-09). Riding the knob **back below the threshold releases the whole overlay** — the
flood and the dim both fade back to the normal look over `release_ramp_ms`, as if nothing
was interrupted; a fresh push past the threshold re-triggers. At 12 everything is normal.
**Counterclockwise / low-pass does NOTHING — no mirror variant, ever.**

Build order (executive-ruled): (1) CFX runtime read — the first runtime consumer of the
mixer RE evidence; (2) LED behavior on top; (3) desk calibration session with the operator
(runbook in Part F).

## Part A - Context & Root Cause (verified; read, do not implement)

- [confirmed] No CFX runtime read exists at HEAD. `rb_offsets.py`, `rb_memory.py`,
  `rb_state_reader.py` contain zero CFX code (grepped at `02588d7`).
- [confirmed] The mixer read path is the template. Named optional offset chains
  (`_REQUIRED_MIXER_LABELS`, `rb_offsets.py:196-201`; fail-closed group parser
  `_parse_optional_mixer_lines` `rb_offsets.py:204-239`), optional fields on
  `RBOffsetVersion` (`rb_offsets.py:180-183`), reader-thread tick `_tick_mixer`
  (`rb_state_reader.py:526-575`), validated f32 reads
  `_follow_finite_f32_result` (`rb_state_reader.py:775-796`, reasons
  `unreadable` / `non_finite` / `out_of_range`), frozen snapshot models
  `MixerDeckReading` / `MixerAuthoritySnapshot` (`models.py:120-139`), event
  `Ev.MIXER_STATE` consumed in `StateManager._handle_event`
  (`state_manager.py:1362-1366`).
- [confirmed] **Isolation trap (the one line that can hurt the live show):**
  `_tick_mixer` invalidates the WHOLE mixer-authority snapshot when ANY of its four
  reads fails (`rb_state_reader.py:552-561`), and that snapshot drives active-deck
  resolution (`state_manager.py:1883-1938`). CFX reads must therefore live in their own
  tick/event/snapshot and never join `_tick_mixer`'s reads tuple. This is now a
  contract-level forbidden assumption (`docs/agents/change_contracts.yml`,
  `rekordbox_readers.forbidden_assumptions`, added 2026-07-09).
- [confirmed] CFX FILTER chains are RE-proven for local Rekordbox 7.2.11 only, as
  tracking/status data: `docs/research/rekordbox_mixer_active_deck_re_evidence.md:154-228`
  (Ghidra static + operator-approved passive one-control-at-a-time proof; param0 is a
  normalized `0..1` f32 at `layer + 0xe8`; selected effect id `0` = FILTER at
  `layer + 0x70`; `unit_channel` i32 at `cfx_unit + 0xd0`). The RE doc requires a future
  reader to validate `unit_channel`, selected effect id, and finite readable values
  before trusting a CFX value (`:200-204`).
- [assumed] `param0 > 0.5` = clockwise / high-pass, `param0 < 0.5` = counterclockwise /
  low-pass. The passive proof shows the value range and per-deck isolation, not the
  physical rotation direction. Task 1's probe verifies this at the desk before any LED
  behavior is trusted; if inverted, flip the mapping constant in one place
  (`cfx_sweep` envelope, Task 6) — do not guess.
- [confirmed] The darkest palette hue exists and is derivable: v2 identity dressings put
  the darkest base slot at `Dressing.slot_rgbs[0]` (`led_identity_v2.py:184-198` —
  slot 0 evaluates the base ramp at its low end). Engine holds the active dressing via
  `_v2_active_dressing()` (used at `led_color_engine.py:1121, 1164`).
- [confirmed] The continuous parent→child channel for a live scalar already exists: the
  frame-engine client pumps a `BeatAnchor` every ~20 ms (`_pump_anchor`
  `govee_frame_engine_client.py:331-338`, wire form `_anchor_to_wire` `:497-505`), the
  child parses it (`govee_frame_engine.py:226-237`) and the runner consumes it per frame
  (`GoveeRealtimeRunner._tick_once` `govee_realtime_runner.py:285`,
  `_compose_frame` `:432-458`). The parent-side provider is
  `get_active_beat_anchor` (`led_dispatch_policy.py:439-464`), wired at
  `__main__.py:1167`.
- [confirmed] `request_brightness` is the WRONG channel for this feature: it is a
  device-level LAN command owned by blackout/restore
  (`led_dispatch_coordinator.py:241, 253`; wire path
  `govee_frame_engine_client.py:145-149`). A 30 Hz knob-tracked dim through it would spam
  UDP and race the blackout owner. Do not touch it.
- [confirmed] Feature kill-switch pattern to copy: `IdentityV2Config.enabled = False`
  default (`led_models.py:83-84`), example config ships `false`
  (`config/led_look_director.example.json:42-43`), loader fails closed to the disabled
  dataclass. Tune-live constants live in the config dataclass, not module constants
  (`led_models.py:91, 95` are the precedent).
- [confirmed] Blackout/emergency precedence today: emergency short-circuits LED
  automation before look selection (`led_dispatch_policy.py:1163`,
  `led_look_director.py:156-170`); the child-side emergency path
  (`govee_realtime_runner.py:172, 509`) never flows through `_compose_frame`.
- [confirmed] F2 owns intentional darkness around drops (`led_models.py:114-165`); F4 is
  texture-only and never touches brightness (`led_models.py:186-226`).

Root cause framing: the bridge already reads the mixer for authority but is deaf to the
one knob the operator rides most. The feature adds a read-only CFX tracking channel and a
frame-space flood/dim overlay that composes with (and always loses to) every existing
darkness owner.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- Out of scope: `laser_*`, `soundswitch_*`, `osl_output.py`, `sound_switch_engine.py`,
  `os2l_injector.py`, autoloop/scripted/drop logic, `runtime_status.py` command surface,
  `active_deck_resolver.py`, `rb_memory.py`. Do not add runtime commands. Do not create
  git branches; work on `main`. You may be in a dirty worktree — never revert or clean
  files you did not change; no destructive git.
- Behavior that must not change: active-deck resolution, mixer-authority validity, master
  handling, transport/play inference, ANLZ-before-TRACK_LOADED ordering, blackout and
  Static Override semantics, F2/F4 behavior, all laser behavior.
- **CFX never feeds authority.** No CFX value, validity, or staleness may reach
  `resolve_active_deck`, `_resolver_deck_inputs`, `MixerAuthoritySnapshot`, or
  `_tick_mixer`.
- The 200 Hz push loop gains no blocking I/O and no new work beyond reading one
  in-memory tuple. All process-memory reads stay on the `RBStateReader` thread.
- Error handling: fail closed toward today. Any missing/invalid input (no chains for the
  RB version, wrong selected effect, unit-channel mismatch, non-finite/out-of-range read,
  stale snapshot, v2 identity off, feature flag off, emergency/blackout active) means the
  overlay is inert and the room renders exactly as it does today. No broad try/except, no
  silent success-shaped fallbacks — invalid readings carry a short `reason` string like
  the mixer path does.
- Do not restart the bridge, sample process memory, or open any output path in the
  implementation turn. Software tests only. (The Task 1 probe is run later BY or WITH the
  operator at the desk, not during implementation.)

### Task 1 - `probe_cfx_filter.py` (repo root): passive desk-calibration probe

Mirror the structure of the existing root probes (`probe_live_bpm.py`, `probe_deck2.py`):
a standalone read-only CLI, no bridge import side effects, no writes to the RB process.

- Attach passively: `task_for_pid` + vmmap TEXT base, same helpers pattern as
  `rb_state_reader.RBStateReader._attach` (`rb_state_reader.py:251-259`).
- Resolve the six CFX chains for the detected RB version via `rb_offsets`
  (Task 2 fields). If the version has no CFX chains, print that and exit nonzero.
- Loop at ~10 Hz printing one line per sample per deck:
  `deck=1 selected_id=0 unit_ch=0 param0=0.732 [VALID]` (validity = selected id `0`,
  unit channel == deck channel, finite `0..1`).
- On Enter keypress, print a `MARK param0=<value>` line for the active sample (both
  decks). This is the bloom-threshold capture used in Part F.
- Ctrl-C exits cleanly.

### Task 2 - `rb_offsets.py`: named CFX chain group (independent fail-closed)

- Add to the `7.2.11` block of `_OFFSETS_MACOS_ARM64` (after the MIXER lines,
  `rb_offsets.py:108-111`), values transcribed from
  `docs/research/rekordbox_mixer_active_deck_re_evidence.md:165-199`:

  ```text
  CFX_D1_FILTER_PARAM0 04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8
  CFX_D2_FILTER_PARAM0 04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8
  CFX_D1_SELECTED_ID   04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 70
  CFX_D2_SELECTED_ID   04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 70
  CFX_D1_UNIT_CHANNEL  04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 D0
  CFX_D2_UNIT_CHANNEL  04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 D0
  ```

- Add six `Optional[ChainEntry] = None` fields to `RBOffsetVersion`
  (`rb_offsets.py:171-183`): `cfx_deck1_filter_param0`, `cfx_deck2_filter_param0`,
  `cfx_deck1_selected_id`, `cfx_deck2_selected_id`, `cfx_deck1_unit_channel`,
  `cfx_deck2_unit_channel`.
- Add `_REQUIRED_CFX_LABELS` as a SEPARATE label group. Extend
  `_parse_optional_mixer_lines` (or add a sibling `_parse_optional_cfx_lines` called from
  the same spot in `parse_offsets`) so that:
  - a malformed/duplicate/partial CFX group fails closed to `(None,)*6` for CFX **without
    touching the mixer group**, and a malformed mixer group must equally not disable a
    healthy CFX group;
  - anonymous trailing chains keep today's behavior (warned, ignored,
    `rb_offsets.py:229-234`).
- No CFX lines for any version other than `7.2.11` — other versions stay `None` ⇒
  feature inert there by construction.

### Task 3 - `models.py`: CFX snapshot models + event kind

- `Ev.CFX_STATE = "cfx_state"` in `class Ev` (`models.py:245+`).
- Frozen dataclasses next to the mixer models (`models.py:120-139`):

  ```python
  @dataclass(frozen=True)
  class CfxDeckReading:
      deck: int                 # bridge deck 1/2
      filter_norm: float        # param0, already 0..1 per RE evidence
      selected_effect_id: int   # 0 == FILTER
      unit_channel: int         # must equal deck - 1
      valid: bool               # id==0 and unit_channel==deck-1 and finite 0..1
      reason: str               # "ok" | "unreadable" | "non_finite" | "out_of_range"
                                # | "wrong_effect" | "unit_channel_mismatch"

  @dataclass(frozen=True)
  class CfxFilterSnapshot:
      valid: bool               # chains present and both decks attempted
      deck: Mapping[int, CfxDeckReading]
      updated_at: float
      reason: str
      # __post_init__ wraps deck in MappingProxyType, same as MixerAuthoritySnapshot
  ```

  Per-deck validity is deliberate (unlike the mixer snapshot): deck 1's knob must keep
  working when deck 2's CFX unit is unreadable.

### Task 4 - `rb_state_reader.py`: `_tick_cfx` on the reader thread

- Add `_follow_i32` mirroring `_follow_i64` (`rb_state_reader.py:798-806`) — 4-byte
  `<i` read at the chain address.
- Add `_tick_cfx(task, base)` called from `_tick` right after the `_tick_mixer` call
  site (`rb_state_reader.py:287`), gated only on the six CFX chains being non-None
  (NOT on `_mixer_authority_enabled` — the two features are independent).
- Per deck: read param0 via `_follow_finite_f32_result(..., minimum=0.0, maximum=1.0)`,
  selected id and unit channel via `_follow_i32`. Build `CfxDeckReading` with `valid` and
  `reason` per Task 3. Missing chains ⇒ enqueue an invalid snapshot with
  `reason="missing_offsets"`, mirroring `_tick_mixer`'s shape
  (`rb_state_reader.py:536-544`).
- Enqueue `BridgeEvent(Ev.CFX_STATE, 0, {"snapshot": snapshot}, "rb_state")` via
  `self._enqueue` every tick (~30 Hz, same cadence discipline as `_tick_mixer`).
- `Ev.CFX_STATE` must NOT be added to `_authoritative_kinds`.

### Task 5 - `state_manager.py`: store the snapshot, nothing else

- In `_handle_event`, alongside the `Ev.MIXER_STATE` branch (`state_manager.py:1362`):
  `elif ev.kind == Ev.CFX_STATE:` → `self._cfx_snapshot = ev.payload["snapshot"]`.
  **No resolver rerun, no output-state flags, no status coupling.**
- Init `self._cfx_snapshot: CfxFilterSnapshot | None = None` next to
  `self._mixer_snapshot` (`state_manager.py:800`).
- Constant `CFX_STALE_AFTER_S = 1.0` next to `MIXER_STALE_AFTER_S`.

### Task 6 - LED envelope (pure function) + config + anchor fields

**Config** — new `cfx_sweep` block in `led_look_director.json`, dataclass in
`led_models.py`, loader in `led_config.py` following the F2/F4/v2 fail-closed pattern
(`led_config.py:151-181`, `1423-1478`):

```python
@dataclass(frozen=True)
class CfxSweepConfig:
    enabled: bool = False              # kill switch; example config ships false
    engage_deadband: float = 0.02      # knob must exceed 0.5 + this to do ANYTHING
    bloom_threshold_norm: float = 0.75 # DESK-CALIBRATED (Part F); placeholder until then
    flood_ramp_ms: float = 250.0       # TUNE-LIVE: "quick but not instant" flood-in
    release_ramp_ms: float = 400.0     # TUNE-LIVE: flood-out when knob returns to 12
    dim_floor: float = 0.08            # brightness at the drained floor (never fully black)
    drain_ms: float = 800.0            # TUNE-LIVE: drain feel — dim 1.0 -> floor after the trigger
    rearm_hysteresis: float = 0.02     # knob must fall below thr - this before it can re-fire
```

Example JSON: add the block with `"enabled": false` to
`config/led_look_director.example.json`. Loader returns `CfxSweepConfig()` (disabled) on
absent/malformed block; validate numeric ranges (`0 < bloom_threshold_norm < 1`,
`0.5 + engage_deadband < bloom_threshold_norm`, ramps `> 0`, `0 <= dim_floor < 1`,
`drain_ms > 0`, `0 <= rearm_hysteresis < 0.2`).

**Envelope** — module-level pure function + a tiny frozen `CfxEnvState(mix, dim, armed)`
carried across ticks, in `led_dispatch_policy.py` (pure-function test seam, no I/O, no
time reads — caller passes `dt_s`):

```python
def cfx_sweep_envelope(knob_norm, state, dt_s, cfg) -> CfxEnvState:
    """Trigger semantics (operator re-ruled at the desk 2026-07-09). Low-to-high ONLY.
    CfxEnvState carries (mix, dim, armed, fired): `armed` = fire latch, `fired` = the
    post-trigger regime, which persists until the knob returns to idle.
    IDLE  (knob <= 0.5 + deadband): resets the engagement (armed, not fired); mix ramps
          to 0 over release_ramp_ms; dim -> 1.0.
    FLOOD (engaged, NOT yet fired this engagement, knob <= thr): mix ramps to 1 over
          flood_ramp_ms; dim = 1.0.
    FIRE  (armed AND knob > thr — edge-triggered, incl. a single-tick jump from below the
          deadband to above thr): armed -> False, fired -> True. The flood IS the swell.
    FIRED (fired, knob > thr): dim ramps 1.0 -> dim_floor over drain_ms, then HOLDS; knob
          position above thr has NO further effect.
    RELEASE-AFTER-FIRE (fired, knob <= thr): mix -> 0 AND dim -> 1.0 together over
          release_ramp_ms — the whole overlay lets go. The flood does NOT come back while
          riding down; only a fresh push past thr (once re-armed) re-fires, and only a
          return to idle re-enables a fresh FLOOD.
    Re-arm only once knob < thr - rearm_hysteresis, so jitter at the threshold cannot
    machine-gun the trigger. Counterclockwise (knob < 0.5) is identical to neutral.
    Never negative, never > 1, robust to dt_s == 0 and to jitter at exactly 0.5 / thr."""
```

**Per-tick wiring** — in the LED dispatch path (the same code that maintains
`self._led_rt_beat`), compute and store one atomic tuple
`self._led_cfx_sweep: tuple[float, float, tuple[int,int,int], float] | None`
(= mix, dim, flood_rgb, captured_monotonic), where:

- inputs come from `self._cfx_snapshot` (fresh within `CFX_STALE_AFTER_S`, deck reading
  for the CURRENT active deck, `valid` only) and the engine's darkest slot;
- add engine accessor `LedColorEngine.v2_darkest_rgb() -> tuple[int,int,int] | None`
  returning `self._v2_active_dressing().slot_rgbs[0]` (None when v2 off / no dressing) —
  call it from the LED tick thread only, same thread the engine is driven from today;
- force the stored tuple to None (inert) when ANY of: feature disabled, blackout /
  emergency active (`_led_blackout_active()`), an F2 smart-breakdown section owns the
  frame (`_os.breakdown_active`), the smart-drop pre-drop tactical blackout is held
  (`_led_smart_drop_blackout_key` non-empty — it sets no blackout owner), v2 dressing
  None, snapshot stale/missing/invalid for the active deck, active deck not in (1, 2).

**Anchor extension** — `BeatAnchor` (`led_models.py:405-413`) gains
`cfx_mix: float = 0.0`, `cfx_dim: float = 1.0`,
`cfx_rgb: tuple[int, int, int] | None = None`. `get_active_beat_anchor`
(`led_dispatch_policy.py:439-464`) attaches the stored tuple ONLY in the real-playback
branch, and neutralizes it if `captured_monotonic` is older than 0.5 s; the idle
freewheel branch (`:444-451`) always sends neutral. `_anchor_to_wire`
(`govee_frame_engine_client.py:497-505`) gains the three fields.

### Task 7 - frame-engine child: apply the overlay in frame space

- `govee_frame_engine.py` anchor parse (`:226-237`): read the three fields with
  `a.get("cfx_mix", 0.0)` / `a.get("cfx_dim", 1.0)` / `a.get("cfx_rgb")` so an OLD
  parent or a version-skewed FROZEN child (USB launcher ships a frozen frame engine)
  never crashes — missing fields mean neutral.
- `govee_realtime_runner.py`: in `_tick_once` (`:285`), where the composed frame comes
  back from `_compose_frame` (`:432-458`) and before the transport send, apply per pixel:
  `out = scale(lerp(px, cfx_rgb, cfx_mix), cfx_dim)` — only when `cfx_mix > 0.0` or
  `cfx_dim < 1.0`, and only on the composed-frame path. The blank/idle/emergency paths
  (`_idle_tick` `:484`, `_emergency_teardown` `:509`, `blank()` `:436`) are untouched, so
  blackout wins by construction. Reuse the renderer's existing channel-scale helper
  (`govee_frame_renderer.py:101-106` `_scale`) rather than writing a new one; the lerp is
  three integer mixes, clamped 0..255.
- `tools/led_pad_playback.py` and `scripts/direct_rt_groove_chase.py` construct
  `BeatAnchor` without the new fields — defaults keep them working; do not edit them.

### Task 8 - status visibility (small, no new command)

- Include a compact `cfx` dict (valid flags + filter_norm per deck + snapshot age) in the
  existing LED/status payload the same way mixer authority is surfaced in `OutputState` /
  status providers — read-only diagnostics so the desk session can see what the bridge
  sees. Do not add new runtime commands.

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no blocking network/socket/MIDI/filesystem/subprocess I/O
  (AGENTS.md §6). All CFX process-memory reads run on the `RBStateReader` thread; the
  anchor provider only reads pre-computed in-memory tuples.
- Active-deck resolution, mixer-authority validity, and `MASTER_CHANGED` behavior are
  byte-identical with the feature present (on OR off). A dead/garbage CFX chain while the
  mixer chains are healthy must leave `MixerAuthoritySnapshot.valid == True` (pinned by
  test, Part D).
- Blackout and emergency masks always win: the overlay is forced inert at the dispatch
  gate AND structurally bypassed on the child's blank/emergency paths. Held Static
  Override, scripted arms/clears, autoloop, BPM/beat sends: untouched.
- The dispatch gate (`_compute_led_cfx_sweep`) forces the overlay inert on all three
  darkness signals so the room stays black when it is meant to: blackout/emergency
  owners (`_led_blackout_active()`), F2 smart-breakdown sections
  (`_os.breakdown_active`), and the smart-drop pre-drop tactical blackout
  (`_led_smart_drop_blackout_key` — it sets no blackout owner and rides the permitted
  compose path on the child, so the gate is the only place it is caught). F2 darkness
  moments own their frames; the overlay is inert while they hold.
- `RBStateReader._tick_deck` still enqueues `ANLZ_PATH` before `TRACK_LOADED`; no change
  to any `_tick_deck` logic.
- Fail toward today: RB version ≠ 7.2.11, v2 identity off, feature flag off, stale/invalid
  CFX, non-FILTER effect selected — each independently renders the feature invisible.
- Frozen-child compatibility: a frame-engine child WITHOUT Task 7 must keep working
  against a parent WITH Task 6 (extra wire fields ignored), and vice versa (missing
  fields → neutral).
- Counterclockwise (knob < 0.5) produces zero behavior difference from neutral — pinned
  by test; this is the operator's final ruling, not a default.

## Part D - Tests

Pure seams only — no mach, no live process, no sockets. Reuse the existing fakes:
`MockMem.install_chain` (`tests/test_rb_state_reader.py:43-58`) and the offsets parsing
harness (`tests/test_rb_offsets.py`).

1. `tests/test_rb_offsets.py` — CFX label group parses to the six `ChainEntry`s
   (exact-chain assertion like `test_named_mixer_chains` `:85-100`); partial/duplicate/
   malformed CFX group fails closed to all-None **while mixer chains stay parsed**, and
   the mirror case (bad mixer group, healthy CFX group) keeps CFX parsed; anonymous
   trailing chains still ignored.
2. `tests/test_rb_state_reader.py` — valid snapshot (id 0, matching unit channel, in-range
   param0); `wrong_effect` when selected id ≠ 0; `unit_channel_mismatch`; `non_finite` /
   `out_of_range` / `unreadable` reasons; per-deck independence (deck 1 valid while
   deck 2 unreadable); **the isolation pin: CFX chains broken + mixer chains healthy ⇒
   `MIXER_STATE` snapshots stay `valid=True`**; `Ev.CFX_STATE` never lands in
   `_authoritative_kinds`.
3. Envelope unit tests (`tests/test_led_cfx_sweep.py`), TRIGGER semantics: knob
   0.0/0.3/0.49/0.5 ⇒ exactly neutral (CCW ruling); flood-only below threshold ramps mix
   0→1 at `flood_ramp_ms` with dim 1.0 and stays armed; crossing the threshold fires the
   drain exactly once (dim 1.0→`dim_floor` over `drain_ms`, then holds); three different
   held knob values above threshold ⇒ same dim (knob position has no effect); single-tick
   jump 0.4→0.95 both floods and fires; release-after-fire fades mix AND dim together at
   `release_ramp_ms`, and a re-push re-triggers only after re-arm hysteresis; threshold
   jitter does not re-fire while not re-armed; dt=0 and out-of-range knob inputs are safe.
4. Gating tests (led dispatch): feature off / blackout / F2-darkness hold / v2 off /
   stale snapshot / invalid active-deck reading / active_deck 0 each force the stored
   tuple inert; the freewheel anchor branch always carries neutral cfx; a stale stored
   tuple (> 0.5 s) neutralizes at the provider.
5. Child-side tests: anchor wire messages WITHOUT the new fields parse to neutral
   (frozen-child skew); with fields, `_tick_once`'s output frame equals
   `scale(lerp(frame, rgb, mix), dim)` for a known composed frame; blank/emergency paths
   emit unmodified frames regardless of cfx fields.
6. Config loader tests: absent block ⇒ disabled defaults; malformed values ⇒ disabled;
   range validation rejects `bloom_threshold_norm <= 0.5 + engage_deadband`.

## Part E - Acceptance (definition of done)

- [ ] All Part D tests green; `python3 -m unittest discover tests` from the repo root
      shows ONLY the five known environmental reds (no new failures).
- [ ] Three hard checks green: `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] `rekordbox_readers` contract docs updated: `docs/subsystems/rekordbox_readers.md`
      (CFX tracking path + the isolation rule), `docs/status/support_matrix.md`,
      `docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`,
      `docs/validation/software_test_inventory.md`,
      `docs/agents/task_playbooks/change_rekordbox_reader.md` (CFX notes).
- [ ] `led_govee` contract docs updated: `docs/subsystems/led_govee.md`,
      `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
      `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`,
      `docs/status/active_work_registry.md` (AWR-173 row → implemented/software-tested),
      `docs/agents/task_playbooks/change_led_govee_behavior.md`.
- [ ] Contract `key_symbols` extended WITH the landing code (not before):
      `CfxDeckReading`, `CfxFilterSnapshot` under `rekordbox_readers`; `CfxSweepConfig`
      under `led_govee`.
- [ ] Status language: `implemented` / `software-tested` / `hardware-unvalidated` only.
      The bloom threshold and ramps stay labeled `pending desk calibration`.
- [ ] Example config ships `cfx_sweep.enabled: false`; no live/gitignored config touched;
      no secrets, IPs, or device IDs committed.

## When You Finish

Report: changed files; tests/checks run with outcomes; the five-red baseline confirmation;
which docs each contract required and that each was updated.

Plain-language operator summary to include: "The bridge can now see your filter knob
(Rekordbox 7.2.11 only). With the switch ON and a track's v2 palette active, turning the
knob clockwise from 12 floods the strips with the track's darkest color; the moment you
cross your calibrated bloom point the room swells then dims itself down over about a
second and holds there — holding the knob past that point does nothing more; ride the knob
back below the bloom and the whole thing fades back to normal, as if nothing happened. At
12 everything is normal. Counterclockwise does nothing. Blackouts, emergency, and drop
darkness always win. The switch ships OFF; nothing changes until your desk session sets
the bloom point. Software-tested only — your desk run is the live gate."

## Part F - Desk calibration runbook (operator in session)

Step 0 happens BEFORE trusting any LED behavior; the bridge is not needed for steps 0-2.

0. **Direction check (kills the one [assumed] claim).** Rekordbox running, FILTER
   selected. Run `python3 probe_cfx_filter.py`. Sweep deck 1 knob full CCW → full CW.
   Expect param0 ≈ 0.0 at full CCW, ≈ 0.5 at 12, ≈ 1.0 at full CW, `[VALID]` throughout.
   If inverted, stop and report — the envelope mapping flips in one place.
1. **Bloom capture.** Play a bass-heavy track on deck 1. Sweep slowly clockwise from 12.
   At the ear-bloom moment ("that's the point" — the resonant widening just before the
   lows vanish), press Enter. Repeat 2-3 times; take the median `MARK param0` value.
2. **Pin it.** Write the median into `cfx_sweep.bloom_threshold_norm` in the live
   `config/led_look_director.json`, set `"enabled": true` there (live config is
   gitignored; the example stays `false`).
3. **Feel pass.** Start the bridge via the menubar watcher only (never raw
   `python3 -m rb_ss_bridge_v2`); verify exactly one process
   (`pgrep -f rb_ss_bridge_v2 | wc -l` == 1). Ride the knob: flood speed
   (`flood_ramp_ms`), return feel (`release_ramp_ms`), bottom brightness (`dim_floor`),
   and **`drain_ms` — the drain feel knob**: how long the room takes to dim from the
   swell down to the floor once you cross the bloom. Both the flood and the drain are now
   timed ramps (no hard-snap transient — that note is moot under the trigger semantics),
   so crossing the bloom swells then drains smoothly regardless of how fast you snap the
   knob. Each adjustment = edit live config + menubar restart + single-process check.
4. **Safety spot-checks at the desk:** trigger a blackout mid-sweep (masks must win);
   sweep during a drop's dark moment (F2 owns it); sweep counterclockwise (nothing);
   deselect FILTER for another CFX effect and turn the knob (nothing).

## Adversarial self-review (why this spec doesn't break the show)

Concrete failure scenario attacked: *Rekordbox updates or the CFX unit pointer goes
stale mid-mix; the CFX chain now reads garbage while the operator is mixing.* Path
walked: garbage fails `_follow_finite_f32_result` range/finite checks or the
id/unit-channel validation ⇒ `CfxDeckReading.valid=False` ⇒ dispatch stores None ⇒
anchor carries neutral ⇒ room renders exactly today's frames. Mixer authority is
untouched because CFX never enters `_tick_mixer`'s reads tuple (pinned by the Part D
isolation test + the new contract forbidden assumption). Second attack: *knob ridden
during an emergency blackout* — the dispatch gate forces inert AND the child's blackout
path never runs `_compose_frame`, so even a stale in-flight anchor cannot re-light the
room. Third attack: *frozen USB child older than this feature* — wire fields are
additive and parsed with `.get` defaults on both sides; neutral is the failure mode.
