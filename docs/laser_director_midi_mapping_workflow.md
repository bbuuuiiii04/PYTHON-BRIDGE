# Laser Director MIDI Mapping Workflow

Status: Operator setup notes for Laser Director / SoundSwitch MIDI mapping.

Audience: Coding agents, maintainers, and operators.

This document explains how SoundSwitch MIDI mapping is being prepared manually before Laser Director implementation.

## No manual JSON editing workflow

Use the bridge menu bar wizard instead of hand-editing `laser_director.json`.

```text
1. Open SoundSwitch.
2. Put SoundSwitch into MIDI mapping mode.
3. Map a SoundSwitch cue/autoloop to a MIDI note.
4. Open menu bar -> Map Lasers.
5. Choose personality: house or default (default aliases to house).
6. Choose role: groove, buildup, drop, post_drop, breakdown.
7. Enter MIDI note 0–127.
8. Review warnings and save.
9. Restart bridge if prompted.
10. Keep dry_run=true until ready for live MIDI.
```

Banks are multiple MIDI mappings for the same role. The bridge rotates banks
round-robin (example: house groove notes 37, 45, 46).

To add multiple looks for one role, map the same personality + role again with
a new MIDI note. The wizard automatically adds that mapping to the role bank.

At any wizard prompt, press Escape or type `back` to go back.

## Wizard Setting Runtime Contract

Only settings with runtime effect are exposed in normal wizard setup.

| Wizard Label | Config Key | Model Field | Runtime Consumer | Proof Test |
| --- | --- | --- | --- | --- |
| Personality + role mapping | `personalities.<p>.*_scene` + role bank keys | `LaserPersonality` role fields + banks | `LaserSceneExecutor._bank_for_role()` and role selection path | `tests/test_laser_map_wizard.py::test_second_mapping_auto_appends_bank_keeps_primary` |
| MIDI note | `scenes.<scene>.midi.note` | `LaserMidiMessage.note` | `MidiOutput._send_trigger()` | `tests/test_laser_map_wizard.py::test_verify_runtime_contract_passes_for_wizard_config` |
| Trigger behavior | `scenes.<scene>.midi.behavior` | `LaserMidiMessage.behavior` | `LaserSceneExecutor._materialize_midi()` + `MidiOutput._send_trigger()` | `tests/test_laser_executor.py::test_hold_beats_materializes_with_context_bpm` |
| Role cooldown | `scenes.<scene>.cooldown_beats` (normalized per role bank) | `LaserScene.cooldown_beats` | `LaserSceneExecutor._is_role_cooldown_blocked()` | `tests/test_laser_executor.py::test_role_cooldown_blocks_then_allows_after_beats` |
| Role bank rotation | `personalities.<p>.phrase_bank` etc | `LaserPersonality.*_bank` | `LaserSceneExecutor._choose_bank_scene_locked()` | `tests/test_laser_executor.py::test_drop_bank_rotates_each_crossing` |

Internal-only fields such as `safety_class` stay hidden from normal setup and are
available only in **Advanced Safety Metadata**.

Default operator mappings are SoundSwitch autoloops triggered by MIDI pulse.
Hold behavior is advanced and should only be used when a SoundSwitch control
requires hold-to-play MIDI input.

## Timing / Cooldowns

The wizard includes a visible **Edit Timing & Cooldowns** menu.

- Groove phrase length: how often normal groove changes can happen.
- Minimum scene hold: how long a scene must stay before normal changes replace it.
- Buildup lookahead: how many beats before a Smart Drop buildup is allowed.
- Role cooldown: how soon the same exact role look can be triggered again.
  Changing a role cooldown updates every mapping in that role's bank.
- Hold behavior: pulse / hold_beats / hold_ms / note_on / note_off.

The normal wizard flow does not ask for laser classification. Safety metadata
(`safety_class`) is assigned automatically from role defaults and kept internal.
An optional **Advanced Safety Metadata** menu is available for expert edits.

Role cooldown is a runtime-enforced setting. A role cooldown change updates all
mappings in that role bank and is enforced in `LaserSceneExecutor` using
`ctx.abs_beat` (not wall-clock time).

Drop style options:
- **Drop mode** (default): one drop autoloop mapping; post-drop reuses drop mapping.
- **Emphasized drop**: separate drop and post-drop autoloop mappings.

The wizard includes **Verify mappings actually work**, which loads saved config,
runs a dry runtime simulation through `LaserSceneExecutor`, and reports PASS/FAIL
for role mapping outputs and cooldown enforcement.

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

IAC bus clarification:

```text
Current example/manual-test/default operator bus: IAC Driver Bus 1
```

The current operator mapping setup is using:

```text
IAC Driver Bus 1
```

The MIDI output port must stay configurable via Laser Director config.
Neither Bus 1 nor Bus 2 should be hardcoded in Python code.
SoundSwitch MIDI input must match the configured Laser Director output port.

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
pre_drop_scene -> (deprecated/inert for automatic policy)
drop_scene -> house_drop_1
post_drop_scene -> house_drop_sustain_1
breakdown_scene -> house_breakdown_1
transition_scene -> transition_safe_1
emergency_scene -> emergency_blackout
```

Note: `pre_drop_scene` may remain in config for backward compatibility, but
automatic Laser Director policy intentionally does not select it. Smart Drop
already performs the final pre-drop autoloop cut/rearm workflow, and the
buildup look should persist through the Smart-Drop countdown until drop
crossing.

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

Scene config required fields reference:

```text
- scene name
- safety_class
- fallback_scene
- midi mapping with note/channel/kind
- optional cooldown_beats
- optional immediate
```

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

## Scene banks (role-level round-robin)

Personalities may optionally provide role banks that reference existing scene keys:

```text
phrase_bank, buildup_bank, drop_bank, post_drop_bank, breakdown_bank
```

Rules:

- banks are optional
- missing/empty bank falls back to single-scene role field
- bank picks are deterministic round-robin (never random)
- banks rotate on role-entry/eligible trigger only, not every tick
- phrase MIDI waits for phrase/autoloop boundary eligibility and does not fire
  immediately when post-drop expires mid-cycle

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

Optional later dubstep mappings (operator examples only, not hardcoded requirements):

```text
dubstep_phrase_1 -> channel 1, note 50
dubstep_buildup_1 -> channel 1, note 51
dubstep_pre_drop_1 -> channel 1, note 52
dubstep_drop_1 -> channel 1, note 53
dubstep_drop_sustain_1 -> channel 1, note 54
dubstep_breakdown_1 -> channel 1, note 55
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

For live operation, performer-facing override and blackout actions should be
handled directly in SoundSwitch or through the normal external safety path.
Bridge-side `laser_scene` / `laser_blackout` compatibility commands are for
internal/dev/test use and should not be treated as the primary live workflow.

The SoundSwitch blackout cue should be manually built so laser fixtures are included and set to off/intensity zero.

Laser Director should support a configured emergency scene, for example:

```text
emergency_scene -> emergency_blackout
```

Emergency blackout should not depend on phrase gates or cooldowns.

Laser Director automatic scene selection is subordinate to the existing bridge
autoloop/scripted architecture:

```text
- no playing track => no visible Laser Director output
- no loaded active track => no visible Laser Director output
- scripted context => no visible Laser Director output
- automatic musical scenes only when autoloop readiness is true
```

For phrase/default policy timing, Laser Director should use existing autoloop
tick/rearm lifecycle signals from `StateManager` as the timing authority. It
should not treat standalone continuous beat math as the phrase trigger source.

Same-scene reason-only updates are status/debug changes and should not be
treated as new trigger candidates. Future live MIDI defaults should trigger on
non-empty scene-name changes only.

Future live executors must treat `scene == ""` as send-nothing.

## First live-test safety checklist

```text
1. Prove safe static look fires correctly.
2. Prove gentle movement / phrase look fires correctly.
3. Prove idle/no-output behavior while stopped/stale/unarmed/scripted.
4. Do not start live testing with high-impact drop, strobe, or aggressive scenes.
```

## Implementation requirements for coding agents

When implementing Laser Director MIDI support:

1. Do not hardcode any IAC bus in Python code.
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

## Live dependency expectation

For live mode (`dry_run=false`), the bridge expects Python MIDI dependencies:

```text
mido
python-rtmidi
```

`MidiOutput` uses `mido` with the configured output port (for example
`IAC Driver Bus 1`). If dependencies or ports are missing, `MidiOutput` must
degrade safely while OS2L and the rest of bridge runtime continue.

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
  -> LaserSceneExecutor
  -> MidiOutput
  -> IAC Driver Bus 1
  -> SoundSwitch MIDI mapping
  -> Static Look / Autoloop
```
