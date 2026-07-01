---
doc_status: research-current
truth_level: binary-static-analysis-corroborating
last_verified_commit: 03af947
last_verified_date: 2026-07-01
validation_scope: read-only static analysis of local SoundSwitch 2.10.3 binary; current GhidraMCP expansion is arm64-inspected with x86_64 symbol parity checked but not decompiled; no process attach or modification; hardware-unvalidated
---

# SoundSwitch binary reverse-engineering addendum

## Scope and method

This records load-bearing binary evidence used by the closure report. Project
bytes, controlled diffs, tests, and passive wire captures remain the behavioral
authority; decompilation corroborates physical readers/writers and explains
state/precedence.

The original analysis used `nm`, `c++filt`, `otool`, and headless Ghidra
against the local SoundSwitch 2.10.3 universal binary. The 2026-06-29 expansion
used GhidraMCP against the loaded thin arm64 program
`SoundSwitch_2_10_3_arm64`; the thin x86_64 program was imported but not used as
new evidence. The 2026-07-01 expansion used the same GhidraMCP path against the
operator-open SoundSwitch project and confirmed the `.ssfile` reader/writer/cache
path for the DD42028C parity investigation. No app bundle, project, or live
process was patched, injected, attached, or modified.

Inspected binary identity for the 2026-06-29 expansion:

- universal `/Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch` SHA256
  `636ed4aa48287d019a96c60f8d9107e75f3e72abe4f7b0aa8fa54aaa661984e9`;
- thin arm64 SHA256
  `b8db8335d96d090faf281ef782426d7995a7ae35d0fb656c490f3fd7db8f2694`;
- thin x86_64 SHA256
  `0e68b7273d456f44479fcca100724226780f5dfd6eedf8f7235cc465fce72593`.

## DD42028C parity expansion - 2026-07-01

GhidraMCP was callable in-session: `get_current_function` returned a function
from the opened SoundSwitch program, and `list_methods` returned the loaded
function table. The local universal binary still hashes to
`636ed4aa48287d019a96c60f8d9107e75f3e72abe4f7b0aa8fa54aaa661984e9` and reports
`x86_64 arm64`. Arm64 was decompiled; x86_64 was checked for corresponding
symbols with `nm` but was not separately decompiled.

Additional arm64 functions inspected for the DD42028C mechanism:

| Function | Address | Finding |
| --- | --- | --- |
| `SoundSwitchDocData::Read` | `0x1003318e8` | reads document/version, venue data, beatgrid, `MainTrack`, and the 10-byte trailer fields; no observed post-trailer cue remap branch |
| `MainTrack::ReadMain` | `0x1003cfb8c` | reads `SSTrack`, link/source/ref tracks, `AttributeCueTrack`, then resolves attributes cues |
| `AttributeCueTrack::ReadAttributesCueTrack` | `0x1003c26e4` | reads one `AttributesCueMap`, a timeline count, and one `AttributeCueTrackEntry` per row |
| `AttributesCueMap::Read` | `0x1003c0f00` | reads GUID plus `stored_key` records and builds GUID/key and key/GUID maps |
| `AttributesCueMap::AttributesCueMap` | `0x1003c0c2c` | writer-side map builder assigns zero-based keys from `AttributesCueLibrary` order |
| `AttributeCueTrackEntry::ReadEntry` | `0x1003c16ac` | reads version, constant, time, saved positive integer, and looks that integer up in the cue map |
| `AttributeCueTrackEntry::WriteEntry` | `0x1003c17dc` | writes the cue-map key for the entry's selected cue GUID |
| `AttributeCueTrack::WriteAttributesCueTrack` | `0x1003c2960` | writes the map plus every resolved entry |
| `AttributeCueTrack::ResolveAttributesCues` | `0x1003c2c00` | resolves saved entry GUIDs through `AttributesCueLibrary` |
| `AttributeCueTrackCache::Rebuild` | `0x1003c1e38` | starts from zero, then copies the previous cache entry and overlays converted cue attributes |
| `AttributeCueTrackCacheEntry::Lookup` | `0x1003c4960` | returns cached attribute value by key, otherwise zero |
| `SSPlaybacks::RefreshCache` | `0x100338198` | selects Static Override before normal Static Look, then playback cache path |
| `SSPlaybacks::SetChannelAttributes` | `0x10033710c` | uses base cache values, then applies matching Static Look cache values and final global overrides |
| `AutoLoopLayout::buildAutoLoopForStartingBeat` | `0x10025f22c` | stores Autoloop index/start/end/beat-count/document pointer |
| `AutoLoopLayout::GetStateForTime` | `0x10025f000` | converts time to beat position and 600-ticks-per-beat phase tick |
| `AutoLoopTrack::GetLightingState` | `0x10025e8b0` | renders the selected Autoloop document through venue lighting state |

This pass rejects one tempting explanation for DD42028C: no inspected
reader/writer/cache function consumes the addressed footer, retained prefix, or
shared-table bytes as a cue identity, remap, composition, cache-rebuild, or
runtime lookup table. DD42028C still proves generated cue replay is not exact
U0 parity, but the exact saved-byte mechanism is not present in the inspected
`.ssfile` path.

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

The current arm64 GhidraMCP passes show the reader/writer path uses the saved
integer without a provenance branch. `AttributesCueMap::AttributesCueMap` builds
cue-map keys from zero, and `AttributeCueTrackEntry::ReadEntry` / `WriteEntry`
read/write cue-map keys. Wire behavior remains the final product rule for the
legacy A5, legacy Autoloop, and cold-authored scripted evidence: current 2.10.3
runtime emits positive references as `raw-1`. DD42028C is now the explicit
exception proving that rule is not an exact-parity algorithm for every active
scripted document. The editor/writer can store the visually selected direct
number; that mismatch is application behavior, not a second loader format.

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

## Autoloop runtime bounds

The 2026-06-29 GhidraMCP pass also inspected arm64 Autoloop playback control
flow. This is useful context for RW-7 / T7d, but it is not a replacement for the
passive Art-Net phase corpus.

| Function | Address | Finding |
| --- | --- | --- |
| `SoundSwitchPlayBack::SetAutoloopPlayBackData` | `0x100333ce4` | stores an `AutoLoopTrack` as playback data and switches show state |
| `SoundSwitchPlayBack::GetAutoloopPlayBackData` | `0x1003340cc` | returns the active Autoloop playback object |
| `SoundSwitchPlayBack::ForcePlayAutoLoop` | `0x100334574` | switches to Autoloop playback and calls `AutoLoopTrack::OverrideAutoLoop` |
| `SSPlaybacks::LoadAutoLoopTrack` | `0x100335c64` | constructs an `AutoLoopTrack` from `AutoLoopsManager`, `SeratoBeatGrid`, and deck state |
| `SSPlaybacks::OnAutoLoopElapsed` | `0x1003388e8` | exits Autoloop override state when elapsed handling fires |
| `AutoLoopTrack::AutoLoopTrack` | `0x10025e570` | constructs `AutoLoopLayout` for the track |
| `AutoLoopTrack::OverrideAutoLoop` | `0x10025edb8` | records the selected index when applicable and rebuilds from a starting beat |
| `AutoLoopTrack::GetCurrentIndex` | `0x10025ee20` | exposes the current Autoloop index for manager/UI state |
| `AutoLoopTrack::GetProgress` | `0x10025ee6c` | reports progress from current layout time over Autoloop time |
| `AutoLoopLayout::AutoLoopLayout` | `0x100263bd4` | builds `BeatSpace` from `SeratoBeatGrid`, initializes indexes, then builds the default Autoloop from beat zero |
| `AutoLoopLayout::buildAutoLoopForStartingBeat` | `0x10025f22c` | selects/rotates an Autoloop index and stores index, start beat, end beat, beat count, and document pointer |

This confirms Autoloop playback is beatgrid/beat-window/index based and uses
the same playback/cache path that later feeds static overlay and blackout logic.
It does **not** prove the bridge-facing T7d phase contract: ticks-per-beat,
integer quantizer, origin, reset/continue/snap/correction behavior,
master-switch behavior, drop-hold behavior, BPM/pitch drift behavior, or
identity/holdout coverage. Those remain passive-runtime questions.

## Static Looks

Relevant symbols and arm64 entry points, confirmed in the 2026-06-29 GhidraMCP
pass unless otherwise stated:

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

The arm64 binary evidence confirms the physical `.ssfile`, Static Look, learned
MIDI map, override precedence, blackout, current-profile intensity questions,
and Autoloop beat-window/index machinery needed to bound the exporter/player
research. It also rejects addressed-footer/prefix/shared-table cue remapping in
the inspected reader/cache path. It does not prove Native Autoloop DMX phase
behavior or the exact DD42028C U0 mechanism. Remaining limits are x86_64
decompile parity for this expansion, future version/profile compatibility, the
wire-backed-but-not-reader/writer-binary-located runtime `raw-1` rule outside
the DD42028C exception, the RW-7/T7d passive phase corpus, and hardware
validation.
