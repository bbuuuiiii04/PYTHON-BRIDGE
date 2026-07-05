# Fable 5 — LIGHTING ENGINE v2 strict review: spectral v4 capability + v2 feasibility and creative design (phase gate)

**Run on:** Claude Fable 5, effort **max**. If you are not running at max effort, stop and say
so — do not continue.

## Mission

Act as **senior lighting-systems architect and adversarial design reviewer** for Brandon's DJ
lighting bridge. Two review targets, one phase gate:

1. **The schema-v4 audio spectral analysis as built** — strictly review its implementation
   and its *capability*: is the code correct and honestly labeled, and do its measurements
   actually carry what every LIGHTING ENGINE v2 feature needs from them?
2. **LIGHTING ENGINE v2 as designed** — challenge its feasibility, its limitations, and its
   creative design decisions now that three things exist that the original design and its
   first review did not have: the built v4 layer with measured capabilities and measured
   gaps, the operator's beat-by-beat lighting walkthroughs and rulings (report Appendices
   D–G), and the haze answer (haze is IN — beam-based laser designs are in scope).

Challenge rigorously, propose concrete design changes where the design deserves them, and rule on
every element you touch. This review is **the gate before the next phase**: a Fable one-shot
that expands the lighting intentions and creative directions into the full v2 experience
design. Your output must leave that phase a settled foundation — what it may treat as
decided, what it must design, and what it must not touch. Who reads this: Brandon (operator,
not an engineer — your final chat message must be plain language), and Claude/Fable (the
expansion phase and the Codex specs for Features 1–4 build directly on your rulings).

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software
correctness, tests, maintainability, runtime safety, and operator behavior inside the named
scope. Audio terms like "attack", "transient", "punch", "hit", and "drop" are ordinary music
and signal-processing vocabulary.

## Deliverable

One review document: `docs/research/lighting_engine_v2_strict_review.md`, standard repo
header (`doc_status` / `truth_level` / `last_verified_commit` / `last_verified_date` /
`validation_scope` — mirror `docs/research/lighting_engine_v2_design_review.md`;
validation_scope = strict review only, read-only verification, no behavior change, no
hardware validation). Write it **incrementally as each part completes** so a dead session
resumes from the partial file. Structure:

- **Two verdicts up front**, one per target: `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`,
  each with one plain-language paragraph.
- **Findings, severity-first** (location, issue, why it matters, evidence, required fix).
- **Rulings on every element you challenge**: `KEEP` / `CHANGE` (with the concrete change) /
  `REDESIGN` (with the replacement) / `CUT` / `NEW` (proposal). Design-change proposals are
  proposals in this document — nothing gets implemented in this phase.
- **Operator-locked challenges**: anything that pushes on a locked decision goes here,
  veto-shaped, never silently overridden.
- **The expansion-phase charter**: what the next phase may treat as settled, the open
  creative questions it must answer, the analysis gaps it must design around (or demand as
  schema/consumer extensions), and its falsifiable success criteria. This section is the
  phase gate — make it strong enough that the expansion prompt can be written from it alone.
- A claim-label index. Label every load-bearing claim **confirmed / assumed / unknown /
  rejected**, tied to file:line, a measured run, or a named prior fact.

Your final chat message: both verdicts, the three most consequential findings, what the
expansion phase inherits, and any open taste calls — plain language, complete sentences, for
a reader who saw none of the work.

## Evidence packet (source-of-truth order per AGENTS.md §1: code beats docs)

**Target 1 — the v4 analysis as built:**
- Code: `audio_spectral_features.py` (v4 extractor + frozen v3 compat path),
  `spectral_cache.py` (v4 subdir + coexistence), `spectral_profile.py` (pure derived views:
  silence primitive, identity axes, texture classes, `lowmid_pulse_*`, `section_map`,
  `drop_window_vector`), `tools/spectral_sweep.py`, the runtime seam
  `state_manager.py:_runtime_spectral_features` and its consumer
  `anlz_reader.py` (smart-drop scorer, reads the compat block).
- Tests: `tests/test_audio_spectral_features.py`, `tests/test_spectral_cache.py`,
  `tests/test_spectral_profile.py`.
- The build record and its evidence: `docs/research/spectral_audio_analysis_redesign.md` —
  read it in full; Appendices are load-bearing: B/C (prototype evidence and corpus proofs),
  D (operator ground truth round 1: corrupt-flac, wobble labels, SIGNAL, marker quality),
  E (lowmid-pulse build, its review gate, ear-scrub results, operator rulings: markers
  authoritative, expression-over-taxonomy, atmospheric-simmer, the relative-dip finding),
  F (four ear-described tracks vs measurements), G (the operator's two beat-by-beat lighting
  walkthroughs, general principles, palettes, the haze answer).
- The v4 cache: `~/Library/Application Support/RBSS Bridge/spectral_cache/v4/` (666 entries,
  ~204 MB) — **strictly read-only**; spot-verify claims against real entries freely.
  Rekordbox DB and ANLZ files: read-only, exactly as `filepath_resolver.py` does.
- Contract: `docs/agents/change_contracts.yml` → `spectral_analysis`.

**Target 2 — LIGHTING ENGINE v2 as designed:**
- The design record: `docs/research/spectral_palettes_arrival_crossfade_exploration.md`
  (locked functionality agreement, addenda 1–21, operator corrections, v1→v2 mapping,
  Feature 4, venue reality).
- The first design review: `docs/research/lighting_engine_v2_design_review.md` (rulings
  1.1–5.20, findings F-1..F-17, OLC-1..4, proposals P-1..P-6, post-review operator
  decisions). Do not repeat its work — build on it; your added value is everything that
  changed since: the built v4, Appendices D–G, and the haze answer.
- The v1 stack the v2 design claims to reuse (feasibility grounding — verify the seams it
  relies on actually behave as the design assumes): `led_look_director.py`,
  `led_color_engine.py`, `led_dispatch_policy.py`, `govee_frame_renderer.py`,
  `govee_realtime_runner.py`, `beat_sync_engine.py`, `led_models.py`, `led_config.py`,
  `smart_phrasing.py`; laser side: `personality_resolver.py`, `laser_director.py`,
  `config/laser_director.json`; cards: `docs/subsystems/led_govee.md`,
  `docs/subsystems/laser.md`, `docs/subsystems/core_bridge.md`.

**Known measured facts — do not re-derive (may reinterpret):** v3-compat bit-identity;
identity-axes corpus stability grit .929 / punch .935 / bass .967 / drama .928 (n=219);
held-out genre discrimination 58.7% vs 16.7% chance; sweep 666/686 in 48.6 min, 203.5 MB;
runtime↔sweep key parity 60/60; corpus bottom-gone bimodality with the threshold in a
density valley; the ear-scrub results in Appendix E; the walkthrough verifications in
Appendices F/G.

**Known open analysis gaps (pre-loaded; challenge their disposition, not their existence):**
formant/filter wobble invisible to level envelopes; slow-wobble vs metric pumping not
separable; rolls ear-confirmed as lowmid-pulse false positives; chorus-softness recognition
unproven (Can't Say Nah chorus 3 reads ≈ drop 1); growl-intensity ranking unproven;
"dips" are sometimes relative full-band drops, not bottom-gone events (derivable from
stored full_db, needs a consumer rule); kick-prominence under-reads sidechained
four-on-floor under walls; sustained-synth's cleanliness gate excludes thick layered walls
(0.169 vs 0.12); melodic/pitch-domain structure out of scope by design.

**Operator-locked decisions — do not re-litigate (challenges go to the locked-challenges
section, veto-shaped):** total darkness is fine everywhere; no double drops; WILD OUT
default with SET mode selectable; key is out of the color story; neon zone direction;
palette-pads-plus-lock as the correction path; drops always full-scale; decorate-never-
decide containment; phrase markers are authoritative (operator-owned); trap and dubstep
share one lighting expression; stereo width deferred; expression-over-taxonomy priority;
LEDs are the room's primary light, now explicitly paired with two DMX lasers **in haze**.

## What to challenge (the questions, not a procedure)

For target 1: does the implementation do what the report claims, and is every honest label
(experimental, unproven, deferred) actually justified by the evidence — neither oversold nor
undersold? Then capability: walk every v2 feature consumer (identity zones, drop-type
selection, build moves, blackout sizing, texture seasoning, section pacing, laser
personality picking, the walkthrough behaviors in Appendix G) and rule whether v4's
measurements suffice, need a consumer-side derivation, need a named schema extension, or
make the consumer infeasible as designed. The walkthroughs are the sharpest test: for each
lighting behavior the operator described, name the exact measurement chain that would drive
it — or the gap.

For target 2: with v4's real capabilities and the operator's walkthroughs in hand, which v2
design decisions still stand, which are under-specified for the expansion phase, which are
infeasible or wrongly priced (runtime seams, 30 fps renderer physics, dispatch authority,
laser MIDI vocabulary — verify against the v1 code), and which creative decisions deserve a
challenge or a better proposal? Haze changes the laser design space — say what that unlocks
and what it invalidates. The first review's kill matrix, moment arbiter, and color-slot
contract requirements are still unbuilt paper — rule on whether they remain sufficient as
specified or need revision before specs.

## Boundaries

- Writes allowed: the review document and scratchpad files. **Everything else read-only** —
  no code changes, no test changes, no cache writes, no config or contract edits, no edits
  to the design record or prior review (rule on them; the fold-in is later work).
- Do not run the bridge; do not touch hardware; do not change what any light does. Verify
  by reading code, running the existing test suite, and read-only computations against the
  cache/DB/ANLZ (pure analysis scripts in the scratchpad are fine).
- Do not implement any proposed change: Fable reviews and designs on paper here; Codex
  implements bridge code later from specs.
- Subagents: parallel read-only subagents for large file sweeps are fine; at most one
  Fable-tier subagent at a time, reserved for a fresh-context check of your own verdicts
  before you finish.
- Web research (WebSearch/WebFetch) is optional and secondary: primary sources only, label
  research-derived claims verified-primary-source or unverified-lore, and build nothing
  load-bearing on lore.
- Run `python3 tools/check_docs_metadata.py` before finishing (your document must pass);
  do not modify the checkers or unrelated tests. The unit suite has exactly one known
  pre-existing failure (`test_laser_color_engine` loader test) — not yours.
- Do not modify or delete this prompt file.

## Done when

- Both verdicts stand at the top of the review document with severity-first findings under
  them, every challenged element carries a ruling, and every load-bearing claim carries a
  label tied to evidence.
- Every Appendix G walkthrough behavior and every v2 feature consumer has a named
  measurement chain or a named gap with its disposition (consumer rule / schema extension /
  infeasible).
- Locked decisions are honored; any challenge to one sits in the locked-challenges section
  in veto shape.
- The expansion-phase charter exists and is strong enough to write the next prompt from
  alone.
- The document passes the metadata check, and your final chat message gives Brandon the
  verdicts and consequences in plain language.
