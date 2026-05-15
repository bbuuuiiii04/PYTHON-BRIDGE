# Code Update Tracker For Claude Code

Status: HISTORICAL

Updated: 2026-05-07

## Collaboration Rule

Do not edit bridge code without explicit user approval.

Before any code edit:

1. Propose the exact file and function to change.
2. Explain the evidence and reasoning.
3. State the expected behavior change and risk.
4. Wait for the user to approve.

Markdown documentation edits are allowed when requested.

## Recent Code Changes For Review

These code changes should be reviewed before release:

### B5 SCRIPTED_ARM direct retirement

Implemented behavior:

```text
RBSS_SCRIPTED_DIRECT=1 bypasses the TL OSC /bridge/track_loaded scripted-arm
path after parsing the track id. /bridge/active_deck is untouched and still
drives master-change routing.

StateManager._on_filepath_resolved() now promotes the A6 shadow lookup:
soundswitch_id is matched against SCRIPTED_TRACKS and enqueues either
Ev.SCRIPTED_ARM or Ev.SCRIPTED_CLEAR with source="filepath_resolved". The event
is put back on the same queue while StateManager is draining events, so it is
processed on the next drain-loop iteration.

If soundswitch_id is empty or unmatched, the direct path falls back to a unique
SCRIPTED_TRACKS filepath match. Ambiguous filepath matches do not arm and log a
scan-level INFO line before SCRIPTED_CLEAR. The only non-queue warning in this
lookup path is a successful unique filepath fallback when soundswitch_id is
empty. This preserves scripted tracks with missing SoundSwitch id tags, where
SoundSwitch can still match the show by filepath.

The legacy OSC/switch race transfer in _on_master_changed() is disabled while
RBSS_SCRIPTED_DIRECT=1. Direct FILEPATH_RESOLVED deck identity is already
correct; copying scripted_id from the old deck can arm a stale show on an
unscripted incoming deck.

The repo watcher script and the live /Users/bbui/ss_bridge_watcher.sh both set
RBSS_SCRIPTED_DIRECT=1 alongside B1-B4 direct flags.
```

Files/functions changed:

```text
__main__.py
  SCRIPTED_DIRECT_ENV
  start_osc_listener()
  _track_loaded() guarded bypass

state_manager.py
  _on_filepath_resolved() direct SCRIPTED_ARM / SCRIPTED_CLEAR enqueue
  _on_master_changed() transfer gate under RBSS_SCRIPTED_DIRECT

scripts/ss_bridge_watcher.sh
/Users/bbui/ss_bridge_watcher.sh
  RBSS_SCRIPTED_DIRECT=1 in both launch paths

tests/test_tl_tailer.py
  OSC /bridge/track_loaded bypass and legacy fallback coverage

tests/test_live_bpm_service.py
  StateManager direct arm, direct clear, disabled fallback, and transfer gate
  Empty-ssid filepath fallback, unmatched-ssid filepath fallback, and ambiguous
  filepath rejection
```

Validation:

```text
python3 -m unittest tests.test_tl_tailer tests.test_live_bpm_service
Ran 86 tests
OK
```

### B4 TRACK_LOADED direct retirement

Implemented behavior:

```text
RBSS_TRACK_LOAD_DIRECT=1 promotes Ev.TRACK_LOADED from RBStateReader to the
authoritative StateManager queue. TLLogTailer remains running and is bypassed
only after direct title memory is ready for that bridge deck.

B4 depends on B1 ANLZ direct. If RBSS_TRACK_LOAD_DIRECT=1 is set without
RBSS_ANLZ_DIRECT=1, the bridge ignores B4 and leaves TL TRACK_LOADED
authoritative. This prevents direct TRACK_LOADED from arriving before TL
ANLZ_PATH and causing StateManager._on_track_loaded() to consume a stale or
missing pending ANLZ path.

RBStateReader._tick_deck() now reads/enqueues ANLZ_PATH before track-info /
TRACK_LOADED in the same tick. This ordering is a critical invariant.

Track-load direct readiness requires a non-empty readable title buffer. Empty
buffers do not mark a deck ready and therefore do not cause TL TRACK_LOADED
bypass.

The repo watcher script and the live /Users/bbui/ss_bridge_watcher.sh both set
RBSS_TRACK_LOAD_DIRECT=1 alongside RBSS_ANLZ_DIRECT=1, RBSS_PLAY_DIRECT=1,
RBSS_POS_CHAIN_DIRECT=1, and RBSS_MASTER_SEED_DIRECT=1.
```

Files/functions changed:

```text
tl_tailer.py
  TRACK_LOAD_DIRECT_ENV
  TLLogTailer.__init__(track_load_direct_ready=...)
  _track_load_direct_bypass_enabled()
  _process_line() TRACK_LOADED bypass

rb_state_reader.py
  RBStateReader.__init__(track_load_available_callback=...)
  _tick()
  _tick_deck() ANLZ-before-title ordering
  _update_track_load_available()
  _set_all_track_load_unavailable()
  _set_track_load_available()

__main__.py
  TRACK_LOAD_DIRECT_ENV import
  track_load_direct flag and ANLZ dependency guard
  _set_track_load_direct_ready()
  _is_track_load_direct_ready()
  Ev.TRACK_LOADED authoritative_kinds promotion
  track_load_available_callback wiring

scripts/ss_bridge_watcher.sh
/Users/bbui/ss_bridge_watcher.sh
  RBSS_TRACK_LOAD_DIRECT=1 in both launch paths

tests/test_tl_tailer.py
  TL TRACK_LOADED bypass, callback fallback, and B4-without-B1 fallback

tests/test_rb_state_reader.py
  direct TRACK_LOADED routing, ANLZ-before-TRACK_LOADED ordering, direct
  readiness set/clear, and empty-title readiness suppression
```

Validation:

```text
python3 -m unittest tests.test_tl_tailer tests.test_rb_state_reader
Ran 63 tests
OK

python3 -m unittest discover -s tests
Ran 197 tests
OK
```

### Rekordbox beatgrid-driven autoloop beat position

Implemented behavior:

```text
During ANLZ resolution, FilepathResolver reads beatgrid markers from Rekordbox
analysis files. It prefers non-empty PQT2 and falls back to PQTZ. Marker order,
not the ANLZ beat field, defines the bridge's absolute beat convention.

PQT2 is accepted only when adjacent marker spacing is plausible for beat
markers. Sparse PQT2 tempo-anchor data is rejected so it cannot make autoloop
beatpos advance near-zero over many seconds; the resolver then falls back to
PQTZ or constant-BPM math.

TrackMetadata now carries beatgrid_times_ms, beatgrid_bpms, and beatgrid_source.
first_beat_ms is set to the first grid marker when a valid grid exists.

Autoloop timing maps live elapsed_ms onto the beatgrid. get_beatpos, beat.pos
boundary detection, and arm phrase-lock all use that same grid-derived absolute
beat position. Scripted/non-autoloop timing remains on existing wrapped
constant-BPM behavior.

BPM sends are unchanged: arm_bpm/live-BPM logic remains the outgoing BPM source.
The beatgrid is phase/position authority only.

If ANLZ parsing fails or the grid has fewer than two valid markers, behavior
falls back to existing constant-BPM math.
```

Files/functions changed:

```text
filepath_resolver.py
  _extract_beatgrid_from_anlz()
  _grid_from_tag()
  _candidate_anlz_paths()
  _db_lookup_by_anlz()

models.py
  TrackMetadata.beatgrid_times_ms
  TrackMetadata.beatgrid_bpms
  TrackMetadata.beatgrid_source

state_manager.py
  _compute_beatgrid_position()
  _on_filepath_resolved()
  _apply_lighting(..., mode="autoloop")
  _push_tick()

tests/test_filepath_resolver_beatgrid.py
  PQT2/PQTZ preference, sparse PQT2 rejection, and corrupt/missing fallback
  coverage.

tests/test_live_bpm_service.py
  beatgrid interpolation, autoloop elapsed, beat boundary, phrase-lock, and
  scripted fallback coverage.
```

Validation:

```text
python3 -m unittest discover -s rb_ss_bridge_v2/tests
Ran 43 tests in 1.190s
OK
```

### Autoloop arm phrase-lock synchronization

Implemented behavior:

```text
Master-switch autoloop arm remains immediate. After the immediate arm,
StateManager marks OutputState.autoloop_arm_pending=True and waits for the next
16-beat phrase boundary before sending BPM to SoundSwitch again.

Phrase boundaries are (AUTOLOOP_ARM_PHRASE_BEATS * n). With
AUTOLOOP_ARM_PHRASE_BEATS=16, the lock beats are 16, 32, 48, 64, ...

AUTOLOOP_ARM_PHRASE_BEATS is intentionally separate from AUTOLOOP_BEATS. If
AUTOLOOP_BEATS is changed to an 8-beat loop length, arm phrase-lock still uses
16-beat phrase boundaries.

Pending arm phrase-lock state clears on idle/stop, master change, active track
load, and Rekordbox restart.
```

Files/functions changed:

```text
models.py
  OutputState.autoloop_arm_pending
  OutputState.autoloop_arm_sync_beat
  OutputState.autoloop_arm_pending_since

config.py
  AUTOLOOP_ARM_PHRASE_BEATS = 16

state_manager.py
  _next_autoloop_arm_phrase()
  _maybe_lock_autoloop_arm()
  _clear_autoloop_arm_phrase_lock()
  _apply_lighting(..., mode="autoloop")
  _push_tick()
  reset paths for master change, idle, stop, active track load, RB restart

tests/test_live_bpm_service.py
  unit coverage for 16-beat boundary targets, phrase-lock BPM send, and reset.
```

Simulation findings:

```text
arm at beat 5.2:
  target=16
  no BPM at 15.9
  BPM sent to decks 1,2,3,4 at 16.0

3:00 song at 138 BPM, arm at 2:10.130 / beat 299.3:
  total song beats ~= 414
  target=304
  no BPM at 303.9
  BPM sent to decks 1,2,3,4 at 304.0

deck 1 -> deck 2 transition:
  deck 1 pending target=304 before switch
  master change clears pending target and autoloop arm deck
  deck 2 immediate arm sends deck loads to 2,1,3,4
  deck 2 beat 172.4 targets 176 and sends BPM at 176.0
```

Validation so far:

```text
python3 -m unittest discover -s rb_ss_bridge_v2/tests
```

### Live BPM service and V2 controlled autoloop rearm

Implemented behavior:

```text
LiveBPMService runs as a read-only background service. It attaches to the
current Rekordbox pid/base, scans for per-deck BPM-shaped candidates using
ENGINE STATE/library BPM only as hints, and promotes candidates only after
observed current-session BPM movement.

Autoloop arm snapshots validated live BPM when available. If live BPM is absent,
disabled, stale, unreadable, non-finite, or unvalidated, arm falls back to
d.meta.bpm.

Active-autoloop live BPM follow is enabled by default. During an active
autoloop, if validated live BPM diverges from timing BPM, the bridge sends the
new BPM to all four SoundSwitch deck slots in place and updates
autoloop_arm_bpm/timing_bpm. Sends are rate-limited to avoid 200 Hz push-loop
spam while tracking live pitch changes.

Live testing showed BPM apply alone made SoundSwitch progress move at the right
speed but could leave phrase offset. The bridge now sets a one-shot
autoloop_change_on_next_beat flag after LIVE-BPM-APPLY; the next autoloop beat
uses absolute beat.pos with change=True once, then returns to steady
change=False. This matches the VDJ capture pattern where change=True appears
during tempo-change re-locks, not as a recurring 4-beat marker.

RBSS_LIVE_BPM_FOLLOW=0 disables active follow and keeps timing frozen to the arm
snapshot until disarm/rearm. RBSS_LIVE_BPM_DISABLE=1 disables LiveBPMService
entirely.

Master-transition autoloop arms are default phrase-window behavior. Set
RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0 to disable it. Only autoloop arms immediately
after a master deck switch are affected. Normal track-start autoloop arms remain
immediate. This reflects the live finding that normal starts are already in
phrase, while transition arms can lock SoundSwitch to the wrong phrase offset.

Live result: phrase-window delay by itself did not fix master-transition phrase
offset. Delaying deck-load/autoloop activation to the next 16-beat phrase target
is therefore not sufficient by itself. Keep this as negative evidence; the
transition path must include the re-lock signal around activation rather than
only delaying deck-load timing.

Current default transition behavior: master-transition autoloop arms are
phrase-window aware. If MASTER_CHANGED lands within the configured
start-of-phrase grace window, the bridge snaps immediately: deck-load/loop/play
fire now and a one-shot change=True beat is anchored to the previous 16-beat
phrase boundary. If MASTER_CHANGED lands later in the phrase, the bridge waits
for the next phrase target; when the delayed deck-load fires, it sets the same
one-shot change=True re-lock at the actual delayed arm point. This keeps normal
starts immediate, makes halfway-through-phrase transitions wait for the next
phrase, and avoids repeating the failed delayed-arm-without-relock test.

Live result after adding phrase-window re-lock: transition phrase targets
appeared one beat late. The bridge now targets 16-beat boundaries
`16, 32, 48, ...` instead of the previous `17, 33, 49, ...`. Outgoing
autoloop beat.pos remains absolute and unshifted; the change is the delayed arm
target, not a global beat-value offset.
```

Files/functions changed:

```text
live_bpm.py
  LiveBPMService, LiveBPMReader, LiveBPMStatus, current-session candidate
  validation and invalidation.

state_manager.py
  StateManager.__init__(..., live_bpm=None, live_bpm_follow=None)
  _autoloop_arm_bpm()
  _maybe_apply_live_bpm_follow()
  _apply_lighting() master-transition phrase-window arm/re-lock
  _should_delay_autoloop_master_arm()
  _is_near_autoloop_phrase_start()
  _mark_autoloop_master_relock()
  send_autoloop_deck_load()
  _clear_live_bpm_follow()
  _live_bpm_status_text()
  _live_bpm_follow_status_text()

models.py
  OutputState.autoloop_arm_bpm
  OutputState.autoloop_arm_deck
  OutputState.last_autoloop_status_mono
  OutputState.pending_live_bpm
  OutputState.last_live_follow_bpm
  OutputState.last_live_follow_send_mono
  OutputState.autoloop_change_on_next_beat
  OutputState.autoloop_arm_after_master_change
  OutputState.pending_autoloop_arm_meta
  OutputState.live_follow_generation

__main__.py
  starts/stops LiveBPMService
  RBSS_LIVE_BPM_DISABLE kill-switch warning
  log color mapping for LBPM/RBMEM/autoloop tags

tests/test_live_bpm_service.py
  unit coverage for LiveBPMService validation/fallback and StateManager live BPM
  arm/follow behavior.
```

Runtime flags:

```text
RBSS_LIVE_BPM_DISABLE=1  disables LiveBPMService entirely.
RBSS_LIVE_BPM_FOLLOW=0   disables default active-autoloop live BPM follow.
RBSS_AUTOLOOP_MASTER_PHRASE_ARM=0  disables default phrase-window master-transition autoloop arms.
```

Validation so far:

```text
python3 -m unittest discover -s rb_ss_bridge_v2/tests
python3 -m compileall -q rb_ss_bridge_v2

Live run confirmed:
  [SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
  next autoloop beat sends absolute beat.pos with change=True once
  [SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ...
  SoundSwitch stayed in phrase during BPM changes after the one-shot re-lock.
```

### `rb_memory.py`, `state_manager.py`, `__main__.py`

Proposed/implemented behavior:

```text
Deck 2 discovery now has a conservative paused/startup provisional path.

RBMemoryReader receives a read-only Deck 2 elapsed hint from StateManager.
On each unresolved Deck 2 retry, it logs attempt number, scan window, and
target_ms. Scan windows widen progressively from ±0x10000 to ±0x20000 to
±0x40000 across retries. Normal unresolved retries remain 30s; if a provisional
candidate has been found, retries run every 5s so the candidate can be promoted
soon after Deck 2 starts playing.

If Deck 2 is not moving, the moving zone scan finds no hits, and StateManager
has a fresh TL/MTC elapsed estimate, RBMemoryReader scans around inner1 for an
aligned ObjC candidate whose +0x0c i32 value is close to that elapsed estimate.
That candidate is stored as deck2_provisional only if it is a clear best match:
ties within 250ms of the best candidate are treated as ambiguous and ignored.

Provisional candidates are sampled in later 4s validation windows and are only
promoted to deck2_inner after the existing strict 38k-50k samples/sec movement
validation passes. Provisional candidates are not published to PositionCache and
do not drive SoundSwitch timing before strict promotion.
```

Files/functions changed:

```text
state_manager.py
  StateManager.get_deck_elapsed_ms(deck)

__main__.py
  RBMemoryReader construction now passes deck_elapsed_hint=sm.get_deck_elapsed_ms

rb_memory.py
  added Callable import
  added _D2_STATIC_TOL_MS, _D2_STATIC_GAP_MS, _D2_SCAN_WINDOWS,
        _D2_RETRY_S, _D2_PROVISIONAL_RETRY_S
  added _scan_static_elapsed_candidates()
  RBSession.__init__: added _deck2_provisional
  RBSession.start_deck2_resolution(..., target_ms=None, scan_window=0x10000)
  RBSession._eval_deck2_candidates(): promote/reject provisional candidates
  RBMemoryReader.__init__(..., deck_elapsed_hint=None)
  RBMemoryReader._tick(): pass target_ms and progressive scan_window into resolution
                          retry provisional candidates every 5s
  RBMemoryReader._try_attach(): reset Deck 2 attempt count on attach
```

Reasoning:

```text
The existing strict resolver can only prove Deck 2 while the position field is
moving. When Deck 2 is paused at startup, the true field is flat and cannot be
strictly distinguished by rate. A paused/static scan can still find a likely
candidate if TL/MTC has a current elapsed estimate, but this evidence is weaker
than movement. Therefore the implementation stores only a provisional pointer
and still requires later movement validation before committing Deck 2 memory.

Progressive widening reduces the chance that a future restart places inner2
outside the initial ±0x10000 scan window, without hardcoding session-local
inner1-relative offsets.
```

Expected behavior:

```text
If Deck 2 is playing at startup, behavior remains strict movement discovery and
commit as before, now with logged attempt/window/target_ms.

If Deck 2 is paused at startup and TL/MTC has a fresh elapsed estimate, the
bridge may log a unique deck2 provisional candidate. Deck 2 remains pos=no-snap
until the candidate later passes movement validation. Once Deck 2 starts moving,
the provisional candidate enters the next retry window within about 5s, not the
normal 30s unresolved retry interval.

If static evidence is ambiguous, no provisional candidate is stored and the
bridge keeps retrying with MTC/TC fallback.
```

Risk:

```text
False static matches are possible while paused. Mitigation: provisional
candidates are not published to PositionCache and must pass strict movement
validation before use.

Fresh TL/MTC elapsed may be unavailable immediately after startup, in which case
paused discovery cannot form a target_ms and falls back to the old retry path.

Wider scans read more memory and can add short blocking work in RBMemoryReader,
but do not block StateManager.
```

Validation so far:

```text
python3 -m compileall -q . passed.
Live Rekordbox/SoundSwitch validation still needed after restart, ideally with
Deck 2 paused first, then played to verify provisional promotion.
```

### `rb_memory.py` broad ObjC heap fallback

Proposed/implemented behavior:

```text
Deck 2 discovery now has a broad moving fallback for sessions where the true
Deck 2 inner is outside the near-inner1 scan window.

On attach, RBMemoryReader caches vmmap-derived ObjC/nano heap regions instead
of the previous standard-heap scan regions. After repeated unresolved attempts
(attempt >= 4), if near-inner1 moving scan finds no hits and StateManager has a
target_ms hint, RBSession scans readable ObjC regions in bounded chunks.

The broad scan looks for i32 fields that:
  advance at 38k-50k samples/sec,
  are within 10s of target_ms,
  map back to an aligned ObjC inner pointer,
  have a readable/ObjC-like secondary pointer or zero secondary.

The broad scan adds candidates as deck2 candidate D(heap). These candidates
still enter the same 4s strict validation window and are not committed until
_strict_eval_candidate() passes.
```

Files/functions changed:

```text
rb_memory.py
  added _objc_regions_from_vmmap()
  added _scan_objc_heap_moving()
  added _D2_HEAP_SCAN_MIN_ATTEMPT, _D2_HEAP_CHUNK_BYTES,
        _D2_HEAP_MAX_BYTES, _D2_HEAP_TARGET_TOL_MS,
        _D2_HEAP_MAX_CANDIDATES
  RBSession.start_deck2_resolution(..., attempt=1): adds D(heap) candidates
  RBMemoryReader._tick(): passes attempt into start_deck2_resolution()
  RBMemoryReader._try_attach(): caches ObjC regions and logs objc_regions count
```

Reasoning:

```text
Live restart evidence showed Deck 2 playing around 40s but inner1±0x40000 had
zero moving hits and zero static target hits. The bad container fast path still
rejected as a repeating counter. This indicates the true Deck 2 position field
can land outside the current near-inner1 window, so the resolver needs a
bounded process-heap fallback that does not assume a fixed inner1-relative
offset.
```

Expected behavior:

```text
Attempts 1-3 keep using the cheap near-inner1 path with progressive windows.
Attempt 4+ can log:

ObjC heap moving scan regions=N chunks=M bytes=B target=Tms: H hit(s)
deck2 candidate D(heap): 0x...
deck2 candidate 0x... PASS: rate=...
deck2 inner committed: 0x...
```

Risk:

```text
The broad scan is heavier than the near-inner1 scan. It is bounded to 128 MB
per attempt and only runs after repeated failures. It runs in RBMemoryReader,
not StateManager, so SoundSwitch event-loop timing is not blocked.

If the true Deck 2 field is outside the first 128 MB of readable ObjC chunks,
the fallback may still miss it. Live logs should include regions/chunks/bytes
so the cap can be adjusted with evidence.
```

Validation so far:

```text
python3 -m compileall -q . passed.
Live validation needed against the restart session that produced
inner1±0x40000 0 hit(s) while Deck 2 was playing.
```

### `rb_memory.py`, `state_manager.py`, `__main__.py` play-triggered discovery

Proposed/implemented behavior:

```text
Deck 2 discovery now starts immediately when TL reports Deck 2 playback and
Deck 2 memory is unresolved. The play signal is only a scheduling hint; it does
not affect play-state authority or memory validation.

While Deck 2 is idle/paused, unresolved discovery keeps the low 30s retry
cadence and broad ObjC heap scans are skipped. While Deck 2 is playing,
unresolved discovery uses a 5s retry cadence. The broad D(heap) fallback is
eligible after the configured failed-attempt threshold if Deck 2 is currently
playing or was seen playing within the recent-play window.

SoundSwitch continues to receive MTC/TL fallback until strict Deck 2 memory
validation commits deck2_inner. Provisional and candidate pointers still do not
publish PositionCache snapshots.
```

Files/functions changed:

```text
state_manager.py
  StateManager.get_deck_playing(deck) -> bool

__main__.py
  RBMemoryReader construction now passes deck_playing_hint=sm.get_deck_playing

rb_memory.py
  renamed RBMemoryReader._scan_regions to _objc_regions
  RBMemoryReader.__init__(..., deck_playing_hint=None)
  added _D2_RETRY_IDLE_S and _D2_RETRY_PLAYING_S
  added _D2_PLAY_RECENT_S
  added _d2_was_playing rising-edge state
  added _d2_play_seen_at recent-play timestamp
  RBMemoryReader._tick(): detects Deck 2 False->True play transition,
                          starts resolution immediately,
                          uses idle/playing retry cadences,
                          passes recent-play state for D(heap) gating
  RBSession.start_deck2_resolution(..., deck2_playing=False):
                          gates D(heap) broad scan on Deck 2 playing
```

Expected logs:

```text
[D2] playing
RBMemoryReader: deck2 play trigger — starting resolution
RBMemoryReader: starting deck-2 resolution attempt=N window=0x... target_ms=...
...
deck2 candidate 0x... PASS: rate=...
deck2 inner committed: 0x...
```

Reasoning:

```text
The previous retry loop could wait up to 30s after TL detected Deck 2 playback.
Live use needs discovery to start when Deck 2 starts moving, while avoiding
expensive broad heap scans during long idle periods. This change makes scanning
play-triggered without changing the source priority hierarchy.
```

Risk:

```text
If deck_playing_hint is unavailable, the bridge falls back to idle cadence
behavior. If TL PLAY arrives before MTC/TL elapsed has a target_ms, the resolver
still runs, but broad D(heap) requires target_ms and will wait for a later short
retry. The recent-play window exists because TL load/play/pause transitions can
briefly toggle during a validation window; strict movement validation still
prevents false commits.
```

Validation so far:

```text
python3 -m compileall -q . passed.
Live validation needed: fresh Rekordbox idle startup, Deck 2 play trigger,
and playing-session D(heap) fallback.
```

### `rb_memory.py` ObjC vmmap region parser fix

Proposed/implemented behavior:

```text
ObjC/nano heap region extraction now finds address ranges anywhere in a vmmap
line, not only at the beginning of the line. This allows lines such as:

MALLOC_NANO 600000000000-600020000000 ... rw-/rwx ...

to produce ObjC regions for the broad D(heap) scan.
```

Reasoning:

```text
Live Test B logged `objc_regions=0`, so D(heap) could not run. Direct vmmap
inspection showed the relevant MALLOC_NANO line starts with the region type,
then the address range. The previous regex required the address at line start.
```

Validation so far:

```text
Local parser check against the observed MALLOC_NANO line returned one
0x600000000000-0x600020000000 region.
python3 -m compileall -q . passed.

Live validation:
RBMemoryReader: attached pid=2512 base=0x104388000 objc_regions=1
ObjC heap moving scan regions=1 chunks=32 bytes=134217728 target=10129ms: 4 hit(s)
deck2 candidate D(heap): 0x6000023f6160
deck2 candidate 0x6000023f6160 PASS: rate=44116 samples=57 ms=36210
deck2 inner committed: 0x6000023f6160
```

### `osl_output.py`, `__main__.py` SoundSwitch DNS-SD lifetime fix

Proposed/implemented behavior:

```text
SoundSwitchDiscovery now retains Zeroconf and ServiceBrowser handles for the
life of the bridge and closes Zeroconf on shutdown. __main__.py now keeps the
SoundSwitchDiscovery instance in a local variable instead of constructing and
discarding it immediately.

Discovery now handles both Added and Updated DNS-SD events, waits up to 3s for
service info, selects an IPv4 address explicitly, and logs when service info or
IPv4 is unavailable.
```

Reasoning:

```text
Live restart tests showed repeated fallback connection failures while
SoundSwitch was open. The previous code called SoundSwitchDiscovery(conn).start()
without retaining the discovery object, and start() also kept Zeroconf/browser
handles only in locals. That could allow DNS-SD discovery to disappear after
startup and leave OS2L retrying only the localhost fallback port.
```

Expected behavior:

```text
On bridge restart with SoundSwitch open:

SoundSwitchDiscovery: DNS-SD browser started
SoundSwitchDiscovery: found ... at host:port
OS2L: connected to SoundSwitch at host:port
```

Validation so far:

```text
System dns-sd sees _os2l._tcp.local.
Standalone Python Zeroconf probe resolved SoundSwitch at 127.0.0.1:55927.
python3 -m compileall -q . pending after final edits.
```

Risk:

```text
Low. This only extends object lifetimes and adds shutdown cleanup. Fallback
connection behavior remains unchanged if DNS-SD cannot start or finds nothing.
```

### `rb_memory.py`

Proposed/implemented behavior:

```text
For Deck 2 snapshots, set track_length_ms=0.
```

Reasoning:

```text
The runtime-discovered Deck 2 inner is proven by the +0x0c i32 position field.
Its surrounding layout is not proven to match Deck 1.
Live evidence showed +0x08 can mirror current position rather than track length.
Returning that as track_length_ms creates bogus lsof duration matching.
Deck 2 filepath resolution should rely on ANLZ/title fallback instead.
```

Validation so far:

```text
RBMemoryReader still resolves Deck 2 after restart.
Deck 2 elapsed advances correctly.
Deck 2 len now reports 0ms instead of mirroring elapsed.
```

### `state_manager.py`

Proposed/implemented behavior:

```text
Apply the 45-second TC freshness guard to the snap.elapsed_ms == 0 fallback path.
```

Reasoning:

```text
The no-snapshot TC fallback already has a 45-second guard.
The zero-position fallback previously did not.
Using stale TC anchors when a memory snap is zero can synthesize drifted position.
```

Validation so far:

```text
compileall passed after the change.
Deck 2 memory snapshots still resolve and advance.
```

## Deck 2 Discovery Evidence To Preserve

Session 1:

```text
pid=83311
base=0x102a0c000
container=0x1596c9a00
inner1=0x600006b28410
Deck 2 field=0x600006b284ec
inner2=0x600006b284e0
offset=inner1+0xd0
playing rate≈44.1 kHz
paused delta=0
cue reset≈50 ms
container+0x480/+0x488 rejected as flat pos=1
```

Session 2:

```text
pid=88640
base=0x100548000
container=0x10cd1e200
inner1=0x6000070e5520
Deck 2 field=0x6000070e84ec
inner2=0x6000070e84e0
offset=inner1+0x2fc0
scan rate=44102.4 samples/sec
playing rate=44158.0 samples/sec
paused delta=0
container+0x480/+0x488 rejected as flat pos=1
```

Full bridge runtime log:

```text
deck2 candidate B(container-0x270+0x78): 0x6000000916e0
ObjC zone scan: pos=inner1+0x2fcc inner_ptr=inner1+0x2fc0
deck2 candidate C(zone): 0x6000070e84e0
deck2 candidate 0x6000070e84e0 PASS: rate=44045 samples=57 ms=21812
deck2 inner committed: 0x6000070e84e0
```

Conclusion:

```text
Deck 2 inner pointer is session-dependent.
Do not hardcode inner1+0xd0 or inner1+0x2fc0.
Runtime behavioral scan is required.
```

## Autoloop Beatphase Investigation - 2026-05-04

Context:

```text
Unscripted SoundSwitch autoloop appeared to repeat/reset every 4 beats.
AUTOLOOP_BEATS was already changed to 16, but that alone did not fix it.
```

Evidence:

```text
VDJ/SoundSwitch capture used continuous get_beatpos and continuous beat.pos.
Bridge baseline used modulo-4 get_beatpos and modulo-4 beat.pos.
Bridge baseline also sent change=True every 4 beats.
Autoloop arms were not repeatedly firing during stable playback.
```

Current active autoloop timing behavior:

```text
Autoloop get_beatpos sends absolute beat position.
Autoloop beat.pos sends absolute beat count.
Scripted/non-autoloop behavior remains wrapped.
change=True still fires every 4 beats.
```

Current diagnostic logging:

```text
state_manager.py:
- [SS][AUTOLOOP-ARM] logs deck, mirror, elapsed, source, timing_bpm, arm_bpm, meta_bpm, loop length, filepath, previous file.
- [SS][AUTOLOOP-ARM-PENDING] logs the current absolute beat and the phrase-lock target beat.
- [SS][AUTOLOOP-ARM-LOCKED] logs the phrase-lock BPM send beat and BPM.
- [SS][AUTOLOOP-TICK] logs periodic elapsed, absolute beat, timing_bpm, arm_bpm, meta_bpm, live_bpm, follow state, filepath.
- [SS][LIVE-BPM-APPLY] logs default-on gated BPM transport updates.

models.py:
- OutputState.last_autoloop_status_mono rate-limits [SS][AUTOLOOP-TICK].
- OutputState.last_live_follow_send_mono rate-limits active-autoloop BPM follow sends.

osl_output.py:
- [SS][deck-load] logs outgoing deck-load filepath, ssid state, bpm_out, meta_bpm, fallback_bpm, loop state, play state.
```

Observed result:

```text
SoundSwitch autoloop progress bar no longer restarts every 4 beats with Test A+B active.
Progress speed changes with BPM as expected.
Autoloop arm phrase-lock targets 16-beat boundaries: 16, 32, 48, ...
Simulated arm at beat 299.3 in a 3:00 138 BPM track targeted beat 304.
Simulated deck 1 -> deck 2 master change cleared deck 1 pending state and gave
deck 2 its own target.
Live BPM follow now sends gated transport BPM updates in place and does not
touch autoloop arm/unarm or master-transition ordering.
```

Follow-up:

```text
Inspect first AUTOLOOP-ARM, deck-load, AUTOLOOP-TICK, and LIVE-BPM-APPLY after stop -> pitch change -> play.
Check whether beatpos_out starts phase-aligned with Rekordbox or offset.
Steady autoloop change markers are now false; preserve that unless a capture proves an activation-only re-anchor needs change=True.
```

Separate resolver bug:

```text
lsof can overwrite a correct title/ANLZ resolution with the wrong file.
Example observed: intended track resolved at bpm=128, then lsof resolved Click Sound 01 Electronic.wav bpm=0 and autoloop armed the wrong file.
Prevent lower-confidence/stale lsof results from replacing a better title/ANLZ result.
```

## Direct Master Runtime Validation And TL-Retirement Planning - 2026-05-06

Historical status at the time of this section:

```text
Direct master was still observational at this point in the log.
Runtime master, TL TC fallback, and startup ENGINE STATE reconstruction remain
TL-authoritative. Guarded direct authority has since landed for ANLZ (B1),
position chain (B2), play/pause (B3), track load (B4), and scripted arm/clear
(B5); see the newer sections above.
LiveBPMService is already the first and most mature direct-first TL-reduction
path: offset-table BPM is used when valid, with discovery and metadata/ENGINE
STATE fallback when unavailable.
```

Superseded by later B6 work:

```text
As of the 2026-05-07 B6 implementation and live validation,
RBSS_MASTER_DIRECT=1 can route runtime MASTER_CHANGED source='rb_state' through
the main RBStateReader path while direct master is currently readable and valid.
The bounded DirectMasterRuntimeObserver remains shadow-only; runtime direct
master authority is the separate guarded B6 path. See
docs/history/tl_retirement_process_log.md.
```

Implemented validation support:

```text
rb_state_reader.py:
- startup direct-master probe and settle observation
- bounded runtime direct-master observer
- TL-only TLMasterSnapshot comparison source
- runtime summary fields:
  outcome
  final_direct_master
  final_tl_master
  transition_count
  mismatches
  first_valid_elapsed_s
  comparison_source=tl_master_snapshot
  authority=tl_log

tests/test_rb_state_reader.py:
- focused coverage for runtime summary fields and direct-vs-TL outcomes
```

Live evidence summary:

```text
Clean deck1 stable windows:
- outcome=became_valid_and_matched_tl
- final_direct_master=deck1
- final_tl_master=deck1
- transition_count=1
- mismatches=0

Deck2 startup cases:
- direct read deck2 while TL snapshot initially reported deck1
- TL/ENGINE later updated to deck2
- final direct/TL matched deck2
- interpretation: direct Rekordbox master may surface current master earlier
  than the TL-only snapshot becomes fresh at startup

Single intentional master switch:
- transition_count=2
- final direct/TL matched deck2
- not flapped
```

Repo-local continuity files:

```text
docs/validation/direct_master_runtime_validation.md
docs/validation/direct_master_runtime_runbook.md
docs/validation/direct_master_runtime_results_template.md
docs/history/tl_retirement_process_log.md
```

Historical near-term decision:

```text
Hold runtime master TL authority.
At the time, the only plausible authority-adjacent next step was a future master startup-seed
experiment design, if explicitly authorized, with strict fail-closed behavior.
Do not generalize LiveBPM readiness to master or TL-TC retirement. TL TC
fallback and runtime master remain out of scope for retirement until separately
authorized.
```

Current decision after B6:

```text
Runtime master has a guarded direct-authority path behind RBSS_MASTER_DIRECT=1.
TL remains fail-closed fallback whenever direct master is unsupported,
unreadable, not yet warmed up, or reporting the no-master sentinel.
```
