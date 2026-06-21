---
doc_status: research-current
truth_level: binary-static-analysis-corroborating
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: read-only static analysis of local SoundSwitch 2.10.3 arm64 and x86_64 binaries using symbols and headless Ghidra; no process attach or modification; hardware-unvalidated
---

# SoundSwitch binary reverse-engineering addendum

## Scope and method

This records load-bearing binary evidence used by the closure report. Project
bytes, controlled diffs, tests, and passive wire captures remain the behavioral
authority; decompilation corroborates physical readers/writers and explains
state/precedence.

The analysis used `nm`, `c++filt`, `otool`, and Ghidra 12.1.2 headless against
the local SoundSwitch 2.10.3 universal binary. GhidraMCP was not required. No
app bundle, project, or live process was patched, injected, attached, or
modified.

## `.ssfile` readers and writers

The actual call chain is:

```text
SoundSwitchDocData::Read
  -> MainTrack::Read
  -> AttributeCueTrack::Read
  -> AttributesCueMap::Read
  -> AttributeCueTrackEntry::Read
```

The paired writers establish:

- `AttributesCueMap`: `u32 version`, `u32 count`, repeated 16-byte ClassId plus
  `u32 stored_key`;
- `AttributeCueTrackEntry`: `u32 version`, `u32 constant`, signed elapsed/tick,
  `u32 raw_reference`;
- `SoundSwitchDocData` trailer: `u32, bool, u32, bool`, 10 physical bytes.

Both architectures use the stored integer without a provenance branch inside
these readers. Wire behavior remains the final product rule: current 2.10.3
runtime emits positive references as `raw-1`, including a cold-open newly
authored track. The editor/writer can store the visually selected direct number;
that mismatch is application behavior, not a second loader format.

`AttrChangeEntry::Read/Write` proves the 17-byte records are version-2
intensity `AttributeTrack` entries. `Channel::SetIntensity` requires a channel
with the intensity flag. The current 19-channel profile has none, so nonzero
entries are retained but do not write CH1-CH19.

## Cue/cache rendering

`SSPlaybacks::RefreshCache`, `RefreshCache_2PlayBackMode`,
`RefreshCache_4PlayBackMode`, and `SetChannelAttributes` establish:

- playback buffers are read first;
- a selected Static Look cache is passed as an overlay;
- cached generic attributes replace matching base attributes;
- absent static-cache attributes leave the base value;
- blackout is a final intensity/shutter mask;
- two-playback mode blends with levels/crossfader;
- four-playback mode chooses the greatest upfader and retains prior owner on a
  tie.

The bounded player consumes the bridge's stricter single-active-deck authority,
so it does not need to duplicate SoundSwitch's inactive multi-deck composition.

## Static Looks

Relevant symbols and arm64 entry points:

| Function | Address | Finding |
| --- | --- | --- |
| `StaticLook::Write` | `0x10033a728` | writes version 5, name, four fixture maps, generic attributes |
| `StaticLook::Read` | `0x10033aa6c` | reads the same fields with backward-version branches |
| `StaticLooks::Write` | `0x10033bd44` | writes version 1, count 32, then 32 slots |
| `StaticLooks::Read` | `0x10033bcc8` | reads version/count and 32 fixed slots |
| `StaticLooksManager::Write` | `0x10033c284` | writes GUID-keyed Venue collections |
| `StaticLooksManager::Read` | `0x10033c4fc` | reads GUID plus one `StaticLooks` object per collection |
| `RebuildStaticLookCache` | `0x100335230` | converts intensity, strobe, colour, position, and generic maps |
| `EnableStaticLook` | `0x100338770` | direct index; matching release resets to `-1` |
| `EnableStaticLookOverride` | `0x100338794` | same direct-index momentary behavior for override |
| `RefreshCache` | `0x100338198` | override index wins over normal static index |
| `SetChannelAttributes` | `0x10033710c` | applies matching static generic attribute after base value |

`StaticLookDown` and `StaticLookOverrideDown` pass their integer index and bool
directly to the playback methods. This proves that a control path suffix
`StaticOverrideN` selects zero-based slot `N`. Release rerenders current base;
there is no saved-frame stack.

The current mapped slots' intensity values are 1.0 and strobe fractions are
0.0. Stored position GUIDs have no pan/tilt target in the current laser profile.
Their generic map therefore contains the exact active CH1-CH19 output.

## Learned MIDI map

The current learned registry uses `utils::Recordable`.

| Function | Address | Finding |
| --- | --- | --- |
| `operator<<(ControlMapDetail)` | `0x10012f5ec` | writes type, data byte, channel, control path, enabled |
| `operator>>(ControlMapDetail)` | `0x10012f674` | reads the same fields |
| collection writers/readers | `0x10012f6fc`..`0x10012faa8` | collection ID, binding vector, feedback vector |
| `NamedControlMapCollections::saveData` | `0x10013134c` | rewrites version/status and complete device map |
| `loadData` | `0x100133538` | reads version 1; clears/resaves corrupt data |
| `newControlMapping` | `0x10013c240` | builds a detail from MIDI status/data/device/control |
| new-map completion lambda | `0x10013c9d4` | calls `saveData` |
| `unmapControl` | `0x100131f70` | removes matching control path and calls `saveData` |
| `removeAllMap` | `0x1001312d4` | clears and calls `saveData` |
| `removeDeviceMap` overloads | `0x1001316d8`, `0x10013189c` | remove device/collection and call `saveData` |

This closes go-forward learned-map add/edit/delete detection. A complete export
rescan reads the exact current registry; no UI provenance or filename heuristic
is required.

## Static and blackout precedence

`RefreshCache` selects a cache pointer as follows:

```text
if static_override_index >= 0: override slot cache
else if normal_static_index >= 0: normal slot cache
else: no static cache
```

`SetChannelAttributes` then applies per-channel static-cache values after base
playback and before final global safety overrides. `SetBlackoutOverrideState`
stores one bool used as a final zero/shutter mask. Clearing it does not copy a
prior frame; the next refresh recomputes current playback/static state.

The bridge's current note-0 blackout uses a different UI surface—a momentary
Autoloop selection—but observed note-on/note-off and file-3 zero output have the
same stateless player consequence.

## Fixture and hardware boundary

Binary Venue routing converts saved group/channel attributes into engine
channels before output. Current bytes and passive wire prove the bounded target
Universe 0 CH1-CH19. The research does not claim physical laser/Enttec address
or optical validation. A changed Venue/profile/routing fingerprint must fail
export until separately decoded and validated.

## Net result

The binary evidence closes the physical `.ssfile`, Static Look, learned MIDI
map, override precedence, blackout, and current-profile intensity questions
needed by the bounded perfect exporter/player spec. Remaining limits are
version/profile compatibility and hardware validation, not unknown active
SoundSwitch behavior.
