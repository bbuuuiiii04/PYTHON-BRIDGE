---
doc_status: active-plan
truth_level: code-and-test-grounded
last_verified_commit: 2e347e8
last_verified_date: 2026-06-25
validation_scope: Codex review + revisions for the publish_pack binding-sidecar atomicity change, the AWR-107 independent software/wire review, and docs-staleness bookkeeping; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — publish_pack sidecar review, independent software/wire review, docs-staleness bookkeeping

You are Codex, implementing on `rb_ss_bridge_v2`. This handoff has **both review and
implement phases**. Do the tasks in order and commit after each. Code and tests win
over any doc. Work directly on `main`; do **not** create branches or worktrees.

This is exporter/menubar/docs work. The exporter is an on-demand tool, but the
canonical pack it publishes is what the runtime loads — so the live-safety
invariants in Part C are non-negotiable.

## Part A — Context & root cause (verified; read, do not implement yet)

Claude just landed a fix and re-ran the pack proof. Your job is to review that fix
adversarially, implement any needed revisions, run the standing independent
software/wire review of the SoundSwitch exporter/player, and clear the
docs-staleness flags honestly.

### A1. The change under review (publish_pack sidecar atomicity)
- [confirmed] HEAD `2e347e8` made the Stream Deck MIDI binding sidecar a **required**
  export artifact (`BindingSidecarWriteError`, verdict `sidecar_failed`).
- [confirmed] Before Claude's fix, `publish_pack` wrote the required sidecar **after**
  the canonical pack swap with **no rollback**, so a sidecar-write failure could leave
  a live new pack with a missing/old sidecar while returning `sidecar_failed`; on a
  re-export the prior good pack was already gone. `export_pack` was already all-or-nothing
  (it `rmtree`s the destination on sidecar failure), so the two paths were asymmetric.
- [confirmed] Claude's fix (working tree / latest `main` commit touching the exporter):
  - `tools/export_soundswitch_pack.py:142` `_binding_sidecar_rows(decoded)` — extracted
    pure row-builder (was inlined in `_write_binding_sidecar`).
  - `tools/export_soundswitch_pack.py:161` `_write_binding_sidecar` — now just
    `_atomic_write_result(_binding_sidecar_path(destination), _binding_sidecar_rows(decoded))`.
    The `export_pack` path is unchanged in behavior (`_write_required_binding_sidecar`
    → `_write_binding_sidecar`, rollback `rmtree(destination)`).
  - `tools/export_soundswitch_pack.py:172` `_stage_binding_sidecar(parent, name, decoded)`
    — produces + durably writes the sidecar to a `.{name}.tmp-…` **sibling** temp
    (matches `_gc_orphan_staging`'s glob), returns the temp `Path`; raises
    `BindingSidecarWriteError` on any produce/write failure.
  - `tools/export_soundswitch_pack.py:427` `publish_pack` — stages the sidecar **before**
    the swap (`:452`), swaps, then promotes with one rename `os.replace(staged_sidecar,
    _binding_sidecar_path(destination))` (`:466`). On swap failure it unlinks the staged
    temp and raises `PackSwapError`; on a post-swap promote failure it unlinks the temp
    and raises `BindingSidecarWriteError`.
- [confirmed] Tests: `tests/test_soundswitch_pack.py:864`
  `test_sidecar_failure_before_swap_preserves_prior_pack` (new);
  `:1210` `test_canonical_publish_binding_sidecar_failure_is_visible` repointed its
  injection seam from `_write_binding_sidecar` to the shared `_binding_sidecar_rows`
  (same intent: failure → `ok=False`, verdict `sidecar_failed`, source sidecar not called).
- [confirmed] At handoff: full suite `2399 OK` (3 skipped, 1 expected failure);
  `check_docs_metadata` / `check_agent_contracts` / `check_docs_drift` pass;
  `git diff --check` clean; `prove_soundswitch_pack_generation.py` against
  `~/Music/SoundSwitch/default.ssproj` = `PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0
  (foundation 27/27).
- [confirmed] Known residual to evaluate: across two filesystem objects (pack dir +
  sidecar sibling) there is no single atomic rename, so a failure of the *post-swap
  promote rename itself* still yields new-pack + old/absent-sidecar + verdict
  `sidecar_failed`. Claude judged this negligible (rename of an already-durable file in
  the same dir) and fail-safe (runtime degrades manual static, pack DMX unaffected).
  You must independently confirm or challenge that judgement.

### A2. The standing independent review (AWR-107 item #1)
- [confirmed] `docs/plans/active/soundswitch_exporter_remaining_work.md:91-102` requires an
  independent software/wire review of the SoundSwitch exporter/player against the pushed
  commit range, conclusions bounded to software/wire evidence.
- [confirmed] The existing review-only handoff
  `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`
  defines the hard boundary and source order to reuse. Its commit range is older; for
  this pass the range is current `main`.

### A3. The staleness bookkeeping
- [confirmed] `python3 tools/check_docs_staleness.py --report` flags two contracts STALE
  vs the global baseline `docs/agents/change_contracts.yml:5` `last_verified_commit: 2ed93f3`:
  `core_bridge` (state_manager.py changed) and `soundswitch_pack_player` (8 files changed
  by the static-overlay + binding-sidecar commits). `last_verified_commit` is a **single
  global field** (line 5), so bumping it marks all contracts fresh — only honest after the
  flagged docs are re-verified.
- [confirmed] The SoundSwitch status docs still carry stale frontmatter
  `last_verified_commit`: `soundswitch_exporter_remaining_work.md` and `soundswitch_README.md`
  (`e17733b`), `active_work_registry.md` / `feature_status_matrix.md` /
  `validation_matrix.md` (`e17733b`).

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **No runtime behavior change.** Do not alter the 200 Hz push loop, `_drive_pack_output`,
  the safe-zero/blackout/emergency precedence, the `select_autoloop`-never-called property,
  or the default-off config. Do not touch T7d, autoloop phase derivation, or native
  Autoloop DMX. Those stay exactly as they are.
- **No live/hardware actions.** No bridge start/stop/restart, no process inspection, no live
  config read/edit, no menubar runtime actions, no MIDI/serial/Enttec/DMX open, no fixtures.
  All tests use fake/injected interfaces.
- **Do not weaken or delete tests to make anything pass.** Repointing an injection seam to
  match a refactor is allowed only when the assertion intent is preserved.
- Out-of-scope files: everything not named in a task. In particular do not edit
  `state_manager.py`, `soundswitch_laser_player.py`, or `soundswitch_midi_input.py` unless a
  Task-1/Task-3 **blocker** finding requires it and you justify it in the commit.

### Task 1 — Adversarial review of the publish_pack sidecar change (review; produce a note)
1. Identify the commit(s): `git log --oneline -8 -- tools/export_soundswitch_pack.py tests/test_soundswitch_pack.py`.
   The change is the `_stage_binding_sidecar` stage-before-swap + promote-after refactor.
2. Reproduce, do not trust: `python3 -m unittest tests.test_soundswitch_pack`,
   `python3 -m unittest discover tests`, `git diff --check`, and the three hard doc checks.
3. Verify these falsifiable properties at current line evidence (re-resolve lines yourself):
   - **B-1 pre-swap failure is clean.** A failure to produce/write the sidecar raises
     `BindingSidecarWriteError` **before** any swap; the prior canonical pack and prior
     sidecar are byte-identical; no `.{name}.tmp-*` or `.{name}.bak-*` leftovers; on a
     `first_export` nothing is published.
   - **B-2 swap failure is clean.** On `_renamex_np_swap`/fallback failure, the staged
     sidecar temp is unlinked, `_atomic_swap_dir` restores the prior pack, the prior
     sidecar is untouched, verdict is `swap_failed` (`PackSwapError` is an `OSError`).
     Confirm `test_fallback_second_rename_failure_restores_old_pack` still passes and the
     staged temp does not leak there.
   - **B-3 success is correct.** A successful publish yields the new pack plus the new
     sidecar at the **sibling** path (never inside the pack dir), byte-identical to the
     `export_pack` sidecar for the same `decoded`, with no temp leftovers.
   - **B-4 promote residual.** Evaluate the post-swap promote-rename failure window (A1).
     Either confirm it is the minimal achievable residual and fail-safe, or, if you can
     make publish strictly safer without a runtime behavior change, propose the smallest
     such change (Task 2).
   - **B-5 orphan reclamation.** A crash leaving a `.{name}.tmp-…` sidecar temp is reclaimed
     by `_gc_orphan_staging` (prefix glob match) and cannot be promoted into a pack.
   - **B-6 export_pack unchanged.** The refactor did not change `export_pack`'s all-or-nothing
     behavior or its sidecar content.
   - **B-7 no leak.** `_binding_sidecar_rows` still excludes `device_name` and emits only the
     `channel/note/target_kind/interaction/name` fields; no paths/ports/UUIDs/device names.
4. Write a short sanitized review note to
   `docs/validation/soundswitch_publish_sidecar_review.md` (proper frontmatter; status
   header): each property PASS/FAIL with file:line evidence, and a findings list graded
   blocker / high / medium / low. Commit.

### Task 2 — Implement revisions from Task 1 (implement)
- Fix every **blocker** and **high** finding with the smallest reviewed change plus a test
  that fails before and passes after. Keep changes inside `tools/export_soundswitch_pack.py`
  and `tests/test_soundswitch_pack.py` unless a finding proves otherwise.
- If there are no blocker/high findings, record "no revisions required" in the review note
  with the reproduced evidence. Medium/low findings: fix only if trivial and safe; otherwise
  list them as follow-ups. Commit (or note no-op).

### Task 3 — Independent software/wire review of the SoundSwitch exporter/player (review, then implement fixes)
1. Adopt the **hard boundary** and **source order** of
   `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`
   (review-only constraints on live/hardware; offline + fake-interface tests allowed). The
   range is current `main`. Do **not** review T7d capture, phase derivation, native Autoloop
   DMX, or roadmap reconciliation.
2. Treat prior conclusions and test claims as untrusted until reproduced. Re-resolve all line
   evidence at the review head. Inspect at least: `tools/export_soundswitch_pack.py`,
   `scripts/bridge_menubar.py`, `soundswitch_project_decoder.py`, `soundswitch_pack*.py`,
   `soundswitch_pack_loader.py`, `soundswitch_pack_verifier.py`, `soundswitch_laser_player.py`,
   `soundswitch_midi_input.py`, `soundswitch_pack_player_config.py`, `soundswitch_frame_sender.py`,
   the pack-driver paths of `state_manager.py`, and the matching `tests/`.
3. Verify the load-bearing software/wire properties already claimed in the status docs, at
   minimum: export → canonical replace → required sidecars → conservative reload;
   lock/swap/recovery and stale-state handling; static-look export/load/manual/layer with
   Press/Toggle and unknown-mode fail-closed; scripted render + unsupported-layout/identity
   fail-closed; runtime default-off, safe-zero, blackout/emergency precedence,
   `select_autoloop`-never-called, sanitized RW-5 status; and no Stream Deck code in bridge
   runtime paths.
4. Write a sanitized review note to
   `docs/validation/soundswitch_exporter_player_software_review.md` (frontmatter; status
   header) with PASS/FAIL + file:line + graded findings. **Because this handoff implements
   revisions**, fix every blocker/high finding with a minimal reviewed change + test (respect
   Part C; no runtime behavior change beyond a proven defect). Keep all conclusions bounded to
   software/wire evidence — never upgrade hardware status. Commit.

### Task 4 — Docs-staleness bookkeeping (implement)
1. Re-verify against current code (do not trust the docs) every doc listed under the
   `core_bridge` and `soundswitch_pack_player` contracts in `docs/agents/change_contracts.yml`.
   Fix any genuine drift you find (prose that contradicts code) as part of this task.
2. In `docs/plans/active/soundswitch_exporter_remaining_work.md`, mark the publish_pack
   binding-sidecar atomicity item as resolved (it is now stage-before-swap with prior-pack
   preservation) — an honest status update, not a new claim.
3. Bump the global baseline `docs/agents/change_contracts.yml:5` `last_verified_commit` and
   `:6` `last_verified_date` to the current HEAD/date **only after** step 1 is genuinely done.
4. Bump the frontmatter `last_verified_commit` / `last_verified_date` of the SoundSwitch status
   docs you re-verified: `soundswitch_exporter_remaining_work.md`, `soundswitch_README.md`,
   `docs/status/active_work_registry.md`, `docs/status/feature_status_matrix.md`,
   `docs/status/validation_matrix.md`. Do not bump a doc you did not actually re-verify.
5. Run all gates and confirm green (Part D). Commit.

## Part C — Invariants that MUST still hold (live safety)
- `StateManager` stays the only `DeckState` writer and the sole per-tick pack-frame submitter;
  the 200 Hz loop gains no filesystem/subprocess/MIDI/serial/socket/sleep/retry work.
- Pack mode stays default-off (`enabled=False`, `dry_run=True`, `output_backend="none"`);
  enabling still requires explicit `output_backend=pack` + `dry_run=false` + a real Enttec port.
- Automatic autoloop base stays software-zero; `select_autoloop` keeps having no production
  caller; T7d stays blocked. Blackout/emergency keep zeroing over static and scripted.
- Source SoundSwitch projects stay read-only; only independently verified packs publish;
  reload/export never enables output, changes backend, starts/restarts the bridge, or opens
  hardware. Sidecars stay siblings of the pack dir, never inside the manifest tree.
- Status/logs/docs/reviews never expose local paths, ports, aliases, device names, fixture
  serials, project UUIDs, raw frames/hashes, or config contents. No software/wire pass upgrades
  hardware status.

## Part D — Tests / gates (must be green at every commit and at the end)
```bash
python3 -m unittest tests.test_soundswitch_pack
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report   # expect: no STALE contracts after Task 4
git diff --check
```
Optional (needs the local source project; software gate only, opens no hardware):
```bash
python3 tools/prove_soundswitch_pack_generation.py \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir "$TMPDIR/ss_pack_proof_$(date +%s)"
```

## Part E — Acceptance (definition of done)
- [ ] Task 1 review note exists with B-1…B-7 each PASS/FAIL + file:line + graded findings.
- [ ] Every blocker/high finding from Tasks 1 and 3 is fixed with a test that fails before /
      passes after; or "no revisions required" is recorded with reproduced evidence.
- [ ] Task 3 software/wire review note exists, conclusions software/wire-bounded, hardware
      status unchanged.
- [ ] `check_docs_staleness --report` shows **no** STALE contracts; the global and per-doc
      `last_verified_commit` bumps reflect docs actually re-verified.
- [ ] Full suite, three hard doc checks, and `git diff --check` all green; pack proof still
      29/0/0 if run.
- [ ] No runtime behavior change; Part C invariants intact; no new branches.

## When you finish
Commit each task separately. Suggested final messages:
`soundswitch: review + harden publish_pack sidecar atomicity`,
`soundswitch: independent software/wire review of exporter/player`,
`docs: clear soundswitch staleness + record publish sidecar fix`.
Report back: the graded findings (with what you fixed vs deferred), the final gate/proof
results, and a one-line statement that runtime behavior and hardware status are unchanged.
