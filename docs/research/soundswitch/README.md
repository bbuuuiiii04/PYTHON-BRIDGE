---
doc_status: research-current
truth_level: repository-routing-authority
last_verified_commit: b2ce63d
last_verified_date: 2026-06-23
validation_scope: SoundSwitch reverse-engineering document routing; software evidence only; hardware-unvalidated
---

# SoundSwitch reverse-engineering authority

All current SoundSwitch reverse-engineering authority and evidence matrices are
grouped in this directory. Superseded handoffs, intermediate findings, and draft
specifications are physically separated under `history/`. Do not create another
SoundSwitch RE document elsewhere. Runtime
SoundSwitch/OS2L behavior remains documented in
`docs/subsystems/soundswitch_output.md`; repository-wide routing remains in the
doc index and active-work registry.

Read in this order:

1. `soundswitch_re_closure_report.md` — bounded reverse-engineering verdict and
   supported source-format boundary. It is not current implementation status.
2. `soundswitch_ssfile_format.md` — physical project, catalog, `.ssfile`,
   MIDI-map, and static-look formats.
3. `soundswitch_ghidra_addendum.md` — binary-derived reader/writer and runtime
   behavior.
4. `soundswitch_validation_matrix.md` and
   `soundswitch_authoring_mutation_matrix.md` — capture and mutation evidence.
5. `research_tools.md` — reproduction commands and tool inventory.
6. `soundswitch_importer_exporter_player_codex_spec.md` — original authorized
   default-off product/implementation contract.
7. `../../plans/active/soundswitch_exporter_remaining_work.md` — current landed
   implementation status, confirmed gaps, checklist, dependencies, and next
   design/spec task.

Historical research artifacts are indexed in `history/README.md`. Their old
readiness statements are superseded by the closure report for research truth and
by the active remaining-work roadmap for implementation status.

Current control-surface facts that every future exporter must preserve:

- newly created, edited, renamed, and deleted autoloops are discovered by a
  complete project rescan; identity is catalog index/file number, never display
  name;
- learned MIDI mappings are decoded from the version-1
  `NamedControlMapCollections` recordable and rescanned on every export;
- channel-2 safe/transition/emergency bridge scenes are intentionally not
  learned in the current SoundSwitch project and are not missing-project
  errors;
- four DDJ-800 mappings select primary Venue static-look slots 8, 16, 17, and
  24; those static looks and their CH1-CH19 values are required pack inputs.

Accepted status remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.
