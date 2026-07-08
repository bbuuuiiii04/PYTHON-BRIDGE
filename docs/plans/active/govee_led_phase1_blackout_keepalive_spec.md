# Codex Implementation Spec - Govee LED Phase 1: Blackout Hammer, Razer Keepalive, Dispatch Retry, Pad Mutual Exclusion

status: planned
last_verified_commit: d2ed39c
owner: operator (Brandon) via Claude Fable 5 audit session 2026-07-08
registry: AWR-145

Execute tasks **in order, one commit per task**. Every file:line below was re-verified against HEAD
`d2ed39c` on 2026-07-08. Labels: [confirmed] = read in current code / ran / operator-observed on
hardware, [assumed] = inferred, [unknown] = stated where load-bearing.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make unless
> explicitly requested. If asked to make edits and there are unrelated changes in those files, do
> not revert them. If you notice unexpected changes you didn't make, STOP and ask how to proceed.
> NEVER use destructive commands like `git reset --hard` or `git checkout --` unless specifically
> requested.

> Skip the planning tool for straightforward tasks (roughly the easiest 25%). Do not make
> single-step plans. After performing a sub-task on the plan, update it. Unless asked for a plan,
> never end with only a plan — the deliverable is working code. Before finishing, reconcile every
> stated intention/TODO: mark each Done, Blocked (one-sentence reason + targeted question), or
> Cancelled (with reason). Do not end with in_progress/pending items.

## Part A - Context & Root Cause (verified; read, do not implement)

The Govee strip accepts realtime UDP frames only while in "razer mode". A cloud DIY scene knocks it
out of razer mode; while out, razer data frames — including blackout frames — are silently ignored
(fire-and-forget UDP, no device feedback). All claims below anchor the tasks:

1. [confirmed] The razer-on command is sent in exactly two places: the inactive→active edge in
   `GoveeRealtimeRunner._tick_once` (`govee_realtime_runner.py:317-323`, which also sends
   `set_brightness(100)`), and the WI-6 reconcile block (`govee_realtime_runner.py:237-250`) which
   only runs when a cloud dispatch armed it (`note_cloud_dispatch`, `:114-126`), only inside a 5 s
   window, and only while `_active`. `set_desired`/`fire_trigger` never send it (`:104-112`).
2. [confirmed] `LEDDispatchCoordinator.tactical_blackout` (`led_dispatch_coordinator.py:190-205`)
   only calls `runner.set_desired(blackout)`. No activate, no reconcile arm. If the strip left razer
   mode, blackout frames stream into the void with `err=none`.
3. [confirmed on hardware, operator 2026-07-08] A DIY cloud scene from the app instantly displaces a
   live realtime stream; afterwards realtime triggers do nothing until the runner passes through an
   inactive→active edge (the operator's STOP-then-play ritual), which proves the activate command
   alone recovers the strip from cloud-scene mode.
4. [confirmed on hardware, operator 2026-07-08] The LAN JSON brightness command
   (`GoveeRealtimeTransport.set_brightness`, `govee_realtime_transport.py:84-91`, payload
   `{"msg":{"cmd":"brightness","data":{"value":N}}}` to UDP `<ip>:4003`) **fully darkens the strip
   even while a cloud scene is playing**, and value 100 restores it. This is the any-mode blackout
   backstop.
5. [confirmed] The policy latches `_led_last_auto_role_key = role_key` BEFORE the dispatch outcome
   is known (`led_dispatch_policy.py:1048`; stable-key early return at `:968-969`). A dispatch the
   coordinator rejects (min-dwell gate `led_dispatch_coordinator.py:95-108` returns `False` →
   outcome `"rejected"`) is therefore never retried until the role_key string changes. Live impact
   observed 2026-07-08: 3 drop looks rejected and swallowed in one mix ("drops not cycling").
6. [confirmed] Same pattern at idle: `_dispatch_led_idle_ambient` latches `_led_last_idle_role_key`
   (`led_dispatch_policy.py:1170-1171`) before sending (`:1183`), and only an `"accepted"` outcome
   starts the idle freewheel clock (`:1202-1207`). A rejected idle look = dark idle instead of
   ambient.
7. [confirmed] The LED Pad checks bridge ownership only inside `play()`
   (`tools/led_pad_playback.py:284-286`); an already-running playback never yields when the bridge
   comes alive. Live incident 2026-07-08: a Pad look kept streaming through an entire bridge mix
   (second writer → ghost comet + flicker on every look).
8. [confirmed] All bridge-side transport I/O (activate/deactivate/brightness/frames) currently
   happens on the runner thread only. The 200 Hz push loop must stay free of socket I/O
   (AGENTS.md §6).

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `govee_realtime_runner.py`, `led_dispatch_coordinator.py`, `led_dispatch_policy.py`,
  `state_manager.py` (retry-cleanup lines only), `tools/led_pad_playback.py`,
  `docs/agents/change_contracts.yml` (+ its `.md` mirror if it enumerates the same globs), the
  tests named in Part D, and the Part E docs.
- Out of scope — must not change: `govee_frame_renderer.py`, `beat_sync_engine.py`,
  `led_color_engine.py`, `led_look_director.py`, `govee_scene_adapter.py`, `govee_runtime_sender.py`,
  laser/SoundSwitch/reader subsystems, any config example values, transport packet formats.
- Behavior that must not change: cloud handoff (`force_deactivate` → `_emergency_teardown` with
  `_handoff_deactivate_pending`) must NOT gain a brightness change — cloud looks must never dim;
  the operator-blackout cloud path (adapter `off` command, rate-limit-exempt) stays as is; the
  edge-activate at `govee_realtime_runner.py:317-323` (activate + brightness 100) stays.
- Error handling: blackout paths fail toward dark (never swallow a failure into "assume lit");
  transport send failures keep the existing `_last_error`/health reporting; no new broad
  try/except, no silent early-returns.
- The 200 Hz push loop must not gain any socket call: every new transport action is requested via a
  flag and executed on the runner thread.

### Task 0 - `docs/agents/change_contracts.yml`: extend the `led_govee` contract
Add `tools/led_pad_playback.py` to `led_govee.code_globs` (`docs/agents/change_contracts.yml:102-122`)
so Task 5 has a matching contract. Mirror in `docs/agents/change_contracts.md` only if that file
enumerates the same glob list. Run `python3 tools/check_agent_contracts.py` before committing.

### Task 1 - `govee_realtime_runner.py`: razer assert-on-demand + unconditional keepalive (replaces WI-6)
1. Module constant: `RAZER_KEEPALIVE_S = 2.0`.
2. New fields in `__init__`: `self._assert_pending = False`, `self._brightness_request: int | None = None`,
   `self._brightness_repeat = 0`, `self._razer_assert_count = 0`.
3. New thread-safe methods (lock with `self._lock`, same style as `set_desired`):
   - `request_activate_assert()` → sets `_assert_pending = True`.
   - `request_brightness(value: int)` → sets `_brightness_request = int(value)`,
     `_brightness_repeat = 2` (send on 2 consecutive ticks — idempotent insurance against a single
     lost UDP packet).
4. In `_tick_once`, DELETE the WI-6 reconcile block (`:237-250`) and insert, at the same position
   (after the emergency check):
   - if `_assert_pending` (read+clear under lock): `self._transport.activate()`,
     `self._last_activate_mono = now`, `self._razer_assert_count += 1`.
   - elif `self._active and self._desired_spec is not None and (now - self._last_activate_mono) >= RAZER_KEEPALIVE_S`:
     same three actions. This is the keepalive: while streaming, razer mode is re-asserted every
     2 s unconditionally, so a knockout or lost activate heals in ≤2 s.
   - if `_brightness_request is not None` (under lock): `self._transport.set_brightness(value)`,
     decrement `_brightness_repeat`, clear the request when it reaches 0. Runs regardless of
     `_active` (the runner loop always ticks).
   - Log the assert at DEBUG only (high-frequency diagnostics stay at DEBUG); the count is visible
     in status.
5. DELETE `note_cloud_dispatch` (`:114-126`) and the fields `_reconcile_enabled`,
   `_reconcile_window_s`, `_reconcile_interval_s`, `_cloud_suspect_until`, `_rt_reconcile_count`,
   and the `RBSS_LED_RT_RECONCILE` env read (`:92-97`). In `status()` replace
   `"rt_reconcile_count"` with `"razer_assert_count"`.
6. `_emergency_teardown` (`:427-446`): when tearing down and `not handoff` (pure emergency /
   operator blackout — NOT the cloud handoff), send `self._transport.set_brightness(0)` before the
   existing `blackout()` + `deactivate()`. The handoff branch is untouched. Rationale: operator
   blackout must hold dark in any device mode; a later look restores brightness via the
   edge-activate (`:319`) or the Task 3 restore. Fail direction: a crash mid-blackout leaves the
   strip dark — that is the intended priority (blackout > beauty).

### Task 2 - `led_dispatch_coordinator.py`: assert razer on every realtime takeover and blackout
1. In `trigger`, realtime branch, after `self._runner.fire_trigger()` (`:151`):
   `self._runner.request_activate_assert()`.
2. In `tactical_blackout`, after `self._runner.set_desired(...)` (`:196-203`):
   `self._runner.request_activate_assert()`. (Do NOT add a brightness change here — the pre-drop
   blackout is followed 1-4 beats later by a drop look; dimming would risk a dark drop on one lost
   restore packet. With the keepalive, black frames now reliably reach the strip.)
3. DELETE the WI-6 `note_cloud_dispatch` call block (`:180-187`).
4. Add method `restore_brightness() -> None`: `self._runner.request_brightness(100)` (used by
   Task 3).

### Task 3 - `led_dispatch_policy.py`: restore brightness when the operator blackout clears
In the `Ev.LED_CLEAR_BLACKOUT` handler (`led_dispatch_policy.py:473-475`), after the owner discard
and `_led_emergency_blackout` recompute: when `_led_blackout_active()` is now False, call
`restore = getattr(self._led_scene_adapter, "restore_brightness", None); if callable(restore): restore()`
(duck-typed like the existing adapter calls). This covers the case where the next look after a
blackout goes to the CLOUD path (whose scenes may not reset device brightness — [unknown] device
behavior, so restore explicitly rather than assume).

### Task 4 - `led_dispatch_policy.py` + `state_manager.py`: latch-on-accept with bounded retry
Goal: a coordinator-rejected dispatch is retried with the SAME decision (no director re-tick — the
director advances cursors/shuffle bags and queues paired post-drops on every tick call, so retries
must not re-tick it) until accepted, the role_key changes, or attempts run out.

1. Module constant `LED_DISPATCH_RETRY_S = 0.35`, max attempts `LED_DISPATCH_RETRY_MAX = 8`.
2. New fields in `LEDDispatchPolicyMixin.__init__` region (`led_dispatch_policy.py:90-130`):
   `self._led_auto_retry: tuple[str, str, Any, int] | None = None`  # (role_key, role, decision, attempts)
   `self._led_auto_retry_at = 0.0`
   `self._led_idle_retry: tuple[str, Any, int] | None = None`       # (role_key, decision, attempts)
   `self._led_idle_retry_at = 0.0`
3. Automation flow (`_dispatch_led_automation`):
   - In the rejected branch (the `adapter-rejected` log site at `:1105-1113`): store
     `self._led_auto_retry = (role_key, role, decision, 1)`,
     `self._led_auto_retry_at = time.monotonic() + LED_DISPATCH_RETRY_S`. Keep the existing latch
     at `:1048` (the no_look / error / director-error behaviors stay exactly as today).
   - In the stable-key early return (`:968-969`): before returning, if `_led_auto_retry` is set,
     its role_key equals this role_key, and `time.monotonic() >= _led_auto_retry_at`: re-send the
     cached decision via `_led_send_decision` with the same arguments as the original call
     (`:1078-1090`). On `"accepted"`: clear the retry slot and replicate the accepted-branch
     bookkeeping (`self._led_smart_drop_blackout_key = ""`; `if role == "drop":
     self._led_note_drop_decision_accepted(decision, sp_state)`). On `"rejected"`: increment
     attempts, `_led_auto_retry_at = now + LED_DISPATCH_RETRY_S`, and clear the slot when attempts
     exceed `LED_DISPATCH_RETRY_MAX`. On `"error"`: clear the slot (give up; error latching stays).
   - When a NEW role_key passes the stable-key check normally, clear `_led_auto_retry` (superseded).
4. Idle flow (`_dispatch_led_idle_ambient`): same pattern. On rejected (outcome not accepted/error
   after `:1183`): cache `(role_key, decision, 1)` + retry-at. In the stable idle-key early return
   (`:1143-1144`): retry the cached decision on the same schedule; on `"accepted"` replicate the
   freewheel logic (`:1202-1207`) exactly (set `_led_idle_freewheel_since`/log when backend is
   `realtime_razer`, else clear it).
5. Cleanup (pending-state + mode-transition guard — every path, not just the introducing one):
   clear BOTH retry slots (set to None) at every site that resets `_led_last_auto_role_key = ""`:
   `state_manager.py:2006`, `:2050`, `:3049`, `:4840`, `:4894`, `led_dispatch_policy.py:502`; plus
   in `_gate_led_automation` (`led_dispatch_policy.py:1211-1232`) and in the `Ev.LED_BLACKOUT`
   handler (`:458` region). A retry must never fire across a deck switch, track load, blackout,
   manual override, or gate transition.

### Task 5 - `tools/led_pad_playback.py`: pad auto-stops when the bridge owns the strip
In `PadPlayback._poll_once` (`:272-276`), on the same every-8th-tick cadence as `poll_owned()`
(≈2 s): if `self._clock.playing and self._ownership.state != "pad_owned"`, call
`self._ownership.refresh()`; if the state comes back `"bridge_owned"`, call `self.stop()`, set
`self._ownership.last_warning = "auto_stopped_bridge_active"`, and log one INFO line. Do NOT
auto-stop when the gate is `"pad_owned"` (a legitimate takeover) or `"free"` (bridge down — the
Pad is the only writer and may play). Uses the existing injected `status_reader`/`time_fn` seams.

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no blocking or socket I/O: `request_activate_assert` /
  `request_brightness` / `restore_brightness` only set flag state under the runner lock; all
  transport calls execute on the runner thread (AGENTS.md §6).
- `BridgeEvent`s stay immutable; no reader thread mutates `DeckState`.
- Operator/emergency blackout is never weakened: the cloud `off` command path and
  `runner.emergency_stop()` behavior are unchanged; brightness-0 is additive on top.
- Cloud handoff (`reason=handoff_to_cloud`) must never send brightness-0 — cloud looks must not dim.
- A drop look must never inherit blackout brightness: tactical (pre-drop) blackout does not touch
  brightness; only the operator/emergency path does, and its release restores 100 twice
  (edge-activate + Task 3 restore).
- Scripted/static SoundSwitch behavior, laser paths, and the Held Static Override contract are
  untouched.
- Failure direction on any blackout path is dark, never "assume lit".

## Part D - Tests

Extend the existing suites (they already inject `time_fn`, fake transports, and fake status
readers — keep everything pure, no sleeps, no sockets, no files):

- `tests/test_govee_realtime_runner.py`:
  - keepalive: with a fake clock, an active streaming runner re-sends `activate` after 2.0 s and
    increments `razer_assert_count`; an idle runner does not.
  - `request_activate_assert()` causes `activate` on the next tick even when `_active` is True.
  - `request_brightness(100)` sends `set_brightness(100)` on exactly 2 consecutive ticks.
  - `_emergency_teardown` sends `set_brightness(0)` on the pure-emergency path and does NOT on the
    handoff path.
  - Remove/replace the WI-6 reconcile tests (`note_cloud_dispatch` / `rt_reconcile_count`).
- `tests/test_led_dispatch_coordinator.py`: `tactical_blackout` and the realtime `trigger` branch
  both call `request_activate_assert`; the `note_cloud_dispatch` call is gone.
- `tests/test_led_state_manager.py`:
  - a dwell-rejected automation dispatch (fake coordinator returns False then True) is retried with
    the SAME decision after ~0.35 s and lands without the role_key changing; the director is NOT
    re-ticked for the retry (cursor unchanged).
  - retry slots are cleared on deck switch, track load, LED_BLACKOUT, and gate transitions.
  - a dwell-rejected idle look retries and, once accepted with a realtime backend, starts the idle
    freewheel.
- `tests/test_led_pad_playback.py`: a playing pad auto-stops within two poll cycles when the status
  reader reports a fresh bridge and the gate is not `pad_owned`; it keeps playing when `pad_owned`
  or when the bridge status is stale/absent.

## Part E - Acceptance (definition of done)

1. All Part D tests pass; `python3 -m unittest discover tests` green except the three known
   environmental reds (live-config LED test, export-pack parity fixtures fallback, SoundSwitch
   golden `test_ddj_slots_8_16_17_24_exact_ch1_ch19`) — do not fix or mask those here.
2. Contract checks green: `python3 tools/check_docs_metadata.py`,
   `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
3. `led_govee` contract `docs_update` satisfied: `docs/subsystems/led_govee.md` (razer keepalive +
   assert-on-takeover replace WI-6 reconcile; blackout brightness backstop; dispatch retry; pad
   mutual exclusion), `docs/status/feature_status_matrix.md`, `docs/status/support_matrix.md`,
   `docs/status/validation_matrix.md`. Status language: `implemented` / `software-tested` /
   `hardware-unvalidated` only.
4. Registry row AWR-145 updated in `docs/status/active_work_registry.md` to reflect
   implemented/software-tested state.
5. No changes outside the Part B file list.

## When You Finish

Report: changed files, tests/checks run with results, and anything Blocked with a one-sentence
reason. Then a plain-language operator summary covering: what the room should do differently
(blackouts recover the strip from cloud mode within ~2 s; a kill-switch blackout also hard-dims the
strip in any mode; swallowed looks now land a third of a second later instead of never; the Pad
politely bows out when the bridge is live), what is unchanged (all look content, colors, timing,
laser/SoundSwitch behavior), watchpoints for the next mix (drop looks must never come up dim — if
one does, the brightness restore path regressed), and that everything is SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED until his next live pass. Note there is no config toggle for the keepalive; a
rollback is `git revert` of these commits plus a bridge restart via the menubar.
