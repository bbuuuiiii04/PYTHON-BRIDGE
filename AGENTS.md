# AGENTS.md — rb_ss_bridge_v2

**This file is the single entrypoint for every AI coding agent. Read it fully, then read only what your task needs.**

This repo is an **extreme early-alpha** Python bridge that reads Rekordbox / DJ runtime state and drives lighting (SoundSwitch via OS2L, MIDI lasers, LEDs, Govee). It is coded almost entirely by AI agents.

Accepted repo status — do not upgrade without code/test/config + validation evidence:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

It works in the maintainer's local macOS setup only. It is **not** production-ready, show-ready, plug-and-play, broadly compatible, generally supported, or hardware-validated.

---

## 0. Communication Mode

The maintainer is the project owner/operator, not a software engineer. Agents should communicate in a low-noise, natural, and concrete way that helps direct engineering work on a live-performance bridge safely.

*If a local, gitignored file named `PRIVATE_OPERATOR_PROFILE.md` exists in the repo root, read it for operator communication preferences before starting work.*

### Core communication rules

* **Talk like a human, not a dashboard.**
* **No robotic `STATUS: GREEN/YELLOW/RED` blocks** for routine updates.
* **No giant walls of text** and **no narration of every internal step.**
* **Stay quiet** during routine reading, editing, or test reruns unless something meaningful changes.
* Provide **short natural updates** only when something meaningful changes (risks, blockers, completed checkpoints).
* Explain the **plain-language meaning** before technical labels.
* Define technical terms only when they matter.
* **Explain like the maintainer is five.** Plain, conversational English only — no engineering jargon (banned examples: "blast radius", "load-bearing", "seams"). But do **not** dumb it down to nothing: he still needs to understand **how** something works and **why** it works that way. Skip the jargon, keep the mechanism.
* **No vague questions** like "How would you like to proceed?"
* **No "looks good," "done," "fixed," or "robust"** without evidence.
* **No raw diffs** unless explicitly requested.
* **No implementation** before validating the current repo state.
* **Code/tests beat docs** when they conflict.

### Proof and decisions

* **Important claims need proof**, but proof should be written naturally in the text, not as formal proof-card templates unless explicitly requested in that format.
* **Pause for real decisions only**: behavior changes, architecture changes, live-safety risk, code/docs conflict, multiple valid paths, or validation risk. Do not ask for approval on routine mechanical edits.

### Git workflow

* Work directly on `main`. Do not create feature, topic, review, temporary, agent, or worktree branches unless the user explicitly authorizes one in the current request.
* Do not create additional worktrees when they would create or require another branch. If a tool requires a branch or pull request, explain the conflict instead of creating one silently.
* Before deleting an existing branch, prove its unique work is represented in `main`.
* Never run `git clean -fd` here: multi-GB gitignored capture corpora (e.g. `tools/ssfmt/captures/`) were already lost to it once.

### Examples

**Good example style:**
"I checked the repo state. We're on the right branch, and there's one existing `AGENTS.md` change I'm not touching. I'm moving into the requested docs edit now."

**Good example style:**
"I found the test failure. The runtime behavior looks consistent with the spec; the old harness is missing the new wiring. I'm patching the harness, not production behavior."

**Bad example style:**
`STATUS: YELLOW`
`Plain meaning: ...`
`Risk: ...`
`Next: ...`

## 1. Source-of-truth order (use every time)

1. Executable code (`*.py`)
2. Tests (`tests/`)
3. Config examples (`config/*.example.json`)
4. Runtime command parser + status surfaces (`runtime_status.py`)
5. Current file tree
6. Docs — **only after** verifying against code
7. Old prompts / plans / history / reports — **historical evidence only**

If a doc conflicts with code, **code wins**. If you cannot verify a claim, **mark it uncertain** — do not guess. If you change behavior without updating the docs named by its change contract, you created drift.

## 2. Token budget — pick the smallest reading path

Do **not** read the whole repo. Do **not** start with old prompts/plans/history.

| Task size | Read |
|---|---|
| **Small** (typo, one command doc, one subsystem doc, narrow review) | this file → 1 subsystem card → exact files it names |
| **Medium** (one subsystem behavior change, config/runtime-command change, targeted tests) | this file → `docs/agents/change_contracts.yml` → 1 task playbook → 1 subsystem card → named code + tests → named docs to update |
| **Large** (crosses runtime ownership / threading / multiple subsystems) | this file → `docs/architecture/current_architecture.md` → `docs/architecture/runtime_invariants.md` → relevant subsystem cards → code directly |

If the task is still unclear after the path above, **stop and report uncertainty.** Do not spelunk old prompts to invent context.

If `graphify-out/graph.json` exists and the task needs broad codebase orientation, `graphify query`,
`graphify explain`, or `graphify path` can point at likely files before opening many files. Skip
Graphify for exact symbol, line, or known-file lookups where `rg` is cheaper and narrower. Never
report Graphify output as confirmed architecture, ownership, call flow, blast radius, or live
behavior: the graph is a lead only. `INFERRED` / `AMBIGUOUS` edges and shortest paths require
source/test confirmation, especially before any live-critical claim. Do not use or document
`graphify plan` unless the current local CLI proves that command exists.

## 3. Task router

| Task | Playbook | Subsystem card | Contract key |
|---|---|---|---|
| Runtime command change | `docs/agents/task_playbooks/change_runtime_command.md` | `docs/subsystems/runtime_commands.md` | `runtime_commands` |
| LED / Govee behavior | `docs/agents/task_playbooks/change_led_govee_behavior.md` | `docs/subsystems/led_govee.md` | `led_govee` |
| Laser behavior | `docs/agents/task_playbooks/change_laser_behavior.md` | `docs/subsystems/laser.md` | `laser` |
| Rekordbox reader / offsets | `docs/agents/task_playbooks/change_rekordbox_reader.md` | `docs/subsystems/rekordbox_readers.md` | `rekordbox_readers` |
| SoundSwitch output | — | `docs/subsystems/soundswitch_output.md` | `soundswitch_output` |
| Config schema | `docs/agents/task_playbooks/update_config_schema.md` | `docs/subsystems/config.md` | `config_schema` |
| Add tests | `docs/agents/task_playbooks/add_tests.md` | `docs/subsystems/tests.md` | `tests` |
| Docs-only work | `docs/agents/task_playbooks/update_docs.md` | `docs/architecture/doc_index.md` | `docs` |
| Review agent changes | `docs/agents/task_playbooks/review_agent_changes.md` | `docs/agents/change_contracts.md` | — |

Human + machine change contracts: `docs/agents/change_contracts.md` and `docs/agents/change_contracts.yml`. Drift detection: `docs/agents/drift_detection.md`.

Prompt/spec authoring — one repo skill per target agent (Claude autoloads them; Codex reads them as standalone documents from these paths):
- Fable 5 prompt → `.claude/skills/fable-prompt-writer/SKILL.md` (hardest / most ambiguous / long-horizon / safety-sensitive reasoning, planning, and review one-shots).
- Opus 4.8 prompt → `.claude/skills/opus-prompt-writer/SKILL.md` (default Claude coding / agentic / knowledge / frontend / code-review work).
- Codex implementation/review spec → `.claude/skills/codex-spec/SKILL.md` (the spec Codex executes on bridge code; Part A–E format + pre-handoff checklist).
- Template Lab prompt → `.claude/skills/template-lab/SKILL.md` (Template Lab design/spec handoffs).

Per-model drop-in blocks live under `docs/prompts/snippets/`. Rules across the suite: Fable/Opus reason, plan, audit, and review; Codex implements bridge code. Prompt-generation/spec-only tasks default to no tools, no shell, no broad repo search, no accidental skill invocation, and no implementation unless the generated prompt states the exact allowed access and why.

Multi-agent work (any model family): `docs/agents/multi_agent_org_workflow.md` is the canonical org doctrine — executive → manager → orchestrator → implementer seats, dispatch/watch tooling (`tools/agents/`), review-chain and suite-baseline discipline, seat handoffs. Build-lane seats (Opus, GPT, any mid-tier model) additionally follow `docs/agents/opus_seat_harness.md`. Resuming the program cold: newest `docs/agents/codex_resume_state_*.md`.

## 4. Source map (modules are intentionally flat at repo root)

| Area | Files | Card |
|---|---|---|
| Runtime coordinator | `__main__.py`, `state_manager.py`, `active_deck_resolver.py`, `models.py`, `config.py` | `docs/subsystems/core_bridge.md` |
| Runtime status / commands | `runtime_status.py`, `validation_runner.py`, `diagnostics.py`, `bridge_fmt.py` | `docs/subsystems/runtime_commands.md` |
| Logging (event stream + viewer) | `bridge_log.py`, `bridge_view.py`, `scripts/ss_bridge_watcher.sh` (monitor window) | `docs/subsystems/logging.md` |
| Rekordbox direct readers | `rb_state_reader.py`, `rb_memory.py`, `rb_offsets.py`, `live_bpm.py`, `probe_live_bpm.py`, `probe_deck2.py`, `mtc_reader.py` | `docs/subsystems/rekordbox_readers.md` |
| Track metadata | `filepath_resolver.py`, `anlz_reader.py`, `scripted_tracks.py`, `ss_library_scanner.py` | — |
| Phrasing / autoloop / beat / spectral analysis | `smart_phrasing.py`, `smart_rearm.py`, `autoloop_controller.py`, `drop_lifecycle.py`, `beat_math.py`, `audio_spectral_features.py`, `spectral_cache.py`, `spectral_profile.py`, `section_energy_v0.py` (AWR-288 energy E2 per-section grades; runtime-imported by state_manager on the ANLZ worker, status-only, `RBSS_SECTION_ENERGY` default-off) | spectral v4: `docs/research/spectral_audio_analysis_redesign.md` |
| SoundSwitch output | `osl_output.py`, `sound_switch_engine.py`, `os2l_injector.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py` | `docs/subsystems/soundswitch_output.md` |
| SoundSwitch pack player / exporter | `soundswitch_pack*.py`, `soundswitch_project_decoder.py`, `soundswitch_parity_registry.py`, `soundswitch_scripted_resolution.py`, `soundswitch_static_assertions.py`, `soundswitch_frame_sender.py`, `soundswitch_midi_input.py`, `native_autoloop_resolver.py` (offline U0 oracle now lives at `tools/ssfmt/soundswitch_parity_oracle.py`, no runtime importers) | `docs/subsystems/soundswitch_output.md` |
| Offline analysis tooling (no runtime importers) | `energy_model.py`, `tools/analyze_anlz_energy_corpus.py`, `tools/spectral_sweep.py`, `tools/spectral_stick_sweep.py`, `tools/spectral_calibration_report.py`, `tools/spectral_ear_benchmark.py` (AWR-200 Stage-1 ear benchmark + AWR-205 offline gold-label intake: `--emit-gold-template` / `--gold`, read-only), `hardness_v0.py` + `tools/hardness_ablation.py` (AWR-203 offline intrinsic-hardness shadow + read-only ablation; zero runtime importers), `approach_features_v0.py` (AWR-204 offline raw four-view approach descriptors; zero runtime importers, no tool), `track_weight_v0.py` + `tools/track_weight_report.py` (AWR-286 energy E1 offline library track-weight descriptor + read-only corpus report/sidecar-store tool; gain-invariant by loudness_ref_db-relative construction; zero runtime importers) | `docs/research/anlz_energy_project.md`, `docs/research/spectral_audio_analysis_redesign.md`, `docs/research/spectral_calibration_expansion_2026_07_08.md`, `docs/plans/active/spectral_ear_benchmark_spec_2026_07_10.md` |
| DMX / laser output backends | `enttec_dmx_pro.py`, `laser_output_backend.py`, `artnet_truth.py` (validation tap) | `docs/subsystems/laser.md` |
| Laser | `laser_director.py`, `laser_executor.py`, `laser_config.py`, `laser_models.py`, `laser_decision_log.py`, `personality_resolver.py`, `midi_output.py` | `docs/subsystems/laser.md` |
| LED / Govee | `led_config.py`, `led_models.py`, `led_look_director.py`, `led_color_engine.py`, `led_dispatch_policy.py`, `led_dispatch_coordinator.py`, `govee_scene_adapter.py`, `govee_runtime_sender.py`, `govee_realtime_runner.py`, `govee_realtime_transport.py`, `govee_frame_renderer.py`, `govee_owner_state.py`, `govee_lan_discovery.py`, `beat_sync_engine.py`, `led_pad_controls.py` (LED/Laser Pad web tools live in `tools/`) | `docs/subsystems/led_govee.md` |
| Config | `config.py`, `laser_config.py`, `led_config.py`, `config/*.example.json` | `docs/subsystems/config.md` |
| Session tooling | `session_recorder.py`, `session_replayer.py`, `session_phase_trace.py` | — |
| Stream Deck controller | `streamdeck/` | `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` |
| Operator scripts | `scripts/` (menubar, pads, watcher, session recorder entry points) | — |
| Tests | `tests/` | `docs/subsystems/tests.md` |

Entrypoint: `python3 -m rb_ss_bridge_v2` (package name `rb_ss_bridge_v2`). Do not move modules to "fix" imports; use this map.

## 5. Architecture (authoritative detail — verify against code)

| Doc | Use |
|---|---|
| `docs/architecture/current_architecture.md` | compact current system overview |
| `docs/architecture/runtime_invariants.md` | rules extracted from code/tests |
| `docs/architecture/bridge_design.md` | detailed design anchor |
| `docs/architecture/laser_director_design.md` | canonical Laser Director design |
| `docs/architecture/doc_index.md` | **the single classification index for every doc** |

Agent-facing summaries live in the subsystem cards; the four docs above are the deeper authority.

## 6. Invariants agents must not break (verified at the current HEAD)

- `StateManager` (`state_manager.py`) is the central runtime owner and the only writer of `DeckState`; it owns the **200 Hz push loop** (`_TICK_INTERVAL = 1.0/200`).
- Runtime mutations flow through `BridgeEvent`s (`models.py`); events are treated as immutable after creation. Reader threads publish events/snapshots, never mutate `DeckState` directly.
- `RBStateReader._tick_deck()` must enqueue `ANLZ_PATH` **before** `TRACK_LOADED` (`rb_state_reader.py`).
- The push loop must **not** gain blocking network, socket, MIDI, filesystem, or subprocess I/O.
- Memory play bits do not override `DeckState.playing`; direct flags alone must not bypass TL — direct readiness must be currently true.
- Scripted/autoloop arms, clears, BPM, beat, elapsed, and beatpos sends must cover decks active, mirror, 3, and 4 as appropriate.
- Held SoundSwitch Static Override is a manual overlay, not an automatic base: with healthy input it can stand alone over idle/cleared scripted-autoloop selection, releases on the next healthy empty-layer snapshot, and loses to blackout/emergency masks and pack-disabled/shutdown zeroing.
- Laser **policy** (`LaserDirector`) and laser MIDI **execution** (`LaserSceneExecutor`) are separate responsibilities.
- Secrets (e.g. `GOVEE_API_KEY`), local IPs, device IDs, live config, and backup files must never be committed. Never commit `config/led_look_director.json.backup_1781599611`.
- Docs-only work must not change runtime behavior. Old prompts/plans are never current truth without code verification.

## 7. The non-negotiable anti-drift rule

**Before** changing code: find its contract in `docs/agents/change_contracts.yml`.
**After** changing code: update **every** doc that contract lists under `docs_update`, and run the checks below.
If the change has no matching contract, **add/extend the contract first**, then edit code.

## 8. Checks before committing docs- or agent-routing changes

```bash
python3 tools/check_docs_metadata.py     # required docs + status headers exist
python3 tools/check_agent_contracts.py   # routing/cards/contracts reference real files & symbols
python3 tools/check_docs_drift.py        # runtime command surface & status strings match code
python3 tools/check_ui_jargon.py         # LED pad/lab/sim UI copy stays musician-legible (AWR-264)
python3 tools/check_docs_staleness.py --report   # advisory: impl changed since docs were verified
```

The first four are hard checks (CI fails on them). Staleness is advisory — when it flags a
contract, re-verify the listed docs against code and bump `last_verified_commit`.

Optional local gate (runs the hard checks before every commit): `git config core.hooksPath tools/git-hooks`
(skip once with `git commit --no-verify`; disable with `git config --unset core.hooksPath`).

Run software tests when practical (some need optional deps; none prove hardware):

```bash
python3 -m unittest discover tests
```

Do **not** modify tests to make docs pass.

## 9. Do not trust blindly (evidence, not authority)

`docs/prompts/**`, `docs/plans/**`, `docs/history/**`, `docs/archive/**`, any doc without a current status header, and any doc claiming "complete / ready / supported" without matching status-matrix evidence. A doc is **active** only if it is listed in `docs/status/active_work_registry.md` **and** verified against current code.

## 10. Status language

Allowed: `implemented`, `software-tested`, `local-setup-operational`, `hardware-unvalidated`, `experimental`, `partial`, `planned`, `unsupported`, `unknown`, `stale/superseded`.

Forbidden unless validation matrices prove them: `stable`, `production-ready`, `show-ready`, `plug-and-play`, `broadly compatible`, `generally supported`, `hardware-validated`.
