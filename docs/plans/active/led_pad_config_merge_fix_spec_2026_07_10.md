---
doc_status: current
truth_level: implementation spec (LED Pad commit clobber fix; executive seat authored)
last_verified_commit: 66034e7
last_verified_date: 2026-07-10
validation_scope: >
  Fix for the operator-reported LED Pad config data-loss bug, which FIRED live on
  2026-07-10 at 14:29: a pad commit overwrote the live config with a stale draft,
  destroying the f2 block (operator-restored since), the f4 / cfx_sweep /
  drop_presentation / scripted_mode / blank_role_hold blocks, 17 looks, and six
  loop_beats params. Root cause verified at the executive desk. Staged/tooling
  only; nothing here restarts or contacts the running bridge.
---

# Implementation Spec - LED Pad commit must merge, never overwrite (config data loss)

## Part A - Context & Root Cause (verified; read, do not implement)

**The incident [confirmed].** `tools/led_pad_web.py` `LedPadService.commit()`
(line ~891) writes `self._draft` WHOLESALE over the live config
(`config/led_look_director.json`, gitignored) via `save_config_atomically`. The
draft is loaded once at server start (`_load_initial_draft`, line ~321) from
`led_look_director.draft.json` if present - which can be arbitrarily stale. On
2026-07-10 14:29:43 the operator's pad commit wrote a pre-overnight draft over the
live config: the backup pair proves it -
`config/led_look_director.json.bak-20260710-142943-810747` (good pre-clobber state,
89 looks, has `f2`/`f4`/`cfx_sweep`/`drop_presentation`/`scripted_mode`/
`blank_role_hold` and six `loop_beats` params) vs the post-commit live file
(72 looks, none of those blocks). The operator lost real work. There is a
`live_changed` staleness flag in `get_config_payload()` (line ~423) but nothing
blocks or merges at commit time.

**What the pad actually manages [confirmed by reading every mutator]:**
`save_look` / `duplicate_look` / `move_look` / `delete_look` / lab endpoints touch
ONLY: entries inside `looks`, role lists inside `banks.default`, `_pad_meta`, and
the three per-look maps inside `color_engine`
(`slot_fill_strategy_by_look`, `slot_mono_chance_by_look`,
`locked_palette_by_look`). Every other top-level block (`f2`, `f4`, `cfx_sweep`,
`drop_presentation`, `scripted_mode`, `blank_role_hold`, `automation`, `safety`,
`rate_limits`, `targets`, `drop_pairs`, `realtime_param_profiles`, palettes inside
`color_engine`, and any FUTURE block) is read-only context for the pad - yet
commit() currently overwrites all of it with the draft's stale copy.

## Part B - Requirements (design the mechanics yourself; requirements are pinned)

Scope: `tools/led_pad_web.py` + its tests (`tests/test_led_pad_service.py`,
`tests/test_led_pad_lab.py` if lab save paths are affected) + Part E docs. Nothing
else. Do not modify the live config or any backup as part of this work (tests use
tmp dirs). The pad server on :8766 stays running; do NOT restart it (the operator
activates restarts).

1. **Commit becomes read-modify-merge.** At commit time, load the CURRENT live
   config fresh from disk and produce the merged result:
   - Top-level blocks the pad does not manage: taken from LIVE, always -
     including blocks the pad has never heard of (iterate live's keys; never
     enumerate a hardcoded allowlist of "known unknown" names).
   - `looks`: start from LIVE looks; apply only the looks this pad session
     actually touched (edited/created/duplicated), and apply deletions only for
     looks explicitly deleted through the pad. Untouched looks that exist only in
     live (e.g. added by another tool since the draft was created) MUST survive.
     You will need to track touched/deleted names (e.g. in `_pad_meta` or a
     service-level set persisted with the draft) - design this; make it survive a
     pad-server restart mid-session (the draft file already persists).
   - `banks.default` role lists: same principle - preserve live entries for looks
     the pad didn't move/delete; apply the pad's moves/removals/additions.
   - `color_engine`: merge only the three per-look maps (per touched look);
     everything else in `color_engine` comes from live.
   - `_pad_meta`: pad-owned, written from the draft.
2. **The draft rebases after commit** so the next commit doesn't re-apply history:
   post-commit, draft = merged result; touched/deleted tracking clears; the base
   fingerprint refreshes (existing `_write_draft_base`).
3. **Validation still gates:** the MERGED config (not the raw draft) must pass
   `load_led_look_director_config_from_dict` before writing; on errors return
   them and write nothing.
4. **The backup behavior stays** (pre-write `.bak-*` copy) - it is what saved the
   operator today.
5. **Regression tests (minimum):**
   - Unknown top-level block preservation: seed a live config containing `f2`,
     `f4`, and a made-up future block `zz_future`; start a pad service whose
     draft predates them; edit one look through the pad API; commit; assert all
     three blocks are present and byte-equal in the result (F2/F4 present before
     == present after).
   - Untouched-look preservation: live gains a look the draft doesn't have;
     pad edits a different look; commit; assert the new live look survives with
     its params.
   - Deletion still works: delete a look via the pad; commit; assert it is gone
     from the result (and from banks) while unrelated live state survives.
   - Stale-draft params: live look has params the draft's copy lacks; the pad did
     NOT touch that look; commit; assert live params survive.
6. **No behavior change** to play/preview/lab rendering paths, ownership/takeover,
   or the HTTP surface beyond what the merge requires. `discard` keeps its
   semantics (re-derive draft from live).

Error handling: no broad try/except, no success-shaped fallbacks; a merge that
cannot be computed safely must surface an error to the UI and write NOTHING.

## Part C - Invariants That MUST Still Hold
- The live config file is written only by an explicit operator commit through the
  pad (plus the atomic temp-file mechanics already present). No background writes.
- STOP-look guards (`_guard_mutable`) and drop-pair reference guards unchanged.
- The pad never invents or renames top-level schema; schema_version passes through
  from live.
- Nothing contacts the running bridge; :8766 server not restarted by you.

## Part D - Tests
- All new tests pure/tmp-dir (the existing test files already use tmp config
  paths - follow their harness).
- Scoped: `python3 -m unittest tests.test_led_pad_service tests.test_led_pad_lab
  tests.test_led_pad_controls` green from repo root.
- Full discover + hard checks (`tools/check_docs_metadata.py`,
  `check_agent_contracts.py`, `check_docs_drift.py`) - reconcile reds BY NAME;
  known pre-existing reds (do not chase): patch_b/c/d config-validation reds,
  export_pack_parity_self_heal x2, laser_player golden slot=16, parity_oracle
  capture_rows, pack byte-identity flappers (isolate; green in isolation =
  baseline).

## Part E - Acceptance
- [ ] Requirements 1-6 implemented; regression tests green; scoped + discover
  reconciled; hard checks green.
- [ ] Contract `led_pad` docs_update honored: `docs/guides/led_pad.md` (commit
  semantics paragraph), `docs/subsystems/led_govee.md` if it describes pad
  commit, `docs/status/active_work_registry.md` (fresh-read, take the next free
  AWR id - max was AWR-200 at spec authoring, re-check; note another concurrent
  round may take AWR-201).
- [ ] Commits by EXPLICIT PATHS only (auto-sync hook sweeps `-a`), message prefix
  `LEDPAD-MERGE:`. Never `git commit -a`. No branches.
- [ ] Concurrent-lane fence - do NOT touch: `packaging/make_stick.sh`,
  `install_controller.py`, `enttec_dmx_pro.py`, `usb_launcher.py`, `__main__.py`,
  `govee_realtime_runner.py`, `beat_sync_engine.py`, `led_look_director.py`,
  `led_dispatch_policy.py`, `led_models.py`, `lighting_moments_v2.py`, and their
  tests - other lanes own them right now.
- [ ] STAGED ONLY; plain-language operator line in your report: "saving a look in
  the pad now only writes what you actually changed - everything else in your
  live lighting config (F2, F4, looks added by other tools) survives a pad save
  untouched."
