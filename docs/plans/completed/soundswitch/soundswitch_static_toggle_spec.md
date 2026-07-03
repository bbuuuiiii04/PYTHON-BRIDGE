---
doc_status: completed-spec
truth_level: code-verified-requires-research
last_verified_commit: b53b0ce
last_verified_date: 2026-06-25
validation_scope: Revised Codex spec for SoundSwitch Static Override Press/Toggle mode parity; spec only, no implementation; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec - SoundSwitch Static Override Press/Toggle Mode Parity

## Verdict

**NOT READY FOR BRIDGE IMPLEMENTATION.**

The required live behavior is clear: the bridge must honor the MIDI interaction mode saved in SoundSwitch.

- If a SoundSwitch Static Override control is saved as **Press Mode**, the bridge-exported pack must behave as press/momentary.
- If a SoundSwitch Static Override control is saved as **Toggle Mode**, the bridge-exported pack must behave as toggle/latch.
- Operator-declared config must not be the source of truth for Press/Toggle mode. It may be useful later as an explicit debug override, but it is not acceptable for this product requirement.

Current repo code does not yet expose a verified saved-project Press/Toggle field. Therefore the next implementation must start with a narrow SoundSwitch RE/exporter proof step, not with bridge config.

## Part A - Context & Root Cause (verified; read, do not implement)

- [confirmed] This spec was re-reviewed against current `main` at `b53b0ce`. During authoring, an unrelated local modification exists in `docs/architecture/doc_index.md`; do not touch that file while implementing this spec.
- [confirmed] The current bridge-native Static Override input model is momentary. `SoundSwitchMidiInputAdapter._process_note_on()` selects a `static_look` slot and treats repeated note-on for the same slot as idempotent, while `_process_note_off()` releases the current matching slot only. See `soundswitch_midi_input.py:214-256`.
- [confirmed] Velocity-zero note-on is normalized to note-off before dispatch. See `soundswitch_midi_input.py:267-300`; current tests cover this in `tests/test_soundswitch_midi_input.py:144-155`.
- [confirmed] Current stale-hold behavior is incompatible with a one-shot toggle-on. `snapshot()` clears `_held_static_slot` when `_static_held_at` ages past `stale_timeout_ms`, defaulting to 2000 ms from adapter construction. See `soundswitch_midi_input.py:68-80` and `soundswitch_midi_input.py:100-122`.
- [confirmed] Existing emergency/cleanup paths already clear held static state and must continue to clear toggles. `panic()` and `on_pack_reload()` route to `_clear_held()` (`soundswitch_midi_input.py:189-195`), `_clear_held()` clears `_held_static_slot`, `_static_held_at`, blackout, worker state, and error (`soundswitch_midi_input.py:201-212`), `stop()` calls `_clear_held("stop")` (`soundswitch_midi_input.py:174-187`), and worker death calls `_clear_held("worker_death", ...)` (`soundswitch_midi_input.py:354-362`).
- [confirmed] The runtime binding has no interaction mode today. `PackMidiBinding` stores device, MIDI message identity, target kind, target slot, and target identity only. See `soundswitch_pack_loader.py:39-52`.
- [confirmed] The pack loader builds active static bindings from `selection_map.json` rows and does not currently stamp any momentary/toggle mode. See `soundswitch_pack_loader.py:245-299`. It also fail-closes if a static binding references a missing Static Look slot. See `soundswitch_pack_loader.py:647-663`.
- [confirmed] The current SoundSwitch learned-map decoder reads `message_type`, `data_byte`, `zero_based_channel`, `control_path`, and `enabled` for each binding. See `soundswitch_project_decoder.py:811-848`. The standalone RE inventory parser reads the same exposed fields. See `tools/ssfmt/re/inventory_project_artifacts.py:100-146`.
- [confirmed] Current RE authority resolves four DDJ-800 Static Override mappings to zero-based slots 8, 16, 17, and 24. The closure report gives the exact notes and slots at `docs/research/soundswitch/soundswitch_re_closure_report.md:108-125`.
- [confirmed] SoundSwitch binary/static-analysis evidence says `StaticOverrideN` selects zero-based slot `N`, note-on holds, matching note-off clears, and release rerenders current base rather than restoring a prior frame. See `docs/research/soundswitch/soundswitch_ghidra_addendum.md:83-92` and `docs/research/soundswitch/soundswitch_ssfile_format.md:274-283`.
- [confirmed] A previous read-only string scan of the installed SoundSwitch binary found UI strings `Toggle Mode` and `Press Mode` near `SoundSwitch.Controls.StaticOverride`, but current repo decoders and docs do not yet identify a durable saved-project field that records that choice.
- [confirmed] StateManager already consumes static input as a transition, not as a per-mode algorithm. `_drive_pack_output()` reads `snapshot().held_static_slot`; when the slot differs from `_pack_last_static_slot`, it calls `player.hold_static()` for a slot or `player.release_static()` for `None`. See `state_manager.py:3405-3435`. A correct interaction mode implementation should still avoid a StateManager algorithm rewrite unless tests prove an integration gap.
- [confirmed] Input degradation already forces manual overlays released in output. Worker death, any error, or a new mailbox drop latches distrust; while latched, `slot = None` and `blackout = False`. The latch clears only on a healthy, error-free, no-held-static/no-blackout tick. See `state_manager.py:3418-3428`. Existing tests cover worker loss, mailbox drop, recovery after clean release, conflict, and runtime swap behavior in `tests/test_state_manager_pack_driver.py:587-773`.
- [confirmed] Runtime swap already resets `_pack_last_static_slot` while preserving the degradation latch, so a fresh player cannot skip a needed `hold_static()` call. See `state_manager.py:3284-3312`. Existing H11 coverage is `tests/test_state_manager_pack_driver.py:753-773`.
- [confirmed] Multi-device input grouping returns `held_static_slot=None` and `error="conflicting_static_holds"` when more than one distinct slot is held across adapters. See `soundswitch_midi_input.py:443-460`.
- [confirmed] Current SoundSwitch project status remains default-off and hardware-unvalidated. The active roadmap forbids implicit restart, config toggle, runtime command, MIDI/serial/Enttec/DMX open, fixture connection, or hardware action. See `docs/plans/active/soundswitch_exporter_remaining_work.md:16-28`.
- [unknown] The saved-project byte(s) or object field(s) that distinguish Press Mode from Toggle Mode for Static Overrides have not been identified in current repo docs/code. This is now a hard blocker, not a reason to replace SoundSwitch authority with bridge config.

Root cause: the bridge imported SoundSwitch's Static Override target identity but not SoundSwitch's saved controller interaction policy. The bridge currently treats every Static Override binding as momentary, so Toggle Mode controls saved in SoundSwitch would be exported incorrectly unless the exporter captures and preserves that mode.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- Do not open MIDI, serial, Enttec, DMX, SoundSwitch, Rekordbox, or fixture connections during automated implementation or tests.
- Do not start, stop, count, restart, or runtime-toggle the bridge as part of implementation or tests.
- Do not read or edit ignored live config.
- Do not use operator config as the authority for Press/Toggle mode.
- Do not implement bridge-native toggle behavior until Task 1 proves where the SoundSwitch-saved Press/Toggle mode lives and how the exporter can carry it.
- Preserve default behavior for any binding whose saved mode is unknown: fail closed to momentary and report the unknown as an implementation blocker, not as a successful export.
- Preserve all non-SoundSwitch behavior: OS2L, lasers, LEDs/Govee, Rekordbox readers, runtime commands outside `set_soundswitch_pack`, and existing direct-DMX default-off behavior.
- Preserve the one-active-static-slot model. No stack, no multi-static blend, no background reassert loop.
- Keep the 200 Hz path free of filesystem, subprocess, socket, MIDI, serial, sleep, retry, parsing, config load, or blocking work.
- Keep status/log/docs sanitized: no local paths, ports, aliases, device IDs, raw frames, raw project UUIDs, ignored config contents, or private setup details.

### Task 1 - SoundSwitch RE/exporter proof: locate and preserve Press/Toggle mode

Find the saved SoundSwitch field or byte pattern that records Static Override Press Mode versus Toggle Mode.

Implementation guidance:

- Start from `docs/research/soundswitch/README.md`, `docs/research/soundswitch/soundswitch_re_closure_report.md`, `docs/research/soundswitch/soundswitch_ssfile_format.md`, `docs/research/soundswitch/soundswitch_ghidra_addendum.md`, `soundswitch_project_decoder.py`, and `tools/ssfmt/re/inventory_project_artifacts.py`.
- Use only checked-in captures, checked-in project bytes, and read-only tooling unless the operator explicitly approves a new capture step.
- Produce a before/after proof that changes only Press/Toggle mode for a Static Override while holding target slot, note, channel, device, and enabled state constant.
- Update the decoder/inventory/exporter model to expose `interaction_mode` for Static Override bindings with exactly `"press"` or `"toggle"`.
- If the field cannot be proven from existing evidence, stop and report **NOT READY: saved Press/Toggle mode field still unknown**. Do not continue to bridge implementation.

Required proof:

- At least one Press Mode Static Override and one Toggle Mode Static Override decoded from saved project bytes.
- A tool/test fixture that fails if the Press/Toggle field is absent, misread, or confused with target slot/note/channel/enabled.
- Documentation update in the SoundSwitch RE docs explaining the byte/object location, allowed values, and confidence level.

### Task 2 - Pack artifacts: carry SoundSwitch interaction mode as verified source truth

After Task 1 proves the saved mode, extend pack generation and loading so the mode is part of the verified pack artifact path.

Implementation guidance:

- Add an interaction field to the generated learned-control rows for Static Override bindings only, using the SoundSwitch-authored values `"press"` or `"toggle"`.
- Do not infer mode from slot number, button label, device name, or local bridge config.
- Do not write mode for blackout, pack-selection, bridge-owned safety, no-target, or inactive bindings unless a future proven SoundSwitch source field requires it.
- Update pack verification so malformed, missing, or unknown Static Override interaction mode fails export/load rather than silently guessing.
- Keep pack artifact schema migration explicit and tested.

Tests:

- Export/generation test proves Press Mode and Toggle Mode rows are serialized distinctly from source project bytes.
- Loader/verifier test proves missing or invalid interaction mode on active Static Override rows fails closed.
- Tests must use a non-skipped unit seam. Do not put this coverage only inside a class gated on `~/Music/SoundSwitch/default.ssproj`.

### Task 3 - `soundswitch_pack_loader.py`: stamp runtime binding interaction from pack artifacts

Extend the immutable runtime binding model from verified pack data.

Implementation guidance:

- Add `interaction: Literal["press", "toggle"] = "press"` to `PackMidiBinding` after the existing optional target fields, so existing positional callers keep working.
- When `_runtime_metadata()` appends a `static_look` binding, set `interaction` from the verified pack row.
- Leave non-static bindings at `"press"` unless they later gain a proven SoundSwitch interaction mode.
- Keep the existing fail-closed check that a static binding's slot exists in `looks` (`soundswitch_pack_loader.py:658-660`).
- Add validation that active Static Override runtime bindings do not create ambiguous same-slot ownership for toggle semantics. Either fail load on duplicate active `(device, slot)` / same-slot toggle ownership, or document and test the narrower allowed shape. Do not leave cross-toggle behavior implicit.

Tests:

- Default/legacy test fixtures without explicit mode must either migrate intentionally or fail with a clear schema error; do not silently treat current packs as correct if the new schema requires mode.
- Press rows produce `interaction="press"`.
- Toggle rows produce `interaction="toggle"`.
- Duplicate/ambiguous toggle ownership is rejected or explicitly covered by tests.

### Task 4 - `soundswitch_midi_input.py`: add Press/Toggle state machine

Implement runtime behavior from `PackMidiBinding.interaction`, reusing the existing snapshot contract.

Press behavior must match current momentary behavior:

- nonzero note-on selects/replaces `held_static_slot`;
- repeated same-slot nonzero note-on remains idempotent and may refresh the stale timer;
- matching note-off releases;
- non-current note-off is ignored;
- stale timeout can auto-release press static and blackout holds.

Toggle behavior:

- For a `static_look` binding with `interaction == "toggle"`, nonzero note-on flips:
  - if the current held slot is the same slot, clear `_held_static_slot` and `_static_held_at`;
  - otherwise set `_held_static_slot` to that slot and set `_static_held_at = None`.
- For toggle bindings, note-off is ignored.
- Velocity-zero note-on is already normalized to note-off in `_feed_raw_message()`; because toggle note-off is ignored, velocity zero must not flip the latch.
- A toggle-on slot is exempt from `snapshot()` stale-hold auto-release because `_static_held_at` remains `None`.
- `_clear_held()` must clear a toggle exactly as it clears press/momentary state today.
- One active static slot remains authoritative. A toggle note-on for a different slot replaces the current static slot. A press note-on can also replace a toggled slot; releasing that press slot clears the override rather than restoring the prior toggle. This matches the one-index SoundSwitch override model in `docs/research/soundswitch/soundswitch_ssfile_format.md:274-283`.
- Preserve device filtering by `_connected_device` and event key matching in `_feed_raw_message()` (`soundswitch_midi_input.py:285-300`).

Tests:

- Press-mode bindings pass the existing idempotent/release/stale tests unchanged.
- Toggle first note-on latches a slot.
- Toggle second same-slot note-on unlatches it.
- Toggle note-off does not unlatch it.
- Toggle velocity-zero note-on does not unlatch it.
- Toggle stale timeout does not clear a toggled-on static.
- Panic, pack reload, stop, and worker death clear a toggled-on static.
- A different toggle slot replaces the current toggled slot deterministically.
- Missed toggle-off risk is documented in test comments or covered by a deliberate mailbox/drop detection change. Do not pretend current `_mail_drop_count` protects this path; it is currently inert in `soundswitch_midi_input.py`.

### Task 5 - StateManager: no algorithm change unless tests prove a gap

Do not rewrite `_drive_pack_output()` unless tests prove an actual integration gap.

Expected behavior from existing code:

- Healthy snapshot `held_static_slot=None -> slot` causes `hold_static(slot)`.
- Healthy snapshot `slot -> None` causes `release_static(last_slot)`.
- Degraded input forces `slot=None`, releasing a toggled static in output.
- If the adapter still reports a latched toggle during recovery after degradation, the StateManager latch remains set until a clean no-held-static/no-blackout tick. This is acceptable fail-closed behavior.

Tests:

- Keep the existing PackDriverInputHealthTests green (`tests/test_state_manager_pack_driver.py:587-773`).
- Add a small explicit regression only if needed: simulated healthy toggle `None -> 8 -> None` drives static then release through the existing transition consumer. Do not create a new fake mode if the existing `_FakeInput(held_static_slot=...)` covers the behavior.

### Task 6 - Docs required by the change contract

After implementation, inspect and update every doc named by the `soundswitch_pack_player` contract, or explicitly report no-drift for each one.

Contract docs to inspect:

- `docs/plans/active/soundswitch_exporter_remaining_work.md`
- `docs/plans/active/soundswitch_README.md`
- `docs/subsystems/soundswitch_output.md`
- `docs/subsystems/core_bridge.md`
- `docs/subsystems/runtime_commands.md`
- `docs/subsystems/laser.md`
- `docs/subsystems/config.md`
- `docs/subsystems/tests.md`
- `docs/architecture/current_architecture.md`
- `docs/architecture/runtime_invariants.md`
- `docs/architecture/laser_director_design.md`
- `docs/setup/configuration.md`
- `docs/setup/runtime_commands.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/status/known_limitations.md`
- `docs/validation/software_test_inventory.md`
- `docs/validation/hardware_validation_log.md`

Keep claims bounded to software validation. Do not claim hardware validation.

## Part C - Invariants That MUST Still Hold (live safety)

- [confirmed] `StateManager` remains the central runtime owner and the only writer of `DeckState`; the pack driver reads state and submits once per tick. See `AGENTS.md` invariants and `state_manager.py:3263-3282`.
- [confirmed] The 200 Hz push loop gains no blocking work. All new decoding, config, pack verification, and pack loading work must happen outside `_drive_pack_output()`.
- [confirmed] Pack runtime publication remains a single immutable bundle assignment in `set_pack_runtime()`; the implementation must not split player/input/backend updates across multiple tick-visible writes. See `state_manager.py:3284-3312` and `soundswitch_pack_runtime.py:19-44`.
- [confirmed] Runtime pack reload remains validate-first and no-implicit-enable. `SoundSwitchPackController._reload()` validates while disabled and swaps only when already enabled. See `soundswitch_pack_controller.py:139-147`.
- [confirmed] Graceful disable/swap still attempts physical zero before stopping old sender/input through `_safe_zero_and_stop()`. See `soundswitch_pack_controller.py:34-50` and `soundswitch_pack_controller.py:98-120`.
- [confirmed] Input degradation releases manual overlays while preserving the automatic scripted base truth. See `state_manager.py:3383-3428` and tests at `tests/test_state_manager_pack_driver.py:587-773`.
- [confirmed] `SoundSwitchMidiInputGroup.snapshot()` conflict semantics for distinct held slots remain fail-closed: different held static slots across devices become no held slot plus `conflicting_static_holds`. See `soundswitch_midi_input.py:443-460`.
- [confirmed] Direct DMX and physical MIDI-laser output remain mutually exclusive; do not add a fallback path from pack failure to MIDI.
- [confirmed] No status/log/doc surface exposes local paths, ports, aliases, device names, fixture serials, raw frames, raw project UUIDs, raw errors, ignored config contents, or raw status files. See roadmap invariant 11 at `docs/plans/active/soundswitch_exporter_remaining_work.md:176-178`.

## Part D - Tests

Run focused tests after implementation:

```bash
python3 -m unittest tests.test_soundswitch_pack_startup tests.test_soundswitch_pack tests.test_soundswitch_midi_input tests.test_static_looks tests.test_state_manager_pack_driver
```

Run the full contract gate before calling the change complete:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Use existing injected-message seams in `tests/test_soundswitch_midi_input.py`; do not open real MIDI. Use decoder/exporter/loader unit seams; do not read ignored live config.

## Part E - Acceptance

- [ ] Saved SoundSwitch Press/Toggle mode has a byte/object-level proof in checked-in evidence or an operator-approved capture.
- [ ] Exported pack artifacts preserve Static Override interaction mode from SoundSwitch, not from operator bridge config.
- [ ] Active Static Override rows without a verified interaction mode fail closed instead of guessing.
- [ ] `PackMidiBinding.interaction` defaults compatibly but is sourced from verified pack artifacts for active Static Override rows.
- [ ] Press Mode bindings preserve current momentary behavior.
- [ ] Toggle Mode bindings note-on flip on/off; note-off and velocity-zero note-on do not flip.
- [ ] Toggle stale-timeout exemption works, while press stale-timeout behavior still works.
- [ ] Panic, stop, pack reload, worker death, disabled runtime, and degraded input release a toggled-on static in output.
- [ ] Runtime swap does not carry a toggled static into a fresh pack/player unless a fresh healthy input snapshot asserts it.
- [ ] Multi-device conflicting static holds still fail closed to no held static plus an error; duplicate same-slot toggle ownership is either rejected or explicitly tested.
- [ ] No StateManager blocking work, new runtime command, status field, menubar control, background reassertion loop, or hardware interaction is added.
- [ ] Required focused tests, full unittest discovery, and docs checks pass, or any failure is reported with exact command output and cause.

## Adversarial Self-Review

- Attack: implementation uses local config to mark slots 8/16/17/24 as toggles. Prevention: the spec forbids config authority; SoundSwitch saved Press/Toggle mode must be decoded and exported.
- Attack: the RE proof confuses Press/Toggle with target slot, note, channel, or enabled flag. Prevention: Task 1 requires a before/after proof where only Press/Toggle changes while target identity stays constant.
- Attack: toggle slot latches on, then the controller misses the second note-on/toggle-off. Because stale timeout no longer clears toggles, the static could remain on. Prevention: implementation must either document this as a residual operator risk or add a deliberate detection/release policy; current `_mail_drop_count` does not solve it.
- Attack: two controls/devices map to the same Static Override slot and cross-toggle each other. Prevention: loader/runtime validation must reject or explicitly test the allowed duplicate same-slot shape.
- Attack: velocity-zero note-on arrives from a toggle pad and silently flips the latch. Prevention: `_feed_raw_message()` normalizes velocity zero to note-off (`soundswitch_midi_input.py:267-300`), and toggle note-off is ignored.
- Attack: a pack reload or runtime swap leaves `_pack_last_static_slot` equal to the new snapshot slot, suppressing `hold_static()` on the fresh player. Prevention: `set_pack_runtime()` resets `_pack_last_static_slot=None` (`state_manager.py:3301-3303`); keep H11 green.

## When You Finish

Report back:

- changed files, grouped by RE/decoder/exporter/pack/model/input/tests/docs;
- exact tests and docs checks run;
- whether full `python3 -m unittest discover tests` was run or intentionally skipped;
- whether any docs staleness advisory remains;
- whether any behavior was hardware-validated (expected answer: no, unless the operator separately ran the hardware procedure).

Plain-language operator summary to include:

- Live difference: Static Override controls saved in SoundSwitch as Press Mode act momentary; controls saved as Toggle Mode tap on and stay on until tapped again.
- Unchanged: no output enables itself; no bridge restart happens; Autoloop native DMX remains software-zero; OS2L, lasers, LEDs/Govee, Rekordbox reader state, and existing pack default-off behavior stay unchanged unless pack mode is explicitly enabled.
- Healthy behavior: pressing a Press Mode static shows only while held; tapping a Toggle Mode static shows that static; tapping it again returns to the scripted/base or zero state; panic, reload, stop, controller failure, pack disable, or shutdown-style disable releases it.
- Watchpoints: if SoundSwitch/DMX shows a static staying on after controller loss, reload, panic, or disable, treat that as a blocker; if a missed toggle-off leaves a static on, that is either the documented residual risk or evidence the chosen mitigation failed.
- Verification boundary: software tests only; no fixture, Enttec, MIDI controller, SoundSwitch UI, or real hardware validation unless separately approved and logged.
- Live commands/approval gates: implementation and tests require no live commands. Any restart, config toggle, backend enable, `set_soundswitch_pack`, MIDI/serial/Enttec/DMX open, SoundSwitch UI capture, or hardware-adjacent check needs explicit operator approval in that future session.
