# LED Look Director Design

Status: CURRENT SUPPORTING

This document describes the implemented LED Look Director lane. The controlling
phase and gate rules remain in
`docs/plans/completed/led_agent_orchestrator_workflow.md`; code remains the final source
of truth.

## Purpose

The LED lane controls room-perimeter Govee strips as macro scene devices. It is
not a DMX replacement and is not intended for beat-accurate fixture control.
The goal is to select broad room looks at meaningful musical transitions while
keeping SoundSwitch, laser output, and bridge timing isolated.

## Runtime Shape

```text
JSONL/manual command or SmartPhrasing role-entry
  -> StateManager
  -> LEDLookDirector
  -> GoveeSceneAdapter
  -> Govee worker-owned transport
```

`StateManager` owns the runtime LED state:

- enabled latch
- manual scene override
- emergency blackout latch
- automation gate reason and counters
- sanitized LED status

`LEDLookDirector` is policy-only. It chooses a configured look from manual
override, emergency blackout, or a configured LED role bank.

`GoveeSceneAdapter` owns transport queueing and worker-side I/O. Its public
`trigger(...)` method is bounded and non-blocking. Slow Govee API behavior must
not enter `StateManager._push_tick`.

## Priority Rules

Priority is fixed:

```text
emergency blackout > manual override > automation > safe/default policy
```

Manual override suppresses automatic role-entry until cleared. Emergency
blackout suppresses everything until explicitly cleared. Clearing a scene
override must not clear emergency blackout.

## Automation Boundaries

Automatic role-entry is gated by config and current runtime state:

- LED lane must be enabled.
- `automation_enabled` must be true.
- Current Phase 8 automation is dry-run/config-gated only; `dry_run=false`
  automation remains closed until a later live gate.
- Scripted mode is conservative by default. Automatic LED role changes do not
  run during scripted mode unless explicitly enabled in config.
- Triggers are role-entry/transition keyed. The bridge must not trigger every
  tick or every beat.

Smart Drop blackout coupling is not part of this phase. It remains a later
gated requirement.

## Status And Failure

LED status is exposed under `led_look_director` in the runtime status snapshot.
Status must be sanitized:

- no `GOVEE_API_KEY`
- no full device IDs
- no raw request or response bodies
- no raw headers

Adapter failures are fail-soft and visible through degraded/status fields such
as queue depth, degraded reason, last error, dry-run state, and counters. They
must not stop SoundSwitch or laser behavior.
