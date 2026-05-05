# Autoloop Beatphase Findings

Date: 2026-05-04

Scope: historical investigation and final notes for unscripted/autoloop OS2L
timing behavior in `rb_ss_bridge_v2`.

## Baseline Finding

`AUTOLOOP_BEATS` is currently `16`, and the autoloop arm path sends that loop
length. Changing it from `4` to `16` did not fix the visible 4-beat repeat,
which points away from loop length as the primary cause.

Baseline logs showed:

- Autoloop armed once for the current unscripted track.
- No repeated autoloop-arm spam during normal playback.
- Absolute beat advanced normally: `abs_beat=4, 8, 12, 16, ...`.
- OS2L beat events still wrapped every 4 beats:
  `wrapped_beat=0,1,2,3,0...`.
- `change=True` was sent every 4 beats:
  `abs_beat=4`, `8`, `12`, `16`, etc.
- Wrapped beat position sent by the old code cycled through `0..4`.

Interpretation: SoundSwitch was receiving `loop=16`, but also receiving timing
signals that looked like a 4-beat reset. This is the best current explanation
for lasers starting in time, drifting/lagging after a few bars, then snapping
back into sync.

## VDJ Capture Comparison

The VDJ/SoundSwitch capture showed `get_beatpos` and `beat.pos` advancing
continuously beyond 4, including values in the hundreds. That differs from the
bridge baseline, which wrapped both the beat position and beat event position
every 4 beats.

## Instrumentation Added

Files changed:

- `state_manager.py`: added autoloop/live-BPM diagnostics:
  - `[SS][AUTOLOOP-ARM]`
  - `[SS][AUTOLOOP-TICK]`
  - `[SS][LIVE-BPM-PENDING]`
  - `[SS][LIVE-BPM-APPLY]`
- `osl_output.py`: added `[SS][deck-load]` to log the actual outgoing BPM and
  loop/play state during `send_deck_load()`.

These logs record arm-time BPM source, current timing BPM, metadata BPM,
validated live BPM, follow state, pending target beat, and deck-load BPM.
`AUTOLOOP-TICK` is rate-limited to periodic status. `LIVE-BPM-PENDING` is
rate-limited while pitch is still moving. The old per-beat autoloop logging has
been removed from normal INFO output.

## Test A Applied

Test A changes autoloop only:

- `send_elapsed(..., beatpos)` now sends absolute beat position as
  `beatpos_out` when `os.lighting_mode == "autoloop"`.
- Scripted/non-autoloop behavior still uses the old wrapped beat position.
- `send_beat()` was intentionally left unchanged for isolation.

Log-only validation passed. Example output:

```text
abs_beat=5.2303  wrapped_pos=1.2303  beatpos_out=5.2303
abs_beat=9.6048  wrapped_pos=1.6048  beatpos_out=9.6048
abs_beat=16.1655 wrapped_pos=0.1655  beatpos_out=16.1655
abs_beat=20.6548 wrapped_pos=0.6548  beatpos_out=20.6548
abs_beat=27.1808 wrapped_pos=3.1808  beatpos_out=27.1808
```

Conclusion: Test A correctly makes autoloop `get_beatpos` advance continuously
past 4.

## Remaining Suspect

After Test A, beat events still reset every 4 beats:

```text
abs_beat=20 wrapped_beat=0 change=True
abs_beat=24 wrapped_beat=0 change=True
```

This is expected for Test A. If lasers still snap or repeat every 4 beats with
Test A, the next target is beat event semantics.

## Test B Applied

Test B keeps Test A and changes autoloop only:

- `get_beatpos` still sends absolute beat position (`beatpos_out=abs_beat`).
- `send_beat()` now sends absolute beat count as `beat.pos` in autoloop.
- Scripted/non-autoloop behavior still uses the old wrapped beat event position.
- `change=True` is intentionally still tied to the old wrapped 4-beat boundary
  for isolation.

Log-only validation passed. Example output:

```text
abs_beat=28 wrapped_beat=0 beat_out=28 wrapped_pos=0.0000 change=True
abs_beat=31 wrapped_beat=3 beat_out=31 wrapped_pos=3.1403 change=False
abs_beat=32 wrapped_beat=0 beat_out=32 wrapped_pos=0.0107 change=True
abs_beat=36 wrapped_beat=0 beat_out=36 wrapped_pos=0.0085 change=True
abs_beat=40 wrapped_beat=0 beat_out=40 wrapped_pos=0.0000 change=True
```

Conclusion from the log-only check: Test B correctly made autoloop `beat.pos`
advance continuously. It is currently active. The current active state is
Test A + Test B: absolute autoloop `get_beatpos` and absolute autoloop
`beat.pos`, with `change=True` still every 4 beats.

## Next Tests

1. Live laser validation of Test A.
   - Expected if Test A fixes it: lasers stay aligned past 4, 8, 16, 32 beats.
   - Expected if only partially fixed: drift improves, but visible reset/snap
     remains every 4 beats.

2. Live laser validation of Test B.
   - Expected if Test B fixes it: lasers stay aligned past 4, 8, 16, 32 beats
     even though `change=True` still appears every 4 beats.
   - Expected if only partially fixed: visible snap/reset remains every 4 beats,
     pointing at `change=True`.

3. Test C: autoloop-only phrase-safe `change`.
   - Keep absolute `get_beatpos`.
   - Keep absolute `beat.pos`.
   - Set `change=True` every `AUTOLOOP_BEATS` beats, or temporarily always
     `False`, to test whether `change=True` every 4 beats is the reset trigger.

## Current Best Hypothesis

The issue is most likely caused by SoundSwitch interpreting wrapped beat timing
signals as a phrase/autoloop reset. `AUTOLOOP_BEATS=16` is not enough if
`get_beatpos`, `beat.pos`, or `change=True` continue to imply a 4-beat cycle.

## BPM Arming Hypothesis

Observation from live testing: when the physical deck played a 128 BPM original
track pitched to 132 BPM, SoundSwitch's autoloop progress bar appeared to move
at the original/slower BPM. When the same track played at original 128 BPM, the
progress bar matched.

Hypothesis: SoundSwitch may lock autoloop timing from BPM received at deck-load
arm time, or from file/original metadata, rather than honoring later live BPM
updates.

Pass 1 instrumentation added and later normalized:

- `[SS][AUTOLOOP-ARM]` logs timing source, `timing_bpm`, `arm_bpm`, and
  `meta_bpm`.
- `[SS][deck-load]` logs the actual outgoing `bpm_out`, `meta_bpm`,
  `fallback_bpm`, loop state, and play state for each `send_deck_load()`.
- `[SS][AUTOLOOP-TICK]` periodically logs `timing_bpm`, `arm_bpm`, `meta_bpm`,
  `live_bpm`, follow state, and pending state.

Compare these lines for the same track at original BPM and pitched BPM:

```text
[SS][AUTOLOOP-ARM] ... timing_bpm=... arm_bpm=... meta_bpm=...
[SS][deck-load] ... bpm_out=... meta_bpm=... fallback_bpm=... loop=16
[SS][AUTOLOOP-TICK] ... timing_bpm=... arm_bpm=... meta_bpm=... live_bpm=...
```

If pitched playback shows deck-load `bpm_out` at the original BPM while
autoloop ticks show the live pitched BPM, the arm-time BPM mismatch is confirmed.

Pass 1 result:

- Original-BPM run was polluted by resolver overwrite:
  - title lookup resolved the intended track at `bpm=128.0`;
  - later lsof resolved `Click Sound 01 Electronic.wav` at `bpm=0.0`;
  - autoloop armed that wrong filepath with `bpm_out=0.00`.
- Pitched run later armed `Click Sound 01 Electronic.wav` with
  `bpm_arg=132.00`, `meta_bpm=132.00`, and deck-load `bpm_out=132.00` on all
  four SS deck slots.

Interpretation: the simple arm-time BPM mismatch hypothesis is not supported
for the pitched run that armed at 132. If SoundSwitch still runs its progress
bar at the original/slower rate after receiving deck-load `bpm_out=132.00`,
then it may ignore OS2L BPM for autoloop progress once the filepath is loaded,
or derive timing from the audio/file metadata internally. The lsof overwrite is
also a real separate bug: stale/wrong lsof results can replace a correct
title/ANLZ resolution and cause autoloop to arm the wrong file and BPM.

## Relation To Live BPM Probe

The live BPM probe evidence became the production `LiveBPMService` path. The
runtime service remains read-only and fail-closed:

- It attaches read-only to the current Rekordbox pid/base.
- It scans/watches candidates using ENGINE STATE/library BPM only as hints.
- It promotes only candidates that move correctly during observed pitch changes.
- It invalidates everything on Rekordbox restart.
- It never hardcodes candidate addresses.
- It returns no BPM if validation is absent or stale.

Relevant standalone probe capabilities remain useful for investigation:

- `validate` can find BPM-shaped memory candidates, watch them during a
  controlled pitch move, and cache only candidates that pass for the current
  Rekordbox pid/base/deck.
- `validate --monitor-cache-deck <deck>` can monitor another deck's cached
  candidates during a target-deck validation window.
- `cache-monitor` can watch current-session cached candidates for stability
  while the operator moves the other deck.
- `--save-traces` can preserve full sample traces for offline review.

Runtime behavior:

- At autoloop arm, StateManager snapshots validated live BPM when available and
  otherwise falls back to `d.meta.bpm`.
- V1 default freezes active autoloop timing to the arm snapshot.
- V2, enabled with `RBSS_LIVE_BPM_FOLLOW=1`, watches live BPM during an active
  autoloop. If it changes, stabilizes for 1.5s, and reaches a phrase-safe
  absolute beat (`9, 17, 25, ...`), the bridge sends BPM to SoundSwitch.
- Live testing showed SoundSwitch rearms autoloops on BPM sends. Therefore V2
  intentionally treats the phrase-boundary BPM send as a controlled rearm.

Observed V2 acceptance:

```text
[SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=134.30 target_beat=129
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
[SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ... pending_bpm=none
```
