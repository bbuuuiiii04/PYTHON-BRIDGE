---
doc_status: research-current
truth_level: byte-capture-and-binary-grounded
last_verified_commit: 74febec
last_verified_date: 2026-06-29
validation_scope: SoundSwitch 2.10.3 current-project bytes, controlled diffs, static binary analysis, and passive software-visible Art-Net; hardware-unvalidated
---

# SoundSwitch 2.10.3 project format research

## Authority and scope

This is the physical format authority for the bounded SoundSwitch-to-bridge
product. The readiness verdict and active inventory are in
`soundswitch_re_closure_report.md`. Research helpers are strict readers; they do
not write into `~/Music/SoundSwitch` and are not bridge runtime modules.

Accepted status remains **SOFTWARE/WIRE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.

Supported source boundary:

- SoundSwitch 2.10.3 project/container version 3;
- primary Venue `RAVE`, GUID
  `b8ad2201b9e4c94696c898a7e8f6a5a9`;
- current 19-channel laser profile on Universe 0 CH1-CH19;
- current Autoloop and scripted layout families;
- primary-Venue Static Looks, Attribute Cues, catalogs, TrackMap, and learned
  MIDI mappings.

## Common CAF encoding

- Integers are little-endian unless stated otherwise.
- CAF strings use `u32 encoding=1`, `u32 UTF-16 code-unit count including the
  terminal NUL`, followed by UTF-16LE bytes.
- `sys::ClassId`/GUID fields are 16 physical bytes. Reports use the physical
  byte hex unless they explicitly label a display-form UUID.
- Counts are full-width physical integers. They must not be inferred from the
  first byte.

## `.ssfile` physical document layout

The outer document is version 3 and the inner `SoundSwitchDocData` is version
12. Exact prefix content differs across supported families, so parsers locate
the binary-proven cue-map/timeline grammar and require one unique, bounded
candidate.

### Attribute Cue map

```text
u32le version == 1
u32le cue_count
repeat cue_count:
    guid[16]
    u32le stored_key
```

The old research parser treated the count as big-endian and shifted the records
by three bytes. That model is obsolete. `stored_key` is a lookup key; GUID is
the durable cue identity.

### Timeline entry

```text
u32le version == 1
u32le constant == 1
i32le elapsed_or_tick
u32le raw_reference
```

Each entry is 16 bytes. Signed negative values are real Autoloop pre-roll state.
They are sorted before nonnegative events and are not a `-1` sentinel.

### Document trailer

```text
u32le field_0
u8    bool_0
u32le field_1
u8    bool_1
```

The physical trailer is 10 bytes. The former 13-byte report included three
bytes from the shifted timeline view.

### Runtime reference resolution

For version-locked SoundSwitch 2.10.3 emitted runtime behavior:

```text
raw_reference == 0: clear/control event
raw_reference > 0:  stored_key = raw_reference - 1
```

Evidence:

- legacy A5 scripted wire: 14/14 positive events one-based, 0/14 direct;
- legacy Autoloop probe: discriminating one-based frames match, direct does not;
- cold-open newly authored track: raw 21/22/26 emitted stored-key 20/21/25,
  3/3 one-based and 0/3 direct.

Binary boundary:

- current GhidraMCP inspection of the arm64 reader/writer confirms the physical
  fields above, but does not prove the runtime `raw-1` renderer rule;
- `AttributesCueMap::AttributesCueMap(AttributesCueLibrary&)` assigns cue-map
  keys from zero, and `AttributeCueTrackEntry::ReadEntry` / `WriteEntry` use the
  stored map key directly;
- therefore the `raw-1` rule is passive-wire/runtime evidence for SoundSwitch
  2.10.3 current content, not a `.ssfile` reader/writer storage rule.

The editor selected RED/BLUE/GREEN for that cold track but runtime emitted
PURPLE/RED/TURQOISE. The exporter reproduces runtime output from saved bytes; it
does not substitute editor intent. Generic research CLIs still default to
`ambiguous` to prevent this version-specific rule from leaking into other
versions.

### Count-257 regression

`SSAutoLoop13.ssfile` has one physical timeline count of 257, 257 ordinary
16-byte records, and the normal 10-byte trailer. It has no sentinel record and
no 256-record continuation. This file locks the corrected parser.

## Supported Autoloop layouts

All 42 current Autoloops parse. The common current-profile structure is:

1. document/version header;
2. fixture/profile and `MainTrack` framing;
3. zero or more 17-byte type-1 `AttrChangeEntry` records;
4. optional shared 441-byte link/source/ref-track framing;
5. Attribute Cue map;
6. timeline count and 16-byte timeline records;
7. 10-byte trailer.

The 441-byte anchor has SHA-256
`ef84f0902fac69c8836cab500cee88b61b71ce13f3bf544d8c3f9ecfb6e73fd1`
across its 42 identical copies. It is preserved and validated but is not an
independent CH1-CH19 effect layer.

### Type-1 17-byte entries

Binary `AttrChangeEntry::Read/Write` identifies:

```text
u32le version == 2
i32le start_tick
i32le end_tick
u32le AttributeValue
u8    bool
```

These are intensity `AttributeTrack` nodes. Files 48 and 50 contain nonzero
values. The current fixture profile has no intensity channel, and
`Channel::SetIntensity` writes nothing when that flag is absent. Preserve these
records; they do not alter current CH1-CH19 output.

### Raw-zero and pre-roll

- raw zero clears the main cue layer;
- file 3 uses raw-zero records as the current momentary blackout Autoloop;
- negative records establish cycle-start state;
- a newly authored scripted placement before the first beat is stored at
  elapsed zero because that editor exposes no earlier beat; Autoloop pre-roll
  can be negative because loop origin differs.

## Supported scripted layouts

The corpus contains 45 scripted artifacts:

| Layout | Count | Status |
| --- | ---: | --- |
| shared 441-byte framing + cue map + timeline | 36 | parsed |
| cue map/timeline + 10-byte trailer + addressed footer | 7 | parsed; footer retained/bounded |
| cue map/timeline without shared anchor | 1 | parsed |
| In-App Demo v3 | 1 | unsupported and inactive |

`{AE9E3C61-AF40-4392-80B4-380D39C631B9}.ssfile` has one physical timeline
count of 367 and no continuation. Header offsets in addressed-footer files
bound their retained footer. `analyze_scripted_layouts.py` emits exact offsets
for every file.

Thirty-two scripted files have TrackMap paths that currently exist. All 32 use
supported layouts and reference no missing cue GUID. Wire capture is independent
validation coverage, not a per-file export requirement.

## Attribute Cue rendering

`SoundSwitchVenues.bin` contains 232 parsed Attribute Cues. Each cue has a GUID,
profile reference, and sparse `SSAttrValueMap` entries:

```text
u32le present == 1
u32le fixture_group_key
u32le channel_id
u8[4] repeated AttributeValue byte
```

For the current generic profile, channel IDs map to CH1-CH19 and the repeated
byte is the emitted DMX byte. Cue application is sparse and persistent:

- initial state is zero;
- encoded channels overwrite their prior value;
- omitted channels retain their value;
- Venue-disabled entries do not apply;
- raw-zero clears the main layer under the source-specific control rules.

The active Autoloop/script union references 166 cue GUIDs; all are present.
Deleting a global cue may leave stale saved references. The exporter must name
every missing source file/raw reference/GUID and refuse pack publication until
the placement is removed or replaced and SoundSwitch is saved again.

## Primary fixture profile

The embedded current profile exposes:

1. On/Off
2. Auto Mode
3. Static Pattern
4. Static Pattern Selection
5. Pattern Size
6. Horizontal Adjustment
7. Vertical Adjustment
8. Color
9. Color Speed
10. Pattern Line
11. Strobe
12. Rotation Z
13. Rotation X
14. Rotation Y
15. Horizontal Movement
16. Vertical Movement
17. Zoom
18. Gradient
19. X/Y Wave

Passive captures prove the software-visible surface is Universe 0 CH1-CH19;
Universe 1 is zero and no byte beyond CH19 is nonzero. Physical fixture hardware
and address validation remain separate. A changed Venue/profile/routing
fingerprint is an export error until separately supported.

## Static Looks

### Manager and collection grammar

Binary `StaticLooksManager::Read/Write` and current bytes agree:

```text
u32le manager_version == 1
u32le venue_collection_count
repeat venue_collection_count:
    venue_guid[16]
    u32le static_looks_version == 1
    u32le slot_count == 32
    repeat 32: StaticLook v5
```

The current Venue binary contains historical collections for other Venue GUIDs.
The exporter selects only the unique collection whose GUID equals the primary
Venue GUID. It does not use scan order.

### `StaticLook` version 5

```text
u32le version == 5
CAF string name
map<u32 fixture_instance_id, f64 intensity_fraction>
map<u32 fixture_instance_id, f64 strobe_fraction>
map<u32 fixture_instance_id, ColourValue[8]>
map<u32 fixture_instance_id, position_guid[16]>
SSAttrValueMap sparse generic attributes
```

All five maps are parsed and retained. In the current laser profile, the sparse
generic attribute map supplies the exact CH1-CH19 frame. Intensity has no target
channel, strobe fractions are zero in the four learned DDJ slots, and the
profile has no pan/tilt path for the stored position GUIDs.

Controlled diffs prove create and edit in a stable zero-based slot.
`StaticLooksManager::SetStaticLook` writes the slot, while
`RebuildStaticLookCache` converts intensity, strobe, colour, position, and
generic attributes into the runtime cache.

### Runtime selection

`EnableStaticLookOverride(index, pressed)` stores `index` on press and resets to
`-1` only when the matching slot is released. `RefreshCache` chooses override
before normal static selection and base playback. `SetChannelAttributes`
applies matching cached generic attributes after base state. Release rerenders
base; no prior-frame snapshot is restored.

Current learned DDJ-800 mappings resolve direct, zero-based slots 8, 16, 17,
and 24. The complete crosswalk and frames are in the closure report.

## Learned MIDI mappings

One of four `recordable/*.dat` files is the version-1
`NamedControlMapCollections` registry. Its physical grammar is:

```text
u32le 0xDEADBEEF
u16le version == 1
u8 status
TypeSignature map (0x01380308), u64 device_count
repeat devices:
    typed NUL string device_name (0x01380305)
    typed vector (0x01380306), u64 collection_count
    repeat collections:
        u32le collection_id
        typed vector, u64 binding_count
        repeat bindings:
            shared_ptr signature 0x01380307
            u8 message_type       # 0 note, 1 CC, 2 pitch bend
            u8 data_byte
            u8 zero_based_channel
            typed NUL string control_path
            u8 enabled
    typed vector, u64 feedback_byte_count, feedback bytes
u32le 0xDEADBEEF
```

### Static Override button interaction mode

A separate version-1 `recordable/*.dat` control-label state map stores the
saved `PushButton` colour and interaction state:

```text
u32le 0xDEADBEEF
u16le version == 1
TypeSignature map (0x01380308), u64 control_count
repeat controls:
    typed NUL string control_path (0x01380305)
    u32le label_rgba
    u8 interaction_flag        # 0 press, 1 toggle
u32le 0xDEADBEEF
```

SoundSwitch 2.10.3 binary evidence ties this final byte to Press/Toggle mode.
`MIDIDialog::eventFilter` changes `PushButton+0xc1`: choosing `Toggle Mode`
calls `QAbstractButton::setCheckable(true)` and stores `1`; choosing
`Press Mode` calls `setCheckable(false)` and stores `0`.
`ControlManagerPrivate::saveControlLabelColour` writes the same byte after
the label RGBA value, and `ControlManagerPrivate::reloadData` reads it back,
calls `QAbstractButton::setCheckable(flag)`, then stores it back at
`PushButton+0xc1`.

Current local saved project bytes include both values. In
`recordable/f87a4dfc2a52298e7e4f71fa8a89395a.dat`,
`StaticOverride8`, `16`, `17`, and `24` decode as `press`, while
`StaticOverride9`, `10`, and others decode as `toggle`. An older checked copy
under `vln_ss_analysis/copies/ssproj` differs only for `StaticOverride9`
from `press` to `toggle`, with target path identity unchanged. Confidence is
binary-and-saved-byte confirmed for SoundSwitch 2.10.3; physical controller
behavior remains hardware-unvalidated until an operator-approved live check.

The current file has 24 bindings across DDJ-800, IAC Driver Bus 1, and KOMPLETE
KONTROL A49; 19 IAC Autoloop bindings and four DDJ Static Overrides are
render-affecting for the product.

Binary `ControlMapDetail` read/write operators match every decoded field.
`newControlMapping` inserts a detail and its completion lambda calls `saveData`.
Unmap, clear-all, and both device-map removal paths also call `saveData`.
`saveData` rewrites the complete map; `loadData` reads the same structure and
handles corruption. Therefore add/edit/delete is detected by a full file rescan.

If one enabled device/message/channel/data-byte event resolves to multiple
render-affecting control paths, the exporter reports the paths and fails unless
their exact composition is supported. The current registry has zero collisions.

## Autoloop catalogs

Both current catalogs parse exactly to EOF:

| File | Entries | Index/file range | Identity |
| --- | ---: | --- | --- |
| `SoundSwitchAutoLoops.bin` | 18 | AppLog 0..17 / files 1..18 | base categories |
| `SoundSwitchAutoLoopsEx.bin` | 24 | AppLog 32..55 / files 33..56 | extended categories |

Each entry contains AppLog index, file number, enabled flag, display name,
category, and authored ordering. Final per-category order tables map control
slot banks to AppLog identities. Learned `AutoLoopsPlayAutoloopN` therefore
resolves by `divmod(N, 32)` into the saved category table—not by filename order
or display name.

Duplicate names are valid. Index/file number is stable identity. Controlled
create/rename/timeline-edit/delete experiments prove catalog and file mutation.

## TrackMap

The strict repeated-subrecord scanner finds 95 mappings, 71 unique normalized
SSIDs, 78 unique filepaths, and 11 duplicated SSIDs. Existing and stale paths
for the same SSID prove filepath is a locator, not identity.

Each repeated record contains a Qt UUID plus title, artist, and filepath. Stable
script identity is normalized SSID, cross-validated among TrackMap UUID,
`{SSID}.ssfile` filename, and audio `SOUNDSWITCH_ID` tag when available. A
conflict fails closed; the exporter never fuzzy-searches the filesystem.

The top-level object graph outside these records remains unnamed, but every
current render-affecting identity/locator field is parsed. Six alternate-profile
scripts have no TrackMap mapping and are inactive inventory rows.

## Authoring and complete-rescan behavior

The controlled fixture-bearing scratch corpus proves:

- Autoloop create, rename, cue add, move/reorder, pre-roll, post-roll,
  placement delete, and object delete;
- scripted create, edit, clear, and edit of legacy content;
- Attribute Cue create, rename, edit, placement, undo, and delete;
- Static Look create and edit;
- saved learned MIDI-map add/remove semantics from the binary writer paths.

Every Export performs a stable complete rescan. It must retain and compare:

- all paths and hashes, including additions/removals;
- project/version and primary Venue/profile fingerprint;
- catalogs/category order;
- all `.ssfile` dictionaries/timelines;
- TrackMap identities/locators;
- all Attribute Cues and 32 Static Looks;
- learned MIDI maps;
- opaque sidecars as reported, non-render inputs.

The scanner rechecks source metadata after reading and refuses concurrent
mutation. It publishes a pack atomically only after all cross-references pass.

## Non-render inputs and bounded unknowns

| Artifact | Current treatment |
| --- | --- |
| `.ssproj` | read project UUID/version; hash |
| `.ssa` | opaque sidecar; hash/report; no current playback call-chain consumer |
| `.sspreset` | opaque automation preset; hash/report; fail if future active use is detected |
| other recordables | hash/report; no current supported render consumer |
| `In App Demo.mp4` | media only; ignore for lighting |
| `SoundSwitchVenues.bin.backup` | report only; never substitute for current Venue |

These opaque semantics do not block the bounded current product because static
binary analysis shows they are not consumed by its active `.ssfile`/Static Look
playback path. A future active dependency or format/profile/version change must
fail closed and reopen RE; it must not be guessed.
