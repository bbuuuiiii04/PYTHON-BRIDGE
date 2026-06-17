# rb_ss_bridge_v2

**Status: extreme early alpha.**

This is my Python bridge for reading Rekordbox / DJ runtime state and driving lighting systems such as SoundSwitch, MIDI-controlled lasers, LEDs, and Govee-style realtime lighting.

It works in my current local setup, but the repo must not be read as production-ready, show-ready, plug-and-play, broadly compatible, generally supported, or hardware-validated. The accepted public repo status is:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

That means local operation exists, but the repository does not yet contain enough repeatable hardware-validation evidence to claim broad hardware support. Tiny wording difference, enormous future-debugging difference. Software loves punishing optimism.

## Fast path for AI agents

AI coding agents must start with:

1. `AGENTS.md` — single entrypoint: router, source map, invariants, and the token budget.
2. `docs/agents/change_contracts.yml` — what must update when code changes.
3. The relevant task playbook in `docs/agents/task_playbooks/`
4. The relevant subsystem card in `docs/subsystems/`

Do **not** start by reading every historical prompt, old plan, or rollout note. That is how token budgets go to die in a ditch.

## What this project does right now

At a high level, the bridge:

1. Reads Rekordbox state from guarded local runtime sources.
2. Uses a central `StateManager` event loop to own bridge state.
3. Sends VirtualDJ-shaped OS2L messages to SoundSwitch.
4. Supports optional laser policy and MIDI execution.
5. Supports optional LED / Govee look selection, cloud scene dispatch, and realtime frame output.
6. Writes local runtime status and accepts local JSONL runtime commands.

## Current known working scope

The current real scope is my local macOS setup. Anything outside that should be treated as unvalidated until it is entered in the support and validation matrices.

| Area | Current public status |
| --- | --- |
| Project maturity | Extreme early alpha |
| Primary OS | macOS local setup only |
| Rekordbox support | Current local setup only; other versions unvalidated |
| SoundSwitch output | Implemented through OS2L path |
| Laser output | Implemented through config-driven policy plus MIDI execution |
| LED / Govee output | Implemented paths exist, including Govee cloud and realtime modules |
| Hardware validation | Not documented as repeatable repo evidence |
| General compatibility | Not claimed |

## What not to assume

Do not assume:

- another Rekordbox version works
- another operating system works
- another Govee device works
- another laser fixture works
- another SoundSwitch version works
- another machine can clone and run this without local setup work
- tests prove live hardware behavior
- old prompts or plans describe current behavior

## Start here

Read these in order:

1. `AGENTS.md` - source-of-truth rules and AI-agent workflow.
2. `docs/architecture/current_architecture.md` - human/system overview.
3. `docs/status/project_status.md` - current project truth.
4. `docs/status/feature_status_matrix.md` - implemented, partial, experimental, planned, unknown.
5. `docs/status/support_matrix.md` - Rekordbox, OS, lighting, and hardware support boundaries.
6. `docs/status/validation_matrix.md` - software validation versus hardware validation.
7. `docs/agents/change_contracts.md` - what must update when code changes.
8. `docs/agents/task_playbooks/` - task-specific reading routes.
9. `docs/subsystems/` - concise subsystem cards.
10. `docs/architecture/doc_index.md` - which docs are current, supporting, active, or archived.

## Development install

From the repository root:

```bash
pip install -e ".[dev]"
```

Run the software tests:

```bash
python -m unittest discover tests
```

Some tests may require optional dependencies. Hardware behavior is not proven by these tests.

## Runtime entrypoint

From an editable install or configured local environment:

```bash
python -m rb_ss_bridge_v2
```

Runtime status is written to:

```text
/tmp/rb_ss_bridge_v2_status.json
```

Runtime commands are read from:

```text
/tmp/rb_ss_bridge_v2_commands.jsonl
```

See `docs/setup/runtime_commands.md` and `docs/subsystems/runtime_commands.md` for the command surface.

## Documentation and drift checks

Run these before committing docs or agent-routing changes:

```bash
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
python tools/check_docs_drift.py
```

These checks are lightweight. They do not replace tests or hardware validation, because apparently reality still requires being tested in reality.

## Repository map

| Area | Location |
| --- | --- |
| Current project status | `docs/status/` |
| Architecture | `docs/architecture/` |
| AI-agent workflow | `AGENTS.md`, `docs/agents/` |
| Task playbooks | `docs/agents/task_playbooks/` |
| Change contracts | `docs/agents/change_contracts.md`, `docs/agents/change_contracts.yml` |
| Setup and usage | `docs/setup/` |
| Subsystem navigation | `docs/subsystems/` |
| Validation | `docs/validation/` |
| Active unfinished work | `docs/status/active_work_registry.md` |
| Historical docs | `docs/archive/` and existing classified historical docs |

## Safety note

This project can drive lights, lasers, and network-connected devices. The repo documentation must stay conservative. If a feature is not validated in current repo evidence, it must be labeled unvalidated, unknown, experimental, partial, planned, or unsupported. Optimism is not a test result.
