---
doc_status: current
truth_level: code-verified
last_verified_commit: e43edff
last_verified_date: 2026-07-08
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

Required tests:
- Run the targeted tests listed in the subsystem card.
- For ANLZ/track-load ordering or cache changes, include `tests/test_rb_state_reader.py` coverage for
  transient ANLZ read failures and recovery.
- Run `python -m unittest discover tests` when practical for cross-subsystem changes.
- Run docs checks for docs changes.

Required docs updates:
- `docs/subsystems/rekordbox_readers.md`, support/validation matrices

Stop and report if:
- code and docs disagree
- tests cannot run
- hardware validation would be needed to make the requested claim
- the change appears to cross subsystem boundaries not covered by this playbook
