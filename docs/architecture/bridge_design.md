---
name: rb_ss_bridge_v2 design rules and invariants
description: Current authoritative design reference for rb_ss_bridge_v2. Covers runtime wiring, direct/MTC authority, state ownership, lighting, timing, fallbacks, launcher defaults, and known hazards.
type: project
originSessionId: 88cd1a53-8b87-4b05-b106-26c1fb0a5730
---
# rb_ss_bridge_v2 — Design Reference

Status: CURRENT AUTHORITATIVE

Last reconciled against implementation commit `0d3aa5c` on 2026-06-29.

## Purpose

`rb_ss_bridge_v2` bridges Rekordbox on macOS to SoundSwitch by pretending to be
VirtualDJ on OS2L. It is Frida-free and injection-free. Direct Rekordbox process
memory reads provide the primary modern signals when the matching guarded direct
flags are enabled. MTC remains available as a timecode fallback.

The live launcher defaults currently run with B1-B6 direct paths enabled:

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

These defaults exist in `scripts/ss_bridge_watcher.sh`.

## Runtime Topology

| Component | File | Current role |
| --- | --- | --- |
| `RBStateReader` | `rb_state_reader.py` | Reads versioned Rekordbox offset-table chains at about 30 Hz. Can authoritatively emit ANLZ, track-load, play/pause, mixer snapshots, and master events through `authoritative_kinds`. |
| `active_deck_resolver.py` | `active_deck_resolver.py` | Pure resolver for show-deck authority from Deck 1/2 playing state, decoded upfader/LOW, `rb_master_deck`, validity/freshness, and stability state. No I/O. |
| `RBMemoryReader` | `rb_memory.py` | Polls position at 60 Hz into `PositionCache`; can use versioned direct position chains with ObjC scan fallback. Emits `RB_RESTARTED`. |
| `LiveBPMService` | `live_bpm.py` | Reads displayed BPM from versioned offset-table chains when supported; otherwise uses validated discovery and metadata fallback. |
| `MTCReader` | `mtc_reader.py` | Reads IAC Bus 1 MTC at about 25 fps and emits `TC_UPDATE` as position fallback. |
| `FilepathResolver` | `filepath_resolver.py` | Resolves loaded tracks by ANLZ, lsof/length, and title DB lookup; emits `FILEPATH_RESOLVED`. |
| `StateManager` | `state_manager.py` | Sole owner of `DeckState` and most `OutputState`; consumes `BridgeEvent`s, owns push-loop output ordering, and coordinates SoundSwitch behavior from one event/push loop thread. |
| `SmartPhrasingEngine` | `smart_phrasing.py` | Pure musical phrasing engine producing immutable smart-drop, smart-breakdown, transition-mask, and phrase-anchor intents. |
| `LaserDirector` | `laser_director.py` | Scene-policy/role selector from `LaserContext`; no direct OS2L or MIDI transport side effects. |
| `LaserSceneExecutor` | `laser_executor.py` | Executes laser decisions via MIDI with blackout/cooldown/role-bank logic and transition-mask cleanup. |
| `SoundSwitchEngine` | `sound_switch_engine.py` | OS2L/SoundSwitch output-intent fanout helper for scripted/autoloop/smart-transition/live-BPM-follow sends requested by `StateManager`. |
| `beat_math` | `beat_math.py` | Pure beat and beatgrid math helpers used by timing paths. |
| `OS2LConnection` / `OS2LOutput` | `osl_output.py` | Persistent TCP OS2L connection, sender queue, reconnect, and DNS-SD endpoint discovery. |
| `OS2LInjector` | `os2l_injector.py` | Runtime injection support for validation and operator commands. |
| `StatusWriter` | `runtime_status.py` | Writes `/tmp/rb_ss_bridge_v2_status.json` every 0.5 s for the menu bar. |
| `CommandReader` | `runtime_status.py` | Tails `/tmp/rb_ss_bridge_v2_commands.jsonl` for menu commands. |
| `ValidationRunner` | `validation_runner.py` | Runs operator health checks from the menu/command channel. |
| Menu bar | `scripts/bridge_menubar.py` | Local macOS control/status UI for launch, health check, Smart Phrasing toggles, and laser mapping. |

`SoundSwitchDiscovery` must be retained for the bridge lifetime. It owns the
Zeroconf browser used to discover `_os2l._tcp.local.` endpoints and update
`OS2LConnection`; dropping it after startup can leave the bridge retrying only
the localhost fallback.

## Threading And Ownership

| Thread | Writes | Reads |
| --- | --- | --- |
| StateManager thread | `DeckState`, most `OutputState`, SoundSwitch commands via `SoundSwitchEngine` | Event queue, `PositionCache`, `LiveBPMService` snapshots |
| `RBMemoryReader` | `PositionCache`, `RB_RESTARTED` events | Rekordbox process memory |
| `RBStateReader` | Direct `BridgeEvent`s and readiness callbacks | Rekordbox process memory |
| `LiveBPMService` | Internal BPM state | Rekordbox process memory |
| `MTCReader` | `TC_UPDATE` events | IAC Bus 1 MIDI |
| Resolver workers | `FILEPATH_RESOLVED`, `ANLZ_DATA` events | DB, ANLZ, lsof, audio files |
| OSC server | legacy active-deck / legacy scripted events | UDP port 7001 |
| OS2L sender | TCP writes | Send queue |
| Status writer | Status JSON file | Runtime snapshots |
| Command reader | Command state, command side effects | Command JSONL file |

Design invariant: `DeckState` is written only by `StateManager`. `BridgeEvent`s
are immutable after creation. `PositionSnapshot`s are written by
`RBMemoryReader` and read through `PositionCache`.

Runtime menu commands that need `StateManager` mutation should enqueue a
`BridgeEvent` and let the StateManager thread perform the mutation. The Smart
Drop menu toggle follows this pattern with `Ev.SMART_DROP_TOGGLE`.

## Event And Authority Model

`StateManager` does not perform broad event-source arbitration. Source selection
must happen before events reach it: `__main__.py` configures
`RBStateReader.authoritative_kinds`, and direct events are routed only when the
corresponding guarded direct flag is enabled. Named mixer authority is the
exception to the old flag-only model: when the selected Rekordbox offset version
has all required Deck 1/2 mixer labels, startup routes `MIXER_STATE`, `PLAY`,
`PAUSE`, and direct `MASTER_CHANGED` even if the old direct flags are disabled,
so resolver support inputs are not dropped.

| Signal | Default/fallback source | Direct source | Current authority rule |
| --- | --- | --- | --- |
| ANLZ path | none | `RBStateReader` `Ev.ANLZ_PATH` | Direct when `RBSS_ANLZ_DIRECT=1` and readable for that deck. |
| Position | `RBMemoryReader` ObjC scan, MTC | `RBMemoryReader` versioned `live_pos_per_deck` chain | Direct chain when `RBSS_POS_CHAIN_DIRECT=1` and valid; ObjC/MTC fallback remains. |
| Startup master seed | legacy deck 1 default when mixer authority is disabled; idle show deck when mixer authority is enabled and direct seed is unavailable | one-shot direct `master_deck` reads | Direct can seed startup `rb_master_deck` only with `RBSS_MASTER_SEED_DIRECT=1` after two stable valid reads. Mixer-authority startup without that proof begins at `active_deck=0`, not synthetic Deck 1 authority. |
| Runtime Rekordbox master | legacy/control fallback | `RBStateReader` `Ev.MASTER_CHANGED` | Direct when `RBSS_MASTER_DIRECT=1`, or when mixer authority needs rb-master support, and the current master byte is readable and valid. With valid/fresh mixer authority this updates `rb_master_deck`; it does not directly select `active_deck`. |
| Mixer active-deck authority | invalid/stale mixer fallback to current valid/fresh `rb_master_deck` | `RBStateReader` `Ev.MIXER_STATE` | Default-on when named Deck 1/2 mixer offset labels exist. Resolver uses Deck 1/2 playing state, upfader, LOW/BASS, `rb_master_deck` tie/fallback, validity/freshness, and stability state. |
| Play/pause | none | `RBStateReader` movement-derived `Ev.PLAY`/`Ev.PAUSE` | Direct when `RBSS_PLAY_DIRECT=1` and transport is warmed/readable for that deck. |
| Track load | none | `RBStateReader` full title string | Direct when `RBSS_TRACK_LOAD_DIRECT=1` and `RBSS_ANLZ_DIRECT=1` and title is readable. |
| Scripted arm/clear | OSC `/bridge/track_loaded` when direct scripted mode is disabled | `FILEPATH_RESOLVED` from direct load path | Direct by default unless `RBSS_SCRIPTED_DIRECT=0`; direct uses resolved SSID/registry/filepath. |
| Live/displayed BPM | metadata fallback | `LiveBPMService` offset-table or validated discovery | Direct when fresh and valid; fallback to metadata. |
| TC fallback | none | MTCReader | MTC writes frequent `TC_UPDATE`. |

Fail-closed rule: every direct authority path must become active only when its
own current-readiness condition is true. Unsupported Rekordbox versions, attach
failure, unreadable chains, stale reads, and no-master sentinels keep the
corresponding direct path inactive.
Unknown, anonymous, partial, duplicate, malformed, unreadable, NaN/Inf, or
out-of-range mixer fields fail closed for mixer authority.

## Direct B1-B6 Details

### B1: Direct ANLZ

With `RBSS_ANLZ_DIRECT=1`, `RBStateReader._tick_deck()` reads
`anlz_path_per_deck[d]`. Non-empty paths enqueue `Ev.ANLZ_PATH` with
`source='rb_state'` when the direct ANLZ path is readable for that bridge deck.

Direct `_tick_deck()` ordering is contractual: ANLZ is read and enqueued before
direct `TRACK_LOADED`. `StateManager._on_track_loaded()` consumes the pending
ANLZ path for that deck, so reversing this order can attach the previous ANLZ
file to the new load.

### B2: Direct Position Chain

With `RBSS_POS_CHAIN_DIRECT=1`, `RBMemoryReader` loads versioned offsets and
uses `live_pos_per_deck` chains when validation passes. ObjC discovery remains
fallback/validation, not dead code.

Deck 2 on DDJ-800 is special: `container+0x480` can reach a static/stub object.
The working deck-2 inner is session-local and must be found behaviorally. The
reader tries the outer fast path, near-`inner1` ObjC zone scan, static elapsed
scan, and bounded broad ObjC heap scan. A candidate is published only after
strict movement validation at about 44.1 kHz, no large negative jumps, and sane
range checks. Provisional candidates are not published to `PositionCache`.

### C1: Direct Master Startup Seed

With `RBSS_MASTER_SEED_DIRECT=1`, `_direct_master_startup_seed()` reads the
direct master byte twice, 0.5 s apart, using the same offset table as
`RBStateReader`. Direct seed is used only if both reads are readable, valid
bridge decks, stable, and equal. Any unsupported version, attach failure,
unreadable chain, invalid deck, unstable read, or `0xFF` no-master sentinel
falls closed. When mixer authority is enabled, that fallback startup show deck
is idle (`active_deck=0`) so Deck 1 is not treated as proven audible authority.
When mixer authority is disabled, legacy startup can still use the default deck.

### B3: Direct Play/Pause

With `RBSS_PLAY_DIRECT=1`, `RBStateReader` infers play/pause by movement in
`live_pos_per_deck[d]` after warmup and evidence polls. A failed position read
resets inference for that deck. The direct transport path emits only once it is
currently readable and has a baseline/last state for the deck.

`StateManager` still treats `d.playing` as the authoritative play state after
the selected source has produced events. The raw `PositionSnapshot.playing` bit
does not override `d.playing`; DDJ-800 mode signatures made memory play bits
unreliable for lighting/stop authority.

### B4: Direct Track Load

With `RBSS_TRACK_LOAD_DIRECT=1`, direct track-load requires
`RBSS_ANLZ_DIRECT=1`. If ANLZ direct is not enabled, B4 is ignored so
ANLZ-before-load ordering is preserved.

Direct track load emits the full direct Rekordbox title string only while title
memory is currently readable and non-empty for the bridge deck.

### B5: Direct Scripted Routing

`RBSS_SCRIPTED_DIRECT` defaults on unless set to `0`. In direct mode, the OSC
`/bridge/track_loaded` handler returns after parsing and does not enqueue
`SCRIPTED_ARM` or `SCRIPTED_CLEAR`.

Direct scripted routing happens after `FILEPATH_RESOLVED`:

1. Match `meta.soundswitch_id` against `SCRIPTED_TRACKS`.
2. If no SSID registry match, use a unique resolved filepath match.
3. If `RBSS_SCRIPTED_SHOWFILE_DIRECT=1` and a direct show-file SSID is recognized,
   synthesize a direct scripted ID. Launcher defaults set this env var to `1`,
   but plain SSID candidates alone are not treated as scripted unless the code
   recognizes them through the configured helper.
4. Enqueue `SCRIPTED_ARM` when matched, otherwise `SCRIPTED_CLEAR`.

Deck identity comes from `FILEPATH_RESOLVED`, which inherited the original
`TRACK_LOADED` deck. It does not depend on active-deck OSC ordering.

### B6: Direct Runtime Master

With `RBSS_MASTER_DIRECT=1`, `RBStateReader` adds `Ev.MASTER_CHANGED` to
`authoritative_kinds`. The main reader emits `MASTER_CHANGED source='rb_state'`
when the raw master byte changes and maps to a valid Rekordbox deck index. The
`0xFF` no-master sentinel updates the direct baseline but does not emit an event
and does not mark direct master ready.

When mixer authority is enabled, `RBStateReader` also routes direct
`MASTER_CHANGED` as resolver support even if `RBSS_MASTER_DIRECT=0`. Raw Deck
3/4 master bytes are not resolver support. StateManager stores current valid
Deck 1/2 direct master as `rb_master_deck`; while mixer authority is valid/fresh
this must not directly write `active_deck`.

OSC `/bridge/active_deck` and `/bridge/bridge_deck` enqueue legacy active-deck
fallback events for non-mixer-authority operation. They do not update
`rb_master_deck`; when mixer authority is enabled, invalid/stale fallback is
resolver-mediated `rb_master_deck` fallback only. If direct master is unsupported,
unreadable, sentinel, missing, or not warmed up, direct master stays inactive.

`read_direct_master_status()` is diagnostic/status support. Runtime direct
master truth is only the guarded B6 main `RBStateReader` path.

## StateManager Event Handling

`StateManager` consumes these events:

| Event | Effect |
| --- | --- |
| `MIXER_STATE` | Store immutable mixer snapshot and rerun active-deck resolver. |
| `MASTER_CHANGED` | With mixer authority enabled and `source='rb_state'`, update `rb_master_deck` and rerun resolver. With mixer authority disabled, request legacy active-deck fallback. Other mixer-enabled sources are ignored and rerun the resolver. |
| `LEGACY_ACTIVE_DECK` | Request legacy active-deck fallback only when mixer authority is disabled; ignored when mixer authority is enabled. |
| `TRACK_LOADED` | Clear deck metadata/scripted ID, increment `load_gen`, remember title and load trace, consume pending ANLZ path if present, start resolver work. |
| `PLAY` / `PAUSE` | Set `DeckState.playing`; active pause clears resume-settle and reruns active-deck resolver when mixer authority is enabled. |
| `ANLZ_PATH` | Store pending ANLZ path for the next matching `TRACK_LOADED`. |
| `ANLZ_DATA` | If `load_gen` matches, store drop beat indices for Smart Drop/Phrase Anchor. |
| `FILEPATH_RESOLVED` | Ignore stale generations; update full metadata; feed LiveBPM hint; run direct scripted match/clear if enabled. |
| `BPM_UPDATE` | Feed LiveBPM hint and update `d.meta.bpm` when movement is large enough. |
| `TC_UPDATE` | Store `_tc_anchor[deck] = (elapsed_ms, mono, pitch_factor)` for timecode fallback synthesis. |
| `SCRIPTED_ARM` | Set `scripted_id`; if active scripted lighting is already armed, force re-arm. |
| `SCRIPTED_CLEAR` | Clear scripted state and SSID. |
| `RB_RESTARTED` | Stop/reset play/scripted/autoloop/live BPM state and invalidate LiveBPMService. |

`load_gen` is the stale-result guard for resolver and ANLZ worker results. A
new `TRACK_LOADED` invalidates older async work for that deck.

## Startup Sequence

Startup does the following, in order:

1. Acquire `/tmp/rb_ss_bridge_v2.lock`; exit if another bridge owns it.
2. Resolve registered scripted filepaths and start SoundSwitch library scanning.
3. Create the shared raw event queue and wrap it with logging instrumentation.
4. Create `PositionCache`, `LiveBPMService`, OS2L connection/output/mirror,
   injector, discovery, `StateManager`, validation runner, command reader, and
   status writer.
5. Read Rekordbox version and run direct master startup seed if enabled; with
   mixer authority enabled and no direct seed, choose idle `active_deck=0`.
6. Call `StateManager.set_initial_state()` with the chosen active deck/source
   and guarded `rb_master_deck` seed state.
7. Attach `FilepathResolver`.
8. If any direct B1/B3/B4/B6 flag is enabled, or named mixer authority offsets
   exist for the selected Rekordbox version, create `RBStateReader` with the
   corresponding `authoritative_kinds`. Mixer authority always adds
   `MIXER_STATE`, `PLAY`, `PAUSE`, and `MASTER_CHANGED` support inputs.
9. Start direct reader, memory reader, LiveBPMService, injector,
    StateManager thread, command reader, status writer, MTC reader, and OSC
    listener.

## Position And Timing Priority

Push loop frequency: 200 Hz. Memory reader frequency: 60 Hz. Direct state reader
frequency: about 30 Hz.

Position synthesis for the active deck:

1. Use a fresh `PositionCache` snap if present.
2. If no snap, synthesize from `_tc_anchor` only when the TC anchor is less than 45 s
   old.
3. If snap exists but `snap.elapsed_ms == 0`, use the same `_tc_anchor` fallback when
   the anchor is less than 45 s old.
4. Otherwise keep the current deck elapsed fallback.

The active code currently applies the 45 s guard in both no-snap and zero-snap
fallback paths.

Interpolation:

```python
elapsed_ms = snap.elapsed_ms + (age_ms if snap.playing else 0)
```

`_tc_anchor` is written through `TC_UPDATE`:

1. `MTCReader`: about 25 fps, `pitch_factor=1.0`, already pitch-adjusted track
   time.

Resume-after-pause hazard: when `d.playing` flips true, stale TC anchors could
advance immediately. `PLAY_SETTLE_MS=400` prevents beat/elapsed emission during
the settle window; MTC normally delivers a corrected anchor inside that window.

## Lighting State Machine

Only the resolved active/show bridge deck drives lighting. Rekordbox master is
tracked separately as `rb_master_deck` for mixer tie/fallback behavior. Idle
`active_deck=0` means no audible show deck and must not drive the previous deck,
index `self._deck[0]`, or route SoundSwitch deck 0.

Mode derivation on every push tick:

```text
d.scripted_id > 0 and d.playing  -> scripted
d.scripted_id == 0 and d.playing -> autoloop
not d.playing                   -> idle
```

Idle transitions are debounced by `STOP_DEBOUNCE_S=0.5`. Autoloop-to-idle uses
`max(STOP_DEBOUNCE_S, 2.0)`. Scripted and autoloop activation are immediate.

Mode actions:

| Mode | SoundSwitch action |
| --- | --- |
| scripted | Two-phase scripted arm: clear all four slots, then deck-load scripted metadata after 100 ms. |
| autoloop | Arm autoloop with empty SSID, loop/play on, BPM snapshot, optional delayed phrase-window rearm after master switch. |
| idle | Send play off, loop off, and filepath clear to all four slots. |

Mode transitions fire only on actual mode changes, except autoloop can rearm
when the filepath arrives after an initial arm (`last_armed_filepath` changes).
`ARM_GUARD_S=3.0` suppresses stop detection only; it does not block lighting
transitions.

## Scripted Arm

`_arm_scripted()` is non-blocking and two-phase:

1. Phase 0 immediately clears filepath, loop, and play on all four SoundSwitch
   slots for the active/mirror/3/4 set.
2. Phase 1 runs about 100 ms later from `_check_pending_arm()` and sends
   `send_deck_load()` to the active bridge deck, mirror, 3, and 4.

Elapsed is captured at phase 0 and refreshed from `PositionCache` at phase 1
when a fresh snap is available. `_arm_scripted()` debounces repeated arms for the
same `(track_id, deck)` for 2 s.

Legacy OSC scripted mode (`RBSS_SCRIPTED_DIRECT=0`) has no deck in
`/bridge/track_loaded`, so the bridge uses `get_last_loaded_deck()` and only
falls back to `get_active_deck()` before any load has been seen. Direct scripted
mode should not use that fallback because resolved events already carry the
correct deck.

## Autoloop Timing And BPM

Core constants:

```text
AUTOLOOP_BEATS = 8
AUTOLOOP_ARM_PHRASE_BEATS = 32
SMART_DROP_LOOKAHEAD_BEATS = 4
SMART_DROP_IGNORE_INTRO_BEATS = 32
SMART_DROP_IGNORE_OUTRO_BEATS = 32
PHRASE_ANCHOR_BEATS = 64
BPM_THRESHOLD_UNSCRIPTED = 0.1
BPM_THRESHOLD_SCRIPTED = 2.0
```

Autoloop BPM concepts:

| Name | Meaning |
| --- | --- |
| `meta_bpm` | Metadata fallback BPM (`d.meta.bpm`). |
| `live_bpm` | Fresh validated displayed BPM from `LiveBPMService`. |
| `arm_bpm` | BPM snapshot chosen when current autoloop was armed. |
| `timing_bpm` | BPM currently used for outgoing beat/elapsed timing. |

At autoloop arm, `StateManager` asks `LiveBPMService` for the active deck. A
fresh live value wins; otherwise it uses metadata BPM. The chosen BPM is stored
in `OutputState.autoloop_arm_bpm`. Live BPM follow is enabled by default and can
send in-place BPM updates during an already armed autoloop. It never reloads the
deck, toggles loop state, or changes master.

Autoloop beat position:

- When valid ANLZ beatgrid data exists, prefer `PQT2` over `PQTZ`, map live
  elapsed to marker order, and use absolute beat position.
- Sparse tempo-anchor-only `PQT2` is rejected by marker-spacing sanity checks.
- Without beatgrid, fall back to constant-BPM math.
- Autoloop `beat.pos` and `get_beatpos` use absolute beat position.
- Scripted/non-autoloop beat events keep wrapped 4-beat behavior.
- Steady autoloop beats send `change=False`; a live BPM apply sets
  `change=True` once on the next autoloop beat.

Master-transition autoloop arms are phrase-window aware when
`RBSS_AUTOLOOP_MASTER_PHRASE_ARM` is not `0`:

- Near a 32-beat phrase start, arm immediately.
- Later in the phrase, clear all slots and delay deck-load/loop/play until the
  next 32-beat phrase target.
- If a late/short-runway arm must happen immediately, schedule a corrective
  clear plus deck-load at the next 32-beat phrase target.

`AUTOLOOP_BEATS` controls the loop length sent to SoundSwitch. It is separate
from the 32-beat phrase-lock target.

## Smart Rearm, Smart Drop, Phrase Anchor, Smart Breakdown

Post-PR-7 architecture split:

- `SmartPhrasingEngine` computes smart-transition intents from snapshot inputs.
- `StateManager` consumes those intents, applies suppression gates, owns
  `OutputState` writes/logs, and triggers side effects in deterministic order.
- `SoundSwitchEngine` performs canonical 4-deck OS2L fanout for helper sends
  requested by `StateManager`.
- `LaserDirector` and `LaserSceneExecutor` consume the same
  `SmartPhrasingState` for laser scene policy and MIDI execution.

Intentionally retained after the refactor:

- `StateManager` keeps event-loop ownership, suppression-gate ownership,
  `DeckState`/`OutputState` writes, and decision/log ordering.
- `StateManager` keeps direct per-tick `OS2LOutput` BPM/beat/elapsed fanout and
  raw `_sub` sequences used by autoloop-arm and idle-disarm paths in
  `_apply_lighting`.
- `OutputState.phrase_anchor_last_beat` remains StateManager-owned runtime state
  even though periodic phrase-anchor intents are computed in
  `SmartPhrasingEngine`.

The Smart Rearm experiment is enabled only when `RBSS_SMART_REARM_EXPERIMENT=1`.
Launcher defaults enable the experiment and set `RBSS_SMART_DROP=1`.
Phrase Anchor defaults on within the experiment unless `RBSS_PHRASE_ANCHOR=0`.

Smart Drop:

- Preserves raw ANLZ drop beat indices in `TrackMetadata.anlz_drops`.
- Computes `TrackMetadata.smart_drops` once when `ANLZ_DATA` is accepted.
- Stores `TrackMetadata.smart_drop_energy_shadow` as log-only evidence for
  nearby waveform-energy suggestions. Shadow rows carry elapsed milliseconds
  from the ANLZ beatgrid so logs can report timestamps even before filepath
  resolution populates track metadata.
- Phase 1 selection only sorts/dedupes and filters obvious intro/outro drops:
  drops before beat 32 are ignored, and drops in the final 32 beats are ignored
  only when beatgrid length is available.
- No clustering, cooldown, or energy-based timing shift is applied in Phase 1.
- Runtime Smart Drop acts on `smart_drops`, not raw `anlz_drops`.
- Phase 2 energy shadow does not move runtime targets; `_smart_drop_tick()`
  still uses `smart_drops` only.
- `SmartPhrasingEngine` emits Smart Drop intents (window, preclear, crossing).
- When preclear/crossing intents are true and gates pass, `StateManager`
  triggers smart-transition clear/rearm sends through helper paths while
  preserving existing beat-order requirements.
- Can be toggled at runtime from the menu bar through `toggle_smart_drop`.
- When toggled off, pending Smart Drop cut/rearm state is cleared.
- The runtime toggle cannot enable Smart Drop if the global Smart Rearm
  experiment is off.
- Launcher defaults set `RBSS_SMART_DROP=1`.

Phrase Anchor:

- Rearms autoloop every `PHRASE_ANCHOR_BEATS=64` beats to correct phrasing drift.
- Fires at the next clean 64-beat periodic anchor. It no longer snaps to nearby
  ANLZ drops; exact drop handling belongs to Smart Drop.
- `SmartPhrasingEngine` emits periodic phrase-anchor preclear/rearm intents from
  snapshot inputs (`phrase_anchor_last_beat`, `phrase_anchor_period_beats`).
- `_phrase_anchor_tick` consumes those intents after suppression gates; it keeps
  init sentinel and stale-rebase ownership in `StateManager` and sends pre-clear
  one beat before anchor plus direct rearm on anchor.
- Uses `_send_direct_autoloop_rearm()`, not `_apply_lighting("autoloop")`.

Smart Breakdown:

- Automatically handles lighting transitions during breakdown sections using ANLZ
  `breakdown_beat_indices` and `buildup_beat_indices`.
- `SmartPhrasingEngine` emits smart-breakdown clear/restore intents from
  breakdown segments.
- When clear/restore intents are true and gates pass, `StateManager` invokes
  smart-transition clear or direct rearm helper paths and updates breakdown
  runtime state.
- The restore beat is the next available buildup or smart drop after the
  breakdown; if none are found, it uses `SMART_BREAKDOWN_DEFAULT_DURATION_BEATS=64`.
- Smart Breakdown can be toggled at runtime from the menu bar.
- It respects its own intro/outro ignore windows (`SMART_BREAKDOWN_IGNORE_INTRO_BEATS=32`,
  `SMART_BREAKDOWN_IGNORE_OUTRO_BEATS=32`) to avoid triggering during the start
  or end of a track.
- It is only active when `RBSS_SMART_REARM_EXPERIMENT=1` and `RBSS_SMART_BREAKDOWN=1`.

## Four-Deck Mirroring

SoundSwitch is driven like VDJ:

| Operation | Decks |
| --- | --- |
| Scripted Phase 0 clear | active, mirror, 3, 4 |
| Scripted Phase 1 load | active, mirror, 3, 4 |
| Autoloop arm/rearm | active, mirror, 3, 4 |
| Idle clear | 1, 2, 3, 4 |
| BPM send | active, mirror, 3, 4 |
| Beat event | active, mirror, 3, 4 |
| Elapsed and beatpos | active, mirror, 3, 4 |

`mirror = 3 - deck` for bridge decks 1 and 2. Autoloop always sends
`soundswitch_id=""`; that empty SSID is what tells SoundSwitch to treat the
track as an autoloop instead of a scripted show.

## Stop, Resume, And Auto-Switch

Stop detection:

```text
if not d.playing and not arm_guard and os.was_playing:
    start not_playing_since
    after STOP_DEBOUNCE_S:
        if mirror deck is playing by authoritative state and fresh memory: queue MASTER_CHANGED
        else: _do_stop()
```

`_do_stop()` resets internal bridge state only. It does not clear SoundSwitch by
itself; the lighting machine applies idle and sends the SoundSwitch clear.

Auto-switch fallback also handles active idle + mirror playing when no explicit
master event arrives only when mixer authority is not enabled. The stronger
stopped+mirror-playing path requires both authoritative state and memory
corroboration for the mirror deck. The active-idle path uses authoritative
playing state only, for startup cases where memory may not yet be resolved.
While mixer authority is enabled, playing-only mirror promotion is not an
independent authority path; deck selection must go through the resolver.

Resume detection waits `PLAY_SETTLE_MS=400` after `d.playing` becomes true before
emitting beat/elapsed, preventing stale TC synthesis from producing an early
wrong position after pause.

## Runtime Status And Commands

`StatusWriter` writes `/tmp/rb_ss_bridge_v2_status.json` with schema `1`. It
includes process state, `StateManager.snapshot()`, per-deck memory and live BPM,
SoundSwitch connection status, validation result, runtime command status, and
recent errors.

State snapshots and heartbeat expose `active_deck`/`show_deck` separately from
`rb_master_deck`. Heartbeat must not report `master = active_deck`; `master`
means current valid Rekordbox master when present. Mixer authority status
includes validity, age/timestamp, fallback reason, authority reason, and decoded
Deck 1/2 upfader plus LOW/BASS raw/norm/label fields.

`CommandReader` tails `/tmp/rb_ss_bridge_v2_commands.jsonl`. Supported commands:

```text
run_validation
toggle_smart_drop
toggle_smart_breakdown
toggle_laser_director
set_laser_director
laser_blackout
laser_clear_blackout
laser_scene
laser_clear_scene_override
laser_set_personality
```

`run_validation` starts a daemon validation thread. Smart phrasing toggles queue
`Ev.SMART_DROP_TOGGLE` / `Ev.SMART_BREAKDOWN_TOGGLE`; runtime flag mutation
happens in the StateManager thread.

## Logging And Validation

Runtime logs are intentionally summary-centric. Important operator lines:

- `[MAIN] running`: direct flags, live BPM, follow, Smart Rearm, scripted direct,
  OSC port, and log-control path.
- `[MAIN] rsr-direct`: active direct `RBStateReader` event classes, including
  mixer-authority support inputs when enabled.
- `[BEAT]`: show deck and separate `rb_master` plus status summary.
- `[RBMASTER][DIRECT]`, `[MASTER-SEED]`: direct master status evidence.
- `[ANLZ][DIRECT]`, `[TITLE][DIRECT]`, `[LIVEPOS][DIRECT]`: direct state-reader
  evidence when shadow/direct logging is enabled.
- `[LBPM][DIRECT]`, `[LBPM][SOURCE]`, `[LBPM][CURRENT]`, `[LBPM][SUMMARY]`: live
  BPM chain/discovery behavior.
- `[SM] load`, `[SM] resolve`, `[SM] scripted-match`, `[SM] arm-autoloop`,
  `[SM] arm-pending`, `[SM] autoloop-rearm`: StateManager decisions.
- `[SS][AUTOLOOP-TICK]`: 32-beat phrase boundary status only, not per-beat spam.

Update current validation notes after new live runs or decisions.

## Failure Modes And Mitigations

| Scenario | Effect | Mitigation |
| --- | --- | --- |
| Unsupported Rekordbox version | Direct offset-table readers no-op or fail closed | Add offsets before promoting direct paths for that version. |
| Direct reader attach/read failure | Direct readiness false | Direct path stays inactive. |
| Direct master `0xFF` sentinel | No master event; direct master not ready | Direct master stays inactive. |
| Missing/invalid/stale mixer authority | Active-deck resolver cannot compare fader/bass dominance | Status marks visible mixer fallback; use current valid/fresh `rb_master_deck` only, otherwise hold a still-playing current show deck or go idle without synthesizing Deck 1. |
| Active deck resolves to 0 | No audible show deck | Clear idle runtime state; do not route deck 0, index deck 0, create MTC deck-0 anchors, or keep driving previous-deck output. |
| Deck-2 position unresolved | `pos=no-snap`; timing from MTC/current elapsed | Retry discovery; MTC covers gap. |
| RB restarts mid-show | Memory stale / old pointers invalid | `RB_RESTARTED` resets state and invalidates live BPM. |
| MTC unavailable | Position fallback has no external timecode anchor | Warning logged; direct memory continues when available. |
| Live BPM unavailable/disabled | Autoloop uses metadata BPM | Fail closed; `RBSS_LIVE_BPM_DISABLE=1` is supported. |
| Resolver stale result | Old filepath could arrive after a new load | `load_gen` mismatch is ignored. |
| False SoundSwitch SSID candidate | Could arm wrong show if trusted blindly | Default direct scripted path uses registry/unique filepath; show-file direct is separately gated. |

## Do Not Break These Invariants

- Do not make memory play bits override `d.playing`; selected play/pause events
  are authority.
- Do not treat a direct flag as readiness. Direct authority requires current
  readiness for that signal.
- Do not reverse direct ANLZ-before-TRACK_LOADED ordering.
- Do not route legacy OSC scripted arms by active deck when
  `get_last_loaded_deck()` is available.
- Do not block or sleep in the `StateManager` thread.
- Do not omit mirror/3/4 from SoundSwitch arms, clears, BPM, beat, or elapsed
  sends.
- Do not send a SoundSwitch ID on autoloop arms.
- Do not remove MTC fallback while direct position can still be stale,
  unresolved, or unavailable.
- Do not hardcode absolute memory addresses across Rekordbox restarts. Offset
  tables are version-specific; discovered heap addresses are session-local.
- Runtime Rekordbox master truth is only the guarded B6 main `RBStateReader`
  path.
- Do not let legacy OSC active-deck input, playing-only mirror detection, or
  `_do_resume()` directly rewrite `active_deck` while mixer authority is enabled;
  invalid/stale mixer fallback must go through `rb_master_deck`.
- Do not let CFX FILTER, Decks 3/4, crossfader, trim/gain, mute, mid/high EQ,
  FX, or real audio loudness affect active-deck authority.
- Do not document resolver thresholds, tolerances, stale windows, or stability
  timing as reverse-engineered facts.
- Do not add blocking I/O, process-memory sampling, filesystem scans, network
  calls, MIDI/serial/DMX calls, sleeps, subprocesses, or status-provider calls
  to the 200 Hz push loop for active-deck authority.
