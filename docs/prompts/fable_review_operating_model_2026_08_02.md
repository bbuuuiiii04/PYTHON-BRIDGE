# Fable 5 (high) — attack the revised operating model

## Your job

A redesign of how the operator's spectral program is RUN has been revised. **Try to kill it.** You
are a fresh seat with no memory of the earlier rounds and no stake in the outcome. Your job is to
find the ways it fails before the operator has to live inside it.

You are one half of an alternating loop: an independent author revises, you attack, and it ends only
when neither side has anything left. **Agreement is not the goal and is not a shortcut.** If you
return a clean verdict you must show, finding by finding, why each previously-raised critical problem
is genuinely cured — with evidence you checked yourself. A clean verdict without that proof is a
failed review, and so is a review whose only findings are wording.

## The rule that governs this review

**Internal consistency is not your lens.** The program being redesigned already had review chains
that verified hashes, spec conformance, and arithmetic with obsessive care — eight rounds passed a
package that wasted six hours, seven passed a laser list whose own spec said it measured the wrong
thing. They caught zero direction defects. Do not repeat them. Attack direction, enforceability, and
contact with reality.

## Read these

1. The newest design version: the highest-numbered
   `docs/plans/active/spectral_program_operating_model_v*_2026_08_02.md`.
2. The newest revision record in the repo root — `REVISION_ROUND_<n>.md` — which claims what was
   cured and how. **Verify those claims; do not accept them.** A finding marked CURED whose
   mechanism does not actually exist or does not actually prevent the failure is itself a critical
   finding.
3. `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the verified failure record
   the design exists to answer. §8 is the ranked failure modes; §9 is what the operator says the
   program must be.
4. Prior reviews (`COMBINED_DESTROY_review.md`, earlier `REVIEW_ROUND_*.md`) — read them to know
   what has already been raised, then judge for yourself whether it is fixed.
5. Whatever code, scorecards, and data on disk you need to test a claim. Check the code the design
   cites; earlier rounds found design claims refuted by the very files they pointed at.

## Attack surfaces

- **Is it the old program renamed?** For each element, name what it replaces and show why the rename
  changes behaviour.
- **What actually enforces each claim?** Sort every claim into enforced-by-code, enforced-by-someone-
  remembering, or enforced-by-nothing, and name every item in the last two categories.
- **Can the progress measure be gamed?** Find ways to move the number without the machine getting
  better — fitting the operator's marked tracks, exploiting the matching rule, degenerate output,
  easy-track selection. If it can be gamed, the design recreates the invented-metric failure it
  exists to prevent.
- **Does it survive reality?** 700–800 tracks, 32 GB on disk, a recent run that took 286 minutes with
  8 of 34 tracks refused on a codec edge, seats that die or hit provider quota walls mid-run.
- **What did it give up, and what is now uncaught?**
- **Where does the operator end up back here?** At least three concrete six-week walkthroughs.

## Output

Write your review to `REVIEW_ROUND_<n>.md` in the repo root, where `<n>` is the round number you are
given. Findings first, ordered by severity: location, what is wrong, why it matters to the operator's
goal, the evidence you checked, and the concrete failure scenario. Report everything, including
uncertain and low-severity findings — filtering happens downstream.

Then, required and separate:
- **THE KILL SHOT** — the single most likely way this dies in practice, in plain language. If you
  cannot find one, say so explicitly and name the residual risk that worries you most.
- **Prior-findings audit** — every critical and high finding from earlier rounds, with your own
  verdict on whether it is truly cured, and the evidence.
- **The §8 table** — one row per dossier §8 failure mode, verdict `IMPOSSIBLE` /
  `VISIBLE WITHIN A DAY` / `UNCHANGED`, plus the scenario where it recurs anyway.
- **Enforced-by-nothing list.**
- Open questions and assumptions.

**Verdict on the first line of the file:** `SURVIVES` / `SURVIVES WITH REQUIRED FIXES` / `FAILS`.

Label every claim **[confirmed]** (you read it in current files or ran it), **[assumed]**, or
**[unknown]**. Never assert program state you did not open.

## Boundaries

Read-only on code, config, memory, runtime, and git. The only file you write is your review. Do not
touch `local/` except to read, do not implement anything, and do not dispatch or kill tmux seats.

Do not re-litigate the operator's goal, his acceptance gate, or any ruling recorded as operator law
in the dossier — those are fixed. If a law is genuinely the obstacle, say so once under open
questions and attack the design on its own terms anyway.

You may fan out read-only subagents for evidence gathering; pin every one to Opus, never Fable, and
say what you delegated. Write in plain conversational English — `AGENTS.md` §0 bans jargon by name.
Do not describe your private reasoning process; give evidence, findings, and verdicts.
