---
doc_status: current
truth_level: executive gate record (independent SOL 4.6 re-verification)
last_verified_commit: 00daa95
last_verified_date: 2026-07-11
validation_scope: >
  Fresh executive re-gate after SOL2 findings 2-5, the LED Pad merge fix,
  AWR-197/AWR-199, the repaired AWR-200 Stage-1 benchmark, the AWR-203/AWR-204
  offline spectral layers, and the completed USB/frozen-app packaging rounds landed
  on main. Claims below were checked against current code, focused tests, two
  full-suite working-directory conventions, and the built app.
  Evidence class remains SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Executive re-gate verdicts — 2026-07-11 (SOL 4.6 seat)

## Overall activation verdict: NO-GO

Do not start the bridge or activate staged lighting. SOL2 finding 1 is still open:
`lighting_moments_v2.py` can classify a buildup-shaped quiet section as a deep-sub
void from a single low `growl_min` sample. AWR-199 only releases darkness after at
least three returned-music beats; it does not prevent the wrong classification.
The measured threshold-tail interim guard was rejected because it changed 52 of 93
currently accepted firings. The real correction remains the Stage-2 approach-shape
and intrinsic-hardness refactor.

## Full-suite reconciliation by exact failing name

The tested code HEAD is `00daa95`; local `main` and `origin/main` were identical.

- Repo-root convention: 4,319 tests; 8 failures, 6 skipped, 1 expected failure.
  All eight are a strict subset of `/tmp/fable_discover_post_solfix.log`'s nine-red
  baseline. The old `test_tracked_config_validates` baseline red is now green.
- Parent-directory convention: 4,319 tests; 9 failures, 6 skipped, 1 expected
  failure. Its ninth failure is
  `test_loader_ships_calibrated_fixed_band_and_menu_ch9`, the known
  working-directory artifact; the file is present and that test is green from the
  repo root.
- Shared failing names: `test_absent_fixtures_fall_back_to_committed_snapshot`,
  `test_stale_venue_sha_snapshot_is_healed_at_export`,
  `test_live_config_slot_color_smoke`, two separately qualified
  `test_tracked_and_live_configs_validate` cases,
  `test_drop_slot_color_smoke_and_snap`,
  `test_ddj_slots_8_16_17_24_exact_ch1_ch19`, and
  `test_autoloop_capture_rows_identify_passes_and_blockers`.
- No USB, launcher, installer, Enttec, Rekordbox, menubar, SOL2, pad-merge, or
  spectral test entered either sequential failure set. An earlier parallel pair of
  full-suite runs made one Rekordbox cancellation test contend on its intentional
  cross-process lock; that test passed alone, and the clean sequential repo-root
  run above is the gate of record.

## Fresh round verdicts

| Round | Verdict | Fresh evidence at current main |
|---|---|---|
| SOL2 finding 2 | **PASS** | `tests.test_govee_realtime_runner` is included in the 268-test SOL2 focused gate. The healthy permitted tick clears `_idle_since`, so stale idle grace cannot survive. |
| SOL2 finding 3 | **PASS** | `tests.test_beat_sync_engine` is included in the 268-test gate. Whole-beat age survives re-anchor; reset requires continuous divergence evidence. |
| SOL2 finding 4 | **PASS** | `tests.test_led_look_director` is included in the 268-test gate. Shuffle-bag state rebuilds when candidate membership changes. |
| SOL2 finding 5 | **PASS** | `tests.test_led_look_director` + `tests.test_lighting_moments_v2_f4` are included in the 268-test gate. Preference terms narrow independently; an empty F2/F4 intersection falls back to the F2 pool. |
| SOL2 finding 1 | **OPEN / ACTIVATION BLOCKER** | Current classification still uses the unsafe one-sample deep-sub-void signal. No accepted interim guard covers it. |
| AWR-197 speed/size tripwires | **PASS** | `tests.test_led_color_engine_m2_patch_b` + `tests.test_speed_size_law`: 13/13 green. Tests/docs only; no new runtime/config mutation. |
| AWR-199 returned-music pickup abort | **PASS, limited scope** | `tests.test_lighting_moments_v2`: 63/63 green. It can only release darkness and is kill-switched, but it does not fix finding 1. |
| AWR-202 LED Pad read/modify/merge | **PASS** | `tests.test_led_pad_service`: 37/37 green. Content edits preserve live placement; explicit moves win; history restore preserves live-only blocks/looks. The current :8766 server started after the fix and therefore already serves the merged code. |
| AWR-186 cross-platform USB + Enttec | **PASS, software only** | Positive Enttec identity replaces generic FTDI/`usbserial` acceptance; pack declaration errors fail closed. Final combined launcher/packaging gate: 374 focused tests green, three hard doc checks green, shell syntax clean. |
| Frozen app / guest-Mac packaging | **PASS, software only** | The built app's 14-dependency self-check exits zero; binary is arm64; deep/strict code-sign verification passes; `LSMinimumSystemVersion=11.0`; version `0.0.1`. Real `task_for_pid`, Gatekeeper, Local Network permission, target Rekordbox build, Enttec output, and end-to-end lighting remain untested on the guest Mac. |
| AWR-200 spectral EAR benchmark | **PARTIAL, trust repairs PASS** | 32/32 direct tests green. The anti-leak boundary, amendment lineage grouping, fold invariant, marker availability, comparable denominators, duplicate IDs, and identity warnings were repaired. The current read-only run resolves 21/21 usable lineages and scores 158 markers: +/-1 family 11.4%, tier 22.8%, darkness 24.7%; +/-2 family 23.4%, tier 39.2%, darkness 51.3%. These are sensitivity measurements, not accuracy. Tier/family/darkness/growl/laser accuracy axes still lack structured per-drop operator gold and remain honestly UNAVAILABLE, so Stage 1 remains PARTIAL. |
| AWR-203 intrinsic-hardness shadow | **EXPERIMENTAL / SOFTWARE-TESTED / OFFLINE ONLY** | 28/28 direct tests green. The frozen SOL3 B/A/R/N three-path candidate and read-only ablation tool have zero runtime importers. A small descriptive run scored 36/40 tracks and 206 drops with zero identity rejects; `H >= 1.0` is only candidate path firing, not a validated tier boundary, and no T1/T2 split exists. It does not replace the live `violence`/`.tier` authority. |
| AWR-204 raw approach descriptors | **EXPERIMENTAL / SOFTWARE-TESTED / OFFLINE ONLY** | 27/27 direct tests green. The pure four-view descriptor layer reports trajectories, relative depths, void-run curves, separate landed windows, and +/-2 marker sensitivity while abstaining honestly on missing/non-finite/insufficient data. It has zero runtime importers and decides no class, threshold, or darkness length. **SOL2 finding 1 remains open:** no approach classifier, reporting tool, or live wiring exists. |

## Live config incident — approval required

The LED Pad clobbered the live config at 14:29. No restore has been performed.
The exact pre-clobber candidate is
`config/led_look_director.json.bak-20260710-142943-810747` (89 looks, all six
live blocks, SHA-256
`8aab94a1febc3b915d9cebc0b277c1d387c311ea348afb2887b01b5aefa70ecd`).
The current live file has 72 looks and only the `f2` block. Restore remains an
operator-owned write. After an approved restore, click **Discard** once in LED Pad
to rebase its stale draft before editing.

Approval phrase:

> Approve restoring `config/led_look_director.json.bak-20260710-142943-810747`
> and then rebasing the pad draft.

## Branch and runtime state

Only the `main` branch remains locally and on `origin`. The completed USB branch
was fast-forwarded and deleted after ancestry proof. The retired June 30
`GoveeBluetooth` experiment was preserved as tag
`archive-govee-bluetooth-20260630` before its local/remote branch was removed;
its canonical static-overlay runtime fix already exists on main as `087a531`.

The bridge remains OFF. Do not restart the bridge or menubar for this gate. While
OFF, SoundSwitch autorotation is not expected. The LED Pad server on :8766 is a
separate tool and does not activate the bridge.
