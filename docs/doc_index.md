# Documentation Index

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-05-09. Classification is based on
code verification, not document age or detail level.

| File | Classification | Why |
| --- | --- | --- |
| `README.md` | CURRENT AUTHORITATIVE | New repo entry point; points to the current docs path and launcher defaults verified in watcher scripts. |
| `docs/current_architecture.md` | CURRENT AUTHORITATIVE | Compact current architecture derived from `__main__.py`, `StateManager`, readers, resolver, output, status, and launcher scripts. |
| `docs/bridge_design.md` | CURRENT AUTHORITATIVE | Detailed current design anchor. Major claims were checked against runtime wiring and supporting code. |
| `docs/runtime_invariants.md` | CURRENT AUTHORITATIVE | Extracted invariants from current code paths and tests. |
| `docs/laser_director_design.md` | PROPOSED FEATURE DESIGN | Canonical Laser Director implementation spec; not current runtime behavior until implemented. |
| `docs/laser_director_midi_mapping_workflow.md` | PROPOSED FEATURE / OPERATOR SETUP NOTES | SoundSwitch MIDI mapping workflow and operator setup guidance for Laser Director. |
| `docs/doc_index.md` | CURRENT AUTHORITATIVE | Maintains the current classification table. |
| `docs/subsystems/logging.md` | CURRENT SUPPORTING | Runtime logging controls still match `logging_manager.py` and `__main__.py`; supporting detail rather than architecture source. |
| `docs/validation/direct_master_runtime_validation.md` | VALIDATION EVIDENCE | Correctly describes bounded direct-master observer as shadow-only while noting B6 authority is separate. |
| `docs/validation/direct_master_runtime_runbook.md` | VALIDATION EVIDENCE | Live evidence capture workflow; its sample command is not the full launcher-default authority set. |
| `docs/validation/direct_master_runtime_results_template.md` | VALIDATION EVIDENCE | Template for observer results, not behavior documentation. |
| `docs/validation/live_bpm_findings.md` | VALIDATION EVIDENCE | Historical/live probe evidence; useful for validation semantics and session-local address warnings. |
| `docs/validation/autoloop_beatphase_findings.md` | VALIDATION EVIDENCE | SoundSwitch activation and beatphase evidence. It informs current autoloop design but is not the main design source. |
| `docs/history/tl_retirement_process_log.md` | HISTORICAL / ROLLOUT LOG | Valuable chronology of B1-B6 promotion and validation. Current state must be checked against code. |
| `docs/history/timecodelink_integration_analysis.md` | HISTORICAL / ROLLOUT LOG | Reverse-engineering evidence for TL internals and offsets; not current bridge behavior. |
| `docs/history/code_update_tracker.md` | HISTORICAL / ROLLOUT LOG | Review/approval tracker with historical rules and change notes, not current architecture. |
| `docs/history/dashboard_plan.md` | HISTORICAL / ROLLOUT LOG | Planning/implemented-slice note for operator dashboard; current status code is authoritative. |
| `docs/history/logging_implementation_handoff.md` | DUPLICATIVE / SHOULD BE MERGED | Overlaps with `docs/subsystems/logging.md`; retained as implementation handoff history. |
| `docs/history/live_bpm_handoff.md` | HISTORICAL / ROLLOUT LOG | Handoff with useful evidence pointers; current live BPM behavior belongs in current architecture/design docs. |
| `docs/history/live_bpm_v2_plan.md` | STALE / SHOULD BE ARCHIVED | Older live-BPM rearm design record with fields that no longer match current `OutputState`; retained for context. |
| `docs/history/codex_smart_drop_and_phrase_anchor.md` | STALE / SHOULD BE ARCHIVED | Implementation prompt with superseded Phrase Anchor and default-off wording; banner already warned it is historical. |
| `docs/history/smart_drop_phase2_handoff.md` | HISTORICAL / ROLLOUT LOG | Local Phase 2 handoff and validation evidence; current behavior is now summarized in `bridge_design.md`. |
| `.pytest_cache/README.md` | STALE / SHOULD BE ARCHIVED | Generated pytest cache note; not project documentation and excluded from the developer reading path. |

## Main Path For New Developers

Read in this order:

1. `README.md`
2. `docs/current_architecture.md`
3. `docs/runtime_invariants.md`
4. `docs/bridge_design.md`

Only then open `docs/validation/` for evidence or `docs/history/` for rollout
context.
