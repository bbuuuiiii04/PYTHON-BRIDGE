---
doc_status: active-research-protocol
truth_level: evidence-constrained-procedure
last_verified_commit: a5f7ced
last_verified_date: 2026-06-20
validation_scope: scratch-project authoring diffs only; passive software evidence; hardware-unvalidated
---

# SoundSwitch Authoring Mutation Matrix

## Purpose and current status

This matrix tests the product requirement that a future exporter can perform a
complete rescan of a named SoundSwitch project and deterministically detect
every supported addition, edit, rename, and removal. It is a research protocol,
not authority to implement the exporter, importer, renderer, output adapter, or
bridge integration.

- [confirmed] The current unmodified project baseline reproduces 42/42
  autoloop parses, 44/45 scripted classifications, 232 Venue cues, exact
  catalogs, 95 TrackMap records, A5 16/16 event equality, and the documented
  autoloop/control/ownership totals.
- [confirmed] `compare_project_snapshots.py` performs complete relative-path
  inventory, stable reads, size/SHA-256 comparison, aligned byte-offset ranges,
  and parsed catalog, autoloop, scripted, Venue-cue, and TrackMap comparisons.
- [confirmed] Repeated no-change scans of frozen copies produced byte-identical
  comparator JSON and reported zero path changes.
- [confirmed] The operator created `CODEX MUTATION SCRATCH.ssproj`, but it had no
  fixture access. Its attempted AL-ADD comparison did not add or change a
  cataloged autoloop; instead it exposed a fixtureless, unsupported project
  layout. That run is invalid setup evidence, not AL-ADD mutation evidence.
- [confirmed] Merely opening `default.ssproj` caused SoundSwitch to rewrite
  `SoundSwitchVenues.bin.backup` to equal the current Venue bytes. The current
  `SoundSwitchVenues.bin`, catalogs, timelines, and parsed 232-cue semantics did
  not change.
- [confirmed, superseding the prior "no corpus" status] A valid fixture-bearing
  scratch duplicate, `~/Music/SoundSwitch/codex fixture research real.ssproj/`,
  was created and a full controlled authoring corpus was captured under
  `/tmp/soundswitch_finish_IiVlD1`. The supported Attribute-Cue identity/placement,
  scripted, and static-look mutations now have before/after snapshot+report
  evidence (see "2026-06-20 results" below and `soundswitch_stage3_handoff.md`
  Part C). The fixtureless `CODEX MUTATION SCRATCH.ssproj` runs remain invalid.

Accepted status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

## Identity and rescan rules under test

| Artifact | Candidate identity | Current evidence | Mutation evidence required |
| --- | --- | --- | --- |
| Autoloop | Catalog AppLog index plus catalog `file_number`; display name is mutable. | [confirmed] Both catalogs parse exactly and map index to `SSAutoLoop{index+1}.ssfile`. | [unknown] Add, rename, and remove diffs must prove index reuse/shift/tombstone behavior. |
| Scripted track | Normalized SSID across `{SSID}.ssfile`, TrackMap UUID, and exact audio tag when present. | [confirmed] 61/61 comparable tags agree; moved-file duplicates show path is a locator. | [unknown] New, edit, move, rename, clear/remove, and case-only behavior need controlled diffs. |
| Static look / Venue cue | Cue GUID; display name is mutable and sparse group patches are content. | [confirmed] 232 cue records parse by GUID/name/group/channel/value. | [unknown] Add, edit, rename, and remove behavior needs controlled diffs. |
| Source file | Project-relative path plus size and SHA-256 for integrity. | [confirmed] Full 100-file current inventory is deterministic. | [unknown] Which files change for each UI action requires the matrix. |
| Content hash | Integrity and diagnostic exact-content rename evidence only. | [confirmed] Hashes reproduce current sources/captures. | A hash must never replace SSID, catalog index, or cue GUID as authored identity. |

Modification time is never authoritative identity. A source that changes during
either scan fails closed. Added, removed, changed, unsupported, and opaque paths
must remain visible.

## Per-experiment procedure

Only an operator-created scratch/duplicate project may be changed. Never modify
`~/Music/SoundSwitch/default.ssproj/`.

1. Record SoundSwitch version, scratch-project path, exact single UI action,
   render-affecting expectation, and a falsifiable prediction.
2. Stop authoring and let project writes settle.
3. Freeze the complete before state to a new path outside
   `~/Music/SoundSwitch`:

   ```bash
   python3 tools/ssfmt/re/freeze_project_snapshot.py \
     <scratch.ssproj> <new-before-snapshot.ssproj> \
     > <new-before-manifest.json>
   ```

4. The operator performs exactly one requested UI action and stops. Codex does
   not manipulate the SoundSwitch UI.
5. After writes settle, freeze the complete after state to another new path.
6. Compare the two frozen copies with experiment metadata:

   ```bash
   python3 tools/ssfmt/re/compare_project_snapshots.py \
     <before-snapshot.ssproj> <after-snapshot.ssproj> \
     --metadata <experiment.json> \
     > <new-mutation-report.json>
   ```

7. Record every added, removed, and changed path; before/after size and SHA-256;
   aligned byte-offset ranges; parsed semantic differences; stable identity;
   and expected exporter add/replace/rename/remove action.
8. Request passive output evidence only when the mutation can change rendered
   CH1-CH19 behavior. That requires separate explicit approval and recorded
   confirmation that fixtures are disconnected or otherwise safe.

Required experiment metadata fields are `experiment_id`,
`soundswitch_version`, `scratch_project_path`, `exact_ui_action`, `prediction`,
and `render_affecting`.

## Mutation matrix

All predictions are falsifiable and currently [assumed] unless a row says
otherwise. Every execution status is [unknown] / not run.

| ID | One UI mutation | Predicted source consequence | Identity/export action to test | Passive capture? | Status |
| --- | --- | --- | --- | --- | --- |
| AL-ADD | Add one autoloop. | One catalog entry and one `SSAutoLoopN.ssfile` are added or activated; category tables may change. | New catalog identity produces exactly one pack addition; no stale removed artifact survives. | Yes, after separate safety approval: play two repeated cycles from known state. | [unknown] attempted in fixtureless scratch; invalid setup, not run successfully |
| AL-TIMELINE | Edit one existing autoloop timeline event. | Existing autoloop path remains; hash and timeline bytes change; identity remains stable. | Replace one artifact under the same catalog identity. | Yes, if rendered values/timing change. | [unknown] not run |
| AL-CONTROL | Edit one autoloop cue/effect/control property. | Autoloop, Venue, preset, or recordable/control source changes; the matrix must identify which. | Replace every affected semantic artifact; opaque render-affecting change blocks support. | Yes. | [unknown] not run |
| AL-RENAME | Rename one autoloop. | Catalog display name changes; file identity may remain stable. | Rename metadata without duplicate old-name artifact. | No unless SoundSwitch also changes rendering. | [unknown] not run |
| AL-REMOVE | Remove one autoloop. | Catalog entry/category table and possibly `.ssfile` path change or disappear. | Remove exactly the prior stable identity; do not retain stale pack content. | No. | [unknown] not run |
| ST-ADD | Add one scripted track. | New `{SSID}.ssfile`, TrackMap mapping, and possibly `.ssa` appear. | Add one SSID identity; path is locator only. | Yes, after separate safety approval. | [unknown] not run |
| ST-TIMELINE | Edit one scripted timeline event. | Same SSID file changes; TrackMap identity should remain. | Replace timeline under the same SSID. | Yes. | [unknown] not run |
| ST-CONTROL | Change one scripted cue/effect/control property. | Script, Venue, preset, or sidecar changes; exact owner must be isolated. | Replace known semantics or fail closed on opaque render-affecting state. | Yes. | [unknown] not run |
| ST-MOVE | Rename/move the source audio while preserving SSID. | TrackMap locator changes; `{SSID}.ssfile` identity remains. | Locator update only; no delete/add identity churn. | No unless lighting bytes change unexpectedly. | [unknown] not run |
| ST-REMOVE | Clear/remove one scripted track. | Mapping and/or `{SSID}.ssfile` is removed, cleared, or orphaned. | Remove or explicitly orphan the SSID; no fuzzy path recovery. | No. | [unknown] not run |
| VEN-ADD | Add one static look/Venue cue. | One new cue GUID/name/patch appears in current Venue. | Add one cue identity. | Yes, after separate safety approval: trigger twice from known state. | [unknown] not run |
| VEN-VALUES | Edit one static look's channel values. | Same cue GUID/name with changed sparse patch bytes. | Replace cue content under stable GUID. | Yes. | [unknown] not run |
| VEN-CONTROL | Edit one static look position/effect/control property. | Venue and possibly preset/control sources change. | Replace known referenced objects or fail closed if semantics remain unnamed. | Yes. | [unknown] not run |
| VEN-RENAME | Rename one static look. | Same cue GUID and patch with changed name. | Metadata rename only; no duplicate old-name cue. | No. | [unknown] not run |
| VEN-REMOVE | Remove one static look. | Cue GUID disappears or becomes an explicit tombstone/orphan. | Remove exactly that GUID and reject any remaining positive reference. | No. | [unknown] not run |
| FIX-ADDRESS | Change one fixture address/universe field. | Venue fixture-object bytes change; cue timelines should remain stable. | Replace explicit fixture routing; unknown mapping fails closed. | Yes only after separate hardware-safety approval. | [unknown] not run |
| FIX-GROUP | Change one fixture mirror/group-membership field. | Venue fixture/group topology bytes change. | Replace explicit routing/membership; never infer physical mirror behavior from names. | Yes only after separate hardware-safety approval. | [unknown] not run |
| PRESET | Change one automation preset value. | `.sspreset` and any referencing source may change. | Include only if render-affecting semantics decode; otherwise fail closed. | Only if a source reference or output effect is observed. | [unknown] not run |
| REANALYZE | Trigger track reanalysis with no authored-lighting edit. | `.ssa` changes while authored timeline/cue identity remains stable. | Treat analysis-only change as non-lighting input only after the diff proves isolation. | No initially. | [unknown] not run |

## Separate render actions requested by the operator

These are validation actions, not project mutations:

| ID | Action | Gate | Required evidence | Status |
| --- | --- | --- | --- | --- |
| RUN-AUTOLOOP | Play the newly created or edited autoloop. | Explicit per-run approval plus recorded fixture-disconnected/safe confirmation. | Passive pcap, copied AppLogs/bridge log, project hashes before/after, two cycles plus repeat, exact CH1-CH19 and separate timing residual. | [unknown] not authorized |
| RUN-STATIC | Trigger the newly created or edited static look. | Same explicit safety gate. | Known initial state, repeated trigger, exact sparse-patch result and timing. | [unknown] not authorized |

Creating, editing, renaming, clearing, or deleting content does not by itself
prove rendered output. Playing or triggering content does not by itself prove
how the project bytes encode the authoring mutation.

## Evidence acquired without a valid authoring mutation

- [confirmed] The AL-ADD frozen-before snapshot contained 136 regular files.
  Its attempted after state added `SoundSwitchTrackMap.bin` and
  `SoundSwitchVenues.bin.backup` and changed `SoundSwitchVenues.bin`, but added
  no catalog entry and no named autoloop file.
- [confirmed] Both fixtureless scratch states contained 128 autoloop files that
  fail the current-profile parser at byte 2,259. The comparator retains all 256
  unsupported occurrences and fails closed.
- [confirmed] Offline adversarial copies of the frozen evidence corpus prove
  that the comparator detects add/remove/replace/exact-content rename,
  case-only TrackMap relocation, catalog/file mismatches, unresolved positive
  references, missing current Venue cues, duplicate cue indices, fixture-profile
  mismatches, unsupported scripted layouts, opaque changes, and concurrent
  source mutation.
- [assumed] These synthetic cases validate the verifier's failure behavior, not
  SoundSwitch UI mutation semantics. They cannot close any matrix row.
- [unknown] A fixture-bearing duplicate suitable for controlled diffs has not
  been created. SoundSwitch's documented `Save Project As` flow is a candidate,
  but it is not authorized here because the prior open already rewrote a file
  in the real project directory.

## 2026-06-20 results (fixture-bearing scratch corpus)

Evidence dir: `/tmp/soundswitch_finish_IiVlD1`. Reference modes per provenance;
scripted legacy convention is wire-anchored, see
`docs/research/soundswitch_ssfile_format.md`.

| ID | Status | Evidence (snapshots/reports) |
| --- | --- | --- |
| AL-ADD | [confirmed] | `AL-ADD_after_candidate1/2`, `AL-ADD_final_report.json`; new autoloop emitted compact placeholder then standard layout; catalog identity 18 → `SSAutoLoop19.ssfile`. |
| AL-TIMELINE | [confirmed] | RED add `AL-TIMELINE_*`; BLUE add `AL-SECOND-CUE_*`; move `AL-MOVE-BLUE_*`; delete placement `AL-DELETE-PLACEMENT_*`; pre-roll `AL-PREROLL_*` (signed −86); post-roll `AL-POSTROLL_*` (19,271). 16-byte records; one record per placement. |
| AL-RENAME | [confirmed] | `AL-RENAME_*` → `CODEX AL-RENAME`, BREAKDOWN, 8 bars; name-only. |
| AL-REMOVE | [confirmed] | `AL-DELETE_*`; removed catalog identity 18 + `SSAutoLoop19.ssfile`; both catalog binaries rewritten. |
| ST-ADD | [confirmed] | `SCRIPT-CREATE_*` (Opalite); added only `{SSID}.ssfile`; TrackMap unchanged; new file uses DIRECT references. |
| ST-TIMELINE | [confirmed] | `SCRIPT-EDIT_*` (BLUE direct 22 @1875); **legacy-edit (Task 1):** A5 `84f6bf72→addd777d`, WHYB `1f740632→63302346` — edited legacy file becomes MIXED (old one-based + new direct), dict expands to full bank, pre-first-beat = elapsed 0. |
| ST-REMOVE | [confirmed] | `SCRIPT-CLEAR_*`; file + 233-entry dict preserved, timeline → 0 records, size 7,381, trailer 12×00 then 01. |
| VEN-ADD | [confirmed] | Attribute cue: `ATTR-CREATE_*` (GUID `3c411717…`), placed `ATTR-PLACE_*` (ref 233 @4200, propagated to `SSAutoLoop3.ssfile`). Static look: `STATIC-CREATE_*`/`STATIC-CREATE_SETTLED` (filled empty slot ordinal 3, name `CODEX STATIC 01`, +2 sparse group/ch-8 entries). |
| VEN-VALUES | [confirmed] | `STATIC-EDIT-BLUE_*`; two 4-byte values 10→24 for groups 0x493/0x496 only. |
| VEN-RENAME | [confirmed] | `ATTR-RENAME_*` → `CODEX ATTR RENAMED 01`; name only, GUID preserved. |
| VEN-REMOVE | [confirmed] | `ATTR-DELETE_*`; bank delete removed cue from every autoloop in the UI [operator-confirmed]; Venue identity removed; stale `.ssfile` dictionary/timeline residue remained until the autoloop itself was deleted — export must NOT resurrect stale references. |
| ST-MOVE | [confirmed] structurally | Moved-file duplicates show `{SSID}.ssfile` identity stable, path is locator only (TrackMap). |

### Excluded from declared supported scope (Task 3)

The product was narrowed to Attribute-Cue identity/placement; master intensity is
irrelevant. These rows are **excluded by scope**, not silently skipped, and the
full-rescan inventory must still report any change to them and fail closed if it
could affect a supported result:

- AL-CONTROL, ST-CONTROL, VEN-CONTROL (unrelated position/effect/control authoring);
- FIX-ADDRESS, FIX-GROUP (fixture address/group — supply via versioned external
  fixture-map input, never inferred from SoundSwitch);
- PRESET (automation presets);
- REANALYZE (`.ssa` track-analysis sidecars);
- master-intensity edits.

## Completion gate

This matrix is complete for the declared scope: every supported Attribute-Cue
identity/placement, scripted (create/edit/legacy-edit/clear), and static-look
(create/settle/edit) mutation has a before/after report with stable identity
behavior. The one material readiness caveat is that scripted/autoloop cue-
reference resolution is **provenance-dependent and not byte-deterministic** for
edited/mixed files (wire-proven for legacy scripted), so the exporter must fail
closed there. Unsupported layouts, opaque sidecars, unresolved references,
changing sources, and nondeterministic repeated runs remain visible and fail
closed.

Excluded-scope authoring mutations remain separately blocked on explicit per-run
approval. Scripted render/playback now has operator-gated multi-track and
seek/pause/loop/refire/stop/unload evidence, but the result does not clear this
gate: three representative tracks retain byte residuals and New Sky falsifies
universal CH8 persistence. The mutation matrix cannot promote those render
semantics to supported until the residual owner is decoded and recaptured.
