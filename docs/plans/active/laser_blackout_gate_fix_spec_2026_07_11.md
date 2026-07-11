---
doc_status: current
truth_level: spec
last_verified_commit: 2d6782a
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-206 — split the laser pre-drop blackout arm gate
  from the scene-fire gate so the 4-beat blackout survives autoloop re-arm
  churn during real mixing. Operator GO 2026-07-11. STAGED: activates only at
  the operator's next bridge restart.
---

# Implementation Spec — AWR-206 Laser pre-drop blackout: relaxed arm gate

## Part A — Context & Root Cause (verified at exec desk; read, do not implement)

- [confirmed] The 4-beat pre-drop laser blackout is intact but almost never
  fires during real mixing. Current live session: 30 `[SM] smart-drop-blackout-arm`
  intents → 0 `[LX] blackout_on sent`. The only session it ever fired
  (13:19 today, 3/3) had an idle autoloop. Full triage evidence:
  `/tmp/rbss_lane_signals/claude3.LZBLK.report.md`.
- [confirmed] Mechanism: `laser_executor.py` `on_decision` — for `_AUTO_ROLES`,
  `_passes_automatic_gates(ctx)` (laser_executor.py:586-594) is checked BEFORE
  blackout arming; on failure it `return None`s, skipping the arm at :155-160.
  The predicate requires `ctx.autoloop_ready`, and `autoloop_ready`
  (state_manager.py:5204-5210) is False whenever the SoundSwitch autoloop has
  an arm pending / pending arm meta / mismatched `last_armed_filepath` — which
  is the normal state at the pre-drop instant while actively mixing (the
  clear-1-beat-before-reload re-anchor).
- [confirmed] A plain MIDI blackout note does not need a render-ready autoloop.
  The release path is healthy independent of the gate: `_resolve_pending_blackout`
  runs on drop crossings even inside the blocked branch (:135, :142-143) — 69/69
  drop crossings resolved this session.
- [confirmed] Both arm signals flow through this path:
  `ctx.smart_drop_blackout_arm or ctx.smart_phrasing_blackout_arm` (:128-131).
  The relaxed gate must cover both identically.
- [confirmed] The skip reason currently logs at DEBUG only (:145), invisible at
  the INFO level the bridge runs at — that's why this was undiagnosable from
  live logs.
- [operator ruling 2026-07-11] GO on the root-cause fix below. STAGED only; the
  RUNNING bridge must not be touched.

## Part B — Tasks (in order; commit by explicit paths after each)

### Absolute Rules
- The bridge is LIVE right now: never start/stop/restart/contact it, never send
  MIDI, never edit live configs. Code + tests + named docs only.
- Out of scope: `laser_director.py` policy, scene selection/policy gates,
  personality resolution, `_resolve_pending_blackout` release machinery,
  state_manager's `autoloop_ready` definition, every non-laser subsystem.
- Behavior that must not change: scene firing stays behind the strict
  `_passes_automatic_gates` unchanged; idle/no-scene early return unchanged;
  missing-scene-mapping skip unchanged; scripted tracks (`scripted_id != 0`)
  never arm; blackout precedence/release semantics unchanged.
- Error handling: no new try/except, no fallbacks; gates fail closed (no arm).

### Task 1 — `laser_executor.py`: split the blackout arm gate
Add:
```python
def _passes_blackout_gates(self, ctx: LaserContext) -> bool:
    # Strict automatic gate MINUS autoloop_ready: a blackout note needs a
    # genuinely live deck, not a render-ready autoloop.
    return (
        ctx.playing
        and ctx.active_track_loaded
        and not ctx.position_stale
        and ctx.lighting_mode == "autoloop"
        and ctx.scripted_id == 0
    )
```
In `on_decision`'s auto-gate-blocked branch (currently :140-146): when
`should_arm_blackout and self._passes_blackout_gates(ctx)` and the existing
scene-mapping condition (`decision.scene in self._config.scenes`) holds, call
`self.trigger_blackout_on(ctx)` before returning None (scene MIDI stays
blocked). When the blackout still cannot arm, log the skip at **INFO** with the
failing sub-conditions (replace the :145 DEBUG for this branch; arm attempts
are edge-triggered ~once per drop, so INFO volume is fine — outcomes at INFO
per the repo's logging convention). Keep `_record_gate("auto_gate_blocked")`
and the drop-crossing resolve exactly as they are.

### Task 2 — release-path audit (verify, do not redesign)
Enumerate every path that releases/clears the manual blackout once armed
(drop crossing, master_switch/mask owners, emergency/blackout masks,
track-unload/mode-transition cleanup, shutdown zeroing) and confirm each is
reachable from the NEW arming window (armed while autoloop churns, then: drop
crosses / deck swapped / track unloaded / mode goes scripted / bridge
shutdown). If any path cannot release a blackout armed in the new window,
STOP and write the `.blocked` signal with the evidence — do not invent a new
release path; that is an executive decision.

### Task 3 — tests (extend `tests/test_laser_executor.py`, following its
existing harness patterns; check `test_laser_blackout_rewire.py` for prior
blackout-arm pins and extend whichever file owns this seam)
- autoloop_ready=False + smart_drop arm → blackout FIRES, scene does NOT, gate
  counter still records the block.
- Same with smart_phrasing arm.
- Each relaxed-gate sub-condition individually False (not playing / no track /
  position_stale / mode!=autoloop / scripted_id!=0) → NO arm.
- Missing scene mapping in the blocked branch → NO arm (unchanged).
- Drop crossing in the blocked branch still resolves a pending blackout.
- The INFO skip log carries the failing sub-conditions.

### Task 4 — contract + docs + checks
Contract key `laser` in `docs/agents/change_contracts.yml` (§7: extend first if
this seam isn't covered); update every `docs_update` doc it lists (subsystem
card `docs/subsystems/laser.md` at minimum); add the AWR-206 registry row
(re-check current max ID first); run the 3 hard checks + scoped laser suites
(`test_laser_executor`, `test_laser_executor_lifecycle`,
`test_laser_blackout_rewire`, `test_laser_director`) and report counts by name.

## Part C — Invariants That MUST Still Hold
- LaserDirector policy vs LaserSceneExecutor execution stay separate
  responsibilities (AGENTS.md §6).
- Blackout/emergency masks and pack-disabled/shutdown zeroing keep precedence
  over everything, including this arm.
- No blocking I/O added anywhere near the push loop; no new threads.
- Scripted tracks never receive smart-drop blackouts.
- STAGED: zero effect on the currently-running bridge; activates only at the
  operator's next restart. Fail-open beats fail-dark: when in doubt the
  blackout releases.

## Part D — Tests
Task 3. Pure-function/context-injection seams only (the executor harness
already injects `LaserContext`; no MIDI hardware, no subprocess).

## Part E — Acceptance
- [ ] Relaxed gate arms blackout under autoloop churn in tests; scene firing
      unchanged; all Task 3 cases green.
- [ ] Release-path audit written into the lane report with file:line per path
      (or `.blocked` raised).
- [ ] Scoped laser suites green with counts by name; 3 hard checks green.
- [ ] Contract docs_update honored; AWR-206 registry row added.
- [ ] Commits by explicit paths; no live config, secret, or gitignored file
      touched; running bridge untouched (`pgrep -f 'rb_ss_bridge_v2$'`-style
      check irrelevant — just never signal it).

## When You Finish
Report to `/tmp/rbss_lane_signals/<session>.LZFIX.report.md`: changed files,
test counts by name, the release-path audit table, honest ceilings (this is
SOFTWARE-VALIDATED ONLY; the real proof is the operator's next mix), and the
plain-language summary: what now happens live after his next restart (4-beat
laser blackout before drops actually fires during real mixing), what does not
change (scenes, precedence, scripted tracks), and what to eyeball at that
restart.
