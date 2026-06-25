---
doc_status: active-plan
truth_level: code-verified-requires-adversarial-review
last_verified_commit: 199af0d (+ uncommitted rtmidi MidiIn fix in working tree)
last_verified_date: 2026-06-25
validation_scope: Adversarial review-and-fix handoff for the SoundSwitch-RE-derived Static Looks feature, emphasizing the bridge MIDI reader. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Adversarial Review + Fix — SoundSwitch Static Looks (RE → bridge MIDI reader → DMX)

## 0. Your job (read first)

Perform an **extensive, strict, adversarial review** of the entire Static Looks feature that was
reverse-engineered from SoundSwitch and wired into the bridge. **Emphasize the bridge's MIDI
reader (`soundswitch_midi_input.py`), but do not limit yourself to it** — the RE decoder, exporter,
verifier, loader, StateManager integration, startup wiring, and live config are all in scope.

You are **authorized to implement fixes** for any real defect you find. For each fix:
1. State the finding first with **file:line evidence** and why it matters live.
2. Implement the **minimal** correct fix (root cause, not symptom — fix the shared function, not
   one caller).
3. Add or extend the **smallest test that fails without the fix** (pure-function or injected seam;
   never open real MIDI/serial/DMX).
4. Re-run the focused tests plus any broader suite the change touches.
5. Commit after each logically separate fix with a clear message.

**Do not trust prior claims.** Do not assume correctness from this document, commit messages, the
existing spec (`docs/plans/active/soundswitch_static_toggle_spec.md`), docs, or existing tests.
Re-verify everything against current code and local primary evidence. If a claim here is wrong,
say so with evidence — finding errors in this prompt is part of the job.

Label every claim you make: **[confirmed]** (you read it in current code / ran it),
**[assumed]**, or **[unknown]**.

## 1. Hard constraints (live-safety; non-negotiable)

- **Do NOT start, stop, restart, or runtime-toggle the live bridge.** Do not run the menubar
  launcher or `ss_bridge_watcher.sh`.
- **Do NOT open real MIDI, serial, Enttec, DMX, or SoundSwitch connections** in code or tests. Use
  the existing injected seams (`_message_source=` on the adapter; fake `rtmidi` module via
  `sys.modules` patch as in `tests/test_soundswitch_midi_input.py::TestRealMidiSource`).
- **Do NOT touch** Rekordbox readers, lasers, LEDs/Govee, OS2L (`os2l_*`, `sound_switch_engine.py`),
  or any runtime command other than the SoundSwitch pack path, unless a real correctness bug in
  THIS feature forces it (then justify it).
- **Do NOT read or commit ignored live config contents.** `config/soundswitch_pack_player.json`
  and `local/soundswitch/rbss_canonical_pack/` are gitignored; you may reason about their shape but
  never commit them or print secrets/device paths/ports/UUIDs.
- **Keep the 200 Hz push loop non-blocking.** No filesystem/socket/MIDI/serial/sleep/subprocess in
  `StateManager._drive_pack_output()` or anything it calls per tick. MIDI I/O lives only in the
  input worker thread.
- **Keep status/logs/docs sanitized:** no local paths, ports, aliases, device serials, raw frames,
  raw project UUIDs, or ignored-config contents.
- **Do not push.** Commit locally only. Work directly on `main` (no new branches).
- Run the repo doc-contract checks if you change code that has a change contract
  (`tools/check_docs_metadata.py`, `tools/check_agent_contracts.py`, `tools/check_docs_drift.py`,
  `tools/check_docs_staleness.py --report`).

## 2. What the feature does (context — verify, do not trust)

SoundSwitch Static Override buttons can be saved as **Press Mode** (momentary) or **Toggle Mode**
(latch). The bridge, in pack mode, **replaces SoundSwitch as the light-output engine** and renders
DMX directly via Enttec. To do that faithfully it must (a) decode the saved Press/Toggle mode from
the SoundSwitch project, (b) carry it through the exported pack, and (c) read the physical DDJ-800
controller itself at runtime and apply press/toggle semantics.

Pipeline and key files (all paths relative to repo root):

- **RE decode:** `soundswitch_project_decoder.py`
  - `decode_control_label_states()` (~L852–893): parses a `recordable/*.dat` "control label colour"
    map; per control: typed string `control_path`, `u32 label_rgba`, `u8 interaction_flag`
    (`0`=press, `1`=toggle).
  - `_resolve_controls()` (~L956–1025): joins the flag onto Static Override learned-MIDI bindings by
    `control_path`; fails closed if a static binding has no saved mode.
  - `decode_project()` (~L1109–1140): selects the control-label file, builds `control_states_by_path`,
    conflict-checks duplicates.
  - Header disambiguation at ~L862–866 (note the `data[7:11]` guard — assess whether it is dead).
- **Models:** `soundswitch_pack_models.py` — `ControlLabelState` (~L243), `ResolvedControlBinding.interaction_mode` (~L260).
- **Export:** `soundswitch_pack.py` `_selection_map()` (~L215–220) — writes `interaction_mode` for
  `static_look` rows only.
- **Verify:** `soundswitch_pack_verifier.py` (~L608–612) — rejects missing/invalid mode on static,
  rejects mode on non-static.
- **Load:** `soundswitch_pack_loader.py` — `PackMidiBinding.interaction` (~L50–53), `_runtime_metadata()`
  (~L248–297): validates mode, dedups `(device, slot)` ownership, stamps `interaction`.
- **MIDI reader (PRIMARY FOCUS):** `soundswitch_midi_input.py`
  - `_make_real_source()` (~L320–351): **just changed** to python-rtmidi `MidiIn` (see §3).
  - `_process_note_on/off()` (~L217–256): press vs toggle latch.
  - `snapshot()` (~L100–122): stale-hold auto-release; toggle exemption.
  - `start()/_worker()` (~L128–172, ~L347–383): worker lifecycle, readiness, stop.
  - `_clear_held()` (~L201–212); `SoundSwitchMidiInputGroup` (~L385–470): per-device adapters,
    conflict semantics, empty-aliases behavior.
- **RE tool mirror:** `tools/ssfmt/re/inventory_project_artifacts.py` — `_decode_recordable_control_label_state()` (~L201).
- **Startup wiring:** `__main__.py` `_build_soundswitch_pack_startup()` (~L438–530) and
  `_start_soundswitch_pack_workers()` (~L532–560).
- **Runtime driver:** `state_manager.py` `_drive_pack_output()` (~L3405–3435), `set_pack_runtime()` (~L3284–3312).
- **Config:** `soundswitch_pack_player_config.py`; live (gitignored) `config/soundswitch_pack_player.json`.
- **Tests:** `tests/test_soundswitch_midi_input.py`, `tests/test_soundswitch_project_decoder.py`,
  `tests/test_soundswitch_pack.py`, `tests/test_soundswitch_laser_player.py`,
  `tests/test_inventory_project_artifacts.py`, `tests/test_state_manager_pack_driver.py`.

## 3. State of the working tree you are reviewing

[confirmed] Feature commit `3b53ab2` ("Implement SoundSwitch static interaction modes") is an
ancestor of `HEAD` (`199af0d`).

[confirmed] An **uncommitted change is in the working tree** (apply your review to it; commit it if
you agree it is correct, or revise it): `soundswitch_midi_input.py::_make_real_source` was rewritten
from the `rtmidi.RtMidiIn()` (rtmidi-python) API to the **`python-rtmidi` `MidiIn`** API
(`get_ports`/`open_port`/`get_message`/`close_port`), because the bridge Python ships `python-rtmidi`
1.5.8 (`MidiIn`, no `RtMidiIn`). A regression test `tests/test_soundswitch_midi_input.py::TestRealMidiSource`
was added (reproduced the `AttributeError` before the fix). Full suite was green (2392 passed,
3 skipped, 1 xfailed).

**Scrutinize this change hardest** (see §4.A). It had no test coverage before, which is exactly how
the original `RtMidiIn` bug shipped unnoticed.

## 4. Adversarial targets — attack these specifically

For each, try to construct a concrete failure (input, sequence, or live scenario) before concluding
it is sound.

### A. MIDI reader correctness (python-rtmidi `MidiIn`)
- Is the `get_message()` contract used correctly? It returns `([status, d1, d2, ...], delta)` or
  `None`. Confirm the unpack, the `len(data) >= 3` filter, and that running-status / multi-byte /
  14-bit / non-note messages cannot crash or be mis-dispatched.
- Are `ignore_types()` defaults (sysex/timing/active-sensing ignored) actually in effect, or must
  they be set explicitly so MIDI clock from the DDJ does not flood the mailbox?
- Busy-loop / CPU: `get_message()` is non-blocking; the empty-poll path sleeps `_INPUT_POLL_INTERVAL_S`
  (3 ms). Is that the right trade between button latency and CPU? Does the drain-before-sleep loop
  starve the stop check under a sustained message stream?
- Worker readiness/stop: does `start()` reliably set `_ready_event`, detect a failed `open_port`,
  and does `stop()` actually terminate the worker (the zombie-thread path at ~L180)?
- Port matching is substring (`port_name in name`). Can it match the wrong device (e.g., a port whose
  name contains "DDJ-800" plus another)? Is first-match the right policy?
- `close_port()` in `finally` when `open_port` never succeeded — safe?

### B. Disconnected / missing controller = loss of ALL DMX (HIGH PRIORITY, live-safety)
- [confirmed] With a populated `midi_input_aliases` but the controller **absent**, the adapter raises
  `OSError("MIDI port not found")` → worker dies → `start()` raises → `_start_soundswitch_pack_workers`
  rolls back to `NoneBackend` ("worker_start_failed") → **no DMX output at all**.
- Is that acceptable for a live show? If the DDJ is unplugged at startup (or its port name drifts),
  should the bridge instead **degrade to DMX-without-controller** (render scripted/base, no static
  overrides) rather than going dark? Decide, and if it should degrade, implement it without
  weakening the existing exclusive-port and no-MIDI-fallback invariants. If current behavior is
  intended, document it explicitly as an operator watchpoint.

### C. Empty `midi_input_aliases` = silent loss of controller input
- [confirmed] Empty aliases → `SoundSwitchMidiInputGroup` builds zero adapters → `snapshot()` always
  reports no held slot → Static Looks are inert while pack DMX still runs. This is silent.
- Should startup emit a loud, sanitized warning when pack mode is enabled with render-affecting
  static/blackout bindings but no input alias maps their device? Propose/implement if warranted.

### D. Toggle semantics & stuck-on risk
- Verify: toggle latches on nonzero note-on, second same-slot note-on clears, note-off ignored,
  velocity-0 note-on (normalized to note-off) does not flip, toggle is exempt from stale-timeout
  (`_static_held_at=None`), press still honors stale-timeout.
- Stuck-on: a missed toggle-off leaves a static latched indefinitely (stale-timeout intentionally
  skipped for toggles; `_mail_drop_count` is inert). Confirm panic / stop / pack-reload / worker
  death / degraded-input ALL release a latched toggle in output. Decide whether the missed-toggle-off
  residual needs a real mitigation or only documentation.
- Cross-device same-slot ownership: loader dedups `(device, slot)` within one device. Two devices
  mapping the same slot are not deduped — can they cross-toggle destructively through the group's
  conflict merge (`snapshot()` ~L456–470)? Construct the sequence.

### E. RE soundness (do not take the byte on faith)
- Re-derive that the `u8` after `label_rgba` is genuinely the Press/Toggle (checkable) flag, not
  another field. Use: the real local `.dat` decoding to exact EOF, semantic plausibility
  (ColourOverride/PlayPause = toggle; TapBPM/BPMInc = press), and the SoundSwitch 2.10.3 binary
  symbols (`MIDIControl::ControlManagerPrivate::loadControlLabelColour`/`saveControlLabelColour`,
  `MIDIControl::ControlManager::reloadData`, `MIDIDialog::eventFilter`, UI strings `Press Mode`/
  `Toggle Mode`). Read-only `nm`/`strings` on `/Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch`
  is allowed.
- Assess the header guard at `soundswitch_project_decoder.py:865` (`if data[7:11] == sig: return None`)
  and its mirror in the inventory tool: prove whether it is dead given the offset-6 check, and either
  remove it (with a comment documenting the offset-6 vs offset-7 disambiguation) or justify keeping it.
- Version handling: `decode_control_label_states` only accepts `version == 1` and silently skips
  others. Confirm the skipped version-3 "Extra" file carries no StaticOverride entries on the real
  project; if a project could carry static modes in another version, this is a fail-open gap.

### F. Fail-closed completeness
- Confirm an active Static Override with missing/unknown mode fails closed at **decode, export,
  verify, AND load** — and that a legacy pack exported before this feature fails closed (not silently
  treated as press) on load.

### G. StateManager integration (no algorithm rewrite expected)
- `_drive_pack_output()` consumes `snapshot().held_static_slot` as a transition. Confirm degraded
  input forces release, runtime swap resets `_pack_last_static_slot` (H11), and the conflict latch
  behaves. Keep `tests/test_state_manager_pack_driver.py` green.

## 5. Verified-now facts you may build on (still re-check load-bearing ones)
- [confirmed] Real project decodes: active DDJ statics slots 8/16/17/24 = `press`; other slots show
  `toggle`; the control-label `.dat` parses to exact EOF.
- [confirmed] Pack loads under the new loader with `interaction` stamped; export writes
  `interaction_mode` only on static rows; verifier rejects violations; focused + full suites pass.
- [confirmed] Live config has `enabled=true, dry_run=false, output_backend=pack`, `enttec_port` set,
  but `midi_input_aliases = {}`. Pack input bindings span `DDJ-800` (4 static_look) and
  `IAC Driver Bus 1` (1 blackout_mask). **`IAC Driver Bus 1` is the bridge's OUTPUT bus to
  SoundSwitch (autoloop/look selection), not a controller to read** — do not add it as an input.
- [confirmed] Bridge Python `/opt/homebrew/bin/python3` (3.14) → `python-rtmidi` 1.5.8 (`MidiIn`,
  no `RtMidiIn`). Laser output uses `mido` + `python-rtmidi`; that is the house MIDI stack.

## 6. Invariants that MUST still hold (Part C)
- `StateManager` is the only `DeckState` writer; pack driver reads once per tick; 200 Hz loop gains
  no blocking work.
- Pack runtime publication stays a single immutable bundle assignment; reload is validate-first,
  no-implicit-enable; disable/swap zeroes physical output before stopping.
- Direct DMX and physical MIDI-laser output remain mutually exclusive; pack failure must NOT fall
  back to MIDI output.
- One active static slot; no stack/blend/background-reassert loop.
- Multi-device conflicting distinct held slots → no held slot + `conflicting_static_holds`.

## 7. Tests to run before you call it done
```
python3 -m pytest tests/test_soundswitch_midi_input.py tests/test_soundswitch_project_decoder.py \
  tests/test_soundswitch_pack.py tests/test_soundswitch_laser_player.py \
  tests/test_inventory_project_artifacts.py tests/test_state_manager_pack_driver.py -q
python3 -m pytest -q
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```
(Run from the repo root; the tests import as the `tests.` package. The repo root must be on the
import path — these commands already are run from there.)

## 8. Deliverable (Part E — definition of done)
- **Verdict:** READY / REVISE / NOT-READY for the feature as a whole, and separately for the MIDI
  reader.
- **Findings**, ordered by severity (Critical / Important / Minor), each with file:line, why it
  matters live, and — if you fixed it — the commit and the test that now guards it.
- **Decisions** on the open design questions §4.B and §4.C (degrade-vs-die on missing controller;
  warn-on-empty-aliases) with rationale, implemented or explicitly deferred.
- **Validated** section: exact commands + pass/fail.
- **Not validated** section: hardware/live/SoundSwitch-UI gaps (expected: no hardware validation; the
  DDJ port name and live press/toggle behavior remain operator-verified only).
- **Operator summary** in plain language: what changes live, what stays the same, how to recognize
  healthy behavior, what to watch in SoundSwitch / lasers / LEDs / Rekordbox reader / bridge logs,
  and the exact approval gates before any restart or hardware-adjacent check.

## Adversarial self-review (attack this prompt)
- If §3's rtmidi fix is subtly wrong (message shape, latency, CPU, stop responsiveness), the MIDI
  reader regresses silently again — the new test must actually exercise the parse + port-match paths.
- If you only review the reader, you miss the bigger live risk (§4.B): a disconnected controller
  taking down all DMX. Cover the startup/degradation path.
- If you accept the RE byte because tests pass, you have not reviewed the RE — re-derive it from
  primary evidence (§4.E).
