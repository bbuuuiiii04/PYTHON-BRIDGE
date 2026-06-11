# Current Architecture

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-06-11. Treat code as the source of
truth; `docs/architecture/bridge_design.md` is the detailed companion reference.

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

These defaults are present in `scripts/ss_bridge_watcher.sh`.

## Runtime Subsystems

| Subsystem | Authority status | Hot path | Thread ownership | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| `StateManager` | live authority after source selection | yes | owns `DeckState`, most `OutputState`, lighting state | `BridgeEvent`s, `PositionCache`, `LiveBPMService` | OS2L sends, snapshots |
| `RBStateReader` | guarded live authority for ANLZ, play/pause, track load, runtime master when enabled and ready | yes | `rb-state-reader` thread | Rekordbox offset-table chains | authoritative events and readiness callbacks |
| `RBMemoryReader` | live position authority when direct chain or validated memory snapshot is fresh; fallback scanner retained | yes | memory reader thread writes `PositionCache` | Rekordbox memory, offset tables, vmmap | `PositionSnapshot`s, `RB_RESTARTED` |
| `MTCReader` | position fallback only | yes | MTC thread | IAC Bus 1 MTC | `TC_UPDATE` |
| `LiveBPMService` | direct displayed-BPM authority when fresh and valid; metadata fallback otherwise | yes | live BPM thread owns BPM validation state | Rekordbox BPM chains, discovery, hints | live BPM snapshots |
| `FilepathResolver` | auxiliary metadata authority for loaded tracks | async hot path after load | short-lived worker threads | ANLZ path, DB, lsof, audio tags | `FILEPATH_RESOLVED`, `ANLZ_DATA` |
| `SmartPhrasingEngine` | pure musical phrasing engine (no OS2L sends, no `OutputState` writes) | yes | called by `StateManager` thread | per-tick `SmartPhrasingSnapshot` | immutable `SmartPhrasingState` intents |
| `LaserDirector` | laser scene/role policy only | yes | called by `StateManager` thread | `LaserContext` (including `SmartPhrasingState`) | `LaserSceneDecision` |
| `LaserSceneExecutor` | laser trigger execution only (MIDI/blackout/cooldown/transition-mask) | yes | called by `StateManager` thread | `LaserSceneDecision`, `LaserContext` | MIDI triggers and executor blackout state |
| `SoundSwitchEngine` | SoundSwitch output-intent fanout helper | yes | called by `StateManager` thread | active deck routing and send intents from `StateManager` | routed OS2L sends for scripted/autoloop/smart-transition/live-BPM-follow helpers |
| `beat_math.py` | pure beat and beatgrid math helper | yes | called in hot path from `StateManager` | elapsed ms, bpm, beatgrid markers | computed beat positions / target elapsed |
| `OS2LConnection` / `OS2LOutput` | output transport authority | yes | sender/reconnect threads own sockets | SoundSwitch DNS-SD, send queue | TCP OS2L messages |
| `StatusWriter` / `CommandReader` | auxiliary operator status/control | auxiliary | status/command threads | snapshots, command JSONL | status JSON, command side effects |
| `ValidationRunner` | diagnostic only | auxiliary | daemon validation thread when requested | runtime snapshots and process checks | validation result |

## Authority Model

`StateManager` does not perform broad event-source arbitration. Source
selection happens before events reach it:

- `__main__.py` builds `RBStateReader.authoritative_kinds` from enabled direct
  flags.
- `RBStateReader` reports per-signal readiness.
- OSC `/bridge/active_deck` is bypassed only while direct master is currently
  ready.

This is fail-closed. Unsupported versions, attach failures, unreadable chains,
sentinels, stale data, and unwarmed transport inference leave the corresponding
direct path inactive while MTC/current state fallbacks continue where available.

## Signal Flow

1. Startup creates the event queue, OS2L connection, resolver, live BPM service,
   status/command helpers, `StateManager`, optional `RBStateReader`,
   `RBMemoryReader`, `MTCReader`, and OSC listener.
2. Startup master is seeded from direct master only when
   `RBSS_MASTER_SEED_DIRECT=1` and two direct reads are stable and valid;
   otherwise deck 1 is the default startup deck.
3. MTC can publish `TC_UPDATE` as an active-deck position fallback.
4. Direct ANLZ, track-load, play/pause, and master events flow from
   `RBStateReader` only when configured as authoritative.
5. `StateManager` resolves tracks, selects scripted or autoloop lighting, and
   sends mirrored OS2L updates to active, mirror, 3, and 4 through
   `SoundSwitchEngine`.

## Smart-Transition Architecture

- `SmartPhrasingEngine` computes smart-drop, smart-breakdown, and phrase-anchor
  intents from `SmartPhrasingSnapshot` each tick.
- `StateManager` consumes those intents in `_smart_drop_tick`,
  `_smart_breakdown_tick`, and `_phrase_anchor_tick`; suppression gates remain
  in `StateManager`, which also owns `OutputState` writes and transition logs.
- `StateManager` intentionally remains the owner/writer of
  `OutputState.phrase_anchor_last_beat` for periodic anchor runtime state.
- `SoundSwitchEngine` performs canonical OS2L/SoundSwitch deck-route fanout for
  the sends requested by `StateManager`.
- `LaserDirector` consumes `SmartPhrasingState` through `LaserContext` to make
  scene policy decisions only.
- `LaserSceneExecutor` consumes those decisions and handles laser MIDI output,
  role cooldown/rotation, blackout latching, and transition-mask cleanup.

## Current Direct Paths

| Path | Current status |
| --- | --- |
| B1 ANLZ | Direct when path is readable for the deck. |
| B2 Position | Direct versioned position chain when valid; ObjC scan and MTC remain fallbacks. |
| C1 Startup master seed | Direct only after two stable valid reads; otherwise deck 1 default startup. |
| B3 Play/pause | Direct movement-derived events after warmup/evidence. |
| B4 Track load | Direct full-title load only when direct ANLZ is enabled and title memory is readable. |
| B5 Scripted routing | Direct from `FILEPATH_RESOLVED` by SSID, show-file SSID, or unique filepath. |
| B6 Runtime master | Direct `MASTER_CHANGED` when direct master byte is readable and valid; OSC remains a bridge control input. |
| Live BPM | Direct offset-table BPM when fresh and valid; discovery and metadata fallback remain. |

## Documentation Map

Use `docs/architecture/doc_index.md` for the full classification. In short:

- Current truth: `README.md`, this file, `docs/architecture/bridge_design.md`,
  `docs/architecture/runtime_invariants.md`.
- Offline ANLZ energy tooling: `docs/research/anlz_energy_project.md`,
  `docs/research/anlz_waveform_tag_inventory.md`,
  `docs/validation/anlz_energy_evaluation_guide.md`.
- Current supporting details: `docs/subsystems/`.
- Laser policy/scene detail: `docs/architecture/laser_director_design.md`.
- Active and deferred plans: `docs/plans/`.
- Agent prompts and review prompts: `docs/prompts/`.
- Validation evidence: `docs/validation/`.
- Rollout history: `docs/history/`.
