---
doc_status: current
truth_level: labeled-evidence-corpus
last_verified_commit: f0b40ba
last_verified_date: 2026-07-09
validation_scope: >
  Operator ear-truth labeling corpus (AWR-182, evening labels session 2026-07-09,
  operator-attended). Each entry pairs the operator's verbatim statement about a named
  track+timestamp with what the v4 spectral analysis + F2 plan measurably see there,
  via the real seams (read_anlz_drops, spectral_cache.get_cached_v4,
  led_identity_v2.identity_scores/assign_zone, lighting_moments_v2.build_track_plan),
  measured read-only at the commit above. Classifications grade the analysis, not the
  operator: his ear is ground truth. Machine layer (same entries as JSONL):
  local/labels/operator_track_labels_2026_07_09.jsonl (gitignored). Labels here change
  no behavior; they are calibration/acceptance evidence for future rounds (P1 growl
  centroid acceptance set, F2/LED/laser/stems tuning).
---

# Operator track labels — 2026-07-09 evening session (AWR-182)

How to read an entry:
- **his words** — verbatim operator statement (ground truth).
- **measured** — what the analysis sees at that timestamp, from the real seams at the
  header commit. All dB values are the v4 corpus-absolute scale.
- **classification** — `AGREES` (analysis sees it) / `PARTIAL` / `BLIND` (analysis
  cannot express it; the missing dimension is named) / `MISREAD` (analysis contradicts
  his ear).
- **systems** — which consumers the statement bears on: `f2` (drop plan), `led`,
  `laser`, `stems` (relayed to the stems session), `p1` (growl-centroid acceptance).

P1 context tonight: `growl_centroid_frames` exists only for fresh extractions; the
library backfill sweep runs after 20:00. Growl statements tonight are measured on
amplitude (`growl_band_db` / `growl_band_frames`) and become the P1 acceptance set
once the backfill lands.

---

## Sexy (Extended Mix) — Matt Sassari (content_id 216468125)

Track dossier (measured 2026-07-09): 708 beats / 5:21, 8 drops, 5 buildups; identity
zone DEEP_POOL (aggression 0.12, luminance 0.02, distortion 0.63); F2 plan: b192 WALL
T2 blackout, b480 HOUSE T2 blackout, remaining six drops T1 snap.

### 3:38 — carried over from the 2026-07-09 live session (executive-measured; re-measured tonight as the session smoke test)

- **his words:** "aggressive tech house bass growl for 8 beats then tapering" — the
  ONLY drop of this track he hears that way (source: AWR-176 spec Part E, operator
  live-labeled 2026-07-09).
- **measured:** 3:38 → beat 479; the drop is b480 (3:38.2). `growl_band_db` next 8
  beats: 24.7, 27.4, 27.3, 27.9, 27.8, 27.8, 27.5, 27.7 — flat ≈27 dB, and flat at
  the same ≈27 dB across ALL 8 drops of the track; frame-level growl mean 26.9 dB
  (n=156 frames). Sub sustained ≈32.6 dB. F2 does rank it: HOUSE T2 (violence 0.620)
  blackout, white_share 0.25. `growl_centroid_frames` = 0 entries (pre-backfill).
- **classification:** BLIND — the growl's aggressive character and its taper are
  timbre movement (WHERE the growl tone sits over time); no stored series can express
  it. Missing dimension = frame-rate growl-band centroid, exactly AWR-176/P1. Tier
  partially compensates (T2 ranks it big) but cannot say "growl".
- **systems:** p1, led
- **notes:** This entry is the session's seam smoke test: values reproduce the
  executive's desk measurements from the AWR-176 spec (growl mean ~27.0, 8 drops,
  bass/sub sustain flat). Becomes a named P1 acceptance case after the backfill.
