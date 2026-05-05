# rb_ss_bridge_v2 logging

The bridge keeps normal logs readable by default:

```text
14:23:45 [INFO   ] TRACK_LOADED title=Track Name load_gen=12 [deck=1 src=tl_log tr:a3f91c]
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
| green | Lifecycle applied / successful action |
| cyan | Periodic status / routing / currently active state |
| yellow | Pending / fallback / degraded-but-working |
| orange | Retry / suspicious / recoverable failure |
| red | Stop / stale / crash-risk / action needed |
| magenta | Scripted-show lifecycle |
| grey | Debug noise |

Examples:

```text
[SS][AUTOLOOP-ARM]       green
[SS][AUTOLOOP-ARM-PENDING] yellow
[SS][AUTOLOOP-ARM-LOCKED]  green
[SS][AUTOLOOP-TICK]      cyan
[SS][LIVE-BPM-APPLY]     green
[LBPM][SCAN|CURRENT]     cyan
[LBPM][ATTACH|VALIDATED] green
[LBPM][INVALID|ERROR]    orange
[RBMEM][SCAN|CANDIDATE]  cyan
[RBMEM][VALIDATED]       green
[RBMEM][REJECT|INVALID]  orange
```

## Autoloop And Live BPM Diagnostics

Normal autoloop status is periodic, not per beat:

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
pitch changes during playback. The periodic `AUTOLOOP-TICK` line shows whether
active follow is on or disabled.

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

Master-transition autoloop arms use the same next-beat re-lock signal without
delaying deck load:

```text
[SS][AUTOLOOP-MASTER-RELOCK] deck=2 source=auto-detect timing=immediate next_beat_change=true
```

After this line, the first autoloop beat event sends absolute `beat.pos` with
`change=True` once, then returns to steady `change=False`.

Autoloop arm phrase-lock is separate from live BPM follow. Normal track-start
autoloop arms fire immediately, then the push loop schedules one more BPM send
at the next 16-beat phrase boundary:

```text
[SS][AUTOLOOP-ARM-PENDING] deck=1 current_beat=5.2 target_phrase_beat=16
[SS][AUTOLOOP-ARM-LOCKED] deck=1 beat=16 bpm=120.50
```

Master-switch autoloop arms are phrase-window aware by default. Set
`RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` to disable this behavior. If the switch
lands near the start of a phrase, the bridge arms immediately and logs
`timing=immediate` with an anchored one-shot `change=True`. If it lands later in
the phrase, the bridge delays SoundSwitch deck-load/autoloop activation until
the next phrase target:

```text
[SS][AUTOLOOP-MASTER-ARM-PENDING] deck=2 mirror=1 current_beat=5.2 target_phrase_beat=16 ...
[SS][AUTOLOOP-MASTER-ARM-LOCKED] deck=2 beat=16 bpm=120.50 ...
[SS][AUTOLOOP-MASTER-RELOCK] deck=2 source=auto-detect timing=delayed next_beat_change=true
```

Live testing showed delayed activation did not fix the master-transition phrase
offset by itself; the default behavior pairs phrase-window activation with the
one-shot `change=True` re-lock at the selected arm point.

With `AUTOLOOP_ARM_PHRASE_BEATS=16`, phrase-lock targets are `(16 * n)`:
`16, 32, 48, ...`. This is separate from `AUTOLOOP_BEATS`, which controls loop
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

with log_event_scope("track_load", deck=1, source="tl_log") as trace_id:
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
