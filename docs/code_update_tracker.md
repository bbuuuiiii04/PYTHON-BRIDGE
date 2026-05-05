# Code Update Tracker For Claude Code

Updated: 2026-05-04

## Collaboration Rule

Do not edit bridge code without explicit user approval.

Before any code edit:

1. Propose the exact file and function to change.
2. Explain the evidence and reasoning.
3. State the expected behavior change and risk.
4. Wait for the user to approve.

Markdown documentation edits are allowed when requested.

## Current Uncommitted Code Changes For Review

These code changes exist in the worktree and should be reviewed before commit:

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

V1 remains the default active-autoloop behavior: timing is frozen to the arm
snapshot until disarm/rearm.

V2 is enabled with RBSS_LIVE_BPM_FOLLOW=1. During an active autoloop, if
validated live BPM diverges from timing BPM, the bridge tracks one pending
update, waits for 1.5s stability, then sends BPM to all four SoundSwitch deck
slots at the next absolute beat where beat % 8 == 1 and beat > 1.

SoundSwitch rearms autoloops when it receives BPM. The V2 BPM send is therefore
an intentional controlled rearm at a phrase-safe beat, not a transparent
mid-loop timing update.
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
  _next_live_bpm_follow_beat()
  _clear_live_bpm_follow()
  _live_bpm_status_text()
  _live_bpm_follow_status_text()

models.py
  OutputState.autoloop_arm_bpm
  OutputState.autoloop_arm_deck
  OutputState.last_autoloop_status_mono
  OutputState.pending_live_bpm
  OutputState.pending_live_bpm_since
  OutputState.pending_live_bpm_target_beat
  OutputState.last_live_follow_pending_log_mono
  OutputState.last_live_follow_bpm
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
RBSS_LIVE_BPM_FOLLOW=1   enables V2 controlled phrase-boundary BPM/rearm.
```

Validation so far:

```text
python3 -m unittest discover -s rb_ss_bridge_v2/tests
python3 -m compileall -q rb_ss_bridge_v2

Live run confirmed:
  [SS][LIVE-BPM-PENDING] deck=1 current=130.00 pending=134.30 target_beat=129
  [SS][LIVE-BPM-APPLY] deck=1 bpm=134.30 beat=129
  [SS][AUTOLOOP-TICK] ... timing_bpm=134.30 arm_bpm=134.30 ...
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
- [SS][AUTOLOOP-TICK] logs periodic elapsed, absolute beat, timing_bpm, arm_bpm, meta_bpm, live_bpm, follow state, pending state, filepath.
- [SS][LIVE-BPM-PENDING] logs first/rate-limited pending V2 BPM and target beat.
- [SS][LIVE-BPM-APPLY] logs the phrase-boundary BPM send / controlled SoundSwitch rearm.

models.py:
- OutputState.last_autoloop_status_mono rate-limits [SS][AUTOLOOP-TICK].
- OutputState.last_live_follow_pending_log_mono rate-limits pending replacement logs while pitch is moving.

osl_output.py:
- [SS][deck-load] logs outgoing deck-load filepath, ssid state, bpm_out, meta_bpm, fallback_bpm, loop state, play state.
```

Observed result:

```text
SoundSwitch autoloop progress bar no longer restarts every 4 beats with Test A+B active.
Progress speed changes with BPM as expected.
V2 live BPM follow intentionally sends BPM at phrase-safe absolute beats because
SoundSwitch rearms autoloop on BPM sends.
```

Follow-up:

```text
Inspect first AUTOLOOP-ARM, deck-load, AUTOLOOP-TICK, LIVE-BPM-PENDING, and LIVE-BPM-APPLY after stop -> pitch change -> play.
Check whether beatpos_out starts phase-aligned with Rekordbox or offset.
Test C is not applied: autoloop change=True every AUTOLOOP_BEATS or always false.
```

Separate resolver bug:

```text
lsof can overwrite a correct title/ANLZ resolution with the wrong file.
Example observed: intended track resolved at bpm=128, then lsof resolved Click Sound 01 Electronic.wav bpm=0 and autoloop armed the wrong file.
Prevent lower-confidence/stale lsof results from replacing a better title/ANLZ result.
```
