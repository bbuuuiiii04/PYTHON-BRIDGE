---
doc_status: current
truth_level: code-verified
last_verified_commit: eff532e
last_verified_date: 2026-06-21
validation_scope: software-only
---

# Core Bridge

Status:
- implementation: alpha
- software-tested: partial
- hardware-validated: no repo evidence
- compatibility: my local setup only

Purpose:
- Own startup wiring, bridge state, event handling, timing, and top-level coordination.

Task 2 boundary:
- The strict SoundSwitch 2.10.3 decoder, deterministic exporter, canonical 95-artifact pack, and independent verifier are read-only/offline and are not imported, started, or owned by `StateManager` or `__main__.py`.
- No live bridge behavior changed: OS2L, MIDI lasers, LED/Govee, Rekordbox readers, runtime status, config, and runtime commands retain their existing paths. Task 3 loader/player and Task 4+ MIDI/runtime/backend/Enttec integration remain planned and unimplemented.

Authoritative code:
- `__main__.py`
- `state_manager.py`
- `models.py`
- `config.py`
- `runtime_status.py`

Key symbols:
- `main`
- `StateManager`
- `DeckState`
- `OutputState`
- `BridgeEvent`
- `Ev`

Runtime flow:
- inputs: Rekordbox reader events, MTC fallback, runtime command events, position snapshots, config bundles
- decisions: active deck state, phrase/role state, lighting dispatch timing
- outputs: OS2L sends, laser decisions, LED decisions, copied status snapshots
- scripted-track LED automation is still StateManager-gated: `safety.scripted_mode_automation` must be true, `lighting_mode` must be `scripted`, and the smart-phrasing role is remapped through the latched LED `scripted_mode` policy before dispatch

Config:
- `config.py`
- environment flags used by startup and state manager
- local ignored config files for laser/LED bundles

Tests:
- inspect `tests/` for state manager, runtime status, smart phrasing, and integration tests
- recommended broad command: `python -m unittest discover tests`

Change contract:
- If modifying startup, also inspect `runtime_status.py`, subsystem bundle builders, and status docs.
- If modifying `StateManager`, inspect relevant subsystem director/executor docs and tests.
- Update `docs/architecture/current_architecture.md`, `docs/architecture/runtime_invariants.md`, and this card.

Known risks:
- blocking the hot path
- creating competing state writers
- treating fallback readers as always authoritative
- documenting local setup as broad support
