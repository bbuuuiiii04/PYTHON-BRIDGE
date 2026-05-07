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
- Guarded direct authority has been promoted for B1 ANLZ, B2 position chain,
  B3 play/pause, B4 track-load, and B5 scripted arm/clear. Runtime master and
  TL TC fallback remain TL-authoritative.

## Current Repo State

- `TLLogTailer` remains authoritative for TL log and ENGINE STATE events except
  for the narrow guarded B1/B3/B4 bypasses described below.
- `LiveBPMService` is the strongest direct-first subsystem and already uses
  offset-table BPM when valid.
- Direct master support exists as:
  - one-shot startup probe
  - startup settle/retry observation
  - bounded runtime observer
  - TL-only `TLMasterSnapshot` comparison source
- Direct master logs remain observational and use `authority=tl_log`.
- Direct master runtime comparison uses `comparison_source=tl_master_snapshot`.
- `RBMemoryReader` can use the guarded B2 direct position chain; ObjC discovery
  remains fallback/validation.
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

**B3 — IMPLEMENTED / AWAITING LIVE VALIDATION** (2026-05-07): added
`RBSS_PLAY_DIRECT=1`. When enabled, `RBStateReader` routes only `Ev.PLAY` and
`Ev.PAUSE` to the authoritative queue; unrelated direct events still remain
shadow-only or dropped unless their own kill switch is enabled. `TLLogTailer`
still runs and parses the log, but TL log `PLAY`/`PAUSE` output is bypassed only
after `RBStateReader` has attached and warmed up a direct transport baseline for
that bridge deck. If the direct path is unavailable or loses readability, TL
play/pause remains the fail-closed fallback. Startup ENGINE preload remains
unchanged so an already-playing deck can still seed state before direct polling
warms up. Focused unit tests cover direct transport routing, TL play/pause
bypass, and fallback before direct readiness.

**B3 — LIVE VALIDATION CONFIRMED** (2026-05-07):

Run conditions:
- `RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1 RBSS_PLAY_DIRECT=1`
- `RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11; deck 1 playing at start; deck 2 loaded mid-session
- Startup message confirmed: `RBStateReader PLAY/PAUSE direct enabled via RBSS_PLAY_DIRECT=1`

Scenarios covered and results:

- Deck 1 simple play/pause (master), ~12 cycles: all `src=rb_state` ✓
- Deck 2 play/pause (non-master), ~10 cycles: all `src=rb_state` ✓
- Rapid cue on deck 2 (bursts at 02:29:41–44): all `src=rb_state` ✓
- Rapid cue on deck 1 (non-master after switch, 02:30:05–09): all `src=rb_state` ✓
- Master switch deck1→deck2: `MASTER_CHANGED reason=tl_log` — correct, master authority unchanged ✓
- Master switch deck2→deck1: `MASTER_CHANGED reason=tl_log` — correct ✓
- Non-master deck pause: `src=rb_state` ✓
- Pause auto-switch: D1 paused (rb_state) → `[D1→D2] auto-switch (D1 stopped)` fired correctly ✓

Zero TL play/pause events leaked through on either deck across all scenarios.
Auto-switch (which depends on correct PAUSE detection from rb_state) fired correctly.

Conclusion: B3 is confirmed working. Direct play/pause is the authoritative source
for both decks. TL bypass is complete and fail-closed (TL still runs as fallback
if RBStateReader loses readability). B4 authorization is the next step.

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

**B4 — IMPLEMENTED / AWAITING LIVE VALIDATION** (2026-05-07): wired
`Ev.TRACK_LOADED` from `RBStateReader` to the authoritative queue behind
`RBSS_TRACK_LOAD_DIRECT=1`.

Implemented behavior:

- `tl_tailer.py`: added `TRACK_LOAD_DIRECT_ENV` and a
  `track_load_direct_ready(deck)` readiness gate. TL `TRACK_LOADED` is bypassed
  only when `RBSS_TRACK_LOAD_DIRECT=1`, `RBSS_ANLZ_DIRECT=1`, and direct title
  memory is ready for that bridge deck. Without B1 ANLZ direct, B4 fails closed
  and TL load events remain authoritative.
- `rb_state_reader.py`: added track-load availability tracking and direct
  `TRACK_LOADED` routing through `authoritative_kinds`. Direct title readiness
  requires a non-empty readable title buffer.
- `rb_state_reader.py`: reordered `_tick_deck()` so direct ANLZ reads/enqueues
  before direct track-info / `TRACK_LOADED` reads in the same tick. This is a
  critical ordering invariant because `StateManager._on_track_loaded()` pops
  `_pending_anlz_path[deck]` when the load event arrives.
- `__main__.py`: added `RBSS_TRACK_LOAD_DIRECT` startup flag, ready-state
  callback pair, `Ev.TRACK_LOADED` promotion, and startup log. The flag is
  ignored with a warning unless `RBSS_ANLZ_DIRECT=1` is also set.
- `scripts/ss_bridge_watcher.sh` and the live `/Users/bbui/ss_bridge_watcher.sh`
  now launch with `RBSS_TRACK_LOAD_DIRECT=1` alongside the existing B1/B2/C1/B3
  env vars.

Review follow-up from Claude Code:

- Fixed the deployed-watcher gap: the live `/Users/bbui/ss_bridge_watcher.sh`
  was updated, not just the repo copy.
- Converted the B4-without-B1 risk from silent filepath-resolution degradation
  into fail-closed TL fallback.
- Tightened `_title_readable_this_tick` so empty title buffers do not mark a
  deck ready.

Unit validation:

- `python3 -m unittest tests.test_tl_tailer tests.test_rb_state_reader`
  → 63 tests passed.
- `python3 -m unittest discover -s tests`
  → 197 tests passed.

**B4 — LIVE VALIDATION CONFIRMED** (2026-05-07):

Run conditions:
- `RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1 RBSS_PLAY_DIRECT=1 RBSS_TRACK_LOAD_DIRECT=1`
- `RBSS_LIVE_BPM_FOLLOW=1`
- RB version 7.2.11; no deck loaded at bridge start; rapid-fire load sequence
  across both decks immediately after startup

Scenarios covered and results:

- 10 total TRACK_LOADED events (5 per deck, load_gen 1–5): all `src=rb_state` ✓
- Zero `src=tl_log` TRACK_LOADED events on either deck ✓
- ANLZ ordering invariant held on all 10 loads: every load in the log shows
  `[ANLZ][DIRECT]` → `[TITLE][DIRECT]` → `TRACK_LOADED` in strict order ✓
- Full non-truncated titles confirmed (e.g. "How Deep Is Your Love Vs. Glue
  (G-Fire Mashup) (Clean) 9A 130", "Charli xcx - 365 (Whethan Turn)") ✓
- `FILEPATH_RESOLVED [src=anlz]` followed every load on both decks;
  trace IDs matched TRACK_LOADED → FILEPATH_RESOLVED on all 10 loads ✓
- FILEPATH_RESOLVED latencies: 304–416ms ✓
- Auto-switch (D1→D2, D2→D1) and master changes unaffected ✓
- C1 fail-closed confirmed: `direct=none tl=deck1 using=tl reason=no_master`
  (no deck loaded at startup) ✓

Conclusion: B4 is confirmed working. Direct TRACK_LOADED is the authoritative
source for both decks. TL bypass is complete and fail-closed. B5 authorization
is the next step.

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

**B5 — IMPLEMENTED / AWAITING LIVE VALIDATION** (2026-05-07): retired TL OSC
`/bridge/track_loaded` scripted arm behind `RBSS_SCRIPTED_DIRECT=1`.

Implemented behavior:

- `__main__.py`: added `SCRIPTED_DIRECT_ENV = "RBSS_SCRIPTED_DIRECT"`.
- `__main__.py`: `_track_loaded()` now returns after parsing the track id when
  `RBSS_SCRIPTED_DIRECT=1`, so TL OSC no longer enqueues `SCRIPTED_ARM` /
  `SCRIPTED_CLEAR`. `_active_deck()` is untouched, so TL OSC master routing
  remains active.
- `__main__.py`: startup log confirms direct mode:
  `scripted arm direct enabled via RBSS_SCRIPTED_DIRECT=1 - _track_loaded bypassed`.
- `state_manager.py`: `_on_filepath_resolved()` now performs the A6-proven
  `soundswitch_id` → `SCRIPTED_TRACKS` lookup when `RBSS_SCRIPTED_DIRECT=1`.
  If ssid is empty or unmatched, it falls back to a unique filepath match in
  `SCRIPTED_TRACKS`; this preserves scripted tracks whose SoundSwitch id tag is
  absent and lets SoundSwitch match the show by filepath. It then enqueues
  `Ev.SCRIPTED_ARM` or `Ev.SCRIPTED_CLEAR` with `source="filepath_resolved"`
  onto the same event queue. The event is drained on the next iteration of the
  same `_drain_events()` cycle.
- `state_manager.py`: the legacy OSC/switch-race scripted-id transfer in
  `_on_master_changed()` is disabled while `RBSS_SCRIPTED_DIRECT=1`, because
  direct FILEPATH_RESOLVED deck identity is already correct and copying from
  the old deck can arm a stale show on an unscripted incoming deck.
- `scripts/ss_bridge_watcher.sh` and live `/Users/bbui/ss_bridge_watcher.sh`
  now launch with `RBSS_SCRIPTED_DIRECT=1` alongside B1-B4 direct flags.

Unit validation:

- `python3 -m unittest tests.test_tl_tailer tests.test_live_bpm_service`
  → 86 tests passed.
- Claude review follow-up added filepath-fallback coverage for empty ssid,
  unmatched ssid, and ambiguous filepath matches.
- Log-level policy: ssid-present misses and ambiguous filepath matches stay at
  INFO. The only non-queue WARNING in the direct lookup path is a successful
  unique filepath fallback when ssid is empty.

Live validation — 2026-05-07:

Run conditions:

- `RBSS_SCRIPTED_DIRECT=1 RBSS_TRACK_LOAD_DIRECT=1 RBSS_ANLZ_DIRECT=1`
  (plus `RBSS_LIVE_BPM_FOLLOW=1 RBSS_POS_CHAIN_DIRECT=1 RBSS_MASTER_SEED_DIRECT=1
  RBSS_PLAY_DIRECT=1`)
- RB version 7.2.11, bridge started via manual session terminal

Observed:

- Startup bypass confirmed:
  `04:19:50 scripted arm direct enabled via RBSS_SCRIPTED_DIRECT=1 - _track_loaded bypassed`

- Scripted track load, deck=1 (Kesha - Blow, id=15):
  `TRACK_LOADED title=Kesha - Blow ... [deck=1 src=rb_state tr:a4f9a7]`
  `FILEPATH_RESOLVED path=Kesha - Blow ....wav bpm=130.0 ssid=yes [deck=1 src=anlz tr:a4f9a7]`
  `[SCRIPTED][DIRECT] deck=1 scripted_id=15 ssid={F1E0AB4 latency_ms=431.8 [deck=1 src=anlz tr:a4f9a7]`
  `SCRIPTED_ARM id=15 path=Kesha - Blow ....wav elapsed=48ms bpm=130.0`
  Source is `rb_state`, not `tl_log`. Arm fires 48ms after FILEPATH_RESOLVED.
  No `_track_loaded` OSC arm path in the log.

- Scripted track load, deck=2 (Opalite, id=14):
  `[SCRIPTED][DIRECT] deck=2 scripted_id=14 ssid={74044FA latency_ms=466.7 [deck=2 src=anlz tr:156d8f]`
  `MASTER_CHANGED deck1 -> deck2 reason=tl_log`
  `SCRIPTED_ARM id=14 path=Taylor Swift - Opalite ....mp3 elapsed=14823ms bpm=130.0`
  Arm deferred correctly until deck became master. `/bridge/active_deck` path functional.

- Second scripted load, deck=1 (Lowkey, id=5):
  `[SCRIPTED][DIRECT] deck=1 scripted_id=5 ssid={E36664D latency_ms=786.4 [deck=1 src=anlz tr:78f143]`
  `MASTER_CHANGED deck2 -> deck1 reason=tl_log`
  `SCRIPTED_ARM id=5 path=Scilo - Lowkey (Original Mix).wav elapsed=3662ms bpm=130.0`
  Correct deck, correct id.

- Auto-switch master recovery:
  `MASTER_CHANGED deck2 -> deck1 reason=pause auto-switch`
  `SCRIPTED_ARM id=5 path=Scilo - Lowkey (Original Mix).wav elapsed=48825ms bpm=130.0`
  Re-arms scripted deck on auto-switch ✓. Old `_on_master_changed` scripted-id
  transfer from the outgoing deck did not fire — direct deck identity used throughout.

- Unscripted track, deck=2 (OMG.wav):
  `FILEPATH_RESOLVED path=OMG.wav bpm=127.0 ssid=no [deck=2 src=anlz tr:5d40c9]`
  `[SCRIPTED][DIRECT] deck=2 scripted=no ssid=none latency_ms=659.0 [deck=2 src=anlz tr:5d40c9]`
  `[D2] scripted cleared [deck=2 src=filepath_resolved tr:5d40c9]`
  `MASTER_CHANGED deck1 -> deck2 reason=tl_log`
  `[SS]  → autoloop  deck=2  elapsed=4656ms`
  SCRIPTED_CLEAR fires at FILEPATH_RESOLVED. Master change goes to autoloop,
  not scripted arm. No spurious SCRIPTED_ARM.

- Filepath fallback edge case: not exercised this session. No WARNING-level
  filepath fallback events fired. All scripted matches resolved via ssid.

Known anomaly (non-blocking):

  The `[SCRIPTED][DIRECT]` log line shows truncated ssid values: `ssid={F1E0AB4`
  with no closing `}`. Appears to be a format string issue — the `}` is consumed
  as a format placeholder. Arming behavior is correct in all cases; this is a
  cosmetic log defect only.

Judgment: CONFIRMED. B5 is live-safe.

- Deck correctness: all arms matched the loaded track's deck ✓
- Direct source correctness: all TRACK_LOADED from `rb_state`, FILEPATH_RESOLVED
  from `anlz` ✓
- Scripted behavior: `SCRIPTED_ARM` on ssid=yes, correct id and deck ✓
- Unscripted behavior: `SCRIPTED_CLEAR` on ssid=no, no spurious arm ✓
- `/bridge/active_deck` functional: `MASTER_CHANGED` via tl_log path active ✓
- No filepath fallback or WARNING path fired ✓

Open items:

- Restart with `RBSS_SCRIPTED_DIRECT` unset to confirm legacy TL OSC scripted
  routing still works (skipped; low priority since legacy path is unchanged).
- Fix the `ssid={...` truncation in the `[SCRIPTED][DIRECT]` log format string.

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
  TL `Ev.ANLZ_PATH` while `RBSS_ANLZ_DIRECT=1` only after direct ANLZ is
  currently readable for that bridge deck. Before direct readiness, TL ANLZ
  remains the fail-closed fallback.
- B2: `RBMemoryReader` follows the versioned `live_pos_per_deck` chain on each
  poll when `RBSS_POS_CHAIN_DIRECT=1`, validates raw values, and updates
  `PositionCache` with chain snapshots. Existing ObjC Deck-2 resolution still
  runs in the background as fallback/validation. Rejected out-of-range chain
  values do not update the previous-raw validation anchor, so one bad read
  cannot poison later valid reads.
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

- remove TLLogTailer or MTCReader (prerequisites not met)
- add broad source arbitration to StateManager (not a current design target)
- retire scripted routing until B5 is explicitly authorized

**B6 — IMPLEMENTED / AWAITING LIVE VALIDATION** (2026-05-07): retired TL OSC
`/bridge/active_deck` as the runtime master-change relay behind
`RBSS_MASTER_DIRECT=1`.

Implemented behavior:

- `__main__.py`: added `MASTER_DIRECT_ENV = "RBSS_MASTER_DIRECT"`.
- When `RBSS_MASTER_DIRECT=1`, the main `RBStateReader` starts if needed and
  routes `Ev.MASTER_CHANGED` with `source='rb_state'` to the authoritative
  queue.
- `RBStateReader` now exposes a single direct-master readiness callback.
  Readiness is true only when the most recent tick read the master byte and the
  raw value is a valid Rekordbox deck index for the current offset table.
- `0xFF` sentinel remains a no-event direct-master baseline update, and now
  marks direct master not ready so OSC can fall back.
- OSC `/bridge/active_deck` returns without enqueueing only while
  `RBSS_MASTER_DIRECT=1` and direct master is currently ready. If the direct
  chain is unreadable, missing, sentinel, or not yet warmed up, OSC remains the
  fail-closed fallback.
- TL log `MASTER_CHANGED` from ordinary TL log lines and ENGINE STATE master
  blocks is bypassed only while `RBSS_MASTER_DIRECT=1` and direct master is
  currently ready. If direct master is not ready, TL master remains the
  fail-closed fallback. ENGINE STATE BPM and TC fallback events still flow.
- `DirectMasterRuntimeObserver` remains shadow-only and uses its independent
  ephemeral reader for comparison against `TLMasterSnapshot`.

Live validation — 2026-05-07:

Run conditions:

- Full B1–B6 flag set:
  `RBSS_LIVE_BPM_FOLLOW=1 RBSS_ANLZ_DIRECT=1 RBSS_POS_CHAIN_DIRECT=1
  RBSS_MASTER_SEED_DIRECT=1 RBSS_MASTER_DIRECT=1 RBSS_PLAY_DIRECT=1
  RBSS_TRACK_LOAD_DIRECT=1 RBSS_SCRIPTED_DIRECT=1`
- RB version 7.2.11, manual terminal session

Observed:

- Startup confirmation:
  `04:51:38 RBStateReader MASTER direct enabled via RBSS_MASTER_DIRECT=1`
  All B1–B6 direct flags confirmed active in a single session.

- 0xFF readiness gate (no deck loaded):
  `[RBMASTER][DIRECT] raw=255 direct_master=none reason=no_master authority=tl_log`
  `[MASTER-SEED] direct=none tl=deck2 using=tl reason=no_master`
  `StateManager: initial active_deck=2 (from TL ENGINE STATE)`
  Runtime summary: `outcome=never_became_valid final_raw=255 transition_count=0 mismatches=0`
  Sentinel correctly suppressed event and fail-closed to TL seed ✓

- First transition before ready (fail-closed):
  `MASTER_CHANGED deck2 -> deck1 reason=auto-detect [deck=1 src=auto-detect tr:c45c80]`
  Direct reader not yet ready (raw still 0xFF); auto-detect fallback fired as expected ✓

- Direct master takes over — 5 consecutive transitions:
  `04:52:20 MASTER_CHANGED deck1 -> deck2 reason=rb_state [deck=2 src=rb_state tr:5b9ed0]`
  `04:52:24 MASTER_CHANGED deck2 -> deck1 reason=rb_state [deck=1 src=rb_state tr:1a151d]`
  `04:52:28 MASTER_CHANGED deck1 -> deck2 reason=rb_state [deck=2 src=rb_state tr:d42fa0]`
  `04:52:30 MASTER_CHANGED deck2 -> deck1 reason=rb_state [deck=1 src=rb_state tr:d501c0]`
  `04:52:34 MASTER_CHANGED deck1 -> deck2 reason=rb_state [deck=2 src=rb_state tr:bf95c4]`
  All 5/5 transitions: correct deck, correct source ✓

- TL log suppression:
  Zero `reason=tl_log` MASTER_CHANGED events after readiness established.
  No duplicate events per transition. `_master_direct_bypass_enabled()` working ✓

- SoundSwitch propagation:
  All 5 autoloop arms confirm `master_source=rb_state` ✓

- B5 interop: all unscripted loads correctly ran `[SCRIPTED][DIRECT] scripted=no`
  and `scripted cleared` with no interference from B6 ✓

- Restart without RBSS_MASTER_DIRECT: not exercised in this session (low priority;
  OSC path is unchanged).

Judgment: CONFIRMED. B6 is live-safe.

- Deck correctness: 5/5 ✓
- Direct source correctness: `rb_state` after readiness, `auto-detect` before ✓
- 0xFF suppression: no spurious event, fail-closed to TL ✓
- TL log suppression: no duplicates ✓
- SoundSwitch master_source correct ✓
- B5 interop: unaffected ✓

## Update Rule For Future Agents

After each new live run, decision, or user correction, append or revise this
file with:

- exact observed summary fields
- scenario conditions
- judgment: encouraging, inconclusive, or concerning
- what the evidence proves
- what remains open
- smallest justified next step
