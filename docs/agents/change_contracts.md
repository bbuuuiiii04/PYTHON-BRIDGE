---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-only
---

# Change Contracts

This file tells future agents what must be inspected, tested, and documented when code changes. It is the anti-chaos layer for this repo. Apparently “remember to update docs” was not enough to save civilization.

Use this with `docs/agents/change_contracts.yml`, which is the machine-readable version checked by `tools/check_agent_contracts.py` and `tools/check_docs_drift.py`.

## Contract rule

Before editing code:

1. Find the matching contract.
2. Read the listed subsystem card and task playbook.
3. Inspect the listed code files.
4. Plan the docs/tests updates before touching code.

After editing code:

1. Run the listed tests/checks.
2. Update the listed docs.
3. Run doc drift checks.
4. State any uncertainty instead of overclaiming.

## Runtime command changes

Triggered by changes to:

- `runtime_status.py`
- command callback wiring in `__main__.py`
- status/command file paths
- validation runner command behavior

Inspect:

- `runtime_status.py`
- `__main__.py`
- `validation_runner.py`
- `docs/subsystems/runtime_commands.md`
- `docs/setup/runtime_commands.md`

Run:

```bash
python tools/check_docs_drift.py
python -m unittest discover tests
```

Update:

- `docs/setup/runtime_commands.md`
- `docs/subsystems/runtime_commands.md`
- `docs/status/feature_status_matrix.md` if behavior/status changed
- `docs/status/validation_matrix.md` if tests/evidence changed
- `docs/validation/software_test_inventory.md` if test coverage changed
- `docs/agents/task_playbooks/change_runtime_command.md` if workflow changed

Forbidden assumptions:

- Accepted parser command does not mean callback is wired.
- Callback wired does not prove hardware-visible behavior.
- A new command is not documented until both runtime command docs mention it.

## LED / Govee changes

Triggered by changes to:

- `led_config.py`
- `led_models.py`
- `led_look_director.py`
- `led_color_engine.py`
- `led_dispatch_coordinator.py`
- `govee_scene_adapter.py`
- `govee_runtime_sender.py`
- `govee_realtime_runner.py`
- `govee_realtime_transport.py`
- `govee_frame_renderer.py`
- `govee_owner_state.py`
- `beat_sync_engine.py`
- LED/Govee config examples

Inspect:

- `docs/subsystems/led_govee.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/validation/hardware_validation_log.md`

Run:

```bash
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
python -m unittest discover tests
```

Update:

- `docs/subsystems/led_govee.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md` only if compatibility evidence changed
- `docs/status/validation_matrix.md` if software tests changed
- `docs/validation/hardware_validation_log.md` only with real repeatable validation evidence
- `docs/status/active_work_registry.md` if unfinished LED work changed
- `docs/agents/task_playbooks/change_led_govee_behavior.md` if workflow changed

Forbidden assumptions:

- H612D behavior does not imply all Govee devices work.
- Realtime packet output does not prove visual smoothness.
- Software tests do not prove hardware compatibility.

## Laser changes

Triggered by changes to:

- `laser_config.py`
- `laser_models.py`
- `laser_director.py`
- `laser_executor.py`
- `midi_output.py`
- `personality_resolver.py`
- laser config examples
- Laser Pad docs/tooling

Inspect:

- `docs/subsystems/laser.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/validation/hardware_validation_log.md`

Run:

```bash
python -m unittest discover tests
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
```

Update:

- `docs/subsystems/laser.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md` only if fixture/interface evidence changed
- `docs/status/validation_matrix.md` if test coverage changed
- `docs/validation/hardware_validation_log.md` only with real repeatable validation evidence
- `docs/agents/task_playbooks/change_laser_behavior.md` if workflow changed

Forbidden assumptions:

- MIDI dry-run does not prove laser safety.
- A mapped scene does not imply arbitrary fixture support.
- Local fixture success does not prove broad laser compatibility.

## Rekordbox reader / offset changes

Triggered by changes to:

- `rb_memory.py`
- `rb_state_reader.py`
- `live_bpm.py`
- `rb_offsets.py`
- offset data files
- Rekordbox path/version assumptions

Inspect:

- `docs/subsystems/rekordbox_readers.md`
- `docs/status/support_matrix.md`
- `docs/status/known_limitations.md`
- `docs/validation/software_test_inventory.md`

Run:

```bash
python -m unittest discover tests
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
```

Update:

- `docs/subsystems/rekordbox_readers.md`
- `docs/status/support_matrix.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/validation/software_test_inventory.md`
- `docs/agents/task_playbooks/change_rekordbox_reader.md` if workflow changed

Forbidden assumptions:

- One Rekordbox version does not imply another version works.
- macOS Mach reader logic does not imply Windows/Linux support.
- Offset discovery success must be documented with version evidence before support claims change.

## SoundSwitch output changes

Triggered by changes to:

- `osl_output.py`
- `sound_switch_engine.py`
- `os2l_injector.py`
- SoundSwitch catalog/import/UI code if present

Inspect:

- `docs/subsystems/soundswitch_output.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`

Run:

```bash
python -m unittest discover tests
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
```

Update:

- `docs/subsystems/soundswitch_output.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md` only with version/interface evidence
- `docs/status/validation_matrix.md` if tests/evidence changed

Forbidden assumptions:

- OS2L message generation does not prove every SoundSwitch version works.
- Catalog/import/UI documents are uncertain unless verified against current code.

## Config schema changes

Triggered by changes to:

- `config.py`
- `laser_config.py`
- `led_config.py`
- `config/*.example.json`
- env flag semantics

Inspect:

- `docs/subsystems/config.md`
- `docs/setup/configuration.md`
- relevant subsystem card
- relevant config example

Run:

```bash
python -m unittest discover tests
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
```

Update:

- `docs/subsystems/config.md`
- `docs/setup/configuration.md`
- relevant subsystem card
- `docs/status/feature_status_matrix.md` if behavior changed
- `docs/agents/task_playbooks/update_config_schema.md`

Forbidden assumptions:

- Do not change local ignored config semantics casually.
- Do not commit secrets, API keys, local IPs, or local backup files.

## Test additions or changes

Triggered by changes under:

- `tests/`
- test fixtures
- test commands

Inspect:

- `docs/subsystems/tests.md`
- `docs/validation/software_test_inventory.md`
- `docs/status/validation_matrix.md`

Run:

```bash
python -m unittest discover tests
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
```

Update:

- `docs/subsystems/tests.md`
- `docs/validation/software_test_inventory.md`
- `docs/status/validation_matrix.md`
- relevant subsystem card

Forbidden assumptions:

- Do not modify tests just to make unrelated docs pass.
- Passing software tests does not prove hardware behavior.

## Documentation/status changes

Triggered by changes to:

- `README.md`
- `AGENTS.md`
- `docs/**`
- `.github/**`
- doc validation tools

Inspect:

- `docs/architecture/doc_index.md`
- `docs/architecture/doc_index.md`
- `docs/architecture/doc_index.md`
- `docs/agents/drift_detection.md`

Run:

```bash
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
python tools/check_docs_drift.py
```

Update:

- `docs/architecture/doc_index.md`
- `docs/architecture/doc_index.md`
- affected docs' metadata headers
- `docs/status/active_work_registry.md` if unfinished work changed

Forbidden assumptions:

- Do not make alpha software look mature.
- Do not convert old prompts/plans into current truth without code verification.
- Do not claim hardware validation without validation log evidence.
