---
doc_status: current
truth_level: code-verified
last_verified_commit: 0d3aa5c
last_verified_date: 2026-06-29
validation_scope: software-only plus Rekordbox 7.2.11 passive mixer RE evidence routing for Deck 1/2 upfader, LOW/BASS EQ, CFX FILTER, Deck 1 mid fader, relaunch reacquire, and mixer-chain readability after operator-labeled master-button actions; hardware-output unvalidated
---

# Active Work Registry

This is the single repo-facing place for unfinished work. Old prompts and plans are not active unless listed here.

## Active engineering work

Each item points at an on-disk spec. **A spec is a plan, not proof of implementation — verify against current code before acting.**

| ID | Area | Spec | Verify |
| --- | --- | --- | --- |
| AWR-105 | LED role mapping v2 | `docs/plans/completed/led_role_mapping_v2_spec.md` | scripted groove/drop/post-drop blackout remap is implemented and software-tested in current worktree; broader role-mapping-v2 scope still needs verification against `led_look_director.py`/`led_models.py` |
| AWR-106 | LED color engine M2.5 solid-color strategy + Patch F cleanup | `docs/plans/completed/led_color_engine_solid_color_and_patch_f_spec.md` | Patch S `random_with_mono_chance` and Patch F tracked-example bank cleanup are implemented and software-tested only; live-config mirror remains operator-gated; all hardware behavior remains unvalidated |
| AWR-107 | SoundSwitch static exporter / bridge-native player | `docs/plans/active/soundswitch_exporter_remaining_work.md` (single current status/roadmap), `docs/plans/active/soundswitch_README.md` (project index), `docs/research/soundswitch/README.md` (RE routing), `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` (capture blocker), `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md` (only active SoundSwitch execution prompt), `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` (reusable review-only handoff), `docs/validation/soundswitch_hardware_validation_procedure.md` and `soundswitch_hardware_runs/TEMPLATE.md` (non-Autoloop operator gate) | Current project proof is 29 PASS / 0 FAIL / 0 INCOMPLETE and 32/32 active scripted tracks are exportable. RW-1 through RW-5, graceful shutdown ownership, the copied menubar status, the connection auto-switch (`set_soundswitch_pack action=enable`, with one bounded `pack_start_failed` retry and no manual pack button), the SoundSwitch-saved Static Override Press/Toggle interaction mode, the repo-local ignored pack path `local/soundswitch/rbss_canonical_pack`, required binding-sidecar stage-before-swap publication, and the non-Autoloop procedure/template are implemented and software-tested. The latest independent software/wire review found no blocker/high issues; one medium menubar parser mismatch was fixed. Material specs are historical under `docs/plans/completed/soundswitch/`. No operator hardware evidence run exists. T7d still lacks four scenario pairs, identity/holdout reconciliation, and a unique oracle; native Autoloop DMX remains unimplemented and software-zero. Pack blackout routing and the F12 held-blackout hold-expiry fix (edge-case hardening Task 11, now in `docs/plans/completed/soundswitch/`) are deferred pre-go-live: the BLACK OUT pad is currently inert in pack mode (never opened), so there is no live exposure today; decide routing and apply F12 together before any hardware go-live. No live config, restart, runtime command, device, output, or hardware action is authorized. SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-108 | Laser drop/post-drop lifecycle mirror | `docs/plans/active/chorus_drop_cycling_spec.md` | Tasks 1-5 and Part D are implemented and software-tested at `9918dd4` and `ed78263`. Live LED behavior is unchanged. Laser hardware/SoundSwitch observation and kill-switch rehearsal remain pending; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-109 | Stream Deck MIDI controller / layered static-look compositor | `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` (Phase 1 implemented; Part F Phase 2 spec), `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` (implementation handoff), `docs/plans/active/streamdeck_phase2_plan_review.md` and `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` (review evidence) | Phase 1 controller lifecycle hardening is implemented in current `main`. Phase 2 is a revised implementation plan only: generic layered DMX compositor, lock-free hot-path snapshots, worker-thread input-port-gone recovery, pure render path, sibling binding sidecar, and local controller LED state. No bridge restart, controller smoke, Enttec/DMX, fixture, or live hardware action is authorized. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-110 | Rekordbox mixer active-deck authority | `docs/architecture/active_deck_authority.md` (operator-authoritative target behavior), `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` (Ghidra/Ghidra-MCP RE + implementation handoff), `docs/research/rekordbox_mixer_active_deck_re_evidence.md` (current RE proof), `docs/prompts/active/rekordbox_mixer_active_deck_re_continuation_prompt.md` (superseded implementation-prompt context), `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` (adversarial RE review handoff) | Runtime implementation is present and software-tested at `0d3aa5c`. `active_deck` is now the resolved show deck selected from Deck 1/2 playing state, decoded upfader, decoded LOW/BASS, `rb_master_deck` tie/fallback, validity/freshness, and stability state; `rb_master_deck` is retained separately. Named mixer offset labels fail closed, mixer reads use finite range-checked f32 instead of the live-BPM float helper, partial/invalid snapshots invalidate authority, and status/heartbeat expose show deck plus Rekordbox master separately. Legacy OSC, playing-only mirror, and `_do_resume()` active-deck bypasses are gated while mixer authority is enabled; invalid/stale mixer fallback is resolver-mediated current valid/fresh `rb_master_deck` fallback only. CFX FILTER is confirmed RE evidence but is non-authority and is not decoded for active-deck authority in this implementation. Static Ghidra/GhidraMCP evidence plus operator-approved passive process-memory proof still applies only to local Rekordbox 7.2.11 mixer chains. Resolver thresholds/stability windows are implementation policy, not RE facts. Versions beyond 7.2.11, actual loaded-track play/stop survival, live runtime observation, SoundSwitch/laser/LED/Govee/DMX/MIDI/Enttec behavior, and hardware-visible behavior remain unvalidated. No bridge restart, additional live capture, process-memory sampling, or hardware action is authorized by the spec alone. |
| AWR-111 | Laser color (CH8/CH9 color control) | `docs/plans/active/laser_color_engine_design_spec.md` | PLANNED / DESIGN-INTENT — **not implemented**; blocked on operator capture of CH8/CH9 laser channel behavior (VirtualLaserNode). Authored pre-handoff in PR #111 but never registered until 2026-06-29. Verify against code before any implementation. |
| AWR-112 | Graphify repo-map integration | `docs/prompts/active/graphify_install_prompt.md` | Install + tune Graphify (local code-AST relationship map) for orient-before-read. Locked: always-on hooks ENABLED for both Claude and Codex (operator wants the auto query-before-read nudge), code-only (no cloud key), `graphify-out/` gitignored, flat module layout preserved. Pilot gate (3 known-answer questions) decides keep/drop. Not started. |

**Closed 2026-06-29:** AWR-101 (LED color engine M2.5), AWR-102 (LED color engine core), AWR-103 (realtime comet), AWR-104 (beat-sync runtime) — operator hardware sign-off on Home Govee. Software work landed (specs in `docs/plans/completed/`); evidence in `docs/validation/hardware_validation_log.md`. AWR-105 and AWR-106 remain active (software-done, hardware-pending).

## Documentation system follow-ups

| ID | Area | Status | Next action |
| --- | --- | --- | --- |
| AWR-001 | Old-doc classification + archive pass | done | `docs/architecture/doc_index.md` classifies all docs. 2026-06-29 sweep: completed SoundSwitch RE-edgecase + publish-sidecar specs → `docs/plans/completed/soundswitch/`, chorus drop-lifecycle revision → `docs/plans/completed/`, RE-edgecase findings → `docs/research/soundswitch/`, deferred laser SM-net spec → `docs/archive/plans/`; spent review/handoff prompts deleted (Git history preserves them). |
| AWR-002 | Untracked govee spec | open | Classify `docs/plans/completed/govee_realtime_codex_spec.md` (completed vs awaiting-build) and commit or archive it in a separate change. |
| AWR-003 | Stray root output files | done | Relocated `cues_output.md` / `cues_timing_output.md` to `docs/data/` (2026-06-29). |
| AWR-004 | First agent-workflow dry run | active | Use this system on the next real feature change on `main`; record missing routes, unclear contracts, token-waste points, or hidden branch-state risks. |
| AWR-005 | Runtime command test inventory | active | Map parser/handler tests and add missing ones only in a separate code/test PR. |
| AWR-006 | Contract coverage audit | active | After a feature PR, tighten `docs/agents/change_contracts.yml` around any files agents had to rediscover. |
| AWR-007 | Docs orphan-coverage check | spec ready for Codex | `docs/plans/active/docs_orphan_check_spec.md` — extend `tools/check_agent_contracts.py` to fail CI when a file in `docs/plans/active/` or `docs/prompts/active/` is not classified in `doc_index.md`/registry. Closes the gap that let the AWR-111 orphan persist. |

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
