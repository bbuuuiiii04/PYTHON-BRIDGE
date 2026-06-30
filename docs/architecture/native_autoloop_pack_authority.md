---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: 74706f4
last_verified_date: 2026-06-29
validation_scope: intended native Autoloop pack-runtime behavior; current code remains software-zero for native Autoloop DMX; no bridge run, restart, SoundSwitch, MIDI, serial, Enttec, DMX, laser, LED/Govee, Rekordbox live sampling, or hardware validation
---

# Native Autoloop Pack Authority

Status: AUTHORITATIVE TARGET BEHAVIOR; IMPLEMENTATION PLANNED

This document defines the intended bridge-owned native SoundSwitch Autoloop DMX
runtime. Behavior that differs from this document is a regression unless this
document is intentionally updated.

This is not a claim that native Autoloop DMX is implemented today. Current code
keeps the pack Autoloop base software-zero: `StateManager._drive_pack_output()`
clears the pack player selection when scripted transport is not active, and the
existing tests assert that `LaserPackPlayer.select_autoloop()` is not called.
The current SoundSwitch pack runtime already implements scripted tracks,
Static Override, blackout/status plumbing, pack reload/enable/backend commands,
and SoundSwitch-presence auto-switching.

## Meaning

Native Autoloop pack runtime means:

- SoundSwitch remains the authoring tool.
- The exporter publishes a verified canonical pack.
- When SoundSwitch is absent, the bridge owns Enttec CH1-19 DMX from that pack.
- When SoundSwitch is present, native pack output is suppressed and current
  SoundSwitch-controlled behavior remains unchanged.
- The bridge never runs a dual-driver mode where SoundSwitch and native pack
  output both drive the same fixtures.

The purpose is to operate the bridge as if SoundSwitch is not running, while
preserving the authored SoundSwitch looks and the bridge's existing musical
role-selection behavior.

## Operating Model

The supported workflow is:

1. Author or edit looks in SoundSwitch.
2. Use the exporter to publish the verified canonical pack.
3. Run the bridge normally.
4. If SoundSwitch is disconnected/absent, the existing pack auto-switch enables
   pack output when the pack runtime is available and configured for real output.
5. If SoundSwitch is connected/present, the auto-switch disables pack output and
   legacy SoundSwitch behavior is left alone.

Native runtime must consume only the verified canonical pack. It must not read
the live `.ssproj` or SoundSwitch files directly from the 200 Hz loop.

The existing pack runtime gates still apply. Pack output can physically send
frames only when pack output is enabled and the real-output prerequisites are
met: configured pack backend, `dry_run=false`, and an available Enttec port.
There is no separate native-Autoloop dry-run or observe mode.

## Precedence

Native Autoloop is the automatic base below existing higher-priority pack
behavior:

1. blackout/emergency
2. held Static Override layers
3. scripted track DMX
4. native Autoloop base
5. zero

Static Override Press/Toggle behavior is exported from SoundSwitch and remains
the authority. Native Autoloop must not change Static Override behavior. Held or
toggled Static Looks apply above the continuously rendered Autoloop base through
the existing pack-player layering model.

During blackout/emergency, native Autoloop selection and phase may keep advancing
internally, but rendered output remains blacked out by precedence. When blackout
clears, output resumes at the current musical phase/look, not from a frozen old
state.

## Mapping Authority

Laser Pad and the exported SoundSwitch pack are two views of the same operator
mapping:

- Laser/bridge config chooses the bridge role scene and MIDI note.
- The exported SoundSwitch pack resolves that MIDI note to a SoundSwitch
  Autoloop identity, rendered DMX content, and the actual SoundSwitch Autoloop
  display name.

For example, if the Laser Pad maps a drop scene to note `120`, and the
SoundSwitch project maps note `120` to `SSAutoLoop32.ssfile`, native runtime
uses the bridge role scene to choose note `120`, then uses the pack to resolve
and render `SSAutoLoop32.ssfile`.

If a Laser Pad scene/note is not mapped to a SoundSwitch Autoloop in the exported
pack, native runtime must fail closed for that look. It must not guess another
Autoloop, keep stale output, or fall across roles. A mapped Autoloop with no DMX
content is not an error; it is a valid authored dark look and renders dark.

The pack/runtime status must distinguish at least:

- `rendering_active`
- `empty_dark_look`
- `missing_binding`
- `missing_autoloop_file`
- `unsupported_layout`
- `soundswitch_present_native_suppressed`

Status/logs should show the bridge and SoundSwitch sides together:

`role`, `scene`, `note`, `soundswitch_name`, `target_identity`, `phase_tick`,
and a short reason.

The SoundSwitch Autoloop display name must be available from the canonical pack
at runtime. Runtime must not need to open the source `.ssproj` to show it.

## Musical Role Behavior

Native Autoloop runtime reuses the bridge's current musical role decisions:

- groove
- breakdown
- buildup
- drop
- post_drop

Existing bridge role logic remains the authority for when those roles are
active. Native runtime must not invent a separate role classifier.

The existing laser personality timing knobs are the source of truth for
drop/post-drop timing:

- `drop_impact_beats`, default `32`
- `max_drops_in_a_row`, default `2`
- `post_drop_cycle_beats`, retained as the intended native-DMX post-drop cycle
  cadence knob even though current laser cadence still comes from Autoloop ticks

Native runtime must reuse the existing `DropLifecycle` behavior for drop vs
post_drop timing rather than implementing a parallel drop resolver.

## Long Phrases And 32-Beat Cycling

SoundSwitch may randomly cycle to a different look after an Autoloop's 32-beat
window. The current bridge refire machinery exists to keep the bridge in control
of which Autoloop is active. Native runtime must keep that semantic behavior
without sending SoundSwitch MIDI/OS2L rearm/refire/correction commands.

Target behavior:

- Role changes win immediately.
- On role change, the old Autoloop is dropped and the new role's selected look
  anchors at phase `0`.
- Within the same role, the bridge owns the 32-beat reselect/cycle edge.
- On a same-role 32-beat edge, native runtime advances the role's bank/shuffle
  selection using the existing bridge/laser selection semantics.
- If the role has one mapped look, the same look is reselected and restarted.
- If the role has multiple mapped looks, selection stays role-confined.
- Between role-cycle edges, phase advances from bridge/Rekordbox beat position,
  not wall-clock time.

The selected Autoloop asset itself is not stretched to phrase length. It remains
the authored SoundSwitch Autoloop cycle rendered by `render_autoloop_frame()`.

## Role-Specific Rules

Groove:

- Groove is the normal non-breakdown, non-buildup, non-drop automatic role.
- Long groove/up phrases cycle or reselect within the groove bank on the
  bridge-owned 32-beat edge.
- One mapped groove look means the same look restarts.

Breakdown:

- Breakdown uses the existing breakdown role decision.
- Long breakdowns cycle or reselect within the breakdown bank on the bridge-owned
  32-beat edge.

Buildup:

- Buildup is the pre-drop runway behavior the bridge already computes.
- Buildup does not become a generic random long-phrase role.
- A role change into buildup anchors the selected buildup Autoloop at phase `0`.
- If a same-role 32-beat buildup edge occurs because configured timing allows it,
  selection remains confined to buildup looks.

Drop:

- Drop looks play during the configured drop impact window from an allowed
  drop/chorus anchor.
- Allowed impact behavior and chorus-to-chorus caps come from `DropLifecycle`
  and existing timing knobs.
- Drop selection remains confined to drop looks.

Post-drop:

- Post-drop starts after the drop impact window while the chorus/post-drop region
  remains active.
- Post-drop selection remains confined to post_drop looks.
- If no usable post_drop look is mapped, fallback behavior is to cycle drop
  looks, not to go dark.

## Reset And Reload

Native Autoloop selection state is bridge memory for:

- current role
- selected scene
- selected MIDI note
- resolved SoundSwitch Autoloop identity and display name
- anchor beat
- phase tick
- last 32-beat role-cycle edge
- role bank/shuffle state, where needed
- pack generation/hash

This state must reset on the same lifecycle boundaries as current laser
director/executor state:

- active track loaded
- active deck/master change
- stop/resume transitions
- scripted/idle transitions
- personality application, where role banks change

It also resets on pack reload/export replacement. On reload, old Autoloop state
is cleared before the new pack mapping is proven valid. A one-tick zero/native
base gap is acceptable and preferred over rendering stale output from the old
pack.

## Current Code Facts

- `AUTOLOOP_ARM_PHRASE_BEATS = 32` in `config.py`.
- `StateManager` currently computes SoundSwitch refire edges from
  phrase-anchor, marker, interval, or fallback-grid sources.
- `render_autoloop_frame()` renders a 19-channel CH1-19 tuple, wraps by
  `loop.cycle_ticks`, and fails closed to zero for unsupported/inactive looks.
- The pack loader already exposes `LoadedPack.autoloops`.
- The pack export `selection_map.json` already carries each resolved control's
  note, target identity, and `target_name`.
- The pack loader currently uses active IAC selections to mark active Autoloops,
  but it does not yet expose a runtime note-to-Autoloop lookup with display name.
- Current pack output status has states such as `autoloop_phase_blocked` and
  `software_zero_frame`; native Autoloop status should extend this surface.

## Non-Goals

Native Autoloop implementation must not:

- run or control SoundSwitch when native mode is active
- add a second output loop or second `PackOutputBackend.submit_frame()` caller
- add file, serial, socket, MIDI, subprocess, or blocking work to the 200 Hz
  push loop
- change Static Override Press/Toggle semantics
- change scripted-track priority or scripted transport behavior
- change laser/LED/Govee output behavior except for any explicit shared
  selection helper needed to expose the already-selected scene
- claim hardware validation without a real rig evidence run

## Validation Bar

Software implementation must include unit tests for the pure native selection
and phase resolver plus pack-driver integration tests.

Hardware/live status remains `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED`
until an operator-approved rig A/B check proves the native output against
SoundSwitch-authored looks. Starting SoundSwitch remains the fallback: the
existing auto-switch should suppress native pack output and restore legacy
SoundSwitch behavior.
