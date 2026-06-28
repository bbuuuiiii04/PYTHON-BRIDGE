---
doc_status: current
truth_level: code-verified
last_verified_commit: 27a078b
last_verified_date: 2026-06-28
validation_scope: software-only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-output unvalidated
---

# Rekordbox Readers

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: current local Rekordbox/macOS setup only

Purpose:
- Read Rekordbox runtime state, position, track/load data, ANLZ paths, and displayed BPM through guarded local readers.
- Future mixer active-deck reader work should start from
  `docs/research/rekordbox_mixer_active_deck_re_evidence.md` and
  `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`.

Authoritative code:
- `rb_memory.py`
- `rb_state_reader.py`
- `rb_offsets.py`
- `live_bpm.py`
- `probe_live_bpm.py`
- `probe_deck2.py`

Key symbols:
- `RBMemoryReader`
- `PositionCache`
- `RBStateReader`
- `LiveBPMService`
- offset-table constants and probes

Runtime flow:
- inputs: Rekordbox process memory, offset tables, discovery probes, local file/path hints
- decisions: readiness, freshness, valid chains, fallback behavior
- outputs: `BridgeEvent`s, `PositionSnapshot`s, live BPM status

Config:
- `config.py`
- `rb_offsets.py`
- direct-reader environment flags

Tests:
- search `tests/` for Rekordbox reader, offset, live BPM, and memory-reader tests
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
- treating the proven local 7.2.11 upfader/LOW chains as implemented runtime
  authority before reader, resolver, status, and fallback work exists
