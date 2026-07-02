---
doc_status: current
truth_level: code-verified
last_verified_commit: 3f4bcc0
last_verified_date: 2026-07-02
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
| AWR-107 | SoundSwitch static exporter / bridge-native player | `docs/plans/active/soundswitch_exporter_remaining_work.md`, `docs/plans/active/soundswitch_perfect_parity_finisher_spec.md`, `docs/plans/active/soundswitch_parity_evidence_finisher_spec.md`, `docs/plans/active/soundswitch_README.md`, `docs/research/soundswitch/README.md`, `docs/architecture/native_autoloop_pack_authority.md`, `docs/plans/active/native_autoloop_dmx_runtime_spec.md`, `docs/plans/active/soundswitch_autoloop_equivalence_oracle_spec.md`, `docs/validation/soundswitch_hardware_validation_procedure.md`, `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | **PARITY EVIDENCE FINISHER STATUS (2026-07-02):** scripted, Autoloop, and Static Look passive-capture registries are implemented; Static Looks are `algorithm_generalized` via the C6 assertion plus unavailable-window fallback; segment-aware Autoloop fixture reduction records capture-diverged non-PASS segments outside the positive registry; supported scripted layout variants generalize only after every positive reference resolves into the current cue set. Fresh export reports active lanes `algorithm_generalized: 69`, `oracle_proven: 14`, `unverified_parity: 0`, so trusted publication is software-gated green; inactive unverified documents remain reported separately. RW-1 through RW-5, graceful shutdown ownership, copied menubar status, connection auto-switch, saved Static Override Press/Toggle mode, required binding-sidecar stage-before-swap publication, native Autoloop DMX, and the non-Autoloop procedure/template are implemented and software-tested. No operator hardware evidence run exists; no live config, restart, runtime command, device, output, or hardware action is authorized unless a task explicitly grants it. SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-112 | SoundSwitch DMX cue parity | `docs/plans/active/soundswitch_pack_parity_root_cause_spec.md`, `docs/plans/active/soundswitch_pack_render_defect.md`, `docs/plans/active/soundswitch_dmx_cue_mismatch_spec.md` (baseline / negative-control) | **BASELINE — audit target (2026-07-01 runtime reframe).** The live U0/U1 capture (`tools/ssfmt/captures/parity/parity_20260701T185231Z`) INDICATES the exporter/pack content is faithful and parity is blocked by 3 RUNTIME bugs — scripted render zero-blip flicker (= the ~17% mismatch), static MIDI trigger authority, autoloop phase/SSAutoLoop4 selection — NOT a cue-composition mechanism. That reframe is TO BE PROVEN by the Fable finisher (`docs/prompts/active/soundswitch_perfect_parity_fable5_prompt.md`), which audits this spec as its baseline and supersedes it only if the reframe holds. DD42028C is EXCLUDED from operator performance/parity coverage but RETAINED as a negative-control witness (not erased). Prior investigation retained below as the baseline evidence: ROOT CAUSE UPDATED AGAIN. The scripted playback-mixer theory is rejected by operator ground truth and current evidence. The real shared issue is global: the exporter/importer publishes `.ssfile` cue replay from `raw_reference -> raw-1 -> cue GUID` and the verifier proves only that same internal model, not SoundSwitch U0 parity. DD42028C is the first concrete witness that this can resolve/compose wrong cue content while the bridge renders its loaded pack exactly. The 2026-07-01 callable GhidraMCP pass confirmed the arm64 `.ssfile` reader/cache shape and rejected an addressed-footer/prefix/shared-byte cue remap in the inspected path, but it did not find the exact DD42028C saved-byte/runtime mechanism. Simple key offsets are rejected (`raw-1` still best at 69/91 nearest-U0 matches; direct is 27/91). The ignored local canonical pack is patched with capture-derived `oracle_rendered` boundary frames, but that is containment only: it improves first-lit nearest-U0 boundary matching from 69/91 to 81/91 and regresses boundary 10, so it is not a root fix. The current pack has 32 active scripted tracks: DD42028C confirmed affected; the other 31 are unproven until structural proof or U0-oracle proof exists. Active Autoloops have separate confirmed residual oracle mismatches; Static Looks use a separate generic-attribute path and have software/binary evidence but no completed U0/U1 Static Look live parity run. Runtime pack driver corruption/dropout is retracted. No bridge restart, runtime toggle, SoundSwitch export click, canonical-pack overwrite, process-memory sampling, Enttec/DMX, laser, LED/Govee, Rekordbox, or hardware action is authorized by this spec. SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-108 | Laser drop/post-drop lifecycle mirror | `docs/plans/active/chorus_drop_cycling_spec.md` | Tasks 1-5 and Part D are implemented and software-tested at `9918dd4` and `ed78263`. Live LED behavior is unchanged. Laser hardware/SoundSwitch observation and kill-switch rehearsal remain pending; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-109 | Stream Deck MIDI controller / layered static-look compositor | `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` (Phase 1 implemented; Part F Phase 2 spec), `docs/prompts/active/streamdeck_phase2_codex_implementation_prompt.md` (implementation handoff), `docs/plans/active/streamdeck_phase2_plan_review.md` and `docs/plans/active/streamdeck_phase2_codex_review_prompt.md` (review evidence) | Phase 1 controller lifecycle hardening is implemented in current `main`. Phase 2 is a revised implementation plan only: generic layered DMX compositor, lock-free hot-path snapshots, worker-thread input-port-gone recovery, pure render path, sibling binding sidecar, and local controller LED state. No bridge restart, controller smoke, Enttec/DMX, fixture, or live hardware action is authorized. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| AWR-110 | Rekordbox mixer active-deck authority | `docs/architecture/active_deck_authority.md` (operator-authoritative target behavior), `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md` (Ghidra/Ghidra-MCP RE + implementation handoff), `docs/research/rekordbox_mixer_active_deck_re_evidence.md` (current RE proof), `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md` (adversarial RE review handoff) | Runtime implementation is present and software-tested at `0d3aa5c`. `active_deck` is now the resolved show deck selected from Deck 1/2 playing state, decoded upfader, decoded LOW/BASS, `rb_master_deck` tie/fallback, validity/freshness, and stability state; `rb_master_deck` is retained separately. Named mixer offset labels fail closed, mixer reads use finite range-checked f32 instead of the live-BPM float helper, partial/invalid snapshots invalidate authority, and status/heartbeat expose show deck plus Rekordbox master separately. Legacy OSC, playing-only mirror, and `_do_resume()` active-deck bypasses are gated while mixer authority is enabled; invalid/stale mixer fallback is resolver-mediated current valid/fresh `rb_master_deck` fallback only. CFX FILTER is confirmed RE evidence but is non-authority and is not decoded for active-deck authority in this implementation. Static Ghidra/GhidraMCP evidence plus operator-approved passive process-memory proof still applies only to local Rekordbox 7.2.11 mixer chains. Resolver thresholds/stability windows are implementation policy, not RE facts. Versions beyond 7.2.11, actual loaded-track play/stop survival, live runtime observation, SoundSwitch/laser/LED/Govee/DMX/MIDI/Enttec behavior, and hardware-visible behavior remain unvalidated. No bridge restart, additional live capture, process-memory sampling, or hardware action is authorized by the spec alone. |
| AWR-111 | Laser color (CH8/CH9 color control) | `docs/plans/active/laser_color_engine_design_spec.md` | PLANNED / DESIGN-INTENT — **not implemented**; blocked on operator capture of CH8/CH9 laser channel behavior (VirtualLaserNode). Authored pre-handoff in PR #111 but never registered until 2026-06-29. Verify against code before any implementation. |

**Closed 2026-06-29:** AWR-101 (LED color engine M2.5), AWR-102 (LED color engine core), AWR-103 (realtime comet), AWR-104 (beat-sync runtime) — operator hardware sign-off on Home Govee. Software work landed (specs in `docs/plans/completed/`); evidence in `docs/validation/hardware_validation_log.md`. AWR-112 (Graphify repo-map integration) — local Graphify CLI installed as `graphifyy` 0.9.2 via `pipx`; repo graph is code-only (`258` manifest entries, including root code, `scripts/`, `streamdeck/`, `tests/`, `tools/`, and 3 example JSON configs) with `graphify-out/` gitignored. Hook decision remains manual query only: no PreToolUse/read-interception hooks and no post-commit graph hook. Current workflow is `docs/setup/graphify.md`; completed install prompt moved to `docs/prompts/completed/graphify_install_prompt.md`. No bridge restart, live process, config, device, output, or hardware action was authorized or performed. AWR-105 and AWR-106 remain active (software-done, hardware-pending).

## Documentation system follow-ups

| ID | Area | Status | Next action |
| --- | --- | --- | --- |
| AWR-001 | Old-doc classification + archive pass | done | `docs/architecture/doc_index.md` classifies all docs. 2026-06-29 sweep: completed SoundSwitch RE-edgecase + publish-sidecar specs → `docs/plans/completed/soundswitch/`, chorus drop-lifecycle revision → `docs/plans/completed/`, RE-edgecase findings → `docs/research/soundswitch/`, deferred laser SM-net spec → `docs/archive/plans/`; spent review/handoff prompts deleted (Git history preserves them). |
| AWR-002 | Untracked govee spec | open | Classify `docs/plans/completed/govee_realtime_codex_spec.md` (completed vs awaiting-build) and commit or archive it in a separate change. |
| AWR-003 | Stray root output files | done | Relocated `cues_output.md` / `cues_timing_output.md` to `docs/data/` (2026-06-29). |
| AWR-004 | First agent-workflow dry run | active | Use this system on the next real feature change on `main`; record missing routes, unclear contracts, token-waste points, or hidden branch-state risks. |
| AWR-005 | Runtime command test inventory | active | Map parser/handler tests and add missing ones only in a separate code/test PR. |
| AWR-006 | Contract coverage audit | active | After a feature PR, tighten `docs/agents/change_contracts.yml` around any files agents had to rediscover. |
| AWR-007 | Active-doc lifecycle check (orphan + stale) | done | Implemented in `tools/check_agent_contracts.py`: orphan coverage (Codex, `574247d`/`1420aad`) + stale-classified flag (direct, 2026-06-29). Record at `docs/plans/completed/docs_orphan_check_spec.md`; tests in `tests/test_docs_orphan_check.py`. Resolved the one live stale instance by deleting the superseded rekordbox continuation prompt (Git preserves). |

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
