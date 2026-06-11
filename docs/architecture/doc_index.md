# Documentation Index

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-06-11. Classification is based on
current file layout, code organization, and document purpose. Code remains the
source of truth when documents conflict.

## Document Type Legend

| Type | Meaning |
| --- | --- |
| CURRENT AUTHORITATIVE | Primary documentation for current behavior or contribution workflow. |
| CURRENT SUPPORTING | Current, useful supporting detail that is not the main architecture source. |
| PLAN / SPEC | Active or deferred implementation planning material. Validate against code before execution. |
| COMPLETED PLAN / SPEC | Completed implementation planning material retained as evidence, not active work. |
| AGENT PROMPT | Prompt text for Codex, Composer, Claude, or reviewers. Validate branch and file paths before use. |
| REVIEW / AUDIT | Review brief, audit prompt, or reviewer handoff. |
| RESEARCH | Reverse-engineering, discovery, or exploratory notes. |
| VALIDATION EVIDENCE | Test evidence, runbook, template, or corpus support. |
| HISTORICAL / ROLLOUT LOG | Chronology and rollout evidence. Useful context, not current authority. |
| ARCHIVED STALE HISTORY | Superseded plan retained for evidence only. |
| GENERATED CACHE | Tool-generated file outside the project documentation path. |

## Current Entry Points

| File | Classification | Why |
| --- | --- | --- |
| `AGENTS.md` | CURRENT AUTHORITATIVE | AI agent orientation, source map, docs map, invariants, and common commands. |
| `README.md` | CURRENT AUTHORITATIVE | Human repo entry point; points to `AGENTS.md` and the current architecture path. |
| `docs/architecture/current_architecture.md` | CURRENT AUTHORITATIVE | Compact current architecture derived from startup wiring, `StateManager`, readers, resolver, output, status, and launcher scripts. |
| `docs/architecture/runtime_invariants.md` | CURRENT AUTHORITATIVE | Extracted invariants from current code paths and tests. |
| `docs/architecture/bridge_design.md` | CURRENT AUTHORITATIVE | Detailed current design anchor. Major claims were checked against runtime wiring and supporting code. |
| `docs/architecture/laser_director_design.md` | CURRENT AUTHORITATIVE | Canonical Laser Director design reference for `laser_director.py`, `laser_executor.py`, and `laser_models.py`. |
| `docs/architecture/doc_index.md` | CURRENT AUTHORITATIVE | Maintains this classification table and reading order. |

## Plans And Specs

| File | Classification | Why |
| --- | --- | --- |
| `docs/plans/led_agent_orchestrator_workflow.md` | PLAN / SPEC | Automation controller for the LED Look Director work; controls phase order, gates, and prompt execution. |
| `docs/plans/led_look_director_integration_plan_revised.md` | PLAN / SPEC | Required LED Look Director architecture/design reference paired with the orchestrator. |
| `docs/plans/phase9_personality_resolver_plan.md` | PLAN / SPEC | Deferred/revised personality resolver plan. Validate line references before implementation. |
| `docs/plans/completed/ultimate_autoloop_intelligence_plan.md` | COMPLETED PLAN / SPEC | Completed section-correct autoloop planning document retained as implementation evidence. |
| `docs/plans/completed/autoloop_codex_spec.md` | COMPLETED PLAN / SPEC | Completed implementation spec plus audit context for section-correct autoloop selection. |

## Agent Prompts

| File | Classification | Why |
| --- | --- | --- |
| `docs/prompts/active/codex_ss_catalog_handoff.md` | AGENT PROMPT | SoundSwitch catalog handoff prompt retained from the former root `prompts/` directory; validate current API paths before use. |
| `docs/prompts/completed/anchored_tuner_codex_prompt.md` | AGENT PROMPT | Completed/superseded Codex prompt retained as evidence. |
| `docs/prompts/completed/autoloop_composer_prompt.md` | AGENT PROMPT | Completed Composer implementation prompt for the autoloop spec. |
| `docs/prompts/completed/codex-laser-pad-ux-refactor.md` | AGENT PROMPT | Completed/stale Laser Pad UI refactor prompt for the old `Laser-Pad-UX` branch. |
| `docs/prompts/completed/codex_smart_drop_and_phrase_anchor.md` | AGENT PROMPT | Superseded implementation prompt moved from history archive to the completed prompt archive. |
| `docs/prompts/completed/laser_drop_mode_hold_rotated_codex_prompt.md` | AGENT PROMPT | Completed/superseded laser prompt retained as evidence. |
| `docs/prompts/completed/laser_drop_rotation_seed_codex_prompt.md` | AGENT PROMPT | Completed/superseded laser prompt retained as evidence. |
| `docs/prompts/completed/laser_verify_deterministic_cursor_codex_prompt.md` | AGENT PROMPT | Completed/superseded laser verification prompt retained as evidence. |
| `docs/prompts/reviews/autoloop_fable_audit.md` | REVIEW / AUDIT | Pre-implementation audit prompt for the section-correct autoloop work. |
| `docs/prompts/reviews/drop_detection_review_brief.md` | REVIEW / AUDIT | Original drop-detection review brief and problem statement. |
| `docs/prompts/reviews/drop_detection_review_v2.md` | REVIEW / AUDIT | Drop-detection review document and failure framing. |
| `docs/prompts/reviews/pr88_review_prompt.md` | REVIEW / AUDIT | PR 88 review prompt. |

## Guides And Supporting References

| File | Classification | Why |
| --- | --- | --- |
| `docs/guides/laser_director_midi_mapping_workflow.md` | CURRENT SUPPORTING | SoundSwitch MIDI mapping workflow and operator setup guidance for Laser Director. |
| `docs/guides/laser_director_rollout_checklist.md` | CURRENT SUPPORTING | Rollout and validation checklist for safe Laser Director enablement and rollback. |
| `docs/guides/laser_pad.md` | CURRENT SUPPORTING | Browser-based Laser Pad workflow, API surface, and operator caveats. |
| `docs/guides/laser_pad_parity.md` | CURRENT SUPPORTING | Parity note confirming Laser Pad owns retired terminal mapper actions. |
| `docs/subsystems/logging.md` | CURRENT SUPPORTING | Runtime logging controls that match `logging_manager.py` and `__main__.py`. |

## Research

| File | Classification | Why |
| --- | --- | --- |
| `docs/research/anlz_energy_project.md` | RESEARCH | Bridge-local ANLZ energy tooling overview, labels, limits, and validation framing. |
| `docs/research/anlz_waveform_tag_inventory.md` | RESEARCH | Read-only ANLZ tag inventory focused on waveform, beatgrid, and phrase tags. |
| `docs/research/ss_memory_discovery.md` | RESEARCH | SoundSwitch memory discovery notebook and future-offset notes. |

## Validation

| File | Classification | Why |
| --- | --- | --- |
| `docs/validation/anlz_energy_evaluation_guide.md` | VALIDATION EVIDENCE | Practical operator workflow for validating ANLZ energy tooling on a small corpus. |
| `docs/validation/anlz_energy_corpus_report.md` | VALIDATION EVIDENCE | Report template and JSONL schema for offline ANLZ energy corpus runs. |
| `docs/validation/autoloop_beatphase_findings.md` | VALIDATION EVIDENCE | SoundSwitch activation and beatphase evidence supporting autoloop design. |

## History

| File | Classification | Why |
| --- | --- | --- |
| `docs/history/dashboard_plan.md` | HISTORICAL / ROLLOUT LOG | Planning/implemented-slice note for operator dashboard; status code is authoritative. |
| `docs/history/logging_implementation_handoff.md` | HISTORICAL / ROLLOUT LOG | Historical logging handoff. Current guidance is in `docs/subsystems/logging.md`. |
| `docs/history/pssi_mood23_up_mapping_spike_2026-05-10.md` | HISTORICAL / ROLLOUT LOG | Historical PSSI/mood mapping investigation. |
| `docs/history/smart_drop_phase2_handoff.md` | HISTORICAL / ROLLOUT LOG | Local Phase 2 handoff and validation evidence; current behavior is summarized in `docs/architecture/bridge_design.md`. |
| `docs/history/archive/live_bpm_v2_plan.md` | ARCHIVED STALE HISTORY | Older live-BPM rearm design record with fields that no longer match current `OutputState`. |
| `.pytest_cache/README.md` | GENERATED CACHE | Generated pytest cache note; excluded from the developer reading path. |

## Data Files

| File | Classification | Why |
| --- | --- | --- |
| `docs/data/offsets-macos.yaml` | CURRENT SUPPORTING | Rekordbox offset data retained as repo-local reference data. |
| `docs/data/offsets-macos-x86_64.yaml` | CURRENT SUPPORTING | Comparative x86_64 Rekordbox offset data. |
| `docs/data/offsets-windows.yaml` | CURRENT SUPPORTING | Comparative Windows Rekordbox offset data. |

## Main Path For New Developers

Read in this order:

1. `README.md`
2. `AGENTS.md`
3. `docs/architecture/current_architecture.md`
4. `docs/architecture/runtime_invariants.md`
5. `docs/architecture/bridge_design.md`
6. `docs/architecture/doc_index.md`

Only then open `docs/validation/` for evidence or `docs/history/` for rollout
context.
