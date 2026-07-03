# Codex Implementation Spec - 2026-07-03 Codebase Audit Fix Queue (P1-P4)

status: planned
last_verified_commit: 30bbb98
owner: operator (Brandon) via Claude Fable 5 audit session 2026-07-03

Execute patches **in order, one commit per patch** (P1 → P2 → P3 → P4). Every claim below was
re-verified against HEAD `30bbb98` during the audit session; labels: [confirmed] = read in current
code or executed, [assumed] = inferred, stated where load-bearing.

Baseline before any change: `python3 -m unittest discover tests` → **2749 tests, OK
(skipped=5, expected failures=1)** [confirmed, ran 2026-07-03].

## Part A - Context & Root Cause (verified; read, do not implement)

- **A1 [confirmed]** `__main__.py:1266-1285`: `_toggle_smart_drop` / `_toggle_smart_breakdown`
  return `None` on both success and `queue.Full`. `runtime_status.py:616-628` `_invoke_callback`
  treats only an explicit `False` as failure, so a dropped toggle event reports OK to the operator
  (`commands.last_error` stays empty). Every sibling callback (`_toggle_laser_director` etc.,
  `__main__.py:1288+`) returns `bool`.
- **A2 [confirmed]** `__main__.py:1214,1652`: `OS2LInjector` is constructed and `start()`ed
  unconditionally. It tails `/tmp/rbss_os2l_inject.jsonl` (`os2l_injector.py:22-23`) every 0.1 s and
  injects any appended packet into the live SoundSwitch socket. It is validation tooling running
  ungated in every live session.
- **A3 [confirmed]** `state_manager.py:3975-3990` and `4198-4213` (`_drive_pack_output`,
  `soundswitch_connected` branches): `_publish_pack_status(... input_degraded=False,
  static_held=False, blackout=False ...)` is published even while the MIDI input group holds
  static layers or blackout. DMX output is genuinely ZERO there (correct), but the status surface
  hides the held operator overlay, so "why is my held look dead?" cannot be diagnosed from status.
- **A4 [confirmed]** `led_look_director.py:230-234`: `commit_role()` calls
  `_automation_decision_for_role(role)` **without** the `diy_eligible` predicate that `tick()`
  passes (`led_look_director.py:136-139`). `commit_role("drop")` is live via
  `state_manager.py:2432-2436` (`_led_drop_decision_for_anchor(commit=True)`), so a committed drop
  look can bypass the DIY-eligibility filter and pick a look the engine cannot color-inject.
- **A5 [confirmed]** `led_dispatch_coordinator.py:144-146` → `govee_realtime_runner.py:130-148`
  `force_deactivate()`: on realtime→cloud handoff the coordinator synchronously calls
  `self._transport.blackout()` + `.deactivate()` (UDP `sendto`) **on the caller thread**, and the
  caller is the 200 Hz push loop (`state_manager.py:4568 → trigger()`). Socket is non-blocking
  (`govee_realtime_transport.py:52`) so no hang, but it violates the AGENTS.md §6 push-loop
  no-socket-I/O invariant. The runner already owns an `_emergency` Event mechanism
  (`govee_realtime_runner.py:126-128`) that runs on the runner thread.
- **A6 [confirmed]** `rb_state_reader.py:336-349` `_tick_deck`: when the ANLZ pointer-chain read
  fails transiently (`_follow_pointer_string` returns `None`), `self._last_anlz[d]` is overwritten
  with `""` and **no** `ANLZ_PATH` event fires, while the independent title read on the same tick
  can still succeed and emit `TRACK_LOADED`. The recovered `ANLZ_PATH` then arrives on a later tick
  — after `_on_track_loaded` (`state_manager.py:3062`) already popped `_pending_anlz_path` — so the
  invariant "ANLZ_PATH before TRACK_LOADED" breaks for that load (resolution degrades to
  lsof/title) and the late path sits in `_pending_anlz_path` for the *next* load.
- **A7 [confirmed]** `TIMING_COMPENSATION_MS` (`config.py:73`, currently `0`) is multiply applied:
  scripted-arm path up to 3× (`state_manager.py:3453` `_arm_scripted`, `state_manager.py:3493`
  `_check_pending_arm` stale-snap branch re-adds on top of the already-compensated
  `arm.elapsed_ms`, `osl_output.py:323` `send_deck_load` adds again) and the push path 2×
  (`state_manager.py:4372` bakes it into `d.elapsed_ms`, then `osl_output.py:329` `send_elapsed`
  adds again — and the baked-in copy leaks into beat math, pack driver, and laser context, which
  never wanted OS2L compensation). Harmless at 0; a landmine for anyone tuning it. The value
  reaches `send_deck_load` via `object.__setattr__(arm_meta, "elapsed_ms", ...)`
  (`state_manager.py:3473,3496`) — an undeclared attribute on the mutable dataclass `TrackMetadata`
  (`models.py:34`, not frozen), read back via `hasattr` at `osl_output.py:323`.
- **A8 [confirmed]** `spectral_cache.py:60` `put_cached` writes one JSON per (path, mtime, size,
  beatgrid) forever; `evict_stale()` (`spectral_cache.py:101`) is called nowhere in the repo.
  Unbounded only when the operator opts into `RBSS_SPECTRAL_ENABLE=1`.
- **A9 [confirmed]** `midi_output.py:428-437` `_record_send_error`: one send error sets
  `self._degraded = True` and closes the port; `trigger()` (`midi_output.py:122-128`) rejects all
  subsequent messages. The only `_degraded = False` in the file is `__init__` (`midi_output.py:70`).
  One transient CoreMIDI error silently freezes laser scene changes until bridge restart.
- **A10 [confirmed]** `laser_executor.py:160-185, 445-469`: `_role_state_snapshot` is taken before
  selection, but `_restore_role_state` runs only on the role-cooldown gate. The
  `missing_scene_mapping` (:168-176) and `high_impact_blocked` (:177-185) gates return without
  restoring, leaving `_role_cursors[role]` advanced and `_role_active_scene[role]` set to the
  blocked scene — subsequent ticks re-return the blocked `active_scene`
  (`laser_executor.py:451-453`) and the role can stay dark until the next role change.
  `_choose_bank_scene_locked` (:456-469) also does not filter `safety_class`, unlike
  `_usable_bag_entries`.
- **A11 [confirmed]** Laser Pad master toggle: `tools/laser_pad_assets/index.html:23-25` tooltip
  says "Single tap enables or disables laser output immediately"; `setEnabled()`
  (`tools/laser_pad_assets/pad-actions.js:468-473`) only PATCHes the **draft** config
  (`tools/laser_pad_web.py:801 → apply_draft_patch:226-253`, draft file only). Even after the pad's
  save flow writes the real config (`laser_pad_web.py:284`), the hot-reload callback
  `__main__.py:1704-1760` only rebuilds personality resolver/provider — it never applies
  `cfg.enabled`. The live enable path is the `set_laser_director` runtime command
  (`runtime_status.py:356-364` → `LASER_SET_ENABLED` event), which the pad never calls
  [confirmed: zero grep hits in tools/laser_pad_web.py].
- **A12 [confirmed]** `laser_config.py:499-522` `_validate_scene` validates neither
  `fallback_scene` membership in `scenes` nor `cooldown_beats >= 0`; a bad hand-edit loads
  `reason="ok"` and surfaces live as `missing_scene_mapping` silence.
- **A13 [confirmed]** Dead code with zero non-test references (repo-wide `rg`, including tools/,
  scripts/, streamdeck/, getattr call sites): `diagnostics.py:29-128` (`DeckTransition`,
  `TransitionLog`, `LatencySample`, `LatencyTracker`; only `DriftDetector`/`enable_debug`/`is_debug`
  are wired); `led_color_engine.py:731,743,748` engine controls `unlock`, `queue_palette`, `shift`
  (+ their protocol stubs at :19-22, exercised only by tests); `midi_output.py` `_panic_event`
  (set/cleared at :64,:89,:106,:146,:322, never read). `validation_runner.py:131-140`
  `_check_singleton` runs `pgrep` twice for one check.
- **A14 [confirmed]** Stale/misleading text that invites wrong future edits:
  `sound_switch_engine.py:4,13-15` docstring still claims "no-op scaffold" though the class has 8
  live send methods; `govee_frame_renderer.py:1868,1916` comments claim `SLOT_EFFECTS` is empty but
  it has 14 live effects (`:1796`); `config/led_look_director.example.json` top-level `"metadata"`
  key is read by nothing; `laser_config.py:126` docstring lists a `"dependency_missing"` reason the
  loader never returns.

## Part B - Tasks (implement exactly, in order; one commit per patch)

### Absolute Rules
- Do NOT touch: the pack driver logic in `_drive_pack_output` beyond the two `_publish_pack_status`
  call sites named in P2-b; `smart_phrasing.py`; `smart_rearm.py`; `autoloop_controller.py`;
  `soundswitch_pack*.py`; `rb_memory.py`; `live_bpm.py`; anything under `tools/ssfmt/`;
  `streamdeck/`; git history (no force-push, no `git clean`).
- Behavior that must not change: OS2L send ordering (BPM → beat → elapsed fanout), pack ZERO-frame
  fail-closed semantics, `_pack_operational_state` precedence, LED look selection order, laser
  scene selection for non-gated picks, all existing runtime command names and status field names
  (additions allowed, renames not).
- Error handling: propagate or fail closed exactly as the surrounding code does. No new broad
  `try/except`. No success-shaped fallbacks.
- The 200 Hz push loop must not gain any blocking or socket I/O (AGENTS.md §6). P3-a *removes*
  socket I/O from it; do not reintroduce any.
- Contract-first: before each patch, find the matching contract in
  `docs/agents/change_contracts.yml` (`runtime_commands`, `soundswitch_output`, `led_govee`,
  `rekordbox_readers`, `laser`, `tests` as applicable), update every `docs_update` doc it lists,
  and run the three hard checks (§8) before committing.
- Dirty-worktree safety: work only on the files each task names; never revert unrelated changes.

### Patch P1 - runtime-command truth + confirmed dead-weight removal
1. `__main__.py` `_toggle_smart_drop`, `_toggle_smart_breakdown`: return `True` after successful
   `put_nowait`, `False` in the `except queue.Full` branch (annotate `-> bool`), matching
   `_toggle_laser_director`.
2. `tests/test_runtime_status.py`: add `queue.Full`-style failure tests for both commands asserting
   `commands.last_error` is set (mirror the existing laser/LED failure tests at :212-221, :297-307).
3. `validation_runner.py` `_check_singleton`: call `_pgrep_count` once and derive both facts from
   that single result.
4. `diagnostics.py`: delete `DeckTransition`, `TransitionLog`, `LatencySample`, `LatencyTracker`.
   Keep `DriftDetector`, `enable_debug`, `is_debug`. Fix any imports/tests that referenced the
   deleted names (audit found none outside this file, re-verify with `rg`).
5. `led_color_engine.py`: KEEP all five live-control methods (`lock`, `unlock`, `set_palette`,
   `queue_palette`, `shift`) and their tests — operator decision 2026-07-03: these are intentional
   future surface for the LED Pad and Stream Deck buttons (`lock`/`set_palette` are already called
   by `tools/led_pad_web.py:528-529`). Only change: update the section comment above `lock()`
   (currently "Live-control stubs (§8, §15.6 M3 precedence)") to state they are operator-reserved
   future LED-Pad/Stream-Deck controls that must not be removed as dead code, and that any future
   caller outside the StateManager thread must route through BridgeEvents/runtime commands, not
   call the engine directly.
6. `midi_output.py`: delete `_panic_event` and correct the `panic()` docstring (queue-drain is the
   mechanism).
7. Stale-text fixes from A14: `sound_switch_engine.py` module/class docstring;
   `govee_frame_renderer.py:1868,1916` comments; remove `"metadata"` from
   `config/led_look_director.example.json`; fix `laser_config.py:126` docstring reason list.
8. `models.py:255-257`: delete `Ev.LIGHTING_SCRIPTED_ON`, `Ev.LIGHTING_AUTOLOOP_ON`,
   `Ev.LIGHTING_OFF` — zero producers/consumers repo-wide including tests [confirmed via rg
   2026-07-03]. Re-verify with `rg` before deleting.
10. `state_manager.py:3312-3324`: delete the `RBSS_RB_STATE_SHADOW` A6 shadow-log block (the
   whole `if _os.environ.get("RBSS_RB_STATE_SHADOW") == "1":` branch) — operator decision
   2026-07-03: will never be used; rb_state is the authority. The only repo reference is this one
   block [confirmed via rg]. Remove any doc mention flagged by the drift checks.
9. `state_manager.py:178-182`: the env-name constants `LED_MIN_DWELL_ENV`,
   `LED_CANCEL_PENDING_ENV`, `LED_RT_RECONCILE_ENV`, `LED_TRANSPORT_STICKY_ENV`,
   `LED_TRANSPORT_COOLDOWN_ENV` are defined and never referenced (the consuming modules read the
   same env vars via string literals). Point the consumers at shared constants OR delete the
   constants — pick ONE: prefer moving the constant definitions to the module that reads each
   (`led_dispatch_coordinator.py`, `led_look_director.py`, `govee_realtime_runner.py`) and keep
   `state_manager.py` free of them; `LED_PHRASE_MONOTONIC_ENV` stays (it is read in
   `state_manager.py:490`). No behavior change; env var names must not change.

### Patch P2 - output/status truth
- **a. Gate the OS2L injector.** `__main__.py`: construct/start `OS2LInjector` only when
  `RBSS_OS2L_INJECT=1` (new env, default off) or `RBSS_OS2L_INJECT_PATH` is explicitly set. Guard
  the `injector.stop()` call at `__main__.py:1787` accordingly (keep a `None` injector safe). Log
  one INFO line in both the enabled and disabled cases. Do NOT change `os2l_injector.py` itself.
- **b. Surface the suppressed overlay in pack status.** `state_manager.py`: in the two
  `soundswitch_connected` publish sites (`:3975-3990`, `:4198-4213`), keep every existing field
  exactly as-is (they truthfully describe the ZERO output) and add one new key
  `"overlay_suppressed": {"static_held": bool(layers), "blackout": bool(blackout),
  "input_degraded": bool(input_degraded)}`. In all other `_publish_pack_status` call sites the key
  must be present as all-False (add it inside `_publish_pack_status` with parameters defaulting to
  False so the schema is stable). Extend `tests/test_state_manager_pack_driver.py` with one test:
  SS connected + held static layer ⇒ frame is ZERO AND `overlay_suppressed.static_held` is True.
- **c. Fix committed-drop eligibility.** `led_look_director.py` `commit_role`: accept
  `diy_eligible` (same type as `tick`'s usage) and pass it to `_automation_decision_for_role`.
  `state_manager.py` `_led_drop_decision_for_anchor`: pass the engine's `diy_eligible` (same
  expression as `_dispatch_led_automation` builds for `LEDContext`, guarded for engine
  None/disabled) when calling `commit_role`. Add a director test: bank with one DIY-ineligible
  look ⇒ `commit_role("drop", diy_eligible=...)` filters it exactly as `tick()` does.

### Patch P3 - hot-path and reader correctness
- **a. Move realtime→cloud transport teardown off the push loop.**
  `govee_realtime_runner.py`: change `force_deactivate()` so the caller thread only (under the
  existing lock) clears `_desired_spec`, marks a handoff/emergency flag, and returns; the actual
  `self._transport.blackout()` / `.deactivate()` calls run on the **runner thread** on its next
  tick (reuse the `_emergency` mechanism at :126-128; keep the "no more frames leak" property by
  having the runner check the flag before sending any frame). Update
  `led_dispatch_coordinator.py:145` only if the method signature changes. Keep the INFO log
  `reason=handoff_to_cloud`, emitted from the runner thread. Extend
  `tests/test_govee_realtime_runner.py`: force_deactivate from a foreign thread ⇒ no transport
  call on the calling thread (assert via a transport fake recording thread idents), blackout+
  deactivate happen exactly once on the runner thread, and no frame is sent after the call
  returns.
- **b. Preserve ANLZ ordering across transient read failures.** `rb_state_reader.py`
  `_tick_deck`: when the ANLZ read returns `None` (read failure), do NOT overwrite
  `self._last_anlz[d]`; only update the cache and diff on a successful read (`anlz is not None`).
  An empty-string successful read (track unloaded) keeps current semantics. Add a reader test:
  tick1 anlz=None + title success, tick2 anlz=path ⇒ exactly one ANLZ_PATH whose enqueue precedes
  no TRACK_LOADED for the same load... concretely: simulate load where anlz read fails on the
  tick that emits TRACK_LOADED and succeeds next tick; assert ANLZ_PATH is still emitted (not
  swallowed by a stale-diff) — this pins the recovery path. (The cross-tick ordering itself cannot
  be fully restored without holding TRACK_LOADED, which is out of scope; the fix removes the
  cache-poisoning that makes recovery emit late/never.)
- **c. Delete TIMING_COMPENSATION_MS entirely and kill the hidden attribute.**
  Operator decision 2026-07-03: this knob will never be used — delete it rather than repair its
  multi-application. Remove the constant from `config.py:73` and every application site
  (`state_manager.py:3453`, `:3493`, `:4372`; `osl_output.py:323`, `:329`) plus both imports
  (`state_manager.py:37`, `osl_output.py:23`); elapsed values are raw everywhere, end of story.
  In the same motion remove the hidden-attribute smuggle: make `OS2LOutput.send_deck_load` take an
  explicit `elapsed_ms: int = 0` parameter and use it directly; remove the
  `object.__setattr__(arm_meta, "elapsed_ms", ...)` writes (`state_manager.py:3473,3496`) and the
  `hasattr` read at `osl_output.py:323`; thread `elapsed_ms` through
  `SoundSwitchEngine.send_scripted_arm_phase1` (and any other `send_deck_load` callers — find them
  all with `rg "send_deck_load"` first) as a real parameter. With the constant already 0 this is a
  no-behavior change; the full suite is the gate. Update any tests referencing the constant or
  pinning the old signature (`rg TIMING_COMPENSATION_MS` must return zero hits when done).
- **d. Wire spectral cache eviction.** `__main__.py`: at startup, only when the spectral path is
  enabled (`RBSS_SMART_REARM_EXPERIMENT=1` and `RBSS_SPECTRAL_ENABLE=1`), run
  `spectral_cache.evict_stale()` once on a short-lived daemon thread (never on the push loop).
  One INFO log with evicted count if the function returns one (read its signature first).

### Patch P4 - laser resilience + pad truth
- **a. MIDI degrade recovery.** `midi_output.py`: on `trigger()` while degraded with
  `degraded_reason == "send_error"`, attempt one port reopen at most every 5 s (monotonic
  cooldown field; reuse the existing open/prepare logic; keep all failures counted). Success
  clears `_degraded`/`_degraded_reason` and proceeds; failure keeps rejecting. Permanent
  degradations that are NOT send errors (port missing at startup, dependency missing) keep
  current behavior — only the send-error latch becomes recoverable. Tests: fake backend erroring
  once then healthy ⇒ second trigger after cooldown succeeds and status shows recovered; repeated
  failure ⇒ stays degraded, no tight retry loop (cooldown respected).
- **b. Bank gating correctness.** `laser_executor.py`: (i) in `_choose_bank_scene_locked`, skip
  entries whose `scenes[name].safety_class == "high_impact"` when the active personality has
  `allow_high_impact=False` (mirror `_usable_bag_entries`; treat missing scene defs as skippable);
  (ii) call `_restore_role_state(role, cursor_before, active_before)` in BOTH the
  `missing_scene_mapping` and `high_impact_blocked` gate branches before returning. Tests: drop
  bank [high_impact, normal] with allow_high_impact=False ⇒ the normal scene fires at the drop and
  the cursor is not burned; missing mapping ⇒ cursor/active restored.
- **c. Config validation.** `laser_config.py` `_validate_scene`: error when `fallback_scene`
  names a scene not in `scenes`; error when `cooldown_beats < 0`. Extend
  `tests/test_laser_config.py` with both cases (loader returns invalid + reason, matching existing
  error style).
- **d. Laser Pad master toggle drives the live director.** `tools/laser_pad_web.py`: on an
  `enabled` draft patch, ALSO append the runtime command
  `{"cmd": "set_laser_director", "enabled": <bool>}` as one JSON line to the bridge command file
  (same path/format the menubar uses — read `runtime_status.py` `COMMANDS_PATH` and reuse/import
  the canonical path constant rather than hardcoding). Keep the draft patch behavior unchanged.
  If the command file append fails, surface `ok: False` with a reason (no silent success). Update
  the tooltip (`tools/laser_pad_assets/index.html:23`) to say exactly what happens: immediate
  live toggle + saved to draft. Test in `tests/test_laser_pad_web.py`: enabled patch writes the
  command line (tmp command path) and still persists the draft; append failure surfaces an error.
- **e. Blackout-mask refcount tests.** `tests/test_laser_executor.py` (or lifecycle file): with a
  real config + fake backend, two owners hold the blackout mask; assert exactly one
  `manual_blackout_on` send on first hold, zero sends on second hold, zero on first release, one
  `manual_blackout_off` on final release; and `blackout_pending_for_drop_window=True` suppresses
  the off-send on final release.
- **f. `canon_alias` dedupe.** Make `laser_config.py:383` import/reuse
  `personality_resolver.canonicalize_text` (or vice versa — pick the direction with no import
  cycle; `personality_resolver` already imports nothing from `laser_config` [re-verify]). No
  behavior change; both call sites keep working (`laser_config_ops.py:15`,
  `tools/laser_pad_web.py:23`).
- **g. Remove `pre_drop_scene`; protect laser `post_drop_cycle_beats`.** Operator decisions
  2026-07-03: `pre_drop_scene` is not used for anything and never will be — remove the personality
  field end-to-end: `laser_models.py` field, `laser_config.py` parsing/validation,
  `laser_director.py` status echoes (~:100,200,864), `tools/laser_config_ops.py` handling, the
  `pre_drop_scene` entry in `tools/laser_pad_assets/pad-selectors.js:874` (and any pad UI
  label/dropdown for it), all six `"pre_drop_scene"` keys in `config/laser_director.example.json`,
  and the references across the nine test files (`rg -l pre_drop_scene tests/`).
  **Load-compat is mandatory:** the operator's live gitignored `config/laser_director.json` still
  contains the key in every personality — the loader must IGNORE (deprecation-tolerate) a leftover
  `pre_drop_scene` key, never error; follow the repo's existing deprecated-field pattern
  (see `tests/test_laser_config_deprecation.py` for prior art) and add that test for this key.
  The laser-side `post_drop_cycle_beats` (`laser_models.py:119` area) is KEPT even though nothing
  consumes it yet — operator-reserved for future post-drop laser looks; add a one-line
  reserved-future comment on the field so it is not re-flagged as dead.

## Part C - Invariants That MUST Still Hold (live safety)
- 200 Hz push loop gains no blocking/socket/MIDI/file/subprocess I/O; P3-a strictly removes I/O.
- `StateManager` remains the only `DeckState` writer; all new control flows go through
  `BridgeEvent`s or the command thread as today.
- Pack driver: fail-closed ZERO on any uncertain state is unchanged; `_pack_operational_state`
  precedence unchanged; SS-present ⇒ ZERO frame unchanged (P2-b only ADDS a status key).
- Held Static Override semantics (AGENTS.md §6) unchanged.
- Laser policy (LaserDirector) vs execution (LaserSceneExecutor) split unchanged; P4-b touches
  only executor-internal selection/restore.
- `RBStateReader._tick_deck` still reads ANLZ before title within a tick (P3-b changes only the
  failure-path caching).
- No secrets/IPs/device IDs in committed files or logs.

## Part D - Tests
- Named per task above. All new algorithm-level assertions must run through pure seams (fakes for
  transport/backend/ports; no sleeping loops — drive monotonic clocks via injected `clock` where
  the pattern exists, e.g. midi cooldown).
- Full suite green: `python3 -m unittest discover tests` (expect 2749+new, OK; 5 skips, 1 expected
  failure are pre-existing).

## Part E - Acceptance (definition of done, per patch)
1. Patch compiles + full suite green.
2. Matching contract(s) in `docs/agents/change_contracts.yml` identified; every `docs_update` doc
   updated; if a task has no matching contract, extend the contract FIRST (AGENTS.md §7).
3. Hard checks pass: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
   `python3 tools/check_docs_drift.py`.
4. One commit per patch, message prefixed `Audit P<n>:`; work directly on `main`; no new branches.
5. Status language stays within AGENTS.md §10 (everything here is software-tested only).

## When You Finish
Report: changed files per patch, test counts before/after, the three hard-check results, and a
plain-language operator summary: what now behaves differently live (smart-drop toggle reports
failures honestly; injector off unless opted in; pack status shows suppressed overlays; drop looks
respect palette eligibility; Govee handoff leaves the push loop clean; laser MIDI self-heals after
transient errors; blocked high-impact picks no longer eat drops; pad master toggle is live), what
is unchanged, and that NO hardware validation was performed (all claims software-tested only).
Do not restart the bridge; do not touch hardware, SoundSwitch, Rekordbox, or Govee devices.
