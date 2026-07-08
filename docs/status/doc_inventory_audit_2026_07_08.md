---
doc_status: completed-investigation
truth_level: code-verified
last_verified_commit: d31c290
last_verified_date: 2026-07-08
validation_scope: Read-only per-file placement inventory of all 293 Markdown docs under docs/ at HEAD d31c290; buckets A/B/C/D from doc_status-vs-folder plus reconciliation against docs/status/active_work_registry.md and docs/architecture/doc_index.md; four docs checkers run (3 hard PASS, staleness advisory). Content-staleness is advisory only. Proposes moves; moves nothing.
---

# Docs Inventory & Placement Audit - 2026-07-08

> **UPDATE 2026-07-08 (post-audit, operator-directed):** all 30 Bucket-B moves plus the Bucket-D
> Phase-9 archive were **executed** via `git mv` (history preserved). `docs/prompts/` root now holds
> only `README.md`; `docs/plans/` root is empty of loose files. Stale path references in the registry,
> `doc_index.md`, and 6 other docs were updated; the 3 hard doc checkers pass. The tables below are the
> pre-move audit snapshot — the "correct folder" column is where each file now lives.

Total docs under `docs/`: **293** (213 with `doc_status:` header, 80 without).

**Bucket counts (sum = 293):** A (active, correctly placed) = **178** | B (misfiled) = **30** | C (inactive, correctly placed) = **84** | D (ambiguous / operator decision) = **1**.

Buckets: **A** authoritative/active work in the right folder. **B** inactive/spent/superseded sitting in the wrong folder (needs a move). **C** completed/archived/historical where the folder itself is the status (no move; `docs/plans/completed/**`, `docs/prompts/completed/`, `docs/archive/**`, `docs/history/**`, `docs/research/soundswitch/history/`). **D** cannot be resolved without an operator or code decision.

Column notes: `folder-implied` = what the doc's location says its status should be. Missing `doc_status:` on a doc that is otherwise correctly placed is an *advisory* metadata nit, not a misfile.

## Bucket B - MISFILED (needs a move)

| path | doc_status | folder-implied | correct folder (if move) | confidence | note |
|---|---|---|---|---|---|
| `docs/plans/active/led_pad_color_immediacy_spec.md` | superseded | active | docs/plans/completed/ | confirmed | doc_status: superseded; AWR-134 superseded by AWR-137 |
| `docs/prompts/cross_platform_portability_fable_review.md` | current | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/cross_platform_portability_plan_opus.md` | current | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/drop_dark_rootcause_opus.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/fable_creative_lead_crowd_experience_brainstorm.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/fable_led_laser_drop_debug.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/fable_lighting_engine_v2_design_review.md` | NO-HEADER | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/fable_lighting_engine_v2_expansion.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/fable_lighting_engine_v2_strict_review.md` | NO-HEADER | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/fable_lighting_v2_f2_drop_choreography.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/fable_p5_led_dispatch_extraction.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/fable_self_learning_workflow_prompt.md` | current | loose-prompt(root) | docs/prompts/active/ | confirmed | AWR-127 names it companion to OPEN Phase-2 work |
| `docs/prompts/fable_spectral_audio_redesign.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/fable_spectral_palettes_arrival_crossfade_exploration.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/gemini_lighting_color_research.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/gemini_lighting_color_research_round2.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/gemini_lighting_color_research_round3.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/gemini_lighting_color_research_round4.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/govee_led_audit_redesign_fable_prompt.md` | current | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/laser_color_tuning_opus.md` | NO-HEADER | loose-prompt(root) | docs/prompts/active/ | confirmed | Ongoing laser-color tuning (AWR-111 chart still operator-pending) |
| `docs/prompts/laser_led_diagnosis_opus.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/laser_mute_wiring_investigation_opus.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | assumed | Spent one-shot prompt; driven work landed |
| `docs/prompts/led_subsystem_deep_diagnosis_fable.md` | current | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/lighting_engine_v2_fable_prompt.md` | current | loose-prompt(root) | docs/prompts/active/ | confirmed | Standing owner of v2 F1->F4 build-out (F2-F4 open) |
| `docs/prompts/lighting_v1_foundation_audit_opus_prompt.md` | current | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/live_run_20260706_eve_fable_orchestration.md` | current | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/logging_overhaul_fable_design_prompt.md` | NO-HEADER | loose-prompt(root) | docs/prompts/completed/ | confirmed | Spent one-shot; driven work landed |
| `docs/prompts/logging_ux_fix_review_fable_prompt.md` | NO-HEADER | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/usb_bridge_launcher_fable_review.md` | current | loose-prompt(root) | docs/prompts/reviews/ | confirmed | Review/audit brief — belongs with review handoffs |
| `docs/prompts/usb_launcher_design_changes_handoff.md` | current | loose-prompt(root) | docs/prompts/active/ | assumed | AWR-122 pickup handoff for open (parked) M1 spec |

## Bucket D - AMBIGUOUS (operator/code decision)

| path | doc_status | folder-implied | correct folder (if move) | confidence | note |
|---|---|---|---|---|---|
| `docs/plans/phase9_personality_resolver_plan.md` | NO-HEADER | loose-plan(root) | docs/archive/plans/  OR  new AWR | unknown | doc_index: DORMANT, not registry-listed, 'revive or archive - operator decision pending' |

## Bucket A - ACTIVE & CORRECTLY PLACED

| path | doc_status | folder-implied | correct folder (if move) | confidence | note |
|---|---|---|---|---|---|
| `docs/agents/change_contracts.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/drift_detection.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/README.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/awr-ids-grep-before-assign.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/checker-glob-blindspots.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/index-labels-need-grep-gates.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/prompts-live-in-the-repo.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/registry-rows-are-indexes.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/stop-hook-autosync-races-agents.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/lessons/tmux-tui-submit-separately.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/add_tests.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/change_laser_behavior.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/change_led_govee_behavior.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/change_rekordbox_reader.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/change_runtime_command.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/review_agent_changes.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/update_config_schema.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/agents/task_playbooks/update_docs.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/active_deck_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/bridge_design.md` | NO-HEADER | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/current_architecture.md` | NO-HEADER | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/doc_index.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/drop_presentation_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/laser_blackout_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/laser_color_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/laser_director_design.md` | NO-HEADER | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/led_pad_template_lab_design.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/lighting_engine_v2_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/logging_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/native_autoloop_pack_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/palette_control_authority.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/architecture/runtime_invariants.md` | NO-HEADER | authoritative | - | confirmed | Status matches folder |
| `docs/archive/README.md` | current | archive->inactive | - | confirmed | Current archive banner (doc_index CURRENT) |
| `docs/data/cues_output.md` | NO-HEADER | reference/generated | - | confirmed | Status matches folder |
| `docs/data/cues_timing_output.md` | NO-HEADER | reference/generated | - | confirmed | Status matches folder |
| `docs/govee_capability_notes.md` | NO-HEADER | docs-root-supporting | - | confirmed | Status matches folder |
| `docs/govee_realtime_design.md` | current-supporting | docs-root-supporting | - | confirmed | Status matches folder |
| `docs/guides/laser_director_midi_mapping_workflow.md` | NO-HEADER | current-supporting | - | confirmed | Status matches folder |
| `docs/guides/laser_director_rollout_checklist.md` | NO-HEADER | current-supporting | - | confirmed | Status matches folder |
| `docs/guides/laser_pad.md` | NO-HEADER | current-supporting | - | confirmed | Status matches folder |
| `docs/guides/laser_pad_parity.md` | NO-HEADER | current-supporting | - | confirmed | Status matches folder |
| `docs/guides/led_pad.md` | current | current-supporting | - | confirmed | Status matches folder |
| `docs/led_look_director_design.md` | NO-HEADER | docs-root-supporting | - | confirmed | Status matches folder |
| `docs/led_look_mapping_workflow.md` | NO-HEADER | docs-root-supporting | - | confirmed | Status matches folder |
| `docs/plans/active/audit_2026_07_03_fix_queue_spec.md` | NO-HEADER | active | - | confirmed | No-header active spec (AWR-116) - correctly placed |
| `docs/plans/active/audit_2026_07_03_followups_spec.md` | NO-HEADER | active | - | confirmed | No-header active spec (AWR-118) - correctly placed |
| `docs/plans/active/cross_platform_portability_fable_review.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/cross_platform_portability_plan.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/drop_presentation_impl_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/drop_presentation_label_rearm_leak_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/drop_presentation_true_drop_section_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/drop_two_hit_rule_restore_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/govee_health_reporting_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_blackout_rewire_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_color_engine_design_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_color_hold_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_color_impl_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_color_menu_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_drop_section_gate_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_drop_window_impact_reentry_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/laser_solo_observability_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_blackout_transport_observability_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_dispatch_extraction_spec.md` | NO-HEADER | active | - | confirmed | No-header active spec (AWR-117) - correctly placed |
| `docs/plans/active/led_hold_starvation_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_idle_pause_ambient_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_intra_section_rotation_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_pad_color_queue_restore_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_pad_template_lab_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_realtime_wrap_flicker_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/led_solo_predark_race_fix_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/lighting_engine_v2_f1_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/lighting_v1_foundation_audit.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/lighting_v1_foundation_fix_spec.md` | current | active | - | confirmed | Implemented, operator live-pass pending; index lists ACTIVE |
| `docs/plans/active/logging_edge_trigger_warning_spam_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/logging_overhaul_design.md` | active-design | active | - | confirmed | Status matches folder |
| `docs/plans/active/logging_overhaul_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/native_autoloop_dmx_runtime_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/palette_gesture_v2_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/retro_launch_guard_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/self_learning_workflow_design.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/smart_drop_marker_collapse_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/soundswitch_README.md` | active-plan-index | active | - | confirmed | Status matches folder |
| `docs/plans/active/soundswitch_exporter_remaining_work.md` | active-plan | active | - | confirmed | Status matches folder |
| `docs/plans/active/soundswitch_t7c_pack_driver_spec.md` | compatibility-pointer | active | - | confirmed | Deliberate compatibility-pointer (doc_index) |
| `docs/plans/active/streamdeck_bridge_side_hardening_impl_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_palette_control_design_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_palette_control_impl_spec.md` | active-spec | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` | review-evidence | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_phase2_plan_review.md` | review-evidence | active | - | confirmed | Status matches folder |
| `docs/plans/active/streamdeck_surface_hardening_findings_2026_07_04.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/template_lab_direction_2026_07_04.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/template_lab_round1_codex_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/template_lab_round2_codex_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/template_lab_round3_codex_spec.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/usb_bridge_launcher_design.md` | current | active | - | confirmed | Status matches folder |
| `docs/plans/active/usb_bridge_launcher_fable_review.md` | current | active | - | confirmed | Status matches folder |
| `docs/prompts/README.md` | current | index | - | confirmed | Folder index README - correctly placed |
| `docs/prompts/active/doc_inventory_audit_opus_prompt.md` | active-prompt | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/led_laser_color_fable_review_expand_prompt.md` | current | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/led_laser_design_adversarial_review_fable_prompt.md` | current | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/spec_review_revise_implement_fable_prompt.md` | current | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/streamdeck_debug_fable_prompt.md` | current | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` | active-implementation-prompt | active-prompt | - | confirmed | Status matches folder |
| `docs/prompts/active/template_lab_creative_lead_fable.md` | NO-HEADER | active-prompt | - | confirmed | No-header, but active standing companion (AWR-126) - correctly placed |
| `docs/prompts/reviews/autoloop_fable_audit.md` | NO-HEADER | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/drop_detection_review_brief.md` | NO-HEADER | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/drop_detection_review_v2.md` | NO-HEADER | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/native_autoloop_spec_readiness_review_prompt.md` | active-review-prompt | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/pr88_review_prompt.md` | NO-HEADER | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/rekordbox_mixer_active_deck_re_findings_verification_prompt.md` | active-review-prompt | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` | active-review-prompt | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` | active-review-prompt | review | - | confirmed | Status matches folder |
| `docs/prompts/reviews/soundswitch_rw7_capture_agent_review_prompt.md` | active-review-prompt | review | - | confirmed | Status matches folder |
| `docs/prompts/snippets/codex_gpt5_snippets.md` | current | loose-prompt(root) | - | confirmed | Status matches folder |
| `docs/prompts/snippets/fable5_snippets.md` | current | loose-prompt(root) | - | confirmed | Status matches folder |
| `docs/prompts/snippets/opus48_snippets.md` | current | loose-prompt(root) | - | confirmed | Status matches folder |
| `docs/research/anlz_energy_project.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/anlz_waveform_tag_inventory.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/edm_lighting_color_research.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/edm_lighting_color_research_round2.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/edm_lighting_color_research_round3.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/edm_lighting_color_research_round4.md` | NO-HEADER | research | - | confirmed | Status matches folder |
| `docs/research/lighting_engine_v2_design_review.md` | current | research | - | confirmed | Status matches folder |
| `docs/research/lighting_engine_v2_strict_review.md` | current | research | - | confirmed | Status matches folder |
| `docs/research/rekordbox_mixer_active_deck_re_evidence.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/README.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/research_tools.md` | research-tool-guide | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_authoring_mutation_matrix.md` | research-complete-bounded-scope | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_ghidra_addendum.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` | active-product-contract-implementation-partial | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_live_capture_findings_2026_07_02_evening.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_re_closure_report.md` | research-complete-bounded-scope | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_re_edgecase_findings.md` | historical-evidence | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_ssfile_format.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md` | research-current | research | - | confirmed | Status matches folder |
| `docs/research/soundswitch/soundswitch_validation_matrix.md` | active-validation-evidence | research | - | confirmed | Status matches folder |
| `docs/research/spectral_audio_analysis_redesign.md` | current | research | - | confirmed | Status matches folder |
| `docs/research/spectral_palettes_arrival_crossfade_exploration.md` | current | research | - | confirmed | Status matches folder |
| `docs/setup/configuration.md` | current | current | - | confirmed | Status matches folder |
| `docs/setup/graphify.md` | current | current | - | confirmed | Status matches folder |
| `docs/setup/local_setup.md` | current | current | - | confirmed | Status matches folder |
| `docs/setup/repo_move_checklist.md` | current | current | - | confirmed | Status matches folder |
| `docs/setup/runtime_commands.md` | current | current | - | confirmed | Status matches folder |
| `docs/setup/troubleshooting.md` | current | current | - | confirmed | Status matches folder |
| `docs/status/active_work_registry.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/current_working_setup.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/feature_status_matrix.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/known_limitations.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/project_status.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/support_matrix.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/status/validation_matrix.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/config.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/core_bridge.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/laser.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/led_govee.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/logging.md` | NO-HEADER | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/rekordbox_readers.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/runtime_commands.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/soundswitch_output.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/subsystems/tests.md` | current | authoritative | - | confirmed | Status matches folder |
| `docs/validation/anlz_energy_corpus_report.md` | NO-HEADER | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/anlz_energy_evaluation_guide.md` | NO-HEADER | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/autoloop_beatphase_findings.md` | NO-HEADER | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/hardware_validation_log.md` | current-incomplete | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/software_test_inventory.md` | current | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_exporter_player_software_review.md` | active-validation | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_hardware_runs/2026-06-24_3b7469a_rw5-software-preflight.md` | in-progress-run-record | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | template | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_hardware_validation_procedure.md` | current | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_publish_sidecar_review.md` | active-validation | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_t7d_phase_contract_blocked.md` | active-validation | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/soundswitch_t7d_phase_contract_evidence.md` | active-validation | validation-evidence | - | confirmed | Status matches folder |
| `docs/validation/validation_policy.md` | current | validation-evidence | - | confirmed | Status matches folder |

## Bucket C - INACTIVE & CORRECTLY PLACED (no move)

| path | doc_status | folder-implied | correct folder (if move) | confidence | note |
|---|---|---|---|---|---|
| `docs/archive/plans/autoloop_codex_spec.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/plans/laser_smartnet_mask_preserve_spec.md` | deferred-reference | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/plans/ultimate_autoloop_intelligence_plan.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/anchored_tuner_codex_prompt.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/autoloop_composer_prompt.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/codex-laser-pad-ux-refactor.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/codex_smart_drop_and_phrase_anchor.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/laser_drop_mode_hold_rotated_codex_prompt.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/laser_drop_rotation_seed_codex_prompt.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/archive/prompts/laser_verify_deterministic_cursor_codex_prompt.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/history/archive/live_bpm_v2_plan.md` | NO-HEADER | archive->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/history/dashboard_plan.md` | NO-HEADER | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/history/logging_implementation_handoff.md` | NO-HEADER | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/history/pssi_mood23_up_mapping_spike_2026-05-10.md` | NO-HEADER | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/history/smart_drop_phase2_handoff.md` | NO-HEADER | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/beat_sync_runtime_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/bridge_log_visibility_gemini_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/bridge_log_visibility_phase2_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/chorus_drop_cycling_revision_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/chorus_drop_cycling_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/docs_orphan_check_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/govee_realtime_codex_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_agent_orchestrator_workflow.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_color_engine_m2_5_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_color_engine_solid_color_and_patch_f_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_color_engine_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_look_director_integration_plan_revised.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/led_role_mapping_v2_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/patch_d_staleness_bump_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/rt_comet_pause_continuation_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/rt_comet_smoothness_fix_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/rt_comet_stutter_fix_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/README.md` | completed-plan-index | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_autoloop_equivalence_oracle_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_dmx_cue_mismatch_spec.md` | superseded-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_hardware_validation_harness_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_impl_progress.md` | superseded-ledger | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_pack_menu_enable_spec.md` | NO-HEADER | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_pack_parity_root_cause_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_pack_render_defect.md` | completed-investigation | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_pack_repo_local_handoff.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_parity_capture_orchestration_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_parity_evidence_finisher_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_perfect_parity_finisher_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_publish_sidecar_review_bookkeeping_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_re_edgecase_hardening_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_remaining_software_scope.md` | superseded-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_roadmap_registry_reconciliation_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw1_export_change_detection_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw1_export_fixes_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw1_export_from_ss_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw1a_shutdown_ownership_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw2_scripted_transport_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw3_mode_authority_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw4_input_health_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw4_static_slot_swap_resync_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_rw5_operational_status_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_static_toggle_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t7_t8_t9_implementation_spec.md` | superseded-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t7c_pack_driver_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t7d_b1_phase_trace_wiring_spec.md` | completed-plan | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t7d_capture_evidence_plan.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t7e_status_commands_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_t8_offline_shadow_proof.md` | completed-proof | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/plans/completed/soundswitch/soundswitch_witness_auto_retire_spec.md` | completed-spec | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/graphify_install_prompt.md` | completed-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/soundswitch_perfect_parity_fable5_prompt.md` | active-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/soundswitch_perfect_parity_fable_oneshot_2026_07_02.md` | active-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/soundswitch_rw7_capture_agent_prompt.md` | active-review-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/soundswitch_time_domain_offline_exam_codex_prompt.md` | active-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/prompts/completed/soundswitch_truth_exam_fable_fix_prompt.md` | active-prompt | completed->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/README.md` | research-history-index | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/codex_ss_catalog_handoff.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_decode_export_codex_spec.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_exporter_renderer_full_plan.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_reverse_engineering_session_handoff.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_scripted_b2_operator_capture_handoff.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_scripted_renderer_closure_handoff_spec.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_stage2_research_findings.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_stage3_handoff.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_standalone_laser_exporter_spec.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/soundswitch_static_pack_player_spec.md` | historical-draft | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/ss_memory_discovery.md` | historical-evidence | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |
| `docs/research/soundswitch/history/working_notes_stage1.md` | NO-HEADER | historical->inactive | - | confirmed | Location IS status (inactive graveyard/archive) - no move |

