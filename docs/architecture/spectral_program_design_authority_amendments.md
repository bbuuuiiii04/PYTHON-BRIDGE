---
doc_status: current
truth_level: mixed — operator-ratified where an entry says so, otherwise exec-adopted process law (each entry's provenance paragraph is authoritative; design authority companion; not code-derived)
last_verified_commit: a88c5921
last_verified_date: 2026-07-25
validation_scope: >
  Design/architecture amendments only. SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED. Authorizes no implementation, dependency, runtime, or
  lighting change; every build stage still needs its own spec, review, and
  operator authorization.
---

# Spectral Program Design Authority — amendment log (append-only)

**Why this file exists.** The base authority document
(`docs/architecture/spectral_program_design_authority.md`) is BYTE-FROZEN: sealed
experiment pin tables (QBE spec §7, scorer spec §6 in
`local/spectral_v5_2026_07_17/`) reference its exact bytes, so the base document must
never be edited. From 2026-07-22 the authority is **base document + this amendment
log**, read together; where an amendment below modifies a base clause, the amendment
wins. This log is append-only: new amendments are added as new numbered entries;
existing entries are never edited or removed.

---

## AMENDMENT-1 (2026-07-22) — §5 Stage-3 embeddings discipline

**Adoption provenance:** SPECRESEARCH research program (research manager seat, TAG
SPECRESEARCH), deliverable
`local/spectral_research_2026_07_22/spectral_research_report.md` §4 (A1). Review
chain: adversarial Fable 5 review (13 findings applied) + GPT-5.6 Sol xhigh
discussion, verdict AGREE-WITH-EDITS, converged (report §6). **Operator GO ruled
2026-07-22** on the converged recommendation set (relayed by the executive seat,
SPECAUTHOR order 2026-07-22).

**Base clause amended:** §5 ("MERT-v1-95M vs MuQ, mixture audio, frozen final hidden
state, predeclared pooling…").

**Amendment text (verbatim from the adopted report §4-A1):**

(a) Add MusicFM-MSD as a third CANDIDATE (not an ensemble member —
one-winner-or-NEITHER stands). Grounds: it is MIT-licensed (the only permissive
music-SSL option) and the strongest published encoder for structure BOUNDARIES
(HR.5F 54.2 vs MERT-330M 45.4; MERT-330M led section-function labeling, so the
advantage is boundary-specific and its transfer to short-event QbE is UNPROVEN —
license diversity and single-model challenger value are the honest justification).
Before entry, freeze the exact checkpoint, artifact hash, license, and the unresolved
MSD underlying-data terms; note the pre-2024-02-13 broken-checkpoint history
(re-download hygiene).

(b) Replace "frozen final hidden state" with "exactly ONE predeclared layer per
encoder, chosen from published probing results and frozen before any local data is
touched." Published evidence shows the final layer is systematically suboptimal and
layer choice is task-dependent; for short-event retrieval the published
tagging/structure layers are HYPOTHESES, stated as such. Local layer sweeps remain
forbidden (preserves the anti-overfit intent).

(c) Record MuQ open-checkpoint caveats: trained on ~0.9K hours vs 160K in-paper; fp32
required (NaN risk).

CLAP is NOT added to the pilot; any text-query lane is a separate later decision.
Grouped folds, lineage exclusion, cost gates, the engineered/spectrogram baseline, and
deletion-on-failure all stand unchanged.

**Withdrawn sibling proposals (recorded for the trail, adopted nowhere):** draft
amendments A2 (veto-validation doctrine change to §7) and A3 (two-sided uncertainty
boundary objects in the L3 envelope) were proposed in the same report and WITHDRAWN
after hostile review — full reasoning at report §4 ("A2 — WITHDRAWN", "A3 —
WITHDRAWN") and the review record at report §6. No §7 or L3 clause is modified; the
two-channel veto routing (§1.2, L5.3, §3.4) is untouched settled law.

---

## AMENDMENT-2 (2026-07-24) — §0 North star: the ratified transcription vision

**Adoption provenance:** Operator-ratified verbatim 2026-07-22 (session
2feb819e-213b-49d9-9b8b-9c2e7ecfd8cf): "Yes. That is correct exactly. That
should be authoritative. I should never have to rexplain myself regarding
that." Recorded as the AUTHORITATIVE, never-re-explain project memory
(`user_transcription_vision_authoritative`, with honest-confidence calibration
told to the operator by exec2 the same day and accepted). Drafted into this log
by the EFSPEC spec-authoring seat (exec4 dispatch, 2026-07-24); landed by the
executive after review. Any agent asking the operator to re-explain this vision
is a process failure.

**Base clause amended:** §0 ("North star (operator, verbatim intent)") —
SUPPLEMENTED, not replaced: the statement below sits above §0 as the top-layer
vision; where they differ in emphasis, this statement wins. No other base
clause is modified; boundaries (§1), rejections (§3), validation doctrine (§7),
and runtime gates (§8) all stand unchanged and continue to govern how this
vision may be pursued and what may ever be claimed.

**Amendment text (verbatim from the ratified record):**

The lights are **an instrument playing the track** — not decoration synced to
it. Each prominent musical element gets its own **light-voice** that moves as
the element moves, for as long as it lives: a sparkle behavior that IS the
big-room figure wearing light (begins when it begins, breathes with its
phrasing, dies when it dies); comets whose relentlessness IS the bass line's.
The show is **composed per track from what the track actually contains** —
the way a human lighting designer would sit with THAT track and score it,
element by element — never merely selected from a pool and garnished. The
target is **TRANSCRIPTION: music into light, continuously**, so tightly
coupled a listener could almost reconstruct the track from the room.

**The interface law inside it:** he said "I literally cannot put into words
what this drop sounds like" — he should NEVER have to. The mapping runs
sound → light DIRECTLY, with no vocabulary bottleneck; his only job is
vetoing wrong translations. (This is the program's standing
he-is-the-judge-never-the-lexicographer principle at full scale.)

**Subsumption [links expanded from the memory record]:** the operator's 2026-07-22 energy-fabric statement (3-layer
energy fabric — track-in-library × section × drop; cues CAST, never cycled;
the breath-hold rule) and accent-layer statement (base cue + event-locked
accents; the SPIRAL / ANIMALS / GODSPEED exemplar timestamps) are COMPONENTS
of this statement — mechanisms in service of transcription. All detection /
retrieval / concept machinery is the machine's INTERNAL vocabulary for
performing the transcription; the operator never touches a word of it.

**Honest-confidence calibration (exec2, told to the operator 2026-07-22, he
accepted):** the vision's literal core — light continuously coupled to an
unnamed musical element tracked through a dense mix — is the program's
LEAST-confident item (element-conditioned models weaken in dense mixes;
electronic = separation's worst genre). Expectation: stem-level light-voices
+ event accents + energy envelopes deliver most of the FELT transcription;
the per-element literal version is the asymptote, revisited as the field's
tools improve. Runner-up uncertainty: live sub-beat accent timing through
the actual hardware (no end-to-end latency measurement exists yet —
measure before promising). Never present the approximation as the finish
line; never present the asymptote as impossible.

**Effect on the program:** every future presentation-layer spec, cue-compiler
design, and lighting review is judged against THIS statement first; agents
cite it, never re-solicit it. It authorizes no implementation, dependency,
runtime, or lighting change by itself; §7 validation doctrine and §9
step-by-step authorization stand.


## AMENDMENT-3 (2026-07-24) — three laws: lasers-only-on-drops; grades select, never scale; the facet-vector output shape

**Adoption provenance:** CDSPEC1 combined design round + CDSPEC1FIX cure (spec-author seat
energyres, Fable 5, exec7 dispatch 2026-07-24; deliverable
`local/spectral_v5_2026_07_17/combined_design_spec_v2.md` — provenance reference only; every
normative law text is inlined below), drawing on: the operator's lasers-only-on-drops ruling of
2026-07-24; the TRKENERGY research round
(`local/trkenergy_research_2026_07_24/track_energy_redesign_report.md`, R0/R2 with the V8 clause
mapping in its §6); the sealed E3 challenger and E1 scramble measurement rounds
(`local/e3_challenger_2026_07_24/e3_challenger_report.md`,
`local/e1_scramble_2026_07_24/e1_scramble_report.md`); and the one scored laser drop-warrant run
(`local/spectral_v5_2026_07_17/laser_drop_warrant_v1/results/`, inventoried with per-file shas in
`LDWRUN_report.md`). Review chain: hostile review CDSPECREV1 (reviewer ≠ author), CDSPEC1FIX
cure round, CDSPECREV2 delta review, exec adjudication. Applied to this log by the executive
seat.

**Provenance distinction (binding on how this entry is read):** clause 3a RECORDS an operator
law already ruled on 2026-07-24 — this entry records it, it does not create it, and no new
operator approval attaches to its recording. Clauses 3b and 3c are research-derived proposals
that become program law ONLY by the exec adopting this entry after review; they are
exec-adopted, NOT operator-ratified, and nothing in any clause is approved by operator silence —
the operator's standing veto applies to all three clauses, at any time.

**This amendment authorizes no implementation, dependency, runtime, or lighting change.** §7
validation doctrine, §8 runtime gates, and §9 step-by-step authorization stand unchanged and
govern how every clause below may ever be pursued.

### Clause 3a — Lasers only on detected true drops (operator law, recorded)

**Base clauses touched:** §1 (Non-negotiable boundaries) — ADDITION as boundary 8; L7 (warrant +
presentation) — constrained, not modified. No existing clause contradicts it; §0's deliverable #1
(the laser-warrant list) is now bounded by it.

**Law text:** Every laser candidate, laser list row, and laser wiring proposal anchors to a
detected TRUE drop — the existing selection law (`select_true_drops` by name; surfaced as
`meta.drop_sections[].true_drop_beat`) — or is **invalid by construction**. This is not a
quality bar to be traded against; a non-drop-anchored laser moment is not a weaker candidate, it
is not a candidate. The similarity-list method that produced free-floating laser moments is
closed and is not re-proposed.

**Recorded honestly beside it (the law's measured cost, said before the operator rediscovers
it):** at least one operator-confirmed growl — item 44's [386,450) span — has no true drop of
its own and is structurally unreachable by any drop-anchored list; the sealed run's §D.3 output
carries this line verbatim, and any future presentation batch on that track carries it too. The
operator hears the law's cost from us, first. The sealed laser drop-warrant spec v6
(`local/spectral_v5_2026_07_17/laser_drop_warrant_spec_v6.md`, sha published in
`LDWSPEC6_review.md`) already operates under this law; this clause lifts it from that spec into
the program's standing law so every FUTURE laser lane inherits it without re-derivation.

### Clause 3b — Energy grades select pools and pick within pools; they never scale a level

**Base clauses touched:** §1 — ADDITION as boundary 9; L7 (presentation) — constrained. Per the
V8 mapping AS CORRECTED by CDSPECREV1 F2: no AUTHORITY clause contradicts this and none states
it, but ONE ladder clause conflicts as worded —
`docs/plans/active/energy_fabric_ladder_spec_v1.md:240-241` (§B.3, "how hard the accent/impact
reads" — a magnitude mapping) — and is REPLACED in the same change that lands the ladder's B.0
addition (correction text in the change record this clause adopts: "`drop_grade` biases WHICH
cue is cast — including whether harder-reading cues are in the candidate pool — and never maps
onto any magnitude/level parameter; casting harder-reading cues is pool selection, not
amplitude"). The ladder's B.4 cast coordinates and B.0 no-dim-drops bullet were verified
compatible.

**Law text:** An energy grade (track weight, section grade, drop grade, or any successor) may
decide WHICH look, cue, palette family, or pool is cast, and WHERE within a candidate pool a
pick lands. No grade value may be multiplied into, added to, or otherwise mapped onto any
brightness, intensity, dimmer, floor, or level parameter — at any layer, on any path, live or
compiled. Grades RANK and CAST; they never warrant (the warrant is always the sound, per
standing law) and they never scale. This protects the no-dim-drops law BY CONSTRUCTION: a
low-graded drop can only be cast a different full-strength treatment, never an attenuated one.
Enforcement is structural, not behavioral: an import-fence-style static test — deny-by-default
over the whole repo with an explicit allowlist, its enforcement lexicon DERIVED as a superset of
this clause's law lexicon (brightness, intensity, dimmer, floor, level), never a second
hand-kept list — must exist wherever a grade consumer exists, and wiring that violates the
fence is invalid by construction, not a tuning choice.

**The ladder form of this law (inlined verbatim — the exact §B.0 addition adopted with this
clause; no `local/` file is normative for it):**

> - **Energy grades select pools and pick within pools; they NEVER scale a level.** A grade may
>   decide WHICH look / cue / palette family is cast and WHERE within a candidate pool a pick
>   lands; no grade value may be multiplied into, added to, or otherwise mapped onto any
>   brightness, intensity, dimmer, floor, or level parameter, at any layer, on any path. This
>   protects no-dim-drops BY CONSTRUCTION: a low grade can only select a different full-strength
>   treatment, never attenuate one. An import-fence-style test enforces it; wiring that
>   violates it is invalid by construction, not a tuning choice.

### Clause 3c — The output shape: facet vector + categorical basis record; scalars are compatibility views; numeric confidence stays banned

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED (the categorical basis record
is affirmed as the lawful uncertainty form; the ban on calibrated-confidence claims is restated,
not weakened); L3's "there is NO universal confidence field" — REAFFIRMED and extended to every
energy layer. Per the V8 mapping: the real conflict in the ladder is with §B.2/§B.3's
definitional single-construct sentences (one grade per layer), NOT with "scalar-per-layer" — V8
found that phrasing was a misquote, and ladder §B.2's own "two components kept separate for
consumers" wording is already compatible.

**Ruling text:** At every energy layer, the PUBLISHED PRODUCT is the facet vector, plus a
categorical basis record WHEREVER MORE THAN ONE LAWFUL BASIS EXISTS; any composite scalar is a
compatibility view whose ordering means whatever its dominant facet means, and consumers are
built against the facets. The per-layer publications, inlined (CDSPECREV1 F18 — no `local/`
file is normative for this list):

- **E3** publishes its four term values (`body`, `activity`, `perc_high`, `growl`) beside
  `within_track` / `library_scaled`, plus its basis record `body_basis` ∈ {`track_drops`,
  `corpus`}.
- **E2** publishes magnitude (`within_track`) + `slope` + the existing section label + its basis
  records `segmentation_basis` ∈ {`markers`, `section_map`} and `contrast_class` ∈ {`flat`,
  `normal`}.
- **E1** publishes its scalar (`track_weight`) + its four component values (the
  `COMPONENT_KEYS` set: `body_duty`, `brightness_med`, `onset_mh_mean`,
  `growl_flatness_mean`) + the acceptance verdict, pinned constants, and library distribution
  per the schema-2 store. **E1 carries NO basis record, by construction, and that is lawful
  (CDSPECREV1 F3):** a basis record marks WHICH of several lawful bases produced a number; E1
  has exactly one construction path and no fallback, so there is nothing to record. A basis
  record becomes MANDATORY the day E1 grows a second basis. (The feel axes grit/punch/bass/drama
  are `spectral_profile.identity_axes()` output — an adjacent sibling surface, NOT an E1
  publication; named here only so no consumer goes looking for them in the E1 store.)

Every basis vocabulary is a CLOSED categorical set. A numeric confidence float is banned at
every layer, in every store, on every surface — the categorical basis record is the only lawful
uncertainty form. Rank output carries its basis so that rank spread is never mistaken for real
contrast (`contrast_class` exists because a pure rank is measurably blind to whether the
contrast it reports exists — TRKENERGY A2, measured).

**Effect on the program:** every future energy-layer spec, store schema, status surface, and
consumer spec is judged against these three clauses; agents cite them, never re-derive them.
Boundaries (§1), rejections (§3), validation doctrine (§7), and runtime gates (§8) of the base
document stand unchanged everywhere not explicitly supplemented above.

*(End of AMENDMENT-3. Next amendment, if ever adopted, appends below as AMENDMENT-4.)*

## AMENDMENT-4 (2026-07-25) — four checks from the blind-test failure: entry gates (4a), exemplar hygiene (4b), evidence sufficiency (4c), the suspicious-caveat obligation (4d)

**Adoption provenance:** on 2026-07-25 the operator blind-tested the program's first shipped laser
list and it hard-failed; the four faults and the root process failure are recorded in
`local/spectral_v5_2026_07_17/OPUS_EXEC8_handoff_2026_07_25.md` §2–§4 (provenance reference only —
every normative clause below is inlined). The contamination half of the diagnosis is the hostile
review `local/spectral_v5_2026_07_17/CTREV1_review.md` (reviewer ≠ author, ruling DISPUTED), §1 F1 and
§2. Drafted into this log by the A4DRAFT spec-authoring seat (Opus, exec8 dispatch, 2026-07-25),
cured through the A4REV / A4REV2 hostile reviews and the A4FIX1 / A4FIX2 exec adjudications; applied to
this log by the executive seat after review.

**Provenance distinction (binding on how this entry is read):** clause 4a's fourth gate RECORDS an
operator law already ruled (`user_acceptance_gate_the_list`, 2026-07-25 — "length is co-equal with
location"); this entry records it, it does not create it. The other three 4a gates and clauses 4b, 4c,
4d are exec-adopted PROCESS law derived from the failure — they become program law ONLY by the exec
adopting this entry after review, they are exec-adopted NOT operator-ratified, and nothing here is
approved by operator silence. The operator's standing veto applies to every clause at any time.

**This amendment authorizes no implementation, dependency, runtime, or lighting change.** §7 validation
doctrine, §8 runtime gates, and §9 step-by-step authorization stand unchanged and govern how every
clause below may ever be pursued. AMENDMENTS 1–3 stand unchanged.

**The root failure these four clauses close.** Every gate this program built asked *"is this internally
consistent?"* — byte-fidelity, sha match, bar reproduction, hunk-map coverage. None ever asked *"does
this design use the evidence he actually gave us?"* His words were converted to coordinates ONCE, early
(*"lasts 8 beats and then tapers off"* → `[416,424)`); from then on every gate verified the translation
against itself, and eight review rounds passed while the design ignored 48 of his 54 verdict records.
The clauses below make those questions failable.

### Clause 4a — Four mandatory entry gates, before any laser or accent spec is sealed

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED with pre-seal entry gates; §0's
deliverable (the acceptance list) — constrained.

**Law text:** every laser/accent spec passes all four gates below before it is sealed; each gate names
its instrument, a configuration in which it can fail, and the consequence of failing, and a gate that
cannot fail is not a gate (see 4c). The reasons a gate accepts — a record declared unusable (gate 1), a
structure declared unrepresentable (gate 3), and the significance a run asserts (gate 2) — are REVIEWABLE
EVIDENCE at the sealing review, not a checkbox: a spec does not pass by declaring everything unusable,
unrepresentable, or weakly significant with plausible prose.

**The satisfiability standard is not scoped to gates.** It binds EVERY mandatory obligation a spec
imposes, gate or not: each must name the instrument that computes or checks it, and must be dischargeable
by a lawful route without violating any closed set or other obligation in the same document. An
obligation with no instrument, or one no lawful route can satisfy, is a DEFECT TO REPORT as an open
adjudication — never patched, never satisfied by widening a closed set. A sweep for this class MUST NOT
be scoped to gates alone: the energy lane demonstrated the hole live — a mandatory NON-gate obligation
with no instrument, colliding with another gate's closed permitted set, fell straight through a
gate-scoped sweep (`ER5REV_review.md` finding 1, `:39`; "instrumented: no … explicitly not a gate,"
`:322-323`).

**Gate 1 — Corpus-use declaration.** *Required:* the spec enumerates every record in his sealed verdict
corpus — 54 records, one revised by the 2026-07-22 addendum (55 lines across
`local/laser_drop_spans_2026_07_16/review_verdicts.jsonl`, 54 records, and `verdict_addenda_2026_07_22.jsonl`,
1 revision of item 3) — and states, per record, whether the design uses it and why, or why it cannot. A
record that cannot be used is REPORTED, never silently dropped. *Instrument / can-fail:* the enumeration
lives in the spec and is checked against the corpus record count (54); it fails if any record is neither
used-with-reason nor reported-unusable. *Consequence:* the spec is not sealable. *(Closes: 48 of 54
records invisible to eight review rounds.)*

**Gate 2 — Operator-positives.** *Required:* his confirmed positives outrank the presentation floor,
measured on the RUN'S OWN OUTPUT plus his verdict corpus, BEFORE any list reaches him, with self-matches
excluded (an exemplar matching itself is not evidence; leave-one-out per class). "Presentation floor" is
the score of the lowest row actually presented (`laser_drop_warrant_spec_v7.md:112-116`, §C). *Pass
threshold (governed — no self-owned number):* the pass count/fraction is PROPOSED by the authoring spec,
APPROVED by the sealing review (reviewer ≠ author) and the exec on adoption, NEVER self-approved by the
authoring seat; PREDECLARED before the run's output is scored, provably (the mtime chain that proved
`CORPUSTEST1_predeclaration.md` predated its results by 11 minutes, `CTREV1_review.md:58`, is the
standard); and stated as a count/fraction of the **M** non-self-matching confirmed positives, with **M**
printed beside it so the bar is legible against how many positives exist. It is INADMISSIBLE if an
uninformative ranking would clear it, at the run's own n, more often than the significance the spec
asserts (4c's best-achievable-significance test, turned on this gate itself), or if it could be met by
self-matches. *Instrument / can-fail:* the corpus-vs-output separation measurement CTREV1 confirmed sound
— reference `local/spectral_v5_2026_07_17/CORPUSTEST1_separation.py` (its arithmetic was independently
re-derived and banked; its DIAGNOSIS was disputed — run it against a 4b-clean exemplar set); the gate
fails when fewer than the predeclared admissible threshold of his confirmed positives clear the floor
once self-matches are removed. *Consequence:* the run does not ship a list; the failure is reported by
which positives fell below the floor. *(Closes: of 31 confirmed-YES growls, only the 3 self-matching
exemplars cleared the shipped floor — and a self-owned threshold of 1 would have waved that run through.)*

**Gate 3 — Representability.** *Required:* for each structure he states — *skips the 1st beat*, *skips
the 8th beat*, *rests N beats then repeats*, *tapers off*, *stabs N times in one bar*, *repeats
throughout*, *lasts the entire drop section* — the spec states how the design CARRIES it, or declares it
UNREPRESENTABLE and why. *Instrument / can-fail:* a per-structure table in the spec, each row a checkable
property (carried / unrepresentable-with-reason), not prose; it fails if any stated structure is
neither. *Consequence:* the spec is not sealable. *(His descriptions must survive as properties later
checks can still fail against, instead of dying at the first translation to coordinates.)*

**Gate 4 — Length is a required output, co-equal with location.** Operator law, verbatim
(`user_acceptance_gate_the_list`, 2026-07-25): *"how long the lasers last for is literally AS important
because the LASERS need to ACCENT the moment."* *Required:* every laser/accent row emits a start AND an
extent, each with honest uncertainty; that uncertainty takes the AMENDMENT-3 clause 3c form
(`spectral_program_design_authority_amendments.md:257-261`) — an interval and/or a categorical basis
record — NEVER a numeric confidence float, which 3c bans at every layer. *Instrument / can-fail:* the
output-shape check — every deliverable row carries both a start field and a length/extent field; it fails
if any row carries a location and no length, or if the output shape has no length field at all.
*Consequence:* a row without a length is NOT a deliverable row and cannot be presented; such a spec is
not sealable. This CORRECTS the program's earlier reading of the detector-v3 stop ruling as "route
around length": that ruling made length first-class UNCERTAINTY, never absent.

### Clause 4b — Exemplar hygiene

**Base clauses touched:** §2 warrant-family definitions — constrained; supplements AMENDMENT-3 clause 3a
with an exemplar-provenance law.

**Law text:** an exemplar drawn from a moment the operator ruled warrant-negative may NEVER score
candidates. Demoting such an exemplar from a bar LEG while leaving it SCORING every candidate does not
satisfy this — that exact half-measure is what shipped: P3, drawn from item 12 (operator verdict NO), was
demoted from the §D.1 ship condition to a printed diagnostic (`laser_drop_warrant_spec_v7.md:124-133`)
yet still scored every candidate (`:31-34`, §A.2), and CTREV1 measured it driving both the failed
separation and the inversion (`CTREV1_review.md` §1 F1, §2). *Audit obligation:* every exemplar family
declares each exemplar's operator verdict; any family carrying a warrant-negative or cross-track-spliced
anchor is REPORTED before the family is used. *Instrument / can-fail:* the per-exemplar verdict table in
the spec, checked against the verdict corpus; it fails if any exemplar with a NO / warrant-negative
verdict appears in a candidate-scoring set. *Consequence:* the family is not usable until that anchor is
removed.

**Selection discipline (the cure's own trap):** exemplar sets are chosen BY LAW, not by score. Choosing
among law-clean exemplars by maximising a statistic on his corpus is fitting to the test set. Among
law-clean candidates the default is KEEP THEM ALL; a better-scoring subset is REPORTED AS A SENSITIVITY,
never adopted as a selection.

### Clause 4c — Evidence sufficiency: a test that cannot fail is not evidence

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED.

The Stage-A representation was crowned "pilot winner" on SIX pair-ordering comparisons — two positives ×
three negatives (`r4_stage_a_v1/results/metrics.json`, `falsifiers.F1.n_pairs` = 6). Under the null that
the representation is uninformative, a perfect score there occurs with probability 1/C(5,2) = 1/10, so
the best achievable p-value of the whole eligibility test was 0.10 — one in ten uninformative
representations passes it perfectly. And Stage-A won by ELIMINATION: the pilot's own verdict was
"NEITHER" (`RBT4_report.md:23-25`, `:29-33`), all three learned encoders disqualified on inversions,
none reaching the beat-the-baseline comparison; half its positive evidence came from the contaminated
exemplar of 4b (`CTREV1_review.md` §2).

**Law text (binds forward and backward):**

- Every comparative claim states the BEST ACHIEVABLE SIGNIFICANCE OF ITS OWN DESIGN — what the test could
  have shown had it worked perfectly — BEFORE the result is reported. *Instrument / can-fail:* the
  significance is computed from the test's own n (the null probability of a perfect score) and printed
  beside the claim; it fails if the claim is reported without it, or if that best-achievable significance
  does not clear what the claim asserts.
- "Won by elimination" and "won by demonstrated skill" are DIFFERENT CLAIMS and are never interchangeable
  in later documents. The specific overclaim to stop propagating: downstream specs promoted the pilot to
  *"the only eligible representation"* (`laser_warrant_list_spec_v3.md:16`, identically `v2:14`), and the
  phrase then did load-bearing work in every spec after it.
- A superseded claim is CORRECTED where it is carried, not merely footnoted somewhere newer. For an
  editable (non-sealed) carrier this is an in-place correction. **For a sealed, sha-pinned, or
  append-only carrier — whose bytes may never be edited (`spectral_program_design_authority_amendments.md:16-19`,
  the same byte-freeze that protects this log) — the correction is a BINDING SUPERSESSION recorded in the
  controlling forward authority (this amendment log, or a superseding non-sealed spec) that (i) names the
  sealed document and the exact superseded claim, and (ii) is MANDATORY for anyone citing that document —
  so the correction travels WITH the sealed claim and is not a stray unlinked footnote. The sealed bytes
  are never edited.**

*Consequence:* a spec resting on a comparative claim that fails either the significance test or the
elimination-vs-skill distinction is not sealable; the claim is corrected — in place if editable, else by
binding forward supersession — before any successor cites it.

**Correction at source, recorded here (the binding supersession 4c requires — MANDATORY for anyone
citing these documents):** the claim that the Stage-A engineered representation (R-ENG) is the *"pilot
winner"* / *"the only eligible representation"* — carried at `laser_warrant_list_spec_v2.md:14`,
`laser_warrant_list_spec_v3.md:16`, and `laser_warrant_v1/results/report.md:3` — is SUPERSEDED. It won
its eligibility pilot by ELIMINATION, not demonstrated skill: the pilot's own verdict was "NEITHER"
(`RBT4_report.md:23-25`), the three learned encoders were disqualified on inversions and none reached
the beat-the-baseline comparison, the whole test's best achievable p-value was 0.10 (six pair-orderings;
`r4_stage_a_v1/results/metrics.json`, `falsifiers.F1.n_pairs` = 6), and half its positive evidence came
from the P3 exemplar since ruled warrant-negative (`CTREV1_review.md` §2). Spec v3 is content-pinned by a
frozen package (`laser_warrant_v1/MANIFEST.json` — `pin_table` + `spec` block, `frozen_at: LWT1`) and
`report.md` is a regenerable output of the frozen runner, so their bytes stay untouched; THIS record is
the lawful correction, and any document citing R-ENG as a "winner" or "the only eligible representation"
must carry this supersession with it.

### Clause 4d — A suspicious caveat is a test to run, not a sentence to write

**Base clauses touched:** §7 (validation doctrine) and §5 (presentation discipline) — SUPPLEMENTED;
obligation on the delivering seat.

**Law text:** when a delivery's own disclosure names, in one sentence, a large SHARE of the output AND a
WEAKNESS in the evidence under it, that is a MEASUREMENT TO RUN BEFORE DELIVERY, not a caveat to write.
*Trigger (concrete):* any caveat pairing a share of the output with a weakness in the same sentence.
*Instrument / can-fail:* the delivering seat runs the measurement the caveat implies and reports the
result in place of the caveat; it fails if a delivery ships carrying such a caveat unmeasured.
*Consequence:* the delivery is held until the measurement runs; if it fails, no rows ship. *(The instinct
was correct — exec reported "12 of the 24 shipped rows rest on your most doubtful example" to the
operator AS A CAVEAT and treated a defect as a disclosure — `OPUS_EXEC8_handoff_2026_07_25.md` §5; the
one-minute measurement it implied would have caught the contamination first.)*

**Effect on the program:** every future laser / accent / energy spec, scored run, and operator delivery
is judged against these four clauses. A spec that cannot show it passed 4a's four gates, kept 4b's
exemplar hygiene, stated 4c's best-achievable significance, and ran 4d's implied measurement is not
sealed and does not deliver; agents cite these clauses and never re-derive them. Boundaries (§1),
rejections (§3), validation doctrine (§7), and runtime gates (§8) of the base document, and AMENDMENTS
1–3, stand unchanged everywhere not explicitly supplemented above.

*(End of AMENDMENT-4. Next amendment, if ever adopted, appends below as AMENDMENT-5.)*


## AMENDMENT-5 (2026-07-29) — source preservation: the source outlives the conclusion (5a the source record and its citations, 5b the method behind a number, 5c pointer direction and integrity)

**Adoption provenance:** on 2026-07-29 the operator asked whether his sound descriptions had actually
survived the 2026-07-25 handoff. They had not. An audit that day found three losses with one mechanism, and
the exec8 seat then composed the one-sentence law this entry builds on and OFFERED it to the operator:
*"Operator-supplied source material is preserved VERBATIM, and a derived artifact never replaces its
source. This binds his words, his descriptions, and the script behind any reported number."* **That
sentence is the exec's wording, not the operator's** — its two on-disk carriers both say so
(`local/spectral_v5_2026_07_17/A5DRAFT_work_order.md:7` heads it *"as proposed by the exec8 audit …
operator offered, NOT ratified"*, and the program's own memory record calls it a *"PROPOSED AMENDMENT-4
CLAUSE 5, offered to the operator … NOT YET RATIFIED"*), and no record anywhere shows the operator
formulating it. It is quoted here as an exec proposal and is NOT presented as an operator quotation; the
first draft of this entry got that wrong, and the producer check in clause 5a is what caught it. The audit's
on-disk record is the three cures it produced — `OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md` (his words
transcribed, with the third-party description sets kept separate and attributed),
`OPERATOR_SPANS_2026_07_25.md:3` (the pointer added the same day), `operator_spans_measure.py` +
`operator_spans_measure.json` (the method behind the six span measurements) — plus
`A5DRAFT_work_order.md` §"Provenance exhibits". There is no standalone audit report, which is itself a
small instance of the class this entry closes. Drafted by the A5DRAFT seat (Opus 5, exec dispatch,
2026-07-29), cured through two hostile reviews (A5REV, A5REV2 — reviewer ≠ author, both ruling FIX) and the
A5FIX1 / A5FIX2 rounds; applied to this log by the executive seat after a fresh review. Provenance
references only — every normative clause below is inlined.

**Provenance distinction (binding on how this entry is read):** nothing in this entry is
operator-ratified. The founding sentence is an EXEC PROPOSAL offered to him and not ruled on; the three
clauses, their instruments, their consequences and their limits are exec-adopted PROCESS law that becomes
program law ONLY by the exec adopting this entry after review. Nothing here is approved by his silence, and
his standing veto applies to every clause at any time. If he rules on the founding sentence — restating,
narrowing, or rejecting it — his words become the source and this entry is corrected forward, never edited
in place.

**This amendment authorizes no implementation, dependency, runtime, or lighting change.** §7 validation
doctrine, §8 runtime gates, and §9 step-by-step authorization stand unchanged and govern how every clause
below may ever be pursued. AMENDMENTS 1–4 stand unchanged. No repo tool, hard check, or CI gate is
authorized here: the one instrument this entry adds is a lane script, run by hand at review time.

**It binds FORWARD only, and it certifies nothing already shipped.** Adopting this entry does not declare
any existing spec, report, run, or delivery compliant, and it does not require any of them to be reworked.
It also proves nothing about completeness: the recovered files show that named material exists NOW; no
record establishes that nothing else was lost, or that the recovered transcriptions are complete. Every
count below is a count of KNOWN losses.

**Every mandatory obligation below names the check that fails when it is broken, and no obligation is
wider than its check.** Where a promise exceeded what could be checked, the promise was NARROWED to the
check and the remainder is named as a REVIEW OBLIGATION carrying no gate — a duty a human reviewer owes,
stated as unenforced rather than dressed as enforcement. Where nothing can check a promise at all, this
entry says so. That rule is applied to this entry's own text: three rounds of hostile review found it
describing checks it did not have, which is why it is stated here rather than assumed.

**The root failure these three clauses close.** The program kept what it CONCLUDED and discarded what it
concluded FROM. One audit, three known losses, one mechanism:

1. **The description corpus.** None of the sound-description text existed in any file — neither his
   definitions in his own voice nor the four description sets a third-party model wrote from his
   boundaries, whose adjectives (*raspy*, *foghorn*, *tea-kettle*, *wall-of-sound*, *masking the
   percussion*) are hypotheses and not his words, a distinction that itself nearly went missing. Only
   summaries survived. These were the definitions the program had waited nine months for, and the text of
   them lived in a chat session about to be closed.
2. **Three measured numbers.** New Sky's per-slot pump shape, the Twin pump depths, and the Twin
   `sustain_high_db` lift existed nowhere on disk — recorded once in conversation, then gone.
3. **Every method behind a number.** All six Tier-3 span measurements were taken with throwaway shell
   python. The numbers were written down; the way they were derived was not. Re-deriving them four days
   later reproduced one family of numbers exactly and failed to reproduce two others (clause 5b).

AMENDMENT-4's root-failure paragraph names this same class — *"lasts 8 beats and then tapers off"* became
`[416,424)` and the words were gone. But 4a's gates require OBTAINING his definitions (gate 1) and
CARRYING his structures (gate 3); none of them requires the SOURCE to still exist. A program can pass all
four gates while the evidence they were checked against evaporates. That is the gap this entry closes.

**What this entry binds, and what it does not.** BINDS: the laser / accent / energy program's artifacts —
design specs, design rounds, hostile reviews, scored runs and their reports, operator deliveries, and
entries in this log. Does NOT bind: repo runtime code and its docstrings, the general upkeep of the
tracked `docs/` tree, other programs or repos, and it creates **no duty to transcribe everything the
operator ever says** — the duty attaches only to source material a program artifact actually uses.
Third-party generated description text is not operator truth: it is preserved WITH its generator named and
its producer intact, and is never promoted to a label.

### Clause 5a — The source record, and what a citation of it must survive

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED; AMENDMENT-4 clause 4a gates 1 and 3 —
supplemented (they require his evidence be used and carried; this requires it still exist in his own
words). §1 boundary 3 (taste is human authority) is unchanged and is why this matters: if his words are the
authority, a paraphrase of them is not. AMENDMENT-3 clause 3c's closed-categorical-set discipline is
followed, not modified — the producer vocabulary below is a closed set.

**Law text, part 1 — the source record, in the form the instrument parses.** Operator source material a
program artifact will use is transcribed by the receiving seat into a PASSAGE of a source record: a file
carrying a `SOURCE-RECORD:` header, an `INDEX:` line listing every passage ID, and one block per passage —

```
PASSAGE <ID> | PRODUCER: <producer> | RECEIPT: <YYYY-MM-DD> | seat: <seat> | arrival: <how it arrived> | raw: no|<path>
> the text
END PASSAGE
```

- **producer** comes from the closed set {`OPERATOR`, `THIRD-PARTY:<name>`, `EXEC-MEASUREMENT`,
  `EXEC-RECORD`}. `THIRD-PARTY` without a name is not a lawful value.
- **receipt** carries all four fields — date, seat, arrival route, and `raw:` either `no` or the path to
  the retained raw material. **The date is written `YYYY-MM-DD` and only that.** Other real date syntaxes
  a parser might accept (`20260729`, `2026-W31-3`) are not this form and are rejected; the same rule binds
  the date a citation cites on.
- **text** is transcribed with no word added, removed, reordered, or respelled. **This is what "VERBATIM"
  means in this entry, exactly:** the only differences permitted between raw material and passage are line
  wrapping and a `>` prefix per line.
- **The grammar is validated, and a malformed record is not a lawful source.** A header-form record must
  carry the header; **EXACTLY ONE `INDEX:` line — counted whether or not it carries any IDs** — which must
  itself be non-empty and **list no ID twice**; complete `PASSAGE … END PASSAGE` blocks; unique passage IDs;
  and an index whose ID set matches the body. A record failing any of those is not a source at all
  (check S) — a header line alone does not make one, neither does an index that repeats an ID, nor a second
  index line quietly replacing the first, **nor a bare `INDEX:` followed by a real one**: two index lines
  are two index lines even when the first is empty.
- **Legacy form, still lawful, and closed at three:** a file that declares producers as `TIER n` headings is
  a source record whose passages are cited by line range, with the mapping TIER 1 → `OPERATOR`, TIER 2 →
  `THIRD-PARTY:<name from the heading>`, TIER 3 → `EXEC-MEASUREMENT`. **Those three are the whole lawful
  set:** any other tier number is not a source form, and a TIER 2 heading that names no producer is not
  one either. Legacy files carry no receipts and no index; what that costs is stated in the instrument
  below rather than papered over.
- A file that is neither form is a DERIVED artifact and may never be cited as a source.

**Law text, part 2 — the citation.** A derived artifact quoting source material names the source FILE, the
PASSAGE (its ID, or its line range in a legacy file), the PRODUCER it claims, and the DATE it cites on. A
quote naming only a file is not a citation. **Everything mandatory in this clause binds the citations an
artifact DECLARES.** Declaring every quotation it makes is a REVIEW OBLIGATION on the authoring seat and
the sealing reviewer, NOT a gate: the instrument's coverage scan is advisory only, and an undeclared
quotation is invisible to it. That is stated here so no one mistakes a clean run for a complete one. Any omission — inside the quotation or at its end — is MARKED
with an elision mark; a citation that stops before the end of its passage and does not mark it is a
violation, whether or not it ends in punctuation. A remainder that is only punctuation is the end of the
passage and needs no mark.

**Law text, part 3 — the permitted normalization (closed, because "verbatim" cannot be enforced against an
open set).** Comparing a citation to its passage folds only: Unicode quotes/apostrophes/dashes to ASCII;
apostrophes dropped; markdown markers `>` `*` `_` and backticks stripped; whitespace runs collapsed; case
folded; fragment-edge punctuation trimmed. A word-level difference — a word added, dropped, changed, or
reordered — fails check C or O below. A difference INSIDE that list passes by design and is not a
violation.

*Instrument:* `local/spectral_v5_2026_07_17/a5_quote_check.py`, run over a manifest that declares the
citation cases and the `scan` windows of the citing artifacts:

```
python3 -B a5_quote_check.py --manifest <manifest>.json [--baseline <baseline>.json] \
                            [--write-baseline <baseline>.json] --out <results>.json
```

Seven checks gate a citation; a citation passes only if every gate that applies to it holds:

- **S — source, not derivative, and well-formed.** The cited file must be a source record: header form
  with a valid grammar (header + exactly one index line, counted even when bare, whose value is non-empty
  and free of duplicate IDs + complete blocks + unique passage IDs + index matching body), or legacy tier
  form using ONLY tiers 1, 2 and 3. A derived artifact FAILS; a malformed header-form record FAILS —
  including `INDEX: P1, P1`, a record carrying two index lines, a bare `INDEX:` followed by a valid one,
  and a record whose only index line is bare; a `TIER 999` file FAILS; a TIER 2 heading naming no producer
  FAILS. *(This is the check that
  refuses to let a work order, a spec, or an amendment entry stand in for the words it quotes — and that
  refuses a record whose own bookkeeping does not parse.)*
- **T — producer.** The passage's declared producer must equal the producer claimed, matched against the
  closed vocabulary. `THIRD-PARTY` with no name FAILS; a claim against a file that declares no producer
  FAILS; a third-party passage claimed as `OPERATOR` FAILS.
- **C — containment.** Every fragment of the citation appears in the cited passage under part 3's
  normalization.
- **O — order.** The fragments appear in the passage in the citation's order, non-overlapping.
- **E — omission marking.** An omission inside a quotation breaks C or O for free. A terminal omission —
  the citation stopping anywhere before the end of its passage, punctuated or not — FAILS unless the
  citation carries a trailing elision mark.
- **R — receipt.** For a source record: the four receipt fields must be present, the receipt date must be
  a real calendar date **written `YYYY-MM-DD`**, and it must be on or before the citation's date — which
  must satisfy the same rule. A missing field FAILS; `2026-99-99` FAILS; `20260729` and `2026-W31-3` FAIL,
  because they are dates in a form the law does not print; a receipt dated after the citation FAILS. **For a legacy tier
  file the receipt is REPORTED, not gated** — legacy files predate the form, and retrofitting them is not
  required by this entry.
- **X — raw versus passage.** Where the receipt names retained raw material, the passage must match it
  under transcription normalization (line wrapping and `>` prefixes only, since transcription may not
  respell). A mismatch FAILS, and a receipt naming a raw file that does not exist FAILS. **Where no raw was
  retained, this is REPORTED as `not-available` and is not gated:** a passage transcribed from a display
  cannot be verified against material that no longer exists, and no check here can pretend otherwise.

One check gates the RUN rather than one citation:

- **B — integrity against a preserved baseline.** `--write-baseline` first VALIDATES every cited source
  record and **refuses to write anything if one is malformed**; what it then records, per record, is the
  index ID set and each passage's producer, TEXT, and COMPLETE receipt metadata — date, seat, arrival and
  raw. `--baseline` re-verifies and FAILS on: a deleted passage, mutated text, a changed producer, ANY
  changed receipt field (a rewritten `seat:` or `arrival:` alone is enough), an index ID set that shrank,
  a record that no longer parses, a cited source record that has no baseline entry at all, **and a CITED
  PASSAGE APPENDED AFTER the baseline was taken and not yet armed** — which is the hole a passage could
  otherwise slip through by being added later and quoted immediately.
- **Arming an appended passage — `--extend-baseline IN OUT`.** Appending is lawful and must stay lawful, so
  the law names the procedure rather than forbidding growth: the extension **re-verifies every recorded
  passage first and REFUSES to write when any of them changed**, then records the new IDs. An extension can
  therefore arm new material but can never launder an edit to old material, and a record whose earlier
  passages were quietly rewritten cannot be re-baselined into cleanliness. The baseline stores text and
  metadata in the clear — no hashes — so it detects any change to material it has a record of, and nothing
  about material it does not.

*Advisory, never gating — M, the coverage scan.* For each `scan` window the manifest declares, the
instrument parses the citing artifact and prints any double-quoted span of twelve characters or more that
no case covers. **It is not a completeness check and this entry does not claim it is:** a manifest that
declares no windows produces no output at all, two identical quotation occurrences covered by one case
report clean, and quotations not wrapped in quote characters are never seen. It is a reading aid for the
reviewer who owns the declaration duty, and nothing more.

*Reported, never gating:* a citation that starts mid-passage without a leading mark. This entry does not
require a leading mark, so it is not made a gate; it is printed so a reviewer can see it.

*The temporal duties, downgraded honestly.* "In the receiving round" is not provable by any check available
here. What check R enforces is narrower and real: that a receipt exists, carries its four fields, and is
dated on or before the citation. File mtimes are corroboration only and bind nothing. **A receipt is a
declaration; nothing here detects a backfilled or untruthful one, and this entry claims no more than it can
check.**

*Can-fail — measured, with every gate demonstrated firing separately (33 cases, 9 PASS / 24 FAIL; 5 gating
run rows, 4 PASS / 1 FAIL; 2 advisory rows that gate nothing):*

| gate | case that fails it | case that passes it |
|---|---|---|
| **S** | the exec work order (`A5DRAFT_work_order.md:9-11`) cited as an `EXEC-RECORD` source; a `TIER 999` file cited as `EXEC-MEASUREMENT`; a header-form record with no `INDEX:`; one whose index lists an ID twice; one carrying two index lines; **one whose first index line is bare and whose second is valid**; and one whose only index line is bare | any citation into a valid source record or a tier-1/2/3 file |
| **T** | *"raspy, brassy resonance"* (`OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md:76-77`) claimed as `OPERATOR`; and the same words claimed as unnamed `THIRD-PARTY` | the same words as `THIRD-PARTY:Gemini`; a Tier-3 measurement as `EXEC-MEASUREMENT` |
| **C** | `accent_moment_spec_v9.md:15` — *"on the drop the elephant toots…"* where he wrote *"on the beat drop (or later in the drop)…"*; a control sentence never written; this entry's founding sentence claimed as his | the five v9 quotations whose words match |
| **O** | his correction at `:49-50` with its two fragments swapped | the same correction in his order |
| **E** | five live v9 quotations that stop mid-passage unmarked, including *"a broadly defined musical element that can take many forms"* (`:41-47`), which carries no punctuation at all | the identical quotation with a trailing `…`; and quotations that reach the end of their passage |
| **R** | a fixture passage with no `RECEIPT:` field; one dated the day AFTER the citation; one dated `2026-99-99`, which is ten characters and not a date; one dated `20260729`, which is a real date in a form the law does not print; and a citation whose own `cited_on` is `20260729` | a fixture passage with all four fields, dated `YYYY-MM-DD` on or before the citation date |
| **X** | a fixture passage that respells one word of its retained raw material (*"whilst"* for *"while"*) | a fixture passage that matches its raw file exactly |
| **B** | a mutated copy of the fixture record (passage deleted, text mutated, index shrunk — all reported in one run); a copy with ONLY `seat:` and `arrival:` rewritten; a cited source record with no baseline entry; **a cited passage appended after the baseline (`EXT-02`), whether quoted faithfully or after being reworded**; `--write-baseline` refusing to write while a cited record is malformed; and `--extend-baseline` refusing to arm while a recorded passage has changed | the unmutated record against its own baseline; a passage cited after being armed by a lawful extension |
| M *(advisory)* | — it gates nothing. It reports five uncovered quotations in one declared window of `accent_moment_spec_v9.md` and none in the `:14-23` window | — |

Two of the eight operator-quote spans in `accent_moment_spec_v9.md:14-23` pass; six fail — one for altered
words, five for unmarked terminal omissions. **That is the honest price of check E, and it is one character
per quote.** The alternative — excusing a cut that lands on a sentence boundary — was considered and
rejected: it is exactly the hole that let a quotation drop the whole second half of his accented-moment
definition while passing.

*Consequence — a failed citation has exactly two lawful outcomes.* CORRECT the citation — re-quote, add the
mark, fix the producer, add the receipt — or RECLASSIFY it as a paraphrase, dropping the quotation marks
and any "verbatim" claim with them. **No reviewer may accept altered words as the operator's verbatim
words:** a reviewer can verify a transcription or reject it, but cannot make words he did not write into
words he wrote. The sealing review (reviewer ≠ author) confirms which outcome occurred and records it; the
authoring seat may not self-certify either. A spec quoting operator words with no source passage at all is
not sealable, and a delivery in that state does not ship.

*What no check here does.* It cannot tell whether a faithful, correctly-attributed, correctly-marked
quotation is being used out of context or selected to mislead; it cannot verify a passage transcribed from a
display; and it cannot detect an untruthful receipt. The producer binding and the operator's veto are the
only guards on those, and neither is a check. This is claimed as a transcription-fidelity and
record-integrity instrument, and nothing more.

### Clause 5b — A reported number names the method that reproduces it

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED (what may be claimed now includes how it
may be re-derived); AMENDMENT-4 clause 4c — extended from a claim's SIGNIFICANCE to a number's
REPRODUCIBILITY, and its sealed-carrier supersession mechanism is reused below.

**Law text:** any measured or computed number — derived from audio, the spectral cache, a corpus, or a
run's output — that a program artifact REPORTS or CITES names, at the point of citation, the on-disk
method that reproduces it: a committed repo tool, a preserved lane script, or a frozen manifest-pinned
runner, together with the exact command. Ad-hoc shell and throwaway interpreter sessions remain a lawful
way to EXPLORE and are never a lawful way to REPORT: the moment a number leaves the session, its method is
written down, or the number does not travel.

*Instrument / can-fail:* the citing artifact prints the method path and the exact command; the sealing
review RE-RUNS the numbers its own pass/fail decision depends on and records which ones it re-ran. It fails
when a cited number names no method, when the named method does not produce it, or when a review's decision
rested on a number the review never re-ran and did not say so. This one is discharged by a human reading and
a re-run, not by a script, and it says so plainly — the demonstrations below are what a re-run found both
times it was done.

*Consequence, including when a re-run is not possible.* A number with no named method does not travel: the
artifact is not sealable on it and does not ship it. When the method is named but re-running is genuinely
unavailable — cost, missing hardware, an environment that no longer exists — the artifact MAY still seal on
that number by naming the RUN IDENTITY it relies on instead: the frozen manifest-pinned package or the
recorded prior run of the named script, identified in the artifact, with the review recording that it
relied on a prior run rather than its own. What may never happen is sealing on a number whose method is
absent, or a review recording an open item and sealing anyway as if the check had passed. An open item is a
disclosure, not a discharge.

*Demonstration 1 — the method that came back, and the error it exposed.* The six Tier-3 span measurements
of 2026-07-25 were taken with throwaway shell python; numbers recorded, method lost.
`operator_spans_measure.py`, written 2026-07-29 to cure exactly that, reproduces all six figure/ground
lifts EXACTLY as recorded (+1.4 / +8.4 / +8.4 / +13.2 / +13.2 / +2.6 dB) — **and it exposed a number the
ad-hoc version had produced differently.** New Sky's track air-duck baseline was recorded as 6.0 dB
(`OPERATOR_SPANS_2026_07_25.md:59`); the preserved script reproduces 6.14 dB, because the ad-hoc version
excluded the span itself from the track baseline while the script includes the whole track
(`operator_spans_measure.py:159`). Same span, same cache, a method difference nobody could see and nobody
chose.

*Demonstration 2 — the numbers that did NOT come back (found by the hostile review of this entry, not by
its author).* Two other recorded families do not reproduce as printed. The I Cannot growl's stereo width was
recorded as side/mid `0.163` and L-R correlation `0.949`
(`OPERATOR_SPANS_2026_07_25.md:42-45`); the preserved run gives `0.15989` and `0.95015`. Its band-limited
centre was recorded as moving `159 → 172 Hz`
(`OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md:86-87`); the preserved run prints per-quarter values
`[158.1, 180.5, 171.8, 163.6]`, in which the recorded pair cannot be located unambiguously — first-to-last
is `158.1 → 163.6`, a net of `+5.5 Hz`, not the recorded pair at all. **Why they differ is UNKNOWN and
cannot be determined, because the method that produced the recorded values no longer exists.** The
conclusions those numbers supported are unaffected in direction (the width contrast and the absence of a
pitch dive both survive), and both are recorded here as *reproduced approximately, not exactly*. This is
the clause's real argument: **an unpreserved method does not merely inconvenience a later reader — it hides
errors, and it makes the errors it hides unattributable afterwards.** Three number families, one
reproduces exactly, two do not, and nobody can say why.

*Legacy numbers, and the route that edits no sealed byte:* this clause binds at the ACT OF CITATION, so it
is satisfiable without touching one existing byte anywhere. A number already recorded whose method is
unrecoverable is DEMOTED to *recorded, not reproducible* and REPORTED as such; it may not be cited as
measured evidence by a NEW artifact until a reproducer exists — and writing one is always available, which
is how the three lost measurements came back. Where the carrier is sealed, sha-pinned, or append-only, the
demotion is recorded as a BINDING SUPERSESSION in the controlling forward authority exactly as AMENDMENT-4
clause 4c requires, mandatory for anyone citing that document; sealed bytes are never edited. Numbers
produced by a frozen, manifest-pinned runner ALREADY satisfy this clause — the runner IS the preserved
method — and nothing here reopens a sealed package.

### Clause 5c — The derived artifact points at its source, and the cited source is integrity-checked

**Base clauses touched:** §7 (validation doctrine) — SUPPLEMENTED. Consistent with, and modifying nothing
in, this log's own byte-freeze and append-only rules (`:16-22`), which are the same discipline applied to
this document.

**Law text:** every derived artifact — spec, review, report, delivery, entry in this log — names the
preserved source passages it draws on, in the artifact itself, near its top. The pointer runs **derived →
source**; a source that happens to point forward at its derivatives does not discharge the derivative's
duty to point back, and a pointer that lands on another derived artifact is not a source pointer (check S).
A summary, table, coordinate, or grade is an ADDITION to its source, never a REPLACEMENT.

**Source records are append-only, and that is enforced against a baseline, not on trust.** The superseded
passage keeps its bytes and its ID; a source record carries an `INDEX:` whose ID set only grows. What
enforces this is check B: a baseline is taken with `--write-baseline` — which validates first and refuses
to write over a malformed record — and re-verified with `--baseline`, failing on a deleted passage, mutated
text, a changed producer, any changed receipt field, a shrunken index, an index that no longer matches the
body, or a cited record with no baseline entry. **The obligation is exactly co-extensive with that check,
and no wider:**

- It binds source records that have a baseline, and a cited record without one now FAILS rather than
  passing in silence — taking the baseline is part of creating the record.
- **It binds the passages the baseline records, and a cited passage appended later is NOT protected until
  it is armed — which is a failure, not a silence.** A record can grow lawfully; what it cannot do is grow
  a passage, have that passage quoted, and call the result integrity-checked. Arming is
  `--extend-baseline`, which re-verifies everything already recorded and refuses to proceed if any of it
  changed, so growth can never be used to bless an edit. Until a passage is armed, any run citing it fails
  B by name.
- **A correction appending a passage that NAMES what it supersedes is a REVIEW OBLIGATION, not a gate.**
  The schema carries no `supersedes` field, the instrument does not parse one, and a correction added
  without a back-link passes B. The reviewer owns that link; this entry does not pretend a check owns it.
- For a LEGACY tier file, what is verified is the cited passages — their text, order and producer section,
  re-checked by re-running the citation manifest (checks C, O, T) plus any baseline entry that exists. **A
  legacy file's uncited passages are not protected**, and this entry does not claim they are.
- No hashes are used, so this is not tamper-evidence: a coordinated rewrite of both a source record and its
  baseline would pass. Detection is also only as fresh as the last re-run.

*Instrument / can-fail:* at seal or delivery, the citation manifest is run: every named passage resolves,
its quoted words pass 5a's gates against that passage, its cited numbers carry 5b's command, and every
cited source record AND every cited passage re-verifies against its baseline (B). The coverage scan (M)
prints alongside and gates nothing. Demonstrated failing states for B: a mutated copy of a fixture record
(passage deleted, text mutated, index shrunk — all reported in one run); a copy with only `seat:` and
`arrival:` rewritten; a cited record with no baseline; a cited passage appended after the baseline, both as
quoted and after being reworded; `--write-baseline` refusing to write while a cited record is malformed;
and `--extend-baseline` refusing to arm while a recorded passage has changed. Demonstrated failing states
for S: a derived work order, a `TIER 999` file, a header-form record with no index, one whose index repeats
an ID, and one carrying two index lines.

*Consequence:* the artifact is not sealable and does not deliver until every pointer resolves, its cited
passages re-verify, and its baselined records pass. A source that turns out to be missing is REPORTED —
never reconstructed from a derived artifact that quoted it, and never re-titled as a source. Copying a
derivative into a file named for its source changes the filename, not the provenance.

*Stated limit:* no check can detect a source that was never written — which is precisely why the pointer
duty attaches at AUTHORING time. A seat that cannot name a source passage is discovering, in that moment,
that the source does not exist; the lawful move is to write it (5a) if the material is still in hand, and
to REPORT it if it is not. That report is a legitimate outcome, not a blocked lane — an honest "his words
for this were never saved and cannot be recovered" is worth more than a spec that quietly quotes a
reconstruction. This entry's own founding sentence is the worked example: it is attributed to the exec
because no operator source for it exists, and check S refuses the work order as a substitute.

**Durability — the honest limit of the word "preserved", and one open adjudication.** `local/` is
gitignored (`.gitignore:49`), so nothing in the program's lane directory is in git history. "Preserved" in
the clauses above therefore means **a file in the working tree**, whose only backstop is the repo's
standing ban on `git clean -fd` (`AGENTS.md:47`) — a ban earned by an actual multi-gigabyte loss. Two
durability tiers exist and are named, never conflated: **TRACKED** (committed repo paths — this log,
`docs/`, `tools/`) and **WORKING-TREE** (the lane). **No tracked SOURCE record exists for lane material,
and the law text inlined into an amendment entry is not one:** an amendment entry is a derived artifact,
and treating its embedded quotation as the source would be the very substitution clause 5c forbids. What
inlining buys is a tracked, durable copy of the LAW; the source it was drawn from stays in the working
tree, and the entry carries the pointer to it. Closing that gap — a tracked mirror, a backup, a policy
change about what may be committed — is **NOT authorized by this entry** and is REPORTED as an OPEN
ADJUDICATION for the exec. Per AMENDMENT-4's satisfiability standard, a gap this entry cannot instrument is
disclosed, not quietly widened; the three clauses are fully satisfiable as written against working-tree
files, and what is undecided is only how much durability the program buys.

**Effect on the program:** every future laser / accent / energy spec, design round, hostile review, scored
run, and operator delivery is judged against these three clauses alongside AMENDMENT-4's four, from
adoption forward. A spec that quotes him without a source passage, a report whose numbers name no method,
or a derived artifact with no path back to what it was derived FROM is not sealed and does not deliver;
agents cite these clauses and never re-derive them. Boundaries (§1), rejections (§3), validation doctrine
(§7), and runtime gates (§8) of the base document, and AMENDMENTS 1–4, stand unchanged everywhere not
explicitly supplemented above.

*(End of AMENDMENT-5. Next amendment, if ever adopted, appends below as AMENDMENT-6.)*

