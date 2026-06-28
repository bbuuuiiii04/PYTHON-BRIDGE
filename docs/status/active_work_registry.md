---
doc_status: current
truth_level: code-verified
last_verified_commit: c14bff1
last_verified_date: 2026-06-28
validation_scope: software-only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-output unvalidated
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
| AWR-107 | SoundSwitch static exporter / bridge-native player | `docs/plans/active/soundswitch_exporter_remaining_work.md` (single current status/roadmap), `docs/plans/active/soundswitch_README.md` (project index), `docs/research/soundswitch/README.md` (RE routing), `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` (capture blocker), `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md` (only active SoundSwitch execution prompt), `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` (reusable review-only handoff), `docs/validation/soundswitch_hardware_validation_procedure.md` and `soundswitch_hardware_runs/TEMPLATE.md` (non-Autoloop operator gate) | Current project proof is 29 PASS / 0 FAIL / 0 INCOMPLETE and 32/32 active scripted tracks are exportable. RW-1 through RW-5, graceful shutdown ownership, the copied menubar status, the connection auto-switch (`set_soundswitch_pack action=enable`, with one bounded `pack_start_failed` retry and no manual pack button), the SoundSwitch-saved Static Override Press/Toggle interaction mode, the repo-local ignored pack path `local/soundswitch/rbss_canonical_pack`, required binding-sidecar stage-before-swap publication, and the non-Autoloop procedure/template are implemented and software-tested. The latest independent software/wire review found no blocker/high issues; one medium menubar parser mismatch was fixed. Material specs are historical under `docs/plans/completed/soundswitch/`. No operator hardware evidence run exists. T7d still lacks four scenario pairs, identity/holdout reconciliation, and a unique oracle; native Autoloop DMX remains unimplemented and software-zero. No live config, restart, runtime command, device, output, or hardware action is authorized. SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-108 | Laser drop/post-drop lifecycle mirror | `docs/plans/active/chorus_drop_cycling_spec.md` | Tasks 1-5 and Part D are implemented and software-tested at `9918dd4` and `ed78263`. Live LED behavior is unchanged. Laser hardware/SoundSwitch observation and kill-switch rehearsal remain pending; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-109 | Stream Deck MIDI controller / layered static-look compositor | `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` (Phase 1 implemented; Part F Phase 2 spec), `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` (implementation handoff), `docs/plans/active/streamdeck_phase2_plan_review.md` and `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` (review evidence) | Phase 1 controller lifecycle hardening is implemented in current `main`. Phase 2 is a revised implementation plan only: generic layered DMX compositor, lock-free hot-path snapshots, worker-thread input-port-gone recovery, pure render path, sibling binding sidecar, and local controller LED state. No bridge restart, controller smoke, Enttec/DMX, fixture, or live hardware action is authorized. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-110 | Rekordbox mixer active-deck authority | `docs/architecture/active_deck_authority.md` (operator-authoritative target behavior), `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` (Ghidra/Ghidra-MCP RE + implementation handoff), `docs/research/rekordbox_mixer_active_deck_re_evidence.md` (current RE proof), `docs/prompts/active/rekordbox_mixer_active_deck_re_continuation_prompt.md` (remaining RE continuation handoff), `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` (adversarial RE review handoff) | Planned runtime implementation. Current code still treats Rekordbox master/playing-only mirror switching as active-deck authority. Target behavior redefines `active_deck` as the playing audible show deck selected by Deck 1/2 upfader and bass EQ, with `rb_master_deck` retained separately for tie/fallback. Static Ghidra headless decompilation plus operator-approved passive process-memory proof confirms the local Rekordbox 7.2.11 Deck 1/2 upfader chains, LOW/BASS EQ chains, Deck 1/2 channel ownership, and EQ band 2 = LOW/BASS. Required implementation guardrails now call out named mixer offset parser fields/tests and a mixer-specific finite-f32 reader because the existing live-BPM float helper rejects valid mixer values. Filter, Deck 1 intermediate/audible fader symmetry, version/relaunch stability, play/stop/master-change survival, fail-closed runtime validity, and resolver thresholds remain unimplemented/unproven. GhidraMCP was unavailable in the RE pass. No bridge restart, additional live capture, process-memory sampling, or hardware action is authorized by the spec alone. |

## Documentation system follow-ups

| ID | Area | Status | Next action |
| --- | --- | --- | --- |
| AWR-001 | Old-doc classification + archive pass | mostly done | Done in this refactor (`docs/architecture/doc_index.md` classifies all docs; completed prompts/plans moved to `docs/archive/`). Remaining: verify M2 prompts in `docs/prompts/active/` and archive the completed ones. |
| AWR-002 | Untracked govee spec | open | Classify `docs/plans/completed/govee_realtime_codex_spec.md` (completed vs awaiting-build) and commit or archive it in a separate change. |
| AWR-003 | Stray root output files | open | Relocate tracked `cues_output.md` / `cues_timing_output.md` to `docs/data/` or gitignore. |
| AWR-004 | First agent-workflow dry run | active | Use this system on the next real feature change on `main`; record missing routes, unclear contracts, token-waste points, or hidden branch-state risks. |
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
| HW-001 | SoundSwitch OS2L/local direct-DMX setup | version, interface, track, expected behavior, result, date | reviewed procedure/template exist; no run logged |
| HW-002 | Laser MIDI path | fixture/mapping, blackout behavior, manual override, safety notes | not logged |
| HW-003 | Govee realtime path | device model, firmware/app assumptions, effect, expected behavior, result | not logged |

## Compatibility expansion tasks

| ID | Target | Required proof | Status |
| --- | --- | --- | --- |
| COMP-001 | Rekordbox versions beyond my current setup | reader/offset validation plus tests/logs | unknown |
| COMP-002 | macOS versions beyond my current setup | launch/read/status validation | unknown |
| COMP-003 | Windows/Linux | architecture decision, not docs optimism | unsupported/unknown |
