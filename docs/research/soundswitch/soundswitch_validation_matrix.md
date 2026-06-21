---
doc_status: active-validation-evidence
truth_level: byte-binary-test-and-capture-grounded
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: SoundSwitch 2.10.3 bounded current project/profile; passive software-visible wire only; hardware-unvalidated
---

# SoundSwitch reverse-engineering validation matrix

The current verdict is `soundswitch_re_closure_report.md`. Missing per-file
capture is confidence coverage, not a parser or export blocker when physical
bytes, references, and active cue dependencies are unambiguous.

## Product-gate matrix

| Surface | Current evidence | Result | Product consequence |
| --- | --- | --- | --- |
| Autoloop physical grammar | 42/42 strict parses; count-257 regression | pass | all current files readable |
| Scripted physical grammar | 44/45 strict parses | pass bounded | inactive demo unsupported |
| Active scripted inventory | 32/32 existing-path rows supported | pass | no per-track capture requirement |
| Active Autoloop selection | 19/19 IAC bindings resolve | pass | 18 automatic + file-3 blackout |
| Positive reference rule | legacy A5, legacy Autoloop, cold new scripted wire | pass | runtime `raw-1` |
| Raw zero | A5 2/2 plus current file-3 zero behavior | pass | explicit clear/blackout source |
| Attribute Cue bank | 232/232 parsed; 166 active referenced, 0 missing | pass | full GUID closure |
| Sparse persistent patches | controlled diffs + A5/Autoloop wire + cache binary | pass | omitted channels persist |
| Intensity metadata | reader/writer + current profile flag absence | pass | preserve; no CH1-CH19 effect |
| Static Look physical grammar | unique primary GUID collection, 32/32 slots | pass | export full bank |
| Static create/edit | controlled slot-7 create/edit diffs | pass | future edits rescan directly |
| DDJ Static Override mapping | 4/4 bindings resolve to slots 8/16/17/24 | pass | include DDJ controls/frames |
| Static override precedence | binary enable/refresh/cache call chain | pass | note-on hold, note-off rerender base |
| Learned MIDI map grammar | 24/24 bindings parsed, zero event collisions | pass | complete rescan input |
| Learned map mutation | binary add lambda and all remove paths call save | pass | new/removed mappings detected |
| Autoloop authoring mutations | create/rename/add/move/pre/post/delete corpus | pass | identity and reorder rules closed |
| Scripted authoring mutations | create/edit/clear/legacy edit + cold reopen | pass | future matching files export directly |
| Blackout/restore | file-3 bytes, bridge/AppLog/wire, generic binary flag | pass | stateless zero then current rerender |
| Transport | seek/loop/refire/pause/stop evidence + position renderer | pass bounded | bridge position is authority |
| Deck ownership | binary SoundSwitch modes + bridge invariant | pass bounded | bridge single owner; no SS parity promise |
| Fixture output | Universe 0 CH1-CH19 passive wire | software/wire pass | hardware remains unvalidated |

## Reference evidence

### A5 legacy scripted

- 16/16 event states byte exact under the layered current-profile renderer;
- 14/14 positive references match one-based;
- 0/14 match direct;
- 2/2 raw-zero events match;
- no captured frame is used as renderer input.

### Legacy Autoloop discrimination

The dedicated operator-gated capture uses color-discriminating records. Across
the decisive files, one-based-rendered states appear on wire; direct candidate
states do not. Example: file 52 raw 27 at tick 2325 resolves stored key 26 and
matches GREEN byte-exact; direct key 27 CYAN never appears.

### Cold newly authored scripted track

Source hash:
`11d6913f90ab641ff80c98032d860a2db3a5d40c355d1982198dc41d668513b4`.

Capture:
`/tmp/ss_cold_direct_0D25_20260621_001.pcap`, SHA-256
`c1db3fb7c190138189a95e73c6f4303cd783053b3c8900f0a78349eb792e4d00`.

Saved raw 21/22/26 emitted stored keys 20/21/25: 3/3 one-based, 0/3 direct.
The operator's RED/BLUE/GREEN editor selection mismatch is therefore a verified
SoundSwitch runtime behavior.

## Active inventory checks

`build_coverage_reports.py` reports:

- Autoloops: `complete_bounded_inventory`, 42/42 parsed;
- scripted: `complete_bounded_inventory`, 44/45 parsed;
- active existing-path scripted: 32/32 supported;
- active missing referenced cue GUIDs: zero.

`inventory_project_artifacts.py` reports:

- 19 enabled IAC note bindings resolved through catalog category order;
- four DDJ-800 Static Overrides resolved through the primary Venue's exact
  32-slot collection;
- current learned-map event collision count zero;
- intentionally absent channel-2 utility mappings remain visible but are not
  misclassified as missing SoundSwitch content.

## Static Look evidence

The parser finds 20 valid GUID-keyed `StaticLooks` collections in the Venue
binary and selects the unique collection keyed by primary Venue GUID
`b8ad2201b9e4c94696c898a7e8f6a5a9`. It parses exactly 32 version-5 slots.

Current learned rows:

| Control | Slot/name | CH1-CH19 outcome |
| --- | --- | --- |
| DDJ CH7 note106 | 16 OFF | all zero |
| DDJ CH10 note122 | 24 STROBE BUILDUP #1 | exact sparse generic frame |
| DDJ CH10 note123 | 8 STROBE EFFECT | exact sparse generic frame |
| DDJ CH10 note127 | 17 RAINBOW STROBE | exact sparse generic frame |

The controlled `STATIC-CREATE` comparison changes slot 7 from empty to
`CODEX STATIC 01` and adds only its generic group values. The edit comparison
changes that slot's value. Binary read/write and runtime cache paths independently
corroborate the grammar and precedence.

## Mutation evidence

The fixture-bearing scratch corpus under `/tmp/soundswitch_finish_IiVlD1`
contains frozen before/after copies and reports for:

- Autoloop create, rename, second cue, timeline add, move, pre-roll, post-roll,
  placement delete, and object delete;
- scripted create, edit, clear, and legacy edit;
- Attribute Cue create, rename, place, edit, undo, and delete;
- Static Look create, settle, and edit.

The reports retain unrelated/opaque changes and may say `partial_fail_closed`
because the scratch copy also contains an inactive unsupported script. That
global report label does not invalidate the isolated, identity-scoped mutation;
the operation rows name every changed source and the unsupported artifact stays
visible.

## Reproduction

Commands and expected current totals are in `research_tools.md`. Core regression
tests:

```bash
python3 -m unittest \
  tests.test_ssfile_reference_convention \
  tests.test_inventory_project_artifacts \
  tests.test_static_looks \
  tests.test_venue_fixture_profile
```

No software test or passive Art-Net capture proves physical laser, Enttec,
addressing, optical, or show safety behavior.
