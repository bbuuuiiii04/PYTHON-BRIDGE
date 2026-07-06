---
doc_status: current
truth_level: implementation spec — IMPLEMENTED/software-tested (operator-directed, by Claude)
last_verified_commit: 030bc63
last_verified_date: 2026-07-06
validation_scope: standalone v1-baseline stabilization pass (NOT folded into LIGHTING ENGINE v2); covers the two on-v2-path CONFIRMED findings from lighting_v1_foundation_audit.md; IMPLEMENTED and software-tested, no hardware validation
---

> **IMPLEMENTED 2026-07-06 (operator directed Claude to fix directly, no subagents).** Both
> tasks landed and are software-tested: Task 1 in `state_manager.py`
> (`_drop_presentation_release_on_stop` + `_do_stop` call), Task 2 the `led_color_engine.py`
> `lock()` docstring. Regression coverage:
> `tests/test_state_manager_drop_presentation.py::StopFailOpenReleaseTests` (3 tests, incl. a
> negative check proving the pre-fix bug reproduces without the fix). Full suite green; no
> golden re-baselining needed. Operator live visual pass is the remaining gate. The Part A–E
> spec below is retained as the implementation record.

# Codex Implementation Spec — LIGHTING v1 baseline stabilization (2 fixes)

**Standalone pass. This is NOT part of the LIGHTING ENGINE v2 build.** It fixes two
CONFIRMED v1 bugs in shared lighting machinery so the v2 `v2-off ⇒ v1 byte-identical`
toggle locks in a correct baseline. Keep it separate from any v2 feature branch/spec so the
toggle stays clean. Source audit: `docs/plans/active/lighting_v1_foundation_audit.md`.

**Only proceed after operator approval.** Findings C-1 and C-2 are the sole scope; the
audit's AMBIGUOUS items are operator decisions, not part of this pass.

## Part A — Context & Root Cause (verified; read, do not implement)

### A.1 — Bug DD1: reader-stale stop leaves the room dark (fail-open violation) `[confirmed]`

- **What happens today:** during a Laser-Solo / pre-dark drop window the Govees are held
  dark via the LED blackout owner `drop_spotlight`. If the Rekordbox reader goes **stale**
  while the deck was playing, the room latches fully dark (LEDs gated + lasers stopped) until
  the reader recovers *and* the drop window naturally ends.
- **Root cause `[confirmed]`:** the reader-stale stop branch early-`return`s before the only
  code that releases the hold.
  - The dark hold is released **only** by `_drop_presentation_apply_actions`
    (`state_manager.py:2382-2404`), which emits `LED_CLEAR_BLACKOUT reason="drop_spotlight"`
    and clears `_drop_presentation_led_dark_held` / base suppression. Its **only** caller is
    `_drop_presentation_tick` (sole call site `state_manager.py:4117`).
  - The reader-stale branch (`state_manager.py:3536`, `if os.was_playing:`) calls `_do_stop`
    (3540) then `_dispatch_led_idle_ambient` (3554) then `return` at **3559** — above 4117.
  - `_do_stop` (`state_manager.py:4357-4386`) resets the lasers
    (`reset_runtime_state(reason="stop")`, 4382-4385) but **never** discards the
    `drop_spotlight` owner nor clears `_drop_presentation_led_dark_held`.
  - `_dispatch_led_idle_ambient` then gates out at `led_dispatch_policy.py:990-992` because
    `_led_blackout_active()` (`led_dispatch_policy.py:253`) is still True (owner held) →
    renders nothing. Room is dark; lasers were just stopped.
- **Intent it violates `[confirmed]`:** `docs/architecture/drop_presentation_authority.md`
  §Presentation Mechanics (lines 135-138): *"Fail-open, always: LEDs restore and suppression
  releases on ANY of: … stop … laser-output loss mid-window … The policy can never latch a
  fixture dark."* (doc = IMPLEMENTED / SOFTWARE-TESTED current v1 behavior; this is not one of
  its two documented known limitations.) Healthy stops fail-open correctly (they reach 4117
  with `stopped=True`); only the stale branch short-circuits it.
- **Reuse target `[confirmed]`:** the scripted-mode branch of `_drop_presentation_tick`
  (`state_manager.py:2251-2259`) already demonstrates the exact minimal fail-open: build a
  `WindowInputs(..., stopped=…)`, `tick()` the `WindowMachine`, `_drop_presentation_apply_actions(actions)`.
  Reuse this — do NOT invent a new owner-clear or a second blackout mechanism.
- **Considered and excluded from scope:** the second stale early-return
  (`state_manager.py:3611`, the "not playing" branch) does not call `_do_stop` and cannot
  hold a live drop window (windows require a playing drop); `_do_resume`'s legacy empty-deck
  correction is a separate AMBIGUOUS item (audit statemgr PI4), not this fix.

### A.2 — Bug PI2: `lock()` docstring contradicts the code `[confirmed]`

- **What happens today:** `led_color_engine.py:784` `lock()` docstring says
  *"Freeze palette (suppresses drift + drop-snap + queued apply)."* The **"queued apply"**
  clause is false.
- **Root cause `[confirmed]`:** `begin_dispatch` (`led_color_engine.py:389-395`) applies a
  queued palette via `_apply_palette_now` **before** and independent of the
  `elif not self._lock:` dwell branch (396); `_apply_palette_now` never mutates `self._lock`.
  So a queued palette commits under lock and the lock transfers — matching
  `palette_control_authority.md` Rule 8. Only the docstring is wrong. Runtime is correct.
- **Scope:** docstring text only. **No behavior change.**

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute Rules
- **Out of scope — do not touch:** any file other than `state_manager.py` and
  `led_color_engine.py` for code; laser modules (`laser_*.py`), SoundSwitch pack/output,
  Govee LAN discovery, session tooling; and every AMBIGUOUS/REJECTED item in the audit. Do
  **not** "improve" adjacent code.
- **Behavior that must NOT change:** the healthy-stop fail-open path (already correct); the
  `drop_presentation` `enabled: false` byte-identical regression gate; any blackout owner
  other than `drop_spotlight`; the 200 Hz push-loop I/O profile; manual mute / emergency
  blackout ownership and precedence.
- **Error handling:** the release path must not swallow errors into a success-shaped
  fallback. Follow the existing `_drop_presentation_apply_actions` contract (it already emits
  events / sets flags with no try/except); do not add a broad try/except around it. If the
  policy is disabled, return early explicitly (do not construct inputs).
- Include the `dirty-worktree` safety block: do not revert unrelated working-tree changes, do
  not use destructive git; work on `main`.

### Task 1 — `state_manager.py`: fail-open the drop-presentation window on every stop

Add a small release helper and call it from the single stop chokepoint `_do_stop`, so a
held `drop_spotlight` LED dark-hold (and its base suppression) can never survive a stop — no
matter which stop path ran. This reuses the WindowMachine's own universal `stopped=True`
fail-open plus the idempotent `_drop_presentation_apply_actions`.

**1a.** Add the helper (place it next to `_drop_presentation_apply_actions`, after line 2404):

```python
def _drop_presentation_release_on_stop(self) -> None:
    """Fail-open the drop-presentation window on a hard stop.

    The reader-stale stop branch (and any stop path that short-circuits before
    _drop_presentation_tick) would otherwise leave a Laser-Solo / pre-dark LED
    dark-hold latched: _do_stop resets the lasers but never releases the
    drop_spotlight LED blackout owner, and _dispatch_led_idle_ambient then
    renders nothing while that owner is held -> a dark room until the reader
    recovers and the window ends. Reuse the WindowMachine's universal
    stopped=True fail-open + the idempotent action applier so this releases the
    drop_spotlight owner and base suppression and returns the machine to idle.
    No-op when the policy is disabled (keeps enabled:false byte-identical) and
    idempotent (safe on every stop path, including healthy stops that also reach
    _drop_presentation_tick this tick)."""
    cfg = self._drop_presentation_config
    if not cfg.enabled:
        return
    actions = self._drop_presentation_window.tick(
        WindowInputs(
            abs_beat=None, beats_to_next_drop=None, next_drop_beat=None,
            drop_role="none", impact_now=False, laser_visible=False,
            scripted_mode=False, stopped=True,
        ),
        pending_presentation=None, pending_reason="",
    )
    self._drop_presentation_apply_actions(actions)
    self._drop_presentation_last_actions = actions
    self._drop_presentation_last_pending = (None, "", None)
```

(`WindowInputs` is already imported at `state_manager.py:80`; its required kwargs are
`abs_beat, beats_to_next_drop, next_drop_beat, drop_role, impact_now, laser_visible` — verify
the signature at `drop_presentation.py:563` before writing.)

**1b.** Call it at the end of `_do_stop` (after the existing `self._reset_native_autoloop()`
at `state_manager.py:4386`):

```python
        self._reset_native_autoloop()
        self._drop_presentation_release_on_stop()
```

### Task 2 — `led_color_engine.py:784`: correct the `lock()` docstring

Replace the false docstring so it matches the code and `palette_control_authority.md` Rule 8:

```python
    def lock(self) -> None:
        """Freeze automatic palette selection (dwell drift + drop-snap). A
        queued palette still applies at the next track boundary and the lock
        transfers to it (palette_control_authority.md Rule 8)."""
        self._lock = True
```

No code/behavior change.

## Part C — Invariants That MUST Still Hold (live safety)

- **Never a new dark-room failure mode.** After Task 1 the room fails open on stop; verify the
  release *removes* the `drop_spotlight` owner (never adds one) and touches no other owner.
- **`enabled: false` byte-identical.** With `_drop_presentation_config.enabled` False the
  helper returns immediately — no `WindowInputs` built, no tick, no event. A disabled run must
  be byte-identical to today (`drop_presentation` master regression gate).
- **Manual/emergency precedence unchanged.** The release only clears the `drop_spotlight`
  owner via the existing `_drop_presentation_apply_actions`; a held manual LED mute
  (`led_mute_pad`) or emergency blackout owner survives (set discard is owner-scoped).
- **200 Hz push loop gains no blocking I/O.** `WindowMachine.tick` is pure computation;
  `_drop_presentation_apply_actions` enqueues a `BridgeEvent` through the existing
  `_handle_led_event` owner path and flips an in-memory `set_base_suppressed` flag — the same
  operations `_drop_presentation_tick` already performs on the hot path. No new socket/file/
  MIDI/subprocess/sleep. (`runtime_invariants.md` LED Look Director Ownership; `AGENTS.md §6`.)
- **Idempotent.** Healthy stops that also reach `_drop_presentation_tick` (4117) the same tick
  re-confirm the released state; `_drop_presentation_apply_actions` is documented idempotent.

## Part D — Tests

Add to `tests/test_state_manager_drop_presentation.py` (or the nearest existing
state_manager drop-presentation integration test module — reuse its harness/fakes; do not
add a new framework):

1. **Stale-stop fail-open (the DD1 regression).** Drive the state manager so a
   `drop_spotlight` LED dark-hold is held (`_drop_presentation_led_dark_held=True`, owner in
   `_led_blackout_owners`, and base suppression held via the fake player), then trigger the
   reader-stale stop branch (or call `_do_stop` directly as the unit seam). Assert: a
   `LED_CLEAR_BLACKOUT` event with `reason="drop_spotlight"` was emitted,
   `_drop_presentation_led_dark_held` is False, the `drop_spotlight` owner is gone from
   `_led_blackout_owners`, and base suppression was released. A pure seam is available: seed
   the held state and call `_drop_presentation_release_on_stop()` directly (no reader/RB
   dependency), plus one test that `_do_stop` invokes it.
2. **`enabled: false` byte-identity.** With `_drop_presentation_config.enabled` False, seed no
   window and call `_do_stop`; assert the helper is a no-op (no new event, no owner change) —
   the disabled path stays byte-identical.
3. **Owner isolation.** With both a held manual `led_mute_pad` owner AND a `drop_spotlight`
   owner, run the release; assert only `drop_spotlight` is cleared and the manual mute owner
   survives.

No golden/byte-identical test currently encodes the buggy behavior (audit §4), so **no
existing test needs re-baselining.** Task 2 needs no test (docstring only).

## Part E — Acceptance (definition of done)

- [ ] `python3 -m unittest discover tests` green (baseline was 3269 OK); the three new tests
      pass and the existing `test_state_manager_drop_presentation.py` /
      `test_drop_presentation.py` fail-open tests still pass unchanged.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Contract-first (`drop_presentation` contract): update the `docs_update` docs that the
      change touches — at minimum record the fix in `docs/subsystems/led_govee.md` (Package 3
      section) and `docs/status/active_work_registry.md`; review
      `docs/architecture/drop_presentation_authority.md` line 11 (known-limitations note) and
      adjust only if this fix changes what that paragraph claims. Do **not** edit the audit or
      this spec's frontmatter to claim more than software validation.
- [ ] Task 1 changes only `state_manager.py`; Task 2 changes only the `led_color_engine.py:784`
      docstring. No other files touched.
- [ ] Status language stays SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED (`AGENTS.md §10`).

## Part F — Adversarial self-review (attack the spec)

- *"The release double-fires on a healthy stop and clears an owner mid-drop."* — No: it only
  fires inside `_do_stop`, i.e. the deck is stopping; `_drop_presentation_apply_actions` is
  idempotent and the WindowMachine `stopped=True` tick returns a released `WindowActions`, so a
  subsequent healthy `_drop_presentation_tick` (4117) with `stopped=True` re-confirms the same
  released state. It cannot clear a live in-progress drop because there is no live drop once
  the deck stopped.
- *"It breaks `enabled:false` byte-identity."* — Guarded: the helper returns before building
  any input when the policy is disabled. Test D.2 pins it.
- *"It clears the operator's manual mute."* — No: the release routes through the same
  `drop_spotlight`-scoped owner discard the WindowMachine already uses; other owners are
  untouched. Test D.3 pins it.
- *"It adds I/O to the 200 Hz loop."* — No: identical operation set to what
  `_drop_presentation_tick` already runs on the hot path (pure tick + owner event + in-memory
  flag).

## When You Finish

- **Report:** changed files (`state_manager.py`, `led_color_engine.py`, the test module, the
  two docs), tests/checks run with output, and the review target (Claude review of the
  stale-stop fail-open + byte-identity gate).
- **Operator summary (plain language):** *"On a rare stop path (Rekordbox reader glitches
  mid-Laser-Solo), the room could stay black until things recovered. Now every stop releases
  the LED dark-hold, so the Govees come back on immediately. Nothing else changes; with drop
  presentation turned off it behaves exactly as before. Also fixed a misleading code comment
  about palette lock. Verified in software (tests green); not yet hardware-validated — your
  live eyes are still the acceptance gate. Rollback is a one-line revert; no restart behavior
  change."*
