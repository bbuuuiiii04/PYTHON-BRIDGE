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

*(End of log. Next amendment, if ever adopted, appends below as AMENDMENT-3.)*
