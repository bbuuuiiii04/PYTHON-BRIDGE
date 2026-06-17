---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Software Test Inventory

This inventory routes agents to tests without pretending software tests validate physical lighting hardware.

## Broad command

```bash
python -m unittest discover tests
```

If using pytest-specific tests or fixtures:

```bash
python -m pytest tests
```

## Subsystem routing

| Area | What to look for in `tests/` | Notes |
| --- | --- | --- |
| Core bridge | state manager, models, smart phrasing, integration tests | verifies software behavior only |
| Runtime commands | parser/handler/status writer tests | needed before command changes |
| Rekordbox readers | reader, offset, live BPM tests | cannot prove all app versions |
| SoundSwitch | OS2L/output helper tests | cannot prove all SoundSwitch versions |
| Laser | laser config/director/executor/MIDI dry-run tests | cannot prove physical safety |
| LED/Govee | LED config/director/color/realtime/renderer tests | cannot prove device compatibility |
| Replay/session tooling | replay format and smoke tests | software-only |
| Frontend tools | syntax and smoke tests | does not prove live safety |
| Docs/agent workflow | docs metadata, agent contract, and drift checkers | docs-only validation |

## Required documentation update

When adding or changing tests, update:

- `docs/status/validation_matrix.md`
- `docs/subsystems/tests.md`
- relevant subsystem card
- relevant task playbook if test workflow changed

Hardware behavior still needs manual validation logs.
