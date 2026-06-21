---
doc_status: research-current
truth_level: byte-capture-and-binary-grounded
last_verified_commit: 2c71a2e
last_verified_date: 2026-06-20
validation_scope: passive software and wire capture only; hardware-unvalidated
---

# SoundSwitch v3 Project and `.ssfile` Format Research

## Status and boundary

This document records the current read-only reverse engineering of the maintainer's
SoundSwitch 2.10.3 project. It is not a production parser contract and does not
authorize exporter, importer, bridge-runtime, configuration, restart, MIDI, OS2L,
Art-Net, serial, Enttec, or physical-DMX work.

Accepted status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

The final readiness authority is
`soundswitch_re_closure_report.md`. In particular, the current binary's direct
loader/writer conflicts with the A5 one-based wire result, so this document's
legacy/new provenance observations must not be promoted to a general byte-only
export rule until the cold-load gate in that report is complete.

No agent command modified the authoritative files under
`~/Music/SoundSwitch/default.ssproj/`. Opening that project in SoundSwitch did,
however, rewrite `SoundSwitchVenues.bin.backup` to equal the current Venue.
This observed application side effect is retained as evidence and no restore or
substitution was performed. All claims below come from current file bytes,
frozen pre-open bytes, passive pcaps, copied SoundSwitch AppLogs, copied bridge
logs, and research helpers under `tools/ssfmt/re/`.

## Frozen evidence

| Artifact | Size | SHA-256 | Use |
| --- | ---: | --- | --- |
| `SoundSwitchVenues.bin` | 243,878 | `f34bfc796e9e589c7eb4707ee4f223c6ea6fd2f597d08622d30370f16a2a3398` | Current Venue and cue authority. |
| `{A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF}.ssfile` | 7,621 | `84f6bf7286d1bdb304318129b7c3b2acfb249d3f02057c4e4cf826e0f40d30e0` | Scripted A5 byte-exact oracle. |
| `scripted_sanfrandisco_a5_20260619.pcap` | 9,585,050 | `a2521081a215f30e8e24c6570caa594d0b3133ce3b29ab6bf77666f770136d47` | Passive A5 wire evidence. |
| `bridge_driven_autoloops_20260619.pcap` | 36,210,534 | `40156bda42d6618518402827bd8d6022d9ee597b176dbbc19b9a8ac2461c3564` | Passive combined autoloop evidence. |
| `artnet_lo.pcap` | 99,027,324 | `f4ea14d5cad9b0f1ff5064dad4d849ca50d5c5989a934c9228325c13d1aaab38` | Earlier passive Art-Net corpus. |
| `SoundSwitchTrackMap.bin` | 786,379 | `f17da436d791eaaa2fac0fc00ea48d0e4cd1e71c782c372d0cf13f5ab66c3deb` | Track identity subrecords. |

Capture validation proves bytes visible on the wire. It does not prove any
fixture, laser, LED/Govee device, Enttec interface, or physical DMX behavior.

The older `artnet_lo.pcap` is fully audited rather than silently discarded. Its
frozen hash manifest has 99 entries: 96 still match, including all 42 autoloop
files. Current Venue, the now-rewritten Venue backup, and A5 differ. The old
snapshot, frozen pre-open Venue/backup, and current Venue have identical cue
GUID sets and all 232 parsed cue semantics, so the Venue hash drift is outside
parsed cue patches. Its surviving derived library covers 41/42 AppLog indices
(missing 6), but stores only one sample state per index and no raw segment
timestamps; copied AppLogs are absent. It cannot be promoted to per-frame exact
validation without inventing boundaries.

## Common container encoding

Observed `.ssfile`, Venue, and catalog containers begin with:

| Offset | Size | Encoding | Meaning |
| ---: | ---: | --- | --- |
| 0 | 4 | bytes | `AA AA 09 55` magic. |
| 4 | 4 | little-endian `u32` | Version; all current corpus files are version 3. |

Observed Qt-style strings are `[u32 code-unit count][UTF-16LE data]`; the count
includes the trailing UTF-16 NUL. UUIDs are generally 16 raw bytes. A TrackMap
UUID uses Qt field endianness: its first `u32`, `u16`, and `u16` are little
endian, while the final eight bytes remain in display order.

## Current-profile autoloop structure

All 42 cataloged files (`SSAutoLoop1..18` and `SSAutoLoop33..56`) parse with the
same current fixture prefix and timeline grammar.

### Header and fixture prefix

| Offset | Size | Meaning |
| ---: | ---: | --- |
| 28 | 16 | Fixture-profile raw GUID `b8ad2201b9e4c94696c898a7e8f6a5a9`. |
| 48 | 4 | Group count 6. |
| 52 | 2,136 | Six 356-byte group records, ending at 2,188. |
| 2,255 | 4 | Little-endian count of 17-byte pre-table records. |

The group records have IDs `0x492..0x497`. Each record has 12 position
references beginning at record offset `+72`; each position reference is
`[16-byte raw UUID][u32 slot]`. The verified parent/owner field at `+40` forms:

| Group | Parent/owner field |
| --- | --- |
| `0x492` | `1` |
| `0x493` | `0x492` |
| `0x494` | `0x492` |
| `0x495` | `1` |
| `0x496` | `0x495` |
| `0x497` | `0x495` |

The 12 slots resolve to Venue position records:

| Slot | Venue position |
| ---: | --- |
| 0 | Disco Ball |
| 1 | Stage Left |
| 2 | Stage Right |
| 3 | Dance Floor Centre |
| 4 | DJ Booth |
| 5 | Crossed Over |
| 6 | Up |
| 7 | Down |
| 8 | Stage Center |
| 9 | Cake |
| 10 | New Position (`be160b...`) |
| 11 | New Position (`b34b58...`) |

The group block SHA-256 is
`9e7719238ea5cac705c23ddbe1d0a2ac4256b07c8b90301e448bcc7a5bb1f120`
in all 42 autoloops.

### Seventeen-byte records

Starting at byte 2,259, each record is:

```text
u32le type == 2
u32le tick_a
u32le tick_b == tick_a
u32le auxiliary
u8 trailer == 0
```

There are 72 nonzero auxiliary records across files 2, 7, 35, 48, and 50,
using 12 distinct values. Their semantics are unresolved and they are not safe
to ignore: files 48 and 50 have capture residuals, while files 2, 7, and 35 have
no clean captured segment.

### Shared block, cue dictionary, and timeline

The pre-table records are followed by a 441-byte shared block. All 42 copies are
identical with SHA-256
`ef84f0902fac69c8836cab500cee88b61b71ce13f3bf544d8c3f9ecfb6e73fd1`.
Its controller/effect semantics remain unnamed because the current corpus has no
variant for a controlled diff.

The cue dictionary begins immediately after the shared block. Headless analysis
of the actual loader establishes the physical CAF layout:

```text
u32le dictionary_version = 1
u32le cue_count
repeat cue_count:
    bytes[16] cue_guid
    u32le cue_index
```

`cue_index` is the dictionary key. It is not the entry's physical order in the
file. The keys are unique.

The timeline follows:

```text
u32le declared_timeline_count
repeat count:
    u32le entry_version = 1
    u32le constant = 1
    i32le elapsed_ms
    u32le raw_reference
```

The existing research parser's `[u32be count]`, `[3 zero][GUID][u8]`, and split
time/reference descriptions are a three-byte-shifted view of these same bytes;
they recover the same GUID, key, elapsed, and raw-reference values but are not
the physical serialization. Negative elapsed values are real and must be
preserved.

The key lookup is `{entry.cue_index: entry}`, not `cues[raw - 1]` — the
dictionary is GUID-sorted and physically permuted, so the stored `cue_index`
byte is the key, not the entry's position.

#### Reference resolution is PROVENANCE-DEPENDENT (corrected 2026-06-20)

There is **no currently validated single byte-only rule across the active
corpus**. Controlled current-version writes are direct, while the A5 wire
capture behaves one-based:

```text
legacy record (older SoundSwitch):   cue_index_byte = raw_reference - 1   (ONE-BASED)
new record   (current SoundSwitch):  cue_index_byte = raw_reference       (DIRECT)
raw_reference == 0:                  clear/control event (not cue_index 0)
```

- **A5 behaves ONE-BASED on wire** (SANFRANDISCO Art-Net
  capture, 14/14 byte-exact: raw 91 → cue_index_byte 90 = "RED BOX SWAY DROP";
  raw 22 → cue_index_byte 21 = "RED" = `a554afd8…`).
- **Newly created scripted records are DIRECT in bytes** (controlled scratch
  creation; new RED = raw 21 → key 21). Opalite is not creation-proven and its
  capture must not be used to label all new content.
- **Editing a legacy scripted file = MIXED.** Appending a cue leaves the old
  records ONE-BASED and writes the new record DIRECT, with no renormalization
  and no structural disambiguator (version 3, all `field_a=field_b=1`,
  elapsed-sorted). This storage result is controlled-diff confirmed on WHYB;
  the edited file itself was not wire-captured.
- **Autoloops contain legacy-looking one-based and new direct records.** New
  placements use direct (controlled authoring: RED 21, BLUE 22, GREEN 26). The
  earlier "autoloops are uniformly direct" claim was a self-consistency artifact
  and is withdrawn. The legacy=one-based result was confirmed by a dedicated
  operator-gated Art-Net capture (`autoloop_probe.pcap`, scratch project, fixtures
  confirmed safe): rendering each captured autoloop through the layered renderer,
  one-based-rendered cue states appear on the wire 17× vs direct 4×, and for every
  file with a color-discriminating record (SSAutoLoop50/52/53) one-based matches
  byte-exact while direct matches 0. Decisive example: SSAutoLoop52 raw 27 at tick
  2325 renders one-based → byte 26 GREEN
  `{1:41,3:48,4:14,6:117,7:145,8:21,11:214,15:159}` = the captured wire frame
  byte-exact; direct → byte 27 CYAN `{1:28,4:255,…,15:255}` never appears.
  (Context: all BYTE-ONLY tests are convention-insensitive — the RED scan is
  circular and the dictionary-coverage test passes under both because dictionaries
  now hold the full 233-cue bank — and the OLD autoloop pcap was also insensitive
  because its discriminating cues were animated; the new capture's per-record
  color match is what settled it.)

Static analysis now proves that both ARM64 and x86_64 2.10.3 loaders and writers
use the stored key directly with no subtract-one branch. That contradicts the A5
wire result and means the earlier claim of two numeric loader paths is withdrawn.

**Exporter/importer consequence:** tools must continue to preserve both
candidates. The final product cannot stop at fail-closed for active content; it
must close the binary/wire contradiction, re-author and cold-validate the file,
or use a complete wire-oracle pack as specified in the closure report.

Most timeline records use `(field_a, field_b) == (1, 1)`. One file-13 sentinel
record at byte 8,082 uses `(0x01000001, 1)`. The meaning of that high bit is
unresolved. `SSAutoLoop13.ssfile` has one declared timeline record plus 256
validated 16-byte continuation records before its 13-byte trailer.

### Missing and stale cue correction

No current autoloop timeline references a GUID missing from the current Venue.
Earlier claims that files 16 and 54 referenced removed GUID
`b0aca10df204a0418b09cdbdc5b0d437` were another off-by-one artifact. Their raw
reference 232 resolves `cue_index=231`, GUID
`4737582a51e1664980890a5f7f6be88a` (`WIDE SPREAD  copy copy`), which is present.

The removed `b0aca...` entry is unused in each dictionary where it occurs.
File 36 also contains two unused stale GUIDs:

- `7d75b0dadaee454b9950f23297de0360`
- `a2fde79e40a58743b21b08c412e64ddb`

Both the frozen pre-open and current non-authoritative Venue backups contain 232
parsed cues and none of these three stale GUIDs. They contain the current
`473758...` cue. There is therefore no deleted cue payload to recover from a
backup, and none is needed for files 16/54.

An exporter must still report unused stale entries, but must not fabricate or
substitute cue data.

## Scripted layouts

There are 45 `{UUID}.ssfile` files:

| Layout | Count | Structural status |
| --- | ---: | --- |
| Shared 441-byte table + dictionary + timeline | 36 | Parsed. |
| Dictionary/timeline + 13-byte trailer + header-addressed footer | 7 | Parsed structurally; no representative wire validation. |
| Dictionary/timeline without shared anchor | 1 | Parsed structurally; no representative wire validation. |
| In-App Demo v3 layout | 1 | Unsupported. |

Thus 44/45 are structurally classified, improving the earlier 36/45 result.
The only remaining structurally unsupported file is
`{4C5F1B0F-59AB-4715-BECC-9C498727C9DD}.ssfile` (10,663 bytes). Its header points
to a footer at 10,570, but no strict `(1,1)` timeline candidate ends at the
required boundary.

The seven addressed-footer files are six alternate-profile files with profile
GUID `b7527f4d5debc6499fb9cdb82b591239` and the large current-profile DD42 file.
Their header offsets at bytes 8 and 12 address the footer. A standard 13-byte
timeline trailer ends exactly at the first footer offset. The footer structure
is bounded but its semantics are not yet named.

| SSID prefix | Cue count byte/count | Timeline count byte/count | Timeline end / trailer | Footer byte/size |
| --- | --- | --- | --- | --- |
| 06F2C1C5 | 28,907 / 10 | 29,111 / 9 | 29,259 | 29,272 / 93 |
| 15D10A9C | 46,447 / 10 | 46,651 / 11 | 46,831 | 46,844 / 125 |
| 597E28D3 | 32,931 / 10 | 33,135 / 18 | 33,427 | 33,440 / 109 |
| 9383CF6E | 43,750 / 10 | 43,954 / 15 | 44,198 | 44,211 / 125 |
| D3E7322D | 36,377 / 10 | 36,581 / 16 | 36,841 | 36,854 / 141 |
| D7B1DA3D | 26,261 / 10 | 26,465 / 8 | 26,597 | 26,610 / 173 |
| DD42028C | 89,840 / 189 | 93,624 / 91 | 95,084 | 95,097 / 109 |

The no-shared-anchor 1A62 file has cue count byte 3,176 / 119,
timeline count byte 5,560 / 51, and timeline end/trailer byte 6,380; it has no
addressed footer. These boundaries are structural-only until a representative
wire capture exists.

`{AE9E3C61-AF40-4392-80B4-380D39C631B9}.ssfile` has 111 declared timeline
records plus a fully decoded 256-record continuation (367 total); no trailing
bytes are silently skipped.

Positive references in every structurally parsed layout use the same packed
record grammar, but the raw→`cue_index` relation is **provenance-dependent, not
universal** (see "Reference resolution is PROVENANCE-DEPENDENT" above). Legacy
records resolve `cue_index = raw - 1` (one-based: A5 fully wire-proven and
strongly preferred by the three new representative comparisons); controlled
newly written records resolve `cue_index = raw` (direct); edited-legacy files are
mixed. `cue_index = raw - 1` must therefore NOT be applied uniformly. The live
default-project Opalite bytes contradict their earlier “new direct” provenance
label, so a title/SSID label is not a resolver. Uncaptured layouts remain
structural-only and all files require explicit trustworthy provenance or must
fail closed.

## A5 scripted correction and wire proof

A5 offsets are:

| Field | Offset/value |
| --- | --- |
| Shared block | 2,243; 441 bytes |
| Cue count | 2,684; 233 cues |
| Timeline count | 7,348; 16 records |
| Timeline records | 7,352 through 7,607 |
| Trailer | 7,608; 13 bytes |

The first record at byte 7,352 has elapsed 59,088 and raw reference 91. It
resolves stored `cue_index=90`, dictionary record byte 7,148, GUID
`f6b7ab2ce4d7fb468e5ae468bcb2d869`, `RED BOX SWAY DROP 149bpm`.
Its exact CH1-CH19 vector is:

```text
[3, 0, 41, 121, 186, 107, 134, 79, 0, 141, 0, 196, 0, 0, 143, 0, 0, 0, 255]
```

Raw reference 229 resolves stored `cue_index=228`, GUID
`0d9fbc031d4d3549acdf7de94e2d05f8`, `IMPLODE`.

The passive capture fits with an all-zero initial state and no captured frame as
renderer input:

- 16/16 event states byte exact;
- 14/14 positive-reference event states byte exact;
- 2/2 raw-reference-zero states byte exact;
- RMS transition residual 6.075 ms; maximum absolute residual 13.92 ms;
- fit mode `exact_layered_state_anchor`.

For this one file, CH11 behaves as a provisional independent control layer.
Raw-reference-zero clears the main layer while retaining CH11=210 at record
7,512 / elapsed 116,022 and CH11=214 at record 7,544 / elapsed 124,478. This is
a single-file result, not a universal CH11 rule.

## Layered render model and remaining control blocker

The research harness tracks:

1. inherited initial state;
2. main cue layer;
3. named control/effect layers;
4. raw-reference-zero main-layer clears;
5. negative-time records;
6. provisional active deck owner.

Sparse cue patches update only encoded channels. They do not zero-fill omitted
channels. A wire-seeded initial state is reported only as transition-only
validation and never as full static render proof.

The current autoloop capture contains 68 segments for 19 files. Seventeen
segments are byte-exact static renders, but only files 5 and 18 are exact across
all of their captured segments. Fifty-one segments retain unresolved layer,
field, or ownership state.

The Venue `STROBE` cue GUID is `ea7be0ca8e396340b5de863399bb6004`.
It resolves correctly at the known file/record locations:

- file 47 bytes 7,622 and 7,910;
- file 48 bytes 7,467, 7,515, and 7,579;
- file 55 byte 7,416.

Its group `0x493` patch includes CH1=3, CH10=110, CH11=0. The passive capture
instead retains CH11=227 at 354 mismatch frames in file 47, 287 in file 48
(including one expected 214), and 102 in file 55. The STROBE cue itself does not
explain 227. The remaining candidates are an independent control/effect layer,
negative-time preload, the 17-byte auxiliary field, the shared table, inherited
state, another deck, or a fixture-profile transform.

## Venue, fixture, and position scope

The cue parser finds 232 current attribute cues, all using profile
`b8ad2201b9e4c94696c898a7e8f6a5a9`. Of those cues, 229 encode groups `0x493`
and `0x496`; three encode all four child groups `0x493`, `0x494`, `0x496`, and
`0x497`.

Four fixture-instance names are located at Venue string-length offsets 4,141,
4,355, 4,642, and 4,856. The surrounding object fields have not yet established
physical fixture membership or mirror routing.

The software-visible wire target is narrower and confirmed: across all three
pcaps, Universe 0 contains 123,254 frames and no nonzero byte beyond CH19;
Universe 1 contains 123,253 frames and is zero in every frame. Thus the current
captured byte surface is Universe 0, base channel 1, footprint 19. This does not
prove how four physical fixture instances mirror or consume that surface, so a
physical fixture patch remains blocked.

## Autoloop catalogs

Both catalogs parse exactly to EOF:

| File | Size | Layout | Entries | Index range | SHA-256 |
| --- | ---: | ---: | ---: | --- | --- |
| `SoundSwitchAutoLoops.bin` | 1,112 | 2 | 18 | 0..17 / files 1..18 | `152f10e1bac6b32779c1611417789090a88d90a47f519484cc0d159939768a6a` |
| `SoundSwitchAutoLoopsEx.bin` | 1,534 | 3 | 24 | 32..55 / files 33..56 | `bb0fd5be333688f110e01d1b2b9227664bdc77b0caf3d52653dcfbd601ec3d70` |

Each entry provides record type 2, AppLog index, file number `index + 1`, eight
bars, enabled flag 1, display name, category index, and authored ordering. Both
files end in exact per-category index tables and a final marker; unparsed size
is zero. Categories are BREAKDOWN, GROOVE // MID ENERGY, BUILDUP // RISING, and
DROP // HIGH ENERGY.

## TrackMap identity

The strict repeated-subrecord scanner proves:

- 95 mapping records at exact byte boundaries;
- 71 unique normalized SSIDs;
- 78 unique filepaths;
- 11 duplicated SSIDs and 5 duplicated paths;
- 62 mappings whose current path exists and 33 stale paths;
- no case-fold collisions in this corpus;
- 39 of 45 current scripted SSIDs represented;
- 61/61 comparable audio `SOUNDSWITCH_ID` tags match the mapped SSID exactly;
- one existing-path mapping has no readable tag; 33 stale paths are not comparable;
- no tag mismatch.

Six duplicated SSIDs have both stale and currently existing paths (DD42, 9947,
2889, 4883, 5996, and 88E1 prefixes). This is direct moved-file evidence: the
SSID persists while the locator changes, so filepath cannot be the stable key.

Each mapping subrecord begins with `04 00 00 00 01`, a Qt UUID, and three
presence-flagged Qt strings: title, artist, and filepath. For A5 the marker is at
4,343, UUID at 4,348, title at 4,368, artist at 4,436, path at 4,464, and the
subrecord ends at 4,580.

The future stable identity must be normalized SSID, cross-validated among the
TrackMap UUID, audio `SOUNDSWITCH_ID` tag when available, and `{SSID}.ssfile`
name. Any conflict fails closed. Filepath is a locator only; it is not a stable
identity. Content hash is useful for integrity but has no current evidence as a
SoundSwitch identity field.

The six TrackMap-missing scripts are exactly the six alternate-profile footer
files. They remain orphan project scripts for inventory purposes and cannot be
associated with audio by fuzzy filesystem search.

The top-level TrackMap object graph outside the repeated mapping subrecords is
still unnamed, so the TrackMap parser reports `partial`, not complete.

## Additional project artifacts

| Type | Observed classification | Future pack treatment |
| --- | --- | --- |
| `.ssproj` | 160-byte JSON project manifest; project UUID and version 2.10.3. | Read, hash, report. |
| `*.ssa` | One 14,432-byte high-entropy (`7.9858` bits/byte) track-adjacent opaque artifact; filename matches a script SSID. | Hash/report; fail closed if later proven render-affecting. |
| `automation_presets/*.sspreset` | One 161-byte opaque binary preset. | Hash/report; do not interpret without a controlled diff. |
| `recordable/*.dat` | Four `0xDEADBEEF` structured binaries containing 9, 24, 114, and 96 `SoundSwitch.Controls.*` strings. | Treat as external-control mapping data, separate from authored static render input. |
| `In App Demo.mp4` | 44,701,022-byte `mp42` media. | Ignore as authored lighting source; optionally hash/report. |
| `SoundSwitchVenues.bin.backup` | Opening the project rewrote it from frozen `521cc9...` bytes to the current Venue hash `f34bfc...`; current size and bytes now equal current Venue. | Hash/report side effects only; never source truth and never auto-restore. |

`.ssa`, `.sspreset`, and recordable numeric binding semantics remain opaque.

## Authoring mutation and rescan result

[confirmed] The read-only `freeze_project_snapshot.py` and
`compare_project_snapshots.py` helpers now provide complete relative-path
inventory, stable reads, hashes, byte-diff ranges, parsed identity diffs, and
cross-source consistency diagnostics. Repeated no-change reports are
byte-identical. [confirmed] Offline adversarial copies prove the comparator fails closed for
add/remove/replace/rename, case-only relocation, unresolved/missing references,
duplicate cue indices, fixture-profile mismatch, unsupported/opaque changes,
and concurrent source mutation.

[confirmed] Those verifier tests are not SoundSwitch authoring evidence. The only attempted
AL-ADD run used an operator-created `CODEX MUTATION SCRATCH.ssproj` with no
fixtures. It produced no new cataloged autoloop, changed Venue/TrackMap
artifacts, and exposed 128 fixtureless autoloop files in an unsupported layout.
[confirmed] The run is invalid setup evidence and leaves AL-ADD [unknown]. No valid
add/edit/rename/remove UI mutation has been isolated.

[assumed] Creating a fixture-bearing duplicate is the next research prerequisite. No
further SoundSwitch UI action is authorized by this document because merely
opening the real project already rewrote its backup file. Any future play or
static-look trigger also requires separate per-run approval and recorded
fixture-disconnected/safe confirmation. Those future results remain [unknown].

## Deck ownership and transport blockers

Within the combined capture, AppLogs expose 97 Deck-0 and 156 Deck-1 autoloop
events. They do not expose master-deck selection, crossfader state, stop/unload,
or Universe-0 ownership. Of 167 event clusters, 39 contain Deck 0 only, 83 Deck
1 only, and 45 both. Sixty-five of 68 validation segments contain other-deck
changes, including 16 byte-exact segments. Temporal proximity therefore does
not identify output ownership.

The 2026-06-20 operator-gated run captured three additional real scripted tracks
plus a dedicated transport run. Canonical summary:
`/tmp/ss_scripted_validation_summary_20260620.json` (SHA-256 `9ec44192…`).
Both Venue fixture groups `0x493` and `0x496` produced identical comparisons.

| Track | Convention comparison at bridge-anchored time | One-based full-frame samples | Arbitrary bridge-position samples | Result |
| --- | --- | ---: | ---: | --- |
| TITANIUM `FC10FC02` | one-based 16/64 vs direct 0/64 event samples | 16/64 | 21/57 | blocked; many channel residuals |
| Opalite `74044FA4` | one-based 23/39 vs direct 0/39 event samples | 23/39 | 48/57 | blocked; its previous “new direct” provenance label is contradicted by default-project wire evidence |
| New Sky `AE9E3C61` | one-based 304/367 vs direct 45/367 event samples | 304/367 | 53/71 | blocked; representative but not byte-exact |

The validator now anchors elapsed zero to the nearest copied bridge
`arm-scripted` observation; unconstrained wire fitting remains explicitly
exploratory. Expected event samples are rendered at
`event_elapsed + sample_delay`, so 1–2 ms compound cue pairs are compared to the
same settled instant as the wire. `render_at_elapsed` rebuilds from project bytes
for every query, and `render_playback_state` adds explicit playing/paused versus
ended/unloaded policy. Both fail closed unless provenance is explicitly
`one_based` or `direct`.

The New Sky decoupled-color candidate falsifies the current persistence rule.
`WHITE` at 214.807 s sets CH8/CH9=`172/255` byte-exact. The following decoded
CH15-only `BUILDUP SPEEDUP` record at 215.483 s was expected to retain those
bytes and set CH15=207; wire instead emitted CH8/CH9/CH15=`0/255/0`. The same
result repeats at 217.137/217.387 s. Therefore a Venue patch that omits CH8/CH9
cannot yet be treated as proof that both bytes persist on scripted tracks.

The dedicated Opalite transport capture
`/tmp/ss_scripted_transport_74044FA4-45A5-4FE6-85ED-F8D8698A346A.pcap`
(SHA-256 `ac6c8d99…`) demonstrates position-based evaluation without mutable
history where the underlying static model is already correct: the backward seek
sample and the second forward seek sample are byte-exact; all 22 logged loop
window samples are byte-exact; and re-fire is byte-exact from the first actually
playing sample at 1.978 s. The first forward seek and pause landed in Opalite's
independently observed 116–133 s static-render residual interval. Wire held the
same frame through pause, then returned to an exact rendered frame after resume
at 133.887 s. Both confirmed stop markers are all-zero byte-exact. Unload caused
a bridge position reset to zero but left stale filename/mode status; wire was
already zero and made no additional transition. Deck transfer, Decks 3/4, and
scripted/autoloop overlap remain uncaptured.

The archived edited copy (`WHYB-AFTER.ssproj`, hash `63302346…`) remains the
MIXED negative control. `validate_scripted_capture.py --reference-rule mixed`
fails closed with exit status 2 before rendering.

## Readiness decision

Export/import implementation is **not ready**. The format work is materially
further along, but the following render-affecting unknowns remain:

- auxiliary values and negative-time activation semantics;
- shared-table and independent control/effect layers, including CH11=227;
- the newly captured scripted classes outside A5 have representative wire proof
  but retain full-frame residuals, plus one unsupported demo layout;
- position-evaluation transport semantics and bridge-owned multi-deck
  composition;
- top-level TrackMap completeness;
- `.ssa`/preset semantics when active;
- complete authoring add/edit/rename/remove mutation evidence from a
  fixture-bearing scratch duplicate;
- physical fixture membership/mirroring beyond the confirmed Universe-0
  CH1-CH19 wire surface, unless deliberately supplied by a versioned external
  fixture-map input.

All unsupported cases must remain visible and fail closed. The controlled
operator procedures are in `docs/plans/active/soundswitch_stage3_handoff.md`.

## 2026-06-20 legacy scripted-edit experiment (RED pre-roll)

Two controlled operator edits added the global **RED** Attribute Cue before the
first beat of two legacy scripted tracks and saved (evidence under
`/tmp/soundswitch_finish_IiVlD1`: A5/SANFRANDISCO `84f6bf72…`→`addd777d…`;
"Where Have You Been" `528E8B22` `1f740632…`→`63302346…`). Confirmed findings:

- **Edited legacy scripted files become MIXED** (old records one-based, new
  record direct; no byte disambiguator). This is the central reference-convention
  result — see "Reference resolution is PROVENANCE-DEPENDENT" above.
- **The dictionary is expanded to the full current Attribute-Cue bank on edit**
  (WHYB 196→233 cue entries, +37 GUIDs, 0 removed) and re-normalized (two
  `cue_index` bytes swapped with the matching timeline raw refs rewritten to keep
  the GUID stable under its own convention). Full-project rescan stays mandatory.
- **Pre-first-beat scripted placement stores `elapsed = 0`**, not a negative
  time. The track's beatgrid begins at the first beat (`elapsed` of the first
  existing cue, e.g. 60064); "before the first beat" maps to absolute elapsed 0.
  This differs from autoloop pre-roll, which uses signed-negative ticks (−86/−76)
  because the loop origin is the grid start. [operator-confirmed] No track exposes
  a beat *before* the first beat, so "exactly one beat before" is not authorable
  in either editor; the earliest UI-allowed pre-roll is the observable bound.
- **Lazy scripted-track rediscovery** [operator-confirmed]: a project duplicated
  from `default.ssproj` does not show the scripted icon in music search until the
  operator opens a track whose timeline contains attribute cues. A deterministic
  rescan must therefore detect scripted tracks from `{SSID}.ssfile` bytes + the
  TrackMap, never from a UI/project "scripted" flag.

## Layered laser render model (autoloop-verified; scripted scope falsified 2026-06-20)

In this rig SoundSwitch's Universe-0 CH1-19 output IS the laser fixture; the
bridge owns decks/transport/selection. The autoloop evidence supports a layered
persistent buffer of static snapshots (segments show ~4-9 distinct frames over
~500 captured, not hundreds). The three new scripted captures show that this
model is **not yet general enough for scripted tracks**. A standalone renderer
still only needs to replicate the byte-exact frame, but the missing scripted
layer/mask semantics must be decoded first.

Autoloop composition rule (derived from `autoloop_probe.pcap` + venue cue patches):

- **Position/pattern layer** = the captured autoloop timeline cue resolved
  ONE-BASED. Sets its patch channels; leaves CH8/CH9 open in that capture scope.
- **Color layer** = an independently bridge-selected color Attribute Cue, driving
  CH8 (color/effects) and CH9 (color speed).
- **Persist/control channels** CH8, CH9, CH11(strobe) hold their last value until
  a cue sets them; a raw-0 (clear) event zeroes the main/position channels but
  NOT these persist channels.
- Idle/transition between looks = all-zero (bridge domain).

Autoloop verification: across the full bridge-used autoloop corpus captured (SSAutoLoop
3/5/18/50/52/53/54), **29/30 distinct wire frames are full-frame byte-exact**
under `position-cue(one-based) ⊕ color-cue(CH8/9) ⊕ persist(CH8,9,11)`; the color
layer matches a known cue 30/30; the lone position miss is the all-zero blackout
frame. Render config that reproduces this autoloop scope:
`control_channels=(8,9,11)` with a steady-loop inherited initial state. It does
not establish scripted parity: TITANIUM, Opalite, and New Sky are respectively
16/64, 23/39, and 304/367 exact under the current scripted hypothesis, and the
New Sky decoupled-color case specifically clears CH8 instead of persisting it.
