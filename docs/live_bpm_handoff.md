# Live BPM Memory Handoff

Date: 2026-05-04
Repo: `bbuuuiiii04/PYTHON-BRIDGE`, package `rb_ss_bridge_v2`
Scope: read-only Rekordbox memory investigation. No bridge runtime behavior has been changed.

## End Goal

Provide SoundSwitch autoloop with Rekordbox's actual live/displayed per-deck BPM before arm, including pitched BPM while paused or immediately on play. The bridge must not rely on stale library BPM, delayed ENGINE STATE, or hardcoded memory addresses.

Target future integration shape:

1. Discover live BPM candidates dynamically per Rekordbox process/session.
2. Validate candidates by watching them move with the correct deck's pitch.
3. Cache only validated candidates keyed by Rekordbox pid/base/deck.
4. Let bridge code use the cached live BPM only behind an explicit opt-in flag.
5. Keep scripted-track behavior and existing timing behavior unchanged unless separately approved.

## Current Code Changes

`probe_live_bpm.py` now has read-only investigation commands:

- `snapshot`: scans anchor windows and optional bounded rw regions for BPM/factor-shaped floats.
- `watch`: samples explicit addresses over time.
- `compare`: compares saved snapshot outputs.
- `validate`: scans, optionally includes manual seed addresses, watches candidates during pitch movement, classifies behavior, and caches only passing candidates.
- `cache-check`: reads current-session cached candidates and checks whether they still match current expected BPM.

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

- verdict classification (`pass`, `stale`, `moved_wrong_value`, etc.)
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

## Important Caveats

- Absolute addresses are never reusable across sessions.
- Deck 2 is validated by scan/watch/cache behavior, not by a stable structural anchor.
- Deck 1 is not solved.
- Deck 1 looked promising in early sessions (`secondary1 + 0x1cb8`, once `secondary1 + 0x1ac8`), but later sessions rejected those offsets.
- Equal-BPM and near-equal-BPM Deck A/Deck B states are required validation cases, not optional edge cases. In real DJ use the decks are often beatmatched, and the only clear ownership window may be brief while the incoming deck is being pitched into match.
- Bridge integration must not proceed as a default behavior yet.
- Any prototype should be opt-in and should fail closed if validation/cache is absent.

## Why Deck 1 Is Behind

Deck 2 was the original failure path and produced clearer live candidates. Deck 1 initially appeared simpler, but later restarts proved its candidate offsets drift or disappear. Deck 1 needs the same scan/watch/cache workflow before any bridge logic can treat both decks as solved.

## Next Session Plan

1. Do Deck 1 parity validation before bridge integration; today's Session 7 attempt did not solve Deck 1.
2. Start from a known Deck A BPM from TimecodeLink.
3. Prefer starting from a state where Deck A and Deck B are deliberately different, then repeat after beatmatching them.
4. Run a Deck 1 scanner validation:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm <deck_a_bpm> --bpm-min <min> --bpm-max <max> --include-rw-regions --watch-limit 20 --duration 8 --hz 4 --max-hits-per-region 12
```

5. If scanner-selected candidates include plausible Deck A fields, run seeded validation with a controlled Deck A pitch move:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm validate --deck 1 --expect-bpm <before> --expected-after <after> --addr 0xADDR1 --addr 0xADDR2 --watch-limit 8 --duration 30 --hz 5 --tolerance 0.35
```

6. Verify:

```bash
python3 -m rb_ss_bridge_v2.probe_live_bpm cache-check --deck 1 --expect-bpm <after>
```

7. Deck separation test:
   - keep cached Deck 1 candidates;
   - move only Deck B;
   - confirm Deck 1 cached values do not follow Deck B.

8. Beatmatched ownership test:
   - set Deck A and Deck B to the same or near-same displayed BPM;
   - move only one deck by a small amount;
   - confirm the candidate follows only the deck being moved.

9. Only after Deck 1 passes, design an opt-in bridge prototype.

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

## Commands Used For Verification

```bash
python3 -m unittest discover -s tests
python3 -m py_compile rb_ss_bridge_v2/probe_live_bpm.py rb_ss_bridge_v2/tests/test_probe_live_bpm.py
git -C rb_ss_bridge_v2 diff --check -- probe_live_bpm.py docs/live_bpm_findings.md tests/test_probe_live_bpm.py
```

## Current Implementation Boundary

Do not edit `RBMemoryReader`, `StateManager`, or autoloop behavior yet unless the user explicitly authorizes bridge integration. The current deliverable is a read-only probe plus documented evidence.
