---
doc_status: current
truth_level: code-verified
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
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
- Runtime status heartbeat changes need `tests/test_runtime_status.py` coverage for payload shape,
  log formatting, throttling seam, StateManager-published color status, and fail-soft provider behavior.
- Logging visibility changes need `tests/test_bridge_fmt_rate.py` for spam-control primitives and
  `tests/test_logging_diag_coverage.py` for diagnostic coverage and the live-watch preset.
- Config schema changes need validation tests.
- LED/Govee rendering changes need deterministic renderer/runner tests where practical.
- Laser changes need config/executor/director tests.
- `tests/test_soundswitch_project_decoder.py` covers the strict decoder/frozen models. `tests/test_soundswitch_pack.py` covers deterministic export, the canonical 95-artifact pack, independent verification, exact 232+1/32/42/45 inventory, the seven-class F-3 crosswalk, byte-identical repeat export, and mutation rejection. The current-project proof is 29 PASS / 0 FAIL / 0 INCOMPLETE with F9 and F10 passing. Config/startup/controller/commands, StateManager driver, player, MIDI input, frame sender, Enttec, shadow, and T7d tooling have focused suites. The 2026-06-23 audit ran 310 focused tests and the full 2256-test suite successfully. These remain software/wire tests; they do not prove physical fixtures or close the scripted pause/mode/input-health gaps listed in the active roadmap.

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
