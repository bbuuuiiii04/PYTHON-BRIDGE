---
doc_status: current
truth_level: manager-state-brief
last_verified_commit: 8a90796
last_verified_date: 2026-07-09
validation_scope: >
  Specbank-lane manager state brief (Fable/HIGH, tmux specbank). Phase 1 (paper:
  AWR-176/177/178 authored) closed at 02fe439. Phase 2 = the AWR-176 build round,
  executive-dispatched to this seat. Updated as things land; successor seats boot
  from here. Retire when the round closes.
---

# Specbank manager state — 2026-07-09 (AWR-176 build round)

## Executive directive (afternoon, verbatim anchors)
- AWR-176 spec APPROVED; implementation dispatched to THIS seat.
- Founding acceptance case added by the executive to spec Part E (staged edit,
  in the index at dispatch time): **Sexy (Extended Mix) 3:38** — operator
  live-labeled the exact blindness mid-mix; every current v4 signal flat across
  all 8 of that track's drops (growl_band mean ~27.0, bass/sub sustain 1.00,
  executive-measured). The centroid-movement measure must separate 3:38's
  post-drop window from the other seven. Post-sweep check, not the
  implementer's.
- Extraction lands TONIGHT; backfill sweep runs AFTER 20:00 (CPU-only, no live
  contact, never against his mixing) — **stage the command in the close-out
  report, do not run it.**
- Laser-gate-on-growl consumer NOT in scope; founding label recorded; consumer
  designs post-P1-data.
- Suite: named five-red repo-root baseline PLUS
  `test_laser_color_engine.LaserColorStateManagerHoldTests` has 5 known ERRORs
  at HEAD being fixed by the filter lane (`b1f360c` is theirs) — reconcile by
  name AROUND them.
- My completion signal: `/tmp/rbss_lane_signals/specbank.P1BUILD.done`.

## Round state
- [x] Spec re-read incl. the staged Sexy amendment; target files verified
  UNCHANGED d93f047 → 8a90796 (spec cites hold at HEAD).
- [x] Implementer dispatched: lane `p1impl`, Opus 4.8 / effort high (pin
  verified on-screen), TAG `P1IMPL`, brief
  `docs/prompts/active/p1impl_dispatch_2026_07_09.md` (fence, live-safety,
  acceptance names, four harness clauses). First dispatch attempt
  MODEL-PIN-FAILED on boot-race; re-dispatch clean; paste chip clear; lane
  confirmed working.
- [x] Watcher armed: signal-file only, 90 min deadline, one watcher.
- [ ] Implementer round completes (or blocks).
- [ ] Manager adversarial review AT THIS DESK: diff-stat vs fence per commit;
  re-run new tests + the four scoped neighbor modules; re-derive 2-3 spec
  cites at HEAD; hunt: dataclass-default ordering, tolerant-read vs
  length-check ordering in `_features_v4_from_payload`, sweep skip condition
  inversion, any touch of existing calibration keys / V4_*_KEYS /
  compat block, tests touching the REAL cache dir, unspecced fold-ins.
- [ ] Full suite repo-root at MY desk, reconciled by name (five baseline +
  laser-5-in-flux + flappers isolated-if-red).
- [ ] Three hard checks at my desk.
- [ ] Close-out report to executive (superman3 gates) + staged sweep command
  + signal P1BUILD.

## Named baseline (repo root, from the resume doc + executive addendum)
`test_drop_slot_color_smoke_and_snap` (error); both
`test_export_pack_parity_self_heal` fails;
`test_ddj_slots_8_16_17_24_exact_ch1_ch19`;
`test_autoloop_capture_rows_identify_passes_and_blockers`; PLUS in-flux:
5 ERRORs `test_laser_color_engine.LaserColorStateManagerHoldTests` (filter
lane's to fix). Flappers (isolate, never chase):
`test_fallback_second_rename_failure_restores_old_pack`, the two
`test_soundswitch_pack` byte-identity race tests.

## Staged sweep command (for the close-out; run after 20:00, never against a mix)
`caffeinate -i python3 tools/spectral_sweep.py --jobs 2`
(from `/Users/bbui`, i.e. the repo's parent dir — the tool inserts parents[2]
on sys.path; disk floor trivially met, 32 GiB free at 15:45). Acceptance: final
counts show the cached library re-extracted; immediate re-run reports ≈ all
`cached`; record cache MB delta vs the +40-55 MB estimate. Then the Part E
named-track checks (Sexy 3:38 separation; capochino 1:01.7; Girl$
1:16.1/2:25.6 vs App-E negatives).

## Phase 1 record (closed)
AWR-176/177/178 artifacts authored + registry/doc-index rows at `02fe439`;
AWR-175 ceded to the F3 lane (their claim landed as `eb9eadf`).
