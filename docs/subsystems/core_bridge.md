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

Audit P1 (2026-07-03):
- Removed confirmed-unused legacy lighting events and the unused `RBSS_RB_STATE_SHADOW` branch.
- Kept `LED_PHRASE_MONOTONIC_ENV` in `state_manager.py`; unused LED env-name constants were removed
  because their consumers already read the same env names directly.

Audit P2 (2026-07-03):
- Startup leaves OS2L injection tooling off unless explicitly opted in by env.
- `StateManager` still submits software ZERO while SoundSwitch is connected; the copied pack status
  adds suppressed-overlay diagnostics without changing pack output precedence.

Audit P3 (2026-07-03):
- Startup can launch one daemon spectral-cache eviction thread only when both smart-rearm and
  spectral analysis are explicitly enabled (it evicts both the v3 dir and the v4 subdir, never
  crossing versions). Govee realtime handoff transport teardown is runner thread work, not
  StateManager caller-thread work.

Spectral v4 (2026-07-05):
- The spectral ANLZ worker reads the schema-v4 cache first and falls back to v3 entries or a
  fresh extraction (v4 preferred; grids longer than ~15 min take the legacy v3 extraction at
  load and leave v4 to the offline sweep). Every path feeds the smart-drop scorer a
  bit-identical v3-shaped view, and the chosen path is logged as `[SM] spectral-path`.
- E2 section-energy grades (AWR-288, `section_energy_v0.grade_sections`): computed on the
  same ANLZ worker at track load when `RBSS_SECTION_ENERGY` is on (default OFF ⇒ byte-identical),
  carried on the `ANLZ_DATA` event beside `f2_plan`, stored on `TrackMetadata.section_grades`
  (reset in `clear()`), and surfaced in the per-deck status `section_energy` block. Status-only:
  no lighting consumer reads them at E2.
  Details + proofs: `docs/research/spectral_audio_analysis_redesign.md`.

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
- `ANLZ_DATA` stores raw drop markers on `meta.anlz_drops` and selected,
  section-collapsed markers on `meta.smart_drops`; phrase-segment labeling
  still uses the raw list.
- AWR-257: alongside `meta.smart_drops`, inside the same `markers_changed`
  guard, StateManager computes `meta.drop_sections` (`smart_phrasing.drop_sections`
  over the runway-gated `select_true_drops`) — one `DropSection` per true drop
  (Brandon's rule: only the FIRST marker in a drop section, with a buildup
  runway, is a true drop). It carries the section's true drop, its contiguous
  chorus-run end, and the ≥16-beat in-section LED advance points. Reset with
  `smart_drops` in `TrackMetadata.clear()`. It governs LED look selection ONLY;
  laser/SoundSwitch/firing/blackout paths never read it.
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
- while a bridge deck is playing, `TRACK_LOADED`/`ANLZ_PATH` events whose
  `rb_raw_deck` differs from the RB deck that last drove `PLAY` are ignored
  (`_is_playing_sibling_load`) so a transient idle-sibling buffer write cannot
  clobber the playing deck's metadata or arm the wrong scripted show; events
  without `rb_raw_deck` pass unchanged (fail-open)

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
