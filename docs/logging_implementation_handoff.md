# Logging Implementation Handoff

This records the practical logging updates made for `rb_ss_bridge_v2`.

## Implemented

- Added `LoggingManager` in `rb_ss_bridge_v2/logging_manager.py`.
- Wrapped the bridge event queue so `BridgeEvent.payload` gets:
  - `__trace_id` for following a call chain.
  - `__enqueue_mono` for enqueue-to-process latency.
- Updated `StateManager` INFO logs for high-signal events:
  - `TRACK_LOADED`
  - `FILEPATH_RESOLVED`
  - `MASTER_CHANGED`
  - `SCRIPTED_ARM`
- Added bounded log stats for:
  - event counts
  - transition counts
  - latency percentiles
  - error summaries
  - recent event samples
- Added remediation hints for common errors such as OSC listener failures,
  RB restarts, memory stale states, queue-full conditions, and lsof failures.
- Added optional JSON log output with `BRIDGE_LOG_JSON=1`.
- Added a live logging control file:
  - default path: `/tmp/rb_ss_bridge_v2_logging.json`
  - override path: `BRIDGE_LOG_CONTROL=/path/to/file.json`
  - bridge checks the file about once per second and reloads changes.
- Control file supports:
  - `debug`: `true` or `false`
  - `modules`: logger names to keep visible
  - `decks`: deck numbers to keep visible
  - `events`: event names to keep visible
  - `levels`: per-logger level overrides
  - `anomalies`: enable anomaly tagging
- `SIGHUP` remains available as a manual reload fallback.

## Noise Reduction

- `tc_update` latency warnings now trigger at `250ms`.
- Other event latency warnings now trigger at `50ms`.
- Link BPM logs are rate-limited:
  - first BPM/peer observation
  - peer count changes
  - BPM changes by at least `0.5`
  - otherwise at most once every `10s`

## ADHD-Friendly Color System

The color formatter is now attention-based:

- Red: action needed now, such as RB restart, memory stale, forcing stop, OSC
  listener failure, or OS2L send error.
- Orange: degraded but still running, such as event latency, attach failure,
  queue full, connect failure, or port error.
- Yellow: retry/fallback/no peers/cooldown.
- Cyan: deck routing and master-deck decisions.
- Magenta: scripted show lifecycle.
- Green: successful user-facing state, including `TRACK_LOADED`,
  `FILEPATH_RESOLVED`, playing/resume, attached, connected, autoloop, and active
  deck status lines beginning with `► D`.
- Grey: diagnostic/status noise such as Link BPM, timecode/MTC, event processed
  lines, event relation lines, and scripted registry logs.

## Practical Debug Use

Normal operation should be readable at INFO. Use the control file for targeted
debug without restarting:

```json
{
  "debug": true,
  "events": ["track_loaded", "filepath_resolved", "scripted_arm"],
  "levels": {
    "state_manager": "DEBUG",
    "filepath_resolver": "DEBUG"
  }
}
```

Turn full debug back off:

```json
{
  "debug": false
}
```

For show operation, prefer targeted debug over global debug so the INFO screen
stays readable.

