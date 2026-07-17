---
doc_status: current
truth_level: dispatch brief for the LASERHUNT Fable seat (program AWR-195 laser path)
last_verified_commit: a379740b
last_verified_date: 2026-07-16
validation_scope: >
  Offline read-only analysis brief. Everything it produces is propose-only
  evidence; no runtime, laser, LED, or config behavior may change.
---

# LASERHUNT — laser-warranting drop span hunt (Fable seat, tmux `laserhunt`)

Target: Claude Fable 5, effort high.

> This is benign local software work for Brandon's DJ lighting bridge and agent
> workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery,
> biology, chemistry, life-sciences, model-distillation, or hidden-reasoning
> extraction task. "Laser" throughout means cheap DJ lighting fixtures. Review
> only normal software correctness and offline audio-feature analysis inside the
> named scope.

## Mission

Sweep Brandon's analyzed library for TRUE drops whose drop section carries an
accented sustained texture that warrants lasers: **bass growls** and/or **synth
sustains** running **4–16 beats** from the drop (operator correction 2026-07-16:
beats, NOT bars). These are the drops where the sustained texture
makes the hit feel harder — the laser lives on that texture. Operator's words:
"drops that have an accented musical characteristic that warrants lasers."

Output feeds the post-pilot laser path (sustain+growl span protocols). The
morning review seat presents your results to Brandon in chat — you never message
him and never point him at files.

## Operator ground truth (calibration examples — these gate the sweep)

1. **Chemicals (Feat. Nat Slater) (Extended)** [ItsMurph] — synth sustain at one
   of the LATER true drops. Pack true drops: 1:42 / 2:25 / 3:53. Your detector
   must find which later drop(s) carry it.
2. **Cash Out (Odd Mob Extended Remix)** — synthy bass-growl sustain **≈8 beats**
   at the 2nd true drop (2:23) — squarely inside the operator's 4–16-beat
   window.
3. **I Cannot (Extended Mix)** [Anti Up] — tech-house bass growl AND synth
   sustain in the SAME drop sections, at true drop 1 AND true drop 2.
   **CRITICAL:** operator ear-truth (pilot, frozen) = true drops at **1:19.4 and
   3:00.4**. The evidence pack also lists 0:28 as TRUE — that marker is
   operator-rejected (bassline only, a known runway-rule false positive). Use
   1:19 + 3:00 for this track.

All three tracks are confirmed present in the evidence pack with those drop
timestamps (verified at dispatch).

## Evidence packet

- `local/spectral_night_2026_07_16/evidence_pack.jsonl` — 735 tracks /
  1,665 TRUE drops (runway rule). Per record: `drops[]` = true drops with
  `beat`, `mmss`, `bpm`, `group`, spectral summary fields.
- `local/spectral_night_2026_07_16/laser_spans.json` — overnight whole-track
  span mining: 3,426 spans, kinds `growl` / `synth_sustain`, MIN 16 beats,
  gap-tolerant (≤2-beat dropouts), fields `beat_a/beat_b/beats/duty/conf`.
- `local/laser_drop_spans_2026_07_16/laser_spans.py` — the miner that produced
  it (copied from the night seat; `evidence_pack.py` beside it). Reference
  method: `spectral_profile.sustained_synth_flags` / `growl_flags` over the
  strict v4 cache, via pyrekordbox on a **scratch DB copy**. It is NOT
  drop-anchored and misses <16-beat spans by construction (Cash Out's 8-beat
  growl is absent from laser_spans.json — expected).
- `local/laser_drop_spans_2026_07_16/master_copy.db` — scratch copy of the
  rekordbox DB (copied at dispatch, stable path). NEVER read or write the live
  rekordbox master.db.
- Coverage honesty: the pack covers only tracks with cached v4 spectral data.
  Report what the sweep could NOT cover (no cache / no drop markers) — never
  silently.

## Task shape (yours to refine)

1. Adapt the miner into a **drop-anchored detector**: for each TRUE drop, find
   growl and synth-sustain spans starting at/within ~4 beats after the drop
   beat, gap-tolerant like the reference. Primary window: **4–16 beats**.
   Spans that keep running past 16 beats go in a secondary "long sustain" list
   (pad-like; the whole-track miner already covers those) — never mixed into
   the primary ranking.
2. **Calibrate first:** all three examples must produce the operator-described
   detections (right drop, right kind(s), plausible length). If any example
   fails, STOP and diagnose (file resolution, cache gaps, thresholds) — report
   the failure rather than sweeping with a detector that misses known ground
   truth. Threshold tuning to pass calibration is expected; invent nothing.
3. Sweep every TRUE drop in the pack (for I Cannot, substitute the ear-truth
   drops). Rank by **accent salience** — how much the texture stands out against
   that track's own norm — not by length alone. Buckets: BOTH growl+synth
   (I-Cannot-like, highest interest), growl-only, synth-only.
4. Deliverables, all under `local/laser_drop_spans_2026_07_16/` (gitignored;
   track titles never leave `local/`):
   - `candidates.jsonl` — every hit, machine-readable, with measurements
   - `candidates_top.md` — calibration proof at the top (the three examples with
     measured spans), then top ~40 ranked candidates per bucket
   - `SEAT_NOTES.md` — method, thresholds, coverage gaps, honest self-review

## Boundaries (verbatim, non-negotiable)

- Read-only analysis. New files ONLY under `local/laser_drop_spans_2026_07_16/`
  and your session scratchpad. No repo code edits, no runtime / bridge / laser /
  LED / config changes, no bridge restart, no commits.
- Never touch the pad/lab/sim services, never Accept lab drafts.
- If you fan out, subagents are cheaper-tier only (Opus or below) — you are the
  only Fable-tier agent.
- Use the same cache/module path the reference scripts use; add no new
  dependencies.

## Claim discipline

Label load-bearing claims confirmed / assumed / unknown. Detector thresholds are
assumed until calibration passes. The three examples are the only ground truth —
everything else in your output is candidate, not fact.

## Success criteria (falsifiable)

1. All 3 calibration examples detected as the operator described, or a STOP
   report explaining precisely why not.
2. Sweep covers every TRUE drop in the pack, or lists exclusions with reasons.
3. `candidates_top.md` exists with calibration proof and ranked buckets.
4. `git status` shows no repo diffs outside `local/` before you signal.

## Completion signal (mandatory, machine channel)

When fully done run exactly:
`touch /tmp/rbss_lane_signals/laserhunt.SPANHUNT.done`
If blocked instead run:
`echo "<one-line reason>" > /tmp/rbss_lane_signals/laserhunt.SPANHUNT.blocked`
Also print `LASERHUNT-DONE` (or `LASERHUNT-BLOCKED`) on its own line. Run
straight through; never idle at checkpoints.
