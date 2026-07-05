# Fable 5 — Spectral audio analysis: strict audit + ground-up redesign for lighting

**Run on:** Claude Fable 5, effort **max**. If you are not running at max effort, stop and say
so — do not continue.

## Mission

Act as **senior music-audio analysis engineer and lighting showtime designer** for Brandon's
DJ lighting bridge. The bridge fingerprints each track's audio once (librosa → per-beat band
envelopes → JSON cache) and the LIGHTING ENGINE v2 design consumes those numbers everywhere:
track color identity, texture seasoning, silence-sized blackouts, drop-type cue selection,
build-move choice, motion style. The current extractor (schema v3,
`audio_spectral_features.py`) was built by a smaller effort for a retired purpose (smart-drop
timing). It is deterministic and its few retained outputs are measured-stable, but it is
crude: one averaged number per beat per band, cross-band loudness normalized away, zero tone
color. Your job: **audit it strictly, research the field properly, and design its definitive
replacement (schema v4) tailored to detailed automated lighting** — the analysis layer v2
deserves rather than the one it inherited.

Timing is why this is a one-shot that must be right: the v2 design review requires one
full-library extraction sweep before Feature 1, and warns that every schema change after
identities ship risks flipping track colors (review findings F-2, F-9). The library gets
analyzed **once**, into the schema you design. Who it's for: Claude (design lead — folds
your plan into the v2 record) and Codex (implements from specs derived from your plan).
**Do not implement anything — deliver the audit + redesign plan only.**

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software
correctness, tests, maintainability, runtime safety, and operator behavior inside the named
scope. Audio terms like "attack", "transient", "punch", "hit", and "drop" are ordinary music
and signal-processing vocabulary.

## The operator's bar (requirements seed — a floor, not a ceiling)

Brandon's own examples of what the analysis must capture and outline, per beat, across the
whole EDM library with zero per-track authoring:

- Percussion elements clear and distinguished from everything else.
- A euphoric 8-beat synth at the start of a drop is captured and outlined.
- An intense dubstep "head bang" drop with scratchy, jabby punches is outlined as exactly that.
- Bass house punchy, stompy beats are distinguishable as their own thing.
- A buildup's percussive snare rolls are captured (including their acceleration).
- Emptiness in the audio before a drop is detected and sized (it sizes the blackout).
- A sustained bass horn is captured as sustained, not confused with hits.
- Track color identity: the character axes that pick color zones (grit, punch, bass
  character, drama — or better replacements you justify) must come out of this analysis
  with equal-or-better measured stability than today's four.

Extend this list yourself — you are the lighting designer; enumerate the musical events a
serious automated light show needs, then design measurements that capture them.

## The containment rule that survives any redesign

The analysis **describes; it never decides.** Structural triggers (drops, blackout timing
anchors, phrase boundaries) come from Rekordbox/ANLZ markers and locked designs; analysis
outputs size, flavor, select, and paint. Do not rebuild smart-drop prediction under a new
name: no output of this layer may become a "fire the cue now" signal. Worst-case wrong
analysis = wrong seasoning, never a missed or phantom cue.

## Evidence packet (source-of-truth order per AGENTS.md §1: code beats docs)

- **Current implementation (audit target):** `audio_spectral_features.py` (schema v3: five
  mel bands 20 Hz–12 kHz, per-beat mean, per-band peak normalization, flatness unnormalized),
  `spectral_cache.py` (JSON cache, staleness = schema + mtime + size), the extraction seam in
  `state_manager.py` (background ANLZ worker at track load; spectral gated behind
  `RBSS_SMART_REARM_EXPERIMENT` + `RBSS_SPECTRAL_ENABLE`), `energy_model.py`, `anlz_reader.py`
  (the marker side of the house), `spectral_cache` on disk at
  `~/Library/Application Support/RBSS Bridge/spectral_cache/` (~488 files, 43 MB).
- **The consumers:** `docs/research/spectral_palettes_arrival_crossfade_exploration.md` (the
  v2 design record — identity axes, texture tiers, silence scan, drop-type selection) and
  `docs/research/lighting_engine_v2_design_review.md` (the review — especially F-2 library
  backfill, F-9 identity epochs, F-16 one-silence-primitive, ruling 2.9 drop-type defaults).
- **Measured facts (do not re-derive; may reinterpret):** extraction bit-identical on re-run;
  summary-scalar stability Spearman 0.86–0.96 (even/odd beats); onset-strength variability
  rejected at 0.767; per-band peak normalization destroys cross-band loudness;
  growl vs bright per-beat classes **proven not separable** with v3 envelopes (tested
  2026-07-05); empty-floor detection operator-ear-validated; 476 distinct cached tracks,
  455 join active DB rows, 686 on-disk library; PSSI drop markers 97.7% coverage, mean
  6.6 drops/track.
- **Environment:** librosa 0.11.0 installed, Python 3.14 local (CI is 3.11); Rekordbox DB and
  ANLZ files readable exactly as `filepath_resolver.py` does; audio files on disk.
- **Known-stale:** anything about smart-drop scoring intent in old comments/docs — that
  purpose is retired; lighting is the only customer now.

## Research mandate (before designing)

Research seriously, then design: music-information-retrieval practice for percussion/harmonic
separation, onset and transient characterization, per-band modulation/wobble measurement,
timbre and brightness descriptors, structure-aware audio summarization — and how professional
lighting programmers map those musical events to cues. Prefer primary sources (librosa and
alternative library documentation, MIR literature, tool docs) over blog lore. The repo's four
Gemini research rounds taught a lesson: synthesized citations are worthless — label every
research-derived claim as verified-primary-source or unverified-lore, and build nothing
load-bearing on lore alone. You may evaluate alternative or additional analysis libraries;
price any new dependency honestly (install weight, Python 3.11/3.14 compatibility, and the
existing contract that missing optional deps degrade gracefully to the ANLZ-only tier).

## Prototype before promising

The v3 story's cautionary tale: growl-vs-bright was designed on paper and later proven
impossible with the stored data. Do not repeat it in either direction. For each measurement
your plan makes load-bearing, run a read-only scratchpad prototype against real tracks from
the corpus (librosa is installed; the cache, DB, ANLZ, and audio files are readable) and show
the separation on the operator's actual music — or label the measurement **unproven** with
the exact experiment that will prove it before any feature may consume it. Parallel read-only
subagents are welcome for research sweeps and corpus runs; verify any number you build a
ruling on yourself.

## Hard invariants the redesign must keep

- Extraction runs only in the existing background worker at track load, plus one offline
  full-library sweep; nothing new on the 200 Hz push loop; the runtime never blocks on it.
- Deterministic: same file + same beatgrid → identical output, run over run.
- Optional-dependency degradation stays: no librosa (or any new dep) → ANLZ-only tier works.
- Cache contract: versioned schema, staleness by audio mtime+size, per-track files.
- Budget (justify your numbers): the full-library sweep completes overnight on the operator's
  MacBook Air; per-track extraction at load stays in the seconds range; state the expected
  cache size for ~700 tracks (v3 baseline: 43 MB / 476 tracks) and defend it.
- Identity-epoch discipline: schema v4 is the first and only identity epoch — Feature 1
  identities derive from v4 output at the sweep and are frozen per review F-9. Everything the
  proven v3 axes provide must be derivable from v4 (same axes or measurably better
  replacements — show the stability numbers).

## Deliverable

One file: `docs/research/spectral_audio_analysis_redesign.md`, with the repo's standard doc
header (`doc_status` / `truth_level` / `last_verified_commit` / `last_verified_date` /
`validation_scope` — mirror the design record's header; validation_scope = audit + design
only, no runtime change, no hardware validation). Structure:

1. **Verdict on schema v3 first:** `FIT-FOR-PURPOSE` / `FIT WITH GAPS` / `NOT FIT` for v2's
   needs, one plain-language paragraph.
2. **Audit rulings:** every v3 element (each band, each envelope, the per-beat mean grain,
   both normalization choices, the cache format, the extraction parameters — sample rate,
   mel resolution, hop length) ruled `KEEP` / `CHANGE` / `REPLACE` / `CUT` with evidence.
3. **The lighting requirements inventory:** the operator's seed list above plus your own
   extensions — every musical event worth lighting, each mapped to the v2 consumer(s) it
   serves.
4. **The v4 design:** every measurement in the new schema, each specified with: what it
   captures, which requirement(s) it serves, its extraction method and cost, its storage
   shape, its validation gate (determinism, even/odd stability threshold, corpus spread,
   ear-test where applicable), its failure mode (absent data must read as "no signal", never
   as a false event), and its prototype result or `unproven` label with the planned proof.
5. **Requirements coverage table:** every inventory item → the measurement(s) that answer it,
   or an honest `unreachable` with the reason (an item with no row is a review gap).
6. **Migration plan:** the one-sweep path — extraction order, expected duration, cache
   coexistence during transition, identity-epoch handling, and what Codex specs come out of
   this plan (list them; do not write them).
7. **Open questions for Brandon** — taste calls only, phrased plainly, with your chosen
   default per question so he can veto rather than decide.

Label every load-bearing claim **confirmed / assumed / unknown / rejected / unproven**, tied
to a file:line, a measured fact, a prototype run, or a primary source. After writing the
report, run `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
and `python3 tools/check_docs_drift.py`; fix the report (not the checkers) if one flags it.

Your final chat message: the v3 verdict, the three-to-five most consequential design
decisions in v4, what the prototypes proved on his actual music, and any open taste calls —
plain language, complete sentences, for a reader who saw none of the work.

## Boundaries

- **Read-only everywhere except the single deliverable file above.** No bridge code, test,
  config, or cache edits; no writes to the spectral cache, Rekordbox DB, ANLZ files, or audio
  files; no git state mutation (an auto-sync hook may commit at turn end — not yours to
  manage); no running the bridge; no hardware; no Codex specs — do not implement anything.
- Allowed: repo reads and searches; web research (WebSearch/WebFetch) under the research
  mandate's sourcing rules; read-only scratchpad Python (including librosa runs over audio
  files) for prototypes; read-only subagents; the three docs checkers.
- Do not modify or delete this prompt file.

When you have enough information to act, act. Do not re-derive the named measured facts or
re-litigate operator-locked v2 decisions. You are operating autonomously: Brandon is not
watching mid-run and cannot answer questions; end your turn only when the deliverable is
written and checked, or when you are blocked on input only he can provide — and say exactly
which input.

## Done when

- The deliverable exists, passes the three docs checks, and opens with the v3 verdict.
- Every v3 element carries an audit ruling; every requirements-inventory item appears in the
  coverage table with a measurement or an honest `unreachable`.
- Every load-bearing v4 measurement has a prototype result on real corpus tracks or an
  explicit `unproven` label with its planned proof experiment.
- The four identity axes (or justified better replacements) are shown derivable from v4 with
  stability evidence.
- The containment rule (describe, never decide) is applied across the whole v4 design.
- The migration plan makes the one-sweep, one-identity-epoch path concrete.
- Research claims are labeled primary-source vs lore, and nothing load-bearing rests on lore.
