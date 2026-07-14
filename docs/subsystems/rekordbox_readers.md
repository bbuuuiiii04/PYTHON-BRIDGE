---
doc_status: current
truth_level: code-verified
last_verified_commit: 81f1b15
last_verified_date: 2026-07-13
validation_scope: software-only plus Rekordbox 7.2.11 passive mixer RE evidence routing; Rekordbox 7.2.16 direct-reader offset row software-tested (four roots STATIC-CONFIRMED; interior hops CANDIDATE from 7.2.14 deck + 7.2.11 mixer/CFX layout; live-unvalidated); AWR-157 deck-2 chain freshness gating software-tested; AWR-160 phantom track-load stability gate software-tested; AWR-207/AWR-209/AWR-211 USB local-twin, foreign-import, portable-sidecar refresh, phrase-worker handoff, and Rekordbox-7 split-local-UUID classification software-tested; USB ANLZ PPTH leading-slash stick-root-relative paths accepted by `_device_audio_filepath` (software-tested); AWR-222 dormant AX measurement probe implemented/software-tested/not executed (not a reader); hardware-output unvalidated
---

# Rekordbox Readers

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: current local Rekordbox/macOS setup only

Purpose:
- Read Rekordbox runtime state, position, track/load data, ANLZ paths, and displayed BPM through guarded local readers.
- Read named Deck 1/2 mixer upfader and LOW/BASS chains for software-tested
  active-deck authority when the selected Rekordbox offset version exposes all
  required mixer labels.
- Mixer RE evidence and implementation boundaries live in
  `docs/research/rekordbox_mixer_active_deck_re_evidence.md`,
  `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`, and
  `docs/architecture/active_deck_authority.md`.
- Read the CFX FILTER knob (param0 + selected-effect-id + unit-channel) for
  decks 1/2 as **tracking/status only** (AWR-173, RB 7.2.11 and 7.2.16 chains,
  `implemented` / `software-tested` / `hardware-unvalidated`). This is the first
  runtime consumer of the mixer RE evidence and drives the LED filter-sweep
  overlay in `led_govee`. It is fully isolated from mixer authority (see the
  isolation rule below) and inert on every other RB version by construction.
- Rekordbox 7.2.16 direct-reader support (RB7216) is software-tested at parity
  with 7.2.11 for master/BPM/position/track/ANLZ decks 1-4, Deck 1/2 mixer
  upfader+LOW/BASS, and Deck 1/2 CFX FILTER tracking. Four roots are
  STATIC-CONFIRMED; interior hops are CANDIDATE carried from the 7.2.14 deck
  layout and 7.2.11 mixer/CFX layout. Live-unvalidated; not cleared for live use.
- Resolve USB-device-tree loads to their unique local-library twin on the
  operator's laptop (AWR-207), including the local ANLZ/PSSI source needed for
  phrase parsing. Foreign-laptop portability is the separate AWR-208 program.

Authoritative code:
- `rb_memory.py`
- `rb_state_reader.py`
- `rb_offsets.py`
- `live_bpm.py`
- `probe_live_bpm.py`
- `probe_deck2.py`
- `probe_cfx_filter.py` (AWR-173 passive CFX desk-calibration probe)
- `filepath_resolver.py` (AWR-207 local-twin identity/data-source resolver)

Key symbols:
- `RBMemoryReader`
- `PositionCache`
- `RBStateReader`
- `LiveBPMService`
- `MixerAuthoritySnapshot`
- `MixerDeckReading`
- `CfxDeckReading`
- `CfxFilterSnapshot`
- offset-table constants and probes

Runtime flow:
- inputs: Rekordbox process memory, offset tables, discovery probes, local file/path hints
- decisions: readiness, freshness, valid chains, fallback behavior
- outputs: `BridgeEvent`s, `PositionSnapshot`s, live BPM status, mixer authority
  snapshots
- under mixer authority, raw Deck A/B direct-master reads publish
  `MASTER_CHANGED` on change and on a bounded refresh interval before
  `rb_master_deck` freshness can expire
- raw Deck C/D, sentinel/no-master, and unreadable direct-master states publish
  a single invalidating `MASTER_CHANGED deck=0` transition with a short reason;
  raw C/D never alias into Deck 1/2 authority
- Deck 1/2 transport support fails closed: once a transport path was available,
  becoming unreadable emits `PAUSE` with `reason=transport_unavailable`; raw
  Deck C/D transport remains suppressed for resolver eligibility
- `RBStateReader` attach is retrying, not one-shot (AWR-234): if the bridge
  starts before Rekordbox is up, the thread marks all direct signals
  unavailable, logs one WARNING then DEBUG on repeats, clears cached pid/base,
  waits ~5 s on `stop_event`, and retries. Mid-session process death
  (`os.kill(pid, 0)` failure after a tick `OSError`) detaches the same way and
  re-enters the wait/retry loop. `attach_health()` exposes `{'attached': bool}`;
  when memory health has no reason and the event reader is not attached, status
  surfaces `reason=waiting_for_rekordbox` (reads_ok unchanged). Tick logic,
  ANLZ_PATH-before-TRACK_LOADED, and enqueue-only emission are unchanged.
- `ANLZ_PATH` and `TRACK_LOADED` payloads carry `rb_raw_deck` (the raw RB deck
  index 0-3) so `StateManager` can reject a load surfacing on the idle RB
  sibling of a playing bridge deck (RB decks 1&3 collapse onto bridge deck 1,
  2&4 onto bridge deck 2 via `_bridge_deck`; the reader itself performs no
  sibling arbitration)
- A transient failed ANLZ pointer-chain read (`None`) must not overwrite the last
  successful ANLZ cache entry; empty-string successful reads still represent
  unloaded/empty state. `tests/test_rb_state_reader.py` covers the recovery path.
- The unresolved-deck-2 playhead scans (`_scan_objc_zone`,
  `_scan_static_elapsed_candidates`, `_scan_objc_heap_moving`) compare two memory
  snapshots int32-by-int32. Done as a pure-Python loop that holds the GIL these
  froze the whole bridge: measured ~54 ms per 512 KB zone pass and ~427 ms per
  4 MB heap chunk, up to a 128 MB cap = multiple seconds, recurring every 5 s
  while deck 2 is unresolved during play (the live 1-7 fps LED collapse and
  `event-late` bursts at cue/load moments). The numeric pre-filter is now shared
  helpers `_i32_moving_candidates` / `_i32_static_candidates` with a numpy fast
  path (measured 28-40× — 1.9 ms / 10.6 ms) and a pure fallback that yields the
  GIL every 16,384 ints. numpy is a lazy OPTIONAL import (repo pattern); it never
  becomes a hard dependency and any numpy error falls back to the pure loop for
  that call. Candidate values, order, per-candidate checks, retries, and every log
  line are unchanged — proven byte-identical against an old-loop oracle (incl. the
  int32-overflow edge) in `tests/test_rb_memory_scans.py`.
- AWR-157 deck-2 chain freshness gating (`rb_memory.py`): a live_pos chain
  snapshot only counts as healthy (`chain_ok`) for deck 2 when it is FRESH — raw
  advanced within the last `_CHAIN_FRESH_TICKS = 5` consecutive reads while the
  external playing hint (`RBMemoryReader._deck_playing_hint`, wired from
  `StateManager.get_deck_playing` in `__main__.py`) says the deck is playing. A
  frozen-while-playing chain now marks `chain_ok = False` so the existing ObjC
  fallback (`RBSession.read_deck`) engages on the same tick instead of silently
  trusting a dead value; position handling is otherwise unchanged (no zeroing).
  While the hint says paused/stopped, an unchanging raw is exempt — a real pause
  reads frozen legitimately and never counts as stale. Deck 1 is untouched:
  `chain_ok` stays exactly `chain_snap is not None`. `skip2` (the "don't scan
  while the chain is healthy" gate) already read `_chain_ok_last[2]`, so it
  inherits the freshness gate automatically — `RBSS_POS_CHAIN_SKIP_OBJC=1` now
  means "never scan while the chain is actually working", not "never scan while
  a chain merely exists"; the env line itself is untouched. Edge-triggered INFO
  `[RBMEM] chain-stale fallback-engaged/fallback-idle deck=2` logs the
  staleness transition. A companion Q-B DEBUG log (`[RBMEM] deck=2
  pause-vs-freeze`) fires when deck 2's self-inferred playing flips true→false
  within 10s of the deck starting to play, with raw/prev_raw/the hint value, to
  tell a real pause apart from a frozen-while-playing field from one live
  session — diagnostic only, no dispatch behavior change.
- AWR-160 phantom track-load stability gate (`rb_state_reader.py:_tick_deck`):
  a candidate track title must read identically for `_LOAD_STABLE_TICKS = 3`
  consecutive deck ticks, and differ from the currently emitted track, before
  `ANLZ_PATH` + `TRACK_LOADED` fire (ANLZ_PATH still first, same tick). This
  is a stability window, not a playing/position requirement — a track that
  loads and is never played still emits once stable (the FEIN case). Browse-
  cursor bleed (library browsing surfacing as a stream of fake loads while the
  position path correctly reads the deck empty — up to 168 phantom loads in
  one mix, one deck-2 burst cycling 9 fake "tracks" in ~2 s) rarely holds one
  title across 3 ticks and is discarded before it ever reaches emission. Once
  a title is already confirmed, a late-resolving ANLZ path may still catch up
  on its own (unaffected by a transient read failure during the stability
  window). Every discarded pre-stability candidate emits one throttled DEBUG
  line (`[RBSR] phantom-load-suppressed`) carrying the discarded title/ticks
  and the ANLZ read available in scope, plus an edge-triggered INFO summary
  at most once per 60 s (`[RBSR] phantom-storm`) so a storm is visible in
  normal logs without turning DEBUG on. Unload/track-change recognition for
  an already-confirmed track is unchanged and immediate — the gate delays
  recognition of a new candidate, it never suppresses a stable state.
- AWR-207/AWR-209 USB-export resolution (`filepath_resolver.py`): local UUID
  lookup is unchanged. The path-only classifier recognizes both local layouts:
  a complete UUID directory and Rekordbox 7's split
  `USBANLZ/<first-3>/<UUID remainder>/ANLZ...` layout. `/Volumes/...` remains a
  device export before UUID inspection. This keeps the early phrase worker on
  for local loads while real USB loads still use only the resolved-time worker.
  A device-export miss filters local DB rows by BPM
  (±0.05) and duration (±2 s), reads ANLZ only for that candidate set, and
  accepts an untagged mirror twin only when the complete beatgrid fingerprint
  is exact. The payload carries local
  identity plus optional `local_anlz_path`; StateManager prefers that field for
  the resolved-time phrase/spectral worker. Zero/multiple matches stay
  unresolved, and a device miss skips lsof. All I/O remains in the resolver
  daemon thread; the push loop is unchanged.
- AWR-209 foreign-stick imports use the mounted stick's read-only
  `PIONEER/rekordbox/export.pdb` only after the exact mirror match abstains.
  Exact-normalized title + artist + duration (±2 s) must select one local row,
  then the USB grid's BPM + duration must agree. Missing tags log
  `usb-crossanalysis-unconfirmed`; no local tag match logs `usb-pdb-miss`;
  duplicate local matches log `usb-pdb-ambiguous` with candidate IDs; missing
  or unreadable local analysis logs `imported-not-analyzed` and tells the
  operator to finish analysis in Rekordbox, then CHAINS to the sidecar source
  (AWR-211 source order: local DB → sidecar → miss) rather than returning None,
  so a foreign laptop can still resolve the track from his stick's sidecar. A
  crafted `export.pdb` that raises IndexError is caught alongside the other
  parse errors and degrades to the sidecar with the right reason. Every conflict
  returns no identity.
- AWR-211 portable sidecar resolution runs only after the local library cannot
  answer. It lazily discovers schema-v1
  `*/RBSS BRIDGE USB/lighting_sidecar/index.json` across mounted volumes plus
  the installed
  `~/Library/Application Support/RBSS Bridge/lighting_sidecar/index.json`.
  Index caches are revalidated by file identity/metadata, so a rebuild,
  unplug/replug, or newly mounted root is rediscovered. Exact full-grid
  fingerprints may resolve mirror copies; cross-analysis requires the loading
  stick's PDB tags plus BPM/duration agreement. Identical matching records in
  App Support and on a still-mounted USB are deduplicated with App Support
  preferred; different matching generations fail closed as
  `sidecar-root-ambiguous`. The payload points `local_anlz_path` into the
  selected sidecar, carries SSID/laser tags, and passes a validated sidecar v4
  object directly to the ANLZ worker before any local-cache lookup. With smart
  rearm enabled, that resolved ANLZ phrase worker now starts even when spectral
  analysis and LED-v2 identity are both disabled. Missing DB logs `no local
  library — sidecar-only mode` once. Unknown schemas, ambiguous identities,
  escaped paths, missing declared files, and corrupt v4 fail closed. All
  discovery and parsing stays on the resolver/worker threads; no file I/O was
  added to the 200 Hz push loop.

Config:
- `config.py`
- `rb_offsets.py`
- direct-reader environment flags

Tests:
- search `tests/` for Rekordbox reader, offset, live BPM, and memory-reader tests
- `tests/test_rb_memory_scans.py` proves the deck-2 scan pre-filters are
  byte-identical across numpy / pure fallback / old-loop oracle and that both
  paths yield the GIL (pure seams only — no mach, no live process)
- `tests/test_rb_memory_chain.py` (`ChainFreshnessTests`) proves the AWR-157
  freshness gate: frozen raw while playing goes stale after exactly 5
  identical reads, advancing raw always stays fresh, frozen raw while paused
  stays healthy indefinitely (the FEIN case), the ObjC fallback engages when
  stale, deck 1 is provably untouched, and both new log lines are
  edge-triggered rather than per-tick. Pure seams via a fake-memory `RBSession`
  — no mach, no live process.
- `tests/test_rb_state_reader.py` (`TickEventTests`) proves the AWR-160
  stability gate: a churning browse storm (a new title every tick) emits
  nothing and logs phantom-suppressed/phantom-storm; a stable load emits
  exactly one ANLZ_PATH+TRACK_LOADED pair in order after 3 ticks; a track
  that loads and is never played still emits (the FEIN case); a title that
  changes again before stabilizing only lets the later one emit; unload
  after a stable load behaves as before; deck 1 and deck 2 gate
  symmetrically; a stable load never re-emits on later unchanged ticks.
  Pure seams via the existing fake mach-read backend — no mach, no live
  process.
- `tests/test_filepath_resolver_usb_twin.py` proves AWR-207/AWR-209 device
  detection (including split local UUID versus the same shape under `/Volumes`),
  exact mirror identity, red-team collision abstention, minimal PDB
  parsing, copied/referenced imports, cross-analysis matching, conflict and
  duplicate rejection, actionable analysis misses, payload parity, and the
  no-lsof miss. `tests/test_smart_transitions.py` pins the split-local path's
  early + resolved worker calls plus the payload-selected local ANLZ handoff.
- `tests/test_filepath_resolver_sidecar.py` proves AWR-211 schema/path guards,
  revalidated multi-mount and installed discovery, rebuild/unplug/replug,
  identical-root deduplication, conflicting-generation rejection,
  collision/tag rules, payload parity (including SSID/laser tags/v4),
  local-hit priority, local-miss chaining, no-DB logging, and sidecar-v4
  preference. `tests/test_smart_transitions.py` pins the smart-rearm sidecar
  phrase worker with spectral and LED-v2 disabled.
- `tests/test_awr211_sidecar_phrase_e2e.py` is the executed no-mocked-seams
  sidecar phrase proof (review R1): a hermetic test builds a real PQTZ/.DAT +
  PSSI/.EXT sidecar, loads the real index, selects via the real exact-fingerprint
  rule, and parses phrase through the real runtime worker; a skip-unless-mounted
  test drives AWR-210's real 880-track MINK sidecar through the full
  `_sidecar_lookup` → `_payload_for_sidecar` → `_read_runtime_anlz_data` chain and
  asserts real USB loads resolve to phrase with v4.
- if no direct hardware/process test exists, mark live behavior unvalidated in repo evidence

Change contract:
- If modifying offsets or memory chains, update `docs/status/support_matrix.md` and validation docs.
- If changing event emission, inspect `state_manager.py` and `models.py`.
- Run relevant unit tests plus broad discovery tests if available.

Known risks:
- macOS process permission assumptions
- Rekordbox version drift
- stale offsets
- false readiness
- treating one working local version as support for all versions
- treating the software-tested local 7.2.11 mixer-authority code path as
  hardware/live validation
- accidentally accepting anonymous/unknown offset lines as mixer authority
- using the live-BPM `_follow_float()` helper for mixer values; valid mixer
  endpoints include `0.0`, `255.0`, and `1023.0`, so mixer reads use finite
  range-checked f32 reads instead and preserve `unreadable`, `non_finite`, and
  `out_of_range` invalid reasons
- letting Decks 3/4, CFX FILTER, mid/high EQ, crossfader, gain/trim, mute, FX,
  or real audio loudness become active-deck authority inputs

CFX FILTER tracking (AWR-173) — the isolation rule:
- `_tick_cfx` (`rb_state_reader.py`) reads the CFX FILTER param0 (`0..1` f32),
  selected-effect-id (`0` == FILTER), and unit-channel (`== deck-1`) for decks
  1/2 and publishes a frozen `CfxFilterSnapshot` via `Ev.CFX_STATE`. Per-deck
  validity is deliberate (deck 1 keeps working when deck 2 is unreadable).
- `Ev.CFX_STATE` is **never** in `_authoritative_kinds`, `CFX_STATE` never enters
  `_tick_mixer`'s reads tuple, and `StateManager` only STORES the snapshot (no
  resolver rerun). A dead/garbage CFX chain with healthy mixer chains must leave
  `MixerAuthoritySnapshot.valid == True` — pinned by
  `tests/test_rb_state_reader.py` (`CfxTickTests.test_isolation_broken_cfx_keeps_mixer_valid`).
  The `_tick_mixer` whole-snapshot invalidation (any read fails ⇒ mixer invalid)
  is exactly the trap CFX must never join.
- CFX chains exist for RB 7.2.11 and 7.2.16 only; every other version leaves the six fields
  `None`, so `_tick_cfx` emits nothing and the feature is inert.

Reader live-safety + cross-version extension (AWR reader-safety, 2026-07-10, software-tested):
- **Direct-read BPM cap.** `_follow_float` (`rb_state_reader.py`) rejects a live-BPM
  read outside `0 < v < _RB_BPM_READ_MAX` (default 300, env `RBSS_RB_BPM_READ_MAX`),
  returning `None` (keep-prior). Tightened from the old `< 1000`: a garbage memory
  read can no longer reach `d.meta.bpm` and drive beat-locked LED/laser flash timing.
  The live-BPM SCANNER (`live_bpm.py` `_valid_bpm`) independently gates to
  `LIVE_BPM_MIN..LIVE_BPM_MAX` (40..250), version-independent.
- **Fail-closed on unknown version is partial by design.** `make_rb_state_reader`
  is inert on an unsupported build (`_offs is None` ⇒ `run()` early-returns, no direct
  reads); `LiveBPMService`/`RBMemoryReader` still scan (bounded 40..250). The
  outgoing-tempo clamp `osl_output.clamp_emit_bpm` is the version-independent choke on
  the SoundSwitch feed (see `soundswitch_output.md`).
- **Version-extension mechanism (offline).** `tools/rekordbox_derive_offsets.py`
  derives a new build's chain anchors from the rekordbox **arm64 symbol table**:
  master/anlz/mixer anchor = `<Class>::singletonHolder + 0x40`
  (`ApplicationMode` / `browse::LoadedContentsManager` / `djengine::DjEngineIF`),
  reproduced against 7.2.11 by `--expect 7.2.11`. The deck (bpm/pos/track_info) anchor
  is an LLVM `__MergedGlobals` with no clean symbol — carried forward from the nearest
  known version and confirmed by a live read. Fails closed (raises) on a missing or
  ambiguous anchor symbol or an implausible RVA — never a silent-wrong offset. Offline
  dev-machine tool only (no runtime importers); adding a version = rebuild `rb_offsets.py`
  + the USB bundle (the table is frozen into the bundle).
- Pinned by `tests/test_rekordbox_reader_safety.py`.

AWR-222 dormant Accessibility MEASUREMENT probe (2026-07-12; honesty 2026-07-13):
- Packaged `--probe-rekordbox-accessibility` → `usb_launcher_ax_probe.py` is
  implemented/software-tested and **not executed**. It is a diagnostic only —
  not a reader, emits no `BridgeEvent`s, does not write `PositionCache`, and is
  not on the normal menu. No live AX/TCC/USB evidence. AX remains dormant, not
  a selected replacement reader. Target `get-task-allow` is the expected
  TimecodeLink-style access mechanism; stock Apple-Silicon attach after
  successful patch + deep verify + GTA=true + relaunch is live-unvalidated /
  unknown. Current memory/MTC/OSC readers and active-deck policy are unchanged.

USB ANLZ audio-path leading slash (2026-07-12, software-tested):
- `_device_audio_filepath` now strips a leading `/` on stick-root-relative PPTH
  tags (`/Contents/...`) before joining under the ANLZ mount — same rule as
  `tools/spectral_stick_sweep.py`. `..` / drive-letter escapes and symlink-out
  still fail closed. `_read_device_pdb_track` still requires an absolute
  `/Volumes/<mount>/PIONEER/...` anlz path to locate export.pdb (root-relative
  `/PIONEER/...` alone is not a mount locator — fail closed by design).
  Pinned in `tests/test_filepath_resolver_sidecar.py`.
