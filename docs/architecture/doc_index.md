---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: f6910f9
last_verified_date: 2026-06-24
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
| `AGENTS.md` | CURRENT AUTHORITATIVE — single AI-agent entrypoint (communication, main-only Git workflow, router, source map, invariants, token budget). |
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
| Validation policy | `docs/validation/{validation_policy,software_test_inventory,hardware_validation_log,soundswitch_hardware_validation_procedure}.md`, `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | CURRENT — SoundSwitch procedure/template are operator gates, not completed hardware evidence. |
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
| `docs/plans/active/soundswitch_exporter_remaining_work.md` | ACTIVE CHECKLIST / ROADMAP | Current landed-versus-remaining authority. RW-1 through RW-5 are implemented/software-tested; T7d, native Autoloop DMX, a real hardware run, and final closeout remain. |
| `docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md` | ACTIVE CONTRACT POINTER | Symlink to the original product/implementation contract. Read the active remaining-work roadmap for current status. |
| `docs/plans/active/soundswitch_t7c_pack_driver_spec.md` | COMPATIBILITY POINTER | Preserves code/test links to the completed T7c spec; current status is in the SoundSwitch remaining-work roadmap. |
| `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` | PLAN / SPEC (ACTIVE) | Current six-scenario T7d blocker plan: prove ticks/beat plus arm/refire/master/drop/buildup/correction origin rules from operator-owned captures. It selects no phase mapping and grants no runtime/hardware authorization. |
| `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md` | AGENT PROMPT (ACTIVE) | Only active SoundSwitch execution prompt; operator-conducted T7d evidence collection with no pack/hardware enablement authority. |
| `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` | REVIEW PROMPT (ACTIVE) | Commit-scoped independent ChatGPT review of RW-5, the non-Autoloop procedure/template, and SoundSwitch document lifecycle. Review-only. |
| `docs/plans/completed/soundswitch/*.md` | COMPLETED / SUPERSEDED PLANNING | Material RW-1 through RW-5, hardware-procedure, T7/T8 specs/proofs, and the old progress ledger. Historical evidence only. |
| `docs/plans/active/soundswitch_roadmap_registry_reconciliation_spec.md` | UNROUTED / EXCLUDED SPEC | Explicitly outside the current implementation pass and not active because the registry does not list it. Do not execute it without fresh operator scope. |
| `docs/plans/led_agent_orchestrator_workflow.md`, `led_look_director_integration_plan_revised.md`, `phase9_personality_resolver_plan.md` | PLAN / SPEC (ACTIVE) | Validate line refs before implementation. |
| `docs/prompts/active/*.md` | AGENT PROMPT (ACTIVE) | Active prompts only; SoundSwitch has one operator-presence T7d capture prompt. Obsolete SoundSwitch prompts were deleted. |
| `docs/plans/completed/govee_realtime_codex_spec.md` | PLAN / SPEC | **Untracked local file** — classify (completed vs awaiting-build) and commit or archive separately. |

## Archive / historical — evidence only

| Zone | Type | Notes |
| --- | --- | --- |
| `docs/archive/prompts/*.md` (7) | ARCHIVE | Completed/superseded agent prompts. |
| `docs/archive/plans/*.md` (2) | ARCHIVE | Completed autoloop spec + plan. |
| `docs/prompts/reviews/*.md` | REVIEW / AUDIT | Current review handoffs plus non-SoundSwitch historical review briefs retained where code references them. Completed SoundSwitch review prompts were deleted; Git history preserves them. |
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
checkers. When a doc's status changes, reclassify it here, retain material
implementation specs under `docs/plans/completed/`, and delete redundant prompts
whose only remaining value is already preserved in Git history.
