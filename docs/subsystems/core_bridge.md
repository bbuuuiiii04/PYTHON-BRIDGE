---
doc_status: current
truth_level: code-verified
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
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

SoundSwitch pack-player boundary:
- The strict decoder/exporter/verifier and immutable pack loader/player remain outside `StateManager`. Optional MIDI-input, backend, and Enttec components are built by startup/command-thread orchestration and passed to `StateManager` as one immutable runtime bundle.
- T7.0 keeps process signal ownership in `__main__`; T7.1 routes the existing laser executor through one injected backend while retaining the MIDI default path.
- T7a/T7b/T7c/T7e are wired: `__main__` loads optional default-off config, chooses one backend, starts verified workers, creates `PackRuntime`, injects it into `StateManager`, and wires sanitized status plus validate-first commands. Absent/disabled config preserves legacy MIDI; dry-run/none opens no pack hardware.
- The active roadmap records remaining runtime closure: one-click export/publish/reload, scripted pause/mode/input-health/status, T7d Autoloop phase, and hardware validation. Current Autoloop pack output remains zero-safe.

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
- laser drop-lifecycle state is reset alongside existing lifecycle teardown on master change, active track load, full stop, and resume; director-only resets also run on scripted and idle lighting transitions

Config:
- `config.py`
- environment flags used by startup and state manager
- local ignored config files for laser/LED bundles

Tests:
- inspect `tests/` for state manager, runtime status, smart phrasing, and integration tests
- recommended broad command: `python -m unittest discover tests`
- laser lifecycle integration coverage includes `tests/test_laser_director_lifecycle.py` and `tests/test_laser_executor_lifecycle.py`

Change contract:
- If modifying startup, also inspect `runtime_status.py`, subsystem bundle builders, and status docs.
- If modifying `StateManager`, inspect relevant subsystem director/executor docs and tests.
- Update `docs/architecture/current_architecture.md`, `docs/architecture/runtime_invariants.md`, and this card.

Known risks:
- blocking the hot path
- creating competing state writers
- treating fallback readers as always authoritative
- documenting local setup as broad support
