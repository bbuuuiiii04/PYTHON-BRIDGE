---
doc_status: research-complete-bounded-scope
truth_level: code-byte-binary-and-wire-verified
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: SoundSwitch 2.10.3, current project/container v3, current RAVE Venue and 19-channel laser profile, passive Art-Net and static binary analysis; hardware-unvalidated
---

# SoundSwitch reverse-engineering closure report

## Final verdict

**RE COMPLETE: READY FOR PERFECT EXPORTER SPEC**

This verdict is bounded to Brandon's actual workflow:

- SoundSwitch 2.10.3;
- the current v3 project/container family;
- primary Venue `RAVE`, GUID
  `b8ad2201b9e4c94696c898a7e8f6a5a9`;
- Universe 0, laser CH1-CH19;
- complete rescans after Autoloop, Static Look, Attribute Cue, scripted-track,
  and learned MIDI-map edits;
- bridge-authoritative single active deck, transport, scene policy, and safety.

The exporter can derive SoundSwitch's emitted behavior from the saved project
without guessing. It must fail before publishing if an input changes during the
read, a referenced cue is missing, a learned event is ambiguous, the primary
Venue/profile changes, or a new container/version is unsupported. Those are
deterministic safety checks, not unresolved active content.

Exporter, importer, player, bridge integration, and physical output are not
implemented by this research change. Status remains
**SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## Active-content inventory

### Current reachability summary

| Object class | Active/current count | Export status | Authority |
| --- | ---: | --- | --- |
| IAC learned Autoloop controls | 19 | all resolved to parsed files | recordable map + catalog category order |
| Automatically selected bridge Autoloops | 18 | all clean-byte exportable | live config crosswalk + parsed files |
| Current manual blackout target | 1 | file 3, all-zero hold target | live config + recordable map + log/wire evidence |
| Existing-path scripted tracks | 32 | all clean-byte exportable | TrackMap + physical `.ssfile` parser |
| Primary-Venue Static Look slots | 32 | all parsed | Venue GUID-keyed `StaticLooks` collection |
| DDJ-800 learned Static Look overrides | 4 | all resolved to exact slots/frames | recordable map + Static Look parser + binary |
| Venue Attribute Cues | 232 | all parsed | Venue parser |
| Cues referenced by active Autoloops/scripts | 166 | all present; none missing | GUID union across active files |

The sorted 166-GUID active cue union has SHA-256
`88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`
when encoded as lowercase GUID hex, one per line. `build_coverage_reports.py`
and `parse_venue_cues.py` emit every source reference, GUID, name, and sparse
CH1-CH19 patch; the hash prevents a summarized count from hiding drift.

### Learned IAC Autoloop targets

Identity is the catalog AppLog index and file number, never the display name.
Every row is structurally parsed and has no missing referenced cue.

| MIDI note | Control slot | AppLog index | File | Current catalog name | Special records |
| ---: | ---: | ---: | --- | --- | --- |
| 0 | 0 | 2 | `SSAutoLoop3.ssfile` | BLACKOUT | two raw-zero records; all-zero hold target |
| 32 | 32 | 4 | `SSAutoLoop5.ssfile` | BLACKOUT | one raw-zero record |
| 64 | 64 | 17 | `SSAutoLoop18.ssfile` | BLACKOUT | one raw-zero record |
| 96 | 96 | 3 | `SSAutoLoop4.ssfile` | LAGGY 1/4 W | 131 timeline records |
| 97 | 97 | 12 | `SSAutoLoop13.ssfile` | LAGGY 1/8 W | 257 physical records; one negative-time record |
| 98 | 98 | 5 | `SSAutoLoop6.ssfile` | stack out in | one negative-time record |
| 99 | 99 | 14 | `SSAutoLoop15.ssfile` | curve out in | two negative-time records |
| 100 | 100 | 13 | `SSAutoLoop14.ssfile` | ruby | one negative and one raw-zero record |
| 101 | 101 | 15 | `SSAutoLoop16.ssfile` | pulsating | one negative and one raw-zero record |
| 102 | 102 | 16 | `SSAutoLoop17.ssfile` | sperm race | one negative and two raw-zero records |
| 103 | 103 | 7 | `SSAutoLoop8.ssfile` | seizure | one negative-time record |
| 104 | 104 | 45 | `SSAutoLoop46.ssfile` | New Autoloop | one negative-time record |
| 105 | 105 | 46 | `SSAutoLoop47.ssfile` | MEGA DROP | normal |
| 106 | 106 | 47 | `SSAutoLoop48.ssfile` | New Autoloop | nonzero intensity metadata; no current-profile output effect |
| 107 | 107 | 49 | `SSAutoLoop50.ssfile` | New Autoloop | five raw-zero records; nonzero intensity metadata has no current-profile effect |
| 108 | 108 | 51 | `SSAutoLoop52.ssfile` | New Autoloop | one negative and two raw-zero records |
| 109 | 109 | 52 | `SSAutoLoop53.ssfile` | New Autoloop | one negative-time record |
| 110 | 110 | 53 | `SSAutoLoop54.ssfile` | New Autoloop | one negative and two raw-zero records |
| 111 | 111 | 54 | `SSAutoLoop55.ssfile` | New Autoloop | one negative and one raw-zero record |

Negative-time records are normal pre-roll state. The nonzero type-1 values in
files 48 and 50 are intensity `AttributeTrack` nodes; the current profile has no
intensity channel, so the binary setter performs no CH1-CH19 write.

The live bridge reaches groove note 32, buildup note 64, and drop notes 96-111.
Breakdown note 1 is intentionally unlearned and is sent while the separately
learned note-0 blackout mask is held. It is therefore a no-op, not a missing
Autoloop target. Note 41 is unlearned and its current post-drop bank is empty.

### Intentionally unmapped bridge controls

| Bridge control | Current MIDI | SoundSwitch project status | Product behavior |
| --- | --- | --- | --- |
| safe/static | CH2 note 0 | intentionally not learned | bridge-owned safety state; do not invent a SoundSwitch target |
| transition | CH2 note 1 | intentionally not learned | bridge-owned transition state; do not invent a target |
| emergency | CH2 note 2 | intentionally not learned | bridge-owned direct zero/emergency policy |
| breakdown scene | CH1 note 1 | intentionally not learned | no-op underneath held CH1 note-0 blackout |
| post-drop scene | CH1 note 41 | not learned; inactive bank | inactive, report only |

An absent mapping is not an export error unless the saved bridge policy marks
that event as requiring a SoundSwitch-authored target. If Brandon later learns
one of these notes, the next full rescan discovers it through the same generic
recordable parser.

### DDJ-800 Static Look overrides

`recordable/7ce5eb8b689a957b8032d703a1ace534.dat` has SHA-256
`bb312e6603ce67dded5335980beebabe7583250d842d0c6c82826c9444a9eac3`.
It contains 24 bindings across three devices, including these four enabled
DDJ-800 notes:

| DDJ MIDI | Control path | Slot | Static Look | Exact primary laser CH1-CH19 hex |
| --- | --- | ---: | --- | --- |
| CH7 note 106 | `StaticOverride16` | 16 | OFF | `00000000000000000000000000000000000000` |
| CH10 note 122 | `StaticOverride24` | 24 | STROBE BUILDUP #1 | `010015ff00288a00ff00ff00ff005d000000ff` |
| CH10 note 123 | `StaticOverride8` | 8 | STROBE EFFECT | `1800260000797c0000d6ff000000000000006e` |
| CH10 note 127 | `StaticOverride17` | 17 | RAINBOW STROBE | `26001d00006483ffffff00000000000000004f` |

The exporter must include these learned inputs and all 32 primary-Venue slots,
not only bridge-output IAC mappings. `StaticOverrideN` selects zero-based slot
`N`. Note-on holds the override; matching note-off clears that slot only and
rerenders the current underlying playback.

Binary `StaticLooksManager::Read/Write` proves the GUID-keyed collection, fixed
32 slots, and version-5 record writers. `EnableStaticLookOverride(int,bool)`
stores the direct slot index or `-1`; `RefreshCache` chooses the override slot
before the normal static slot and passes its cache into `SetChannelAttributes`.
The cache overrides matching generic attributes after base playback state. The
controlled `STATIC-CREATE` and `STATIC-EDIT-BLUE` diffs prove create/edit slot
mutation. No hidden saved-frame stack exists.

### Active scripted tracks

All 32 current TrackMap entries whose audio paths exist are clean-byte
exportable. Per-file wire capture is validation coverage, not an export rule.

| SoundSwitch ID | Track title | Layout |
| --- | --- | --- |
| `025C1DDF-2CDC-4E54-BD8C-156B90DD8247` | Isoxo - how2fly vs Rihanna - We Found Love (2HEARTs Mashup).wav | shared 441 |
| `02E3AA51-6983-42C4-BDBD-19CEB4140C2F` | M.A.A.D. CITY (EYEWITNESS & NJOY ).wav | shared 441 |
| `16F51143-D1ED-46D5-A786-8BE50AAD33AE` | I Wanna Go (John Summit Extended Remix) | shared 441 |
| `1A62CF25-0346-4EE5-BBAF-2553293FD5E9` | Booyah Bounce - Cheyenne Giles & Knock2 (Festival Flip).mp3 | no-anchor dictionary/timeline |
| `1FD042ED-A260-47E5-AB93-EBEA7CB61F1F` | BLACKPINK - JUMP (JAY ESKAR EXTENDED REMIX).mp3 | shared 441 |
| `32D96480-AAB5-4BAB-A212-8F779F1CCDB6` | Slut Me Out 2 (RAW Remix) Final Seriously v3.wav | shared 441 |
| `4883E811-4C69-45E7-BD72-549B17AC7241` | Knock2 x Nelly - Gettin' Hot in Here (Auxshan's Edit).mp3 | shared 441 |
| `494785CC-8B9F-4C5F-BB67-7FA36BCBC4C1` | Dracula (OMNOM Remix) (Extended Mix) | shared 441 |
| `528E8B22-BD17-41B9-A111-275D3E8B3031` | Where Have You Been (Hardwell Club Mix) | shared 441 |
| `5996871E-5D88-4197-98B4-6F67A4638013` | Party Rock Anthem (REXY=DEXY REMIX).wav | shared 441 |
| `651A3059-C891-4F7B-BA08-128508C6C4BA` | Billie Eilish - LUNCH (Phrva Flip).wav | shared 441 |
| `69F8532E-9D47-440F-8787-0B6609E8B02D` | Twin Diplomacy, Jack August - Better Place (Original Mix) MT V3.wav | shared 441 |
| `74044FA4-45A5-4FE6-85ED-F8D8698A346A` | Opalite (Chris Lake Remix) | shared 441 |
| `772519EB-C8B6-443E-98C0-2CAC98E077CB` | Turn My Swag On (NETGATE x Danny Diggz VIP Edit) | shared 441 |
| `8C6BFF4A-18D6-4D97-9865-349876258326` | YOU KNOW YOU LIKE IT (CG REMIX v.1) | shared 441 |
| `9947C65E-CFD1-476E-AA90-4AED65AE5F11` | Niggas In Paris x Core x OK!OK!OK! (AWON Edit).wav | shared 441 |
| `A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF` | SANFRANDISCO (KING KOZZ FLIP) | shared 441 |
| `AD786435-85BB-401F-93DF-B5D4EA59ADC0` | PICTURE IN MY MIND W IN K NIKKO REMIX FINAL.wav | shared 441 |
| `AE9E3C61-AF40-4392-80B4-380D39C631B9` | New Sky (Odd Mob Remix).wav | shared 441; 367 physical records |
| `B335B3AF-12A0-4149-89F0-638D33D0DCB8` | Rude Boy (Klean Remix) | shared 441 |
| `BFF9DFCD-622D-42F9-934D-55CDAEBF13F5` | Mean Girls RMX - Final V4 | shared 441 |
| `C3A1B60D-D2D7-4E19-9C6C-84B76F29463D` | Trademark USA (DEFOND remix) | shared 441 |
| `D44722CA-693B-4D2B-BBF1-7EAAA69300B4` | Britney Spears - ...Baby One More Time (Never Sleep Remix) | shared 441 |
| `DD42028C-0823-4A8D-AD7E-B26E24180272` | John Summit & Hayla - Where You Are (Crankdat Remix).wav | addressed footer |
| `E36664D0-246B-46A6-92AF-5267AE372008` | Scilo - Lowkey (Original Mix).wav | shared 441 |
| `ED463C27-B1A5-420D-A062-B831C0F13AB6` | No Hands (SWEETLK Tremor Edit).wav | shared 441 |
| `ED66BABB-3514-471C-A2EA-593934016BC2` | MANEATER (DRYDEN EDIT) extended.wav | shared 441 |
| `F0947ED0-530C-4E6F-915B-ABD053162065` | TYNAN - His Name Is (KAYA! x Luciden remix) | shared 441 |
| `F1E0AB45-E1A1-445F-9992-1E8214ACEDDD` | Kesha - Blow (CHALANT & Donny Graves Remix).wav | shared 441 |
| `F358F6B0-65F2-4CEB-8D54-2F4DA22A0A23` | Demi Lovato - Cool For The Summer (Daevo Remix).wav | shared 441 |
| `FB4EF1CA-E91C-4951-829F-DFF7D6FF0792` | Break Free (Juelz Remix) | shared 441 |
| `FC10FC02-93C2-418F-8815-16088884DA42` | TITANIUM (TWINSICK REMIX).wav | shared 441 |

The inactive In-App Demo v3 layout remains visible and unsupported. It has no
existing-path active TrackMap entry and therefore does not block the current
product.

## Scripted-track conclusion

Future newly saved scripted tracks export directly after clicking Export when
their container/profile matches the supported set. The exporter reads their
GUID dictionary and physical timeline and applies the version-locked runtime
rule below. It does not require a capture or an oracle per track.

If a future file uses a new layout, changes while being read, or references a
deleted Attribute Cue, export fails before pack publication and names the exact
file/GUID. The operator action is to save/close the SoundSwitch edit, remove or
replace the stale placement in SoundSwitch, save again, and re-export. Capture
is required only to extend support to a genuinely new SoundSwitch version or
rendering feature, not to canonicalize ordinary new tracks.

## Autoloop conclusion

All 42 current Autoloop files parse. The 19 learned IAC targets above are
export-safe; 18 are used by normal bridge selection and file 3 is the manual
blackout target. Missing per-file wire captures do not make the other clean
files ambiguous. Negative pre-roll, raw-zero control records, counts over 255,
and nonzero intensity metadata are decoded.

The controlled mutation corpus proves:

- create adds catalog identity 18 and `SSAutoLoop19.ssfile`;
- rename changes display metadata without changing identity;
- cue add, move, pre-roll, post-roll, and placement delete change only the
  identified file/timeline semantics;
- Autoloop delete removes both catalog identity and file;
- duplicate names are harmless because identity is index/file number;
- category reorder is resolved from the saved category-order table, not from
  names or directory order.

Newly created Autoloops and newly learned IAC mappings are therefore discovered
on the next complete rescan. No operator capture is required.

## Go-forward `.ssfile` serialization rule

For SoundSwitch 2.10.3 emitted runtime behavior:

```text
raw_reference == 0  -> clear/control event
raw_reference > 0   -> dictionary stored_key = raw_reference - 1
```

This is wire-proven for legacy A5, legacy Autoloops, and a cold-open newly
authored three-cue track. The cold track stored raw 21/22/26 after the operator
selected RED/BLUE/GREEN, but runtime emitted stored keys 20/21/25
(PURPLE/RED/TURQOISE): 3/3 one-based, 0/3 direct. That editor/runtime mismatch
is a SoundSwitch 2.10.3 behavior the product must reproduce; it is not an
exporter ambiguity.

Create, add, delete, move/reorder, duplicate, and resave operations do not need
a provenance heuristic. The loader always consumes the saved positive integer
through the same effective `raw-1` behavior. The writer preserves the integer
present in each record. The exporter reads current bytes after save and renders
exactly what current SoundSwitch would emit, even if the editor's visual cue
selection appears off by one.

Generic research parsers continue to default to `ambiguous` so they are not
silently applied to other SoundSwitch versions. The version-locked exporter
must pass `one_based` explicitly and record source version/hash evidence.

## Learned MIDI-map serialization conclusion

The version-1 `NamedControlMapCollections` recordable is fully decoded for the
supported controls:

```text
DEADBEEF, u16 version, u8 status
map<string device, DeviceControlMapCollection>
  vector<collection_id, vector<shared ControlMapDetail>>
    u8 message_type, u8 data_byte, u8 zero_based_channel
    string control_path, u8 enabled
  vector<u8> feedback
DEADBEEF
```

Binary `newControlMapping` constructs exactly these fields; its completion
lambda calls `saveData`. Unmap, remove-device-map, and clear-all also call
`saveData`, which rewrites the complete registry. `loadData` reads the same map
and rejects/corrects corrupt data. The exporter rescans the whole registry,
includes every enabled binding, and fails loud if one enabled device/event maps
to multiple render-affecting control paths whose composition is unsupported.
The current registry has zero such collisions.

## Runtime behavior required by the player

### Sparse cues and timing

- Cue identity is GUID/ClassId based; names and numeric indices are metadata.
- Cue patches are sparse, Venue-enabled persistent updates into an initial zero
  state. Omitted channels persist.
- Attribute value maps produce the current profile's DMX bytes directly.
- Negative events establish pre-roll state before nonnegative events.
- Seek, pause/resume, loop, refire, stop, and unload are history-independent:
  rerender the current source at the authoritative position; stopped/unloaded
  is zero.

### Blackout and restore

The current bridge's CH1 note-0 blackout is a learned momentary Autoloop control
to file 3, whose two raw-zero records produce zero. Bridge logs show note-on at
pre-drop/breakdown entry, note-off at restore/drop, and immediate selection of
the current target. Release does not restore a captured frame; it rerenders the
current underlying source.

SoundSwitch's separate `SetBlackoutOverrideState(bool)` has the same stateless
final-mask property. Emergency remains bridge-owned direct zero because CH2
note 2 is intentionally unlearned.

### Static override precedence

An active Static Override takes precedence over the normal Static Look/base
playback for every matching attribute. Note-off clears only the active matching
slot; current base playback is recomputed. The player's precedence is:

```text
bridge emergency/blackout safety mask
  > held DDJ StaticOverride slot
  > bridge-selected Autoloop or scripted source
  > zero when stopped/unloaded
```

### Deck ownership

SoundSwitch two-playback mode blends levels/crossfader; four-playback mode
chooses the highest upfader and retains the prior owner on ties. The current
bridge already has stricter single-active-deck authority. The player consumes
that authority and does not emulate inactive SoundSwitch multi-deck policy.

## Claim ledger

| Load-bearing claim | Current evidence | Status | Export/player impact |
| --- | --- | --- | --- |
| Cue identity is GUID-based | Venue/ClassId bytes, dictionary readers, controlled rename | confirmed | names never resolve identity |
| Numeric cue index is metadata | dictionary key and runtime reference traces | confirmed | never persist name/index as identity |
| Positive runtime reference is `raw-1` | A5, Autoloop wire, cold new-track wire | confirmed | version-locked one-based renderer |
| Storage provenance can look mixed/direct | controlled legacy edit and current writer | confirmed but not a runtime blocker | preserve bytes; reproduce emitted runtime |
| Raw zero is clear/control | parser, binary, A5 2/2, file-3 zero output | confirmed | explicit clear semantics |
| Cue application is sparse/persistent | controlled cues, renderer equality, cache binary | confirmed | omitted channels retain state |
| Attribute value maps are current DMX bytes | Venue diffs and wire equality | confirmed | no scaling for generic CH1-CH19 |
| Venue-enable gate applies | controlled Venue diffs and binary | confirmed | disabled patches do not render |
| Timeline is physical `<IIiI>` | reader/writer, count-257 regression | confirmed | no shifted count/continuation model |
| Negative records are pre-roll | bytes, ordering, renderer | confirmed | apply before time zero |
| Type-1 17-byte records are intensity | `AttrChangeEntry` reader/writer | confirmed | preserve; no current-profile channel write |
| All active Autoloops are clean-byte exportable | 19 bindings, 42/42 parser, no missing GUIDs | confirmed | captures are optional validation |
| All active scripted tracks are clean-byte exportable | 32 existing-path rows, supported layouts | confirmed | new matching tracks export directly |
| Static Looks are GUID-keyed 32-slot arrays | manager/slot reader-writer and controlled diffs | confirmed | export all slots and values |
| `StaticOverrideN` uses direct slot N | registry bytes + `EnableStaticLookOverride` | confirmed | DDJ note-on/off exact override |
| MIDI mappings are complete-rescan data | recordable operators and save/load callers | confirmed | add/edit/delete picked up next export |
| Current note-0 blackout is file 3 | registry, live config, AppLog/bridge/wire | confirmed | momentary zero then current-source rerender |
| Channel-2 utilities have SoundSwitch targets | decoded registry | contradicted/obsolete | treat as bridge-owned, never guess |
| Per-file oracle canonicalization is required | corrected physical grammar + runtime rule | obsolete for supported content | oracles remain independent verification only |
| Exact SoundSwitch multi-deck parity is required | bridge ownership contract | not a product requirement | consume bridge active deck |

## Remaining unknowns and unsupported boundaries

There are no remaining behavioral unknowns that block the bounded perfect
exporter/player specification.

The following are explicit compatibility or hardware boundaries:

- SoundSwitch versions other than 2.10.3;
- a changed primary Venue/profile, universe, or address layout until separately
  decoded and validated;
- the inactive In-App Demo layout;
- exact SoundSwitch multi-deck crossfade/four-deck parity;
- opaque `.ssa`, automation preset, and non-MIDI recordable payload semantics
  unless a future active source proves them render-affecting;
- physical laser/Enttec behavior, which remains hardware-unvalidated.

The exporter must fingerprint these boundaries and fail before publishing a
pack if they change. It must name the unsupported file/version/profile and the
smallest action: restore the validated profile/version or run a new RE/validation
extension. It must never silently fall back to names, old Venue backups, frozen
oracles, or guessed channel routing.

## Go/no-go

**GO** for a perfect exporter/importer/player implementation specification.

The specification must include complete atomic rescans, version/profile gates,
all active Autoloops and scripted tracks, the full primary-Venue Attribute Cue
bank, all 32 Static Looks, learned IAC and DDJ mappings, collision detection,
momentary Static Override and blackout behavior, deterministic current-position
rendering, a bridge-owned emergency mask, pack hashes, independent verification,
and rollback/default-off phases.

Runtime implementation, bridge restart/toggle, MIDI/Art-Net/Enttec output, and
physical hardware checks remain blocked pending their own reviewed phases and
explicit operator approval.
