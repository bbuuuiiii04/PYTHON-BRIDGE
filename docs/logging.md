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
[SS][AUTOLOOP-TICK]      cyan
[SS][LIVE-BPM-PENDING]   yellow
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
  timing_bpm=134.30 arm_bpm=134.30 meta_bpm=134.30
  live_bpm=134.30 live_age_ms=... live_addr=0x.../f32
  follow=on pending_bpm=none file=...
```

BPM names:

- `meta_bpm`: library/ENGINE STATE fallback.
- `live_bpm`: validated Rekordbox displayed BPM from memory.
- `arm_bpm`: BPM selected for the current autoloop timing epoch.
- `timing_bpm`: BPM currently used for outgoing bridge beat timing.

V2 live BPM follow is enabled with `RBSS_LIVE_BPM_FOLLOW=1`. During an active
autoloop, live BPM changes are logged as pending first:

```text
[SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=134.30 target_beat=stabilizing
[SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=134.30 target_beat=129
```

`target_beat=stabilizing` means the live BPM is still moving or has not been
stable for 1.5s. Numeric `target_beat` means the bridge has scheduled the
SoundSwitch BPM send for that absolute beat. Replacement pending logs are
rate-limited while pitch is moving; the periodic `AUTOLOOP-TICK` line carries
the latest pending value between those events.

Apply means the bridge sent BPM to SoundSwitch:

```text
[SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
```

SoundSwitch has been observed to rearm autoloops on BPM sends. Treat
`LIVE-BPM-APPLY` as a phrase-aligned controlled autoloop rearm, not merely an
internal bridge timing update.

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
