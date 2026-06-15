# LED Look Mapping Workflow

Status: CURRENT SUPPORTING

This guide describes how to maintain LED look mappings for the room-perimeter
Govee strip without exposing secrets or enabling unsafe live behavior.

## Config Files

The committed example is:

```text
config/led_look_director.example.json
```

Do not commit a live local config containing real device identifiers. If a local
runtime config is needed, keep it outside git and point the bridge at it with:

```text
RBSS_LED_CONFIG=/path/to/local/led_look_director.json
```

`GOVEE_API_KEY` must come from the environment only. Do not place API keys in
JSON config, docs, tests, shell history snippets, or status output.

## Core Fields

- `enabled`: enables the LED lane.
- `dry_run`: keeps adapter output local and non-physical when true.
- `automation_enabled`: allows automatic role-entry decisions when true.
- `targets`: named physical or logical LED targets.
- `looks`: named actions such as scenes or blackout/off.
- `banks`: role-to-look lists for automation.
- `safe_default`: fallback/default look.
- `blackout`: emergency blackout/off look.
- `rate_limits`: queue, cooldown, request timeout, and shutdown timeout values.
- `safety`: brightness, strobe, flash duration, and scripted-mode policy.

## Roles And Banks

Automation uses LED-specific banks, separate from laser banks:

```text
ambient
groove
buildup
pre_drop
drop
post_drop
breakdown
utility
```

Only map looks that the operator has chosen and the device can support. Empty
banks are valid and fail soft; agents must not invent scene names.

## Current Operator Mapping

The current handoff mapped one H612D target, `Strip Light`, as
`room_perimeter`. The real device ID remains private. Operator-provided scene
names are encoded in the example config for groove, buildup, drop, and
breakdown banks. Ambient, pre-drop, post-drop, and safe default remain
conservative unless explicitly mapped later.

Safety choices currently recorded:

- max brightness: `100`
- strobe: allowed
- high-impact/drop cooldown: custom `4s` mapping choice
- phase-default high-impact/drop cooldown: `12s`
- max drop flash duration: `750ms`

## Manual JSONL Commands

The first operator surface is the JSONL command file:

```text
/tmp/rb_ss_bridge_v2_commands.jsonl
```

Supported LED commands:

```json
{"cmd":"set_led_look_director","enabled":true}
{"cmd":"led_scene","look":"room_drop_a","ttl_s":5}
{"cmd":"led_blackout","reason":"operator"}
{"cmd":"led_clear_blackout"}
{"cmd":"led_clear_scene_override"}
```

`led_clear_scene_override` clears only the manual scene override. It does not
clear emergency blackout. `led_clear_blackout` clears only emergency blackout;
if a manual override remains, the manual look may be re-emitted once.

## Safe Rehearsal Checklist

Before claiming live physical bridge behavior:

1. Confirm `GOVEE_API_KEY` is set in the local environment without printing it.
2. Confirm the strip is powered, paired, reachable, and named correctly.
3. Start with `dry_run=true` and confirm status shows the LED lane and adapter
   state without secrets.
4. Send one manual scene command and verify exactly one queued/accepted action.
5. Send `led_blackout` and verify blackout wins over the manual scene.
6. Send `led_clear_scene_override` while blacked out and verify blackout remains.
7. Send `led_clear_blackout` and verify the documented clear behavior.
8. Verify queue-full or adapter-degraded status does not affect SoundSwitch or
   lasers.
9. Only after an explicit live command gate, test physical output and record
   operator visual confirmation.

Event-facing use requires a later explicit human/operator approval and the
special event-use gate. Phase 8/9 approval alone does not open event use.
