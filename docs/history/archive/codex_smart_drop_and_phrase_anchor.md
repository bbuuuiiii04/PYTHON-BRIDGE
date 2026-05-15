# Codex Implementation Prompt — Smart Drop + Phrase Anchor

Status: DEPRECATED

> Historical note: this was an implementation planning prompt, not the current
> bridge design. It contains superseded behavior, including Phrase Anchor
> snap-to-drop logic and earlier Smart Drop planning details. Use
> `docs/bridge_design.md` for current runtime semantics.

## Context

`rb_ss_bridge_v2` is a Rekordbox → SoundSwitch bridge that sends OS2L beat/BPM/arm
events to SoundSwitch for DMX-driven light shows. The bridge runs a 200 Hz push loop
in `StateManager._push_tick` (state_manager.py:878). For unscripted tracks it sends
an "autoloop" arm to SoundSwitch so SS can beat-sync its own loop engine.

This task adds two features to the autoloop path:

1. **Smart drop**: parse the track's ANLZ phrase analysis (`PSSI`) at load time,
   read Rekordbox drop/chorus phrase starts (`kind == 5`), convert their 1-based
   phrase beats to bridge 0-based beat indices, and 1 bar (4 beats) before each
   detected drop: cut the autoloop (filepath clear via `send_deck_clear` +
   `send_loop_off`), then rearm at the drop beat so SS re-syncs cleanly to the new
   phrase.

2. **Phrase anchor**: every 64 beats, rearm the autoloop to recover from any
   accumulated phrasing drift. If a PSSI-derived drop beat is within ±8 beats of the
   next 64-beat boundary, snap the anchor fire to that drop beat instead. This is an
   experiment and must default off until live SoundSwitch validation confirms that
   periodic full deck-load rearms do not create visible disruption.

Both features operate only in `lighting_mode == "autoloop"`. They are independent of
the existing autoloop transition rearm (`_apply_lighting` / `_maybe_lock_autoloop_arm`)
which stays unchanged at highest priority.

**Hierarchy (highest → lowest):**
1. Existing autoloop transition rearm — unchanged
2. Smart drop cut + rearm
3. Phrase anchor rearm

---

## Files to create / modify

| File | Action |
|------|--------|
| `rb_ss_bridge_v2/anlz_reader.py` | Create |
| `rb_ss_bridge_v2/models.py` | Modify — add fields to TrackMetadata and OutputState |
| `rb_ss_bridge_v2/state_manager.py` | Modify — fire ANLZ parse, add push-loop logic, direct beat-boundary rearms, kill switches |
| `rb_ss_bridge_v2/config.py` | Modify — add two constants |
| `tests/test_anlz_reader.py` | Create |
| `tests/test_smart_drop.py` | Create |

Do NOT modify `filepath_resolver.py`, `osl_output.py`, or any other file. Do modify
`models.py` to add the `Ev.ANLZ_DATA` kind and the new state fields below.

---

## Phase 0 — ANLZ phrase + waveform spike (complete before runtime wiring)

This spike is complete enough to change the implementation direction: Rekordbox
phrase analysis (`PSSI`) is the primary semantic source for musical drops. Waveform
amplitude is only a fallback when `PSSI` is unavailable or empty. Do not wire runtime
smart-drop behavior until `read_anlz_drops()` returns PSSI-derived beat indices and the
real-track validation below remains true.

### Confirmed PSSI phrase results — 2026-05-07

Source corpus: local Rekordbox tracks under `/Users/bbui/Desktop/better songs` and
`/Users/bbui/Music`. A 30-track local sample had `PSSI` on every track inspected.

Important conversion:

```python
bridge_drop_beat = pssi_entry.beat - 1
```

Rekordbox stores `PSSI` phrase beats as 1-based beat indices. The bridge and existing
autoloop scheduler use 0-based absolute beat indices. All smart-drop and phrase-anchor
scheduling must use the converted bridge beat index and then resolve execution time via
the beatgrid. **The beatgrid is the absolute authority for execution timing.** Do not
execute from approximate phrase wall-clock timestamps.

Validated tracks:

| Track | PSSI evidence | User validation |
|-------|---------------|-----------------|
| `A2 - All Night Long` | `kind=5 beat=257 -> bridge beat 256 -> ~1:39`; `kind=5 beat=513 -> bridge beat 512 -> ~3:18` | Correct |
| `Skrillex & Habstract - Chiken Soup (Vortek's Remix)` | `kind=5 beat=161 -> bridge beat 160 -> ~1:01.9`; `kind=5 beat=417 -> bridge beat 416 -> ~2:41` | Correct |
| `Blaame - Can't run [DURVA005]` | `kind=5 beat=193 -> bridge beat 192 -> ~1:19/1:20`; `kind=5 beat=481 -> bridge beat 480 -> ~3:18/3:19` | Correct |
| `Tove Lo - Habits (Stay High) (Bessey Remix)` | `kind=5` candidates at ~0:30, ~1:29, ~3:42 | Correct in spot check |
| `rockyourbody FINAL` | `kind=5` candidates at ~0:52, ~1:30, ~3:04 | Correct in spot check |
| `timeless - dhil.p edit` | `kind=5` candidates at ~0:45, ~1:15, ~2:23 | Correct in spot check |
| `ROB49 - WTHELLY (JULIAN JORDAN REMIX) EXTENDED` | `kind=5` candidates at ~1:00, ~2:28, ~2:58 | Correct in spot check |
| `Bicep - Glue (Kanine Bootleg)` | `kind=5` candidates did not match user validation | Rekordbox phrase analysis appears wrong for this track |

Interpretation of currently observed `PSSI` fields:

- `tag.content.entries` contains phrase entries.
- `entry.beat` is the 1-based phrase start beat.
- `entry.kind == 5` corresponds to the Rekordbox phrase label family that best matches
  drop/chorus starts in the tested tracks. Treat it as the primary drop candidate.
- Other `kind` values likely correspond to Intro/Up/Down/Out families, but the exact
  mapping is not needed for smart-drop targeting yet.
- Bad phrase analysis is possible. If Rekordbox marks a phrase incorrectly, the bridge
  should follow Rekordbox rather than trying to override it with waveform amplitude.
  This is source-data quality, not a bridge timing bug.

### Confirmed waveform results — fallback only

Spike source directory:
`/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/eac/ed59d-f6a1-4814-a850-312b003de118/`

| Item | Confirmed result |
|------|------------------|
| A | Waveform entries are exposed as `tag.content.entries`, not `tag.entries`, `tag.data`, `tag.body`, or `tag.waveform`. |
| B | `PWV3` and `PWAV` entries are bare `int` values. Height extraction is `entry & 0x1F`. |
| C | No useful dedicated duration field was found. Use a validated full beatgrid duration: `waveform_duration_ms = last_beat_time_ms + (last_beat_time_ms - previous_beat_time_ms)`. In the tested files, `.DAT` `PQTZ.get_times()` returned the full 747-marker grid and estimated `289210 ms`; `.EXT` `PQT2.get_times()` returned only 2 timestamps and must be rejected. |

Additional confirmed file-shape notes:

- `.2EX` did not contain `PWV3` in the tested Rekordbox files. It contained `PWV7`,
  `PWV6`, and `PWVC`. Do not assume `.2EX` is a usable `PWV3` source.
- `.EXT` contained `PWV3` with `43360` entries. `289210 / 43360 ~= 6.67 ms/entry`,
  which matches the expected high-detail waveform resolution.
- `.DAT` contained `PWAV` with `400` entries and `PQTZ` with the full beatgrid.
- Waveform amplitude failed on user-validated tracks where the musical drop occurs
  while amplitude is already high. Therefore waveform must not be the primary source.

---

## 1. New file: `rb_ss_bridge_v2/anlz_reader.py`

### Purpose

Parse Rekordbox ANLZ phrase data for a track and return a sorted list of drop beat
indices. This module has no imports from other bridge modules except `logging`. It is
called from a background thread.

### Public API

```python
@dataclass
class TrackAnlzData:
    drop_beat_indices: list[int]   # sorted bridge absolute beat indices of detected drops
    # empty list = no phrase drops detected or ANLZ unavailable

def read_anlz_drops(anlz_path: str) -> TrackAnlzData:
    """Parse ANLZ files for the given path and return drop beat data.

    Primary source: PSSI phrase entries from EXT/2EX/DAT candidates.
    Drop candidates: entries where kind == 5. Convert PSSI's 1-based beat to the
    bridge's 0-based absolute beat with beat - 1.

    Fallback source only when PSSI is missing or empty: PWV3/PWAV waveform amplitude
    using the validated beatgrid duration rules below.

    Returns TrackAnlzData with empty drop_beat_indices on any parse failure
    (fail-closed). Never raises. All exceptions are caught and logged at DEBUG level.
    """
```

### File resolution

The `anlz_path` string may point to the DAT. Look for EXT/2EX siblings by replacing the
suffix. Candidate priority should parse all available siblings once, then extract tags
by semantic priority:

1. `PSSI` from any parsed candidate, preferring `.EXT` if duplicate phrase data exists.
2. Valid beatgrid from `PQT2`/`PQTZ` for beat-to-time validation and runtime scheduling.
3. Waveform fallback from `.EXT` `PWV3`, then `.DAT` `PWAV`.

Do not put runtime scheduling timestamps into `TrackAnlzData`; return beat indices only.
The bridge must use `_autoloop_target_elapsed_for_beat()` with the returned beat index.

```python
path = Path(anlz_path)
candidates = []
if path.suffix.upper() in (".DAT", ".EXT", ".2EX"):
    for suffix in (".EXT", ".2EX", ".DAT"):
        p = path.with_suffix(suffix)
        if p.exists():
            candidates.append(p)
if not candidates and path.exists():
    candidates.append(path)
```

### PSSI phrase source priority

Use `tag.getall_tags("PSSI")` and inspect `tag.content.entries`. For each entry:

```python
kind = int(entry.kind)
pssi_beat = int(entry.beat)
bridge_beat = max(0, pssi_beat - 1)
```

Keep entries where `kind == 5` and `bridge_beat > 0`. Sort and de-duplicate them.
Return these as `drop_beat_indices`. Do not filter by intro/outro here; Rekordbox's
phrase analysis is the semantic source, and the feature needs the phrase beat identity.

Optional implementation guard: if there are many adjacent `kind=5` entries, keep all for
now. Later live validation can add higher-level selection rules if SoundSwitch should not
rearm on every chorus-like phrase.

### Beat grid source priority

1. Validated `PQT2` (from EXT or DAT)
2. Validated `PQTZ` (from DAT)

Use `tag.get_times()` -> list of float seconds. Beat count = track length in beats. Do
not accept a tag just because `get_times()` returns at least two timestamps. Copy the
existing plausibility pattern from `filepath_resolver._grid_from_tag`: sort rows, require
strictly increasing positive intervals, and reject median intervals outside 150 ms to
3000 ms. If `PQT2` is sparse or implausible, fall through to `PQTZ`.

The Phase 0 spike found `.EXT` `PQT2.get_times()` returning only 2 timestamps while
`.DAT` `PQTZ.get_times()` returned the full beatgrid. This means `PQTZ` is often the
correct duration/grid source even when phrase data and waveform data came from `.EXT`.

**Do not use phrase timestamps for runtime execution.** The returned drop beat index is
only an identity. Runtime cut/rearm timing must be derived from beatgrid scheduling.

### Waveform fallback algorithm

Use only if no PSSI `kind=5` candidates are found. This fallback is less reliable than
phrase analysis and exists only for tracks without usable phrase tags.

Run entirely at load time. Return a sorted list of beat indices.

```
BREAKDOWN_THRESHOLD = 0.35
DROP_THRESHOLD = 0.65
MIN_LOW_BARS = 3
MAX_DROP_GAP_BARS = 2
POST_HIT_SHIFT_WINDOW_BARS = 8
POST_HIT_MIN_LOW_BARS = 2
COOLDOWN_BARS = 16
IGNORE_INTRO_BARS = 8
IGNORE_OUTRO_BARS = 8
```

The fallback groups every 4 beatgrid beats into one bar, maps each bar to waveform
indices, and looks for a low-energy run followed by a high-energy hit. It includes the
post-hit shift refinement discovered during validation of `A2 - All Night Long`, but it
should not be considered authoritative for musical drops.

### Internal helpers

Expose these helpers for focused tests:

```python
def _extract_pssi_drop_beats(parsed: list[tuple[Path, Any]]) -> list[int]: ...
def _extract_waveform_drop_beats(parsed: list[tuple[Path, Any]]) -> list[int]: ...
def _detect_drop_beats(heights: list[int], waveform_duration_ms: float, beatgrid_times_ms: list[float]) -> list[int]: ...
```

`read_anlz_drops(path)` calls `_extract_pssi_drop_beats()` first. Only if it returns
`[]` should it call the waveform fallback.

### Failure modes

- `pyrekordbox` not installed -> return `TrackAnlzData([])`
- File not found -> return `TrackAnlzData([])`
- Parse exception -> log at DEBUG, return `TrackAnlzData([])`
- No PSSI drops and no fallback drops -> return `TrackAnlzData([])`
- All returns are via the dataclass, never `None`

---

## 2. `rb_ss_bridge_v2/models.py`

### `TrackMetadata` — add one field

```python
anlz_drops: list[int] = field(default_factory=list)
```

Add to `clear()`:
```python
self.anlz_drops = []
```

### `OutputState` — add three fields

```python
# Smart drop
drop_cut_armed:      bool  = False   # cut fired; waiting for drop_rearm_beat
drop_rearm_beat:     int   = 0       # abs beat index to rearm on

# Phrase anchor
phrase_anchor_last_beat: int = -1    # -1 = uninitialised (set by _apply_lighting);
                                     # ≥0 = abs beat of last anchor fire
```

### `Ev` — add one constant

```python
ANLZ_DATA = "anlz_data"   # deck, payload={"drop_beat_indices": list[int], "load_gen": int}
```

---

## 3. `rb_ss_bridge_v2/config.py`

Add two constants:

```python
SMART_DROP_LOOKAHEAD_BEATS = 4   # cut fires this many beats before the drop
PHRASE_ANCHOR_BEATS        = 64  # rearm every N beats to recover phrasing drift
```

---

## 4. `rb_ss_bridge_v2/state_manager.py`

### 4a. Imports

Add to the config import line (state_manager.py:32):
```python
from .config import (
    ...
    SMART_DROP_LOOKAHEAD_BEATS,
    PHRASE_ANCHOR_BEATS,
)
```

Add env constant names near the existing `LIVE_BPM_FOLLOW_ENV` /
`AUTOLOOP_MASTER_PHRASE_ARM_ENV` constants:

```python
SMART_DROP_ENV = "RBSS_SMART_DROP"
PHRASE_ANCHOR_ENV = "RBSS_PHRASE_ANCHOR"
SMART_REARM_EXPERIMENT_ENV = "RBSS_SMART_REARM_EXPERIMENT"
```

Add boolean init in `StateManager.__init__`. Unlike the already-validated
`RBSS_LIVE_BPM_FOLLOW` and `RBSS_AUTOLOOP_MASTER_PHRASE_ARM` defaults, this experiment
must default off until live SoundSwitch validation confirms periodic full rearms are
visually acceptable:

```python
self._smart_rearm_experiment = (
    _os.environ.get(SMART_REARM_EXPERIMENT_ENV, "0") == "1"
)
self._smart_drop_enabled = (
    self._smart_rearm_experiment
    and _os.environ.get(SMART_DROP_ENV, "1") != "0"
)
self._phrase_anchor_enabled = (
    self._smart_rearm_experiment
    and _os.environ.get(PHRASE_ANCHOR_ENV, "1") != "0"
)
```

When `RBSS_SMART_REARM_EXPERIMENT=0`, both feature flags must be false and the ANLZ
drop worker must not launch.

To enable the experiment for validation:

```bash
RBSS_SMART_REARM_EXPERIMENT=1 python -u -m rb_ss_bridge_v2
```

First live validation should isolate the features:

1. Validate parser output only: run `read_anlz_drops()` against real tracks and review
   detected beats before any bridge runtime wiring.
2. Validate smart-drop cut/rearm with `RBSS_SMART_REARM_EXPERIMENT=1` and
   `RBSS_PHRASE_ANCHOR=0`.
3. Validate phrase anchor separately after smart drop is proven visually safe.

Add a deferred import inside the new method (not at module level) to avoid hard
dependency:
```python
from .anlz_reader import read_anlz_drops
```

### 4b. Handle `Ev.ANLZ_DATA` in `_drain_events`

Find the `elif ev.kind == Ev.ANLZ_PATH:` block (state_manager.py:314). After it, add:

```python
elif ev.kind == Ev.ANLZ_DATA:
    d = self._deck.get(ev.deck)
    if d is not None:
        gen = ev.payload.get("load_gen", -1)
        if gen == d.load_gen:
            d.meta.anlz_drops = list(ev.payload.get("drop_beat_indices", []))
            log.info("[SM] anlz-drops  deck=%d  drops=%s",
                     ev.deck, d.meta.anlz_drops or "none")
        else:
            log.debug("[SM] anlz-drops-stale  deck=%d  gen=%d  current=%d",
                      ev.deck, gen, d.load_gen)
```

### 4c. Kick off ANLZ parse from `_on_track_loaded` (state_manager.py:428)

**Not** `_on_filepath_resolved`. By the time FILEPATH_RESOLVED fires, `anlz_path` has
already been popped from `_pending_anlz_path` in `_on_track_loaded` (line 452), and
the FILEPATH_RESOLVED payload never includes the ANLZ path (confirmed in
`filepath_resolver.py:_resolve_anlz_worker` — the payload is `{**result, 'load_gen'}`
and `result` from `_db_lookup_by_anlz` does not carry the path).

Inside `_on_track_loaded` (state_manager.py:428), in the `if anlz_path:` branch
(line 453), after the existing `resolve_by_anlz` call, launch the worker only when
the experiment is enabled:

```python
if self._smart_rearm_experiment:
    # Kick off background ANLZ drop detection (anlz_path and d.load_gen both valid here)
    eq = self._eq
    load_gen = d.load_gen
    def _anlz_worker(path: str, bridge_deck: int, gen: int) -> None:
        try:
            from .anlz_reader import read_anlz_drops
            result = read_anlz_drops(path)
        except Exception:
            log.debug("[SM] anlz-worker-error", exc_info=True)
            return
        try:
            eq.put_nowait(BridgeEvent(
                kind=Ev.ANLZ_DATA,
                deck=bridge_deck,
                payload={"drop_beat_indices": result.drop_beat_indices, "load_gen": gen},
                source="anlz",
            ))
        except queue.Full:
            log.warning("[SM] queue-full  event=anlz-data  deck=%d", bridge_deck)
    threading.Thread(
        target=_anlz_worker,
        args=(anlz_path, deck, load_gen),
        daemon=True,
        name=f"anlz-drop-{deck}",
    ).start()
```

`d.load_gen` has already been incremented at line 432 before this branch is reached.
`d.meta.clear()` at line 430 clears `anlz_drops` for the new load — correct.
Do not launch this worker outside the `if anlz_path:` branch. Tracks resolved only by
lsof or title fallback have no ANLZ path available here, so smart drop degrades
silently and phrase anchor runs without drop snapping.

### 4d. Reset smart drop + phrase anchor state on all relevant state transitions

Use one helper only. Do not mix inline triple-field resets with helper calls.

```python
def _clear_smart_rearm_state(self) -> None:
    self._os.drop_cut_armed = False
    self._os.drop_rearm_beat = 0
    self._os.phrase_anchor_last_beat = -1
```

Call it in every state transition that can invalidate the active autoloop context.
Without this, a mid-cut scripted arm, stop transition, track load, master switch, or
Rekordbox restart can leave `drop_cut_armed=True` stale until the next autoloop arm.

In `_apply_lighting` (state_manager.py:736), call the helper in all three mode branches.

In the `if mode == "scripted":` branch, call it at the start before `_arm_scripted()`:

```python
if mode == "scripted":
    self._clear_smart_rearm_state()
    self._os.autoloop_arm_after_master_change = False
    self._os.autoloop_master_change_source = ""
    ...
    self._arm_scripted(deck, d.scripted_id)
```

In the `elif mode == "autoloop":` branch, call it with the other arm resets, before
the new autoloop state is armed:

```python
elif mode == "autoloop":
    self._clear_smart_rearm_state()
    self._pending_arm = None
    self._os.push_reset_bpm = True
    arm_bpm, bpm_source = self._autoloop_arm_bpm(deck, d.meta.bpm)
    ...
```

In the `elif mode == "idle":` branch, call it alongside the existing autoloop resets:

```python
elif mode == "idle":
    self._clear_smart_rearm_state()
    self._pending_arm = None
    self._os.last_armed_filepath = ""
    ...
```

Also call the helper anywhere the active autoloop context can be invalidated without an
`_apply_lighting` mode transition.

In `_on_track_loaded` (state_manager.py:428), `d.meta.clear()` already clears
`anlz_drops`, but smart rearm state lives on `_os`, so reset it separately. Do this only
when the loaded deck is the active deck:

```python
def _on_track_loaded(self, deck: int, title: str, ev: BridgeEvent) -> None:
    d = self._deck[deck]
    d.meta.clear()
    d.scripted_id = 0
    d.load_gen += 1
    if deck == self._os.active_deck:
        self._clear_smart_rearm_state()
        self._clear_autoloop_arm_phrase_lock()
        self._clear_live_bpm_follow()
        self._clear_autoloop_tempo_relock()
        self._clear_pending_autoloop_master_phrase_arm()
    ...
```

In `_on_master_changed` (state_manager.py:381), call it after the active-deck swap
state is reset and before the existing autoloop/live-BPM clear helpers:

```python
self._os.autoloop_arm_bpm = 0.0
self._os.autoloop_arm_deck = 0
self._os.last_autoloop_status_phrase_beat = 0
self._os.autoloop_arm_after_master_change = True
self._os.autoloop_master_change_source = source
self._clear_smart_rearm_state()
self._clear_autoloop_arm_phrase_lock()
self._clear_live_bpm_follow()
self._clear_autoloop_tempo_relock()
self._clear_pending_autoloop_master_phrase_arm()
```

In the `Ev.RB_RESTARTED` branch of `_drain_events` (around state_manager.py:351), call
it with the other restart resets:

```python
self._os.autoloop_arm_bpm = 0.0
self._os.autoloop_arm_deck = 0
self._os.last_autoloop_status_phrase_beat = 0
self._clear_smart_rearm_state()
self._clear_autoloop_arm_phrase_lock()
self._clear_live_bpm_follow()
self._clear_autoloop_tempo_relock()
self._clear_pending_autoloop_master_phrase_arm()
```

### 4e. Do not add `force_beat` to `_apply_lighting`

Do not change `_apply_lighting`'s signature and do not add a `force_beat` parameter.
For smart drop and phrase anchor, the target beat has already arrived inside
`_push_tick`; there is no future arm to schedule. Calling `_apply_lighting("autoloop")`
from these beat-boundary helpers would also reset unrelated autoloop state
(`_clear_live_bpm_follow`, pending master phrase arm state, smart-drop state, and the
phrase-anchor counter).

Use a small direct helper instead:

This helper is also module-level, placed before `_smart_drop_tick()` near the bottom of
`state_manager.py`.

```python
def _send_direct_autoloop_rearm(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    elapsed_ms: int,
    reason: str,
    target_beat: int | None = None,
) -> bool:
    d = sm._deck[active]
    if not d.meta.filepath:
        return False
    # Use the BPM that was locked when the autoloop was armed, not the raw push-loop
    # bpm variable (which may lag a live-follow update). Falls back to push-loop bpm
    # when no arm has fired yet (autoloop_arm_bpm == 0).
    arm_bpm = sm._os.autoloop_arm_bpm if sm._os.autoloop_arm_bpm > 0 else bpm
    arm_meta = TrackMetadata(
        filepath=d.meta.filepath,
        soundswitch_id="",
        bpm=arm_bpm,
        first_beat_ms=d.meta.first_beat_ms,
        beatgrid_times_ms=list(d.meta.beatgrid_times_ms),
        beatgrid_bpms=list(d.meta.beatgrid_bpms),
        beatgrid_source=d.meta.beatgrid_source,
        total_ms=d.meta.total_ms,
    )
    target_elapsed_ms = elapsed_ms
    target_source = "current"
    lateness_ms = 0
    if target_beat is not None:
        # The beat-boundary tick can arrive late. Prefer the beatgrid/fallback target
        # elapsed for the intended beat so the deck-load is anchored to the beat identity
        # that triggered the rearm, not merely the slightly-late push tick.
        target_elapsed_ms, target_source = sm._autoloop_target_elapsed_for_beat(
            target_beat, elapsed_ms, arm_bpm, arm_meta,
        )
        lateness_ms = max(0, elapsed_ms - target_elapsed_ms)
    object.__setattr__(arm_meta, "elapsed_ms", target_elapsed_ms)
    sm._os.last_arm_mono = time.monotonic()
    sm._os.last_armed_filepath = d.meta.filepath
    sm._sse.send_autoloop_deck_load(active, mirror, active, arm_meta)
    log.info("[SM] autoloop-rearm  deck=%d  reason=%s  beat=%s  elapsed=%s"
             "  target_elapsed=%s  late=%dms  grid=%s  bpm=%.1f  file=%s",
             active, reason, target_beat if target_beat is not None else "-",
             bf.elapsed(elapsed_ms), bf.elapsed(target_elapsed_ms),
             lateness_ms, target_source, arm_bpm, bf.short(d.meta.filepath))
    return True
```

The helper deliberately updates only the output fields needed for a fresh deck-load:
`last_arm_mono` and `last_armed_filepath`. It must not clear live BPM follow,
pending master phrase arms, tempo anchors, or smart-drop / phrase-anchor counters.

### 4f. Smart drop and phrase anchor in the push loop

In `_push_tick` (state_manager.py:878), inside the `if this_beat > last_beat:` block
(around line 1129), after the existing `_maybe_lock_autoloop_arm` calls and beat-send
block, add the following. Insert it just before the existing `for dk ... send_elapsed`
line (line 1175) so it runs once per beat boundary:

```python
if os.lighting_mode == "autoloop":
    if self._smart_drop_enabled and d.meta.anlz_drops:
        _smart_drop_tick(self, active, mirror, bpm, this_beat, elapsed_ms)
    if self._phrase_anchor_enabled:
        _phrase_anchor_tick(self, active, mirror, bpm, this_beat, elapsed_ms, abs_beat_pos)
```

Define `_send_direct_autoloop_rearm()`, `_smart_drop_tick()`, and
`_phrase_anchor_tick()` as module-level functions (not methods) after the
`StateManager` class definition, at the bottom of `state_manager.py`, to keep
`_push_tick` readable.

**Priority guard placement**: each function begins by checking whether a transition arm
is pending and returning immediately if so. The guard lives inside the functions (not in
`_push_tick`) so unit tests can call the functions directly with controlled `sm._os` state
and verify that the guard fires. A guard placed only in `_push_tick` is invisible to
module-level function tests.

```python
def _smart_drop_tick(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    this_beat: int,
    elapsed_ms: int,
) -> None:
    """Fire smart-drop cut 4 beats before a detected drop, rearm on the drop beat."""
    os = sm._os
    d  = sm._deck[active]

    # Strictly lower priority than the existing transition rearm.
    # The pending arm will fire its own deck-load at the correct phrase boundary.
    if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
        return

    if os.drop_cut_armed:
        # Waiting for the drop beat — rearm when we reach it
        if this_beat >= os.drop_rearm_beat:
            log.info("[SM] smart-drop-rearm  deck=%d  beat=%d", active, this_beat)
            if _send_direct_autoloop_rearm(
                sm, active, mirror, bpm, elapsed_ms, "smart-drop",
                target_beat=os.drop_rearm_beat,
            ):
                os.drop_cut_armed = False
                os.drop_rearm_beat = 0
        return

    # Find the next unprocessed drop beat.
    # This intentionally scans the sorted drop list each beat instead of adding an
    # OutputState cursor; normal tracks have very small drop lists (<20), and avoiding
    # another state field keeps the first experiment easier to reason about.
    drops = d.meta.anlz_drops
    for drop_beat in drops:
        cutoff = drop_beat - SMART_DROP_LOOKAHEAD_BEATS
        if this_beat < cutoff:
            break   # too early for any remaining drop
        if this_beat >= drop_beat:
            continue   # already past this drop
        # We are in the [cutoff, drop_beat) window — fire the cut.
        # Autoloops are armed/disarmed by filepath presence, not play state.
        # send_deck_clear clears filepath ("") which disarms SS's autoloop engine;
        # send_loop_off follows the same pattern as the existing arm-correction-clear
        # path (state_manager.py:1500-1504).
        log.info("[SM] smart-drop-cut  deck=%d  beat=%d  drop_at=%d",
                 active, this_beat, drop_beat)
        for dk in (active, mirror, 3, 4):
            sm._out.send_deck_clear(dk)
            sm._out.send_loop_off(dk)
        os.drop_cut_armed  = True
        os.drop_rearm_beat = drop_beat
        break


def _phrase_anchor_tick(
    sm: "StateManager",
    active: int,
    mirror: int,
    bpm: float,
    this_beat: int,
    elapsed_ms: int,
    abs_beat_pos: float,
) -> None:
    """Rearm autoloop every PHRASE_ANCHOR_BEATS to correct phrasing drift."""
    os = sm._os
    d  = sm._deck[active]

    # Strictly lower priority than the existing transition rearm.
    if os.autoloop_arm_pending or os.pending_autoloop_arm_meta is not None:
        return

    # Init anchor on the first tick after an autoloop arm
    if os.phrase_anchor_last_beat < 0:
        os.phrase_anchor_last_beat = (int(abs_beat_pos) // PHRASE_ANCHOR_BEATS) * PHRASE_ANCHOR_BEATS
        return

    # Skip if a smart drop cut is in progress
    if os.drop_cut_armed:
        return

    next_anchor = os.phrase_anchor_last_beat + PHRASE_ANCHOR_BEATS

    # Optional ANLZ snap: if a detected drop is within ±8 beats of the anchor, use the
    # closest future drop to the anchor.
    # Only snap forward (drop_beat >= this_beat) — snapping to a past drop would send
    # SS a deck-load at an elapsed position that has already passed.
    SNAP_WINDOW = 8
    snap_candidates = [
        drop_beat for drop_beat in d.meta.anlz_drops
        if drop_beat >= this_beat and abs(drop_beat - next_anchor) <= SNAP_WINDOW
    ]
    if snap_candidates:
        next_anchor = min(snap_candidates, key=lambda b: abs(b - next_anchor))

    if this_beat >= next_anchor:
        log.info("[SM] phrase-anchor  deck=%d  beat=%d  anchor=%d",
                 active, this_beat, next_anchor)
        if _send_direct_autoloop_rearm(
            sm, active, mirror, bpm, elapsed_ms, "phrase-anchor",
            target_beat=next_anchor,
        ):
            os.phrase_anchor_last_beat = next_anchor
```

---

## 5. Edge cases and failure modes

**Accepted behavioral cost — pending arm suppression:** `_apply_lighting("autoloop")`
sets `autoloop_arm_pending=True` even when it immediately sends a deck load. Because the
priority guard in `_smart_drop_tick` and `_phrase_anchor_tick` returns when
`autoloop_arm_pending` is true, smart drop and phrase anchor are suppressed during the
`autoloop_arm_pending` window after any normal autoloop arm — including the initial arm
on track load. This is intentional: the pending arm owns the phrase boundary and will
fire its own deck-load via `_maybe_lock_autoloop_arm`. Smart drop and anchor resume after
`autoloop_arm_pending` clears — which happens when the arm resolves or is cleared by a
mode/load/master transition. There is no timeout path for `autoloop_arm_pending`. No action needed.

| Scenario | Expected behavior |
|----------|-------------------|
| ANLZ file not found / parse error | `anlz_drops = []`; smart drop disabled; phrase anchor still fires every 64 beats only when the experiment is enabled |
| Drop beat arrives before `Ev.ANLZ_DATA` is processed (fast DJ) | `anlz_drops` is empty; drop feature silently skipped for that track |
| `drop_cut_armed` when lighting_mode transitions to idle or scripted | `_apply_lighting` resets `drop_cut_armed`, `drop_rearm_beat`, `phrase_anchor_last_beat` in all three mode branches (step 4d) |
| Active track load while `lighting_mode` remains autoloop | `_on_track_loaded` clears smart-drop and phrase-anchor state so no stale cut/rearm carries into the next track |
| Master deck changes or Rekordbox restarts | `_on_master_changed` / `Ev.RB_RESTARTED` clear smart-drop and phrase-anchor state with the same helper |
| Drop beat already past when `Ev.ANLZ_DATA` arrives | `this_beat >= drop_beat` → skipped in the loop |
| Two PSSI `kind=5` entries are close together | Keep both after sort/dedupe; future live validation can add selection rules if SS should not rearm on every chorus-like phrase |
| Waveform fallback finds close drops | `_detect_drop_beats()` applies `COOLDOWN_BARS`; only first fallback candidate is kept |
| Phrase anchor fires at same beat as smart drop rearm | `drop_cut_armed` guard in `_phrase_anchor_tick` prevents double-arm |
| Track load has no ANLZ path | ANLZ worker is not launched; smart drop is unavailable; phrase anchor still runs but cannot snap to drops |
| `RBSS_SMART_REARM_EXPERIMENT` unset or `0` | Smart drop, phrase anchor, and the ANLZ drop worker are all disabled |
| RB restart / deck track unloaded | `_on_filepath_resolved` won't fire for the new load_gen until new track loaded; `anlz_drops` cleared by `meta.clear()` |

---

## 6. Tests

### `tests/test_anlz_reader.py`

Prefer small synthetic objects over real ANLZ files in unit tests. Real-track evidence
belongs in the Phase 0 notes above and in optional manual validation scripts, not in
CI-coupled tests that require the user's music library.

**PSSI primary tests:**

- `test_pssi_kind5_returns_bridge_beats_minus_one`: synthetic `PSSI` entries
  `kind=5 beat=161` and `kind=5 beat=417` return `[160, 416]`.
- `test_pssi_ignores_non_drop_kinds`: entries with other `kind` values are ignored.
- `test_pssi_sorts_and_dedupes`: duplicate/out-of-order `kind=5` entries return a
  sorted unique list.
- `test_pssi_primary_skips_waveform_fallback_when_present`: if PSSI returns drops,
  waveform fallback is not consulted even if waveform data would produce different
  candidates.
- `test_pssi_empty_falls_back_to_waveform`: if no `kind=5` entries are found, the
  reader calls the waveform fallback.
- `test_pssi_bad_source_data_is_not_waveform_overridden`: when PSSI is present but
  disagrees with waveform fallback, return PSSI. This matches the `Bicep - Glue`
  source-data-risk decision.
- `test_validated_a2_pssi_fixture`: synthetic entries from `A2 - All Night Long`
  `beat=257` and `beat=513` return `[256, 512]`.
- `test_validated_chiken_soup_pssi_fixture`: synthetic entries `beat=161` and
  `beat=417` return `[160, 416]`.
- `test_validated_blaame_pssi_fixture`: synthetic entries `beat=193` and `beat=481`
  return `[192, 480]`.

**File and failure tests:**

- `test_missing_file_returns_empty`: path that does not exist -> `read_anlz_drops`
  returns `TrackAnlzData([])`.
- `test_pyrekordbox_not_installed`: mock ImportError on pyrekordbox in
  `read_anlz_drops` -> `TrackAnlzData([])`.
- `test_all_failures_return_dataclass_not_none`: parser failures always return
  `TrackAnlzData(drop_beat_indices=[])`, never `None`.
- `test_candidate_ordering_prefers_ext_pssi`: if `.EXT` and `.DAT` both contain
  duplicate PSSI phrase data, `.EXT` is preferred for phrase extraction.

**Beatgrid and waveform fallback tests:**

- `test_waveform_accessor_content_entries`: mock a PWV3/PWAV tag whose entries live at
  `tag.content.entries`; confirm heights are extracted with `entry & 0x1F`.
- `test_2ex_without_pwv3_falls_through_to_ext`: when `.2EX` exists but has no `PWV3`,
  `.EXT` `PWV3` is used instead of failing early.
- `test_candidate_ordering_ext_before_dat_for_waveform`: when only `.EXT` and `.DAT`
  exist, `.EXT` `PWV3` is preferred over `.DAT` `PWAV`.
- `test_pqt2_sparse_falls_through_to_pqtz`: when `.EXT` `PQT2.get_times()` returns only
  two timestamps but `.DAT` `PQTZ` returns a plausible full grid, use `PQTZ`.
- `test_implausible_beatgrid_rejected`: reject non-increasing intervals and median beat
  intervals outside 150 ms to 3000 ms, matching `filepath_resolver._grid_from_tag`.
- `test_no_drops_flat_energy`: flat waveform -> empty drop list.
- `test_single_drop_detected`: low energy bars 8-15, high energy bars 16+
  -> drop at beat 64 (bar 16 * 4).
- `test_three_bar_pre_drop_valley_detected`: 3-bar quiet pre-drop valley is enough to
  qualify as a fallback drop setup.
- `test_intro_filtered`: fallback drop would be at bar 3 -> filtered
  (`IGNORE_INTRO_BARS=8`).
- `test_outro_filtered`: fallback drop in last 5 bars -> filtered.
- `test_cooldown_deduplication`: two fallback drops 8 bars apart -> only first kept.
- `test_medium_buildup_after_breakdown_is_not_drop`: low run followed by more than
  `MAX_DROP_GAP_BARS` of medium-energy buildup before the first high bar -> no drop.
- `test_buildup_hit_shifts_to_following_drop`: buildup hit followed by a short
  low-energy valley and second high hit shifts to the later true fallback drop.

### `tests/test_smart_drop.py`

Mock `StateManager` internals. Test against the module-level functions directly.

**Priority guard tests** (call module-level functions directly with a mock `sm`):
- `test_smart_drop_skipped_while_transition_arm_pending`: call `_smart_drop_tick(sm, ...)`
  with `sm._os.autoloop_arm_pending=True`, `drop_beat=64`, `this_beat=60` → no cut fires
- `test_smart_drop_skipped_while_pending_arm_meta_set`: call `_smart_drop_tick(sm, ...)`
  with `sm._os.pending_autoloop_arm_meta` set to a non-None object, `this_beat=60` → no cut fires
- `test_smart_drop_misses_drop_during_pending_arm_window`: with
  `autoloop_arm_pending=True`, `drop_beat=64`, and `this_beat=60..64`, no cut or rearm
  fires. After `autoloop_arm_pending` clears and `this_beat > drop_beat`, the drop is
  skipped as already past. This documents the accepted suppression window.
- `test_phrase_anchor_skipped_while_transition_arm_pending`: call `_phrase_anchor_tick(sm, ...)`
  with `sm._os.autoloop_arm_pending=True`, `phrase_anchor_last_beat=0`, `this_beat=64`
  → `send_autoloop_deck_load` NOT called

**State reset on mode transition tests:**
- `test_drop_cut_cleared_on_idle_transition`: `drop_cut_armed=True`; call
  `_apply_lighting(deck, "idle", ...)` → `drop_cut_armed=False`, `drop_rearm_beat=0`,
  `phrase_anchor_last_beat=-1`
- `test_drop_cut_cleared_on_scripted_transition`: same as above with `"scripted"`
- `test_drop_cut_cleared_on_active_track_load`: `drop_cut_armed=True`; call
  `_on_track_loaded()` for the active deck → smart rearm fields reset
- `test_drop_cut_not_cleared_on_inactive_track_load`: `drop_cut_armed=True`; call
  `_on_track_loaded()` for an inactive deck → smart rearm fields unchanged
- `test_drop_cut_cleared_on_master_change`: `drop_cut_armed=True`; call
  `_on_master_changed()` → smart rearm fields reset
- `test_drop_cut_cleared_on_rb_restart`: `drop_cut_armed=True`; drain an
  `Ev.RB_RESTARTED` event → smart rearm fields reset

**Smart drop tests:**
- `test_cut_fires_4_beats_before_drop`: `drop_beat=64`, `this_beat=60` →
  `send_deck_clear` + `send_loop_off` called for all 4 decks;
  `drop_cut_armed=True`, `drop_rearm_beat=64`
- `test_cut_does_not_fire_before_window`: `this_beat=55` → no cut
- `test_rearm_fires_on_drop_beat`: `drop_cut_armed=True`, `drop_rearm_beat=64`,
  `this_beat=64` → `send_autoloop_deck_load` called through direct rearm helper;
  `drop_cut_armed=False`, `drop_rearm_beat=0`
- `test_past_drop_skipped`: `this_beat=70`, `drop_beat=64` → no cut, no rearm
- `test_past_drops_scanned_but_ignored`: `anlz_drops=[32,64,128]`,
  `this_beat=124` → past drops are ignored and the upcoming drop can still cut at 124
- `test_rearm_uses_autoloop_arm_bpm`: `autoloop_arm_bpm=130.5`, push-loop `bpm=131.0`
  → `send_autoloop_deck_load` called with `arm_meta.bpm == 130.5`
- `test_rearm_falls_back_to_push_bpm_when_arm_bpm_zero`: `autoloop_arm_bpm=0`,
  push-loop `bpm=131.0` → `arm_meta.bpm == 131.0`
- `test_rearm_uses_target_elapsed_for_drop_beat`: `target_beat=64` and a mocked
  `_autoloop_target_elapsed_for_beat()` → `arm_meta.elapsed_ms` uses the target elapsed,
  not the current late push-loop elapsed

**Phrase anchor tests:**
- `test_phrase_anchor_fires_at_64`: `phrase_anchor_last_beat=0`, `this_beat=64` →
  `send_autoloop_deck_load` called; `phrase_anchor_last_beat=64`
- `test_phrase_anchor_snaps_to_nearby_future_drop`: `next_anchor=64`, `drop_beat=60`,
  `anlz_drops=[60]`. Call 1: `this_beat=58` → `drop_beat >= this_beat` and within ±8 of
  64, so `next_anchor` is snapped to 60 but `58 < 60` → no rearm, no deck-load.
  Call 2: `this_beat=60` (same `sm` state, `phrase_anchor_last_beat` unchanged) →
  `this_beat >= next_anchor(60)` → rearm fires; assert `send_autoloop_deck_load` called
  and `phrase_anchor_last_beat == 60`.
- `test_phrase_anchor_chooses_closest_drop_not_earliest`: `next_anchor=64`,
  `anlz_drops=[56, 60]`, `this_beat=56` → snap to 60 because `abs(60-64)` is smaller
  than `abs(56-64)`.
- `test_phrase_anchor_does_not_snap_to_past_drop`: `next_anchor=64`, `drop_beat=55`,
  `this_beat=62` → drop_beat < this_beat; anchor fires at 64, not 55
- `test_phrase_anchor_blocked_by_drop_cut`: `drop_cut_armed=True`, `this_beat=64`
  → direct rearm helper NOT called
- `test_phrase_anchor_init_sentinel`: `phrase_anchor_last_beat=-1` →
  sets to `(current_beat // 64) * 64`, does not fire arm on first tick

**Kill switch tests:**
- `test_experiment_default_off_skips_anlz_worker`: with `RBSS_SMART_REARM_EXPERIMENT`
  unset, `_on_track_loaded` in the `if anlz_path:` branch still resolves filepath by
  ANLZ but does not start the drop parser worker
- `test_experiment_off_skips_anlz_worker`: with `RBSS_SMART_REARM_EXPERIMENT=0`,
  `_on_track_loaded` in the `if anlz_path:` branch still resolves filepath by ANLZ
  but does not start the drop parser worker
- `test_global_switch_off_disables_both`: `RBSS_SMART_REARM_EXPERIMENT=0` →
  `_smart_drop_enabled=False`, `_phrase_anchor_enabled=False`
- `test_global_switch_on_enables_defaults`: `RBSS_SMART_REARM_EXPERIMENT=1` with no
  per-feature opt-outs → `_smart_drop_enabled=True`, `_phrase_anchor_enabled=True`
- `test_smart_drop_kill_switch_disables_cut`: with `RBSS_SMART_DROP=0`, loaded
  `anlz_drops` do not fire cuts
- `test_phrase_anchor_kill_switch_disables_anchor`: with `RBSS_PHRASE_ANCHOR=0`,
  phrase anchor does not rearm

---

## 7. Known unknowns

- **Does SS cleanly rearm after a 1-bar filepath-clear gap (~1.9 s at 130 BPM)?**
  The cut sends `send_deck_clear` (filepath="") + `send_loop_off` — identical to the
  existing arm-correction-clear path (state_manager.py:1500-1504) which already works
  in production. The rearm sends the full filepath again via `send_autoloop_deck_load`.
  Assumed safe; confirm via `[INJECT]` logs on first live test.
- **ANLZ path availability**: drop detection is intentionally tied to the
  `_on_track_loaded` `if anlz_path:` branch. Do not try to recover an ANLZ path from
  `FILEPATH_RESOLVED`; that payload does not carry it.
- **Exact Rekordbox phrase-kind mapping**: user-visible Rekordbox phrase labels are
  Intro 1/2/3, Up 1/2/3, Chorus 1/2/3, Down 1/2/3, and Out 1/2/3. Current evidence
  only needs `kind == 5` as the drop/chorus-like marker. Do not overfit a complete
  kind-to-label map until more source evidence is needed.
- **Rekordbox source-data quality**: PSSI can be wrong (`Bicep - Glue` was the observed
  example). The bridge should treat that as bad Rekordbox phrase analysis and follow
  PSSI rather than using waveform amplitude to silently override the phrase data.
- **Waveform fallback thresholds (0.35 / 0.65)**: these are fallback-only constants.
  They were useful for exploration but produced obvious false positives on validated
  tracks. Keep them module-level constants and do not use them as the primary detector.

---

## 9. Post-implementation Notes (Session 37 — Live Validation)

**Status**: ✅ Live-validated 2026-05-08. Phrase anchor confirmed working with lights.

### Critical SS re-anchor finding

SoundSwitch ignores a `send_deck_clear` + `send_deck_load` pair when both are enqueued in the same push tick. SS's recv queue processes them atomically — the cleared state is never rendered, and the reload is treated as a no-op for the currently-playing track.

**Fix**: `_phrase_anchor_tick` sends the clear (`send_deck_clear + send_loop_off` to all 4 decks) at `this_beat == next_anchor - 1` (1 beat before the anchor) and returns early. The full reload fires on the anchor beat as normal. The ~460ms gap at typical BPM gives SS time to render the cleared state before the reload arrives.

Log evidence of working sequence:
```
[SM] phrase-anchor-clear  deck=1  beat=63  anchor=64
[SM] phrase-anchor        deck=1  beat=64  anchor=64
[SM] autoloop-rearm       deck=1  reason=phrase-anchor  beat=64  ...
```

### Additional session fixes

- **Push loop ordering**: `_smart_drop_tick` / `_phrase_anchor_tick` now execute BEFORE `send_beat` in the beat-boundary block. Deck-load must precede the activation beat event — this matches the arm-lock pattern SS requires.
- **`change=True` on rearm beat**: both tick functions return `bool`; push loop sets `change=True` for the beat event when either fires a rearm. This resets SS's internal beat counter.
- **`_send_direct_autoloop_rearm` BPM finalization**: after `send_autoloop_deck_load`, sends `send_bpm` to all 4 decks and updates `last_sent_bpm`, matching the `_maybe_lock_autoloop_arm` finalization sequence.
- **Smart drop disabled in production** (`RBSS_SMART_DROP=0` in watcher). Only phrase anchor is live.

### Rule for future SS re-anchor work

Any clear+reload pattern for a currently-playing SS track MUST separate the clear and reload by at least 1 beat (one beat boundary tick). Same-tick clear+reload will silently fail.

---

## 8. What NOT to do

- Do not modify `filepath_resolver.py`
- Do not modify `_maybe_lock_autoloop_arm` logic
- Do not add `force_beat` or call `_apply_lighting("autoloop")` from smart drop or
  phrase anchor
- Do not launch the ANLZ drop worker when `RBSS_SMART_REARM_EXPERIMENT=0`
- Do not block the event-loop thread on file I/O (use the background thread pattern)
- Do not add phrase anchor logic for scripted mode
- Do not touch the scripted arm path
- Do not use waveform amplitude as the primary drop source when PSSI exists
- Do not execute smart-drop or phrase-anchor timing from phrase timestamps; return beat
  indices and resolve timing through the beatgrid
- Do not silently override incorrect Rekordbox phrase analysis with waveform guesses
