# rb_ss_bridge_v2 logging

Status: CURRENT SUPPORTING

Audited against the current checkout at `7c16fd5` plus current worktree changes on 2026-06-29.

This is the canonical runtime logging guide. Historical implementation context
is retained in `docs/history/logging_implementation_handoff.md`, but current
runtime behavior should be documented here.

Current repo-facing status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

The bridge keeps normal logs readable by default:

```text
14:23:45 [INFO   ] TRACK_LOADED title=Track Name load_gen=12 [deck=1 src=rb_state tr:a3f91c]
14:23:45 [INFO   ] FILEPATH_RESOLVED path=track.mp3 bpm=128.4 ssid=yes latency=35.2ms [deck=1 src=lsof tr:a3f91c]
14:23:45 [INFO   ] SCRIPTED_ARM id=5021 path=track.mp3 elapsed=1234ms bpm=128.4 first_beat=0.0ms [deck=1 tr:a3f91c]
```

Trace IDs are propagated through `BridgeEvent.payload["__trace_id"]` and are
created automatically by the logging queue wrapper. Internal `__*` keys are not
shown in event payload debug logs.

## Runtime Controls

Set these before launch:

```bash
export BRIDGE_LOG_MODULES=state_manager,filepath_resolver
export BRIDGE_LOG_DECKS=1
export BRIDGE_LOG_EVENTS=track_loaded,filepath_resolved,scripted_arm
export BRIDGE_LOG_LEVELS=state_manager=DEBUG,filepath_resolver=DEBUG
export BRIDGE_LOG_ANOMALIES=1
```

For live changes after launch, edit `/tmp/rb_ss_bridge_v2_logging.json`.
The bridge watches this file and reloads it automatically:

```json
{
  "modules": ["state_manager", "filepath_resolver"],
  "decks": [1],
  "events": ["track_loaded", "filepath_resolved", "scripted_arm"],
  "levels": {
    "state_manager": "DEBUG",
    "filepath_resolver": "DEBUG"
  },
  "debug": false,
  "anomalies": true
}
```

Use `BRIDGE_LOG_CONTROL=/path/to/file.json` before launch to choose a different
control file. `SIGHUP` still works as a manual reload fallback, but it is not
needed for normal use.

## Live Watch Preset

For a clean operator watch stream, use the checked-in preset:

```bash
cp docs/setup/logging_live_watch.json /tmp/rb_ss_bridge_v2_logging.json
```

If the bridge is already running with the default control path, the logging
watcher reloads the file automatically. If the bridge was launched with a
different path, copy the preset there or launch with:

```bash
BRIDGE_LOG_CONTROL=/path/to/logging_live_watch.json python -m rb_ss_bridge_v2
```

The preset uses the existing control-file schema only. It filters to the
operator-facing runtime loggers for:

- `runtime_status` for the throttled `[BEAT]` heartbeat.
- `state_manager`, `rb_state`, `rb_memory`, and `live_bpm` for show-deck,
  Rekordbox-master, mixer-authority, and reader visibility.
- `osl_output` and `os2l_injector` for SoundSwitch routing/output visibility.
- `laser_director`, `laser_executor`, and `laser_config` for laser policy and
  MIDI execution visibility.
- `led_look_director`, `led_color_engine`, `led_dispatch_coordinator`,
  `govee_scene_adapter`, `govee_runtime_sender`, `govee_realtime_runner`,
  `govee_realtime_transport`, and `govee_owner_state` for current and
  forward-referenced LED/Govee logger coverage. Current direct emitted lines
  primarily come from dispatch, scene, and realtime runner paths; LED/color
  current state is also visible through `[BEAT]`.

The preset sets these loggers to `INFO` and leaves `debug` and `anomalies`
disabled, so it should not turn on broad DEBUG noise. Errors still pass through
even when their logger is not in the filtered module list.

Healthy watch output should include a throttled `[BEAT]` line with show deck
and separate `rb_master`, BPM, phrase, laser scene, LED look, palette, and RGB
health, plus transition lines such as `[LASER]`, `[LX]`, `[LED] look=...`,
`[RGB] activate`, `[RGB] summary`, `[OS2L]`, and StateManager master/play/load
lines when those subsystems actually emit them. The preset does not send
commands, change runtime state, or validate hardware-visible behavior.

RW-5 pack status failures remain bounded: the status surface and pack-driver error line expose only
an exception category, never a raw message that could contain a path, port, alias, device name, or
identifier. `software_zero_frame` is software intent and must not be interpreted as physical
darkness.

Programmatic output:

```bash
BRIDGE_LOG_JSON=1 python -m rb_ss_bridge_v2
```

Full debug mode is unchanged:

```bash
BRIDGE_DEBUG=1 python -m rb_ss_bridge_v2
python -m rb_ss_bridge_v2 --debug
```

## Color Meaning

Terminal colors follow this convention:

| Color | Meaning |
|-------|---------|
| green | Lifecycle applied / successful action / locked timing |
| cyan | Periodic status / routing / currently active state |
| yellow | Pending / fallback / corrective action / degraded-but-working |
| orange | Late / retry / suspicious / recoverable failure |
| red | Stop / stale / crash-risk / action needed |
| magenta | Scripted-show lifecycle |
| grey | Debug noise |

Examples:

```text
[SS][AUTOLOOP-ARM]       green
[SS][AUTOLOOP-ARM-PENDING] yellow
[SS][AUTOLOOP-ARM-LOCKED]  green
[SS][AUTOLOOP-MASTER-CLEAR] yellow
[SS][AUTOLOOP-MASTER-CORRECTION-PENDING] yellow
[SS][AUTOLOOP-MASTER-ARM-LATE-CORRECTION] orange
[SS][AUTOLOOP-TICK]      cyan
[SS][LIVE-BPM-APPLY]     green
[LBPM][SCAN|CURRENT]     cyan
[LBPM][ATTACH|VALIDATED] green
[LBPM][INVALID|ERROR]    orange
[RBMEM][SCAN|CANDIDATE]  cyan
[RBMEM][VALIDATED]       green
[RBMEM][REJECT|INVALID]  orange
```

Normal INFO output keeps `[LBPM][SCAN]`, `[LBPM][CURRENT]`,
`[RBMEM][SCAN]`, and `[RBMEM][CANDIDATE]` visible because they show whether
decks still need live-BPM or memory validation.

## Autoloop And Live BPM Diagnostics

Normal autoloop status logs at 32-beat phrase boundaries, not every beat and
not on a wall-clock timer:

```text
[SS][AUTOLOOP-TICK] deck=1 elapsed=... beat=...
  timing_bpm=134.30 arm_bpm=134.30 meta_bpm=134.30 grid=PQT2:ANLZ0000.EXT
  live_bpm=134.30 live_age_ms=... live_addr=0x.../f32
  follow=on pending_bpm=none file=...
```

BPM names:

- `meta_bpm`: library/ENGINE STATE fallback.
- `live_bpm`: validated Rekordbox displayed BPM from memory.
- `arm_bpm`: BPM selected for the current autoloop timing epoch.
- `timing_bpm`: BPM currently used for outgoing bridge beat timing.
- `grid`: autoloop phase source. `PQT2:...` or `PQTZ:...` means ANLZ beatgrid
  drove absolute beat position; `fallback` means constant-BPM math was used.

VDJ-like live BPM follow is enabled by default. Set `RBSS_LIVE_BPM_FOLLOW=0`
to disable active follow. During an active autoloop, validated live BPM changes
are sent in place and logged when applied:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
```

BPM apply logs are rate-limited to avoid push-loop spam while still tracking
pitch changes during playback. The phrase-boundary `AUTOLOOP-TICK` line shows
whether active follow is on or disabled.

After LIVE-BPM-APPLY, the next autoloop beat event sends absolute `beat.pos`
with `change=True` once, then returns to steady `change=False`. Live testing
confirmed this one-shot beat re-lock kept SoundSwitch autoloops phrase-synced
during BPM changes.

Apply means the bridge sent BPM to SoundSwitch:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
```

SoundSwitch has been observed to react to BPM sends and beat `change=True`
re-locks. Treat `LIVE-BPM-APPLY` plus the next one-shot change beat as the
validated active-autoloop tempo-change sync path.

Master-transition autoloop arms do not use this beat re-lock path; they clear
SoundSwitch and re-send the filepath/deck-load package on the selected phrase.

Autoloop arm phrase-lock is separate from live BPM follow. Normal track-start
autoloop arms fire immediately, then the push loop schedules one more BPM send
at the next 32-beat phrase boundary:

```text
[SS][AUTOLOOP-ARM-PENDING] deck=1 current_beat=5.2 target_beat=32 ...
[SS][AUTOLOOP-ARM-LOCKED] deck=1 target_beat=32 ... bpm=120.50
```

Master-switch autoloop arms are phrase-window aware by default. Set
`RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` to disable this behavior. If the switch
lands near the start of a phrase, the bridge clears SoundSwitch and arms
immediately. If it lands later in the phrase, the bridge clears SoundSwitch and
delays deck-load/autoloop activation until the next phrase target:

```text
[SS][AUTOLOOP-MASTER-CLEAR] deck=2 mirror=1 source=auto-detect
[SS][AUTOLOOP-MASTER-ARM-PENDING] deck=2 mirror=1 current_beat=5.2 target_beat=32 ...
[SS][AUTOLOOP-MASTER-ARM-LOCKED] deck=2 target_beat=32 target_elapsed_ms=16000 actual_elapsed_ms=16000 ...
```

Live testing showed beatpos/`change=True` tugging moves the progress bar but
does not reliably restart the laser phrase. Master-transition rearm therefore
uses clear plus filepath/deck-load on the selected phrase target.

With `AUTOLOOP_ARM_PHRASE_BEATS=32`, phrase-lock targets are `(32 * n)`:
`32, 64, 96, ...`. This is separate from `AUTOLOOP_BEATS`, which controls loop
length.

## Common Questions

Why did a scripted track arm fail?

Use:

```json
{
  "events": ["track_loaded", "filepath_resolved", "scripted_arm", "scripted_clear"],
  "levels": {
    "state_manager": "DEBUG",
    "scripted_tracks": "DEBUG",
    "filepath_resolver": "DEBUG"
  }
}
```

Look for one trace ID across `TRACK_LOADED`, `FILEPATH_RESOLVED`, and
`SCRIPTED_ARM`. Unknown scripted IDs now log an explicit `SCRIPTED_ARM failed`
line and remediation hints are attached to common errors.

What caused deck switch delay?

Use:

```json
{
  "events": ["master_changed", "play", "pause"],
  "levels": {
    "state_manager": "DEBUG"
  }
}
```

Debug logs include event processing latency and nearby event relationships, for
example `play deck1 45.0ms after pause deck2`.

Did Rekordbox restart?

Search for:

```text
RB_RESTARTED
RBMemoryReader: RB pid ... gone
RBMemoryReader: attached pid=...
```

The memory reader posts `RB_RESTARTED` to the StateManager queue so the stop path
and log trace are tied to the restart detection.

Which constants or offsets matter?

Memory offsets live in `rb_ss_bridge_v2/config.py`. Useful anchors are
`RB_GLOBAL_OFF`, `RB_DECK1_OFF`, `RB_DECK2_OFF`, `RB_POS_OFF`,
`OUTER_INNER1_OFF`, and `OUTER_INNER2_OFF`.

## API

Scoped logs:

```python
from .logging_manager import log_event_scope

with log_event_scope("track_load", deck=1, source="rb_state") as trace_id:
    log.info("TRACK_LOADED title=%s", title)
```

On-demand stats:

```python
from .logging_manager import get_logging_manager

LOG = get_logging_manager()
LOG.log_stats(log)
```

The stats snapshot includes latency percentiles, event counts, transition
counts, error summaries, and the most recent bounded event samples.
