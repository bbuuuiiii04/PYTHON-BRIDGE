---
doc_status: active-spec
truth_level: implementation-spec, operator decision 2026-07-07 (restore capped rule; keep marker collapse)
last_verified_commit: 63c52e0
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — restore the capped two-hit drop rule (keep the marker collapse)

Contract keys: `laser` (drop_lifecycle.py) + `led_govee` (led_dispatch_policy.py). **Operator
decision (Brandon, 2026-07-07): "drop look on true drop and 2nd chorus marker; any other chorus
marker within the drop section is demoted to post_drop." The ×64 smart-drop marker collapse STAYS
(it killed the 2026-07-06 blackout-chaining) — restore only the capped label re-arm that the same
change deleted.**

## Part A — Context (verified; read, do not implement)

- AWR-131 (`docs/plans/active/smart_drop_marker_collapse_spec.md`, landed 2026-07-06 eve, commits
  in the `7600332..ac31726` auto-sync window) did two things: (1) added the ×64-gap collapse in
  `select_smart_drops` (`smart_phrasing.py:603-625`) — KEEP; (2) **deleted the chorus→chorus label
  re-arm branch** (old `drop_lifecycle.py:66-71` and its LED mirror in
  `_led_drop_impact_allowed`, old `led_dispatch_policy.py:1481-1490`), which was capped at 2
  impacts per section via `max_drops_in_a_row` / `LED_MAX_DROP_IMPACTS`. That deletion is what
  killed the operator's intended rule; the cap knobs and `_impact_count` counters were left in
  place but documented inert (AWR-131 Part A "Known consequences"). [confirmed against the AWR-131
  spec + current code: `drop_lifecycle.py` `impact_allowed` today has no label re-arm branch]
- Phrase segments are still built from the RAW `anlz_drops` (AWR-131 explicitly kept the
  phrase-segment builder raw), so the "2nd chorus" label boundary still exists as a
  `phrase_start_crossing` into a chorus segment even though its duplicate drop MARKER was
  collapsed away. That is the signal the restored branch keys on. [confirmed by AWR-131 Part A]
- **Do NOT duplicate or remove the chorus ANCHOR branch — it already exists at HEAD.**
  `drop_lifecycle.drop_anchor` (`drop_lifecycle.py:50-52`) and the LED mirror
  `_led_drop_marker_anchor` (`led_dispatch_policy.py:1560-1562`) already return an anchor on
  `current_phrase_is_chorus and phrase_start_crossing`. That branch is correct and stays as-is;
  today the anchor it produces resolves to `post_drop` only because `impact_allowed` /
  `_led_drop_impact_allowed` reject it. The ONLY change in Task 1/2 is inside those two
  `impact_allowed` functions (add the capped chorus re-arm). Verified at HEAD 2026-07-07: the
  earlier "Part A says impact_allowed has no chorus branch" drift note refers to `impact_allowed`,
  which is correct — it has no re-arm branch; the anchor/`should_clear` chorus checks near lines
  50 and 70 are the anchor and clear helpers, NOT the impact test, and must not be touched.
- Live evidence for the rule being missed: operator live pass 2026-07-07 15:24 session — within
  drop sections the LED held/behaved wrong at the 2nd chorus; operator explicitly requested this
  restore.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `drop_lifecycle.py`, `led_dispatch_policy.py`, `tests/`, Part E docs.
- Do NOT touch: `smart_phrasing.py` (the collapse stays byte-identical), `select_smart_drops`,
  the pre-drop blackout arming (`smart_phrasing.py:396-429` region), `laser_director.py`,
  `state_manager.py`, `drop_presentation.py` (AWR-138/139 semantics stay; a label re-arm is NOT a
  presentation impact — presentation stays per-section per AWR-139).
- Laser/LED parity is mandatory: `drop_lifecycle.py` and the `_led_drop_impact_allowed` mirror
  change together, symmetrically (module docstring contract).
- Recover the exact deleted logic from git history (`git log -p --follow drop_lifecycle.py
  led_dispatch_policy.py` across the 2026-07-06 21:43→2026-07-07 00:36 auto-sync commits) rather
  than re-inventing it; adapt only where today's surrounding code differs.

### Task 1 — `drop_lifecycle.py`: restore the capped chorus re-arm
Re-add the label re-arm branch to `impact_allowed` (and any helper state the old code used):
a chorus phrase-start crossing (`sp.current_phrase_is_chorus and sp.phrase_start_crossing`) while
the lifecycle is already armed counts as a NEW drop impact **iff `_impact_count <
max_drops_in_a_row`** (config default 2). Beyond the cap, the crossing is NOT an impact — role
stays `post_drop` (the demotion the operator wants). Real smart-drop marker crossings keep their
AWR-131 unconditional allow. Update the `max_drops_in_a_row` / `_impact_count` doc comments to
remove the "inert" wording.

### Task 2 — `led_dispatch_policy.py`: mirror in `_led_drop_impact_allowed`
Same restore, symmetric, using `LED_MAX_DROP_IMPACTS` (=2) and the LED-side impact counter, so the
LED drop look re-fires at the 2nd chorus boundary and demotes afterward, in lockstep with the
laser.

### Task 3 — Tests (both sides, existing harness style)
1. Section with true-drop impact then chorus→chorus label crossings at +32/+64/+96: impact #1
   (marker) fires role=drop; the FIRST label crossing (+32) fires role=drop (impact #2); the +64
   and +96 crossings resolve role=post_drop (cap enforced).
2. Cap resets per section: after `should_clear` (section exit) a new true drop starts a fresh
   count.
3. Single-marker track with no extra chorus boundaries: byte-identical to today (one impact only).
4. LED/laser parity: same sequence through the LED mirror yields the same role sequence.
5. Presentation unaffected: a label re-arm does NOT open/re-enter a presentation window (AWR-139
   gate untouched — presentation impacts remain true-drop/manual/hotcue only).

## Part C — Invariants That MUST Still Hold
- ×64 marker collapse byte-identical; pre-drop blackout arming unchanged (arms off smart-drop
  markers only — a label re-arm must NOT arm a new pre-drop blackout, matching the old behavior;
  verify against the recovered hunks).
- AWR-138 window re-entry + AWR-139 true-drop presentation gating unchanged.
- No RNG, no tick-path I/O; scripted exemptions unchanged.

## Part D — Tests
Task 3; pure in-memory.

## Part E — Acceptance
- [ ] Tasks 1–3 exact; `laser` + `led_govee` contract suites + full `discover tests` at the
      known-3-reds baseline; `check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py` pass.
- [ ] `docs_update` for both contracts (subsystem cards' drop-impact descriptions, the AWR-131
      spec's "inert" note corrected via a dated addendum — do not rewrite its history — and
      `docs/status/active_work_registry.md`: this spec AWR-140 implemented; AWR-131 row annotated
      "capped two-hit rule restored by AWR-140, collapse retained").
- [ ] Status language: `implemented`/`software-tested`; HARDWARE-UNVALIDATED.

## When You Finish
Report changed files, tests/checks, plain operator summary ("a drop section gets exactly two drop
hits — the real drop and the second chorus marker — then everything demotes to post-drop looks;
the anti-blackout-chain collapse stays"), rollback note. End with the literal line CODEX-SPEC9-DONE.
