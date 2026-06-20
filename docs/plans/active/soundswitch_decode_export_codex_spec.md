---
doc_status: active-blocked-spec
truth_level: evidence-constrained-plan
last_verified_commit: fd40843
last_verified_date: 2026-06-20
validation_scope: specification only; no exporter/importer implementation; hardware-unvalidated
---

# Deferred SoundSwitch Decode / Export / Bridge-Import Spec

## 1. Decision and scope

This is the information contract for a future static SoundSwitch pack. It is
not authority to implement `export.py`, a pack, an importer, bridge runtime
modules, configuration, output threads, or hardware behavior.

Implementation remains blocked by the gates in section 10. Current accepted
status is **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The first supported scope, if the blockers close, is deliberately narrow:

- SoundSwitch project version 2.10.3 / container version 3;
- the current fixture profile and current 19-channel Universe-0 byte vector;
- current Venue cues and current cataloged autoloops;
- scripted layouts with representative wire validation;
- deterministic failure for every unsupported structure or identity conflict.

Compatibility with other fixture profiles, SoundSwitch versions, projects,
universes, or hardware is not implied.

## 2. Source authority

The exporter must read a named project directory only. It must never perform a
filesystem-wide fuzzy scan.

Source priority within that directory:

1. current `.ssproj` manifest;
2. current `SoundSwitchVenues.bin`;
3. current autoloop catalogs and `.ssfile` bytes;
4. current `SoundSwitchTrackMap.bin` mappings;
5. audio tags only at the exact TrackMap paths;
6. explicitly classified sidecars and control artifacts.

`SoundSwitchVenues.bin.backup` is report-only and must never replace current
Venue. Every source receives size and SHA-256 before parsing. A source changed
during export is a fatal error.

## 3. Identity rules

Normalized SSID UUID is the authoritative scripted-track identity.

Cross-validation rules:

- TrackMap UUID, audio `SOUNDSWITCH_ID` tag, and `{SSID}.ssfile` name must agree
  whenever present;
- duplicate mappings are retained and reported, not silently deduplicated;
- a path is a locator only and cannot become the identity;
- path normalization may compare exact and case-folded spellings for diagnosis,
  but cannot merge conflicting files;
- a content hash proves integrity, not SoundSwitch identity;
- missing or stale paths remain explicit;
- a current script with no TrackMap mapping is an orphan, not a fuzzy-match
  candidate;
- any UUID/tag/filename conflict is fatal for that track.

## 4. Time, references, and layers

Every serialized timeline record must retain:

- source file and source offset;
- raw fields and raw cue reference;
- stored dictionary `cue_index` and physical dictionary record offset;
- resolved cue GUID/name and Venue record offset;
- raw time bytes and decoded unit;
- layer/event classification;
- source-decode error, if any.

Positive resolution is `cue_index = raw_reference - 1`. Raw zero is a
clear/control event, never cue index zero. Negative time remains a separate
sentinel/preload class until controlled evidence names its activation behavior.

The rendered state model must expose inherited state, main cue layer, each
control/effect layer, clear semantics, and active output owner. It must not use a
captured frame as hidden production state. A wire-derived initial state is
permitted only in a validation report labeled `transition_only`.

## 5. Proposed pack artifacts

All JSON uses UTF-8, sorted object keys where order is not semantic, arrays in a
specified deterministic order, integer byte values 0..255, lowercase SHA-256,
and an explicit `schema_version`. Unknown fields are not invented.

### `manifest.json`

Required fields:

- `schema_version`;
- `generator_version` and source commit;
- project ID and SoundSwitch manifest version;
- declared supported scope;
- source-relative path, size, SHA-256, format version, and parse status for
  every file;
- pack artifact hashes;
- completeness totals for catalogs, autoloops, scripted files, TrackMap, cues,
  fixtures, and captures;
- unresolved and unsupported counts;
- validation status fixed to software/capture-only unless separate evidence
  changes it.

No wall-clock timestamp participates in deterministic content hashing.

### `fixture_patch.json`

Required fields:

- current Venue hash and profile GUID;
- all fixture instances with stable IDs, universe, base address, footprint, and
  enabled state;
- six group records with source offsets, IDs, parent/owner links, member
  fixtures, and mirror/routing rule;
- 12 position slots with raw UUID, Venue name, and source offsets;
- CH1-CH19 semantic/channel map when known;
- exact Universe-to-fixture byte routing;
- unsupported profiles and validation evidence.

Passive evidence fixes the software-visible surface at Universe 0, base channel
1, footprint 19, with Universe 1 all zero. This artifact still cannot be emitted
as a physical fixture patch until four-instance membership/mirror fields are
decoded. Group names and wire address alone are insufficient.

### `selection_map.json`

Required fields:

- catalog source hash/layout;
- category name/index and authored category order;
- catalog entry order, enabled/type flags, AppLog index, and file number;
- display name and eight-bar loop length;
- bridge MIDI note/personality mapping only when read from an explicit source
  and cross-validated against capture;
- unsupported or unmapped selections.

### `venue_cues.json`

Required fields per cue:

- cue GUID, name, profile GUID, source offsets;
- every encoded fixture group/channel/value;
- explicit sparse-patch semantics;
- categories/positions/effects only after their object records are decoded;
- missing and duplicate diagnostics.

Cue arrays order by source offset. A consumer resolves by GUID, never display
name.

### `autoloops/<app-index>.json`

Required fields:

- source path/hash/version;
- catalog identity;
- fixture prefix and shared-table hash/reference;
- every 17-byte record, auxiliary value, and byte offset;
- dictionary entries including physical order and stored `cue_index`;
- declared and continuation timeline records;
- raw/reference/time fields and resolved cue diagnostics;
- negative/ref-zero/layer semantics;
- canonical 0..19,199 tick rendering only after all render-affecting fields are
  known;
- capture segment counts, exact frames, compared frames, timing residuals,
  mismatched channels/value pairs, and ownership interruptions;
- unsupported reason and next experiment.

### `scripted/<ssid>.json`

Required fields:

- normalized SSID and identity cross-checks;
- source path/hash/version/layout;
- header-addressed footer boundaries where present;
- dictionary/timeline/continuation records and raw offsets;
- clear/control/negative semantics;
- duration/time unit and transport state machine;
- representative capture validation for the layout;
- exact failure for unclassified layouts.

### `track_map.json`

Required fields:

- TrackMap source size/hash/version and partial/full parser status;
- every mapping's marker, UUID, title, artist, path, and field offsets;
- normalized SSID, path existence, exact/case-folded normalization evidence;
- duplicate-ID and duplicate-path groups;
- audio tag read status/value/match;
- relationship to current script filenames;
- stale paths, orphans, conflicts, and unsupported top-level fields.

### `import_report.json`

Required fields:

- pack schema/version and artifact hash verification;
- accepted/rejected counts by artifact and reason;
- source-to-import identity mapping;
- every unsupported timeline, cue, fixture, track, layout, or transport case;
- declared runtime scope and disabled features;
- no silent fallback or substitution;
- software validation performed and hardware validation explicitly absent unless
  separately proven.

## 6. Deterministic ordering

- source files: normalized project-relative bytewise path order;
- catalogs: authored ordering, then AppLog index as a consistency check;
- cues: source record offset;
- dictionary entries: physical source order, with `cue_index` stored separately;
- timeline: source sequence, retaining equal-time record order;
- mappings: marker offset;
- fixtures/groups: source record offset;
- diagnostics: `(source_path, source_offset, code)`.

## 7. Completeness and fail-closed policy

A pack is unsupported if any in-scope source:

- changes during read;
- has unknown magic/version/layout;
- has unconsumed non-trailer bytes;
- contains a duplicate dictionary key;
- has an unresolved positive reference;
- references a missing current Venue cue;
- needs unknown auxiliary, sentinel, shared-table, control, fixture, or owner
  semantics;
- has an identity conflict;
- lacks fixture routing required for CH1-CH19 output;
- lacks the representative capture evidence promised by its supported scope.

Unsupported files remain in totals and diagnostics. They are never skipped to
make completeness percentages look better.

## 8. Import/runtime requirements deferred to a later spec

The future importer must have a deterministic state transition for:

- initial load and play from zero;
- forward/backward seek;
- pause/resume;
- refire/reload;
- deck transfer;
- end, unload, and stop;
- scripted/autoloop overlap;
- master-deck and crossfader changes;
- Decks 3/4 if declared supported.

It must keep the bridge's 200 Hz push loop free of socket, MIDI, filesystem,
subprocess, and hardware I/O. Any future output uses a bounded worker/sender
boundary and requires a separate runtime design review. This research session
does not choose or implement that seam.

## 9. Verification required before implementation

- every supported autoloop captured byte-exact from known state;
- representative capture for each supported scripted layout;
- repeated runs proving determinism;
- controlled diffs for auxiliary, negative, ref-zero, and control lanes;
- complete fixture universe/address/mirror decode;
- isolated owner/master/crossfader/transport captures;
- exact TrackMap top-level inventory or a declared, bounded partial source rule;
- round-trip deterministic pack generation from a frozen project copy;
- independent verifier that rejects a single altered source byte, reference,
  artifact hash, or unsupported-case omission.

## 10. Current blockers

1. CH11=227 control ownership in files 47/48/55.
2. Twelve nonzero auxiliary values and 21 negative-time records lack semantics.
3. Shared 441-byte table semantics are not isolated.
4. Only files 5/18 and A5 have complete captured byte proof at file level.
5. One scripted demo layout remains structurally unsupported.
6. Other scripted layouts and transport behaviors lack wire proof.
7. Multi-deck ownership/composition is not deterministic.
8. Fixture universe/address/mirror behavior is not decoded.
9. TrackMap top-level object graph and opaque sidecars/preset fields remain
   partial.

Until these close, implementation readiness is **no**. The next authorized work
is controlled research using the operator handoff, not exporter development.
