---
doc_status: current
truth_level: dispatch-brief
last_verified_commit: 8a90796
last_verified_date: 2026-07-09
validation_scope: >
  Implementer dispatch for the AWR-176 build round (P1 growl-band centroid,
  executive-approved spec). Opus lane p1impl, TAG P1IMPL. Retire when the round
  closes.
---

# AWR-176 implementer dispatch — P1 growl-band centroid (lane p1impl)

You are the IMPLEMENTER for AWR-176. Your spec is
`docs/plans/active/spectral_growl_centroid_p1_spec.md` — **read it FULLY first**
and implement its Part B Tasks 1–5 exactly, in order, one commit per task, by
EXPLICIT paths (never `git add -a`, never `-A`).

## Ground truth, pinned
- Spec cites were verified at `d93f047`; the four target code files are
  UNCHANGED through `8a90796` (checked by the manager at dispatch time). The
  tree moves constantly (auto-sync + parallel lanes): verify every cite at YOUR
  HEAD immediately before using it, and record `git log -1 --format='%h'` in
  your report as your working pin.
- The worktree may be DIRTY with other lanes' files (right now at least
  `govee_frame_renderer.py`, `tools/govee_manual_trigger.py`,
  `docs/agents/change_contracts.yml` carry other lanes' edits). Never revert,
  stash, clean, or commit files outside your fence; `git clean` of ANY form is
  banned repo-wide.

## File fence (touch ONLY these)
- `audio_spectral_features.py` (Task 1)
- `spectral_cache.py` (Task 2)
- `spectral_profile.py` (Task 3)
- `tools/spectral_sweep.py` (Task 4)
- `tests/test_growl_centroid.py` — NEW file; put ALL Part D tests here (do not
  edit the existing shared test files)
- Task 5 docs only: `docs/agents/change_contracts.yml` (additive key_symbols —
  this file is mid-edit by another lane: re-read it fresh IMMEDIATELY before
  your edit, change only the `spectral_analysis` block, commit by explicit
  path), `docs/research/spectral_audio_analysis_redesign.md` (the :960-973
  App-E note gains the landed pointer + one schema row),
  `docs/status/active_work_registry.md` (edit ONLY the AWR-176 row; re-read
  fresh immediately before editing). `AGENTS.md` is VERIFY-ONLY — confirm no
  edit is needed and say so in your report.
- `docs/architecture/doc_index.md` already has the AWR-176 row — do not touch.

## Live safety (this round)
- Do NOT run `tools/spectral_sweep.py` against the real library and do NOT
  touch `~/Library/Application Support/RBSS Bridge/spectral_cache/` in any way.
  All cache tests run under a `RBSS_SPECTRAL_CACHE_DIR` tmpdir (the
  `tests/test_spectral_cache.py` pattern). The overnight backfill sweep is
  staged by the manager, run after 20:00 by the executive's schedule — not you.
- No bridge start/stop/restart, no live config reads or writes, no
  `python3 -m rb_ss_bridge_v2`.
- The registry row edit states the round's TRUE state: "IMPLEMENTED (evidence:
  commits + test names) — awaiting manager adversarial review + executive
  gate". You do not write "software-tested" as a settled status — the review
  chain above you settles it.

## Acceptance (evidence, not adjectives)
1. Per task: the scoped tests you ran, by name, with pass counts.
2. New `tests/test_growl_centroid.py` green, all 10 Part D items covered
   (item 9's extraction test skips cleanly when librosa is absent — mirror
   `tests/test_audio_spectral_features.py`'s guard).
3. Scoped modules green: `python3 -m unittest tests.test_spectral_profile
   tests.test_spectral_cache tests.test_audio_spectral_features
   tests.test_lighting_moments_v2 tests.test_growl_centroid` (the first four
   prove no regression in neighbors you did not touch).
4. FULL suite from REPO ROOT (`python3 -m unittest discover tests`),
   reconciled BY NAME. Expected reds — names, not counts:
   - `test_drop_slot_color_smoke_and_snap` (error)
   - `test_export_pack_parity_self_heal` (both fails)
   - `test_ddj_slots_8_16_17_24_exact_ch1_ch19`
   - `test_autoloop_capture_rows_identify_passes_and_blockers`
   - `test_laser_color_engine.LaserColorStateManagerHoldTests` currently shows
     5 ERRORs at HEAD; ANOTHER LANE is fixing them mid-day (`b1f360c` is part
     of that work). Report their presence or absence by name and do NOT chase
     them either way — they are not yours.
   - Known load-flappers (`test_fallback_second_rename_failure_restores_old_pack`,
     the two `test_soundswitch_pack` byte-identity race tests): if red in the
     full run, re-run in isolation; green-in-isolation = baseline, report it
     that way.
   Anything else red = reproduce in isolation, report the name + output, and
   if it traces to your diff, fix before proceeding; if it does not, STOP and
   write the .blocked signal with the evidence.
5. Three hard checks green after Task 5: `python3 tools/check_docs_metadata.py`,
   `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.

## The four clauses (verbatim, in force)
- You report evidence; the manager reviews; the executive gates. You never
  declare the round shipped.
- Do not pause at checkpoints for acknowledgment; run straight through unless
  genuinely blocked.
- If reality diverges from the spec (unknown name, missing file, unexpected
  state): STOP, write the .blocked signal with one line of evidence, and wait.
  Blocking is a success mode; invention is the failure mode.
- Touch ONLY spec-listed files; an improvement you notice = a NOTE in your
  report, never an edit.

## Report format (final message)
Working pin; per-task commit hashes + one-line summaries; test evidence per
acceptance item (names + counts); full-suite red names reconciled against the
list above; hard-check output; any NOTEs; explicit statement that the sweep
was NOT run and the real cache was NOT touched.
