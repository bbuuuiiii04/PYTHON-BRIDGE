---
name: rb_ss_bridge_v2 design rules and invariants
description: Authoritative design doc for the Frida-free bridge. Threading model, data flow, state ownership, lighting rules, position priority, failure modes. Check before implementing anything.
type: project
originSessionId: 88cd1a53-8b87-4b05-b106-26c1fb0a5730
---
# rb_ss_bridge_v2 — Design Reference

## What it does

Rekordbox (Mac) → SoundSwitch (DMX lighting controller).
Pretends to be VirtualDJ speaking OS2L protocol over TCP.
No Frida. No injection. Position from direct RB memory reads via mach task API.

---

## Components

| Component | File | Role |
|-----------|------|------|
| `TLLogTailer` | `tl_tailer.py` | Tails TL log; emits MASTER_CHANGED, TRACK_LOADED, PLAY, PAUSE, ANLZ_PATH, BPM_UPDATE, TC_UPDATE |
| `RBMemoryReader` | `rb_memory.py` | Reads RB process memory at 60 Hz; writes PositionCache |
| `LiveBPMService` | `live_bpm.py` | Read-only background Rekordbox memory service; uses fixed offset-table BPM chains when supported, otherwise discovers, validates, and refreshes per-deck live BPM |
| Direct master observers | `rb_state_reader.py` | Startup and bounded-runtime fixed offset-table master byte reads for visibility/corroboration only; do not enqueue events |
| `MTCReader` | `mtc_reader.py` | Reads MTC quarter-frames + full-frame SysEx from IAC Bus 1 at ~25 fps; emits TC_UPDATE |
| `FilepathResolver` | `filepath_resolver.py` | Resolves filepath metadata. With ANLZ: ANLZ DB lookup, then lsof fallback on miss. Without ANLZ: lsof and title DB lookup race in parallel; emits FILEPATH_RESOLVED |
| `StateManager` | `state_manager.py` | Single event-loop + 200 Hz push loop thread; owns all DeckState; drives SS output |
| `OS2LConnection` | `osl_output.py` | Persistent TCP to SS; dedicated sender thread + auto-reconnect; DNS-SD discovery |

---

## Threading model

All DeckState writes happen in the **StateManager thread only** — no locks needed on DeckState fields.

| Thread | Writes | Reads |
|--------|--------|-------|
| StateManager | DeckState, OutputState | PositionCache (short locked reads) |
| RBMemoryReader | PositionCache (locked) | RB process memory |
| LiveBPMService | internal validated BPM state (locked) | RB process memory |
| TLLogTailer | event_queue | TL log file |
| MTCReader | event_queue | IAC Bus 1 MIDI port |
| FilepathResolver (daemon threads) | event_queue | lsof, DB, audio files |
| OS2LConnection sender thread | TCP socket | send_queue |
| OSC server thread | event_queue | UDP socket |

`SoundSwitchDiscovery` must be retained for the bridge lifetime. It owns the
Zeroconf browser used to discover `_os2l._tcp.local.` endpoints and update
`OS2LConnection`; dropping it after startup can leave the bridge retrying only
the localhost fallback port.

StateManager calls `get_active_deck()` and `get_last_loaded_deck()` from OSC/MTC threads — safe because int reads are atomic under the GIL.

---

## Authority hierarchy

| Signal | Source | Authority |
|--------|--------|-----------|
| Play / pause | TL log `[EVENT] Deck X playing/paused`; direct `RBStateReader` only with `RBSS_PLAY_DIRECT=1` | **Authoritative**, source selected by kill switch |
| Master deck | TL log `Rekordbox master deck changed` + ENGINE STATE every ~15s | **Authoritative** |
| Direct master status | `rb_offsets.py` `master_deck` chain via startup probe + bounded runtime observer | Observational only; logs availability/corroboration and does not change active deck |
| Track load | TL log `[EVENT] Deck X loaded` | **Authoritative** |
| Scripted track ID | TL OSC `/bridge/track_loaded` | Authoritative — routed via TL log deck |
| Track filepath / BPM / ssid | ANLZ DB, lsof + length match, title DB lookup | Informational |
| Autoloop beat phase | ANLZ `PQT2`/`PQTZ` beatgrid when valid | Phase authority for autoloop only |
| Position (ms) | RB memory 60 Hz → MTC 25 fps → TL TC ~15s | Informational; priority in that order |
| Memory play bit | RB memory | Corroboration only — never overrides TL |
| BPM hint/fallback | ENGINE STATE every ~15s | Updates `d.meta.bpm`; static DB BPM until first update |
| BPM live/displayed | LiveBPMService fixed offset-table chain or current-session discovery validation | Used for autoloop arm snapshot and default-on gated active follow when valid |

**Critical rule**: TL log is truth by default. Direct memory overrides only for
the explicit guarded retirement items listed below.
- `d.playing` is the authoritative play state as set by the selected
  play/pause source: TL by default, direct only with `RBSS_PLAY_DIRECT=1`.
- `confident_playing = d.playing` in push loop — DDJ-800 mode=4112 makes memory play bit unreliable.
- Stop detection, lighting mode, resume detection all key off `d.playing`.

Guarded TL-retirement exceptions:

- `RBSS_ANLZ_DIRECT=1`: direct `Ev.ANLZ_PATH` from `RBStateReader` is routed to
  the authoritative queue. TL ANLZ correlation output is bypassed only for a
  bridge deck while direct ANLZ is currently readable for that deck; otherwise
  TL remains the fail-closed fallback.
- `RBSS_POS_CHAIN_DIRECT=1`: `RBMemoryReader` uses versioned
  `live_pos_per_deck` chains to feed `PositionCache`; ObjC scan still runs as
  fallback/validation. Chain reads update their previous-raw validation anchor
  only after negative, backward-jump, and elapsed-range validation passes.
- `RBSS_MASTER_SEED_DIRECT=1`: startup-only direct master seed can override the
  initial TL active deck after two stable reads; runtime master remains TL.
- `RBSS_PLAY_DIRECT=1`: direct `Ev.PLAY`/`Ev.PAUSE` from `RBStateReader` is
  routed to the authoritative queue. TL log play/pause output is bypassed only
  for a bridge deck after direct transport has attached, read live position, and
  warmed up a baseline for that deck; otherwise TL remains the fail-closed
  fallback. Startup ENGINE preload remains unchanged.

**Audit note (2026-05-06):** `docs/timecodelink_integration_analysis.md` §7–10 documents the
exact RB memory layout TL reads (master-deck `uint8_t`, per-deck live BPM `float`,
per-deck **live position samples → `isPlaying` via diff** + `elapsedSec` via `samples/44100`,
per-deck trackInfo string, ANLZ filename) and the per-version `OffsetVersion`
chain structure. The full per-version offset table for **all 5 supported RB
versions (7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14)** has been extracted
verbatim from TL's compiled-in Qt resource and is shipped alongside the bridge
in `rb_offsets.py` (and as raw text under `docs/offsets-macos.yaml`).
A working `RBStateReader` (`rb_state_reader.py`) — daemon thread, fail-closed,
no-op on unsupported RB versions — is implemented and unit-tested (24 tests,
backed by a fake-mach-read harness in `tests/test_rb_state_reader.py` /
`tests/test_rb_offsets.py`).

The audit confirmed (analysis §8 + disassembly of `RekordboxPlugin::start` /
`tryConnect`) that TL's licensing (in-house, libsodium-Ed25519) is fully
decoupled from the memory tap, so no DRM boundary blocks the direct-read
implementation.

`RBStateReader` can run in explicit shadow mode for parity checks, but it does
not feed the authoritative `StateManager` queue. Until direct-read events are
observed in parallel against `TLLogTailer` for at least one full session per RB
version and an arbitration path is added, **TL log remains authoritative for
play / pause / master / track-load events**. Adoption gating in analysis §10.5.

The master-specific convergence path is observational only. On supported
Rekordbox versions, `read_direct_master_status()` and the startup settle probe
follow the same `master_deck` byte chain used by `RBStateReader`, log
`[RBMASTER][DIRECT]` availability, and log `[RBMASTER][SOURCE]` with
`current=tl_log`, direct deck, TL startup deck, and corroboration state.

A bounded runtime observer then starts after startup wiring settles. It polls
the direct master byte at low rate for a short fixed window and compares it
against `TLMasterSnapshot`, a TL-only snapshot that accepts only
`tl_log`, `engine_state`, and `initial_engine_state` `MASTER_CHANGED` events.
Runtime summaries log `outcome`, `final_direct_master`, `final_tl_master`,
`transition_count`, `mismatches`, `first_valid_elapsed_s`,
`comparison_source=tl_master_snapshot`, and `authority=tl_log`.

Current live evidence is encouraging for direct master readability and
stability, and suggests direct Rekordbox master may surface current startup
master before the TL-only snapshot becomes fresh in some deck-2 cases. This is
not authority promotion. The direct master path still does not enqueue
`MASTER_CHANGED`, does not call `StateManager.set_initial_state`, and fails
closed to TL-only status when the RB version is unsupported, attach fails, the
chain is unreadable, or direct master is not valid.

The current TL-retirement evidence and next-step log lives in
`docs/tl_retirement_process_log.md`. Future agents should update that file
after every new live run, user correction, or TL-retirement decision.

Live BPM is a separate read-only memory signal. On supported Rekordbox versions,
LiveBPMService follows the same per-version BPM chain shipped in `rb_offsets.py`
as soon as it has attached to the Rekordbox pid/base; this direct path does not
wait for ENGINE STATE because the versioned chain itself supplies the deck-owned
field. If that chain is unreadable, unsupported, stale, or non-finite, it fails
closed and uses the older discovery path once hints are available. Discovery
candidates are still never promoted from a static address match: they require
current-session pid/base/deck validation through observed BPM movement. If no
fresh live BPM is available, the bridge falls back to `d.meta.bpm`.

---

## Position priority and interpolation

Push loop runs at 200 Hz; memory polls at 60 Hz. Between memory reads, interpolate forward:
```
elapsed_ms = snap.elapsed_ms + (age_ms if snap.playing else 0)
```

When `snap is None`, fall back to `_tl_tc[deck]` only if the TC anchor is less than 45s old:
```
age_ms = (now - tl_at) * 1000.0 * pitch_factor
elapsed_ms = tl_ms + (age_ms if d.playing else 0)
```

When `snap.elapsed_ms == 0` (DDJ-800 deck 2 / mode=4112), the code also falls back to `_tl_tc[deck]`, but currently does **not** apply the 45s guard in that branch:
```
elapsed_ms = tl_ms + (age_ms if (mem_playing or d.playing) else 0)
```
This is intentional current-code behavior, not an invariant to preserve forever. If stale zero-snap TC drift appears, add the same 45s guard to this branch.

`_tl_tc` is written by two sources via TC_UPDATE events (most-recent-write wins):
1. **MTCReader** — ~25 fps, max 40ms interpolation error. `pitch_factor=1.0` (MTC is already pitch-adjusted track time).
2. **TL TC** (ENGINE STATE) — ~15s cadence. `pitch_factor` from ENGINE STATE pitch% field. Safety net if MTC unavailable.

Memory snap takes priority the moment PositionCache has a valid non-zero entry — TC path only activates when snap is absent or its elapsed position is zero.

**Resume-after-pause hazard**: when `d.playing` flips True, TC synthesis immediately starts adding `age_ms` — but `tl_at` is from before the pause, so synthesized position can be stale by the full pause duration. The **400ms play settle window** (`PLAY_SETTLE_MS`) prevents the bridge from emitting beats/elapsed to SS during this gap. MTC delivers a corrected anchor within ~40ms of playback resuming, well within the settle window.

**45s guard**: TC synthesis is disabled if `tl_at` is more than 45s old only in the `snap is None` path. The zero-position fallback path currently lacks this guard.

---

## Lighting state machine

Master/active deck drives ALL lighting decisions. Non-master deck state is tracked but never applied to SS.

### Mode derivation (every push tick):
```
d.scripted_id > 0  AND  d.playing  →  desired = "scripted"
d.scripted_id == 0 AND  d.playing  →  desired = "autoloop"
not d.playing                      →  desired = "idle"
```

### Debounce:
- `idle` transitions debounced by `STOP_DEBOUNCE_S = 0.5s`
- All other transitions are immediate (desired fires as soon as stable)

### Mode transitions:
| From | To | SS action |
|------|----|-----------|
| any | scripted | `_arm_scripted(deck, scripted_id)` |
| any | autoloop | snapshot BPM, clear filepaths on all 4, then `send_deck_load` with ssid="" + loop=on to all 4 |
| any | idle | `send_deck_play(off)` + `send_deck_clear` to all 4 decks |

Transitions only fire on mode change. Exception: autoloop re-arms if `d.meta.filepath` changes after initial arm (`last_armed_filepath` check).

### Arm guard (3s, `ARM_GUARD_S`):
Suppresses stop detection only. Does NOT block lighting transitions. Recomputed AFTER `_update_lighting()` fires on each tick, so a just-fired arm is immediately reflected.

### Scripted arm 2s debounce:
`_arm_scripted` silently drops calls within 2s of a prior arm for the same `(track_id, deck)` pair. If a scripted arm appears to not fire, check for this debounce.

---

## Two-phase scripted arm

Phase 0 and Phase 1 are always separated by ~100ms (`fire_at = now + 0.10`). This gives SS time to process the clear before receiving track data.

**Phase 0 (immediate)** — clears SS for all 4 deck slots:
```python
for dk in (deck, mirror, 3, 4):
    send filepath=""
    send loop=off
    send play=off
```

**Phase 1 (100ms later, via `_check_pending_arm`)** — loads track to all 4 deck slots:
```python
for dk in (arm.deck, arm.mirror, 3, 4):
    send_deck_load(dk, arm_meta, cur_active, play="on")
```
Elapsed is refreshed from PositionCache at phase 1 time. If snap is stale, uses `arm.elapsed_ms` captured at phase 0.

---

## Autoloop BPM policy

Autoloop has four BPM concepts:

| Name | Meaning |
|------|---------|
| `meta_bpm` | Current metadata/fallback BPM from library/ENGINE STATE (`d.meta.bpm`) |
| `live_bpm` | Fresh validated Rekordbox displayed BPM from LiveBPMService |
| `arm_bpm` | BPM chosen for the current SoundSwitch autoloop arm/timing epoch |
| `timing_bpm` | BPM currently used by the bridge for outgoing beat/elapsed timing |

At autoloop arm:

1. StateManager asks LiveBPMService for the active deck's current BPM.
2. If a validated live BPM exists, `arm_bpm` uses it and the deck-load metadata
   sent to SoundSwitch uses that value.
3. Otherwise `arm_bpm` falls back to `meta_bpm`.
4. The chosen value is stored in `OutputState.autoloop_arm_bpm`.
5. The arm still fires immediately for workflow, then StateManager marks
   `autoloop_arm_pending=True` so the push loop can send a second BPM at the
   next 32-beat phrase boundary.

Autoloop arm phrase-lock:

- Phrase targets are absolute beat boundaries: `(AUTOLOOP_ARM_PHRASE_BEATS * n)`.
- With `AUTOLOOP_ARM_PHRASE_BEATS=32`, arm phrase-lock targets `32, 64, 96, ...`.
- This is intentionally separate from `AUTOLOOP_BEATS`, which controls the
  loop length sent at arm time.
- Example simulations:
  - arm at beat `5.2` -> target `32`; no BPM at `31.9`; BPM at `32.0`.
  - arm at beat `299.3` in a 3:00, 138 BPM track -> target `320`.
  - deck 1 -> deck 2 transition clears deck 1 pending lock; deck 2 gets its
    own immediate arm and own phrase target, e.g. beat `172.4` -> `192`.
- Pending arm phrase-lock is cleared on idle/stop, master change, active track
  load, and Rekordbox restart.
- Master-transition phrase arm is enabled by default. Set
  `RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` to disable it.
- Autoloop arms after a master deck switch are phrase-window aware:
  - the bridge first clears all four SoundSwitch deck slots so the old autoloop
    is cut;
  - if the switch lands near the start of a phrase, deck-load/loop/play fire
    immediately;
  - if the switch lands later in the phrase, deck-load/loop/play wait until the
    next 32-beat phrase target.
- If a master-transition rearm is late, short on runway, or only accepted by the
  phrase-start grace window after the tolerance, it still arms immediately and
  schedules a corrective clear plus filepath/deck-load on the next 32-beat
  phrase target.
- Normal track-start autoloop arms remain immediate.
- Beatpos/`change=True` tugging was live-tested and only moved the progress bar;
  production master-transition rearm uses clear plus filepath/deck-load instead.

VDJ-like live-follow behavior:

- Enabled by default; set `RBSS_LIVE_BPM_FOLLOW=0` to disable active follow.
- During an already armed autoloop, the bridge watches fresh `live_bpm` from the
  offset-table chain when available, otherwise from the validated discovery path.
- Runtime status text labels the source as `live_source=offset_table`,
  `live_source=discovery`, or `live_source=fallback_meta`.
- Live BPM source transitions are logged as `[LBPM][SOURCE]`; direct offset-table
  acceptance/rejection is logged as `[LBPM][DIRECT]`. Set
  `RBSS_LIVE_BPM_DIAGNOSTICS=1` for compact `[LBPM][SUMMARY]` lines during live
  validation runs.
- If live BPM diverges from `timing_bpm` by more than the unscripted BPM
  threshold, the bridge sends the new BPM to all four SoundSwitch deck slots.
- BPM follow sends are rate-limited to avoid push-loop spam while still tracking
  pitch changes during playback.
- After sending BPM to all four SoundSwitch deck slots, StateManager updates
  `autoloop_arm_bpm` / `timing_bpm` to the new value.
- The next autoloop beat after a live BPM apply sends absolute `beat.pos` with
  `change=True` exactly once, then steady autoloop beats return to
  `change=False`. This is not used for master-transition rearm.
- Live BPM follow never reloads the deck, toggles loop state, or changes master.

Live-follow cancellation:

- Live-follow state is cleared on idle/stop, deck switch, active track load,
  Rekordbox restart, live BPM invalidation/stale read, and resume-settle state.

Kill switches:

- `RBSS_LIVE_BPM_DISABLE=1` disables LiveBPMService entirely.
- `RBSS_LIVE_BPM_FOLLOW=0` disables active-autoloop follow while still allowing
  arm-time live BPM snapshots when validated.
- `RBSS_LIVE_BPM_DIAGNOSTICS=1` adds compact LiveBPM source summaries for
  proving whether offset-table BPM became active before ENGINE STATE hints.
- `RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0` disables default phrase-window
  master-transition autoloop activation.

---

## 4-deck mirroring

VDJ mirrors active deck to SS decks 3 and 4. SS uses 3/4 internally for show timing and beat sync.

| Operation | Decks |
|-----------|-------|
| Phase 0 clear | 1, 2, 3, 4 (always all 4) |
| Phase 1 scripted load | arm.deck, arm.mirror, 3, 4 |
| Autoloop arm | deck, mirror, 3, 4 |
| Idle clear | 1, 2, 3, 4 |
| BPM send | active, mirror, 3, 4 (arm/reset and gated active-autoloop live follow) |
| Beat event | active, mirror, 3, 4 |
| Elapsed + beatpos | active, mirror, 3, 4 |

`mirror = 3 - deck` (bridge deck 1 ↔ 2).

For autoloop: `soundswitch_id=""` is always sent — this is what tells SS to treat the track as autoloop rather than a scripted show.

Current autoloop timing state:

- VDJ/SoundSwitch capture showed continuous `get_beatpos` and continuous
  `beat.pos`; the old bridge sent both as modulo-4 bar phase.
- When ANLZ beatgrid data is available, the bridge prefers non-empty `PQT2`
  over `PQTZ`, maps live `elapsed_ms` onto marker order, and uses that as the
  autoloop phase/position authority.
- Sparse `PQT2` tempo-anchor data is rejected by marker-spacing sanity checks;
  it falls back to `PQTZ` or constant-BPM math.
- Autoloop `get_beatpos` sends absolute beat position from the beatgrid when
  valid, otherwise from existing constant-BPM math.
- Autoloop `beat.pos` sends absolute beat count from the same source.
- Autoloop beat-boundary detection and arm phrase-lock use that same absolute
  beat position, preserving `(16 * n)` phrase targets.
- Scripted/non-autoloop beat timing still uses the old wrapped behavior.
- BPM sends remain governed by arm/live-BPM logic; the beatgrid is not used as
  the outgoing BPM source.
- Steady autoloop beat events send `change=False`, including 4-beat boundaries.
- User observed SoundSwitch's autoloop progress bar no longer restarts every
  4 beats with absolute autoloop beat positions active.
- Autoloop diagnostics are periodic, not per-beat: `[SS][AUTOLOOP-ARM]`,
  `[SS][AUTOLOOP-TICK]`, `[SS][LIVE-BPM-APPLY]`, and `[SS][deck-load]`.
- See `docs/autoloop_beatphase_findings.md` for the evidence log.

---

## SCRIPTED_ARM routing

TL OSC `/bridge/track_loaded` fires with a track ID but NO deck info.

**Correct**: use `get_last_loaded_deck()` — the deck that most recently received TRACK_LOADED from the TL log (which carries explicit deck A/B/C/D). This is always set before the OSC fires.

**Wrong**: `get_active_deck()` — incorrect when loading on non-master deck.

Fallback: if `_last_loaded_deck == 0` (startup, no loads yet) → fall back to `get_active_deck()`.

The lighting machine enforces master authority itself. SCRIPTED_ARM only needs to set `scripted_id` on the correct deck so it's ready when that deck becomes master.

---

## Deck switch invariants

On every `_on_master_changed`, reset ALL of:
1. `was_playing = False` — prevents old deck's play state from force-stopping new master
2. `play_settle_after = 0.0`
3. `not_playing_since = 0.0`
4. `lighting_mode = ""` AND `lighting_desired = ""` AND `lighting_stable_since = 0.0`
   — `lighting_mode=""` forces a re-arm even when both old and new master have the same mode
   (e.g. scripted→scripted: without this the machine sees `desired == mode` and skips the arm)
5. `last_arm_mono = now` — arm guard window starts
6. `push_reset_bpm = True`

**OSC/switch race**: if old deck has `scripted_id > 0`, new deck has `scripted_id == 0`, and old deck is not playing → transfer `scripted_id` to new deck. Handles SCRIPTED_ARM landing on old master before MASTER_CHANGED processed.

---

## Stop detection

```
if not d.playing and not arm_guard and os.was_playing:
    start not_playing_since timer
    if timer >= STOP_DEBOUNCE_S (0.5s):
        if other deck playing (TL AND memory) → auto-switch: MASTER_CHANGED to mirror
        else → _do_stop()
```

`_do_stop` resets internal bridge state only (`was_playing=False`, `last_sent_bpm=0`, etc.). It does NOT send any SS commands. The SS clear comes from the lighting machine: `d.playing=False` → `desired="idle"` → 0.5s debounce → `_apply_lighting("idle")` → play=off + clear to all 4 decks.

Auto-switch fires MASTER_CHANGED into the event queue so `_on_master_changed` runs in the event-loop thread, not the push-loop.

---

## Auto-detect deck switch

Fallback for when TL doesn't send MASTER_CHANGED.

**Path 1 — stop detection leads to switch** (when `stop_confirmed and was_playing`):
```
if other_playing and not arm_guard → MASTER_CHANGED to mirror
```
`other_playing` requires BOTH `self._deck[mirror].playing` (TL) AND `other_snap.playing` (memory) — guards against wrong DPU offsets causing false switches.

**Path 2 — active idle, mirror playing** (when `not was_playing and not d.playing`):
```
if not arm_guard and self._deck[mirror].playing → MASTER_CHANGED to mirror
```
TL only — no memory corroboration. Handles startup case where bridge never saw playback on this deck.

---

## Deck-2 position resolution (`rb_memory.py`)

`container+0x480` (RB_DECK2_OFF) reaches a static/stub inner in DDJ-800 mode. Deck-2 inner pointer is found via candidate paths, validated over a 4s window:

1. **Existing provisional candidate**: sampled again on retry until strict movement validation promotes or rejects it
2. **Outer struct fast path**: `container − OUTER_FAST_PATH_DELTA(0x270) + OUTER_INNER2_OFF(0x78)` — one read, no scan
3. **ObjC zone scan**: `_scan_objc_zone(inner1, ±window, dt=0.5s)` — two bulk mach reads 0.5s apart; finds any i32 advancing at ~44100 Hz near inner1
4. **Static elapsed scan**: if the moving zone scan finds no hits and StateManager has a fresh Deck-2 TL/MTC elapsed estimate, scan near `inner1` for one aligned ObjC candidate whose `+0x0c` i32 value is close to that elapsed. This stores only a provisional pointer. Ties within 250ms of the best match are treated as ambiguous and ignored.
5. **Broad ObjC heap moving scan**: after repeated near-`inner1` failures while Deck 2 is playing or was recently seen playing, scan vmmap-derived ObjC/nano heap regions in bounded chunks for moving i32 fields near current TL/MTC elapsed. These become `D(heap)` candidates and still require strict 4s validation before commit.

inner1/inner2 are independent ObjC allocations with no fixed relative offset (observed: +0x4e0, −0x7570, −0x6870 across sessions). Resolution is non-blocking relative to `StateManager`, but the RBMemoryReader thread can block for ~0.5s during the ObjC zone scan. It runs once on attach, retries every 30s while Deck 2 is idle, and widens the scan window across repeated unresolved attempts: ±0x10000, then ±0x20000, then ±0x40000. If TL reports Deck 2 playback while memory is unresolved, RBMemoryReader starts discovery immediately; while Deck 2 remains playing, unresolved retries use a 5s cadence. If a provisional candidate exists, retry cadence is also 5s so the remembered candidate can be promoted soon after Deck 2 starts playing. First attempt often inconclusive (deck not playing); MTC covers the gap.

The broad ObjC heap fallback runs only on later unresolved attempts, only while Deck 2 is playing or was seen playing within the recent-play window, and only when a Deck-2 elapsed hint is available. The recent-play window tolerates brief TL play/load/pause toggles during a validation attempt; strict movement validation is still required before commit. The scan is bounded to 128 MB of readable ObjC chunks per attempt and uses the elapsed hint only as a filter/ranking input. It is not a commit path by itself:

```
RBMemoryReader: deck2 play trigger — starting resolution
ObjC heap moving scan regions=N chunks=M bytes=B target=Tms: H hit(s)
deck2 candidate D(heap): 0x...
deck2 candidate 0x... PASS: rate=...
deck2 inner committed: 0x...
```

Provisional Deck-2 candidates are not published to `PositionCache` and do not drive SoundSwitch timing. They only reduce rediscovery work after a paused/startup scan. A provisional candidate becomes usable only after the same strict movement validation passes:

```
deck2 provisional promoted: 0x...
deck2 inner committed: 0x...
```

If it fails strict validation later, it is discarded:

```
deck2 provisional rejected: 0x...
```

`pos=no-snap` in status log = inner2 not yet resolved.

### Live Deck-2 discovery evidence

Session evidence from Rekordbox pid `83311`:

```
base      = 0x102a0c000
container = 0x1596c9a00
dpu1      = 0x60000386a060
inner1    = 0x600006b28410
```

Container slots were rejected for Deck 2:

```
container+0x480 -> inner=0x1074da5d0 pos=1 flat
container+0x488 -> inner=0x1074da5d0 pos=1 flat
```

The ObjC-zone scan around `inner1` found one strict Deck-2 candidate while Deck 2 was playing:

```
position field = 0x600006b284ec
field offset   = inner1 + 0xdc
inner2         = 0x600006b284e0
inner2 offset  = inner1 + 0xd0
run 1 rate     = 44097.8 samples/sec, neg_jumps=0
run 2 rate     = 44088.8 samples/sec, neg_jumps=0
```

When Deck 2 was paused and the same scan was rerun, no strict moving candidate was found. This is the expected paused signature: the true Deck-2 position field goes flat, so movement-based discovery becomes inconclusive until playback resumes.

Direct sampling of the discovered field confirmed the same behavior:

```
paused sample:  first=3543419 last=3543419 delta=0 over 3.31s
playing sample: first=4035964 last=4180860 delta=144896 rate=44131.9 samples/sec neg_jumps=0
cue sample:     first=2205    last=2205    delta=0 ms=50
```

Second-session evidence after restarting Rekordbox:

```
pid       = 88640
base      = 0x100548000
container = 0x10cd1e200
dpu1      = 0x6000023d3410
inner1    = 0x6000070e5520

container+0x480 -> inner=0x1050165d0 pos=1 flat
container+0x488 -> inner=0x1050165d0 pos=1 flat

position field = 0x6000070e84ec
field offset   = inner1 + 0x2fcc
inner2         = 0x6000070e84e0
inner2 offset  = inner1 + 0x2fc0
scan rate      = 44102.4 samples/sec, neg_jumps=0
playing sample = delta=143360 rate=44158.0 samples/sec neg_jumps=0
paused sample  = first=2520286 last=2520286 delta=0
```

Do not hardcode `inner1 + 0xd0` or `inner1 + 0x2fc0`. Those offsets are session-local evidence only; prior sessions observed different offsets. The invariant is behavioral: find an i32 at candidate `inner + 0x0c` that advances at ~44.1 kHz while Deck 2 plays, has no large negative jumps, stays in range, and goes flat when Deck 2 pauses.

---

## Known failure modes

| Scenario | Effect | Mitigation |
|----------|--------|------------|
| Deck-2 inner not found (not playing during scan) | pos=no-snap; deck 2 position from MTC/TC | 30s retry; MTC covers gap |
| Deck-2 true inner outside ObjC scan window | pos=no-snap; deck 2 position from MTC/TC | Outer fast path plus ±0x10000 ObjC zone scan; 30s retry |
| SCRIPTED_ARM before any TRACK_LOADED (startup) | `_last_loaded_deck=0` → falls back to active_deck | Acceptable at startup |
| RB restarts mid-show | Memory goes stale → was_playing force-stop | RB_RESTARTED event resets all state |
| Deck switch before SCRIPTED_ARM | scripted_id on wrong deck | Transfer logic in _on_master_changed |
| DDJ-800 mode=4112 memory play bit | Memory says playing when paused | TL PAUSE event is authoritative; d.playing overrides |
| MTC unavailable (mido/IAC) | Position fallback only has TL TC (~15s) | TL TC still sufficient; warning logged |
| Live BPM unavailable/disabled | Autoloop arm/follow uses `d.meta.bpm` fallback | Fail closed; fixed chains require supported RB version; discovery still validates |
| BPM changes during active autoloop | Default-on live follow sends gated BPM updates in place | `RBSS_LIVE_BPM_FOLLOW=0` disables active follow |

---

## What NOT to do

- Do not use memory play bit as authoritative play state — always use `d.playing`
- Do not route SCRIPTED_ARM via `get_active_deck()` — use `get_last_loaded_deck()`
- Do not block lighting transitions with arm_guard — arm_guard suppresses stop detection only
- Do not omit mirror or decks 3/4 from any SS send — always all 4 slots
- Do not sleep or block in the StateManager thread — 200 Hz, any block cascades
- Do not send `soundswitch_id` on autoloop arms — empty ssid is what triggers SS autoloop mode
- Do not remove TL TC synthesis from tl_tailer.py — it is the fallback when MTC is unavailable
- Do not call `_do_stop` expecting it to clear SS — it only resets internal state; lighting machine clears SS
- Do not route active-autoloop BPM changes through deck load, loop on/off, or
  master-change paths. Live follow is transport-only and rate-limited.
- Do not hardcode live BPM absolute addresses or reuse absolute addresses across
  Rekordbox restarts. Offset-table BPM is version-specific chain resolution;
  discovery BPM remains current-session validation only.
