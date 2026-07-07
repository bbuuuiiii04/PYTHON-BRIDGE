---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (diagnosis 2026-07-07, Fable 5 + log evidence)
last_verified_commit: 35e0a90
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — LED hold starvation fix + LED freeze observability

Contract key: `led_govee` (`docs/agents/change_contracts.yml:101`). Highest-impact LED fix from the
2026-07-07 deep diagnosis (operator symptom: "LEDs freeze on one look for 20–320 s while the track
plays; loading one track on deck 1 leaves the LEDs stuck").

## Part A — Context & Root Cause (verified; read, do not implement)

What happens today:

- The ONLY path that repaints the Govee strips during play is `_dispatch_led_automation`
  (`led_dispatch_policy.py:731+`). It early-returns at `led_dispatch_policy.py:781-789` when
  `self._led_hold_active` is True — **silently**: no `_gate_led_automation()` call, no log line,
  and the return happens BEFORE the role_key is built at `:812`, so look rotation, color recompute,
  everything downstream stops. [confirmed — read at current HEAD]
- The hold releases only when `sp_state.beats_into_phrase <= LED_HOLD_RELEASE_BEATS` (1.0, a
  one-beat window at a phrase entry; constant at `led_dispatch_policy.py:36`) or
  `sp_state.phrase_start_crossing` is True. Both are derived from the track's phrase segments
  (`smart_phrasing.py:281-306`): if `snapshot.phrase_segments` is empty, or the playhead is past
  the last labeled segment, `beats_into_phrase` is None and `phrase_start_crossing` is False on
  every tick — **the hold never releases**. [confirmed]
- `_led_hold_active` is SET at exactly two sites: every active-deck switch
  (`state_manager.py:1953`) and every track load onto the active deck (`state_manager.py:2089`).
  It is CLEARED at exactly two sites: idle entry `_enter_idle_no_audible` (`state_manager.py:2045`)
  and `_do_stop` (`state_manager.py:4799`). A pause/stop of a NON-active deck goes through the
  pause handler (`state_manager.py:1364-1372`) and never touches the flag. [confirmed — these are
  the only reads/writes in the tree]
- Live-mix consequence: mixer-authority deck switches (`switch 1->2 (bass_dominance)` etc., up to
  5/min in the night's logs) and track loads each re-arm the hold; each hold then waits up to a
  full phrase — or forever on phrase-less stretches — while the laser (fed the raw `abs_beat_pos`,
  not hold-gated) keeps animating. Log evidence: 30 stall windows ≥20 s with the deck playing and
  the laser beat advancing; in the three deep-dived windows with a visible trigger, a
  `deck-load`/`switch` line sits at −4.4 s … +0.0 s of the freeze-start dispatch. [confirmed
  windows W1/W2/W4; overall mechanism label: **likely** — see next bullet]
- Root-cause label: **likely, not confirmed** — 12 of 30 stall windows show no switch/load trigger
  nearby, and nothing at runtime logs the hold flag, `beats_into_phrase`, or the engine reset
  reason, so the hold being engaged during any given freeze is inferred, never observed. The
  SmartPhrasing engine's reset diagnostics are computed (`smart_phrasing.py:192-203`) and then
  **discarded** — `_update_smart_phrasing_state` keeps only `.state`
  (`state_manager.py:4672-4673`). This spec therefore ships the observability to settle the
  remaining unknown as part of the fix, not as temporary instrumentation.
- Ruled out (do not re-chase): the `RBSS_LED_PHRASE_MONOTONIC` beat clamp (disabling it live made
  stalls longer); engine `abs_beat=None` resets as the trigger (all four reset conditions
  contradicted by `[SM] pos bpm=/file=` fields in 4/4 sampled windows); anchor-chasing in the
  role_key builders (groove/post_drop anchors are fixed within a phrase, `led_dispatch_policy.py:
  1683-1704`, `1638-1657`).

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_dispatch_policy.py`, `state_manager.py`, `tests/` (new/extended tests), plus the
  contract's `docs_update` docs in Part E. Do not touch laser, SoundSwitch, autoloop, or Govee
  transport modules.
- Behavior that must not change: normal hold semantics for tracks WITH phrase data (release at the
  next phrase entry stays the primary release); the `role_key` stability gate at
  `led_dispatch_policy.py:813-814`; the laser's beat feed and color path; `_dispatch_led_idle_ambient`.
- Error handling: no broad try/except, no silent fallbacks. Logging must use the existing
  `bridge_log.perf` / `log.info` emitters already imported in each file.
- The push loop must gain no blocking I/O (logging via the existing handlers is fine; both target
  files already log from tick context).

### Task 1 — `led_dispatch_policy.py`: bounded hold release + hold visibility

1. Next to `LED_HOLD_RELEASE_BEATS = 1.0` (`:36`) add:
   ```python
   LED_HOLD_BACKSTOP_BEATS = 16.0   # release even without a phrase entry
   LED_HOLD_BACKSTOP_S = 8.0        # wall-clock fallback when no beat is readable
   ```
2. In the mixin state init (next to `self._led_hold_active: bool = False`, `:110`) add:
   ```python
   self._led_hold_started_mono: float = 0.0
   self._led_hold_started_beat: Optional[float] = None
   ```
3. Replace the hold block at `:781-789` with logic that (in this order):
   - On the FIRST hold tick (`self._led_hold_started_mono == 0.0`): stamp
     `self._led_hold_started_mono = time.monotonic()` and
     `self._led_hold_started_beat = self._led_abs_beat(sp_state)` (may be None), and emit ONE
     `log.info` line:
     `"[RGB] hold-engaged deck=%d bip=%s crossing=%s abs_beat=%s"` (use `sp_state.beats_into_phrase`,
     `sp_state.phrase_start_crossing`, and the stamped beat; format None as `-`).
   - Compute release:
     - `at_phrase_entry` / `phrase_start_crossing` exactly as today (primary release), OR
     - backstop: current `_led_abs_beat(sp_state)` and `_led_hold_started_beat` both non-None and
       `current - started >= LED_HOLD_BACKSTOP_BEATS`, OR
     - wall-clock: `time.monotonic() - self._led_hold_started_mono >= LED_HOLD_BACKSTOP_S`.
   - On release: set `_led_hold_active = False`, reset both stamps (`0.0` / `None`), emit ONE
     `log.info` line `"[RGB] hold-released deck=%d reason=%s held_s=%.1f"` with reason ∈
     `phrase_entry | crossing | beat_backstop | time_backstop`, then FALL THROUGH to normal
     dispatch (do not return).
   - If still held: `return` (unchanged behavior, still no per-tick spam).
4. Reset the two stamps everywhere `_led_hold_active` is written False outside the release path
   (see Task 2 for the state_manager sites).

### Task 2 — `state_manager.py`: stamp resets at the four flag sites

At all four existing `_led_hold_active` writes — `:1953` (True, deck switch), `:2089` (True, track
load), `:2045` (False, idle entry), `:4799` (False, `_do_stop`) — also set
`self._led_hold_started_mono = 0.0` and `self._led_hold_started_beat = None`. (The stamps are
lazily filled on the first held tick; the set-sites run on the event thread and have no beat.)

### Task 3 — `state_manager.py:4672-4673`: stop discarding engine reset diagnostics

Keep an attribute `self._last_sp_reset_reason: str = ""` (init near the other `_sp_*` attrs). After
`_sp_result = self._smart_phrasing_engine.update(_sp_snapshot)`:
- Extract `reason = _sp_result.diagnostics[0].reason if _sp_result.diagnostics else ""`.
- If `reason != self._last_sp_reset_reason`: emit
  `log.info("[SP] reset-reason-change reason=%s prev=%s deck=%s track=%s abs_beat=%s", ...)` using
  the diagnostic's fields (format None/empty as `-`), then store the new value. A healthy tick
  (no diagnostics) logs the transition back to `prev=<reason> reason=-` the same way.
This is change-triggered only — steady state adds zero log volume.

### Task 4 — `led_dispatch_policy.py` look-line enrichment

In the accepted-dispatch emitter (`bridge_log.perf("led.look", ...)`, `:1244-1252`) add to `data`
(only when dispatch came from `_dispatch_led_automation` — the automation call path already builds
`data` above `:1244`): `abs_beat` (`self._led_abs_beat(sp_state)`, None→omit), `bip`
(`sp_state.beats_into_phrase`, None→omit), `phrase_label` (`sp_state.current_phrase_label`), and
`seq` (`self._led_phrase_seq`). If the emitter helper does not currently receive `sp_state`,
thread it through from the automation call site as an optional keyword defaulting to None (manual/
idle/blackout callers pass nothing and get today's exact payload).

## Part C — Invariants That MUST Still Hold

- `StateManager` remains the only `DeckState` writer; the 200 Hz push loop gains no blocking I/O.
- Hold still exists: a deck switch / track load must NOT instantly repaint (that flash-protection
  is the hold's purpose); only its worst case is bounded (16 beats / 8 s).
- Phrase-entry release fires before the backstop when phrase data exists (primary path unchanged).
- No new per-tick log lines: hold engage/release log once per episode; reset-reason logs on change
  only.
- Blackout, manual override, idle-ambient, and scripted gates in `_dispatch_led_automation` are
  untouched and still run BEFORE the hold block.

## Part D — Tests

Extend `tests/test_led_state_manager.py` (follow its existing harness style; pure in-memory, no
files/subprocess):
1. **Starvation bounded:** hold set + `sp_state` with `beats_into_phrase=None`,
   `phrase_start_crossing=False`, advancing `abs_beat` → dispatch resumes within
   `LED_HOLD_BACKSTOP_BEATS`; before the bound, no dispatch.
2. **Wall-clock fallback:** same but `abs_beat` None throughout (frozen feed) → resumes after
   `LED_HOLD_BACKSTOP_S` (inject/monkeypatch the monotonic source the same way existing tests do;
   if none do, read the started-mono attr and set it backwards — no sleeping in tests).
3. **Primary release unchanged:** hold set + `beats_into_phrase=0.5` → releases immediately on that
   tick and dispatches.
4. **Stamps reset:** after `_do_stop` / idle entry, the started stamps are cleared.
5. **Reset-reason logging:** engine returning a reset diagnostic logs exactly one
   `[SP] reset-reason-change` line per change (use `assertLogs`), none while the reason is stable.

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–4 implemented exactly; no other behavior changed.
- [ ] `python3 -m unittest tests.test_led_state_manager`, `python3 -m unittest tests.test_led_identity_v2`,
      `python3 -m unittest discover tests` pass (3 pre-existing env-dependent reds documented in the
      repo are acceptable if unchanged: live-config LED test, parity fixtures, SS-project golden).
- [ ] Contract `led_govee` `docs_update` docs updated (at minimum `docs/subsystems/led_govee.md`
      hold section + `docs/status/active_work_registry.md` entry for this spec; touch the status
      matrices only if their claims change).
- [ ] `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
      `python3 tools/check_docs_drift.py` pass.
- [ ] Status language: `implemented` / `software-tested` only; the root-cause label stays "likely"
      until a live session with the new `[RGB] hold-engaged/released` + `[SP] reset-reason-change`
      lines either shows holds spanning the freezes (confirm) or shows freezes with no hold
      (falsify → the new lines then carry the data needed for the next diagnosis).

## When You Finish

Report: changed files, test/check output, and a plain-language operator summary — expected live
behavior ("LED looks can never stick longer than ~16 beats after a deck switch or track load;
freezes now leave a log trail"), unchanged behavior (phrase-entry timing when phrase data exists),
watchpoints (the two new log line families), rollback (revert the commit; no config/env changes).
