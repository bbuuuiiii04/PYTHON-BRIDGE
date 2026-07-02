---
doc_status: current
truth_level: code-verified
last_verified_commit: 74febec
last_verified_date: 2026-06-29
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
- Read named Deck 1/2 mixer upfader and LOW/BASS chains for software-tested
  active-deck authority when the selected Rekordbox offset version exposes all
  required mixer labels.
- Mixer RE evidence and implementation boundaries live in
  `docs/research/rekordbox_mixer_active_deck_re_evidence.md`,
  `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`, and
  `docs/architecture/active_deck_authority.md`.

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
- `MixerAuthoritySnapshot`
- `MixerDeckReading`
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
- `ANLZ_PATH` and `TRACK_LOADED` payloads carry `rb_raw_deck` (the raw RB deck
  index 0-3) so `StateManager` can reject a load surfacing on the idle RB
  sibling of a playing bridge deck (RB decks 1&3 collapse onto bridge deck 1,
  2&4 onto bridge deck 2 via `_bridge_deck`; the reader itself performs no
  sibling arbitration)

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
- treating the software-tested local 7.2.11 mixer-authority code path as
  hardware/live validation
- accidentally accepting anonymous/unknown offset lines as mixer authority
- using the live-BPM `_follow_float()` helper for mixer values; valid mixer
  endpoints include `0.0`, `255.0`, and `1023.0`, so mixer reads use finite
  range-checked f32 reads instead and preserve `unreadable`, `non_finite`, and
  `out_of_range` invalid reasons
- letting Decks 3/4, CFX FILTER, mid/high EQ, crossfader, gain/trim, mute, FX,
  or real audio loudness become active-deck authority inputs
