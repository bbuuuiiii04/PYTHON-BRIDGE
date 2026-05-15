# Runtime Invariants

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-05-12.

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

## Direct Authority

- A direct flag alone must not bypass TL.
- TL is bypassed only when the matching direct readiness condition is currently
  true.
- Direct master startup seed must use two stable valid reads or fall back to TL.
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
- Position priority is fresh `PositionCache`, then fresh `_tl_tc` fallback, then
  existing deck elapsed fallback.
- MTC and TL TC fallback stay retained while direct position can be stale,
  unresolved, or unavailable.
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
- If a history file conflicts with current code or `docs/bridge_design.md`,
  treat the code and current docs as authoritative and the history file as
  stale context.
