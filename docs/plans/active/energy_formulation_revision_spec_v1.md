---
doc_status: draft-for-review
truth_level: planned
last_verified_commit: 0a40b7b9
last_verified_date: 2026-07-24
validation_scope: >
  Codex implementation spec for AWR-291, the energy-formulation revision (v2)
  of the three energy-fabric descriptors E1/E2/E3 and their acceptance gates.
  Fixes the defects measured in
  local/spectral_v5_2026_07_17/energy_formulation_research_report.md against
  the real 551-track BY GENRE corpus: E2 grade saturation (66.8% of sections
  railed), E3 term collapse (two of three terms pinned at 1.0 on >92% of
  drops), and the E1 compression confound (rho -0.592 with dynamic range vs
  -0.043 with loudness). Changes descriptor math + acceptance gates + report
  tools ONLY: the env flags, thread placement, status surfaces, import fences
  and flag-off byte-identity kill tests DO NOT MOVE. Store schema bumps to 2
  so E2/E3 refuse v1 stores by the existing refusal law. All code claims
  verified at HEAD 0a40b7b9 on 2026-07-24. Awaiting exec review + operator
  gate before Codex executes. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Codex Implementation Spec - AWR-291: energy formulation revision (E1/E2/E3 v2)

Parent design: `energy_fabric_ladder_spec_v1.md`. Predecessors, whose landed
discipline is the template and whose laws are preserved verbatim unless this
spec names an exception: `energy_e1_track_weight_spec_v1.md` (AWR-286),
`energy_e2_section_grades_spec_v1.md` (AWR-288),
`energy_e3_drop_grades_spec_v1.md` (AWR-290).

Evidence base: `local/spectral_v5_2026_07_17/energy_formulation_research_report.md`
(ENERGYRES, 2026-07-24). Every number quoted below as "measured" comes from that
report's read-only passes over 551 BY GENRE tracks / 6,837 sections / 3,335
drops, whose counts reproduce the three official acceptance reports exactly.

**Framing law (exec, non-negotiable):** v2 outputs REPLACE v1 outputs
everywhere. The store schema bump to 2 makes E2/E3 **refuse to library-scale**
against a v1 store, by the existing refusal-by-construction law, so **no v1
number can survive into a v2 grade**. Stated precisely (EREV1 N6): what a
version mismatch refuses is the *store*, hence `library_scaled` and E3's corpus
fallback — `within_track` takes no store input at all, so with a stale v1 store on
disk both layers still emit v2 `within_track` grades with `library_scaled = None`.
That is the intended behaviour and it achieves the framing law; it is **not**
"refuse to grade". The operator's trust dossier is regenerated AFTER the rebuild —
that regeneration is the final deliverable of the IMPLEMENTATION, not of this spec.

---

## Part A - Context & Root Cause (verified; read, do not implement)

Every code claim re-read at HEAD `0a40b7b9` on 2026-07-24; **[confirmed]**
unless labeled otherwise.

### A.1 What the three layers do today

- **E1** `track_weight_v0.py:39` — `COMPONENT_KEYS = ("body_duty", "sub_duty",
  "onset_mh_mean", "growl_flatness_mean")`; `track_weight()` at `:121-124` is the
  unweighted mean of each component's library mid-rank percentile. Zero runtime
  importers, enforced by `tests/test_track_weight_v0.py:244-262`. [confirmed]
- **E2** `section_energy_v0.py:128-147` — `within_track` maps the section's mean
  `full_db`, relative to the track's own `loudness_ref_db`, through the span
  `SECTION_QUIET_OFFSET_DB = -8.0` → 0.0, `SECTION_LOUD_OFFSET_DB = -3.0` → 1.0
  (`:38-39`), clipped. `library_scaled = within_track × track_weight` (`:142-144`).
  Runtime-imported by `state_manager.py:132`, computed on the ANLZ worker at
  `state_manager.py:320-332`. [confirmed]
- **E3** `drop_energy_v0.py:90-112` — three terms over `[beat, beat+16)`:
  `body` (same −8/−3 span), `sub_duty` (beats with `sub_db ≥ ref − 12`),
  `onset_ratio` (`mean(onset_density_midhigh) / scalars["onset_mh_p90"]`);
  `within_track` = mean of present terms. Runtime-imported by
  `state_manager.py:133`, computed on the ANLZ worker at `state_manager.py:346-355`.
  [confirmed]
- **Store** `tools/track_weight_report.py:120-136` writes `schema_version: 1`
  with `accepted`, `distribution`, `tracks`. `section_energy_v0.py:52-71`
  refuses anything whose `schema_version != STORE_SCHEMA_VERSION` (`:41`),
  whose `accepted is not True`, or whose shape is wrong. [confirmed]

### A.2 The three measured defects

**D1 — E3's drop grade is one term wearing three terms' clothes.** [confirmed]
Measured over 3,335 graded drops: `body` is pinned at exactly 1.000 on **94.0%**
of drops and `sub_duty` on **92.3%**. Consequences: `rho(onset_ratio,
within_track) = +0.945`; the median absolute difference between the real grade
and `(2 + onset_ratio)/3` is **0.0000** (p90 of that difference 0.021); and the
composite cannot leave the top third of its own scale — measured p05 0.806,
p50 0.910, p95 1.000, IQR **0.0625** against a G2 floor of 0.05.

Mechanism for `sub_duty`: in drop windows `sub_db` sits **+15.2 dB above**
`loudness_ref_db` at the median (p05 +9.3, p95 +16.5), because `full_db` averages
all 128 mel bands (`audio_spectral_features.py:354-355`) while `sub_db` averages
only the two bands at 20–60 Hz (`:39-40`, `:350-352`). The threshold `ref − 12`
therefore sits ~27 dB below where the signal is; the term has 16 possible values
in a 16-beat window and takes the top one on 92.3% of drops.

Mechanism for `body`: measured, drop-window mean levels sit within **0.89 dB**
(interquartile) of the track's own p95 — p25 −1.24, p50 −0.67, p75 −0.36 dB.
Widening the span to −12..0 dB un-rails it (94.0% → 1.7%) but its IQR is still
only **0.074**. Level is exhausted as a discriminator inside drops; widening the
span does not rescue E3.

**D2 — E2's section grade has collapsed into a near-yes/no.** [confirmed]
Measured over 6,837 sections: **17.7% at exactly 0.000, 49.0% at exactly 1.000,
66.8% railed**; only 33.2% land in between. **83.9%** of `chorus` sections read
exactly 1.000. In **190 of 504** tracks with ≥3 `chorus` sections (**37.7%**)
every one of those sections carries the identical grade.

Mechanism, arithmetic not opinion: measured section levels relative to
`loudness_ref_db` are p05 −12.02, **p50 −3.13**, p75 −1.1, p95 −0.40 dB. The top
rail sits at **−3.0 dB**, i.e. essentially exactly on the corpus median, so about
half of all sections pin at maximum by construction. This is structural — the
reference is the track's own p95, so section means are almost always ≤ 0 dB
relative, and any top rail meaningfully below 0 pins a large share.

**D3 — E1's weight is substantially a compression meter.** [confirmed] The
pinned loudness gate passes honestly: `rho(loudness_ref_db, track_weight) =
−0.0431` against `SPEARMAN_ACCEPT_MAX = 0.50` (`track_weight_v0.py:40`). But the
variable that actually drives the score is the track's own dynamic range:
`rho(p95−p05 of full_db, track_weight) = −0.592`, and with the silence-robust
form `rho(p95−p25, track_weight) = −0.675`. At the extremes it is near
deterministic and admits no exceptions: the top 8 tracks by weight span 6.1–9.2
dB of range; the bottom 12 span 17.3–24.1 dB; library median is 12.5 dB.

The gain-invariance construction correctly cancels a **uniform** dB offset — that
part works and is the same mechanism EBU Tech 3342 uses. But loud masters are
made by limiting and compression, which reshape the level distribution rather
than shifting it, and `body_duty` ("fraction of beats within 8 dB of the track's
own p95") reads that reshaping almost directly.

### A.3 Why the gates did not catch any of it

[confirmed] E2's G2 spread gate was re-run across eight span settings, from
today's binarized −8..−3 to a fully spread −20..0. **It passes at 99.1%–99.8% in
every case.** Worse, the pathology helps it pass: railing at both ends guarantees
a per-track spread of exactly 1.0, which is why the accepted report prints
"within_track spread: median 1.000" — that number reads as success and is the
symptom. Measured today vs the proposed span on the same corpus:

| measure | today (−8..−3) | proposed (−12..0) |
|---|---|---|
| sections railed | **66.75%** | **5.28%** |
| tracks with ≥3 chorus sections that can be ranked | **314/504 = 0.623** | **504/504 = 1.000** |
| G2 spread gate (as pinned) | passes 0.991 | passes ~0.996 |

E3's G3 separation gate compares E3's three-term drop grade against E2's
one-term section grade; its own review already recorded this as "a
direction-of-truth check, not a calibrated distance"
(`local/spectral_v5_2026_07_17/E3REV_review.md:80-81`). Its impressive 0.7466 is
inflated by exactly the binarization in D2.

### A.4 Record-keeping items folded into this spec (exec adjudication)

1. **The compression confound was never considered.** [confirmed] A grep across
   all four energy specs and every review doc for "compress"/"limiter"/"limiting"
   returns nothing. Every invariance claim in the lane is proven only for a
   uniform dB offset. Task 10 records it.
2. **The ladder's §B.2 intent for drop grades was silently narrowed.**
   [confirmed] `energy_fabric_ladder_spec_v1.md:230-231` defines the drop grade as
   "the drop's energy **within the track's set of drops**, scaled against
   library-typical drop energy via layer 1." E3 shipped an absolute
   loudness-relative measure instead. `E3REV_review.md:88-93` ruled the parent
   bullet an implementation sketch — a legitimate call — but **no document records
   that the within-set-of-drops normalization was dropped.** Task 5 restores it as
   the body term; Task 10 records the narrowing.
3. **Three docstrings overclaim exact gain invariance.** [confirmed] An
   independent re-derivation of the extractor re-ran real audio at 1.0× and 0.5×
   gain: with no clamping every dB series shifted by exactly −6.0206 dB to within
   8e-6 dB, but end-to-end through the real formulas `body_duty` moved +0.0022,
   E2 `within_track` up to 0.0044 and E3 `within_track` up to 0.0017 — caused by
   the 0.1 dB rounding applied to every stored value (`r1`,
   `audio_spectral_features.py:307-311`). Separately, the fixed power floor
   `_DB_FLOOR_POWER = 1e-10` (`:35`, applied at `:313-314`) pins beats at −100.0
   dB on **104 of 551 (18.9%)** BY GENRE tracks, where invariance fails outright.
   Task 10 mandates the docstring corrections. The magnitude (±0.005 grade units)
   is far too small to matter for lighting — this is honesty, not a functional bug.

### A.5 What is NOT broken and must not be "fixed"

[confirmed, all measured] — do not touch these while implementing:

- Uniform-loudness immunity works: `rho(loudness_ref_db, track_weight) = −0.043`.
- Refusal discipline works: missing / short / malformed data yields `None` or
  `[]` on every traced path in all three modules; the store gate genuinely
  refuses `accepted: false`, wrong-version, and malformed stores.
- The product law `library_scaled = within_track × track_weight` is **not** the
  defect. [confirmed] It collapses under v1 — `rho` **+0.9803** with track weight
  vs **+0.1713** with the moment — only because `within_track` varies 1.24× while
  track weight varies 3.76×. **[measured prediction, EREV1 F2]** Fixing D1 and D2
  substantially improves the product without changing the formula, but does *not*
  restore it. Measured on a full v2 stack (v2 E1 weights × the v2 four-term
  composite):

  ```
  v1:  rho(library_scaled, track_weight) = +0.9803   rho(library_scaled, within_track) = +0.1713
  v2:  rho(library_scaled, track_weight) = +0.8844   rho(library_scaled, within_track) = +0.5101
       within_track spread 1.24x -> 1.71x  ;  track_weight spread 3.76x -> 3.02x
  ```

  The moment's grip roughly triples (+0.171 → +0.510), which is a real gain. But
  `library_scaled` still tracks *which track it is* more than *which drop it is*,
  and the hard consequence survives intact: at the extremes of the real library the
  gentlest track's best drop scores 0.077 while the heaviest track's weakest drop
  scores 0.669, and **550/550 tracks still cannot have their best drop outrank some
  other track's weakest.** Do not read "the product law is fine" as "the product
  law is solved" — it is improved, measured, and left alone deliberately. Task 7
  makes both correlations permanent report lines so nobody has to take this on
  trust.
- No track-length confound (`rho(n_beats, weight) = +0.035`), no tempo confound
  driving the numbers (`rho(bpm, drop onset_ratio) = −0.062`), no sub-bass genre
  bias (DUBSTEP median sub 0.853 is **above** TECH HOUSE's 0.787).
- E1's `onset_mh_mean` is well chosen: nearly independent of the level terms
  (+0.007 with `body_duty`, −0.041 with `sub_duty`).
- Equal weighting is correct and stays. With positively correlated components,
  unit weights land essentially where optimal weights would (Wilks 1938; Wainer
  1976; Dawes 1979) — **redundancy is fixed by replacing a component, never by
  reweighting.** No learned weights, no PCA (its weights would move every time
  the library grows).
- The attach-match rate of 1.000 (1,659/1,659) and the true-drop law.

---

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

**Out of scope — do not touch:**
- `audio_spectral_features.py`, `spectral_cache.py`, `spectral_profile.py`,
  `smart_phrasing.py`, `anlz_reader.py`, `models.py`, `drop_presentation.py`.
  No new cached feature, no v4 schema change, no re-extraction of the library.
  **Every input this spec uses is already persisted in the v4 cache.**
- The env flags `RBSS_SECTION_ENERGY` / `RBSS_DROP_ENERGY`
  (`state_manager.py:232-233`), their default-OFF reads (`:871`, `:875`), the
  worker-thread placement, the status-block shapes (`:1287-1310`), the
  `DropDecision.energy_grade` attachment, the import fences, and the four-surface
  flag-off byte-identity kill tests. **The wiring does not move.**
- Anything LED, laser, SoundSwitch, Govee, or presentation. There is still NO
  consumer of any energy grade — that stays true after this change.

**Exactly one wiring delta is authorized** (Task 6): one keyword-only parameter
with a `None` default added at the existing E3 call site, following the precedent
`plan_track(..., drop_grades=None)` set by AWR-290. Nothing else in
`state_manager.py` changes. If you find yourself editing a second call site, a
thread, a flag, or a status key, **stop — that is out of scope.**

**Behavior that must not change:**
- Flag-off is byte-identical. With both flags unset the bridge must do no energy
  computation, add no payload key, add no status key, and leave every
  `DropDecision.energy_grade` at `None`.
- Absent / short / malformed data yields absent grades, never fabricated ones.
- No blocking I/O of any kind enters the 200 Hz push loop. All energy compute and
  the single store read stay on the ANLZ worker thread.
- All statistics, gates and reports use BY GENRE playlist tracks only, excluding
  the `RAP` playlist (`tools/section_energy_report.py:37-38`).

**Error handling:** propagate or fail closed — never swallow. No broad
`try/except`, no success-shaped fallback, no silent early return. A missing
normaliser makes a drop **ungraded (omitted)**; it never produces a re-weighted
mean. A failed acceptance gate is a **valid, reported result** that exits non-zero.

**The no-tuning law, stated three times because it is the one that gets broken:**
1. Every constant in this spec is pinned. **The implementer may not move any of
   them**, including every gate threshold, to make a run or a test pass.
2. If a gate fails on the real corpus, that is a legitimate outcome: report it
   plainly, exit non-zero, and return to the exec as a spec amendment.
3. Do not add a constant this spec does not name, and do not "temporarily" relax
   one. There is no such thing as a temporary threshold change here.

**Disclosure the implementer must not treat as licence to tune:** the gate floors
below were chosen *after* measuring both today's values and the candidate's, so
they are calibration-informed floors with stated headroom, not blind predictions.
That is exactly why they are frozen at implementation time.

---

### Task 1 - `track_weight_v0.py`: swap `sub_duty` for the brightness channel, add the compression control

**1a. Replace the redundant component.** `sub_duty` duplicates `body_duty`
(measured `rho = +0.578`), so the unweighted mean gives the shared
"how continuously full is this track" factor roughly 2 votes of 4 — which shows
in the outcome (`rho(component, weight)`: body +0.704, sub +0.712, onset +0.417,
growl +0.566).

Four replacement candidates were measured on the full 551-track corpus. Selection
criteria, in order: (i) lowest maximum correlation with the three kept components,
(ii) largest reduction in the compression confound, (iii) loudness neutrality
preserved, (iv) non-degenerate spread.

| candidate | max abs rho vs kept components | rho(weight, p95−p25) | rho(weight, loudness) |
|---|---|---|---|
| `sub_duty` (today) | 0.578 | −0.675 | −0.045 |
| **`brightness_med`** | **0.242** | **−0.480** | **−0.044** |
| `perc_full_mean` | 0.389 | −0.455 | −0.110 |
| `tilt_mean` (high−bass) | 0.399 | −0.448 | +0.077 |
| `perc_high_mean` | 0.540 | −0.441 | −0.053 |

`brightness_med` wins on both primary criteria. It is **already a persisted v4
scalar** — `"brightness_med": r1(np.median(centroid_hz))`,
`audio_spectral_features.py:422` — so this costs one dict read, no series scan and
no new audio pass. It is level-invariant (a power-weighted centroid, `:374`), so
it satisfies E1's standing law "no absolute-dB feature may enter the aggregate"
(`energy_e1_track_weight_spec_v1.md:101`). Its measured corpus spread is
339.7 → 1405.3 Hz (p05 → p95): non-degenerate by a wide margin.

It is also the change the arousal literature points at. Gingras, Marin & Fitch
(*QJEP* 67(7), 1428–1446, 2014) had two groups of 30 listeners rate 84 excerpts —
one group on originals, one on **amplitude-normalized** versions — and arousal
ratings were largely unaffected by removing level entirely. Spectral brightness
carries arousal information that survives amplitude normalization; three of E1's
four components were level-derived.

Change `COMPONENT_KEYS` (`:39`) to:

```python
COMPONENT_KEYS = ("body_duty", "brightness_med", "onset_mh_mean",
                  "growl_flatness_mean")
```

In `components()` (`:58-95`): delete the `sub` series read and the `sub_duty`
computation together with `REL_SUB_OFFSET_DB` and `sub_thr`; read
`scalars["brightness_med"]` alongside `loudness_ref_db` under the **same refusal
discipline** — absent, non-numeric or non-finite ⇒ `return None`, never a
fabricated component. Keep `REL_BODY_OFFSET_DB = -8.0` unchanged: `body_duty` is
not the component being replaced, and its rail is not the defect.

`REL_SUB_OFFSET_DB` is deleted from this module. `drop_energy_v0` keeps its own
sub constant only until Task 5 deletes it there too.

**Rewrite the module docstring, not just the one invariance sentence** (EREV1 F4).
`track_weight_v0.py:15-18` currently names `sub_duty` and its `sub_db` duty as one
of "the two dB duties" — that is describing code this task deletes. Rewrite the
whole header to describe the v2 component set (`body_duty`, `brightness_med`,
`onset_mh_mean`, `growl_flatness_mean`), state that `brightness_med` is a
level-invariant frequency statistic rather than a dB duty and therefore satisfies
the no-absolute-dB law by a different route than the duties do, and fold in the
corrected invariance wording from Task 10c. A stale module header is drift by the
repo's own §7 rule, and this header is the first thing E4's author will read.

**1b. Add the compression negative control (E1-a).** Add:

```python
DRAMA_ACCEPT_MAX = 0.55     # |rho(track_weight, robust dynamic range)| ceiling
```

Rationale, in the same shape as the existing `SPEARMAN_ACCEPT_MAX = 0.50`
argument (`energy_e1_track_weight_spec_v1.md:336-342`): a track that stays loud
throughout genuinely *is* more relentlessly energetic, so some correlation with
dynamic range is real signal and demanding rho ≈ 0 would reject a correct weight.
Above roughly 0.55 the weight is more compression-meter than energy-meter.
Measured: today's formulation reads **−0.675** (author) / **−0.6788** (EREV1
reviewer) — **fails** either way; the v2 formulation reads **−0.4799** (author,
using the cached `brightness_med` scalar) / **−0.4858** (reviewer) — **passes**
either way. **Take the reviewer's pessimistic figure as the planning number:
headroom is 0.064, not 0.070** (EREV1 N3). The 0.006 gap between the two
independent measurements is unexplained at this precision and is not worth chasing
— it is well inside the margin and both readings pass. This is the tightest gate
in the spec and the EAMEND report already flags it as the one it is least
comfortable with. `[assumed-reasonable]`, pinned, moved only by spec amendment.

**Use the silence-robust range, not the cached `drama` scalar.** `drama` is
`p95 − p05` (`audio_spectral_features.py:421`) and p05 lands on the −100 dB floor
on the 18.9% of tracks that contain digital silence — one such track already reads
`drama = 116.4 dB`. Add the pure helper:

```python
def robust_dynamic_range(v4) -> "Optional[float]":
    """p95 - p25 of the track's own per-beat full_db, in dB. The silence-robust
    stand-in for the cached `drama` scalar (which is p95 - p05 and is pinned by
    the -100 dB power floor on ~19% of BY GENRE tracks). None on absent / short /
    non-finite data - never a fabricated range."""
```

Read `full_db` over exactly `n_beats` with the existing `_finite_floats` guard and
the existing `MIN_BEATS` floor; reuse the module's local `_percentile` (`:161-176`)
— do **not** import `spectral_profile` (`energy_e1_track_weight_spec_v1.md:190-192`).

**1c. Add the component-redundancy gate (EREV1 F6).** Component redundancy at
`rho +0.578` is *the entire reason E1 is being changed* — yet as first drafted, E3
got a pinned term-correlation ceiling and E1, where redundancy is the actual
defect, got no correlation number printed at all. Nothing would notice if a future
`brightness_med` drifted back into agreement with `body_duty` on a grown library.
Fix the asymmetry with a mirror of E3's gate:

```python
COMPONENT_CORRELATION_MAX = 0.60   # worst |rho| between any two components
```

Measured v2 component matrix over the 551-track by_genre corpus, using the
**cached `brightness_med` scalar** (not a recomputed series median — this is what
the implementation will actually read):

```
                      body_duty  brightness  onset_mh  growl_flat
  body_duty             +1.000     -0.004     +0.007     +0.115
  brightness_med        -0.004     +1.000     -0.237     +0.242
  onset_mh_mean         +0.007     -0.237     +1.000     +0.102
  growl_flatness_mean   +0.115     +0.242     +0.102     +1.000

  worst |rho| = 0.2417        (v1's body_duty x sub_duty = 0.5783)
```

Independently reproduced by EREV1 to four decimals. The ceiling of 0.60 passes
with **2.5× headroom** and **fails loudly on today's 0.578** — the same value and
the same reasoning as E3's `TERM_CORRELATION_MAX`, deliberately, so the two layers
are policed symmetrically.

**1d. Extend the acceptance verdict.** New signature, precedence
corpus size → loudness proxy → **compression proxy** → **component redundancy** →
degenerate → ok:

```python
def acceptance_verdict(n_by_genre: int, rho: "Optional[float]",
                       rho_drama: "Optional[float]",
                       rho_components_max: "Optional[float]",
                       degenerate: "Sequence[str]") -> "tuple":
```

New branches: `(False, "compression_proxy")` when `rho_drama is None or
abs(rho_drama) > DRAMA_ACCEPT_MAX`; `(False, "redundant_components")` when
`rho_components_max is None or rho_components_max > COMPONENT_CORRELATION_MAX`.
Every `None` fails closed, exactly as the existing `rho is None` branch does
(`:199-200`).

**1e. Bump the store schema — and be honest that there are two literals**
(EREV1 N5). Add `STORE_SCHEMA_VERSION = 2` to this module. `tools/track_weight_report.py`
already imports `track_weight_v0`, so it **must use the constant**, not a third
literal — `"schema_version": track_weight_v0.STORE_SCHEMA_VERSION` in `build_store`.
`section_energy_v0.py` may not import it (the deliberate no-import convention at
`section_energy_v0.py:39`), so it restates the literal `2` with a comment naming
this spec. That leaves **two** declarations, not one: do not describe it as a
single source of truth. Every possible skew fails **closed** — a mismatch refuses
every store, loudly — so this is a clarity issue, not a safety one. Task 9 adds the
free one-line test asserting the two module literals agree.

---

### Task 2 - `tools/track_weight_report.py`: v2 store, corpus drop levels, new control

Read-only against the Rekordbox DB / ANLZ / audio / caches; writes ONLY
`<cache_dir>/trackweight_v1/track_weight_store.json` (+ optional `--out`).
Machine-local, **never committed**. That law is unchanged.

**2a.** Compute and report the compression control. For each scored track call
`track_weight_v0.robust_dynamic_range(v4)`; over the by_genre set compute
`rho_drama = spearman(track_weight, robust_dynamic_range)` using the existing
`spearman` helper. Pass it into the new `acceptance_verdict`. Print:

```
  Spearman(dynamic range p95-p25, track_weight) by_genre = %+.4f  (gate |rho| <= 0.55, n >= 100)
```

**2a-bis. Print the component correlation matrix and gate its worst off-diagonal**
(EREV1 F6). Over the by_genre scored set, compute the full 4×4 Spearman matrix
between `COMPONENT_KEYS` with the existing `spearman` helper, print it, and pass
`max(|rho|)` over the off-diagonal into `acceptance_verdict`:

```
## Component correlation (by_genre) — gate: worst |rho| <= 0.60
                        body_duty  brightness  onset_mh  growl_flat
  body_duty               +1.000     ...
  ...
  worst |rho| between components = %.4f   (gate <= 0.60)
```

This completes the adjudicated three-part E1-b comparison: (i) the component
matrix — here, (ii) `rho(weight, dynamic range)` — 2a, (iii) whether the top/bottom
15 lists move — already printed by the tool at `:296-313`.

**2b.** Add the corpus drop-level distribution to the store. E3's body term needs
a corpus fallback for tracks with fewer than two graded drops (measured: **12 of
550 = 2.18%**).

**This is NOT free — budget the plumbing** (EREV1 N4). `_grid_for`
(`tools/track_weight_report.py:95-102`) does call `read_anlz_drops` at `:98`, but
it returns **only the grid**; the caller at `:221` never sees the `data` object, so
`drop_beat_indices` is thrown away. **Widen `_grid_for` to return both** (e.g.
`(grid, drop_beat_indices)` or the `data` object) and thread it to the caller. Do
**not** re-open and re-parse the ANLZ file a second time per track — that would be
a silent 2× on the tool's I/O and it is avoidable in four lines.

**One implementation of the window convention only.** Import the new
`drop_energy_v0.drop_body_levels` (Task 5) from this tool. `tools/` is inside the
E3 import fence allowlist (`tests/test_drop_energy_v0.py:297`), so this is legal;
`track_weight_v0.py` must **not** import it, because that root module is outside
the allowlist and would break the fence. Do not reimplement the window math here —
a second copy would drift and the fallback would silently rank against a different
quantity than the primary term.

Accumulate every by_genre track's drop-window levels into one sorted list and
write it into the store.

**2c.** Store shape v2 (`build_store`, `:108-136`) — use the imported constant,
not a third literal (Task 1e / EREV1 N5):

```python
"schema_version": track_weight_v0.STORE_SCHEMA_VERSION,   # == 2
...
"distribution": {k: list(distribution.get(k, [])) for k in COMPONENT_KEYS},
"drop_body_distribution": sorted(all_by_genre_drop_body_levels),
```

`COMPONENT_KEYS` now carries `brightness_med` in place of `sub_duty`, so the
`distribution` keys change with it — that is the point of the schema bump. Keep
`sort_keys=True` on the dump (`:152`) and the atomic-write shape unchanged.

**2d.** Print the new component name in the distribution block and keep the
per-BY-GENRE-playlist median table as-is (descriptive, non-gating, reading it is
optional — `energy_e1_track_weight_spec_v1.md:250-254`).

---

### Task 3 - `section_energy_v0.py`: the span, and gates that can actually fail

**3a. Re-place the rail (E2-a).** Replace `SECTION_QUIET_OFFSET_DB = -8.0` /
`SECTION_LOUD_OFFSET_DB = -3.0` (`:38-39`) with:

```python
# Loudness-relative span for the section grade. NOT the spectral_profile section
# tier offsets any more: those are -8/-3 and are flagged in their own source as
# "engineering scale constants, not corpus-calibrated" (spectral_profile.py:54-55).
# Re-placed by AWR-291 from the measured corpus distribution of section levels
# relative to loudness_ref_db (p05 -12.02, p50 -3.13, p95 -0.40 dB): the old top
# rail sat on the corpus MEDIAN, pinning 49.0% of sections at 1.000.
SECTION_SPAN_LOW_DB = -12.0     # -> 0.0
SECTION_SPAN_HIGH_DB = 0.0      # -> 1.0
```

**Rename, do not just re-value.** The old names asserted an identity with the
`spectral_profile` tier constants that no longer holds, and leaving them would
make the next reader believe the tiers moved too. Update `span` and the mapping at
`:128` and `:141` accordingly. The clip, the `MIN_SECTION_BEATS = 4` floor, the
`_normalized_segments` fallback chain and the `library_scaled` product are
**unchanged**.

Measured effect of the span change alone, on the real corpus (all independently
reproduced by EREV1): sections railed **66.75% → 5.28%**; `chorus` sections pinned
at 1.000 **83.9% → 0.51%**; tracks whose ≥3 chorus sections can be ranked
**0.623 → 1.000**; chorus-vs-breakdown separation 0.836 → **0.501**. The
separation figure falls because today's 0.836 is inflated by the binarization
itself — 0.501 is still twice the new floor.

The span is **necessary but not sufficient**: with the mean aggregator retained,
2.25% of chorus sections still grade at the bottom rail. That is what Task 3d
fixes.

**3b. Bump the refused-store version.** `STORE_SCHEMA_VERSION = 2` (`:41`), with
a comment naming AWR-291 and noting this is the second of two declarations (Task
1e). This is what makes a v1 store refuse to **library-scale** by construction —
`within_track` is still computed, with `library_scaled = None` (EREV1 N6).

**3b-bis. Rewrite the module docstring** (EREV1 F4). `section_energy_v0.py:19-20`
states the span as "−8 dB → 0.0, −3 dB → 1.0" and calls it "the same
loudness-relative span the repo's section tiers use". Both halves become false in
this task: rewrite the header for the −12/0 span, state that the tier identity no
longer holds (the same point Task 3a's inline comment makes), describe the
aggregator chosen in Task 3d, and fold in the corrected invariance wording from
Task 10c.

**3c. Replace G2 with gates that discriminate (G-a, G-b).** The current
`SPREAD_GATE_FRACTION` / `SPREAD_MIN` pair passes at 99%+ under every span
setting and is maximally satisfied by the pathology it was meant to catch. Delete
both and pin:

```python
COVERAGE_GATE = 0.95            # G1, unchanged
SATURATION_GATE_MAX = 0.20      # G2 (new): fraction of sections on either rail
RANKABILITY_GATE = 0.90         # G3 (new): tracks whose chorus sections differ
SEPARATION_GATE = 0.25          # G4 (new): median(chorus) - median(low)
MIN_ACCEPT_N = 100              # unchanged
```

Rationale for each, measured on the real corpus. Three columns because Task 3d
changes the aggregator: **today** (mean, −8/−3) → **span only** (mean, −12/0) →
**as landing** (median, −12/0, the configuration this spec ships):

| gate | floor | today | span only | **as landing** |
|---|---|---|---|---|
| saturation | ≤ 0.20 | 0.6675 ❌ | 0.0528 | **0.0437** |
| rankability | ≥ 0.90 | 0.623 ❌ | 1.000 | **0.994** |
| separation | ≥ 0.25 | 0.836 | 0.501 | **0.471** |
| *(chorus at bottom rail — not a gate, the E2-b trigger)* | — | — | 2.25% | **0.63%** |

- **`SATURATION_GATE_MAX = 0.20`** — today fails by 3.3×; as landing it passes
  with **4.6× headroom**. This is the gate that would have caught D2 on day one,
  and it is the diagnostic the ceiling-effect literature prescribes.
- **`RANKABILITY_GATE = 0.90`** — 0.623 → **0.994**. Measured as: among by_genre
  tracks with ≥3 `chorus` sections, the fraction having ≥2 distinct
  `within_track` values. A grade that cannot rank a track's own drops is useless
  to the cue-casting consumer whatever else it does. The median costs 0.006 here
  (three tracks) against a 0.90 floor — noted, and far outweighed by what it buys
  in Task 3d.
- **`SEPARATION_GATE = 0.25`** — 0.836 → **0.471**. A direction-of-truth floor,
  deliberately loose, not a calibrated distance: drops must out-grade breakdowns
  or the mapping points the wrong way. Set at half the measured value because the
  operator's own law says some breakdowns legitimately grade high
  (`energy_fabric_ladder_spec_v1.md`, "an energetic breakdown in hard techno reads
  as such").

New verdict, precedence corpus floor → coverage → saturation → rankability →
separation:

```python
def gates_verdict(n_by_genre_eligible: int, n_graded: int,
                  railed_fraction: "Optional[float]",
                  rankable_fraction: "Optional[float]",
                  separation: "Optional[float]") -> "tuple[bool, str]":
```

returning `"insufficient_corpus"`, `"insufficient_coverage"`,
`"saturated_grades"`, `"unrankable_grades"`, `"inverted_or_flat_separation"`, or
`("ok")`. Every `None` fails closed.

**3d. E2-b: the section aggregate becomes the MEDIAN (exec adjudication on EREV1 F1).**

This was drafted as a deferred follow-up with a "2% of chorus sections at the
bottom rail" trigger and a baseline of "~1.6% — under the trigger, but only just".
**That baseline was wrong.** It was extrapolated from the long-section subset —
`6.7% × 24.6% ≈ 1.6%` counts only sections ≥64 beats, and short chorus sections
rail at the bottom too. Measured directly over all 3,335 by_genre chorus sections
at span −12..0:

```
chorus sections at the bottom rail = 75 / 3335 = 2.25%     (trigger was: > 2%)
   of which >= 64 beats : 55        (= 6.67% of the 824 long ones)
   of which  < 64 beats : 20        <- the ones the extrapolation dropped
```

So the trigger is **tripped the day this lands**, 2.25% against 2%. Re-placing a
threshold to preserve a deferral is exactly the goalpost move this spec forbids
three times over, so E2-b comes into this round. The deferral machinery is deleted
(Task 10e).

**The change:** in `grade_sections`, aggregate the section's `full_db` beats with
the **median** instead of the arithmetic mean, then map through the span exactly as
before. One line, plus a local percentile helper (do **not** import
`spectral_profile` — same convention as everywhere else in this lane).

**Measured rationale — the mean is destroyed by silence, the median is not.**
The dB conversion clamps at a fixed absolute floor of −100.0 dB
(`audio_spectral_features.py:35`, applied at `:313-314`), and **104 of 551 (18.9%)**
BY GENRE tracks contain at least one beat pinned there. One silent beat drags a
32-beat mean by roughly 3 dB; the worst real case is a 105-beat "drop" section with
48 silent beats whose mean is −56.8 dB while its median is −11.2 dB.

```
sections whose mean sits >5 dB below their own median : 212
   ... graded 0.000 by the MEAN   : 105
   ... graded 0.000 by the MEDIAN :  15      <- 86% of the false zeros cured

chorus sections at the bottom rail : 2.25% (mean) -> 0.63% (median)    3.6x better
long (>=64 beat) chorus at bottom  : 6.67% (mean) -> 2.18% (median)    3.1x better
```

The interaction with Task 4b's diagnostic is the point: sections come from
marker-to-marker spans with no audio refinement, and the final marker's section
runs to `total_beats` (`smart_phrasing.py:690-711`), so long sections routinely
swallow the outro and its fade to digital silence. A **mean** over such a section
describes neither the drop nor the tail. A median describes the part that lasts.

**What it costs, stated plainly:** saturation improves (0.0528 → 0.0437),
rankability slips 1.000 → 0.994 (three tracks), separation slips 0.501 → 0.471,
and `chorus` sections pinned at the *top* rail rise 0.51% → 1.50%. All four still
clear their floors with margin. Accepted trade.

**3e. The silence-gated reference is MEASURED INERT — do not implement it; exec
decision requested.**

The adjudication paired E2-b's median with an EBU Tech 3342-style silence gate on
the reference ("exclude quiet material before forming the p95"). I specified it,
measured it, and it does nothing. Candidate: exclude beats below
`ungated_p95 − 40 dB`, then re-take p95.

```
tracks where the gate moves the reference at all : 70 / 551
reference shift, dB      : min +0.000   p50 +0.000   p95 +0.025   max +0.180
beats gated out          : 2,808 / 286,150 = 0.98%   (424 of them at the floor)

every E2 gate metric, cached ref vs gated ref, at span -12..0:
   mean   + cached ref   railed 5.28%  chorus@1 0.51%  rankable 1.000  sep 0.501  bottom 2.25%
   mean   + gated  ref   railed 5.28%  chorus@1 0.48%  rankable 1.000  sep 0.501  bottom 2.25%
   median + cached ref   railed 4.37%  chorus@1 1.50%  rankable 0.994  sep 0.471  bottom 0.63%
   median + gated  ref   railed 4.37%  chorus@1 1.44%  rankable 0.994  sep 0.471  bottom 0.63%
```

**And it is inert by construction, not by luck.** EBU's gate exists to protect a
*range* statistic (Tech 3342's p10–p95 spread), where the low anchor sits in the
material the gate removes. Our reference is a **p95 anchor alone** — a high
percentile. Deleting ~1% of beats from the bottom of the distribution can only
shift a p95 by the width of one percentile step. No library will make that matter.

**My default is: do not implement it** — shipping a gate that provably cannot
change an output is precisely the disease this whole round is curing (a gate that
cannot fail, a term that is a constant). The silence damage is real and the median
in Task 3d cures 86% of it. **Veto this if you want it built anyway**; it is ~6
lines and harmless, just inert. This paragraph stays in the spec either way so the
next reader does not re-derive the idea and assume it was overlooked.

---

### Task 4 - `tools/section_energy_report.py`: new metrics + the boundary diagnostic

**4a.** Compute and print the three new gate inputs and feed them to
`gates_verdict`: the railed fraction over all graded by_genre sections
(`within_track <= 0.0 or >= 1.0`), the rankable fraction (denominator: tracks with
≥3 `chorus` sections), and the separation
`median(chorus within_track) - median(low within_track)`. Keep G1, the
MUST-print absolute-coverage informational line (`:168-171`) and the
`--limit ⇒ partial_run` forced failure (`:152-154`) exactly as they are.

**4b. Boundary-jitter diagnostic (E2-c) — REPORT-ONLY, never a gate.** Sections
come from `smart_phrasing.build_phrase_segments_from_markers`, which never looks
at the audio: each marker's section runs to the next marker, and the final
marker's section runs all the way to `total_beats` (`smart_phrasing.py:700-709`).
Measured consequence: **24.6%** of `chorus` sections are ≥64 beats (median 32),
and **4.4%** of them grade 0.000 with a median length of 73 beats — last drops
merged with the outro.

For each offset in `(-4, -2, -1, +1, +2, +4)` beats, re-grade with every section
boundary shifted by that many beats (clamped into `[0, n_beats]`, sections falling
under `MIN_SECTION_BEATS` skipped as usual) and print the median and p90 of
`|within_track_shifted - within_track|` over matched sections:

```
## Boundary-jitter sensitivity (INFORMATIONAL — not a gate)
  offset  median |delta|  p90 |delta|
  -4      ...            ...
```

This measures how much of the section grade is boundary noise rather than music.
It needs no labels and gates nothing.

**4c. Print the bottom-rail chorus fraction as an INFORMATIONAL line.** It is no
longer a deferral trigger (Task 3d landed E2-b), but it is the number that exposed
the mis-derived baseline in the first place and it is the cheapest early warning
that section aggregation has regressed:

```
  chorus sections at the bottom rail = %d / %d = %.2f%%  (INFORMATIONAL; median aggregator, expect ~0.6%%)
```

Print the count **directly over all chorus sections** — never extrapolate it from
a length-filtered subset. That extrapolation is what produced a 1.6% baseline for
a quantity whose true value is 2.25% (EREV1 F1).

---

### Task 5 - `drop_energy_v0.py`: four independent terms, none of them a constant

This is the largest change. The module keeps its identity — stdlib only, pure, no
I/O, runtime-imported by `state_manager.py` on the ANLZ worker.

**5a. Delete the two dead terms.** Remove `sub_duty` entirely (E3-a): measured
92.3% pinned at 1.000, 16 possible values, threshold ~27 dB from the signal.
Remove the level `body` term and its span constants `BODY_QUIET_OFFSET_DB` /
`BODY_LOUD_OFFSET_DB` and `SUB_OFFSET_DB` (`:38-40`): measured 94.0% pinned, and
still only 0.074 IQR after un-railing, because drop windows sit within 0.89 dB
(IQR) of the track's own ceiling.

**5b. Export the window-level helper** (used by the report tool in Task 2b and by
the new body term):

```python
def drop_body_levels(v4, drop_beats) -> "list[float]":
    """Per drop with window coverage >= MIN_WINDOW_BEATS: the window's mean
    full_db minus the track's own loudness_ref_db, in dB. The ONE implementation
    of this window convention - tools/track_weight_report.py imports it rather
    than reimplementing it, so the corpus fallback distribution ranks exactly the
    same quantity the primary term does. [] on absent / short / non-finite data."""
```

Same `DROP_WINDOW_BEATS = 16` / `MIN_WINDOW_BEATS = 8` convention as today
(`:37-38`), which is retained unchanged.

**5c. The body term becomes a rank (E3-b) — the ladder's original §B.2 intent.**
`energy_fabric_ladder_spec_v1.md:230-231` asked for "the drop's energy within the
track's set of drops"; E3 shipped an absolute measure instead (A.4 item 2). A rank
**cannot saturate by construction**, which is precisely why it is immune to the
defect that broke the level term.

- **Primary basis** — mid-rank percentile of this drop's window level among *this
  track's own* drop-window levels, when the track has ≥2 of them. Record
  `"body_basis": "track_drops"`.
- **Pinned fallback** — when the track has fewer than 2 (measured 2.2% of
  tracks), mid-rank against `corpus_drop_levels`, the sorted corpus distribution
  carried in the v2 store. Record `"body_basis": "corpus"`.
- **Neither available** ⇒ that drop is **ungraded (omitted)**. Never a
  re-weighted mean, never a fabricated 0.5.

Reuse the mid-rank definition already proven in `track_weight_v0.rank_in`
(`:98-107`) — `(count_less + 0.5*count_equal) / n` — reimplemented locally, since
`drop_energy_v0` must not import `track_weight_v0` (that root module is outside
the E3 fence allowlist and the dependency direction would be backwards).

`body_basis` is written into every grade dict. Grades on different bases are not
comparable to each other; recording the basis makes that visible instead of
silent, in the same spirit as E2's self-describing section boundaries.

**Three properties of the rank that MUST be documented where `body_basis` is
defined** (EREV1 F7) — E4's author will read this and must not misread
`within_track` as absolute or as "rank among the drops I hear":

1. **The ranking population is the RAW ANLZ marker set, not the true drops.**
   `drop_beats` is `data.drop_beat_indices`, and the true-drop law means only
   plan-attached true drops ever reach a surface. Measured: **3,335 raw graded
   drop windows vs 1,659 surfaced true drops — 49.7% of the ranking population is
   never shown to anyone.** So a surfaced drop's body term means "how this moment
   ranks among *all* of this track's raw Rekordbox drop markers", and the value
   **moves if Rekordbox re-analysis adds or removes a marker anywhere in the
   track.** That is a defensible choice — the raw set is the stable, complete,
   tick-independent population, and ranking against the plan-selected subset would
   make the grade depend on smart-drop selection — but it is exactly the class of
   thing that must not happen silently. Recorded in the change record too.
2. **Granularity on two-drop tracks.** With exactly 2 gradeable drops the mid-rank
   percentile can only ever be `{0.25, 0.75}`. Measured: **34 / 550 = 6.2%** of
   tracks. Not a defect; the rank is doing what a rank does with n=2. Say so.
3. **Ties.** Exact within-track level ties occur on **100 / 3,335 = 3.0%** of drop
   levels. The mid-rank definition `(less + 0.5·equal)/n` handles them correctly —
   tied drops share a value rather than being ordered arbitrarily. Not a defect,
   just undocumented until now.

**5d. The other three terms.** All four terms are within-track normalised, all
four are ratios or ranks (so all four are inherently level-invariant, a stronger
property than the relative-dB construction), and all four are computed from
already-cached data:

```python
body        = mid-rank of the window level among the track's own drop levels
onset       = clip01(mean(onset_density_midhigh[window]) / scalars["onset_mh_p90"])
perc_high   = clip01(mean(perc_high[window])            / p90(perc_high over n_beats))
growl       = clip01(mean(growl_flatness[window])       / scalars["growl_timbre_p90"])
within_track = (body + onset + perc_high + growl) / 4
library_scaled = within_track * track_weight   # or None - unchanged product law
```

`onset_mh_p90` (`audio_spectral_features.py:426`) and `growl_timbre_p90` (`:424`)
are **already persisted scalars** — free reads. `perc_high` has no cached p90, so
compute it in-module over the track's own `n_beats` with a local percentile
helper. That is one `sorted()` per track on the ANLZ worker thread, which already
does far more than that per track; it must **never** move to the push loop, and
adding a cached scalar instead would force a v4 schema bump and a full library
re-extraction, which is explicitly out of scope.

Why these three and not others: a measured **range-over-IQR** statistic — the
median across tracks of each series' within-track **range (max − min)** over that
track's own drop windows, divided by the series' **corpus-wide IQR**. Name it
precisely (EREV1 N1): it is *not* a like-for-like ratio, because a range is
compared against an interquartile spread, so **do not gloss it as "above 1.0 means
it varies as much within a track as across the library"** — that reading is wrong.
It is a consistent relative ordering, nothing more. The like-for-like version
(median within-track IQR ÷ corpus IQR) tops out at 0.456, and **produces the
identical ordering**, so every selection decision below stands under either
definition:

| series | range ÷ corpus IQR | IQR ÷ corpus IQR | rho vs onset density |
|---|---|---|---|
| `perc_high` | **1.22** (best of all 21 cached series) | 0.456 | +0.273 |
| `onset_density_midhigh` | 1.10 | 0.412 | — |
| `growl_flatness` | 0.93 | 0.367 | +0.066 |
| `fluxsum_midhigh` (rejected) | 0.95 | 0.351 | see 5e |
| `sub_db` (dropped) | 0.83 | 0.206 | — |
| `full_db` (dropped) | **0.74** (weakest) | 0.207 | — |

The two terms being deleted are the two weakest discriminators in the entire
cached feature set under **both** definitions.

**5e. E3-d: `fluxsum_midhigh` is REJECTED — argued.** `fluxsum_midhigh` is the
continuous version of `onset_density_midhigh` (which is an integer count per
beat), so it is superficially attractive. Measured, it loses on every axis that
matters: its range-over-IQR discrimination is **0.95 vs onset's 1.10**; it
carries the two highest correlations of any candidate pair (**+0.248** with
`onset`, **+0.268** with `perc_high`, both in term space — see the correction
below); and adding it as a fifth term would
reintroduce exactly the correlated-component disease this spec is removing from
E1 (A.5, Wilks/Wainer/Dawes). The coarseness argument does not survive contact
with the data either: averaging 16 integer counts gives 1/16 resolution, and
today's composite already achieves a mean distinct-fraction of 0.82 across a
track's own drops. **Four terms, not five.** Do not add it.

**Correlation figures, stated in full because EREV1 N2 could not reproduce them.**
The number depends entirely on which space you measure in, so name it:

```
raw window means                      rho(fluxsum, onset) = +0.5189
p90-normalised AND clipped to [0,1]   rho(fluxsum, onset) = +0.2478   <- the spec's +0.248
p90-normalised AND clipped to [0,1]   rho(fluxsum, perc_high) = +0.2680  <- the spec's +0.268
EREV1's independent measurement       rho(fluxsum, onset) = +0.3378
```

**Term space — p90-normalised *and clipped* — is the correct comparison**, because
that is exactly the form a term would take inside the composite, and it is what
`TERM_CORRELATION_MAX` would police. The clipping is the step most likely to have
been missed. The rejection holds under **every** reading (0.248 / 0.338 / 0.519)
and gets stronger under the two alternatives, so nothing about the decision
changes; only the printed figure needed pinning down.

**5f. All four terms are REQUIRED — this cures a latent silent-reweight bug.**
Today, `onset_ratio` is dropped from the mean when `onset_mh_p90 <= 0`
(`:104-106`), silently re-weighting the survivors from 1/3 to 1/2 each and making
those grades non-comparable with every other grade. The E3 spec never
acknowledged that consequence. Measured, the path never fires on the current
corpus (0 of 3,335 drops), so it is latent, not active — cure it anyway:

> **If any of the four normalisers is absent, non-finite, or ≤ 0 — `onset_mh_p90`,
> `growl_timbre_p90`, the in-module `perc_high` p90, or the body basis — that drop
> is ungraded (omitted from the returned list). The mean is ALWAYS over exactly
> four terms or the drop does not exist.**

**5g. New signature** (`corpus_drop_levels` is keyword-only with a `None`
default, so the legacy call shape still type-checks and the flag-off path is
untouched):

```python
def grade_drops(v4, *, drop_beats, track_weight: "Optional[float]",
                corpus_drop_levels: "Optional[Sequence[float]]" = None) -> "list[dict]":
```

Grade dict shape: `{"drop_beat", "within_track", "library_scaled", "coverage",
"body_basis"}`. `grades_by_beat` (`:115-117`) is unchanged.

**5h. Replace the gates.** Delete `IQR_GATE = 0.05` and `SEPARATION_GATE = 0.15`
(`:42-43`) and pin:

```python
COVERAGE_GATE = 0.95            # G1, unchanged
TERM_SATURATION_MAX = 0.20      # G2 (new): worst single term's railed fraction
TERM_CORRELATION_MAX = 0.60     # G3 (new): worst |rho| between any two terms
IQR_GATE = 0.10                 # G4 (raised from 0.05)
RANKABILITY_GATE = 0.90         # G5 (new)
LEVEL_SEPARATION_DB = 3.0       # G6: dB sanity check on the window indexing
GRADE_SEPARATION_GATE = 0.10    # G7 (new): the composite must out-grade breakdowns
MIN_ACCEPT_N = 100              # unchanged
```

Measured on the real corpus for the v2 terms (all pass, with the stated headroom):

| gate | pinned floor | measured v2 | measured today |
|---|---|---|---|
| G2 worst term railed | ≤ 0.20 | **0.062** (`onset`) | 0.940 (`body`) |
| G3 worst term pair rho | ≤ 0.60 | **0.246** (`perc_high`×`growl`) | n/a |
| G4 composite IQR | ≥ 0.10 | **0.1448** | 0.0625 (**would fail**) |
| G5 rankability | ≥ 0.90 | **1.000** | 0.996 |
| G6 level separation | ≥ 3.0 dB | **+6.51 dB** | +6.51 dB |
| G7 grade separation | ≥ 0.10 | **+0.1938** | n/a (v1 had no such gate) |

**G6 is a dB sanity check on the window indexing — it is NOT a grade check.**
The old G3 compared E3's three-term grade against E2's one-term section grade, two
different scales, which its own reviewer flagged. Now that the body term is
rank-normalised the composite's median sits near 0.5 by construction, so a
grade-space comparison against *E2* would be even less meaningful. G6 therefore
asserts direction of truth **in dB**: `median(drop-window mean rel_dB) −
median('low' section mean rel_dB) >= 3.0`. Measured section levels by label —
`chorus` p50 −1.17, `up` p50 −5.98, `low` p50 −7.18, drop windows p50 −0.67 dB —
give **+6.51 dB**, a 2.2× margin. Keep it: if the window math ever points the wrong
way this goes negative and nothing else would catch it.

**G7 exists because G6 alone let a random-number generator through** (EREV1 F3).
This spec's own indictment of v1 is "a gate that passes identically whether the
measurement is broken or healthy is not testing anything" — and as first drafted,
G6 read only cached dB levels and never touched `within_track`, any term, or any
normaliser. The reviewer tested it the direct way: replace all four terms with
`random.random()` and run the pinned gates over the real corpus.

```
RANDOM four-term composite:
  G2 worst term railed  0.0000  (<= 0.20)  PASS
  G3 worst term rho     0.0415  (<= 0.60)  PASS
  G4 composite IQR      0.2115  (>= 0.10)  PASS
  G5 rankability        1.0000  (>= 0.90)  PASS
  G6 level separation   +6.52 dB (>= 3.0)  PASS   <- identical to the real value
```

A pure RNG was ACCEPTED by every E3 gate. E2 already had a grade-space separation
gate and is not foolable this way (a random E2 `within_track` collapses its
separation to ~0 against a 0.25 floor); E3 had none. **G7 closes it**: score the
*identical four-term formula* on the `low` (breakdown) windows — the body term's
rank basis is perfectly well defined for a breakdown window — and require drops to
out-grade them **in grade space**:

```
v2 composite, drop windows  : n=3323  p25 0.6046  p50 0.6787  p75 0.7493
v2 composite, 'low' windows : n= 955  p25 0.3832  p50 0.4849  p75 0.5743
GRADE-SPACE SEPARATION      = +0.1938        (a random composite gives ~0.000)
```

Independently measured by the author and by EREV1 (+0.1938 / +0.1936). Floor set
at **half the measured value = 0.10**, the same convention this spec uses for
`SEPARATION_GATE = 0.25` from a measured 0.501. No new audio, no new cached
feature, no labels.

New verdict, precedence corpus floor → coverage → term saturation → term
correlation → composite IQR → rankability → level separation → grade separation:

```python
def gates_verdict(n_by_genre_eligible: int, n_graded: int,
                  term_railed_max: "Optional[float]",
                  term_rho_max: "Optional[float]",
                  iqr: "Optional[float]",
                  rankable_fraction: "Optional[float]",
                  level_separation_db: "Optional[float]",
                  grade_separation: "Optional[float]") -> "tuple[bool, str]":
```

reasons: `"insufficient_corpus"`, `"insufficient_coverage"`,
`"saturated_term"`, `"redundant_terms"`, `"degenerate_distribution"`,
`"unrankable_grades"`, `"inverted_level_separation"`,
`"inverted_or_flat_grade_separation"`, `"ok"`. Every `None` fails closed.

**Regression test this, do not just implement it** (Task 9): a synthetic
all-random four-term composite must be **REJECTED** by `gates_verdict` on G7. That
test is the one that proves the E3 gate set is no longer noise-passable.

**5i. Measured shape of the v2 composite, for the report and for expectations.**
p05 0.492, p25 0.604, p50 0.679, p75 0.749, p95 0.840; IQR **0.1448** (2.3× today's
0.0625); **0.00% railed**; rankability 1.000 with **zero** all-tied tracks (today:
2). `rho(v2 composite, today's onset-only proxy) = +0.421` — this is a genuinely
different, multi-dimensional measurement, not a repackaging of the old one.
State honestly in the report that the composite still clusters toward the middle
(p05–p95 spans 1.7× versus today's 1.24×): that is the arithmetic of averaging
four independent terms, and what improves is resolution and ordering, not spread.

**5j. Rewrite the module docstring** (EREV1 F4). `drop_energy_v0.py:15-20` says
"Three gain-invariant terms per drop window" and lists `body` (as a dB span),
`sub_duty` and `onset_ratio`. Every clause of that is false after this task.
Rewrite the header to describe the four required terms, the rank-based body with
its two bases and the three properties from 5c (raw-marker population, two-drop
granularity, tie handling), the four-terms-or-omit law from 5f, and the corrected
invariance wording from Task 10c.

---

### Task 6 - `state_manager.py`: the ONE authorized wiring delta

At the existing E3 call site (`:346-355`), inside the block that already extracts
`tw` from the memoized store, also extract the corpus fallback distribution from
the **same already-loaded store object** and pass it through:

```python
data.drop_grades = drop_energy_v0.grade_drops(
    v4, drop_beats=data.drop_beat_indices, track_weight=tw,
    corpus_drop_levels=(store or {}).get("drop_body_distribution")) or None
```

**No second store path, no second read, no new memo** — `_track_weight_store_once`
(`:247-252`) stays the only route to the store file, per the standing law
(`docs/agents/change_contracts.yml:775`). Nothing else in this file changes: not
the flags, not the thread, not the status blocks, not the `try/except` shape, not
the existing `[E3]` log line. Do not add a status key for `body_basis`.

---

### Task 7 - `tools/drop_energy_report.py`: the new gate inputs

Compute and print, over the by_genre eligible set: each term's railed fraction
(and their maximum), the full 4×4 term correlation matrix using the existing
`spearman` helper (and its worst off-diagonal absolute value), the composite IQR,
the rankability fraction (denominator: tracks with ≥3 graded drops), the G6 level
separation in dB, and the **G7 grade-space separation**. Also print the **count and
percentage of drops graded on the `"corpus"` body basis** — that number is how you
would notice the fallback firing more than the measured 2.18%.

**G7 computation.** Score the identical four-term composite on the first 16 beats
of every `low`-labelled section, reusing `section_energy_v0._normalized_segments`
for the segment list and `drop_energy_v0`'s own term math for the scoring — do
**not** write a second copy of the formula in the tool. Rank each `low` window's
body term against **the same track's own drop-window levels** (that is what makes
it commensurable with the drop grades). Print both medians, not just the
difference, following the E3 spec's own N1 precedent:

```
  G7 grade separation  median(drop composite) - median('low' composite) = %.4f  (gate >= 0.10)
     median(drop) = %.4f ; median('low') = %.4f ; n_low = %d
```

**Two informational correlation lines** (EREV1 F2) — the product law is the one
thing this spec declines to change, and as first drafted nothing in Part D ever
measured it:

```
  rho(library_scaled, track_weight) = %+.4f   (INFORMATIONAL; v1 +0.9803, v2 expected ~+0.884)
  rho(library_scaled, within_track ) = %+.4f   (INFORMATIONAL; v1 +0.1713, v2 expected ~+0.510)
```

They gate nothing. They exist so that if a future change quietly returns
`library_scaled` to being pure track weight, somebody sees it.

Feed the gate quantities to the new `gates_verdict`. Keep G1, the MUST-print
absolute-coverage line, the attach-match-rate line, and the `--limit ⇒
partial_run` forced failure exactly as they are.

---

### Task 8 - `tools/energy_perturbation_check.py` (new): the Sturm invariance test (G-c)

Today's three "gain invariance" tests add a float offset to **already-rounded
cached values, never re-round, and have no floor**
(`tests/test_track_weight_v0.py:77-84` and its two siblings). They prove the
modules' algebra cancels a synthetic offset; they cannot detect what the pipeline
actually does. This tool applies Sturm's horse method (*ACM Computers in
Entertainment* 14(2), 2016): apply a transformation irrelevant to the construct
and check the output does not move.

Offline, read-only, ~10 tracks, one audio pass. Behaviour:

1. Enumerate BY GENRE tracks the same way the other three report tools do
   (`tools/section_energy_report.py:49-72`), sort by `content_id`, and take every
   `len(tracks)//10`-th track — **deterministic selection, no RNG**, so reruns are
   comparable.
2. For each track, exactly this call sequence — the extractor loads with
   `librosa.load(path, sr=22050, mono=True)` (`audio_spectral_features.py:269`),
   so match that on the way in and the resample becomes a no-op instead of a
   second variable:

   ```python
   y, sr = librosa.load(src_path, sr=22050, mono=True)      # same load the extractor does
   y_shift = y * (10.0 ** (DELTA_DB / 20.0))                # DELTA_DB = -6.0206
   sf.write(tmp_wav, y_shift, 22050, subtype="FLOAT")       # float32: no re-quantization
   shifted = extract_spectral_features_v4(str(tmp_wav), beatgrid_times_ms)
   ```

   `tmp_wav` lives inside a **`tempfile.TemporaryDirectory()`** — never next to
   the source, never in the music library. The beatgrid passed in is the **same**
   list used for the cached original, so the per-beat spans are identical and the
   only difference between the two runs is level.

   **`DELTA_DB` must stay negative** (attenuation) and the write must stay
   float: a positive gain could clip the waveform and an integer subtype would
   re-quantize it, and either would confound the test with a second
   transformation. `extract_spectral_features_v4` holds `_V4_EXTRACT_LOCK`
   (`:268`) and does one extraction at a time — keep the tool single-threaded.
3. Compute E1 components, E2 section grades and E3 drop grades from both the
   cached original and the freshly extracted shifted version, and report the max
   absolute delta per layer.

**Two hard safety rules, both of which would corrupt the library if broken:**

- **NEVER call `spectral_cache.put_cached_v4`** on the shifted extraction, and
  never write anything under `spectral_cache._cache_dir()`. A gain-shifted entry
  written into the real cache would silently poison every future run of every
  energy layer. Call the extractor directly; do not route through any cache
  put/get-or-compute helper.
- **Never write to, move, or re-encode any file under the Rekordbox library
  path.** The only writes this tool performs are inside the temporary directory
  and the optional `--out` report file.

Report-only thresholds, stated as expectations rather than a CI gate, because
this needs an audio pass and optional deps:

- Expected: max delta ≈ 0.005 grade units, from the 0.1 dB quantization measured
  in A.4 item 3.
- **Hard failure (exit 1): any grade moves by more than 0.10.** That is 20× the
  expected quantization drift and would mean a genuine invariance break.
- Print, per track, whether its `full_db` touches the −100.0 dB floor. Measured,
  18.9% of BY GENRE tracks do, and those are the ones where invariance genuinely
  fails rather than merely rounds.

Missing optional deps (librosa / numpy / soundfile) ⇒ exit 2 with a clear
`ENV ERROR:` line, matching `tools/section_energy_report.py:90-97`.

---

### Task 9 - Tests

Extend the three existing test modules; do not rewrite them and do not weaken any
existing assertion. Every algorithm below must be testable through a **pure
function seam** — no files, no subprocess, no Rekordbox DB, no cache.

**`tests/test_track_weight_v0.py`**
- `components()` returns the new `brightness_med` key and no `sub_duty`.
- `components()` returns `None` when `brightness_med` is absent / non-numeric /
  non-finite (refusal discipline, one case each).
- `robust_dynamic_range()`: a known series gives the exact p95−p25; `None` on
  short / absent / non-finite input.
- `acceptance_verdict()` precedence table, exercising **every** branch in order:
  `insufficient_corpus`, `loudness_proxy`, `compression_proxy`,
  `redundant_components`, `degenerate_component`, `ok` — including
  `rho_drama=None` and `rho_components_max=None` failing closed.
- **N5:** a one-line test asserting `track_weight_v0.STORE_SCHEMA_VERSION ==
  section_energy_v0.STORE_SCHEMA_VERSION`, so the two declarations cannot skew.
- Keep the existing gain-invariance test **and add a rounding-aware sibling**
  that rounds the shifted series to 1 dp before recomputing, asserting the
  component deltas stay within 0.01 (the honest tolerance from A.4 item 3) rather
  than `places=9`. Leave the exact-arithmetic test in place; add, don't replace.
- The zero-runtime-importer fence test is unchanged and must still pass.

**`tests/test_section_energy_v0.py`**
- The new span maps −12 dB → 0.0, −6 dB → 0.5, 0 dB → 1.0, and clips outside.
- **The median aggregator (Task 3d):** a section whose beats are
  `[-3, -3, -3, -100]` grades from the median (−3 dB → 1.0), not from the mean
  (−27.25 dB → 0.0). This is the single assertion that encodes E2-b.
- `load_track_weight_store` refuses a `schema_version: 1` store (so
  `library_scaled` is `None`) and still refuses `accepted: false`, malformed, and
  missing — and, per N6, a refused store must still yield **v2 `within_track`
  grades**, never an empty list.
- `gates_verdict()` precedence table, every branch including each `None`.
- The import fence (`ALLOW = ("state_manager.py",)`) is unchanged.

**`tests/test_drop_energy_v0.py`**
- `drop_body_levels()` window convention: coverage ≥ 8 kept, < 8 omitted, `[]` on
  absent / non-finite input.
- Body basis: ≥2 own drops ⇒ `"track_drops"`; 1 own drop with
  `corpus_drop_levels` ⇒ `"corpus"`; 1 own drop with none ⇒ **drop omitted**.
- **The four-term law**: for each of the four normalisers, a case where it is
  absent / ≤ 0 / non-finite omits the drop entirely, and no returned
  `within_track` is ever a mean over fewer than four terms.
- Body-basis documentation cases: a 2-drop track's body term takes only
  `{0.25, 0.75}`; two drops at an identical level both receive 0.5 (mid-rank ties).
- A saturation regression test: on a synthetic track whose drops differ only in
  `perc_high`, the grades must still differ — this is the assertion that would
  have failed on v1 and is the reason this revision exists.
- **The noise regression test (EREV1 F3):** a synthetic all-random four-term
  composite must be **REJECTED** by `gates_verdict`, and the rejection reason must
  be `inverted_or_flat_grade_separation` — i.e. G7, not something else. This is
  the test that proves the E3 gate set is no longer noise-passable; without it,
  G7 could be implemented wrongly and nothing would say so.
- `gates_verdict()` precedence table, every branch including each `None`.
- The import fence is unchanged.

**New: `tests/test_energy_perturbation_check.py`** — unit-test only the pure
comparison seam of Task 8 (given two grade lists, produce the max deltas and the
pass/fail verdict). Do **not** decode audio, extract features, or touch the cache
in a unit test.

---

### Task 10 - Contract, docs, and the record

**10a. Contract-first** (`docs/agents/change_contracts.yml`, contract key
`spectral_analysis`). `code_globs` already lists all six energy files
(`:713-718`); add `tools/energy_perturbation_check.py`. Add to `key_symbols`:
`robust_dynamic_range`, `drop_body_levels`. Replace the three energy entries in
`forbidden_assumptions` (`:770-777`) with v2 text stating: the v2 component set
(`body_duty`, `brightness_med`, `onset_mh_mean`, `growl_flatness_mean`); the
**three** E1 acceptance controls (loudness |rho| ≤ 0.50, dynamic-range |rho| ≤
0.55, worst component-pair |rho| ≤ 0.60); store `schema_version: 2` with
`drop_body_distribution`, which makes a v1 store refuse to **library-scale** (not
refuse to grade); E2's span `-12..0` with the **median** aggregator and the
saturation / rankability / separation gates; E3's four required terms with the
rank-based body ranked against the **raw ANLZ marker set**, its `body_basis`
field, and its **seven** gates including the grade-space separation gate that
makes the set non-noise-passable; that all four E3 terms are required so no grade
is ever a re-weighted mean; and that the flags, threads, fences, status surfaces
and flag-off byte-identity kill tests are **unchanged**.

`docs_update` for this contract is `docs/research/spectral_audio_analysis_redesign.md`
and `AGENTS.md` — update both: the AGENTS.md source-map rows for
`section_energy_v0.py` / `drop_energy_v0.py` / `track_weight_v0.py` and their
tools still describe the v1 formulations.

**10b. Registration is ALREADY DONE — verify, do not duplicate.** The spec author
registered this file as the **AWR-291** row in `docs/status/active_work_registry.md`
(status `SPEC DRAFT-FOR-REVIEW`, §10-allowed language) and re-ran all four hard
checks green at HEAD `0a40b7b9`. Your job is to **update that row's status** when
the work lands — implemented / software-tested, with the real measured gate values
— exactly as the AWR-286/288/290 rows record theirs. Do not add a second row and
do not also classify it in `docs/architecture/doc_index.md`: `check_agent_contracts.py`
accepts either location and it is already satisfied by the registry entry.

**10c. Correct the overclaiming docstrings** (A.4 item 3). In
`track_weight_v0.py:16-21`, `section_energy_v0.py:24-25` and
`drop_energy_v0.py:22-23`, replace "cancels EXACTLY" / "Exactly gain-invariant"
with the measured truth:

> Gain-invariant by construction in exact arithmetic. In the shipped pipeline the
> cancellation is exact to about ±0.005 grade units, because every stored dB value
> is rounded to 0.1 dB (`audio_spectral_features.py:307-311`); and it does not hold
> at all on beats pinned at the fixed −100.0 dB power floor (`:35`, `:313-314`),
> which occurs on ~19% of BY GENRE tracks. Verified by re-extraction at two gains,
> not by adding an offset to cached values (`tools/energy_perturbation_check.py`).

**10d. Write the change record into this spec file** under a `## Change record`
heading, carrying the three record-keeping items verbatim from A.4: the
unexamined compression confound, the unrecorded §B.2 narrowing, and the
docstring overclaims.

**10e. Record the deferred follow-up.** E2-b (section **median** instead of mean,
plus EBU Tech 3342-style silence gating before the p95 reference is formed) is
**DEFERRED by exec adjudication**, on the ENERGYRES recommendation to land the
span fix first. Record it in the change record with its trigger, measured now so
the trigger is checkable:

> **E2-b trigger** — authorize E2-b as its own spec if, after AWR-291 lands,
> either (i) the boundary-jitter diagnostic (Task 4b) shows a median
> `|Δwithin_track| > 0.10` at ±4 beats, or (ii) the fraction of `chorus` sections
> graded at the bottom rail exceeds 2% of all chorus sections. Baseline for (ii)
> under the new span: among the 24.6% of chorus sections that are ≥64 beats, the
> mean aggregator grades 6.7% at the bottom rail, which is ~1.6% of all chorus
> sections — under the trigger, but only just. Evidence that E2-b works when
> needed: switching that aggregator to the section p75 drops the long-section
> false-zero rate from 13.3% to 0.1%.

**10f. Regeneration is the implementation's final step, not this spec's.** After
all gates pass, rebuild in dependency order — E1 store (v2) → E2 report → E3
report — and then regenerate the operator trust dossier from the v2 numbers. The
v1 dossier at `local/spectral_v5_2026_07_17/trust_dossier_2026_07_24.md` describes
grades that will no longer exist; do not leave it presented as current.

---

## Part C - Invariants That MUST Still Hold (live safety)

1. **The push loop gains no work of any kind.** `_TICK_INTERVAL = 1.0/200`
   (`state_manager.py`); all energy compute and the single store read stay on the
   ANLZ worker thread. The new in-module `perc_high` p90 is one `sorted()` per
   track on that worker — it must never be reachable from the tick path.
2. **Flag-off is byte-identical.** With `RBSS_SECTION_ENERGY` and
   `RBSS_DROP_ENERGY` unset: no computation, no ANLZ_DATA payload key, no status
   key, every `DropDecision.energy_grade` `None`. The four-surface kill test is
   preserved unchanged.
3. **There is still no consumer.** No LED, laser, SoundSwitch, Govee or
   presentation module may read any grade. The import fences
   (`tests/test_section_energy_v0.py:326`, `tests/test_drop_energy_v0.py:297`,
   and E1's zero-runtime-importer test) stay exactly as they are and must still
   pass. `track_weight_v0.py` gains no runtime importer — in particular it must
   not import `drop_energy_v0`.
4. **One store path only.** `_track_weight_store_once` +
   `section_energy_v0.load_track_weight_store` remain the sole route to the store
   file. Task 6 reads a key off the already-loaded object; it does not open a file.
5. **Refusal beats fabrication, everywhere.** Absent / short / malformed /
   non-finite ⇒ absent grade. No default 0.5, no re-weighted mean, no
   success-shaped fallback. A v1 store must be refused, not migrated in place.
6. **True-drop law unchanged.** The worker grades raw ANLZ-marker windows as
   attach material only; every surfaced grade comes from plan-attached true-drop
   decisions. No surface enumerates the raw set. `body_basis` is not surfaced.
7. **Read-only offline tools.** The report tools never write outside
   `<cache_dir>/trackweight_v1/` and their optional `--out`. The perturbation tool
   writes only inside a temporary directory. Nothing touches the Rekordbox DB,
   ANLZ files, or audio files except to read them. The store is machine-local and
   never committed.
8. **No re-extraction of the library.** Every input is already in the v4 cache.
   The v4 schema does not change.
9. **BY GENRE law.** Every gate, statistic and validation claim uses BY GENRE
   playlist tracks only, excluding `RAP`.
10. **A failed gate is a valid result.** Report it, exit non-zero, escalate as a
    spec amendment. Never move a threshold to pass.

---

## Part D - Tests & acceptance gates

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_ui_jargon.py
python3 tools/check_docs_staleness.py --report
```

Then, in dependency order (each must be ACCEPTED before the next is meaningful):

```bash
python3 tools/track_weight_report.py    --out local/spectral_v5_2026_07_17/track_weight_report_v2.txt
python3 tools/section_energy_report.py  --out local/spectral_v5_2026_07_17/section_energy_report_v2.txt
python3 tools/drop_energy_report.py     --out local/spectral_v5_2026_07_17/drop_energy_report_v2.txt
python3 tools/energy_perturbation_check.py --out local/spectral_v5_2026_07_17/energy_perturbation_v2.txt
```

**Expected values on the current library** (measured by ENERGYRES; report the
real ones, never adjust anything to reach these):

| layer | gate | floor | expected |
|---|---|---|---|
| E1 | loudness \|rho\| | ≤ 0.50 | ~0.04 |
| E1 | dynamic-range \|rho\| | ≤ 0.55 | ~0.48 |
| E2 | coverage | ≥ 0.95 | 1.000 |
| E2 | railed fraction | ≤ 0.20 | ~0.053 |
| E2 | rankability | ≥ 0.90 | ~1.000 |
| E2 | separation | ≥ 0.25 | ~0.50 |
| E3 | worst term railed | ≤ 0.20 | ~0.062 |
| E3 | worst term pair \|rho\| | ≤ 0.60 | ~0.25 |
| E3 | composite IQR | ≥ 0.10 | ~0.145 |
| E3 | rankability | ≥ 0.90 | 1.000 |
| E3 | level separation | ≥ 3.0 dB | ~6.5 dB |

The E1 dynamic-range gate is the tightest (~0.48 against 0.55). **If it fails,
that is a real result, not a tuning opportunity** — it means one swapped component
was not enough and the next candidate is `body_duty` itself, which is banked and
explicitly NOT authorized here.

---

## Part E - Acceptance (definition of done)

- [ ] E1 components are `body_duty`, `brightness_med`, `onset_mh_mean`,
      `growl_flatness_mean`; `sub_duty` and `REL_SUB_OFFSET_DB` are gone from
      `track_weight_v0.py`; refusal on a missing `brightness_med` is tested.
- [ ] `robust_dynamic_range` exists, is pure, uses p95−p25, and is tested against
      the cached `drama` scalar's silence exposure.
- [ ] `acceptance_verdict` has the `compression_proxy` branch in the pinned
      precedence order, with `None` failing closed, and every branch is tested.
- [ ] Store writes `schema_version: 2` with `drop_body_distribution`;
      `section_energy_v0` refuses v1 stores; a test proves the refusal.
- [ ] E2 span is `SECTION_SPAN_LOW_DB = -12.0` / `SECTION_SPAN_HIGH_DB = 0.0`,
      renamed with the comment explaining why they are no longer the tier
      constants.
- [ ] E2's spread gate is replaced by saturation / rankability / separation, all
      three computed and printed by the report, every branch tested.
- [ ] E2 report prints the boundary-jitter diagnostic at ±1/±2/±4 beats, clearly
      marked INFORMATIONAL and gating nothing.
- [ ] E3 has exactly four terms; `sub_duty` and the level `body` span constants
      are gone; `fluxsum_midhigh` was **not** added.
- [ ] E3's body term is the rank among the track's own drops, with the corpus
      fallback, with `body_basis` recorded on every grade, and a drop is omitted
      when neither basis is available.
- [ ] All four E3 terms are required: a missing normaliser omits the drop, and a
      test proves no `within_track` is ever a mean over fewer than four terms.
- [ ] `drop_body_levels` is the single implementation of the window convention;
      `tools/track_weight_report.py` imports it; `track_weight_v0.py` does not.
- [ ] E3's six gates are implemented, printed, tested branch by branch, and the
      report prints the `"corpus"`-basis drop count.
- [ ] `state_manager.py` changed in exactly one place: the `corpus_drop_levels`
      keyword at the existing E3 call site. No flag, thread, status key, or log
      line moved. `git diff --stat state_manager.py` shows a single hunk.
- [ ] `tools/energy_perturbation_check.py` exists, selects ~10 tracks
      deterministically, extracts into a temp dir, **never** calls
      `put_cached_v4` or writes under the cache dir, and reports per-layer deltas
      plus floor-touching tracks.
- [ ] Flag-off byte-identity re-verified for both flags (all four surfaces).
- [ ] All three import fences still pass; `track_weight_v0.py` still has zero
      runtime importers.
- [ ] The three gain-invariance docstrings are corrected to the measured truth.
- [ ] Contract updated (`code_globs`, `key_symbols`, all three
      `forbidden_assumptions` entries) and its `docs_update` docs updated:
      `docs/research/spectral_audio_analysis_redesign.md` and `AGENTS.md`.
- [ ] Spec registered in `docs/status/active_work_registry.md` and classified in
      `docs/architecture/doc_index.md`; §10 status language only.
- [ ] Change record written into this spec: compression confound, §B.2 narrowing,
      docstring overclaims, and the deferred E2-b with its measurable trigger.
- [ ] All five repo checks green and `python3 -m unittest discover tests` green.
- [ ] All three reports rerun in dependency order and ACCEPTED — or a failure
      reported plainly, with **no constant moved**.
- [ ] Trust dossier regenerated from the v2 numbers as the final step; the v1
      dossier is no longer presented as current.

---

## When You Finish

Report: every changed file; the exact tests and checks run with their output; the
four report tools' verdicts with their measured gate values side by side with the
floors; and the one-hunk `state_manager.py` diff for review.

**Plain-language operator summary** (write it in Brandon's terms, no jargon):

- **What changes in the room:** nothing yet. All three layers are still
  status-only with no consumer, and both flags are still off by default. This
  changes what the numbers *mean*, not what the lights do.
- **What was actually wrong:** the section grade had turned into a near-yes/no
  (two thirds of sections read exactly 0 or exactly 1), the drop grade had
  quietly become a single measurement instead of three, and the track weight was
  reading how squashed a master is more than how hard the music hits.
- **What is different now:** section grades spread out instead of pinning at the
  rails; drop grades are built from four things that actually vary — where the
  drop sits among that track's own drops, how busy the top end is, how percussive
  it is, and how gritty it is; and the track weight now has a check that catches
  the squashed-master problem.
- **What to watch:** the numbers will all move. A track that was 0.9 may now be
  0.6 — that is the scale spreading out, not the track changing. The old trust
  dossier is stale and gets regenerated.
- **Unverified:** nothing here proves the new numbers match your ear. Software
  measurements only, no hardware, no listening. That check only happens when you
  play the music.
- **Rollback:** both flags are still default-off, so the bridge is unaffected
  either way. To roll back, revert the commits and rerun
  `tools/track_weight_report.py` to rewrite a v1 store.

---

### Claim ledger

**[confirmed]** — every code citation re-read at HEAD `0a40b7b9` on 2026-07-24;
every corpus number measured over the 551 BY GENRE tracks / 6,837 sections /
3,335 drops in ENERGYRES, whose counts reproduce the three accepted reports
exactly.

**[assumed-reasonable]** — the five new thresholds `DRAMA_ACCEPT_MAX = 0.55`,
`SATURATION_GATE_MAX = 0.20`, `RANKABILITY_GATE = 0.90`, `SEPARATION_GATE = 0.25`,
`TERM_CORRELATION_MAX = 0.60`, and the raised `IQR_GATE = 0.10` and new
`LEVEL_SEPARATION_DB = 3.0`. Each is pinned from a measured value with stated
headroom, in the same spirit as the existing `SPEARMAN_ACCEPT_MAX = 0.50`. The
author saw both today's and the candidate's numbers before pinning them — that is
disclosed here rather than hidden, and it is exactly why they are frozen at
implementation time.

**[assumed]** — that `brightness_med` is a musically better fourth component than
`sub_duty`. What is *measured* is that it is far less redundant (0.242 vs 0.578)
and much less compression-coupled (−0.480 vs −0.675); what is *assumed*, on the
Gingras et al. 2014 result, is that spectral brightness tracks perceived energy.

**[unknown]** — whether any of the v2 numbers matches Brandon's ear. Nothing in
this spec tests that and nothing offline can, under the standing no-labeling law.
The first real test is the operator's veto after E4 exists.

**Adversarial self-review — how this spec could still break, and what stops it:**

1. *The rank-based body term makes every track's best drop a 1.0, implying a
   ferocity it may not have.* Real cost, deliberately accepted: rank normalisation
   destroys magnitude (Hicks & Irizarry's critique of quantile normalisation is
   the general form). It is contained because `library_scaled = within_track ×
   track_weight` restores absolute standing, and because G6 asserts direction of
   truth in dB where ranks cannot hide an inversion. **Recorded as a known cost,
   not solved.**
2. *A mixed-basis composite.* If some drops ranked against their own track and
   others against the corpus without anyone knowing, grades would silently mean
   different things. Prevented by `body_basis` on every grade plus the report's
   corpus-basis count.
3. *A silent re-weight sneaking back.* The old code dropped a term when a
   normaliser was unusable. Prevented by the four-terms-or-omit law (5f) and the
   test that asserts no mean is ever over fewer than four terms.
4. *A poisoned cache from the perturbation tool.* A gain-shifted entry written
   into the real v4 cache would corrupt every future energy run and would be very
   hard to notice. Prevented by the explicit ban on `put_cached_v4` and on any
   write under the cache dir, plus temp-dir-only output.
5. *Gate laundering.* The most likely human failure is nudging 0.55 or 0.10 when
   a run comes back red. Prevented by stating the no-tuning law three times, by
   disclosing that the floors were set with knowledge of the measurements, and by
   naming the correct escalation (a spec amendment, with `body_duty` as the banked
   next candidate).
6. *Scope creep into `state_manager.py`.* The E3 change genuinely needs one new
   argument, and it would be easy to "improve" the surrounding block. Prevented by
   the single-hunk `git diff --stat` acceptance item.
