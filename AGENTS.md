# AI Agent Guide - rb_ss_bridge_v2

## Quick Orientation

- **What this is**: Realtime Rekordbox to SoundSwitch bridge for macOS live DJ performance.
- **Language**: Python 3, macOS only, with process-memory readers, OS2L, MIDI, and local web tools.
- **Entry point**: `python3 -m rb_ss_bridge_v2` from `/Users/bbui`, or from an editable install.
- **Central authority**: `StateManager` is the event-loop owner and the only writer of `DeckState`.
- **Source layout**: Python modules are intentionally flat at repo root. Use the source map below instead of moving imports.

## Reading Order

1. `AGENTS.md` - repo orientation for automated contributors.
2. `docs/architecture/current_architecture.md` - 15-minute system overview.
3. `docs/architecture/runtime_invariants.md` - rules you must not break.
4. `docs/architecture/bridge_design.md` - detailed design reference.
5. `docs/architecture/doc_index.md` - classification of every Markdown document.

## Source Map

| Area | Files | Purpose |
| --- | --- | --- |
| Runtime coordinator | `__main__.py`, `state_manager.py`, `models.py`, `config.py` | Startup wiring, event loop ownership, state models, config constants. |
| Rekordbox direct readers | `rb_state_reader.py`, `rb_memory.py`, `rb_offsets.py`, `rb_state_shadow.py`, `live_bpm.py`, `probe_live_bpm.py`, `probe_deck2.py` | Direct state, position, BPM, offsets, probes, and debug shadowing. |
| TL/MTC fallback | `tl_tailer.py`, `mtc_reader.py` | TimecodeLink log and MIDI timecode fallback inputs. |
| Track metadata | `filepath_resolver.py`, `anlz_reader.py`, `scripted_tracks.py`, `ss_library_scanner.py` | Filepath, ANLZ, scripted-track, and SoundSwitch library resolution. |
| Lighting and phrasing | `smart_phrasing.py`, `smart_rearm.py`, `autoloop_controller.py`, `sound_switch_engine.py`, `beat_math.py` | Phrase intent, rearm timing, autoloop control, SoundSwitch fanout, beat math. |
| Laser output lane | `laser_director.py`, `laser_executor.py`, `laser_config.py`, `laser_models.py`, `laser_decision_log.py`, `personality_resolver.py` | Laser policy, MIDI execution, config validation, decision models/logs, personality selection. |
| Output transports | `osl_output.py`, `os2l_injector.py`, `midi_output.py` | OS2L/TCP, injector helpers, and MIDI transport. |
| Runtime ops | `runtime_status.py`, `validation_runner.py`, `logging_manager.py`, `diagnostics.py`, `bridge_fmt.py` | Status/command IO, health checks, logging controls, diagnostics, formatting. |
| Energy and spectral tools | `energy_model.py`, `audio_spectral_features.py`, `spectral_cache.py` | Offline and advisory energy/spectral analysis. |
| Session tooling | `session_recorder.py`, `session_replayer.py` | Recording and replaying bridge sessions. |

## Documentation Map

| Directory | Document type |
| --- | --- |
| `docs/architecture/` | Current authoritative architecture, design, invariants, and doc index. |
| `docs/plans/` | Active or deferred implementation plans and specs. |
| `docs/plans/completed/` | Completed implementation plans/specs retained as evidence. |
| `docs/prompts/active/` | Agent prompts that may be actionable after branch/file validation. |
| `docs/prompts/completed/` | Completed or superseded prompts retained as historical evidence. |
| `docs/prompts/reviews/` | Review prompts, audit prompts, and reviewer briefs. |
| `docs/guides/` | Operator workflows and setup guides. |
| `docs/research/` | Reverse-engineering notes, discovery notebooks, and research support. |
| `docs/subsystems/` | Per-subsystem supporting references. |
| `docs/validation/` | Validation evidence, runbooks, templates, and test corpora. |
| `docs/history/` | Historical rollout logs and archived plans. |
| `docs/data/` | Repo-local documentation data files such as extracted offsets. |

## Active Work

- `docs/plans/led_agent_orchestrator_workflow.md`
- `docs/plans/led_look_director_integration_plan_revised.md`
- `docs/plans/phase9_personality_resolver_plan.md`
- `docs/prompts/active/`

Validate branch, file paths, and current code before executing any plan or prompt. Historical prompts are evidence, not authority.

## Invariants For AI Agents

- `StateManager` is the only writer of `DeckState`.
- `StateManager` owns most `OutputState`; publish copies for readers.
- Runtime mutations should flow through `BridgeEvent`s.
- `BridgeEvent`s are immutable after creation.
- `RBStateReader._tick_deck()` must enqueue `ANLZ_PATH` before `TRACK_LOADED`.
- Direct flags alone must not bypass TL; direct readiness must be currently true.
- Memory play bits do not override `DeckState.playing`.
- The push loop must not perform blocking socket, MIDI, filesystem, network, or subprocess IO.
- Scripted/autoloop arms, clears, BPM, beat, elapsed, and beatpos sends must cover active, mirror, 3, and 4 as appropriate.
- Laser policy (`LaserDirector`) and laser MIDI execution (`LaserSceneExecutor`) are separate responsibilities.
- `GOVEE_API_KEY` and other secrets come from environment or local ignored config only, never committed.

## Common Commands

```bash
python -m unittest discover tests
python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q
node --check tools/laser_pad_assets/pad.js
```
