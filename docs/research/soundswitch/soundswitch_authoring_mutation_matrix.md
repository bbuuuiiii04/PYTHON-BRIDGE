---
doc_status: research-complete-bounded-scope
truth_level: controlled-diff-and-binary-grounded
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: fixture-bearing scratch-project authoring diffs plus binary save paths; software evidence only; hardware-unvalidated
---

# SoundSwitch authoring mutation matrix

## Result

The go-forward complete-rescan rule is closed for the bounded SoundSwitch
2.10.3 workflow. After Brandon saves and clicks Export, supported additions,
edits, moves/reorders, renames, duplicates, learned mappings, and removals are
discoverable from current saved bytes without a capture oracle.

The experiment corpus is `/tmp/soundswitch_finish_IiVlD1`. It uses a
fixture-bearing duplicate of the real project. The earlier fixtureless
`CODEX MUTATION SCRATCH` attempt is invalid setup evidence and is not used.

## Matrix

| Object/action | Observed saved mutation | Stable identity | Export rule | Status |
| --- | --- | --- | --- | --- |
| Autoloop create | adds catalog identity 18 and `SSAutoLoop19.ssfile` | AppLog index + file number | full catalog/file rescan | confirmed |
| Autoloop rename | display name only | index/file unchanged | name is metadata | confirmed |
| Autoloop cue add | file 19 timeline/dictionary change | file number | parse current records | confirmed |
| Autoloop second cue | file 19 timeline change | file number | parse all records | confirmed |
| Autoloop move/reorder | elapsed/tick changes in file 19 | file number + source order | sort by signed time then stored order | confirmed |
| Autoloop pre-roll | signed negative tick | file/record | apply before cycle zero | confirmed |
| Autoloop post-roll | positive tick beyond prior end | file/record | retain full saved range | confirmed |
| Autoloop placement delete | timeline record removed | file/record | absence is authoritative | confirmed |
| Autoloop delete | catalog identity and file removed | index/file | remove from pack; detect stale maps | confirmed |
| Autoloop duplicate name | name may match other rows | index/file | never resolve by name | supported by identity grammar |
| Category reorder | saved category-order table changes | AppLog identity | resolve control slot through current table | supported by catalog writer/reader grammar |
| Script create | new `{SSID}.ssfile` and TrackMap identity | normalized SSID | parse supported layout after save | confirmed |
| Script cue add/edit | dictionary/timeline changes | SSID + cue GUID | parse current bytes | confirmed |
| Script clear | timeline records removed | SSID | empty/current timeline is authoritative | confirmed |
| Script legacy edit | old/new stored integers coexist | SSID + raw records | runtime still uses version-locked `raw-1` | confirmed |
| Script move/reorder | elapsed/order changes | SSID + record order | physical timeline order/times | covered by writer/reader and move semantics |
| Script duplicate | duplicated records remain distinct by stored order/time | SSID + record occurrence | retain every record | covered by physical writer |
| Attribute Cue create | Venue cue GUID and sparse map added | GUID | add to cue bank | confirmed |
| Attribute Cue rename | mutable name changes | GUID unchanged | name is metadata | confirmed |
| Attribute Cue edit | sparse channel values change | GUID | replace current patch | confirmed |
| Attribute Cue placement | `.ssfile` reference added | cue GUID via dictionary | cross-validate reference | confirmed |
| Attribute Cue undo | saved bytes return to prior semantics | GUID | current bytes win | confirmed |
| Attribute Cue delete | Venue GUID removed; stale refs can remain | GUID | fail with exact source/ref until repaired | confirmed |
| Static Look create | primary Venue slot 7 gains name/map | Venue GUID + zero-based slot | export all 32 slots | confirmed |
| Static Look edit | same slot map changes | Venue GUID + slot | replace current slot | confirmed |
| Static Look rename | name field changes | Venue GUID + slot | name is metadata | physical grammar confirmed |
| Static Look clear | empty slot record remains in fixed array | Venue GUID + slot | export empty slot | physical grammar confirmed |
| MIDI learn add/edit | `ControlMapDetail` inserted and complete registry saved | device/collection/event/control path | full recordable rescan | binary confirmed |
| MIDI unmap | matching detail removed and registry saved | same | absence authoritative | binary confirmed |
| MIDI clear/remove device | map/device vector removed and saved | same | absence authoritative | binary confirmed |

## `.ssfile` runtime rule after every mutation

```text
raw_reference == 0 -> clear/control
raw_reference > 0  -> dictionary stored_key raw_reference - 1
```

Controlled creation proves the editor may store the visually selected direct
number while cold runtime emits `raw-1`. The exporter intentionally reproduces
emitted SoundSwitch behavior rather than attempting to repair editor intent.
This applies equally after create, add, delete, move/reorder, duplicate, and
resave because the physical reader consumes the current stored integer through
the same runtime path.

## Complete-rescan invariants

Every export must:

1. read a stable project snapshot and verify no source changed during the read;
2. inventory every path, including additions, removals, opaque sidecars, and
   backups;
3. validate version and primary Venue/profile fingerprint;
4. decode both catalogs and their category-order tables;
5. decode all learned MIDI bindings and report event collisions;
6. decode all Attribute Cues and 32 primary-Venue Static Looks;
7. decode all current Autoloop and scripted `.ssfile` records;
8. cross-check TrackMap/SSID and every positive cue reference;
9. fail before publication for unsupported layout, missing cue, collision,
   profile change, or concurrent mutation;
10. publish the pack atomically only after independent verification passes.

## Exact operator remediation for a stale cue reference

If a deleted Attribute Cue is still referenced, the exporter reports the cue
GUID, source `.ssfile`, raw reference, and elapsed/tick. Brandon must open that
source in SoundSwitch, remove or replace the stale placement, save, close the
edit, and click Export again. No capture or manual byte editing is permitted.

## Evidence limitation

These are saved-byte authoring results. They do not validate physical fixture,
laser, Enttec, optical, or show behavior.
