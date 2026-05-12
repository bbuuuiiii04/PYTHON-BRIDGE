# Logging Implementation Handoff

Status: HISTORICAL

Audited against the current checkout on 2026-05-12.

This document preserves historical context about the logging rollout. Runtime
operator guidance now lives in `docs/subsystems/logging.md`.

## Historical Summary

- Introduced `LoggingManager` (`logging_manager.py`) and queue instrumentation
  fields (`__trace_id`, `__enqueue_mono`) for traceability and event latency.
- Added higher-signal StateManager lifecycle/event summaries and bounded logging
  stats snapshots.
- Added dynamic runtime logging controls via
  `/tmp/rb_ss_bridge_v2_logging.json` with optional override path via
  `BRIDGE_LOG_CONTROL`.
- Added `BRIDGE_LOG_JSON=1` output mode and retained `SIGHUP` manual reload.

## Canonical Runtime Guidance

For active operation and debugging procedures, use:

- `docs/subsystems/logging.md`

This historical handoff is intentionally concise to avoid duplicated,
conflicting operator guidance.

## Addendum (2026-05-12)

- Smart Drop blackout masking in `laser_executor.py` was decoupled from scene
  policy gates (`high_impact_blocked`, `role_cooldown_blocked`, and
  `same_scene_skip`) after core auto/mapping validity checks pass.
- Blackout arming now executes before those policy gates so transition masking
  can still engage even when the scene itself is later policy-blocked.
- Auto-gate failures and missing scene mappings still suppress blackout arming
  by design.
- Added regression coverage in `tests/test_laser_executor.py` for:
  - cooldown-blocked scene + blackout arm
  - high-impact-blocked scene + blackout arm
  - auto-gate blocked contexts (blackout must not arm)
  - missing scene mapping (blackout must not arm)
