# SoundSwitch pack-player — planning & spec doc set (grouped index)

> **Status:** ACTIVE INDEX (AWR-107). Repo status **SOFTWARE-VALIDATED ONLY /
> HARDWARE-UNVALIDATED**. This index groups every SoundSwitch pack-player planning/spec doc so
> they are read together, not scattered. It grants **no runtime or hardware authorization**.
> If a doc conflicts with code, **code wins**.

## Current state (verified at HEAD `b7e0e66`, 2026-06-21)

- Tasks **0–6**: merged (PR #115). Deterministic export + independent verification of the
  canonical pack; loader/player/MIDI-input/backends/Enttec sender all software/wire-validated.
- Task **7.0** (`07581ca`) + **7.1** (`f7ae38d`): implemented + fresh-opus review APPROVE, on
  **PR #116** (open). Signal-authority fix + executor single-backend injection + `scene_name`.
- Task **7a**: implemented and fresh-context review **APPROVE** in the current PR worktree;
  validated config loader/example remain default-off and are not runtime-wired yet.
- Tasks **7b–e / 8 / 9**: in progress under the combined implementation/orchestration specs.
- **Open blocker:** capture evidence proves 600 animation ticks/beat, but does not prove a
  universal phase origin across every arm/refire path. T7d and autoloop shadow parity therefore
  remain blocked; pack autoloop output must stay safe/zero rather than guess.

## Read in this order

| # | Doc | Role |
|---|-----|------|
| 1 | `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` | **Implementation authority** — the only active impl spec (Part B T7 `:534` / T8 `:574` / T9 `:605`; Part C invariants `:699`). Also surfaced via the `soundswitch_importer_exporter_player_codex_spec.md` symlink in this folder. |
| 2 | `soundswitch_t7_t8_t9_implementation_spec.md` | **Combined implementer brief** (this effort): decomposes T7→T7a–e, pins the verified mechanisms, flags the `phase_tick` blocker, and specs T8 + T9. The grouped "everything spec'd out" doc. |
| 3 | `soundswitch_orchestration_prompt.md` | Generic orchestration protocol (bootstrap, per-task loop, gates, reporting). |
| 4 | `soundswitch_t7_t8_orchestration.md` | T7+T8 orchestration prompt (effort/reviewer map, T7.0/T7.1 preconditions, after-T8 opus-max review). |
| 5 | `soundswitch_review_pack.md` | Adversarial review gates: before-T7 `:168`, T8 `:195`, T9 `:217`. |
| 6 | `soundswitch_impl_progress.md` | **Resume ledger** (AWR-107) — proof-gate state, next action, per-task status. Verify against code before resuming. |
| 7 | `docs/agents/change_contracts.yml` → `soundswitch_pack_player` (`:233`) | Change contract: code globs, tests, `docs_update` list, forbidden assumptions. |

Historical / superseded: `soundswitch_t4_t6_handoff.md` (T4–T6 handoff; those tasks are merged).

## What "done" looks like for the remaining work
The combined spec (#2) Part E is the definition of done. In short: T7a–c+e are determinable from
current code now; **T7d (autoloop DMX) and autoloop shadow coverage in T8 remain gated on a
universal phase-origin proof**. T9 starts as an operator hardware-gate handoff document. The
operator has separately authorized controlled device/restart validation after the offline,
shadow, review, zero-frame, rollback, and single-process gates pass.
