---
doc_status: current-incomplete
truth_level: code-and-config-grounded
last_verified_commit: 889b068
last_verified_date: 2026-07-10
validation_scope: software-validated only, except the Govee/LED color-engine, realtime-comet, and beat-sync paths (AWR-101–104) which carry operator hardware sign-off on Home Govee (2026-06-29); SoundSwitch / laser / Enttec remain hardware-unvalidated
---

# Hardware Validation Log

Current repo-facing hardware validation status:

> **HARDWARE-UNVALIDATED**

Audit P1 (2026-07-03): no hardware, SoundSwitch app, Rekordbox, laser, LED, Govee, MIDI, DMX, or
Enttec validation was performed. The changes are software-tested cleanup and command-status truth
only.

AWR-235 (2026-07-14): idle-ambient freewheel latch restore is software-tested only;
no bridge restart, Govee, or room-visible hardware action was performed for this fix.

Audit P2 (2026-07-03): no hardware, SoundSwitch app, Rekordbox, laser, LED, Govee, MIDI, DMX, or
Enttec validation was performed. Injector gating, pack-status overlay diagnostics, and committed
LED drop eligibility are software-tested only.

Audit P3 (2026-07-03): no hardware, SoundSwitch app, Rekordbox, laser, LED, Govee, MIDI, DMX, or
Enttec validation was performed. Govee handoff threading, ANLZ read-failure recovery, raw elapsed
OS2L sends, and startup spectral-cache eviction are software-tested only.

Audit P4 (2026-07-03): no hardware, SoundSwitch app, Rekordbox, laser, LED, Govee, MIDI, DMX, or
Enttec validation was performed. Laser MIDI send-error recovery, executor bank-gate restore,
scene config validation, Laser Pad live-toggle command append, blackout-mask refcounting,
`canon_alias` dedupe, and `pre_drop_scene` deprecation tolerance are software-tested only.

Audit P5 (2026-07-03): no hardware, SoundSwitch app, Rekordbox, laser, LED, Govee, MIDI, DMX, or
Enttec validation was performed. LED dispatch bookkeeping centralization and the
`led_dispatch_policy.py` mixin extraction are software-tested only.

LED white-knob round 1 (AWR-152, 2026-07-08): no hardware, Govee, or room-visible validation was
performed. The per-zone `slot5_white` tint, the all-6-slot palate-reset dim, the deleted
`_blend_white` blend, the v2 DIY-tag-filter removal, the breakdown-twinkle slot range, and the
example-config bank/palette changes are software-tested only. The live, gitignored
`config/led_look_director.json` was not touched or mirrored; the operator's config mirror +
menubar restart + next mix is the remaining validation gate.

LED pad blackout unlatch fix (AWR-154, 2026-07-08): no hardware, Govee, or room-visible validation
was performed; the code fix and its tests are software-only. This defect was caught live during an
operator mix (a pad-owned blackout claim was unremovable) and the fix's actual effect on the
currently-running latched-dark process cannot be validated without a bridge restart, which was
explicitly out of scope for this pass. `led_dispatch_policy.py`'s owner-set discard logic was not
touched — only the reason now reaches it.

LED bare-clear fail-open (AWR-155, 2026-07-08): no hardware, Govee, or room-visible validation was
performed; the code fix and its tests are software-only. Landed the same evening as AWR-154, with
the bridge live and already restarted once for that round. `led_dispatch_policy.py`'s owner-set
logic WAS touched this time (the no-reason branch now clears the whole set instead of discarding
only `legacy`) but the change's actual effect on a running process cannot be validated without a
further restart, which was explicitly out of scope for this pass — no restart, live-config edit, or
strip-touching action was performed.

LED round 2: strobe-gate rebuild + accepted-look promotion (AWR-156, 2026-07-08): no hardware,
Govee, or room-visible validation was performed. The Hz-based strobe gate, the 7 colorway strobes,
the 3 promoted looks, the knob #4 mashup removal, the knob #9 widths, the bank recast + rename, and
the Task 9 slot-5 narrowing are all software-tested only. The live, gitignored
`config/led_look_director.json` was not touched or mirrored; the operator's config mirror + menubar
restart + next mix is the remaining validation gate.

Darkness-fix round: blank-role hold + reader freshness (AWR-157, 2026-07-08): no hardware, Govee,
or room-visible validation was performed. The `blank_role_hold` dispatch guard, its Q-A
instrumentation, the deck-2 chain-freshness gate, the conditional ObjC fallback re-engage, and the
Q-B pause-vs-freeze instrumentation are all software-tested only. Unlike AWR-154/155/156, the
bridge was DOWN for this entire round — implemented overnight against the executive-released spec
with no running process to affect. NO bridge start, NO live-config edit, and nothing touching the
strip was performed at any point. The live, gitignored `config/led_look_director.json` was not
touched or mirrored; the tracked example gains `blank_role_hold: true`. The operator's next
menubar start (the first start since this round landed) plus his next mix are the remaining
validation gate — both for whether a blank-role blackout still recurs and for whether the deck-2
fallback actually re-engages on a real freeze.

LED round 3: Hz-gate migration + rainbow/firework promotions + center-burst fix (AWR-161,
2026-07-09): no hardware, Govee, or room-visible validation was performed. The ten migrated
strobe gates, the `rainbow_ordered` and `drop_firework_explosion` promotions (the latter passed its
software contrast gate at 101/255, not a room-visible check), and the center-burst pixel fix are all
software-tested only. The bridge was DOWN for the entire round (operator-sanctioned overnight
delegate lane, parallel Track C) — no bridge start, no live-config edit, and nothing touching the
strip was performed at any point. The live, gitignored `config/led_look_director.json` was not
touched or mirrored; the tracked example gains `hz`/`duty` on 18 effect names plus the two new
looks (`rt_rainbow_drop`/`rt_rainbow_post_drop`, `rt_drop_firework_explosion`). The operator's config
mirror + menubar restart + next mix are the remaining validation gate — whether the migrated strobes
read the same at any BPM, whether the rainbow pair and firework explosion look right in the room, and
whether the center-burst gap is actually gone on the physical 60-segment strip.

Firework remnants sparse-tail rebuild (AWR-215, 2026-07-11): no hardware, Govee, or room-visible
validation was performed. Software dry renders prove the old full-strip background is gone, peak
lit coverage stays at or below 20% across the sampled 60-segment window, frames flicker, and the
sparkle tail ends at beat 8. The ignored live config, running bridge, and strip were untouched.
Healthy room behavior still requires an operator audition: sparse palette sparks should follow the
impact without filling the room or hiding SoundSwitch/laser strobe contrast.

The current exporter/importer evidence boundary is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The pinned SoundSwitch 2.10.3 project/pack tooling, immutable loader/player,
MIDI-input adapter, output backends, Enttec sender, default-off config/startup,
StateManager scripted driver, runtime controller, and copied RW-5 status have
software validation only. The passive SoundSwitch U0 parity fixtures and static
assertion fallback are software/wire evidence only; they do not validate Enttec
delivery or physical fixture output, and remaining active `unverified_parity`
documents still block trusted direct-DMX publication. Current ignored-config/runtime/device state was not
inspected during RW-5 implementation. Owner-driven Enttec stop sends zero, but process
death/`kill -9` can leave the last frame latched; a physical kill path and
explicit hardware gate remain mandatory.

The reusable procedure is `soundswitch_hardware_validation_procedure.md`; copy
`soundswitch_hardware_runs/TEMPLATE.md` for a real operator run. These documents are not evidence
that a run occurred.

My local setup may be operational, but this repo does not yet contain repeatable hardware-validation records sufficient to claim hardware support.

## Required entry template

```text
Date:
Commit:
Operator:
OS version:
Rekordbox version:
SoundSwitch version:
Lighting hardware:
Config files used, with secrets redacted:
Test steps:
Observed results:
Pass/fail:
Caveats:
Rollback notes:
```

## Tracking table

| Date | Area | Hardware/software | Version/config | Test performed | Result | Evidence path | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pending | SoundSwitch | pending | pending | reviewed procedure/template available | pending | pending | no repeatable repo evidence yet |
| pending | Enttec exporter/player backend | pending | software/startup/status lane implemented; current live config not inspected | zero preflight, one scripted track, controls/masks, emergency physical kill, known-dark reset, graceful closeout | pending | pending | process death is not accepted as a hard kill; no operator run occurred |
| pending | Laser MIDI | pending | lifecycle default-on; local ignored config | gated drop impact, capped second chorus hit, later post-drop demotion, 32-beat hold, post-drop/drop fallback cycling, shuffle-bag order, blackout release, and kill switch | pending | pending | lifecycle is software-tested only; verify no drop leak during groove/buildup and no dark initial hit before any hardware-validated claim |
| pending | Laser Audit P4 resilience | pending | current Laser Director config; live MIDI port not inspected | transient MIDI send-error reopen, high-impact bank skip, missing-scene restore, Laser Pad master toggle live command, blackout-mask refcounting | pending | pending | software-tested only; no bridge restart, live MIDI, laser hardware, SoundSwitch, Rekordbox, LED/Govee, DMX, or Enttec action occurred |
| pending | Laser color menu/follow-LED (CH8/CH9) | pending | `config/laser_color_map.json` enabled, `fixed_ch9: 90`, per-mood menus; CH3/CH4 stay authored | per-mood color follows LED wander, brightness floor keeps laser no dimmer than LEDs, drops fire chase, white early-return → white, CH9=90 chase speed; verify the chase CH8 values (172/68/100/164/72) render correctly with CH3/CH4 left authored | pending | pending | software-tested only (`tests/test_laser_color_engine.py` Part D, 10 cases); no bridge restart, live output, or hardware action occurred. Chase CH8 values need a supervised live eyeball because CH3/CH4 are deliberately not driven |
| 2026-06-29 | Govee/LED color/comet/beat-sync (AWR-101–104) | Home Govee (hardware) | bridge HEAD 2026-06-29; live LED config (gitignored) | operator ran the rig and observed M2.5 slot cues (Patch E1/E2/E3), color-engine core (decoupled color/drift/drop-snap), realtime comet (stutter/smoothness/pause), and beat-sync against spec | PASS — operator visual sign-off | this log entry | visual sign-off, not instrumented capture; code-milestone re-audit for AWR-102/103/104 not separately performed |
| pending | Govee/LED remaining (AWR-105/106) | pending | pending | scripted groove/drop/post-drop blackout policy (AWR-105); Patch S solid-color outcomes + Patch F default-bank rotation (AWR-106); Patch D stable-hue sparkle; center-burst 0-2 / 2-4 accent band split | pending | pending | software-tested only; need operator visual sign-off. The AWR-101–104 paths were signed off 2026-06-29 (row above). |
| pending | LED Pad Phase 3 Locked Palette + renderer param unlocks (AWR-113) | pending | pending | Locked Palette playback, locked-palette visual output, and renderer param unlock visual behavior for groove/drop/post-drop slot cues | pending | pending | software-tested only; no live Govee output or visual hardware validation performed |
| pending | LIGHTING ENGINE v2 F1 identity + correction surface (AWR-128) | pending | current v2 example config is default-off; live ignored config not inspected | v2 engine latch, first-play neutral/provisional behavior, measured identity arrival, zone correction, manual white/red/green/blue, Rainbow manual, max-energy arm/consume/log, v1 rollback, and no unwanted changes to mutes/Solo/static looks | pending | pending | software-tested only; no bridge restart, Stream Deck hardware, live Rekordbox, SoundSwitch, laser, LED/Govee, MIDI, DMX, Enttec, or room-visible validation performed |
| pending | Govee/LED phrase-aware active-content hold | pending | current StateManager LED automation; live LED config not inspected | active deck switch and active-deck track load landing more than `1.0` beat into phrase should keep the previous look until the incoming track reaches a phrase entry; missing phrase data should release by 16 beats / 8 seconds; landing within `1.0` beat should change immediately; `[RGB] hold-engaged` / `[RGB] hold-released` and `[SP] reset-reason-change` should explain or rule out freeze windows | pending | pending | software-tested only; needs operator visual sign-off that mid-phrase switch/load no longer pops and that phrase-less holds no longer freeze for long stretches |
| pending | Govee/LED idle-pause ambient (AWR-133) | pending | current StateManager LED automation and Govee realtime path; live LED config not inspected | pausing or fading both decks to no-audible idle should dispatch the ambient look; realtime ambient should stay alive through `[RGB] idle-freewheel-start`; if idle-grace teardown occurs, `[RGB] deactivate reason=idle_grace blackout_sent=1` should precede a dark strip instead of a leftover bright DIY scene | pending | pending | software-tested only; no bridge restart, live Govee output, or visual hardware validation performed. Firmware fallback remains hardware-assumed until an operator pause validates the room-visible result |
| pending | Govee/LED health reporting (AWR-136) | pending | current Govee cloud sender/adapter; live LED config not inspected | If a configured mirror strip stops accepting frames, one `[RGB] mirror-send-degraded ...` warning should appear and recovery should produce one `[RGB] mirror-send-recovered ...` info line; after a cloud circuit-breaker blip, a later successful send should leave LED status non-degraded unless another fault exists | pending | pending | software-tested only (`tests/test_govee_runtime_sender.py`, `tests/test_govee_scene_adapter.py`); no bridge restart, live Govee output, or visual hardware validation performed |
| pending | LED round 2: strobe-gate rebuild + accepted-look promotion (AWR-156) | pending | `govee_frame_renderer.py`/`govee_realtime_runner.py` at `e28ce6c`; example config only, live LED config not mirrored | after the operator mirrors the example config's new looks/widths/bank-recast/rename and restarts: the white drop strobe should flash at a steady dialed rate at any BPM with no hold/stutter; the 7 colorway strobes should join the drop rotation at their dialed rates/colors (`strobe_red_white` side B white unless vetoed); the balloon buildup, palette heartbeat groove, and firework remnants should read as real looks in their roles; comets should render as one solid palette color per spawn, no rainbow-smear; drop/post-drop comets should look fatter (width 4), grooves slightly fatter (width 2.5, veto-able); the two sparkle chases should read in the post-drop slot under their new names; firework bursts should read pure white, nebula comets should read the zone-tinted white | pending | pending | software-tested only (`tests/test_govee_frame_renderer.py`, `tests/test_govee_realtime_runner.py`, `tests/test_led_config.py`, `tests/test_led_pad_controls.py`); no bridge restart, live-config edit, or strip-touching action was performed while implementing this |
| pending | LED round 3: Hz-gate migration + rainbow/firework promotions + center-burst fix (AWR-161) | pending | `govee_frame_renderer.py` at `abd3e0c`; example config only, live LED config not mirrored | after the operator mirrors the example config's new looks and hz/duty knobs and restarts: the ten migrated strobes should flash at their dialed rate steadily at any BPM (same feel as before at the current BPM, since defaults match the accepted feel); the rainbow drop look should sweep an ordered spectrum with the beat-locked fast travel, the rainbow post-drop look should keep its slower legacy pace; the firework explosion should show a bright hit resolving down to a warm background with visible amber/white sparks (not stuck full-bright/invisible-sparks like the pre-fix lab defect); the center-burst pulse should light every pixel across the strip with no every-other-pixel gap | pending | pending | software-tested only (`tests/test_govee_frame_renderer.py`, `tests/test_led_color_engine_m2_patch_d.py`); no bridge restart, live-config edit, or strip-touching action was performed while implementing this |
| pending | Firework remnants sparse-tail rebuild (AWR-215) | pending | tracked renderer/example only; ignored live config unchanged | audition `rt_post_drop_firework_remnants`: sparse palette sparks for the first 8 beats, no initial explosion, no full-room wash, and no masking of SoundSwitch or laser strobes | pending | pending | software-tested only (`tests/test_govee_frame_renderer.py`, `tests/test_led_config.py`, `tests/test_led_pad_controls.py`); no bridge restart, live-config edit, packet send, or strip-touching action performed |
| pending | Enttec port auto-detect + USB stick pack carriage (AWR-186 executive-gate fix) | software-only | `enttec_dmx_pro.find_enttec_port` + `packaging/make_stick.sh` at HEAD 7397792 + gate-fix; no Enttec/DMX device attached, no stick mounted | positive-identity detection (rejects a lone generic FTDI VID 0x0403 / bare `usbserial` name, returns a device only on ENTTEC descriptor strings, ambiguous on two Enttecs, metadata-only — no port opened); `make_stick.sh` aborts on a malformed pack config or a non-readable non-empty `pack_path` | pending | `tests/test_enttec_dmx_pro.py`, `tests/test_make_stick.py` | software-tested only; NO serial/DMX/Enttec device opened, NO stick write, NO bridge restart — no hardware action performed |

## Validation records

```text
Date: 2026-06-29
Commit: docs change in the adb5511 cleanup series
Operator: Brandon
OS version: macOS (Darwin 24.3.0)
Rekordbox version: 7.2.11
SoundSwitch version: n/a — Govee/LED path, SoundSwitch not involved
Lighting hardware: Home Govee strip(s), LAN / realtime path
Config files used, with secrets redacted: live LED look-director + color-engine config (gitignored; Govee key in govee.env)
Test steps: ran the bridge live on the home rig and observed the four LED workstreams during normal play — M2.5 slot cues (Patch E1 nebula, E2 center-comet, E3 ambient twinkle), color-engine core (decoupled color, drift, drop-snap), realtime comet (stutter / smoothness / pause), beat-sync runtime
Observed results: all four behaved per spec on hardware
Pass/fail: PASS
Caveats: operator visual sign-off, not an instrumented capture; covers AWR-101–104 only. AWR-105 (role mapping) and AWR-106 (solid-color + Patch F) were NOT signed off and remain hardware-pending. Code-level milestone audit for AWR-102/103/104 was not separately performed; sign-off is on observed running behavior.
Rollback notes: docs-only record; no runtime/config change.
```

## Claim rule

Do not change support/status docs from hardware-unvalidated to hardware-validated unless this file contains a repeatable validation record and the supporting evidence is committed or explicitly referenced.
