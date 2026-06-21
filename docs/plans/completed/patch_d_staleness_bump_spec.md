# Codex Implementation Spec — Patch D follow-up: clear the `led_govee` / `config_schema` staleness flag

> **Status:** SPEC — doc-metadata only, zero runtime behavior change. Author: Claude (review follow-up to Patch D, commit `ca3a74b`).
> **Scope:** ONE doc-only commit. No `.py`, no `config/*.json`, no tests.

## Part A — Context & root cause (verified; read, do not implement)

Patch D (`ca3a74b`, "Implement M2.5 Patch D drop slot cues") added `rt_drop_chase` /
`rt_drop_center_burst` slot cues and updated the 7 `led_govee` docs, **but did not bump the
change-contract verification baseline**. As a result `tools/check_docs_staleness.py --report`
(advisory) flags two contracts as STALE.

- **[confirmed]** The repo uses a **single global** baseline, not per-contract:
  `docs/agents/change_contracts.yml:5` → `last_verified_commit: 0675a31` and `:6`
  → `last_verified_date: 2026-06-17`.
- **[confirmed]** The staleness tool reads exactly that line via regex
  `^last_verified_commit:\s*(\S+)` (`tools/check_docs_staleness.py:118`) and, for each contract,
  diffs its `code_globs` impl files between that baseline and HEAD
  (`:133-137`). A doc changing does **not** trip it — only impl (`is_impl`, `:68-78`).
- **[confirmed]** `HEAD = ca3a74b` (`git rev-parse --short HEAD`). The only commits between
  `0675a31` and `ca3a74b` are `a470aba` (metadata-only "Bump LED/Govee verification to Patch C")
  and `ca3a74b` (Patch D). The only **impl** files changed across that range are
  `govee_frame_renderer.py` and `config/led_look_director.example.json`
  (`git show ca3a74b --stat`). Those globs belong to exactly `led_govee` and `config_schema` —
  which is why only those two are flagged, and why bumping the single global hash masks **nothing
  else** (no other contract's impl changed).
- **[confirmed]** The card carries its own frontmatter baseline:
  `docs/subsystems/led_govee.md:4` → `last_verified_commit: 0675a31`, `:5`
  → `last_verified_date: 2026-06-17`. Patch D's STEP-0 hygiene called for bumping both the
  contract and this card.
- **[confirmed]** Patch D's 7 `led_govee` docs were already updated in `ca3a74b` and use only
  allowed status words (`SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED`, `software-tested`,
  `partial`); the three hard checks (`check_docs_metadata.py`, `check_agent_contracts.py`,
  `check_docs_drift.py`) already pass at HEAD. Only the advisory staleness baseline is behind.
- **[assumed]** The `config_schema` docs at HEAD accurately describe the committed config surface;
  the example.json change in `ca3a74b` was the additive `rt_drop_chase` / `rt_drop_center_burst`
  look objects only. Re-verify (Task 0) before bumping.

Root cause: the verification baseline was not advanced when Patch D landed.

## Part B — Tasks (implement exactly, in order; one commit at the end)

### Absolute rules — DO NOT TOUCH
- **No code, no config, no tests.** Do **not** stage, commit, modify, or revert any of the
  *currently uncommitted* working-tree changes (`led_color_engine.py` fail-safe,
  `tests/test_color_engine_config.py`, `tests/test_led_color_engine.py`,
  `tests/test_led_color_engine_m2_phase1.py`, `docs/setup/configuration.md`,
  `docs/subsystems/config.md`, `docs/subsystems/tests.md`,
  `docs/validation/software_test_inventory.md`,
  `docs/agents/task_playbooks/update_config_schema.md`). Those belong to a separate
  Patch-A/B/logging workstream and are out of scope. Leave them dirty.
- Do **not** re-verify or "touch up" docs outside the `led_govee` + `config_schema` `docs_update`
  sets. No behavior change to any runtime module.
- This commit must contain **only** `docs/agents/change_contracts.yml` and
  `docs/subsystems/led_govee.md`.

### Task 0 — Re-verify the flagged docs against current code (read-only; AGENTS.md §8 obligation)
Confirm each of these still matches HEAD code before advancing the baseline. If any is wrong,
**STOP and report** (do not bump a baseline over a stale doc):
- `led_govee` `docs_update` set — confirm `docs/subsystems/led_govee.md` and the status matrices
  describe `rt_drop_chase` / `rt_drop_center_burst` as software-tested / hardware-unvalidated, and
  that `SLOT_EFFECTS` in `govee_frame_renderer.py:1568-1578` contains both new keys.
- `config_schema` `docs_update` set — confirm the committed example config
  (`config/led_look_director.example.json`) drop bank lists both new looks with
  `color_source:"engine"`, `params:{}`, `safety_class:"drop"`.

### Task 1 — `docs/agents/change_contracts.yml`: advance the global baseline
- Line 5: `last_verified_commit: 0675a31` → `last_verified_commit: ca3a74b`
- Line 6: `last_verified_date: 2026-06-17` → keep `2026-06-17` (re-verification date is today;
  update only if you run this on a later date).

### Task 2 — `docs/subsystems/led_govee.md`: sync the card frontmatter
- Line 4: `last_verified_commit: 0675a31` → `last_verified_commit: ca3a74b`
- Line 5: `last_verified_date: 2026-06-17` → keep `2026-06-17` (match Task 1's date exactly).

## Part C — Invariants that MUST still hold (live safety)
- **Doc-only change ⇒ zero runtime impact.** No module imported by the bridge is touched; the
  200 Hz push loop, `StateManager` ownership, laser/LED/SS behavior, and the live show are all
  unaffected by definition. This is the strongest possible live-safety posture: nothing executable
  changes.
- The baseline must only ever move **forward** to a commit whose governed docs were actually
  re-verified (Task 0). Never bump past unverified impl drift.

## Part D — Tests
No new tests (doc metadata only; nothing executable changes). Validation is the repo doc gate:
```
python3 tools/check_docs_metadata.py     # must pass
python3 tools/check_agent_contracts.py   # must pass
python3 tools/check_docs_drift.py        # must pass
python3 tools/check_docs_staleness.py --report   # must now report led_govee + config_schema CLEAN
```

## Part E — Acceptance (definition of done)
- [ ] Task 0 re-verification done; no stale doc found (else STOPPED + reported).
- [ ] `change_contracts.yml:5` and `led_govee.md:4` both read `ca3a74b`; dates match.
- [ ] The three hard checks pass (exit 0).
- [ ] `check_docs_staleness.py --report` no longer flags `led_govee` **or** `config_schema`
      (expected: "no contract is stale" — both were flagged only by the impl files in `ca3a74b`).
- [ ] `git diff --staged --name-only` shows **exactly** two files:
      `docs/agents/change_contracts.yml`, `docs/subsystems/led_govee.md`. No other file staged.
- [ ] Working tree still has the pre-existing uncommitted Patch-A/B/logging changes untouched.

## When you finish
- Commit message: `Bump LED/Govee + config_schema verification baseline to Patch D (ca3a74b)`
  (append the repo's standard `Co-Authored-By` trailer if you use it).
- Report back: the staleness `--report` output proving both contracts are now clean, and confirm
  the two-file diff.

---
### Pre-handoff checklist (author self-review)
1. Claims labeled confirmed/assumed/unknown — **yes** (Part A).
2. Verified against current code — **yes** (re-read `change_contracts.yml:5`, `led_govee.md:4`,
   `check_docs_staleness.py:118`, `git rev-parse HEAD`, `git show ca3a74b --stat` this session).
3. Pending-state guard — **N/A** (no runtime state).
4. Mode-transition cleanup — **N/A** (no runtime state).
5. Third-party API completeness — **N/A** (no API calls).
6. Cross-checked against existing code — **yes** (baseline is global, not per-contract; only two
   contracts' globs changed in range, so the bump masks nothing).
7. Pure-function test seam — **N/A** (no algorithm; repo doc gate is the check).
8. Live safety explicit — **yes** (Part C: doc-only, nothing executable changes).
9. Adversarial self-review — **done.** Attack: "bumping a global baseline can hide a genuinely
   stale contract." Mitigation: verified the *only* impl files changed in `0675a31..ca3a74b` are
   `govee_frame_renderer.py` + `example.json` (led_govee + config_schema), and Task 0 forces
   re-verification of those two before the bump. Second attack: "the uncommitted config docs make
   config_schema's content lag the bumped baseline." Mitigation: staleness is commit-based and the
   committed docs at HEAD already describe the committed config; the uncommitted enhancements are a
   separate workstream explicitly fenced off in Part B.
