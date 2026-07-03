---
doc_status: completed-spec
truth_level: code-grounded-design-spec
last_verified_commit: ab4d293
last_verified_date: 2026-06-24
validation_scope: SoundSwitch roadmap, registry, routing, and status-doc reconciliation only; no runtime/test/config/live/hardware changes; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED unless a committed run record proves a narrower local result
---

# Codex Implementation Spec - SoundSwitch Roadmap and Registry Reconciliation

## Part A - Context & root cause (verified; read, do not implement)

- [confirmed] RW-1 export/replace/reload is implemented in the current menubar and tool. The
  independent review produced a concrete follow-up spec and landed conservative reload/recovery
  fixes (`docs/plans/active/soundswitch_rw1_export_fixes_spec.md:9-20`,
  `scripts/bridge_menubar.py:831-881`). The active registry already calls RW-1 independently
  reviewed (`docs/status/active_work_registry.md:25`), while the roadmap still says review pending
  (`docs/plans/active/soundswitch_exporter_remaining_work.md:163-164`,
  `docs/plans/active/soundswitch_exporter_remaining_work.md:265-324`).
- [confirmed] RW-3 now requires bridge-owned scripted identity before selecting a scripted frame,
  binds pause hold to the full played identity, and clears otherwise
  (`state_manager.py:3363-3416`). The targeted regression suite passed during this spec pass.
- [confirmed] A later current handoff records RW-3 independent review as `APPROVE`
  (`docs/prompts/active/soundswitch_rw4_input_health_spec_authoring_prompt.md:19-34`). The roadmap,
  registry, and doc index still route RW-3 as review-pending/active
  (`docs/plans/active/soundswitch_exporter_remaining_work.md:360-386`,
  `docs/status/active_work_registry.md:25`, `docs/architecture/doc_index.md:89-90`).
- [confirmed] RW-4 is implemented at current HEAD. The driver reads all health fields directly,
  latches degradation, drops static/blackout only, preserves the scripted base, and fails the whole
  frame to zero on malformed input (`state_manager.py:3293-3345`, `state_manager.py:3420-3427`).
  The runtime-swap static-slot resync fix landed at `ef46de1` (`state_manager.py:3247-3265`).
- [confirmed] The kickoff records RW-4's independent approval at `ef46de1`. No standalone review
  verdict artifact is present, so reconciliation must cite the operator-supplied approval and the
  implementation/test evidence without inventing reviewer details.
- [confirmed] The roadmap still says RW-4 health is ignored and requires whole-output fail-to-zero
  work (`docs/plans/active/soundswitch_exporter_remaining_work.md:388-417`). That contradicts both
  code and the accepted overlay-only policy.
- [confirmed] `soundswitch_README.md` still says menubar export is not implemented and RW-2/3/4
  remain gaps (`docs/plans/active/soundswitch_README.md:62-74`). The subsystem card likewise lists
  pause, mode, and health as active gaps (`docs/subsystems/soundswitch_output.md:27-30`).
- [confirmed] Hardware evidence is still absent at this spec point, and native Autoloop DMX remains
  intentionally unimplemented (`docs/status/active_work_registry.md:45`,
  `docs/status/active_work_registry.md:64`, `state_manager.py:3409-3419`).

**Root cause [confirmed].** RW-1/RW-3/RW-4 landed in separate implementation/review passes, but the
single roadmap and its routing/status mirrors were not reconciled afterward. The stale docs now
describe removed gaps and the wrong RW-4 safety policy.

## Part B - Tasks (implement exactly, in order)

### Absolute rules

- Docs-only. Do not edit Python, tests, config, scripts, local ignored files, runtime state, or
  hardware evidence.
- Re-resolve every line anchor against the implementation HEAD. Code/tests win.
- Do not mark RW-5 done until its implementation commit and tests exist.
- Do not mark HW-001/ROAD-003 done unless a committed run under
  `docs/validation/soundswitch_hardware_runs/` supports the exact bounded claim.
- Keep T7d capture, phase/origin derivation, identity/holdout reconciliation, and native Autoloop
  DMX unchanged and blocked/out of this reconciliation.
- Preserve SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED except for a narrowly worded local
  hardware result backed by a real run record.

### Task 1 - Reconcile the authoritative roadmap

Update `docs/plans/active/soundswitch_exporter_remaining_work.md`:

1. Advance its verification baseline/date to the implementation evidence actually checked.
2. In the completion matrix:
   - mark menubar export and canonical replacement implemented, software-tested, and independently
     reviewed;
   - mark RW-2/RW-3/RW-4 scripted driver and input integration implemented/software-tested;
   - describe RW-4 as manual-overlay fail-to-released, not whole-output fail-to-zero;
   - leave RW-5 pending until its implementation evidence exists;
   - leave hardware and native Autoloop rows bounded to actual evidence.
3. RW-1: change review-pending to reviewed/closed; cite the original implementation commits, review
   fix spec, landed review fixes, change-detection commits/tests, and current menubar behavior.
4. RW-3: mark status and four checkboxes complete; cite implementation range
   `6fdef84..4ffe7c8`, current code anchors, targeted tests, and the recorded independent approval.
5. RW-4: replace the stale section with the shipped policy and mark every implemented requirement
   complete. State exactly:
   - degraded input releases held Static Look and controller blackout only;
   - the scripted base continues;
   - the unified latch clears only after a clean, quiet, healthy snapshot;
   - the latch survives runtime swaps (Option B);
   - malformed snapshots still fail the whole frame to zero;
   - `ef46de1` closes same-slot resync on a fresh runtime.
6. RW-5: link `soundswitch_rw5_operational_status_spec.md` and keep it as the remaining unblocked
   software implementation item unless its code/tests have since landed.
7. Hardware gate: link `soundswitch_hardware_validation_harness_spec.md`; update only from a real
   run record if one exists.
8. Milestone M2: show RW-2/RW-3/RW-4 complete and RW-5 pending/complete according to current code.
   Remove the stale whole-output fail-to-zero language.
9. Replace §10's stale “next task is RW-1 review” with the actual next executable item. After these
   specs are authored, priority is the operator-gated hardware procedure, then RW-5 implementation;
   if one has already completed, select the remaining item from current evidence.
10. Do not change the project-complete gates for T7d/native Autoloop. Mark only gates with actual
    evidence complete.

### Task 2 - Reconcile registry, project index, and subsystem/status mirrors

Update only the current truth/routing surfaces that repeat the stale claims:

- `docs/status/active_work_registry.md` AWR-107: link the three new specs; close RW-1/RW-3/RW-4;
  leave RW-5, hardware, and T7d/native Autoloop at their verified state.
- `docs/plans/active/soundswitch_README.md`: remove “menubar not implemented” and pause/mode/health
  gap claims; route the new hardware, RW-5, and reconciliation specs in current order.
- `docs/subsystems/soundswitch_output.md`: replace its stale active-gap paragraph with RW-1-4 landed,
  RW-5/hardware status, and the unchanged native-Autoloop safe-zero boundary.
- `docs/architecture/doc_index.md`: list the three new specs. Reclassify RW-1/RW-3/RW-4 prompts and
  specs as completed evidence where appropriate; do not call an already-consumed prompt active.
- `docs/prompts/reviews/soundswitch_exporter_remaining_work_adversarial_review_prompt.md`: update
  only status assumptions that would make a fresh roadmap review start from known-false RW-1/3/4
  claims.
- Contract-required status/validation mirrors (`feature_status_matrix.md`,
  `validation_matrix.md`, `known_limitations.md`, `hardware_validation_log.md`) only where they
  repeat these claims. Hardware rows remain unchanged without a run record.

Do not move/delete prompts or specs in this pass. Reclassifying them in routing tables is enough;
physical lifecycle cleanup can happen only if it is separately requested and all links/contracts are
updated.

### Task 3 - Review evidence language

Use these bounded forms:

- RW-1: `[confirmed] implemented, software-tested, independently reviewed; hardware-unvalidated`.
- RW-3: `[confirmed] implemented and software-tested at 4ffe7c8; independent APPROVE recorded by
  the subsequent RW-4 handoff; hardware-unvalidated`.
- RW-4: `[confirmed] implemented/software-tested through ef46de1; independent approval supplied by
  the operator kickoff; hardware-unvalidated`.

Do not invent reviewer name, review date, hardware result, or compatibility claim. If a stronger
durable review artifact appears before implementation, cite it instead.

## Part C - Invariants that MUST still hold (live safety)

- This pass cannot alter runtime behavior, tests, config, process state, or hardware state.
- RW-4 degraded-controller behavior is documented as overlay-only release; do not reintroduce the
  rejected whole-output-zero wording.
- Malformed snapshot -> whole-frame zero remains distinct from ordinary degraded input -> scripted
  base continues.
- RW-1A shutdown zero, RW-2 transport, RW-3 authority, RW-4 latch/Option B, manual Static Override,
  and default-off posture remain unchanged.
- Existing OS2L, laser, LED/Govee, Rekordbox-reader, and menubar behavior is only described, never
  modified.
- Native Autoloop DMX remains safe-zero and T7d remains capture-blocked.

## Part D - Verification

Run the smallest current-code proof needed before editing, then the docs gates after editing:

```bash
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_bridge_menubar
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Run `python3 -m unittest discover tests` if RW-5 or the hardware harness landed before this
reconciliation and the touched status docs summarize their broader evidence. Staleness is advisory,
but every touched contract doc must be deliberately re-verified against the implementation-evidence
commit; do not point it at a later docs-only commit merely to silence the report.

## Part E - Acceptance

- [ ] Roadmap, AWR-107, SoundSwitch README, subsystem card, and doc index agree on RW-1/RW-3/RW-4.
- [ ] All stale RW-3/RW-4 checkboxes are corrected from current code/tests.
- [ ] RW-4 wording says degraded input drops only the manual overlay; malformed input alone fails
      the whole pack frame to zero.
- [ ] RW-1 export/replace/reload is no longer review-pending.
- [ ] RW-5 and hardware status reflect only evidence that exists when this spec is executed.
- [ ] T7d/native-Autoloop status and completion gates remain out of scope and blocked.
- [ ] No runtime/test/config/live files changed.
- [ ] Three hard docs checks pass, staleness is reviewed, and `git diff --check` is clean.

## Pre-handoff checklist

1. Claims are labeled; the missing standalone RW-4 verdict artifact is disclosed.
2. File/line claims were checked at `ab4d293`; implementation must re-anchor at its HEAD.
3. Pending-state interactions are documented by separating input degradation from scripted activity.
4. RW-3/RW-4 runtime-swap and recovery paths are represented, not just happy paths.
5. No third-party API or live command is added.
6. Existing code/test authorities and commit ranges are reused.
7. No algorithm is introduced; targeted tests are the executable proof seam.
8. Docs-only/live-safety and hardware/T7d boundaries are explicit.
9. Adversarial case: a blanket “RW-4 fail-to-zero” edit would contradict live code and black the
   documented scripted base; the required two-case wording prevents that regression.

## When you finish

Report every reconciled file, RW-1/RW-3/RW-4 evidence used, the current RW-5/hardware/T7d boundary,
hard-check results, advisory staleness result, and confirmation that no process/restart/config/device/
hardware action occurred. Include the plain-language operator summary required by `AGENTS.md`.
