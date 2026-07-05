---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: fc56bb5
last_verified_date: 2026-07-03
validation_scope: software-validated only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-unvalidated in repo evidence
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
| `docs/architecture/active_deck_authority.md` | CURRENT AUTHORITATIVE — operator-authoritative behavior for fader/bass active-deck authority; software-tested implementation exists, live/hardware validation pending. |
| `docs/architecture/laser_director_design.md` | CURRENT AUTHORITATIVE — Laser Director design. |
| `docs/architecture/led_pad_template_lab_design.md` | CURRENT AUTHORITATIVE — LED Pad + Template Lab intended-features design (browser UI, banks, editor, lab, output ownership). Implementation tracked under AWR-113; verify against code as phases land. |
| `docs/architecture/native_autoloop_pack_authority.md` | CURRENT AUTHORITATIVE — native Autoloop pack authority (grounds AWR-107 native DMX runtime). |
| `docs/architecture/palette_control_authority.md` | CURRENT AUTHORITATIVE — operator-authoritative behavior for the Stream Deck palette/mute/solo/rainbow surface; NOT YET IMPLEMENTED (design approved 2026-07-04). |
| `docs/architecture/drop_presentation_authority.md` | CURRENT AUTHORITATIVE — operator-authoritative per-drop fixture presentation (LEDs-only majority, Laser Solo tiers, zero RNG); NOT YET IMPLEMENTED (design approved 2026-07-04). |
| `docs/architecture/laser_color_authority.md` | CURRENT AUTHORITATIVE — operator-authoritative laser color behavior (LED-follow quantizer, white rules, chart gating); NOT YET IMPLEMENTED (design approved 2026-07-04). |
| `docs/architecture/laser_blackout_authority.md` | CURRENT AUTHORITATIVE — operator-authoritative blackout ownership contract (two owner systems, survival matrix); RE-WIRE NOT YET IMPLEMENTED (design approved 2026-07-04). |
| `docs/architecture/doc_index.md` | CURRENT AUTHORITATIVE — this index. |

## Agent operating system — current

| Area | Files | Type |
| --- | --- | --- |
| Change contracts | `docs/agents/change_contracts.md`, `docs/agents/change_contracts.yml` | CURRENT AUTHORITATIVE — what must update when code changes; enforced by checkers. |
| Drift detection | `docs/agents/drift_detection.md` | CURRENT AUTHORITATIVE. |
| Agent lessons | `docs/agents/lessons/*.md` | CURRENT AUTHORITATIVE — agent lessons; verify before reuse. |
| Task playbooks | `docs/agents/task_playbooks/*.md` (8) | CURRENT AUTHORITATIVE — per-task reading routes. |
| Subsystem cards | `docs/subsystems/{core_bridge,rekordbox_readers,soundswitch_output,laser,led_govee,runtime_commands,config,tests}.md` | CURRENT — compact, code-verified cards. |
| Status / truth | `docs/status/*.md` (7) | CURRENT — project status, feature/support/validation matrices, known limitations, active work. |
| Prompt authoring | `docs/prompts/README.md`, `docs/prompts/snippets/*.md`, `.claude/skills/fable-prompt-writer/SKILL.md`, `.claude/skills/opus-prompt-writer/SKILL.md`, `.claude/skills/codex-spec/SKILL.md` | CURRENT SUPPORTING — one prompt/spec-authoring skill per target agent (Fable 5, Opus 4.8, Codex/GPT-5) plus per-model snippet libraries; prompt-only, not active work. |
| Setup / usage | `docs/setup/*.md` (5) | CURRENT. |
| Validation policy | `docs/validation/{validation_policy,software_test_inventory,hardware_validation_log,soundswitch_hardware_validation_procedure}.md`, `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | CURRENT — SoundSwitch procedure/template are operator gates, not completed hardware evidence. |
| Archive banner | `docs/archive/README.md` | CURRENT. |

## Current supporting — verify before relying

| File | Type |
| --- | --- |
| `docs/govee_realtime_design.md` | CURRENT SUPPORTING — Govee realtime design (referenced by `current_architecture.md`). |
| `docs/led_look_director_design.md` | CURRENT SUPPORTING — LED Look Director design. |
| `docs/led_look_mapping_workflow.md` | CURRENT SUPPORTING — operator mapping workflow. |
| `docs/govee_capability_notes.md` | CURRENT SUPPORTING — Govee device capability notes. |
| `docs/guides/*.md` (5) | CURRENT SUPPORTING — laser MIDI mapping, rollout checklist, Laser Pad live-toggle/draft behavior, LED Pad/Template Lab operator guide. |
| `docs/subsystems/logging.md` | CURRENT SUPPORTING — matches `bridge_log.py`/`bridge_view.py` (AWR-125; `logging_manager.py` is retired). |
| `docs/data/offsets-*.yaml` (3) | CURRENT SUPPORTING — Rekordbox offset reference data. |
| `docs/data/cues_*.md` (2) | GENERATED OUTPUT — relocated cue dumps; not in the reading path. |
| `docs/research/*.md` | RESEARCH — ANLZ energy/waveform-tag evidence plus Rekordbox mixer active-deck RE proof. |
| `docs/research/soundswitch/*.md` | SOUNDSWITCH RE AUTHORITY — current closure report, format/binary findings, evidence matrices, tool guide, and product contract. Start with `README.md`. |
| `docs/research/soundswitch/history/*.md` | SOUNDSWITCH RE HISTORY — superseded handoffs, intermediate findings, and draft exporter/player specs. Historical provenance only. |
| `docs/validation/anlz_energy_corpus_report.md`, `anlz_energy_evaluation_guide.md`, `autoloop_beatphase_findings.md`, `smart_drop_synthetic_corpus.yaml` | VALIDATION EVIDENCE. |
| `docs/validation/soundswitch_exporter_player_software_review.md`, `docs/validation/soundswitch_publish_sidecar_review.md`, `docs/validation/soundswitch_t7d_phase_contract_blocked.md`, `docs/validation/soundswitch_t7d_phase_contract_evidence.md` | VALIDATION EVIDENCE — SoundSwitch exporter/player software review, publish-sidecar review, and T7d phase-contract blocked/evidence records. |
| `docs/validation/soundswitch_hardware_runs/2026-06-24_3b7469a_rw5-software-preflight.md` | VALIDATION EVIDENCE — software preflight record; not a hardware run. |

## Active plans & prompts — VALIDATE against code before executing

Active only if also listed in `docs/status/active_work_registry.md`. Confirm each against current `main` before acting.

| Zone | Type | Notes |
| --- | --- | --- |
| `docs/plans/completed/{led_color_engine_spec,led_color_engine_m2_5_spec,led_color_engine_solid_color_and_patch_f_spec,led_role_mapping_v2_spec,beat_sync_runtime_spec,rt_comet_*}.md` | COMPLETED / SUPERSEDED PLANNING | LED color engine (core + M2.5 + solid-color/Patch F), role-mapping v2, beat-sync, and realtime-comet specs — software work landed. AWR-101–104 have operator hardware sign-off (2026-06-29, Home Govee; see `docs/validation/hardware_validation_log.md`); AWR-105 (role mapping) and AWR-106 (solid-color + Patch F) are software-done but hardware-pending. Historical evidence only. |
| `docs/plans/active/laser_color_engine_design_spec.md` | PLAN / SPEC (PLANNED — design-intent, expanded 2026-07-04) | Laser color (bridge-owns-frame, fixed-color quantizer, white moments, settle, rainbow tier) + blackout re-wire. Only the CH8/CH9 value table is operator-blocked. Behavior contracts: `laser_color_authority.md`, `laser_blackout_authority.md`. Tracked as AWR-111. **Not implemented.** |
| `docs/plans/active/laser_blackout_rewire_spec.md` | PLAN / SPEC (ACTIVE — Codex-ready, Package 1) | Blackout re-wire implementation spec: owner latch decouple + OR at the single mask writer + survival-matrix tests. AWR-111/119. **Not implemented.** |
| `docs/plans/active/streamdeck_palette_control_impl_spec.md` | PLAN / SPEC (ACTIVE — Codex-ready, Package 2) | Palette control + deck surface implementation spec: engine fade/lock semantics, coordinator, pad bindings/events/commands, feedback file, deck icons, Rainbow (LED). AWR-119. **Not implemented.** |
| `docs/plans/active/drop_presentation_impl_spec.md` | PLAN / SPEC (ACTIVE — Codex-ready, Package 3) | Drop presentation policy implementation spec: planner, solo tiers (master.db hotcues, learned, gear-shift, record), window machine, base suppression, Solo pad. AWR-119. **Not implemented.** |
| `docs/plans/active/laser_color_impl_spec.md` | PLAN / SPEC (ACTIVE — Codex-ready, Package 4) | Laser color plumbing implementation spec: accessor, quantizer+snapshot, merge seam, white-moment flag; ships pass-through until the operator chart lands as config. AWR-111. **Not implemented.** |
| `docs/prompts/active/led_laser_design_adversarial_review_fable_prompt.md` | AGENT PROMPT (ACTIVE) | Fable 5 adversarial review + stress test of the AWR-119/111 design corpus (4 authority docs + 4 impl specs + 2 design specs) before Codex handoff; read-only, findings + verdicts, stops for operator. |
| `docs/plans/active/streamdeck_palette_control_design_spec.md` | PLAN / SPEC (PLANNED — design-intent, expanded 2026-07-04) | Stream Deck palette control (queue/override-fade/lock, `white_sand`, mutes, Laser Solo, Rainbow mode, iconography) + the zero-RNG drop presentation policy. Behavior contracts: `palette_control_authority.md`, `drop_presentation_authority.md`. Tracked as AWR-119. **Not implemented.** |
| `docs/plans/completed/docs_orphan_check_spec.md` | COMPLETED / SUPERSEDED PLANNING | Active-doc lifecycle check (orphan + stale) — IMPLEMENTED in `tools/check_agent_contracts.py`; AWR-007 done. Historical record. |
| `docs/plans/completed/chorus_drop_cycling_spec.md` | COMPLETED / SUPERSEDED PLANNING | Laser drop/post-drop lifecycle mirror (AWR-108); implemented/software-tested; hardware observation + kill-switch rehearsal pending. |
| `docs/plans/active/soundswitch_README.md` | ACTIVE PROJECT INDEX | Grouped routing for the SoundSwitch exporter/bridge-native DMX project. |
| `docs/plans/active/soundswitch_exporter_remaining_work.md` | ACTIVE CHECKLIST / ROADMAP | Current landed-versus-remaining authority. RW-1 through RW-5 and native Autoloop DMX are implemented/software-tested; old T7d six-scenario gating is historical and no longer blocks native implementation; live/runtime validation, a real hardware run, and final closeout remain. |
| `docs/plans/completed/soundswitch/soundswitch_pack_parity_root_cause_spec.md` | BASELINE / CONTEXT AUDIT TARGET | Prior parity investigation and Ghidra function-map baseline. Do not resume it as the active fix scope. The current 2026-07-02 evidence shows a broader exporter/runtime perfect-parity problem set than the old "3 runtime bugs" reframe: official comparator invalidity, live byte/timing disagreements, offline scripted/autoloop timing outliers, static-not-covered, playback/seek/BPM/transition/active-deck gaps, stale-source divergence, and unsupported/opaque inventory. Final Fable handoff (completed; superseded by `docs/prompts/completed/soundswitch_perfect_parity_fable_oneshot_2026_07_02.md`); workstream software-complete per AWR-107. Current evidence: `docs/research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md` and `docs/research/soundswitch/soundswitch_time_domain_exam_2026_07.md`. DD42028C remains a negative-control witness, not show coverage. Tracked under AWR-112. |
| `docs/plans/completed/soundswitch/soundswitch_parity_capture_orchestration_spec.md` | CAPTURE PLAN (COMPLETED / historical evidence) | Codex-orchestrated live all-surface U0/U1 parity capture WITH the operator (static looks slots 0/24/16/31, autoloops via phrase-driven playback, real scripted tracks; DD42028C excluded as an orphan). Observer/read-only; operator owns the live binds (bridge truth-check, SoundSwitch Art-Net U0, sniffer). Produces one aligned gitignored capture directory that later derives + proves perfect parity. Feeds AWR-112. |
| `docs/plans/completed/soundswitch/soundswitch_parity_evidence_finisher_spec.md` | PLAN / SPEC (COMPLETED / historical evidence) | Codex implementation spec for turning the passive parity capture into fixture/oracle/registry evidence. Current canonical manifest reports active lanes `algorithm_generalized: 67`, `oracle_proven: 16`, `unverified_parity: 0`; inactive unverified lanes remain tracked separately. This evidence-finisher status does not prove perfect runtime parity: final Fable handoff (completed; superseded by `docs/prompts/completed/soundswitch_perfect_parity_fable_oneshot_2026_07_02.md`); workstream software-complete per AWR-107. |
| `docs/plans/completed/soundswitch/soundswitch_pack_render_defect.md` | NEGATIVE-CONTROL WITNESS | DD42028C is a metadata-less orphan the operator never plays: EXCLUDED from operator performance/parity coverage, but RETAINED as a negative-control witness (a known-divergent track the parity oracle should correctly flag). Not erased. Scripted U0/U1 mismatch for `dd42028c-0823-4a8d-ad7e-b26e24180272`: mixer theory rejected; local ignored canonical pack patched with capture-derived `oracle_rendered` boundary frames; later audit shows the patch improves but does not exactly match U0 boundaries. |
| `docs/plans/completed/soundswitch/soundswitch_dmx_cue_mismatch_spec.md` | REJECTED-THEORY WARNING | Kept for provenance only. Its playback-mixer theory is rejected (do not resume mixer-renderer tasks from its body). Final Fable handoff (completed; superseded by `docs/prompts/completed/soundswitch_perfect_parity_fable_oneshot_2026_07_02.md`); workstream software-complete per AWR-107. Older Fable prompts are historical context unless reverified against the 2026-07-02 evidence docs. |
| `docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md` | ACTIVE CONTRACT POINTER | Symlink to the original product/implementation contract. Read the active remaining-work roadmap for current status. |
| `docs/plans/active/soundswitch_t7c_pack_driver_spec.md` | COMPATIBILITY POINTER | Preserves code/test links to the completed T7c spec; current status is in the SoundSwitch remaining-work roadmap. |
| `docs/plans/completed/soundswitch/soundswitch_t7d_capture_evidence_plan.md` | EVIDENCE / TOOLING PROVENANCE | Operator confirmed T7d is not the vehicle for parity; retained as evidence/tooling provenance only, not an active gate. Final Fable handoff (completed; superseded by `docs/prompts/completed/soundswitch_perfect_parity_fable_oneshot_2026_07_02.md`); workstream software-complete per AWR-107. Historical six-scenario T7d blocker plan. It is not the active gate for native Autoloop DMX; the greenlit native path uses the authority doc, native runtime spec, offline equivalence oracle, and operator two-flight calibration/A-B run. |
| `docs/plans/active/native_autoloop_dmx_runtime_spec.md` | PLAN / SPEC (ACTIVE) | Codex implementation spec for native Autoloop DMX: pack note->Autoloop map, exposing the executor's post-bank selected scene, a latched I/O-free phase resolver, StateManager pack-driver wiring, status migration, fail-closed bindings. Grounded in `docs/architecture/native_autoloop_pack_authority.md`. Implemented/software-tested; phase carries a `phase_offset_beats` calibration input pending the two-flight capture. Tracked under AWR-107. |
| `docs/plans/completed/soundswitch/soundswitch_autoloop_equivalence_oracle_spec.md` | PLAN / SPEC (COMPLETED — oracle landed; supports AWR-107 calibration) | Falsifiable oracle that checks native Autoloop output equivalence against SoundSwitch-authored looks via `render_autoloop_frame`. Supports the native Autoloop phase calibration; validate against code before relying. Tracked under AWR-107. |
| `docs/prompts/completed/soundswitch_rw7_capture_agent_prompt.md` | AGENT PROMPT (COMPLETED / provenance) | Legacy operator-conducted T7d evidence prompt retained for provenance; not a native-Autoloop implementation gate and no pack/hardware enablement authority. |
| `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` | REVIEW PROMPT (COMPLETED / provenance) | Commit-scoped independent ChatGPT review of RW-5, the non-Autoloop procedure/template, and SoundSwitch document lifecycle. Review-only. |
| `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` | PLAN / SPEC (ACTIVE) | Stream Deck controller lifecycle plus Phase 2 generic layered static-look compositor. Phase 1 implemented; Phase 2 is implementation-ready but live restart/hardware smoke remain operator-gated. |
| `docs/plans/active/led_pad_template_lab_spec.md` | PLAN / SPEC (ACTIVE) | Codex implementation spec for LED Pad + Template Lab (Phases 0–3 implemented/software-tested), including the authoritative UI design spec. Grounded in `docs/architecture/led_pad_template_lab_design.md`. Tracked under AWR-113. |
| `docs/plans/active/template_lab_direction_2026_07_04.md` | PLAN / SPEC (ACTIVE) | Template Lab creative + engineering direction (operator-approved 2026-07-04): sessions are variants-first (agent authors 2-3 takes, Brandon flips between them live, then tunes), both talk-mode (agent API) and knob-mode (UI) driving are first-class, devices include iPad/phone, beat source stays the synthetic clock (no Rekordbox-follow, no tap tempo). Grounds the Round 1-3 Codex implementation specs. Tracked under AWR-126. |
| `docs/plans/active/template_lab_round1_codex_spec.md` | PLAN / SPEC (ACTIVE) | Codex implementation spec for Template Lab Round 1: live param apply (`/api/lab/update`), seamless variant switching (`/api/lab/switch`), an offline preview endpoint (`/api/lab/preview`), and the rewritten `template-lab` agent skill. Implemented/software-tested. Grounded in the direction doc above. Tracked under AWR-126. |
| `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` | AGENT PROMPT (ACTIVE) | Codex implementation handoff for Phase 2 Part F. Software-only; no bridge restart or hardware action authority. |
| `docs/prompts/active/led_laser_color_fable_review_expand_prompt.md` | AGENT PROMPT (ACTIVE) | Fable 5 handoff to review + expand the LED/laser color-control design docs (3 phases, 2 operator gates), surface CH8/CH9 questions, then author the Codex spec and orchestrate implementation via the `codex` tmux session. Review/planning authority only; Codex implements. |
| `docs/plans/active/streamdeck_phase2_plan_review.md`, `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` | REVIEW / AUDIT | Phase 2 review evidence and pre-implementation review prompt. Evidence only; current implementation instructions are in the spec and active prompt. |
| `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` | PLAN / SPEC (ACTIVE) | Static Ghidra plus passive process-memory RE handoff that now has a software-tested runtime implementation. Validate any follow-up against `docs/architecture/active_deck_authority.md` and `docs/research/rekordbox_mixer_active_deck_re_evidence.md`; live/hardware actions remain separately gated. |
| `docs/plans/active/audit_2026_07_03_fix_queue_spec.md` | PLAN / SPEC (ACTIVE) | Ordered Codex implementation queue P1-P4 for the 2026-07-03 codebase audit; implementation is software-tested in current `main`, but the spec remains the audit provenance. Software-only; no live bridge or hardware authority. Tracked under AWR-116. |
| `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` | REVIEW PROMPT (standing review handoff; re-verify before use) | Adversarial review handoff for the Rekordbox mixer RE process and implementation spec. Review-only. |
| `docs/plans/completed/soundswitch/*.md` | COMPLETED / SUPERSEDED PLANNING | Material RW-1 through RW-5, hardware-procedure, T7/T8 specs/proofs, and the old progress ledger. Historical evidence only. |
| `docs/plans/completed/led_agent_orchestrator_workflow.md`, `docs/plans/completed/led_look_director_integration_plan_revised.md` | COMPLETED / SUPERSEDED PLANNING | Early Govee/LED bootstrap plans superseded by the landed LED color engine + LED Pad work. |
| `docs/plans/phase9_personality_resolver_plan.md` | PLAN (DORMANT — not registry-listed) | Personality resolver implemented; Phases 5 (live tuning) and 7–8 unscheduled; revive via a new AWR entry or archive — operator decision pending. |
| `docs/prompts/active/*.md` | AGENT PROMPT (ACTIVE) | Active prompts only. Completed setup prompts belong in `docs/prompts/completed/`; obsolete SoundSwitch prompts — including the completed remaining-software scoping and static-toggle authoring prompts — were deleted; Git history preserves them. |
| `docs/plans/completed/govee_realtime_codex_spec.md` | PLAN / SPEC | Tracked since `50f469e`; completed implementation record. |

## Setup notes

| File | Type |
| --- | --- |
| `docs/setup/graphify.md` | CURRENT SUPPORTING — local Graphify CLI/query setup; graph is an orientation lead, not authority. |

## Archive / historical — evidence only

| Zone | Type | Notes |
| --- | --- | --- |
| `docs/archive/prompts/*.md` (7) | ARCHIVE | Completed/superseded agent prompts. |
| `docs/archive/plans/*.md` (3) | ARCHIVE | Completed autoloop spec + plan; deferred laser SM-net blackout-mask spec (do-not-implement in MIDI path, 2026-06-23 — reference design for future DMX-frame blackout). |
| `docs/prompts/completed/graphify_install_prompt.md` | ARCHIVE / HISTORICAL | Completed Graphify install/tuning prompt for AWR-114; current workflow is `docs/setup/graphify.md`. |
| `docs/prompts/completed/*.md` | ARCHIVE / HISTORICAL | Retained completed prompts are provenance still referenced by current docs; spent zero-reference prompts were deleted 2026-07-03 (Git history preserves them). |
| `docs/prompts/reviews/*.md` | REVIEW / AUDIT | Current review handoffs plus non-SoundSwitch historical review briefs retained where code references them. Completed SoundSwitch review prompts were deleted; Git history preserves them. |
| `docs/history/*.md` + `docs/history/archive/*.md` (5) | ARCHIVE / HISTORICAL | Rollout logs; kept in place (referenced by `current_architecture.md`, `subsystems/logging.md`, and a test name). |

## Main reading order

1. `AGENTS.md`
2. `docs/architecture/current_architecture.md`
3. `docs/architecture/runtime_invariants.md`
4. `docs/architecture/bridge_design.md`
5. `docs/architecture/active_deck_authority.md` for fader/bass active-deck target behavior
6. this index

Then open `docs/validation/` for evidence, `docs/archive/` only for history.

## Maintenance rule

When code changes, update the docs named by the matching contract in
`docs/agents/change_contracts.yml`, then run the three `tools/check_docs_*.py`
checkers. When a doc's status changes, reclassify it here, retain material
implementation specs under `docs/plans/completed/`, and delete redundant prompts
whose only remaining value is already preserved in Git history.
