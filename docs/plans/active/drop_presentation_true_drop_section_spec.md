---
doc_status: active-spec
truth_level: implementation-spec, operator design ruling 2026-07-07 afternoon; code-verified vs current HEAD
last_verified_commit: 0231b74
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — presentation is per-SECTION, decided by the TRUE drop

Contract key: `drop_presentation` (`docs/agents/change_contracts.yml:346`). **Operator design
ruling (Brandon, 2026-07-07, do not re-litigate):** a *true drop* is a drop with an up-marker
runway; that true drop's presentation (LEDS_ONLY / LEDS_PLUS_LASERS / LASERS_ONLY) applies to the
drop section AS A WHOLE. Drop markers without a runway never change the section's presentation.
LED and laser drop/post-drop look cycling inside the section continues unchanged.

## Part A — Context (verified; read, do not implement)

- `impact_now` fed to `_drop_presentation_tick` is the Laser Director's `drop_crossing` decision
  (`state_manager.py:4545-4547`, passed at `:4561`). The lifecycle's `impact_allowed`
  (`drop_lifecycle.py`) passes ANY `smart_drop_crossing` regardless of predecessor phrase — so
  today, a runway-less mid-section drop marker (≥64-beat gap survivor) both opens windows from
  idle and (since AWR-138) re-enters open windows with a freshly rolled presentation. That
  per-marker re-rolling is what the operator is overruling. [confirmed]
- The runway primitive already exists: `runway_beats(beat, phrase_roles)`
  (`drop_presentation.py:145-170`) = contiguous "low"/"up" phrase beats immediately before the
  drop; `plan_track` computes it per drop (`:292` `runways = {...}`) and `DropDecision.runway`
  carries it to the tick (used at `state_manager.py:2617` for the record tier). [confirmed]
- At the impact tick, `_drop_presentation_tick` resolves `decision` from the plan
  (`state_manager.py:2604+`) and builds `WindowInputs(impact_now=...)` (`:2659`); session/learned
  bookkeeping keys off the same tick (`:2672-2688`). [confirmed]
- The WindowMachine itself needs NO change: entry (`drop_presentation.py:715`) and AWR-138
  re-entry (`:702-705`) both key off `inputs.impact_now` — gating the INPUT gates both. [confirmed]

## Part B — Tasks

### Absolute Rules
- Touch ONLY: `state_manager.py` (`_drop_presentation_tick` and/or its call site), `tests/`,
  Part E docs. `drop_presentation.py` itself should need NO code change (the primitive exists);
  if you find one is genuinely required, keep it minimal and say why in the report.
- Do not change: the laser lifecycle / look cycling (`drop_lifecycle.py`, director bank rotation)
  — runway-less markers must STILL fire their laser look bursts exactly as today; the min-gap-64
  smart-drop filter; the ladder tiers; fail-opens; the 192 cap; session/learned bookkeeping
  (observations still recorded for ALL impacts as today — presentation gating must not starve the
  learned store).

### Task 1 — gate the presentation impact on "true drop or explicit operator call"
In `_drop_presentation_tick`, after `decision` is resolved for the impact tick, compute:
```python
presentation_impact = bool(
    impact_now
    and decision is not None
    and (decision.runway > 0.0 or decision.tagged or armed)
)
```
where `armed` is the same manual Solo-arm flag the ladder already reads at that point (reuse the
existing local/state — do not re-derive). Pass `presentation_impact` (NOT the raw `impact_now`)
into `WindowInputs(impact_now=...)` at `state_manager.py:2659`. Every other use of the raw
`impact_now` in the method (eval-beat choice `:2604`, ladder evaluation `:2630`, bookkeeping
`:2672-2688`) stays on the RAW value.
Operator-approved defaults encoded here (flagged for veto in chat, proceed unless overruled):
breakdown-only runways count as true; manual-arm and hot-cue-tagged drops override the runway
requirement.

### Task 2 — Tests (`tests/test_state_manager_drop_presentation.py`, existing harness style)
1. Runway-less drop marker from idle: window does NOT open (actions stay idle; lasers+LEDs floor).
2. Runway-less marker impacting while a LEDS_ONLY window is open: window unchanged (no re-entry,
   suppression continues) — this is the section-as-a-whole guarantee.
3. True drop (runway > 0) impacting while a window is open: re-enters with its own presentation
   (AWR-138 behavior preserved for true drops).
4. Runway-less but hot-cue-tagged drop: still opens/re-enters (operator override).
5. Manual-armed Solo on a runway-less drop: still fires LASERS_ONLY.
6. Learned/session bookkeeping still records the runway-less impact (raw impact path untouched).

## Part C — Invariants That MUST Still Hold
- Laser drop/post-drop look cycling and LED look rotation inside a section: byte-untouched.
- Fail-opens, 192 hang guard, role-exit release, blackout/mute ownership, scripted no-op,
  `enabled:false` byte-identity: unchanged.
- No RNG added; no tick-path I/O.

## Part D — Tests
Task 2; pure in-memory.

## Part E — Acceptance
- [ ] Tasks 1–2 exact; contract `drop_presentation` suites + full `discover tests` at the
      known-3-reds baseline; `check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py` pass.
- [ ] `docs_update`: `docs/architecture/drop_presentation_authority.md` (record the operator's
      per-section ruling + the true-drop definition + the two defaults),
      `docs/subsystems/led_govee.md` / `docs/subsystems/laser.md` if their claims mention
      per-drop presentation, `docs/status/active_work_registry.md` (this spec AWR-139
      implemented; note it refines AWR-138's re-entry to true drops only).
- [ ] Status language: `implemented`/`software-tested`; HARDWARE-UNVALIDATED.

## When You Finish
Report changed files, tests/checks, operator summary in plain words ("one drop section = one
lighting decision, made by the drop that has a real runup; stray mid-section markers can't
re-roll it; your Solo pad and hot-cue tags still always win"), rollback (revert commit). End with
the literal line CODEX-SPEC8-DONE.
