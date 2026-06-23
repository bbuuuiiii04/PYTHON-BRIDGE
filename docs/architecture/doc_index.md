---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: bc9f7f4
last_verified_date: 2026-06-22
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---

# Documentation Index

**The single classification index for every doc in this repo.** Code remains the
source of truth when documents conflict. A doc is *active* only if it is listed in
`docs/status/active_work_registry.md` **and** verified against current code.

## Legend

| Type | Meaning |
| --- | --- |
| CURRENT AUTHORITATIVE | Primary truth for current behavior or workflow. Still loses to code. |
| CURRENT SUPPORTING | Useful current detail; verify against code before relying. |
| PLAN / SPEC (ACTIVE) | Active or deferred plan. **Validate against code before executing.** |
| AGENT PROMPT (ACTIVE) | Prompt text. Validate branch/files/status before use. May already be done. |
| REVIEW / AUDIT | Review brief or reviewer handoff. Evidence, not authority. |
| RESEARCH | Reverse-engineering / discovery notes. |
| VALIDATION EVIDENCE | Test evidence, runbook, template, corpus. |
| ARCHIVE / HISTORICAL | Completed or superseded. **Evidence only**, never current truth. |
| GENERATED OUTPUT | Tool-generated; not part of the doc reading path. |

## Current authoritative — start here

| File | Type |
| --- | --- |
| `AGENTS.md` | CURRENT AUTHORITATIVE — single AI-agent entrypoint (router, source map, invariants, token budget). |
| `README.md` | CURRENT AUTHORITATIVE — public/GitHub truth and project boundary. |
| `docs/architecture/current_architecture.md` | CURRENT AUTHORITATIVE — compact system overview. |
| `docs/architecture/runtime_invariants.md` | CURRENT AUTHORITATIVE — invariants from code/tests. |
| `docs/architecture/bridge_design.md` | CURRENT AUTHORITATIVE — detailed design anchor. |
| `docs/architecture/laser_director_design.md` | CURRENT AUTHORITATIVE — Laser Director design. |
| `docs/architecture/doc_index.md` | CURRENT AUTHORITATIVE — this index. |

## Agent operating system — current

| Area | Files | Type |
| --- | --- | --- |
| Change contracts | `docs/agents/change_contracts.md`, `docs/agents/change_contracts.yml` | CURRENT AUTHORITATIVE — what must update when code changes; enforced by checkers. |
| Drift detection | `docs/agents/drift_detection.md` | CURRENT AUTHORITATIVE. |
| Task playbooks | `docs/agents/task_playbooks/*.md` (8) | CURRENT AUTHORITATIVE — per-task reading routes. |
| Subsystem cards | `docs/subsystems/{core_bridge,rekordbox_readers,soundswitch_output,laser,led_govee,runtime_commands,config,tests}.md` | CURRENT — compact, code-verified cards. |
| Status / truth | `docs/status/*.md` (7) | CURRENT — project status, feature/support/validation matrices, known limitations, active work. |
| Setup / usage | `docs/setup/*.md` (4) | CURRENT. |
| Validation policy | `docs/validation/{validation_policy,software_test_inventory,hardware_validation_log}.md` | CURRENT. |
| Archive banner | `docs/archive/README.md` | CURRENT. |

## Current supporting — verify before relying

| File | Type |
| --- | --- |
| `docs/govee_realtime_design.md` | CURRENT SUPPORTING — Govee realtime design (referenced by `current_architecture.md`). |
| `docs/led_look_director_design.md` | CURRENT SUPPORTING — LED Look Director design. |
| `docs/led_look_mapping_workflow.md` | CURRENT SUPPORTING — operator mapping workflow. |
| `docs/govee_capability_notes.md` | CURRENT SUPPORTING — Govee device capability notes. |
| `docs/guides/*.md` (4) | CURRENT SUPPORTING — laser MIDI mapping, rollout checklist, Laser Pad. |
| `docs/subsystems/logging.md` | CURRENT SUPPORTING — matches `logging_manager.py`. |
| `docs/data/offsets-*.yaml` (3) | CURRENT SUPPORTING — Rekordbox offset reference data. |
| `docs/research/*.md` | RESEARCH — ANLZ energy and waveform-tag evidence. |
| `docs/research/soundswitch/*.md` | SOUNDSWITCH RE AUTHORITY — current closure report, format/binary findings, evidence matrices, tool guide, and product contract. Start with `README.md`. |
| `docs/research/soundswitch/history/*.md` | SOUNDSWITCH RE HISTORY — superseded handoffs, intermediate findings, and draft exporter/player specs. Historical provenance only. |
| `docs/validation/anlz_energy_corpus_report.md`, `anlz_energy_evaluation_guide.md`, `autoloop_beatphase_findings.md`, `smart_drop_synthetic_corpus.yaml` | VALIDATION EVIDENCE. |

## Active plans & prompts — VALIDATE against code before executing

Active only if also listed in `docs/status/active_work_registry.md`. Confirm each against current `main` before acting.

| Zone | Type | Notes |
| --- | --- | --- |
| `docs/plans/active/led_color_engine_spec.md` | PLAN / SPEC (ACTIVE) | LED color engine build contract (spec §15). |
| `docs/plans/active/led_color_engine_m2_5_spec.md` | PLAN / SPEC (ACTIVE) | M2.5 (slotize Frame cues + fill); spec'd, **not implemented**. |
| `docs/plans/active/beat_sync_runtime_spec.md` | PLAN / SPEC (ACTIVE) | Beat-sync runtime. |
| `docs/plans/active/led_role_mapping_v2_spec.md` | PLAN / SPEC (ACTIVE) | Verify status against code. |
| `docs/plans/active/rt_comet_*.md` (3) | PLAN / SPEC (ACTIVE) | Realtime comet stutter/smoothness/pause work; verify which are landed. |
| `docs/plans/active/soundswitch_README.md` | ACTIVE PROJECT INDEX | Grouped routing for the SoundSwitch exporter/bridge-native DMX project. |
| `docs/plans/active/soundswitch_exporter_remaining_work.md` | ACTIVE CHECKLIST / ROADMAP | Current landed-versus-remaining authority. Covers one-click export/publish/reload, scripted runtime closure, T7d, hardware gating, dependencies, invariants, and completion criteria. |
| `docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md` | ACTIVE CONTRACT POINTER | Symlink to the original product/implementation contract. Read the active remaining-work roadmap for current status. |
| `docs/plans/active/soundswitch_t7c_pack_driver_spec.md` | COMPATIBILITY POINTER | Preserves code/test links to the completed T7c spec; current status is in the SoundSwitch remaining-work roadmap. |
| `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` | PLAN / SPEC (ACTIVE) | Current six-scenario T7d blocker plan: prove ticks/beat plus arm/refire/master/drop/buildup/correction origin rules from operator-owned captures. It selects no phase mapping and grants no runtime/hardware authorization. |
| `docs/prompts/active/soundswitch_rw1_export_from_ss_design_prompt.md` | AGENT PROMPT (ACTIVE) | Opus design/spec prompt for one-click canonical export, safe replacement, menubar execution, and explicit reload acknowledgement. No implementation/live authority. |
| `docs/plans/completed/soundswitch/*.md` | COMPLETED / SUPERSEDED PLANNING | Material T7/T8 implementation specs/proofs and the old progress ledger. Redundant prompts/handoffs were deleted. Historical evidence only. |
| `docs/plans/led_agent_orchestrator_workflow.md`, `led_look_director_integration_plan_revised.md`, `phase9_personality_resolver_plan.md` | PLAN / SPEC (ACTIVE) | Validate line refs before implementation. |
| `docs/prompts/active/*.md` | AGENT PROMPT (ACTIVE) | Active prompts only; SoundSwitch has the RW-1 design prompt and the operator-presence T7d resume handoff. Obsolete SoundSwitch prompts were deleted. |
| `docs/plans/completed/govee_realtime_codex_spec.md` | PLAN / SPEC | **Untracked local file** — classify (completed vs awaiting-build) and commit or archive separately. |

## Archive / historical — evidence only

| Zone | Type | Notes |
| --- | --- | --- |
| `docs/archive/prompts/*.md` (7) | ARCHIVE | Completed/superseded agent prompts. |
| `docs/archive/plans/*.md` (2) | ARCHIVE | Completed autoloop spec + plan. |
| `docs/prompts/reviews/*.md` (4) | REVIEW / AUDIT | Past review briefs; kept in place (a runtime comment in `anlz_reader.py` references `drop_detection_review_v2.md`). |
| `docs/history/*.md` + `docs/history/archive/*.md` (5) | ARCHIVE / HISTORICAL | Rollout logs; kept in place (referenced by `current_architecture.md`, `subsystems/logging.md`, and a test name). |
| `cues_output.md`, `cues_timing_output.md` (repo root) | GENERATED OUTPUT | Tool output; relocate to `docs/data/` or gitignore. |

## Main reading order

1. `AGENTS.md`
2. `docs/architecture/current_architecture.md`
3. `docs/architecture/runtime_invariants.md`
4. `docs/architecture/bridge_design.md`
5. this index

Then open `docs/validation/` for evidence, `docs/archive/` only for history.

## Maintenance rule

When code changes, update the docs named by the matching contract in
`docs/agents/change_contracts.yml`, then run the three `tools/check_docs_*.py`
checkers. When a doc's status changes (e.g. a plan completes), reclassify it here
and move completed prompts/plans into `docs/archive/`.
