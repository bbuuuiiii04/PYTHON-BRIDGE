# Smart Drop Phase 2 Handoff

Status: HISTORICAL

Last updated: 2026-05-08

## Current Checkpoint

- Branch: `main`
- Latest pushed commit: `f09ea92 Implement smart drop phase 1`
- Phase 2 is implemented locally but not yet committed.
- Current local verification:
  - `python3 -m pytest` -> `320 passed`
  - `python3 -m py_compile __main__.py models.py state_manager.py runtime_status.py scripts/bridge_menubar.py anlz_reader.py` -> passed
  - `git diff --check` -> passed

## What Phase 1 Implemented

Smart Drop is now separated into raw source data and runtime-selected data:

- `TrackMetadata.anlz_drops`: exact raw ANLZ/parser drop markers.
- `TrackMetadata.smart_drops`: filtered drops Smart Drop is allowed to act on.
- `_select_smart_drops(raw_drops, total_beats=...)`:
  - sorts and dedupes
  - filters drops before beat `32`
  - filters drops in the final `32` beats only when beatgrid length is known
  - does not cluster
  - does not apply cooldown
  - does not apply energy/timing shifts
- `_smart_drop_tick()` now loops over `d.meta.smart_drops`, not raw
  `d.meta.anlz_drops`.
- `ANLZ_DATA` logs raw vs selected once:
  - `[SM] smart-drop-select  deck=...  raw=[...]  selected=[...]`

Phase 1 also removed active Phrase Realign UI/command/status behavior, added a
runtime Smart Drop menu toggle, and marked the old Smart Drop/Phrase Anchor
implementation prompt as historical.

## Live Validation Evidence

User live-tested with:

```text
Mochakk, Joni - Da Fonk (feat. Joni) (Original Mix).flac
BPM: 127.0
```

Observed log:

```text
[SM] smart-drop-toggle  enabled=True
[SM] smart-drop-select  deck=1
  raw=[64, 192, 256, 352, 384, 416, 448, 576, 608, 640, 672, 704]
  selected=[64, 192, 256, 352, 384, 416, 448, 576, 608, 640, 672, 704]
[SM] smart-drop-cut  deck=1  beat=60  drop_at=64
[SM] smart-drop-rearm  deck=1  beat=64
[SM] autoloop-rearm  deck=1  reason=smart-drop  beat=64
  elapsed=0:30.238  target_elapsed=0:30.236  late=2ms  grid=grid
```

User reported: "feels good".

Interpretation:

- ANLZ parsing worked.
- Phase 1 selected drops matched raw drops for this track.
- Smart Drop cut fired exactly four beats before the first selected drop.
- Smart Drop rearm fired on beat `64`.
- Target elapsed was within `2ms`, which is strong timing.

## What Phase 2 Implemented

Phase 2 adds energy shadow logging only.

Do not change runtime Smart Drop timing yet. Runtime must continue to cut/rearm
at `smart_drops`. Energy should only answer:

```text
For each selected ANLZ drop, which nearby beat would energy suggest?
How much stronger is that suggestion than the ANLZ beat?
```

Implementation:

- Added a shadow result model:

```python
@dataclass
class SmartDropEnergyShadow:
    anlz_beat: int
    suggested_beat: int
    anlz_elapsed_ms: int
    suggested_elapsed_ms: int
    lift_at_anlz: float
    lift_at_suggested: float
    confidence: float
```

- Stored shadow rows on `TrackMetadata`:

```python
smart_drop_energy_shadow: list[SmartDropEnergyShadow]
```

- Added `anlz_reader.py` helpers that reuse existing waveform and beatgrid
  extraction:

```python
read_smart_drop_energy_shadow(
    anlz_path: str,
    selected_drops: list[int],
) -> list[SmartDropEnergyShadow]
```

Runtime integration:

- The ANLZ worker remains the only parser call site.
- The worker computes shadow rows for raw ANLZ drops during the same parse that
  produces `TrackAnlzData.drop_beat_indices`, because it runs before
  `StateManager` applies selected-drop filtering.
- The worker stores elapsed milliseconds on each shadow row because
  `StateManager` may receive `ANLZ_DATA` before `FILEPATH_RESOLVED` has
  populated `TrackMetadata.beatgrid_times_ms`.
- `StateManager` must filter shadow rows down to accepted `smart_drops` before
  storing or logging them.
- Stale `load_gen` events must not mutate raw drops, selected drops, or shadow
  rows.
- `_smart_drop_tick()` must continue to use `TrackMetadata.smart_drops` only.

Energy behavior now implemented:

- If waveform or full beatgrid is unavailable, return `[]`.
- For each selected ANLZ drop, scan beats from `anlz_beat` through
  `anlz_beat + 8`.
- For each candidate beat:
  - `before = average energy over previous 16 beats`
  - `after = average energy over next 16 beats`
  - `lift = after - before`
- Choose the candidate with the highest lift.
- `confidence = lift_at_suggested - lift_at_anlz`.
- Do not move `smart_drops`.

Log shape:

```text
[SM] smart-drop-energy-shadow  deck=1
  anlz_elapsed=0:30.236  suggested_elapsed=0:34.016
  lift_anlz=0.12  lift_suggested=0.41  confidence=0.29
```

One line per selected drop is acceptable for Phase 2 because validation needs
clear evidence. The runtime still stores beat indices internally, but the
operator-facing shadow log reports elapsed timestamps. If logs become too noisy,
compact later.

## Constraints And Non-Goals

- Do not let energy change the runtime target in Phase 2.
- Do not read ANLZ files from the `StateManager` event loop.
- Do not cluster drops.
- Do not add cooldown.
- Do not search earlier than the ANLZ beat unless the user explicitly revisits
  that design.
- Do not estimate outro filtering from BPM/track length.
- Keep logs sparse and explainable.

## Tests Added

- Pure energy-shadow tests with synthetic waveform/beatgrid:
  - strongest lift at ANLZ beat -> `suggested_beat == anlz_beat`
  - strongest lift at `anlz_beat + 8` -> suggested beat shifts in shadow only
  - missing waveform or insufficient beatgrid -> empty shadow result
- StateManager integration tests:
  - accepted `ANLZ_DATA` stores raw drops, selected drops, and shadow results
    after selected-drop filtering
  - runtime still uses `smart_drops`, not `suggested_beat`
  - stale `ANLZ_DATA` does not mutate shadow results
- Regression:
  - `python3 -m pytest` -> `320 passed`
  - `python3 -m py_compile __main__.py models.py state_manager.py runtime_status.py scripts/bridge_menubar.py anlz_reader.py` -> passed
  - `git diff --check` -> passed

## Useful Files

- `state_manager.py`
  - `Ev.ANLZ_DATA` handling
  - `_select_smart_drops()`
  - `_smart_drop_tick()`
- `models.py`
  - `TrackMetadata`
- `anlz_reader.py`
  - waveform extraction and `_detect_drop_beats()`
- `tests/test_smart_drop.py`
  - Phase 1 selector/runtime tests
- `docs/bridge_design.md`
  - current authoritative runtime behavior
