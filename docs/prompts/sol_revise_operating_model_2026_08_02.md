# Sol (xhigh) — revise the operating model until it survives

## Your job this round

You are now the **author**, not the attacker. A hostile review has ruled the current operating model
`FAILS`. Fix it. Produce the next version of the design so that the findings against it are cured by
mechanism, not by rewording.

This alternates: you revise, then a fresh independent reviewer with no memory of this conversation
attacks the result. The loop ends only when the reviewer can find nothing and you have nothing open.
Do not aim to please the reviewer — aim to build something that cannot be killed.

## Read these

1. `docs/plans/active/spectral_program_operating_model_v1_2026_08_02.md` — the current design.
2. The most recent review of it — `COMBINED_DESTROY_review.md` on the first revision round, or the
   newest `REVIEW_ROUND_<n>.md` on later rounds. Every finding in it must be answered.
3. `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the verified failure record
   the design exists to answer. §8 is the ranked failure modes; §9 is what the operator says the
   program must be. This does not change between rounds.
4. Whatever code, scorecards, and data on disk you need to prove a cure actually holds.

## The bar for a cure

For each finding, one of exactly three outcomes, stated plainly:

- **CURED** — name the mechanism, and cite the file/line or the concrete build contract that makes
  the failure impossible or self-announcing. "The design now says X" is not a cure. If the cure
  depends on code that does not exist yet, the design must specify it tightly enough that two
  different builders would produce the same behaviour, including what happens on the failure path.
- **ACCEPTED LIMIT** — the failure is real, cannot be designed out, and the design now makes it
  visible instead of hiding it. Say what the operator will see and when.
- **DISPUTED** — the finding is wrong. Show the evidence. Disputing without evidence is worse than
  conceding.

Known hard constraints from the last review, all confirmed against current files — do not design
around them by assertion:

- Outside Lowkey, the operator never enumerated every real moment in a track, so an unmatched output
  is **not** provably wrong (`local/spectral_v5_2026_07_17/KNOWNSCORE_scorecard.md`). Any score that
  counts unmatched rows as errors on those tracks is invalid.
- `smart_phrasing.py:780-795` `select_true_drops` **fails open** — with sparse or absent phrase data
  it returns every smart drop unchanged. A true-drop label therefore does not prove a real drop, so
  requiring that label in a row does not keep a laser out of a buildup.
- The offline runner (`local/spectral_v5_2026_07_17/combined1_runner.py:1127-1175`) fails closed and
  skips tracks missing audio, grid, frames, or an unambiguous drop. A "point it at any track"
  command must state which behaviour it takes and what the operator sees on the refusal path.
- Nothing named `listen` or `score` exists in the tree today.

## Deliverable

Write the next design version to
`docs/plans/active/spectral_program_operating_model_v<n+1>_2026_08_02.md` — the complete design,
standalone and readable on its own, not a diff. Alongside it write
`REVISION_ROUND_<n>.md` in the repo root: one row per finding from the review you are answering,
with its outcome (CURED / ACCEPTED LIMIT / DISPUTED), the mechanism or evidence, and where in the
new design it lives.

Both are for an operator who is not a software engineer, mixes live, and refuses to open documents.
Plain conversational English; `AGENTS.md` §0 bans jargon by name. Status language per §10 only.
Label claims **[confirmed]** / **[assumed]** / **[unknown]**. Do not describe your private reasoning
process — give evidence, mechanisms, and outcomes.

## Boundaries

Read-only on code, config, memory, runtime, and git. The only files you write are the two named
above. Do not touch `local/` except to read. Do not dispatch or kill tmux seats. Do not implement
the design — this is the design, not the build.

Do not re-litigate the operator's goal, his acceptance gate, or any ruling recorded as operator law
in the dossier. If a law is genuinely the obstacle, say so once and design to it anyway.

Run straight through. When finished print `REVISION RULED` on its own line and touch
`/tmp/rbss_lane_signals/sol3.REVISE.done`.
