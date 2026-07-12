---
doc_status: current
truth_level: code-verified
last_verified_commit: b16792a
last_verified_date: 2026-07-10
validation_scope: software-only; laser color held-snapshot CH8/CH9 forwarding and the 2026-07-07 menu/follow-LED/brightness-floor/CH9=90 layer verified in tests, hardware-unvalidated (chase CH8 values await live eyeball; CH3/CH4 untouched); AWR-186 USB gate-fix (Enttec positive-identity port detection in enttec_dmx_pro.find_enttec_port + make_stick pack-config fail-closed) software-tested 2026-07-10 — no behavior change in this doc's scope, no hardware action
---

# Laser Subsystem

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: configured local rig only

Purpose:
- Choose laser roles/scenes and execute configured MIDI triggers with blackout, cooldown, and override behavior.

Audit P1 (2026-07-03): `MidiOutput.panic()` documentation now matches the queue-drain/all-notes-off
mechanism, and `LaserConfigResult` no longer documents the obsolete `dependency_missing` loader
reason. Laser runtime behavior is unchanged in this patch.

Audit P2 (2026-07-03): pack-status overlay diagnostics are SoundSwitch/pack-driver reporting only;
Laser Director policy and laser MIDI execution are unchanged.

Audit P4 (2026-07-03): laser MIDI send-error degradation can recover by reopening the output port
after a 5-second cooldown; startup/dependency degradations stay fail-closed. Executor bank
selection skips disallowed high-impact or missing bank entries when a usable replacement exists,
and blocked/missing selections restore the previous cursor/active-scene state before reporting the
failure. Scene config now rejects unknown `fallback_scene` references and negative
`cooldown_beats`. `pre_drop_scene` is removed from the live personality model and tracked example,
but leftover keys in ignored local configs are tolerated as deprecated. Laser Pad's master enable
toggle now also appends the live `set_laser_director` runtime command while saving the draft.
All of this is software-tested only; no laser hardware, MIDI device, SoundSwitch, Rekordbox, LED,
Govee, DMX, or Enttec validation was performed.

Offline SoundSwitch pack boundary:
- Task 2 deterministically exports and independently verifies the repo-local canonical pack for the pinned SoundSwitch 2.10.3 canonical RAVE project, including the seven-class F-3 control crosswalk. Live export reconciles saved-project inventory dynamically; the old exact-count snapshot is proof-only. It does not replace or alter Laser Director policy, MIDI execution, mappings, blackout behavior, or status.
- The pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender exist. `LaserSceneExecutor` has one injected backend slot; startup selects legacy MIDI, none/dry-run, or verified pack/Enttec from the optional default-off config. Physical MIDI and direct DMX remain mutually exclusive.
- Pack backend startup, `StateManager` scripted frame driving, commands, copied RW-5 status, and native pack Autoloop scene-edge handoff are implemented in software. Laser policy, MIDI execution, blackout, and configured mappings stay unchanged; the executor now exposes the already-selected Autoloop scene so the pack driver can resolve canonical Autoloop bindings even on no-new-edge ticks when SoundSwitch is absent. Hardware remains unvalidated.
- Blackout-mask migration Package 1 is implemented/software-tested: smart-side blackout owners and pending drop-window latches survive pack-backend note rejection, and `StateManager` ORs that smart-side state with the existing manual MIDI-input blackout at the single pack-player mask writer. Manual blackouts remain owned by the MIDI-input binding refcount and survive smart-side lifecycle wipes. MIDI-mode accepting-backend note on/off sequences are unchanged. No laser hardware, SoundSwitch, Rekordbox, LED, Govee, MIDI device, DMX, or Enttec validation was performed.
- Laser color plumbing Package 4 is implemented/software-tested: StateManager samples LED color state into a pure `LaserColorSnapshot`, the color engine holds that snapshot, and the pack player reads it on every drive so CH8 stays palette-driven on every healthy native Autoloop frame until the next accepted LED automation trigger updates it or the engine has no snapshot. The chart's fixed-color half LANDED and was ENABLED by operator decision 2026-07-04 (`config/laser_color_map.json`: calibrated CH8 bands W,R,Y,G,C,B,M from the operator's virtuallasernode camera calibration; the quantizer's `purple` anchor is (255,0,255) — the fixture's band 28-31 is magenta). `fixed_ch9` and the effect families remain null pending operator data, so CH9 stays authored pass-through everywhere; the supervised first visual pass is still pending. Scripted, diagnostic, masked, static-override, and CH11 behavior stay unchanged. Hardware remains unvalidated. A same-pass review landed three riders: `LaserColorSnapshot.ch9` is now `Optional[int]` and `_merge_color_snapshot` writes CH8/CH9 independently (a null channel leaves that channel authored); the map gained `fixed_ch9` (null by default) for the quantized-color path's CH9, eased through the existing settle logic; the white path's CH9 is always `None` (preserves authored speed) instead of a hardcoded 0. All-null config still injects nothing on either channel.
- Laser color menu/follow-LED layer LANDED 2026-07-07 (`docs/plans/active/laser_color_menu_spec.md`, software-tested / hardware-unvalidated): `config/laser_color_map.json` now carries `fixed_ch9: 90` and a per-mood `menus` block. `LaserColorMap.from_dict` parses each mood's list into nested tuples of `("solid", name)` / `("chase", ch8, (names...))` entries. `_target()` picks from the mood's menu after the unchanged white / white_sand / rainbow early returns: it follows the LEDs' actual last-emitted color (`led_color_engine.color_state()["live_rgb"]`, quantized to the nearest fixed color), applies a 3-tier brightness floor (`_BRIGHTNESS`: white=3; cyan/green/yellow=2; blue/purple/red=1) so the laser is never picked dimmer than the LEDs, and on `drop_phase=="drop"` fires the mood's eligible chase (else tracks the matching solid). Empty eligible → brightest option (never dark). Unresolved CH8 or any invalid/missing/disabled state → `None` (authored CH8/CH9 pass through). Moods with no menu keep the legacy single-solid nearest-fixed pick. "LEDs white → laser white" is the EARLY white return, not the brightness floor. `led_color_engine.py` stashes `_last_emitted_rgb` in both `resolve_color` and the active-engine `_v2_resolve_color`, clears it on v1↔v2 switch, and surfaces it via `color_state()["live_rgb"]` (pure read). `state_manager._sync_laser_color_if_needed` adds the QUANTIZED live_rgb bucket to the re-sync signature (raw RGB would flap it every 200 Hz tick). **CH3/CH4 are never read or written anywhere** — the chase effects are authored at CH3=0/CH4=10 in the pack, so some chase CH8 values may render slightly differently live (accepted operator eyeball risk).
- Laser round AWR-170 LANDED 2026-07-09 (`docs/plans/active/laser_tier_chase_prechorus_spec.md`, software-tested / hardware-unvalidated), carrying AWR-162 (B) + (D.2). **(B) per-tier chase divisions:** a `menus` chase entry's `chase` may now be a `{"standard"|"intense"|"monster": <ch8>}` dict as well as a single int. `LaserColorMap.from_dict`/`_parse_menus` resolves the dict to a `("chase_tiered", {tier: ch8}, names)` entry (missing keys → standard → first present; all-junk → skip, fail closed); `_target`/`_pick_menu_entry` resolve CH8 by the drop's F2 energy tier at `drop_phase=="drop"` (`None`/unknown/`small` → standard). `config/laser_color_map.json` seeds `crimson` + `v2:EMBERCORE` with the operator 100→116→140 ladder; every other menu keeps its single int and renders byte-identical. `state_manager._laser_color_drop_tier` plumbs the tier one hop (a push-loop-safe `f2_plan.for_drop` lookup, folded into the laser-color re-sync signature). **(D.2) pre-chorus laser blackout:** the new `pre_chorus` smart mask owner (see `laser_blackout_authority.md`) darkens lasers for `f2.pre_chorus_laser_beats` before every chorus phrase start; `smart_phrasing` computes the window off the RAW chorus markers (uncollapsed) and `smart_rearm._pre_chorus` holds/releases the owner with a leaked-window guard. Held-static ducks dark for the window and restores after (Part C chosen behavior). F2-off / scripted / tier-less / absent-config ⇒ byte-identical to before. Tests: `tests/test_laser_tier_prechorus.py`, `tests/test_state_manager_pack_driver.py`.
- Laser round AWR-206 LANDED 2026-07-11 (software-tested / hardware-unvalidated; STAGED — activates at the operator's next bridge restart). Fix round after the first attempt failed independent review (its relaxed executor branch was unreachable — the director returned idle one layer above it). The 4-beat smart-drop **pre-drop blackout** now arms on the *reachable* path: when the autoloop is mid-re-arm the `LaserDirector` still returns its `autoloop_not_ready` idle decision (no scene), but now tags that decision `blackout_arm=True` (`laser_director.py`, priority-7); the `LaserSceneExecutor` idle path then arms the manual blackout note on the relaxed gate `_passes_blackout_gates` = the strict `_passes_automatic_gates` MINUS `autoloop_ready` (`laser_executor.py`). Scene MIDI is unchanged (still strict-gated; no scene is ever selected on this path). Why: at the pre-drop instant during real mixing the SoundSwitch autoloop is normally mid-re-arm, so `autoloop_ready` was False and the strict gate silently ate the blackout (live triage: 30 arm intents / 0 sends). A blackout note only needs a genuinely live deck, not a render-ready autoloop. Both arm signals (`smart_drop_blackout_arm`, `smart_phrasing_blackout_arm`) take this path; the manual blackout note needs no scene mapping; every release path is untouched (fail-open — drop crossing, StateManager's no-drop-decision safety net at `state_manager.py:4882-4893`, mask owners, lifecycle resets, shutdown zeroing); the arm signal is level-held at 200 Hz so the skip reason logs at INFO throttled to once per changed failing-condition tuple. Authority: `docs/architecture/laser_blackout_authority.md`. Tests: `tests/test_laser_executor.py` (`test_integrated_director_executor_arms_blackout_under_autoloop_churn`, `test_blackout_arms_under_autoloop_churn_*`, and siblings).
- Package 4 review Rider B: `LEDDispatchCoordinator` now accepts an explicit `white_templates` override (used ahead of the never-populated `config.laser_color_white_templates` attribute); `__main__.py` loads `config/laser_color_map.json`'s `white_templates` at the coordinator's construction site, so editing that JSON actually changes white-moment detection instead of only feeding the coordinator's own hardcoded defaults.
- Drop presentation policy Package 3 (AWR-119, 2026-07-04; AWR-135/AWR-138/AWR-139 updates 2026-07-07) is implemented/software-tested: the behavior authority is `docs/architecture/drop_presentation_authority.md`. `soundswitch_laser_player.py` gained `LaserPackPlayer.set_base_suppressed(held)` for the `leds_only` presentation — it withholds the automatic base exactly like the existing `missing_selection` path (ZERO base, held static layers still apply, masks/blackout untouched) WITHOUT clearing `_selection`, so the drop resumes rendering the instant suppression lifts. The ladder/session/learned-store/window-machine logic itself lives in the pure module `drop_presentation.py`, wired from `state_manager.py`: per push tick it feeds beats-to-next-drop, phrase role, the Laser Director's own `drop_crossing` decision as the raw impact signal, and a darkness-guard signal (pack live + last autoloop base diagnostic-free, combined with Package 1's `mask_owners_active()` and the MIDI-input blackout snapshot) into a `WindowMachine` that applies `leds_only` suppression or (for `lasers_only`) an LED blackout held under the Package-2 owner key `"drop_spotlight"`. `leds_only` suppression follows the real drop/post-drop role end; only a later true-drop impact (runway > 0.0, or manual Solo / hot-cue override) inside an open window asserts its own planned presentation and re-stamps the cap from that impact. AWR-143 (2026-07-07): the raw `drop_crossing` impact signal is now cross-checked against `sp_state.smart_drop_crossing` before it can count as a presentation impact (`impact_now = bool(impact_now and sp_state.smart_drop_crossing)`), because post-AWR-140 the Laser Director also emits `reason="drop_crossing"` for the capped 2nd-chorus LABEL re-arm (no real smart-drop marker); without the gate that label re-arm mis-re-entered/extended the presentation window ~192 beats. The AWR-140 drop LOOK is unchanged; only presentation-window bookkeeping is gated. Runway-less markers still fire their laser look bursts, but cannot re-roll the section's fixture split. `drop_window_cap_beats` defaults to 192 and is only a stuck-role backstop. Native Autoloop status reports intended-dark base as `base_suppressed`, not `unsupported_layout`. `enabled: false` in `/drop_presentation` (config) is the master regression gate — every drop renders `leds_plus_lasers` exactly as today, byte-identical. Known, reported limitations: impact detection is inert if the Laser Director object is never configured at all (matches the operator's actual setup, where it IS configured); tracks without chorus/post-drop phrase markers can still leave `post_drop` after the existing short post-drop hold; a `lasers_only` solo that re-enters mid-window fires at impact without the LED pre-dark countdown. Hardware remains unvalidated. AWR-159 (2026-07-09) fixed two others: the "manual interaction" fail-open trigger is now wired (a Solo-pad press while a window is open cancels it, one tick later); and a MANUAL arm's own darkness guard no longer depends on the Laser Director's enable flag (only `base_live`/unmasked/role) and refuses visibly instead of silently downgrading when even that fails — see `drop_presentation_authority.md` for the full behavior. AWR-220 (2026-07-12): when F2 laser tiers exist, personality lasers require the interim `drop_laser_qualifies` gate (intense/monster by `laser_tier_min`, default 2) plus the same `laser_ratio` cap; tier-less tracks stay on the legacy ratio ranking byte-identical. A section verdict latch keeps a true-drop `leds_only` ruling on pack-base suppression through coarse chorus re-arms after the window released on a role gap — drop-look lasers outside an open window follow that section verdict; see `docs/architecture/drop_presentation_authority.md` §Section verdict latch.
- Smart Drop marker selection is handled in the shared `SmartPhrasingEngine`:
  raw ANLZ drops still feed phrase labels, while runtime smart-drop crossings
  use the selected list that collapses 32-beat-spaced marker clusters to the
  first marker of each drop section. The first live tick after a reset fires an
  exact drop beat once, without rounding near-misses forward.

Authoritative code:
- `laser_config.py`
- `drop_lifecycle.py`
- `laser_models.py`
- `laser_director.py`
- `laser_executor.py`
- `laser_decision_log.py`
- `laser_color_engine.py`
- `midi_output.py`
- `personality_resolver.py`

Key symbols:
- `LaserConfig`
- `DropLifecycle`
- `LaserScene`
- `LaserDirector`
- `LaserSceneExecutor`
- `LaserColorEngine`
- `MidiOutput`
- `PersonalityResolver`

Runtime flow:
- inputs: `LaserContext`, smart phrasing state, runtime laser commands, config scenes/personalities
- decisions: role selection, gated drop/post-drop lifecycle, manual override, blackout, cooldown, bank/personality rotation
- outputs: MIDI note/CC/pulse/hold events through `MidiOutput`
- `drop_lifecycle_mirror` defaults on. Allowed predecessor-label impacts and
  real smart-drop crossings hold for the configured flat `drop_impact_beats`.
  After the first anchor, one label-only chorus-to-chorus boundary may re-fire
  a capped second drop impact; later chorus boundaries demote to
  `post_drop`/fallback drop cycles on autoloop ticks. Drop and post-drop cycle
  banks use usable-only shuffle bags that reset per track; a static configured
  drop scene remains valid for the at-anchor impact so an empty cyclable bank
  does not make the hit dark.
- Setting `drop_lifecycle_mirror` to false preserves the previous ungated crossing and fixed post-drop-hold path (flag-OFF is byte-identical to pre-change EXCEPT the resume transition, which now also resets the executor: a benign phrase-bank reshuffle + active-scene clear; no dark, no drop leak). Director and executor lifecycle state reset on master/track/stop/resume transitions; director state also resets on scripted/idle transitions and personality application rebuilds it.
- Blackout-mask migration: the transition blackout — the held `manual_blackout_on/off` note refcounted by `breakdown`/`master_switch` owners in `LaserSceneExecutor`, plus the Smart-Drop drop-window pending — now also drives the pack player's frame-level blackout through `StateManager._drive_pack_output`. Backend note rejection no longer discards smart owners; accepted MIDI backends still receive the same note on/off sequence. The manual laser-pad/web blackout stays in the separate MIDI-input binding refcount and must not be routed through executor `_mask_owners`, because executor lifecycle wipes intentionally clear only smart-side covers.
- Laser color Package 4: the mapper is pure in-memory math and publishes an immutable held snapshot. `LaserPackPlayer` merges the current held snapshot by copying the rendered Autoloop frame and writing only CH8/CH9; missing/no-op snapshots, disabled config, null table entries, scripted tracks, diagnostics, blackout, and static override all fall back to authored pack output.

Config:
- `config/laser_director.example.json`
- `config/laser_color_map.json` is ENABLED with a calibrated fixed-color CH8 table, `fixed_ch9: 90`, and a per-mood `menus` block (2026-07-07); further CH8/CH9/menu updates are config-only and require operator live validation. Chase CH8 values (172/68/100/164/72) and CH9=90 await a supervised live eyeball.
- local ignored `config/laser_director.json`
- launcher environment for `RBSS_LASER_CONFIG`
- personality knobs: `drop_lifecycle_mirror` (default `true`),
  `drop_impact_beats`, `max_drops_in_a_row` (caps drop hits per section), and operator-reserved
  future `post_drop_cycle_beats`; laser cycle cadence still comes from autoloop
  ticks. Deprecated leftover `pre_drop_scene` keys are ignored for load
  compatibility.
- `/drop_presentation` top-level block in `config/led_look_director.example.json` (`enabled`, `laser_ratio`, `laser_tier_min`, `opening_tracks`, `led_predark_beats`, `drop_window_cap_beats`, `hotcue_marker`, `solo_learn_threshold`, `gearshift_bpm_jump`, `record_min_drops`, `ws_handoff_enabled`); loaded independently of the main LED config's validate/build pipeline via `led_config.load_drop_presentation_config()`, so an unrelated `looks`/`banks` config error never blocks hot-cue tags or the presentation policy.

Laser Pad (operator companion tool):
- `tools/laser_pad_web.py` (local web service), `tools/laser_config_ops.py` (config read/write
  helpers), `tools/laser_pad_assets/` (UI assets), `scripts/laser_pad.py` (launcher), LaunchAgent
  `launchagents/com.bbui.laser-pad.plist` (always-on background launch), operator guide
  `docs/guides/laser_pad.md`. Tracked under the `laser_pad` change contract in
  `docs/agents/change_contracts.yml`.
- The pad edits laser config and personality selection through a local browser UI. Most changes
  write config that the bridge picks up separately (hot-reload or restart), the same way any other
  config edit does. The master `enabled` toggle is the exception: it also appends a
  `set_laser_director` runtime command to the bridge command file so the live director follows the
  draft toggle immediately; append failure returns an error instead of success.
- Status: implemented / software-tested / hardware-unvalidated.

Tests:
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` if pytest is available
- otherwise inspect `tests/` and run relevant unittest equivalents
- lifecycle coverage: `tests/test_drop_lifecycle.py`, `tests/test_laser_director_lifecycle.py`, and `tests/test_laser_executor_lifecycle.py`
- blackout re-wire coverage: `tests/test_laser_blackout_rewire.py`
- laser color plumbing coverage: `tests/test_laser_color_engine.py` (includes the per-channel-independent CH9/`fixed_ch9` rider tests)
- Rider B (white-templates plumb) coverage: `tests/test_led_dispatch_coordinator.py`
- drop presentation policy coverage: `tests/test_drop_presentation.py` (the authority doc's Required Behavior Tests 1-9 plus runway/determinism/config coverage, all pure/hardware-free, plus AWR-159's manual-arm-visibility/refusal and predark reset-reason coverage), `tests/test_soundswitch_laser_player.py` (base suppression), `tests/test_filepath_resolver_hotcue_tags.py` (hot-cue DB-read wiring and degradation), `tests/test_state_manager_drop_presentation.py` (state_manager wiring integration: plan build, per-tick ladder/window, Solo pad arm/disarm/veto/learn/cancel, darkness guard, damper, the `enabled: false` byte-identity regression gate, AWR-159's arm-key-staleness/feedback-truth coverage)
- transitional mapping check: `python3 tools/check_laser_midi_sync.py`
- Audit P4 coverage: `tests/test_midi_output.py`, `tests/test_laser_executor.py`,
  `tests/test_laser_config.py`, `tests/test_laser_config_deprecation.py`,
  `tests/test_laser_pad_web.py`, and lifecycle/status regression suites cover send-error recovery,
  bank-gate cursor restore, config validation/deprecation, blackout-mask refcounting, and Laser Pad
  live-toggle command append behavior.

Change contract:
- If modifying policy, inspect `laser_director.py`, `laser_models.py`, and smart phrasing state usage.
- If modifying execution, inspect `laser_executor.py`, `midi_output.py`, and blackout behavior.
- If modifying the shared drop resolver, preserve flat-window parity with the existing StateManager LED resolver without redirecting live LED behavior through it.
- If modifying drop presentation, inspect `docs/architecture/drop_presentation_authority.md` first (the acceptance oracle), then `drop_presentation.py`, the `state_manager.py` wiring, and `soundswitch_laser_player.py`'s base suppression. Follow the `drop_presentation` change contract in `docs/agents/change_contracts.yml`.
- Update this card, feature status, validation matrix, and hardware validation log if manual testing occurs.

Known risks:
- laser safety assumptions
- MIDI mapping drift
- blackout override mistakes
- drop/post-drop gate or teardown drift between director and executor
- treating one fixture/mapping as generic laser support
