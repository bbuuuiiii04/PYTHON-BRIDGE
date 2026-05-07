# TimecodeLink Retirement Process Log

Purpose: continuously track the current evidence, decisions, and next steps for
phased TimecodeLink reduction in `rb_ss_bridge_v2`.

This is a repo-local continuity file for future agents. It does not change
runtime behavior and does not promote any authority source.

## Terminology

**A items (evidence tracks):** Shadow observation runs only. A log line is added
to compare the direct signal against TL side-by-side. No authoritative behavior
changes. The bridge behaves identically to before — the DJ and SoundSwitch see
nothing different. A items are run before any corresponding B item.

**B items (narrow retirements):** Wire one specific direct signal to the
authoritative path. TL stays running as a fallback. Each B item has an env-var
kill-switch (e.g. `RBSS_ANLZ_DIRECT=1`) that lets you revert instantly at a gig
without restarting. B items are implemented by Codex after the corresponding
A item is confirmed.

**C items:** Startup-only or one-off changes that don't fit A/B cleanly.
Currently only C1 (direct master startup seed, fail-closed to TL).

**The rule:** Never implement a B item before its A item is confirmed. Never
implement a B item without a kill-switch. Never skip the prerequisite sequence
(B1 → B2 → B3 → B4 → B5).

## Current Ground Rules

- TL retirement is signal-by-signal, not a single switch.
- Evidence gathering (A items) must stay separate from retirement (B items).
- `StateManager` does not currently arbitrate by event source.
- TL remains authoritative unless a later explicit, narrow migration changes
  one signal with fail-closed behavior.
- No direct master authority has been promoted.
- No play/pause, track-load, timing, scripted-routing, ANLZ, or TL TC authority
  has been promoted.

## Current Repo State

- `TLLogTailer` remains authoritative for TL log and ENGINE STATE events.
- `LiveBPMService` is the strongest direct-first subsystem and already uses
  offset-table BPM when valid.
- Direct master support exists as:
  - one-shot startup probe
  - startup settle/retry observation
  - bounded runtime observer
  - TL-only `TLMasterSnapshot` comparison source
- Direct master logs remain observational and use `authority=tl_log`.
- Direct master runtime comparison uses `comparison_source=tl_master_snapshot`.
- `rb_memory.py` remains unchanged in this process.
- Lighting/output behavior remains unchanged.

## Direct BPM Status

Direct BPM is already the most mature TL-reduction path in the repo.

Current behavior:

- `LiveBPMService` reads Rekordbox displayed BPM directly from process memory.
- On supported Rekordbox versions, it uses the per-version offset-table BPM
  chains from `rb_offsets.py`.
- If the offset-table chain is unsupported, unreadable, stale, or invalid, it
  falls back to discovery/validation and ultimately to metadata/ENGINE STATE
  fallback.
- It is used for autoloop arm snapshots and default-on active autoloop BPM
  follow when fresh and valid.
- It does not change master deck, play/pause, track load, or timing authority.

Evidence and handoff docs:

- `docs/live_bpm_findings.md`
- `docs/live_bpm_handoff.md`
- `docs/bridge_design.md` Live BPM section

Current TL-retirement interpretation:

- TL/ENGINE BPM is no longer the primary live BPM source when direct BPM is
  valid.
- TL/metadata BPM remains the fail-closed fallback.
- Direct BPM readiness must not be generalized to direct master, direct
  play/pause, direct track load, scripted routing, ANLZ, or TL TC retirement.

Remaining Direct BPM risks:

- unsupported Rekordbox versions
- stale reads after Rekordbox restart or session/base change
- same/near-same BPM deck separation
- discovery latency when offset-table reads are unavailable
- validation windows where the wrong deck moves or no pitch movement occurs

No current action is needed for Direct BPM in the TL-retirement sequence except
to preserve its direct-first, fail-closed behavior and keep validation logs
visible.

## Direct Master Live Evidence So Far

### Clean Deck 1 Stable Startup / No-Touch Runs

Observed:

- `outcome=became_valid_and_matched_tl`
- `first_valid_master=deck1`
- `final_direct_master=deck1`
- `final_tl_master=deck1`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=1`
- `mismatches=0`
- `comparison_source=tl_master_snapshot`
- `authority=tl_log`

Judgment: encouraging. Direct master is immediate, readable, stable, and aligned
with TL in clean deck1 windows.

### Dirty Deck 2 Stable-Window Runs

Observed pattern:

- direct reads `deck2`
- TL snapshot initially says `deck1`
- TL/ENGINE later updates to `deck2`
- final direct and TL match `deck2`
- `transition_count=1`
- `mismatches` observed during startup freshness gap

Representative fields:

- `outcome=became_valid_but_mismatched_tl`
- `first_valid_master=deck2`
- `final_direct_master=deck2`
- `final_tl_master=deck2`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=1`
- `mismatches=1` or more

2026-05-06 22:43 EDT observed run:

- scenario: deck2 loaded as master before bridge startup; no intentional master
  switch during bounded runtime observer window
- startup TL initial state: `read_initial_state: active_deck=1`
- direct initial probe: `raw=1 direct_master=deck2 reason=ok`
- TL startup comparison: `tl_startup_master=deck1 corroboration=disagree`
- runtime first valid: `first_valid_master=deck2`
- runtime TL at first valid: `tl_master=deck1`
- TL/ENGINE later update:
  `MASTER_CHANGED deck1 -> deck2 reason=engine_state`
- summary:
  `attempts=31 outcome=became_valid_but_mismatched_tl supported_version=1 readable=1 version=7.2.11 first_valid_master=deck2 final_direct_master=deck2 final_raw=1 final_tl_master=deck2 tl_master_at_first_valid=deck1 first_valid_elapsed_s=0.00 transition_count=1 mismatches=20 comparison_source=tl_master_snapshot authority=tl_log`

2026-05-06 additional run (A1 confirmation):

- scenario: deck2 loaded as master before bridge startup; same clean no-touch
  attempt; intended to capture `tl_master_at_first_valid=deck2 mismatches=0`
- result: same `became_valid_but_mismatched_tl` pattern
- ENGINE STATE updated to deck2 only after the bounded window opened; direct
  master read deck2 immediately; TL snapshot held deck1 until ENGINE STATE fired
- conclusion: this is a structural artifact of ENGINE STATE cadence (~15s),
  not a fluke of the prior run and not evidence of direct-master instability

Structural finding: a clean deck2 symmetric run with `tl_master_at_first_valid=deck2
mismatches=0` is not achievable in a normal startup scenario. TL's config.yaml
persists the previous master and ENGINE STATE requires up to ~15s to fire after
bridge startup. The only way to achieve `tl_master_at_first_valid=deck2` is if
TL happened to fire an ENGINE STATE in the window between the user switching to
deck2 and bridge startup — a narrow timing condition that cannot be reliably
reproduced. Further deck2 clean-run attempts will keep hitting this same pattern.

Judgment: encouraging for direct readability and stability, but not a clean
deck2 no-mismatch proof. The narrow interpretation is that direct Rekordbox
master may surface current master state earlier than the TL-only snapshot
becomes fresh at startup. The mismatch is consistently explained by ENGINE STATE
cadence, not by direct-master instability.

What this proves:

- direct master can read deck2 immediately while TL-only snapshot still holds
  the previous deck1 startup state
- the TL-only snapshot later converges to deck2 when the slower ENGINE STATE
  update reaches the bridge
- direct master remained stable at deck2 in the observer window
- this pattern is structural and reproducible, not session-specific noise
- chasing a clean deck2 mismatches=0 symmetric run via normal startup is not
  a productive evidence path; it cannot close the structural ENGINE STATE gap

What remains open:

- whether direct master is suitable only as a narrowly fail-closed startup seed
  experiment (the structural finding above supports this framing)
- a clean deck2 no-touch run is only possible if the bridge is started after TL
  has already fired a fresh ENGINE STATE for deck2; this is not worth pursuing
  as a standard evidence run

Smallest justified next step:

- do not repeat the deck2 startup run; the structural finding is now established
- move to evidence-gathering for other signals (ANLZ shadow parity, live_pos
  absolute value shadow) per the corrected retirement plan

### Intentional Single Master Switch

Observed:

- `first_valid_master=deck1`
- `final_direct_master=deck2`
- `final_tl_master=deck2`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=2`
- `mismatches=1`
- outcome did not become `flapped`

Judgment: encouraging for single-switch behavior. Direct moved once, ended
aligned with TL, and did not flap. The mismatch appears consistent with a
switch-time TL/direct timing race.

## Current Conclusions

Convincingly proven:

- direct master is live-readable on the tested Rekordbox `7.2.11` setup
- raw `0` maps to bridge `deck1`
- raw `1` maps to bridge `deck2`
- first valid direct master appears immediately in observed runs
- clean deck1 stable windows match TL with `mismatches=0`
- a single direct transition during an intentional switch gives
  `transition_count=2`, not `flapped`
- final direct/TL state has matched in reviewed useful runs

Not yet proven:

- direct master should become runtime authority
- a clean deck2 stable-window run where TL is fresh at first valid and
  `mismatches=0`
- direct play/pause readiness, despite prior investigation
- direct track-load authority readiness
- direct startup metadata replacement
- ANLZ path replacement
- scripted OSC / scripted ID replacement
- TL TC fallback removal

## TL Dependency Retirement Roadmap

This roadmap is signal-by-signal. It is not a plan to turn TimecodeLink off, and
it does not promote direct runtime authority.

### 1. Live BPM: Partly Migrated / Preserve

Status:

- strongest direct-first subsystem today
- `LiveBPMService` uses direct offset-table BPM when valid
- TL/metadata/discovery remain fail-closed fallbacks

Already covered:

- direct BPM readiness has been investigated separately from direct master
- direct BPM is used for autoloop arm snapshots and default-on active autoloop
  BPM follow when fresh and valid

Next:

- preserve current direct-first/fallback behavior
- do not generalize Live BPM readiness to master, play/pause, timing, track
  load, scripted routing, ANLZ, or TL TC fallback

### 2. Direct Master: Evidence Complete / Startup-Seed Candidate

Status:

- observational/shadow-only
- direct master is readable and stable in all reviewed runs
- direct master consistently surfaces the current Rekordbox master faster than
  TL ENGINE STATE reaches the bridge at startup
- TL/ENGINE remains runtime authority

Evidence collection complete:

- clean deck1 stable startup/no-touch runs matched TL with `mismatches=0`
- deck2 startup runs show direct deck2 immediately, stale TL deck1 initially,
  and later TL convergence to deck2 after ENGINE STATE fires; this is
  structurally reproducible and not a noise artifact
- intentional single switch showed one direct transition, no flap, and final
  direct/TL agreement
- additional A1 deck2 confirmation run reproduced the same structural pattern;
  further deck2 clean-run attempts are not a productive evidence path

Structural finding (settled):

- the deck2 `tl_master_at_first_valid=deck2 mismatches=0` symmetric run cannot
  be achieved in a normal startup scenario due to ENGINE STATE cadence; the
  startup visibility gap is confirmed as structural, not session noise
- this is exactly the use case for the startup-seed experiment: direct master
  can seed the correct initial state that TL ENGINE STATE has not yet delivered

Active roadmap item: design a narrow startup-seed experiment

Startup-seed design boundaries (do not implement until explicitly authorized):

- startup only; no runtime authority change
- direct must be supported, readable, valid `deck1`/`deck2`, and stable
- fail closed to TL on unsupported, unreadable, `none`, or unstable
- TL/ENGINE remains runtime authority after startup seed
- no broad arbitration framework
- no play/pause, timing, lighting/output, scripted routing, ANLZ, TL TC, or
  `rb_memory.py` changes

No-go conditions:

- direct final master disagrees with TL final master after settle
- direct flaps or returns to `none`
- the rule requires runtime arbitration or direct runtime authority

Do not repeat:

- the deck2 dirty startup run; the structural finding is now established
- any run whose purpose is to re-prove that direct master is faster than
  ENGINE STATE visibility at startup

### 3. Existing RBMemoryReader Scan Replacement: Important TL-Removal Lane

Status:

- `RBMemoryReader` already exists and currently owns high-cadence
  `PositionCache` snapshots
- Deck 1 has a proven direct path in `rb_memory.py`
- Deck 2 may still require ordered resolution attempts and scans before a
  validated inner pointer is committed
- TimecodeLink reverse engineering recovered per-version `OffsetVersion`
  chains for live per-deck position samples

Important distinction:

- this is not "build a Rekordbox memory puller"; the bridge already has one
- the roadmap question is whether TL reverse-engineering findings can replace
  or shortcut the expensive `rb_memory.py` scan path, especially for instant
  deck1/deck2 live position access
- this is separate from direct master runtime authority

Already covered:

- `docs/timecodelink_integration_analysis.md` shows TL reads per-deck live
  position through `OffsetVersion+0x60` chains
- TL infers play/pause from whether the live position field changed between
  polls, not from a dedicated play boolean
- `rb_offsets.py` / `rb_state_reader.py` already carry shipped TL-style chains
  for master, live BPM, live position, and track info on supported Rekordbox
  versions
- `docs/bridge_design.md` documents the current `rb_memory.py` Deck-2 scan and
  validation behavior

Next:

- design a scan-replacement or scan-shortcut plan for the existing
  `RBMemoryReader` using TL-derived `live_pos_per_deck` chains
- keep it evidence-first and shadow/compare before changing timing authority
- preserve strict fail-closed behavior on unsupported Rekordbox versions,
  unreadable chains, stale reads, or invalid movement
- do not change `rb_memory.py` until explicitly authorized

Success would mean:

- deck1 and deck2 live position can be resolved quickly from validated
  per-version chains without waiting for broad scan windows
- unsupported/unreadable versions fall back to the current scan/MTC/TL TC path
- parity logs can compare TL-derived-chain position against current
  `PositionCache` snapshots before authority changes

No-go:

- replacing strict movement validation with blind trust in a chain
- removing current scan/MTC/TL TC fallbacks before parity evidence
- coupling scan replacement to direct master runtime authority

### 4. Play/Pause And Timing: Previously Reviewed / Parked

Status:

- previously looked at in this TL-reduction thread
- current direct authority interpretation is high-risk and not ready
- not the current next authority migration target

Next:

- do not spend the next step rediscovering play/pause or timing
- keep play/pause and timing authority on TL unless the user explicitly reopens
  that signal later

Clarification:

- TL reverse engineering showed TL itself derives play/pause from position
  movement, so this signal may benefit from the same `live_pos_per_deck`
  scan-replacement work
- that does not make play/pause authority ready; it makes position-chain parity
  the prerequisite evidence path

### 5. Track Load / Title / Startup Metadata: Later Parity Work

Status:

- not migrated
- track-load/title replacement and startup loaded-deck metadata replacement
  still need parity validation
- startup ENGINE STATE preload still does real work

Next:

- leave current startup ENGINE STATE preload in place
- evaluate track/title parity only after the current direct-master startup
  seed and/or RBMemoryReader scan-replacement design questions are resolved

### 6. Scripted Routing, ANLZ, TL TC Fallback: Stay On TL

Status:

- not ready for retirement
- no current evidence justifies migration

Next:

- keep scripted OSC/scripted ID routing on TL
- keep ANLZ correlation on TL
- keep TL TC fallback on TL

### 7. Full TL Runtime Removal: Later Outcome, Not One Step

Status:

- not a single implementation step
- depends on replacing or shadow-validating the specific TL-fed signals first
- cannot be justified by direct master evidence alone

Next:

- do not design or implement full TL removal
- continue with narrow, evidence-backed signal reductions
- the existing RB memory puller scan-replacement lane is one important runtime
  removal prerequisite

## Current Smallest Justified Next Step

Direct master evidence gathering is complete. The structural deck2 startup
visibility gap is settled. Do not run further deck2 dirty-startup evidence runs.

Active evidence tracks (Track A — no authority changes):

1. ANLZ shadow parity (A2): IMPLEMENTED — awaiting live evidence

- `_follow_pointer_string` primitive added to `RBStateReader`
  (`rb_state_reader.py`): walks chain to final address, reads u64 pointer
  there, reads NUL-terminated string at that pointer; returns None on null
  pointer, OSError, or decode failure
- `anlz_path_per_deck[d]` read in `_tick_deck` after BPM block; logs
  `[ANLZ][DIRECT] deck=N path=...` on change; enqueues `Ev.ANLZ_PATH` with
  `source='rb_state'` to shadow queue
- `self._last_anlz: dict[int, str]` tracks last seen path per RB deck index
  to suppress duplicate events
- activated by `RBSS_RB_STATE_SHADOW=1` (RBStateReader is not started in the
  normal path)

Live evidence — 2026-05-06 session:

Run conditions:
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11, deck1 active at startup
- loaded deck1 then deck2 during session; one master switch

Direct ANLZ paths observed:

- deck1 (bridge deck 1, RB deck 0): path appeared at track load boundary
  `/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/bbf/98cb0-d334-4383-a169-0b415cf727f0/ANLZ0000.DAT`
  track: We Could Be Love (Odd Mob Extended Remix) - Hayden James & ARCO.mp3
  timing: `[ANLZ][DIRECT]` appeared in same second as TL `TRACK_LOADED [src=tl_log]`
  and `FILEPATH_RESOLVED [src=anlz]`

- deck2 (bridge deck 2, RB deck 1): path appeared at track load boundary
  `/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/7a4/26710-46e3-4f54-94e1-b776ccb333ac/ANLZ0000.DAT`
  track: Odd Mob, Walker, Royce - Can't Say Nah (Original Mix).m4a
  timing: `[ANLZ][DIRECT]` appeared in same second as TL `TRACK_LOADED [src=tl_log]`
  and `FILEPATH_RESOLVED [src=anlz]`

Confirmed:

- `_follow_pointer_string` primitive works: both decks returned valid Pioneer
  USBANLZ filesystem paths (UUID-keyed subdirectories, ANLZ0000.DAT filename)
- paths appeared at the correct track load boundary, not from a stale prior load
- paths updated independently per deck (different UUIDs, different tracks)
- direct chain read deck1 path slightly ahead of TL log emission (RBStateReader
  sees memory update before TL writes the log line) — expected behavior
- pointer chain format assumption (readPointer + readString at final addr) is
  correct for the 7.2.11 offset table

Bonus parity from same session:

- `master_changed agree=2 mismatch=0` — both master switch events (ENGINE STATE
  at startup + deck1→deck2 runtime switch) agreed; runtime switch delta_ms=+0.1
- `track_loaded agree=1 title_truncated_prefix=1 mismatch=0` — deck1 title
  agreed; deck2 title showed TL 50-char truncation vs full RBStateReader buffer;
  not a semantic mismatch
- `pause: expected_tl_lag_pause_match=2` — direct pause inference fired before
  TL log confirmed; expected (position diff is faster than log write)

2026-05-07 confirmation session (second run):

Direct vs TL UUID-to-UUID path comparison — all 4 matched exactly:

  deck=1 00:02:22 `9b8/c42b4-3c43-4cac-b6ec-5e80d1abd3c3` ← TL AnlzParser exact match
  deck=1 00:02:23 `bf4/4d0fe-722d-4be6-8724-03886e27ef59` ← TL AnlzParser exact match
  deck=1 00:02:32 `8fd/2c147-b6ce-4a20-acdc-d977cb6da664` ← TL AnlzParser exact match
  deck=2 00:03:23 `1d9/2396d-e50a-4eba-be27-0cf6d9e14596` ← TL AnlzParser exact match

TL deck numbering: Deck 0 = bridge deck=1, Deck 1 = bridge deck=2. Consistent.

Startup pre-loaded paths (at attach, 00:02:17) returned immediately for both
decks with no TL AnlzParser counterpart — correct, TL had already processed
those tracks before bridge startup and will not re-emit.

deck=1 updated 3 times across 3 distinct track loads; each produced a distinct
UUID with no stale carry-forward. deck=2 updated once; distinct UUID. Path
update behavior is correct.

Session-summary from parity monitor:
  track_loaded agree=4 title_truncated_prefix=0 mismatch=0
  master_changed agree=1 mismatch=0
  bpm_update agree=1 mismatch=0

A2 verdict: CONFIRMED. `_follow_pointer_string` chain gives paths byte-for-byte
identical to TL AnlzParser for every track load on both decks. Chain format
assumption (readPointer + readString) is correct for 7.2.11 offset table.

Next step: ANLZ_PATH retirement is now a justified Track B candidate.

**B1 — AWAITING AUTHORIZATION** (2026-05-07): wire `Ev.ANLZ_PATH` from
RBStateReader to the authoritative queue, add `RBSS_ANLZ_DIRECT=1` kill-switch
env var, retire TLLogTailer ANLZ correlation path. Do not implement until
explicitly authorized.

2. live_pos_per_deck absolute value shadow (A3): IMPLEMENTED — awaiting live evidence

- `RB_SCALE` and `PositionCache` imported into `rb_state_reader.py`
- `position_cache: Optional[PositionCache] = None` kwarg added to
  `RBStateReader.__init__`; stored as `self._pos_cache`
- `self._last_livepos_log: dict[int, float] = {}` tracks last log time per deck
- `_LIVEPOS_LOG_INTERVAL_S = 5.0`, `_LIVEPOS_RESET_SAMPLES = 10_000` constants
- livepos block added in `_tick_deck` after `self._last_pos_samples[d] = pos`:
  - logs every 5s per deck, or immediately on apparent track reset
  (prev > 10000 samples → pos < 10000 samples)
  - log format: `[LIVEPOS][DIRECT] deck=N samples=X elapsed_ms=Y cache_ms=Z delta_ms=W [reset]`
  - `elapsed_ms = int(pos * RB_SCALE)` (same conversion as rb_memory.py)
  - `cache_ms` from `PositionCache.get(bridge_deck).elapsed_ms`; `none` if cache
    unavailable or deck not yet resolved
  - `delta_ms = elapsed_ms − cache_ms`; `none` if either side unavailable
- `__main__.py`: `make_rb_state_reader` call now passes `position_cache=pos_cache`
- activated by `RBSS_RB_STATE_SHADOW=1` (same as A2)

Live evidence — 2026-05-07 session:

Run conditions:
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11, deck 1 playing at bridge attach; deck 2 loaded mid-session
- Steps performed: deck1 pre-loaded → bridge start → load deck2 → switch master → pause deck1

Observation notes:
- Four log lines per 5s interval: RB deck indices 0/1/2/3 → bridge 1/2/1/2.
  Indices 2/3 (C/D decks, DDJ-800 unused) always show samples=0. Signal is
  in the first two lines per block only.

Chain accuracy — deck 1 (playing throughout):
- delta_ms across all intervals: +6, 0, +18, +6, +11, +6, +23, +11, +17, 0,
  +17, 0, 0, 0, 0, 0
- range 0–23ms; never drifts; consistently slightly ahead of PositionCache
  (expected — chain reads memory directly; cache has interpolation lag)

Deck 2 startup gap — confirmed and measured:
- 00:15:26: chain sees deck 2 at elapsed_ms=22 (samples=1014) immediately at
  track load; cache_ms=none (PositionCache scan not yet resolved)
- cache_ms=none for deck 2 from 00:15:26 through 00:15:41 (~20s gap)
- 00:15:46: cache_ms=16755 appears — PositionCache resolved ~20s after load
- chain tracked deck 2 for the full 20s while PositionCache had nothing

Deck 2 post-resolution accuracy:
- delta_ms: +17, +18, +12, +17, 0, +23, +17, +6, +18, 0
- same 0–23ms range as deck 1; consistent

Pause detection:
- 00:16:16 onwards: deck 1 samples=3156865, elapsed_ms=71584 frozen across
  five consecutive 5s intervals → chain correctly reads pause as frozen samples
- delta_ms=0 throughout pause (PositionCache also freezes)

Cross-checked against full bridge log (Terminal 1):

Deck 2 scan duration — exact measurement:
- 00:15:24: TRACK_LOADED deck=2 (track loaded)
- 00:15:44: [RBMEM][D2COMMIT] ttc_ms=38477 attempts=5
- ObjC scan took 38.5s and 5 attempts to commit deck 2
- Chain had valid position at elapsed_ms=22 by 00:15:26 (within 2s of load)
- Chain covered the full 38.5s gap with no PositionCache

Chain faster than PositionCache for deck 1 too at startup:
- 00:15:06: chain logs deck=1 elapsed_ms=6798 cache_ms=none
- RBMemoryReader had just finished vmmap; PositionCache was empty for deck 1 also
- Chain beat PositionCache at startup even for the already-playing deck

Pause events corroborated by shadow monitor:
- Deck 1 pause 00:16:12: transport-expected-TL-lag-pause-match delta_ms=-184.6
- Deck 2 pause 00:17:41: transport-expected-TL-lag-pause-match delta_ms=-394.7
- Both pauses: chain froze samples before TL logged the pause event (expected)
- Deck 2 samples=5847711 frozen from 00:17:41 to end of log, cache also frozen

Master switch corroborated:
- 00:15:53: MASTER_CHANGED deck1→deck2 reason=tl_log
- [rb_state_shadow][agree] delta_ms=-44.8 (direct 44.8ms ahead of TL log)

A3 verdict: CONFIRMED. `live_pos_per_deck` chain:
- faster than PositionCache for both decks at bridge attach (chain immediate,
  ObjC scan requires vmmap + movement validation)
- for deck 2: chain has valid position within 2s of track load; ObjC scan
  confirmed at 38.5s (ttc_ms=38477, 5 attempts) — chain covers the full gap
- tracks position within 0–23ms of PositionCache once both are available
- correctly freezes on pause for both decks
- directly removes the deck 2 30s scan dependency and eliminates startup
  position gap for both decks on supported RB versions

Next step: A3 evidence justifies a scan-replacement or scan-shortcut design
for `RBMemoryReader` using `live_pos_per_deck` chains. This is Track B2.
Authorize separately — do not implement until explicitly authorized.

Startup-seed design (candidate C1):

- not yet authorized to implement
- design boundaries are settled (see Direct Master roadmap section above)
- implement only when explicitly authorized after A2 and A3 evidence is clean

3. play/pause shadow parity (A4): CONFIRMED with implementation note

Run conditions — 2026-05-07:
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11
- Scenario 1: 5 play/pause cycles on deck 1 (master), deck 2 stopped
- Scenario 2: deck 2 loaded, crossfade deck1→deck2→deck1, hot-cue jump on deck 2
- Scenario 3: rapid cue/play on deck 2 (sub-second play-pause sequences)

Scenario 1 — simple play/pause, deck 1:
- 10 events, 10 matched (strong-match or expected-TL-lag)
- 0 misses, 0 false positives
- Pause delta range: -100 to -177ms (direct ahead of TL — position freeze detected
  before TL writes log line; correct ordering)
- Play delta range: -37 to +37ms
- Clean across all pause/play cycles at human speed

Scenario 2 — crossfade:
- Both master switches agree: delta_ms=+7.7 and -23.1
- All play/pause during crossfade matched cleanly on both decks simultaneously
- No bleed between decks during concurrent playback
- Hot-cue jump on deck 2 (position jumped to samples=970): chain caught immediately,
  PositionCache drift detector fired, both converged within 1 poll

Scenario 3 — rapid cue:
- All human-speed events matched
- TL lag on rapid cues: delta_ms=-431ms and -1133ms (TL log write backs up during
  rapid input; direct more responsive, not less accurate; resolved via
  expected-TL-lag classifier)
- 2 pairs of "missing TL pair" events (the only notable finding):
  - pair 1: play+pause at mono=24674.610/24674.775, gap=165ms
  - pair 2: play+pause at mono=24693.081/24693.211, gap=165ms
  - both pairs on deck 2 (non-master at time of occurrence)
  - rb_state caught 165ms position blips TL did not log; TL has longer implicit
    debounce; `_PLAY_EVIDENCE_POLLS=2` at 30Hz (~66ms) is too sensitive for
    sub-200ms bounces from extreme rapid cue

A4 verdict: CONFIRMED. Play/pause chain signal is accurate and complete for all
normal and crossfade scenarios. One implementation note for B3:

**B3 — AWAITING AUTHORIZATION** (2026-05-07): wire `Ev.PLAY`/`Ev.PAUSE` from
RBStateReader to the authoritative queue, add `RBSS_PLAY_DIRECT=1` kill-switch.
`_PLAY_EVIDENCE_POLLS` stays at 2 — the missing-TL-pair blips only occur on the
non-master deck during extreme rapid cue; master-only lighting authority means
they are irrelevant to the authoritative path. Prerequisites: B1, B2 must land
first.

---

4. track load/title shadow parity (A5): CONFIRMED

Implementation — 2026-05-07:
- One-line addition to `rb_state_reader._tick_deck` at the title-change branch:
  `log.info("[TITLE][DIRECT] deck=%d title=%r", bridge, title)`
- No new state or kwargs needed — title-change detection already existed.
- Activated by same `RBSS_RB_STATE_SHADOW=1` env var as A2/A3/A4.

Run conditions — 2026-05-07:
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11
- Rapid-fire load sequence: ~12 distinct track loads across both decks,
  including hot-swaps (load while other deck playing), and startup title seeding

Deck 1 load events (delta = rb_mono − tl_mono, negative = direct ahead of TL):
| Track                                | delta_ms | verdict               |
|--------------------------------------|----------|-----------------------|
| Age Of Love (Dave Summer Edit)       |    −42.0 | agree                 |
| Vertigo feat. Ed Graves              |     −0.6 | agree (hot-swap)      |
| Lowkey (Original Mix)                |   +182.1 | agree (reversed)      |
| Die Young (Sidepiece)                |     −8.0 | agree                 |
| Tchami - Adieu (Westend Edit) 1644   |     +8.1 | agree                 |
| Sexy Bitch X Odd Mob NoFun edit      |     +8.2 | agree                 |

Deck 2 load events:
| Track                                | delta_ms | verdict               |
|--------------------------------------|----------|-----------------------|
| At The Disco (Extended Mix)          |    −48.2 | agree                 |
| Won't Be Possible (Extended Mix)     |     −3.1 | agree (hot-swap)      |
| Rock Your Body (Twin Diplomacy V5.1) |   +763.7 | title_truncated_prefix|
| Lowkey (Original Mix)                |    −38.5 | agree                 |
| Felix Jaehn (long title)             | TL first | title_truncated (rb_state full title confirmed fired, no mono delta available) |

Startup seeding: both deck 1 and deck 2 titles detected at RBStateReader attach
(00:44:21, within 1s of bridge start), before any TL events processed.

Notable findings:

1. Direct fires before TL in 7/10 matched events. Delta range: −48ms to −0.6ms
   (direct ahead). Two near-simultaneous (~±8ms). One reversal (+182ms) during
   extreme rapid-fire sequence — RB memory update lag under high load.

2. Title truncation advantage: TL log truncates long titles at ~50 chars.
   rb_state reads the full string from memory. "Rock Your Body (Twin Diplomacy
   Extended Remix) V5." (TL) vs "V5.1 2" (rb_state full) — direct is
   strictly more accurate. Same for "Felix Jaehn, Sophie Ellis-Bextor..." and
   "Twin Diplomacy, Jack August - Better Place...". This matters for B4:
   FilepathResolver gets better input from rb_state than from TL.

3. Hot-swap confirmed: Vertigo (delta=−0.6ms) and Won't Be Possible (delta=−3.1ms)
   were loaded while the other deck was playing. Both fired near-simultaneously
   with TL.

4. Startup title seeding confirmed: direct detected both loaded deck titles at
   attach with no warm-up window needed.

A5 verdict: CONFIRMED. Direct track-load title detection is at least as timely as
TL (usually 0–48ms ahead), produces fuller/more accurate titles (TL truncates
long names), handles hot-swap and startup correctly. B4 (track load/title
retirement) is supported.

**B4 — AWAITING AUTHORIZATION** (2026-05-07): wire `Ev.TRACK_LOADED` from
RBStateReader to the authoritative queue, add `RBSS_TRACK_LOAD_DIRECT=1`
kill-switch. FilepathResolver will receive full (non-truncated) titles from
rb_state vs the 50-char TL truncation. Prerequisites: B1, B2, B3 must land
first.

---

5. scripted routing shadow validation (A6): CONFIRMED

Implementation — 2026-05-07:
- `state_manager.py` `_on_filepath_resolved`: added `[SCRIPTED][DIRECT]` log
  under `RBSS_RB_STATE_SHADOW=1` guard — ssid reverse-lookup against
  SCRIPTED_TRACKS, logs scripted_id or scripted=no.
- `__main__.py` `_track_loaded` OSC handler: added `[SCRIPTED][TL-OSC]` log
  just before SCRIPTED_ARM enqueue.

Run conditions — 2026-05-07:
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11
- Loaded 4 scripted tracks across deck 1 and deck 2, including non-master loads,
  crossfade, and hot-swap. 3 unscripted tracks also loaded.

SCRIPTED events observed:

Scripted track detections:
| Track              | id | Direct deck | Direct latency | TL-OSC deck | TL-OSC timing         |
|--------------------|----|-------------|----------------|-------------|-----------------------|
| Kesha - Blow       | 15 | 1 ✓         | 443ms          | 1 ✓         | ~0ms (pre-armed)      |
| Opalite (CL Remix) | 14 | 2 ✓         | 470ms          | 1 ✗ wrong   | 46s late, wrong deck  |
| John Summit WYARE  |  6 | 1 ✓         | 524ms          | 2 ✗ wrong   | race: OSC before TL   |
| New Sky (Odd Mob)  |  4 | 1 ✓         | 1176ms         | 1 ✓         | ~same (pre-armed)     |

Unscripted track detections:
| Track              | Direct result      | TL-OSC |
|--------------------|--------------------|--------|
| Felix Jaehn        | scripted=no ✓      | none   |
| Rude Boy (Cazes)   | scripted=no ✓      | none   |
| PUSHINN            | scripted=no ✓      | none   |

Notable findings:

1. Direct deck routing always correct (4/4). TL OSC deck routing has two bugs
   in one session:
   - Opalite: TL OSC fired 46s after load and routed to deck=1 (wrong). At OSC
     time, `get_last_loaded_deck()` returned deck=1 (New Sky had been loaded
     there since). TL OSC carries no deck identity.
   - John Summit: TL OSC arrived before `TRACK_LOADED` was processed by
     StateManager, so `get_last_loaded_deck()` returned stale deck=2 (Opalite).
     Track was on deck=1. Race condition inherent to the OSC→TL log ordering.

2. Direct FILEPATH_RESOLVED latency: 344–1384ms. Higher end under heavy rapid-
   load sequence. Normal single-load range: 340–530ms. In real gig conditions
   (DJ takes time between loading and pressing play), this window is irrelevant —
   scripted arm fires hundreds of ms before first beat.

3. Pre-armed tracks (DJ arms in TL before loading): TL OSC fires at ~TRACK_LOAD
   +0ms; direct fires at +443–1176ms. TL wins on timing only in this case.
   However, these cases had correct deck routing in TL. The routing bugs only
   appeared under non-master deck loads and race conditions.

4. No false positives: all 3 unscripted tracks correctly returned `scripted=no`.

5. B5 design note: direct path should gate scripted arm on
   `deck == master OR deck just became master`, not on TL OSC timing. The direct
   path must replace the OSC handler entirely (not augment) to fix the routing
   bugs. The 344–1384ms FILEPATH_RESOLVED window is acceptable since it precedes
   play in all real gig scenarios.

A6 verdict: CONFIRMED. Direct path correctly identifies all scripted and
unscripted tracks, always routes to the correct deck (4/4), fires within
344–1384ms of TRACK_LOADED. TL OSC demonstrated two confirmed deck-routing bugs
in this single session. B5 (scripted routing retirement) is supported, and the
direct path is more reliable than TL OSC for deck routing.

**B5 — AWAITING AUTHORIZATION** (2026-05-07): retire TL OSC `/bridge/track_loaded`
scripted arm. Replace with FILEPATH_RESOLVED → ssid lookup → SCRIPTED_TRACKS →
SCRIPTED_ARM. Gate arm on `deck == master OR deck just became master`. Add
`RBSS_SCRIPTED_DIRECT=1` kill-switch. Prerequisites: B1, B2, B3, B4 must land
first. Highest-risk retirement item — last in sequence.

---

## B1/B2/C1 Implementation And First Live Validation

Implementation date: 2026-05-07.

Runtime guards:

- `RBSS_ANLZ_DIRECT=1` enables direct ANLZ authority from `RBStateReader`.
- `RBSS_POS_CHAIN_DIRECT=1` enables `RBMemoryReader` position-chain snapshots.
- `RBSS_MASTER_SEED_DIRECT=1` enables startup-only direct master seed.

Implemented behavior:

- B1: `RBStateReader` can route only explicitly enabled event kinds to the main
  authoritative queue. For this step, only `Ev.ANLZ_PATH` is promoted. Other
  direct events stay shadow-only or are dropped when shadow mode is off.
- B1: `TLLogTailer` still parses ANLZ correlation state, but does not enqueue
  TL `Ev.ANLZ_PATH` while `RBSS_ANLZ_DIRECT=1`.
- B2: `RBMemoryReader` follows the versioned `live_pos_per_deck` chain on each
  poll when `RBSS_POS_CHAIN_DIRECT=1`, validates raw values, and updates
  `PositionCache` with chain snapshots. Existing ObjC Deck-2 resolution still
  runs in the background as fallback/validation.
- C1: startup master seed does two direct reads about 500ms apart and uses the
  direct deck only when both reads are readable, supported, valid, and stable.
  Runtime master authority remains TL/ENGINE.

Live validation run 1 — fail-closed startup, direct ANLZ, and B2 chain:

Run conditions:

- `RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1`
- `RBSS_RB_STATE_SHADOW=1 RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11
- bridge started with no loaded deck; then deck 2 track loaded/played

Observed:

- C1 fail-closed:
  `[MASTER-SEED] direct=none tl=deck1 using=tl reason=no_master`
- B1 direct ANLZ:
  `[ANLZ][DIRECT] deck=2 path=.../ANLZ0000.DAT`
- B1 resolver path:
  `FILEPATH_RESOLVED ... [deck=2 src=anlz ...]`
- B2 chain enabled:
  `[RBMEM][CHAIN] enabled via RBSS_POS_CHAIN_DIRECT=1 version=7.2.11`
- B2 deck-2 chain filled position before ObjC commit:
  `[LIVEPOS][DIRECT] deck=2 samples=3131 elapsed_ms=70 cache_ms=70 delta_ms=+0`
- ObjC scan still ran and committed later:
  `[RBMEM][D2COMMIT] inner=... ttc_ms=10370 attempts=2`
- Runtime direct-master observer stayed observational and reproduced the known
  TL startup gap:
  `first_valid_master=deck2 final_direct_master=deck2 final_tl_master=deck2
  tl_master_at_first_valid=deck1 outcome=became_valid_but_mismatched_tl`

Judgment:

- B1 live behavior is encouraging: direct ANLZ reached the authoritative
  resolver path and matched the expected ANLZ load flow.
- B2 live behavior is encouraging: chain position covered Deck 2 before ObjC
  commit, while ObjC validation still ran in the background.
- C1 fail-closed behavior is confirmed for `direct_master=none`.

Live validation run 2 — C1 deck 1 success:

Run conditions:

- same env vars as above
- deck 1 loaded/master before bridge start

Observed:

- `[MASTER-SEED] direct=deck1 tl=deck1 using=direct`
- `StateManager: initial active_deck=1 (from direct master seed)`
- direct master corroboration:
  `initial_direct_master=deck1 direct_master=deck1 tl_startup_master=deck1
  corroboration=agree outcome=settled`

Judgment:

- C1 direct startup seed success path is confirmed for deck 1.

Live validation run 3 — C1 deck 2 success:

Run conditions:

- same env vars as above
- deck 2 loaded/master before bridge start

Observed:

- TL startup value was stale deck 1:
  `read_initial_state: active_deck=1 (master_layer=0 from config.yaml)`
- two direct reads agreed on deck 2:
  `[RBMASTER][DIRECT] ... raw=1 direct_master=deck2 reason=ok`
  repeated twice
- C1 used direct seed:
  `[MASTER-SEED] direct=deck2 tl=deck1 using=direct`
- StateManager accepted the direct seed:
  `StateManager: initial active_deck=2 (from direct master seed)`
- direct master startup observation settled and documented TL disagreement:
  `initial_direct_master=deck2 direct_master=deck2 tl_startup_master=deck1
  corroboration=disagree outcome=settled`
- B1/B2 were also active:
  `[RBMEM][CHAIN] enabled via RBSS_POS_CHAIN_DIRECT=1 version=7.2.11`
  `[ANLZ][DIRECT] deck=2 path=.../ANLZ0000.DAT`
  `[LIVEPOS][DIRECT] deck=2 samples=4145 elapsed_ms=93 ...`

Judgment:

- C1 deck-2 success path is confirmed. This is the exact structural startup
  stale-TL case C1 was designed for: TL config reported deck 1, direct memory
  reported stable deck 2, and `StateManager` started on deck 2.
- This still does not promote runtime direct master authority. Runtime observer
  remains comparison-only.

Untested / intentionally skipped for now:

- explicit B1 kill-switch run without `RBSS_ANLZ_DIRECT=1`
- explicit B2 kill-switch run without `RBSS_POS_CHAIN_DIRECT=1`
- RB restart while bridge is running with `RBSS_POS_CHAIN_DIRECT=1`

User decision on 2026-05-07: flag these as untested and skip them for now.

Do not:

- promote RBStateReader events to the authoritative queue (not justified yet)
- remove TLLogTailer or MTCReader (prerequisites not met)
- add broad source arbitration to StateManager (not a current design target)

## Update Rule For Future Agents

After each new live run, decision, or user correction, append or revise this
file with:

- exact observed summary fields
- scenario conditions
- judgment: encouraging, inconclusive, or concerning
- what the evidence proves
- what remains open
- smallest justified next step
