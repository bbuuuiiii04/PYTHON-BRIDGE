# Bridge Operator Dashboard v1

## Scope

V1 adds a local, read-mostly observability/control layer for `rb_ss_bridge_v2`.
The bridge process owns runtime state and writes a JSON snapshot under `/tmp`.
The macOS menu bar app is a custom AppKit status item that reads that snapshot
and appends high-level commands to a local JSONL command file.

There is no network server in this pass. The dashboard is not a web UI and is
not rumps.

## V1 Commitments

- Read-only by default.
- Status snapshots are written by the bridge process to
  `/tmp/rb_ss_bridge_v2_status.json`.
- Commands are appended by the menu app to
  `/tmp/rb_ss_bridge_v2_commands.jsonl`.
- Live/send-capable commands require bridge-owned temporary arming.
- The bridge clamps arm TTL to a short maximum and ignores caller-provided
  long-lived expirations.
- The OS2L mirror is a queue-boundary mirror with honest outcomes:
  `queued`, `queue_full_drop`, `no_socket_drop`, `send_error`, `sent_live`,
  and `simulated`.
- Validation uses contextual states, not only pass/fail:
  `pass`, `warn`, `fail`, `warming`, and `not_applicable`.

## Implemented V1 Slice

### AppKit Menu

`/Users/bbui/bridge_menubar.py` is a direct AppKit status item. It preserves the
existing manual start/stop behavior:

- start via `/Users/bbui/ss_bridge_watcher.sh`
- stop watcher, bridge process, manual launchctl job, and monitor terminal
- keep one menu app instance

The dropdown shows compact live rows:

- bridge/process/armed state
- SoundSwitch connection and queue health
- Deck 1/Deck 2 play/load state
- live BPM status
- autoloop/scripted summary
- validation counts
- mirror state, rate, and last packet outcome

Actions:

- `Arm Live Actions`
- `Run Validation`
- `Toggle Mirror`
- `Start Capture` / `Stop Capture`

### Runtime Status

`runtime_status.py` provides:

- `StatusWriter`: writes an atomic JSON snapshot every 500 ms.
- `CommandReader`: tails the command JSONL file, validates commands, truncates
  stale commands on bridge startup, creates the file mode `0600`, and clamps arm
  lifetime to 30 seconds.

### State Snapshot

`StateManager.snapshot()` returns only a copied snapshot published by the
StateManager thread. It does not read live `DeckState` or `OutputState` from a
foreign thread.

Snapshot fields include active deck, lighting mode, deck play/load state,
autoloop arm fields, pending scripted phase-2 arm state, drop-cut state, and
basic BPM/scripted identifiers.

### OS2L Mirror

`os2l_mirror.py` records bounded packet history and optional JSONL captures.
`OS2LConnection` records at the connection boundary:

- enqueue accepted: `queued`
- queue full: `queue_full_drop`
- sender found no socket: `no_socket_drop`
- socket send failed: `send_error`
- socket send succeeded: `sent_live`

The menu intentionally shows only the compact mirror summary in v1.

### Validation

`validation_runner.py` runs in the bridge process and reports:

- bridge singleton
- SoundSwitch connection
- Rekordbox process
- memory freshness per deck
- live BPM state per deck
- autoloop readiness/state
- scripted registry context
- OS2L queue health

Validation results are displayed in the status snapshot and menu only. There is
no mandatory report file in v1.

## Deferred

- Full packet table UI.
- Event-level rehearsal replay with deterministic injected clock.
- Live packet replay.
- Raw OS2L injector integration or gating changes.
- Any network API.
