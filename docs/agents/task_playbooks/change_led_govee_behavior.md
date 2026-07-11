---
doc_status: current
truth_level: code-verified
last_verified_commit: 96923d3
last_verified_date: 2026-07-08
validation_scope: software-only
---

# Task: LED/Govee behavior changes

Use when:
- The requested work is specifically about LED/Govee behavior changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/led_govee.md`
4. `docs/agents/change_contracts.md`

Do not read first:
- archive docs
- old prompts
- old plans
- unrelated subsystem cards

Allowed changes:
- The narrow files required by the task.
- Docs/status/test inventory files required by the change contract.

Forbidden changes:
- unrelated runtime behavior
- local ignored configs or backups
- support/validation claims without evidence
- test modifications just to hide failures

Implementation notes:
- Inspect `led_*`, `govee_*`, `beat_sync_engine.py`, `led_dispatch_policy.py`, and StateManager dispatch call sites.
- LED color-engine live controls are operator-reserved future pad/deck surfaces; if they become live
  from outside `StateManager`, route through `BridgeEvent`s or runtime commands.
- Committed drop-look selection must thread the same `diy_eligible` predicate used by normal
  `LEDLookDirector.tick()` automation.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For scripted-track LED automation, preserve the split between `safety.scripted_mode_automation` as the master switch (the shipped example config enables it; the `LEDSafety` dataclass default stays `false`) and the top-level `scripted_mode` role-remap policy. `utility` is a blackout destination only; verify active and off role transitions separately.
- When a blackout can be produced by several upstream causes (blank role, scripted mapping, an
  upstream reject) and only some of those causes should actually darken the room, intercept at the
  DISPATCH layer where every path converges — do not chase and patch each origin path separately
  (AWR-157's `blank_role_hold` guard: one check in `_dispatch_led_automation` right before
  `_led_send_decision`, gated on `decision.look == blackout_look`, catches every upstream cause at
  once). Keep the source check load-bearing and test-pinned: the guard must live somewhere
  emergency/manual/tactical-blackout code paths structurally cannot reach, not behind a runtime
  `source ==` string check that could silently drift.
- For StateManager LED automation timing changes, keep the push-loop path pure/non-blocking, keep source arming at the content-change event, and prove arm/release/cleanup in `tests/test_led_state_manager.py`.
- For realtime-to-cloud handoff changes, `force_deactivate()` must not perform transport socket
  calls on the caller/push-loop thread; prove teardown on the runner thread in
  `tests/test_govee_realtime_runner.py`.
- The realtime frame trio runs in a bridge-owned child process (AWR-146): `govee_frame_engine.py`
  (`FrameEngineHost` + JSON-lines protocol + `main()`) and `govee_frame_engine_client.py`
  (`GoveeFrameEngineClient`, the in-bridge supervisor and drop-in for `GoveeRealtimeRunner`). Keep
  every client method the coordinator calls lock-and-flag (zero I/O on the caller thread); all IPC,
  spawning, respawn/replay, and IP re-resolution stay on the client thread. Fail-dark on EOF is
  `runner.stop()` (blackout + deactivate, never brightness-0 so cloud looks survive a restart); a
  pure-emergency respawn replays `emergency_stop` + an unconditional brightness-0. The runner change
  is only the additive `on_thread_start` hook. Prove host/client behavior in
  `tests/test_govee_frame_engine.py` and the real-subprocess fps/orphan proof in
  `tests/test_govee_frame_engine_integration.py`.
- For Govee cloud health-reporting changes, keep fixes reporting-only: log
  mirror send failure/recovery on state changes only, do not alter send order or
  queue/rate-limit behavior, and prove status healing in the sender/adapter
  tests.
- For color-engine slot behavior, verify `resolve_slot_colors()` invariants and slot strategy config validation before updating setup/status docs.
- (AWR-173) CFX filter-sweep overlay: the per-tick math is the pure module function
  `cfx_sweep_envelope(knob, prev_mix, dt_s, cfg)` in `led_dispatch_policy.py` — keep it a pure seam
  (no I/O, no time reads; caller passes `dt_s`) and test it directly. `StateManager._compute_led_cfx_sweep`
  stores an atomic `(mix, dim, rgb, captured_monotonic)` tuple; `get_active_beat_anchor` attaches it to
  the real-playback anchor (idle freewheel stays neutral) and neutralizes a tuple older than
  `CFX_ANCHOR_DEAD_S`. The overlay MUST stay inert whenever any darkness owner holds
  (`_led_blackout_active()` or `_os.breakdown_active`), when v2 identity is off, or when the active-deck
  CFX reading is stale/invalid — fail closed toward today. The frame-engine child applies it as
  `scale(lerp(px, cfx_rgb, cfx_mix), cfx_dim)` on the composed-playback frame ONLY; the blank/idle/
  emergency paths must never run it. Wire fields are `.get`-defaulted on BOTH sides (`_anchor_to_wire`,
  the child anchor parse) so a frozen/version-skewed frame-engine child stays neutral — never make a cfx
  wire field required. `CfxSweepConfig` ships `enabled: false`; the bloom threshold + ramps stay
  `pending desk calibration`. Prove the envelope, gating, anchor, child overlay, and config loader in
  `tests/test_led_cfx_sweep.py`.
- For M2.5 slotized cues, keep `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED` language until operator hardware visual sign-off covers sparkle hue stability, center-burst band split, strobe gating, drop snap behavior, Patch E visual balance, Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation.
- `drop_lifecycle.py` is a pure flat-window parity seam used by laser policy. The live LED resolver remains in `StateManager`; do not redirect LED runtime through the shared resolver without a separate approved change.
- For LIGHTING ENGINE v2 identity work, preserve the v1-off compatibility gate, keep identity-store
  disk writes on writer/helper threads (never the 200 Hz push loop), route Stream Deck/runtime
  mutations through `BridgeEvent`s, and update the palette authority/design docs plus AWR-128.
- When registering a new realtime effect (`_EFFECTS` or `SLOT_EFFECTS` in `govee_frame_renderer.py`),
  `led_pad_controls.py` has a MODULE-LEVEL completeness assertion (`RENDER_GROUPS` must union to
  exactly `REALTIME_EFFECT_NAMES`) that raises on import if a new name isn't slotted into a
  `RENDER_GROUPS` tuple — this breaks `tests/test_led_pad_controls.py`/`tests/test_led_pad_lab.py`/
  `tests/test_led_pad_service.py` at collection time, not just at a normal assertion failure. Every new
  static param key also needs a `CONTROL_META` entry (`test_every_allowlisted_key_has_metadata`
  requires `set(CONTROL_META) == union(REALTIME_EFFECT_PARAM_KEYS.values())`), and if its renderer
  fallback differs by scene_ref, a `PARAM_DEFAULT_OVERRIDES` entry (both audited against exact
  `params.get("key", literal)` source strings in `tests/test_led_pad_controls.py` — see AWR-156).
  Also check the older `tests/test_led_color_engine_m2_patch_*.py`/`phase*.py` regression-lock files
  for frozen `SLOT_EFFECTS`-set/bank-membership/`drop_pairs`/look-params assertions that a bank
  recast, rename, or new registration can break — they are not named in this playbook's required
  test list but do need updating in the same change (AWR-156 touched all of them).
- When rebuilding an existing effect and retiring its knobs, remove those params from the tracked
  example and its renderer-default tests. If the ignored live config still carries them, keeping
  them allowlisted as documented no-op compatibility input is permitted until an operator-approved
  live mirror; do not edit the live config to make tests pass (AWR-215).

Required tests:
- Run the targeted tests listed in the subsystem card.
- For active-content LED hold or role-gate changes in `StateManager`, run `python3 -m unittest tests.test_led_state_manager`.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.
- For Govee cloud health-reporting changes, run `python3 -m unittest tests.test_govee_runtime_sender tests.test_govee_scene_adapter`.
- For frame-engine child-process changes (AWR-146), run `python3 -m unittest tests.test_govee_frame_engine tests.test_govee_frame_engine_integration` (the integration suite is timing-sensitive and skips under `CI=true`).
- For M2.5 slot-cue work, include every existing `tests/test_led_color_engine_m2_patch_*.py` file, including the newest Patch F file when present.
- For LIGHTING ENGINE v2 identity work, include `tests/test_led_identity_v2.py`,
  `tests/test_led_color_engine.py`, `tests/test_color_engine_config.py`,
  `tests/test_led_palette_control.py`, `tests/test_soundswitch_midi_input.py`,
  `tests/test_streamdeck_midi.py`, `tests/test_runtime_status.py`, and the relevant
  StateManager LED tests.
- When changing the shared drop resolver, run `tests.test_drop_lifecycle` and the existing LED state-manager tests; pure parity does not prove live per-look-duration or offset parity.

Required docs updates:
- `docs/subsystems/led_govee.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/validation/hardware_validation_log.md`
- `docs/status/active_work_registry.md`
- `docs/agents/task_playbooks/change_led_govee_behavior.md` if workflow guidance changes

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
