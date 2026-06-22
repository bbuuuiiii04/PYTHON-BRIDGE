# Runtime Invariants

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-06-21.

## SoundSwitch Pack Component Boundary

- `soundswitch_pack_models.py` and `soundswitch_project_decoder.py` provide frozen models and strict read-only decode; `soundswitch_pack.py` and `tools/export_soundswitch_pack.py` deterministically publish a canonical 95-artifact pack; `soundswitch_pack_verifier.py` independently verifies it. All are pinned to SoundSwitch 2.10.3 and the canonical UUID/RAVE profile.
- Decode/export must not mutate a source project. Pack publication is deterministic and fail-closed; independent verification rejects inventory, hash, canonicalization, semantic, crosswalk, or source-drift changes, including the F9 one-byte mutation.
- The immutable pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender exist as software-tested components. T7a adds a never-raising config loader and an inert tracked example; config loading is startup/reload work and must never enter `_push_tick`.
- `__main__` does not load the T7a config, and `StateManager` does not drive the pack player. No pack controller, direct-DMX, command, or status path is active. Existing OS2L/MIDI/LED/Govee behavior stays unchanged.
- Direct DMX and physical MIDI output must remain mutually exclusive when later startup wiring lands. Owner-driven Enttec stop sends zero, but process death/`kill -9` can leave the last frame latched; hardware validation remains future work.

## State Ownership

- `StateManager` is the only writer of `DeckState`.
- `StateManager` owns most `OutputState` and publishes copied snapshots for
  status readers.
- Runtime commands that need state mutation should enqueue a `BridgeEvent`.
- `BridgeEvent`s are immutable once enqueued.
- `PositionSnapshot`s are written by `RBMemoryReader` through `PositionCache`.

## SmartPhrasing / Laser Ownership

- `SmartPhrasingEngine` is a pure musical phrasing engine. It emits
  `SmartPhrasingState` intents and does not send OS2L or write `OutputState`.
- `LaserDirector` is scene policy only; it does not send OS2L and does not emit
  MIDI side effects directly.
- `LaserSceneExecutor` owns laser MIDI trigger execution, blackout/cooldown,
  and transition-mask cleanup for laser output.
- `StateManager` remains the coordinator: event-loop owner, suppression-gate
  owner, `DeckState`/`OutputState` owner, and runtime decision/log owner.
- `beat_math.py` helpers remain pure computation utilities (no runtime state or
  I/O side effects).

## LED Look Director Ownership

- `StateManager` owns LED enabled/manual override/emergency blackout latches,
  the sanitized LED runtime status surface, and copied LED color-engine status
  for status readers.
- `LEDLookDirector` is policy-only. It may choose configured looks from manual
  override, emergency blackout, or LED role banks, but it must not perform
  Govee transport I/O.
- `GoveeSceneAdapter.trigger(...)` is the only bridge-side LED output handoff.
  It must remain bounded and non-blocking; worker-side transport owns slow Govee
  API/LAN/cloud behavior.
- Automatic LED role-entry is transition/role-keyed only. It must not emit
  commands every tick or every beat.
- Scripted-track LED automation must stay behind the existing
  `safety.scripted_mode_automation` master switch and the `lighting_mode ==
  "scripted"` gate. Role remapping is a latched policy lookup, not config
  parsing or transport I/O in `_push_tick`.
- Emergency blackout beats manual override; manual override beats automation.
- Phase 8 automatic LED role-entry is dry-run/config-gated. Live automation,
  event-facing use, and Smart Drop blackout coupling require later explicit
  gates.
- `StateManager._push_tick` must not perform LED config parsing, discovery,
  DNS/network calls, sleeps, retries, blocking queue operations, or status
  provider calls.
- LED status must not expose `GOVEE_API_KEY`, full device IDs, raw Govee
  request/response bodies, or headers.

## Direct Authority

- A direct flag alone must not mark a direct path ready.
- Direct authority is active only when the matching direct readiness condition is
  currently true.
- Direct master startup seed must use two stable valid reads or fall back to the
  default startup deck.
- Direct runtime master must ignore the no-master sentinel and remain not-ready
  until the byte maps to a valid Rekordbox deck.
- Direct track load requires direct ANLZ to be enabled so ANLZ-before-load
  ordering remains intact.

## Ordering

- `RBStateReader._tick_deck()` must enqueue `ANLZ_PATH` before
  `TRACK_LOADED`.
- `StateManager._on_track_loaded()` consumes the pending ANLZ path for the new
  `load_gen`.
- Resolver and ANLZ worker results must carry `load_gen`; stale generations are
  ignored.

## Position And Timing

- Memory play bits do not override `DeckState.playing`.
- Position priority is fresh `PositionCache`, then fresh `_tc_anchor` fallback, then
  existing deck elapsed fallback.
- MTC fallback stays retained while direct position can be stale, unresolved, or
  unavailable.
- Deck 2 memory candidates are session-local and must pass behavioral
  validation before publication.
- Absolute heap addresses must not be reused across Rekordbox restarts.

## Output

- Only the active bridge deck drives lighting decisions.
- SoundSwitch/OS2L fanout for autoloop arm/clear/BPM, scripted Phase 0/1,
  smart-transition clears, and live BPM follow is emitted through
  `SoundSwitchEngine.deck_route(...)` and `SoundSwitchEngine.send_*` helpers.
- `StateManager` retains direct `OS2LOutput` calls only for canonical per-tick
  BPM/beat/elapsed fanout and for the autoloop-arm and idle-disarm raw `_sub`
  filepath/play/loop sequences in `_apply_lighting`.
- Scripted/autoloop arms, clears, BPM, beat, elapsed, and beatpos sends must
  cover active, mirror, 3, and 4 as appropriate.
- Enabling scripted-track LED automation must not change SoundSwitch scripted
  arm/clear routing; it only allows the separate LED dispatch path to run after
  the scripted LED policy remap.
- Autoloop arms send an empty SoundSwitch ID.
- `OS2LConnection` owns socket I/O on sender/reconnect threads; the push loop
  should only enqueue sends.

## Phrase Anchor

- `OutputState.phrase_anchor_last_beat` remains StateManager-owned state.
- `StateManager` still owns phrase-anchor sentinel init, stale rebase,
  successful periodic rearm writes, smart-drop/smart-breakdown alignment writes,
  and runtime reset writes.
- `SmartPhrasingEngine` computes periodic phrase-anchor intents from snapshot
  inputs (`phrase_anchor_last_beat`, `phrase_anchor_period_beats`) and does not
  write anchor state.
- `_phrase_anchor_tick` consumes
  `sp_state.phrase_anchor_preclear_requested` and
  `sp_state.phrase_anchor_rearm_requested` after suppression gates.
- `_send_direct_autoloop_rearm(...)` in phrase-anchor flow consumes
  `sp_state.phrase_anchor_target_beat` as the canonical target. `StateManager`
  writes `OutputState.phrase_anchor_last_beat` after a successful rearm, after
  the stale-rebase fallback, and during sentinel bootstrap.

## Live BPM

- `LiveBPMService` publishes only fresh, current-session validated values.
- Direct offset-table BPM is preferred when supported and valid.
- Discovery candidates require movement validation and are invalidated on
  Rekordbox pid/base change.
- `RBSS_LIVE_BPM_DISABLE=1` disables live BPM discovery.
- `RBSS_LIVE_BPM_FOLLOW=0` disables active autoloop follow without removing
  arm-time fallback behavior.

## Historical Docs

- Historical rollout notes are evidence, not authority.
- If a history file conflicts with current code or `docs/architecture/bridge_design.md`,
  treat the code and current docs as authoritative and the history file as
  stale context.
