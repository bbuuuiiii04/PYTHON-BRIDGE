# Fable 5 — Spectral audio analysis: audit, redesign, and BUILD (one shot)

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
color. Your job, in one shot: **audit it strictly, research the field properly, design its
definitive replacement (schema v4) tailored to detailed automated lighting — and build it.**
Analyze the operator's actual music yourself: decode the audio of his real Rekordbox tracks,
run your candidate measurements over them, and verify what they capture against the tracks'
known structure. Design on paper is not acceptance — proof on his music is.

**Operator-granted role exception (2026-07-05, this workstream only):** Fable executes and
builds the spectral v4 analysis itself — Codex is not in the loop for this build. The
standing Codex-implements rule resumes when this prompt completes.

Timing is why this must be right in one pass: the v2 design review requires one full-library
extraction sweep before Feature 1, and warns that every schema change after identities ship
risks flipping track colors (review findings F-2, F-9). The library gets analyzed **once**,
into the schema you design and build here. Who it's for: Brandon (operator/DJ, not an
engineer — your final chat message must be plain language) and Claude (design lead — folds
the result into the v2 record and the coming Codex specs for Features 1–4).

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a
cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software
correctness, tests, maintainability, runtime safety, and operator behavior inside the named
scope. Audio terms like "attack", "transient", "punch", "hit", and "drop" are ordinary music
and signal-processing vocabulary.

## Track selection — non-negotiable

Two different scopes, do not mix them:

- **The sweep analyzes the whole on-disk library.** Every track gets a v4 cache entry, so
  whatever the operator plays has data. Lots of his EDM is not filed into genre playlists —
  that music still gets analyzed.
- **Everything you hand-pick comes from the "BY GENRE" playlist folder**: manual sample
  tracks, prototype targets, timestamped event outlines, corpus-absolute calibration
  statistics, and every genre-discrimination proof. His collection also contains non-EDM
  (e.g. rap); tracks outside the genre folder must never be chosen as examples and must
  never enter calibration statistics or validation claims — cache them in the sweep, learn
  from them never. Query the playlist tree via the bridge's own DB layer
  (`personality_resolver.py` shows the playlist-membership pattern); the folder is named
  "BY GENRE" (verified present in the DB 2026-07-05 — note the DB shows two nodes with that
  name; use the playlist *folder* whose children are the per-genre playlists); if you cannot
  resolve it, stop and report rather than sampling the whole collection.

**The genre playlists are labeled ground truth — use them.** Each playlist under BY GENRE
holds one genre; analyze tracks from each and prove your measurements capture what defines
that genre's sound. The operator's own genre map, in his words:

- Festival tech house (e.g. Odd Mob sound): bassy accent **sustains** at the drops.
- Bass house: **stabby, jumpy** beats.
- Dubstep: several distinct **drop characters** — the measurements should tell them apart.
- Trap (e.g. ISOxo): **heavy but sparse** beat drops.
- Hard techno: **pounding, driving** beats.
- Synth house: the **euphoric synth sustain** drop examples live here.

A v4 that cannot demonstrate these distinctions on the labeled playlists has not met the
bar — genre-level discrimination of drop-window character is a required proof, not a
nice-to-have. One honest exception: if a *specific* distinction proves genuinely unreachable
from the signal, an evidence-backed `unreachable` ruling (what was tried, why it fails, what
data would be needed) is an acceptable answer for that distinction — overclaiming is not.

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
serious automated light show needs, then design and build measurements that capture them.

## The containment rule that survives any redesign

The analysis **describes; it never decides.** Structural triggers (drops, blackout timing
anchors, phrase boundaries) come from Rekordbox/ANLZ markers and locked designs; analysis
outputs size, flavor, select, and paint. Do not rebuild smart-drop prediction under a new
name: no output of this layer may become a "fire the cue now" signal. Worst-case wrong
analysis = wrong seasoning, never a missed or phantom cue.

## Evidence packet (source-of-truth order per AGENTS.md §1: code beats docs)

- **Current implementation (audit + build target):** `audio_spectral_features.py` (schema v3:
  five mel bands 20 Hz–12 kHz, per-beat mean, per-band peak normalization, flatness
  unnormalized), `spectral_cache.py` (JSON cache, staleness = schema + mtime + size), the
  extraction seam in `state_manager.py` (background ANLZ worker at track load; spectral gated
  behind `RBSS_SMART_REARM_EXPERIMENT` + `RBSS_SPECTRAL_ENABLE`), `energy_model.py`,
  `anlz_reader.py` (the marker side), the on-disk cache at
  `~/Library/Application Support/RBSS Bridge/spectral_cache/` (~488 files, 43 MB), and the
  existing tests for these modules under `tests/`.
- **The consumers:** `docs/research/spectral_palettes_arrival_crossfade_exploration.md` (the
  v2 design record — identity axes, texture tiers, silence scan, drop-type selection) and
  `docs/research/lighting_engine_v2_design_review.md` (the review — especially F-2 library
  backfill, F-9 identity epochs, F-16 one-silence-primitive, ruling 2.9 drop-type defaults).
- **Measured facts (do not re-derive; may reinterpret):** extraction bit-identical on re-run;
  summary-scalar stability Spearman 0.86–0.96 (even/odd beats); onset-strength variability
  rejected at 0.767; per-band peak normalization destroys cross-band loudness; growl vs
  bright per-beat classes **proven not separable** with v3 envelopes (tested 2026-07-05);
  empty-floor detection operator-ear-validated; 476 distinct cached tracks, 455 join active
  DB rows, 686 on-disk library; PSSI drop markers 97.7% coverage, mean 6.6 drops/track.
- **Environment:** librosa 0.11.0 installed, Python 3.14 local (CI is 3.11, unit job is
  PR-only); Rekordbox DB and ANLZ files readable exactly as `filepath_resolver.py` does;
  audio files on disk; the bridge is not running and must not be started.
- **Known-stale:** anything about smart-drop scoring intent in old comments/docs — that
  purpose is retired; lighting is the only customer now.

## Research mandate (before designing)

Research seriously, then design: music-information-retrieval practice for
percussion/harmonic separation, onset and transient characterization, per-band
modulation/wobble measurement, timbre and brightness descriptors, structure-aware audio
summarization — and how professional lighting programmers map those musical events to cues.
Prefer primary sources (librosa and alternative library documentation, MIR literature, tool
docs) over blog lore. The repo's four Gemini research rounds taught a lesson: synthesized
citations are worthless — label every research-derived claim as verified-primary-source or
unverified-lore, and build nothing load-bearing on lore alone. You may adopt alternative or
additional analysis libraries; price any new dependency honestly (install weight,
Python 3.11/3.14 compatibility, and the existing contract that missing optional deps degrade
gracefully to the ANLZ-only tier).

## Prove it on his music

The v3 cautionary tale: growl-vs-bright was designed on paper and later proven impossible
with the stored data. Do not repeat it in either direction. Every measurement that becomes
load-bearing in v4 must be demonstrated on real tracks from the genre folder before it
ships: run it over the audio, inspect what it detects, and validate against known structure
(ANLZ drop/buildup/breakdown markers, beatgrids, and the operator-validated reference events
— e.g. the empty-floor runs). For a handful of named tracks spanning his genres, produce
**timestamped event outlines** (time — detected event class) in the report so the operator
can scrub to those timestamps in Rekordbox and confirm by ear — that scrub test is this
repo's established acceptance pattern. A measurement that cannot be demonstrated is either
cut or shipped disabled and labeled `unproven` with the exact experiment that would prove it.

## Build requirements (hard invariants)

- **Zero lighting behavior change.** This build replaces the analysis layer only. Whatever
  currently consumes v3 fields keeps working identically; light output is untouched; the
  full test suite stays green (`python3 -m unittest discover tests`). v2 features consume v4
  later, via their own Codex specs.
- Extraction runs only in the existing background worker at track load, plus the offline
  sweep tool; nothing new on the 200 Hz push loop; the runtime never blocks on analysis.
- Deterministic: same file + same beatgrid → identical output, run over run. Prove it.
- Optional-dependency degradation stays: no librosa (or any new dep) → ANLZ-only tier works;
  tests skip cleanly where optional deps are absent (existing pattern; CI is Python 3.11).
- Cache contract: versioned schema, staleness by audio mtime+size, per-track files. v4
  entries must not corrupt or delete v3 entries mid-transition — design the coexistence and
  cutover. Writing **v4 cache entries** is in scope; v3 entries, the Rekordbox DB, ANLZ
  files, and audio files are strictly read-only.
- Budget (justify your numbers): the full whole-library sweep completes overnight on the
  operator's MacBook Air; per-track extraction at load stays in the seconds range; state and
  defend the expected cache size (v3 baseline: 43 MB / 476 tracks; the on-disk library is
  ~686 tracks and growing).
- Identity-epoch discipline: v4 is the first and only identity epoch — Feature 1 identities
  will derive from v4 output and freeze (review F-9). The four proven character axes (or
  measurably better replacements) must be derivable from v4 — show stability numbers.
- Anti-drift (AGENTS.md §7): find the change contract covering these modules in
  `docs/agents/change_contracts.yml` before editing (extend it first if none matches), update
  every doc that contract names, and pass the three hard checks before finishing.
- Never commit secrets, device IDs, or live config; an auto-sync hook may commit at turn end
  — not yours to manage. Do not create branches or worktrees; work directly on `main`.

## Execution shape

Work autonomously, end to end: research → audit → design → implement → validate on his music
(genre-folder samples) → run the whole-library sweep (background it and verify completion +
coverage stats) → write the report. You may deploy **at most one Fable-tier subagent at a time** for
implementation or fresh-context adversarial review (operator grant); cheaper read-only
subagents for research and corpus sweeps may run in parallel. Verify any claim you build on
yourself. When you have enough information to act, act; do not re-derive the named measured
facts or re-litigate operator-locked v2 decisions. Brandon is not watching mid-run and
cannot answer questions; end your turn only when the work is done and verified, or when you
are blocked on input only he can provide — and say exactly which input.

## Deliverables

1. **The built v4 analysis layer** (extraction, cache, sweep tool, tests, contract + doc
   updates), suite green, checks green.
2. **The report:** `docs/research/spectral_audio_analysis_redesign.md`, with the repo's
   standard doc header (`doc_status` / `truth_level` / `last_verified_commit` /
   `last_verified_date` / `validation_scope` — mirror the design record's header;
   validation_scope = software build + corpus validation, no lighting behavior change, no
   hardware validation). Structure: v3 verdict first (`FIT-FOR-PURPOSE` / `FIT WITH GAPS` /
   `NOT FIT` + one plain paragraph); audit rulings on every v3 element (each band, each
   envelope, the per-beat grain, both normalization choices, cache format, extraction
   parameters) ruled `KEEP` / `CHANGE` / `REPLACE` / `CUT` with evidence; the lighting
   requirements inventory (the seed list above plus your extensions, each mapped to its v2
   consumers); the v4 design — every measurement with what it captures, which requirements
   it serves, method, cost, storage shape, validation gate, failure mode (absent data reads
   as "no signal", never a false event), and its **proof on his music**; a requirements
   coverage table (every inventory item → measurements, or an honest `unreachable` with the
   reason — an item with no row is a review gap); sweep results (coverage, duration, cache
   size, stability spot-checks); the timestamped event outlines for the named sample tracks;
   and open questions for Brandon — taste calls only, each with your chosen default so he
   can veto rather than decide.
3. Label every load-bearing claim **confirmed / assumed / unknown / rejected / unproven**,
   tied to a file:line, a measured run, or a primary source. Run
   `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
   `python3 tools/check_docs_drift.py`, and the unit suite; fix your work (not the checkers
   or unrelated tests) if anything flags.

Your final chat message: the v3 verdict, what v4 now captures that v3 could not, what the
proofs showed on his actual tracks (name the tracks), sweep results, and any open taste
calls — plain language, complete sentences, for a reader who saw none of the work.

## Boundaries

- Writes allowed: bridge analysis-layer code + its tests, the change contract + docs the
  contract names, the report file, v4 cache entries, and scratchpad files. Everything else
  read-only: v3 cache entries, Rekordbox DB, ANLZ files, audio files, live configs, laser/LED
  runtime modules beyond the analysis seam.
- Do not run the bridge; do not touch hardware; do not change what any light does.
- Web research (WebSearch/WebFetch) under the research mandate's sourcing rules.
- Do not modify or delete this prompt file.

## Done when

- v4 is implemented, deterministic (proven), suite green, three docs checks green, contract
  + docs updated.
- Every v3 element carries an audit ruling; every requirements-inventory item appears in the
  coverage table with a measurement or an honest `unreachable`.
- Every load-bearing v4 measurement is proven on genre-folder tracks; anything unproven is
  disabled and labeled with its missing experiment.
- The genre-discrimination proof stands: the labeled BY GENRE playlists' defining drop
  characters (per the operator's genre map) are demonstrably distinguishable in v4 output —
  or a specific distinction carries its evidence-backed `unreachable` ruling.
- The four identity axes (or justified better replacements) are derivable from v4 with
  stability evidence.
- The whole-library sweep has run to completion with reported coverage, duration, and cache
  size — while every hand-picked sample, calibration statistic, and validation claim used
  genre-folder tracks only.
- The report exists, passes checks, opens with the v3 verdict, and includes the timestamped
  event outlines the operator can verify by ear.
