---
doc_status: current
truth_level: code-verified
last_verified_commit: 51367a1
last_verified_date: 2026-06-18
validation_scope: software-only
---

# Tests

Status:
- implementation: partial
- software-tested: partial
- hardware-validated: no
- compatibility: local test environment only

Purpose:
- Route agents to relevant tests without making them inspect the entire suite first.

Authoritative locations:
- `tests/`
- `requirements-dev.txt`
- `pyproject.toml`

Common commands:
- `python -m unittest discover tests`
- `python -m pytest tests/test_laser_config.py tests/test_laser_executor.py -q` when pytest is available and relevant
- `node --check tools/laser_pad_assets/pad.js` when touching Laser Pad frontend assets

Coverage expectations:
- Core/state changes need state manager or integration tests.
- Runtime command changes need parser/handler tests.
- Config schema changes need validation tests.
- LED/Govee rendering changes need deterministic renderer/runner tests where practical.
- Laser changes need config/executor/director tests.

Change contract:
- Do not modify tests just to make docs changes pass.
- If tests cannot run due local environment or optional dependencies, report that explicitly.
- Hardware behavior requires validation logs/checklists, not only unit tests.

M2.5 LED slot-color workstream adds patch-specific tests through `tests/test_led_color_engine_m2_patch_f.py`.
Focused M2.5 subsets should include the color config test, `tests/test_led_color_engine.py`, the phase tests, and every existing `tests/test_led_color_engine_m2_patch_*.py` file.

Known risks:
- tests proving software behavior but not actual hardware behavior
- optional pytest/unittest mismatch
- local dependency gaps
