# SoundSwitch implementation — progress ledger

last_updated: 2026-06-21T23:55:00Z   last_session_model: claude-opus-4-8

## Proof gate

- HEAD: `f7ae38d`
- Verdict: `PASS_IMPLEMENTATION_MAY_BEGIN` (exit 0; last proven at `601d8db`)
- Checks: 29 PASS / 0 FAIL / 0 INCOMPLETE (F10 promoted in Task 4)
- Foundation: 27/27 PASS
- Note: T7.0 (`07581ca`) and T7.1 (`f7ae38d`) introduce NO SoundSwitch-semantics
  change (signal/shutdown wiring; executor backend injection + scene_name), so the
  proof gate is unaffected. Rerun at the T7 checkpoint and whenever SS
  decode/export/render changes (T8).

## Orchestration

- Operator (2026-06-21) put a Claude session in charge of T7+T8+T9-handoff per
  `soundswitch_t7_t8_orchestration.md`; chose **Claude-subagents-per-effort-table**
  as the implementer path (sanctioned failover for THIS workstream only — does not
  generalize). Before-T7 operator milestone is satisfied; auto-advance T7→T8.
- Running PR for the series: **#116** (`soundswitch/impl` → `main`).
- Carry-forwards to T7 author:
  1. In `__main__._shutdown`, place the real `soundswitch_frame_sender.stop()`
     EARLY (not last) so DMX blackout is prompt.
  2. T7 owns the `output_backend` config + the __main__ PORT-level selection
     (don't open IAC when `output_backend=pack`; build SoundSwitchFrameSender →
     PackOutputBackend; `none`→NoneBackend). T7.1 delivered only the executor-OBJECT
     half. opus-xhigh T7 reviewer must verify port-level mutual exclusivity.

## Task 7 design (verified at HEAD `f7ae38d`; for the implementer spec)

Surfaces mapped (read-only triage). Integration design direction — StateManager
is the runtime owner; per tick in pack mode it DRIVES the pure `LaserPackPlayer`
from authoritative state and submits frames nonblocking:
- mode authority = `os.lighting_mode` (`state_manager.py:3084`; scripted if
  `d.scripted_id and is_playing`, else autoloop if playing, else idle/debounced).
- scripted → `player.select_scripted(soundswitch_id=d.meta.soundswitch_id,
  elapsed_ms=d.elapsed_ms, …)`; autoloop → `player.select_autoloop(identity=
  <executor-accepted>, phase_tick, …)`; idle/stop/stale → safe/ZERO frame;
  controller (MIDI-input `snapshot()`, lock-protected nonblocking) →
  `set_masks(blackout, emergency)` + `hold_static(slot)`.
- output path: `submit_frame(player.render().frame)` → `frame_sender.submit(...)`
  (nonblocking deque). `PackOutputBackend.submit_frame` currently has NO caller —
  StateManager becomes the caller (the spec's "nonblocking frame submission").
- load/verify ordering: build `SoundSwitchPackPlayerConfig` + `load_pack()` (blocking
  fs I/O — startup ONLY) + `LaserPackPlayer` + `SoundSwitchMidiInputAdapter` +
  `PackOutputBackend(scene_to_identity, frame_sender)` at `__main__.py:722`
  (the `soundswitch_frame_sender = None` placeholder), BEFORE `StateManager(...)`
  (~794) and `sm.start()` (~1175).

Mechanisms to PIN during spec authoring (verify against current code, no guessing):
1. `phase_tick` source for `select_autoloop` (beat/autoloop-tick authority var —
   check the autoloop controller + `abs_beat_pos`/`autoloop_tick_just_fired`).
2. Routing the executor-accepted autoloop IDENTITY to StateManager (PackOutputBackend
   exposes last-accepted identity, vs StateManager maps `_last_triggered_scene` via
   `scene_to_identity`). Decide one; single source of truth.
3. `select_scripted` arg authority vars: transport / metadata_ready / authority /
   source_errored / elapsed_discontinuous / track_changed — map from deck state +
   the player's own tests (`tests/test_soundswitch_laser_player.py` = usage contract).
4. `scene_to_identity` built from the pack's 19 IAC bindings (loader output).
5. `fixture_map` (CH1-CH19→512) from `fixture_map_path`; passed to `frame_sender.submit`.
Live-safety: `_build_laser_context` forbids ALL I/O (`state_manager.py:3896`);
`load_pack`/config parse are blocking fs — startup only, never tick. Every transition
path (scripted/autoloop/idle, deck change, track load, stop/stale, config disable,
pack reload, worker error, shutdown) must clear held/pending state and resolve ZERO.

## Next action

> TASK 7 IN PROGRESS (PR #116): authoring Part A–E implementer spec
> (`docs/plans/active/soundswitch_task7_runtime_integration_spec.md`) via codex-spec,
> then opus-high implement → opus-xhigh review (full "Gate — before-T7"). Subtasks:
> config `soundswitch_pack_player.example.json`
> + validated loader; load/verify pack+config before workers; StateManager calls
> only pure player methods + nonblocking submit; output_backend port selection;
> all transitions resolve safe frames; sanitized status; no implicit hot enable
> (runtime-command contract). Reviewer: opus xhigh, full "Gate — before-T7".
> Then auto-advance to T8, run after-T8 opus-max review, author + review T9
> handoff, then AWAITING OPERATOR hardware gate.

## Task status (0–9)

| task | title | impl | review | gates | PR | notes |
| ---- | ----- | ---- | ------ | ----- | -- | ----- |
| 0 | change contract | done | done | green | #115 | Review approved; hard checks green; full suite `Ran 1881`, `OK` (3 skipped, 1 expected failure). |
| 1 | project decoder | done | done | green | #115 | Review approved; 17 targeted tests; proof 27/0/2 PASS; full suite `Ran 1898`, `OK` (3 skipped, 1 expected failure). |
| 2 | exporter and verifier | done | done | green | #115 | Review approved; 31 targeted tests; F9 PASS; full suite `Ran 1914`, `OK` (3 skipped, 1 expected failure). |
| 3 | pure renderer/player | done | done | green | #115 | Loader+player+verifier parity at `94cee81`. Opus review APPROVE (nits only). 43 targeted OK; full suite `Ran 1942`, `OK` (3 skipped, 1 expected failure); proof 28/0/1; twice-export byte-identical; F9 mutation rejected; identity gate rejects wrong-UUID scratch corpus. |
| 4 | MIDI input adapter | done | done | green | #115 | 32 tests; F10 CC export-fail check; proof 29/0/0; device-name dispatch + error-preservation + zombie-worker fixes post-review. HEAD `6a8ecf2`. |
| 5 | output backend | done | done | green | #115 | MidiOutputBackend/NoneBackend/PackOutputBackend; priority signature fix; PackOutputBackend unlearned→False; stale attr removed. 70+170 tests pass. HEAD `db7eac2`. |
| 6 | Enttec sender | done | done | green | #115 | 518-byte VLN-identical framing; bounded non-blocking deque; zero-on-stop; kill-9 hazard documented. 35 new tests; 2009 total. T7 note: remove _install_signal_handlers before wiring into __main__. HEAD `601d8db`. |
| 7 | runtime integration | wip | — | — | #116 | T7.0 (`07581ca`) + T7.1 (`f7ae38d`) done, both review APPROVE (fresh opus). T7.0: signal handlers removed, __main__ single signal authority. T7.1: executor single-backend injection + scene_name, MIDI byte/order-identical. Next: Task 7 proper (config/loader/StateManager/status/commands + port-level backend selection). |
| 8 | offline/shadow gates | todo | — | — | — | |
| 9 | hardware handoff | todo | — | — | — | operator-only; never auto-execute |
