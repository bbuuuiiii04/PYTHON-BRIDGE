# Attack the design as an AUTONOMOUS AGENT ORG, not as a list factory

Fresh adversarial seat, no history in this work. **Attack only** — do not revise, do not write a
design version.

## The framing correction that makes this necessary

Eight rounds of hostile review converged on
`docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md` believing the deliverable was
a trustworthy per-track **list**. The operator has now corrected that.

What he is building is: **an organization of AI agents that work together AUTONOMOUSLY to achieve
his north-star goals — and the thing they must autonomously build is the spectral audio analysis
"ears and brain" that drives lighting cues, lasers, energy and accented moments.** One goal, not
two: the org exists to build the ears, and the ears getting smarter unattended is how he knows the
org works.

His words, 2026-08-01: *"This is supposed to be autonomous, but everytime I take a peek at the
program I immediately see you doing some bullshit."*

Judge v8 against **that** goal, not against list quality.

## Read

- `docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md` in full.
- `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the verified failure record.
- The existing org doctrine: `docs/agents/multi_agent_org_workflow.md`,
  `docs/agents/opus_seat_harness.md`.
- `local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md` and the trail
  `local/spectral_v5_2026_07_17/PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md` (6,465 lines — sample it;
  it is the actual record of eleven executive seats running this org for a month).
- The three attacks already written: `ATTACK_HUMAN_ANGLES.md`, `ATTACK_SYSTEM_ANGLES.md`,
  `ATTACK_NORTH_STAR.md`.

## Four passes, each its own findings section

**PASS 1 — AUTONOMY.** Does v8 let agents decide what to work on next without him? Every point that
requires his attention, decision, or correction to keep moving is a place autonomy fails. The
month's record shows execs idling and asking permission (*"why are we stopped??? we should never
stop for anything"*). Does v8 fix that or codify it?

**PASS 2 — COMPOUNDING.** Does the org get smarter across rounds, or restart? Eleven executive seats
ran this program in a month; the trail shows each filing its realization and rebuilding the process
while the real number moved from 2 of 34 to 2 of 34. What in v8 makes round N+1 begin from more
capability than round N — **for the ears, not for the paperwork**? If nothing does, say so plainly.

**PASS 3 — SELF-CORRECTION.** He says every time he peeks he sees bullshit. What in v8 detects
bullshit **without him looking**? Separate mechanisms that catch a bad artifact from mechanisms that
catch a lane that is stuck, aimed wrong, or optimizing the wrong thing. The month's worst failures —
a metric nobody asked for grading a month of work, rigor spent on the wrong object, seven review
rounds passing a package that measured drop entrances instead of growls — were invisible to every
gate that existed. Would v8 have caught them unattended?

**PASS 4 — WHAT AN ORG BUILT FOR THIS WOULD HAVE THAT v8 LACKS.** Concrete and mechanical: how work
is chosen, how a stuck lane is detected and killed without him, how capability accumulates, how the
ears' progress is measured continuously rather than at his check-ins, how agents hand off without
losing what was learned, and what the org does for a week when he does not appear at all.

## Output

Write `ATTACK_AUTONOMY_SOL.md` in the repo root. Findings per pass, worst first: what is wrong, why
it matters to an autonomous org building the ears, the evidence you checked, and a concrete failure
scenario. Then a combined verdict: **is v8 salvageable for this goal, or is it the wrong artifact
entirely?**

Label claims **[confirmed]** / **[assumed]** / **[unknown]**. Plain conversational English, no
jargon (`AGENTS.md` §0 bans it by name), mechanism intact.

## Boundaries

Read-only except that one file. Do not implement, do not touch `local/` except to read, do not
dispatch or kill tmux seats, do not touch the running bridge. His north-star goals and acceptance
gate are fixed — you are testing whether an autonomous org can reach them.

When finished print `AUTONOMY ATTACK RULED` on its own line and touch
`/tmp/rbss_lane_signals/sol3.AUTONOMY.done`.
