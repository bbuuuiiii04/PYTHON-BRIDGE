---
doc_status: active-plan-index
truth_level: code-and-test-grounded-routing
last_verified_commit: 7d9ecdc
last_verified_date: 2026-07-10
validation_scope: SoundSwitch exporter and bridge-native player planning routes; AWR-186 USB gate-fix (Enttec positive-identity port detection in enttec_dmx_pro.find_enttec_port + make_stick pack-config fail-closed) software-tested 2026-07-10 — no behavior change in this doc's scope, no hardware action; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch exporter / bridge-native DMX - active project index

This is the grouped planning index for AWR-107. Code and tests remain the
implementation authority. Research/format evidence remains grouped under
`docs/research/soundswitch/`.

## Read now, in order

1. `soundswitch_exporter_remaining_work.md` - **single active completion
   checklist and roadmap**. As of the 2026-07-02 software finalization pass
   the software side is complete (values byte-proven, selection-beat autoloop
   anchor, idle manual overlay, scrub latch, sibling-load guard,
   edited-witness auto-retire); the remaining gate is the operator's live
   hardware run.
2. `../../research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md`
   plus `../../research/soundswitch/soundswitch_truth_exam_live_blockers_2026_07_02.md`,
   `soundswitch_live_capture_findings_2026_07_02_evening.md`, and
   `soundswitch_time_domain_exam_2026_07.md` - the durable evidence base for
   the finalization pass (mechanism proofs, live capture findings, timing
   analysis). Historical evidence, already acted on.
3. `../../research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`
   - original product/implementation contract. Use it for intended behavior,
   then use the remaining-work roadmap for actual landed status.
4. `../../validation/soundswitch_hardware_validation_procedure.md` and
   `../../validation/soundswitch_hardware_runs/TEMPLATE.md` - operator
   procedure and evidence schema for the one remaining gate. Their presence is
   not a hardware-validation result.

Capture/exam-era plans, prompts, and the parity-investigation lineage
(truth-exam prompts, finisher specs, capture orchestration, T7d evidence plan,
equivalence-oracle spec, DD42028C root-cause/containment records) are retired
to `docs/plans/completed/soundswitch/` and `docs/prompts/completed/`. They are
kept for future truth checks, not current routing. The Art-Net truth-check
runtime lane stays in the bridge, default-off, opt-in per launch via
`RBSS_BRIDGE_TRUTH=1` on the watcher.

The compatibility symlink
`soundswitch_importer_exporter_player_codex_spec.md` remains for older links.

## Physical document layout

| lifecycle | location | contents |
| --- | --- | --- |
| current planning authority | `docs/plans/active/soundswitch_*.md` | roadmap, product-contract pointer; the separately scoped reconciliation spec is not part of this route |
| current task prompt | none | software side complete; the remaining gate is the operator hardware run |
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

- Decoder/exporter/compiler/verifier: implemented. Live export performs a
  dynamic saved-project rescan; the old closure-count gate is proof-only.
- Current parity evidence lanes: the passive SoundSwitch U0 capture
  `parity_20260701T185231Z` feeds scripted, Autoloop, and Static Look registry
  fixtures. Static Looks are now `algorithm_generalized` through the documented
  unavailable-window fallback plus the C6 non-generic assertion. Segment-aware
  Autoloop reduction plus supported-layout-family scripted generalization now
  reports fresh active lanes `algorithm_generalized: 67`, `oracle_proven: 16`,
  `unverified_parity: 0`; trusted publication is software-gated green.
- Pure scripted renderer: implemented/software-wire tested.
- Config/startup/runtime command/StateManager/Enttec lane: implemented and
  default-off; RW-2 through RW-5 runtime authority/status work is
  software-tested and does not claim sender/physical state. StateManager ordinary
  loop exceptions preserve the 200 Hz throttle and submit at most one pack ZERO
  for the failed iteration.
- Menubar `Export from SS` plus canonical replacement/reload and combined pack/export row:
  implemented and software-tested.
- Menubar auto-switch by SoundSwitch connection (`set_soundswitch_pack
  action=enable`): implemented and software-tested, including one bounded retry
  after a fresh disconnected `pack_start_failed`; no manual pack button and no
  implicit hot-enable.
- Audit P2 makes file-driven OS2L injection opt-in and adds copied
  `soundswitch_pack.overlay_suppressed` diagnostics under SoundSwitch-connected
  ZERO suppression.
- Static Override Press/Toggle interaction mode decoded from the SoundSwitch-saved
  byte and honored by the bridge MIDI input: implemented and software-tested;
  unknown saved mode fails closed to momentary. Static-controller input is
  auto-bound from pack bindings unless an alias overrides it; missing or
  ambiguous input degrades manual Static Looks without disabling pack DMX.
- Canonical pack now lives at the repo-local ignored path
  `local/soundswitch/rbss_canonical_pack`.
- T7d phase tooling: implemented and historical; four captures pass conductor
  integrity across arm/refire, while four scenario pairs and the corpus oracle
  remain incomplete. This no longer blocks the bridge-owned native path.
- Native-DMX Autoloop selection: implemented/software-tested through canonical
  pack note bindings, 32-beat phase at 600 ticks/beat, `phase_offset_beats`, and
  the existing pack driver. Existing scout oracle reports show Autoloop residual
  mismatches separate from the DD42028C scripted-boundary defect; live/runtime
  and hardware validation remain open.
- Art-Net truth-check gate: implemented/software-tested as a temporary
  default-off U1 shadow-output comparator path. It requires
  `RBSS_ARTNET_TRUTH_CHECK=1` plus a valid universe, opens no Enttec/serial, and
  does not replace SoundSwitch U0 as final-exam authority.
- Hardware procedure/template: present; latest software/wire review complete;
  no real operator run, so hardware remains unvalidated.

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
`docs/plans/completed/soundswitch/`: the menubar auto-switch spec,
the repo-local pack-move handoff, the Static Override Press/Toggle parity spec,
the roadmap/registry reconciliation spec, and the read-only remaining-software
scoping snapshot. Their two authoring/scoping prompts were deleted (Git history
preserves them). The `soundswitch_t7c_pack_driver_spec.md` compatibility pointer
stays active because live code and tests still cite that path.

## Safety boundary

No active planning document by itself authorizes a restart, backend toggle,
MIDI/serial open, Enttec/DMX output, fixture connection, or hardware test. Those
actions remain behind explicit operator approval or a task prompt that grants
that authority.
