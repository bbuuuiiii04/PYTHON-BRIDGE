# Laser Director MIDI Mapping Workflow

Status: Operator setup notes for Laser Director / SoundSwitch MIDI mapping.

Audience: Coding agents, maintainers, and operators.

This document explains how SoundSwitch MIDI mapping is being prepared manually before Laser Director implementation.

## Core idea

SoundSwitch does not know about Python scene names directly.

The bridge will eventually send MIDI notes into macOS IAC Driver. SoundSwitch will listen to that IAC bus and trigger whatever SoundSwitch cue, Static Look, or Autoloop has been manually mapped to that MIDI note.

The relationship is:

```text
Laser Director scene name
  -> configured MIDI note/channel
  -> IAC Driver virtual MIDI bus
  -> SoundSwitch MIDI mapping
  -> SoundSwitch Static Look or Autoloop
```

Example:

```text
house_drop_1
  -> MIDI channel 1, note 40
  -> IAC Driver Bus 1
  -> SoundSwitch mapped button/control
  -> House Drop Autoloop or Static Look
```

## Current operator MIDI setup

The operator is using:

```text
IAC Driver Bus 1
```

Do not assume `IAC Driver Bus 2`.

Implementation should allow the MIDI output port to be configured.

Recommended config field:

```json
{
  "laser_director": {
    "midi_output_port": "IAC Driver Bus 1"
  }
}
```

If the operator later switches to another bus, the config should change without code changes.

## Important naming rule

Scene names are arbitrary config keys.

Do not hardcode scene names such as:

```text
low_sweep
drop_hit
breakdown_blackout
```

Those names are examples only.

Valid real cue names may look like:

```text
safe_static
house_phrase_1
house_buildup_1
house_pre_drop_1
house_drop_1
house_drop_sustain_1
house_breakdown_1
transition_safe_1
emergency_blackout
dubstep_drop_1
techno_breakdown_1
```

The code should separate musical roles from actual scene names.

Example:

```text
role: drop_scene
actual configured scene: house_drop_1
```

A personality/config profile should map roles to real scene names:

```text
safe_scene -> safe_static
default_scene -> house_phrase_1
phrase_scene -> house_phrase_1
buildup_scene -> house_buildup_1
pre_drop_scene -> house_pre_drop_1
drop_scene -> house_drop_1
post_drop_scene -> house_drop_sustain_1
breakdown_scene -> house_breakdown_1
transition_scene -> transition_safe_1
emergency_scene -> emergency_blackout
```

## Manual SoundSwitch mapping method

SoundSwitch MIDI mapping requires the operator to select a mappable SoundSwitch control and then send/press a MIDI note.

Because there may not be a physical MIDI controller, the operator is using a small local Python web pad to send virtual MIDI notes into IAC Driver Bus 1.

The workflow is:

```text
1. Open SoundSwitch.
2. Ensure SoundSwitch is listening to IAC Driver Bus 1.
3. Create or select a Static Look or Autoloop.
4. Put SoundSwitch into MIDI mapping/listen mode for that control.
5. Click a note button in the local MIDI web pad.
6. SoundSwitch records that note as the mapping.
7. Operator writes down which cue maps to which note.
```

The local web pad is not part of the production bridge. It is only a setup/debugging helper.

## Local MIDI web pad

The operator created a local Python environment in:

```text
~/midi-test
```

The environment uses:

```text
mido
python-rtmidi
```

A local script such as:

```text
midi_web_pad.py
```

runs a browser page at:

```text
http://127.0.0.1:8765
```

The browser page sends MIDI notes to IAC Driver Bus 1.

Coding agents should understand that this tool is only for manual mapping and local testing. It should not be required by the bridge runtime.

## MIDI behavior expected from Laser Director

Laser Director should eventually mimic the same note presses that the local web pad sends.

A scene config should be able to specify:

```json
{
  "house_drop_1": {
    "safety_class": "high_impact",
    "fallback_scene": "house_drop_sustain_1",
    "midi": {
      "kind": "note_pulse",
      "channel": 1,
      "note": 40,
      "velocity": 127,
      "duration_ms": 80
    }
  }
}
```

When Laser Director chooses `house_drop_1`, `MidiOutput` should send a short MIDI note pulse:

```text
note_on channel 1 note 40 velocity 127
wait duration_ms
note_off channel 1 note 40
```

The note pulse should be sent by the MIDI output thread, not by `StateManager._push_tick`.

## MIDI note/channel assumptions

Standard MIDI supports:

```text
128 notes per channel: 0 through 127
16 channels: 1 through 16
```

For early Laser Director testing, use:

```text
MIDI channel 1
IAC Driver Bus 1
```

Recommended early note range:

```text
36 through 60
```

This gives enough room for initial laser cues without making the mapping hard to manage.

Do not require use of other MIDI channels in MVP.

## Suggested first mappings

These are suggestions only. The actual mapping is controlled by the operator in SoundSwitch.

Safe initial test set:

```text
safe_static -> channel 1, note 36
house_phrase_1 -> channel 1, note 37
emergency_blackout -> channel 1, note 44
```

Later example house mappings:

```text
house_buildup_1 -> channel 1, note 38
house_pre_drop_1 -> channel 1, note 39
house_drop_1 -> channel 1, note 40
house_drop_sustain_1 -> channel 1, note 41
house_breakdown_1 -> channel 1, note 42
transition_safe_1 -> channel 1, note 43
```

These are not hardcoded requirements. They are operator mapping examples.

## Static Looks vs Autoloops

SoundSwitch cue types are chosen manually by the operator.

Suggested use:

```text
Static Looks:
- safe_static
- emergency_blackout
- transition_safe_1
- short drop hits

Autoloops:
- house_phrase_1
- house_buildup_1
- house_drop_sustain_1
- house_breakdown_1
```

Coding agents should not assume whether a scene is a Static Look or Autoloop. The bridge only sends MIDI. SoundSwitch decides what that MIDI note triggers.

## Safety notes

Emergency blackout must be treated as a first-class safety path.

The SoundSwitch blackout cue should be manually built so laser fixtures are included and set to off/intensity zero.

Laser Director should support a configured emergency scene, for example:

```text
emergency_scene -> emergency_blackout
```

Emergency blackout should not depend on phrase gates or cooldowns.

## Implementation requirements for coding agents

When implementing Laser Director MIDI support:

1. Do not hardcode `IAC Driver Bus 2`.
2. Use the configured MIDI output port, currently likely `IAC Driver Bus 1`.
3. Do not hardcode scene names like `drop_hit` or `low_sweep`.
4. Treat scene names as arbitrary strings from config.
5. Treat role names as policy-level fields.
6. Send MIDI from `MidiOutput`, not directly from `StateManager`.
7. Use non-blocking enqueue from policy code.
8. Use a bounded MIDI queue.
9. Support dry-run mode.
10. Missing MIDI dependency or missing MIDI port must degrade Laser Director only; OS2L must continue.
11. Do not call MIDI APIs from `StateManager._push_tick`.
12. Do not call `conn.status()` from `StateManager._push_tick`.

## Debugging expectations

During development, the operator may test MIDI manually with the local web pad.

If SoundSwitch reacts to the web pad but not to Laser Director, check:

```text
- Is Laser Director sending to the same IAC bus?
- Is the MIDI channel the same?
- Is the MIDI note the same?
- Is SoundSwitch listening to the same MIDI input?
- Is dry_run still enabled?
- Is MidiOutput degraded?
- Did the MIDI queue drop the message?
```

The bridge status JSON should expose enough information to debug this:

```json
{
  "laser_director": {
    "enabled": true,
    "dry_run": false,
    "current_scene": "house_drop_1",
    "last_reason": "drop_scene",
    "midi": {
      "port": "IAC Driver Bus 1",
      "connected": true,
      "sent_count": 12,
      "drop_count": 0,
      "send_error_count": 0
    }
  }
}
```

## Production note

The local web MIDI pad is not required once Laser Director is implemented.

It is only used to teach SoundSwitch which MIDI notes correspond to which cues and to manually test the IAC bus.

The production path should be:

```text
LaserDirector
  -> MidiOutput
  -> IAC Driver Bus 1
  -> SoundSwitch MIDI mapping
  -> Static Look / Autoloop
```
