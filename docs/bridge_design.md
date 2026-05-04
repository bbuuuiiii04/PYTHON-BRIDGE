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
| `MTCReader` | `mtc_reader.py` | Reads MTC quarter-frames + full-frame SysEx from IAC Bus 1 at ~25 fps; emits TC_UPDATE |
| `FilepathResolver` | `filepath_resolver.py` | Resolves filepath metadata. With ANLZ: ANLZ DB lookup, then lsof fallback on miss. Without ANLZ: lsof and title DB lookup race in parallel; emits FILEPATH_RESOLVED |
| `StateManager` | `state_manager.py` | Single event-loop + 200 Hz push loop thread; owns all DeckState; drives SS output |
| `OS2LConnection` | `osl_output.py` | Persistent TCP to SS; dedicated sender thread + auto-reconnect; DNS-SD discovery |
| `LinkReader` | `link_reader.py` | Ableton Link BPM/phase reader; informational only (not used for show timing) |

---

## Threading model

All DeckState writes happen in the **StateManager thread only** — no locks needed on DeckState fields.

| Thread | Writes | Reads |
|--------|--------|-------|
| StateManager | DeckState, OutputState | PositionCache (short locked reads) |
| RBMemoryReader | PositionCache (locked) | RB process memory |
| TLLogTailer | event_queue | TL log file |
| MTCReader | event_queue | IAC Bus 1 MIDI port |
| FilepathResolver (daemon threads) | event_queue | lsof, DB, audio files |
| OS2LConnection sender thread | TCP socket | send_queue |
| OSC server thread | event_queue | UDP socket |

StateManager calls `get_active_deck()` and `get_last_loaded_deck()` from OSC/MTC threads — safe because int reads are atomic under the GIL.

---

## Authority hierarchy

| Signal | Source | Authority |
|--------|--------|-----------|
| Play / pause | TL log `[EVENT] Deck X playing/paused` | **Authoritative** |
| Master deck | TL log `Rekordbox master deck changed` + ENGINE STATE every ~15s | **Authoritative** |
| Track load | TL log `[EVENT] Deck X loaded` | **Authoritative** |
| Scripted track ID | TL OSC `/bridge/track_loaded` | Authoritative — routed via TL log deck |
| Track filepath / BPM / ssid | ANLZ DB, lsof + length match, title DB lookup | Informational |
| Position (ms) | RB memory 60 Hz → MTC 25 fps → TL TC ~15s | Informational; priority in that order |
| Memory play bit | RB memory | Corroboration only — never overrides TL |
| BPM (live pitch-adjusted) | ENGINE STATE every ~15s | Updates `d.meta.bpm`; static DB BPM until first update |

**Critical rule**: TL log is truth. Memory confirms; it never overrides.
- `d.playing` (from TL PLAY/PAUSE) is the authoritative play state.
- `confident_playing = d.playing` in push loop — DDJ-800 mode=4112 makes memory play bit unreliable.
- Stop detection, lighting mode, resume detection all key off `d.playing`.

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
| any | autoloop | clear filepaths on all 4, then `send_deck_load` with ssid="" + loop=on to all 4 |
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

## 4-deck mirroring

VDJ mirrors active deck to SS decks 3 and 4. SS uses 3/4 internally for show timing and beat sync.

| Operation | Decks |
|-----------|-------|
| Phase 0 clear | 1, 2, 3, 4 (always all 4) |
| Phase 1 scripted load | arm.deck, arm.mirror, 3, 4 |
| Autoloop arm | deck, mirror, 3, 4 |
| Idle clear | 1, 2, 3, 4 |
| BPM send | active, mirror, 3, 4 |
| Beat event | active, mirror, 3, 4 |
| Elapsed + beatpos | active, mirror, 3, 4 |

`mirror = 3 - deck` (bridge deck 1 ↔ 2).

For autoloop: `soundswitch_id=""` is always sent — this is what tells SS to treat the track as autoloop rather than a scripted show.

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

`container+0x480` (RB_DECK2_OFF) reaches a static/stub inner in DDJ-800 mode. Deck-2 inner pointer is found via two candidate paths, validated over a 4s window:

1. **Outer struct fast path**: `container − OUTER_FAST_PATH_DELTA(0x270) + OUTER_INNER2_OFF(0x78)` — one read, no scan
2. **ObjC zone scan**: `_scan_objc_zone(inner1, ±0x10000, dt=0.5s)` — two bulk mach reads 0.5s apart; finds any i32 advancing at ~44100 Hz near inner1

inner1/inner2 are independent ObjC allocations with no fixed relative offset (observed: +0x4e0, −0x7570, −0x6870 across sessions). Resolution is non-blocking relative to `StateManager`, but the RBMemoryReader thread can block for ~0.5s during the ObjC zone scan. It runs once on attach, retries every 30s. First attempt often inconclusive (deck not playing); MTC covers the gap.

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
