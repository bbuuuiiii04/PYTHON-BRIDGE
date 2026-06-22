# SoundSwitch finisher — after-T7e handoff (for the next Claude Opus session)

status: active handoff
last_updated: 2026-06-22
author: Claude Opus 4.8 (finisher session)
branch / PR: `soundswitch/impl` / #116 → base `main`
current HEAD: `039845a`
CI at HEAD: **`unit` GREEN, `docs` GREEN** (perf skipped on PR) — verified via `gh run watch`.

## Status banner (do not upgrade without evidence)
**SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.** No hardware was opened or validated in this
work. The hardware gate (Task 9) is **operator-executed only** — do NOT open MIDI/serial/Enttec/DMX,
do NOT restart the bridge, do NOT send DMX. Never claim show/rig-ready.

## Done this finisher series
- **Step 0** — CI red fixed (Python 3.11 vs 3.14; mappingproxy→default_factory + latent test fixes).
- **Step 1** — export crash-durability (`_fsync_dir`).
- **Step 2 / T7c** — StateManager pack driver (sole `submit_frame` caller; `clear_selection()` idle
  static; autoloop safe-zero). ChatGPT ACCEPT as software checkpoint.
- **Step 3 / T7e** — sanitized pack status + validate-first `set_soundswitch_pack` runtime commands.

## Accepted T7c manual-static policy (carry forward verbatim)
Automatic scripted/autoloop **base** resolves ZERO on idle/stop/stale/error/track-change/
discontinuity. A held **manual Static Override** is operator-controlled (independent MIDI controller)
and **may visibly stand alone** during those deck-authority problems; it loses ONLY to **blackout,
emergency, pack-disabled, and shutdown**. The controller's hold-timeout auto-releases it. Autoloop
output stays safe-zero; never call `select_autoloop`.

## T7e command / status behavior (as implemented)
- One immutable `soundswitch_pack_runtime.PackRuntime` bundle (enabled/reason/player/midi_input/
  backend/frame_sender/pack_sha12) is published to StateManager by a single atomic assignment
  (`set_pack_runtime`); the push loop reads exactly one reference per tick.
- `set_soundswitch_pack` (command thread, `SoundSwitchPackController`): `action` =
  `reload`|`backend`|`enable`.
  - validate-first (`parse_command`); rejected commands invoke no callback and change no state.
  - no implicit hot-enable (reload/backend never enable a disabled pack).
  - stop-before-start on the shared Enttec serial port; **explicit `frame_sender.zero_and_stop()` on
    the OLD sender** (NoneBackend.submit_frame is a no-op — the bundle swap alone does NOT darken the
    rig).
  - no partial swap (old verified runtime retained on prepare/verify failure; else safe no-output).
  - pack failure → disabled/none, **never MIDI**; runtime `backend=midi` deferred → sanitized
    `unsupported_action`; no runtime command opens IAC/MidiOutput.
  - all blocking load_pack/serial work runs on the command thread, never in `_push_tick`.
- Sanitized `soundswitch_pack` status + sanitized command-failure detail (class/category only): no
  paths, ports, aliases, device names, fixture maps, UUIDs, or raw exception messages.

## Files changed (this session, all pushed)
- code: `soundswitch_pack_loader.py`, `bridge_fmt.py`, `tools/export_soundswitch_pack.py`,
  `soundswitch_laser_player.py`, `state_manager.py`, `__main__.py`, `runtime_status.py`,
  **new** `soundswitch_pack_runtime.py`, **new** `soundswitch_pack_controller.py`.
- tests: `tests/test_soundswitch_pack.py`, `tests/test_midi_output.py`,
  `tests/test_runtime_status.py`, `tests/test_led_color_engine_m2_patch_c.py`/`_d.py`/`_phase3.py`,
  `tests/test_soundswitch_laser_player.py`, **new** `tests/test_state_manager_pack_driver.py`,
  **new** `tests/test_soundswitch_pack_controller.py`, **new** `tests/test_soundswitch_pack_commands.py`.
- docs: `docs/subsystems/soundswitch_output.md`, `docs/subsystems/runtime_commands.md`,
  `docs/setup/runtime_commands.md`, the ledger, the T7c/T7e specs, prior handoff.

## Verification run at this HEAD (commands + results)
- `python3.14 -m unittest discover tests` → **OK** (skipped=3, expected failures=1).
- `python3.11 -m unittest tests.test_soundswitch_pack_commands tests.test_soundswitch_pack_controller
  tests.test_state_manager_pack_driver tests.test_runtime_status` → **OK**.
- `cd /Users/bbui && python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation` →
  **PASS_IMPLEMENTATION_MAY_BEGIN** (29 PASS / 0 FAIL / 0 INCOMPLETE; foundation 27/27).
- `tools/check_docs_metadata.py` / `check_agent_contracts.py` / `check_docs_drift.py` → **pass**.
- CI `unit` job → **green at `039845a`**.

## Remaining work (operator's execution order)
- **Step 4 / Task 8** — offline + shadow proof: re-run proof gate at the final commit; export the
  canonical pack twice and prove a byte-identical tree; mutate adversarial artifacts and prove the
  verifier rejects them; run a shadow backend with physical backend `none`, logging frame hashes
  only; if T7d is still blocked, shadow covers scripted/static/blackout and logs autoloop coverage as
  deferred. Pinned totals to assert (from the original task prompt): 42 autoloops, 45 scripted
  inventory, 44 parsed scripted, 32 active existing-path scripted, 232 render + 1 catalog-tail = 233
  venue records, 32 Static Looks, 19 IAC bindings, 4 DDJ overrides, active-cue union count 166 + the
  pinned union SHA `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`.
- **Step 5 / Task 9** — author `docs/plans/active/soundswitch_t9_hardware_handoff.md` (REVIEW-ONLY;
  open no devices; operator-executed gate only).
- **Do not start Step 4 in a new session unless Brandon explicitly asks after reviewing this handoff.**

## T7d blocker (unchanged)
Autoloop DMX stays blocked until capture evidence proves (1) ticks/beat (~600 likely) AND (2)
universal phase origin across initial-arm/refire/master-switch/drop-hold/buildup/phrase-anchor/
correction. **Do not implement autoloop DMX**; the driver must never call `select_autoloop`.

## Operator working agreement (carry forward)
- Codex-implements rule is overridden for THIS task (Claude implements directly); task-scoped only.
- **Plan-first / review-before-implement for live-critical pieces** (author spec → commit → pause for
  ChatGPT review → implement). T7c and T7e both went through this.
- CI `unit` runs **Python 3.11** (PR-only); local is 3.14 — always run 3.11 for dataclass/import work.
- Proof gate runs from the PARENT dir (`cd /Users/bbui && python3.14 -m rb_ss_bridge_v2.tools...`).
