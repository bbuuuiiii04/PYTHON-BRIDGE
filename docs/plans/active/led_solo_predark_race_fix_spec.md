---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (verified at working tree with AWR-140/141/142/143, 2026-07-07)
last_verified_commit: 20ad2dd
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex/Subagent Implementation Spec — RC4: stop the LED drop-look flashing before a laser-solo blackout

Contract key: `led_govee` (`led_dispatch_policy.py`). Fixes RC4 from the 2026-07-07 session: on a
learned/armed **laser-solo** drop, the LEDs flash a bright drop look for ~0.6–2 s before the solo
blackout hides them. **LED-side only; solo LENGTH and the blackout itself are unchanged (that taste
call stays deferred).** This suppresses the pre-marker flash only.

## Part A — Context & Root Cause (verified; read, do not implement)

- The LED drop look and the solo blackout key off **different drop signals**:
  - LED automation resolves `role="drop"` from `_led_drop_marker_anchor`, which fires on
    `current_phrase_is_chorus and phrase_start_crossing` OR `smart_drop_crossing`
    (`led_dispatch_policy.py:1559-1567`). The chorus phrase-start edge typically lands **~0.6 s before**
    the anlz smart-drop marker. [confirmed]
  - The drop-presentation solo blackout only sees a drop on `smart_drop_crossing`
    (`state_manager.py:2593`), i.e. at the marker — later. [confirmed]
- In the push tick, `_dispatch_led_automation` runs at `state_manager.py:4301`, **before**
  `_drop_presentation_tick` at `:4565`. So on a solo drop the LED drop look is dispatched at the early
  chorus anchor, and only at the marker does drop-presentation set the `drop_spotlight` LED blackout
  owner (`state_manager.py:2702-2707` via `LED_BLACKOUT`). Once that owner is set,
  `_dispatch_led_automation` masks everything (`led_dispatch_policy.py:863-865`,
  `if self._led_blackout_active(): gate "emergency_blackout"; return`). So the ONLY unmasked window is
  the ~0.6 s between the chorus anchor and the marker — that is the flash. [confirmed by trace + the
  16:43:52 / 17:01:51 log events: `drop_diy_* via=cloud role=drop` at −0.6 s, then
  `led blackout (from drop_presentation) reason=drop_spotlight` at the crossing]
- The room-split plan already knows, during the approach, that the upcoming drop is a solo:
  `_drop_presentation_last_pending` = `(pending_presentation, pending_reason, eval_beat)`
  (`state_manager.py:2674`; on the scripted/disabled path it is `(None, "", None)`,
  `state_manager.py:2570`). During the approach (`impact_now` False) `eval_beat = next_smart_drop_beat`
  and `pending_presentation` is `LASERS_ONLY` for a learned/armed solo (via `resolve_presentation`,
  `drop_presentation.py:361-379`). The bridge already reads exactly `self._drop_presentation_last_pending[0]
  == LASERS_ONLY` in `_drop_presentation_update_solo_feedback` (`state_manager.py:~2757`) — proven prior
  art for this signal. [confirmed]
- `_gate_led_automation(reason, ...)` sets an observability gate reason and returns WITHOUT dispatching
  a look, leaving the last-dispatched look on the device — i.e. it HOLDS the current look
  (`led_dispatch_policy.py:846-`). This is exactly the "hold the buildup look through the gap" behavior
  we want; it is the same mechanism the `emergency_blackout` mask uses. [confirmed]
- `LASERS_ONLY` is defined in `drop_presentation.py`; `led_dispatch_policy.py` does not import it today.
  [confirmed — no match]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_dispatch_policy.py` and `tests/` (the LED-state-manager suite), plus Part E docs.
- Do NOT touch: `state_manager.py`, `drop_presentation.py`, `laser_director.py`, `smart_phrasing.py`,
  the drop-presentation blackout/pre-dark logic, or config. Do NOT change solo length, the blackout
  itself, or laser behavior — the lasers MUST still fire during the solo.
- This is LED-side and additive: it only SUPPRESSES an LED drop look for a known-solo drop by holding
  the current look. It must never force a bright look, never itself send a blackout, and must be a
  no-op when drop-presentation is disabled/unconfigured (pending `(None, ...)` → not `LASERS_ONLY` →
  no suppression → today's behavior byte-identical).
- Error handling: read the pending tuple defensively (it is always a 3-tuple by construction; index
  `[0]` and compare). No try/except.

### Task 1 — `led_dispatch_policy.py`: import the constant + a small predicate
Add `from .drop_presentation import LASERS_ONLY` with the other imports. Add a helper:

```python
def _led_upcoming_drop_is_lasers_only(self) -> bool:
    """True when the drop-presentation plan's pending verdict is a Laser Solo (LEDs dark).
    Used to suppress the early LED drop-look flash before the solo blackout owner is set.
    Safe/no-op when drop-presentation is off: pending is (None, "", None)."""
    pending = getattr(self, "_drop_presentation_last_pending", None)
    return bool(pending is not None and pending[0] == LASERS_ONLY)
```

### Task 2 — `led_dispatch_policy.py`: suppress the drop look for a pending solo
In `_dispatch_led_automation`, AFTER `role = self._led_role_from_smart_phrasing(sp_state, mutate=True)`
(`~:963`) and BEFORE the `if role == "drop":` dispatch (`~:1015`), insert:

```python
if role == "drop" and self._led_upcoming_drop_is_lasers_only():
    # RC4: the room-split plan says this drop is a Laser Solo (LEDs dark). The LED drop anchor
    # fires ~0.6 s before the smart-drop marker (chorus phrase-start), so without this the LEDs
    # flash a drop look before the marker sets the solo blackout owner. Hold the current look
    # through the gap; the marker's drop_spotlight blackout then owns the darkness. Does NOT
    # change solo length or the blackout itself; lasers still fire the solo.
    self._gate_led_automation(
        "solo_predark_hold", active_deck=active, role=role, role_key=role_key,
    )
    return
```

Keep the `mutate=True` role resolution as-is (the drop lifecycle still arms/tracks the section
normally; only the visible look is withheld). Do NOT add a second resolve call.

## Part C — Invariants That MUST Still Hold (live safety)
- Suppression fires ONLY when pending == `LASERS_ONLY`; every non-solo drop (`LEDS_ONLY` /
  `LEDS_PLUS_LASERS` / `plan_unavailable` / disabled) dispatches its drop look exactly as today.
- Never forces a bright look and never sends a blackout itself; it can only HOLD the current look. The
  actual solo darkness still comes from drop-presentation's `drop_spotlight` owner at the marker
  (unchanged), and the `emergency_blackout` mask (`:863`) still owns the post-marker darkness.
- Lasers unaffected — the laser director still fires the solo; this is LED-only.
- No new tick-path I/O; pure attribute read + existing gate call. 200 Hz push loop / runner untouched.
- No-op parity: with drop-presentation disabled, `_dispatch_led_automation` behaves byte-identically.

## Part D — Tests (`tests/`, existing LED-state-manager harness)
Pure in-memory via the existing StateManager LED test harness (as `test_led_state_manager.py` does):
1. **Solo suppressed:** set `_drop_presentation_last_pending = (LASERS_ONLY, "solo_learned", <beat>)`,
   drive a tick whose `sp_state` resolves `role="drop"` (chorus phrase-start anchor) → assert NO drop
   look was dispatched to the adapter and the automation gate reason is `solo_predark_hold`.
2. **Non-solo unaffected:** same drop tick with `_drop_presentation_last_pending =
   (LEDS_PLUS_LASERS, "both_finale", <beat>)` → assert the drop look IS dispatched (role `drop`),
   byte-identical to today.
3. **Disabled/no-op:** `_drop_presentation_last_pending = (None, "", None)` → drop look dispatched
   (today's behavior).
4. **Post-marker still masked:** with a blackout owner set (`_led_blackout_active()` True), the tick
   still gates `emergency_blackout` (pre-existing behavior; prove RC4 didn't disturb it).

## Part E — Acceptance (definition of done)
- [ ] Tasks 1–2 exact; `led_govee` contract suite + `discover tests` at the known baseline reds only
      (from `/Users/bbui`: `python3 -m unittest discover rb_ss_bridge_v2.tests`; known reds: LED color
      Patch D, export parity fixtures, SoundSwitch golden slot 16, live-config `test_laser_color_engine`).
- [ ] Hard checks pass: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] `led_govee` `docs_update`: note the solo pre-dark hold in `docs/subsystems/led_govee.md`; add an
      AWR-144 row to `docs/status/active_work_registry.md` (implemented/software-tested;
      HARDWARE-UNVALIDATED); record the new tests in `docs/validation/software_test_inventory.md`.
- [ ] Status language §10 only.

## Adversarial self-review (author, pre-handoff)
- *"A non-solo drop loses its look."* Prevented: the gate keys on `pending[0] == LASERS_ONLY`, which is
  only set for actual solos; `LEDS_ONLY`/`LEDS_PLUS_LASERS` drops are untouched (Test 2).
- *"Stale pending suppresses the wrong drop."* During the approach the pending is recomputed every tick
  for the imminent drop; one-tick-stale (automation reads last tick's value) is steady-state-safe. Known
  edge: a manual solo armed <1 tick before the marker may still flash — acceptable and rare; noted, not
  fixed here.
- *"Drop-presentation off → crash/behavior change."* Prevented: pending is `(None, "", None)` →
  predicate False → today's path (Test 3), and the attribute is read via `getattr` default.
- *"Lifecycle desync from withholding the look."* The lifecycle still arms (`mutate=True`); only the
  visible look is held. After the solo window ends the role resolves to `post_drop` normally; the ~8-beat
  drop window has long passed, so no stale drop look reappears.

## When You Finish
Report the exact `led_dispatch_policy.py` diff, the new tests, docs updated, and verbatim test/check
output. Operator summary: "On a laser-solo drop the LEDs were flashing a bright drop look for about a
second before they blacked out for the solo, because the LED drop look fires a hair before the drop
marker while the solo blackout waits for the marker. Now, when the plan already knows the next drop is a
laser solo, the LEDs just hold whatever they were showing until the blackout takes over — no flash. The
lasers still do the solo exactly as before, and how long the solo lasts is unchanged." Rollback = remove
the Task 2 block, the helper, and the import. End with the literal line SUBAGENT-RC4-DONE.
