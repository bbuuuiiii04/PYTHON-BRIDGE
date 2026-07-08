# Implementation Spec - Drop-Impact Transport Guarantee (impact never gambles on internet latency)

status: planned (awaiting executive review; Task 3.1 already landed as the live interim guard `e707199`)
last_verified_commit: e707199
owner: operator (Brandon) via Claude Fable 5 orchestration session 2026-07-08
registry: AWR-150

Execute tasks **in order, one commit per task**. File:lines verified at HEAD `931feef` on
2026-07-08 (post-AWR-149) unless marked. Labels: [confirmed] / [assumed] / [unknown].

> Shared dirty worktree + auto-sync hook: NEVER revert changes you did not make; commit ONLY by
> explicit file paths; no destructive git; work on `main`; touch ONLY the files listed here.
> **DO NOT run the full test suite or heavy parallel work until the operator declares the live
> mix over** — single-module test runs only until then. Never touch the running bridge.

## Part A - Live Incident & Root Cause (verified; read, do not implement)

1. [confirmed, operator live 2026-07-08 14:57, current.jsonl] Deck-2 transition → the pre-drop
   blackout rode the CLOUD path (`room_blackout` scene, `smart-drop-blackout-accepted
   transport=cloud` 14:57:36) because the committed drop pick was cloud (`drop_diy_3`,
   14:57:37). The cloud drop scene arrived ~5 s late over the internet; the room sat on the
   blackout scene THROUGH the drop beat until realtime post-drop looks rescued it at 14:57:41.
   Operator experienced "stuck on a blackout" at the impact moment.
2. [confirmed] The coupling: `_dispatch_led_smart_drop_blackout` commits the upcoming drop pick
   (`_led_drop_decision_for_anchor(sp_state, commit=True)`, `led_dispatch_policy.py:682`; the
   committed-decision cache is `:1564-1589`) and branches on ITS backend — realtime pick →
   realtime tactical blackout (`:684-725`); cloud pick → the whole pre-drop/impact pair rides
   cloud (`:727-804`). A cloud drop therefore gambles the impact moment on internet latency.
3. [confirmed] Cloud dispatch is fire-and-forget HTTP: there is NO device-residency feedback.
   "Wait until the scene is resident" is unobservable; apply latency varies (observed tail 5 s)
   and routinely exceeds the 1-4 beat blackout runway. Any residency-deadline design degrades to
   "cloud drops almost always fall back" while still needing all the takeover machinery — so
   this spec builds the convergent shape directly (Task list below).
4. [confirmed] The backend-dependent dispatch offsets (`_led_sp_state_for_next_backend`,
   `led_dispatch_policy.py:2023-2080`; `automation_cloud_offset_s` vs
   `automation_realtime_offset_s`) already send cloud looks early — an early SEND cannot close a
   variable tail while the cloud scene still owns the beat itself.
5. [confirmed] Why a mid-drop cloud takeover is now safe: AWR-145 keepalive re-asserts razer
   every 2 s while streaming (`govee_realtime_runner.py:35,271-284`) — so a staged cloud scene
   that lands mid-drop would be STOLEN BACK within 2 s unless the keepalive deliberately yields.
   The coordinator's normal cloud path tears realtime down BEFORE the scene arrives
   (`led_dispatch_coordinator.py:167-183` force_deactivate → 1-5 s gap = the dark hole).

**Operator design requirement (recorded 2026-07-08, do not re-litigate):** the pre-drop-blackout
+ drop-impact pair must never depend on internet latency; cloud drops STAY in rotation (never
deleted, never filtered out) — they just cannot own the beat.

**Design (the convergent shape):** every drop impact renders REALTIME on the beat. When the
committed drop pick is cloud, the impact tick dispatches a realtime SUBSTITUTE look on the beat
and simultaneously STAGES the cloud scene — sent without tearing realtime down, with the
keepalive yielding — so the cloud drop look takes over whenever it lands (typically 1-5 s into a
16-32-beat drop). Pre-drop blackout always rides realtime tactical frames. F2-forward bonus:
every drop impact now has realtime frames for future within-drop choreography to ride,
regardless of which transport the rotation picked.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_look_director.py`, `led_dispatch_policy.py`, `led_dispatch_coordinator.py`,
  `govee_realtime_runner.py`, `tests/test_led_look_director.py`,
  `tests/test_led_dispatch_coordinator.py`, `tests/test_govee_realtime_runner.py`,
  `tests/test_led_state_manager.py`, the Part E docs, and the AWR-150 registry row (exists
  before you start; `rg -n "AWR-150" docs/status/active_work_registry.md`, STOP if absent).
- Out of scope: `govee_frame_engine.py` / `govee_frame_engine_client.py` (commands cross the IPC
  transparently — `emergency`/`desired`/`assert` semantics are untouched; the ONE new runner
  method must be forwarded, see Task 3 note), `state_manager.py`, config schema, banks, cloud
  adapter internals, laser/SoundSwitch.
- Behavior that must not change: AWR-149 plan/rotation semantics (the cloud pick CONSUMES its
  plan slot — the substitute is a rendering stand-in, not a re-pick); operator/emergency
  blackout paths; AWR-145 retry; cloud-handoff-never-dims; the cloud `room_blackout` path for
  rigs whose adapter has no `tactical_blackout` (cloud-only adapter keeps today's behavior).
- Error handling: if staging the cloud scene errors, the realtime substitute already owns the
  drop — log and continue (the room is lit and on-beat); never fail the impact because the
  stage failed.

### Task 1 - `govee_realtime_runner.py`: keepalive yield (event-cancelled, capped)

New constant `KEEPALIVE_YIELD_MAX_S = 30.0`. New thread-safe method
`request_keepalive_yield() -> None`: under `self._lock`, set `_keepalive_yield_until =
now + KEEPALIVE_YIELD_MAX_S` (field init in `__init__`). While `now < _keepalive_yield_until`,
the keepalive branch (`:271-284`) does NOT fire (the on-demand assert branch is governed by the
cancel rule below, not by the clock). The yield is CANCELLED (field set to 0.0) inside:
`set_desired` (any value), `fire_trigger`, `request_activate_assert`, `emergency_stop`,
`force_deactivate` — any new intent reclaims or releases the strip explicitly; a blackout must
never find the keepalive asleep. Brightness requests and anchors do NOT cancel. Rationale: the
staged cloud scene knocks the strip out of razer whenever it arrives; the yield stops the 2 s
keepalive from stealing it back for the rest of the drop; the cap guarantees a forgotten yield
cannot disable the knockout-healing keepalive for more than 30 s.

Note for the frame-engine deployment: add the `{"t": "keepalive_yield"}` message to
`govee_frame_engine.py`'s `handle_message` map and a mirror `request_keepalive_yield()`
lock-and-enqueue method on `GoveeFrameEngineClient` — mechanical, same pattern as
`request_activate_assert`; these two files may be touched for EXACTLY this forwarding and
nothing else. The yield is intentionally NOT replayed on child respawn (a fresh child's
keepalive re-asserting razer is the safe direction).

### Task 2 - `led_dispatch_coordinator.py`: `stage_cloud_takeover(decision) -> bool`

New method: dispatch a cloud decision WITHOUT the realtime teardown — `accepted =
bool(self._adapter.trigger(decision))`; when accepted call `self._runner.request_keepalive_yield()`
and return True; do NOT `force_deactivate`, do NOT touch the owner state machine, do NOT update
the dwell bookkeeping (`_last_dispatch_*` — the realtime substitute that fired the same tick
already recorded the dispatch; recording twice would poison the WI-3 dwell gate). Docstring
states the ownership note: owner remains REALTIME_RAZER for the yield window; the next normal
dispatch resolves ownership through the existing paths (`trigger` realtime branch re-asserts;
cloud branch force-deactivates; blackout force-releases).

### Task 3 - `led_dispatch_policy.py`: blackout always realtime; impact = RT substitute + stage

1. **ALREADY LANDED (interim guard, commit `e707199`, 2026-07-08 live session — do not
   re-implement):** `_dispatch_led_smart_drop_blackout` takes the realtime tactical branch for
   ANY previewed drop transport; the cloud `room_blackout` path remains only for cloud-only
   adapters (no `tactical_blackout`) and no-preview ticks; test
   `test_cloud_previewed_drop_still_gets_realtime_tactical_blackout` pins it. Verify it is
   intact at your HEAD, then move on.
2. In the drop-impact dispatch path (the role="drop" fire that stamps
   `_led_drop_look_fired_anchor`, `:1786`; read `_dispatch_led_automation`'s drop branch and
   verify the exact send site at implementation time [assumed-site: the `_led_send_decision`
   call whose accepted branch calls `_led_note_drop_decision_accepted`]): when the committed
   decision's backend is `cloud_diy` AND the adapter has both `tactical_blackout`-style realtime
   capability (duck-check: `stage_cloud_takeover` present) — dispatch the REALTIME SUBSTITUTE
   decision (Task 4 director helper) through the normal `_led_send_decision` path (it must pass
   the coordinator's realtime branch: owner acquire + assert + dwell bookkeeping, exactly like
   any RT drop), and on `"accepted"` also call `stage_cloud_takeover(committed_decision)`.
   Bookkeeping rules: `_led_note_drop_decision_accepted` runs for the COMMITTED decision (drop
   identity, pairing, presentation) exactly as today [verify its current call args at the site];
   the substitute must NOT queue its own paired post_drop (Task 4 guarantees) and must NOT
   overwrite the committed-decision cache. When the adapter is cloud-only (no
   `stage_cloud_takeover`), keep today's cloud dispatch unchanged.
3. AWR-145 retry interplay: a rejected substitute dispatch retries the SAME substitute decision
   via the existing retry slot; the stage call happens only on the accepted outcome (both the
   original and the retry accepted paths — `_led_retry_auto_dispatch`'s accepted branch needs
   the same stage hook; verify at `led_dispatch_policy.py:298-331`).

### Task 4 - `led_look_director.py`: realtime substitute helper

`substitute_realtime_drop(self, *, diy_eligible=None, look_preference=None) ->
LEDLookDecision | None`: select from the drop bank's `realtime_razer` subset (after the same
eligibility/preference filters and known-name filter as `_automation_decision_for_role`), using
the existing `(role="drop", "realtime_razer")` shuffle bag and backend cursor (advance ONLY that
backend cursor, NEVER `self._role_cursors["drop"]` — the plan slot was consumed by the committed
cloud pick), do NOT call `_queue_paired_post_drop` (the committed cloud pick already queued its
pair), reason string `"role_entry:drop:rt_substitute"`. Returns None when the drop bank has no
realtime looks (caller then keeps today's cloud dispatch — a cloud-only drop bank is the
operator's explicit configuration and keeps current behavior).

## Part C - Invariants That MUST Still Hold (live safety)

- **The impact pair never waits on the internet**: pre-drop blackout = realtime tactical frames
  (instant, keepalive-healed); the on-beat drop render = realtime whenever the drop bank has any
  realtime look. Cloud latency can only affect WHEN the cloud look upgrades the room mid-drop,
  never whether the beat lands lit.
- **Cloud drops stay in rotation** (operator rule): the plan still picks them, their identity
  still drives pairing/presentation, their scene still shows for most of the drop section.
- Operator/emergency blackout unchanged and never weakened: every yield-cancel path proves a
  blackout finds the keepalive awake; brightness-0 backstop untouched.
- Keepalive yield is bounded (30 s cap) and cancelled by ANY new intent; a fresh frame-engine
  child never inherits a yield.
- No dwell/cooldown double-recording from the stage call; owner-state transitions stay within
  the existing three paths; no push-loop/StateManager-thread I/O is added (all new methods are
  lock-and-flag; the stage call runs where `_led_send_decision` already runs).
- AWR-149 determinism: the plan cursor advances exactly once per drop pick (by the committed
  pick); substitutes never advance it.

## Part D - Tests (single-module runs ONLY until the operator declares the mix over)

- `tests/test_govee_realtime_runner.py`: yield suppresses the 2 s keepalive (fake clock); each
  of the five cancel methods restores it; the 30 s cap restores it; a yield does not suppress
  brightness drain or emergency teardown.
- `tests/test_led_dispatch_coordinator.py`: `stage_cloud_takeover` triggers the adapter without
  `force_deactivate`/owner change/dwell bookkeeping and requests the yield on accept; rejected
  stage → no yield.
- `tests/test_led_look_director.py`: substitute picks only realtime drop looks, advances only
  the backend cursor (plan cursor unchanged — assert the next planned pick is what it would
  have been), queues no pair; returns None on a cloud-only drop bank.
- `tests/test_led_state_manager.py`: cloud drop pick → blackout goes tactical (transport
  realtime), impact dispatches the RT substitute + stages the committed cloud decision;
  cloud-only adapter keeps today's behavior end-to-end; retry-then-accept also stages once.
- Full `python3 -m unittest discover tests` ONLY after the operator's all-clear; expected green
  except the 5 known environmental reds.

## Part E - Acceptance

1. Part D green (full suite deferred until operator all-clear); 3 hard checks green.
2. `led_govee` docs_update where affected: `docs/subsystems/led_govee.md` (impact-transport
   guarantee section), `docs/status/feature_status_matrix.md`,
   `docs/status/validation_matrix.md`, `docs/validation/software_test_inventory.md`; registry
   row AWR-150 → implemented/software-tested. Status language: implemented / software-tested /
   hardware-unvalidated only.
3. No changes outside the Part B file list; explicit-path commits.

## When You Finish

Plain-language operator summary: a drop can never again sit dark waiting for the internet — the
blackout and the drop hit both ride the local realtime path on the beat, and when the rotation
picks one of the cloud drop scenes, that scene now joins a second or two into the drop (taking
over from the realtime look) instead of gambling the impact moment; nothing was removed from the
rotation; watch on the next mix: every drop lands lit on the beat, cloud drop scenes appear
mid-drop, and no blackout ever sticks past its drop.
