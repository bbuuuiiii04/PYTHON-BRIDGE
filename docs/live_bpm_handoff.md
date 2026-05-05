# Live BPM Memory Handoff

Date: 2026-05-04
Repo: `bbuuuiiii04/PYTHON-BRIDGE`, package `rb_ss_bridge_v2`
Scope: historical handoff plus final integration state. Runtime bridge behavior
now includes LiveBPMService, default-on live BPM follow, and default-on
phrase-window master-transition autoloop arms.

## End Goal

Provide SoundSwitch autoloop with Rekordbox's actual live/displayed per-deck BPM
before arm, including pitched BPM while paused or immediately on play. The
bridge must not rely on stale library BPM, delayed ENGINE STATE, or hardcoded
memory addresses.

Final integration shape:

1. Discover live BPM candidates dynamically per Rekordbox process/session.
2. Validate candidates by watching them move with the correct deck's pitch.
3. Store only current-session validated candidates keyed by Rekordbox
   pid/base/deck.
4. Use validated live BPM for autoloop arm snapshots by default, with
   `RBSS_LIVE_BPM_DISABLE=1` as the emergency kill switch.
5. Enable active-loop live BPM follow by default, with
   `RBSS_LIVE_BPM_FOLLOW=0` as the kill switch.
6. Pair active-loop BPM sends with a one-shot `change=True` beat re-lock.
7. Keep master-transition autoloop arms phrase-window aware by default, with
   `RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` as the kill switch.

## Current Code Changes

Runtime integration:

- `live_bpm.py`: `LiveBPMService` read-only background service.
- `state_manager.py`: arm-time live BPM snapshot, default live-follow, and
  default master-transition phrase-window arms.
- `models.py`: autoloop/live-follow state in `OutputState`.
- `__main__.py`: starts/stops `LiveBPMService`; color-codes live BPM/autoloop
  diagnostics.
- `tests/test_live_bpm_service.py`: unit tests for candidate validation,
  fallback, arm snapshot, V2 pending/apply, and cancellation.

Current active-follow behavior:

```text
RBSS_LIVE_BPM_FOLLOW=0 disables active follow
```

- Detect live BPM divergence during active autoloop.
- Send BPM to decks 1, 2, 3, 4 with rate limiting.
- Set a one-shot autoloop beat `change=True` re-lock after apply.
- SoundSwitch reacts to BPM sends, so the re-lock keeps the active autoloop
  anchored after the timing update.

Observed acceptance:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
[SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ... pending_bpm=none
```

Standalone probe tooling remains available for investigation:

`probe_live_bpm.py` now has read-only investigation commands:

- `snapshot`: scans anchor windows and optional bounded rw regions for BPM/factor-shaped floats.
- `watch`: samples explicit addresses over time.
- `compare`: compares saved snapshot outputs.
- `validate`: scans, optionally includes manual seed addresses, watches candidates during pitch movement, classifies behavior, and caches only passing candidates.
- `cache-check`: reads current-session cached candidates and checks whether they still match current expected BPM.
- `cache-monitor`: watches current-session cached candidates without scanning or writing cache.

Recent read-only probe additions:

- `validate` now distinguishes `zero_start_churn` and `zero_end_decay` from generic movement.
- `validate` reports per-candidate discontinuity counts.
- `validate --save-traces` writes full timestamp/value traces to `~/.cache/rb_ss_bridge_v2/live_bpm_traces_<timestamp>.json`.
- `validate --monitor-cache-deck <deck>` monitors current-session cached candidates from another deck during the same watch window.
- `validate --monitor-addr 0xADDR` adds manual read-only monitor seeds.

Cache path:

```bash
~/.cache/rb_ss_bridge_v2/live_bpm_candidates.json
```

Cache entries are keyed by:

- Rekordbox pid
- Rekordbox base address
- deck number

This prevents old absolute addresses from being reused after restart.

Tests added:

```bash
python3 -m unittest discover -s tests
```

Coverage is intentionally pure/unit-level only:

- verdict classification (`pass`, `stale`, `moved_wrong_value`, `zero_start_churn`, `zero_end_decay`, etc.)
- trace metadata
- render/UI-cache ranking penalty
- current-session cache filtering by pid/base/deck

The tests do not attach to Rekordbox and do not prove any address live.

## Key Evidence

Full details are in `docs/live_bpm_findings.md`.

Deck 2 is strongly validated:

- Multiple restarts found live/displayed BPM float32 fields.
- Fields update immediately with pitch changes while paused.
- Exact BPM duplicates often exist; stale duplicates can only be rejected by behavior.
- Session 5 validated cache promotion in one process.
- Session 6 validated restart cache invalidation, rediscovery, and cache promotion again.

Session 5 cache proof:

- Old Rekordbox pid/base: `28908` / `0x104084000`
- Deck B live candidates passed and cached:
  - `0x12dba36ec`
  - `0x12ddac77c`
  - `0x12851064c`
  - `0x12d928388`
- Stale duplicate rejected:
  - `0x12dba36f0`
- `cache-check --deck 2 --expect-bpm 140.82` matched all four cached candidates.

Session 6 restart proof:

- New Rekordbox pid/base: `50777` / `0x104330000`
- Pre-rediscovery `cache-check --deck 2` returned zero current-session candidates, proving old cache entries did not apply after restart.
- Fresh Deck B candidates moved from `130.0` to `133.899994`:
  - `0x12ff45e98`
  - `0x12ce8782c`
  - `0x128fec9fc`
- Same-value stale duplicates stayed fixed:
  - `0x10f115cc8`
  - `0x12ce5f5ec`
  - `0x128feca00`
  - `0x1285b6cb0`
  - `0x1285b6cac`
- Final cache validation passed and cached:
  - `0x12ff45e98`
  - `0x12ce8782c`
  - `0x128fec9fc`
  - `0x12ff473e0`
- `cache-check --deck 2 --expect-bpm 133.9` matched all four cached candidates.

Session 7 Deck 1 parity attempt:

- Same Rekordbox pid/base: `50777` / `0x104330000`
- Deck A and Deck B were both at TimecodeLink `BPM=133.9` for the main validation windows.
- Initial Deck 1 scan from expected `130.0` watched 20 candidates and found only `stale`; TimecodeLink showed the Deck A move happened after that window, so it is not strong negative evidence by itself.
- Beatmatched Deck 1 scan from expected `133.9` found four SQLite-region `moved_unverified` fields, but they started at `0.0` and ended at unrelated values.
- Seeded follow-up rejected those SQLite fields because they decayed to `0.0`.
- Current-session Deck 2 cached candidates stayed fixed at `133.899994`.
- `cache-check --deck 1 --expect-bpm 133.9` returned zero current-session candidates.
- Status: Deck 1 is still unsolved; no Deck 1 candidate was cached.

Post-Session 7 tooling update:

- The probe can now label the Session 7 SQLite-style false positives as zero-start or zero-end churn instead of plain `moved_unverified`.
- The probe can save full validation traces for offline review.
- The probe can monitor another deck's cached candidates during target-deck validation.
- The probe can run `cache-monitor` for stability-only separation checks.
- This is tooling only. It does not add Deck 1 evidence and does not change bridge runtime behavior.

Session 8 Deck 1 current-session proof:

- Same Rekordbox pid/base: `50777` / `0x104330000`
- Deck A: `Rude Boy (Cazes Edit)`, moved `127.0 -> 129.8`.
- Deck B: `We Could Be Love (Odd Mob Extended Remix)`, stayed `133.9` during the Deck A move, later moved `133.9 -> 129.8` for separation.
- Seeded Deck 1 validation passed and cached:
  - `0x10f115cc8`: `127.000000 -> 129.800003`, nearest `secondary1 +0x2028`
  - `0x10f117210`: `126.984123 -> 129.783783`, nearest `secondary1 +0x3570`
- Deck 2 monitor candidates stayed stable during the Deck A move:
  - `0x12ff45e98`
  - `0x12ff473e0`
  - `0x12ce8782c`
  - `0x128fec9fc`
- `cache-check --deck 1 --expect-bpm 129.8` matched both Deck 1 candidates.
- `cache-monitor --deck 1 --expect-bpm 129.8` showed both Deck 1 candidates stayed stable while only Deck B moved to `129.8`.
- Trace files:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T215241Z.json`
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T215411Z.json`
- Status: Deck 1 has strong current-session scan/watch/cache plus deck-separation evidence, but still needs restart rediscovery proof.

Session 9 Deck 1 restart rediscovery proof:

- Rekordbox restarted from pid/base `50777` / `0x104330000` to `56549` / `0x104598000`.
- Pre-rediscovery `cache-check --deck 1` and `cache-check --deck 2` both returned zero current-session candidates, proving old absolute cache entries did not apply.
- Deck A and Deck B started beatmatched at TimecodeLink `BPM=132.0`.
- Deck A was moved to `128.0` while Deck B stayed at `132.0`.
- Fresh Deck 1 validation passed and cached four candidates:
  - `0x146ef5378`: `132.000000 -> 128.000000`, nearest `secondary1 +0x1998`
  - `0x146eedb6c`: `132.000000 -> 128.000000`, nearest `container -0x4a04`
  - `0x146ef68c0`: `132.013199 -> 128.012802`, nearest `secondary1 +0x2ee0`
  - `0x146ef6a50`: `132.013199 -> 128.012802`, nearest `secondary1 +0x3070`
- `cache-check --deck 1 --expect-bpm 128.0` matched all four current-session candidates.
- `cache-monitor --deck 1 --expect-bpm 128.0` showed all four Deck 1 candidates stayed stable while only Deck B moved from `132.0` to `128.0`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T220150Z.json`
- Status: Deck 1 now has restart invalidation, rediscovery, recache, cache-check, and deck-separation evidence. Absolute addresses remain session-local.

Session 10 Deck 1 restart rediscovery proof:

- Rekordbox restarted from pid/base `56549` / `0x104598000` to `57703` / `0x102630000`.
- Pre-rediscovery `cache-check --deck 1` and `cache-check --deck 2` both returned zero current-session candidates.
- Deck A and Deck B started beatmatched at TimecodeLink `BPM=132.0`.
- Deck A was moved to `128.0` while Deck B stayed at `132.0`.
- Fresh Deck 1 validation passed and cached five candidates:
  - `0x11932c928`: `132.000000 -> 128.000000`, nearest `secondary1 +0x1f18`
  - `0x14520a91c`: `132.000000 -> 128.000000`, nearest `secondary1 +0x2bedff0c`
  - `0x1452f62cc`: `132.000000 -> 128.000000`, nearest `secondary1 +0x2bfcb8bc`
  - `0x11932de70`: `131.940628 -> 127.942429`, nearest `secondary1 +0x3460`
  - `0x11932e000`: `131.940628 -> 127.942429`, nearest `secondary1 +0x35f0`
- `cache-check --deck 1 --expect-bpm 128.0` matched all five current-session candidates.
- `cache-monitor --deck 1 --expect-bpm 128.0` showed all five stayed stable while only Deck B moved from `132.0` to `128.0`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T220826Z.json`
- Status: Deck 1 rediscovered successfully again with a new pid/base and new address set.

Session 11 Deck 1 restart rediscovery proof:

- Rekordbox restarted from pid/base `57703` / `0x102630000` to `58398` / `0x102084000`.
- Pre-rediscovery `cache-check --deck 1` and `cache-check --deck 2` both returned zero current-session candidates.
- Deck A and Deck B started beatmatched at TimecodeLink `BPM=128.0`.
- Deck A was moved upward to `132.0` while Deck B stayed at `128.0`.
- Fresh Deck 1 validation passed and cached two candidates:
  - `0x14874d818`: `128.000000 -> 132.000000`, nearest `secondary1 +0x1dc8`
  - `0x11c15c20c`: `128.000000 -> 132.000000`, nearest `base +0x1a0d820c`
- `cache-check --deck 1 --expect-bpm 132.0` matched both current-session candidates.
- `cache-monitor --deck 1 --expect-bpm 132.0` showed both stayed stable while only Deck B moved from `128.0` to `132.0`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T221247Z.json`
- Status: Deck 1 rediscovered successfully in the opposite pitch direction with a new pid/base and new address set.

Session 12 Deck 2 incoming-track rediscovery proof:

- Rekordbox restarted from pid/base `58398` / `0x102084000` to `59202` / `0x104014000`.
- Pre-rediscovery `cache-check --deck 1` and `cache-check --deck 2` both returned zero current-session candidates.
- Deck A loaded at TimecodeLink `BPM=132.0`: `Blow Your Brain Cell (Extended`.
- Deck B loaded at TimecodeLink `BPM=130.0`: `Function  (Extended Mix)`.
- Deck B was moved to `132.0` while Deck A stayed at `132.0`.
- Fresh Deck 2 validation passed and cached five candidates:
  - `0x131d8f30c`: `130.000000 -> 132.000000`, nearest `secondary1 +0x22e753cc`
  - `0x135a5dc3c`: `130.000000 -> 132.000000`, nearest `secondary1 +0x26b43cfc`
  - `0x135dfc4ec`: `130.000000 -> 132.000000`, nearest `secondary1 +0x26ee25ac`
  - `0x127114de8`: `130.000000 -> 132.000000`, nearest `secondary1 +0x181faea8`
  - `0x10ef2caa0`: `130.010834 -> 132.011002`, nearest `secondary1 +0x12b60`
- Four IOAccelerator fields were rejected as `zero_start_churn`, and 23 candidates were stale.
- `cache-check --deck 2 --expect-bpm 132.0` matched all five current-session candidates.
- `cache-monitor --deck 2 --expect-bpm 132.0` showed all five stayed stable while only Deck A moved.
- TimecodeLink confirmed Deck B stayed at `132.0` during separation while Deck A moved after the match window, observed at `129.4` and then `145.2`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T221853Z.json`
- Status: Deck 2 rediscovered successfully in a realistic incoming-track workflow where the incoming deck starts at a different BPM and is pitched into match.

Session 13 Deck 2 incoming-track attempt with no observed pitch move:

- Rekordbox restarted from pid/base `59202` / `0x104014000` to `60143` / `0x1020d0000`.
- Pre-rediscovery Deck 2 cache-check returned zero current-session candidates.
- Deck A loaded at TimecodeLink `BPM=130.0`: `Kesha - Blow (CHALANT & Donny`.
- Deck B loaded at TimecodeLink `BPM=135.0`: `Lights On (Control Room Extend`.
- Validation was run expecting Deck B to move `135.0 -> 130.0`.
- Result was `stale=32`, no passed candidates, and no cache update.
- TimecodeLink later confirmed Deck B remained at `135.0` throughout the validation window.
- Follow-up `cache-check --deck 2 --expect-bpm 130.0` returned zero current-session candidates.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222332Z.json`
- Status: inconclusive operator/window attempt, not Deck 2 negative evidence. Repeat in the same process because the Deck 2 cache is still empty.

Session 13 Deck 2 incoming-track rerun proof:

- Reran validation in the same pid/base `60143` / `0x1020d0000` after confirming the first attempt had no Deck B movement.
- Deck A stayed at TimecodeLink `BPM=130.0`.
- Deck B was moved from `135.0` to `130.0`.
- Fresh Deck 2 validation passed and cached five candidates:
  - `0x149f457f8`: `135.000000 -> 130.000000`, nearest `secondary1 +0x68d8`
  - `0x11a1087ac`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x1356a1dc`
  - `0x11a1b4a3c`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x1361646c`
  - `0x11a68e70c`: `135.000000 -> 130.000000`, nearest `container_dpu2_inner +0x13af013c`
  - `0x11a20fa10`: `134.983124 -> 129.983749`, nearest `container_dpu2_inner +0x13671440`
- Four fields were rejected as `zero_start_churn`; 23 were stale.
- `cache-check --deck 2 --expect-bpm 130.0` matched all five current-session candidates.
- `cache-monitor --deck 2 --expect-bpm 130.0` showed all five stayed stable while only Deck A moved.
- TimecodeLink confirmed Deck B stayed at `130.0` during separation while Deck A moved to `131.3` and later `140.4`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222507Z.json`
- Status: Deck 2 rediscovered successfully after restart in another incoming-track workflow, including cache-check and deck separation.

Session 14 Deck 1 incoming-track test 1 proof:

- Rekordbox restarted from pid/base `60143` / `0x1020d0000` to `61382` / `0x102a64000`.
- Pre-rediscovery Deck 1 cache-check returned zero current-session candidates.
- Deck A loaded at TimecodeLink `BPM=139.0`: `DaBaby - POP DAT THANG - SIDEQ`.
- Deck B loaded at TimecodeLink `BPM=132.0`: `Blow Your Brain Cell (Extended`.
- Deck A was moved from `139.0` to `132.0` while Deck B stayed at `132.0`.
- Fresh Deck 1 validation passed and cached ten candidates:
  - `0x1348109c8`: `139.000000 -> 132.000000`, nearest `secondary1 +0x1b88`
  - `0x1273d1d9c`: `139.000000 -> 132.000000`, nearest `secondary1 -0xd43d0a4`
  - `0x11af4b3cc`: `139.000000 -> 132.000000`, nearest `base +0x184e73cc`
  - `0x11bec742c`: `139.000000 -> 132.000000`, nearest `secondary1 -0x18947a14`
  - `0x134811f10`: `138.969315 -> 131.970856`, nearest `secondary1 +0x30d0`
  - `0x1348120a0`: `138.969315 -> 131.970856`, nearest `secondary1 +0x3260`
  - `0x13481a2c0`: `138.969315 -> 131.970856`, nearest `secondary1 +0xb480`
  - `0x13481b360`: `138.969315 -> 131.970856`, nearest `secondary1 +0xc520`
  - `0x134825f60`: `138.969315 -> 131.970856`, nearest `secondary1 +0x17120`
  - `0x13484ef80`: `138.969315 -> 131.970856`, nearest `secondary1 +0x40140`
- One IOAccelerator field was rejected as `zero_end_decay`; 21 candidates were stale.
- `cache-check --deck 1 --expect-bpm 132.0` matched all ten current-session candidates.
- `cache-monitor --deck 1 --expect-bpm 132.0` showed all ten stayed stable while only Deck B moved.
- TimecodeLink confirmed Deck A stayed at `132.0` during separation while Deck B moved to `142.6`.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T222910Z.json`
- Status: Deck 1 rediscovered successfully after restart in mirrored incoming-track workflow, including cache-check and deck separation.

Session 15 Deck 1 incoming-track test 2 partial proof:

- Rekordbox restarted from pid/base `61382` / `0x102a64000` to `61977` / `0x1005a8000`.
- Pre-rediscovery Deck 1 cache-check returned zero current-session candidates.
- Deck A loaded at TimecodeLink `BPM=130.0`: `Percolator (Cazes Edit)`.
- Deck B loaded at TimecodeLink `BPM=128.0`: `How Deep Is Your Love x Don't`.
- Deck A was moved from `130.0` to `128.0` while Deck B stayed at `128.0`.
- Fresh Deck 1 validation passed and cached eight candidates:
  - `0x12506800c`: `130.000000 -> 128.000000`, nearest `secondary1 -0xfeb9ea4`
  - `0x11afbfeec`: `130.000000 -> 128.000000`, nearest `secondary1 -0x19f61fc4`
  - `0x11ae13e0c`: `130.000000 -> 128.000000`, nearest `secondary1 -0x1a10e0a4`
  - `0x134f23408`: `130.000000 -> 128.000000`, nearest `secondary1 +0x1558`
  - `0x134f24950`: `130.010834 -> 128.010666`, nearest `secondary1 +0x2aa0`
  - `0x134f24ae0`: `130.010834 -> 128.010666`, nearest `secondary1 +0x2c30`
  - `0x134f623a0`: `130.010834 -> 128.010666`, nearest `secondary1 +0x404f0`
  - `0x134f75060`: `130.010834 -> 128.010666`, nearest `secondary1 +0x531b0`
- `cache-check --deck 1 --expect-bpm 128.0` matched all eight current-session candidates.
- Initial `cache-monitor --deck 1 --expect-bpm 128.0` showed all eight stayed stable, but TimecodeLink did not show Deck B moving during the monitor window.
- Trace file:
  - `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T223323Z.json`
- A second monitor attempt was started but interrupted before completion after the operator reported Deck B was not moved.
- A final `cache-monitor --deck 1 --expect-bpm 128.0` rerun showed all eight cached Deck 1 candidates stayed stable while only Deck B moved.
- TimecodeLink confirmed Deck A stayed at `128.0` during separation while Deck B moved to `137.0` and later `131.8`.
- Status: Deck 1 rediscovery, cache-check, and deck separation passed after rerun.

Session 16 all-inclusive DJ workflow restart proof:

- Rekordbox restarted from pid/base `61977` / `0x1005a8000` to `63036` / `0x102458000`.
- Pre-test `cache-check --deck 1` and `cache-check --deck 2` both returned zero current-session candidates.
- Baseline:
  - Deck A `Blow Your Brain Cell (Extended`, TimecodeLink `BPM=132.0`.
  - Deck B `Rude Boy (Cazes Edit)`, TimecodeLink `BPM=126.0`.
- Deck 2 incoming half:
  - Deck B moved `126.0 -> 132.0` while Deck A stayed `132.0`.
  - Deck 2 validation passed and cached eight candidates:
    - `0x1274d3c9c`: `126.000000 -> 132.000000`
    - `0x1274108ec`: `126.000000 -> 132.000000`
    - `0x1268c5aec`: `126.000000 -> 132.000000`
    - `0x13a744b08`: `126.000000 -> 132.000000`
    - `0x13a746050`: `125.984253 -> 131.983505`
    - `0x13a7461e0`: `125.984253 -> 131.983505`
    - `0x13a78ef60`: `125.984253 -> 131.983505`
    - `0x13a78f0f0`: `125.984253 -> 131.983505`
  - `cache-check --deck 2 --expect-bpm 132.0` matched all eight.
  - `cache-monitor --deck 2 --expect-bpm 132.0` showed all eight stayed stable while only Deck A moved.
  - TimecodeLink confirmed Deck B stayed `132.0` while Deck A moved to `138.6`.
  - Trace file: `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T223911Z.json`
- Deck 1 incoming half:
  - Deck A moved `138.6 -> 132.0` while Deck B stayed `132.0`.
  - Deck 1 validation passed and cached nine candidates:
    - `0x12aa2cd7c`: `138.600006 -> 132.000000`
    - `0x126ce353c`: `138.600006 -> 132.000000`
    - `0x11c0ee85c`: `138.600006 -> 132.000000`
    - `0x13a740148`: `138.599991 -> 132.000000`
    - `0x13a741690`: `138.613861 -> 132.013199`
    - `0x13a741820`: `138.613861 -> 132.013199`
    - `0x1276e0dc0`: `138.613861 -> 132.013199`
    - `0x1276e0810`: `138.613861 -> 132.013199`
    - `0x1276b3ee0`: `138.613861 -> 132.013199`
  - `cache-check --deck 1 --expect-bpm 132.0` matched all nine.
  - `cache-monitor --deck 1 --expect-bpm 132.0` showed all nine stayed stable while only Deck B moved.
  - TimecodeLink confirmed Deck A stayed `132.0` while Deck B moved to `154.7`.
  - Trace file: `/Users/bbui/.cache/rb_ss_bridge_v2/live_bpm_traces_20260504T224110Z.json`
- Status: strongest single-session DJ workflow proof so far; both decks rediscovered, cached, cache-checked, and separation-tested in one restarted process.

## Important Caveats

- Absolute addresses are never reusable across sessions.
- Deck 2 is validated by scan/watch/cache behavior, not by a stable structural anchor.
- Deck 1 now has repeated restart rediscovery evidence, but only via scan/watch/cache behavior, not a stable structural anchor.
- Deck 1 looked promising in early sessions (`secondary1 + 0x1cb8`, once `secondary1 + 0x1ac8`), but later sessions rejected those offsets.
- Session 8 found Deck 1 candidates at `secondary1 +0x2028` and `secondary1 +0x3570`; Session 9 found different Deck 1 candidates at `secondary1 +0x1998`, `container -0x4a04`, `secondary1 +0x2ee0`, and `secondary1 +0x3070`. Treat all offsets as session-local.
- Equal-BPM and near-equal-BPM Deck A/Deck B states are required validation cases, not optional edge cases. In real DJ use the decks are often beatmatched, and the only clear ownership window may be brief while the incoming deck is being pitched into match.
- Bridge integration now exists as a fail-closed default-enabled discovery path
  with `RBSS_LIVE_BPM_DISABLE=1` as the kill switch.
- Active-loop live-follow is default-on and can be disabled with
  `RBSS_LIVE_BPM_FOLLOW=0`.
- Master-transition phrase-window autoloop arms are default-on and can be
  disabled with `RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0`.
- Current policy snapshots BPM at arm time, follows validated live BPM during
  active autoloop, and pairs BPM applies/master-transition arms with one-shot
  beat re-locks.

## Why Deck 1 Is Behind

Deck 2 was the original failure path and produced clearer live candidates. Deck 1 initially appeared simpler, but later restarts proved its candidate offsets drift or disappear. Deck 1 needs the same scan/watch/cache workflow before any bridge logic can treat both decks as solved.

## Next Session Plan

1. Continue validating the integrated guarded bridge path with real DJ workflows.
2. Fail closed when no current-session cache candidate exists for pid/base/deck.
3. Keep default active-autoloop live follow fail-closed when live BPM is
   unvalidated.
4. Preserve the read-only probe as the evidence generator; do not hardcode Session 8 or Session 9 addresses/offsets.
5. Preserve `RBSS_LIVE_BPM_DISABLE=1`, `RBSS_LIVE_BPM_FOLLOW=0`, and
   `RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` kill-switch semantics.
6. For live BPM consumption, use the latest validated memory BPM at autoloop arm
   time. During active loops, apply validated live BPM with rate limiting and a
   one-shot beat re-lock.
7. Continue repeat testing with opposite pitch directions and incoming-track
   deck workflows.

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm <deck_a_bpm>
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 2 --expect-bpm <deck_b_bpm>
```

## Edge Cases To Cover

- Restart invalidates cache.
- Rediscovery works after restart.
- Deck 1-only pitch move.
- Deck 2-only pitch move.
- Both decks loaded at same BPM.
- Both decks loaded at different BPM.
- Small pitch movement.
- Large pitch movement.
- Pitch up and pitch down.
- Paused deck pitch changes.
- Playing deck pitch changes.
- Track unload/reload.
- Same deck, same BPM, different track.
- Same deck, different BPM track.
- Stale exact duplicates.
- Near-BPM stale duplicates.
- Candidates that move but land on the wrong final BPM.
- Candidates that move briefly then freeze.
- BPM changes after autoloop arm: active follow sends the validated BPM with a
  one-shot beat re-lock.

## Commands Used For Verification

```bash
python3 -m unittest discover -s tests
python3 -m py_compile rb_ss_bridge_v2/probe_live_bpm.py rb_ss_bridge_v2/tests/test_probe_live_bpm.py
git -C rb_ss_bridge_v2 diff --check -- probe_live_bpm.py docs/live_bpm_findings.md docs/live_bpm_handoff.md tests/test_probe_live_bpm.py
```

## Current Implementation Boundary

Bridge integration has been authorized and implemented. Preserve the safety
boundary: no hardcoded live BPM addresses, no cross-session absolute-address
reuse, fail closed on validation loss, and preserve `RBSS_LIVE_BPM_FOLLOW=0` as
the active-loop follow kill switch.
