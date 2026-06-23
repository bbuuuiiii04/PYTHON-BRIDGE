---
doc_status: active-plan-index
truth_level: code-and-test-grounded-routing
last_verified_commit: 0c2ba07
last_verified_date: 2026-06-23
validation_scope: SoundSwitch exporter and bridge-native player planning routes; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch exporter / bridge-native DMX - active project index

This is the grouped planning index for AWR-107. Code and tests remain the
implementation authority. Research/format evidence remains grouped under
`docs/research/soundswitch/`.

## Read now, in order

1. `soundswitch_exporter_remaining_work.md` - **single active completion
   checklist and roadmap**. It records what is implemented, the confirmed
   scripted-runtime gaps, the menubar/export gap, T7d dependencies, task order,
   gates, and completion definition.
2. `../../research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`
   - original product/implementation contract. Use it for intended behavior,
   then use the remaining-work roadmap for actual landed status.
3. `soundswitch_t7d_capture_evidence_plan.md` - T7d evidence requirements. No
   phase mapping is selected by this plan.
4. `soundswitch_t7d_capture_gate_handoff.md` - active operator workflow for the
   six live scenarios: arm, refire, master-switch, drop-hold, buildup, and
   correction.
5. `../../validation/soundswitch_t7d_phase_contract_evidence.md` and
   `../../validation/soundswitch_t7d_phase_contract_blocked.md` - current honest
   evidence verdict: `INCOMPLETE_T7D_EVIDENCE`; two accepted arm and two
   accepted refire integrity captures exist, while four scenario pairs and the
   unique corpus oracle remain incomplete.
6. `../../prompts/active/soundswitch_t7d_resume_handoff.md` - use only when the
   operator is physically present to run the T7d capture session.
7. `../../prompts/active/soundswitch_rw1_export_from_ss_design_prompt.md` -
   ready-to-send Opus prompt for the next design/spec task. Scope is RW-1 only;
   it authorizes no implementation or live action.
8. `../../prompts/reviews/soundswitch_exporter_remaining_work_adversarial_review_prompt.md`
   - independent Opus review prompt that tries to disprove this roadmap before
   it is used as implementation authority.

The compatibility symlink
`soundswitch_importer_exporter_player_codex_spec.md` remains for older links.

## Physical document layout

| lifecycle | location | contents |
| --- | --- | --- |
| current planning authority | `docs/plans/active/soundswitch_*.md` | roadmap, T7d evidence plan/handoff, compatibility pointers |
| current task/review prompts | `docs/prompts/active/soundswitch_*.md`, `docs/prompts/reviews/soundswitch_*.md` | RW-1 Opus design prompt, T7d resume prompt, roadmap adversarial-review prompt |
| material implementation history | `docs/plans/completed/soundswitch/` | old ledger, implemented specs, shadow proof |
| current RE authority | `docs/research/soundswitch/` | closure report, format/binary findings, evidence matrices, tool guide, product contract |
| superseded RE history | `docs/research/soundswitch/history/` | intermediate findings, old handoffs, draft specs, Stage-1 scratch |
| active T7d validation | `docs/validation/soundswitch_t7d_*.md` | evidence ledger and blocked report |
| cross-subsystem contracts | `docs/subsystems/`, `docs/architecture/`, `docs/setup/`, `docs/status/` | current runtime/config/operator status; these remain in their repo-wide taxonomy |
| tool-local pointer | `tools/ssfmt/re/README.md` | points to the current research tool guide; not a second authority |

Ignored generated proof reports under `artifacts/` or `/tmp` are execution
artifacts, not planning documents. They are not moved into the authority tree.

## Current implementation snapshot

- Decoder/exporter/compiler/verifier: implemented and current-project proof
  passes 29/29.
- Current scripted content: 32/32 active existing-path tracks supported.
- Pure scripted renderer: implemented/software-wire tested.
- Config/startup/runtime command/StateManager/Enttec lane: implemented,
  default-off, but scripted runtime pause/mode/input-health/status gaps remain.
- Menubar `Export from SS` plus canonical replacement/reload: not implemented.
- T7d phase tooling: implemented; four captures pass conductor integrity across
  arm/refire, while four scenario pairs and the corpus oracle remain incomplete.
- Native-DMX Autoloop selection: intentionally not implemented; safe-zero.
- Hardware validation: absent.

See the remaining-work roadmap for evidence, exact tasks, and acceptance gates.

## Completed/superseded project planning

Completed implementation specs/proofs and the old progress ledger are grouped
under:

```text
docs/plans/completed/soundswitch/
```

They are historical evidence only. Redundant completed session handoffs,
orchestration prompts, and the superseded readiness-review prompt were deleted;
git history remains their provenance. Do not resume from completed artifacts.

## Safety boundary

No active planning document authorizes a restart, backend toggle, MIDI/serial
open, Enttec/DMX output, fixture connection, or hardware test. Those actions
remain behind the explicit operator gate in the remaining-work roadmap.
