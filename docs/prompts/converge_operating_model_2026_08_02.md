# Attack it, then fix what you found — operating model convergence round

## Your job this round

You are handed the current version of a redesign of how the operator's spectral program is RUN.
You do **two** things, in this order:

1. **Attack it.** Try to kill it. Find the ways it fails before the operator has to live inside it.
2. **Fix what you found.** Produce the next version with your own findings cured.

You then hand that version to an independent seat on the other side, which does the same to your
work. It alternates until a seat attacks and finds nothing worth changing. **That** is convergence —
not two seats getting tired of each other.

You are a fresh seat with no memory of earlier rounds and no stake in anyone's prior work. Treat the
version you are handed as a stranger's.

## The rule that governs the attack

**Internal consistency is not your lens.** The program being redesigned already had review chains
that verified hashes, spec conformance, and arithmetic obsessively — eight rounds passed a package
that wasted six hours, seven passed a laser list whose own spec said it measured the wrong thing.
They caught zero direction defects. Do not repeat them. Attack direction, enforceability, and
contact with reality.

A round whose only findings are wording is a failed round. So is one that declares the design fine
without auditing the specific critical problems raised in earlier rounds.

## Read these

1. The newest design version — the highest-numbered
   `docs/plans/active/spectral_program_operating_model_v*_2026_08_02.md`.
2. The newest round record in the repo root — `ROUND_<n>_<seat>.md` (or `REVISION_ROUND_1.md` for
   the first) — which claims what the previous seat cured and how. **Verify those claims; do not
   accept them.** A finding marked cured whose mechanism does not actually exist, or does not
   actually prevent the failure, is itself a critical finding.
3. `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the verified failure record
   the design exists to answer. §8 is the ranked failure modes; §9 is what the operator says the
   program must be. This never changes between rounds.
4. Earlier reviews and round records, to know what has already been raised — then judge for yourself
   whether it is actually fixed.
5. Whatever code, scorecards, and data on disk you need to test a claim. Check the code the design
   cites: earlier rounds found design claims refuted by the very files they pointed at.

## Attack surfaces

- **Is it the old program renamed?** For each element, name what it replaces and show why the rename
  changes behaviour.
- **What actually enforces each claim?** Sort every claim into enforced-by-code, enforced-by-someone-
  remembering, or enforced-by-nothing. Name every item in the last two categories.
- **Can the progress measure be gamed?** Find ways to move the number without the machine getting
  better — fitting the operator's marked tracks, exploiting the matching rule, degenerate output,
  easy-track selection. If it can be gamed, the design recreates the invented-metric failure it
  exists to prevent.
- **Does it survive reality?** 700–800 tracks, 32 GB on disk, a recent run of 286 minutes with 8 of
  34 tracks refused on a codec edge, seats that die or hit provider quota walls mid-run.
- **What did it give up, and what is now uncaught?**
- **Where does the operator end up back here?** At least three concrete six-week walkthroughs.

## Hard constraints — confirmed against current files, do not design around them by assertion

- Outside Lowkey, the operator never enumerated every real moment in a track, so an unmatched output
  is **not** provably wrong (`local/spectral_v5_2026_07_17/KNOWNSCORE_scorecard.md`). Any score that
  counts unmatched rows as errors on those tracks is invalid.
- `smart_phrasing.py:780-795` `select_true_drops` **fails open** — with sparse or absent phrase data
  it returns every smart drop unchanged. A true-drop label therefore does not prove a real drop, so
  requiring that label in a row does not keep a laser out of a buildup.
- The offline runner (`local/spectral_v5_2026_07_17/combined1_runner.py:1127-1175`) fails closed and
  skips tracks missing audio, grid, frames, or an unambiguous drop. Any "point it at any track"
  command must state which behaviour it takes and what the operator sees on the refusal path.
- Nothing named `listen` or `score` exists in the tree today.

## The bar for a fix

For every finding you raise, one of exactly three outcomes, stated plainly:

- **CURED** — name the mechanism and cite the file/line or the concrete build contract that makes the
  failure impossible or self-announcing. "The design now says X" is not a cure. If the cure depends
  on code that does not exist yet, specify it tightly enough that two different builders would
  produce the same behaviour, including the failure path.
- **ACCEPTED LIMIT** — the failure is real, cannot be designed out, and the design now makes it
  visible instead of hiding it. Say what the operator will see and when.
- **DISPUTED** — the finding (yours or an earlier round's) is wrong. Show the evidence. Disputing
  without evidence is worse than conceding.

## Deliverables

**If you found anything worth changing:**
- The next design version, complete and standalone (not a diff), at
  `docs/plans/active/spectral_program_operating_model_v<n+1>_2026_08_02.md`.
- Your round record at `ROUND_<n>_<seat>.md` in the repo root: your findings first, ordered by
  severity — location, what is wrong, why it matters to the operator's goal, the evidence you
  checked, the concrete failure scenario — then one row per finding with its outcome and where in
  the new design the cure lives.

**If you attacked it and found nothing worth changing:** write no new design version. Write the round
record with verdict `AGREED` on its first line, and prove it: an audit of every critical and high
finding from every earlier round with your own verdict and evidence, plus the residual risk that
worries you most. An unproven `AGREED` is a failed round.

Every round record also includes:
- **THE KILL SHOT** — the single most likely way this dies in practice, in plain language. If you
  cannot find one, say so and name what worries you most instead.
- **The §8 table** — one row per dossier §8 failure mode, verdict `IMPOSSIBLE` /
  `VISIBLE WITHIN A DAY` / `UNCHANGED`, plus the scenario where it recurs anyway.
- **Enforced-by-nothing list.**
- Open questions and assumptions.

Label every claim **[confirmed]** (read in current files or run), **[assumed]**, or **[unknown]**.
Never assert program state you did not open.

## Boundaries

Read-only on code, config, memory, runtime, and git. The only files you write are the two named
above. Do not touch `local/` except to read. Do not implement the design — this is design work, not
the build. Do not dispatch or kill tmux seats.

Do not re-litigate the operator's goal, his acceptance gate, or any ruling recorded as operator law
in the dossier — those are fixed. If a law is genuinely the obstacle, say so once under open
questions and design to it anyway.

Written for an operator who is not a software engineer, mixes live, and refuses to open documents:
plain conversational English, mechanism intact, no jargon (`AGENTS.md` §0 bans it by name), §10
status language only. Do not describe your private reasoning process — give evidence, mechanisms,
and outcomes.
