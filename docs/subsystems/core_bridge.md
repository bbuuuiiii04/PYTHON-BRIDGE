---
doc_status: current
truth_level: code-verified
last_verified_commit: 871b5f9
last_verified_date: 2026-07-02
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
- RW-5 status is StateManager-owned copied state: one fresh dict is published from the already-rendered frame, and readers receive only a copy. `software_zero_frame` and the attempted frame counter are software intent, not physical output proof.
- The main 200 Hz loop catches ordinary drain/tick/snapshot exceptions, submits at most one direct pack ZERO frame for the failed iteration, logs a bounded counter, preserves the normal tick throttle, skips only that instant, and continues. It does not double-submit ZERO when `_push_tick()` already handled an inner tick failure, does not catch process-control exceptions, and does not force-zero separate OS2L/laser-MIDI/LED lanes.
- Sender health, native Autoloop live/runtime validation, and hardware
  validation remain open. Native Autoloop pack output is implemented in software
  through the existing pack driver, can seed from the executor's latched active
  Autoloop scene when no fresh edge is present, and remains SoundSwitch-present
  suppressed.
- Art-Net truth-check is a temporary default-off measurement path. With
  `RBSS_ARTNET_TRUTH_CHECK=1` and a valid `RBSS_ARTNET_UNIVERSE`, startup can
  build pack rendering without Enttec, keep production output software-zero when
  SoundSwitch is connected, and enqueue the rendered shadow frame to a bounded
  U1 validation worker. UDP and sidecar writes stay outside `StateManager`.
- Parity lane registries are offline export inputs. They do not change
  `StateManager` ownership or add runtime work; active `unverified_parity`
  documents still block trusted publication.
- Mixer active-deck authority is now StateManager-owned through the pure
  `active_deck_resolver.py` helper. `active_deck` is the resolved show deck and
  may be `0` for idle/no audible deck; `rb_master_deck` is retained separately
  for resolver tie/fallback behavior and status.

Authoritative code:
- `__main__.py`
- `state_manager.py`
- `active_deck_resolver.py`
- `models.py`
- `config.py`
- `runtime_status.py`

Key symbols:
- `main`
- `StateManager`
- `resolve_active_deck`
- `ActiveDeckDecision`
- `DeckState`
- `OutputState`
- `BridgeEvent`
- `Ev`

Runtime flow:
- inputs: Rekordbox reader events, MTC fallback, runtime command events, position snapshots, config bundles
- decisions: resolved show deck, Rekordbox master state, phrase/role state, lighting dispatch timing
- outputs: OS2L sends, laser decisions, LED decisions, copied status snapshots
- scripted-track LED automation is still StateManager-gated: `safety.scripted_mode_automation` must be true, `lighting_mode` must be `scripted`, and the smart-phrasing role is remapped through the latched LED `scripted_mode` policy before dispatch
- laser drop-lifecycle state is reset alongside existing lifecycle teardown on master change, active track load, full stop, and resume; director-only resets also run on scripted and idle lighting transitions
- while mixer authority is enabled, legacy OSC active-deck events, playing-only
  mirror detection, and `_do_resume()` empty-deck correction cannot directly
  rewrite `active_deck`; invalid/stale mixer fallback is resolver-mediated
  `rb_master_deck` fallback only
- idle/no-audible `active_deck=0` clears runtime state and must not call
  `deck_route(0)` or index `self._deck[0]`; entering idle also runs the existing
  fixed-deck SoundSwitch/OS2L clear/off body so stale previous-deck output is
  cleared without routing deck 0

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
- reintroducing an old active-deck authority bypass around the resolver
- treating fallback readers as always authoritative
- documenting local setup as broad support
