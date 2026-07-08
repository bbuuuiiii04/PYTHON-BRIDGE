# Fable 5 — LIGHTING ENGINE v2 EXPANSION: the full experience design (design phase)

**Run on:** Claude Fable 5, effort **max**. If you are not running at max effort, stop and
say so — do not continue.

## Mission

Act as **the lighting-show designer** for Brandon's DJ lighting bridge and produce the
complete LIGHTING ENGINE v2 experience design — the document the Feature 1–4 Codex specs
are authored from. The intentions, locks, and rules are already settled; your job is the
expansion: turn them into the concrete design (zone map, cue vocabulary, formulas,
priorities, switch semantics) and **prove it against Brandon's real library** before
anything is built. Design authority is delegated to you; Brandon's gate is the live look.
Who reads the output: Brandon (operator, not an engineer — plain language, visual
descriptions of what the room does), and Claude/Codex (the spec authors; they need exact
rules, constants, and anchors).

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It
is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry,
life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal
software correctness, tests, maintainability, runtime safety, and operator behavior inside
the named scope. Audio terms like "attack", "hit", "punch", "stab", and "drop" are ordinary
music and signal-processing vocabulary; "aggression profile" and "violence knobs" name how
hard a light look reads, nothing else.

## The assignment (already enumerated — do not reinvent it)

`docs/research/lighting_engine_v2_strict_review.md` **§6 is your charter and is binding**:
§6.1 is settled (do not re-open; challenges to any operator lock go in a veto-shaped
section, never silently overridden), §6.2 items 1–11 are your deliverables, §6.3 lists the
analysis gaps you must design around and never promise, §6.4 criteria 1–7 are your pass/fail
gates. `docs/architecture/lighting_engine_v2_authority.md` is the operator-facing contract
your design must realize — if your design work uncovers a genuine conflict with it, surface
the conflict as a proposed amendment in a dedicated section; do not silently diverge from
it and do not edit it (one narrow exception in Boundaries).

## Deliverable

**One design document, written incrementally as each part completes** (a dead session must
resume from the partial file), with the repo's standard status header
(`doc_status` / `truth_level` / `last_verified_commit` / `last_verified_date` /
`validation_scope` — design intent + read-only measurement, no behavior change, no hardware
validation).

**Operator instruction, verbatim intent: the file must be DISTINGUISHED and EASILY
IDENTIFIABLE.** Choose a filename and title that make it unmistakable and easy to find
(Brandon will look for this file himself); open it with a one-line statement of exactly
what it is and what it governs.

**Operator instruction: use your judgment on where the file lives** — either
`docs/architecture/` (a standing authoritative design document, the detailed companion to
`lighting_engine_v2_authority.md`) or `docs/plans/` (an execution-phase design plan consumed
by the specs). Decide, state the reason in the document's header section, and register it
accordingly (`docs/architecture/doc_index.md` classification; follow the index's existing
conventions for your chosen location).

Structure the content for two readers in one document: every major section leads with the
plain-language "what the room does" description (Brandon's read), followed by the exact
rules/constants/anchors (the spec author's read). Required content = charter §6.2 items
1–11. On the laser package (item 6): design what is designable now — zone→personality
structure, complement-pair coloring, rest-vs-fire discipline, personality skeletons — and
leave the beam-pattern vocabulary as named TBD slots gated on the operator's
hardware-catalog session; do not invent MIDI values the hardware may not have.

Your final chat message: plain language for Brandon — what the design says his room will
do, the library-audit headline numbers (zone spread, drop-family/tier distributions, the
outlier list size), any proposed authority-doc amendments, and what happens next. Complete
sentences, no jargon, assume he read none of the work.

## Evidence packet (source-of-truth order per AGENTS.md §1: code beats docs)

**The settled design record (read fully, in this order):**
- `docs/architecture/lighting_engine_v2_authority.md` — the operator contract (seven laws,
  blackout rules, drop families + intensity tiers, texture mechanism, boundary rulings).
- `docs/research/lighting_engine_v2_strict_review.md` — the charter (§6), the findings your
  rules must answer (S-1 blackout failure taxonomy with per-beat values, S-3 bass-forward,
  S-5 unnamed consumers), verdict-checked 2026-07-05.
- `docs/research/lighting_engine_v2_design_review.md` — rulings 1.1–5.20, F-1..F-17,
  OLC-1..4, P-2..P-5 (as amended by the strict review §4).
- `docs/research/spectral_palettes_arrival_crossfade_exploration.md` — the locked agreement,
  addenda 1–21, corrections, v1→v2 mapping (superseded passages are marked in place — the
  marks win).
- `docs/research/spectral_audio_analysis_redesign.md` — the v4 analysis layer: what is
  measured and how; Appendices D–G are the operator's ground truth and walkthroughs
  (S-4 corrections applied in place).
- The four `docs/research/edm_lighting_color_research*.md` rounds — **lore only**: practices
  are starting points, numbers are tune-live, several citations are synthesized (two
  safety-flavored ones are known-fabricated); import nothing from them as verified.

**Code (read-only grounding for what you design against):**
- Derivable measurements: `spectral_profile.py`, `audio_spectral_features.py` (BAND_RANGES,
  series/scalars, the derived views your consumer rules extend).
- Render/selection seams for templates + color slots: `govee_frame_renderer.py`,
  `led_models.py`, `led_color_engine.py`, `led_dispatch_policy.py`, `beat_sync_engine.py`,
  `govee_realtime_runner.py`.
- Fixture/laser context: `drop_presentation.py`, `personality_resolver.py`,
  `config/laser_director.json`; `smart_phrasing.py` for the phrase grid.

**Data (read-only; required for the audit and rule calibration):**
- The v4 cache: `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/` (666
  entries, 203.5 MB). Rekordbox DB + ANLZ files exactly as `filepath_resolver.py` reads
  them (drop/phrase markers for the audit). Strictly read-only.

**Known measured facts — do not re-derive (reuse freely):** identity-axes corpus stability
grit .929 / punch .935 / bass .967 / drama .928 (n=219); held-out genre discrimination
58.7% vs 16.7%; the strict review's per-beat blackout taxonomy (ILL drop 109 = 12-beat
sub-only gap at beats 97–108, drop 261 = 2 beats at 258–259; Can't Say Nah drop 352 = 26
beats at 324–349, pickup at 350–351; STARsound drop 131 with floor returning at beats
128–130); anchor separations (STARsound brightness_med 1059 / punch .85 / drama 14.2 vs
Can't Say Nah 521 / .51 / 8.7); DROP EM's four drops spanning attack 2.7→16.1 dB and
flatness 0.30→0.42; growl_flags = 0 at Can't Say Nah's drops; LUNCH lowmid-pulse 15.1%
firing at 42.4/45.9/49.7 s.

## Boundaries

- Writes allowed: your design document, scratchpad files, the `doc_index.md` registration
  row for your document, and exactly one cross-reference edit — a pointer line to your
  document in `lighting_engine_v2_authority.md` §15/§16. **Everything else read-only**: no
  code, no tests, no config, no contracts, no edits to the records or reviews (propose
  amendments in your document instead), no cache writes.
- Do not run the bridge; do not touch hardware; do not change what any light does. Verify
  by reading code and running pure read-only analysis scripts in the scratchpad against the
  cache/DB/ANLZ (this is how the library-wide dry-run audit runs — pure functions over
  cached JSON; expect a few minutes of compute, not hours).
- Do not implement any engine change and do not author the Codex specs — this phase designs;
  the specs are authored from your document afterward.
- No web research: the creative corpus is already in-repo with its reliability labeled.
- Subagents: parallel read-only subagents for large sweeps are fine; at most one Fable-tier
  subagent, reserved for a fresh-context adversarial check of your design against the
  charter's criteria before you finish (fold what it finds, then done).
- Run `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, and
  `python3 tools/check_docs_drift.py` before finishing — all three must pass; do not modify
  the checkers or any test.
- Update the LIGHTING ENGINE v2 project memory's NEXT pointer when done (design phase
  complete → spec authoring + the laser hardware-catalog session).
- Do not modify or delete this prompt file.

## Claim discipline

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to a
file:line, a measured run of your own scripts, or a named prior fact. Design choices are
**decided** (yours to make — record the reason in one line); taste-dependent outcomes are
**live-gated** (name what the live pass checks). Never promise anything §6.3 lists as a
gap.

## Done when (falsifiable — these are the charter's §6.4 criteria, plus form)

1. Charter criteria 1–7 all pass, demonstrated inside the document with your own measured
   runs: every walkthrough behavior mapped; the blackout rules reproduce the named gaps
   from the shipped cache (ILL 12@109 / 2@261, CSN 26→capped-16@352, STARsound 2@131 with
   abort) and produce snap-flick classifications where the operator described none; the
   zone map reproduces both anchor palette calls and assigns all 666 tracks with the
   distribution spread visible (no zone > ~40% of the aggressive half); every
   research-round number carries tune-live provenance; the kill matrix covers the named
   dependency and mid-move cases; the specs are writable from your document alone; the
   library audit shows every cached track with a defined outcome at every decision point
   plus a ranked outlier scrub list.
2. DROP EM's four drops do not all land in one intensity tier (charter item 11's gate).
3. Every §6.2 item 1–11 has its section, each led by the plain-language room description.
4. Operator locks honored; any challenge sits veto-shaped in its own section; proposed
   authority-doc amendments (if any) are listed, never applied.
5. The document is registered, distinguished, and easily identifiable; all three docs
   checks pass; the final chat message gives Brandon the design and the audit headlines in
   plain language.
