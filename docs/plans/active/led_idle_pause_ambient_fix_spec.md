---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (diagnosis 2026-07-07, Fable 5 + log evidence)
last_verified_commit: 35e0a90
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — LEDs actually go ambient on pause/idle (no more revert-to-random-scene)

Contract key: `led_govee` (`docs/agents/change_contracts.yml:101`). Operator symptom: "pausing
playback does not return the LEDs to an idle/ambient state — it always defaults to
`groove_diy_bright_white_chase`."

## Part A — Context & Root Cause (verified; read, do not implement)

Three cooperating mechanisms, all read at current HEAD:

1. **No LED look is dispatched on no-audible idle.** With mixer authority live, a pause resolves
   to `switch N->0 (idle_no_audible)`; `_push_tick_inner` then hits
   `state_manager.py:3924-3927`: active not in (1,2) → `_enter_idle_no_audible` → `return`, every
   tick. All six `_dispatch_led_idle_ambient` call sites (`state_manager.py:1535, 3979, 4031,
   4184, 4238, 4293`) live INSIDE the active∈{1,2} tick path, so none is reachable.
   `_enter_idle_no_audible` (`state_manager.py:2026-2058`) resets lasers/SoundSwitch/LED keys but
   sends nothing to the strips. [confirmed] The night's live logs (18:20→07:11) contain ZERO
   `mode→idle` ambient dispatches; the only ambient dispatches of the day sit in an afternoon
   session that idled without mixer switches. [confirmed from logs]
2. **The realtime ambient look is self-defeating.** `_dispatch_led_idle_ambient`
   (`led_dispatch_policy.py:1012+`) sets `self._led_rt_permitted = False` (`:1019`) and then
   usually dispatches `rt_twinkle` (56 of 61 ambient dispatches in logs) — a realtime look. The
   realtime runner's beat provider `get_active_beat_anchor` (`led_dispatch_policy.py:278-292`,
   wired at `__main__.py:1155`) returns None when `_led_rt_permitted` is False, so the runner's
   30 fps loop idles and after `grace_s=0.25 s` sends a bare `self._transport.deactivate()`
   (`govee_realtime_runner.py:410-421`, `[RGB] deactivate reason=idle_grace`) — **no blackout
   frame, no scene**. The strip is left to Govee firmware, which shows its last cloud DIY scene.
   [confirmed at code level; the firmware revert itself is hardware behavior — assumed]
3. **Why the leftover scene is `groove_diy_bright_white_chase` so often:** a spin-back scrub
   (deck wound to ~0 ms) momentarily re-resolves the LED role to groove and fires a fresh
   `role_entry:groove` dispatch of that cloud DIY look ~1 s before the pause (two log-proven
   instances 07:34:37 / 07:39:56 on 2026-07-07), and it is also a common last-groove cloud look
   mid-set. Cloud DIY scenes persist on the device until overwritten. [confirmed]

Ruled out: realtime LAN failure (all 3821 frames that night `err=none`); "idle-ambient only wired
for RB_RESTARTED" (refuted — six call sites); the look director picking a groove look at idle
(61/61 idle dispatches were ambient looks).

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `state_manager.py`, `led_dispatch_policy.py`, `govee_realtime_runner.py`, `tests/`,
  plus Part E docs. Do not touch the laser, SoundSwitch, cloud adapter, or transport modules
  (`govee_realtime_transport.py` unchanged — the runner already exposes `blackout()`+`deactivate()`
  composition in `stop()` `:156-157` and `_emergency_teardown` `:430-431`; reuse that pattern).
- Must not change: blackout precedence (operator blackout still beats ambient — the existing
  `_led_blackout_active()` gate at `led_dispatch_policy.py:1032` already handles this); automation
  behavior while a deck is audible; `_dispatch_led_idle_ambient`'s once-per-idle-entry role_key
  dedupe.
- Error handling: propagate/log via existing emitters; no new try/except blankets.

### Task 1 — `state_manager.py`: dispatch ambient on no-audible idle entry

1. Add `self._last_audible_deck: int = 1` to `__init__` (near the other LED fields). Update it to
   `new_deck` wherever `self._os.active_deck` is assigned a value in (1,2) — the deck-switch
   assignment at `state_manager.py:1952` and any init/default path (grep `active_deck =` to cover
   all writes; only values 1 and 2 update it).
2. At the END of `_enter_idle_no_audible` (`state_manager.py:2058`, after `_reset_native_autoloop()`),
   add:
   ```python
   deck = self._last_audible_deck if self._last_audible_deck in (1, 2) else 1
   self._dispatch_led_idle_ambient(active=deck, d=self._deck[deck], reason="idle_no_audible")
   ```
   Note ordering: the method already clears `_led_last_idle_role_key` (`:2043`) before this point,
   so the dedupe check inside `_dispatch_led_idle_ambient` (`led_dispatch_policy.py:1038`) will not
   swallow the send. `_enter_idle_no_audible` only runs on the entry tick (guarded at `:3925`), so
   this is one dispatch per idle entry, not per tick.

### Task 2 — `led_dispatch_policy.py`: freewheel beat so realtime ambient looks stay alive

1. Add module constant `LED_IDLE_FREEWHEEL_BPM = 120.0` (near `LED_HOLD_RELEASE_BEATS`, `:36`).
2. Add `self._led_idle_freewheel_since: Optional[float] = None` to the mixin state init (`:~110`).
3. In `_dispatch_led_idle_ambient`, after a SUCCESSFUL send (`_led_send_decision` outcome
   `"accepted"`): if `getattr(decision, "backend", "") == "realtime_razer"`, set
   `self._led_idle_freewheel_since = time.monotonic()` and log one
   `log.info("[RGB] idle-freewheel-start look=%s", look)`; else set it to None (cloud ambient needs
   no beat).
4. In `get_active_beat_anchor` (`:278-292`), BEFORE the `_led_rt_permitted` check: if
   `self._led_idle_freewheel_since is not None`, return a synthetic anchor:
   ```python
   now = time.monotonic()
   elapsed = now - self._led_idle_freewheel_since
   return BeatAnchor(deck=0, abs_beat_pos=elapsed * (LED_IDLE_FREEWHEEL_BPM / 60.0),
                     bpm=LED_IDLE_FREEWHEEL_BPM, captured_monotonic=now,
                     playing=True, permitted=True)
   ```
5. Clear `self._led_idle_freewheel_since = None` at: the automation resume point that sets
   `_led_rt_permitted = True` (`:779`); the `Ev.LED_BLACKOUT` handler (`:439-451`, so a blackout
   kills the freewheel and the runner tears down realtime — blackout must win); and the manual
   command dispatch path (`_dispatch_led_manual_command`) before it sends. Grep for every
   `_led_rt_permitted` write and make freewheel state consistent at each.

### Task 3 — `govee_realtime_runner.py`: never leave the strip to firmware on idle teardown

In `_idle_tick`'s grace-expiry branch (`:410-421`), send a blackout frame before deactivating,
mirroring `stop()` (`:156-157`) and `_emergency_teardown` (`:430-431`): call
`self._transport.blackout()` immediately before `self._transport.deactivate()`, and extend the log
line to `"[RGB] deactivate reason=idle_grace blackout_sent=1"`. Rationale: with Tasks 1–2 this path
should rarely fire; when it does (e.g. ambient look failed to send), a dark strip is the correct
failure mode for a DJ room — never a random leftover bright scene.

## Part C — Invariants That MUST Still Hold

- Blackout wins over ambient (existing gate at `led_dispatch_policy.py:1032`) and over the
  freewheel (Task 2.5 clears it on `Ev.LED_BLACKOUT`).
- `StateManager` sole `DeckState` writer; 200 Hz push loop gains no blocking I/O
  (`_dispatch_led_idle_ambient` already runs from tick context today at `:4238` — Task 1 adds one
  call on the idle-entry tick only).
- While a deck IS audible, nothing here changes automation, holds, or pad behavior.
- The freewheel anchor must never leak into playing states: `_led_rt_permitted=True` (playing
  dispatch, `:779`) clears it before any automation look renders.

## Part D — Tests

Extend `tests/test_led_state_manager.py` (and the runner's existing test module if present —
follow current harness style; in-memory only):
1. Entering no-audible idle dispatches exactly one ambient decision (role `ambient`,
   reason `idle_no_audible`), using the last audible deck's state.
2. After an accepted realtime ambient dispatch, `get_active_beat_anchor()` returns a synthetic
   anchor with `bpm == LED_IDLE_FREEWHEEL_BPM` and monotonically increasing `abs_beat_pos` across
   two calls (advance the injected clock, no sleeping).
3. Freewheel cleared: (a) on `Ev.LED_BLACKOUT`, anchor returns None again; (b) after a playing-tick
   automation dispatch sets `_led_rt_permitted=True`, the synthetic branch is not taken.
4. Runner: when the idle grace expires, transport receives `blackout()` then `deactivate()` in that
   order (use the existing fake/stub transport pattern from the runner tests).

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–3 implemented exactly; no other behavior changed.
- [ ] `python3 -m unittest tests.test_led_state_manager` + full `discover tests` pass (the three
      documented env-dependent reds excepted if unchanged).
- [ ] Contract `led_govee` `docs_update` docs updated (`docs/subsystems/led_govee.md` idle section
      + `docs/status/active_work_registry.md`; status matrices only if claims change).
- [ ] `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py` pass.
- [ ] Status language: `implemented` / `software-tested`; the firmware-revert claim stays labeled
      hardware-assumed until Brandon sees a pause land on ambient live.

## When You Finish

Report changed files, test/check output, and a plain-language operator summary: expected live
behavior ("pausing or fading everything out now puts the room into the twinkle/halves ambient
look; if that ever fails, the strip goes dark instead of jumping to a leftover bright scene"),
unchanged behavior (blackout still wins; playing behavior untouched), watchpoints
(`[RGB] idle-freewheel-start`, `deactivate reason=idle_grace blackout_sent=1`), rollback (revert
commit; no config changes).
