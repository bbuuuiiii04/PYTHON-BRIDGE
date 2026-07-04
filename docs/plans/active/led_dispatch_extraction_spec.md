# Codex Implementation Spec - LED Dispatch Extraction (P5)

status: implemented (software-tested)
last_verified_commit: bd1370a
owner: operator (Brandon) via Claude Fable 5 orchestration session 2026-07-03

Two phases, **one commit per phase** (P1 → P2). Every claim below was re-verified against HEAD
`85aac85` on 2026-07-03; labels: [confirmed] = read in current code or executed,
[assumed] = inferred and stated where load-bearing.

Baseline before any change [confirmed, ran 2026-07-03]:
`python3 -m unittest discover tests` → **2762 tests, OK (skipped=5, expected failures=1)**.

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

`state_manager.py` is 5,221 lines at HEAD [confirmed]. Roughly 1,300 of them are LED dispatch
*policy* that grew inside `StateManager`:

- LED instance-field init: `state_manager.py:433-533` (all `self._led_*` fields plus the
  director-status seeding block) [confirmed]. Line 480 (`self._last_sp_snapshot`) sits inside
  this block but is **shared smart-phrasing state, not LED-only** [confirmed: written by
  smart-phrasing update path, read by `_led_sp_state_with_offset`].
- Status surface: `led_status_provider` (754), `color_engine_status_provider` (834),
  `get_active_beat_anchor` (839), `_sanitize_led_adapter_status` (855),
  `_sanitize_led_scene_ref` (914), `_set_led_automation_gate_reason` (931) [confirmed].
- Event handling: `_handle_led_event` (1590), `_led_target_exists` (1641) [confirmed].
- The five dispatch paths [confirmed]:
  1. `_dispatch_led_manual_command` (1653-1712)
  2. `_dispatch_led_smart_drop_blackout` — realtime tactical branch (1735-1794)
  3. `_dispatch_led_smart_drop_blackout` — cloud branch (1796-1911)
  4. `_dispatch_led_automation` (1913-2216)
  5. `_dispatch_led_idle_ambient` (2218-2340)
- Gate/role/lifecycle helpers: 2342-2792 (`_gate_led_automation`, `_led_role_from_smart_phrasing`,
  drop-lifecycle helpers, phrase-latch helpers, `_led_automation_role_key`, `_led_abs_beat`,
  `_clamp_led_beat`, etc.) [confirmed].
- Backend offset selection: `_led_sp_state_with_offset` (4920), `_led_sp_state_for_next_backend`
  (4939) [confirmed].

**Root cause:** one trigger/accept/reject bookkeeping ritual (counters `_led_trigger_count`,
`_led_rejected_count`, `_led_automation_trigger_count`, `_led_automation_gated_count`; fields
`_led_last_error`, `_led_last_look`; gate reason via `_set_led_automation_gate_reason`) is
copy-pasted across the five paths and has drifted. These counters and gate reasons feed
`led_status_provider` — the operator's "why aren't my LEDs changing" surface.

**Confirmed inter-copy divergences (load-bearing; PRESERVE, do not unify):**

| Path | Divergence [all confirmed] |
|---|---|
| manual (1653) | No gate-reason calls, no `_led_automation_gated_count`, **no log lines at all**; `decision is None` → sets `_led_last_error=""` AND `_led_last_look=""` |
| tactical blackout (1735) | Uses `tactical_blackout(drop_preview)` not `adapter.trigger`; on accept sets `_led_last_look="realtime_blackout"` and `_led_smart_drop_blackout_key`; **no log on adapter-rejected**; log strings `tactical-blackout-error` / `tactical-blackout-accepted` |
| cloud blackout (1796) | On accept sets `_led_smart_drop_blackout_key`; log lines include `phase=`; director-error path also sets `_led_last_auto_role_key = blackout_key` after bookkeeping (1825) |
| automation (1913) | On accept **clears** `_led_smart_drop_blackout_key` and, when `role == "drop"`, calls `_led_note_drop_decision_accepted`; `decision is None` → `no_look:{role}` gate + `log.info` no-look line; director-error path sets `_led_last_auto_role_key = role_key` after bookkeeping (2052) |
| idle ambient (2218) | Director-error path sets BOTH `_led_last_auto_role_key` and `_led_last_idle_role_key` (2271-2272); **no `log.warning` on adapter-rejected** (2332-2340); `decision is None` → `no_look:ambient` gate, no log |

**Consistent (safe to centralize) [confirmed by line-by-line comparison]:**

- adapter-exception order everywhere: `_led_last_error = f"adapter_error:{type(exc).__name__}"` →
  `_led_rejected_count += 1` → (automation paths only) `_led_automation_gated_count += 1` →
  gate reason `"adapter_error"`.
- accepted order everywhere: `_led_trigger_count += 1` → (automation paths)
  `_led_automation_trigger_count += 1` → per-path key side effects → `_led_last_error = ""` →
  `_led_last_look = <look>` → (automation paths) gate reason `""`. Field-write ordering between
  these steps has no observable interleaving (single thread, no logging between writes)
  [confirmed: no log call sits between the field writes in any copy].
- rejected (adapter returned falsy) order everywhere: `_led_rejected_count += 1` → (automation
  paths) `_led_automation_gated_count += 1` → `_led_last_error = "adapter_rejected"` → (automation
  paths) gate reason `"adapter_rejected"`.
- director-exception order everywhere: `_led_last_error = f"director_error:{type(exc).__name__}"`
  → `_led_rejected_count += 1` → (automation paths) `_led_automation_gated_count += 1` → gate
  reason `"director_error"`.

**Why a mixin, not a delegate object:** tests reach into `sm._led_*` fields and private methods
directly ~300 times across 14 files (142 references in `tests/test_led_state_manager.py` alone)
[confirmed via grep]. Fields and method names must therefore remain attributes of the
`StateManager` instance. A mixin preserves every access path; a delegate object would need ~30
read/write forwarding properties or mass test edits, destroying the "unchanged tests prove
unchanged behavior" property.

**Logger [confirmed]:** `state_manager.py:117` is `log = logging.getLogger("state_manager")` — a
fixed literal, so the new module can use the identical logger name and log output stays
byte-identical.

**Importers [confirmed]:** no module outside `state_manager.py` imports any LED constant or LED
helper from it. `__main__.py:52` imports only `AUTOLOOP_MASTER_PHRASE_ARM_ENV`,
`LIVE_BPM_FOLLOW_ENV`, `PHRASE_ANCHOR_ENV`, `SMART_DROP_ENV`, `SMART_REARM_EXPERIMENT_ENV`,
`StateManager`. Tests import only `StateManager`, `SmartDropTickResult`,
`STATE_MANAGER_PROFILE_ENV`, `_send_direct_autoloop_rearm`, `_pack_operational_state`.

**`StateManager` has no base class today** (`state_manager.py:360`) [confirmed].

## Part B - Tasks (implement exactly, in order; one commit per phase)

### Absolute Rules

- **Out of scope — do not touch:** `led_dispatch_coordinator.py` (backend-routing adapter, not
  policy), `led_look_director.py`, `led_color_engine.py`, `govee_*.py`, `beat_sync_engine.py`,
  all `laser*` files, `runtime_status.py`, `__main__.py` (except: no change is expected there at
  all), any config file, any capture corpus.
- **Existing test files must not be edited.** New test files may be added only per Part D.
- **Behavior that must not change:** every field/counter transition, gate-reason string, role-key
  format, log line format-and-order, and `led_status_provider` payload must be byte-identical for
  identical event/tick sequences. This is a pure refactor.
- **Operator-reserved code must survive:** `LEDColorEngine.lock/unlock/set_palette/queue_palette/
  shift` (not in this file, but do not "clean up" call sites) and the `post_drop_cycle_beats`
  knob path (`_led_post_drop_cycle_beats`, 2627) move as-is.
- **Error handling:** preserve the existing per-path exception mapping exactly. Do not add new
  try/except, do not remove existing ones, no silent fallbacks beyond what the current code does.
- **No new threads, locks, blocking I/O, or subprocess use anywhere** — everything stays on the
  StateManager thread (AGENTS.md §6).
- Git: work directly on `main`, no branches, no force-push, never `git clean`.
- **Parallel session (live as of 2026-07-03):** another sanctioned session is executing
  `docs/plans/active/audit_2026_07_03_followups_spec.md` and owns `live_bpm.py`,
  `probe_live_bpm.py`, and that spec file — do not touch, stage, revert, or commit them; commit
  ONLY the files this spec changes (use explicit `git add <paths>`, never `git add -A`/`git
  commit -a`). If `git commit` hits a concurrent index lock, wait 5 s and retry. If
  `tools/check_agent_contracts.py` fails ONLY about
  `docs/plans/active/audit_2026_07_03_followups_spec.md` being unclassified, that is the parallel
  session's in-flight state, not yours — note it and proceed; any other check failure blocks.

### Phase 1 — single bookkeeping path (commit: `LED dispatch P1: unify trigger/accept/reject bookkeeping`)

#### Task 1 - `state_manager.py`: add three helpers

Insert immediately after `_gate_led_automation` (currently ends at 2362), exactly:

```python
    def _led_tick_director(
        self,
        context: LEDContext,
        *,
        role: str,
        role_key: str,
        automation: bool,
        active_deck: Optional[int] = None,
    ) -> tuple[Any, bool]:
        """Single director.tick error ritual. Returns (decision, ok).

        On director exception: records director_error bookkeeping (and, for
        automation paths, the gated count + gate reason) and returns (None, False).
        Per-path post-error effects (role-key latches, warning logs) stay at the
        call sites because they intentionally differ per path.
        """
        try:
            return self._led_look_director.tick(context), True
        except Exception as exc:
            self._led_last_error = f"director_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            if automation:
                self._led_automation_gated_count += 1
                self._set_led_automation_gate_reason(
                    "director_error",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            return None, False

    def _led_gate_no_look(
        self,
        *,
        reason: str,
        role: str,
        role_key: str,
        active_deck: Optional[int] = None,
    ) -> None:
        """Single decision-is-None gating ritual for automation-family paths."""
        self._led_automation_gated_count += 1
        self._set_led_automation_gate_reason(
            reason,
            active_deck=active_deck,
            role=role,
            role_key=role_key,
        )

    def _led_send_decision(
        self,
        decision: Any,
        *,
        look: str,
        role: str,
        role_key: str,
        automation: bool,
        active_deck: Optional[int] = None,
        trigger_fn: Any = None,
    ) -> str:
        """Single adapter trigger/accept/reject bookkeeping ritual.

        Returns "accepted", "rejected", or "error". Counters, _led_last_error,
        _led_last_look, and the automation gate reason mutate ONLY here for
        trigger outcomes. Per-path side effects (blackout keys, drop-lifecycle
        notes, log lines) stay at the call sites because they intentionally
        differ per path; none of them log between these field writes, so the
        observable stream is unchanged.
        """
        if trigger_fn is None:
            trigger_fn = self._led_scene_adapter.trigger
        try:
            accepted = bool(trigger_fn(decision))
        except Exception as exc:
            self._led_last_error = f"adapter_error:{type(exc).__name__}"
            self._led_rejected_count += 1
            if automation:
                self._led_automation_gated_count += 1
                self._set_led_automation_gate_reason(
                    "adapter_error",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            return "error"

        if accepted:
            self._led_trigger_count += 1
            if automation:
                self._led_automation_trigger_count += 1
            self._led_last_error = ""
            self._led_last_look = look
            if automation:
                self._set_led_automation_gate_reason(
                    "",
                    active_deck=active_deck,
                    role=role,
                    role_key=role_key,
                )
            return "accepted"

        self._led_rejected_count += 1
        if automation:
            self._led_automation_gated_count += 1
        self._led_last_error = "adapter_rejected"
        if automation:
            self._set_led_automation_gate_reason(
                "adapter_rejected",
                active_deck=active_deck,
                role=role,
                role_key=role_key,
            )
        return "rejected"
```

Note the ordering subtlety [confirmed against all five copies]: in the rejected branch,
`_led_last_error = "adapter_rejected"` comes AFTER the two counter bumps and BEFORE the gate
reason; in the exception branch, `_led_last_error` comes FIRST. The helper above encodes exactly
that. One deliberate, unobservable reordering: the current adapter-exception copies set the gate
reason before their `log.warning`, and the accepted copies apply blackout-key side effects before
the gate reason; with the helper, call-site side effects and logs run after the helper returns.
No log line is emitted between the reordered field writes, so log order and status payloads are
unchanged.

#### Task 2 - `state_manager.py`: route `_dispatch_led_manual_command` through the helpers

Replace the body from the `try:` at 1668 through the end of the method (1712) so that:

- director tick uses `_led_tick_director(context, role="", role_key="", automation=False)`; on
  `ok is False` → `return` (current behavior: error bookkeeping then return; the manual path has
  no gate reason and no logs — `automation=False` reproduces that exactly).
- The `set_manual_override` / `set_emergency_blackout` pre-calls and the
  `unknown_look` rejection stay exactly as they are (1668-1679) — they are inside the same `try`
  today. **Preserve that:** exceptions from `set_manual_override`/`set_emergency_blackout` must
  still produce `director_error:*` bookkeeping. Wrap them together with the tick: keep one `try`
  around the pre-calls that mirrors today's mapping, or pass a closure to `_led_tick_director` —
  the resulting behavior must be: any exception in pre-calls or tick → `director_error` mapping
  with no gate reason and no log. Simplest correct shape: keep the existing single `try/except`
  for the pre-calls + `tick`, and inside the `except` call nothing but the same three lines the
  helper would run with `automation=False` — OR restructure so the pre-calls happen inside a
  small local function passed as the tick. Choose the former (keep the existing try/except for
  this one path and do NOT call `_led_tick_director` here) if the closure version is not clearly
  byte-equivalent; in that case the manual path routes only its trigger side through
  `_led_send_decision`. State in the final report which shape you chose.
- `decision is None` branch stays at the call site verbatim (clears `_led_last_error` AND
  `_led_last_look`).
- The trigger/accept/reject tail (1698-1712) becomes:
  `self._led_send_decision(decision, look=str(getattr(decision, "look", "")), role="", role_key="", automation=False)`
  with no outcome-dependent call-site code (the manual path has none today).

#### Task 3 - `state_manager.py`: route both `_dispatch_led_smart_drop_blackout` branches

Tactical branch (1743-1794): replace the try/accept/reject block with
`outcome = self._led_send_decision(drop_preview, look="realtime_blackout", role="smart_drop_blackout", role_key=blackout_key, automation=True, active_deck=active, trigger_fn=tactical_blackout)`
then call-site handling:
- `outcome == "error"` → the existing `log.warning("[RGB] tactical-blackout-error ...")` (1755-1762)
  verbatim, then `return`.
- `outcome == "accepted"` → set `self._led_smart_drop_blackout_key = blackout_key`, then the
  existing `log.info("[RGB] tactical-blackout-accepted ...")` (1776-1783) verbatim, then `return`.
  (Note: helper already set `_led_last_look="realtime_blackout"` via `look=`.)
- `outcome == "rejected"` → `return` (no log today).

Cloud branch (1805-1911): director tick becomes
`decision, ok = self._led_tick_director(context, role="smart_drop_blackout", role_key=blackout_key, automation=True, active_deck=active)`;
on `not ok` → existing `log.warning("[RGB] director-error ...")` (1817-1824) verbatim, then
`self._led_last_auto_role_key = blackout_key`, then `return`. The `decision is None` branch uses
`_led_gate_no_look(reason="no_look:smart_drop_blackout", role="smart_drop_blackout", role_key=blackout_key, active_deck=active)`.
The trigger tail uses `_led_send_decision(decision, look=look, role="smart_drop_blackout", role_key=blackout_key, automation=True, active_deck=active)` with call-site handling:
- `"error"` → existing adapter-error `log.warning` (1855-1865) verbatim, `return`.
- `"accepted"` → `self._led_smart_drop_blackout_key = blackout_key`, existing trigger-accepted
  `log.info` (1880-1890) verbatim, `return`.
- `"rejected"` → existing adapter-rejected `log.warning` (1902-1911) verbatim.

#### Task 4 - `state_manager.py`: route `_dispatch_led_automation` and `_dispatch_led_idle_ambient`

Automation (2032-2216): director tick → `_led_tick_director(..., role=role, role_key=role_key, automation=True, active_deck=active)`; on `not ok` → existing director-error `log.warning`
(2045-2051) verbatim + `self._led_last_auto_role_key = role_key` + `return`. **Careful:** today the
tick is guarded by `if decision is None:` inside the `try` (2032-2034) because a committed drop
decision may already exist; preserve that — only call the director when `decision is None`, e.g.
`if decision is None: decision, ok = self._led_tick_director(...)`. `decision is None` after tick
→ `_led_gate_no_look(reason=no_look_reason, ...)` + the existing no-look `log.info` (2066-2072)
verbatim. Trigger tail → `_led_send_decision(decision, look=look, role=role, role_key=role_key, automation=True, active_deck=active)`:
- `"error"` → existing adapter-error `log.warning` (2161-2170) verbatim, `return`.
- `"accepted"` → `self._led_smart_drop_blackout_key = ""`; `if role == "drop": self._led_note_drop_decision_accepted(decision, sp_state)`; existing trigger-accepted `log.info` (2187-2196) verbatim; `return`.
- `"rejected"` → existing adapter-rejected `log.warning` (2208-2216) verbatim.

Idle ambient (2259-2340): director tick → `_led_tick_director(..., role="ambient", role_key=role_key, automation=True, active_deck=active)`; on `not ok` → `self._led_last_auto_role_key = role_key` AND `self._led_last_idle_role_key = role_key` (both, per divergence table; no log) + `return`.
`decision is None` → `_led_gate_no_look(reason="no_look:ambient", role="ambient", role_key=role_key, active_deck=active)` (no log). Trigger tail → `_led_send_decision(decision, look=look, role="ambient", role_key=role_key, automation=True, active_deck=active)`:
- `"error"` → existing adapter-error `log.warning` (2301-2308) verbatim, `return`.
- `"accepted"` → existing trigger-accepted `log.info` (2322-2329) verbatim, `return`.
- `"rejected"` → nothing (no log today; helper did all bookkeeping).

**Phase 1 gate before committing:** `python3 -m unittest tests.test_led_state_manager` then the
full suite → must be **2762 OK (5 skipped, 1 expected failure)** with zero edits to existing
tests. If any LED test fails, fix the refactor, never the test.

### Phase 2 — move the policy to `led_dispatch_policy.py` (commit: `LED dispatch P2: move LED dispatch policy out of state_manager.py`)

This phase is a **pure text move**: no logic edits, no renames, no signature changes.

#### Task 5 - create `led_dispatch_policy.py`

Module docstring must state: LED dispatch *policy* mixed into `StateManager`; runs entirely on
the StateManager thread; owns no threads/locks/blocking I/O; all `_led_*` fields live on the
`StateManager` instance (tests and `led_status_provider` depend on that); the backend-routing
*adapter* is `led_dispatch_coordinator.py` and policy must not merge into it.

Imports it needs [confirmed by reading the moved code]: `logging`, `os as _os`, `re`,
`from dataclasses import replace`, `from typing import Any, Optional`,
`from .config import LED_BACKSTEP_SEEK_BEATS`, `from .led_models import BeatAnchor, LEDContext`,
`from .smart_phrasing import SmartPhrasingState`,
`from .govee_frame_renderer import REALTIME_EFFECT_PARAM_KEYS, SLOT_EFFECTS, MAX_SLOTS`.
Type-only references to `DeckState`/`SmartPhrasingSnapshot` may use string annotations or a
`TYPE_CHECKING` import — do not create an import cycle (`led_dispatch_policy` must never import
`state_manager`).

Logger — exactly this, with the comment:

```python
# Same logger name as state_manager.py so moved log lines stay byte-identical.
log = logging.getLogger("state_manager")
```

Move these module constants from `state_manager.py` (delete there):
`LED_PHRASE_MONOTONIC_ENV` (177), `LED_DEFAULT_DROP_IMPACT_BEATS` (179),
`LED_DEFAULT_GROOVE_CYCLE_BEATS` (180), `LED_DEFAULT_POST_DROP_CYCLE_BEATS` (181),
`LED_HOLD_RELEASE_BEATS` (184), `_LED_DROP_IMPACT_PREDECESSORS` (185), `LED_MAX_DROP_IMPACTS`
(189). [Confirmed: no importer outside state_manager.py references any of them.] After the move,
grep `state_manager.py` for each name — zero hits may remain.

Define `class LEDDispatchPolicyMixin:` containing, moved verbatim (docstrings and comments
included):

1. `_init_led_dispatch_state(self, led_look_director, led_scene_adapter, led_color_engine) -> None`
   — new method whose body is the current `__init__` block 433-533 **minus line 480**
   (`self._last_sp_snapshot = None` stays in `StateManager.__init__` at its current position).
2. Status surface: `led_status_provider`, `color_engine_status_provider`,
   `get_active_beat_anchor`, `_sanitize_led_adapter_status`, `_sanitize_led_scene_ref`,
   `_set_led_automation_gate_reason`.
3. Events: `_handle_led_event`, `_led_target_exists`.
4. Dispatchers + Phase-1 helpers: `_dispatch_led_manual_command`,
   `_dispatch_led_smart_drop_blackout`, `_dispatch_led_automation`, `_dispatch_led_idle_ambient`,
   `_gate_led_automation`, `_led_tick_director`, `_led_gate_no_look`, `_led_send_decision`.
5. Role/lifecycle/latch helpers: `_led_should_smart_drop_blackout`, `_preview_led_drop_decision`,
   `_preview_led_decision_for_role`, `_led_drop_anchor_for_blackout`, `_led_same_drop_anchor`,
   `_led_drop_decision_for_anchor`, `_led_diy_eligible_predicate`,
   `_consume_led_committed_drop_decision`, `_led_effective_role_for_dispatch`,
   `_led_role_has_mapped_look`, `_led_role_from_smart_phrasing`, `_led_buildup_active`,
   `_led_drop_marker_anchor`, `_led_drop_impact_allowed`, `_led_drop_lifecycle_should_clear`,
   `_led_arm_drop_lifecycle`, `_led_note_drop_decision_accepted`, `_clear_led_drop_lifecycle`,
   `_led_abs_beat`, `_led_post_drop_cycle_beats`, `_reset_led_phrase_latch`, `_clamp_led_beat`,
   `_advance_led_phrase_latch`, `_led_automation_role_key`.
6. Backend offset selection: `_led_sp_state_with_offset`, `_led_sp_state_for_next_backend`.

If, while moving, a listed method turns out to read a non-LED `StateManager` attribute that does
not exist yet at `_init_led_dispatch_state` time, that is fine — the mixin runs only on a fully
constructed instance; do NOT reorder `__init__`.

#### Task 6 - `state_manager.py`: shrink

- Add `from .led_dispatch_policy import LEDDispatchPolicyMixin` (plus re-import of any moved
  constant ONLY if a non-moved use remains — expected: none).
- `class StateManager:` (360) → `class StateManager(LEDDispatchPolicyMixin):`.
- Replace the `__init__` block 433-533 with `self._last_sp_snapshot: Optional[SmartPhrasingSnapshot] = None` followed by
  `self._init_led_dispatch_state(led_look_director, led_scene_adapter, led_color_engine)` at the
  same position.
- Delete every moved method/constant from `state_manager.py`. These LED touchpoints STAY in
  `state_manager.py` [confirmed list]: the event-router branch (1536-1543), the `RB_RESTARTED`
  idle-ambient call (1503), `_led_hold_active` writes (2919, 2985, 3029, 5119), `_led_rt_beat`
  writes (2981, 4438), all `_dispatch_led_*` / `_led_sp_state_for_next_backend` /
  `_clamp_led_beat` call sites inside the push tick (4305, 4345, 4486, 4528, 4561-4569 and the
  clamp call), and unrelated fields between 433-533 that were excluded above.
- Drop now-unused imports from `state_manager.py` (`BeatAnchor`, `LEDContext`,
  `REALTIME_EFFECT_PARAM_KEYS`, `SLOT_EFFECTS`, `MAX_SLOTS`, `LED_BACKSTEP_SEEK_BEATS`, `re`,
  `replace` — each ONLY if genuinely unused after the move; verify with grep, do not guess).

#### Task 7 - contracts and docs (same commit as Task 5/6)

- `docs/agents/change_contracts.yml` → `led_govee`: add `led_dispatch_policy.py` to `code_globs`
  and `LEDDispatchPolicyMixin` to `key_symbols`.
- `AGENTS.md` §4 LED/Govee row: add `led_dispatch_policy.py` to the file list.
- `docs/subsystems/led_govee.md`: update wherever it says the dispatch policy lives in
  `state_manager.py`; describe the mixin boundary in one short paragraph (policy in
  `led_dispatch_policy.py`, mixed into StateManager, fields on the instance, adapter unchanged).
- `docs/status/active_work_registry.md`: AWR-117 row already exists (added when this spec
  landed); update its status text to implemented/software-tested.
- Remaining `docs_update` entries of the `led_govee` contract
  (`feature_status_matrix.md`, `support_matrix.md`, `validation_matrix.md`,
  `hardware_validation_log.md`, `software_test_inventory.md`,
  `task_playbooks/change_led_govee_behavior.md`): inspect each; a pure refactor changes no
  feature status, so most need no content change — but re-verify each one's statements against
  the new layout and bump its `last_verified_commit`-style header (follow each doc's existing
  header convention) where the doc has one. The playbook likely names `state_manager.py` for
  dispatch logic — fix any such location references.
- Status language: this work is `implemented` / `software-tested` only. Never "complete/ready".

#### Task 8 - verification before the P2 commit

Run and require all green:

```bash
python3 -m unittest tests.test_led_state_manager
python3 -m unittest discover tests           # 2762 OK, 5 skipped, 1 expected failure
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 -c "import rb_ss_bridge_v2.state_manager"   # run from parent dir
```

Also record: `wc -l state_manager.py led_dispatch_policy.py` before/after, and
`grep -c "_led_" state_manager.py` after (expect only the stay-behind touchpoints).

## Part C - Invariants That MUST Still Hold (live safety)

- `StateManager` remains the central runtime owner and the **only** `DeckState` writer; the mixin
  never mutates `DeckState` (it only reads `d.playing`, `d.meta.*`, `d.load_gen`, `d.scripted_id`)
  [confirmed for all moved methods].
- The 200 Hz push loop gains **no** blocking network/socket/MIDI/filesystem/subprocess I/O and no
  locks; the extraction adds zero threads. `_push_tick`/`_push_tick_inner` call flow is unchanged.
- `RBStateReader` event ordering (`ANLZ_PATH` before `TRACK_LOADED`) is untouched.
- `led_status_provider` payload keys, value semantics, counter arithmetic, and gate-reason strings
  are byte-identical.
- Held SoundSwitch Static Override, laser policy/execution split, pack fail-closed semantics:
  untouched subsystems, zero diffs there.
- Docs-only edits in Task 7 change no runtime behavior.

## Part D - Tests

- **No existing test may be edited.** The existing suite (2762 tests, with
  `tests/test_led_state_manager.py` asserting counters, gate reasons, role keys, and status
  payloads through StateManager) is the behavior-preservation oracle for both phases.
- No new algorithm is introduced, so no new pure-function seam is required. Optional (only if
  trivially done): one new test file asserting that `_led_send_decision` outcome strings map to
  the documented counter deltas for automation=True/False — do not add fixtures or frameworks.

## Part E - Acceptance (definition of done)

- [ ] Two commits on `main`, one per phase, messages as specified.
- [ ] Full suite green after EACH phase: 2762 OK, 5 skipped, 1 expected failure; zero existing
      test files modified (`git diff --stat` proves it).
- [ ] Three hard checks pass after each phase.
- [ ] The trigger/accept/reject bookkeeping mutates counters/gate reasons in exactly one place
      (`_led_send_decision`, plus `_led_tick_director`/`_led_gate_no_look` for their rituals);
      the five paths route through them.
- [ ] `state_manager.py` line count reported before/after each phase (expect ≈5,221 → ≈5,050
      after P1 → ≈3,800-3,900 after P2; report actuals, do not force targets).
- [ ] `led_dispatch_policy.py` exists, imports cleanly, never imports `state_manager`, uses
      logger name `"state_manager"`.
- [ ] Contract + docs updates from Task 7 done; `led_govee` contract lists the new file.
- [ ] No operator-reserved code removed; no out-of-scope file touched.

## When You Finish

Report: changed files per phase, exact test/check outputs (counts, not "passed"), the line-count
delta, which shape Task 2 used for the manual path try/except, and any place where you had to
deviate from a stated line anchor because HEAD moved.

Plain-language operator summary to include: live behavior is intended to be identical — LEDs,
Govee, status pad readouts, and logs should look exactly the same; what changed is where the code
lives and that the five copies of LED bookkeeping became one, so future LED changes touch one
place. Unverified on hardware, as always; no bridge restart is required by this change but the
next restart picks it up; rollback is `git revert` of the two commits.
