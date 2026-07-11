---
doc_status: current
truth_level: code-verified
last_verified_commit: fc0f12f
last_verified_date: 2026-07-09
validation_scope: software-only
---

# Task: Rekordbox reader or offset changes

Use when:
- The requested work is specifically about Rekordbox reader or offset changes.

Read first:
1. `AGENTS.md`
2. `docs/agents/change_contracts.yml`
3. `docs/subsystems/rekordbox_readers.md`
4. `docs/agents/change_contracts.md`

Do not read first:
- archive docs
- old prompts
- old plans
- unrelated subsystem cards

Allowed changes:
- The narrow files required by the task.
- Docs/status/test inventory files required by the change contract.

Forbidden changes:
- unrelated runtime behavior
- local ignored configs or backups
- support/validation claims without evidence
- test modifications just to hide failures

Implementation notes:
- Inspect `rb_memory.py`, `rb_state_reader.py`, `rb_offsets.py`, `live_bpm.py`, `state_manager.py`.
- Prefer the smallest code or docs change that satisfies the task.
- Verify current behavior against code before updating docs.
- For active-deck authority support, keep direct master freshness, invalidation,
  raw Deck C/D no-aliasing, concrete mixer invalid reasons, and transport
  fail-closed behavior covered by focused tests.
- The deck-2 playhead scans share the vectorized numeric pre-filters
  `_i32_moving_candidates` / `_i32_static_candidates` (numpy fast path + a pure
  fallback that yields the GIL). If you touch those filters, keep candidate
  values/order/logs identical and re-run the byte-identical oracle check in
  `tests/test_rb_memory_scans.py`; numpy must stay a lazy optional import.
- (AWR-157) Deck 2's live_pos chain health (`chain_ok`) is freshness-gated:
  frozen raw for `_CHAIN_FRESH_TICKS` consecutive reads while the external
  play hint (`RBMemoryReader._deck_playing_hint`) says playing is a miss, not
  a healthy read; a real pause is exempt (unchanging raw while paused is
  legitimate). Deck 1 must stay untouched by any future change here — its
  `chain_ok` is exactly `chain_snap is not None`, no freshness check. If you
  touch the freshness gate, re-verify the exact-5-ticks boundary and the
  deck-1-untouched invariant in `tests/test_rb_memory_chain.py`.
- (AWR-160) Track-load emission in `_tick_deck` is gated by a stability
  window, not readiness: a candidate title must read identically for
  `_LOAD_STABLE_TICKS = 3` consecutive ticks, and differ from the currently
  emitted track, before `ANLZ_PATH` + `TRACK_LOADED` fire (ANLZ_PATH still
  first, same tick). This is deliberate — a track that loads and is never
  played must still emit (the FEIN case); do not turn this into a playing/
  position requirement. Discarded pre-stability candidates log a throttled
  DEBUG line and an edge-triggered 60s INFO storm summary
  (`_note_candidate_discarded`). If you touch this gate, re-verify the
  browse-storm-emits-nothing, FEIN-still-emits, and deck-1/2-symmetry cases
  in `tests/test_rb_state_reader.py`.
- (AWR-173) CFX FILTER tracking is **tracking/status only** and MUST stay
  isolated from mixer/active-deck authority. `_tick_cfx` reads its own chains,
  publishes `Ev.CFX_STATE`/`CfxFilterSnapshot`, and must NEVER: join
  `_tick_mixer`'s reads tuple, enter `_authoritative_kinds`, or trigger a resolver
  rerun. The `_tick_mixer` whole-snapshot invalidation (any failed read ⇒ mixer
  invalid) is the trap CFX avoids by living in its own tick/event/snapshot. CFX
  chains are 7.2.11-only; keep every other version `None` so the feature is inert.
  If you touch this, re-verify the isolation pin
  (`tests/test_rb_state_reader.py`, `CfxTickTests.test_isolation_broken_cfx_keeps_mixer_valid`)
  and the CFX/mixer parser-independence cases in `tests/test_rb_offsets.py`.
- (AWR-207) USB-export resolution is fail-closed and payload-driven. Local UUID
  loads keep their existing path. Device-path misses may resolve only to one
  BPM/duration + beatgrid-confirmed local twin; zero/ambiguous matches stay
  unresolved and never fall through to lsof. The optional FILEPATH_RESOLVED
  `local_anlz_path` is the data-source seam StateManager consumes for the
  resolved-time phrase/spectral worker; do not make StateManager depend on the
  local DB as the only producer. AWR-208 sidecars are separate design work.
- (AWR-209) An untagged device load may use only an exact complete-grid
  fingerprint. Cross-analysis drift requires the mounted export's read-only
  `export.pdb` title + artist + duration to select exactly one local import,
  plus independent BPM/duration agreement. Missing PDB tags, conflicts,
  duplicates, or missing local analysis must return no identity with the
  documented `usb-*` / `imported-not-analyzed` reason; never guess.

Required tests:
- Run the targeted tests listed in the subsystem card.
- For ANLZ/track-load ordering or cache changes, include `tests/test_rb_state_reader.py` coverage for
  transient ANLZ read failures and recovery, and the AWR-160 stability gate
  (browse storm, FEIN never-played, deck-1/2 symmetry).
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.

Required docs updates:
- `docs/subsystems/rekordbox_readers.md`, support/validation matrices

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
