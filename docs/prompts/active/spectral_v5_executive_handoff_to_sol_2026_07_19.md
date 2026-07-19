---
doc_status: current
truth_level: seat handoff — executive authority transfer (operator-ordered)
last_verified_commit: 827ef599
last_verified_date: 2026-07-19
validation_scope: >
  Seat-state transfer only. Everything referenced is SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED. Nothing here authorizes live behavior changes.
---

# EXECUTIVE HANDOFF — spectral v5 program → GPT-5.6 Sol (2026-07-19, ~19:0x)

**Operator order: the Fable orchestrator seat resigns as executive manager; Sol assumes
executive authority over the entire program.** Brandon talks to the Sol seat now. This
document is written by the outgoing seat and is deliberately unflattering to itself.

## 0. Your authority and the operator's law
You are now gate-holder, dispatcher, and adjudicator. Standing operator law (violating
any of these is worse than being slow):
- **No labeling sessions, ever.** Labels accrue passively or from what he volunteers.
  Silence is never approval. A live veto means only "not this proposed moment now."
- **Chat is the surface.** He does not open documents. Everything material must be said
  fully in chat, in plain language, mechanism included, jargon excluded.
- **Taste is his.** No acoustic measurement proves lighting warrant (verdict item 12).
- **Humble reporting.** No triumphant wording; never claim a check you did not run.
- **No unsolicited changes** beyond the asked scope; present findings, then ask.
- **Live safety.** The bridge runtime is untouchable from this program. Offline only.
- **Verify before asserting**; label claims confirmed / assumed / unknown.

## 1. North star + deliverable
Authoritative architecture: `docs/architecture/spectral_program_design_authority.md`
(AWR-284, ratified by you and the outgoing seat, all ten of your edits applied verbatim).
Deliverable #1 remains: a ranked list of tracks with laser-warranted growls/sustains,
honestly calibrated against his 50 ear-verdicts.

## 2. State as of this handoff — CONFIRMED
- **Sweep COMPLETE and gated.** 720/721 tracks analyzed, 1 failed (a genuinely damaged
  source MP3, Tokyo Drift edit). Median 89.7 s/track, peak RSS 3.19 GB (limit 5.5), no
  thermal throttle, 333 MiB of evidence. Reconciliation PASS; independently re-verified
  at the outgoing seat's desk (`sweep_report.md` §8). **This evidence is good and is
  content-addressed — it never needs recomputing.**
- **Scorer spec** `detector_v3_scorer_spec.md` DRAFT v9 — READY after nine of your
  hostile rounds. **Fixture package** `scorer/fixtures/` (68 files, 34 mutations) is the
  BINDING behavioral truth, authored by an independent non-implementer seat; you audited
  it clean.
- **Official scorer run: INVALID.** Blocked at G4, and per your own adjudication
  (`scorer/sol_diagnostic_adjudication.md`) it also silently failed a required G3
  assertion. The produced list is an **unvalidated candidate list** and must be described
  that way to the operator.

## 3. What the outgoing seat got wrong (state these plainly; they are the live defects)
1. **`vocal_dominant` is physically wrong.** It ORs a relative-share test with a
   content-characteristic test (`voiced_frac ≥ 0.6 AND vocal_harm_sustain ≥ 0.6`) that
   carries **no loudness floor**. On items 14/15 the vocal stem sat 30-48 dB below the
   other stem — inaudible bleed — and still vetoed every qualifying beat. This deleted
   exactly the growls the operator had explicitly located. Same error class as the
   dB×ratio unit bug you caught in an earlier draft.
2. **Ledger ruling M1 broke the measurement.** It imported detector-v2's span geometry as
   gold for 26/48 rows; all 26 reject. v2's geometry is documented-unreliable, so the
   official 0.542 measured "agreement with the old detector," not detection.
3. **The gate harness did not fail on a frozen assertion.** Items 14/15 were logged as
   observations instead of failing G3, which let an invalid run produce output.
4. **Corrected sensitivity is still chance (0.483, CI [0.379, 0.571])** — so (1) and (2)
   do not fully explain the result; the frozen detector is independently weak.
   Your ruling stands: the architecture's stop action fires, but "v12 stem evidence is
   incapable" is NOT established — the signal is present in the arrays.

## 4. Open decisions now yours
- Whether/how to repair `vocal_dominant`. **Anti-overfit hazard**: it failed on named
  verdict items, so a fix must be justified on physical grounds (a source 40 dB down
  cannot dominate), specified and reviewed BEFORE scoring, with the affected items
  disclosed as consumed/diagnostic.
- Whether to rebuild the gold intervals without v2 geometry, and how, given that new
  operator judgments cannot be solicited.
- Fix the G3 harness gap and the G4 allow-root path bug (relative-root resolution;
  see your adjudication §1) — the gates must fail, not log.
- Re-run cost is minutes (evidence is cached); this is cheap to iterate.
- Parked: the 2-child pool (three DO-NOT-ADMIT rulings; serial met the deadline anyway),
  and a GPU/MPS benchmark that should have been run before the sweep (CPU was forced
  deliberately — recorded in every manifest — because unified-memory accounting could not
  be confirmed for the safety guard; the design's own "benchmark both" step was skipped).

## 5. Org mechanics (how to actually dispatch)
- Lanes are tmux sessions driven by `tmux load-buffer <file> && tmux paste-buffer -t
  <session>` then `tmux send-keys -t <session> Enter`. **Always verify the paste chip
  landed before Enter, and re-check the model banner after `/clear`** (clearing a codex
  seat has silently switched it to a cheaper model).
- Seats: `v2impl` = Claude Opus xhigh, bypass perms — the production implementer (it built
  the scorer and fixed the sweep crash). `cursor` = Cursor Agent (premium pool spent until
  8/11; currently Grok 4.5 High) — authored the spec v5-v9 and is the **independent
  fixture authority**; keep it separate from the implementer. `codex`/`codex2`/`codex3` =
  additional Sol seats (operator granted parallel sessions).
- Signals: `/tmp/rbss_lane_signals/<seat>.<TAG>.done|.blocked|.ready`. Lanes have stalled
  silently — watch signal files, never rely on a lane ending its turn. Heavy jobs must be
  detached via `detach_run.py` (os.setsid) or the harness reaps them.
- Working artifacts: gitignored `local/spectral_v5_2026_07_17/`.

## 6. Structural warning you should act on
You have been the adversarial reviewer for this entire program, and that independence is
the main reason the defects above were found at all. **Taking the executive seat costs
that independence** — an author reviewing their own specs is exactly the failure mode this
program keeps demonstrating (mine included). Appoint a genuinely independent reviewer for
whatever you now author: the outgoing Fable seat in a review-only role, a separate Sol
seat with a clean context, or the cursor seat. Do not let the review chain collapse into
one voice.

## 7. First acts recommended (advice, not orders — the seat is yours)
1. Tell the operator in chat, plainly, where the deliverable stands and what you intend.
2. Decide the `vocal_dominant` question with an explicit anti-overfit protocol.
3. Fix the two gate defects so an invalid run cannot produce output again.
4. Re-run; report the honest number, whatever it is.
