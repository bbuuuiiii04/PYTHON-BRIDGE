---
doc_status: active-implementation-prompt
truth_level: code-grounded
last_verified_commit: 92a210e
last_verified_date: 2026-06-25
validation_scope: Codex implementation prompt for Stream Deck Phase 2 layered compositor; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no bridge restart or hardware action without operator approval
---

# Codex Task - Implement Stream Deck Phase 2 Layered Static-Look Compositor

You are implementing Phase 2 (Part F) in `/Users/bbui/rb_ss_bridge_v2`.

Do not create a branch or worktree. Work on local `main`. Do not restart the bridge, touch live
hardware, open MIDI/DMX/Enttec ports, or change local ignored configs. Implement code/tests only; live
smoke remains operator-gated.

## Read First

1. `AGENTS.md`
2. `PRIVATE_OPERATOR_PROFILE.md` if present, but do not mention private content in commits/docs.
3. `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` - Part F only.
4. Current code, re-resolving line numbers yourself:
   - `soundswitch_midi_input.py`
   - `soundswitch_laser_player.py`
   - `soundswitch_pack_loader.py`
   - `soundswitch_pack_player_config.py`
   - `state_manager.py` (`_drive_pack_output`)
   - `__main__.py` (`SoundSwitchMidiInputGroup` wiring)
   - `tools/export_soundswitch_pack.py`
   - `soundswitch_pack.py`
   - `soundswitch_pack_verifier.py`
   - tests named below

## Absolute Rules

- No Stream Deck/HID/device-specific string or code in bridge runtime `*.py`. The controller script
  under `streamdeck/` is the only Stream Deck-aware code.
- The 200 Hz push loop gains no MIDI/socket/file/subprocess I/O, no logging, no locks, and no
  snapshot-state mutation.
- `snapshot()` must be lock-free: it returns a cached immutable `MidiInputSnapshot`; worker/mutation
  paths update that snapshot under `_lock`.
- `apply_layers()` must be pure. It starts from a copy of `base`, never `[0] * 19`, and skips malformed
  layers without logging from the render path.
- Layer recency uses one process-global monotonic sequence source. Do not use per-adapter counters.
- The binding sidecar is a sibling of the pack directory, never an artifact inside the pack.
- Existing no-layer autoloop/scripted/blackout behavior must remain unchanged.

## Implement In Order

### 5A - `soundswitch_midi_input.py`: Layer model and cached snapshot

- Add frozen `LayerEntry(slot: int, kind: Literal["toggle", "press"], seq: int)`.
- Replace `MidiInputSnapshot.held_static_slot` with
  `held_layers: tuple[LayerEntry, ...]` ordered bottom-to-top.
- Add a process-global monotonic sequence helper guarded by a lock.
- Add a cached `_snapshot` field. Mutation paths refresh it under `_lock`.
- `snapshot()` must only return `_snapshot`.
- Export `LayerEntry`.

### 5B - `soundswitch_midi_input.py`: Stack lifecycle

- Replace `_held_static_slot` / `_static_held_at` with `_layers`.
- Toggle `note_on`: if that slot has an active toggle layer, remove it without reordering anything
  else; otherwise append a toggle layer with the next global seq.
- Press `note_on`: append a press layer with the next global seq.
- Press `note_off`: remove the topmost matching `(slot, "press")` layer.
- Toggle `note_off` and velocity-0 remain ignored for toggles.
- Static layers no longer auto-expire. Move blackout timeout handling out of `snapshot()` and into the
  worker tick path.
- `panic`, `stop`, `on_pack_reload`, worker death, and input-port-gone clear the whole stack.

### 5C - `soundswitch_midi_input.py`: Worker-thread port-gone clear and recover

- Add injectable port-presence checking for tests.
- Use exact string equality for the bound port name. Non-string entries count as absent.
- Never use substring `_match_port_index` for the periodic presence check.
- On first absence: clear the whole stack, mark input degraded (`worker_alive=False`,
  `error="input_port_gone"`), close the stale source, and retry opening the same exact port on the
  worker thread.
- When the exact port returns and a fresh source opens, publish a clean snapshot and accept fresh notes
  without a bridge restart.

### 5D - `soundswitch_midi_input.py`: Group merge

- `SoundSwitchMidiInputGroup.snapshot()` returns all adapter `held_layers` sorted by process-global
  `LayerEntry.seq`.
- Remove `conflicting_static_holds`.
- Preserve `blackout_held=any(...)`, `worker_alive=all(...)` with empty group healthy, and
  `mail_drop_count=sum(...)`.

### 5E - `soundswitch_laser_player.py`: Player stack API

- Replace `_active_static_slot` with `_static_layers`.
- Add `set_static_layers(layers)` storing an immutable tuple.
- `reload()` clears `_static_layers`.
- Remove or adapt `hold_static`, `release_static`, and `active_static_slot` only after updating all
  local callers/tests.

### 5F - `soundswitch_laser_player.py`: Pure compositor

- Add `apply_layers(base, layers, static_looks, blackout, emergency)`.
- Validate/copy `base`.
- For each layer bottom-to-top, find the look and apply sparse `generic_attributes`.
- Preserve `_apply_attribute`'s primary fixture-group filter.
- Explicit `0` overrides; absent channels fall through.
- Topmost layer wins channel conflicts.
- `emergency` or `blackout` returns `ZERO_FRAME`.
- Malformed/missing layers are skipped and surfaced via a non-blocking diagnostic/result signal, not a
  render-path log.
- `render()` applies layers only when base is healthy or `missing_selection`, preserving the current
  stop/stale/error gate.

### 5G - `state_manager.py`: Push-loop read and latch

- Read `s.held_layers`.
- Call `player.set_static_layers(s.held_layers if input_healthy else ())`.
- Remove `_pack_last_static_slot` or replace it with a cheap tuple change detector.
- Trip `_pack_input_degraded_latched` only on `not worker_alive` (worker death or port gone).
- Do not trip the drop-all latch on transient `error` strings or `new_drop`.
- Keep latch clear strict: only worker alive, no error, no held layers, no blackout.
- Malformed snapshots still fail closed through the existing outer exception and submit ZERO.

### 6 - `tools/export_soundswitch_pack.py`: Sibling binding sidecar

- Add a sibling path helper for `.midi_bindings.json`, matching `_sidecar_path` style.
- Add `_write_binding_sidecar(destination, decoded)` and call it after `_write_source_sidecar` in the
  canonical publish path.
- Payload rows: `{channel, note, target_kind, interaction, name}` for learned active static-look
  bindings.
- Do not include `device_name`.
- Do not edit `compile_pack_artifacts`, `soundswitch_pack.py`, the manifest, or the verifier.
- Prove no `midi_bindings.json` appears inside the pack dir and `manifest_sha256` is unchanged.

### 7 - `streamdeck/streamdeck_midi.py`: Local LED state from sidecar

- Read the sibling sidecar at startup; fallback to fixed notes 36-50 if absent.
- Key pads by `(CHANNEL, note)`.
- Toggle pads track local on/off; press pads are momentary.
- Blank LEDs on restart.
- Add a pure `led_state(sidecar, pressed_set)` seam.
- Keep `CHANNEL = 2`; never emit on MIDI channels 1-2.

## Tests And Checks

Add/update the smallest tests that prove the behavior:

- `tests/test_soundswitch_midi_input.py`: stack lifecycle, toggle remove-without-reorder,
  remove-then-repress top, press over toggle revert, global recency across two adapters, lock-free
  snapshot immutability, port-gone clear, non-string port entry, port reappear/reopen, blackout
  auto-release on worker tick.
- `tests/test_soundswitch_laser_player.py`: transparency over base, explicit 0 override, topmost wins,
  disjoint toggles compose, press-over-toggle revert, blackout/emergency wins, skip malformed layer
  without ZERO, reload clears stack, current pack static golden tests updated to the new compositor.
- `tests/test_shadow_soundswitch_pack.py`: replace `hold_static` flows with `set_static_layers`.
- `tests/test_state_manager_pack_driver.py`: `set_static_layers` receives the snapshot tuple;
  transient error string does not clear layers; `worker_alive=False` drops overlay; malformed snapshot
  still submits ZERO.
- Exporter test: sibling sidecar exists, no in-pack sidecar, verifier passes, manifest hash unchanged.
- Controller selftest covers `led_state` and channel safety.

Run:

```bash
python3 -m unittest tests.test_soundswitch_midi_input tests.test_soundswitch_laser_player tests.test_state_manager_pack_driver tests.test_shadow_soundswitch_pack tests.test_soundswitch_pack tests.test_prove_soundswitch_pack_generation
python3 streamdeck/streamdeck_midi.py --selftest
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check
```

Also run this grep and report it:

```bash
rg -n "streamdeck|Stream Deck" --glob "*.py" --glob "!streamdeck/**" --glob "!tests/**" --glob "!tools/**" --glob "!scripts/**" .
```

Expected grep result: no matches.

## Finish

Do not restart the bridge. Do not run hardware smoke. Report changed files, tests/checks, current
`HEAD`, and a plain-language operator summary:

- what the bridge should do differently live after a future approved restart
- what should remain unchanged
- how to recognize healthy behavior in `/tmp/bridge.log` and pack status
- what was software-verified
- what remains hardware-unvalidated
- exact approval gates before restart, controller smoke, Enttec/DMX, or fixture checks
