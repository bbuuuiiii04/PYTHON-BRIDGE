---
doc_status: historical-evidence
truth_level: evidence-constrained-continuation
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: scratch-project authoring diffs and passive software evidence; hardware-unvalidated
---

# Codex Session Handoff — Finish SoundSwitch Reverse Engineering

> **Mission completed 2026-06-21.** Do not resume the operator campaign or the
> stale blocker list in this handoff. The bounded verdict is `RE COMPLETE`, and
> current findings include clean active Autoloops/scripts, exact Static Look
> slots, DDJ-800 mappings, learned-map save/load behavior, and stateless
> blackout/restore. See `soundswitch_re_closure_report.md`.

> **Current scripted-renderer closure handoff:**
> `docs/research/soundswitch/soundswitch_scripted_renderer_closure_handoff_spec.md`
> supersedes this file's older scripted-capture task ordering. Use this broader
> handoff for historical authoring/catalog context only where the closure spec
> explicitly routes to it.

Paste this entire file into a fresh Codex session opened at:

`/Users/bbui/rb_ss_bridge_v2`

Recommended configuration: use GPT-5.5 with Extra High reasoning if available.
If the session is restricted to GPT-5.3 Codex, use Extra High. This is a long,
agentic binary-research task; do not lower reasoning effort to Medium.

## Part A — Goal, operator protocol, and current truth

Continue the active goal without restarting the research:

> Finish all SoundSwitch reverse-engineering information required for the
> declared exporter/importer scope. SoundSwitch remains the authoring source;
> future export is a complete deterministic rescan of the named project. Do not
> build the production exporter, importer, renderer, output adapter, or bridge
> integration in this session.

The user narrowed the authored-lighting scope during the live experiments:

- [confirmed] Attribute Cue identity, creation, deletion, rename, and timeline
  placement are required.
- [confirmed] Placement before the first beat and beyond the final beat is
  required. In the autoloop editor there is no beatgrid before beat 1 or after
  the last beat, so the operator can place a cue outside the timeline but
  cannot place it exactly one beat before or exactly one beat after the grid.
- [confirmed] Master intensity is irrelevant to the requested product scope.
- [confirmed] Unrelated control-track/property experiments are excluded from
  the declared supported scope unless they are necessary to resolve Attribute
  Cue identity or placement.
- [confirmed] Static Look create/edit/trigger remains required as a separate
  SoundSwitch feature.
- [confirmed] Autoloop and scripted-track playback requires Rekordbox and the
  bridge. The bridge heavily controls autoloops over MIDI. If a later playback
  capture is genuinely required, the operator can hold the requested autoloop
  with a Rekordbox 32-beat loop; do not assume a single autoloop can otherwise
  remain selected.
- [confirmed] Static Look triggering does not require Rekordbox or the bridge.
- [operator-confirmed] Deleting an Attribute Cue from the bank removes it from
  every autoloop where it was used in the SoundSwitch UI. Saved `.ssfile`
  residue observed after deletion is a serialization detail, not evidence that
  the deleted cue remains actively placed.
- [operator-confirmed] The operator never edited `WIDE SPREAD ACCENT`. Any
  observed changes to that cue are unexplained incidental rewrites and must not
  be treated as a controlled payload-edit experiment.

### Non-interactive operator protocol

The user will perform operator commands but should not be expected to reply in
chat. Never stop at an operator gate waiting for a written response.

For every required operator action:

1. Post the exact instruction visibly in commentary, prefixed
   `OPERATOR ACTION:`.
2. Ping audibly with macOS `say` using the same instruction.
3. Request exactly one UI action at a time.
4. Establish the monitored file/hash baseline **before** invoking `say`; an
   earlier monitor missed a deletion because the operator acted during the
   spoken prompt before the baseline was captured.
5. Monitor the relevant project file or full-project signature until it changes
   and remains stable for at least 8-12 seconds.
6. Freeze the complete project to a new unique `/tmp` snapshot, compare it, and
   continue automatically.
7. If no change appears after roughly 90 seconds, repeat the visible and audible
   instruction. Silence is expected and is not a blocker.
8. If the user supplies a correction despite the no-reply protocol, trust the
   correction and reconcile it against the bytes.

Codex must never manipulate the SoundSwitch UI. All SoundSwitch UI work is
operator-owned.

Accepted project status remains:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

## Part B — Absolute rules and current workspace state

### Absolute safety

- Never deliberately modify `~/Music/SoundSwitch/default.ssproj/`.
- Never restore or substitute `SoundSwitchVenues.bin.backup`.
- Use only the valid fixture-bearing scratch project:
  `~/Music/SoundSwitch/codex fixture research real.ssproj/`.
- Do not use the corrupted earlier scratch projects.
- Never start, stop, restart, signal, or toggle the bridge.
- Never send MIDI, OS2L, Art-Net, serial, Enttec, or physical DMX.
- Never run `sudo tcpdump`.
- Never change root bridge runtime behavior, LED/Govee, laser, config, or
  unrelated tests.
- Do not request autoloop/scripted playback unless it is essential and a new
  explicit safe capture protocol has been established.
- Static Look triggering was explicitly operator-authorized and already tested;
  do not infer hardware validation from it.
- Never overwrite an oracle in `/tmp`; create a new uniquely named snapshot or
  report.
- Preserve all unrelated/staged user changes.

### Current Git state

At handoff time, the worktree contains intentional unstaged research/docs work
plus pre-existing staged capture-untracking changes. Re-run `git status --short`
before doing anything.

Pre-existing staged changes that must remain untouched:

- `A  tools/ssfmt/.gitignore`
- staged deletions under `tools/ssfmt/captures/**`; the capture files remain
  physically present and ignored. These are untracking changes, not permission
  to delete the physical evidence.

Current unstaged/untracked research work includes:

- `docs/agents/change_contracts.yml`
- `docs/architecture/doc_index.md`
- `docs/research/soundswitch/soundswitch_ssfile_format.md`
- `docs/research/soundswitch/soundswitch_stage2_research_findings.md`
- `docs/research/soundswitch/soundswitch_validation_matrix.md`
- `docs/research/soundswitch/soundswitch_stage3_handoff.md`
- `docs/research/soundswitch/soundswitch_decode_export_codex_spec.md`
- `docs/research/soundswitch/soundswitch_exporter_renderer_full_plan.md`
- `docs/research/soundswitch/soundswitch_authoring_mutation_matrix.md`
- `docs/status/active_work_registry.md`
- `docs/research/soundswitch/research_tools.md`
- `tools/ssfmt/re/analyze_ssfile_structure.py`
- `tools/ssfmt/re/analyze_scripted_ssfile.py`
- `tools/ssfmt/re/parse_venue_cues.py`
- `tools/ssfmt/re/analyze_static_looks.py`
- `tools/ssfmt/re/compare_project_snapshots.py`
- `tools/ssfmt/re/freeze_project_snapshot.py`

Do not reconstruct the absent
`docs/research/soundswitch/soundswitch_exporter_phase1_2_spec.md` blindly.

### Current live scratch state

- [confirmed] The current live scratch project is byte-identical to
  `/tmp/soundswitch_finish_IiVlD1/LEGACY-EDIT_after.ssproj` at handoff.
- [confirmed] The no-change report is
  `/tmp/soundswitch_finish_IiVlD1/pre_HANDOFF_live_check.json` and reports
  `has_changes: false`.
- [confirmed] The temporary research autoloop was deleted.
- [confirmed] The temporary global Attribute Cue was deleted.
- [confirmed] The Opalite scripted file remains present but has an empty
  timeline after `Clear Scripted Track`.
- [confirmed] Static Look slot ordinal 3 is named `CODEX STATIC 01` and remains
  in the scratch project with two group/channel-8 entries at value 24.
- [confirmed] `MEGA DROP` (`SSAutoLoop47.ssfile`) now contains one added RED
  pre-roll cue from the final compatibility experiment.
- [confirmed] SoundSwitch also normalized cue dictionary indices in
  `SSAutoLoop46.ssfile` and `SSAutoLoop47.ssfile` during that edit.

SoundSwitch was running during the original session. Re-check the process only
read-only if relevant; do not control it.

## Part C — Evidence already completed; do not repeat

All controlled evidence is under:

`/tmp/soundswitch_finish_IiVlD1`

### Reproduced baseline

- [confirmed] Current baseline directory:
  `/tmp/soundswitch_baseline_current_SCS2oe`.
- [confirmed] Baseline discrepancy report:
  `/tmp/soundswitch_baseline_current_SCS2oe/baseline_discrepancy_report.json`.
- [confirmed] Report SHA-256:
  `4e133835e13bd6f090d1e1f7266d444c206a8c77f5c0ddb95628792956097add`.
- [confirmed] 42/42 original autoloops structurally parsed.
- [confirmed] 44/45 original scripted files parsed/classified; In-App Demo is
  unsupported.
- [confirmed] Original Venue had 232 fixture-payload cue records; the extended
  parser now also recognizes the existing empty/minimal tail cue for 233 total
  Attribute Cue identities.
- [confirmed] Catalogs parse 18 + 24 records with exact EOF.
- [confirmed] TrackMap has 95 mappings, 71 IDs, 78 paths, and 61/61 comparable
  tag matches.
- [confirmed] A5 scripted passive capture is 16/16 exact: 14 positive events
  plus two raw-zero events.
- [confirmed] Autoloop pcap has 30,821 Universe-0 frames, 68 segments, 17 exact,
  51 unresolved, across 19 files.
- [confirmed] Full software suite previously ran 1,815 tests OK, 3 skipped, one
  expected failure. Re-run after final parser edits.

### Snapshot infrastructure

- [confirmed] `freeze_project_snapshot.py` refuses existing destinations,
  destinations inside the source, SoundSwitch project destinations, symlinks,
  and source races.
- [confirmed] `compare_project_snapshots.py` performs full inventory and stable
  reads; adversarial add/remove/change/rename/case-only relocation, broken
  references, profile mismatch, duplicate cue indices, unsupported layout,
  opaque change, source race, and deterministic no-change cases were exercised.
- [confirmed] Comparator timeline comparison now ignores serialization offsets
  and matches semantic records, preventing false churn after insertion.
- [confirmed] Comparator dictionary comparison keys by GUID, preventing false
  churn from GUID-sorted insertion.
- [confirmed] Comparator now parses Static Look slots and reports slot operations.

### Autoloop mutation sequence

Use these snapshots/reports rather than repeating UI actions:

- Seed: `fixture_research_real_seed.ssproj`.
- Add/finalize:
  `AL-ADD_after_candidate1.ssproj`, `AL-ADD_after_candidate2.ssproj`,
  `AL-ADD_final_report.json`.
- RED add: `AL-TIMELINE_after.ssproj`, `AL-TIMELINE_report.json`.
- Rename: `AL-RENAME_after.ssproj`, `AL-RENAME_report.json`.
- Add BLUE: `AL-SECOND-CUE_after.ssproj`,
  `AL-SECOND-CUE_file19_full.json`.
- Move BLUE: `AL-MOVE-BLUE_after.ssproj`,
  `AL-MOVE-BLUE_report_v2.json`.
- Delete BLUE placement: `AL-DELETE-PLACEMENT_after.ssproj`.
- Pre-roll: `AL-PREROLL_after.ssproj`, `AL-PREROLL_report_v2.json`.
- Post-roll: `AL-POSTROLL_after.ssproj`, `AL-POSTROLL_report.json`.
- Delete autoloop: `AL-DELETE_after.ssproj`, `AL-DELETE_report.json`.

Confirmed facts:

- [confirmed] New autoloop creation first emitted a compact placeholder, then
  finalized to the standard embedded-fixture layout.
- [confirmed] Catalog identity 18 pointed to `SSAutoLoop19.ssfile`; the final
  name was `CODEX AL-RENAME`, BREAKDOWN, 8 bars.
- [confirmed] New/current autoloop placements use direct dictionary references:
  RED raw/key 21, BLUE 22, GREEN 26.
- [confirmed] First placement stored at time 0 initially and normalized to 1
  after later editing while remaining visibly at the start.
- [confirmed] BLUE at the next beat stored at 601; its later move stored at 1800.
- [confirmed] BLUE outside the start boundary stored at signed time -86.
- [confirmed] GREEN outside the nominal 8-bar/19,200 boundary stored at 19,271.
- [operator-confirmed] Those autoloop positions are not exact one-beat offsets:
  SoundSwitch displays no beatgrid before the first beat or after the last beat.
- [confirmed] Timeline records are 16 bytes.
- [confirmed] Deleting a placement removed exactly one timeline record.
- [confirmed] Deleting the autoloop removed catalog identity 18 and
  `SSAutoLoop19.ssfile` and rewrote both catalog binaries.

### Timeline decoder corrections

- [confirmed] `decode_timeline_time()` at
  `tools/ssfmt/re/analyze_ssfile_structure.py:31` now sign-extends the full
  split 32-bit time. The old parser incorrectly collapsed every negative value
  to -1.
- [confirmed] Autoloop and scripted analyzers expose `direct`, `one_based`, and
  `ambiguous` reference modes at
  `tools/ssfmt/re/analyze_ssfile_structure.py:276` and
  `tools/ssfmt/re/analyze_scripted_ssfile.py:65`.
- [confirmed] The parser must never silently choose a reference convention when
  provenance is absent.

### Global Attribute Cue lifecycle

Snapshots/reports:

- `ATTR-CREATE_after.ssproj`, `ATTR-CREATE_report_v3.json`
- `ATTR-PLACE_after.ssproj`, `ATTR-PLACE_report_v2.json`
- `ATTR-RENAME_after.ssproj`, `ATTR-RENAME_report_v2.json`
- `ATTR-EDIT-BLUE_after.ssproj` (invalid controlled experiment; unexplained
  incidental Venue rewrite only)
- `ATTR-DELETE_pre.ssproj`, `ATTR-DELETE_after.ssproj`,
  `ATTR-DELETE_report.json`

Confirmed facts:

- [confirmed] Creating default/empty `CODEX ATTR CREATE 01` added one minimal
  Venue cue identity with GUID `3c4117179aaa3342a30952599c0cfa76`.
- [confirmed] Default/empty tail cue records use a minimal layout followed by a
  sequential catalog-index table. The previous tail cue is promoted to a full
  zero-entry fixture header when a newer cue is appended.
- [confirmed] `minimal_tail_cue_at()` decodes this at
  `tools/ssfmt/re/parse_venue_cues.py:90`.
- [confirmed] Placing the new cue grew the autoloop dictionary 233 -> 234,
  assigned cue/reference 233, and wrote its beat-8 placement at time 4200.
- [confirmed] The new dictionary GUID also propagated into
  `SSAutoLoop3.ssfile` despite no placement there. Full-project rescans are
  mandatory.
- [confirmed] Renaming to `CODEX ATTR RENAMED 01` changed only the name and
  preserved the GUID.
- [operator-confirmed] Deleting the global cue from the bank removed it from
  every autoloop where it was used in the SoundSwitch UI.
- [confirmed] The same save removed the cue's Venue identity but did not rewrite
  `SSAutoLoop19.ssfile`; its dictionary/timeline bytes remained dangling on
  disk until the autoloop itself was deleted. This is stale serialized residue,
  not an active UI placement.
- [confirmed] Export must resolve positive references against the current Venue
  and fail closed or omit a bank-deleted identity according to the final
  contract; it must never resurrect a stale `.ssfile` reference.
- [operator-confirmed] The operator never edited `WIDE SPREAD ACCENT`.
  `ATTR-EDIT-BLUE_after.ssproj` is therefore not a valid controlled payload
  mutation. Preserve its bytes only as evidence of an unexplained incidental
  Venue rewrite; do not attribute the change or later reversion to an operator
  action, the CODEX cue, or global cue deletion.

### Scripted-track lifecycle

Candidate track:

- Title: `Opalite (Chris Lake Remix)`
- SSID: `0D25CE82-B9FE-4929-9F1F-5066ADD3E2DB`
- Audio path:
  `/Users/bbui/Desktop/better songs/Chris Lake, Taylor Swift - Opalite (Chris Lake Remix).wav`

Snapshots/reports:

- `SCRIPT-CREATE_after.ssproj`, `SCRIPT-CREATE_full_direct.json`
- `SCRIPT-EDIT_after.ssproj`, `SCRIPT-EDIT_full_direct.json`
- `SCRIPT-CLEAR_after.ssproj`, `SCRIPT-CLEAR_full_direct.json`

Confirmed facts:

- [confirmed] Script creation added only `{SSID}.ssfile`; TrackMap was already
  present and did not change.
- [confirmed] Current SoundSwitch created the script with direct RED reference
  21 at elapsed 29.
- [confirmed] Adding BLUE wrote direct reference 22 at elapsed 1875 and appended
  one 16-byte record.
- [confirmed] `Clear Scripted Track` preserved the file and 233-entry dictionary
  and reduced the timeline to zero records; file size became 7,381 bytes.
- [confirmed] Current scripted trailer is twelve zero bytes followed by 01.

### Static Look lifecycle

Snapshots/reports:

- Before: `SCRIPT-CLEAR_after.ssproj`
- Intermediate name-only save: `STATIC-CREATE_after.ssproj`
- Settled create: `STATIC-CREATE_SETTLED.ssproj`
- Edit: `STATIC-EDIT-BLUE_after.ssproj`
- Comparator reports:
  `STATIC-CREATE_report_v2.json`,
  `STATIC-CREATE_SETTLE_report_v2.json`,
  `STATIC-EDIT-BLUE_report_v2.json`

Confirmed facts:

- [confirmed] Venue contains 14 observed Static Look slots.
- [confirmed] Create filled existing empty slot ordinal 3 by setting its name to
  `CODEX STATIC 01`; it did not add a new file or new slot.
- [confirmed] The slot covers fixture-instance IDs 9-13.
- [confirmed] All five instances carry position reference
  `96ef90c3ab5f3f45bb6fd84f60460e29`.
- [confirmed] Name creation was an intermediate +30-byte save; SoundSwitch later
  settled the look by adding two sparse group/channel-8 entries at value 10.
- [confirmed] Editing the look changed only those two four-byte values from 10
  to 24 for groups `0x493` and `0x496`.
- [confirmed] Triggering once produced no project-file change and no new AppLog
  line. The trigger was not independently machine-observable and remains
  operator-confirmed/hardware-unvalidated.
- [confirmed] Static Look grammar is decoded by
  `tools/ssfmt/re/analyze_static_looks.py:43`; comparator integration begins at
  `tools/ssfmt/re/compare_project_snapshots.py:653`.
- [confirmed] Static Look identity is the observed Venue slot ordinal; name is
  mutable. Slot deletion/reordering behavior was not required by the user and
  remains outside the declared scope.

### Critical legacy autoloop correction

Snapshots/reports:

- Before: `STATIC-EDIT-BLUE_after.ssproj/SSAutoLoop47.ssfile`
- After: `LEGACY-EDIT_after.ssproj/SSAutoLoop47.ssfile`
- Report: `LEGACY-EDIT_report.json`
- Direct-equivalence proof: `LEGACY-EDIT_direct_equivalence.json`

Confirmed facts:

- [confirmed] The old claim that autoloop positive references were one-based is
  false.
- [confirmed] Autoloop references are direct in both old and new evidence.
- [confirmed] Before edit, file 47 raw 3 selected dictionary key 3, GUID
  `9b5b1d84cefdb041886c7def04d494fa`; STROBE was key 2.
- [confirmed] SoundSwitch normalized the dictionary by swapping those keys and
  rewrote the same two events raw 3 -> raw 2, preserving the `9b5b…` GUID under
  direct lookup.
- [confirmed] All 70 pre-existing `(time, GUID)` records were preserved under
  direct lookup; exactly one RED record was added at time -76, raw/key 21.
- [confirmed] The direct-equivalence report has `before_count: 70`,
  `after_count: 71`, `preserved_direct_records: 70`, one RED addition, and no
  removals.
- [confirmed] This corrects the prior STROBE/CH11 residual interpretation. Raw 3
  did not select STROBE, so the observed CH11=227 was not an unexplained
  independent STROBE layer. Recompute the affected autoloop validation reports
  using direct lookup before retaining any CH11 fail gate.
- [confirmed] SoundSwitch also normalized the same two dictionary indices in
  `SSAutoLoop46.ssfile` during the file-47 edit. Again, rescan the whole project.

## Part D — Exact continuation tasks

### Task 1 — Run one final legacy scripted-track compatibility experiment

This is the next operator action. Do not skip it, and do not ask the operator to
reply.

This action is in the scripted-track editor. The operator's no-beatgrid
correction applies specifically to autoloop positions outside their bounded
timeline and does not establish that this scripted-track position is
unavailable.

1. Reconfirm the live scratch still matches
   `/tmp/soundswitch_finish_IiVlD1/LEGACY-EDIT_after.ssproj`.
2. Establish the target hash before the ping:
   `~/Music/SoundSwitch/codex fixture research real.ssproj/{A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF}.ssfile`.
3. Post and audibly speak:

   > OPERATOR ACTION: Edit the existing scripted track SANFRANDISCO (KING KOZZ
   > FLIP). Add the existing RED Attribute Cue exactly one beat before the first
   > beat. Do not move, delete, or change any existing cue or control. Then
   > select another track and save the scratch project.

4. Monitor until stable for at least 12 seconds.
5. Freeze to a new unique snapshot such as
   `/tmp/soundswitch_finish_IiVlD1/LEGACY-SCRIPT-EDIT_after.ssproj`.
6. Analyze A5 before and after in `one_based`, `direct`, and `ambiguous` modes.
7. Compare semantic `(elapsed, GUID)` multisets under both conventions.
8. Determine whether SoundSwitch:
   - preserves all legacy one-based records and adds a one-based RED record;
   - rewrites the file to direct references;
   - produces mixed conventions;
   - or changes the dictionary/reference relation in another deterministic way.
9. Cross-check against the existing 16/16 A5 wire proof. Do not discard that
   proof unless the bytes and capture jointly falsify it.

Current known boundary:

- [confirmed] Existing A5 capture resolves raw 91 to dictionary key 90 and is
  byte-exact on wire under one-based lookup.
- [confirmed] Newly created current-version scripted files use direct lookup.
- [unknown] How current SoundSwitch migrates an edited legacy scripted file.

This experiment is the last known operator-authored identity/placement gate.

### Task 2 — Correct parsers and regenerate affected reports

After Task 1:

- Make reference mode explicit per artifact/provenance. Do not leave
  `parse_autoloop_structure()` defaulting silently to an incorrect convention
  in final reports.
- Autoloops must use direct lookup for the observed corpus.
- Scripted files must use the convention proven by generation/migration
  evidence; unsupported ambiguity fails closed.
- Re-run `analyze_control_semantics.py`, coverage builders, layered renderer,
  and all reports that inherited the old one-based autoloop assumption.
- Re-evaluate the STROBE correction section and CH11=227 fail gate.
- Retain raw reference, both candidate indices, chosen rule, and provenance in
  diagnostics.
- Add focused tests for signed negative time (`-86`, `-76`), direct references,
  legacy scripted one-based references, semantic dictionary insertion, and
  Static Look slot parsing.

### Task 3 — Finish the declared mutation matrix

Mark the controlled rows complete with exact snapshot/report evidence:

- Autoloop add, timeline add/edit/move/delete, rename, remove.
- Attribute Cue create, place, rename, bank delete across every visible
  autoloop use, and stale serialized-reference behavior.
- Scripted create, timeline edit, clear.
- Static Look create, settled payload, edit, trigger persistence behavior.

Explicitly exclude the following from the declared supported scope because the
user narrowed the product to Attribute Cue identity/placement and said master
intensity is irrelevant:

- master-intensity edits;
- unrelated autoloop/scripted control tracks;
- unrelated position/effect/control authoring;
- fixture address/group mutation as an inferred product fact;
- automation preset mutation;
- track reanalysis sidecars.

The full-rescan inventory must still report changes to excluded or opaque
sources and fail closed if they could affect the supported result. Do not
silently ignore `.ssa`, `.sspreset`, `recordable/`, unknown Venue objects, or a
new file layout.

Use an explicit external bridge fixture map for physical universe/address,
membership, and mirror routing if production implementation proceeds. Do not
pretend those physical relationships were inferred from SoundSwitch.

### Task 4 — Update every required deliverable

Update the current `soundswitch_research` contract and all named documents:

- byte-layout reference;
- research findings;
- validation matrix;
- operator handoff;
- decode/export information contract;
- exporter/importer/renderer roadmap;
- authoring mutation matrix;
- AWR-107;
- research-tool README;
- explicit supported/unsupported scope.

Required corrections include:

- RED, never PURPLE, in the first new-autoloop experiment.
- Autoloops use direct references; remove the old universal one-based claim.
- Signed negative times are full 32-bit values, not all -1.
- Current new scripted files use direct references; legacy A5 is one-based until
  Task 1 proves migration behavior.
- Bank deletion visibly removes the cue from every autoloop, while saved
  `.ssfile` bytes may retain stale references that export must not resurrect.
- The operator never touched `WIDE SPREAD ACCENT`; exclude that incidental
  rewrite from controlled payload-mutation conclusions.
- Static Looks are Venue slot records, not Attribute Cue GUID records.
- Static trigger is runtime-only at observed storage/log surfaces.
- Master intensity/control-track experiments are excluded by product scope.
- Playback requires Rekordbox/bridge and bridge MIDI autorotation complicates a
  fixed-autoloop capture; a Rekordbox 32-beat loop is the operator workaround.

Do not mark production implementation ready if Task 1 leaves scripted reference
selection ambiguous. Exporter readiness and renderer readiness may be reported
separately.

### Task 5 — Validate and adversarially review

Run at minimum:

```bash
python3 -m py_compile tools/ssfmt/re/*.py
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Re-run every affected research parser/validator and record exact input hashes,
commands, and summaries. Repeat deterministic no-change scans.

Adversarial checks must include:

- current new direct autoloop references;
- edited legacy autoloop dictionary-index normalization;
- current new direct scripted references;
- edited legacy scripted behavior from Task 1;
- global cue deletion removing every visible use while leaving stale serialized
  residue;
- static slot create versus payload settle versus edit;
- source race;
- unsupported layout/profile;
- duplicate/case-only TrackMap locators;
- two identical scans producing deterministic output.

## Part E — Acceptance and finish report

Do not stop merely because the current corpus parses. Finish only when:

- every supported Attribute Cue identity/placement mutation has a controlled
  before/after result;
- autoloop and scripted reference conventions are deterministic or explicitly
  fail closed;
- negative and out-of-range placement is preserved without claiming exact
  beat offsets outside the autoloop beatgrid;
- creation, rename, removal, clear, visible bank-deletion behavior, and stale
  serialized-reference behavior are defined separately;
- Static Look slot identity/content is defined for the observed grammar;
- excluded scope is explicit rather than silently omitted;
- full-project inventory and source-race behavior remain fail closed;
- all required docs and checks pass;
- no staged/unrelated user change was disturbed.

When finished, report:

1. Newly confirmed information.
2. Corrected prior claims.
3. Completed mutation matrix.
4. Supported and unsupported structures.
5. Remaining unknowns and the exact experiment for each.
6. Exporter readiness and importer/renderer readiness separately.
7. Every changed file.
8. Every parser, validator, test, and docs check run.
9. Any operator action still required.
10. Plain-language operator summary: what changed only in the scratch project,
    what remains unchanged live, healthy behavior/watchpoints, what was
    software-verified, what remains hardware-unvalidated, and exact approval
    gates before playback captures, restarts, toggles, or hardware checks.

Do not mark hardware validation. Do not restart the bridge. Do not touch the
real SoundSwitch project. Do not wait for the user to type after an operator
ping.

## Session completion (2026-06-20)

Task 1 executed via TWO operator-authored legacy scripted-edit experiments
(SANFRANDISCO/A5 `84f6bf72→addd777d`; "Where Have You Been" `528E8B22`
`1f740632→63302346`; evidence `/tmp/soundswitch_finish_IiVlD1`). Outcome and
its corrections to Tasks 2–4 are now landed in the canonical docs.

**Pivotal correction.** Cue-reference resolution is provenance-dependent and NOT
byte-deterministic:
- Legacy scripted = ONE-BASED — wire-proven (A5 Art-Net 14/14 exact).
- Newly created (current SoundSwitch) = DIRECT.
- Editing a legacy file = MIXED (old one-based + new direct, no disambiguator:
  version 3, `field_a=field_b=1`, elapsed-sorted); dictionary expands to the full
  current bank and re-normalizes.
- Pre-first-beat scripted placement stores `elapsed = 0` (grid starts >0), not a
  negative tick. There is no beat before the first beat in either editor.
- Autoloops follow the IDENTICAL convention, now WIRE-PROVEN: legacy autoloops =
  one-based (new operator-gated capture `autoloop_probe.pcap`; one-based cue
  states appear on the wire 17× vs direct 4×, SSAutoLoop50/52/53 byte-exact under
  one-based and 0 under direct). The prior "autoloops are direct" claim was a
  self-consistency artifact and is withdrawn. CH11=227 is reclassified as a
  separate render-layer unknown, no longer a convention question.

Parsers now default to `ambiguous` (never silently assert a convention); internal
callers pass explicit provisional `one_based`; convention math is regression-
tested by `tests/test_ssfile_reference_convention.py`. Full suite: 1836 OK / 3
skipped / 1 expected failure. Hard doc checks pass.

**Autoloop convention RESOLVED (2026-06-20):** the operator-gated capture was run
(fixtures confirmed safe) and wire-proved legacy autoloops one-based. The cue
reference convention is now fully characterized for both scripted and autoloop
files. **Remaining non-convention unknowns:** CH11=227 render-layer semantics,
position-animation render model, deck ownership, and the other items in the
validation matrix's fail gates. Exporter readiness is blocked on deterministic
reference resolution for mixed/edited files (must fail closed) and remains
deferred / hardware-unvalidated.

**Scripted renderer follow-up (2026-06-20):**
`layered_renderer.render_at_elapsed` and `render_playback_state` provide pure,
explicit-provenance position/transport seams. Operator-gated captures now exist
for FC10FC02, 74044FA4, AE9E3C61, and a dedicated 74044FA4 transport run. They
falsify completion: event samples are 16/64, 23/39, and 304/367 exact, and New
Sky clears CH8 across a decoded CH15-only record instead of persisting it.
Transport reconstruction is exact on representative backward/forward seek,
22/22 loop, and playing re-fire samples; 2/2 confirmed stops clear to zero. One
seek/pause interval retains the same base-render residual observed in continuous
playback, and unload leaves stale bridge filename/mode. Canonical evidence:
`/tmp/ss_scripted_validation_summary_20260620.json`. Archived
`WHYB-AFTER.ssproj` (`63302346…`) remains the MIXED negative control and is
rejected before rendering.
