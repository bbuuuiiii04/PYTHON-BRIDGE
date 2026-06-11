# Composer Implementation Prompt — Section-Correct Autoloop Selection

## Context

Repo: `/Users/bbui/rb_ss_bridge_v2/`
This is a real-time Rekordbox → SoundSwitch laser show bridge. It runs live at EDM shows.
Wrong behavior is immediately visible to an audience. Implement exactly what is specified.
Do not add features, do not refactor beyond the spec, do not add comments the spec does
not include.

## Spec

Read the full implementation spec at:
```
/Users/bbui/rb_ss_bridge_v2/docs/plans/completed/autoloop_codex_spec.md
```

Part A is audit context. Part B (Tasks 1–10) is what you implement.

---

## Absolute Rules

1. **Follow the spec exactly.** Every change in Part B specifies current code and
   replacement code. Use those exact strings. Do not paraphrase or simplify.
2. **Do not modify any file not listed in the spec.** The spec names every file for
   every task. If you think a change is needed in an unlisted file, stop and report it
   instead of making the change.
3. **Do not add imports not already in the file** unless the spec explicitly shows them
   in the replacement code.
4. **Do not touch `smart_phrasing.py`, `os2l_output.py`, `osl_output.py`, or any test
   file** except as the spec says. Specifically: `tests/test_smart_drop.py` must pass
   without modification — the spec's Task 8a defaults (`or (lambda owner: None)`) ensure
   this.
5. **Do not change `PHRASE_ANCHOR_BEATS` or `os.phrase_anchor_last_beat` handling.**
   The OS2L 64-beat phrase anchor in `smart_rearm.py` is a separate system and must not
   be touched.
6. **Do not change `autoloop_master_phrase_arm` env parsing** in `__main__.py`. Task 9
   makes the flag inert at its callsite; the env-var wiring stays.
7. If any `file:line` reference in the spec does not match the current file (lines have
   shifted), find the matching code by the function name and the quoted "current code"
   snippet, not by line number. Line numbers in the spec are from audit date and may have
   drifted by ±5.

---

## Task Order

Implement in this order. Commit after each task.

1. Task 1 — `PlaylistCache` folder name (`__main__.py` + `config/laser_director.json`)
2. Task 2 — `_sp_phrase_lookahead` personality coupling (`state_manager.py`)
3. Task 3 — Executor owner-mask blackout API (`laser_executor.py`) — 5 sub-changes
4. Task 4 — `OutputState.midi_refire_origin_beat` + phrase-relative re-fire
   (`models.py` + `state_manager.py`) — 3 sub-changes
5. Task 5 — Director pending-latch on markers + breakdown end (`laser_director.py`)
6. Task 6 — Buildup window override (`laser_director.py`)
7. Task 7 — `same_scene_skip` pass-through (`laser_executor.py`)
8. Task 8 — Breakdown blackout (`smart_rearm.py` + `state_manager.py`) — 4 sub-changes,
   using the Task 8b correction above
9. Task 9 — Immediate master arm + mask (`state_manager.py` + `autoloop_controller.py`)
10. Task 10 — Phrase bank shuffle (`laser_executor.py`) — 4 sub-changes

Do not start Task 8 before Task 3 is committed.
Do not start Task 9 before Tasks 3 and 4 are committed.

---

## Commit Format

One commit per task. Message format:
```
feat(autoloop): Task N — <short description from spec>
```

Example: `feat(autoloop): Task 3 — executor owner-mask blackout API`

---

## If You Are Uncertain

Stop and report the specific line or method you cannot locate rather than making a best-
guess substitution. The spec is the authority. Do not resolve ambiguity by inventing code.
