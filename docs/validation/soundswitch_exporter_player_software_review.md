---
doc_status: active-validation
truth_level: code-and-test-grounded
last_verified_commit: c81386c
last_verified_date: 2026-06-25
validation_scope: independent SoundSwitch exporter/player software-wire review; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch exporter/player software-wire review

Review range: current `main` at `c81386c`, with the medium finding below fixed in
this task before commit.

## Status

Verdict: APPROVE after the included medium fix.

This review used the RW-5 hard boundary: no live config read/edit, no bridge
start/stop/restart/process inspection, no runtime commands, no menubar actions,
no MIDI/serial/Enttec/DMX open, and no fixtures. Conclusions are software/wire
only and do not change the repository hardware status.

## Findings

- blocker: none.
- high: none.
- medium: fixed - `scripts/bridge_menubar.py:323-326` now accepts the exporter
  `sidecar_failed` verdict. Before the fix, a required binding-sidecar write or
  promote failure returned `sidecar_failed` from the exporter but the menubar
  parser collapsed it to `unknown_error`, hiding the specific software failure.
  Reload safety was already intact because `ok=false` still stopped the reload
  path. Regression coverage: `tests/test_bridge_menubar.py:288-299`.
- low: none.

## Requirement audit

| Requirement | Result | Evidence |
| --- | --- | --- |
| Export, canonical replace, required sidecars, conservative reload | PASS | `publish_pack` verifies staged artifacts, stages the required binding sidecar before the canonical swap, and promotes it as a sibling after swap (`tools/export_soundswitch_pack.py:427-474`). The menubar only appends the existing reload command after a fresh enabled snapshot with pending SHA (`scripts/bridge_menubar.py:978-1007`). |
| Lock/swap/recovery and stale-state handling | PASS | Export locking/recovery/gc happen before decode/stage (`tools/export_soundswitch_pack.py:437-445`); the fallback swap restores on rename failure (`tools/export_soundswitch_pack.py:377-389`); stale status prevents blind reload (`scripts/bridge_menubar.py:355-363`, `scripts/bridge_menubar.py:982-992`). |
| Static Look export/load/manual/layer Press/Toggle | PASS | The decoder reads the SoundSwitch-saved Press/Toggle flag (`soundswitch_project_decoder.py:852-893`), the loader rejects invalid static interactions (`soundswitch_pack_loader.py:260-297`), and the MIDI adapter latches toggles while ignoring toggle note-off (`soundswitch_midi_input.py:260-319`). |
| Scripted render + unsupported-layout/identity fail-closed | PASS | The player requires normalized identity, fresh authority, supported active scripted rows, and supported layouts before rendering (`soundswitch_laser_player.py:306-350`). Loader cross-checks active scripted inventory before returning a pack (`soundswitch_pack_loader.py:640-655`). |
| Runtime default-off and no implicit hardware enable | PASS | Pack config defaults to `enabled=False`, `dry_run=True`, `output_backend="none"` (`soundswitch_pack_player_config.py:104-113`). Startup returns legacy/none/dry-run bundles unless config explicitly reaches pack mode with an Enttec port (`__main__.py:454-529`). |
| 200 Hz path and safe-zero behavior | PASS | `_TICK_INTERVAL` remains 200 Hz (`state_manager.py:343`); pack runtime is a single reference read per tick and the driver only uses in-memory deck/cache/input snapshots before one submit (`state_manager.py:3270-3282`, `state_manager.py:3361-3511`). Render/submit failures publish bounded software-zero and attempt zero (`state_manager.py:3512-3531`). |
| Blackout/emergency precedence and static overlay | PASS | Layer application returns zero when blackout or emergency is held (`soundswitch_laser_player.py:172-185`); player render checks masks before reload wait, automatic base, or static layers (`soundswitch_laser_player.py:380-407`). |
| `select_autoloop` never called by StateManager | PASS | `_drive_pack_output` derives scripted-or-zero only and uses `clear_selection()` outside the happy scripted path (`state_manager.py:3444-3496`); the regression test installs a raising `select_autoloop` mock and proves it is not called (`tests/test_state_manager_pack_driver.py:864-876`). |
| Sanitized RW-5 status | PASS | `PackRuntime.sanitized_status()` exposes bounded fields and calls no provider (`soundswitch_pack_runtime.py:35-44`); `StateManager` publishes a fresh dict and `get_pack_status()` returns a copy (`state_manager.py:3317-3359`); tests prove provider-free copy behavior, fresh dict publication, simultaneous truths, and bounded render/submit failures (`tests/test_state_manager_pack_driver.py:819-947`). |
| No Stream Deck/export sidecar code in bridge runtime path | PASS | Runtime loading uses verified `learned_midi_bindings` from the pack manifest (`soundswitch_pack_loader.py:657-682`) and startup passes those bindings to the MIDI input group (`__main__.py:492-529`). A search of runtime pack surfaces finds no `_binding_sidecar` or Stream Deck sidecar dependency outside the exporter/menubar launch path. |
| Hardware status unchanged | PASS | Current status docs explicitly keep SoundSwitch direct-DMX and hardware as unvalidated (`docs/status/feature_status_matrix.md:31-49`, `docs/status/validation_matrix.md:38-52`, `docs/validation/hardware_validation_log.md:11-29`). |

## Verification

- `python3 -m unittest tests.test_state_manager_pack_driver tests.test_soundswitch_pack_commands tests.test_runtime_status tests.test_bridge_menubar tests.test_soundswitch_frame_sender tests.test_enttec_dmx_pro tests.test_soundswitch_pack_startup`: PASS, 219 tests.
- `python3 -m unittest tests.test_bridge_menubar`: PASS, 30 tests.
- `python3 -m unittest tests.test_soundswitch_pack`: PASS, 66 tests.
- `python3 -m unittest discover tests`: PASS, 2400 tests, 3 skipped, 1 expected failure.
- `python3 tools/check_docs_metadata.py`: PASS.
- `python3 tools/check_agent_contracts.py`: PASS.
- `python3 tools/check_docs_drift.py`: PASS.
- `python3 tools/check_docs_staleness.py --report`: advisory STALE for `core_bridge` and `soundswitch_pack_player`; Task 4 owns the required re-verification and baseline bump.
- `git diff --check`: PASS.
- `python3 tools/prove_soundswitch_pack_generation.py --project <private canonical project> --output-dir <tmp>`: PASS_IMPLEMENTATION_MAY_BEGIN, 29 PASS / 0 FAIL / 0 INCOMPLETE, foundation 27/27.

## Scope and privacy audit

No live/runtime/hardware action occurred. The review and fix did not read ignored
live config, append command files, inspect bridge processes, open MIDI/serial/DMX,
or run the menubar. The new note and test use only sanitized verdict/category
strings and no local paths, ports, aliases, device names, fixture serials, project
UUIDs, raw frames, raw hashes, or config contents.
