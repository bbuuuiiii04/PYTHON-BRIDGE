---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec for overnight R1.5 (executive-folded, sequenced by manager judgment ahead of the laser rounds); grounded in docs/research/phantom_load_palette_triage_2026_07_08.md (claude5 triage, log-measured); bridge DOWN and stays down
---

# Codex Implementation Spec - Phantom track-load gate (AWR-160)

From `docs/research/phantom_load_palette_triage_2026_07_08.md` (read FIRST):
the reader emitted **168 track loads in one mix** (13 storms; one deck-2 burst
cycled 9 "tracks" in ~2 s) while the position path simultaneously read the
same deck as `file=<none> bpm=0.0` — the operator browsing his library leaks
through the load path as phantom loads. Every phantom ran the full pipeline
(ANLZ → resolve → identity → palette repaint) = the "palettes don't remember"
flicker. The v2 identity store is EXONERATED (zero drift over 122 keys); the
LED code is downstream and innocent; AWR-152 not implicated. The load-emission
path lacks the readiness discipline the position path already has.

## Part A - Context & design decisions (verified)

1. Load emission lives in `rb_state_reader.py:_tick_deck` — ANLZ path is
   emitted BEFORE `TRACK_LOADED` (`:342-373`; this ordering is an AGENTS.md §6
   invariant and MUST survive the gate: delay both together, never reorder).
   `FILEPATH_RESOLVED`/identity flows from the load downstream
   (`state_manager.py:2388` sets `meta.content_id`).
2. **Design decision — the gate is a STABILITY WINDOW, not a
   playing/position requirement.** The triage offers both shapes; a
   readiness requirement (pos>0 / bpm>0 / playing) would suppress legitimate
   load-without-play (the FEIN case from the same night: loaded, never
   played, must still arm scripted tracks). Stability: the SAME track
   identity must be read on `_LOAD_STABLE_TICKS = 3` consecutive deck ticks
   before the load is emitted (load_gen advances only then). Browse storms
   (sub-1.5 s title churn) never reach 3 stable ticks; a real load — playing
   or not — trivially does. Latency cost ≈ 2 extra deck ticks, irrelevant to
   live use (loads precede play by seconds+).
3. A phantom-REJECTED candidate is the instrumentation opportunity for the
   triage's named unknown (which memory read leaks the browse cursor):
   candidates that appear and vanish within the window get one throttled
   DEBUG line carrying whatever source identity the reader has for that read
   (title/id and the read-path fields available in scope) so a future pass
   can pin the leaking offset/pointer WITHOUT another live triage.
4. Unload/eject and track-CHANGE paths: a deck going empty, or changing to a
   different stable track, must behave exactly as today once stability is
   met; the gate delays recognition, never suppresses a stable state.
5. Contract: `rekordbox_readers`.

## Part B - Tasks (one commit each, explicit paths)

### Absolute Rules
- NO bridge starts; live config read-only; LED/laser/SoundSwitch code
  untouched — this round lives in the reader layer (`rb_state_reader.py`
  primarily; `rb_memory.py`/`rb_offsets.py` only if the instrumentation needs
  a field passed through). Do not modify AWR-157's freshness logic beyond
  coexisting cleanly with it.
- Behavior that must not change: ANLZ-before-TRACK_LOADED ordering; stable
  real loads (playing or not) emit exactly one load with correct metadata;
  deck unload/clear semantics; deck-1/deck-2 parity of the gate; the 200 Hz
  push loop; event immutability.
- Fail direction: uncertainty holds the CURRENT state (no emission) rather
  than emitting a possibly-phantom load — a delayed real load is a minor
  lag; a phantom load corrupts palettes and identity state downstream.

### Task 1 - `rb_state_reader.py`: the stability gate
Per deck, track the candidate identity (the same track-identity tuple the
tick already reads) across consecutive ticks; emit ANLZ_PATH + TRACK_LOADED
(in that order, same tick) only when the identity has been identical for
`_LOAD_STABLE_TICKS = 3` consecutive ticks AND differs from the currently
emitted track. Candidate resets whenever the read identity changes. Module
constant, no new env knob.

### Task 2 - Phantom instrumentation (the named unknown)
When a candidate is discarded before stability (browse bleed), emit ONE
throttled DEBUG line (`[RBSR] phantom-load-suppressed deck=N ticks=K
title=…` plus the read-source fields available in scope). Also an
edge-triggered INFO counter summary at most once per minute during storms
(`[RBSR] phantom-storm deck=N suppressed=M window=60s`) so tomorrow's logs
quantify the fix without DEBUG enabled.

### Task 3 - Tests (`tests/test_rb_state_reader.py`)
Pure seams with synthetic tick sequences: browse storm (identities churning
every 1-2 ticks) → zero emissions, suppression counters increment; stable
new track (playing) → exactly one ANLZ+TRACK_LOADED in order after 3 ticks;
stable new track NEVER playing (FEIN case) → still emits; A-then-quickly-B
→ only B emits; unload → today's behavior after stability; deck-1 and
deck-2 symmetric; load_gen advances only on emission.

### Task 4 - Contract docs (final commit)
`rekordbox_readers` docs_update list in full; AWR-160 registry row
(implemented / software-tested; triage doc flips to "gate implemented,
leak-source instrumentation live"); suite (known six reds) + three hard
checks.

## Part C - Invariants
- ANLZ_PATH precedes TRACK_LOADED for every emitted load (§6 invariant).
- A real load that never plays still emits (stability alone gates — pinned
  by the FEIN test).
- No emission ordering/reordering changes for stable states; readers still
  never mutate DeckState (events only).
- AWR-157's chain-freshness behavior untouched and co-tested (both features
  touch reader cadence; run its tests in acceptance).

## Part E - Acceptance
- [ ] Tasks 1-4, one commit each, explicit paths; auto-sync fragmentation
  noted-never-rewritten.
- [ ] Suite at known-six-reds; `tests.test_rb_memory_chain` +
  `tests.test_rb_state_reader` green; three hard checks.
- [ ] Operator summary: browsing the library can no longer spray fake track
  loads — palettes stop flapping mid-browse; real loads (even ones you never
  play) register exactly as before, ~half a second later at most; a new log
  line counts every suppressed phantom so we can see tomorrow that it
  worked, and a debug line fingerprints the leak source for the true
  root-cause pass.
- [ ] Print exactly AWR160-DONE with real suite numbers above it, or
  AWR160-BLOCKED plus the reason.
