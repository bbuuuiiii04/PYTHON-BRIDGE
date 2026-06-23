---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: ded667c
last_verified_date: 2026-06-23
validation_scope: review prompt only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Prompt — Holistic adversarial review of the laser drop/post-drop/chorus lifecycle

> Paste everything below the line into a fresh Opus session running in
> `/Users/bbui/rb_ss_bridge_v2`. It is self-contained.

---

You are performing a HOLISTIC, ADVERSARIAL, REVIEW-ONLY audit of the **entire** laser
drop / post-drop / chorus lifecycle feature in:

- Repository: `/Users/bbui/rb_ss_bridge_v2`
- Branch: `soundswitch/impl`
- Review head: run `git rev-parse HEAD` (expected ~`ded667c` or later)
- Pre-feature baseline (diff the WHOLE feature against this): `34cf876`
- Landmarks: `47c7a32` = original feature complete; `05dc966` = Gemini revision;
  current HEAD = revision + cleanup.

This is NOT a delta review. Assess the feature **as it stands now, in its entirety** —
runtime code, tests, config, docs, and their mutual consistency — as if deciding whether it
is safe to run on a live rig (it is currently SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED;
do not upgrade that status).

## Strict review-only boundary
- Do NOT edit, create, delete, format, stage, commit, push, restart, toggle, or mutate anything.
- Do NOT start/stop/kill the bridge or touch SoundSwitch, MIDI, lasers, LEDs/Govee, Rekordbox,
  Enttec, or any runtime process. No hardware validation is authorized.
- Treat the spec, commit messages, prior audits, docs, and test names as **untrusted claims**
  until you verify them against current executable code and tests.

## Authority order (use every time)
1. Current executable code (`*.py`)  2. Current tests  3. Tracked config examples + read-only
live-config inspection  4. Runtime/status wiring  5. File tree + git history  6. Docs  7. Specs /
old prompts / prior claims. If the spec conflicts with code, or with itself, report a SPEC DEFECT
separately from an IMPLEMENTATION DEFECT.

## Startup verification (run these)
- `pwd`; `git branch --show-current`; `git rev-parse HEAD`; `git status --short`
- `git log --oneline 34cf876..HEAD`
- `git diff --stat 34cf876..HEAD`
- Confirm the working tree is clean and no stray top-level `test_*.py` scratch files exist.

## Required reading (read fully before judging — this is mandatory)
Docs:
- `AGENTS.md` (source-of-truth order, invariants §6, status language §10)
- `docs/plans/active/chorus_drop_cycling_spec.md` (original Part A–E spec)
- `docs/plans/active/chorus_drop_cycling_revision_spec.md` (the R1–R9 revision spec)
- `docs/agents/change_contracts.yml` (the `laser` + `led_govee` contracts)
- `docs/subsystems/laser.md`, `docs/subsystems/led_govee.md`, `docs/subsystems/core_bridge.md`
- `docs/architecture/current_architecture.md`, `docs/architecture/runtime_invariants.md`,
  `docs/architecture/laser_director_design.md`
- `docs/status/validation_matrix.md`, `docs/status/feature_status_matrix.md`,
  `docs/status/support_matrix.md`, `docs/validation/hardware_validation_log.md`
Treat docs as review targets, not runtime authority.

Runtime code:
- `drop_lifecycle.py`, `laser_director.py`, `laser_executor.py`, `laser_models.py`,
  `laser_config.py`, `__main__.py` (construction + hot-reload), `state_manager.py`
  (the LED resolver `_led_role_from_smart_phrasing` + helpers, the laser context build, the
  Smart Drop "SM net" clear path, and the six reset wiring sites), `tools/laser_config_ops.py`,
  `tools/check_laser_midi_sync.py`.

Tests:
- `tests/test_drop_lifecycle.py`, `tests/test_drop_lifecycle_armed_flag.py`,
  `tests/test_laser_director_lifecycle.py`, `tests/test_laser_executor_lifecycle.py`,
  `tests/test_laser_reset_wiring.py`, `tests/test_laser_config.py`,
  `tests/test_smart_transitions.py` (the SM-net blackout tests), `tests/test_golden_trace.py`,
  `tests/test_laser_executor.py`, and any other laser/LED/StateManager tests you find relevant.

## What to audit (holistic — re-derive, do not trust)
Cover the whole feature, including but not limited to:
1. **Resolver purity & LED parity** — `drop_lifecycle.py` vs the live LED region in
   `state_manager.py`. Confirm the parity test actually drives the REAL
   `_led_role_from_smart_phrasing` (not a re-transcription), with flat-window params sourced from
   the real module constants `LED_MAX_DROP_IMPACTS` / `LED_DEFAULT_DROP_IMPACT_BEATS`. State exactly
   what parity is and is NOT proven (the live LED window is per-look-duration; the resolver is flat).
2. **The gate (A3)** — verify a `smart_drop_crossing` with a disallowed predecessor cannot produce
   role=drop / reason=drop_crossing; verify the 32-beat impact window cannot mask a later buildup
   beyond the gate.
3. **Blackout safety (A4)** — the executor blackout code is untouched; for an allowed crossing the
   manual-blackout on/off pair is byte-identical flag-on vs off; for a gated-off crossing the
   StateManager net clears the blackout (no stranded dark). Verify both the executor-side behavior
   and the SM-net path in `state_manager.py`, and the mask-owner teardown divergence (C2).
4. **No-dark fallback (A6/A8)** — empty/usable-only `post_drop` cycles drops; the at-anchor impact
   falls back to the static `_drop_scene` so dubstep (live) + every example personality fire a hit.
   Load BOTH `config/laser_director.json` and `config/laser_director.example.json` read-only and
   reason about the usable sets. Do not expose local identifiers.
5. **Shuffle-bag (A7)** — usable-only, reshuffle on exhaustion, bag rebuild on length change, per-
   track reset; not "same look all track, +1 next track". Check rejection/rollback (cooldown vs
   backend-reject) and same-length bank-membership edge.
6. **Cadence / no arm spam** — cycling fires only on `autoloop_tick_just_fired`; confirm that flag
   is a single-tick-per-beat pulse and cannot double-fire within a beat or bypass cooldown.
7. **Teardown (B3)** — director + executor reset wiring at all six StateManager sites
   (master/track/stop/resume/scripted/idle) + personality apply, with the deliberate scripted/idle
   asymmetry (director only). Verify against `tests/test_laser_reset_wiring.py` AND the code.
8. **Config validation & kill switch** — the four knobs validate correctly (incl. bool-as-number
   rejection); determine truthfully whether `drop_lifecycle_mirror` is an instant runtime kill
   switch or config/hot-reload-latched (trace `__main__._on_laser_config_reload` →
   `_apply_personality_change`). Confirm docs/spec describe it accurately.
9. **Flag-OFF behavior** — is it byte-identical to pre-feature, and is the documented resume-reset
   exception correct and consistent across spec C1 / Part E / `laser.md`?
10. **Thread-safety**, the 200 Hz push-loop I/O boundary (resolver must be pure), and that
    SoundSwitch/Govee/Rekordbox readers are unchanged.
11. **Docs/claims integrity** — no forbidden status words; validation_matrix accurate; change
    contracts satisfied; `git diff --check` clean; no junk files committed.

## REQUIRED DELIVERABLE — How the lasers operate during GROOVE phrases
This is the operator's headline question (the original live bug was drop looks firing during a
groove). Trace the code and produce a precise, evidence-backed account of laser behavior during a
**groove phrase** — i.e. playing, active track loaded, not stale, autoloop ready, not scripted, not
an active breakdown, NOT a chorus, `smart_post_drop_active` false, predecessor NOT in
{up,low,buildup,breakdown}, and no live `smart_drop_crossing`.

Walk `LaserDirector._decide`'s priority order (emergency → manual → not-playing → no-track → stale →
scripted → autoloop-not-ready → breakdown → drop-lifecycle → buildup → phrase default) and state, with
`file:line` proof:
- Which branch wins in a plain groove, what `role`/`reason`/scene the director emits, and what the
  executor actually fires (which bank, what rotation/cadence).
- That **no drop-bank look can fire** during a plain groove, and exactly why (the resolver returns
  `none`; the gate; `in_post_drop_hold=False`).
- The four adjacent cases, each with the precise outcome and the exact condition that bounds it:
  (a) groove immediately AFTER a disallowed `smart_drop_crossing` (what the resolver returns, when
  `should_clear` fires, and whether any `drop_cycle`/`post_drop_cycle` MIDI can reach the rig and on
  which ticks); (b) groove while inside the buildup look-ahead window; (c) groove during
  `smart_post_drop_active` (is this still "groove" to the operator?); (d) a spurious
  `smart_drop_crossing` mid-groove in `blackout_mask` mode (does anything fire at the crossing tick?).
- Conclude plainly: under what exact conditions, if any, the operator could still perceive a
  drop-style look during something they would call a "groove," and whether that is a defect or
  expected (cite the spec's accepted divergences).

## Reproduce (run when practical; report exact results)
- `python3 -m unittest tests.test_drop_lifecycle tests.test_drop_lifecycle_armed_flag tests.test_laser_director_lifecycle tests.test_laser_executor_lifecycle tests.test_laser_reset_wiring tests.test_laser_config`
- `python3 -m unittest discover tests`
- `python3 tools/check_laser_midi_sync.py`
- `python3 tools/check_docs_metadata.py` / `check_agent_contracts.py` / `check_docs_drift.py`
- `python3 tools/check_docs_staleness.py --report` (advisory; baseline predates this work — do not
  "fix" unrelated contracts)
- `git diff --check`
- Read-only load of both laser configs and report personality knobs + usable drop/post_drop sets.

## Required output (in this order)
1. **Findings first**, ordered P0, P1, P2, P3. For each: severity + concise title; exact `file:line`;
   violated spec clause / runtime invariant; concrete live/operator consequence; reproduction or
   reasoning proof; smallest safe correction; and whether it is implementation / test / docs / spec.
   If there are no actionable findings, say so explicitly, then list residual risks.
2. **Groove-phrase behavior** — the full account specified above (plain-language meaning first, then
   the code-traced detail with `file:line`).
3. **Acceptance matrix** — PASS / FAIL / PARTIAL / UNPROVEN for every Part E criterion and every
   revision item R1–R9.
4. **Commands run + exact summarized results.**
5. **Operator summary** — what changes live, what stays the same, how healthy behavior looks, what to
   watch in SoundSwitch / lasers / LEDs / Rekordbox state / logs, what remains hardware-unvalidated,
   and any restart/toggle/rollback gates.

Stop after the review. Do not implement fixes.
