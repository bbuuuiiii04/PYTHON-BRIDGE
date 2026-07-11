---
doc_status: current
truth_level: independent adversarial re-review and activation gate
last_verified_commit: 7ff50b2
last_verified_date: 2026-07-11
validation_scope: >
  Read-only AWR-206 fix-round re-review at HEAD 7ff50b2, followed by a combined
  activation verdict for the already-restored LED live config and staged
  AWR-206 code. Production code, tests, config, bridge processes, MIDI, hardware,
  and the running operator session were not changed or contacted. The only repo
  write is this review document.
---

# AWR-206 re-review and activation verdict

**A206-REREVIEW: PASS**

**A206-ACTIVATION: GO**

## Findings first

No blocking or required-fix finding remains from the original AWR-206 review.
The fix makes the blackout arm reachable without relaxing scene MIDI, the real
director/executor regression exercises that seam, and the level-held arm no
longer produces a 200 Hz INFO flood.

One non-blocking coverage note remains: the named integration test calls the real
director on the recovery tick but deliberately does not pass that one recovery
decision to the real executor (`tests/test_laser_executor.py:1177-1184`). That
does not invalidate its arm-path or crossing assertions. I separately repeated
the production call order while feeding every recovery decision; the pending
latch still emitted one blackout-on only, normal scene MIDI resumed only after
the strict gate reopened, and the crossing emitted one blackout-off. A dedicated
idle-to-auto boundary regression would be useful future coverage, but is not an
activation fix.

## Part 1 — re-review against Findings 1–3

### Finding 1 — resolved: the arm is genuinely reachable

- **[CONFIRMED]** `LaserSceneDecision` has one new frozen, default-false
  `blackout_arm` field (`laser_models.py:152-172`). A production-wide search
  found exactly one assignment to `True`: the director's priority-7
  `autoloop_not_ready` return (`laser_director.py:442-458`). The only runtime
  consumer is the executor (`laser_executor.py:133-154`).
- **[CONFIRMED]** Emergency and manual decisions still win first, followed by
  not-playing, no-track, stale-position, and scripted guards
  (`laser_director.py:371-440`). Therefore `blackout_arm=True` cannot bypass
  those higher safety/ownership decisions. The executor also requires a real
  smart-drop or smart-phrasing arm level before it honors the decision bit
  (`laser_executor.py:133-141`).
- **[CONFIRMED]** StateManager still builds one context, calls the real director,
  and gives the resulting decision plus that same context to the real executor
  (`state_manager.py:4839-4869`). On the reachable idle/no-scene path, the
  executor now consumes `decision.blackout_arm` before returning and applies
  `_passes_blackout_gates()` (`laser_executor.py:143-159`). That relaxed gate
  still requires playing, a loaded active track, fresh position, autoloop mode,
  and no scripted track; only `autoloop_ready` is omitted
  (`laser_executor.py:617-639`).
- **[CONFIRMED]** The round-one automatic-gate arm was reverted. The strict
  automatic branch now only records the scene gate, resolves a crossing, and
  DEBUG-logs an arm that cannot occur from the real director under that same
  context (`laser_executor.py:161-175`). Automatic scene MIDI remains behind
  `_passes_automatic_gates()`, including `autoloop_ready`
  (`laser_executor.py:617-625`).
- **[CONFIRMED]** Pure two-object production-path reproduction, with
  `autoloop_ready=False` and a level-held arm across four ticks, emitted exactly
  one `(note 90, note_on, high)`, zero scene messages, and left one pending
  window. When churn remained closed at the crossing, the real director still
  returned `autoloop_not_ready`; applying StateManager's exact no-drop-decision
  safety-net condition emitted one `(note 90, note_off, high)` and cleared the
  latch. This matches the production safety-net branch
  (`state_manager.py:4882-4893`) and the executor's idempotent arm/release latch
  (`laser_executor.py:339-375`).
- **[CONFIRMED]** The alternate recovery route is also safe. Feeding every real
  director decision through the executor across idle -> auto recovery -> drop
  produced one blackout-on, then ordinary phrase/drop scene pulses only after
  `autoloop_ready=True`, then one blackout-off at `drop_crossing`. There was no
  double-arm across the idle/automatic boundary.

### Finding 2 — resolved: the regression uses the real two objects

- **[CONFIRMED]**
  `test_integrated_director_executor_arms_blackout_under_autoloop_churn`
  instantiates a real `LaserDirector` and real `LaserSceneExecutor`
  (`tests/test_laser_executor.py:1126-1158`), calls `director.tick()`,
  `executor.on_tick()`, and `executor.on_decision()` for the closed-gate churn
  ticks (`tests/test_laser_executor.py:1161-1169`), then drives a real director
  drop-crossing decision into the real executor (`tests/test_laser_executor.py:1186-1203`).
- **[CONFIRMED]** Its assertions pin the original missing behavior: the churn
  calls must be `[90]` exactly, which means one blackout-on and no scene MIDI,
  the pending latch must be true, the crossing must be `drop_crossing`, exactly
  one blackout-on and one blackout-off must exist, and the latch must finish
  false (`tests/test_laser_executor.py:1171-1175`,
  `tests/test_laser_executor.py:1197-1203`).
- **[CONFIRMED]** The lane's failing-first claim at pre-fix `b02f718` is credible
  from that assertion shape and the old source. At `b02f718`, priority 7 returned
  idle/no-scene with no decision arm field
  (`b02f718:laser_director.py:442-452`; `b02f718:laser_models.py:152-167`), and
  the executor returned at idle before the round-one relaxed branch
  (`b02f718:laser_executor.py:128-157`). The current test's expected `[90]`
  therefore becomes the reported old `[] != [90]` failure, not a test that
  could pass accidentally through a synthetic buildup decision.

### Finding 3 — resolved: the INFO diagnostic is throttled and the level latch remains pinned

- **[CONFIRMED]** `_log_blackout_skip()` keys the five relaxed-gate conditions
  and returns without logging when the tuple has not changed
  (`laser_executor.py:647-671`). The key resets when a blackout window really
  arms or resolves (`laser_executor.py:345-367`).
- **[CONFIRMED]** The 200-tick test holds one failing tuple while beat position
  advances and requires exactly one INFO line
  (`tests/test_laser_executor.py:1229-1248`). It passed at current HEAD.
- **[CONFIRMED]** An additional 600-call adversarial check used 200 stale-position
  failures, 200 not-playing failures, then 200 stale-position failures. It
  emitted three INFO lines total: one for each change in the failing-condition
  tuple, never one per tick.
- **[CONFIRMED]** The StateManager level latch is unchanged: the arm remains true
  while `drop_cut_armed` is held and no crossing has occurred
  (`state_manager.py:4827-4837`), then is false on the crossing tick. The two
  pins remain at `tests/test_smart_transitions.py:1368-1436`; that file is
  byte-unchanged from `b02f718`, and both named tests passed.

## New-change attack surface

- **[CONFIRMED] Other consumers:** no production code besides
  `LaserSceneExecutor` reads `LaserSceneDecision.blackout_arm`, and no producer
  besides the director's priority-7 return sets it true. Default-false preserves
  all existing decision construction (`laser_models.py:152-172`).
- **[CONFIRMED] Safety-net release:** StateManager clears the pending blackout
  when the smart-drop crossing occurs without a director `drop_crossing`
  decision (`state_manager.py:4882-4893`). Existing StateManager tests pin
  missing-director, `None`, non-drop, and no-double-clear cases
  (`tests/test_smart_transitions.py:1248-1301`).
- **[CONFIRMED] Double-arm/re-entry:** `trigger_blackout_on()` sets the pending
  latch before backend dispatch and returns immediately on every later arm
  (`laser_executor.py:339-359`). Repeated idle ticks, the idle-to-auto boundary,
  and the crossing routes all produced one blackout-on only.
- **[CONFIRMED] Mask ownership:** resolving the drop latch sends blackout-off
  only when no other named mask owner remains (`laser_executor.py:361-375`), and
  mask releases likewise keep the note held while the drop latch or another
  owner remains (`laser_executor.py:377-413`). The fix did not alter this
  precedence.
- **[CONFIRMED] Focused software verification:** 394/394 passed across
  `test_laser_executor`, `test_laser_executor_lifecycle`,
  `test_laser_blackout_rewire`, `test_laser_director`,
  `test_laser_reset_wiring`, and `test_smart_transitions`. The named integrated,
  200-tick throttle, idempotence, both crossing routes, and both latch pins were
  also run individually.
- **[UNKNOWN] Hardware behavior:** no physical laser, MIDI bus, DMX/Enttec,
  SoundSwitch, LED/Govee device, Rekordbox runtime, bridge process, or bridge log
  was contacted. The result remains SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.

## Part 2 — next menubar restart activation

### GO basis

- **[CONFIRMED FROM RESTORE REPORT; LIVE CONFIG NOT RE-READ]**
  `/tmp/rbss_lane_signals/claude2.RESTORE.report.md` records that the pre-clobber
  backup was copied over the live LED config, the resulting file hash matched
  the backup, and all five content checks passed: 89 looks, `palette_control`
  restored, zero DIY looks in bank roles, plain `rt_drop_chase` and
  `rt_drop_nebula` unbanked, and the named heartbeat/firework/balloon looks
  present. It also records that the speed/size-law apply was byte-idempotent and
  the genuine clobber-sensitive validation test turned green. I did not open,
  hash, load, or write the live config in this review because the operator may
  be mixing and the task explicitly forbids config contact.
- **[CONFIRMED]** AWR-206's software path now passes the independent re-review
  above. The next operator-approved menubar restart is therefore a reasonable
  combined room-visible gate for both staged changes.

### What should change after that restart

- **Lasers:** one smart pre-drop blackout-on should now reach the rig even while
  SoundSwitch's autoloop is mid-re-arm. No laser scene should be selected while
  `autoloop_ready` is false. The blackout should release at the drop crossing,
  either from the director's real drop decision or StateManager's safety net.
- **LEDs/Govee:** the bridge should load the restored 89-look catalog, palette
  controls should return, DIY looks should stay out of bank rotation, and the
  retired plain chase/nebula looks should remain unbanked. The restored
  heartbeat, firework, balloon, strobe, palette, and rainbow families may
  re-enter normal rotation according to their existing banks.

### What should remain unchanged

- SoundSwitch automatic scenes remain strict-gated by autoloop readiness.
  Emergency/manual laser precedence, scripted-track exclusion, named blackout
  mask ownership, and shutdown zeroing remain as before.
- Rekordbox reader ownership and state handling are untouched by AWR-206 and by
  this review. AWR-206 does not change LED/Govee selection, and the config
  restore does not change laser policy.
- **[CONFIRMED]** SOL2 historical Finding 1, the spectral false-blackout problem,
  remains open by design. AWR-199's interim guard remains in force
  (`docs/status/active_work_registry.md:173`); the raw approach measuring layer
  explicitly does not fix the classifier (`docs/status/active_work_registry.md:107`),
  and Stage-2 is designed but not authorized or built
  (`docs/status/active_work_registry.md:111`). This GO does not claim otherwise.

### Operator eyeball at restart

1. Use the normal menubar restart only when you are ready for a room-visible
   validation pass. This review does **not** authorize or perform the restart.
2. Confirm exactly one bridge process after restart with
   `pgrep -f rb_ss_bridge_v2 | wc -l`; the expected result is `1`. If it is not
   `1`, stop the validation and use the normal single-process recovery path.
3. In the bridge log, look for one `[LX] blackout_on sent` per armed pre-drop
   window, a corresponding release at the drop, and no repeated
   `blackout skipped: relaxed gate blocked` line every tick. A changed failure
   tuple may correctly produce one fresh skip line.
4. Watch the laser itself go dark before the drop and return at the crossing.
   While the autoloop-ready gate is closed, there should be no new automatic
   laser scene MIDI. If a later ready tick occurs before the drop, ordinary
   scene MIDI may resume; that is expected and must not emit a second
   blackout-on.
5. Watch SoundSwitch continue its normal autoloop re-arm and scene behavior.
   Watch the LED/Govee output for the restored palette/catalog behavior, no DIY
   looks in rotation, and no plain chase/nebula rotation. Rekordbox reader state
   should remain healthy and unchanged.
6. Treat a missing blackout-on, a blackout that survives the crossing, repeated
   INFO spam, duplicate blackout-on messages, a second bridge process, or the
   restored LED catalog failing to appear as a NO-GO observation and roll back
   through the operator's normal recovery procedure before continuing the mix.

### Residual risks

- **[UNKNOWN]** The combined state has not been observed on the actual laser,
  MIDI bus, SoundSwitch, Govee devices, or live Rekordbox session. GO means
  software evidence supports the next operator-controlled validation restart;
  it is not a hardware-validation claim.
- **[CONFIRMED PRE-EXISTING]** A rejected manual blackout-on backend send is
  latched and is not retried during that window (`laser_executor.py:339-359`).
  This is fail-light rather than stranded-dark, but one transient legacy-MIDI
  rejection can still miss that drop's visible blackout. Watch the bridge log
  for a rejection or for an arm without a matching send.
- **[REPORTED]** The restore report identifies two stale LED tests that remain
  red for unrelated expectations; it separately demonstrates that the one test
  genuinely broken by the clobber turns green after restore. This is residual
  test-debt uncertainty, not evidence that the restored file is wrong.

## Commit and scope boundary

This review writes and commits only
`docs/research/sol_awr206_rereview_2026_07_11.md`. It does not restart, signal,
inspect, or mutate the bridge; send MIDI; contact SoundSwitch, Rekordbox, lasers,
LEDs, or Govee; or read/write any config file.
