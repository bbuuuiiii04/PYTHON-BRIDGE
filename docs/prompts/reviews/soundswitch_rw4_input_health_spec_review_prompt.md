---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: d37a472
last_verified_date: 2026-06-24
validation_scope: adversarial RE-REVIEW of the REVISED RW-4 controller-input health spec (round-1 REJECT addressed) BEFORE implementation; review-only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Adversarial RE-REVIEW — RW-4 controller-input health spec (revision after REJECT)

You are an **independent adversarial reviewer** of a *design spec*, not code. You
previously **REJECTED** this spec; it has been revised. Your job now is twofold:
(1) confirm each prior finding is **actually closed by the spec's own code and tests** — not
merely claimed closed in a revision note — and (2) run a **fresh** adversarial pass for new
holes the revision may have introduced. The spec is **not implemented yet**. Default to
skepticism: a revision note that says "fixed" proves nothing; the Part B code and Part D
tests must prove it. An unfalsifiable or self-contradictory safety spec is a REJECT.

## What you are reviewing

You cannot see the repository. The operator will paste **below this prompt**: (1) the full
revised `soundswitch_rw4_input_health_spec.md`, and (2) the cited code excerpts —
**insist on these** for verification: `soundswitch_midi_input.py` `snapshot()`
(incl. the stale-clear), `_clear_held`, the worker `except`/`finally` paths, and
`SoundSwitchMidiInputGroup.snapshot()` (empty-group branch); and `state_manager.py`'s
controller block + the outer `try/except` of `_drive_pack_output`. If a `file:line` claim
cannot be checked against pasted code, treat it as **unverified** and say so.

## Context

Extreme-early-alpha Python bridge (Rekordbox → SoundSwitch/OS2L + MIDI lasers + LEDs)
driving a bridge-owned CH1–CH19 DMX "pack" player. Default-off (`enabled=false`,
`dry_run=true`, `output_backend=none`); 200 Hz push loop `_drive_pack_output` renders one
frame/tick. **Operator policy [P] (option a):** an unhealthy controller drops its **manual
overlay only** (Static Look + blackout forced released); the **automatic scripted base is
left running**. RW-4 composes with RW-2 (pause-hold), RW-3 (mode-only scripted gate +
blessed held-static overlay), and must not regress them.

## Part 1 — Verify the FOUR prior findings are genuinely closed

For each, confirm against the pasted Part B code and Part D tests (cite where it is/ isn't):

1. **(BLOCKER) mail-drop degradation must be LATCHED, not one-tick.** Confirm a new
   `mail_drop_count` increase sets a push-local latch that stays set across ticks and clears
   **only** on a clean, quiet, healthy snapshot (`worker_alive AND error is None AND
   held_static_slot is None AND not blackout_held`). **Attack the recovery condition:**
   - Can a **stale** held slot (missed note-off, worker healthy, drop count unchanged) clear
     the latch and re-honor the overlay? It must NOT (held_slot must be `None` to clear).
   - Does H4 drive **three** ticks and assert tick-3 stays dropped (CH1==9) with the slot
     still held? A two-tick H4 is insufficient.
   - Does a test (H9) prove the latch clears after a clean tick and a later fresh press is
     re-honored — and that the latch cannot lock the overlay out **permanently** beyond the
     operator's control?
2. **(BLOCKER) missing health fields must be FAIL-CLOSED.** Confirm `worker_alive`, `error`,
   `mail_drop_count` are read **directly** (no `getattr(s, "worker_alive", True)`-style
   healthy defaults). Confirm a malformed snapshot raises into the **existing outer
   `except`** and submits ZERO (verify that outer guard exists in the pasted code). Confirm
   the empty-alias "healthy" verdict comes from the **real** empty-group `snapshot()`
   (`worker_alive=True, error=None, mail_drop_count=0`), not from a defaulted read. Find any
   field still defaulted toward healthy.
3. **(HIGH) the no-alias test must be REAL.** Confirm H3 constructs an actual
   `SoundSwitchMidiInputGroup(bindings=[], aliases={})` (not a `_FakeInput()` with healthy
   defaults), asserts scripted still renders and no overlay is held, and keeps a
   `midi_input is None` variant.
4. **(MEDIUM) the worker-death narrative must be PRECISE.** Confirm the spec no longer claims
   *every* worker death preserves holds. Exception death calls `_clear_held` (clears holds);
   the real gap is the **source-closed `finally`** path that sets `worker_alive=False`
   **without** clearing held state. Confirm H1 models exactly that (`worker_alive=False`,
   held slot still reported, `error=None`) and its pre-RW-4 expectation (CH1==200) is correct
   for that snapshot.

If any prior finding is only *described* as fixed but the code/tests don't enforce it, that
is a **REJECT**.

## Part 2 — Fresh adversarial pass (new risks the revision may add)

- **Latch vs. worker-death/error interaction.** worker_alive/error are *not* latched
  (self-clearing). Confirm that's correct and that a worker-death-while-latched case can't
  wrongly re-honor on worker recovery while a stale slot is still held. Check H7 (worker
  recovery self-clears) does not contradict the latch rule.
- **Permanent-lockout / flapping.** Does the latch ever strand the overlay off forever, or
  strobe the rig near `stale_timeout`? The recovery requires the operator to release holds —
  confirm that's the intended, bounded fail-safe, not an unrecoverable state.
- **Blackout-drop consequence (option a).** A held blackout on a degrading controller is
  released and the scripted base returns. Confirm this is stated, `[P]`-blessed, and applied
  consistently (H2/H5/H6), and that a *healthy* blackout still ZEROs first (no regression).
- **Two push-local fields cleanup.** Confirm both `_pack_last_mail_drop_count` (monotonic,
  strict `>`, reload-safe via H8) and `_pack_input_degraded_latched` are reset/handled on
  every transition; neither leaks across deck/track/runtime changes incorrectly.
- **Scope.** Still only `state_manager.py` (controller block + two init lines) + the test
  file? Flag any reach into the player, adapter, runtime, `sanitized_status()`, config, or
  startup.
- **Test falsifiability.** Each H-case must fail for its intended defect (H1 CH1==200;
  H2/H5/H6 ZERO; H4 tick-3 fails the one-tick draft) and use a pure seam (no device/thread/
  port). Flag any false-pass.
- **Unlabeled certainty.** Any `[C]/[P]/[A]/[U]` mislabel — especially the inert
  `mail_drop_count` claim or a `[U]` hardware fact dressed as `[C]`.

## Required response

1. **Verdict:** exactly `APPROVE`, `REVISE-AND-APPROVE`, or `REJECT`.
2. **Per-finding closure table:** for findings 1–4, `CLOSED` / `NOT CLOSED` with the exact
   spec location (and the failing sequence if not closed).
3. **New findings** (Part 2), ordered by severity: precise location, concrete failing
   sequence or self-contradiction, live-mixing impact, smallest required correction. If none,
   `No new findings.`
4. **Explicit conclusions** on: latch correctness + recovery, fail-closed reads,
   empty-alias-vs-failure, RW-2/RW-3 non-regression, push-loop purity, test strength, scope.
5. **Residual risks / unverifiable claims**, preserving **SOFTWARE-VALIDATED ONLY /
   HARDWARE-UNVALIDATED**. Treat any `file:line` you could not check as unverified.

Do not soften the verdict to be agreeable. If the latch recovery, fail-closed read, or real
empty-group test is not actually enforced by the pasted code/tests, REJECT.

---

*(Paste the full revised `soundswitch_rw4_input_health_spec.md` and the cited
`soundswitch_midi_input.py` / `state_manager.py` excerpts below this line.)*
