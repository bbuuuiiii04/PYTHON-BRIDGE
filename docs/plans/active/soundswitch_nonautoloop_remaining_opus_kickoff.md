# Opus 4.8 kickoff — spec the remaining NON-AUTOLOOP SoundSwitch work

doc_status: active-plan
validation_scope: planning/spec authoring kickoff; no code changes; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED

## Role
You are Claude (Opus 4.8) doing analysis + spec authoring for `rb_ss_bridge_v2`. **Claude specs;
Codex implements bridge core.** Obey `AGENTS.md` (source-of-truth order: code > tests > config >
runtime status > tree > docs; if a doc conflicts with code, **code wins**) and `CLAUDE.md`. Verify
before asserting; label every claim **confirmed / assumed / unknown**; live-safety first; work on
`main` (no branches). Use the `codex-spec` skill for every spec you author and run its 9-point
pre-handoff checklist on each.

## Goal
Produce Codex-ready implementation specs (operator Part A–E format) for the remaining SoundSwitch
pack/exporter work that **does NOT depend on autoloop reverse-engineering capture**. The operator is
ready to perform hardware validation, so prioritize that.

## Context (verify against current code — the roadmap doc is partly stale)
- RW-1 (one-click export/replace/reload), RW-1A (shutdown-zero), RW-2 (pause-vs-stop), RW-3 (mode
  authority), RW-4 (controller-input health) are implemented + software-tested. **RW-4 was
  independently reviewed and APPROVED at commit `ef46de1`** (the static-slot runtime-swap resync fix;
  see `docs/plans/active/rw4_static_slot_swap_resync_spec.md`).
- Pack player → Enttec/DMX / SoundSwitch OS2L lane exists in software; **no repeatable hardware
  evidence exists** (HW-001 / ROAD-003 / "Hardware gate" = not started).
- RW-4 operator policy (so you reconcile the docs correctly): a degraded controller drops only the
  **manual overlay** (held Static Look + blackout forced released) and **keeps the scripted base
  running**; it fails CLOSED to ZERO only on a malformed snapshot. This DIVERGES from the original
  RW-4 "fail-to-zero" wording — reconcile, don't re-litigate.

## Scope IN (spec these; verify each against CURRENT code first, cite file:line)
1. **Hardware-validation harness + repeatable evidence procedure** (HIGHEST priority — operator is
   ready). The pack player → frame sender → Enttec DMX Pro / SoundSwitch OS2L path, run by the
   operator on real fixtures via the menubar bridge. It is a **procedure + evidence schema**, not
   pure software. Define: pre-checks (exactly one bridge process; config present), safe enable
   sequence, per-fixture expected-vs-observed table, an operator-controlled **blackout/emergency
   rehearsal**, and a repeatable in-repo evidence log location + format (feeds HW-001 / ROAD-003).
   The spec must keep all serial/DMX/hardware actions **operator-gated** — it must NOT instruct any
   agent to open serial/DMX/hardware or auto-enable output.
2. **RW-5 — operational status + menubar visibility.** A sanitized, bounded status schema that
   distinguishes at least `scripted_active`, `input_degraded`, `static_held`, `blackout`,
   `autoloop_phase_blocked`, `disabled`; plus a concise menubar pack/export status row + export
   progress. Status must be **snapshot/copied-state sourced**, non-blocking, never call providers from
   the surface. (Reporting `autoloop_phase_blocked` does NOT need autoloop capture — native autoloop
   DMX is safe-zero by design, so this is implementable now.)
3. **Roadmap/registry reconciliation + closeouts (doc-only, code wins).** Mark RW-4 done (reviewed at
   `ef46de1`); close RW-3 review + roadmap; resolve RW-1 export-from-SS / replace-in-place
   review-pending; fix the stale RW-3/RW-4 checkboxes in
   `docs/plans/active/soundswitch_exporter_remaining_work.md`; reconcile the RW-4 "fail-to-zero"
   wording with the shipped overlay-only policy above. Run the `tools/check_docs_*.py` hard checks.

## Scope OUT (do NOT spec — depends on autoloop RE capture or deferred by design)
- T7d live phase evidence / capture-tooling derivation (blocked on operator autoloop captures).
- Native-DMX Autoloop driver (`StateManager` never calls `select_autoloop`; base stays zero by design).
- Anything requiring autoloop quantizer/scale/origin selection or identity/holdout reconciliation.

## Authoritative inputs (read; verify against code; old prompts/plans are historical evidence only)
- `AGENTS.md`, `CLAUDE.md`.
- `docs/status/active_work_registry.md` → AWR-107 (current SS status), ROAD-003, HW-001.
- `docs/plans/active/soundswitch_exporter_remaining_work.md` (roadmap — RW-3/RW-4 sections are STALE).
- `docs/plans/active/soundswitch_rw4_input_health_spec.md`, `rw4_static_slot_swap_resync_spec.md`.
- `docs/plans/active/soundswitch_t7d_capture_*` (this is the autoloop boundary → out of scope).
- Code: `soundswitch_pack_runtime.py` (`PackRuntime.sanitized_status`), `state_manager.py`
  (`_drive_pack_output`, `get_pack_status`, `set_pack_runtime`), `soundswitch_pack_controller.py`,
  the frame sender + `enttec_dmx_pro.py` (DMX lane), `runtime_status.py` + the menubar status surface.

## Method / deliverable
1. First emit a short **verified status map**: for each in-scope item, confirmed/assumed/unknown vs
   current code with file:line, and flag any doc-vs-code drift you find.
2. Then author one Part A–E spec per in-scope workstream into `docs/plans/active/<slug>_spec.md` via
   the `codex-spec` skill, running the 9-point checklist on each. **Hardware-validation harness spec
   first.**
3. Every spec: pure-function test seam wherever there's an algorithm; explicit Part C live-safety
   invariants — push loop stays lockless / non-blocking / no I/O; never regress scripted base, the
   RW-4 latch / Option B, RW-1A shutdown-zero, or the manual Static Override policy; hardware specs
   include an operator-controlled blackout/kill path and never auto-enable output.
4. Status language per `AGENTS.md` §10 (no "production-ready"/"hardware-validated" until matrices
   prove it).

## Report back
The verified status map, the list of spec files created, and which one the operator should run/hand
to Codex first (expected: the hardware-validation procedure).
