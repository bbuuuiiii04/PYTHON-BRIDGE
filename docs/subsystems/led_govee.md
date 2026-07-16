---
doc_status: current
truth_level: code-verified
last_verified_commit: 103ecbe
last_verified_date: 2026-07-15
validation_scope: software-only; existing LED/Govee behavior plus the 2026-07-13 split-local-UUID classifier correction reverified: local Rekordbox 7 loads regain the early phrase worker, real `/Volumes` loads keep the resolved-time-only rule; AWR-241 Template Lab beat meter status field documented; AWR-242 Template Lab UX (`target_role` + lab-route UI) documented; AWR-243 Template Lab functional fixes (live test_palette for lab play + ownership payload on request errors) documented; AWR-245 Template Lab Strip|Room preview hookup (pad serves sim view + profile read-only; fail-soft; preview-only) documented; AWR-247 Template Lab preview length (default full cue_beats) documented; AWR-248 Pad|Lab|Sim cross-nav documented; AWR-254 pad look-editor close dirty check documented; AWR-255 pad+lab stale-config banner (config mtime vs bridge process start; no bridge runtime change) documented; AWR-256 remnants ember_hold/decay wired (dim_beats removed as dead); AWR-258 data-integrity (lab lock+CAS, pad locked_palette, sim stale-mtime/bak/profile_error block); AWR-259 pad integrity tail (stale_look CAS, Discard-all copy, persisted last_applied, EDITOR_FIELDS); AWR-271 R9a Lab-in-Pad shell mount documented; AWR-272 R9b Save-draft/Accept verb pair documented; no LED rendering/output hardware validation
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

Speed/size law (AWR-197, 2026-07-10; staged, software-tested, hardware-unvalidated): realtime
groove, breakdown, drop, and post-drop looks carry explicit beat-speed parameters by musical role,
with big drop looks paired to smaller post-drop echoes. The law's terms live in
`tools/apply_speed_size_law.py` `SPEED_PARAMS`; the tracked example config carries them, and the
idempotent live-config apply sets only missing values so it never overwrites operator tuning.

Firework remnants rebuild (AWR-215, 2026-07-11; staged, software-tested, hardware-unvalidated):
- `rt_post_drop_firework_remnants` no longer draws the old slot-5 full-strip wash or its separate
  sine-envelope ember system. It reuses the sparse drop-chase sparkle intro (palette sparks whose
  density falls across the intro curve). The drop-chase comet half is excluded.
- AWR-256 (2026-07-15): the AWR-215 rewrite had hard-coded `cue_beat >= 8` and ignored
  `ember_hold_beats` / `ember_decay_beats` while the pad still showed those knobs. Hold is now
  `clamp(ember_hold_beats, 1..32)` default 8; sparkle runs while `cue_beat < hold` (hold window
  maps onto the classic 8-beat density curve so default stay byte-identical). Optional
  `ember_decay_beats` (default 0 = hard cut, clamp 0..8) linearly fades intensities until
  `hold+decay`, then empty. Dead `dim_beats` removed from this scene's allowlist and pad catalog
  (drop-chase never consumed it). Strobe-gate-held-open behavior unchanged.
- The drop-chase synchronized Hz gate is held open for this tail. That keeps low-coverage per-pixel
  flicker without classifying the effect as a whole-field strobe; `allow_strobe: false` remains.
- At the physical-room shape of 60 segments, the dry-render test samples 480 frames and caps peak
  simultaneous lit coverage at 20%; it also pins zero slot-5 background, changing frames, exact
  drop-chase-intro parity at default hold, and the hold/decay cutoff. The tracked example keeps
  empty params (defaults apply).
- Bank membership and the `rt_drop_firework_explosion` pairing are unchanged because the temporary
  unbank/repoint stopgap never landed. Room-visible acceptance remains an operator audition gate
  (after a bridge restart so live `ember_hold_beats` is loaded).

Firework redesign (AWR-187, 2026-07-09; implemented, software-tested, hardware-unvalidated):
- Operator visual spec (verbatim acceptance): "the firework background explosion should strobe with
  sparkling hues and then when the firework explosion background quickly dims, the embers continue
  to aggressively spark." New frame effect `drop_firework_explosion_2` replaces the AWR-161 v1 read
  ("white flash → relax → slow sparkle"): the explosion window (2×`surge_beats`, default 0.25) is a
  multi-hue field strobed by `_hz_strobe_on` (hz/duty dialable; hues re-dealt per pixel each flash
  from the injected palette tints — `color_a`/`color_b` arrive via the engine multi inject with
  `color_source: engine`, `spark_a`/`spark_b` join the pool), then the background quick-dims to a
  much lower `bg_hold` (default 0.25, floor 0.0; v1 held 0.7/floor 0.2) and the ember field sparks
  aggressively over it (`_ember_env` fast-in/exp-out, `sparkle_life_s` 0.15, `sparkle_density` 0.5,
  blend-replace keeps embers full-intensity; embers stay time-based per AWR-153). Registered as a
  STROBE (`REALTIME_STROBE_EFFECTS` + hz/duty/color_b in the C5 allowlist), so the look needs
  `allow_strobe: true` + `safety.allow_strobe: true`. Measured post-dim ember contrast at defaults:
  200/255 against the AWR-161 ≥60 bar, same measurement. v1 `drop_firework_explosion` stays
  registered (non-strobe) so the pre-apply live config keeps validating; the executive gate flips
  the live `rt_drop_firework_explosion` look via `tools/apply_firework_redesign.py` (atomic write +
  one-time `.pre_awr187.bak` backup, refuses without `safety.allow_strobe`, idempotent) — retire v1
  and collapse the two-state live-config tripwire in `tests/test_led_color_engine_m2_patch_d.py`
  after the gate. Files: `govee_frame_renderer.py`, `led_pad_controls.py` (pad defaults diverge
  from v1 via `PARAM_DEFAULT_OVERRIDES`; `bg_hold` min 0.2→0), `config/led_look_director.example.json`,
  `tools/apply_firework_redesign.py`. Tests: rewritten `DropFireworkExplosionTests`,
  `tests/test_apply_firework_redesign.py`. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

LED round 3: Hz-gate migration + rainbow/firework promotions + center-burst fix (AWR-161, 2026-07-09; implemented, software-tested, hardware-unvalidated):
- Migrated the last ten BPM-tied `int(beat*16.0)%2==0` / `int(cue_beat*16.0)%2==0` strobe gates onto
  the AWR-156 `_hz_strobe_on(local_t, params)` wall-clock gate (hz 6.0 / duty 0.3 defaults, same
  feel at any BPM, per-look dialable): `post_drop_center_comet_blue_cyan`, `drop_chase_blue/cyan/
  red/green/cyan_white`, `post_drop_chase_blue/cyan/red/green/cyan_white`,
  `post_drop_freestyle_nebula`, `drop_chase_freestyle_nebula`, and the slot cues
  `rt_post_drop_chase`/`rt_post_drop_nebula`/`rt_drop_chase`/`rt_drop_nebula`/
  `rt_post_drop_center_comet`. All 18 names gained `hz`/`duty` in `REALTIME_EFFECT_PARAM_KEYS` (C5
  guard). `_post_drop_chase`/`_post_drop_nebula` gained `local_t`/`params` parameters they didn't
  previously carry, to reach the gate. Sparkle re-seed `beat_bucket = int(beat*16.0)` uses at these
  same sites are NOT strobe gates and were left untouched. Buildup strobes (already time-based sine
  ramps) and `_hz_strobe_on` itself are unchanged.
- New frame effect `rainbow_ordered` (ported from a lab prototype): hue from strip position plus a
  slow time cycle (an ordered spectrum, not a brightness mashup), heads via the AWR-156
  peak-normalized `_head_weights` helper. `travel_per_beat`, when present, beat-locks the head
  advance; absent, falls back to the legacy `loop_beats` pace. Example config: `rt_rainbow_drop`
  (drop bank, `travel_per_beat 30`) paired via `drop_pairs` to `rt_rainbow_post_drop` (post_drop
  bank, legacy pace, accepted as-is).
- New frame effect `drop_firework_explosion` (ported from a lab prototype, contrast-gated): a
  beat-tied surge (the hit) resolves down to `bg_hold` (0.7) over 0.5 beat instead of staying pinned
  at full, and a time-based ember field (`_ember_field_frame`, same independent-lifecycle timing as
  the production `_ember_field` remnants machinery, colorized from `spark_a`/`spark_b` since this is
  a baked Frame effect) blend-replaces into the background so embers read against it. Promoted only
  after a renderer test measured post-surge ember contrast >= 60/255 at default params — actual
  101/255. Example config: `rt_drop_firework_explosion` (drop bank) paired via `drop_pairs` to the
  existing `rt_post_drop_firework_remnants` (the AWR-149 explosion->remnants arc, now real).
- `_slot_drop_center_burst` fix: removed the `if idx % 2 != 0: continue` gate that lit only even
  pixels, leaving gaps every other pixel on the 60-segment strip. Geometry and the main/accent
  slot-band split (0-2 / 2-4) are otherwise unchanged.
- Files: `govee_frame_renderer.py`, `config/led_look_director.example.json`. Tests:
  `tests/test_govee_frame_renderer.py` (Hz-migration BPM-independence sweep across all 18 names,
  C5-guard allowlist check, rainbow beat-lock/legacy-pace/hue tests, the firework contrast gate
  test), `tests/test_led_color_engine_m2_patch_d.py` (center-burst all-pixel-coverage fixture
  replacing the old even-pixels-only fixture).
- Unaffected/unchanged: `_hz_strobe_on` itself, buildup strobes, nebula slot-5 white semantics,
  knob #4 per-spawn mapping, AWR-149 rotation mechanics, emergency/manual/tactical blackout paths,
  palette/slot-color injection semantics. `rb_state_reader.py`/`rb_memory.py` and
  `state_manager.py`/`drop_presentation.py` were out of scope (parallel-lane files).
- The live, gitignored `config/led_look_director.json` was read-only this round; an un-mirrored live
  config runs the migrated gates at the code defaults (hz 6.0/duty 0.3) — this is the operator's
  intended overridden change — while the two new looks and the center-burst pixel fix need the
  mirror to appear (the fix itself is renderer-level and needs no mirror; only the new *looks* being
  selectable needs it). The bridge stayed down the entire round. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

Darkness-fix round: blank-role hold + reader freshness (AWR-157, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Root cause (from `docs/research/deck2_reader_diagnosis_2026_07_08.md`): a blank/none LED role
  while a deck played audibly fell through to the `utility` bank's configured blackout look for
  ~46s during a scripted-mashup crossover — the room went pitch black mid-song even though nothing
  was actually wrong.
- New config knob `blank_role_hold: bool = True` (top-level, `led_config.py`/`led_models.py`,
  absent-key default true). In the automation dispatch path only (never emergency, manual, or the
  tactical pre-drop blackout — those return before this code is even reached), when the decision's
  look equals the configured blackout look while the deck is audibly playing and a prior automation
  decision was already accepted this session, the blackout dispatch is suppressed and the room
  holds its current look; gated via the existing `_gate_led_automation` bookkeeping, reason
  `blank_role_hold`, with `rt_permitted=True` so realtime motion keeps animating (same pattern as
  `manual_override`/`scripted_mode`). Setting the knob `false` restores today's blackout-on-blank
  behavior byte-for-byte.
- Q-A instrumentation: edge-triggered `[RGB] blank-role-hold` INFO log (DEBUG on identical
  per-tick repeats) fires whenever the guard fires OR would fire with the knob off, with
  `original_role`, `effective_role`, `scripted`, `active_deck`, and a best-effort source
  classification (`phrase_none`/`scripted_map`/`adapter_reject`/`other`) — the exact upstream
  origin of the blank role stays Part A's OPEN question in the diagnosis doc; this instrumentation
  is meant to resolve it from one live session's logs, not to already have the answer.
- `led_look_director.py` gained a `blackout_look` property (`self._config.blackout`) so the
  dispatch layer can compare a decision's look against the configured blackout look without
  reaching into a private attribute.
- Files: `led_dispatch_policy.py`, `led_models.py`, `led_config.py`, `led_look_director.py`.
  Tests: `tests/test_led_state_manager.py` (`BlankRoleHoldTests`, 8 cases),
  `tests/test_led_config.py` (`BlankRoleHoldConfigTests`, 5 cases).
- Unaffected/unchanged (test-pinned): emergency/manual blackout paths, the tactical pre-drop
  blackout, idle/no-audible blackout behavior, scripted-mode Required Behavior Test 9, AWR-149
  rotation, the 200 Hz push loop.
- The rekordbox-reader half of this round (deck-2 chain freshness gating, ObjC fallback
  re-engage, Q-B pause-vs-freeze instrumentation) lives in `docs/subsystems/rekordbox_readers.md`.
- The live, gitignored `config/led_look_director.json` was not touched or mirrored; the tracked
  example config gains `blank_role_hold: true`. The bridge stayed down the entire round — no
  bridge start, no live-config edit, no restart. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

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
- Frozen-aware spawn (AWR-122 M1 Task 4). `_child_argv(frozen, fd)` is the pure argv seam: source runs
  keep the byte-identical `[sys.executable, -m rb_ss_bridge_v2.govee_frame_engine, --fd N]` + the
  package-parent `cwd` pin; under a PyInstaller bundle (`sys.frozen`) it re-execs the app binary as
  `[sys.executable, --run-frame-engine, --fd N]` with no `cwd` pin (`usb_launcher` dispatches
  `--run-frame-engine` before any AppKit import). Socketpair/`pass_fds`/lifecycle unchanged.
- IPC protocol. Newline-framed JSON (`encode_msg`/`decode_buffer`). Parent→child: `init`, `anchor`
  (explicit `null` propagates pause/unpermitted), `set_desired`, `fire_trigger`, `activate_assert`,
  `brightness`, `emergency_stop`, `force_deactivate`, `shutdown`. Child→parent: a `hb` heartbeat every
  `HEARTBEAT_S = 1.0` s carrying `achieved_fps`, `streaming`, `fps_degraded`, and the full
  `runner.status()`. Beat anchors stream at 50 Hz on the client thread; `time.monotonic()` is
  cross-process comparable on this machine so the runner's extrapolation math is unchanged. The child's
  provider keeps returning the last anchor through feed starvation (bridge GIL stalls, e.g.
  rb_memory deck-2 scans) so the runner extrapolates through them; only a feed dead past
  `ANCHOR_DEAD_S = 5.0` s reads as gone. Pause/unpermitted always arrives as an explicit null
  anchor, never via staleness (live 2026-07-08: a 0.5 s gate here blacked out the room every scan).
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
  `QOS_CLASS_USER_INTERACTIVE` via the runner's new `on_thread_start` hook); the child
  self-measures `achieved_fps` every heartbeat instead of assuming any lever worked (the demotion
  mechanism was later root-caused — see the AWR-151 Phase B/C bullet below). `engine_alive`, `achieved_fps`, `respawn_count`, and `fps_degraded`
  are exposed through the runtime status surface (`led_dispatch_policy._sanitize_led_adapter_status`).
- Scheduling-band ROOT CAUSE + machine fix (AWR-151 Phase B/C, 2026-07-08; flip-proven 28.1 vs
  60.0 fps): launchd throttles the whole coalition of any LaunchAgent whose plist omits
  `ProcessType` — all three lighting agents (`com.bbui.bridge-menubar` = the whole bridge tree
  including this child, `com.bbui.led-pad`, `com.bbui.laser-pad`) did. No in-process lever
  escapes a coalition throttle, and `getpriority` reads 0 throughout — which is why the levers
  "succeeded" while doing nothing. Fix deployed to machine config 2026-07-08:
  `ProcessType=Interactive` in all three plists plus the disabled watcher plist; agents
  re-bootstrapped (pads verified spawn type `interactive (4)` and serving; menubar bounced with
  the bridge down). `tools/check_launch_agents.py` is the machine-local advisory guard; it also
  enforces the Python 3.10+ interpreter floor after the pads' pinned `/usr/bin/python3` (3.9)
  crashed on `dataclass(slots=True)` at first restart. Expected live: ~60 fps steady via the
  heartbeat self-report on the next mix. Reserve levers (named, NOT implemented): thread
  time-constraint policy; launchd timer-coalescing opt-out.
- Scheduling-band self-report (AWR-151 Tasks 1-2, 2026-07-08; implemented, software-tested,
  hardware-unvalidated). Which lever actually takes hold in production was invisible — the startup band
  line went only to child stderr (the watcher terminal), never the jsonl or status surface. Now
  `raise_scheduling_band()` reads the live darwin band back via `getpriority(PRIO_DARWIN_PROCESS)`
  (verified 0 = not backgrounded on this machine, errno 0), and every heartbeat re-asserts
  `setpriority(PRIO_DARWIN_PROCESS, 0, 0)` (cheap, idempotent — heals a post-start demotion) and
  re-reads the band, carrying `band_setpriority`, `band_nsactivity`, `band_darwin_prio` on every `hb`
  (edge-triggered INFO in the child only when the read value moves). The client logs the band report
  once per (re)spawn into the jsonl (`bridge_log.perf` at INFO) with an edge-triggered health warning
  when a raise fails, and passes the three scalars through `status()` (whitelisted in
  `_sanitize_led_adapter_status`). Instrumentation only — no timing behavior changes, the runner is
  byte-identical. The `sleep_fn`-injected adaptive precision-sleep backstop originally specced as Task 3
  was DROPPED per the operator's root-cause doctrine (a bandage masks the demotion at a permanent CPU
  tax). Naming the actual demotion mechanism is the separate Phase B investigation (offline throwaway
  children only); the true fix is Phase C, executive-gated on Phase B findings. What fps the child
  holds during a real mix is answered only by the operator's next mix.
- Operator-blackout LAN dim backstop (AWR-146 Task 6). Independent of the child move: the runner's
  `_emergency_teardown` only sends transport commands when it was active, so a pure operator blackout
  while the runner is INACTIVE (cloud look showing) never sent the LAN brightness-0 backstop. The
  policy `LED_BLACKOUT` handler now calls the coordinator's new `blackout_brightness()` →
  `request_brightness(0)` after the blackout is accepted (the unknown-target early-return does not
  dim), duck-typed so a cloud-only adapter no-ops. Tactical (pre-drop) blackout still never dims.

Drop-impact transport guarantee (AWR-150, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- The problem. A cloud drop scene is a fire-and-forget HTTP send with no device-residency feedback;
  its apply latency (observed tail ~5 s) routinely exceeds the 1-4 beat pre-drop runway. Live
  2026-07-08: cloud-previewed drops rode the cloud `room_blackout` for the pre-drop blackout and the
  late cloud drop scene latched the room dark through the beat. The rule (operator, do not re-litigate):
  the pre-drop-blackout + drop-impact pair must never depend on internet latency, and cloud drops stay
  in rotation (never deleted, never filtered) — they just cannot own the beat.
- Pre-drop blackout (Task 3.1, interim guard `e707199`, unchanged). `_dispatch_led_smart_drop_blackout`
  takes the realtime tactical branch for ANY previewed drop transport when the adapter has
  `tactical_blackout`; the cloud `room_blackout` path remains only for cloud-only adapters (no
  `tactical_blackout`) and no-preview ticks.
- Drop impact. In `_dispatch_led_automation`'s drop branch, when the committed pick's backend is
  `cloud_diy` AND the adapter can stage (duck-check: `stage_cloud_takeover` present) AND the drop bank
  has a realtime look, the impact dispatches a realtime SUBSTITUTE through the normal `_led_send_decision`
  path (coordinator realtime branch: owner acquire + assert + dwell, exactly like any RT drop) and, on
  `"accepted"`, stages the committed cloud scene. `LEDLookDirector.substitute_realtime_drop` selects from
  the drop bank's `realtime_razer` subset via the existing `(drop, realtime_razer)` shuffle bag and
  backend cursor, advancing ONLY that backend cursor — never `_role_cursors["drop"]`, because the plan
  slot was already consumed by the committed cloud pick (AWR-149 determinism) — and queues no paired
  post_drop (the committed pick already queued its pair). It returns None on a cloud-only drop bank, and
  the caller then keeps today's cloud dispatch.
- Staging without a dark hole. `LEDDispatchCoordinator.stage_cloud_takeover(decision)` sends the cloud
  scene with NO realtime teardown (no `force_deactivate`), NO owner-state change (owner stays
  `REALTIME_RAZER` for the yield window), and NO dwell bookkeeping (the substitute recorded this tick;
  a second record would poison the WI-3 dwell gate). It also calls the runner's new
  `request_keepalive_yield()` — the AWR-145 2 s razer keepalive would otherwise steal the strip back
  within 2 s of the cloud scene landing. The yield is bounded (`KEEPALIVE_YIELD_MAX_S = 30.0` cap, so a
  forgotten yield self-heals) and CANCELLED by any new intent — `set_desired`, `fire_trigger`,
  `request_activate_assert`, `emergency_stop`, `force_deactivate` — so a blackout never finds the
  keepalive asleep; brightness requests and anchors do not cancel. It is forwarded across the
  frame-engine IPC (`{"t":"keepalive_yield"}` in `govee_frame_engine.py`, a mirror lock-and-enqueue on
  `GoveeFrameEngineClient`) and is intentionally NOT replayed on child respawn (a fresh child
  re-asserting razer is the safe direction).
- Bookkeeping + failure. The drop is recorded under the COMMITTED cloud identity
  (`_led_note_drop_decision_accepted(committed)`), so pairing/presentation/duration are unchanged; the
  substitute is a rendering stand-in only. The AWR-145 retry carries the committed decision in
  `_led_drop_cloud_stage_pending` so a rejected-then-accepted substitute stages exactly once (both the
  first-try and retry accepted paths). If staging errors, the realtime substitute already owns the beat
  (room lit, on-beat) — `_led_stage_cloud_drop_takeover` logs and continues, never failing the impact.
- Net effect. Every drop lands lit on the beat via realtime frames; a cloud drop scene, when the rotation
  picks one, upgrades the room mid-drop (typically 1-5 s in) instead of gambling the impact moment; no
  blackout sticks past its drop. F2-forward bonus: every drop impact now has realtime frames for future
  within-drop choreography to ride, regardless of the picked transport. Software-tested only; the live
  feel is the operator's next mix.

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

True-drop section identity + cycling (AWR-257, 2026-07-15, ships default-on):
- `StateManager` computes `meta.drop_sections` beside `meta.smart_drops` (see the
  core_bridge card). A section = one true drop (a smart drop with a buildup/
  breakdown runway in front, `smart_phrasing.select_true_drops`), its contiguous
  chorus-run end, and the ≥16-beat continuation markers inside it.
- LED pool narrowing is now section-aware. `_led_f2_drop_look_names` resolves the
  section containing the drop anchor and looks the F2 plan up at the section's
  TRUE drop, then draws the same-family union of every tier ≤ the section's tier
  (never above it). So a mid-section continuation can't pull a different family
  or a higher tier than the section's opening hit (the "tier-3 WALL ambush").
- In-section advance markers surface through the SmartPhrasing tick
  (`section_advance` + owning true drop + a per-section `:a{index}`), gated by
  their own fired-set that resets wherever `_fired_drop_beats` does. They
  dispatch ONLY through `_dispatch_led_automation`'s full gate stack (blackout,
  not-ready, manual override, scripted, not-autoloop), then re-enter
  `commit_role("drop", …)` with the section's true drop as the explicit
  preference anchor (never `active_drop_beat`, which is `None` at an advance
  beat) and a unique `:a{index}` role-key so the dedupe gate passes each advance
  exactly once. An advance is a look-cursor move ONLY — no laser, darkness,
  autoloop/OS2L/MIDI, or push-loop I/O. Sparse phrase data ⇒ no sections ⇒
  today's per-fired-drop behavior (fail-open). No kill switch (operator ruling);
  rollback is `git revert` + menubar restart. Software-tested
  (`tests/test_true_drop_sections.py`, 31); hardware-unvalidated.

Deterministic mixed-transport look rotation (AWR-149, 2026-07-08):
- Which transport (cloud DIY vs realtime razer) carries a role's next look is no
  longer a per-session coin flip. The old WI-7 transport-sticky latch — prefer
  the role's last-dispatched backend until `reset_for_track()` — is removed and
  replaced by a pure plan: `plan_backend_sequence()` in `led_look_director.py`
  interleaves the role's (already-filtered) bank by an even Bresenham spacing
  and returns one backend label per future pick. Realtime leads on a size tie
  (F2-forward); a single-backend bank returns that backend uniformly. The
  per-role cursor advances the plan (which transport comes next); a per-`(role,
  backend)` cursor advances only for the transport actually picked and drives
  that transport's shuffle bag, so RNG decides only WHICH look within a
  transport, never WHICH transport. The bag rebuilds whenever the filtered
  subset's membership changes, so a new family/tier route cannot reuse looks
  cached for the previous route.
- Operator contract (taste decision 2026-07-08, do not re-litigate): both cloud
  DIY looks and realtime looks stay reachable in every role whose bank has both.
  Pinning a role exclusively to one transport is rejected. No code path filters
  cloud looks out of a bank; the C4 empty-eligibility invariant (a predicate
  that empties the bank keeps the full bank) is unchanged, and the plan is
  computed on whatever survives eligibility/preference filtering.
- Session phase is deterministic: every role starts at plan index 0
  (realtime-leading), so a bridge relaunch reproduces the same transport phase
  from pick 0 regardless of RNG seed. `reset_for_track()` is now a documented
  no-op — the plan/backend cursors deliberately persist across tracks so a track
  load does not re-flatten the rotation.
- The `RBSS_LED_TRANSPORT_STICKY` env flag is deleted (it gated the removed
  latch); the watcher no longer sets it. Frequent transport transitions are safe
  because of the AWR-145 keepalive/assert/retry chain and the AWR-146
  frame-engine child process — this rotation touches no transport, runner, or
  blackout path. Emergency-blackout, manual-override, safe-default, and
  target-override decisions are byte-identical to before. Software-tested,
  hardware-unvalidated; the live gate is the operator's next mix.

White-knob round 1 (AWR-152, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Operator taste verdict: too much clinical white leaked into non-buildup cues. Two dead knobs are
  gone — `Palette.white` (v1 blend toward pure white; every palette shipped `white: 0.0` in
  practice, `_blend_white` and all 7 call sites deleted) and `ZoneRampConfig.white` (parsed,
  consumed by nothing). Both fields no longer exist on `led_models.py`'s dataclasses.
- Slot 5's white accent under v2 is now a per-zone tint: `ZoneRampConfig.slot5_white: RGB =
  (255, 255, 255)`, resolved verbatim (no sat-floor/hue-shift) by `derive_dressing`
  (`led_identity_v2.py`). Absent `slot5_white` in a config defaults to pure white, so an
  un-mirrored live config renders byte-identical to before. v1's hardcoded slot-5 pure white
  (scripted stand-down) is untouched.
- Palate reset now dims all 6 slots by `palate_reset_dim` (was 5 dimmed + slot 5 held at hardcoded
  pure white) — `_v2_resolve_slot_colors`'s reset branch matches the single-color path's treatment.
- `_led_diy_eligible_predicate` (`led_dispatch_policy.py`) returns `None` under the v2 latch instead
  of filtering by the frozen, non-advancing v1 palette: under v2 the v1 palette never updates
  (`begin_dispatch` returns early into the v2 branch), so the old filter was arbitrary and
  white-tagged cloud looks always passed it regardless. Under v2, every banked cloud look now
  rotates evenly; DIY filtering under v1 (latch off) is unchanged.
- `breakdown_star_twinkle` (`govee_frame_renderer.py`) draws its per-star color slot from 0-4 only
  (was 0-5), matching `_slot_twinkle`; breakdown twinkles no longer throw random pure-white stars.
- Example config (`config/led_look_director.example.json`): `groove_diy_bright_white_chase` moved
  from `banks.default.groove` to `banks.default.buildup` (white is the buildup language); every
  palette-level `white: 0.0` key and every v2 zone's `white` key deleted; each v2 zone carries an
  audit-taste `slot5_white` default (e.g. GLACIER `[200, 235, 255]`, EMBERCORE `[255, 225, 200]`).
- Unaffected/unchanged: `exempt_looks` (the three freestyle nebulas stay in the default banks — a
  separate AWR-152 knob was vetoed), bank membership beyond the one move above, v1 scripted-mode
  output (minus the identity `white=0.0` blend, which was already an identity no-op), blackout/
  emergency semantics, AWR-145 keepalive, AWR-150 substitute flow, the 200 Hz push loop (no new
  I/O), `REALTIME_EFFECT_PARAM_KEYS`/`REALTIME_STROBE_EFFECTS`, laser/SoundSwitch/Rekordbox.
- The live, gitignored `config/led_look_director.json` was read-only for this round; the operator
  mirrors the example config's zone/bank changes in and restarts via the menubar to pick this up.
  Until mirrored, the legacy `white` keys still in the live config load harmlessly (no allowlist
  rejection on palette/zone dict keys) and render exactly as before, except the reset-window
  slot-5 dimming and the breakdown-star slot range, which apply immediately. Full detail:
  `docs/plans/active/led_white_knobs_round1_spec.md`.

LED pad blackout unlatch fix (AWR-154, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Caught live during an operator mix: LEDs latched dark and unremovable. Root cause was a
  reason-blind clear chain — the pad takes ownership via `led_blackout reason=led_pad`
  (`tools/led_pad_playback.py`), which lands owner `"led_pad"` in `_led_blackout_owners`
  (`led_dispatch_policy.py`), but `OwnershipGate.release()` sent a bare `led_clear_blackout` with
  no reason, and the whole clear path from there — `runtime_status.py`'s `CommandReader` dispatch
  through `__main__.py`'s `_led_clear_blackout` — carried no reason either. The discard line itself
  (`ev.payload.get("reason") or "legacy"`) was always correct; it just never received anything but
  the implicit `"legacy"` default, so the pad's own claim could never be discarded.
- Minimal fix, three files: `release()` now sends `reason=led_pad`; `parse_command()` accepts an
  optional non-empty `reason` on `led_clear_blackout` (validation split out from the shared
  `led_clear_scene_override` block, which is unchanged); `CommandReader`'s dispatch handler parses
  the reason and passes it to the callback instead of invoking a zero-arg callback;
  `_led_clear_blackout(reason=None)` adds `"reason"` to the `BridgeEvent` payload only when truthy.
  Absent reason resolves to an empty payload everywhere, so a bare clear is byte-identical to
  before this fix.
- `led_dispatch_policy.py` was not touched — the owner-set add/discard logic needed no change, only
  the reason needed to reach it. No clear-ALL-owners fail-open behavior was implemented; that stays
  proposal-only elsewhere.
- This is a code fix, not a runtime unlatch: it changes what the next bridge start will do. A
  process already latched dark from this defect needs a restart to pick up the fix — none was
  performed during this pass.
- Superseded by AWR-155 below: "no clear-ALL-owners fail-open" and "led_dispatch_policy.py was not
  touched" were both true for this round only. AWR-155 later added exactly that behavior.

LED bare-clear fail-open (AWR-155, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Executive-approved shape, landed the same day as AWR-154: a bare `led_clear_blackout` (no
  `reason`) is now operator authority and clears every owner in `_led_blackout_owners`
  (`led_dispatch_policy.py`) at once — `led_pad`, `drop_spotlight`, `legacy`, whatever is present —
  instead of only ever discarding `legacy`. A reasoned clear is unchanged: it still discards exactly
  the named owner, so the LED Pad and drop-presentation machine surfaces keep their own scoped
  clears from AWR-154.
- The no-reason branch snapshots the owner set, clears it, and emits one INFO outcome log
  (`[RGB] blackout-clear-all owners=...`) naming what was cleared. This is a discrete per-command
  log, not a per-tick one. `_led_emergency_blackout` is recomputed from the now-empty set, so the
  existing `restore_brightness()` backstop fires exactly as it does for any other now-clear
  transition.
- Accepted, not guarded against: a bare operator clear during a lasers-only solo window also clears
  `drop_spotlight` and lights the LEDs mid-solo. That is the intended override — operator authority
  outranks the presentation window's hold, and the window's own later release discard is a safe
  no-op against the (now empty) set.
- Effect begins at the next bridge restart after the one this was written during (the bridge had
  already been restarted once this evening for AWR-154 and was live when this landed); no restart,
  live-config edit, or strip-touching action was performed while implementing it.

LED round 2: strobe-gate rebuild + accepted-look promotion (AWR-156, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Standing promotion rules (operator-ruled, binding for future work): strobes are TIME-BASED (real
  Hz + duty on `local_t`, never beat/BPM-subdivided — a strobe must feel identical at any BPM);
  sparkles are TIME-BASED and continuous (independent per-sparkle lifecycles, never a synchronized
  whole-field re-roll — that pattern was the diagnosed ~17 Hz flicker mechanism).
- Strobe gate rebuild (`_hz_strobe_on`, `govee_frame_renderer.py`): replaces the old stateless
  beat-domain 29 ms window (`(beat % 0.25) < 0.0625`) that missed up to ~31% of cycles under
  runner jitter. The new gate reads `hz`/`duty` in the seconds domain and widens its ON window to
  at least ~1.6 rendered frames using `frame_period_s` — a new runtime-injected param (the
  `slot_colors` pattern, deliberately not on any static allowlist) that `GoveeRealtimeRunner`
  maintains as an EMA (alpha 0.2) of actual inter-tick gaps and injects into every render call.
  `drop_white_aggressive` now runs this gate at hz 6.0/duty 0.3 (the accepted reference feel).
- Colorway strobe family: one new frame effect, `drop_strobe_colorway` (baked, not palette-fed) —
  solid `color_a`, or `color_a`/`color_b` alternating per flash when `color_b` is present. Seven
  looks ride it at the operator's dialed rates: `rt_drop_strobe_blue`/`_cyan`/`_green`/`_red` (hz
  6.0/duty 0.3, pure colorway), `_red_white` (hz 5.5/duty 0.25, side B restored to white
  `(255,255,255)` — his last pad dial was red; **one-line operator veto** restores it), `_blue_cyan`
  (hz 5.0/duty 0.25, his dialed azure B `(0,135,255)`), `_cyan_white` (hz 5.0/duty 0.25, his dialed
  periwinkle B `(100,105,255)` despite the "white" name). All seven are in `banks.default.drop`.
- Three promotions: `buildup_balloon_comet` (frame effect, baked white) — a dual-head chase whose
  width lerps `start_width`→`end_width` over `build_beats` with brightness falling to `dim_floor`
  (accepted: 6→0.8 over 32 beats, dim to 0.05). `rt_groove_heartbeat` (slot effect, engine-palette) —
  a dual-head chase whose width pulses on the beat then decays exponentially; `color_mode` (0-3)
  selects slot routing, default 2 = head1→slot1/head2→slot3 (his accepted red+white combo feel).
  `rt_post_drop_firework_remnants` (slot effect, engine-palette) — slot-5 background dims 1.0→0
  over `dim_beats`; time-based embers (`_ember_field`, ported from the Template Lab reference) hold
  full to `ember_hold_beats` then decay to 0 over `ember_decay_beats` (accepted 8+2 — done by beat
  10). **Historical AWR-156 behavior; superseded by AWR-215's sparse drop-chase sparkle tail.**
  All three share a peak-normalized head-weight helper (`_head_weights`, module-level): a
  triangle-falloff weight divided by its own max (not summed), so the brightest pixel always
  carries the full head level — this is the fix for a measured 0.53× between-pixel brightness dip
  that read as stutter.
- Knob #4, the intensity-hue mashup dies: eight renderer sites used to derive a comet's slot
  (hence its palette color) from its own brightness (`slot_coord = intensity * N`), so one comet
  body could sweep well over 100° of hue across its own length. All eight now pick ONE fixed slot
  per spawn — intensity is brightness only. Groove chase/nebula: the two heads take slots
  `cycle % 5` and `(cycle + 2) % 5` (`cycle = int(cue_beat / loop_beats)`). Drop/post-drop
  chase/nebula (palette-comet branch): `slot = spawn_idx % 5`. Post-drop center comet:
  `slot = round(cue_beat - age) % 5`. Drop center burst: main bursts rotate slots 0-2
  (`burst_idx % 3`), accent bursts rotate slots 2-4 (`2 + burst_idx % 3`) — the main/accent band
  split survives, only the intra-burst hue sweep dies. Nebula white comets (slot 5) and the
  sparkle-intro pixels are untouched — not mashup sites. `_slot_groove_center_chase` and
  `_slot_post_drop_firework_chase` (ordered positional gradients, operator-liked) are explicitly
  NOT mashup sites and were not touched.
- Knob #9, role-scoped comet widths: `width` is now a real config knob for every touched cue —
  `rt_groove_chase`/`rt_groove_nebula` previously hardcoded `width = 0.8` and
  `rt_post_drop_center_comet` hardcoded `comet_width = 1.0`; all three now read
  `params.get("width", <their old hardcoded value>)`, so an un-mirrored config is byte-identical.
  Example config: width 4 on `rt_drop_chase`(renamed, see below)/`rt_drop_nebula`(renamed)/
  `rt_post_drop_chase`/`rt_post_drop_nebula`/`rt_post_drop_center_comet` (his stated request); width
  2.5 on `rt_groove_chase`/`rt_groove_nebula` (**veto-able** — his `comet_width` pad dial never
  reported a final number).
- Bank recast + rename (amended by operator mid-round from a plain move to a rename): the two
  sparkle chases move from `banks.default.drop` to `banks.default.post_drop` ("current sparkling
  cues can play the role of the sparkling remnants") AND their look names change to
  `rt_post_drop_remnant_chase` / `rt_post_drop_remnant_nebula` so the name reads as post-drop
  remnant material — their renderer `scene_ref` stays exactly `rt_drop_chase` / `rt_drop_nebula`
  (a look-name rename only). Their `drop_pairs` entries are deleted (a post_drop-role look never
  fires a pair); the AWR-149 drop→post_drop pairing will carry explosion→remnants arcs once the
  explosion round lands. `rt_drop_nebula` no longer pairs to `rt_post_drop_nebula` through
  `drop_pairs` — the "Patch E pairings" note below is stale as of this round.
- Knob #5 explicit no-op: `step_within_section.groove` stays `true` (unchanged; reversal considered
  and rejected).
- Task 9 (operator refinement, same day): the zone-tinted slot-5 white now applies to NEBULA
  COMETS ONLY. A new `BAKED_WHITE_SLOT5_EFFECTS = frozenset({"post_drop_firework_chase"})` set,
  checked at `GoveeFrameRenderer.render()`'s slot-color resolution site, forces slot 5 to literal
  `(255, 255, 255)` for any effect in the set before colorizing — one site covers bridge, pad, and
  lab injection paths alike. Nebula white comets (`rt_drop_nebula`/`rt_post_drop_nebula`) are
  deliberately NOT in the set — they read the zone tint once mirrored. `rt_post_drop_firework_remnants`'s
  slot-5 dimming background is a background, not a white accent, and stays zone-tinted (an
  executive-visibility boundary note, not a gap — a one-line addition if the operator wants it
  pure). No cue writes a twinkle-star white accent today (AWR-152's knob #8 removed it from
  `breakdown_star_twinkle`; `_slot_twinkle` never had one) — **one-line operator flag**: re-adding a
  white entry to the star-twinkle slot range or to `BAKED_WHITE_SLOT5_EFFECTS` restores occasional
  baked-white breakdown stars if he wants them back.
- `ir.local_t` [assumed → confirmed while implementing]: it advances on wall-clock seconds through
  pauses/seeks exactly as the beat-sync engine defines cue time. The Hz gate is stateless in
  `local_t`, so a backward jump on wrap/retrigger simply re-phases the gate rather than breaking it.
- Unaffected/unchanged: `exempt_looks` and the freestyle nebulas' bank membership, blackout/
  emergency semantics (AWR-154 reasons + AWR-155 fail-open), AWR-150 substitute + staged takeover,
  AWR-149 plan rotation mechanics, the 6-slot invariant, buildup cues' white-by-design palette, the
  positional-mapping prototypes, the 200 Hz push loop (the runner's frame-period EMA is arithmetic
  on already-taken timestamps, no new I/O), laser/SoundSwitch/Rekordbox. Out of scope this round
  (verdicts pending): `drop_firework_explosion_2`, `rainbow_drop`/`rainbow_post_drop`,
  `comet_rainbow_ordered` promotion, remnants spawn-feel re-check. Round-3 residual logged, not this
  round: `_slot_drop_center_burst` even-pixels-only gappiness. **All resolved in AWR-161 above** —
  the rainbow pair and firework explosion promoted (contrast-gated), the center-burst gap fixed;
  remnants spawn-feel re-check stayed out of scope.
- The live, gitignored `config/led_look_director.json` was read-only for this round; an un-mirrored
  live config renders identically to today for every look it defines, EXCEPT the two locked
  behavior changes that need no config: the `_drop_white_aggressive` gate rebuild and the knob-#4
  mapping change at all eight sites. The operator mirrors the example config's new looks/widths/
  bank-recast/rename in and restarts via the menubar to pick the rest up. Full detail:
  `docs/plans/active/led_round2_promotion_spec.md`.

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
- AWR-235 (2026-07-14): a same-`role_key` repeat idle tick restores the
  captured freewheel timestamp before returning, so the running realtime
  ambient look keeps its beat anchor across push-loop passes. Gated early
  returns (not configured / disabled / blackout / manual override) still clear
  the freewheel exactly as before; a changed idle `role_key` still re-dispatches
  and re-stamps the freewheel on accept. This closes the July-7 regression that
  left `desired_effect=rt_twinkle` with zero frames rendered.
- If the realtime runner still reaches idle-grace teardown, it now sends a
  blackout frame before deactivating and logs
  `[RGB] deactivate reason=idle_grace blackout_sent=1`, so the failure mode is
  dark instead of leaving a previous cloud DIY scene on the strip. Every
  permitted healthy frame clears the grace timer, so separate brief feed
  hiccups cannot combine into a later blackout; a continuously bad feed still
  blackouts and deactivates after the grace window. The
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

Continuous-look sustained-divergence BPM re-anchor (AWR-189, 2026-07-09):
- A continuous realtime look that spawned while the live-BPM feed was
  mid-transition free-ran at the stale rate forever (live-diagnosed on
  `rt_groove_heartbeat`: "beatsynced looks do not look beatsynced"). The
  engine now re-anchors the beat-phase origin to the live anchor bpm, but
  ONLY when |live − current rate| exceeds `REANCHOR_BPM_DELTA` (2.0)
  CONTINUOUSLY for `REANCHOR_SUSTAIN_S` (3.0 s) — one in-band sample resets
  the timer, so AWR-141's jitter immunity stands and nothing raw-tracks.
  The re-anchor snaps fractional phase onto the real grid while preserving the
  effect's accumulated whole-beat age, so a tempo correction cannot replay a
  multi-beat opening envelope. `local_t`, bucket identity, and progress stay
  born-based so time-based layers and comet sweeps never restart. Feed gaps
  over 1 s, zero-BPM samples, and paused/unpermitted animation clear divergence
  evidence, so the 3 s window must be continuously observed. Retrigger/overlap modes are
  untouched. Both knobs are per-look config-overridable via params
  (`reanchor_bpm_delta` / `reanchor_sustain_s`). Never-diverged behavior is
  byte-identical. Operator acceptance look on record: `rt_groove_heartbeat`
  at next play. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

Palette-cycling comet — rainbow generalization (AWR-188 Part G, 2026-07-09):
- New slot effect `palette_comet` (`govee_frame_renderer.py`): the accepted
  `rainbow_ordered` dual-head movement and position-plus-time color phase,
  quantized onto the runtime-injected palette slots instead of the HSV wheel —
  a palette, not a renderer branch, so rainbow-classified tracks (rainbow
  palette) render rainbow and every other track cycles its own colors. Cycles
  palette slots 0-4 only (slot 5 stays the reserved white accent); any
  injected palette length works (a 3-slot palette cycles slots 0-2; no
  injection fails bright-white on slot 0). Deterministic with a seeded
  palette start offset (same seed + beat + local_t ⇒ same frame). Not a
  strobe. C5 param allowlist: `width`, `cycle_beats`, `palette_span`,
  `travel_per_beat`, `loop_beats`, `duration_beats` (+ sync keys).
- Example config: `rt_drop_palette_comet` (drop, `color_source engine`,
  movement params mirroring the pulled `rt_rainbow_drop`) paired via
  `drop_pairs` to `rt_post_drop_palette_comet` (post_drop). The bespoke
  `rt_rainbow_*` looks stay DEFINED but unrouted; their kill is a later
  cleanup after the operator accepts the replacement live.
- LIVE-config banking ships as `tools/apply_partg_palette_comet.py`
  (add-if-missing, loader-gated, timestamped backup, atomic write,
  self-verifying, idempotent): look defs + pair, `rt_drop_palette_comet`
  into the COMET-family tier-2/3 routing pools and `banks.default.drop`,
  the post_drop look into `banks.default.post_drop`. The executive runs it
  after the Round A routing rewrite lands — no live-config edit shipped
  in-round. Tests: `tests/test_partg_palette_comet.py`. SOFTWARE-VALIDATED
  ONLY / HARDWARE-UNVALIDATED.

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

Idle-no-audible releases the `drop_spotlight` owner (AWR-171 / D3-F1, 2026-07-09):
- `_do_stop` already releases a latched solo window via
  `_drop_presentation_release_on_stop`, but `_enter_idle_no_audible` reset
  LED/laser/autoloop state and never called it. When the active-deck resolver
  lands on 0 mid-solo-window (the operator's fader/EQ mixing path, not a stop),
  `_push_tick_inner` early-returns on `active_deck` not in (1,2) forever, so a
  held `drop_spotlight` LED blackout owner never released — the room stayed dark
  up to the 192-beat cap. The fix mirrors the stop path: one call to the same
  idempotent, policy-gated, in-memory helper at the end of
  `_enter_idle_no_audible` (before the idle-ambient dispatch, so the room
  re-renders lit). `enabled:false` stays byte-identical (helper's own guard).
  Fail-open beats fail-dark. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

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
  read-only behavior for that boot and must not stop v1 color output. In frozen-bundle runs only
  (AWR-186 M2), `led_config.py` resolves that default through `launch_profile.resolve_state_path`
  to `~/Library/Application Support/RBSS Bridge/state/` at parse time (a double-clicked app's cwd
  is `/`, unwritable); source runs get the configured path back byte-identical.
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

LIGHTING ENGINE v2 F4 texture layer (AWR-164, 2026-07-09):
- F4 is a **consumer-only** seasoning layer over the existing v4 spectral classes (`spectral_profile.py`
  unchanged — no new analysis). It picks WHICH variant/params of an already-selected look play; it
  **never** touches scheduling, darkness, family, tier, or look routing. S-2 containment is proven by
  `tests/test_lighting_moments_v2_f4.py` (F4-on seasoning changes only `decision.params`; F4-off/F2-off/
  scripted → no-op; the euphoric look-preference term only narrows within the bank, fail-open).
- `lighting_moments_v2.build_track_plan` records the texture into the F2 plan: per drop a majority-vote
  texture vector (stab / sustained-bass / growl / kick-prominence / thick / bright-tilt + onset density
  for the WALL trap-vs-dense split) and per track the euphoric (sustained-synth ≥8) and simmer
  (attack_low<2.5 & onset<0.5, ≥8-run) beat ranges, plus the EXPERIMENTAL `lowmid_pulse` busy-pulse duty.
  Pure, fail-soft, on the async worker; unread unless F4 is on.
- `led_dispatch_policy._led_inject_f4_seasoning` merges the texture-selected variant params into the
  drop cue's `decision.params` (family+texture key → `f4.variant_seasoning` cell; a HOUSE growl-bar drop's
  bass-forward B/K mask scales sparkle density — a scalar stand-in, not literal per-beat alternation). It
  also seasons quiet role cues with sparse-dim `simmer_seasoning` params during a measured simmer.
  Euphoric windows add a bright/white-end preference through the existing
  `_led_look_preference_predicate`. The v2-dressing, F2 family/tier, and F4
  bright terms narrow independently in that order; an empty F4 intersection
  keeps the F2-routed pool instead of reopening the full drop bank.
- Kill switch: the `/f4` config block, example-ON / absent-OFF (`led_config.load_f4_config` /
  `led_models.F4Config`), so an un-mirrored live config stays byte-identical to F2-only. `busy_pulse`
  is COMPUTED-NOT-CONSUMED behind `busy_pulse_experimental` (renders nothing; C§6d). `sustained_synth`
  is the clean-euphoric proxy (counts vocals) and is **never surfaced as "synth."**
- HONEST scope: seasoning VALUES are TUNE-LIVE config defaults, cloud DIY looks ignore the param merge
  (only realtime looks render it), and F2 never wired a section-rung floor — the simmer "upgrade" seasons
  the selected floor look's params rather than driving a rung-2→rung-4 renderer. Live-tuning is the
  operator gate. No bridge/hardware validation was performed.
- F2 early darkness release (AWR-179 D2-F1, OLC-B): a blackout drop whose sub floor returns early
  carries an `abort_at` beat in its plan. `lighting_moments_v2.transition_release_for` turns that into
  a beats-before-drop release bound, plumbed through `StateManager._f2_transition_release_beats` into
  `SmartPhrasingSnapshot.transition_release_beats`. Once the drop is within that many beats, the pre-drop
  dark window deactivates early and the existing falling-edge `transition_mask_should_clear` releases the
  mask — up to ~3 fewer dark beats, so the room re-lights EARLY (fail-open direction, never darker; the
  window START is unchanged and the drop-crossing clear backstop is untouched). It rides F2's existing
  enable surface (no new config key): F2-off, scripted, no-plan, and no-abort all resolve to a 0.0 bound,
  which is byte-identical to before. Software-tested (`tests/test_lighting_moments_v2.py`,
  `tests/test_smart_phrasing.py`); no bridge/hardware validation.
- Deep sub-void blackout rung (AWR-184, labels batch-1, 2026-07-09): a new additive rung in
  `lighting_moments_v2.darkness_ladder`, checked AFTER the Part H true-silence rung and BEFORE the
  balloon split. Fires only when BOTH the sub band is genuinely voided (`SUB_VOID_DB`, ≥
  `VOID_MIN_BEATS` consecutive beats ending at the drop) AND the growl/tonal band died with it
  (`GROWL_DARK_DB`) — a filtered melodic swell keeps its growl ringing and still resolves balloon
  (Caramelle control), while a real full cut resolves blackout for the void length rounded UP to bar
  rungs {4,8,16}. Grounded in operator ear-truth (AWR-182 labels: Utopia b192 "2 bar blackout" →
  8 beats, b384 "1 bar blackout" → 4 beats) measured against the real spectral cache; no existing
  constant moved. Software-tested (`tests/test_lighting_moments_v2.py`, `TestDeepSubVoidBlackout`);
  no bridge/hardware validation.
    - Precedence guard (AWR-185, 2026-07-09): the true-stop predicate is computed BEFORE this rung
      and the rung yields to it — when the full band is still audible (a vocal stop: deep sub void +
      dark growl band but vocals sitting above the growl band), the calibrated 8-beat stop length
      wins instead of this rung's run-length rounding. Utopia's voids kill the full band below
      audibility so its b192/b384 blackouts are unchanged; no threshold moved (one guard only).
      Software-tested (`test_vocal_stop_yields_to_stop_rung`).
    - Pickup abort (AWR-199, day-0 interim guard, 2026-07-10): the rung now carries an `abort_at`
      when its void ended >= 3 beats before the drop with the sub floor audibly back the whole way
      (the drop-anchored window otherwise keeps returned music dark), releasing at the first
      returned beat through the existing F2 early-release path — 1- and 2-beat pickups stay dark
      per the operator gap-0/1/2 verdicts, and env `RBSS_F2_VOID_PICKUP_ABORT=0` (read at import)
      restores the always-`None` behavior. Software-tested (`TestDeepSubVoidBlackout` pickup
      cases + `test_deep_sub_void_pickup_abort_releases`); no bridge/hardware validation.

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
  existing `get_laser_blackout` pattern) surfacing the Solo pad's state, extended by AWR-159
  (2026-07-09) from three values to five: `off`/`armed`/`pending`/`active`/`refused` (`pending` =
  an auto tier queued for the next drop, distinct from a manual `armed` press; `refused` = a
  one-tick flash when a manual arm could not be honored).
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
- `tools/led_pad_mirror.py` pad-process live-play mirror tee + ring (AWR-269; runner-thread O(1) append only)
- `tools/led_pad_web.py` local LED Pad web service
- `tools/led_pad_lab.py` Template Lab draft registry and pad-only renderer overlay
- `tools/led_pad_assets/` vanilla LED Pad UI assets
- AWR-214.TLAB timing truth: `led_pad_controls.EFFECT_TIMING_MODES` makes `/api/renders` exhaustive for
  beat/time/mixed/static effects; lab registry entries persist the same `timing_mode` and decorate
  `beat_synced`. Both pad pages badge the timing, and Template Lab disables Beat-sync BPM for
  time/static/unknown drafts. The AWR-194 wave-1 software sweep was 25 render-working, 0 static,
  0 render-error (19 beat, 1 mixed, 5 time); no draft function changed. Hardware-unvalidated.
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
- `CfxSweepConfig`

Runtime flow:
- inputs: phrase/role state, runtime LED commands, LED config, color engine state, beat/BPM state
- decisions: manual override, blackout, role-entry look selection, color/slot-color resolution, cloud/realtime ownership, beat sync instances. LED dispatch policy is mixed into `StateManager` from `led_dispatch_policy.py`; it runs on the StateManager thread and owns no backend threads, locks, or blocking I/O.
- outputs: cloud scene commands or realtime UDP frame packets
- The live LED drop/post-drop resolver remains in `StateManager`.
  `drop_lifecycle.py` reproduces its flat-window drop-region state machine for
  laser use; `tests/test_drop_lifecycle.py` parity-checks that seam without
  routing LED output through the new module.
- Active content changes now arm a phrase-aware LED hold in `StateManager`: a nonzero active-deck switch or active-deck track replacement keeps the previously shown look if the incoming track is more than `1.0` beat into its current phrase, then releases at the next phrase crossing. If the incoming track is already within the first beat of a phrase, it changes immediately. Missing phrase segments are bounded by the same hold's 16-beat / 8-second backstop; this is software-tested only and still needs operator visual sign-off.
- CFX filter-sweep overlay (AWR-173, `implemented` / `software-tested` /
  `hardware-unvalidated`): when the operator turns the CFX FILTER knob clockwise
  from 12 o'clock (low→high only; counterclockwise does nothing), the strips
  flood toward the track's darkest v2 hue (`LedColorEngine.v2_darkest_rgb()` =
  `Dressing.slot_rgbs[0]`). **Crossing an ear-calibrated bloom threshold TRIGGERS
  a one-shot timed drain** (operator re-ruled at the desk 2026-07-09): the flood
  swells, then the room dims 1.0→`dim_floor` over `drain_ms` and holds — the dim
  is NOT knob-tracked, and holding the knob past the bloom does nothing extra.
  Riding back below the threshold LATCHES a one-way release of the whole overlay
  (mix→0 and dim→1.0 together over `release_ramp_ms`) that STAYS released for the
  entire ride down (operator return-ride ruling 2026-07-09) — the flood does not
  re-appear no matter where the knob parks above the deadband, and it cannot re-fire
  even if the knob wanders back above the threshold. Re-firing needs a fresh sweep
  from neutral (knob ≤ 0.5 + `engage_deadband`), so the return ride never re-blooms.
  The per-tick pure envelope `cfx_sweep_envelope`
  (in `led_dispatch_policy.py`) carries a small frozen
  `CfxEnvState(mix, dim, fired, released)` across ticks (`fired` + `released` both
  clear only at neutral, so a fresh sweep floods again);
  `StateManager._compute_led_cfx_sweep` stores an atomic tuple that
  `get_active_beat_anchor` attaches to the ~20 ms `BeatAnchor` pump, and the
  frame-engine child applies `scale(lerp(px, cfx_rgb, cfx_mix), cfx_dim)` per
  pixel on the composed-playback frame only. Wire fields are `.get`-defaulted on
  both sides so a frozen/old frame-engine child stays neutral (frozen-child
  skew). Three darkness signals force the overlay inert at the dispatch gate
  (`_compute_led_cfx_sweep`): blackout/emergency owners (`_led_blackout_active()`),
  F2 smart-breakdown sections (`_os.breakdown_active`), and the smart-drop pre-drop
  tactical blackout (`_led_smart_drop_blackout_key`) — and the child's
  blank/idle/emergency paths never run the overlay either, so darkness wins both
  structurally and at the gate. Ships `cfx_sweep.enabled: false`; the bloom threshold
  and ramps stay `pending desk calibration` (Part F of the AWR-173 spec).

Config:
- `config/led_look_director.example.json`
- local ignored `config/led_look_director.json`
- env secrets such as `GOVEE_API_KEY`
- realtime enable flag if present in startup
- `color_engine.slot_fill_strategy_by_look` and `color_engine.slot_fill_strategy_by_role` are optional objects; values must be `gradient_even`, `random_with_replacement`, or `random_with_mono_chance`.
- `color_engine.slot_mono_chance_by_look` is an optional object mapping look names to numeric probabilities in `[0, 1]`; it defaults to `{}` and only affects looks using `random_with_mono_chance`.
- `color_engine.locked_palette_by_look` is an optional object mapping look names to existing palette names. Locked looks resolve color and slot-color injection from that palette's full p-interval without changing the color-engine journey palette, dwell, focus, or RNG state. (AWR-152: the per-palette `white` blend knob was removed — every palette shipped `white: 0.0` in practice, so `Palette` no longer has a `white` field.)
- `cfx_sweep` is optional and default-off (AWR-173). Absent/malformed/out-of-range block ⇒ disabled
  (`CfxSweepConfig()`), so an un-mirrored live config never floods; unknown keys are IGNORED (the
  live config still carries a now-removed `rearm_hysteresis`). Fields: `enabled`,
  `engage_deadband`, `bloom_threshold_norm` (desk-calibrated), `flood_ramp_ms`, `release_ramp_ms`,
  `dim_floor`, `drain_ms` (drain feel — dim 1.0→floor after the trigger).
  Loader validates `0 < bloom_threshold_norm < 1`, `0.5 + engage_deadband <
  bloom_threshold_norm`, ramps `> 0`, `0 <= dim_floor < 1`, `drain_ms > 0`;
  any violation disables the whole block.
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
- Patch F collapsed the tracked example `default` bank onto generic engine-colored slot looks. AWR-265 FINAL deleted the temporary `legacy_color_suffix` storage bank and the color-suffix clone looks; those colorways now surface through palette-fed bases under `blue_cyan` (and peer journey palettes).
- `safety.scripted_mode_automation` remains the master switch for scripted-track LED automation. The shipped example config sets it `true` (paired with the conservative blackout `scripted_mode` policy); set it to `false` to keep LEDs inert during scripted tracks. The code-level `LEDSafety` dataclass default stays `false`, but the loader requires the JSON key. When it is true and `StateManager` is in `lighting_mode == "scripted"`, automatic LED dispatch may proceed through the `scripted_mode` role-remap policy.
- The top-level LED `scripted_mode` block defines `default_role` plus `role_map` for scripted-track automation. If the block is absent, groove, drop, and post-drop map to the `utility` blackout bank; buildup/pre-drop map to `buildup`, and breakdown maps to `breakdown`. `utility` is allowed only as a destination, and partial maps fall back to `default_role`.
- `blank_role_hold` (AWR-157, top-level boolean, default `true`) — when a scripted or blank-role
  path resolves to the configured blackout look while the deck is audibly playing and a look was
  already accepted this session, the room holds its current look instead of blacking out. Set it
  `false` to restore the pre-AWR-157 blackout-on-blank behavior. Absent key parses as `true`.
- LED Pad persists its edit draft in `config/led_look_director.draft.json` and commits only after the full draft passes `load_led_look_director_config_from_dict()`. In the UI this draft commit is labeled **Apply** (2026-07-03 visual reskin; the `/api/commit` route name is unchanged, and the reskin — design tokens plus a vendored Archivo font in `tools/led_pad_assets/` — changes no runtime behavior). The pad-only Drafts bank lives in root `_pad_meta.drafts`, so those looks are automation-invisible unless moved into `banks.default`.
- LED Pad Locked Palette writes through `color_engine.locked_palette_by_look`; playback of a locked look ignores the session Test Palette. Renderer param unlocks are frame-identical when omitted: `loop_beats` on `rt_groove_chase`/`rt_groove_nebula`; `travel_beats` + `width` on `rt_drop_chase`, `rt_post_drop_chase`, `rt_drop_nebula`, and `rt_post_drop_nebula`; `travel_beats` on `groove_center_chase` and `post_drop_firework_chase`.
- AWR-240 (2026-07-15): with lighting-engine v2 enabled, `_inject_engine_colors` in `tools/led_pad_web.py` must `set_scripted_stand_down(True)` on its fresh offline `LedColorEngine` before Test Palette fill. Without that, v2 has no dressing/manual color and returns empty `slot_colors`, so pad preview and lab slot cues paint black (slots 1–5) / white-only (slot 0). Bridge runtime modules are unchanged. Covered by `tests/test_led_pad_service.py` (`test_v2_enabled_pad_still_injects_slot_colors_from_test_palette`).
- AWR-241 (2026-07-15): Template Lab beat meter + metronome. `PadPlayback.status()` includes `beat` from `SyntheticClock` (frozen while stopped). Lab UI: preview derives beat from `frameIndex * bpm / (60 * fps)` (exact; counter `bar B · beat K`); live phase-locks to polled `status.beat` (label **beat phase (server)**). Optional WebAudio click (off by default) — preview = exact, live = synced ± poll jitter. Covered by `tests/test_led_pad_playback.py` (`test_status_beat_advances_with_fake_time`); JS is manual-smoke only.
- AWR-242 (2026-07-15): Template Lab UX overhaul (lab route only). `LabRegistry.save` persists optional `target_role` (empty or ambient/groove/buildup/pre_drop/drop/post_drop/breakdown/utility); list payload includes it. Lab UI: searchable/filterable/grouped draft list, Phrase+Timing selects (timing_mode settable), preview-first detail layout, client health strip + Self-test composing existing `/api/runtime_status` + `/api/lab/reload` + `/api/lab/preview`. New CSS scoped under `.lab-route`. Covered by `tests/test_led_pad_lab.py` (`test_registry_target_role_*`); Pad route markup untouched.
- AWR-243 (2026-07-15): Template Lab functional fix round. Collision banner gated on `production_collision` (CSS honors `[hidden]`); selected draft pinned in the list across Accept; `pad-core.js` `request()` attaches `err.payload` so Lab Play/Switch catch `ownership_required` for PadModal takeover; slider hint when `/api/lab/update` returns `applied:false`; `session(test_palette=…)` live-pushes colors while a `lab_*` scene is playing (lab play clears `_last_play_editor`). Covered by `tests/test_led_pad_lab.py` (`test_list_production_collision_false_for_non_production_name`) and `tests/test_led_pad_service.py` (`test_session_test_palette_live_updates_playing_lab_draft`).
- AWR-245 (2026-07-15): Template Lab preview can render through the LED Studio room view. Pad adds read-only `GET /static/sim/ledsim-view.js` (disk file; 404 if missing) and `GET /api/sim/profile` (example-inherited merge mirroring `LedSimService.profile_state`, JSON-only — no `led_sim_engine` import). Lab UI: Strip|Room toggle (`localStorage` `labPreviewMode`), dynamic import + `createLedSimView` / `destroy` on toggle, same preview RAF clock feeds both canvases, fail-soft note when assets are gone, honesty caption “preview only.” Beat meter untouched. Covered by `tests/test_led_pad_service.py` (`SimRoomHookupRouteTests`); JS is manual-smoke / Claude e2e after pad restart.
- AWR-247 (2026-07-15): Template Lab Preview default window is the draft's full `cue_beats` (was `min(cue_beats, 8)` so every effect looked like 2 bars). Lab UI: 2 bars / 4 bars / Full cue segmented control (`localStorage` `labPreviewLength`, default full); posts `beats` on `/api/lab/preview`. Strip and Room share the same longer frame set. Beat meter still derives from frame math. Covered by `tests/test_led_pad_service.py` (`test_lab_preview_default_beats_equals_full_cue_beats`).
- AWR-248 (2026-07-15): Pad / Lab / Sim cross-nav. Route tabs on pad (`index.html`, `lab.html`) and sim (`led_sim_assets/index.html`) link Pad (`:8766`), Lab (`:8766/lab`), and Sim (`:8767`) as plain same-tab hrefs (canonical defaults). Sim stage room-size chip opens Layout + focuses room width.
- AWR-250 (2026-07-15): Sim **Use** persists `active_layout` immediately (fetch-fresh disk profile → set pointer → POST; unsaved knobs/geometry stay local). Lab Room preview re-fetches `/api/sim/profile` on Preview and on toggle-to-Room (~2s TTL); recreates the view only when the active-layout fingerprint changes. Picker shows “Press Use…” when selection ≠ active.
- AWR-251 (2026-07-15): Lab+Sim save-story overhaul. Lab Accept/Reject persist the current editor state; `/api/lab/update` stays runtime-only (no `drafts.json` write); draft-switch keeps editor-local memory with a truthful dirty badge; Sim Save as/Rename/Delete/Use persist library structure immediately; picker selection previews on stage with editing disabled until Use; Save layout → Save changes. Covered by `tests/test_led_pad_service.py` / `tests/test_led_sim_service.py` plus `tools/awr251_save_story_journey.mjs`.
- AWR-253 (2026-07-15): Lab Room preview presentation mode. `createLedSimView(canvas, profile, options?)` gains an optional third arg; `tools/led_pad_assets/lab.js` passes `{presentation: true}` (`ensureRoomView`), and `tools/led_sim_assets/ledsim-view.js` guards its editor chrome so the small Lab preview draws only room walls, the strip path, the 360 LEDs, the junction marker + "center · control box" label, and the start/end markers. Suppressed: segment ticks + tick labels, boundary/room-size labels, the clickable room-size chip, vertex handles, and the unplaced/excess warning text (guard clauses, no drawing-function fork; optics `transformColor`/`applyBleed`/`drawEmitter` untouched). Default `{}` keeps the sim editor view byte-identical (the sim page passes nothing). JS is manual-smoke / Claude e2e after pad restart; no bridge/output behavior changed.
- AWR-266 (2026-07-16): Sim stage matches Lab Room preview. Shared `ledsim-player.js` clock (pad serves `/static/sim/ledsim-player.js`); Sim Play defaults to presentation; Layout tab restores editor chrome; zoh/slew not applied on screen. Covered by `tests/test_awr266_sim_lab_parity.py`.
- AWR-269 (2026-07-16): Pad-process live-play mirror (R7 / A3). `TeeTransport` + bounded ring in `tools/led_pad_mirror.py` wrap dry-run and real transports inside `PadPlayback` (O(1) append only on the runner thread). SSE `GET /api/mirror/stream` fans out on pad handler threads. Lab **Watch live playback** paints through the same ledsim-view path. Does not mirror bridge show output; bridge runtime untouched. Gates in `tests/test_led_pad_playback_mirror.py`.
- AWR-270 (2026-07-16): R8 one-shell chrome across Pad/Lab/Sim. Shared LIGHTING CONSOLE eyebrow + matched Pad|Lab|Sim route tabs; N9 relative pad↔lab and absolute sim links (`:8767`/`:8766`); pad lands on first non-empty phrase shelf; honest empty-state copy; Sim stage + `?` what-is intact. Assets/CSS only — no playback/save/engine change. Covered by `tests.test_led_ui_integrity.Awr270OneShellTests`.
- AWR-271 (2026-07-16): R9a Lab editor mounts inside Pad shell. Shared `index.html` hosts `#view-pad` + `#view-lab`; `shell.js` switches Pad↔Lab in-place (pushState); `/` and `/lab` both serve that document (not a redirect). One `lab.js` store (`window.LabEditor`); Accept pipeline untouched; PadHealth multi-subscribe. Covered by `tests.test_led_ui_integrity.Awr271LabInShellTests` + `tools/awr271_shell_journey.mjs`. Bridge runtime untouched.
- AWR-272 (2026-07-16): R9b one verb pair. Lab primary: **Save draft** (unpublished only) + **Accept — adds it to your show** (AWR-260 promotion). Reject keeps the cue out of the show. "Save to show" + scary bridge-restart modal removed; Pad look push lives under secondary **Pad look edits** ("Push pad edits" / plain "next bridge start" copy). Reload effect code stays footer/secondary. Status chips unchanged; CAS/Discard/locked_palette intact. Covered by `tests.test_led_ui_integrity.Awr272VerbPairTests` + `tools/awr272_verb_pair_journey.mjs`. Bridge runtime untouched.
- AWR-273 (2026-07-16): R9c single live-fire + `/lab` redirect — **R9 complete**. Pad tile **▶ Play** stays the primary looping live-fire (session Loop). Lab **▶ Play once on lights** is a guarded one-shot via existing `/api/lab/play` with `loop=False` (Preview is the headline verb; Stop is obvious; ownership/dry-run/AWR-269 mirror unchanged; no second save path). `/lab` 302 → `/?view=lab` (never 404); sim Lab nav points at `/?view=lab`. Covered by `tests.test_led_ui_integrity.Awr273SingleLiveFireTests`, lab play-once cases in `tests.test_led_pad_service`, + `tools/awr273_live_fire_journey.mjs`. Bridge runtime untouched.
- AWR-254 (2026-07-15): Pad look-editor close dirty check. `closeEditor` in `tools/led_pad_assets/pad-ui.js` compares against `cleanSnapshot` (updated after a successful Save), not a separate open-time snapshot, so Save → close exits silently and only edits since the last save show "Discard unsaved changes?". Covered by `tests/frontend/test_led_pad_defaults.py` (`test_close_after_save_skips_discard_modal`, `test_close_with_unsaved_edits_shows_discard_modal`). Lab/sim JS untouched.
- AWR-255 (2026-07-15): Pad+Lab stale-config banner. Bridge status has `process.pid` / `written_at` but no `started_at` (confirmed; bridge runtime untouched). Pad `GET /api/runtime_status` adds `config_stale` via pure `compute_config_stale` (live config mtime vs `ps`-resolved process start; weaker post-Apply `commit_proxy` when start is unknown). Shared `PadConfigStale` UI on pad and lab: persistent warn while stale, quiet green when fresh. Covered by `tests/test_led_pad_service.py` (`ConfigStaleComputationTests`).
- AWR-261 (2026-07-16): Status freshness (master-plan R2 / FABLE-3 A2). Pad no longer treats any parseable status file as live — `bridge.live` requires `(now - written_at) < 5s` (OwnershipGate rule). Stale/missing → `not_running` calm banner; fresh file keeps green/warn/`can't-tell` only for dead-pid. Pad-side only (`tools/led_pad_web.py`, `pad-core.js`, `pad.css`). Covered by `ConfigStaleRuntimeStatusTests`.
- AWR-262 (2026-07-16): Pad control truth (master-plan R3). `controls_for` emits curated `EFFECT_VISIBLE_KEYS` only (comet-motion / retrigger / continuous). `heads` UI deleted (allowlist+validator still tolerate). Enum choice word labels; renderer-switch drop warning; Locked-palette `[hidden]` CSS fix. Drift barrier: `tests/test_awr262_control_truth.py`. **Did not** change `REALTIME_EFFECT_PARAM_KEYS` (A1 live-config gate stayed available).
- AWR-263 (2026-07-16): Lab control truth + New cue clone (master-plan R4). New dialog = display name (auto-slug) + start-from working draft; `param_specs` gains `select`; Zone/Texture/Color Mode worded dropdowns; firework specs → spark_a/spark_b family; draft labels preserved (`cycle_beats` → "Color cycle (beats)"); JSON blur re-syncs controls; preview retunes while Preview runs; search relaxes status chips with note; self-test clears on draft switch. Covered by `tests/test_awr263_lab_control_truth.py`. Lab-lane only; no bridge restart.
- AWR-264 (2026-07-16): Language + hierarchy rename-only (master-plan R5). Musician-legible CONTROL_META + pad/lab/sim copy (Flashes per second / Flash length (%) / Save to show / Match the track / …). Look tiles lead with human effect name; machine id demoted; `legacy_color_suffix` colorway chips (A5). Pad rename/duplicate auto-slug. Sim: Saved look, corners, Reverse direction, Seed behind Advanced, human picker labels. Standing gate `tools/check_ui_jargon.py` (hard check). Zero lighting behavior change; no restarts in-round. Covered by `tests/test_awr264_language_hierarchy.py`.
- AWR-265 (2026-07-16): Color-clone collapse COMPLETE (master-plan R10). Steps 0–3 + FINAL: all RT color-suffix clones deleted from example+live; `legacy_color_suffix` bank gone; pad Legacy tab hides when empty. Residual cyan-white / blue-ice / blue-twinkle pairs promoted into in-rotation `blue_cyan` by reordering `scale_stops` so `ice` sits between `cyan` and `blue` (existing cyan→blue multi ends preserved; slots also carry exact ice + reserved white). Living gate: `tests/test_awr265_color_clone_collapse.py` color-level A/B. Tools `tools/awr265_color_clone_collapse.py` / `tools/awr265_step3_delete_clones.py` stay runnable-honest on clone-free configs. Config-only (no `led_color_engine.py` edits). Loader `available=True` on example+live. Bridge was stopped; no restart by implementer.
- AWR-256 (2026-07-15): `rt_post_drop_firework_remnants` wires `ember_hold_beats` (default 8, clamp 1..32) and `ember_decay_beats` (default 0 hard cut, clamp 0..8). Shared `_drop_chase_sparkle_field` keeps default hold byte-identical to AWR-215; longer holds map onto the classic 8-beat density curve (no comet half). Dead `dim_beats` removed from allowlist + pad `CONTROL_META`. Covered by `PostDropFireworkRemnantsTests` in `tests/test_govee_frame_renderer.py`. Bridge restart required to load live params; implementer did not restart.
- AWR-258 (2026-07-15): Data-integrity round. Lab writes take the service lock + optional `updated` CAS (409 `stale_entry`); pad Save includes `locked_palette`; sim Save carries `base_mtime` (409 `stale_profile`), rotates `.bak-*` (keep 5), and refuses overwrite while `profile_error`; beforeunload on lab/pad/sim; lab reconnect stashes dirty fields; rotating snapshots for `config/led_lab/*` on drafts write. Covered by `tests/test_led_pad_lab.py`, `tests/test_led_sim_service.py`, `tests/test_led_ui_integrity.py`. Bridge runtime untouched.
- AWR-259 (2026-07-15): Pad integrity tail (master-plan R1). Pad look Save CAS via `_pad_meta.looks[<name>].updated` (409 `stale_look`; UI Reload re-opens editor); top-bar **Discard all changes** with honest whole-draft confirm + dirty-look count; Lab `_last_lab_applied` persisted to `led_lab/last_applied.json` (Accept after restart still snapshotted); `snapshot_fallback` + Lab UI note when Accept has no snapshot; shared `EDITOR_FIELDS` constant for pad dirty/save parity. Covered by `tests/test_led_pad_service.py`, `tests/test_led_ui_integrity.py`. Bridge runtime untouched; no pad/bridge restart by implementer.
- AWR-260 (2026-07-16): Accept wires a lab draft into production immediately. `lab_accept` persists status=accepted, writes a realtime look with `scene_ref=lab:<draft>`, places it in the `target_role` bank (or the pad **Untagged** shelf = `_pad_meta.drafts` when untagged), auto-Applies via the existing commit path, and appends `led_reload_looks`. The frame-engine child renders `lab:*` / `lab_adapter` through `govee_lab_adapter.LabProductionAdapter` (fail-dark + ~10 ms budget disable-for-session). Adapter resolves draft entry **name → fn** from sibling `drafts.json` (clone/Save-as rename case; fail-soft to name-only if drafts.json is missing). `led_reload_looks` reloads the look-director config and re-imports lab effects + the fn map off the push loop. Reject stays a status flip with plain copy. Covered by `tests/test_awr260_lab_accept_wirein.py`. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no bridge restart in-round.
- Template Lab persists draft metadata under gitignored `config/led_lab/drafts.json` and loads gitignored `config/led_lab/effects_lab.py` from the pad and (AWR-260) the frame-engine child via `LabProductionAdapter`. Pad lab playback still uses `lab_<name>` through `LabRenderer`; production accepted looks use `lab:<name>` and never mutate the baked `_EFFECTS` / `SLOT_EFFECTS` registries.
- Template Lab Round 1 adds three endpoints on `LedPadService` (`tools/led_pad_web.py`): `lab_update` re-applies params to the already-playing lab draft via the shared `PadPlayback.update()` path (no takeover, no `CueTimer`/`SyntheticClock` restart) and only applies when that exact draft is playing; `lab_switch` seamlessly reconfigures the shared playback slot from one already-playing lab draft to another (same `update()` path, beat keeps running) and refuses when nothing is playing or a pad look is playing; `lab_preview` renders frames offline through a fresh local `LabRenderer` (`render_preview_frames` in `tools/led_pad_lab.py`) and never touches `self._playback`, ownership, or the live renderer's effects. All three reuse `_lab_play_spec`'s reload-and-fail-dark behavior for a broken sandbox module. No code-level strobe rail was added (discipline-only, per operator decision).
- LED Pad exposes `GET /api/access` (shared with Laser Pad via `tools/pad_access.py`), which reports the pad's current bind address/loopback state and, when non-loopback, a best-effort LAN URL for a QR "Open on another device" affordance. It never changes bind behavior itself; exposing the pad to the LAN stays an explicit `--host` operator action.
- AWR-193 pad/lab overhaul (2026-07-10, software-tested): the lab name-collision check fires on CREATE only, so an entry whose name became a production effect stays saveable and can be archived (`POST /api/lab/archive` → new status `promoted`; `lab_list` decorates `production_collision`). Play/preview resolve name-first with the entry `fn` as fallback (`LabRenderer(fn_for=...)`, non-throwing resolver). `lab_accept` writes the last-applied pre-injection params into the entry in the same save that flips status (palette-injected colors never persisted; response carries `snapshotted`). `lab_list` also decorates `effective_param_specs`/`spec_conflicts` via `led_pad_controls.effective_lab_specs` (CONTROL_META wins shared-key bounds). The pad server sends `Cache-Control: no-cache` on every response, runs a freshness watchdog (pure decision `freshness_restart_due`: watched-module mtime change stable ≥3 s AND playback idle AND pad not owning the LEDs → `os._exit(3)`, launchd relaunches), and records a live-config fingerprint sidecar `config/led_look_director.draft.base` (gitignored) that surfaces `live_changed` in `/api/config` — no auto-merge. UI: color pickers for rgb triplets/rgb-kind controls with palette-regime badges, shared `PadHealth` reconnect helper on both pages, promotion checklist moved to `docs/guides/led_pad.md`, traceback panel behind `?dev=1`, Delete in a danger zone. JS/UI behavior is code-review + manual-smoke covered only.
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
- blank-role hold guard coverage (AWR-157) lives in `tests/test_led_state_manager.py`
  (`BlankRoleHoldTests`): suppression + look retention while playing, no-op when not playing or
  no prior accepted decision, emergency blackout and the tactical pre-drop blackout both unaffected,
  knob-off byte-identical dispatch, and the Q-A log's edge-triggered INFO/DEBUG split. Config parse
  coverage lives in `tests/test_led_config.py` (`BlankRoleHoldConfigTests`). Software validation
  only — does not prove room-visible behavior.
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
  AWR-235 pins that a same-`role_key` repeat idle pass keeps `_led_idle_freewheel_since`
  and a playing anchor, that gated blackout/manual-override idle passes still
  clear it, and that a changed idle `role_key` re-dispatches and re-stamps the
  freewheel. This is software validation only.
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
  Tests 1-9 verbatim plus additional coverage, including AWR-159's manual-arm-visibility/refusal and
  predark reset-reason tests), `tests/test_state_manager_drop_presentation.py`
  (state_manager wiring integration: plan build, per-tick ladder/window, LED blackout owner
  `"drop_spotlight"` engage/release, Solo pad arm/disarm/veto/learn/cancel via real event dispatch,
  darkness guard, damper, the `enabled: false` byte-identity regression gate, and AWR-159's
  arm-key-staleness/feedback-truth coverage), `tests/test_led_config.py`
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
| rt_groove_heartbeat | _slot_rt_groove_heartbeat | groove | no | software-validated (AWR-156) |
| rt_post_drop_firework_remnants | _slot_rt_post_drop_firework_remnants | post_drop | no | software-validated (AWR-215/256: ember_hold_beats + ember_decay_beats; dim_beats removed) |

Non-slot (baked) frame effects added by AWR-156/AWR-161, registered in `_EFFECTS`:

| Scene ref | Fn | Safety class | Strobe | Status |
|---|---|---|---|---|
| drop_strobe_colorway | _drop_strobe_colorway | drop | yes | software-validated (AWR-156) |
| buildup_balloon_comet | _buildup_balloon_comet | buildup | no | software-validated (AWR-156) |
| rainbow_ordered | _rainbow_ordered | drop / post_drop | no | software-validated (AWR-161) |
| drop_firework_explosion | _drop_firework_explosion | drop | no | software-validated, contrast-gated (AWR-161) |

AWR-156 look-name rename (config only; the `Scene ref` column above is unaffected — `scene_ref`
never changed): the example config's `rt_drop_chase` / `rt_drop_nebula` LOOKS are now named
`rt_post_drop_remnant_chase` / `rt_post_drop_remnant_nebula` and live in `banks.default.post_drop`.

Patch E pairings:
- rt_drop_center_burst pairs explicitly to rt_post_drop_center_comet through `drop_pairs`.
- AWR-156: rt_drop_nebula no longer pairs to rt_post_drop_nebula — the `drop_pairs` entry was
  deleted as part of the bank recast (a post_drop-role look never fires a pair). Superseded line,
  kept for history: "rt_drop_nebula pairs explicitly to rt_post_drop_nebula through `drop_pairs`."
- AWR-161: rt_rainbow_drop pairs to rt_rainbow_post_drop; rt_drop_firework_explosion pairs to the
  existing rt_post_drop_firework_remnants (the AWR-149 explosion->remnants arc, now real) —
  both through `drop_pairs`.

All slot cues, `random_with_mono_chance`, and Patch F bank cleanup: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
Phase 3 renderer params: `rt_groove_chase`/`rt_groove_nebula` accept `loop_beats`; `rt_drop_chase`/`rt_post_drop_chase`/`rt_drop_nebula`/`rt_post_drop_nebula` accept `travel_beats` and `width`; `groove_center_chase`/`post_drop_firework_chase` accept `travel_beats`. Missing params preserve previous frames.
AWR-161: `hz`/`duty` are now dialable on all 18 migrated strobe effects (the non-slot chase/nebula/center-comet family plus `rt_post_drop_chase`/`rt_post_drop_nebula`/`rt_drop_chase`/`rt_drop_nebula`/`rt_post_drop_center_comet`), same defaults/caps as `drop_white_aggressive` (hz 0.5-10 default 6.0, duty 0.05-0.5 default 0.3). `rainbow_ordered` accepts `width`/`cycle_beats`/`rainbow_span`/`travel_per_beat`/`loop_beats`. `drop_firework_explosion` accepts `surge_beats`/`bg_level`/`bg_hold`/`color_a`/`spark_a`/`spark_b`/`sparkle_density`/`sparkle_size`/`sparkle_life_s`.
The stable-hue sparkle (rt_drop_chase), center-burst 0-2/2-4 accent band split (rt_drop_center_burst), Patch E1 looks (rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula), Patch E2 center-comet (rt_post_drop_center_comet), Patch E3 ambient twinkle (rt_twinkle), Patch S probabilistic solid-color outcomes, and Patch F generic-default bank rotation still need operator hardware visual sign-off. AWR-161 additions also await hardware sign-off: the ten migrated strobe gates' Hz feel at the mirrored config, the rainbow pair (rt_rainbow_drop/rt_rainbow_post_drop), the firework explosion (rt_drop_firework_explosion), and the center-burst all-pixel fix.

Known risks:
- API/cloud rate limits
- realtime protocol/device specificity
- confusing local H612D behavior with all Govee devices
- beat-synced motion smoothness issues
- config schema drift
- un-analyzed tracks with no phrase segments can still hold the previous LED look after an active content change, but only until the 16-beat / 8-second backstop; live visual comfort is still hardware-unvalidated
