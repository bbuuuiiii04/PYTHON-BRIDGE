---
doc_status: current
truth_level: implementation spec (SOL2 launch blockers 2-5; executive seat authored)
last_verified_commit: 66034e7
last_verified_date: 2026-07-10
validation_scope: >
  Fixes for SOL2 code-review findings 2-5 (HIGH-severity launch blockers for the
  next live restart: fail-dark on beat-feed flap, re-anchor strobe replay, stale
  shuffle bag across family/tier pools, empty F2xF4 predicate failing open to the
  full drop bank). Every Part A claim was independently re-confirmed at the
  executive desk on 2026-07-10 at commit 66034e7 by code read; findings 2-5 were
  also measured by the SOL2 review (capture:
  ~/Desktop/SOL_captures_2026-07-10/SOL2_code_review.txt). Staged only; nothing
  here restarts or contacts the running bridge. Finding 1 (approach-shape
  misclassification) is NOT in scope - its real fix is the AWR-195 stage-2
  refactor.
---

# Codex Implementation Spec - SOL2 launch blockers 2-5 (LED/beat-engine fail-dark + routing fixes)

> You are autonomous senior engineer: once given this spec, proactively gather context, plan, implement, test, and refine without waiting for additional prompts at each step. Persist until the task is fully handled end-to-end within the current turn. Bias to action; do not end your turn with clarifications unless truly blocked.

> Act as a discerning engineer: optimize for correctness, clarity, and reliability over speed; avoid risky shortcuts, speculative changes, and messy hacks; cover the root cause, not just a symptom. Conform to the codebase conventions. Tight error handling: no broad try/catch and no success-shaped fallbacks. Before adding new helpers, search for prior art.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make. Another agent lane is concurrently editing USB/installer files (see Absolute Rules). If you notice unexpected changes you didn't make, leave them alone. NEVER use destructive commands like `git reset --hard` or `git checkout --`.

**Do the work yourself - do NOT spawn subagents of any kind.** (Subagent-spawning Codex sessions are killed at the usage wall mid-task; a single session runs to completion.)

## Part A - Context & Root Cause (verified; read, do not implement)

Four independent HIGH-severity defects, all landed during the 2026-07-09 overnight
program, all re-confirmed at the executive desk at commit `66034e7`. The live-safety
spine for all of them: **fail-open beats fail-dark** - a room that re-lights early is
recoverable; a stuck-dark or wrong-strobe room is the failure.

**Finding 2 [confirmed by code read] - a recovered beat feed never clears idle
grace, so a later single bad tick blacks the room.**
`govee_realtime_runner.py`: `_idle_tick` (lines 511-534) starts the grace timer by
setting `self._idle_since = now` and, once `now - self._idle_since >= self._grace_s`
(default 0.25 s), sends `blackout()` + `deactivate()`. The healthy composed-playback
path in `_tick_once` clears `_idle_since` ONLY when the motion signature changes
(lines 399-405) or in the paused-comet branch (line 385). A steady-state healthy tick
(same signature - the normal case) never clears it. Sequence: healthy -> one
unpermitted tick at t (grace starts) -> healthy ticks (stale `_idle_since` kept) ->
one more unpermitted tick at t+0.36 -> `0.36 >= 0.25` -> immediate blackout +
deactivate from ordinary anchor flapping. SOL2 measured exactly this pure sequence
(healthy@100.0, bad@100.1, healthy@100.2, bad@100.36 -> blackout + deactivate).

**Finding 3 [confirmed by code read; SOL2-measured] - a sustained-divergence
re-anchor rewinds a continuous effect's whole-beat age, replaying opening
strobe/explosion envelopes mid-drop.**
`beat_sync_engine.py`: `_maybe_reanchor` (lines 227-253) stores
`inst.reanchor = (now, abs_beat, bpm)`; `_render_list` (lines 279-281) then computes
`local_beat = ra_abs % 1.0 + elapsed_since_reanchor * rate`. The `% 1.0` discards the
instance's accumulated whole beats: SOL2 measured a sustained 150->127 BPM correction
moving `local_beat` from 8.375 to 0.25, which puts the AWR-187 firework
(`drop_firework_explosion_2`) back inside its first-half-beat full explosion/strobe -
an unexpected second strobe mid-drop. Existing tests assert only phase modulo one
(`tests/test_beat_sync_engine.py` re-anchor tests), so this was invisible.
Second leg: divergence evidence survives feed gaps. `_maybe_reanchor` returns early
on `bpm <= 0.0` WITHOUT clearing `self._diverged_since`, `animate()` (the
paused/unpermitted path, lines 203-210) never touches it, and nothing detects a gap
in `on_tick` calls - so a divergence timer started before a feed gap counts
wall-clock time across the gap and can re-anchor (with the rewind above) immediately
on the first sample after the feed resumes.

**Finding 4 [confirmed by code read; SOL2-measured with the pre-incident live
config] - the (role, backend) shuffle bag is reused across different filtered
subsets, so a family/tier pick can come from the PREVIOUS drop's tier.**
`led_look_director.py`: `_automation_decision_for_role` narrows `look_names` by the
preference predicate (lines 460-463) and passes the narrowed `subset` to
`_look_name_for_backend` (lines 509-539). The bag is keyed `(role, backend)` only,
and rebuilt only when `cursor % len(subset) == 0 or not bag` (line 524). When the
preference changes between picks (WALL-T1 drop then WALL-T2 drop), the cached bag
still holds T1 names and `bag[cursor % len(bag)]` returns a T1 look for the T2 drop -
a gentle/strobe class from the wrong tier. SOL2 measured it with seed 0: a WALL-T1
pick built the four-chase T1 bag; the next WALL-T2 commit returned
`rt_drop_chase_blue` (T1, absent from T2).

**Finding 5 [confirmed by code read + measured against the CURRENT live config] -
F2 and F4 compose into a single AND predicate; an empty intersection makes the
whole preference vanish, failing open to the ENTIRE drop bank.**
`led_dispatch_policy.py`: `_led_look_preference_predicate` (lines 2045-2067) returns
`lambda name: all(p(name) for p in preds)` over [v2 dressing, F2 family/tier set, F4
euphoric bright set]. The director applies the preference fail-open as ONE term
(lines 460-463: empty preferred subset keeps the full bank). So when the F2 cell and
the F4 bright list do not intersect, the pick becomes a full-bank lottery instead of
falling back to the F2 pool - the chosen family/tier is ignored entirely. SOL2
measured (pre-incident config): 9 of 12 family/tier cells had no F4-bright member;
COMET-T2 euphoric with seed 2 selected a look in neither COMET-T2 nor the bright
list. The comment in the code ("Each term only NARROWS") describes the intended
semantics; the implementation does not deliver it. The executive desk re-measured on
the CURRENT live config (post pad-incident): 6 of 12 routing cells have an empty
intersection with today's drop bank, so this fires immediately on restart.

**Out of scope, for context only:** SOL2 finding 1 (the deep-sub-void rung
misclassifying buildup-shaped quiets; EIIRP wrong 8-beat blackout / SIGNAL missed
blackout at `lighting_moments_v2.py:553`) is handled by the AWR-195 stage-2
approach-shape classifier and an executive escalation - do not touch
`lighting_moments_v2.py`.

## Part B - Tasks (implement exactly, in order; one commit per task, explicit paths)

### Absolute Rules
- Touch ONLY: `govee_realtime_runner.py`, `beat_sync_engine.py`,
  `led_look_director.py`, `led_dispatch_policy.py`, `led_models.py`,
  `tests/test_govee_realtime_runner.py`, `tests/test_beat_sync_engine.py`,
  `tests/test_led_look_director.py`, `tests/test_lighting_moments_v2_f4.py`,
  and the Part E docs. NOTHING else.
- **Concurrent-lane fence (another agent is editing these NOW - do not touch,
  read, revert, or commit them):** `packaging/make_stick.sh`,
  `install_controller.py`, `enttec_dmx_pro.py`, `usb_launcher.py`, `__main__.py`,
  `soundswitch_pack_player_config.py`, `tests/test_make_stick.py`,
  `tests/test_install_controller.py`, `tests/test_enttec_dmx_pro.py`,
  `tests/test_usb_launcher.py`, `tests/test_soundswitch_pack_player_config.py`,
  `scripts/bridge_menubar.py`, `tests/test_bridge_menubar.py`.
- Do NOT touch `lighting_moments_v2.py` (finding 1 is out of scope).
- Do NOT modify `config/led_look_director.json` (live, gitignored) or any backup.
- No bridge restart, no process contact, no config writes, no branch creation.
- Commits by EXPLICIT PATHS only (an auto-sync hook sweeps `-a` commits; never
  use `git commit -a`). Message prefix per task below.
- Behavior that must not change: every existing green test stays green; blackout /
  emergency precedence paths unchanged; the 200 Hz push loop gains no I/O; comet
  pause behavior unchanged; preview_role stays filterless; substitute_realtime_drop
  cursor semantics unchanged (it still never advances `_role_cursors["drop"]`).
- Error handling: these are pure in-memory state fixes - no try/except anywhere.

### Task 1 - `govee_realtime_runner.py`: clear idle grace on every permitted healthy tick (finding 2)
In `_tick_once`, in the healthy composed-playback path, add `self._idle_since = None`
to the existing lock block that records the send result (currently lines 448-450):

```python
        with self._lock:
            self._last_error = "" if sent_ok else "transport_send_failed"
            self._frame_index += 1
            self._idle_since = None
```

That is the whole code change: every permitted tick that composes and sends a frame
resets the grace timer, so an isolated bad tick can never inherit a stale
`_idle_since` from an earlier blip. (The paused-comet branch at line 385 already does
this; you are making the main healthy path consistent with it.)

Tests (extend `tests/test_govee_realtime_runner.py`, following its existing
fake-transport/anchor harness):
1. `test_recovered_feed_clears_idle_grace` - the SOL2 sequence: healthy tick,
   unpermitted tick (+0.1 s), healthy tick (+0.2 s), unpermitted tick (+0.36 s) with
   `grace_s=0.25`. Assert NO blackout/deactivate was sent and the runner is still
   active.
2. `test_idle_grace_still_fires_when_feed_stays_bad` - healthy tick, then
   unpermitted ticks at +0.1 s and +0.4 s. Assert blackout + deactivate DID fire
   (the grace path itself must keep working).

Commit: `SOL2-F2: clear LED idle grace on every permitted healthy tick` +
explicit paths.

### Task 2 - `beat_sync_engine.py`: whole-beat continuity across re-anchor + divergence evidence hygiene (finding 3)

**2a - continuity.** Change the MEANING of the stored re-anchor origin: fold the
instance's accumulated whole beats in at assignment time so `_render_list` no longer
strips them. In `_maybe_reanchor`, replace the assignment (line 252) with:

```python
        # Whole-beat continuity (SOL2 finding 3): snap the FRACTIONAL phase onto
        # the live grid but keep the instance's accumulated whole-beat age, so
        # multi-beat envelopes (firework explosion -> embers) never replay their
        # opening beats after a BPM correction. origin = grid phase + nearest
        # whole-beat count to the instance's current local_beat.
        if inst.reanchor is not None:
            prev_mono, prev_origin, prev_bpm = inst.reanchor
            current_lb = prev_origin + max(0.0, float(now) - prev_mono) * (prev_bpm / 60.0)
        else:
            current_lb = inst.born_abs_beat % 1.0 + (
                max(0.0, float(now) - inst.born_monotonic) * (inst.born_bpm / 60.0)
            )
        phase = float(abs_beat) % 1.0
        whole = max(0.0, round(current_lb - phase))
        inst.reanchor = (float(now), phase + whole, max(1.0, float(bpm)))
        self._diverged_since = None
```

And in `_render_list`, change the re-anchor branch (lines 279-281) to use the stored
origin directly (it now already carries the whole beats):

```python
            if quantize and inst.reanchor is not None:
                ra_mono, ra_origin, ra_bpm = inst.reanchor
                local_beat = ra_origin + max(0.0, float(now) - ra_mono) * (ra_bpm / 60.0)
```

Note the tuple SHAPE is unchanged (mono, origin_beat, bpm) - only the second
element's meaning widens from "abs_beat at re-anchor" to "local-beat origin at
re-anchor". `local_beat % 1.0` is unchanged (origin ≡ grid phase mod 1), so the
existing phase-modulo-one re-anchor tests must stay green as-is. If any existing
test asserts the raw tuple contents, re-pin it to the new origin semantics and say
so in your report.

**2b - divergence evidence hygiene.** Divergence must be observed CONTINUOUSLY;
missing, invalid, or unpermitted samples are not evidence. Three edits:
1. Module constant near the other re-anchor constants:
   `DIVERGENCE_GAP_RESET_S = 1.0` with a comment: any gap this long between
   continuous-mode ticks means observation was interrupted (healthy frame cadence is
   tens of ticks per second; the sustain window is 3.0 s), so the divergence timer
   restarts rather than counting wall-clock time across the gap.
2. Track the last continuous-mode tick: add `self._last_continuous_tick: float | None = None`
   in `__init__`; in `on_tick`'s continuous branch, BEFORE calling
   `_maybe_reanchor`, do:
   ```python
            gap_reset = (
                self._last_continuous_tick is not None
                and float(now) - self._last_continuous_tick > DIVERGENCE_GAP_RESET_S
            )
            self._last_continuous_tick = float(now)
            if gap_reset:
                self._diverged_since = None
   ```
   (Wrap restarts already clear the timer; keep that.)
3. In `_maybe_reanchor`, the early return `if not self._instances or bpm <= 0.0`
   must clear the timer for invalid samples: split it -
   `if not self._instances: return` then
   `if bpm <= 0.0: self._diverged_since = None; return`.
   Also add `self._diverged_since = None` in `animate()` (unpermitted/paused ticks
   are not divergence evidence).
   Also `reset()` / `configure()` - verify they already clear `_diverged_since`
   (configure creates fresh state at line ~181); if not, clear it there too.

Tests (extend `tests/test_beat_sync_engine.py`, pure - no runner needed):
1. `test_reanchor_preserves_whole_beat_age` - continuous mode; drive `on_tick` at
   bpm 150 until the instance's `local_beat` exceeds 8.0 (SOL2 shape); then feed
   bpm 127 (delta > 2.0) continuously past the 3.0 s sustain so a re-anchor fires.
   Assert: post-re-anchor `local_beat` >= (pre-re-anchor local_beat - 1.0) - i.e.
   NO rewind toward 0 - AND `local_beat % 1.0` equals `abs_beat % 1.0` within 1e-6
   at the re-anchor tick (phase snapped to grid).
2. `test_feed_gap_resets_divergence_timer` - start a divergence (one out-of-band
   sample), advance `now` by 2.0 s with NO on_tick calls, then resume out-of-band
   samples: assert no re-anchor happens until a FRESH 3.0 s continuous window
   elapses after resumption.
3. `test_zero_bpm_sample_clears_divergence` - out-of-band sample (timer starts),
   then a `bpm=0` tick, then out-of-band again: assert the timer restarted (no
   re-anchor at the original deadline).
4. `test_paused_animate_clears_divergence` - out-of-band sample, then `animate()`
   calls (paused), then out-of-band: same restart assertion.

Commit: `SOL2-F3: re-anchor keeps whole-beat age; divergence needs continuous
evidence` + explicit paths.

### Task 3 - `led_look_director.py`: rebuild the shuffle bag when subset membership changes (finding 4)
In `_look_name_for_backend`, rebuild whenever the cached bag's membership differs
from the current subset, in BOTH the real and peek paths. Replace the condition at
line 524:

```python
        bag = self._role_shuffle_bags.get(key, ())
        if cursor % len(subset) == 0 or not bag or set(bag) != set(subset):
```

(the body stays as-is; the peek branch inside already re-shuffles with RNG state
restored, which is exactly the preview of the would-be new bag).

Tests (extend `tests/test_led_look_director.py`):
1. `test_shuffle_bag_rebuilds_when_preference_subset_changes` - a drop bank with two
   disjoint 4-look same-backend subsets A and B; commit with preference `n in A`
   (bag built from A), then commit with preference `n in B`: assert the second pick
   is in B. Repeat over several seeds/cursors so the mid-cycle case (cursor % len
   != 0) is covered.
2. `test_shuffle_bag_cycle_intact_for_stable_subset` - with an unchanging
   preference, a full cycle of commits yields each subset member exactly once
   (existing shuffle semantics preserved).

Commit: `SOL2-F4: shuffle bag rebuilds on subset membership change` + explicit
paths.

### Task 4 - narrowing-list preferences: empty F2xF4 falls back to F2, never the full bank (finding 5)
Make the preference a SEQUENCE of independently fail-open narrowing terms, applied
in order, instead of one AND predicate.

**4a - `led_look_director.py`.** In `_automation_decision_for_role` (and the
identical filter in `substitute_realtime_drop`), accept either a single callable or
a sequence of callables. Normalize once:

```python
        if look_preference is not None:
            preds = (
                tuple(look_preference)
                if isinstance(look_preference, (list, tuple))
                else (look_preference,)
            )
            for pred in preds:
                preferred = tuple(n for n in look_names if pred(n))
                if preferred:
                    look_names = preferred
```

Each term narrows only if its narrowing is non-empty - so an empty F4 intersection
keeps the F2-narrowed subset (never the full bank), and an empty F2 intersection
keeps the base-narrowed subset. When every intersection is non-empty this is
set-identical to today's AND composition (verify by reasoning in your report).
Update the `commit_role` / `substitute_realtime_drop` type hints to
`Optional[Callable[[str], bool] | Sequence[Callable[[str], bool]]]` and the
docstring comment that promises "each term only NARROWS" so it is now true.

**4b - `led_dispatch_policy.py`.** `_led_look_preference_predicate` (lines
2045-2067): return the TUPLE of terms instead of the AND lambda - order: v2
dressing base, F2 names, F4 bright:

```python
        preds = []
        if base is not None:
            preds.append(base)
        if f2_names:
            preds.append(lambda name, s=f2_names: name in s)
        if bright:
            preds.append(lambda name, s=bright: name in s)
        if not preds:
            return None
        return tuple(preds)
```

Callers (`commit_role` call at line 1998, LEDContext construction at line 1450,
`substitute_realtime_drop` at 1470) pass it through unchanged - verify each
consumer path ends at the Task 4a normalization (including
`led_look_director.py:200`, the tick path via `LEDContext.look_preference`).

**4c - `led_models.py`.** Widen the `LEDContext.look_preference` annotation (line
437) to accept the sequence form. No runtime logic there (`compare=False` stays).

Tests:
1. Extend `tests/test_led_look_director.py`:
   `test_preference_terms_narrow_independently` - bank with F2 subset present, F4
   subset disjoint from F2. Commit with `[f2_pred, f4_pred]`: assert pick is in the
   F2 subset (NOT the full bank). And with intersecting F2/F4 subsets: assert pick
   is in the intersection.
2. Extend `tests/test_lighting_moments_v2_f4.py` (the existing F2/F4 policy-level
   harness): an integration-shaped case where the active family/tier cell has no
   F4-bright member during a euphoric stretch - assert the committed drop look
   still belongs to the F2 cell. Follow the file's existing fixtures for wiring
   `_led_f2_drop_look_names` / `_led_f4_euphoric_bright`.
3. Single-callable back-compat: the existing `commit_role` tests passing a bare
   callable must pass unmodified.

Commit: `SOL2-F5: preference terms narrow independently; empty F2xF4 falls back to
F2 pool` + explicit paths.

### Task 5 - docs + registry
- `docs/status/active_work_registry.md`: RE-READ the file fresh immediately before
  editing (parallel lanes append rows). Take the next free AWR id (max is AWR-200
  as of this spec's authoring - re-check). One row for this whole round: SOL2
  launch-blocker fixes 2-5, listing the four commits, test counts, and
  SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
- `docs/subsystems/led_govee.md`: one sentence each where the affected behavior is
  described (idle grace, re-anchor, shuffle bags, F2/F4 preference narrowing).
- `docs/validation/software_test_inventory.md`: add the new test names (re-read
  fresh first; another lane may append concurrently).

Commit: `SOL2 fixes 2-5: registry row + docs` + explicit paths.

## Part C - Invariants That MUST Still Hold (live safety)
- Fail-open beats fail-dark: Tasks 1-2 only ever REDUCE unwanted darkness/replays;
  no path gains new darkness. Task 4 only narrows within operator-configured pools;
  the C4 breakdown invariant (diy_eligible empty subset keeps the full bank) is
  untouched.
- Emergency/blackout precedence unchanged (`_emergency_teardown`, blackout paths in
  `govee_realtime_runner.py` not modified beyond the one lock-block line).
- The 200 Hz push loop and runner thread gain NO blocking I/O.
- `StateManager` remains the only `DeckState` writer; nothing here mutates deck
  state.
- Scripted tracks: v2 stands down (`_led_f2_drop_look_names` returns None) -
  unchanged.
- preview_role stays mutation-free and filterless; substitute_realtime_drop still
  never advances `_role_cursors["drop"]`.

## Part D - Tests
- New/extended tests per task above - all pure in-memory seams (fake transports,
  synthetic anchors, direct director/engine construction); no file, network,
  device, or subprocess dependency.
- Scoped runs (from repo root): `python3 -m unittest tests.test_govee_realtime_runner
  tests.test_beat_sync_engine tests.test_led_look_director
  tests.test_lighting_moments_v2_f4 tests.test_led_state_manager` - all green.
- Full: `python3 -m unittest discover tests`, reconciled BY NAME. Pre-existing reds
  you must NOT chase (known, owned elsewhere): patch_d
  `test_drop_slot_color_smoke_and_snap`; `test_export_pack_parity_self_heal` x2;
  `soundswitch_laser_player` golden `slot=16`; `soundswitch_parity_oracle`
  `capture_rows`; patch_c `test_live_config_slot_color_smoke` and
  `test_tracked_and_live_configs_validate`; patch_d
  `test_tracked_and_live_configs_validate` (live-config incident, another round);
  patch_b `test_tracked_config_validates` (AWR-197 re-pin pending, another lane).
  Pack byte-identity flappers: isolate; green in isolation = baseline. Zero NEW
  reds beyond these.
- Hard checks: `python3 tools/check_docs_metadata.py`,
  `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py` -
  all green.

## Part E - Acceptance (definition of done)
- [ ] Tasks 1-4 diffs match the spec shapes; no drive-by edits; fence files
  untouched.
- [ ] All new tests green; scoped suites green; discover reconciled by name per
  Part D; hard checks green.
- [ ] Docs + registry row landed per Task 5 (fresh-read before each shared-doc
  edit).
- [ ] Five commits by explicit paths with the exact message prefixes.
- [ ] STAGED ONLY: no process contact; the running bridge keeps old behavior until
  the operator's next menubar start.

## When You Finish
Report: changed files, commit ids, test counts (scoped + discover with red names),
and for each finding one plain-language line for the operator:
- F2: "a brief beat-feed hiccup can no longer black the room out on the next
  hiccup - the lights only go dark if the feed stays bad past the grace window."
- F3: "a tempo correction mid-effect no longer replays the firework/strobe opening;
  the effect keeps its place and just locks onto the corrected beat."
- F4: "every drop now picks from the family/tier pool it was routed to, never the
  previous drop's pool."
- F5: "when the routing pool and the euphoric-bright list don't overlap, the pick
  stays inside the routing pool instead of the whole drop bank."
Evidence class: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
