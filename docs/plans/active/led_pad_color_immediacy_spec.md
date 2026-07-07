---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (diagnosis 2026-07-07, Fable 5)
last_verified_commit: 35e0a90
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — pad color changes repaint the LEDs immediately (realtime looks)

Contract key: `led_govee` (`docs/agents/change_contracts.yml:101`). Operator symptom: "LEDs are
slow to respond to pad presses; pad color changes are queued for the LEDs but applied immediately
to the lasers."

## Part A — Context & Root Cause (verified; read, do not implement)

- A color pad press (`Ev.LED_MANUAL_PAD` / `Ev.LED_RAINBOW_PAD` / white_sand via
  `Ev.LED_PALETTE_PAD`) reaches `led_palette_control.py` `_handle_manual` (`:477-490`) →
  `engine.set_manual(name)` — this mutates **color-engine state only**; nothing is pushed to the
  strips. [confirmed]
- The ONLY automation path that repaints the strip is `_dispatch_led_automation`, gated at
  `led_dispatch_policy.py:813-814` on a `role_key` change. `role_key` embeds role/phrase/cycle —
  never color. So a pad color waits for the **next phrase/section boundary**: latency is unbounded
  (tens of seconds mid-section). [confirmed]
- The laser consumer of the SAME engine state is polled live: `_advance_palette_fade_and_publish`
  (`led_dispatch_policy.py:672-711`) runs each playing tick and
  `_sync_laser_color_if_needed` (`state_manager.py:3130, 3142-3169`) forwards a fresh
  `LaserColorSnapshot` into `_drive_pack_output` every ~5 ms (`state_manager.py:3499-3506`).
  That asymmetry IS the symptom. [confirmed]
- Colors are injected into a look's params at dispatch time only:
  `led_dispatch_policy.py:901-968` (`engine.resolve_slot_colors` / `engine.resolve_color`, merged
  into `decision.params` via `replace`), then sent; the realtime runner renders a **frozen**
  `EffectSpec` (`led_dispatch_coordinator.py:242-254` `_spec_from_decision`;
  `govee_realtime_runner.py` loop never re-reads the engine). [confirmed]
- Cloud DIY looks cannot be recolored at all — the cloud branch sends a fixed `scene_ref` with no
  RGB parameter (`led_dispatch_coordinator.py:164-179`). Out of scope here (operator taste call,
  tracked in the diagnosis report). This spec fixes the ~29 realtime-recolorable looks.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_dispatch_policy.py`, `led_dispatch_coordinator.py`, `state_manager.py`,
  `tests/`, plus Part E docs. Do NOT touch `led_palette_control.py` internals,
  `govee_realtime_runner.py`, the cloud adapter, or any laser file (the laser path already works).
- Must not change: role_key gating for normal automation; dwell/cooldown behavior of
  `Coordinator.trigger`; blackout and manual-override precedence; per-tick fade advancement.
- The refresh must be a color-only update of the CURRENT look — it must never change look,
  effect, owner state, or restart the effect (`fire_trigger` must NOT be called).
- Error handling: a refresh that cannot run (no realtime look live, engine off) returns without
  side effects — no fallbacks, no retries.

### Task 1 — `led_dispatch_policy.py`: factor color injection + cache the live rt decision

1. Extract the injection block at `:905-968` into a helper on the mixin:
   `_led_inject_engine_colors(self, decision, *, role, section_id, cycle, role_key)` returning the
   (possibly `replace`d) decision — byte-for-byte the same logic, including the
   `color_engine_error` handling. `_dispatch_led_automation` calls it where the block was.
2. Add mixin state (`:~110`): `self._led_live_rt_auto: Optional[tuple] = None` holding
   `(pre_inject_decision, role, section_id, cycle, role_key)`.
3. In `_dispatch_led_automation`, capture the PRE-injection decision; after
   `_led_send_decision(...)` returns `"accepted"`: if
   `getattr(decision, "backend", "") == "realtime_razer"`, store the tuple in
   `self._led_live_rt_auto`; else set it to None. Also set it to None in
   `_enter_idle_no_audible`'s LED resets (state_manager side, next to `_led_last_auto_role_key`
   clearing at `state_manager.py:2042`) and on `Ev.LED_BLACKOUT` (`led_dispatch_policy.py:439-451`).

### Task 2 — `led_dispatch_coordinator.py`: gate-free color refresh

Add:
```python
def refresh_realtime_colors(self, decision: LEDLookDecision) -> bool:
    """Color-only update of the live realtime effect. No gates, no owner change,
    no fire_trigger — the effect keeps running with new colors."""
    if self._owner.current() != OwnerState.REALTIME_RAZER:
        return False
    self._runner.set_desired(self._spec_from_decision(decision))
    return True
```
Verify `GoveeRealtimeRunner.set_desired` is lock-guarded for cross-thread calls (the pad event
arrives on the event-loop thread, not the push loop). If it is not, guard it with the runner's
existing `self._lock` — do not add a new lock.

### Task 3 — `led_dispatch_policy.py` + `state_manager.py`: wire pad events to the refresh

1. Policy mixin method:
   ```python
   def _led_refresh_manual_color(self) -> None:
       cached = self._led_live_rt_auto
       if cached is None or self._led_blackout_active() or self._led_manual_override:
           return
       decision, role, section_id, cycle, role_key = cached
       decision = self._led_inject_engine_colors(
           decision, role=role, section_id=section_id, cycle=cycle, role_key=role_key)
       coordinator = self._led_dispatch_coordinator   # use the attribute name that holds the
       if coordinator is None:                        # LEDDispatchCoordinator on this mixin —
           return                                     # grep its construction; do not invent one
       if coordinator.refresh_realtime_colors(decision):
           log.info("[RGB] manual-color-refresh look=%s", getattr(decision, "look", "-"))
   ```
2. In `state_manager.py`, in the event-dispatch block that routes pad events to
   `self._led_palette_control.handle_event(ev)` (`state_manager.py:1582-1592`): after
   `handle_event` returns for `Ev.LED_MANUAL_PAD`, `Ev.LED_RAINBOW_PAD`, and `Ev.LED_PALETTE_PAD`,
   call `self._led_refresh_manual_color()`. (For a v2-ignored named palette this is a no-op —
   `set_manual` was never called, the engine state is unchanged, and the re-injected colors equal
   the current ones; the extra `set_desired` with identical params is harmless. Do not special-case.)

## Part C — Invariants That MUST Still Hold

- 200 Hz push loop unchanged — the refresh runs from the event thread on pad presses only, never
  per tick; it performs no blocking I/O (set_desired hands the spec to the runner thread).
- Look rotation, dwell, transport cooldown, owner transitions: byte-identical behavior (Task 1's
  extraction is a pure refactor; assert via existing automation tests).
- Blackout/manual-override still win: refresh early-returns under both.
- Cloud-DIY looks: behavior unchanged (refresh returns False without touching the adapter).

## Part D — Tests

Extend `tests/test_led_state_manager.py` / the coordinator's test module (existing harness style):
1. Injection refactor is behavior-preserving: existing color-inject tests still pass unmodified.
2. With a live realtime automation look cached: a manual pad event leads to exactly one
   `set_desired` on the runner stub with params containing the NEW engine color; `fire_trigger`
   NOT called; owner unchanged.
3. With owner CLOUD_DIY: refresh returns False, adapter untouched.
4. Under blackout: refresh is a no-op.
5. Cache cleared on idle entry and blackout.

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–3 implemented exactly; injection refactor byte-equivalent.
- [ ] `python3 -m unittest tests.test_led_state_manager` + full `discover tests` pass (documented
      env reds excepted).
- [ ] Contract `led_govee` `docs_update` docs updated (`docs/subsystems/led_govee.md` pad/color
      section + `docs/status/active_work_registry.md`).
- [ ] `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py` pass.
- [ ] Operator summary states plainly: realtime looks now recolor on the pad press itself; looks
      running as cloud DIY scenes still wait for the next section (design limit, separate taste
      decision).

## When You Finish

Report changed files, tests/checks, and the operator summary above; watchpoint:
`[RGB] manual-color-refresh` lines on pad presses; rollback: revert commit, no config changes.
