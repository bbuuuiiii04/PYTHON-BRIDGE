---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (diagnosis 2026-07-07, Fable 5)
last_verified_commit: 35e0a90
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — Govee health reporting: silent mirror sends + stuck "degraded"

Contract key: `led_govee` (`docs/agents/change_contracts.yml:101`). Two observability defects from
the 2026-07-07 LED deep diagnosis. Neither changes light output; both fix status surfaces the
operator must be able to trust live (the "blackout doesn't work" symptom was unreproducible partly
because health surfaces can mislead in both directions).

## Part A — Context & Root Cause (verified; read, do not implement)

1. **Mirror strip failures are invisible.** `GoveeRuntimeSender.send`
   (`govee_runtime_sender.py:352-359`) sends to the primary target, then iterates
   `target_cfg.mirror_targets` and **discards** each mirror's `_send_to_target` result. The module
   imports no logging at all. A mirror strip that is offline / wrong device id / API-rejecting is
   completely silent — status reads healthy while one strip is dark. [confirmed]
2. **`degraded_reason="circuit_open"` latches forever.** `govee_scene_adapter.py:335-358`: on a
   successful send, the clear condition (`:340`) only matches reasons starting `"send_"` or equal
   to `"malformed_response"`. `"circuit_open"` (set at `:358` after 3 consecutive failures) matches
   neither and is never cleared. Meanwhile the boolean `circuit_open` (`:311`, via
   `_is_circuit_open_locked`) correctly self-heals — so after one transient cloud blip the
   forwarded status self-contradicts for the rest of the session: `circuit_open=false` next to
   `degraded=true, degraded_reason="circuit_open"`. Both keys are in
   `_LED_ADAPTER_STATUS_SAFE_KEYS` (`led_dispatch_policy.py`) and reach the operator panel.
   [confirmed]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `govee_runtime_sender.py`, `govee_scene_adapter.py`, `tests/`, Part E docs.
- Light output, send ordering, retry/queue/rate-limit behavior: unchanged. These are
  reporting-only fixes.
- Logging discipline (repo rule): outcome changes at INFO/WARNING, edge-triggered (log on state
  CHANGE, never per frame); no per-send spam. Follow the edge-trigger pattern used by
  `govee_realtime_runner`'s health lines.

### Task 1 — `govee_runtime_sender.py`: mirror send visibility
- Add the standard module logger (match sibling modules' `import logging` / `log = logging.getLogger(...)`
  convention used elsewhere in the repo, e.g. `govee_scene_adapter.py`).
- Keep per-mirror last-outcome state (`dict[str, bool]`). In the mirror loop (`:356-359`),
  capture each mirror's result; on transition ok→fail emit ONE
  `log.warning("[RGB] mirror-send-degraded target=%s err=%s", mirror_name, <result's error field>)`,
  on fail→ok emit ONE `log.info("[RGB] mirror-send-recovered target=%s", mirror_name)`.
- Expose the map in the sender's existing status surface if one exists (grep for a `status()`
  method; if none exists, the log lines suffice — do NOT invent a new status channel).
- Primary-result semantics unchanged: `send` still returns `primary`.

### Task 2 — `govee_scene_adapter.py`: let `circuit_open` degraded state heal
At `:340`, extend the success-path clear condition to also clear `"circuit_open"`:
```python
if (self._degraded_reason.startswith("send_")
        or self._degraded_reason in ("malformed_response", "circuit_open")):
    self._degraded_reason = ""
```
Rationale: a successful send proves the circuit is closed and service recovered; the sticky string
must agree with the self-healing `circuit_open` boolean.

## Part C — Invariants That MUST Still Hold

- No behavior change to sends, queueing, dedupe, circuit-breaker thresholds, or blackout's
  gate-bypass (`govee_scene_adapter.py:128-197`).
- No per-frame/per-send log lines (edge-triggered only).
- The push loop is not involved (both files run on worker/HTTP threads).

## Part D — Tests

Existing harness style, in-memory stubs:
1. Sender: mirror target failing → exactly one warning logged across N sends (`assertLogs`);
   recovery → exactly one info; primary return value unaffected throughout.
2. Adapter: trip the breaker (3 failures) → `degraded_reason == "circuit_open"`; one successful
   send → `degraded_reason == ""` and `degraded` False (assuming no other degrade source).

## Part E — Acceptance (definition of done)

- [ ] Tasks 1–2 implemented exactly; `python3 -m unittest discover tests` passes (documented env
      reds excepted).
- [ ] Contract `led_govee` `docs_update` (at minimum `docs/subsystems/led_govee.md` health/status
      section + `docs/status/active_work_registry.md`).
- [ ] `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py` pass.
- [ ] Status language: `implemented` / `software-tested`.

## When You Finish

Report changed files + tests, and the operator summary: "if the second strip ever stops taking
frames you'll now see one warning line instead of silence, and the LED status panel stops saying
'degraded' forever after a momentary cloud hiccup." Rollback: revert commit.
