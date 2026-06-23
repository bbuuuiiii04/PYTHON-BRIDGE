---
doc_status: current
truth_level: code-verified
last_verified_commit: 87f3e5e
last_verified_date: 2026-06-23
validation_scope: software-only
---

# Active Work Registry

This is the single repo-facing place for unfinished work. Old prompts and plans are not active unless listed here.

## Active engineering work

Each item points at an on-disk spec. **A spec is a plan, not proof of implementation — verify against current code before acting.**

| ID | Area | Spec | Verify |
| --- | --- | --- | --- |
| AWR-101 | LED color engine M2.5 (slotize hardcoded Frame cues + random_with_replacement fill) | `docs/plans/active/led_color_engine_m2_5_spec.md` | partial; A-D plus Patch E1 nebula, Patch E2 center-comet, Patch E3 ambient twinkle slot cues, and Patch F tracked-example bank cleanup are software-tested in current worktree; runtime behavior still needs operator hardware sign-off |
| AWR-102 | LED color engine core (decoupled color, drift + drop-snap) | `docs/plans/active/led_color_engine_spec.md` | confirm which milestones are landed in `led_color_engine.py` |
| AWR-103 | Realtime comet stutter / smoothness / pause | `docs/plans/active/rt_comet_stutter_fix_spec.md`, `rt_comet_smoothness_fix_spec.md`, `rt_comet_pause_continuation_spec.md` | confirm landed vs pending in `govee_realtime_*`/`beat_sync_engine.py` |
| AWR-104 | Beat-sync runtime | `docs/plans/active/beat_sync_runtime_spec.md` | confirm against `beat_sync_engine.py` |
| AWR-105 | LED role mapping v2 | `docs/plans/active/led_role_mapping_v2_spec.md` | scripted groove/drop/post-drop blackout remap is implemented and software-tested in current worktree; broader role-mapping-v2 scope still needs verification against `led_look_director.py`/`led_models.py` |
| AWR-106 | LED color engine M2.5 solid-color strategy + Patch F cleanup | `docs/plans/active/led_color_engine_solid_color_and_patch_f_spec.md` | Patch S `random_with_mono_chance` and Patch F tracked-example bank cleanup are implemented and software-tested only; live-config mirror remains operator-gated; all hardware behavior remains unvalidated |
| AWR-107 | SoundSwitch static exporter / bridge-native player | `docs/research/soundswitch/README.md` (directory authority), `docs/research/soundswitch/soundswitch_re_closure_report.md` (RE verdict), `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` (implementation spec), `docs/plans/active/soundswitch_impl_progress.md` (active resume ledger) | Tasks 0–2 are complete through deterministic export of an independently verified canonical 95-artifact pack for the pinned SoundSwitch 2.10.3 canonical RAVE project. Exact inventory is 232 render + 1 catalog-tail cues, 32 Static Looks, 42 autoloops, and 45 scripted records; seven-class F-3 crosswalk and F9 mutation rejection pass. Proof: 28 PASS / 0 FAIL / 1 INCOMPLETE, foundation 27/27 PASS; only F10 is deferred to Task 4. Task 3 loader/player and Task 4+ MIDI/runtime/backend/config/commands/`StateManager`/Enttec/hardware work remain planned. No runtime, restart, MIDI/DMX, Enttec, or hardware action is authorized; software/wire-validated only, hardware-unvalidated. |

## Documentation system follow-ups

| ID | Area | Status | Next action |
| --- | --- | --- | --- |
| AWR-001 | Old-doc classification + archive pass | mostly done | Done in this refactor (`docs/architecture/doc_index.md` classifies all docs; completed prompts/plans moved to `docs/archive/`). Remaining: verify M2 prompts in `docs/prompts/active/` and archive the completed ones. |
| AWR-002 | Untracked govee spec | open | Classify `docs/plans/completed/govee_realtime_codex_spec.md` (completed vs awaiting-build) and commit or archive it in a separate change. |
| AWR-003 | Stray root output files | open | Relocate tracked `cues_output.md` / `cues_timing_output.md` to `docs/data/` or gitignore. |
| AWR-004 | First agent-workflow dry run | active | Seeded with `docs/agents/operator_workflow.md` and `docs/agents/skills/*.md`; next real feature branch should use intake → implementation → adversarial review → repair/handoff and record missing routes, unclear contracts, or token-waste points. |
| AWR-005 | Runtime command test inventory | active | Map parser/handler tests and add missing ones only in a separate code/test PR. |
| AWR-006 | Contract coverage audit | active | After a feature PR, tighten `docs/agents/change_contracts.yml` around any files agents had to rediscover. |

## Future roadmap

| ID | Area | Goal |
| --- | --- | --- |
| ROAD-001 | Rekordbox compatibility | Validate and document supported/unsupported versions with evidence. |
| ROAD-002 | OS compatibility | Decide whether non-macOS support is out of scope or requires new reader architecture. |
| ROAD-003 | Hardware validation | Create repeatable validation logs for SoundSwitch, laser, and Govee paths. |
| ROAD-004 | Usability | Improve local setup, config UX, status/debug visibility, and operator workflows. |

## Ideas / experiments

| ID | Idea | Promotion criteria |
| --- | --- | --- |
| IDEA-001 | Broader Govee device support | Device-specific tests, config examples, and validation logs. |
| IDEA-002 | More lighting outputs | Explicit subsystem design and software tests before support claims. |
| IDEA-003 | Deeper docs drift checking | Add code-aware checks only when they are cheap, deterministic, and not dependent on local hardware. |

## Deprecated plans

Deprecated plans belong in `docs/architecture/doc_index.md` or `docs/archive/` with reasons. They must not be revived without code verification.

## Hardware validation tasks

| ID | Device/path | Required proof | Status |
| --- | --- | --- | --- |
| HW-001 | SoundSwitch OS2L local setup | version, interface, track, expected behavior, result, date | not logged |
| HW-002 | Laser MIDI path | fixture/mapping, blackout behavior, manual override, safety notes | not logged |
| HW-003 | Govee realtime path | device model, firmware/app assumptions, effect, expected behavior, result | not logged |

## Compatibility expansion tasks

| ID | Target | Required proof | Status |
| --- | --- | --- | --- |
| COMP-001 | Rekordbox versions beyond my current setup | reader/offset validation plus tests/logs | unknown |
| COMP-002 | macOS versions beyond my current setup | launch/read/status validation | unknown |
| COMP-003 | Windows/Linux | architecture decision, not docs optimism | unsupported/unknown |
