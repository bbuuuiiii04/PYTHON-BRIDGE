# AWR-184 rung-0b vs stop-rung ambiguity — library existence sweep (2026-07-09 19:1x)

doc_status: current
truth_level: measured-evidence (offline sweep, real v4 cache)
scope: post-hoc evidence for ledtune's parked AWR-184 review finding; no code change.

## The parked finding (ledtune, delivered post-gate)

Rung 0b (deep sub-void blackout, AWR-184) runs BEFORE the stop check and reads no
full-band audibility. An a-cappella/vocal stop with a deep sub void + dark growl band
(vocals sit ABOVE the 60–500 Hz growl band) could resolve blackout-4 where the
calibrated stop rung gave 8. Taste-LENGTH risk only — both outcomes are blackouts.
Proposed guard (one line): compute stop first; rung 0b yields to stop.

## Sweep method (superset — decisive only in the negative direction)

`scan every beat` (not just drops) of all 716 v4 cache entries
(`~/Library/Application Support/RBSS Bridge/spectral_cache/v4/`) for runs:
`sub_db < −10` for ≥2 consecutive beats, `min(growl_band_db) < 5` over the run,
`median(full_db) ≥ loudness_ref_db − 10` over the run (the stop-audibility shape).
Empty result would have killed the finding; it did not come back empty.

## Result: the class is REAL in this library

- 716 v4 entries scanned; **55 tracks** contain ≥1 ambiguous run (any-beat superset).
- Caveat: superset — a hit only matters live if such a run ends exactly at a drop
  feeding `darkness_ladder`; per-drop confirmation is the fix round's first step.
- Top examples (track: runs, (start_beat, len, growl_min, full_med−ref)):
  DaBaby POP DAT THANG (XANDRA) ×4 e.g. (96,14,−9.6,−7.7); M.A.A.D. CITY ×3;
  Sidepiece/Disco Lines Give It To Me Good ×2 (172,3,−22.5,−9.3); Tremor ×2
  (363,15,−5.1,−9.2); Cruel Summer (Proppa) ×2 (418,51,0.3,−9.4); Radiohead
  Everything In Its Right Place (SCRIPT) ×2; No Hands (Rick Wonder) ×2;
  Levels (Paper Skies) ×2; Better Off Alone x Rather Be (SEUNG VIP) ×2.
- Utopia (Dombresky) is NOT among the hits — its voids kill the full band too
  (below ref−10), so the proposed guard does not threaten the b192/b384 operator pins.
  Verify explicitly in the fix round anyway (pin both before the guard lands).

## Disposition

Next-session first item (with ledtune's lane memory): add the one-line precedence
guard + per-drop confirmation of the 55 candidates + explicit Utopia/Killa/Caramelle
control pins. Sweep script preserved at
`tools/`-adjacent scratch (rewrite trivially: 40 lines, method above is complete).
