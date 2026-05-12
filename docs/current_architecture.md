# Current Architecture

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-05-12. Treat code as the source of
truth; `docs/bridge_design.md` is the detailed companion reference.

## System Shape

The bridge has one central authority thread: `StateManager`. It owns `DeckState`
and most `OutputState`, drains `BridgeEvent`s, samples `PositionCache`, and
coordinates SoundSwitch output call ordering through `SoundSwitchEngine`.
`StateManager` still emits canonical per-tick BPM/beat/elapsed fanout directly
on `OS2LOutput`. Other threads do not mutate deck state directly; they publish
immutable events or thread-safe snapshots.

The current live launcher defaults enable guarded direct B1-B6 paths:

```text
RBSS_LIVE_BPM_FOLLOW=1
RBSS_ANLZ_DIRECT=1
RBSS_POS_CHAIN_DIRECT=1
RBSS_MASTER_SEED_DIRECT=1
RBSS_MASTER_DIRECT=1
RBSS_PLAY_DIRECT=1
RBSS_TRACK_LOAD_DIRECT=1
RBSS_SCRIPTED_DIRECT=1
RBSS_SCRIPTED_SHOWFILE_DIRECT=1
RBSS_SMART_REARM_EXPERIMENT=1
RBSS_SMART_DROP=1
RBSS_SMART_BREAKDOWN=1
```

These defaults are present in both `scripts/ss_bridge_watcher.sh` and the live
`/Users/bbui/ss_bridge_watcher.sh`.

## Runtime Subsystems

| Subsystem | Authority status | Hot path | Thread ownership | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| `StateManager` | live authority after source selection | yes | owns `DeckState`, most `OutputState`, lighting state | `BridgeEvent`s, `PositionCache`, `LiveBPMService` | OS2L sends, snapshots |
| `RBStateReader` | guarded live authority for ANLZ, play/pause, track load, runtime master when enabled and ready | yes | `rb-state-reader` thread | Rekordbox offset-table chains | authoritative events and readiness callbacks |
| `RBMemoryReader` | live position authority when direct chain or validated memory snapshot is fresh; fallback scanner retained | yes | memory reader thread writes `PositionCache` | Rekordbox memory, offset tables, vmmap | `PositionSnapshot`s, `RB_RESTARTED` |
| `TLLogTailer` | fallback for direct-retired signals; live source for ENGINE BPM/TC fallback | yes | tailer thread | TimecodeLink log and ENGINE STATE | TL/ENGINE `BridgeEvent`s |
| `MTCReader` | position fallback only | yes | MTC thread | IAC Bus 1 MTC | `TC_UPDATE` |
| `LiveBPMService` | direct displayed-BPM authority when fresh and valid; metadata fallback otherwise | yes | live BPM thread owns BPM validation state | Rekordbox BPM chains, discovery, hints | live BPM snapshots |
| `FilepathResolver` | auxiliary metadata authority for loaded tracks | async hot path after load | short-lived worker threads | ANLZ path, DB, lsof, audio tags | `FILEPATH_RESOLVED`, `ANLZ_DATA` |
| `SoundSwitchEngine` | SoundSwitch output behavior and canonical deck-route fanout helper | yes | called by `StateManager` thread | active deck routing, arm/clear/follow intents from `StateManager` | routed OS2L sends for scripted/autoloop/smart-transition/live-BPM-follow helpers |
| `OS2LConnection` / `OS2LOutput` | output transport authority | yes | sender/reconnect threads own sockets | SoundSwitch DNS-SD, send queue | TCP OS2L messages |
| `StatusWriter` / `CommandReader` | auxiliary operator status/control | auxiliary | status/command threads | snapshots, command JSONL | status JSON, command side effects |
| `ValidationRunner` | diagnostic only | auxiliary | daemon validation thread when requested | runtime snapshots and process checks | validation result |

## Authority Model

`StateManager` does not choose between TL and direct sources broadly. Source
selection happens before events reach it:

- `__main__.py` builds `RBStateReader.authoritative_kinds` from enabled direct
  flags.
- `RBStateReader` reports per-signal readiness.
- `TLLogTailer` bypasses TL events only when the matching direct path is both
  enabled and currently ready.
- OSC `/bridge/active_deck` is bypassed only while direct master is currently
  ready.

This is fail-closed. Unsupported versions, attach failures, unreadable chains,
sentinels, stale data, and unwarmed transport inference fall back to the
existing TL/MTC/current path.

## Signal Flow

1. Startup creates the event queue, OS2L connection, resolver, live BPM service,
   status/command helpers, `StateManager`, TL tailer, optional `RBStateReader`,
   `RBMemoryReader`, `MTCReader`, and OSC listener.
2. Startup master is seeded from direct master only when
   `RBSS_MASTER_SEED_DIRECT=1` and two direct reads are stable and valid;
   otherwise TL ENGINE/config state wins.
3. Fresh ENGINE STATE deck metadata is replayed through normal
   `TRACK_LOADED`/`BPM_UPDATE`/`TC_UPDATE`/`PLAY` events.
4. Direct ANLZ, track-load, play/pause, and master events flow from
   `RBStateReader` only when configured as authoritative.
5. TL remains present and emits fallback events whenever the matching direct
   readiness callback is false.
6. `StateManager` resolves tracks, selects scripted or autoloop lighting, and
   sends mirrored OS2L updates to active, mirror, 3, and 4 through
   `SoundSwitchEngine`.

## Current Direct Paths

| Path | Current status |
| --- | --- |
| B1 ANLZ | Direct when path is readable for the deck; TL ANLZ remains fallback. |
| B2 Position | Direct versioned position chain when valid; ObjC scan, MTC, and TL TC remain fallbacks. |
| C1 Startup master seed | Direct only after two stable valid reads; otherwise TL ENGINE/config state. |
| B3 Play/pause | Direct movement-derived events after warmup/evidence; TL play/pause remains fallback. |
| B4 Track load | Direct full-title load only when direct ANLZ is enabled and title memory is readable; TL load remains fallback. |
| B5 Scripted routing | Direct from `FILEPATH_RESOLVED` by SSID, show-file SSID, or unique filepath; TL OSC path remains available when disabled. |
| B6 Runtime master | Direct `MASTER_CHANGED` when direct master byte is readable and valid; TL/OSC remain fallback. |
| Live BPM | Direct offset-table BPM when fresh and valid; discovery and metadata/ENGINE fallback remain. |

## Documentation Map

Use `docs/doc_index.md` for the full classification. In short:

- Current truth: `README.md`, this file, `docs/bridge_design.md`,
  `docs/runtime_invariants.md`.
- Current supporting details: `docs/subsystems/`.
- Validation evidence: `docs/validation/`.
- Rollout history and stale implementation prompts: `docs/history/`.
