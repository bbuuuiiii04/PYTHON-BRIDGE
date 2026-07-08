---
doc_status: current
truth_level: code-verified + live-log-verified
last_verified_commit: d5cdcd4
last_verified_date: 2026-07-06
validation_scope: Codex implementation spec collapsing clustered ANLZ smart-drop markers and gating drop impacts on real crossings (laser + LED mirror); software tests only; hardware-unvalidated
---

# Codex Implementation Spec - Smart-drop marker collapse + true-drop impact gate

> You are an autonomous senior engineer: proactively gather context, plan, implement, test, and refine without waiting for additional prompts. Persist end-to-end within the turn. Bias to action.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make (a prior theme's reviewed changes are present in state_manager.py, tests/test_laser_color_engine.py, and several docs — leave them exactly as they are). If you notice unexpected changes beyond those, STOP and ask. NEVER use destructive commands like `git reset --hard` or `git checkout --`.

> Act as a discerning engineer: optimize for correctness and reliability; cover the root cause, not a symptom. Conform to codebase conventions. Tight error handling: no broad try/catch, no success-shaped fallbacks.

## Part A - Context & Root Cause (verified; read, do not implement)

Live-run problems (operator, 2026-07-06 evening set): (1) lasers fired drop scenes at "2nd chorus" crossings and kept re-firing every 32 beats instead of hitting the one true drop, and sometimes the true drop was demoted; (2) LED buildup looks were stomped dark for entire builds by a re-arming pre-drop blackout.

Both share one root cause — all **[confirmed]** at HEAD d5cdcd4 against code and tonight's log (`bridge-20260706-192659.jsonl`):

- `select_smart_drops` (`smart_phrasing.py:601-617`) passes Rekordbox's raw ANLZ drop candidates through with only intro/outro trimming — no proximity filtering. `d.meta.smart_drops` is set from it once per track load (`state_manager.py:1408-1411`, stored `:1438`). On extended drop sections Rekordbox emits one candidate per 32-beat phrase: tonight "Take Over Control" produced crossings at beats 128, 160, 288, 320, 384, 608, 640, 672; "Turn Up The Bass" at 160, 192, 224, 368; the Hardwell mashup carried 7 candidates, 5 of them ~15-17 s apart.
- Every candidate is a full "drop": the laser buildup→`drop_crossing` pipeline fired at each one (all three operator complaint timestamps were real `smart_drop_crossing` events — log-verified), and the 4-beat pre-drop blackout window (`smart_phrasing.py:396-429`) legitimately re-armed before each candidate and held until its crossing, chaining darkness through a whole build (three separate arm/crossing cycles proven at 19:33:11/27/41).
- The one firing the operator called correct ("Lose Control", 19:54:37) came from a track with a single marker — single-marker tracks must be unaffected.
- Independent demotion bug **[confirmed]**: a real `smart_drop_crossing` is demoted to `post_drop` when the *previous phrase label* isn't in the predecessor set — `drop_lifecycle.py:58-72` (laser) and its mirror `_led_drop_impact_allowed` (`led_dispatch_policy.py:1471-1491`). That is the "skips the true drop" complaint.
- The chorus→chorus label re-arm (`drop_lifecycle.py:66-71`, `led_dispatch_policy.py:1481-1490`, capped at 2) re-fires a drop on a bare phrase boundary. Phrase segments are built from the RAW `anlz_drops` list (not the collapsed one), so after marker collapse this branch would still reproduce the "2nd chorus" firing at the collapsed-away marker's phrase boundary — it must go.
- `drop_lifecycle.py` mirrors the LED resolver by design (module docstring; `drop_lifecycle_mirror` defaults True) — laser and LED changes must land together to preserve parity.
- **[confirmed]** Neither `smart_phrasing.py` nor `drop_lifecycle.py` appears in any `docs/agents/change_contracts.yml` glob — the contract must be extended before code changes (AGENTS.md §7).

Known consequences, deliberate:
- Autoloop re-arm and drop-presentation decisions keyed to smart-drop crossings now happen once per drop section instead of every 32 beats — that is the intent ("a drop" = the section hit).
- **[assumed]** Learned drop-presentation solos stored at beats that are no longer markers simply never match again (dormant, harmless). Do not add migration logic.
- `max_drops_in_a_row` / `LED_MAX_DROP_IMPACTS` and the `_impact_count` counters become inert (write-only) once the chorus re-arm branches are deleted. Leave the config/constants and counters in place (same precedent as the inert `post_drop_cycle_beats`) but document the inertness where those knobs are described.
- The laser `drop_cycle` re-assert (`laser_director.py:495-500`) and the buildup gate (`laser_director.py:574-584`) are intentionally NOT touched — log analysis cleared the buildup gate as a misfire source tonight.

2026-07-07 AWR-140 addendum: the inert-counter note above is historical to AWR-131.
The marker collapse remains in force, but the capped two-hit label re-arm was restored in
`docs/plans/active/drop_two_hit_rule_restore_spec.md`: one true smart-drop impact plus one
chorus-to-chorus label re-hit may render `drop`; later chorus labels demote to `post_drop`.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch only: `docs/agents/change_contracts.yml` (and `docs/agents/change_contracts.md` if it mirrors globs), `smart_phrasing.py`, `drop_lifecycle.py`, `led_dispatch_policy.py`, tests under `tests/`, and Part E docs.
- Do not touch: `laser_director.py`, `state_manager.py`, `smart_rearm.py`, `drop_presentation.py`, any config file, the phrase-segment builder (`build_phrase_segments_from_markers`) or `meta.anlz_drops` (raw list feeds phrase labels and must stay raw).
- Behavior that must not change: single-marker tracks (marker sets with all gaps ≥ 64 beats are byte-identical through selection); breakdown marker selection; `should_clear` logic; impact-hold windows and durations; scripted-track exemptions.
- No I/O, locks, or per-tick allocations added anywhere (selection runs once per track load; the gates are pure in-memory).
- Error handling: selection stays a pure total function — no exceptions for odd inputs (empty, unsorted, duplicates already handled by the existing `sorted(set(...))`).

### Task 0 - contracts first (AGENTS.md §7)
In `docs/agents/change_contracts.yml`: add `smart_phrasing.py` to the `core_bridge` contract's `code_globs`, and `drop_lifecycle.py` to the `laser` contract's `code_globs`. If `docs/agents/change_contracts.md` enumerates the same globs, mirror the additions. Run `python3 tools/check_agent_contracts.py` to confirm the extension parses before moving on.

### Task 1 - `smart_phrasing.py`: collapse clustered drop candidates
Next to `SMART_DROP_IGNORE_INTRO_BEATS`, add:
```python
SMART_DROP_MIN_GAP_BEATS = 64  # ANLZ marks every 32-beat phrase of a drop section; keep the section entry only
```
In `select_smart_drops`, add a keyword param `min_gap_beats: int = SMART_DROP_MIN_GAP_BEATS` and, inside the existing loop after the intro/outro checks, keep a candidate only when it is the first, or `drop_beat - selected[-1] >= min_gap_beats` (keep the FIRST of each cluster — the section entry is the hit). In `select_smart_breakdowns`, pass `min_gap_beats=0` explicitly so breakdown selection is byte-identical to today.

### Task 2 - `drop_lifecycle.py`: real crossing always wins; label re-arm removed
In `impact_allowed` (`:58-72`):
- Replace the crossing block (`:62-65`) with an unconditional allow:
```python
if sp.smart_drop_crossing:
    return True
```
- Delete the `previous == "chorus"` branch (`:66-71`) entirely.
The resulting order: predecessor-label allow, then unconditional crossing allow, then False. Update the module docstring's mirror note if line references change.

### Task 3 - `led_dispatch_policy.py`: identical mirror edits
In `_led_drop_impact_allowed` (`:1471-1491`): make `sp_state.smart_drop_crossing` unconditionally return True (replace `:1475-1480`), and delete the `previous == "chorus"` branch (`:1481-1490`). Do not touch `_led_drop_marker_anchor`, `_led_arm_drop_lifecycle`, or `_led_drop_lifecycle_should_clear`.

## Part C - Invariants That MUST Still Hold (live safety)

- 200 Hz push loop gains no blocking I/O or locks; selection runs on track-load event handling only.
- `StateManager` remains the only writer of `DeckState`.
- Laser policy (`LaserDirector`) and execution (`LaserSceneExecutor`) stay separated; blackout/emergency masks unaffected.
- Laser/LED drop lifecycles remain mirrors: the two `impact_allowed` implementations must end this change structurally identical.
- Scripted tracks get zero policy activity from these paths; mirrors (decks 3/4) generate no decisions.
- Worst-case wrong selection = a missed or single laser hit, never a stuck-on laser or a bypassed blackout.

## Part D - Tests

Pure seams throughout: `select_smart_drops` is a pure function; `DropLifecycle` takes a SimpleNamespace `sp`; `_led_drop_impact_allowed` is drivable with a synthetic `SmartPhrasingState`.

1. `select_smart_drops`: `[128,160,192]`→`[128]`; `[128,160,288,320]`→`[128,288]`; exact-64 gap kept (`[128,192]`→`[128,192]`); single marker unchanged; intro/outro trimming still applied before collapse; `select_smart_breakdowns` output byte-identical to today for a clustered input.
2. `DropLifecycle.impact_allowed`: real crossing with `previous_phrase_label="groove"` (or "other") now yields drop (was post_drop — invert the existing expectation and say so); label-only chorus→chorus crossing now yields post_drop (was drop up to the cap — invert); crossing after a long chorus stretch still fires; predecessor-label allow (up→chorus, no marker) unchanged.
3. LED mirror: the same three cases through `_led_drop_impact_allowed` / `_led_role_from_smart_phrasing`.
4. Sweep for existing tests embedding 32-beat-spaced smart-drop lists (drop presentation, smart rearm, LED role tests) — update only expectations that the collapse legitimately changes, and list every such inversion in your report; do not weaken unrelated assertions.
5. Run targeted suites first (`python3 -m unittest tests.test_smart_phrasing tests.test_drop_lifecycle tests.test_led_state_manager tests.test_drop_presentation` — adjust to the actual test module names you find), then `python3 -m unittest discover tests`.

Known pre-existing full-suite failures at this HEAD, NOT yours to fix and NOT acceptable to worsen: `tests.test_led_color_engine_m2_patch_d` (KeyError `slot_colors_from`, live-config dependent) and `tests.test_export_pack_parity_self_heal` (fixture-dependent parity counts). Anything else red that a clean HEAD didn't show is yours.

## Part E - Acceptance (definition of done)

- [ ] Task 0 contract extension landed and `check_agent_contracts.py` green before code tasks.
- [ ] Tasks 1-3 landed; both `impact_allowed` implementations structurally identical.
- [ ] Full suite: no new failures beyond the two named pre-existing ones.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Docs updated: `docs/subsystems/laser.md` (drop trigger semantics + inert `max_drops_in_a_row`), `docs/subsystems/core_bridge.md` and `docs/architecture/current_architecture.md` and `docs/architecture/runtime_invariants.md` (smart-drop selection now collapses clusters — grep them for smart-drop mentions first; update only where behavior is described, and report any left unchanged), `docs/subsystems/led_govee.md` (LED drop-impact gate), `docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`, `docs/agents/task_playbooks/change_laser_behavior.md` (if it describes impact rules), and register this spec in `docs/status/active_work_registry.md`.
- [ ] Status language §10-allowed only.
- [ ] Do not commit; leave changes in the worktree for review.

## When You Finish

Report: changed files, exact test/check commands with pass counts, every inverted test expectation, and which docs you inspected but left unchanged. Plain-language operator summary: the bridge now treats a run of Rekordbox drop markers 32 beats apart as ONE drop (the first hit), so lasers fire once at the real drop instead of re-firing every 32 bars, the "goes dark before the drop" blackout arms once per real drop instead of chaining through the whole build, and a real drop always fires even when Rekordbox mislabeled the section before it; tracks with one clean drop marker behave exactly as before; watchpoints for the next live run — a track whose second hit comes very fast (under 64 beats) now gets one laser hit instead of two, and autoloop drop re-arms follow the same once-per-section rhythm; hardware-unvalidated until then.
