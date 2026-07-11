---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 9a432b8
last_verified_date: 2026-07-10
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Software Test Inventory

This inventory routes agents to tests without pretending software tests validate physical lighting hardware.

## Broad command

```bash
python -m unittest discover tests
```

If using pytest-specific tests or fixtures:

```bash
python -m pytest tests
```

## Subsystem routing

| Area | What to look for in `tests/` | Notes |
| --- | --- | --- |
| Core bridge | state manager, models, smart phrasing, integration tests | verifies software behavior only. Smart-drop selector tests cover cluster collapse, exact-64 raw gaps, intro/outro trimming, and breakdown-selection parity. |
| Rekordbox reader live-safety (AWR reader cross-version) | `tests/test_rekordbox_reader_safety.py`: the emit-boundary tempo clamp (`clamp_emit_bpm` bounds garbage/NaN/high BPM in `send_bpm`/`send_beat`/`send_deck_load` and the scanner-follow + autoloop + `os2l_injector` paths), the direct-read BPM cap `_RB_BPM_READ_MAX`, unknown-version fail-closed (inert reader `_offs is None`; scanner 40..250 `_valid_bpm` gate), version-string normalization edges, per-version MIXER/CFX presence, and the offline version-extension tool (`tools/rekordbox_derive_offsets.py` reproduces the 7.2.11 anchors from symbols and fails closed on a missing/ambiguous symbol or implausible RVA) | pure-function + fake-conn tests; they prove the value clamps and the symbol-derivation math, NOT that a real garbage memory read occurs live, that beat-locked flash is driven on hardware, or that a future version's binary is symbolized the same way (only 7.2.11's binary is on disk) |
| Runtime commands | parser/handler/status writer tests plus menubar watcher-launch tests and watcher function tests (`tests/test_ss_bridge_watcher.py`: attributable deck stops, bridge-gap respawn). AWR-192 (menubar overhaul) adds 7 cases to `tests/test_bridge_menubar.py` (91 total there; each base-class case runs twice via the M2 `NativeInstallGateTests` subclass): `test_led_row_fields_truth_table` + `test_led_row_fields_malformed_never_raises` (the pure LEDs glance-row helper: on/off/unknown states, fps only while realtime-active, degraded-reason surfacing, malformed-status fail-soft), `test_compact_status_lines_returns_ten_rows_both_branches` (pins the `refresh_` zip contract — a row-count mismatch silently drops rows), `test_menu_blueprint_selector_inventory_exact` (the regroup added/removed NO commands: pre-refactor 14 selectors + 2 M2, each exactly once), `test_menu_blueprint_blackout_promoted_to_top_level`, `test_menu_blueprint_maintenance_block_order`, and `test_menu_blueprint_attrs_unique` | needed before command changes; menubar/watcher tests do not prove live watcher or bridge process health; blueprint tests pin layout data, not rendered NSMenu behavior |
| USB stick helpers (AWR-122 interim) | `tests/test_stick_commands.py` runs the real `packaging/stick/purge.command` under a throwaway `$HOME`: refuses without a manifest, refuses without the typed `PURGE` confirmation, removes exactly the manifest paths and prunes emptied dirs, and skips outside-allowed-roots + `..` paths while still removing legitimate entries | subprocess tests of purge's deletion scoping only; `install.command` (hdiutil mount + copy + manifest) is proven by a desk smoke against the real DMG and a throwaway `$HOME`, not by CI; neither proves foreign-Mac Gatekeeper/permission behavior |
| USB launcher (M2 native install/PURGE, AWR-186) | `tests/test_make_stick.py` drives `packaging/make_stick.sh` through its documented test seams (no PyInstaller/hdiutil): staging layout (app + `RBSS_payload/spectral_cache` + `RBSS_payload/home/` five-file parity list), absent-source skip-with-note, existing-but-unreadable ABORT naming the step, a malformed/unreadable `soundswitch_pack_player.json` OR a declared non-empty `pack_path` that is not a readable directory ABORT nonzero (a stick never ships claiming success with no show), an absent config or empty `pack_path` staying backward-compatible no-pack, PIONEER-volume target refusal, `bash -n`. `tests/test_enttec_dmx_pro.py` proves `find_enttec_port` returns a device ONLY on positive ENTTEC identity (manufacturer/product/description strings): a lone generic FTDI (VID 0x0403) and a bare `usbserial` device name are rejected, two identified Enttecs are ambiguous (None), detection is metadata-only (no port opened), and `resolve_enttec_port` fails closed to the operator's configured port when no positive identity is present. `tests/test_install_controller.py` covers the native installer/purge pure seams: DMG/translocation detection + `bundle_root` walk + install-offer matrix + payload-sibling discovery; `perform_install` full layout with interim-format manifest exactness (absolute paths, app first, appended per success) and partial-failure step naming with the manifest listing only what landed; `launch_profile.app_support_config_env` present/absent env maps (all four seams incl. `RBSS_LASER_COLOR_MAP_CONFIG`); `perform_purge` allowlist + `..` rejection + three-root removal order + own-app deferral + failure-records-and-continues (rmtree fault injection); `launch_profile.resolve_state_path` frozen mapping vs byte-identical source passthrough, wired at both consumers (`led_config` store_path parse, `drop_presentation.LEARNED_STORE_PATH`). `tests/test_bridge_menubar.py` adds the frozen gates (no module-level `install_controller` import; install/purge worker failure marshaling). `tests/test_usb_launcher.py` adds App-Support-copy-wins and explicit-env-wins wiring. `tests/test_laser_color_engine.py` adds the color-map env seam | pure/temp-dir tests only; they prove staging/install/purge decision logic and env wiring, NOT that a rebuilt DMG carries the payload, that the NSAlert flows render, that a running bundle Trash-moves cleanly, or foreign-Mac Gatekeeper/TCC behavior — that is the operator walkthrough (runbook parity table) |
| Frozen-app foreign-Mac fixes | `tests/test_bridge_menubar.py` adds `FrozenDefectHelperTests`: the flock singleton `acquire_menubar_lock` refuses a second holder and re-acquires after release (DEFECT 2, replaces the pgrep/`MENUBAR_PATTERN` guard a frozen argv never matched), `export_button_enabled` is false when frozen (DEFECT 4 authoring-only), `laser_pad_argv`/`led_pad_argv` resolve source vs frozen (`--run-laser-pad`/`--run-led-pad`), `_format_child_failure` names the exit code + stderr tail (DEFECT 6). The pad handlers now `open_pad` (probe port → spawn if down → open) instead of opening a dead URL (DEFECT 5). `tests/test_rekordbox_patch.py` adds `SanitizedSystemEnvTests` for `sanitized_system_env` (DEFECT 3: restore each DYLD_* from `*_ORIG` or drop it). `tests/test_usb_launcher.py` adds `--run-laser-pad`/`--run-led-pad` dispatch | pure/flock/temp-dir + monkeypatched-dispatch only; they prove the guard, gate, argv, env-sanitizer, and pad-spawn LOGIC. They do NOT prove: the python.org universal2 build runs on old/Intel macOS (DEFECT 1 — `make_stick.sh` + runbook, frozen-only), that a frozen bridge/patch child's stderr surfaces in an NSAlert, that the re-signed Rekordbox actually reads under packaged TCC, or that the shell installers' full-payload parity round-trips — all operator-walkthrough only |
| USB launcher (M1) | `tests/test_launch_profile.py` pins the single-source launch env — the 19 `RBSS_*` flags + the laser-config path that the watcher and the future bundle both read from `launch_profile.py`, including the AWR-149 deltas (`RBSS_LED_TRANSPORT_COOLDOWN=0`, `RBSS_LED_TRANSPORT_STICKY` absent) — and greps `scripts/ss_bridge_watcher.sh` to prove it now reads `launch_profile` instead of a hand-maintained flag list. `tests/test_usb_launcher.py` pins the `usb_launcher.py` dispatch table (menubar / `--run-bridge` / `--run-streamdeck` / `--run-frame-engine --fd N`), that `--run-bridge` forces the profile env while honoring an operator `RBSS_LASER_CONFIG` override, that the frame-engine child dispatches without loading the Cocoa menubar, and that an unknown mode fails closed with a nonzero exit. The `scripts/bridge_menubar.py` frozen owned-child-pid branch is `getattr(sys, "frozen", False)`-gated, so `tests/test_bridge_menubar.py` (source-run) stays byte-identical. `tests/test_replay_event_source.py` covers the "Test the Lights" replay source: the merged event/position/live_bpm timeline is time-sorted, rows are re-stamped to the live clock (recorded positions would otherwise be dropped as stale) and paced by their recorded spacing, `None` BPM is skipped, and the preflight fails closed (Rekordbox running OR no session file both refuse, Rekordbox first). `tests/test_launch_agent_plist.py` covers the LaunchAgent plist generator: `ProcessType=Interactive` (AWR-151) is always set, and `tools/check_launch_agents.check()` passes on a generated plist and flags one missing it | pure-function + grep + monkeypatched-dispatch tests only; they prove the shared env source, the arg routing, and the replay timeline/pacing/preflight logic, NOT that a PyInstaller bundle packages/runs, that the frame-engine child spawns, that Rekordbox memory reads match, or that a recorded session actually drives the rig live — the last is the operator-gated Task-7 parity run (record a session, then Test the Lights) |
| Logging visibility | `bridge_log`/`bridge_view` pipeline + viewer tests, `bridge_fmt` rate-control tests, and cross-subsystem `perf.*`/`health.*` emit assertions | verifies the JSONL event stream, viewer lens/latch logic, and spam-control behavior only — no lighting-hardware behavior |
| Runtime audit P1 cleanup | `tests/test_runtime_status.py`; compile/docs checks | smart-drop/breakdown queue-full failures surface in command status; dead-code/stale-text cleanup is software-only |
| Rekordbox readers | reader, offset, live BPM, active-deck resolver, StateManager authority, startup wiring, runtime status tests | cannot prove all app versions or hardware-visible behavior. Audit P3 adds ANLZ read-failure cache recovery coverage. AWR-148 adds `tests/test_rb_memory_scans.py`: deck-2 scan-filter equivalence (numpy vs pure fallback vs old-loop oracle, incl. the int32-overflow edge), GIL-yield behavior, and numpy-failure fallback (pure seams). AWR-157 adds `tests/test_rb_memory_chain.py` (`ChainFreshnessTests`, 7 cases): frozen deck-2 raw while the external playing hint says playing goes stale after exactly 5 identical reads (not 4, not 6); advancing raw always stays fresh; frozen raw while the hint says paused stays healthy indefinitely (the FEIN case); the ObjC fallback engages and `chain_ok` flips false on staleness; deck 1 is provably untouched (one `read_deck(1)` call total, from the pre-existing length-refresh cadence, never from the freshness gate); both new log lines (`chain-stale fallback-engaged/fallback-idle`, `pause-vs-freeze`) are edge-triggered, not per-tick. Pure fake-memory `RBSession` seams, no mach/live process. |
| SoundSwitch | OS2L/output helpers; project/pack/player/native-Autoloop-resolver/MIDI/backend/Enttec/config/startup/controller/commands/StateManager/status/menubar/shadow/Art-Net truth-check/T7d/parity-lane tests | pack coverage is pinned to SoundSwitch 2.10.3 canonical UUID/RAVE; copied status, native Autoloop rendering, U1 truth-check packets, and passive U0 parity fixtures are software/wire evidence and tests do not prove physical fixtures. Audit P2 adds software coverage for SoundSwitch-connected `overlay_suppressed` status. Audit P3 adds explicit scripted elapsed threading coverage. AWR-135 adds `base_suppressed` status coverage for intentional LED-only drop darkness. |
| Laser | laser config/director/executor/MIDI dry-run tests | cannot prove physical safety. `tests/test_drop_lifecycle.py` covers true smart-drop crossings, the capped chorus-to-chorus second hit, post-cap demotion, per-section reset, single-marker behavior, and LED flat-window parity. Audit P4 adds send-error reopen recovery, bank-gate restore, config fallback/cooldown validation, deprecated `pre_drop_scene` tolerance, blackout-mask refcount, and Laser Pad live-toggle command append coverage. |
| LED/Govee | LED config/director/color/realtime/renderer tests plus StateManager LED automation tests | cannot prove device compatibility or room-visible behavior. `tests/test_led_state_manager.py` covers the mirrored real-crossing drop-impact gate, the capped chorus-to-chorus second hit, post-cap demotion, 32-beat intra-section role-key rotation for long buildup/pre-drop/breakdown/monotonic ambient sections, the bounded active-content hold with hold/reset observability, and no-audible idle ambient dispatch/freewheel cleanup. `tests/test_beat_sync_engine.py` covers the AWR-141 realtime wrap guard: sub-threshold backward jitter holds without wrap/spawn, real loops still wrap, forward crossings stay capped, and continuous effects do not replace their instance on jitter. `tests/test_govee_realtime_runner.py` covers idle-grace blackout-before-deactivate ordering. `tests/test_govee_runtime_sender.py` covers mirror-send health transition logging and status; `tests/test_govee_scene_adapter.py` covers circuit-open degraded-state healing. `tests/test_led_color_engine_integration.py` covers stable section/cycle publication, unchanged drop/groove/post_drop key strings, and a dispatch-path second look across a buildup cycle boundary. Audit P2 adds committed-drop DIY eligibility coverage. Audit P3 adds runner-thread realtime handoff teardown coverage. Audit P5 keeps existing LED state-manager coverage as the behavior oracle for dispatch bookkeeping extraction. AWR-142 adds no new test: it appends `transport=`/`runway_beats=` to the accepted smart-drop-blackout log lines (observability only), and the repo does not unit-test log text, so correctness is "no behavior change" covered by the existing LED suite staying green. AWR-144 adds `LEDSoloPredarkHoldTests` (4 cases) in `tests/test_led_state_manager.py`: a pending `lasers_only` drop suppresses the LED drop look and reports the `solo_predark_hold` gate reason, a `leds_plus_lasers` drop still dispatches its drop look, drop-presentation disabled (`(None, "", None)`) is a byte-identical no-op, and a set `drop_spotlight` blackout owner still masks via the pre-existing `emergency_blackout` gate. AWR-146 adds `tests/test_govee_frame_engine.py` (host + client, 14 pure cases: init/deactivate ordering, anchor staleness, list-param render parity, command fan-out, AWR-145-through-the-boundary brightness/activate/keepalive, EOF/shutdown teardown, heartbeat fps + degraded edge-trigger, `decode_buffer` framing, no-caller-thread-I/O + wire order, respawn intent replay, hung/stuck respawn, emergency queue-jump, status merge, stop escalation) and `tests/test_govee_frame_engine_integration.py` (real subprocess: 60.9 fps this machine, orphan-EOF exit-0; timing-sensitive, skipped under `CI=true`). AWR-122 M1 Task 4 adds `ChildArgvTests` in `tests/test_govee_frame_engine.py`: `_child_argv(False, fd)` is the byte-identical source-run argv, `_child_argv(True, fd)` is the frozen `--run-frame-engine` re-exec form, and `_default_spawn` selects argv + drops the `cwd` pin by `sys.frozen` — proving the bundle-portability spawn seam in software only, not that the frozen child actually streams frames (that is the operator parity run). Task 6 adds a coordinator `blackout_brightness()` test, a StateManager accepted/cloud-only-no-op/rejected blackout-dim test, and a runner inactive-`request_brightness(0)`-reaches-transport-twice test. These prove IPC framing, supervision, and the moved-runner parity in software only — not room-visible smoothness or device behavior. AWR-149 adds `LEDLookDirectorPlanRotationTests` in `tests/test_led_look_director.py`: `plan_backend_sequence()` exact tuples (frozen 6RT+2cloud spacing, 1+1 realtime-first, 3+3 realtime-leads-tie, single-backend, empty, order stability), seed-independent 12-pick backend sequences, the no-latch groove regression, plan-index-0 session phase across seeds, eligibility rebase plus C4 full-bank fallback, preview parity with no cursor/bag/RNG mutation, and paired-post_drop plan bypass. These prove the deterministic transport selection in software only. AWR-151 Tasks 1-2 add band-instrumentation cases (Task 3 precision-sleep dropped per operator doctrine, not implemented or tested): `tests/test_govee_frame_engine.py` gains a host test that every heartbeat carries `band_setpriority`/`band_nsactivity`/`band_darwin_prio` and re-reads getpriority + re-asserts setpriority once per heartbeat through a faked module-level libc seam (live semantics recorded in the test: `getpriority(PRIO_DARWIN_PROCESS,0)` == 0 = not in the darwin background band on this machine), a client test that the three scalars pass through `status()` with `False/False/None` defaults before any heartbeat, a client test that the band report logs once per (re)spawn (not per heartbeat) with a failed-raise health edge via a faked `bridge_log`/`log_changed` seam, and a policy test that `_sanitize_led_adapter_status` admits the three band keys; `tests/test_govee_frame_engine_integration.py` adds a CI-skipped real-child test that the first heartbeat carries `band_setpriority` True and a `band_darwin_prio` value. These prove the band self-report is visible in software only — not that the raise is effective under the real launch chain (Phase B) or the live fps (operator's next mix). AWR-150 (drop-impact transport guarantee) adds keepalive-yield cases to `tests/test_govee_realtime_runner.py` (suppress inside the window, 30 s cap restore, each of the five intents cancels, cancel re-enables the keepalive, yield does not block the brightness drain), `stage_cloud_takeover` cases to `tests/test_led_dispatch_coordinator.py` (adapter trigger with no `force_deactivate`/owner change/dwell record + yield on accept; no yield on reject), `substitute_realtime_drop` cases to `tests/test_led_look_director.py` (realtime-only pick, only the `(drop, realtime_razer)` backend cursor advances with the plan cursor and next real commit unchanged, no pair queued, None on a cloud-only drop bank), and three end-to-end cases to `tests/test_led_state_manager.py` (cloud drop → tactical blackout + RT substitute dispatched + committed cloud staged under the committed identity; cloud-only adapter keeps today's cloud dispatch and never consults the substitute; substitute retry-then-accept stages exactly once). These prove the on-beat render + cloud-staging path in software only — not that cloud scenes visibly upgrade mid-drop or that no blackout sticks, which is the operator's next mix. AWR-152 white-knob round 1 adds: `tests/test_led_identity_v2.py` — `derive_dressing` returns a configured `slot5_white` verbatim (not sat-floored/hue-shifted) as slot 5, plus the existing default-pure-white regression. `tests/test_led_config.py` — `slot5_white` parse (valid RGB, absent-default, malformed fails closed and disables only the v2 sub-block), legacy `white` keys in palettes and zones ignored without error, the example config loading clean, and `groove_diy_bright_white_chase` landing in `banks.default.buildup` (not `groove`). `tests/test_led_color_engine.py` and `tests/test_color_engine_config.py` — `Palette`/`ZoneRampConfig` no longer accept `white=`, the deleted `_blend_white` tests removed, and the palate-reset slot path returning all six slots (not five-plus-hardcoded-white) dimmed from NEUTRAL's `slot5_white`. `tests/test_led_color_engine_m2_phase1.py` and `tests/test_led_color_engine_m2_patch_s.py` had their inline `_blend_white`-recomputation math updated to the unblended `_p_to_rgb` result (mechanical fallout of the deletion, wider than the spec's named file list). `tests/test_led_state_manager.py` — `_led_diy_eligible_predicate` returns `None` when the v2 latch is set and the engine predicate otherwise, plus a v2-latched automation tick asserting the director's `LEDContext.diy_eligible` is `None` (no color-tag filtering). `tests/test_govee_frame_renderer.py` — `_slot_breakdown_star_twinkle` never lights the slot-5 column across a multi-beat, multi-frame sweep. These prove the config/engine/dispatch logic in software only — not that the tinted white accents or evenly-rotating cloud scenes read correctly in the room, which needs the operator's config mirror + menubar restart + next mix. AWR-154 (LED pad blackout unlatch fix) adds: `tests/test_led_pad_playback.py` — `OwnershipGate.release()` sends `{"cmd": "led_clear_blackout", "reason": "led_pad"}`. `tests/test_runtime_status.py` — `parse_command` accepts a valid `reason` on `led_clear_blackout`, rejects an empty `reason` and a genuinely unknown field; `CommandReader.handle_command` passes the parsed reason (present or `None`) through to the callback. `tests/test_led_state_manager.py` — a `led_clear_blackout` with `reason=led_pad` discards exactly the `led_pad` owner from `_led_blackout_owners`, leaving a bystander `legacy` owner blacked out (the original bare-clear-only-legacy case in this test was superseded and replaced by AWR-155, see below). These prove the reason threads end to end through `parse_command`/`CommandReader`/`_led_clear_blackout`/the owner set in software only — not that a process already latched dark unlatches without a restart. AWR-155 (LED bare-clear fail-open) adds/replaces in `tests/test_led_state_manager.py`: a bare `led_clear_blackout` with `led_pad`/`drop_spotlight`/`legacy` all present clears every owner in one call and emits exactly one `[RGB] blackout-clear-all` INFO log naming all three (captured via `assertLogs`); a separate case with a `_RestoreAdapter` stub proves `restore_brightness()` fires when the clear-all empties the owner set. These prove the clear-all owner logic and the outcome-log discipline in software only — not that a currently-latched-dark process actually unlatches, since this fix only takes effect on the next bridge restart. AWR-156 (LED round 2: strobe-gate rebuild + accepted-look promotion) adds: `tests/test_govee_frame_renderer.py` — `_hz_strobe_on` BPM-invariance (identical ON/OFF pattern for the same `local_t` series regardless of `beat`), frame-aware widening (a synthetic 28 fps sweep lands >=1 ON frame in every cycle when the ON window is forced to >=1.6 frames), hz/duty caps; the `drop_strobe_colorway` effect (solid/alternating/`_color` fallback/strobe registration); the C5 param-allowlist guard for every new/changed look; `buildup_balloon_comet` monotonic brightness shrink over `build_beats`; `_head_weights` peak==1.0 across a sub-pixel position sweep (the 0.53x between-pixel dip regression guard); all four `rt_groove_heartbeat` `color_mode`s writing only their documented slots; the `rt_post_drop_firework_remnants` ember timeline (full at beat<=8, zero by beat 10.5) plus slot-5-carries-only-background plus same-seed/local_t determinism; single-slot-per-pixel at all 8 knob-#4 rewritten sites plus the untouched positional-mapping prototypes still splitting across two slots; and Task 9's `BAKED_WHITE_SLOT5_EFFECTS` (firework bursts render literal pure white, nebula comets and the remnants background keep the injected tint). `tests/test_govee_realtime_runner.py` — `frame_period_s` reaching the renderer's params via `_tick_once`, and the EMA pulling above the steady-state baseline after a simulated stalled tick (an Event-based lockstep single-steps the runner thread through the fake `sleep_fn` seam, no real wall-clock delay). `tests/test_led_config.py` — the example config loading clean; all 7 colorway looks validating (strobe class + allowlist, `color_source: baked`); `strobe_red_white`/`strobe_cyan_white` side-B color pins; the 3 promoted looks present with the right `color_source`; bank membership for colorways/promotions; the renamed/moved looks (`rt_post_drop_remnant_chase`/`_nebula`) in `post_drop` and absent from `drop` and from `looks` under their old names; their `drop_pairs` entries gone; `step_within_section.groove` still `true`; knob #9 width values. `tests/test_led_pad_controls.py` gained `CONTROL_META`/`PARAM_DEFAULT_OVERRIDES`/`RENDER_GROUPS` entries and hand-extracted-literal audit lines for every new param key (`led_pad_controls.py` has a module-level completeness assertion against `REALTIME_EFFECT_NAMES`/`REALTIME_EFFECT_PARAM_KEYS` that would otherwise fail import for `test_led_pad_controls.py`/`test_led_pad_lab.py`/`test_led_pad_service.py`). The `test_led_color_engine_m2_patch_b/c/d/e1/e2/f.py` and `test_led_color_engine_m2_phase1.py`/`phase2a.py` regression-lock suites (pre-existing exact `SLOT_EFFECTS`-set/bank-membership/`drop_pairs`/look-params assertions, not named in the spec's file list) were updated for the new registry entries, the knob-#4 slot-choice mechanism replacing the old intensity-sweep assertions, and the T6.4 rename. Full suite: 3543 tests, same 5 known pre-existing reds (4 unrelated soundswitch pack-parity + 1 pre-existing LED live-config `KeyError` in `test_drop_slot_color_smoke_and_snap`, confirmed present at the pre-AWR-156 baseline commit `b0bbcb3` via a detached diagnostic worktree), nothing new. These prove the gate math, slot routing, param plumbing, and config wiring in software only — not that the strobe feel, comet colors, or widths read correctly in the room, which is the operator's next mix after mirroring the config and restarting. AWR-157 (darkness-fix round: blank-role hold + reader freshness) adds `BlankRoleHoldTests` (8 cases) in `tests/test_led_state_manager.py`: blank/scripted-mapped role + audible playing + a prior accepted decision suppresses the blackout dispatch (gate reason `blank_role_hold`, current look retained, verified via the scripted `groove`→`utility` mapping since the diagnosis left the literal blank-role origin as an open question); not-playing and no-prior-accepted-decision both dispatch normally; emergency blackout still wins immediately; the tactical pre-drop blackout dispatches unaffected even with a prior accepted decision primed (reusing the AWR-142-style `_led_should_smart_drop_blackout`/`_led_sp_state_with_offset` harness); knob off is byte-identical, including that the Q-A log still fires; the log is edge-triggered (INFO once, DEBUG on identical repeats). `tests/test_led_config.py` gains `BlankRoleHoldConfigTests` (5 cases): `blank_role_hold` absent-defaults-true, explicit true/false, non-boolean rejection, and the shipped example config still loading. These prove the dispatch-suppression and config-parse logic in software only — not that a blank-role blackout stops recurring live, which is the operator's next mix. AWR-161 (LED round 3: Hz-gate migration + rainbow/firework promotions + center-burst fix) adds `Awr161HzMigrationCoverageTests` in `tests/test_govee_frame_renderer.py`: all 18 migrated effect names (13 non-slot + 5 slot) flash on the wall-clock Hz gate at two different `beat_pos` values (BPM-independence), hz/duty params are dialable (hz=1.0/duty=0.5 example), and the C5 allowlist guard covers hz/duty for every one. `RainbowOrderedTests` covers registration + not-a-strobe, beat-locked `travel_per_beat` advance landing on the exact expected pixel independent of `local_t`, the legacy `loop_beats` pace matching the same formula byte-stable when `travel_per_beat` is absent, and hue-ordered-by-position with full HSV value (max channel 255) at the anti-aliased peak. `DropFireworkExplosionTests` covers the promotion gate itself — measured post-surge ember contrast 101/255 against the required >=60/255, sampled across 400 frames at a fixed post-surge beat — plus the surge resolving down to `bg_hold` instead of staying pinned at full background, registration/not-a-strobe, and embers being time-based (`local_t`-driven, not beat-tied, per the AWR-153 sparkle ruling). `tests/test_led_color_engine_m2_patch_d.py`'s `test_center_burst_preserves_even_pixels_only` (which asserted odd pixels always stayed dark) is replaced by `test_center_burst_covers_every_pixel_not_just_even`, sweeping the same beat range and asserting both even- and odd-index pixels light up somewhere; the existing main/accent slot-band-split test is untouched, proving that discipline survived the fix. Verified against the untouched pre-session HEAD (before any of this round's commits): the pre-existing 6-red baseline in the `led_color_engine`/slot-effect family (`test_strobe_off_frames_are_dark`, `test_drop_chase_strobe_off_frames_are_dark`, `test_drop_nebula_strobe_gate_can_go_dark`, `test_post_drop_nebula_strobe_gate_can_go_dark`, `test_strobe_gate_can_go_dark`, `test_drop_slot_color_smoke_and_snap` `KeyError`) is unchanged and unrelated to this round's code. These prove the gate math, the two new effects' render math, and the pixel-coverage fix in software only — not that the migrated strobes, rainbow pair, firework explosion, or fixed center burst read correctly in the room, which is the operator's next mix after mirroring the config and restarting. AWR-179 (QA minors cleanup) adds: `tests/test_led_state_manager.py` — `test_anlz_extractions_capped_at_two_and_skip_stale_gen` (D4-F2: `BoundedSemaphore(2)` caps concurrent ANLZ extractions; a stale-gen worker skips the read). `tests/test_state_manager_drop_presentation.py` — `PerLoadStructureTrimTests` (D4-F4: the drop-damper `(deck, load_gen)` key is trimmed on track change and the new track's latch still fires; the arm-debounce map prunes dead entries and still debounces). `tests/test_led_color_engine.py` — `test_bloom_latch_caps_and_clears_without_losing_bloom` (D4-F4: the once-per-identity bloom latch clears past 512 and still arms a bloom claim). `tests/test_lighting_moments_v2.py` — `TestTransitionRelease` value table + `test_transition_release_gate_off_scripted_and_plumbed` (D2-F1: `transition_release_for` = `drop − abort_at` for blackout+abort only; gate is 0.0 off/scripted). `tests/test_smart_phrasing.py` — release=0 byte-identity, release>0 early-deactivate + clear-before-drop, release==window-length never-activates (D2-F1). `tests/test_govee_manual_trigger.py` — `ValidateProvenanceTests` (D4-F1: commit drift is a warning; freshness/branch/artifact gates still fail closed). These prove the concurrency cap, map hygiene, early-release wiring, and provenance gate in software only — not room-visible behavior. AWR-184 (deep sub-void blackout rung) adds `TestDeepSubVoidBlackout` (5 cases) in `tests/test_lighting_moments_v2.py`: Utopia b192 resolves blackout 8 (2 bars) and b384 blackout 4 (1 bar) from real-cache-shaped series; the Caramelle-style deep-sub-but-growl-ringing swell stays balloon; a shallow melodic drop (no deep run) stays balloon; and the Part H true-silence rung still wins ahead of the new rung. These prove the rung ordering and the two-band discriminator in software only — not that the blackouts read correctly in the room, which is the operator gate. AWR-185 (deep-sub-void rung yields to the true-stop rung) adds `test_vocal_stop_yields_to_stop_rung` in the same `TestDeepSubVoidBlackout`: an ambiguous vocal-stop shape (deep sub void + dark growl band but the full band still audible) resolves via the calibrated 8-beat STOP length instead of the deep-void rung's run-length rounding, proving the precedence guard in software only. AWR-189 (continuous-look sustained-divergence BPM re-anchor) adds `Awr189ReanchorTests` (8 cases) in `tests/test_beat_sync_engine.py`: the heartbeat shape (spawn at a stale 120 while the grid runs 160 → phase lands back on the true grid within the 3 s sustain window and keeps tracking), sub-delta wobble is byte-identical born math with no re-anchor, a flap-back in-band resets the divergence timer, a re-anchor preserves `local_t`/bucket/progress (nothing restarts), both knobs are params-overridable (`reanchor_bpm_delta` wide ⇒ never fires; `reanchor_sustain_s` 0.5 ⇒ fires fast), a second sustained divergence converges again against the new rate, wrap and manual fire reset the divergence state, and retrigger/overlap paths never carry a re-anchor. These prove the divergence gate and phase re-base in software only — not that the heartbeat visibly locks in the room, which is the operator's acceptance look at next play. AWR-187 (firework redesign) rewrites `DropFireworkExplosionTests` in `tests/test_govee_frame_renderer.py` to the new `drop_firework_explosion_2` spec: strobe registration + hz/duty/color_b C5 allowlist; the explosion phase strobing multi-hue (lit frames drawn only from the four palette tints, >=2 distinct hues per flash, dark frames exactly on the Hz gate's OFF windows); quick dim to the much lower default hold ((64,60,55) from beat 0.55 on, no strobe outside the explosion window); the aggressive-ember contrast gate re-measured the AWR-161 way (400 frames at 40 fps post-dim, >=60/255 bar — measured 200/255 at defaults); the `_ember_env` fast-in/exp-out shape (peak at 15% of life, monotone exponential decay, sine path byte-unchanged for v1); the AWR-153 time-based-embers pin kept; and a v1-stays-registered/not-a-strobe pin holding the pre-apply live config valid until the executive gate (retire with v1). `tests/test_apply_firework_redesign.py` (4 cases) proves `tools/apply_firework_redesign.py` flips exactly the one firework look and nothing else, is idempotent, refuses (exit 3, nothing written) without `safety.allow_strobe`, and backs up once + applies atomically via the CLI. `tests/test_led_color_engine_m2_patch_d.py`'s live-config firework tripwire row becomes a two-approved-states pin (pre-apply v1 / post-apply redesign; any third state still red) — collapse after the gate. These prove the render math, registration discipline, and staging script in software only — not that the strobing explosion or aggressive embers read correctly in the room, which is the operator's next mix after the executive gate applies the live config flip. AWR-188 (palette-cycling comet, Part G) adds `tests/test_partg_palette_comet.py` (15 cases): `palette_comet` registration in `SLOT_EFFECTS`/`REALTIME_EFFECT_NAMES` + not-a-strobe + C5 allowlist (with `slot_colors` deliberately NOT allowlisted), same-seed determinism through the public `render()` (frame_index-independent), a 3/5/6-slot palette-length sweep proving the cycle covers exactly `min(n, 5)` slots, slot-5 white-reserve discipline under a full 6-slot dressing, fail-bright-white with no injected palette, seeded palette start-offset variation, legacy `loop_beats` pacing without `travel_per_beat`, example-config pair wiring (`rt_drop_palette_comet` → `rt_post_drop_palette_comet`, `color_source engine`), the apply-script's embedded look defs byte-matching the example config, and `tools/apply_partg_palette_comet.py` behavior (add-if-missing staging, idempotence, operator-tuned-look preservation, refuse-before-write on a pre-Round-A config, end-to-end main() on the example config with one timestamped backup and no rewrite on the second run). The four SLOT_EFFECTS registry guards (`m2_phase1`/`m2_phase2a`/`m2_patch_e1`/`m2_patch_e2`) were extended for the reviewed registration (16→17). These prove the render math, registration, and staging-script logic in software only — not that the palette comet reads correctly in the room, which is the executive apply after Round A plus the operator's next mix. AWR-199 (deep-sub-void pickup abort, day-0 interim guard) adds to `tests/test_lighting_moments_v2.py`: `test_pickup_ended_dip_releases_early` (the SOL2 repro shape — void ends at D-4, 3 audible pickup beats → `abort_at` at the first returned beat, reason suffix + `growl_tail` observability field), `test_two_beat_pickup_stays_dark` and `test_lone_pickup_transient_stays_dark` (the operator-verdicted gap-2 / lone-transient shapes keep `abort_at` None), `test_void_into_drop_no_abort` (void runs into the drop → nothing returns), `test_kill_switch_restores_none` (`RBSS_F2_VOID_PICKUP_ABORT=0` restores today's exact decision), `test_utopia_pin_fixtures_hold` (the frozen AWR-184 b192/b384 pins re-pinned from MEASURED real-cache window values — both keep abort None), and `test_deep_sub_void_pickup_abort_releases` in `TestTransitionRelease` (a real rung-0b decision carrying the abort feeds `transition_release_for` = `drop − abort_at`). These prove the >=3-beat release boundary and consumer wiring in software only — zero library engagements today (prophylactic guard); no bridge/hardware validation. |
| Replay/session tooling | replay format and smoke tests | software-only |
| Frontend tools | syntax and smoke tests | does not prove live safety |
| Docs/agent workflow | docs metadata, agent contract, drift, and staleness checkers | docs-only validation |

AWR-197 adds `tests/test_speed_size_law.py`:
`test_example_config_carries_the_speed_law`, `test_example_config_has_no_dead_pairs`,
`test_apply_is_idempotent`, `test_apply_never_clobbers_existing`, and
`test_apply_aborts_on_missing_look`. The patch_b `test_tracked_config_validates` also pins the
approved explicit `loop_beats` literal. These are config/tool software checks only.

AWR-200 adds `tests/test_spectral_ear_benchmark.py` (32 tests) for the Stage-1 EAR benchmark
harness `tools/spectral_ear_benchmark.py` (read-only offline tooling; no runtime behavior). It
proves, on small synthetic fixtures with no real cache/DB/planner: meta and amendment rows are
not primary examples; exclusions are explicit and cited (scripted/unusable_grid/variable_bpm/
marker_blocked), the manifest counts them, and an undeclared EXCLUDED row is flagged; grouped
leave-one-lineage-out folds never split a lineage — the real fold invariant (no entry id and no
resolved amendment lineage in both train and test, including the hard case of an amendment with
no content_id and a different track string) replaces the old tautological assertion; amendment
grouping follows the `amends` parent link, and missing/cyclic/ambiguous parent links — plus a
duplicated amendment own-id that would else corrupt a primary's lineage — warn loudly instead
of silently splitting/merging; `call_planner` is the single planner boundary (positive
allowlist + `assert_no_leak`) and rejects any forbidden label/locator field OR unexpected field;
the accuracy axes (tier/family/darkness/growl/laser) stay UNAVAILABLE — never zero, never PASS —
and the marker axis is AVAILABLE only when a marker is actually SCORED AND at least one
comparable ±1/±2 perturbation exists (a resolved track that scores zero markers, OR scores
markers whose every ±1/±2 offset falls out of range or collides so both flip rates come back
None, reads UNAVAILABLE — not a hollow AVAILABLE on track or baseline-decision count); marker-
sensitivity flip counting is correct against a synthetic planner seam, the seam receives only
model inputs, a marker with no comparable perturbation at a radius is dropped from that radius's
denominator (per-radius `comparable_pm1`/`comparable_pm2` counts), and unresolved tracks never
reach the planner; same-title/no-content_id identity collisions surface a deterministic
warning/limitation (identity is not guessed — curation work); and the report is byte-
deterministic with the core run PARTIAL. These prove the harness's honesty guarantees in
software only; they do not run the real planner, cache, or Rekordbox DB.

AWR-203 adds `tests/test_hardness_v0.py` (28 tests) for the offline intrinsic-hardness shadow
descriptor `hardness_v0.py` and its read-only evaluator `tools/hardness_ablation.py`. It proves,
on duck-typed synthetics plus one real `SpectralFeaturesV4` fixture (no cache/DB/ANLZ): the B/A/R/N
term math and clip01 bounds against the frozen anchors; first-8/following-8 per-term averaging and
short/end-of-track window clamping (always ≥1 beat, no empty slice); deterministic reducer
selection with the documented tie-break (constant-series ties pick offset 0; the `_select_offset`
rank indices for center/median/q75/max); the three-path math and winning-path diagnostics
(`repeated_wall` uses only the per-track baseline, so it is offset-invariant); the per-term track
median and the `MIN_STABLE_DROPS` stability flag; the marker-shift range bracketing H; that
malformed/empty/out-of-range/None-baseline inputs, and a non-finite (NaN, +inf which else
clip01-saturates to a false T3, −inf) or unshaped/non-numeric required series, all return no result,
while an unknown reducer raises (never a phantom T3); determinism (same inputs → identical frozen
result); and the AST-based
zero-runtime-importer invariant, with a companion test proving the guard catches multiline-paren,
`importlib.import_module`, and `__import__` forms a line-anchored regex would miss. Read-only
offline code — `hardness_v0.py` does no I/O and has zero runtime importers; the evaluator opens the
Rekordbox DB + v4 cache READ-ONLY only. Not run in these tests: the real corpus, cache, or DB.

AWR-204 adds `tests/test_approach_features_v0.py` (27 tests) for the offline raw approach-descriptor
layer `approach_features_v0.py`. On duck-typed `SpectralFeaturesV4` synthetics (no cache/DB/ANLZ) it
proves: rising/falling/held approach trajectories read out in `slope` + half-split `delta` sign; a
ringing melodic layer over a cut sub is summarized independently (no min-masking); depth reads the
approach FLOOR (p10) minus the reference's TYPICAL level (p50), so a broad collapse and a single-band
filter separate without a count-threshold; separate first-8 vs following-8 landed windows; the
track-wide baseline plus the across-`genuine_drops` first-landing reference (no drops → None,
empty drops → an explicit zero reference); the track-referenced void run curve and the
`longest_run_below` primitive where a non-finite beat breaks the run; the ±2 marker-offset bundles
(a length window slides, an explicit-start window moves only its end, offset 0 equals the primary
window, `descriptor_range` collapses to a point on a flat track); and the fail-safe honesty —
boundary clamps reporting requested vs available, a short window insufficient with no slope, a
window with enough beats but no finite data (all-non-finite, or a single finite sample) insufficient
with a reason distinct from the too-few-beats case (finite coverage gates `sufficient`, not just
beat count), a missing series `present=False` with all-None stats, non-finite filtered and counted, top-level
availability requiring at least one finite approach descriptor (all-missing/all-non-finite →
`available=False` with an honest reason, per-series partial availability retained), an empty track
unavailable (not an exception), inconsistent caller inputs raising `ValueError`, byte-identical
determinism, and the AST+raw-text zero-runtime-importer invariant. The module is pure and does no
I/O; **it decides nothing** — no class, threshold, darkness length, or live authority, and missing
data can never fabricate a darkness event. Not run in these tests: the real corpus, cache, or DB.

## Required documentation update

When adding or changing tests, update:

- `docs/status/validation_matrix.md`
- `docs/subsystems/tests.md`

## SoundSwitch Offline Decode And Export Tasks 1–2

`tests/test_soundswitch_project_decoder.py` covers frozen source-model use and strict, read-only decoding: physical document bounds/trailers, venue/static-look parsing, canonical identity and stable inventory gates, learned MIDI/control reconciliation, catalog/script classification, malformed and unsupported-source rejection, render-vs-catalog-tail semantics, and at least one render-bearing cue. When the canonical local project is available, the current-corpus test also verifies decoded classifications.

`tests/test_soundswitch_pack.py` covers deterministic export, independent verification, dynamic saved-project inventory reconciliation, proof-only strict snapshot rejection, byte-identical repeat export, atomic publish, source sidecar ignored-path derivation/sanitization, source/inventory/hash/canonicalization/semantic mutation rejection, the seven-class F-3 crosswalk, loader-superset runtime metadata rejections, report-only import diagnostics, active/inactive parity-lane scoping, and export threading of scripted/Autoloop/Static Look parity registries. `tests/test_soundswitch_project_decoder.py` covers typed truncated-catalog rejection. `tests/test_prove_soundswitch_pack_generation.py` covers the proof-gate seams, including F9, F10, and structural Static Look frame validation without pinning operator recolours. AWR-179 D4-F3 adds `test_canonical_publish_threads_single_generator_commit_read` to `tests/test_soundswitch_pack.py`: a counting `_generator_commit` side effect proves one publish reads the generator commit exactly once and threads the SAME value to both the manifest and the source sidecar.

`tests/test_shadow_soundswitch_pack.py` (Task 8 offline shadow proof) drives a synthetic verified `LaserPackPlayer` through scripted/static/blackout transitions with the physical backend forced to `none` (`tools/shadow_soundswitch_pack.py`), recording ONLY frame SHA-256 hashes and comparing each against an independently hand-computed expected frame. It proves stop/blackout/emergency/reload-wait resolve to a zero frame, that a held Static Override stands alone over a cleared base, twice-run hash determinism, report sanitization (no raw frames/paths/identities), backend-`none` enforcement (a frame sender is rejected), slots 8/16/17/24 plus a controlled slot-7 create/edit, and that the removed non-functional `--project` option is rejected. Pure explicit-`phase_tick` autoloop rendering is covered by `tests/test_soundswitch_laser_player.py`; only runtime beat-to-phase shadow coverage remains reported `deferred_t7d_phase_origin`. Software/offline only — no hardware claim.

This is software validation only. Separate focused suites cover the immutable
pack loader/player, native Autoloop resolver, MIDI adapter, backend abstraction,
Enttec framing/sender, pack-player config, startup matrix, atomic controller,
runtime commands/status, StateManager driver, and menubar. Native Autoloop tests
cover note-to-Autoloop binding/display names, 600 ticks/beat phase, latching,
same-look refire and role re-anchor, missing binding/file/layout, all-zero dark
looks, post-drop fallback and mapped post-drop behavior,
scripted/static/SoundSwitch-present precedence, reload stale clearing, and the
single submit path. MIDI/startup tests cover static-controller auto-bind, alias
override, missing/ambiguous controller degradation, and output-bus exclusion.
RW-5 tests fail on backend/provider re-query,
published-dict mutation/reuse, incorrect precedence or simultaneous truths,
unsafe lifecycle snapshots, raw render/submit errors, 200 Hz loop error death,
missing throttle sleeps, duplicate ZERO submits after `_push_tick()` inner failures,
process-control exception swallowing, blackout self-release drift, stale active UI, export phase races,
reload-command drift, missed one-shot auto-enable retry, or
private-data leaks. The tests use fake/
injected hardware seams. They do not prove Enttec/fixture behavior.

The 2026-07-02 parity-finalization fixes add: idle manual-overlay driver tests
(`PackDriverIdleManualOverlayTests`) proving static press/release and blackout
stay operator-controlled at `active_deck` 0 with truthful status/truth-intent;
a playing-scrub latch test (`PackDriverScrubLatchTests`) proving a waveform
drag holds the automatic base dark and resumes after settling; playing-sibling
load-guard tests (`PlayingSiblingLoadGuardTests`) proving an idle-sibling
`TRACK_LOADED`/`ANLZ_PATH` cannot clobber a playing deck while owner loads and
fail-open cases still pass (all in `tests/test_state_manager_pack_driver.py`);
and selection-beat anchor tests in `tests/test_native_autoloop_resolver.py`
(mid-grid trigger anchors phase 0 at the selection beat, negative-beat clamp,
plus the corrected latch/non-32-cycle expectations).

Art-Net truth-check tests add `tests/test_artnet_truth.py`,
`tests/test_artnet_compare.py`, startup coverage in
`tests/test_soundswitch_pack_startup.py`, and connected-shadow coverage in
`tests/test_state_manager_pack_driver.py`. `python3 tools/artnet_compare.py
--self-check` is the non-network validator measurement test; it uses synthetic
traces only. The comparator now fails closed on stale/missing/unmatched sidecar
rows, sequence wrap, unmatched sidecar frames, and U1 packets missing sidecar
evidence. It allows denser U1 streams only through ordered nearest-neighbor
matches, and extra U1 rows never satisfy coverage. In live streaming mode it
reconciles only a settled prefix — deferring the newest frames and tolerating
the sidecar (written before send) leading received U1 — so a denser/leading
stream is pending rather than a setup error, while a genuine byte mismatch on a
settled frame still fails. Its coverage ledger includes
normalized scripted timeline events/rapid pairs, matched Autoloop
visible/authored-dark phase buckets based on each loop's cycle, static and
blackout overlay/release combinations, and active-deck/mode transition
directions.

Parity evidence tests add `tests/test_build_parity_fixture.py`,
`tests/test_soundswitch_parity_oracle.py`,
`tests/test_soundswitch_scripted_parity.py`, and `tests/test_static_looks.py`.
They cover ordered capture joins, scripted divergence ledgers, Autoloop sample
classification, zero-seeded Autoloop-cycle replay, static unavailable-window
fixture generation, registry hash freshness, same-layout generalization,
active/inactive lane summaries, and static non-generic assertion fallback.
`tests/test_witness_auto_retire.py` covers edited-witness evidence retirement,
including doc-sha retirement, identical-sha regression pinning, synthetic
publish fallback to `algorithm_generalized`, and unchanged-source publish
blocking through `UnverifiedParityPublishError`.
These are passive capture/software
oracle tests only; remaining active `unverified_parity` documents block trusted
publication.
- relevant subsystem card
- relevant task playbook if test workflow changed

Hardware behavior still needs manual validation logs.

## Docs / Agent Workflow

`tests/test_docs_orphan_check.py` covers active-doc classification matching for
`tools/check_agent_contracts.py`. `tests/test_check_docs_staleness.py` covers
`tools/check_docs_staleness.py` contract parsing, recursive glob expansion,
contract-globbed tooling under `tools/`, literal/star glob behavior, and the
`docs/data/*.yaml` implementation-data exception.

## Rekordbox Track-Load Stability Gate (AWR-160)

- `tests/test_rb_state_reader.py` (`TickEventTests`) covers the phantom
  track-load stability gate in `_tick_deck`: a churning browse storm (a new
  title every tick, sub-`_LOAD_STABLE_TICKS` churn) emits zero TRACK_LOADED/
  ANLZ_PATH events and logs a throttled DEBUG phantom-load-suppressed line
  plus an edge-triggered INFO phantom-storm summary; a stable new track
  emits exactly one ANLZ_PATH+TRACK_LOADED pair, ANLZ_PATH first, after
  `_LOAD_STABLE_TICKS = 3` identical reads; a track that loads and is never
  played still emits (the FEIN case — stability alone gates, not playing/
  position); a title that changes again before stabilizing lets only the
  later title emit; unload after a stable load, and reloading the same
  title afterward, behave as before the gate; deck 1 and deck 2 gate
  symmetrically; a stable load never re-emits on later unchanged ticks; and
  a transient ANLZ read failure during the stability window does not block
  title confirmation, with a late-resolving ANLZ path still catching up on
  its own once the title is already confirmed. Pure seams via the existing
  fake mach-read backend — no mach, no live process.

## Rekordbox Mixer Active-Deck Authority

The active-deck authority implementation is covered by focused software tests:

- `tests/test_rb_offsets.py` covers named optional mixer offset parsing, exact
  labels, duplicate/malformed/partial required label fail-closed behavior, and
  unknown/anonymous trailing line rejection for authority.
- `tests/test_rb_state_reader.py` covers finite range-checked mixer f32 reads,
  valid endpoints, concrete invalid reasons, direct-master refresh and
  invalidation, raw Deck C/D no-aliasing, transport-unavailable fail-closed
  pause, immutable mixer snapshots, and default resolver-support event emission.
- `tests/test_active_deck_resolver.py` covers fader eligibility, top-fader
  dominance, LOW/BASS dominance and tie cases, rb-master tie/fallback,
  neutral-labeled LOW/BASS tie behavior, Deck 1/2-only candidate filtering,
  invalid/stale mixer fallback, recovery, no-audible idle behavior, and
  stability/no-flicker policy.
- `tests/test_state_manager_active_deck_authority.py` covers StateManager
  integration, `rb_master_deck` separation, MASTER/OSC/mirror/resume bypass
  gates, invalid-to-valid recovery, invalid/stale master handling, lost
  transport fail-closed behavior, immutable snapshot ownership, and deck-0
  idle clear safety.
- `tests/test_main_mixer_authority_wiring.py` covers startup default-on mixer
  authority, raw Deck A/B direct seed, raw Deck C/D fallback/no-aliasing, and
  required `RBStateReader.authoritative_kinds` when old direct flags are
  disabled.
- `tests/test_runtime_status.py` covers show-deck versus Rekordbox-master
  heartbeat/status separation, stale-master suppression, and mixer authority
  visibility.

This is software validation only. It does not validate live Rekordbox behavior,
loaded-track play/stop survival, SoundSwitch, laser, LED/Govee, DMX, MIDI,
Enttec, or hardware-visible output.

## CFX Filter-Sweep LED Overlay (AWR-173)

The CFX FILTER tracking read and the LED filter-sweep overlay are covered by
pure software tests (mach/live/socket-free):

- `tests/test_rb_offsets.py` covers the CFX 7.2.11 chain group (exact chains),
  the other-versions-are-None inertness, and CFX/mixer group independence in both
  directions (a malformed CFX group never disables a healthy mixer group and vice
  versa), plus anonymous-trailing-line rejection with CFX present.
- `tests/test_rb_state_reader.py::CfxTickTests` covers valid CFX readings, the
  `wrong_effect` / `unit_channel_mismatch` / `non_finite` / `out_of_range` /
  `unreadable` reasons, per-deck independence (deck 1 valid while deck 2 is
  unreadable), `Ev.CFX_STATE` never entering `_authoritative_kinds`, and the
  **isolation pin**: broken CFX chains + healthy mixer chains leave
  `MixerAuthoritySnapshot.valid == True`.
- `tests/test_led_cfx_sweep.py` covers the pure `cfx_sweep_envelope` under the
  TRIGGER semantics (operator re-ruled at the desk 2026-07-09): counterclockwise/
  neutral produce exactly the neutral `CfxEnvState`; flood-only below the threshold
  ramps mix at `flood_ramp_ms` with dim 1.0 and stays armed, releasing at the
  deadband; crossing the bloom fires the one-shot drain exactly once (dim
  1.0→`dim_floor` over `drain_ms`, then holds); three different held knob values
  above the threshold give the same dim (knob position has no effect); a single-tick
  jump 0.4→0.95 both floods and fires; release-after-fire fades mix AND dim together
  at `release_ramp_ms` and a re-push re-triggers only after re-arm hysteresis;
  threshold jitter does not re-fire while not re-armed; dt=0 / NaN / out-of-range
  safety. Dispatch gating (feature-off, blackout, F2-darkness hold, smart-drop
  tactical blackout, v2-off, stale snapshot, invalid active-deck reading, and
  active_deck 0 each force the stored tuple inert and hard-reset the `CfxEnvState`),
  the anchor provider (freewheel always neutral, fresh tuple attached, a tuple older
  than 0.5 s neutralized), the frame-engine child overlay (`_parse_cfx_rgb`, wire
  round-trip, frozen-child skew defaults, `scale(lerp(px, rgb, mix), dim)` parity,
  runner permitted-path applies vs emergency-path emits no overlay frame), and the
  config loader (absent/malformed disabled; range validation rejects
  `bloom_threshold_norm <= 0.5 + engage_deadband`, out-of-range values, and
  `drain_ms <= 0`; unknown keys such as the removed `rearm_hysteresis` are ignored).

This is software validation only. The direction mapping (`param0 > 0.5` =
clockwise) and the bloom threshold + ramps are pending the operator's desk
calibration (Part F of the AWR-173 spec); no bridge restart, process-memory
sampling, or hardware-visible output was performed.

## LED Phrase-Aware Active-Content Hold

`tests/test_led_state_manager.py` covers the StateManager-only LED hold that is
armed by nonzero active-deck switches and active-deck track loads. The focused
tests cover immediate release within `0.5` and `1.0` beats of the incoming
phrase entry, hold at `1.1` beats until the next phrase marker, same-active-deck
track replacement, missing-phrase-data release at the 16-beat backstop,
8-second release when no beat is readable, inactive-deck load exclusion,
idle/stop cleanup, hold stamp cleanup, SmartPhrasing reset-reason change
logging, automation-only `perf.led.look` beat/phrase enrichment, and no
director/adapter or laser/SoundSwitch calls during the hold return.

This is software validation only. It does not prove Govee device behavior or
the room-visible absence of a mid-phrase pop.

## LED Idle/Pause Ambient

`tests/test_led_state_manager.py` covers no-audible idle entry dispatching one
ambient decision from the last audible deck, accepted realtime ambient decisions
starting a synthetic 120 BPM idle beat anchor, blackout clearing that anchor,
and playing automation returning to the normal realtime beat branch.
`tests/test_govee_realtime_runner.py` covers idle-grace teardown sending
`blackout()` before `deactivate()`.

This is software validation only. It does not prove the Govee firmware fallback
explanation or the room-visible pause behavior.

## SOL2 LED/Beat Launch-Blocker Fixes (AWR-201)

- `tests/test_govee_realtime_runner.py`: `test_recovered_feed_clears_idle_grace`
  and `test_idle_grace_still_fires_when_feed_stays_bad` cover recovered versus
  continuously bad beat feeds.
- `tests/test_beat_sync_engine.py`: `test_reanchor_preserves_whole_beat_age`,
  `test_feed_gap_resets_divergence_timer`, `test_zero_bpm_sample_clears_divergence`,
  and `test_paused_animate_clears_divergence` cover continuity and continuous
  evidence hygiene.
- `tests/test_led_look_director.py`:
  `test_shuffle_bag_rebuilds_when_preference_subset_changes`,
  `test_shuffle_bag_cycle_intact_for_stable_subset`, and
  `test_preference_terms_narrow_independently` cover family/tier pool changes,
  stable shuffle cycles, and ordered independently fail-open narrowing.
- `tests/test_lighting_moments_v2_f4.py`:
  `test_empty_f2_f4_intersection_commits_inside_f2_cell` covers the policy-to-
  director path when euphoric-bright and F2 routing pools do not overlap.

The five scoped suites pass 268/268. Full discovery runs 4142 tests with the
nine named pre-existing failures recorded in AWR-201 and no new SOL2 failure.
This is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Govee Health Reporting

`tests/test_govee_runtime_sender.py` covers mirror target failure and recovery
as edge-triggered log transitions, keeps the sender's primary return value
unchanged, and asserts `mirror_send_ok` in sender status. `tests/test_govee_scene_adapter.py`
covers a three-failure circuit-breaker trip followed by a successful emergency
send clearing `degraded_reason="circuit_open"` and returning status to
non-degraded when no other fault exists.

This is software validation only. It does not prove cloud API behavior,
physical strip behavior, or room-visible output.

## M2.5 LED slot-color workstream test files

| File | Covers | Added in |
|---|---|---|
| tests/test_led_color_engine_m2_phase1.py | Phase 2a/b engine cues, renderer byte-identity, resolve_slot_colors | Phase 1 |
| tests/test_led_color_engine_m2_patch_b.py | rt_groove_chase slotization | Patch B |
| tests/test_led_color_engine_m2_patch_c.py | rt_post_drop_chase slotization | Patch C |
| tests/test_led_color_engine_m2_patch_d.py | rt_drop_chase, rt_drop_center_burst slotization | Patch D |
| tests/test_led_color_engine_m2_patch_e1.py | rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula slot fns plus rt_drop_nebula pairing | Patch E1 |
| tests/test_led_color_engine_m2_patch_e2.py | rt_post_drop_center_comet slot fn, rt_drop_center_burst pairing, legacy center-comet regression, solid slot-color selection for slot cues | Patch E2 |
| tests/test_led_color_engine_m2_patch_e3.py | rt_twinkle slot fn, generic ambient config, legacy twinkle_blue regression, solid slot-color selection for rt_twinkle | Patch E3 |
| tests/test_led_color_engine_m2_patch_s.py | random_with_mono_chance mono hit/miss behavior, chance 0 equality with random_with_replacement, determinism, stepping, fade tail, journey RNG isolation, allowlist regression | Patch S |
| tests/test_led_color_engine_m2_patch_f.py | Patch F default-bank cleanup, legacy_color_suffix storage bank, scene_ref registration, generic drop pairing, no static slot_colors params, solid reachability through default generics | Patch F |
| tests/test_color_engine_config.py, tests/test_led_color_engine.py, tests/test_govee_frame_renderer.py, tests/test_led_pad_service.py | Locked Palette config/engine/pad playback plus Phase 3 renderer param default parity and changed-value coverage | LED Pad Phase 3 |
| tests/test_led_identity_v2.py, tests/test_led_color_engine.py, tests/test_color_engine_config.py, tests/test_led_palette_control.py, tests/test_runtime_status.py, tests/test_soundswitch_midi_input.py, tests/test_streamdeck_midi.py, tests/test_led_state_manager.py, tests/test_bridge_menubar.py | LIGHTING ENGINE v2 F1 identity helpers/store, v1/v2 engine behavior (incl. v2-off byte-identity + flip-back journey-state golden, abs-beat bloom/palate-reset windows, moments_blocked gating, scripted stand-down), config gates, Stream Deck zone/manual/max-energy control, runtime commands, MIDI bindings, deck layout, identity-event consumer (stale load_gen drop, provisional-to-measured upgrade, writer submit), real-worker v4 cache-hit path, max-energy mutate-only consume, and the temporary menubar engine toggle | AWR-128 F1 incl. Part F fix round |

All M2.5 slot cue, strategy, Locked Palette, and renderer-param tests: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Runtime Status Heartbeat

`tests/test_runtime_status.py` covers the status JSON `heartbeat` payload, the throttled `[BEAT]`
log line and immediate repeat suppression, show-deck versus Rekordbox-master separation,
StateManager-published color-engine status, fail-soft provider behavior, and throttling for
repeated provider-failure warnings. This is software-only observability coverage and does not
validate SoundSwitch, laser, LED, Govee, or Rekordbox hardware behavior.

## Logging Visibility (AWR-125 overhaul)

The retired `logging_manager.py` control-file/env-var-maze pipeline and its
`tests/test_logging_diag_coverage.py` suite are gone, replaced by the one-JSONL-stream design
(`bridge_log.py`) and its `bridge-view` curses viewer (`bridge_view.py`):

- `tests/test_bridge_log.py` (45 tests) covers `build_record()` field order/optional-key
  omission/contextvar pickup/exc formatting, drop-on-full queue behavior, the writer thread's JSONL
  output and stderr WARNING+ mirror, `_redact()` secret masking, `resolve_log_dir()`/`prune_runs()`,
  `event_scope()`/`stamp_trace()` semantics, `TraceQueue` callback passthrough, and idempotent
  `init()`/`shutdown()` header/footer records.
- `tests/test_bridge_view.py` (96 tests) covers the pure viewer layer: `parse_record` (tolerant of
  truncated/malformed lines), `lens_of` (all four lens predicates, including the legacy-infra
  DEBUG-record-routes-to-DEBUG-only case), `format_line`/truncation, `format_age`, filter
  parsing/matching, and `LatchState` latch/clear/ack semantics.
- `tests/test_logging_surface.py` (7 tests, replaces `test_logging_diag_coverage.py`) covers
  errors-always-visible regardless of logger level, `BRIDGE_LOG_LEVELS` parsing, and `BRIDGE_DEBUG`
  behavior against `bridge_log`.
- `tests/test_bridge_log_integration.py` (9 tests) proves a real subprocess init→emit→shutdown round
  trip, with real JSONL read back through the viewer's lens layer.
- `tests/test_bridge_fmt_rate.py` continues to cover `log_changed()`/`log_throttled()` spam-control
  primitives, including a threaded independent-key throttle check.

The new `perf.*`/`health.*` emit sites added one assertion each to the tests already owning that
behavior, rather than to the logging test files above: `tests/test_laser_director.py` (`perf.laser.
scene`, `perf.laser.personality`, `perf.override`), `tests/test_laser_executor.py`
(`perf.laser.fired`), `tests/test_led_color_engine.py` (`perf.led.palette`),
`tests/test_led_state_manager.py` (`perf.led.look`, `perf.override`),
`tests/test_state_manager_active_deck_authority.py` (`perf.deck`), `tests/test_smart_transitions.py`
(`perf.drop`), `tests/test_autoloop_controller.py` / `tests/test_live_bpm_service.py`
(`perf.autoloop`), `tests/test_live_bpm_service.py` / `tests/test_smart_phrasing_integration.py` /
`tests/test_sound_switch_engine.py` (`perf.ss`), `tests/test_sound_switch_engine.py`
(`perf.scripted`, `health.os2l`, `health.queue`), `tests/test_runtime_status.py`
(`perf.heartbeat`), `tests/test_midi_output.py` (`health.midi`), `tests/test_enttec_dmx_pro.py`
(`health.dmx`), `tests/test_govee_scene_adapter.py` (`health.govee.cloud`),
`tests/test_govee_realtime_runner.py` (`health.govee.rt`), `tests/test_rb_state_reader.py`
(`health.rb`, `health.queue`), `tests/test_rb_memory_skip_objc.py` (`health.rb`,
`health.reader`), and `tests/test_state_manager_pack_driver.py` (`health.tick`).
`tests/test_enttec_dmx_pro.py` / `tests/test_midi_output.py` / `tests/test_govee_realtime_runner.py`
also cover `bridge_log.thread_guard()` wrapping those backends' worker-thread run loops.

This is software-only observability coverage: it proves the log pipeline, the viewer's read-side
lens/latch logic, and the watcher's monitor-window launch, and does not validate physical lighting
outputs.
