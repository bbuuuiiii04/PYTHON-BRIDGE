---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 9ed183f
last_verified_date: 2026-06-18
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

## M2.5 LED slot-color workstream test files

| File | Covers | Added in |
|---|---|---|
| tests/test_led_color_engine_m2_phase1.py | Phase 2a/b engine cues, renderer byte-identity, resolve_slot_colors | Phase 1 |
| tests/test_led_color_engine_m2_patch_b.py | rt_groove_chase slotization | Patch B |
| tests/test_led_color_engine_m2_patch_c.py | rt_post_drop_chase slotization | Patch C |
| tests/test_led_color_engine_m2_patch_d.py | rt_drop_chase, rt_drop_center_burst slotization | Patch D |
| tests/test_led_color_engine_m2_patch_e1.py | rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula slot fns plus rt_drop_nebula pairing | Patch E1 |
| tests/test_led_color_engine_m2_patch_e2.py | rt_post_drop_center_comet slot fn, rt_drop_center_burst pairing, legacy center-comet regression, solid slot-color selection for slot cues | Patch E2 |
| tests/test_led_color_engine_m2_patch_e3.py | rt_twinkle slot fn, generic ambient config, legacy twinkle_blue regression, solid slot-color selection for rt_twinkle | Patch E3 |
| tests/test_led_color_engine_m2_patch_s.py | random_with_mono_chance mono hit/miss behavior, chance 0 equality with random_with_replacement, determinism, stepping, fade tail, journey RNG isolation, allowlist regression | Patch S |

All M2.5 slot cue and strategy tests: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
