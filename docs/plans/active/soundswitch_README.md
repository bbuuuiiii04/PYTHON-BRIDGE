---
doc_status: active-plan-index
truth_level: code-and-test-grounded-routing
last_verified_commit: 199af0d
last_verified_date: 2026-06-25
validation_scope: SoundSwitch exporter and bridge-native player planning routes; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch exporter / bridge-native DMX - active project index

This is the grouped planning index for AWR-107. Code and tests remain the
implementation authority. Research/format evidence remains grouped under
`docs/research/soundswitch/`.

## Read now, in order

1. `soundswitch_exporter_remaining_work.md` - **single active completion
   checklist and roadmap**. It records landed software, the remaining T7d and
   hardware gates, task order, and completion definition.
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
6. `../../prompts/active/soundswitch_rw7_capture_agent_prompt.md` - the only
   active SoundSwitch execution prompt. Use it only with the operator physically
   present and the explicit live gates it names.
7. `../../validation/soundswitch_hardware_validation_procedure.md` and
   `../../validation/soundswitch_hardware_runs/TEMPLATE.md` - non-Autoloop
   operator procedure and evidence schema with the independent-review revisions
   implemented; fresh implementation review remains pending. Their presence is
   not a hardware-validation result.
8. `../../prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`
   - commit-scoped, review-only ChatGPT handoff for RW-5, the procedure/template,
   and this document-lifecycle cleanup.

The compatibility symlink
`soundswitch_importer_exporter_player_codex_spec.md` remains for older links.

## Physical document layout

| lifecycle | location | contents |
| --- | --- | --- |
| current planning authority | `docs/plans/active/soundswitch_*.md` | roadmap, T7d evidence plan/handoff, compatibility pointers; the separately scoped reconciliation spec is not part of this route |
| current task prompt | `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md` | operator-conducted T7d capture only |
| current review prompt | `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md` | independent review of the current non-live implementation checkpoint |
| material implementation history | `docs/plans/completed/soundswitch/` | old ledger, every implemented SoundSwitch spec, shadow proof |
| current RE authority | `docs/research/soundswitch/` | closure report, format/binary findings, evidence matrices, tool guide, product contract |
| superseded RE history | `docs/research/soundswitch/history/` | intermediate findings, old handoffs, draft specs, Stage-1 scratch |
| active T7d validation | `docs/validation/soundswitch_t7d_*.md` | evidence ledger and blocked report |
| hardware-validation procedure | `docs/validation/soundswitch_hardware_validation_procedure.md`, `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` | reviewed operator sequence/template; no completed hardware evidence |
| cross-subsystem contracts | `docs/subsystems/`, `docs/architecture/`, `docs/setup/`, `docs/status/` | current runtime/config/operator status; these remain in their repo-wide taxonomy |
| tool-local pointer | `tools/ssfmt/re/README.md` | points to the current research tool guide; not a second authority |

Ignored generated proof reports under `artifacts/` or `/tmp` are execution
artifacts, not planning documents. They are not moved into the authority tree.

## Current implementation snapshot

- Decoder/exporter/compiler/verifier: implemented and current-project proof
  passes 29/29.
- Current scripted content: 32/32 active existing-path tracks supported.
- Pure scripted renderer: implemented/software-wire tested.
- Config/startup/runtime command/StateManager/Enttec lane: implemented and
  default-off; RW-2 through RW-5 runtime authority/status work is
  software-tested and does not claim sender/physical state.
- Menubar `Export from SS` plus canonical replacement/reload and combined pack/export row:
  implemented and software-tested.
- Menubar pack on/off toggle + auto-switch by SoundSwitch connection
  (`set_soundswitch_pack action=enable`): implemented and software-tested; no
  implicit hot-enable.
- Static Override Press/Toggle interaction mode decoded from the SoundSwitch-saved
  byte and honored by the bridge MIDI input: implemented and software-tested;
  unknown saved mode fails closed to momentary.
- Canonical pack now lives at the repo-local ignored path
  `local/soundswitch/rbss_canonical_pack`.
- T7d phase tooling: implemented; four captures pass conductor integrity across
  arm/refire, while four scenario pairs and the corpus oracle remain incomplete.
- Native-DMX Autoloop selection: intentionally not implemented; safe-zero.
- Hardware procedure/template: present; no real operator run, so hardware remains unvalidated.

See the remaining-work roadmap for evidence, exact tasks, and acceptance gates.

## Completed/superseded project planning

All completed implementation specs/proofs and the old progress ledger are grouped
under:

```text
docs/plans/completed/soundswitch/
```

They are historical evidence only. Redundant kickoffs, authoring prompts,
session handoffs, and completed review prompts were deleted; Git history remains
their provenance. Do not resume from completed artifacts.

The 2026-06-25 audit retired five more now-landed planning docs into
`docs/plans/completed/soundswitch/`: the menubar pack on/off + auto-switch spec,
the repo-local pack-move handoff, the Static Override Press/Toggle parity spec,
the roadmap/registry reconciliation spec, and the read-only remaining-software
scoping snapshot. Their two authoring/scoping prompts were deleted (Git history
preserves them). The `soundswitch_t7c_pack_driver_spec.md` compatibility pointer
stays active because live code and tests still cite that path.

## Safety boundary

No active planning document authorizes a restart, backend toggle, MIDI/serial
open, Enttec/DMX output, fixture connection, or hardware test. Those actions
remain behind the explicit operator gate in the remaining-work roadmap.
