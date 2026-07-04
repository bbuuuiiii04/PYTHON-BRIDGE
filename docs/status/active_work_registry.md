---
doc_status: current
truth_level: code-verified
last_verified_commit: 56c5f90
last_verified_date: 2026-07-03
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
| AWR-107 | SoundSwitch static exporter / bridge-native player | `docs/plans/active/soundswitch_exporter_remaining_work.md`, `docs/plans/active/soundswitch_README.md`, `docs/research/soundswitch/README.md`, `docs/architecture/native_autoloop_pack_authority.md`, `docs/plans/active/native_autoloop_dmx_runtime_spec.md`, `docs/validation/soundswitch_hardware_validation_procedure.md`, `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | **SOFTWARE-COMPLETE (2026-07-02 finalization pass):** values byte-proven (261/261 + A5 16/16), selection-beat autoloop anchor restored (grid anchor disproven by live capture), idle manual-overlay fix, playing-scrub dark latch, playing-sibling load guard, and edited-witness auto-retire all landed with tests; suite green, proof gate 29/0/0, active lanes `unverified_parity: 0`. Capture/exam-era plans and prompts are retired to `docs/plans/completed/soundswitch/` and `docs/prompts/completed/`; the Art-Net truth-check lane is dormant validation-only tooling, opt-in per launch via `RBSS_BRIDGE_TRUTH=1` on the watcher (normal launches are truth-off). The single remaining gate is the operator's live hardware run with the Enttec present. SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-108 | Laser drop/post-drop lifecycle mirror | `docs/plans/completed/chorus_drop_cycling_spec.md` | Tasks 1-5 and Part D are implemented and software-tested at `9918dd4` and `ed78263`. Live LED behavior is unchanged. Laser hardware/SoundSwitch observation and kill-switch rehearsal remain pending; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-109 | Stream Deck MIDI controller / layered static-look compositor | `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` (Phase 1 implemented; Part F Phase 2 spec), `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` (implementation handoff), `docs/plans/active/streamdeck_phase2_plan_review.md` and `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` (review evidence) | Phase 1 controller lifecycle hardening is implemented in current `main`. Phase 2 is a revised implementation plan only: generic layered DMX compositor, lock-free hot-path snapshots, worker-thread input-port-gone recovery, pure render path, sibling binding sidecar, and local controller LED state. No bridge restart, controller smoke, Enttec/DMX, fixture, or live hardware action is authorized. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-110 | Rekordbox mixer active-deck authority | `docs/architecture/active_deck_authority.md` (operator-authoritative target behavior), `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` (Ghidra/Ghidra-MCP RE + implementation handoff), `docs/research/rekordbox_mixer_active_deck_re_evidence.md` (current RE proof), `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` (adversarial RE review handoff) | Runtime implementation is present and software-tested at `0d3aa5c`. `active_deck` is now the resolved show deck selected from Deck 1/2 playing state, decoded upfader, decoded LOW/BASS, `rb_master_deck` tie/fallback, validity/freshness, and stability state; `rb_master_deck` is retained separately. Named mixer offset labels fail closed, mixer reads use finite range-checked f32 instead of the live-BPM float helper, partial/invalid snapshots invalidate authority, and status/heartbeat expose show deck plus Rekordbox master separately. Legacy OSC, playing-only mirror, and `_do_resume()` active-deck bypasses are gated while mixer authority is enabled; invalid/stale mixer fallback is resolver-mediated current valid/fresh `rb_master_deck` fallback only. CFX FILTER is confirmed RE evidence but is non-authority and is not decoded for active-deck authority in this implementation. Static Ghidra/GhidraMCP evidence plus operator-approved passive process-memory proof still applies only to local Rekordbox 7.2.11 mixer chains. Resolver thresholds/stability windows are implementation policy, not RE facts. Versions beyond 7.2.11, actual loaded-track play/stop survival, live runtime observation, SoundSwitch/laser/LED/Govee/DMX/MIDI/Enttec behavior, and hardware-visible behavior remain unvalidated. No bridge restart, additional live capture, process-memory sampling, or hardware action is authorized by the spec alone. |
| AWR-111 | Laser color (CH8/CH9 color control) + blackout re-wire | `docs/plans/active/laser_color_engine_design_spec.md` (expanded design), `docs/architecture/laser_color_authority.md`, `docs/architecture/laser_blackout_authority.md` (operator-authoritative behavior contracts) | Blackout re-wire Package 1 is implemented/software-tested in current worktree: smart-side blackout latches survive pack-backend note rejection and feed the single StateManager pack mask writer alongside manual MIDI-input blackout. CH8/CH9 laser color remains PLANNED / DESIGN-INTENT; only the mapper's CH8/CH9 value table is blocked on operator inputs (fixture profile + live visual validation), and all hardware-visible behavior remains unvalidated. |
| AWR-119 | Stream Deck palette control + drop presentation policy | `docs/plans/active/streamdeck_palette_control_design_spec.md` (expanded design), `docs/architecture/palette_control_authority.md`, `docs/architecture/drop_presentation_authority.md` (operator-authoritative behavior contracts) | PLANNED / DESIGN-INTENT except Package 1 blackout re-wire, which is implemented/software-tested under AWR-111. Palette queue/override-fade/lock, `white_sand`, LED/Laser mute pads, Laser Solo pad + zero-RNG auto-solo tiers (hotcue/learned/gear-shift/record-breaker), finale guarantee, track personality, Rainbow mode, feedback file + pad iconography remain unimplemented. No bridge restart, live process, SoundSwitch, Rekordbox, laser, LED/Govee, MIDI, DMX, Enttec, or hardware action was authorized or performed. |
| AWR-113 | LED Pad + Template Lab (browser UI, banks/editor/lab, output-ownership takeover) | `docs/architecture/led_pad_template_lab_design.md` (authoritative design), `docs/plans/active/led_pad_template_lab_spec.md` (Codex implementation spec, Phases 0–3), `docs/guides/led_pad.md` (operator guide) | Phases 0–3 plus the 2026-07-03 same-day passes (menubar/LaunchAgent, QR access, vendored Alpine + draft/discard, iOS touch, hygiene, stage-console reskin + action hierarchy, editor unset-param defaults) are implemented/software-tested. Audit P2 keeps committed drop-look selection on the same DIY eligibility filter as normal tick automation. Audit P3 keeps realtime-to-cloud handoff transport calls on the Govee runner thread. Full feature ledger: the spec's phase table. All visual/hardware outcomes need operator sign-off. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-116 | 2026-07-03 audit fix queue | `docs/plans/active/audit_2026_07_03_fix_queue_spec.md` | Ordered Codex implementation queue P1-P4. P1-P4 are implemented/software-tested in current `main`: runtime-command truth cleanup, default-off OS2L injector/status truth, Govee handoff/ANLZ/timing/spectral fixes, and laser resilience plus Laser Pad live-toggle truth. Software-only; no bridge restart, live process, SoundSwitch, Rekordbox, laser, LED/Govee, MIDI, DMX, Enttec, or hardware action is authorized by the spec alone. |
| AWR-117 | LED dispatch extraction from `state_manager.py` (audit P5) | `docs/plans/active/led_dispatch_extraction_spec.md` | Implemented/software-tested Codex refactor P1-P2: the five copy-pasted LED trigger/accept/reject bookkeeping paths now route through one helper set, and LED dispatch policy lives in `led_dispatch_policy.py` as a mixin with all `_led_*` fields staying on the `StateManager` instance. Pure refactor — `led_status_provider` payloads, counters, gate reasons, role keys, and log lines are intended to stay byte-identical, covered by the unchanged 2762-test suite. No bridge restart, live process, SoundSwitch, Rekordbox, laser, LED/Govee, MIDI, DMX, Enttec, or hardware action is authorized by the spec alone. |
| AWR-118 | 2026-07-03 audit follow-ups F1/F2 + LED-slice audit (Sonnet session) | `docs/plans/active/audit_2026_07_03_followups_spec.md` | Operator-sanctioned Sonnet implementation lane (Codex quota exhausted). Task A (probe_live_bpm/live_bpm dependency inversion) and Task B (parity oracle relocation + energy_model doc fix) are code changes; Task C is a strictly read-only LED-slice audit report. See spec for status. |

**Closed 2026-06-29:** AWR-101 (LED color engine M2.5), AWR-102 (LED color engine core), AWR-103 (realtime comet), AWR-104 (beat-sync runtime) — operator hardware sign-off on Home Govee. Software work landed (specs in `docs/plans/completed/`); evidence in `docs/validation/hardware_validation_log.md`. AWR-114 (Graphify repo-map integration; renumbered 2026-07-03 — the prior ID was accidentally reused for two workstreams) — local Graphify CLI installed as `graphifyy` 0.9.2 via `pipx`; repo graph is code-only (`258` manifest entries, including root code, `scripts/`, `streamdeck/`, `tests/`, `tools/`, and 3 example JSON configs) with `graphify-out/` gitignored. Hook decision remains manual query only: no PreToolUse/read-interception hooks and no post-commit graph hook. Current workflow is `docs/setup/graphify.md`; completed install prompt moved to `docs/prompts/completed/graphify_install_prompt.md`. No bridge restart, live process, config, device, output, or hardware action was authorized or performed. AWR-105 and AWR-106 remain active (software-done, hardware-pending).

**Closed 2026-07-02:** AWR-112 (SoundSwitch DMX cue parity) — RESOLVED; cue association root-caused (exact-key resolution + precede-associated venue values, `5bb3a5b`) and autoloop divergence root-caused to the window anchor (selection-beat anchor restored). DD42028C remains a negative-control witness. Specs: `docs/plans/completed/soundswitch/soundswitch_pack_parity_root_cause_spec.md`, `.../soundswitch_pack_render_defect.md`, `.../soundswitch_dmx_cue_mismatch_spec.md`; RE evidence: `docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md`.

## Documentation system follow-ups

| ID | Area | Status | Next action |
| --- | --- | --- | --- |
| AWR-001 | Old-doc classification + archive pass | done | `docs/architecture/doc_index.md` classifies all docs. 2026-06-29 sweep: completed SoundSwitch RE-edgecase + publish-sidecar specs → `docs/plans/completed/soundswitch/`, chorus drop-lifecycle revision → `docs/plans/completed/`, RE-edgecase findings → `docs/research/soundswitch/`, deferred laser SM-net spec → `docs/archive/plans/`; spent review/handoff prompts deleted (Git history preserves them). |
| AWR-002 | Untracked govee spec | done | Verified 2026-07-03: file has been tracked since `50f469e`; the registry/index 'untracked' claims were stale and are fixed. |
| AWR-003 | Stray root output files | done | Relocated `cues_output.md` / `cues_timing_output.md` to `docs/data/` (2026-06-29). |
| AWR-004 | First agent-workflow dry run | open — standing follow-up; not yet exercised as of 2026-07-03 despite qualifying feature PRs | Use this system on the next real feature change on `main`; record missing routes, unclear contracts, token-waste points, or hidden branch-state risks. |
| AWR-005 | Runtime command test inventory | open — standing follow-up; not yet exercised as of 2026-07-03 despite qualifying feature PRs | Map parser/handler tests and add missing ones only in a separate code/test PR. |
| AWR-006 | Contract coverage audit | open — standing follow-up; not yet exercised as of 2026-07-03 despite qualifying feature PRs | After a feature PR, tighten `docs/agents/change_contracts.yml` around any files agents had to rediscover. |
| AWR-007 | Active-doc lifecycle check (orphan + stale) | done | Implemented in `tools/check_agent_contracts.py`: orphan coverage (Codex, `574247d`/`1420aad`) + stale-classified flag (direct, 2026-06-29). Record at `docs/plans/completed/docs_orphan_check_spec.md`; tests in `tests/test_docs_orphan_check.py`. Resolved the one live stale instance by deleting the superseded rekordbox continuation prompt (Git preserves). |
| AWR-115 | Agent lessons store | done | Seeded 2026-07-03 with 7 evidence-cited lessons (`docs/agents/lessons/`); add new lessons only with commit-cited evidence. |

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
| HW-004 | Govee/LED phrase-aware active-content hold | deck switch and active-deck track load landing > `1.0` beat into phrase hold the previous look until the next phrase entry; <= `1.0` beat changes immediately; verify no laser/SoundSwitch behavior changes | not logged |

## Compatibility expansion tasks

| ID | Target | Required proof | Status |
| --- | --- | --- | --- |
| COMP-001 | Rekordbox versions beyond my current setup | reader/offset validation plus tests/logs | unknown |
| COMP-002 | macOS versions beyond my current setup | launch/read/status validation | unknown |
| COMP-003 | Windows/Linux | architecture decision, not docs optimism | unsupported/unknown |
