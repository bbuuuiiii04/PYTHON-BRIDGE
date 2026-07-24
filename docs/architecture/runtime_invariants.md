# Runtime Invariants

Status: CURRENT AUTHORITATIVE

Audited against implementation commit `3f4bcc0` on 2026-07-02.

2026-07-03 audit P1 did not change the runtime invariants below. It removed confirmed-unused
internal helpers/events and made smart-drop/breakdown command callback failure reporting explicit.

2026-07-03 audit P2 keeps the pack ZERO precedence while SoundSwitch is connected. It adds copied
status diagnostics only, and does not add blocking/socket/MIDI/file/subprocess I/O to the 200 Hz
push loop.

## SoundSwitch Pack Component Boundary

- `soundswitch_pack_models.py` and `soundswitch_project_decoder.py` provide frozen models and strict read-only decode; `soundswitch_pack.py` and `tools/export_soundswitch_pack.py` deterministically publish the repo-local canonical pack; `soundswitch_pack_verifier.py` independently verifies it with dynamic saved-project inventory reconciliation by default and an explicit proof-only snapshot gate. All are pinned to SoundSwitch 2.10.3 and the canonical UUID/RAVE profile.
- Decode/export must not mutate a source project. Pack publication is deterministic and fail-closed; independent verification rejects inventory, hash, canonicalization, semantic, crosswalk, or source-drift changes, including the F9 one-byte mutation.
- The verifier must stay a runtime-loader superset for pack metadata. It rejects duplicate active controller events, duplicate Static Override slot ownership, invalid Static Override targets on any device, bridge scene target/classification drift, missing Autoloop references, and empty bridge-scene crosswalks before a pack can publish or load.
- The immutable pack loader/player, MIDI-input adapter, backend abstraction, and Enttec sender are software-tested components. The never-raising config loader is used only during startup/reload; config or pack filesystem work must never enter `_push_tick`.
- `__main__` loads optional pack config, chooses one backend, starts verified workers, builds one immutable `PackRuntime`, and wires validate-first commands/status. `StateManager` reads one runtime reference per tick and is the sole `submit_frame` caller.
- `PackRuntime.sanitized_status()` calls no backend/provider. `StateManager` owns the copied pack
  operational snapshot, publishes a fresh dict from the already-rendered frame before submission,
  and returns only a copy to status readers. The 200 Hz path gains no I/O, lock, or worker poll.
- A caught ordinary exception in the 200 Hz drain/tick/snapshot iteration submits at most one direct
  pack ZERO frame, logs a bounded counter, skips only that instant, preserves the normal 200 Hz
  throttle before the next iteration, and keeps the loop alive. If `_push_tick()` already submitted
  ZERO for an inner tick failure, `_run()` does not submit a duplicate. `KeyboardInterrupt`/
  `SystemExit` still pass through; non-pack output lanes are not force-zeroed by this guard.
- `software_zero_frame` is frame equality only and `frame_count` counts attempted normal software
  frames. Neither proves serial delivery, Enttec acceptance, or physical darkness; sender health is
  not inferred.
- Absent/disabled config preserves the legacy MIDI path. Dry-run/none opens no physical pack output. Pack failure falls back to disabled/none, never physical MIDI.
- Direct DMX and physical MIDI output are mutually exclusive at backend construction and port ownership. Owner-driven Enttec stop sends zero, but process death/`kill -9` can leave the last frame latched; hardware validation remains future work.
- Art-Net truth-check output is a temporary validation-only shadow path. It is default-off, requires `RBSS_ARTNET_TRUTH_CHECK=1` plus a valid `RBSS_ARTNET_UNIVERSE`, and `RBSS_ARTNET_UNIVERSE` alone must not emit. Truth-check may construct pack rendering without Enttec by using a sender-free pack backend plus `ArtNetTruthSink`; it must not open serial/Enttec or become live physical authority. The StateManager hot path may only enqueue rendered frames to the bounded truth queue; UDP sends and sidecar writes stay on the truth worker.
- Parity lanes are offline export evidence. Capture-derived registries can mark pack documents
  `oracle_proven` or `algorithm_generalized`, but remaining active `unverified_parity` lanes block
  trusted publication and must not be silently overridden. Lane classification does not add I/O or
  blocking work to the 200 Hz runtime path.
- Native pack Autoloop output is implemented in software through the existing
  `StateManager` pack driver and `LaserPackPlayer.select_autoloop()` path.
  Selection is I/O-free, latches across no-edge ticks, may seed from the
  executor's latched active Autoloop scene when no fresh edge is present, uses
  `AUTOLOOP_TICKS_PER_BEAT = 600` plus `phase_offset_beats`, renders each
  Autoloop cycle from zero with signed negative pre-roll and current-cycle
  events, resolves only canonical-pack Autoloop bindings, fails closed on
  missing/unsupported content, preserves scripted/static/blackout precedence,
  and remains suppressed while SoundSwitch is present. The loop window anchors
  at the integer-truncated selection beat and tiles `beat_count` from that
  anchor (SoundSwitch `buildAutoLoopForStartingBeat` semantics) — not at the
  absolute 32-beat beatgrid tile, which the 2026-07-02 live U0/U1 capture
  disproved via exactly-16-beat mismatch bursts on mid-grid triggers. Phase
  calibration,
  live runtime validation, and
  hardware validation remain separate gates.
- The direct-DMX lane remains hardware-unvalidated. The reviewed operator procedure requires an
  exact bridge-only process detector, a reachable physical kill, and a known-dark Enttec/DMX
  baseline before physical restore after an emergency rehearsal.

## State Ownership

- `StateManager` is the only writer of `DeckState`.
- `StateManager` owns most `OutputState` and publishes copied snapshots for
  status readers.
- Runtime commands that need state mutation should enqueue a `BridgeEvent`.
- `BridgeEvent`s are immutable once enqueued.
- `PositionSnapshot`s are written by `RBMemoryReader` through `PositionCache`.

## Single-instance lock

- Exactly one bridge process runs at a time, enforced by an exclusive `flock` on
  `/tmp/rb_ss_bridge_v2.lock` in `__main__._acquire_single_instance_lock`; the push
  loop never starts until the lock is held. The holder WRITES its pid into that
  file after acquiring the lock, and a process that cannot acquire it exits
  nonzero (`SystemExit(3)`) after writing to stderr. The frozen menubar relies on
  both: after a menubar restart it re-adopts a running bridge it has no `Popen`
  handle for by reading the lockfile pid (validated alive AND a real bridge before
  any signal), and a flock-refused spawn is surfaced instead of read as a clean
  exit. The menubar's OWN single-instance guard is a separate `flock` on
  `/tmp/rb_ss_bridge_v2_menubar.lock`.

## SmartPhrasing / Laser Ownership

- `SmartPhrasingEngine` is a pure musical phrasing engine. It emits
  `SmartPhrasingState` intents and does not send OS2L or write `OutputState`.
- Selected smart-drop markers collapse clustered ANLZ candidates after
  intro/outro trimming; `meta.anlz_drops` stays raw for phrase labels, while
  `meta.smart_drops` keeps the first marker of each drop section.
- On the first live tick after a reset, an exact Smart Drop beat landing fires once with a small exactness epsilon; near-misses must not round forward into a false drop.
- AWR-257: `meta.drop_sections` (`smart_phrasing.drop_sections` over the
  runway-gated `select_true_drops`) is pure — no I/O, no runtime state — and is
  computed only inside the `markers_changed` marker-select guard, never on the
  tick path. The tick reads the precomputed tuple only. Sections govern LED look
  selection ONLY; `meta.smart_drops`, drop firing, the blackout ladder, drop
  presentation, laser, and SoundSwitch inputs are byte-identical whether or not
  sections exist. Section-advance detection mirrors the smart-drop crossing
  (historical crossing + exact resume landing) behind its own fired-set that
  resets wherever `_fired_drop_beats` resets.
- `LaserDirector` is scene policy only; it does not send OS2L and does not emit
  MIDI side effects directly.
- `LaserSceneExecutor` owns laser MIDI trigger execution, blackout/cooldown,
  and transition-mask cleanup for laser output.
- `DropLifecycle` is a pure resolver. Default-on laser impacts must stay
  structurally identical to the LED impact gate: predecessor labels and real
  smart-drop crossings fire, one capped chorus-to-chorus label boundary can
  re-fire the second drop hit, and later chorus boundaries demote to
  `post_drop`.
  Sustained drop/post-drop cycles may fire only on autoloop ticks and may
  select only usable autoloop scenes.
- An initial laser drop impact may fall back to the configured static drop
  scene when no usable cyclable entry exists; this prevents a silent dark hit.
- Setting `drop_lifecycle_mirror` false must retain the pre-mirror director and
  executor path. Lifecycle state must reset on the documented track/deck/mode
  teardown boundaries without adding I/O to `_push_tick`.
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
- The live LED drop/post-drop resolver remains in `StateManager`; pure
  `DropLifecycle` parity covers only its flat impact window and must not be
  treated as live per-look-duration or backend-offset parity.
- Scripted-track LED automation must stay behind the existing
  `safety.scripted_mode_automation` master switch and the `lighting_mode ==
  "scripted"` gate. Role remapping is a latched policy lookup, not config
  parsing or transport I/O in `_push_tick`.
- Emergency blackout beats manual override; manual override beats automation.
- AWR-257: an in-section LED advance is a look-cursor move ONLY and must enter
  exclusively through `_dispatch_led_automation`'s gate stack (blackout,
  not-ready, manual override, scripted, not-autoloop) — never the look-director +
  `coordinator.trigger()` side channel, which has no active-blackout recheck.
  Every owner that wins over a drop-time look selection therefore wins over an
  advance identically. An advance must not fire lasers, touch darkness/blackout,
  emit autoloop/OS2L/MIDI, mutate static-override/emergency state, or add I/O to
  the push loop. Each advance carries a unique `:a{index}` role-key so the
  dedupe gate dispatches it exactly once.
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
- Direct master startup seed must use two stable valid reads. Without that proof,
  mixer-authority-enabled startup must begin with idle `active_deck=0` rather
  than treating Deck 1 as Rekordbox master truth; non-mixer legacy startup may
  still use the old default deck.
- Direct master startup seed must require stable raw Deck A/B; raw Deck C/D must
  fall back rather than aliasing to bridge Deck 1/2.
- Direct runtime master under mixer authority must refresh valid raw Deck A/B
  before the freshness window expires, and must publish invalidation for
  sentinel/no-master, unreadable, or unsupported raw Deck C/D states.
- Direct track load requires direct ANLZ to be enabled so ANLZ-before-load
  ordering remains intact.
- When named Deck 1/2 mixer authority offsets exist for the selected Rekordbox
  version, mixer active-deck authority is default-on without a runtime feature
  flag. Startup must route `MIXER_STATE`, `PLAY`, `PAUSE`, and direct
  `MASTER_CHANGED` through `RBStateReader` even if old direct flags are off.
- While mixer authority is valid/fresh, `MASTER_CHANGED` updates
  `rb_master_deck` only and must not directly write `active_deck`.
- Legacy OSC active-deck input must not rewrite `rb_master_deck` and must not
  bypass mixer authority; when mixer authority is enabled, invalid/stale fallback
  is resolver-mediated `rb_master_deck` fallback only.
- Playing-only mirror auto-switch and resume-time empty-deck correction must not
  act as independent active-deck authority while mixer authority is enabled.
- `active_deck` is the show-driving audible deck. `rb_master_deck` is separate
  Rekordbox master state for tie and invalid-mixer fallback only.
- `active_deck=0` means idle/no audible deck. The push loop must not index
  `self._deck[0]`, call `SoundSwitchEngine.deck_route(0)`, create MTC deck-0
  anchors, or keep driving stale previous-deck output. Entering idle runs the
  fixed safe-deck SoundSwitch/OS2L clear/off path without deck-0 routing.
- The 200 Hz StateManager push loop must not gain Rekordbox reads, filesystem
  scans, process-memory sampling, subprocesses, sleeps, network calls,
  MIDI/serial/DMX calls, status-provider calls, or other blocking I/O for
  active-deck authority.
- Resolver thresholds, tolerances, stale windows, and stability timing are
  implementation policy and must not be documented as RE-proven facts.

## Ordering

- `RBStateReader._tick_deck()` must enqueue `ANLZ_PATH` before
  `TRACK_LOADED`.
- `StateManager._on_track_loaded()` consumes the pending ANLZ path for the new
  `load_gen`.
- Resolver and ANLZ worker results must carry `load_gen`; stale generations are
  ignored.
- E2 section-energy grades (AWR-288, `RBSS_SECTION_ENERGY`, default OFF): all
  grade computation and the single memoized E1-store read run on the ANLZ worker
  thread, never the 200 Hz push loop; grades ride the same `load_gen`-guarded
  `ANLZ_DATA` event as `f2_plan`. Flag OFF ⇒ byte-identical (no computation, no
  payload key, no status key — kill test). Any failure (no store / no v4 / no
  markers / compute error) ⇒ grades absent/null, fail open; nothing reads them at
  E2 (status-only, no lighting consumer).
- `ANLZ_PATH`/`TRACK_LOADED` carry `rb_raw_deck` (the RB deck index 0-3). While
  a bridge deck is playing, a load/anlz event from the idle sibling RB deck
  (1&3 share bridge 1, 2&4 share bridge 2) is ignored
  (`StateManager._is_playing_sibling_load`) — a transient sibling buffer write
  must not clobber the playing deck's metadata. Events without `rb_raw_deck`,
  or with no recorded play owner, pass unchanged (fail-open).

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

- Only the resolved active bridge/show deck drives lighting decisions. Idle
  `active_deck=0` drives idle/no-output-safe behavior, not the previous deck.
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
- Govee realtime-to-cloud handoff must not call realtime transport socket
  methods on the StateManager caller thread. `force_deactivate()` marks the
  handoff and the Govee runner thread performs blackout/deactivate before the
  next realtime frame.

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
