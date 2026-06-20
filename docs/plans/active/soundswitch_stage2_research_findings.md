---
doc_status: active-research
truth_level: byte-and-capture-grounded
last_verified_commit: fd40843
last_verified_date: 2026-06-20
validation_scope: passive software and wire capture only; hardware-unvalidated
---

# SoundSwitch Stage 2 Research Findings

## Decision

The current project can be inventoried deterministically, both catalogs parse
exactly, all 42 autoloops parse structurally, 44/45 scripted files are
structurally classified, TrackMap identity subrecords are decoded, and A5 renders
16/16 captured events byte-exact.

The exporter/importer is still deferred. Control layers, fixture patching,
transport, deck ownership, one scripted demo layout, and representative capture
coverage remain blocking.

Status is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## Corrections to prior findings

1. Positive timeline references are one-based: stored dictionary
   `cue_index = raw_reference - 1`. The lookup is by the stored one-byte
   `cue_index`, not physical dictionary order.
2. Raw reference zero is a distinct clear/control event, not cue index zero.
3. A5 raw 91 resolves cue index 90 / `RED BOX SWAY DROP 149bpm`; raw 229
   resolves cue index 228 / `IMPLODE`.
4. A5 is byte-exact with an all-zero initial state and an explicit main/control
   layer model; no wire frame is hidden renderer input.
5. Files 16 and 54 do not reference a deleted cue. Their raw 232 resolves
   current `WIDE SPREAD  copy copy`. The deleted `b0aca...` entry is unused,
   and neither it nor file 36's two stale GUIDs exists in the Venue backup.
6. The 12 UUIDs in each 356-byte fixture-group record are Venue position
   presets, not attribute-cue UUIDs.
7. Earlier “nine unsupported scripted layouts” was too pessimistic. Strict
   boundary discovery now parses eight without the shared-table anchor. Only
   the In-App Demo file remains structurally unsupported.
8. `SoundSwitchVenues.bin.backup` is not identical to the current Venue and is
   never source truth.

## Confirmed corpus totals

| Corpus | Total | Structurally parsed | Captured files | Byte-exact captured files |
| --- | ---: | ---: | ---: | ---: |
| Autoloops | 42 | 42 | 19 | 2 (files 5 and 18) |
| Scripted | 45 | 44 | 1 | 1 (A5) |
| Venue attribute cues | 232 | 232 cue records | n/a | A5/captured autoloops use group `0x493` oracle |
| Catalog entries | 42 | 42 | n/a | Exact-to-EOF parse |
| TrackMap mapping records | 95 | 95 repeated subrecords | n/a | 61/61 comparable audio tags agree |

The full one-row-per-file coverage is in
`docs/plans/active/soundswitch_validation_matrix.md` and is reproducible with
`tools/ssfmt/re/build_coverage_reports.py`.

## A5 proof

- Project SHA-256: `84f6bf7286d1bdb304318129b7c3b2acfb249d3f02057c4e4cf826e0f40d30e0`
- Capture SHA-256: `a2521081a215f30e8e24c6570caa594d0b3133ce3b29ab6bf77666f770136d47`
- Venue SHA-256: `f34bfc796e9e589c7eb4707ee4f223c6ea6fd2f597d08622d30370f16a2a3398`
- Fit: `exact_layered_state_anchor`
- Events: 16/16 exact
- Positive references: 14/14 exact
- Raw-zero clears: 2/2 exact
- Raw-zero retained CH11: 210 and 214
- RMS/max transition residual: 6.075/13.92 ms

The model is all-zero inherited state, sparse main patches, provisional CH11
control ownership, and raw-zero clear-main/retain-control. CH11 ownership is
single-file provisional, not a general rule.

## Autoloop structure and capture

All 42 files share the same fixture profile, six-group block, 441-byte table,
dictionary grammar, and 16-byte timeline grammar. There are:

- 1,904 timeline records total;
- 21 negative-time records;
- 178 raw-zero records;
- 72 nonzero auxiliary records in files 2, 7, 35, 48, and 50;
- one nonstandard field pair, file 13 byte 8,082 with
  `(field_a, field_b)=(0x01000001,1)`;
- a 256-record continuation in file 13.

The combined pcap contains 30,821 Universe-0 frames across 835.105 seconds. The
validator extracts 68 usable bridge-correlated segments: 17 byte-exact static
segments and 51 unresolved segments. Files 5 and 18 are exact across all their
captured occurrences. A wire-seeded segment is labeled transition-only and is
never counted as a static-render proof.

The earlier 2,308.840-second `artnet_lo.pcap` is also exhausted. Its frozen
manifest proves all 42 autoloop files remain byte-identical and its Venue
snapshot has the same 232 parsed cue semantics as current. A surviving derived
library names 41/42 indices, but omits index 6, accounts for 82,212 of 84,275
Universe-0 frames, and contains no segment timestamps. It proves historical
coverage/sample states, not byte-exact segments.

## Strobe/control result

The one-based lookup confirms the Venue `STROBE` cue at the specified file
offsets. The cue writes CH11=0, while the wire commonly retains CH11=227:

| File | Known timeline offsets | Static CH11 mismatch pairs |
| --- | --- | --- |
| 47 | 7,622; 7,910 | expected 0 / actual 227: 354 frames |
| 48 | 7,467; 7,515; 7,579 | expected 0 / actual 227: 286; expected 214 / actual 227: 1 |
| 55 | 7,416 | expected 0 / actual 227: 102 |

The STROBE patch does not generate 227. Current files do not uniquely identify
whether 227 belongs to an effect lane, preload sentinel, auxiliary record,
shared controller, inherited layer, another deck, or fixture transform.

## Catalog and identity result

`SoundSwitchAutoLoops.bin` and `SoundSwitchAutoLoopsEx.bin` parse exactly to EOF,
including category tables and final markers. AppLog index maps to file number
`index + 1`.

TrackMap has 95 repeated mappings, 71 SSIDs, and 78 paths. Thirty-three mappings
are stale. There are 11 duplicated IDs and five duplicated paths. No case-fold
collision appears. Sixty-one comparable audio tags match exactly; none conflict.
Six SSIDs have both stale and existing path records, directly proving that path
movement does not change stable identity.

The future authority is normalized SSID. TrackMap UUID, audio tag, and script
filename must agree when each exists. A path is only a locator. Six current
alternate-profile scripts are not mapped and must remain explicit orphans.

## Fixture and artifact result

All 42 autoloops contain six 356-byte groups (`0x492..0x497`) and 12 verified
Venue position references per group. The current Venue has four fixture names,
but physical membership/mirror fields remain unnamed. All three pcaps confirm
that only Universe-0 CH1-CH19 becomes nonzero and Universe 1 stays entirely
zero. The software-visible byte address is therefore explicit; the physical
four-fixture mirror patch is not.

The project manifest and four recordable control-mapping files are classified.
The `.ssa` and automation preset payloads remain opaque. The bundled MP4 is
media, not authored lighting. The Venue backup differs from current and is
report-only.

## Deck/transport result

The combined capture proves independent Deck-0 and Deck-1 AppLog selections,
not Universe ownership. It contains 97 Deck-0 and 156 Deck-1 events; 65/68
validation segments overlap another-deck events, including 16 exact segments.
This makes simple temporal attribution invalid.

Master deck, crossfader, stop, unload, seek, pause/resume, end, transfer,
scripted/autoloop overlap, and Decks 3/4 remain unsupported. The bounded
operator protocol is in `soundswitch_stage3_handoff.md`.

## Stage 2 exit assessment

| Gate | Result |
| --- | --- |
| A5 one-based positive refs | Pass |
| A5 raw-zero clear/control | Pass, single-file provisional layer rule |
| A5 16/16 exact | Pass |
| Layer-aware research renderer | Pass for A5 and clean autoloops; incomplete globally |
| Every mismatch named | Pass at blocker-class level; field semantics unresolved |
| 42 structural inventory | Pass |
| Every captured current look byte-exact | Fail |
| 45 scripted classification | Pass (44 parsed, 1 explicit unsupported) |
| Representative wire proof for every layout | Fail |
| Catalogs complete | Pass |
| Track identity deterministic | Partial; repeated records complete, top-level graph and six orphans remain |
| Fixture patch explicit | Fail |
| Multi-deck/transport deterministic | Fail |
| Export/import implementation ready | **No** |

No production exporter, pack, importer, or bridge runtime work should start
until the fail gates are closed or the declared supported scope excludes them
explicitly with fail-closed behavior.
