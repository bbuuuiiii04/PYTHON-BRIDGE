---
doc_status: current
truth_level: operator-ratified amendment log (design authority companion; not code-derived)
last_verified_commit: 12db265e
last_verified_date: 2026-07-24
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

