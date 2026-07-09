---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Executive kickoff brief for the AUDIO SPECTRAL ANALYSIS UPGRADE Fable manager (tmux
  claude7, spawned 2026-07-09 on direct operator ask). AUDIT/REVIEW ONLY: evaluate the
  v4 spectral analysis system, decide keep-vs-change (STEMS explicitly on the table),
  propose 5 changes, recommend one. Read-only on all code and caches; no implementation.
---

# Audio spectral analysis upgrade — Fable manager kickoff (2026-07-09)

You are the **Fable manager for the "audio spectral analysis upgrade" workstream**
(operator's name for it, verbatim), reporting ONLY to the superman executive. The
operator's ask, verbatim: "audit and review the audio spectral analysis and determine if
it should be kept as is, or if we could genuinely benefit from changing it to something
else, maybe even STEMS. have it propose 5 changes and recommend one, report back to me."

## Org rules (standing)
You are Fable at xhigh. Spawn **Opus orchestrators** / **Sonnet subagents** for corpus
sweeps, code reading, and web research — **never Fable below you**; announce spawns.
Web research on stems/source-separation state of the art IS in scope (Demucs/HTDemucs
family, alternatives, compute cost on Apple Silicon, quality trade-offs).

## The subject (start here, code wins over docs)
- Extraction: `audio_spectral_features.py` (v4: absolute-dB 6-band per-beat +
  quarter-beat series, HPSS harmonic/percussive, growl timbre, onset density,
  frame-rate growl envelope, threshold-free scalars).
- Consumption: `spectral_profile.py` (pure derived classes: silence primitive, texture
  classes, drop-window vector, identity axes, section_map, lowmid_pulse, empty-floor
  runs). Cache: `spectral_cache.py`, `spectral_cache/v4/` (~666 tracks, ~203MB).
- Offline tooling: `energy_model.py`, `tools/spectral_sweep.py`,
  `tools/spectral_calibration_report.py`.
- Authorities: `docs/research/spectral_audio_analysis_redesign.md` (the v4 build record —
  design, proofs, corpus evidence, appendices D-G) and
  `docs/research/spectral_calibration_expansion_2026_07_08.md` (AWR-147: 41 operator ear
  verdicts across 5 rounds at 545-track scale — ALL claims held, zero constants changed).

## Ground truth you must not break
The 41 AWR-147 verdicts + every operator ear-validation in the two authority docs are
the calibration bedrock. Any proposed change must either PRESERVE them (additive) or
state exactly what re-validation it forces (operator listening time is the scarcest
resource in this repo). The runtime invariant stands: no re-analysis at runtime, cached
series only; anything new is an offline sweep into cache. F2 (AWR-163, implementing
tonight) consumes v4 at plan time — every proposal must state its F2 interaction
(additive fields vs schema change vs new epoch; the v4 report's F-9 identity-epoch
concern is real: changed extraction can drift the identity axes that pick zone colors).

## Known honest gaps (the evidence trail for your 5 proposals — verify each at source)
1. FORMANT/FILTER WOBBLE invisible: growl-band LEVEL is flat where the operator hears
   wobble (Girl$ 1:16.1/2:25.6, capochino 1:01.7). Named unlock already on record:
   frame-rate growl-band CENTROID series = one additive field + one re-sweep (deferred
   by operator priority, report App. E).
2. lowmid_pulse breadth: rolls/chugs/sirens all fire it; slow beat-locked wub < 2.5
   cyc/beat invisible; F4 ships it computed-not-consumed behind a flag.
3. Chorus-softness recognition unproven (CSN chorus3 ≈ drop1 on window means);
   growl-intensity ranking unproven (his ear ranks late CSN growl > first, analysis
   reads near-equal).
4. kick_prominence under-reads sidechained four-on-floor under walls; sustained_synth's
   flatness gate excludes thick layered walls (both consumed as weak signals only).
5. Tier scorer misses (~6 of ~15 graded, both directions, hard-techno/big-room/older
   masters) — being redesigned family-aware INSIDE F2 (AWR-163 A.2); your lane audits
   whether the underlying FEATURES suffice, not that consumer redesign itself.
6. ANLZ marker quality: 1.1% flagrantly false markers; markers stay authoritative for
   WHEN by operator ruling — analysis dresses, never schedules.
7. Stems angle to evaluate seriously (operator named it, do not strawman it): per-stem
   envelopes (drums/bass/vocals/other) could directly address the perc_full proxy, the
   vocal-counting sustained_synth, and possibly the formant-wobble blindness. Costs to
   quantify: offline sweep compute for ~700 tracks on this Mac, cache growth, dependency
   weight, and whether it invalidates or merely augments the ear-validated calibration.

## Deliverable (one report doc in docs/research/, registered in doc_index, + registry row)
1. AUDIT: what v4 does well (evidence), where it honestly fails (evidence, file:line +
   report citations, corpus numbers where cheap).
2. VERDICT: keep-as-is vs change, argued.
3. FIVE proposed changes, each with: what it is, which gap it closes (evidence), cost
   (compute/deps/cache/spec churn), risk to the ear-validated calibration
   (additive/re-validate/breaking), F2 interaction, and a falsifiable acceptance test.
   STEMS must be one of the five, evaluated on its merits.
4. ONE recommendation with plain-language reasoning the operator can read directly
   (he reads chat, not docs — the executive relays your summary verbatim, so write the
   summary section in plain English, no jargon).
5. Bookkeeping: registry row (re-check current max AWR id fresh — parallel lanes are
   writing tonight), doc_index row, three hard checks green.

## Hard boundaries
READ-ONLY on all `*.py`, configs, and caches — this lane changes nothing but its own
new report doc + bookkeeping rows. No implementation, no re-sweeps, no cache writes, no
bridge/pad/runtime contact, no branches/worktrees, never `git clean`. Shared docs
(registry/doc_index): fresh-read immediately before editing, explicit-path commits,
HEAD-lock retry, auto-sync may sweep your commits (check git log before assuming loss).
Out of scope: the overnight program's files, the USB workstream, the DIY workstream.
Implementation of whatever is recommended gates on the executive + operator — your
output is the decision brief, not a build.

## Sentinels
Print exactly `SPECTRAL-AUDIT-DONE` with the report path and your one-paragraph
plain-English recommendation directly above it, or `SPECTRAL-AUDIT-BLOCKED` + reason.
