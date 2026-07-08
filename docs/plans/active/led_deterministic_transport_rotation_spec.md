# Implementation Spec - Deterministic Mixed-Transport LED Look Rotation (Phase 2)

status: planned
last_verified_commit: 8419962
owner: operator (Brandon) via Claude Fable 5 orchestration session 2026-07-08
registry: AWR-149

Execute tasks **in order, one commit per task**. Every file:line below was verified at HEAD
`8419962` (post-AWR-146) on 2026-07-08. Labels: [confirmed] = read in current code / operator-
recorded, [assumed] = inferred, [unknown] = stated where load-bearing.

> You may be in a dirty git worktree shared with other agents and an auto-sync hook. NEVER revert
> existing changes you did not make. Commit ONLY by explicit file paths (`git add <path> <path>`),
> never `-a` or `add -A`. NEVER use destructive git. Work directly on `main`. Touch ONLY the files
> this spec lists; if a change seems to need another file, STOP and report.

## Part A - Context & Executive Constraint (verified; read, do not implement)

**Operator taste decision, recorded 2026-07-08 — DO NOT RE-LITIGATE:** the old "pin roles
exclusively to one transport" framing is REJECTED. Brandon keeps BOTH cloud DIY looks AND
realtime looks in every role (groove/buildup/drop/ambient all have good looks on each side).
Phase 2 = make the mixed-transport rotation DETERMINISTIC and knockout-safe — planned alternation
instead of the session-long sticky+eligibility coin flip — NOT exclusive pinning. Within-drop
choreography (future v2 F2) renders only on realtime drops: solve by letting choreography ride
the RT drop picks that this plan guarantees recur, while cloud drops keep their scene. Never
delete or filter out cloud drops.

The mechanism being replaced [confirmed at HEAD]:

1. Each role's cursor starts at `rng.randrange(len(bank))` per session
   (`led_look_director.py:59-65`) — random phase per launch.
2. Per pick (`_automation_decision_for_role`, `:271-344`): bank → DIY-eligibility filter
   (`:305-308`; C4 invariant: empty subset keeps the FULL bank) → v2 look-preference filter
   (`:309-312`) → **WI-7 transport-sticky filter (`:314-328`): prefer looks whose backend matches
   the role's last-dispatched backend (`_last_role_backend`, written `:295,:343`)**. The sticky
   latch survives until `reset_for_track()` (`:67-69`, called from `state_manager.py:2122`).
   Net effect: which transport a role runs on for a whole session is a palette-weighted coin
   flip that LATCHES — the 2026-07-08 audit measured one night groove-on-realtime, the next
   groove-100%-cloud, and a mid-mix cloud drop (`drop_diy_3`) that F2 choreography could never
   ride.
3. Look choice inside the bank uses per-role shuffle bags with RNG (`_look_name_for_role`,
   `:346-369+`), with a `peek` mode that restores RNG state. ALL automation roles are shuffled
   (`__main__.py:495` passes `shuffled_roles=LED_AUTOMATION_ROLE_ORDER`).
4. `preview_role` (`:201-229`) previews the next pick WITHOUT the eligibility/preference filters
   — a pre-existing gap; this spec preserves that parity, it does not fix it.
5. The watcher launches the bridge with `RBSS_LED_TRANSPORT_STICKY=1`
   (`scripts/ss_bridge_watcher.sh:166`); the director's env default is also ON (`:57`).
6. Frequent transport transitions are now safe [confirmed]: AWR-145 razer keepalive +
   assert-on-takeover + dispatch retry, AWR-146 frame-engine process + 3-layer blackout
   brightness backstop. This chain is WHY planned alternation is acceptable now.
7. No test anywhere asserts the sticky behavior (`rg "TRANSPORT_STICKY|transport_sticky|
   _last_role_backend" tests/` is empty) [confirmed].

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_look_director.py`, `scripts/ss_bridge_watcher.sh` (one env line),
  `tests/test_led_look_director.py`, `tests/test_ss_bridge_watcher.py` (only if it
  golden-asserts the env list), the Part E docs, and `docs/status/active_work_registry.md`
  (status flip only — the AWR-149 row exists before you start; verify with
  `rg -n "AWR-149" docs/status/active_work_registry.md` and STOP if absent).
- Out of scope — must not change: bank/look config values or schema, `led_models.py`,
  `led_dispatch_policy.py`, `led_dispatch_coordinator.py`, `state_manager.py`,
  `led_color_engine.py`, all `govee_*` files, laser/SoundSwitch subsystems. No new config keys,
  no new env flags.
- Behavior that must not change: emergency-blackout, manual-override, safe_default, and
  target-override paths in `tick()` (byte-identical decisions); the C4 empty-eligibility
  invariant; paired post-drop queueing precedence (`:284-296`) and `drop_pairs`; dwell/cooldown
  gates (coordinator-side); AWR-145 retry semantics (cached decision resent, director never
  re-ticked); `tick()` stays pure — no I/O, no unbounded work.
- Error handling: selection must never return a look outside `self._config.looks`; an empty
  bank/role still returns None exactly as today; no new try/except.

### Task 1 - `led_look_director.py`: pure backend plan function

Module-level pure function (no RNG, no self):

```python
def plan_backend_sequence(look_names, backend_of) -> tuple[str, ...]:
    """Deterministic, evenly-interleaved backend sequence for one role's
    (already-filtered) bank. Partition names by backend preserving order; the
    returned tuple has one backend label per future pick, length == number of
    distinct-backend slots in one full cycle (== len(look_names)), with the
    smaller subset's slots spread evenly through the larger's (Bresenham
    merge). Ties and ordering: 'realtime_razer' leads (F2-forward). A
    single-backend bank returns that backend uniformly. Empty input -> ()."""
```

Exact interleave rule (so two implementations can't diverge): with subsets sized `a >= b`
(a-backend leads; if sizes tie, `realtime_razer` leads), emit `a` slots of the leader and place
the `b` follower slots at indices `floor((i + 1) * (a + b) / (b + 1))`-style even spacing — or
any equivalent Bresenham merge, PROVEN by the exact-tuple tests in Part D (the tests are the
contract; 6 RT + 2 cloud must yield cloud at two evenly spaced positions, e.g.
`(rt, rt, cloud, rt, rt, rt, cloud, rt)` or the symmetric spacing your merge produces — pick one,
freeze it in the tests).

### Task 2 - `led_look_director.py`: planned alternation replaces WI-7 sticky

In `_automation_decision_for_role`, after the eligibility (`:305-308`) and preference
(`:309-312`) filters, REPLACE the sticky block (`:313-330`) with:

1. `plan = plan_backend_sequence(look_names, lambda n: self._config.looks[n].backend)` (names
   not in `self._config.looks` are excluded before planning; if nothing remains, return None as
   today).
2. `chosen_backend = plan[cursor % len(plan)]` where `cursor` is the existing per-role cursor.
3. `subset = tuple(n for n in look_names if self._config.looks[n].backend == chosen_backend)`.
4. Look choice within `subset` via the shuffle-bag machinery, generalized: `_role_shuffle_bags`
   and a NEW `self._role_backend_cursors: dict[tuple[str, str], int]` are keyed by
   `(role, backend)` instead of `role`. The role cursor (existing `:342` `cursor + 1`) advances
   the PLAN only; the `(role, backend)` cursor advances only when that backend is picked and
   drives the bag position. RNG therefore affects WHICH look within the chosen transport, never
   WHICH transport.
5. DELETE: `_transport_sticky_enabled` + the env read (`:57`), `_last_role_backend` (`:58`,
   `:69`, `:295`, `:343`), and the sticky filter block. `reset_for_track()` keeps its name and
   signature (caller `state_manager.py:2122` untouched); its body becomes a documented no-op
   (`pass` + docstring: plan cursors deliberately persist across tracks).

### Task 3 - `led_look_director.py`: deterministic session phase

Replace the `rng.randrange(len(look_names))` cursor init (`:63`) with `0`. Every session starts
each role at plan index 0 (realtime-leading). Look variety still comes from the per-(role,
backend) shuffle bags. [This is the "deterministic" half of the operator constraint — do not
keep any RNG in cursor or plan initialization.]

### Task 4 - `led_look_director.py`: preview parity

`preview_role` (`:201-229`) must preview through the SAME plan logic: compute
`chosen_backend` from the raw bank (filterless — preserve the existing preview gap exactly),
peek the `(role, backend)` bag with the existing RNG-state-restore mechanism (`:358-367`), and
return the same look+backend the next unfiltered commit would produce, without mutating any
cursor, bag, or RNG state. Same for the `peek=True` path used at `:220`.

### Task 5 - `scripts/ss_bridge_watcher.sh`: drop the dead env line

Delete the `RBSS_LED_TRANSPORT_STICKY=1 \` line (`scripts/ss_bridge_watcher.sh:166`). This file
is under the `bridge_menubar` contract: run `python3 -m unittest tests.test_bridge_menubar` and
update `tests/test_ss_bridge_watcher.py` ONLY if it golden-asserts the launch env list. Also
`rg -n "TRANSPORT_STICKY|WI-7|transport-sticky" docs/` and update every doc that documents the
flag or WI-7 (expected: `docs/subsystems/led_govee.md`; possibly the env-flag tables).

## Part C - Invariants That MUST Still Hold (live safety)

- **Both transports stay reachable in every role whose bank has both** — no code path may
  filter cloud looks out of a bank (the executive constraint; exclusive pinning is rejected).
- **Deterministic transport**: two directors with identical config and identical pick sequences
  produce IDENTICAL backend sequences per role regardless of RNG seed; a bridge relaunch
  reproduces the same transport phase from pick 0.
- `tick()` stays pure (no I/O, bounded); emergency/manual/safe_default/target-override decisions
  byte-identical to today.
- C4: an eligibility predicate that empties the bank keeps the FULL bank (a DIY-only bank must
  never be emptied by a non-matching palette); the plan is computed on whatever set survives
  filtering.
- Paired post-drop: a queued post_drop bypasses the plan and advances NO cursor (parity with
  today `:284-296`).
- AWR-145 dispatch retry resends the cached decision without re-ticking the director — retries
  must not advance plan or bag cursors (guaranteed structurally: retry never calls the director).
- Dwell (WI-3) and cooldown (WI-5) gates in the coordinator are untouched; planned transport
  flips arrive at role re-pick cadence and pass through those gates exactly as any pick does.
- Knockout-safety is inherited, not reimplemented: every realtime takeover still goes through
  `request_activate_assert` (AWR-145) and the frame-engine chain (AWR-146). Nothing in this
  change touches transports, runners, or blackout paths.
- F2-forward: RT drop picks recur at the planned cadence whenever the drop bank contains RT
  looks; the decision's existing `backend` field is where future choreography attaches. No
  choreography code in this spec.

## Part D - Tests (pure; extend `tests/test_led_look_director.py`)

1. `plan_backend_sequence`: exact expected tuples for 6RT+2cloud (frozen spacing), 1+1
   (alternation, RT first), 3RT+3cloud (RT leads ties), single-backend, empty; order stability
   within subsets.
2. Determinism: two directors, different RNG seeds, same config, same 12-pick role sequence →
   identical backend sequence; look names within a backend may differ.
3. No-latch regression: groove bank 2RT+1cloud → 6 consecutive groove picks follow the plan
   cycle (cloud recurs at its planned slots) — this test FAILS on the old sticky code.
4. Session-phase determinism: fresh directors with arbitrary seeds all start every role at plan
   index 0.
5. Eligibility rebase: predicate filtering out all cloud looks → all-RT plan; predicate restored
   → cloud returns at planned cadence; predicate rejecting everything → full bank (C4).
6. Preview parity: `preview_role` (and the `:220` peek path) returns the same look+backend as
   the next unfiltered pick and mutates nothing (call twice, then commit, compare).
7. Paired post-drop still bypasses the plan and advances no cursor.
8. Suite: `python3 -m unittest tests.test_led_look_director tests.test_led_state_manager
   tests.test_led_dispatch_coordinator tests.test_bridge_menubar` then
   `python3 -m unittest discover tests` — green except the 5 known environmental reds
   (live-config LED, export-parity ×2, SS golden ddj_slots, SS parity-oracle fixture).

## Part E - Acceptance (definition of done)

1. All Part D tests pass; full suite at the known-reds baseline; 3 hard checks green
   (`tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`).
2. `led_govee` contract docs_update where content is affected: `docs/subsystems/led_govee.md`
   (WI-7 sticky → deterministic planned alternation; both-transports-per-role is an operator
   contract), `docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`,
   `docs/validation/software_test_inventory.md`; `bridge_menubar` side: any doc listing the
   deleted env flag. Registry row AWR-149 → implemented/software-tested. Status language:
   implemented / software-tested / hardware-unvalidated only.
3. No changes outside the Part B file list; explicit-path commits only.

## When You Finish

Report changed files, test/check results, anything blocked. Then a plain-language operator
summary: which transport carries each look is no longer a per-session coin flip that latches —
it now follows a fixed, even rotation through everything in the bank, so both the cloud scenes
and the realtime looks each role owns keep showing up, in a predictable pattern, every session;
look variety within each side is still shuffled; nothing about look content, blackouts, timing,
or the new frame engine changed; the live gate is his next mix (watch: cloud looks reappearing
in roles that had been stuck realtime-only, and vice versa, with no stuck-scene moments — the
keepalive chain is what makes those switches safe).
