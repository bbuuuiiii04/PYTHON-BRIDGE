---
doc_status: current
truth_level: code-verified
last_verified_commit: b660dcb
last_verified_date: 2026-07-08
validation_scope: software-only; LED Pad Phases 1-3, Template Lab Phase 2, Template Lab Round 1 (lab_update/lab_switch/lab_preview), QR same-network access, pad editor unset-param-defaults, Stream Deck palette control Package 2 plus AWR-121 gesture v2, drop presentation policy Package 3, LED idle/pause ambient fix, and LED pad queued-color restore software-tested, hardware-unvalidated
---

# LED / Govee Subsystem

Status:
- implementation: alpha/experimental by path
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: current local setup only

Purpose:
- Select LED room looks, resolve colors, coordinate cloud/realtime ownership, and send Govee-style cloud or realtime output.

Audit P1 (2026-07-03):
- The LED color-engine live-control methods remain intentionally reserved for future LED Pad and
  Stream Deck controls; callers outside `StateManager` must route through events/commands.
- The tracked LED Look Director example no longer carries an unread top-level `metadata` key.

Audit P2 (2026-07-03):
- Committed drop-look selection now passes the same color-engine `diy_eligible` predicate used by
  normal `tick()` automation, so a held smart-drop impact cannot bypass palette eligibility.

Audit P3 (2026-07-03):
- Realtime-to-cloud handoff no longer calls Govee realtime transport blackout/deactivate from the
  StateManager push-loop caller; the runner thread now performs that teardown before another frame
  is sent.

Razer keepalive + blackout backstop + dispatch retry + pad mutual exclusion (AWR-145, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Razer keepalive replaces the WI-6 cloud-suspect reconcile. A cloud DIY scene silently knocks the
  strip out of razer mode, after which realtime frames (including blackout) are ignored.
  `GoveeRealtimeRunner` now re-asserts `activate()` on demand — `request_activate_assert()` set by
  every realtime takeover and every tactical blackout in `led_dispatch_coordinator.py` — and,
  while streaming, unconditionally every `RAZER_KEEPALIVE_S = 2.0` s on the runner thread, so a
  knockout or a lost activate heals within ~2 s. `note_cloud_dispatch`, the reconcile fields, and
  `RBSS_LED_RT_RECONCILE` are gone; `status()` reports `razer_assert_count` (was `rt_reconcile_count`).
  The unused `rate_limits.rt_reconcile_window_s/interval_s` config fields remain inert in `led_models.py`.
- Any-mode brightness backstop. `GoveeRealtimeRunner.request_brightness(value)` sends a LAN JSON
  brightness command on 2 consecutive ticks (idempotent against a lost UDP packet); it darkens or
  restores the strip even while a cloud scene plays. Pure-emergency/operator teardown now sends
  `set_brightness(0)` before blackout+deactivate (fails dark). The cloud handoff path is untouched —
  cloud looks never dim. The tactical pre-drop blackout re-asserts razer but does NOT dim (a drop
  look follows within a few beats). When the operator blackout clears, the policy calls the
  coordinator's `restore_brightness()` (brightness 100), duck-typed so a cloud-only adapter no-ops.
- Latch-on-accept dispatch retry. The policy latches the role_key before the coordinator outcome is
  known, so a dispatch the coordinator rejected (e.g. the min-dwell gate) was never re-sent until
  the role_key string changed (live-observed as drop looks "not cycling"). A rejected automation or
  idle decision is now cached and re-sent with the SAME decision — no director re-tick, so cursors,
  shuffle bags, and paired post-drops do not advance — every `LED_DISPATCH_RETRY_S = 0.35` s until
  accepted, the role_key changes, or `LED_DISPATCH_RETRY_MAX = 8` attempts run out. Both retry slots
  clear at every deck switch, track load, blackout, manual override, and gate transition
  (`_led_clear_dispatch_retries`) so a stale retry never fires across a mode change.
- Pad mutual exclusion. `tools/led_pad_playback.py`: an already-running pad playback checked
  ownership only inside `play()`, so it kept streaming as a second writer once the bridge came alive
  (live-observed ghost comet + flicker). `_poll_once` now, on the same every-8th-tick cadence,
  auto-stops a playing pad that is not in a deliberate `pad_owned` takeover when a fresh bridge
  status reports `bridge_owned`; `pad_owned` and `free`/stale/absent bridge status both keep playing.

Frame engine child process (AWR-146, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- The realtime frame trio (`GoveeRealtimeRunner` → `GoveeFrameRenderer` → `GoveeRealtimeTransport`)
  now runs in a bridge-owned child process, `python3 -m rb_ss_bridge_v2.govee_frame_engine`, so the
  bridge's GIL contention (628 ms RBMEM scans, two-deck loads) can no longer starve LED frame timing.
  Measured this machine: 60.9 fps in the child vs ~28-29 decaying to ~16.5 in-bridge. No AWR-145 logic
  is rewritten — the runner moves in wholesale.
- Architecture. `__main__` builds a `GoveeFrameEngineClient` (`govee_frame_engine_client.py`) in place
  of the in-process runner; it is a drop-in from the coordinator's point of view (same duck-typed
  methods, same `stop() -> bool`). The client spawns/supervises the child (`FrameEngineHost` in
  `govee_frame_engine.py`) over an `AF_UNIX` `SOCK_STREAM` socketpair.
- IPC protocol. Newline-framed JSON (`encode_msg`/`decode_buffer`). Parent→child: `init`, `anchor`
  (explicit `null` propagates pause/unpermitted), `set_desired`, `fire_trigger`, `activate_assert`,
  `brightness`, `emergency_stop`, `force_deactivate`, `shutdown`. Child→parent: a `hb` heartbeat every
  `HEARTBEAT_S = 1.0` s carrying `achieved_fps`, `streaming`, `fps_degraded`, and the full
  `runner.status()`. Beat anchors stream at 50 Hz on the client thread; `time.monotonic()` is
  cross-process comparable on this machine so the runner's extrapolation math is unchanged. The child's
  provider reads an anchor older than `ANCHOR_STALE_S = 0.5` s as "not playing" (hung-parent guard).
- Supervision / fail-dark. The kernel closes the socketpair on ANY process death (including SIGKILL),
  so each side gets EOF — no heartbeat protocol is needed for death detection. Bridge death → child
  sees EOF → `runner.stop()` (blackout + deactivate + close, never brightness-0 so a cloud look
  survives a restart) → `os._exit`. Child death/hang (EOF, no heartbeat >5 s, or a command stuck >2 s)
  → the client kills and respawns with intent replay: a mid-look child resumes the look (set_desired +
  activate_assert), a mid-emergency child goes dark again (emergency_stop + an UNCONDITIONAL
  brightness-0, because a fresh runner is never `_active` and its teardown would send nothing). Every
  coordinator-facing client method is lock-and-flag with zero I/O on the caller's thread — the 200 Hz
  push loop and StateManager threads gain no socket/blocking I/O; all IPC, spawning, and IP
  re-resolution run on the client's own thread.
- Scheduling band + fps self-report. The child raises its macOS scheduling band on startup
  (`setpriority` clear-darwin-bg + an `NSActivity` latency-critical assertion + frame-thread
  `QOS_CLASS_USER_INTERACTIVE` via the runner's new `on_thread_start` hook); which lever actually
  defeats the faceless-process demotion is unknown, so the child self-measures `achieved_fps` every
  heartbeat instead of assuming. `engine_alive`, `achieved_fps`, `respawn_count`, and `fps_degraded`
  are exposed through the runtime status surface (`led_dispatch_policy._sanitize_led_adapter_status`).
- Operator-blackout LAN dim backstop (AWR-146 Task 6). Independent of the child move: the runner's
  `_emergency_teardown` only sends transport commands when it was active, so a pure operator blackout
  while the runner is INACTIVE (cloud look showing) never sent the LAN brightness-0 backstop. The
  policy `LED_BLACKOUT` handler now calls the coordinator's new `blackout_brightness()` →
  `request_brightness(0)` after the blackout is accepted (the unknown-target early-return does not
  dim), duck-typed so a cloud-only adapter no-ops. Tactical (pre-drop) blackout still never dims.

Audit P5 (2026-07-03):
- LED dispatch policy now lives in `led_dispatch_policy.py` as `LEDDispatchPolicyMixin`, mixed into
  `StateManager`. The `_led_*` fields remain on the `StateManager` instance, and the backend-routing
  adapter remains `led_dispatch_coordinator.py`; this is a pure code-layout/bookkeeping refactor.

Smart-drop marker collapse (2026-07-07):
- LED drop-impact gating still lives in `StateManager` through
  `led_dispatch_policy.py`, not through `drop_lifecycle.py`. It now mirrors the
  laser pure resolver: predecessor labels and real smart-drop crossings fire
  drop impacts, and the first label-only chorus-to-chorus boundary after an
  anchored section may fire one capped second drop impact. Later chorus
  boundaries settle into `post_drop`. Collapsed smart-drop markers mean the
  pre-drop blackout arms once per selected drop section instead of every
  32-beat raw ANLZ marker.

Intra-section look rotation (2026-07-07):
- Long `buildup`, `pre_drop`, `breakdown`, and monotonic `ambient` LED role
  keys now carry a 32-beat cycle term from `LED_DEFAULT_GROOVE_CYCLE_BEATS`, so
  the look director can pick a fresh look inside one long section instead of
  holding the first look until the role changes. The stable section id stays the
  drop/restore/phrase marker without the cycle suffix, so the color engine keeps
  one color journey for the section while only the room shape/pattern rotates.
  `drop`, `groove`, `post_drop`, blackout, hold, scripted, and manual-override
  semantics are unchanged. This is software-tested and hardware-unvalidated.

LED hold starvation fix (2026-07-07):
- Active-deck switches and active-deck track loads still protect against an
  instant mid-phrase LED repaint, but the hold can no longer wait forever when
  phrase data is missing or stale: it releases at the normal phrase entry first,
  then at a 16-beat backstop, or after 8 seconds if no beat is readable. Hold
  engage/release is logged as `[RGB] hold-engaged` / `[RGB] hold-released`, and
  SmartPhrasing reset transitions are logged as `[SP] reset-reason-change`.
  Accepted automation `perf.led.look` rows now include beat/phrase context.
  Root cause remains likely, not confirmed, until a live session shows whether
  freezes line up with those hold/reset log lines. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

LED idle/pause ambient fix (2026-07-07):
- No-audible idle entry now dispatches one `ambient` LED decision using the
  last audible deck's state, so a mixer-authority pause/fade-to-silence can
  land on the idle ambient look instead of returning before LED dispatch.
- Accepted realtime ambient looks now get a 120 BPM synthetic idle beat anchor
  (`[RGB] idle-freewheel-start`) so the realtime runner keeps rendering while
  playback is paused. Blackout, manual commands, and playing automation clear
  that freewheel before normal playback resumes.
- If the realtime runner still reaches idle-grace teardown, it now sends a
  blackout frame before deactivating and logs
  `[RGB] deactivate reason=idle_grace blackout_sent=1`, so the failure mode is
  dark instead of leaving a previous cloud DIY scene on the strip. The
  firmware-revert explanation remains hardware-assumed until an operator live
  pause validates the room-visible behavior. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

Realtime LED wrap-flicker guard (AWR-141, 2026-07-07):
- `TriggerClock.advance()` now treats backward beat moves smaller than
  `WRAP_HOLD_BEATS = 0.5` as live extrapolation jitter or short rolls: it holds
  the high-water beat, returns no wrap, and does not restart continuous
  realtime effects. A real loop, cue, or seek at or above the threshold still
  wraps and re-syncs. The Govee realtime runner, renderer, upstream WI-1 beat
  clamp, and config are unchanged. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

Smart-drop blackout transport + runway observability (AWR-142, 2026-07-07):
- `_dispatch_led_smart_drop_blackout` now tags each accepted pre-drop room
  blackout with which transport carried it and how much runway it had. The
  realtime accept line keeps every existing field and appends
  `transport=realtime runway_beats=<beats_to_next_drop>`; the previously silent
  cloud accept now emits `[RGB] smart-drop-blackout-accepted transport=cloud
  phase=... next_drop=... runway_beats=... role_key=... active_deck=...`.
  `runway_beats` is `sp_state.beats_to_next_drop` formatted `%.1f`, or `-` when
  unknown. This is observability only: transport selection, send order, returns,
  and the `_led_smart_drop_blackout_key` lifecycle are unchanged, so a cloud
  blackout that lands late is now distinguishable in the log from one that never
  armed. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

LED solo pre-dark hold (AWR-144, 2026-07-07):
- On a drop the room-split plan already marks a Laser Solo, the LEDs used to
  flash a bright drop look for ~0.6 s before going dark. That gap exists because
  the LED drop look keys off the chorus phrase-start anchor, which fires just
  before the smart-drop marker where drop-presentation sets the `drop_spotlight`
  LED blackout owner. `_dispatch_led_automation` now checks
  `_led_upcoming_drop_is_lasers_only()` (pending
  `_drop_presentation_last_pending[0] == LASERS_ONLY`) when the resolved role is
  `drop`; if so it holds the current look via
  `_gate_led_automation("solo_predark_hold", ...)` instead of dispatching the
  drop look, and the marker's `drop_spotlight` blackout then owns the darkness.
  This is LED-side only: solo length and the blackout itself are unchanged, the
  lasers still fire the solo, and every non-solo drop
  (`leds_only`/`leds_plus_lasers`/plan-unavailable/disabled) dispatches its drop
  look byte-identically. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

LED pad queued-color restore (AWR-137, 2026-07-07):
- AWR-134 instant realtime recolor is superseded by operator decision: color
  pad changes queue again. Manual color pad events (`red`, `green`, `blue`,
  `rainbow`, and `white_sand`) mutate color-engine state only; there is no
  realtime runner refresh path on the pad press.
- The next accepted LED automation dispatch injects the current color-engine
  state through `_led_inject_engine_colors(...)`, so the new color lands at the
  next look/role-key boundary. The AWR-132 hold fix and 32-beat look-cycle
  terms keep those boundaries bounded instead of late/never.
- Cloud DIY scenes still cannot be recolored in place because they are fixed
  scene commands without RGB params; those looks also wait for the next normal
  automation dispatch. Laser color follow remains separate and instant by
  design. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

Govee health reporting (AWR-136, 2026-07-07):
- Cloud mirror sends now report health transitions instead of failing silently:
  a mirror target logs one `[RGB] mirror-send-degraded target=... err=...`
  warning when it first fails, and one `[RGB] mirror-send-recovered target=...`
  info line when it heals. `GoveeRuntimeSender.status()` includes
  `mirror_send_ok` for the last observed mirror send outcome.
- The cloud adapter's `degraded_reason="circuit_open"` now clears after a
  successful send, matching the already self-healing `circuit_open` boolean.
  Light output, send ordering, queueing, rate limits, blackout bypass, and the
  push loop are unchanged. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

Stream Deck palette control (Package 2, 2026-07-04):
- The implemented behavior authority is `docs/architecture/palette_control_authority.md`.
- The `streamdeck_palette` change contract implements palette queue/override-fade/lock, `white_sand`,
  LED mute owner semantics, Rainbow mode, the palette feedback file, and the pinned Stream Deck
  palette/control surface. This is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED until the
  operator performs a deck-in-hand validation.
- AWR-121 updates the physical palette gesture surface: palette pad note-on/down records the press,
  note-off/up resolves tap versus long-press, tap queues or unqueues, tap on the locked active pad
  unlocks, and long-press takes the palette now via the existing override fade and then locks it.
  `long_press_s` is configurable in `color_engine.palette_control` (default 0.5 s). `lock_note`
  is now optional/back-compatible; when absent, no `palette_lock_pad` binding is built and Stream
  Deck key 6 renders dark. Runtime commands keep explicit queue/override/lock/unlock semantics.
- 2026-07-04 evening hardening pass (post-incident, authority rules 25-27; detail in the design
  spec's Part D.2): deck script exception containment + read-thread liveness + stall watchdog,
  feedback lost/restored + layout-change transition logging, latch clear on bridge restart,
  pass-through projections pinned by a producer↔deck contract test, and feedback-writer
  fail/recover transition logs in `led_palette_control.py`. Bridge-side siblings
  (F-B1/F-B3/F-B4) were implemented the same night per
  `docs/plans/active/streamdeck_bridge_side_hardening_impl_spec.md`: the MIDI input group
  survives frame-sender/Enttec failures and pack reloads, `input_degraded` stays truthful
  while pack output is disabled, the feedback payload carries `static_held`, and the deck
  renders static-look latches from that bridge truth (authority rule 28, design spec Part
  D.3). F-B2 (retry log spam) remains open in
  `docs/plans/active/streamdeck_surface_hardening_findings_2026_07_04.md`.

LIGHTING ENGINE v2 F1 identity surface (AWR-128, 2026-07-06):
- F1 adds a default-off v2 branch inside `LedColorEngine` for per-track color identity. The v1
  journey engine remains present and the live master latch (`led_engine v1|v2` or the temporary
  menubar checkbox) decides which branch renders. With v2 off, the v1 render path remains the
  compatibility path.
- `led_identity_v2.py` owns the pure identity helpers, deterministic content key/hash, zone
  assignment, dressing derivation, and the first-write-wins `IdentityStore`. The store path is
  `local/state/led_identity_v2.json` by default; malformed/corrupt store data degrades to
  read-only behavior for that boot and must not stop v1 color output.
- `StateManager` derives `Ev.LED_TRACK_IDENTITY` off the existing ANLZ/spectral worker seam, guards
  identity events by deck `load_gen`, freezes measured records into the store, and forwards only
  serial event mutations to the engine. The 200 Hz push loop does not gain file, socket, MIDI,
  network, or subprocess I/O.
- Stream Deck v2 feedback and input are additive: zone pads stage or correct zones, manual pads set
  `white_sand`/red/green/blue/rainbow, the max-energy pad only arms a future F2 hint, and static
  looks/mutes/Solo remain on the existing rows. The bridge also exposes runtime commands:
  `led_engine`, `led_manual_override`, `led_manual_clear`, `led_max_energy_toggle`, and zone names
  through `led_palette_queue` / `led_palette_override`.
- Look selection may bias toward `LEDLook.motion_style` (`sharp`/`flowing`) and `LEDLook.travel`
  (`calm`/`wide`) when v2 dressing is active. This is a filter over existing eligible looks, not a
  new effect renderer.
- Software validation covers model/config parsing, v1/v2 engine behavior, Stream Deck layout and
  command/control rails, MIDI bindings, runtime commands, and focused state-manager wiring. No
  bridge restart, live Rekordbox, SoundSwitch, laser, LED/Govee, MIDI-device, DMX, Enttec, or
  hardware-visible output validation was performed.

Drop presentation policy (Package 3, AWR-119, 2026-07-04):
- The implemented behavior authority is `docs/architecture/drop_presentation_authority.md`; the
  `drop_presentation` change contract covers it. The pure ladder/session/learned-store/window-machine
  logic lives in the new module `drop_presentation.py` (not LED-specific; laser-side base suppression
  lives in `soundswitch_laser_player.py`). The LED-side seam this card owns: pre-dark and a
  `lasers_only` solo window hold an LED blackout through the EXISTING owner set in
  `led_dispatch_policy.py` (`Ev.LED_BLACKOUT`/`Ev.LED_CLEAR_BLACKOUT`, payload `reason` = owner key
  `"drop_spotlight"`) — a set union, so it never clears a separately-held manual mute owner and is
  never touched by presentation decisions itself (suppression is not blackout). `led_palette_control.py`
  gained an optional `get_laser_solo` callback (pulled fresh on every feedback publish, mirroring the
  existing `get_laser_blackout` pattern) surfacing the Solo pad's `off`/`armed`/`active` state.
  `soundswitch_midi_input.py` gained the `laser_solo_pad` binding kind (note-on emits
  `Ev.LASER_SOLO_PAD`, note-off no-ops, same as the other three Stream Deck pad kinds), built from
  Package 2's already-reserved `laser_solo_note` config key. `enabled: false` in the new
  `/drop_presentation` config block is the master regression gate: every drop renders
  `leds_plus_lasers` exactly as today, byte-identical. AWR-135/AWR-138/AWR-139 updates LED-only
  drop windows so laser base suppression follows the real drop/post-drop role end, and only later
  true-drop impacts (runway > 0.0, or manual Solo / hot-cue override) inside an open window assert
  their own presentation and re-stamp the cap. Runway-less markers keep laser/LED look cycling but
  cannot re-roll the section's fixture split. AWR-143 (2026-07-07) gates the presentation impact in
  `_drop_presentation_tick` on `sp_state.smart_drop_crossing`
  (`impact_now = bool(impact_now and sp_state.smart_drop_crossing)`): post-AWR-140 the Laser
  Director emits `reason="drop_crossing"` for the capped 2nd-chorus LABEL re-arm without a real
  smart-drop marker, and without the gate that re-arm re-entered/extended the presentation window,
  breaking AWR-139's per-true-drop invariant. The AWR-140 drop LOOK / LED drop-impact gating is
  unchanged. The 192-beat `drop_window_cap_beats` default is only
  a stuck-role backstop. A `lasers_only` solo that re-enters mid-window skips the LED pre-dark
  countdown and fires at impact. SOFTWARE-VALIDATED
  ONLY / HARDWARE-UNVALIDATED.

Drop presentation stop fail-open (v1 foundation audit fix DD1, 2026-07-06):
- The `drop_spotlight` LED dark-hold (and laser base suppression) is now released on EVERY stop
  via `StateManager._drop_presentation_release_on_stop()`, called from `_do_stop`. Previously the
  reader-stale stop branch (`state_manager.py` FM-11) returned before `_drop_presentation_tick`
  (the only owner-clear), so a stop during a Laser-Solo / pre-dark window could latch the room dark
  (lasers stopped + LEDs gated by the still-held `drop_spotlight` owner) until the reader recovered
  and the window ended on its own — violating `drop_presentation_authority.md` §Presentation
  Mechanics ("fail-open on stop / laser-output loss mid-window; never latch a fixture dark"). The
  release reuses the WindowMachine's universal `stopped=True` fail-open + the idempotent
  `_drop_presentation_apply_actions`; it is gated on `cfg.enabled` (so `enabled: false` stays
  byte-identical), owner-scoped (a manual mute owner survives), and adds no I/O to the 200 Hz path.
  Coverage: `tests/test_state_manager_drop_presentation.py` (`StopFailOpenReleaseTests`).
  Audit + spec: `docs/plans/active/lighting_v1_foundation_audit.md`,
  `docs/plans/active/lighting_v1_foundation_fix_spec.md`. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

Authoritative code:
- `led_config.py`
- `led_models.py`
- `led_look_director.py`
- `led_color_engine.py`
- `led_identity_v2.py`
- `led_dispatch_policy.py`
- `led_dispatch_coordinator.py`
- `led_palette_control.py`
- `govee_scene_adapter.py`
- `govee_runtime_sender.py`
- `govee_realtime_runner.py`
- `govee_realtime_transport.py`
- `govee_frame_renderer.py`
- `govee_owner_state.py`
- `govee_lan_discovery.py`
- `beat_sync_engine.py`
- `state_manager.py` LED automation call sites and runtime ownership seam
- `led_pad_controls.py` LED Pad render/control catalog. `CONTROL_META[key]["default"]` mirrors
  each renderer's actual unset-param fallback in `govee_frame_renderer.py` (hand-extracted, `None`
  when no single static fallback exists); `PARAM_DEFAULT_OVERRIDES` covers the two keys
  (`travel_beats`, `width`) whose real default differs by scene_ref. See `docs/guides/led_pad.md`
  for the operator-facing summary and `tests/test_led_pad_controls.py` for the source-text pin.
- `tools/led_pad_playback.py` standalone LED Pad realtime playback shell
- `tools/led_pad_web.py` local LED Pad web service
- `tools/led_pad_lab.py` Template Lab draft registry and pad-only renderer overlay
- `tools/led_pad_assets/` vanilla LED Pad UI assets
- `tools/calibrate_identity_v2.py` read-only local spectral-cache calibration summary for v2 identity anchors
- `scripts/led_pad.py` LED Pad launcher
- `streamdeck/streamdeck_midi.py` Stream Deck palette/control renderer and MIDI sender

Key symbols:
- `StateManager`
- `LEDDispatchPolicyMixin`
- `LEDConfig`
- `LEDLookDirector`
- `LedColorEngine`
- `LedIdentityV2`
- `IdentityStore`
- `LEDDispatchCoordinator`
- `LedPaletteControl`
- `GoveeSceneAdapter`
- `GoveeRuntimeSender`
- `GoveeRealtimeRunner`
- `GoveeRealtimeTransport`
- `BeatSyncEngine`

Runtime flow:
- inputs: phrase/role state, runtime LED commands, LED config, color engine state, beat/BPM state
- decisions: manual override, blackout, role-entry look selection, color/slot-color resolution, cloud/realtime ownership, beat sync instances. LED dispatch policy is mixed into `StateManager` from `led_dispatch_policy.py`; it runs on the StateManager thread and owns no backend threads, locks, or blocking I/O.
- outputs: cloud scene commands or realtime UDP frame packets
- The live LED drop/post-drop resolver remains in `StateManager`.
  `drop_lifecycle.py` reproduces its flat-window drop-region state machine for
  laser use; `tests/test_drop_lifecycle.py` parity-checks that seam without
  routing LED output through the new module.
- Active content changes now arm a phrase-aware LED hold in `StateManager`: a nonzero active-deck switch or active-deck track replacement keeps the previously shown look if the incoming track is more than `1.0` beat into its current phrase, then releases at the next phrase crossing. If the incoming track is already within the first beat of a phrase, it changes immediately. Missing phrase segments are bounded by the same hold's 16-beat / 8-second backstop; this is software-tested only and still needs operator visual sign-off.

Config:
- `config/led_look_director.example.json`
- local ignored `config/led_look_director.json`
- env secrets such as `GOVEE_API_KEY`
- realtime enable flag if present in startup
- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` are optional objects; values must be `gradient_even`, `random_with_replacement`, or `random_with_mono_chance`.
- `color_engine.slot_mono_chance_by_look` is an optional object mapping look names to numeric probabilities in `[0, 1]`; it defaults to `{}` and only affects looks using `random_with_mono_chance`.
- `color_engine.locked_palette_by_look` is an optional object mapping look names to existing palette names. Locked looks resolve color and slot-color injection from that palette's full p-interval and white value without changing the color-engine journey palette, dwell, focus, or RNG state.
- `color_engine.v2` is optional and default-off. When present and valid it defines v2 zone ramps,
  bass normalization anchors, the local identity store path, soft-flip, palate-reset, bloom, and
  motion/travel thresholds. The current tracked example/default `bass_norm` anchors are
  `0.5856`/`0.9688`, produced by `python3 tools/calibrate_identity_v2.py` over 666 valid local v4
  cache entries on 2026-07-06. Invalid v2 config disables only v2; the v1 color engine can still
  load.
- `color_engine.palette_control.zone_notes`, `manual_notes`, and `max_energy_note` are emitted only
  when valid v2 config is enabled. They must not collide with existing v1 palette/control notes.
- `LEDLook.motion_style` and `LEDLook.travel` are optional per-look hints consumed only by the v2
  look-selection bias.
- `LedColorEngine.resolve_slot_colors()` returns exactly six slot colors for slot effects; caller `slot_count` is ignored and slot index 5 is reserved as pure white.
- Solid palette slots remain possible for every slot cue: a point/mono palette can collapse slots 0-4 to one RGB while slot 5 remains pure white, and `random_with_mono_chance` can opt individual looks into probabilistic solid slots 0-4 without changing the white slot.
- Patch F collapses the tracked example `default` bank onto generic engine-colored slot looks and moves legacy color-suffix realtime looks into the storage-only `legacy_color_suffix` bank. `LEDLookDirector` still selects only `banks.default`, so the legacy bank preserves definitions without runtime rotation.
- `safety.scripted_mode_automation` remains the master switch for scripted-track LED automation. The shipped example config sets it `true` (paired with the conservative blackout `scripted_mode` policy); set it to `false` to keep LEDs inert during scripted tracks. The code-level `LEDSafety` dataclass default stays `false`, but the loader requires the JSON key. When it is true and `StateManager` is in `lighting_mode == "scripted"`, automatic LED dispatch may proceed through the `scripted_mode` role-remap policy.
- The top-level LED `scripted_mode` block defines `default_role` plus `role_map` for scripted-track automation. If the block is absent, groove, drop, and post-drop map to the `utility` blackout bank; buildup/pre-drop map to `buildup`, and breakdown maps to `breakdown`. `utility` is allowed only as a destination, and partial maps fall back to `default_role`.
- LED Pad persists its edit draft in `config/led_look_director.draft.json` and commits only after the full draft passes `load_led_look_director_config_from_dict()`. In the UI this draft commit is labeled **Apply** (2026-07-03 visual reskin; the `/api/commit` route name is unchanged, and the reskin — design tokens plus a vendored Archivo font in `tools/led_pad_assets/` — changes no runtime behavior). The pad-only Drafts bank lives in root `_pad_meta.drafts`, so those looks are automation-invisible unless moved into `banks.default`.
- LED Pad Locked Palette writes through `color_engine.locked_palette_by_look`; playback of a locked look ignores the session Test Palette. Renderer param unlocks are frame-identical when omitted: `loop_beats` on `rt_groove_chase`/`rt_groove_nebula`; `travel_beats` + `width` on `rt_drop_chase`, `rt_post_drop_chase`, `rt_drop_nebula`, and `rt_post_drop_nebula`; `travel_beats` on `groove_center_chase` and `post_drop_firework_chase`.
- Template Lab persists draft metadata under gitignored `config/led_lab/drafts.json` and loads gitignored `config/led_lab/effects_lab.py` only inside the pad process. Lab scenes play as `lab_<name>` through `LabRenderer`; bridge runtime modules never import lab code, and production renderer registries are not mutated by lab playback.
- Template Lab Round 1 adds three endpoints on `LedPadService` (`tools/led_pad_web.py`): `lab_update` re-applies params to the already-playing lab draft via the shared `PadPlayback.update()` path (no takeover, no `CueTimer`/`SyntheticClock` restart) and only applies when that exact draft is playing; `lab_switch` seamlessly reconfigures the shared playback slot from one already-playing lab draft to another (same `update()` path, beat keeps running) and refuses when nothing is playing or a pad look is playing; `lab_preview` renders frames offline through a fresh local `LabRenderer` (`render_preview_frames` in `tools/led_pad_lab.py`) and never touches `self._playback`, ownership, or the live renderer's effects. All three reuse `_lab_play_spec`'s reload-and-fail-dark behavior for a broken sandbox module. No code-level strobe rail was added (discipline-only, per operator decision).
- LED Pad exposes `GET /api/access` (shared with Laser Pad via `tools/pad_access.py`), which reports the pad's current bind address/loopback state and, when non-loopback, a best-effort LAN URL for a QR "Open on another device" affordance. It never changes bind behavior itself; exposing the pad to the LAN stays an explicit `--host` operator action.
- `/drop_presentation` top-level block (sibling of `color_engine`, `targets`, `banks`) — `enabled`,
  `laser_ratio`, `opening_tracks`, `led_predark_beats`, `drop_window_cap_beats`, `hotcue_marker`,
  `solo_learn_threshold`, `gearshift_bpm_jump`, `record_min_drops`, `ws_handoff_enabled` (parsed but
  the ritual tier stays unimplemented and logs a not-implemented notice if ever enabled). Loaded via
  `led_config.load_drop_presentation_config()`, independent of the main config's validate/build
  pipeline so an unrelated `looks`/`banks` error never blocks the presentation policy or hot-cue
  tags. `color_engine.palette_control.laser_solo_note` (already reserved by Package 2) now builds a
  real `laser_solo_pad` MIDI binding row.

Tests:
- inspect `tests/` for LED color engine, Govee realtime runner, frame renderer, state manager LED integration, and config tests
- slot-color coverage lives in `tests/test_led_color_engine.py`, `tests/test_led_color_engine_m2_phase1.py`, `tests/test_led_color_engine_m2_patch_b.py`, `tests/test_led_color_engine_m2_patch_c.py`, `tests/test_led_color_engine_m2_patch_d.py`, `tests/test_led_color_engine_m2_patch_e1.py`, `tests/test_led_color_engine_m2_patch_e2.py`, `tests/test_led_color_engine_m2_patch_e3.py`, `tests/test_led_color_engine_m2_patch_s.py`, `tests/test_led_color_engine_m2_patch_f.py`, and config validation coverage in `tests/test_color_engine_config.py`
- scripted-mode LED policy coverage lives in `tests/test_led_config.py` and `tests/test_led_state_manager.py`, including blackout mapping for groove/drop/post-drop; this is software validation only and does not prove room-visible Govee behavior during scripted SoundSwitch tracks.
- intra-section rotation coverage lives in `tests/test_led_state_manager.py` and
  `tests/test_led_color_engine_integration.py`: role-key cycle math for long
  buildup/pre-drop/breakdown/monotonic ambient sections, legacy ambient
  behavior with phrase monotonic off, unchanged drop/groove/post_drop key
  strings, stable section/cycle publication, and a dispatch-path second look
  across a buildup cycle boundary. This is software validation only.
- phrase-aware active-content hold coverage lives in `tests/test_led_state_manager.py`, including active deck switch, active-deck track load, the inclusive `1.0` beat release boundary, hold-until-next-marker behavior, missing-phrase-data release by 16-beat backstop, 8-second no-beat fallback, hold stamp cleanup, SmartPhrasing reset-reason change logging, `perf.led.look` beat/phrase enrichment for automation only, inactive-deck load exclusion, idle/stop cleanup, and laser/SoundSwitch path confinement. This is software validation only.
- idle/pause ambient coverage lives in `tests/test_led_state_manager.py` and
  `tests/test_govee_realtime_runner.py`: no-audible idle entry dispatches one
  ambient decision from the last audible deck, accepted realtime ambient
  decisions freewheel a synthetic beat anchor, blackout/playing automation
  clear the freewheel, and idle-grace teardown blackouts before deactivate.
  This is software validation only.
- Govee health reporting coverage lives in `tests/test_govee_runtime_sender.py`
  and `tests/test_govee_scene_adapter.py`: mirror target failure/recovery logs
  emit only on transitions while primary return semantics stay unchanged, and
  a successful send clears a previously latched `circuit_open` degraded reason.
  This is software validation only.
- LED pad queued-color restore coverage lives in `tests/test_led_state_manager.py`:
  a manual color pad event updates the color engine without sending another
  realtime runner `set_desired`, and the next automation dispatch with a new
  role key carries the updated engine color. This is software validation only.
- shared flat-window lifecycle parity coverage lives in `tests/test_drop_lifecycle.py`; live LED per-look duration rewriting and backend latency offsets remain separate by design.
- LED Pad Phase 1/3 coverage lives in `tests/test_led_pad_controls.py`, `tests/test_led_pad_playback.py`, and `tests/test_led_pad_service.py`. It validates metadata coverage, synthetic playback clock/ownership/strobe gates, draft mutation, commit blocking, color injection, Locked Palette playback, ownership-required replies, and one HTTP smoke path. Template Lab Phase 2 coverage lives in `tests/test_led_pad_lab.py` and validates registry persistence, name-collision rejection, hot reload, broken-module errors, lab rendering, and shared playback-slot preemption. Template Lab Round 1 coverage (same file) validates `render_preview_frames` determinism/frame-count clamping, `lab_preview` (frames returned, unknown draft/unregistered fn raise `ValueError`, broken module returns structured failure, zero playback side effects), `lab_update` (applies only when the exact draft is playing, payload params overlay saved params, live code-swap reflects in the live `LabRenderer`), and `lab_switch` (seamless swap between lab drafts, refusal when nothing or a pad look is playing, unknown draft raises). It uses fakes or dry-run paths only. Phase 3 color-engine and renderer regressions live in `tests/test_led_color_engine.py`, `tests/test_color_engine_config.py`, and `tests/test_govee_frame_renderer.py`.
- Stream Deck palette control Package 2 coverage lives in `tests/test_led_palette_control.py`,
  `tests/test_streamdeck_midi.py`, `tests/test_soundswitch_midi_input.py`,
  `tests/test_runtime_status.py`, and the existing LED color-engine/config suites. It validates
  queue/override/lock rail behavior, AWR-121 tap/long-press gesture behavior, LED mute owner
  release, feedback writer/thread behavior, pinned deck layout composition, MIDI pad event
  bindings, and runtime command parsing without hardware.
- LIGHTING ENGINE v2 F1 coverage lives in `tests/test_led_identity_v2.py`,
  `tests/test_led_color_engine.py`, `tests/test_color_engine_config.py`,
  `tests/test_led_palette_control.py`, `tests/test_soundswitch_midi_input.py`,
  `tests/test_streamdeck_midi.py`, `tests/test_runtime_status.py`, and focused StateManager LED
  tests. It is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
- The shared `tools/pad_access.py` LAN-access payload (used by both pads' `GET /api/access`) is covered by `tests/test_pad_access.py` (pure-function, loopback/specific-IP/`0.0.0.0` detection cases), plus one HTTP smoke test each in `tests/test_led_pad_service.py` and `tests/test_laser_pad_web.py`.
- Drop presentation policy Package 3 coverage lives in `tests/test_drop_presentation.py` (pure
  planner/ladder/session/learned-store/window-machine logic; the authority doc's Required Behavior
  Tests 1-9 verbatim plus additional coverage), `tests/test_state_manager_drop_presentation.py`
  (state_manager wiring integration: plan build, per-tick ladder/window, LED blackout owner
  `"drop_spotlight"` engage/release, Solo pad arm/disarm/veto/learn via real event dispatch, darkness
  guard, damper, the `enabled: false` byte-identity regression gate), `tests/test_led_config.py`
  (the `/drop_presentation` loader), `tests/test_led_palette_control.py` (the `get_laser_solo`
  feedback callback), and `tests/test_soundswitch_midi_input.py` (the `laser_solo_pad` binding kind).
- broad command: `python -m unittest discover tests`

Change contract:
- If changing look policy, inspect director, models, config validation, `led_dispatch_policy.py`, and StateManager dispatch call sites.
- If changing active-content timing or LED role gating in `StateManager`, keep the hot path non-blocking and update `tests/test_led_state_manager.py`.
- If changing realtime output, inspect runner, transport, renderer, owner state, and beat sync engine.
- If changing realtime/cloud ownership handoff, keep socket I/O on the runner/transport thread and
  cover foreign-thread `force_deactivate()` behavior in `tests/test_govee_realtime_runner.py`.
- If changing cloud output, inspect scene adapter and runtime sender.
- If changing the shared drop resolver, prove parity against the existing StateManager LED resolver and do not assume that pure-resolver parity changes live LED output.
- If changing LED Pad, follow the `led_pad` contract in `docs/agents/change_contracts.yml` and update `docs/guides/led_pad.md`, this card, `docs/architecture/doc_index.md`, and `docs/status/active_work_registry.md`.
- If changing LIGHTING ENGINE v2 identity behavior, follow the `led_govee` and
  `streamdeck_palette` contracts in `docs/agents/change_contracts.yml`; keep v1-off behavior
  byte-compatible, keep store writes off the push loop, and update this card, runtime command docs,
  palette authority/design docs, status matrices, validation inventory, and AWR-128.
- If changing drop presentation, inspect `docs/architecture/drop_presentation_authority.md` first (the acceptance oracle), then `drop_presentation.py` and its `state_manager.py` wiring. Follow the `drop_presentation` change contract in `docs/agents/change_contracts.yml`; the master regression gate (`enabled: false` byte-identical) must stay green.
- Update this card, feature matrix, validation matrix, active work registry, and config docs.

M2.5 slot cues in SLOT_EFFECTS (govee_frame_renderer.py):

| Scene ref | Fn | Safety class | Strobe | Status |
|---|---|---|---|---|
| groove_center_chase | _slot_groove_center_chase | groove | no | software-validated |
| groove_center_burst_retract | _slot_groove_center_burst_retract | groove | no | software-validated |
| post_drop_firework_chase | _slot_post_drop_firework_chase | post_drop | yes (slot 5) | software-validated |
| breakdown_full_breathing | _slot_breakdown_full_breathing | breakdown | no | software-validated |
| breakdown_star_twinkle | _slot_breakdown_star_twinkle | breakdown | no | software-validated |
| rt_groove_chase | _slot_groove_chase | groove | no | software-validated |
| rt_groove_nebula | _slot_groove_nebula | groove | no | software-validated (Patch E1) |
| rt_post_drop_chase | _slot_post_drop_chase | post_drop | yes | software-validated |
| rt_post_drop_nebula | _slot_post_drop_nebula | post_drop | yes | software-validated (Patch E1) |
| rt_drop_chase | _slot_drop_chase | drop | yes | software-validated |
| rt_drop_nebula | _slot_drop_nebula | drop | yes | software-validated (Patch E1) |
| rt_drop_center_burst | _slot_drop_center_burst | drop | no | software-validated |
| rt_post_drop_center_comet | _slot_post_drop_center_comet | post_drop | yes | software-validated (Patch E2) |
| rt_twinkle | _slot_twinkle | ambient | no | software-validated (Patch E3) |

Patch E pairings:
- rt_drop_nebula pairs explicitly to rt_post_drop_nebula through `drop_pairs`.
- rt_drop_center_burst pairs explicitly to rt_post_drop_center_comet through `drop_pairs`.

All slot cues, `random_with_mono_chance`, and Patch F bank cleanup: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
Phase 3 renderer params: `rt_groove_chase`/`rt_groove_nebula` accept `loop_beats`; `rt_drop_chase`/`rt_post_drop_chase`/`rt_drop_nebula`/`rt_post_drop_nebula` accept `travel_beats` and `width`; `groove_center_chase`/`post_drop_firework_chase` accept `travel_beats`. Missing params preserve previous frames.
The stable-hue sparkle (rt_drop_chase), center-burst 0-2/2-4 accent band split (rt_drop_center_burst), Patch E1 looks (rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula), Patch E2 center-comet (rt_post_drop_center_comet), Patch E3 ambient twinkle (rt_twinkle), Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation still need operator hardware visual sign-off.

Known risks:
- API/cloud rate limits
- realtime protocol/device specificity
- confusing local H612D behavior with all Govee devices
- beat-synced motion smoothness issues
- config schema drift
- un-analyzed tracks with no phrase segments can still hold the previous LED look after an active content change, but only until the 16-beat / 8-second backstop; live visual comfort is still hardware-unvalidated
