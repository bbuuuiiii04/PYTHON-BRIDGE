# SoundSwitch pack-player — planning & spec doc set (grouped index)

> **Status:** ACTIVE INDEX (AWR-107). Repo status **SOFTWARE-VALIDATED ONLY /
> HARDWARE-UNVALIDATED**. This index groups every SoundSwitch pack-player planning/spec doc so
> they are read together, not scattered. It grants **no runtime or hardware authorization**.
> If a doc conflicts with code, **code wins**.

## Current state (verified at HEAD `bc9f7f4`, 2026-06-22)

- Tasks **0–6**: merged (PR #115). Deterministic export + independent verification of the
  canonical pack; loader/player/MIDI-input/backends/Enttec sender all software/wire-validated.
- Task **7.0** (`07581ca`) + **7.1** (`f7ae38d`): implemented + fresh-opus review APPROVE, on
  **PR #116** (open). Signal-authority fix + executor single-backend injection + `scene_name`.
- Tasks **7a/7b/7c/7e**: implemented and software-reviewed on `soundswitch/impl`; validated config
  remains default-off, with validate-first runtime control and sanitized status.
- Task **8**: approved in software/offline scope at `bc9f7f4`. Task **9** remains an explicit
  operator hardware gate.
- **Open blocker:** both ticks/beat scaling (600 is only a candidate) and the transition-origin
  contract across every arm/refire path remain unproven for T7d. Pack autoloop output and runtime
  phase shadow stay safe/zero/deferred rather than guess.

## Read in this order

| # | Doc | Role |
|---|-----|------|
| 1 | `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` | **Implementation authority** — the only active impl spec (Part B T7 `:534` / T8 `:574` / T9 `:605`; Part C invariants `:699`). Also surfaced via the `soundswitch_importer_exporter_player_codex_spec.md` symlink in this folder. |
| 2 | `soundswitch_t7_t8_t9_implementation_spec.md` | **Combined implementer brief** (this effort): decomposes T7→T7a–e, pins the verified mechanisms, flags the `phase_tick` blocker, and specs T8 + T9. The grouped "everything spec'd out" doc. |
| 3 | `soundswitch_t7d_capture_evidence_plan.md` | **Current T7d blocker plan** — seven-scenario operator capture matrix, non-circular scale/origin oracle, safe-zero unblock criteria. T7d remains unimplemented. |
| 4 | `soundswitch_orchestration_prompt.md` | Generic orchestration protocol (bootstrap, per-task loop, gates, reporting). |
| 5 | `soundswitch_t7_t8_orchestration.md` | T7+T8 orchestration prompt (effort/reviewer map, T7.0/T7.1 preconditions, after-T8 opus-max review). |
| 6 | `soundswitch_review_pack.md` | Adversarial review gates: before-T7 `:168`, T8 `:195`, T9 `:217`. |
| 7 | `soundswitch_impl_progress.md` | **Resume ledger** (AWR-107) — proof-gate state, next action, per-task status. Verify against code before resuming. |
| 8 | `docs/agents/change_contracts.yml` → `soundswitch_pack_player` (`:233`) | Change contract: code globs, tests, `docs_update` list, forbidden assumptions. |

Historical / superseded: `soundswitch_t4_t6_handoff.md` (T4–T6 handoff; those tasks are merged).

## What "done" looks like for the remaining work
The combined spec (#2) Part E is the definition of done. In short: T7a–c+e are determinable from
current code now; **T7d (autoloop DMX) and runtime phase shadow remain gated on captured proof of
both scale and every transition-origin rule**. T9 starts as an operator hardware-gate handoff document. The
operator has separately authorized controlled device/restart validation after the offline,
shadow, review, zero-frame, rollback, and single-process gates pass.
