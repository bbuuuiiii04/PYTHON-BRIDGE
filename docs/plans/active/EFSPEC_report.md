---
doc_status: current
truth_level: seat report (verification trail; not design authority)
last_verified_commit: e76cbbf0
last_verified_date: 2026-07-24
validation_scope: >
  EFSPEC seat report (exec4 dispatch 2026-07-24): what was verified at HEAD
  while authoring energy_fabric_ladder_spec_v1.md and
  amendment2_append_draft.md. Read-only trail; authorizes nothing.
---

# EFSPEC report — energy-fabric ladder spec authoring (2026-07-24)

## Delivered

1. `docs/plans/active/energy_fabric_ladder_spec_v1.md` — the 3-layer energy
   fabric design spec (Part A-E), status planned / draft-for-review.
2. `docs/plans/active/amendment2_append_draft.md` — AMENDMENT-2 append draft
   (transcription vision, verbatim, A1-format), NOT landed; exec lands it.
3. This report.

## Verified at HEAD e76cbbf0 (clean tree, 2026-07-24)

- Feature store: `audio_spectral_features.py:24-25` (v3/v4 schema);
  `spectral_cache.py:3-5` per-version namespaces, `:222` cache-dir env.
- Derived measures: `spectral_profile.py` — `bass_duty:98`,
  `identity_axes:118`, `pre_drop_gap_beats:183`, `section_map:531`,
  `drop_window_vector:619`. `energy_model.py:1-28` pure offline utilities.
  `hardness_v0.py` offline shadow, zero runtime importers (header).
- Sections: `smart_phrasing.py:23` PhraseLabel {up, chorus, low, other};
  `:20` runway labels; `:714` `runway_beats` (AWR-257 moved it here —
  `drop_presentation.py:33-36` imports).
- Drops: `drop_presentation.py:192` DropDecision (NO energy field today),
  `:225/:247/:356` TrackPlan/plan_track/resolve_presentation;
  `state_manager.py:2855/2860/3034` runway consumers; `:499` 200 Hz tick.
- Cue selection today is CYCLED: `led_look_director.py:89-101` seeded RNG
  bags/cursors per (role, backend); roles at `:179-233, 278-279, 299`.
- F4 = seasoning only: `led_dispatch_policy.py:162, 1171-1215`.
- stage2/v12 store is research-local:
  `local/spectral_v5_2026_07_17/stage2_pilot.py:39-45, 94-95, 601`.
- Contract keys exist for the staged work: `led_govee:101`,
  `drop_presentation:430`, `spectral_analysis:698`, `config_schema:670`,
  `tests:785` in `docs/agents/change_contracts.yml`.
- Amendment-log format taken from the live
  `docs/architecture/spectral_program_design_authority_amendments.md` (A1
  entry + append-only rules); base-doc §0 heading confirmed as the amended
  clause target.

## Load-bearing findings

- **`pre_drop_gap_beats` is an orphan**: no callers outside
  `tests/test_spectral_profile.py`; its docstring's "consumer" is
  aspirational. Breath-hold (spec §B.5) wires this existing detector — no new
  detection is proposed. Laser's `pre_drop_blackout_beats: 4`
  (`laser_config.py:73`) is fixed-length, laser-only, untouched.
- **No library-relative track weight exists anywhere** — layer 1 is genuinely
  new (offline tool + sidecar), everything else grades existing material.
- **Stale memory corrected**: `user_true_drop_definition` cited
  `drop_presentation.py:173` for `runway_beats`; it moved to
  `smart_phrasing.py:714` (AWR-257). Memory updated this session.

## Open questions (labeled)

- [unknown] Look-metadata schema fit for cast coordinates (E4 spec must read
  `led_config.py` + Template Lab metadata first; `config_schema` contract may
  need extending).
- [unknown] End-to-end LED latency for tight breath-hold release at high BPM —
  measure before promising sub-beat precision.
- [assumed] Duty/relative/rank measures give a gain-invariant `track_weight`;
  E1's loudness-correlation report is the designed test of this assumption.
- [exec decision] E4 (casting) vs E5 (breath-hold) ordering; both need E1-E3.
- [exec landing step] land AMENDMENT-2 per the draft's instructions.

## Write-scope deviation (flagged)

The charter scoped writes to new files under `docs/plans/active/`, but
`tools/check_agent_contracts.py` (a CI hard check) fails on any unclassified
active doc. To avoid pushing a red check (auto-sync commits at turn end), I
appended ONE registry row — AWR-285 in `docs/status/active_work_registry.md`
— classifying all three files. No other existing file was touched. All four
hard checks green after: `check_docs_metadata`, `check_agent_contracts`,
`check_docs_drift`, `check_ui_jargon` (13 files OK).
