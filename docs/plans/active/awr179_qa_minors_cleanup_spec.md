---
doc_status: current
truth_level: implementation-spec
last_verified_commit: d93f047
last_verified_date: 2026-07-09
validation_scope: >
  AWR-179: one scoped build round clearing five of the six CONFIRMED MINOR findings
  from the AWR-172 showcase QA program (the sixth, D2-F2, is already fixed at HEAD by
  f95a53b). Spec authored and every cite verified at HEAD d93f047 by the QA-minors
  manager (Fable/HIGH, tmux qaminors). Implementer: one Opus lane. All work is
  software-only; a live session is running — ZERO runtime contact.
---

# Implementation Spec — AWR-179: QA minors cleanup (five findings, one round)

## Part A — Context & root cause (verified at HEAD `d93f047`; read, do not implement yet)

Source of truth: AWR-172 registry row + `docs/research/qa_showcase_review_2026_07_09.md`.
Line numbers below were verified at `d93f047` on 2026-07-09 ~15:45. The tree moves under
you (auto-sync + parallel lanes): **anchor by symbol, re-verify every cite at HEAD before
editing** (Opus harness rail #7).

- **D2-F2 is NOT in this round** [confirmed]: fixed at HEAD by `f95a53b` (F2 plan attach
  hoisted out of `markers_changed`, `state_manager.py` ~:1551-1559, + 2 regression tests
  in `tests/test_smart_transitions.py`). Do not touch it.

### Finding 1 — D4-F3: pack export reads `git rev-parse HEAD` twice per publish
[confirmed] `tools/export_soundswitch_pack.py`: `_generator_commit()` (def at :175) is
called at :142 (manifest) and :276 (sidecar). Two subprocess reads → inconsistent
provenance if an auto-sync commit lands between (AWR-169 class; currently inert — no
reader compares the field; `scripts/bridge_menubar.py:169` keys only on
`source_fingerprint`).
Root-cause fix: **read once per export invocation, thread the value through** to both
write sites as a parameter. NO module-level/lru cache (a long-lived caller would then
write stale commits on later exports — a new inaccuracy).

### Finding 2 — D4-F1: `govee_manual_trigger.py` provenance gate unusable under auto-sync
[confirmed] `tools/govee_manual_trigger.py`: `validate_provenance()` (:190) appends
`phase1_manifest_commit_mismatch` to `errors` when the phase1 manifest's `repo_commit`
differs from current `rev-parse HEAD` (:203, read at :98), and `ok_for_devices` (:290-297)
hard-gates on it → `main()` aborts (:611-614) before any device read. Auto-sync moves HEAD
every turn, so ANY manifest older than the last commit aborts the tool even when well
inside the 24 h freshness window (`PROVENANCE_MAX_AGE_HOURS`, :35). Fails safe today, but
the tool is permanently unusable. AWR-169 precedent: the export tool's commit-equality
guard was deliberately removed for exactly this reason (in-code `ponytail:` note).
Root-cause fix: **demote commit mismatch from gate to recorded warning; keep every other
gate term** (branch mismatch, artifacts missing, stale >24 h, `generated_at` invalid,
`source_command` unexpected) — still failing safe.
[confirmed] NO tests exist for this tool; `validate_provenance(manifest, repo_context,
now_utc)` is pure EXCEPT `Path(artifact_path).exists()` checks against the module-level
`PHASE1_SUMMARY_PATH` / `PHASE1_DEVICES_PATH` / `PHASE1_SCENES_PATH` constants.
[confirmed] NO change contract covers this file (grepped `docs/agents/change_contracts.yml`)
→ per AGENTS.md §7 the contract must be extended FIRST (same commit is fine).

### Finding 3 — D4-F2: unbounded anlz-worker thread spawn per load
[confirmed] `state_manager.py` `_start_anlz_worker()` (:2269) spawns a bare daemon
`threading.Thread` per track load (:2335-2340, closure `_anlz_worker` :2286 calling the
heavy `_read_runtime_anlz_data` :2288 — cache-miss extraction measured ~16 s,
GIL-releasing). A rapid multi-track cache-miss storm spawns N concurrent extractions →
transient CPU/scheduler contention (AWR-172 D4 measured; GIL itself fine). Stale results
are already discarded on consumption via the `load_gen` guard, but stale extractions
still RUN to completion today.
Fix shape (kickoff-sanctioned "in-flight cap"): **a `threading.BoundedSemaphore(2)`
acquired inside the worker body** (spawn site stays non-blocking; push loop untouched),
plus a stale-generation early-exit at the top of the gated section so queued stale
extractions exit in microseconds instead of running ~16 s. Keep plain daemon threads —
do NOT switch to `ThreadPoolExecutor` (its interpreter-exit join can delay shutdown
behind an in-flight 16 s extraction; today's daemon threads die instantly).

### Finding 4 — D4-F4: three per-load structures grow monotonically
[confirmed, grep-proven: no pop/clear/del path for any of the three]
1. `state_manager.py:605` `_drop_presentation_audible_start_beat: dict[(deck, load_gen), float]`
   — written only for the audible active deck (:2728-2730 in `_drop_presentation_tick`,
   def :2660; `track_key = (active, d.load_gen)` :2698).
2. `state_manager.py:821` `_arm_times: dict[(track_id, deck), float]` — 2.0 s debounce map
   in `_arm_scripted` (def :3081, written :3116); any entry older than 2.0 s is dead.
3. `led_color_engine.py:356` `_v2_bloomed: set[str]` — once-per-track-identity bloom
   latch, adds at :1227/:1235 in `_v2_maybe_arm_bloom`.
Growth is load-cadence (~tens-of-KB over a multi-hour set), no mask/loop consequence —
fix is hygiene: **trim at the natural point** (exact per-task instructions below).

### Finding 5 — D2-F1: F2 `abort_at` computed but never consumed ⚠️ BEHAVIOR-AFFECTING, DROPPABLE
[confirmed] `lighting_moments_v2.py`: `DarknessDecision.abort_at` (:353) is computed by
`_abort()` (:358-372, the D§4.1/OLC-B early darkness release — "darkness ends at the 2nd
consecutive present beat inside the window") and set for blackout decisions (:443-451),
but the only runtime consumer `transition_window_for()` (:811-827) reads `.beats` only.
The docstring-claimed early release was never wired. Bounded effect: up to ~3 extra
pre-drop dark beats on hard-family collapses with a pickup.

**Semantics — get this exactly right.** The dark window is a LEVEL in
`smart_phrasing.py` (:411-414): active while `beats_to_next_drop <=
snapshot.transition_window_beats`; the falling edge (:435-436) emits
`transition_mask_should_clear` which releases the mask. `abort_at` means darkness must
END at beat `abort_at` (window START unchanged at `drop − beats`). Therefore the wiring
is an EARLY DEACTIVATION of the level — expressed as a lower bound
`beats_to_next_drop > (drop − abort_at)` — which rides the existing falling-edge clear
path. Do NOT return a shortened window length from `transition_window_for` — that would
wrongly move the darkness START later, the opposite of the design.

Behavior delta (to be NAMED in docs, registry, and a pinned test): with F2 on, on a
hard-family collapse where the sub floor returns early, pre-drop darkness releases at
the abort beat — up to 3 fewer dark beats; the room re-lights EARLY (fail-open
direction, never darker). F2 off / scripted / no plan / no abort ⇒ byte-identical to
today. No new config key: the wiring rides F2's existing enable surface.

Edge that must fall out correctly: `abort_at == window start` ("floor back at entry
renders zero dark beats") ⇒ release-bound == window length ⇒ the window never
activates ⇒ zero dark beats. This is the design, not a bug.

**This task is droppable by executive ruling**: it is the LAST task, one isolated
commit, and no other task depends on it.

## Part B — Tasks (implement exactly, in order; ONE commit per task, explicit paths, never `-a`)

### Absolute rules
- **File fence** — you may touch ONLY: `tools/export_soundswitch_pack.py`,
  `tools/govee_manual_trigger.py`, `state_manager.py`, `led_color_engine.py`,
  `lighting_moments_v2.py`, `smart_phrasing.py`, `docs/agents/change_contracts.yml`,
  the named test files (incl. one NEW `tests/test_govee_manual_trigger.py`), and the
  contract-listed docs named in Part E. An improvement you notice elsewhere = a NOTE in
  your report, never an edit.
- **A live session is running. ZERO runtime contact**: never start/restart the bridge or
  any pad server, never write any live config (`config/*.json` that is not `*.example.json`),
  never open network/device/MIDI connections, no test may do device or network I/O.
- Behavior that must not change: everything outside the five findings. F2-off, scripted,
  and no-plan paths stay byte-identical (existing kill tests are the proof — they must
  stay green untouched). Do not modify existing tests except where a task names it.
- Error handling: propagate or fail closed; no broad try/except, no silent fallbacks.
- Do not commit secrets, live configs, or backup files. Never `git clean`.
- The four Opus-harness clauses, verbatim:
  1. You report evidence; the manager reviews; the executive gates. You never declare
     the round shipped.
  2. Do not pause at checkpoints for acknowledgment; run straight through unless
     genuinely blocked.
  3. If reality diverges from the spec (unknown name, missing file, unexpected state):
     STOP, write the .blocked signal with one line of evidence, and wait. Blocking is a
     success mode; invention is the failure mode.
  4. Touch ONLY spec-listed files; an improvement you notice = a NOTE in your report,
     never an edit.

### Task 1 — `tools/export_soundswitch_pack.py`: single HEAD read per export (D4-F3)
Read the call graph first: find the function(s) from which BOTH `_generator_commit()`
call sites (:142 manifest build, :276 sidecar write) are reached in one export/publish
invocation. Hoist ONE `generator_commit = _generator_commit()` read to the top of that
shared path and thread the string down as a parameter to both write sites. Keep
`_generator_commit()` itself unchanged (its no-git fallback behavior is load-bearing for
tests). No caching decorator.
Tests: extend the existing export-pack test coverage (follow prior art in
`tests/test_soundswitch_pack.py` / `tests/test_export_pack_parity_self_heal.py`) with one
test that patches `_generator_commit` with a counting side effect returning a DIFFERENT
value per call and asserts manifest and sidecar record the SAME value for one export
(i.e., exactly one read, or one value threaded through).
Baseline caution: `test_absent_fixtures_fall_back_to_committed_snapshot`,
`test_stale_venue_sha_snapshot_is_healed_at_export` (both in
`test_export_pack_parity_self_heal.py`) are named environmental reds — they stay red;
do NOT chase them; your new test must not depend on their fixtures.
Commit: `AWR-179 D4-F3: single generator-commit read per pack export` — paths:
`tools/export_soundswitch_pack.py` + the one test file you extended.

### Task 2 — `tools/govee_manual_trigger.py`: provenance gate mechanism fix (D4-F1)
1. `docs/agents/change_contracts.yml`: add `tools/govee_manual_trigger.py` to the
   `led_govee` contract's `code_globs` (contract-first, AGENTS.md §7).
2. In `validate_provenance()`: change the commit-mismatch branch (:203-204) to append
   `phase1_manifest_commit_drift` to `warnings` (not `errors`); remove the
   `"phase1_manifest_commit_mismatch"` term from `ok_for_devices` (:290-297). Audit the
   WHOLE return expression and every consumer of the result dict for other references to
   the removed error string (`ok_for_scenes`, the :611/:666/:782 abort paths) — the gate
   must now pass on commit drift alone and still hard-abort on: branch mismatch, missing
   manifest/artifacts, stale > `PROVENANCE_MAX_AGE_HOURS`, invalid `generated_at`,
   unexpected `source_command`. Fail-safe is preserved by keeping all of those as errors.
3. NEW `tests/test_govee_manual_trigger.py` — pure-function tests of
   `validate_provenance` (inject `now_utc`; point `PHASE1_SUMMARY_PATH` /
   `PHASE1_DEVICES_PATH` / `PHASE1_SCENES_PATH` at temp files via `unittest.mock.patch`,
   since the function checks `Path(...).exists()` on them; follow the tools-module import
   pattern used by existing `tests/test_export_pack_parity_self_heal.py`). Four cases
   minimum: (a) fresh artifacts + commit drift ⇒ `ok_for_devices` True + warning
   recorded; (b) artifacts older than 24 h ⇒ False; (c) branch mismatch ⇒ False;
   (d) devices record missing ⇒ False. NO network, NO device I/O, NO real git
   dependency (pass `repo_context` as a plain dict).
Commit: `AWR-179 D4-F1: govee tool provenance gates on freshness+branch, commit drift is a warning`
— paths: `tools/govee_manual_trigger.py`, `docs/agents/change_contracts.yml`,
`tests/test_govee_manual_trigger.py`.

### Task 3 — `state_manager.py`: anlz-worker in-flight cap (D4-F2)
1. In `StateManager.__init__` (near the other threading fields): add
   `self._anlz_extract_gate = threading.BoundedSemaphore(2)`.
2. In `_start_anlz_worker`'s `_anlz_worker` closure (:2286): wrap the ENTIRE existing
   body in `with self._anlz_extract_gate:`, and as the FIRST statement inside the gate
   add a stale-generation early-exit:
   `if self._deck[bridge_deck].load_gen != gen: return`
   (benign racy int read — worst case the extraction runs and its result is discarded by
   the existing consumer-side `load_gen` guard, i.e., today's behavior). Add a
   `ponytail:` comment naming the ceiling: cap 2 concurrent extractions; parked threads
   are cheap and exit in microseconds once stale.
3. The SPAWN SITE (:2335-2340) and everything on the state-manager thread stay
   non-blocking and unchanged (`Thread(daemon=True).start()` as today).
Tests: in the test file where `_start_anlz_worker` coverage lives (find it: grep tests
for `_start_anlz_worker` / `anlz_worker`; if none, add to a fitting existing
state-manager test file), patch `state_manager._read_runtime_anlz_data` with a stub that
blocks on an `Event` and records a concurrency high-water mark; start ≥5 workers;
assert max concurrent ≤ 2; assert a worker spawned with a stale `gen` returns without
calling the stub. Use generous timeouts, no sleeps as synchronization.
Commit: `AWR-179 D4-F2: cap concurrent anlz extractions at 2 with stale-gen skip` —
paths: `state_manager.py` + the test file.

### Task 4 — trim the three monotonic structures (D4-F4)
1. `state_manager.py` `_drop_presentation_tick` (:2660): immediately after
   `track_changed` / `active_deck_changed` are computed (:2698-2702), add:
   `if track_changed: self._drop_presentation_audible_start_beat.pop((active, previous_load_gen), None)`
   — this is OUTSIDE the existing `_drop_presentation_armed_key is not None` block
   (:2706); it must run on every track change. This removes exactly the dead prior-gen
   key (keys are written only for the audible active deck, so per-deck liveness is one
   key).
2. `state_manager.py` `_arm_scripted` (:3081): after `now = time.monotonic()` and before
   (or after) the debounce check, prune dead entries in one line:
   `self._arm_times = {k: v for k, v in self._arm_times.items() if now - v < 2.0}`
   (arms are per-track-load rare; O(n) here is nothing; pruned entries were failing the
   `< 2.0` debounce test anyway — behavior identical).
3. `led_color_engine.py` `_v2_maybe_arm_bloom` (:1212): before the add sites, add a cap:
   `if len(self._v2_bloomed) >= 512: self._v2_bloomed.clear()` with a `ponytail:` comment
   naming the ceiling (after 512 distinct track identities — many hours — a repeated
   track may bloom once more; bloom is a claim-ranked color breath, never a mask owner,
   so the consequence is one benign extra bloom).
Tests (this task's required proof: NO mask/loop consequence):
- drop-presentation dict: in `tests/test_state_manager_drop_presentation.py` prior art,
  drive a track change and assert the prior `(deck, load_gen)` key is gone and the
  new track's damper latch still works.
- `_arm_times`: arm, advance the clock stub past 2.0 s, arm a different track, assert the
  old key is pruned and debounce still blocks a <2.0 s re-arm.
- `_v2_bloomed`: fill past the cap, assert the set was cleared and a subsequent bloom
  arm still produces only a bloom claim (no exception, no mask/owner state touched, no
  stuck look).
Commit: `AWR-179 D4-F4: bound the three per-load structures (drop-damper keys, arm debounce, bloom latch)`
— paths: `state_manager.py`, `led_color_engine.py`, the two test files.

### Task 5 (LAST, DROPPABLE) — wire F2 `abort_at` early darkness release (D2-F1)
One isolated commit; nothing else in the round depends on it.
1. `lighting_moments_v2.py`: add alongside `transition_window_for` (:811):
   ```python
   def transition_release_for(plan, abs_beat, smart_drop_beats) -> float:
       """Beats-before-drop at which pre-drop darkness releases early (OLC-B abort),
       for the next upcoming drop. 0.0 = no early release (identical to today)."""
   ```
   Same next-upcoming-drop selection as `transition_window_for` (:818-823). Return
   `float(entry_drop_beat - dark.abort_at)` ONLY when the entry's darkness `kind ==
   "blackout"` and `abort_at is not None`; every other case (no plan, no abs_beat, no
   upcoming drop, no entry, balloon/dip/snap/perc-flick, abort_at None) returns 0.0.
   Note: `for_drop` is keyed by the drop beat you looked up — use that beat, not a
   field you invent (re-read the `F2TrackPlan.for_drop` contract at HEAD first).
2. `smart_phrasing.py`: add field `transition_release_beats: float = 0.0` to
   `SmartPhrasingSnapshot` (default keeps every existing constructor call valid). Change
   the level condition (:411-414) to:
   ```python
   if beats_to_next_drop <= snapshot.transition_window_beats:
       if (snapshot.transition_release_beats <= 0.0
               or beats_to_next_drop > snapshot.transition_release_beats):
           new_transition_window_active = True
   ```
   Nothing else changes: the existing falling edge (:435-436) fires
   `transition_mask_should_clear`, and the `smart_drop_crossing` backstop (:441) is
   untouched. `release == 0.0` reproduces today's behavior bit-for-bit including the
   `beats_to_next_drop == 0` edge.
3. `state_manager.py`: add `_f2_transition_release_beats(self, d, abs_beat, smart_drop_beats)`
   directly below `_f2_transition_window_beats` (:4999) with IDENTICAL gating (not
   `self._f2_enabled` → 0.0; `scripted_id` → 0.0; else delegate to
   `lighting_moments_v2.transition_release_for`). Feed it in the ONE
   `SmartPhrasingSnapshot(...)` construction (:5049-5066) as
   `transition_release_beats=...` with the same `(d, abs_beat_pos if bpm > 0 else None,
   smart_drop_beats)` arguments the window field uses.
4. Docs (led_govee contract): name the behavior delta in
   `docs/subsystems/led_govee.md`'s F2 darkness section — one paragraph: early release
   at the abort beat, ≤3 fewer dark beats, fail-open direction, F2-off untouched.
Tests (pinned, all new; do not weaken any existing kill test):
- `tests/test_lighting_moments_v2.py`: `transition_release_for` value table — blackout
  with `abort_at` ⇒ `drop − abort_at`; blackout without ⇒ 0.0; balloon/dip/snap ⇒ 0.0;
  no plan / no beat / drop passed ⇒ 0.0; `abort_at == window start` ⇒ release == window
  length.
- `tests/test_smart_phrasing.py`: (a) release=0 ⇒ state sequence IDENTICAL to a run
  without the field (the byte-identity pin); (b) release>0 ⇒ window activates at the
  window edge, deactivates when `beats_to_next_drop` reaches the release bound,
  `transition_mask_should_clear` fires on that falling edge BEFORE the drop, and the
  window does NOT re-arm before the drop; (c) `abort == window start` ⇒ window never
  activates, no arm ever emitted.
- One state-manager-level test (prior art: wherever `_f2_transition_window_beats` is
  tested — grep) pinning the gate: F2 off ⇒ release 0.0; scripted ⇒ 0.0; plan with
  abort ⇒ plumbed value.
Commit: `AWR-179 D2-F1: wire F2 abort_at early darkness release (OLC-B)` — paths:
`lighting_moments_v2.py`, `smart_phrasing.py`, `state_manager.py`,
`docs/subsystems/led_govee.md`, the three test files.

## Part C — Invariants that MUST still hold (live safety)
- The 200 Hz push loop gains NO blocking I/O and NO new work beyond O(1) dict ops; the
  semaphore is acquired only on worker threads; the spawn site stays non-blocking.
- `StateManager` remains the only writer of `DeckState`; workers publish events only.
- F2-off, scripted, and no-plan paths are byte-identical to today (existing kill tests
  green, plus the new release=0 identity pin).
- Fail-open beats fail-dark: Task 5 can only RELEASE darkness earlier, never extend it;
  the drop-crossing clear backstop is untouched.
- Masks / emergency / blackout precedence untouched (no task touches owner logic; Task 4
  must prove bloom-trim has no mask/owner consequence).
- ANLZ_PATH-before-TRACK_LOADED ordering untouched (no reader changes).
- Zero runtime contact (see Absolute rules).

## Part D — Tests
Per task above. Interpreter: `/opt/homebrew/bin/python3` (3.14.6), cwd = repo root.
All new tests pure/in-memory: no subprocess git (pass dicts / patch functions), no
network, no devices, no sleeps-as-sync.

## Part E — Acceptance (definition of done)
1. Five commits, one per task, exact messages/paths above, explicit-path `git add` only.
2. Scoped green: each task's named test files pass at that task's commit.
3. Full suite from repo root at the final commit: reds reconcile BY NAME to EXACTLY this
   pre-round baseline (manager desk-verified at `d93f047`, 3812 tests, 4F/6E) — NOTHING
   new, nothing beyond it:
   - FAIL `test_absent_fixtures_fall_back_to_committed_snapshot` (test_export_pack_parity_self_heal)
   - FAIL `test_stale_venue_sha_snapshot_is_healed_at_export` (test_export_pack_parity_self_heal)
   - FAIL `test_ddj_slots_8_16_17_24_exact_ch1_ch19` (test_soundswitch_laser_player)
   - FAIL `test_autoloop_capture_rows_identify_passes_and_blockers` (test_soundswitch_parity_oracle)
   - ERROR `test_drop_slot_color_smoke_and_snap` (test_led_color_engine_m2_patch_d)
   - ERROR ×5: all of `test_laser_color_engine.LaserColorStateManagerHoldTests` —
     pre-existing at round start, attributed to the concurrent CFX lane
     (`_FakeLEDColorEngine` lacks `v2_darkest_rgb`; runtime engine has it at
     `led_color_engine.py:1281`; landed via commit `967ea15`). NOT yours to fix
     (out of fence) — if they change form, report it.
   Report the reds BY NAME. "N reds, pre-existing" without names is an invalid report.
   Flapper caution: the AWR-169 pack byte-identity pair flaps if any commit lands
   mid-run; if red, re-run that file in isolation and report both results.
4. Hard checks green at the final commit:
   `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
   `python3 tools/check_docs_drift.py`. Run `python3 tools/check_docs_staleness.py
   --report` and act on anything it flags for the touched contracts (re-verify the
   listed docs, bump `last_verified_commit` where the contract requires it).
5. Contract docs: `led_govee` docs_update — `docs/subsystems/led_govee.md` (Task 5
   paragraph), `docs/validation/software_test_inventory.md` (new tests, one line each);
   the status matrices only if their current text is contradicted (do not invent rows).
   `core_bridge` docs_update — re-verify the three listed docs against your
   `state_manager.py`/`smart_phrasing.py` changes; none of them documents the touched
   internals today [confirmed], so expect verification-only. `soundswitch_pack_player`
   docs_update — same, verification-only expected. The work registry row (AWR-179) is
   the MANAGER's; do not edit it.
6. Report back (in-pane, then signal file per your dispatch): per task — commit hash,
   files, tests run with counts; the full-suite red names; the hard-check outputs' last
   lines; any NOTE items (improvements you didn't make); any divergence you blocked on.

## When you finish
Print your sentinel on its own line and write the signal file exactly as your dispatch
message instructs. Do not declare the round shipped — the manager adversarially reviews
(re-runs your repro/tests, reads every diff) and the executive gates independently
(D2-F1 gets an explicit executive ruling; it may be dropped by reverting your last
commit — keep it clean and isolated).
