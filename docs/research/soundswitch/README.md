---
doc_status: research-current
truth_level: repository-routing-authority
last_verified_commit: 03af947
last_verified_date: 2026-07-01
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

1. `soundswitch_truth_exam_live_blockers_2026_07_02.md` and
   `soundswitch_time_domain_exam_2026_07.md` — current post-exam evidence for
   SoundSwitch perfect-parity work: official comparator invalidity, diagnostic
   byte/timing disagreements, offline timing outliers, source divergence, and
   coverage gaps.
2. `../../prompts/active/soundswitch_truth_exam_fable_fix_prompt.md` — current
   one-shot Fable handoff that turns this evidence into a Codex-executable
   perfect-parity fix spec.
3. `../../plans/active/soundswitch_exporter_remaining_work.md` — current landed
   implementation status, confirmed gaps, checklist, dependencies, and next
   design/spec task.
4. `soundswitch_re_closure_report.md` — bounded reverse-engineering verdict and
   supported source-format boundary. It is not current implementation status,
   and its broad active-scripted exact-parity implication is superseded by
   `../../plans/active/soundswitch_pack_parity_root_cause_spec.md`.
5. `../../plans/active/soundswitch_pack_parity_root_cause_spec.md` — baseline
   DD42028C/global cue-parity root-cause context. It records the callable
   GhidraMCP pass, the rejected footer/global-offset theories, and the
   fail-closed/oracle requirements for active scripted documents, but it is not
   the current post-exam fix scope.
6. `soundswitch_ssfile_format.md` — physical project, catalog, `.ssfile`,
   MIDI-map, and static-look formats.
7. `soundswitch_ghidra_addendum.md` — binary-derived reader/writer and runtime
   behavior.
8. `soundswitch_validation_matrix.md` and
   `soundswitch_authoring_mutation_matrix.md` — capture and mutation evidence.
9. `research_tools.md` — reproduction commands and tool inventory.
10. `soundswitch_importer_exporter_player_codex_spec.md` — original authorized
   default-off product/implementation contract.

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
