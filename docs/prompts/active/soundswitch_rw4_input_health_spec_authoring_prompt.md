---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: 9b4b825
last_verified_date: 2026-06-24
validation_scope: spec-authoring prompt for the NEXT bridge-native pack-driver step (RW-4 controller-input health fail-to-zero); authoring-only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no implementation, restart, enable, backend change, MIDI/serial open, or hardware action authorized
---

# Spec-authoring prompt — scope the next pack-driver step and write its Codex spec

You are **Opus**, authoring a Codex implementation spec in `/Users/bbui/rb_ss_bridge_v2`.

This is **authoring-only**. Do **not** implement code, edit runtime files, commit code,
restart/enable/stop the bridge, change config or backend, open MIDI/serial/Enttec/DMX,
or run hardware/fixture tests. You may read the repo, run read-only inspection, and run
offline tests that write only to `/tmp`. Your single deliverable is one reviewed spec
file (path below) plus a short report.

RW-3 (mode-only scripted authority gate) just landed and passed independent review
(APPROVE, software-validated). Your job is to scope the **next** step and spec it.

## Step 0 — verify state, then scope (do this first, report before writing the spec body)

1. Read, in this order: `AGENTS.md` (fully), `PRIVATE_OPERATOR_PROFILE.md` if present,
   then `docs/plans/active/soundswitch_exporter_remaining_work.md` §RW-4 and §RW-5, then
   `docs/plans/active/soundswitch_rw3_mode_authority_spec.md` (the immediately-preceding
   pattern you must compose with) and the RW-2 spec it references.
2. Verify the remaining-work doc against **current code at HEAD** — line numbers in that
   doc predate RW-3 and have drifted. Re-anchor every claim you rely on. Code/tests win
   over docs.
3. Confirm the dependency picture before choosing scope. Expected (verify, don't trust):
   RW-1A done; RW-2 done; RW-3 done (review-pending→approved); **RW-4 (controller-input
   health) and RW-5 (status/menubar) are the only unblocked *software* items**;
   RW-6/RW-7/RW-8 are `[U]`/hardware-capture-blocked; RW-9/RW-10 are downstream of RW-4/5.
4. **Default scope: RW-4 alone**, as one bounded single-subsystem change, mirroring RW-3's
   deliberately narrow file boundary. Name RW-5 as the *next* spec, not this one. Only
   propose bundling RW-4+RW-5 if you can make a strong correctness case for it; otherwise
   keep them separate. If your re-verification shows the ordering should differ or a
   blocker exists, **pause and tell the operator in plain language** before writing.

## The RW-4 problem (verify against code; cite exact `file:line` at HEAD)

The pack driver consumes controller input but ignores controller *health*.
`MidiInputSnapshot` exposes `held_static_slot`, `blackout_held`, `worker_alive`, `error`
(incl. `"stale_hold"`), and `mail_drop_count` (`soundswitch_midi_input.py:43-47`); the
adapter clears held state and drops `worker_alive` on failsafe (`:204-209`, `:154`) and
flags `stale_hold` (`:115`). But `StateManager._drive_pack_output()` reads only
`blackout_held` and `held_static_slot` (the masks/static block near `state_manager.py:3281-3290`
after RW-3). So a dead/errored controller silently drops its *manual* overlay while the
*automatic* scripted base keeps rendering — the fail-to-zero contract the original spec
stated is unmet.

## The one decision you MUST surface to the operator (do not guess)

RW-4's crux is a real live-mixing policy choice. Frame it in plain language and get an
explicit operator answer (or present it as a clearly-labeled `[P]` decision the operator
and the spec reviewer must ratify) **before** finalizing:

> "If your MIDI control surface dies or goes unhealthy mid-show, what should the
> bridge-owned light output do? (a) keep the automatic scripted show running and only drop
> any manual Static Override / blackout the dead controller was holding, or (b) force the
> whole bridge-owned output to ZERO until the controller is healthy again?"

This single answer determines whether controller degradation zeros only the manual overlay
(already partly true) or also the automatic base. Do not pick it for the operator.

## Design questions the spec must answer (from RW-4 required-work; verify each)

- The exact **healthy/recovery latch** built only from snapshot fields (`worker_alive`,
  `error`, `mail_drop_count`, `stale_hold`). **No MIDI API call may enter `_push_tick`** —
  the driver reads the in-memory snapshot only.
- On worker death, input error, conflicting holds, or safety-relevant mailbox loss, resolve
  the *appropriate* output to ZERO **before** recovery — where "appropriate" is fixed by the
  operator decision above.
- **Distinguish an intentionally-empty controller-alias configuration from a configured
  worker failure**, so a show with no manual control surface is not made impossible (a
  no-aliases setup must still allow scripted playback). This is the second live-safety trap;
  state the exact signal that separates the two.
- Require a **fresh healthy snapshot** before input-controlled output resumes; prove stale
  note-off/note-on state cannot reappear after a pack reload or worker restart.
- Compose with RW-3 and RW-2 without regressing them: the mode-only `scripted_owned` gate,
  the blessed held-Static-Override overlay (an authoritative overlay that loses only to
  blackout/emergency and pack-disabled/shutdown), the `play_identity` pause-hold latch and
  its de-ownership teardown, and the `clear_selection()`-only ZERO path (never
  `transport="stopped"/"ended"/"unloaded"`). Blackout/emergency precedence stays first.

## Invariants the spec must hold (map to roadmap §7; same rigor as RW-3)

- StateManager stays the sole `DeckState` writer; new state is driver-local push state only.
- Push-loop purity: in-memory only — no I/O, lock, sleep, retry, MIDI/serial/socket/subprocess
  inside `_drive_pack_output`/`_push_tick`.
- Default-off neutrality: inert unless `rt.active`; byte/order-neutral for OS2L/lasers/LEDs/
  Rekordbox/commands when pack is absent/disabled/dry-run/`output_backend=none`.
- No new leaks: if you touch `sanitized_status()`, keep it free of paths/ports/ids/aliases.
- Fail-closed: every uncertain/degraded state resolves toward ZERO, never toward retained
  output.

## Output (the deliverable)

Write the spec to **`docs/plans/active/soundswitch_rw4_input_health_spec.md`** in the
operator's **Part A–E** format:

- **Part A** — context & root cause, every claim labeled **[C] confirmed / [P] policy /
  [A] assumed / [U] needs hardware**, re-verified at HEAD with exact `file:line`.
- **Part B** — tasks to implement exactly, in order, commit-after-each, with the exact files
  and line regions touched (name them; keep the boundary as tight as RW-3's two-file change).
- **Part C** — invariants that must still hold (live safety), mapped to the roadmap.
- **Part D** — pure-seam tests covering: worker death while static held, worker death while
  blackout held, **no aliases configured (scripted still renders)**, mailbox drops, stale
  hold, conflicting holds, pack reload, and healthy recovery. Each test must fail for the
  intended pre-RW-4 defect.
- **Part E** — acceptance / definition of done, including the gate commands (`unittest
  discover tests`, the three hard doc checks, `git diff --check`, the pack-gen proof if
  relevant) and the unchanged default-off posture.

Run the **9-point pre-handoff checklist** against your own draft (verified claims; knowns/
unknowns; pending-state + mode-transition guards; third-party API completeness; pure-function
test seam; live-safety invariants; adversarial self-review with forced-failure scenarios).
Do **not** flip any roadmap completion checkbox — RW-4 is not complete until implemented,
reviewed, and hardware-validated.

## Report back (in chat, concise, operator comms mode)

The scope decision (RW-4 alone vs. other) with the dependency evidence; the surfaced
operator policy decision and its options' plain-language consequences; the spec path; the
exact files/line-regions the implementation will touch; the test list; and the open `[U]`
items. Preserve **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
