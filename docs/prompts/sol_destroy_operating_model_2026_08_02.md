# Sol (xhigh) — destroy the proposed operating model

## Your job

A redesign of how this program is RUN has been proposed. Your job is to **destroy it** — to prove,
with evidence, that it will fail before the operator has to live inside it. You are not here to
improve it, bless it, or tell anyone it reads well. If it survives you, the only reason to trust it
is that you could not kill it.

Think of it as an outside firm reviewing a company's new management structure during a severe
management change. The operator is sick of mistakes. Finding the flaw now costs a review round;
missing it costs another month.

**Read-only. Implement nothing.** Write exactly one file: `COMBINED_DESTROY_review.md` in the repo
root — your findings. Change no code, no config, no memory, no runtime, no git state. Do not touch
`local/` except to read. Do not dispatch or kill tmux seats.

## The one rule that governs this review

**Internal consistency is NOT your lens, and finding the document well-structured is a failed
review.** That failure mode is exactly what this redesign exists to fix: in the program you are
reviewing, eight hostile review rounds passed a package that burned six hours, and seven passed a
laser list whose own sealed spec stated it ranked drop entrances instead of the sound the operator
asked for. Those chains verified hashes, spec conformance and math with obsessive care, and caught
**zero** direction defects. Do not repeat them.

Attack direction, enforceability, and contact with reality.

## Read these

1. `docs/plans/active/spectral_program_operating_model_v1_2026_08_02.md` — the design under attack.
2. `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the verified failure record
   the design must answer. §8 is the ranked list of repeating failure modes; §9 is what the operator
   says the program must be. Every quote in it was verified at its exact transcript line.
3. `AGENTS.md` (§0 communication, §1 source-of-truth order, §6 invariants, §10 status language),
   `docs/agents/multi_agent_org_workflow.md`, `docs/agents/opus_seat_harness.md` — the operating
   model being replaced.
4. `local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md` — current program state.
5. Whatever code and data you need to test the design's claims against what actually exists on disk.

## Attack surfaces — cover all of these

**A. Is it the old program wearing new words?** For every element, find the thing in the current
model it corresponds to and show why the rename changes behaviour — or show that it does not. The
old model also had a canonical state doc, sealed artifacts, hostile reviewers, and standing laws.
Those failed. Say precisely why these will not fail the same way, or find that they will.

**B. What actually enforces each claim.** Go through the design claim by claim and sort each into:
enforced by code that exists or is specified concretely enough to build; enforced by a process step
someone must remember; or enforced by nothing. **Name every claim in the third and second
categories.** The design asserts, for example, that a laser row inside a buildup "cannot be
printed." Test that: does the data needed to enforce it exist for every track, at the moment of
printing, including tracks with no phrase markers, ambiguous drops, or missing analysis? What
happens on the track where the check cannot be evaluated — does it fail closed, fail open, or crash?

**C. The single points of failure.** The answer file is the whole design's foundation. What happens
if it is seeded wrong, seeded incompletely, corrupted, edited by a seat mid-run, or disagrees with
the operator's memory of what he said? The design admits the operator's ear is offline by design
most of the time and the answer file stands in for it — quantify how far that stand-in can drift
before anyone notices, and whether anything in the design detects the drift.

**D. Does the number survive being optimized?** The design makes one computed number the only
measure of progress. Find the ways a seat can move that number without the machine getting better:
overfitting to the operator's marked tracks, tuning against the answer file, exploiting the
scoring rule, degenerate outputs, selection of easy tracks. If the number can be gamed, the design
recreates the invented-metric failure it was built to prevent.

**E. Contact with the real world.** The library is 700–800 tracks; `local/` holds 32 GB; one seat
run recently took 286 minutes and 8 of 34 tracks refused outright on a codec edge. Test the design's
claims about speed, cost, and "one command" against that. Does `listen <track>` actually work on a
track that has never been analysed, on a track on an unmounted USB, on a track whose stems failed?
Does the three-seat structure survive a seat dying, hitting a context limit, or hitting a provider
quota wall mid-run — which happened to two seats in this program today?

**F. What it gives up.** The design removes the review chain, the organizer, the auditor, the proxy,
and the probe machinery. Some of that caught real defects, including a blind-test key leak. Name
what is now uncaught and what the first incident looks like.

**G. Falsifiable failure scenarios.** At least three concrete walkthroughs where the operator ends
up, six weeks from now, in the same position: repeating himself, reading a confident number that
means nothing, or being handed a list that violates a ruling he already gave. Show the exact
sequence of steps that gets there under the new model.

## Output format

Findings first, ordered by severity. Each finding: location (file:line or design section), what is
wrong, why it matters to the operator's goal, the evidence you checked, and the concrete failure
scenario. Report **everything**, including uncertain and low-severity findings — filtering happens
downstream, not in your review.

Then, required and separate:
- **THE KILL SHOT** — the single most likely way this design dies in practice, in plain language.
- **The §8 table** — one row per failure mode from dossier §8, with your verdict: `IMPOSSIBLE` /
  `VISIBLE WITHIN A DAY` / `UNCHANGED`, plus the scenario where it recurs anyway.
- **Enforced-by-nothing list** — every claim resting on discipline rather than mechanism.
- Open questions and assumptions.
- A short change summary last.

Label every claim **[confirmed]** (you read it in current code or ran it), **[assumed]**, or
**[unknown]**. Do not assert anything about program state you did not open. If you find nothing in
a category, say so explicitly and name the residual risk.

**Verdict, at the top of your file, on its own line:** `SURVIVES` / `SURVIVES WITH REQUIRED FIXES` /
`FAILS`.

## Boundaries

Do not re-litigate the operator's goal, his acceptance gate, or any ruling recorded as operator law
in the dossier or the memory store — those are fixed. If you believe one of them is the real
problem, say so once under open questions and attack the design on its own terms anyway.

Write in plain conversational English wherever the operator will read it — `AGENTS.md` §0 bans
jargon by name. Use §10 status language only. Do not describe your private reasoning process;
give evidence, findings, and verdicts.

Run straight through. When finished, print `DESTROY REVIEW RULED` on its own line and touch
`/tmp/rbss_lane_signals/sol3.DESTROY.done`.
