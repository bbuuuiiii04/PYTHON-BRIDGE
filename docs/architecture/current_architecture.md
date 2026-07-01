# Current Architecture

Status: CURRENT AUTHORITATIVE

Audited against implementation commit `6c51eb8` on 2026-06-29. Treat code as the source of
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

The SoundSwitch pack lane contains frozen source models, strict read-only
decode, deterministic canonical-pack export, dynamic saved-project inventory
reconciliation, independent verification, an
immutable pack loader/player, a MIDI-input adapter, an output-backend
abstraction, an Enttec frame sender, a validated default-off config loader,
startup wiring, an atomic `PackRuntime`, validate-first runtime controls, a
StateManager scripted-frame driver, provider-free copied operational status, and
a default-off Art-Net U1 truth-check sink for software/wire comparison against
SoundSwitch U0. Truth-check mode is validation-only: it does not open Enttec,
does not make the bridge physical lighting authority, and keeps production pack
output software-zero while SoundSwitch is connected.
The old exact-count closure snapshot is proof-only; live export accepts
internally consistent saved edits. F9 and F10 proof seams remain covered.

This lane remains subordinate to existing bridge authority. `__main__` loads
the optional config and chooses one physical laser backend before workers start;
`StateManager` reads authoritative deck state, is the sole per-tick
`submit_frame` owner, and publishes one fresh software-intent status dict from the
already-rendered frame before submission. Status reads copy that dict without
calling runtime/backend providers. Ordinary drain/tick/snapshot exceptions skip
only the failed instant with a bounded log, at most one direct pack ZERO frame,
and the normal 200 Hz throttle preserved; process-control exceptions still
escape. Blocking load/verify/serial work remains on startup or the command
thread. Absent/disabled config preserves legacy MIDI;
dry-run/none opens neither physical output path. Sender delivery health,
native Autoloop phase calibration, live runtime validation, and hardware
validation remain open. Native Autoloop pack output is implemented in software
through the existing pack player/submit path with bridge-owned phase; when a
fresh scene edge is absent, the pack driver may seed from the executor's latched
active Autoloop scene. The old T7d six-scenario gate no longer blocks it.

## Runtime Subsystems

| Subsystem | Authority status | Hot path | Thread ownership | Inputs | Outputs |
| --- | --- | --- | --- | --- | --- |
| `StateManager` | live authority after source selection | yes | owns `DeckState`, most `OutputState`, lighting state | `BridgeEvent`s, `PositionCache`, `LiveBPMService` | OS2L sends, copied snapshots |
| `active_deck_resolver.py` | pure show-deck authority policy when mixer authority is enabled | yes | stateless pure function plus caller-owned stability state | Deck 1/2 playing state, decoded upfader/LOW, `rb_master_deck`, validity/freshness | `ActiveDeckDecision`; no I/O |
| `RBStateReader` | guarded live authority for ANLZ, play/pause, track load, runtime master when enabled and ready | yes | `rb-state-reader` thread | Rekordbox offset-table chains | authoritative events and readiness callbacks |
| `RBMemoryReader` | live position authority when direct chain or validated memory snapshot is fresh; fallback scanner retained | yes | memory reader thread writes `PositionCache` | Rekordbox memory, offset tables, vmmap | `PositionSnapshot`s, `RB_RESTARTED` |
| `MTCReader` | position fallback only | yes | MTC thread | IAC Bus 1 MTC | `TC_UPDATE` |
| `LiveBPMService` | direct displayed-BPM authority when fresh and valid; metadata fallback otherwise | yes | live BPM thread owns BPM validation state | Rekordbox BPM chains, discovery, hints | live BPM snapshots |
| `FilepathResolver` | auxiliary metadata authority for loaded tracks | async hot path after load | short-lived worker threads | ANLZ path, DB, lsof, audio tags | `FILEPATH_RESOLVED`, `ANLZ_DATA` |
| `SmartPhrasingEngine` | pure musical phrasing engine (no OS2L sends, no `OutputState` writes) | yes | called by `StateManager` thread | per-tick `SmartPhrasingSnapshot` | immutable `SmartPhrasingState` intents |
| `LaserDirector` | laser scene/role policy only | yes | called by `StateManager` thread | `LaserContext` (including `SmartPhrasingState`) | `LaserSceneDecision` |
| `LaserSceneExecutor` | laser trigger execution only (MIDI/blackout/cooldown/transition-mask) | yes | called by `StateManager` thread | `LaserSceneDecision`, `LaserContext` | MIDI triggers and executor blackout state |
| `DropLifecycle` | pure drop/post-drop role resolver | yes | called by `LaserDirector` on the `StateManager` thread | `SmartPhrasingState` fields and immutable config | `DropResult`; no I/O |
| `LEDLookDirector` | LED room-look policy only | yes | called by `StateManager` thread | manual/emergency LED context and `SmartPhrasingState`-derived role | `LEDLookDecision` |
| `GoveeSceneAdapter` | LED transport queue/worker | no hot-path I/O | public trigger called by `StateManager`; worker owns Govee transport | `LEDLookDecision` | bounded queue commands and sanitized adapter status |
| `SoundSwitchEngine` | SoundSwitch output-intent fanout helper | yes | called by `StateManager` thread | active deck routing and send intents from `StateManager` | routed OS2L sends for scripted/autoloop/smart-transition/live-BPM-follow helpers |
| `LaserPackPlayer` / `PackRuntime` | verified SoundSwitch pack rendering and atomic runtime snapshot | yes, pure/in-memory | player called by `StateManager`; bundle published by command thread | active deck metadata/elapsed, input snapshot, immutable pack | CH1-CH19 frame plus copied software-intent diagnostics |
| `SoundSwitchFrameSender` / Enttec worker | mutually exclusive direct-DMX transport | no blocking hot-path I/O | `StateManager` submits to bounded mailbox; worker owns serial | CH1-CH19 frame + validated fixture map | Enttec DMX Pro packets; owner-driven zero/stop |
| `ArtNetTruthSink` | temporary validation-only U1 shadow output | no blocking hot-path I/O | `StateManager` enqueues rendered frames; worker owns UDP and sidecar writes | CH1-CH19 frame + intent metadata + fixture map | ArtDMX U1 packets and JSONL sidecar evidence; no physical DMX |
| `beat_math.py` | pure beat and beatgrid math helper | yes | called in hot path from `StateManager` | elapsed ms, bpm, beatgrid markers | computed beat positions / target elapsed |
| `OS2LConnection` / `OS2LOutput` | output transport authority | yes | sender/reconnect threads own sockets | SoundSwitch DNS-SD, send queue | TCP OS2L messages |
| `StatusWriter` / `CommandReader` | auxiliary operator status/control | auxiliary | status/command threads | snapshots, command JSONL | status JSON, command side effects |
| `ValidationRunner` | diagnostic only | auxiliary | daemon validation thread when requested | runtime snapshots and process checks | validation result |

## Authority Model

`StateManager` does not perform broad event-source arbitration. Source
selection happens before events reach it:

- `__main__.py` builds `RBStateReader.authoritative_kinds` from enabled direct
  flags.
- When the selected Rekordbox offset version has all named Deck 1/2 mixer
  authority fields, mixer authority is default-on even if the old direct
  ANLZ/play/track-load/master flags are disabled. The same `RBStateReader` is
  reused when other direct paths are also enabled.
- `RBStateReader` reports per-signal readiness.
- OSC `/bridge/active_deck` is a legacy active-deck fallback event only for
  non-mixer-authority operation. It does not update `rb_master_deck`; when mixer
  authority is enabled, invalid/stale fallback is resolver-mediated
  `rb_master_deck` fallback only.
- With mixer authority enabled, `active_deck` is the resolved show deck and may
  be `0` for idle/no audible deck. Rekordbox direct master is retained
  separately as `rb_master_deck` for tie and invalid-mixer fallback cases.

This is fail-closed. Unsupported versions, attach failures, unreadable chains,
sentinels, stale data, and unwarmed transport inference leave the corresponding
direct path inactive while MTC/current state fallbacks continue where available.
Invalid or stale mixer authority is visible in status and falls back only to a
current valid/fresh Rekordbox direct master; it does not synthesize Deck 1.
Under mixer authority, raw Deck A/B direct-master truth is refreshed before the
stale window expires. Raw Deck C/D, sentinel/no-master, and unreadable master
states invalidate `rb_master_deck` instead of aliasing or silently waiting for
staleness. Lost Deck 1/2 transport support emits a fail-closed pause once the
path was previously available.

## Signal Flow

1. Startup loads optional pack config, builds/starts exactly one laser output
   backend when enabled, then creates the event queue, OS2L connection,
   resolver, live BPM service, status/command helpers, `StateManager`, optional
   `RBStateReader`, `RBMemoryReader`, `MTCReader`, and OSC listener.
2. Startup master is seeded from direct master only when
   `RBSS_MASTER_SEED_DIRECT=1` and two direct reads are stable raw Deck A/B
   values. Raw Deck C/D falls back instead of aliasing to bridge Deck 1/2. With
   mixer authority enabled and no direct seed, startup begins idle
   (`active_deck=0`) rather than treating Deck 1 as proven Rekordbox master
   truth. Non-mixer legacy startup can still use the default deck.
3. MTC can publish `TC_UPDATE` as an active-deck position fallback.
4. Direct ANLZ, track-load, play/pause, master, and mixer-state events flow from
   `RBStateReader` only when configured as authoritative. Mixer-authority
   startup always routes `PLAY`, `PAUSE`, `MASTER_CHANGED`, and `MIXER_STATE`
   so resolver support inputs are not dropped by old direct-flag settings.
5. `StateManager` resolves tracks, separates show deck from `rb_master_deck`,
   selects scripted or autoloop lighting from the resolved show deck, and
   sends mirrored OS2L updates to active, mirror, 3, and 4 through
   `SoundSwitchEngine`.
6. When a verified pack runtime is explicitly active, the pack driver submits
   one nonblocking CH1-CH19 frame per tick and publishes copied operational
   status from that same rendered frame. Scripted tracks select scripted pack
   documents; native Autoloops select canonical-pack Autoloops from the
   fresh or executor-latched bridge note and render by Rekordbox beat-grid phase.

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
  scene policy decisions only. Its default-on drop lifecycle uses the LED
  phrase-context gate, a configurable flat impact window, and a capped
  chorus-to-chorus impact count.
- `LaserSceneExecutor` consumes those decisions and handles laser MIDI output,
  role cooldown/rotation, blackout latching, and transition-mask cleanup.
  Drop/post-drop cycles use usable-only shuffle bags and autoloop-tick cadence;
  static scenes remain valid for the initial impact fallback.
- `StateManager` resets director/executor lifecycle state at track/deck/stop/
  resume boundaries. Scripted and idle lighting transitions reset director
  lifecycle state without adding push-loop I/O.

## LED Look Director

- `StateManager` owns LED manual override, emergency blackout, enable,
  automation gate state, and the copied LED color-engine status published for
  status readers.
- Manual LED runtime commands flow through the existing command pattern:
  `CommandReader` parses JSONL, `__main__.py` enqueues `BridgeEvent`s with
  `put_nowait`, and `StateManager._handle_event` owns the durable state.
- Automatic LED role-entry consumes already-computed `SmartPhrasingState` and is
  role-entry/transition keyed. It does not duplicate SmartPhrasing logic and
  must not command every tick or every beat.
- Scripted-track LED automation is an explicit opt-in path: StateManager only
  bypasses the non-autoloop gate when `safety.scripted_mode_automation` is true,
  the deck has a scripted id, and `lighting_mode` is `scripted`; the role is
  remapped through the latched LED `scripted_mode` policy before dispatch.
- `LEDLookDirector` chooses configured LED looks from role banks. LED banks are
  separate from laser banks.
- The live LED drop resolver remains StateManager-owned and unchanged. The pure
  `DropLifecycle` module is parity-tested against its flat-window behavior for
  laser policy reuse; it does not replace LED look-duration or offset handling.
- `GoveeSceneAdapter` keeps public trigger handoff bounded/non-blocking; slow
  Govee transport belongs to its worker.
- Current automatic role-entry is dry-run/config-gated. Live automation,
  event-facing use, and Smart Drop blackout coupling remain later gates.

Supporting LED operator docs:

- `docs/led_look_director_design.md`
- `docs/led_look_mapping_workflow.md`
- `docs/govee_capability_notes.md`

## Current Direct Paths

| Path | Current status |
| --- | --- |
| B1 ANLZ | Direct when path is readable for the deck. |
| B2 Position | Direct versioned position chain when valid; ObjC scan and MTC remain fallbacks. |
| C1 Startup master seed | Direct only after two stable valid raw Deck A/B reads; otherwise mixer-enabled startup begins idle and non-mixer legacy startup uses the old default deck. |
| B3 Play/pause | Direct movement-derived events after warmup/evidence. |
| B4 Track load | Direct full-title load only when direct ANLZ is enabled and title memory is readable. |
| B5 Scripted routing | Direct from `FILEPATH_RESOLVED` by SSID, show-file SSID, or unique filepath. |
| B6 Runtime Rekordbox master | Direct `MASTER_CHANGED` when direct master byte is readable and valid; with mixer authority enabled this updates/refreshes `rb_master_deck`, not `active_deck`, and invalid raw Deck C/D/sentinel/unreadable states clear validity. |
| Mixer active-deck authority | Default-on when named Deck 1/2 mixer offsets exist for the selected version; software-tested for local Rekordbox 7.2.11 chains, hardware/live unvalidated. |
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
