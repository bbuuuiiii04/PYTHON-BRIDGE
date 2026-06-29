---
doc_status: active-implementation-spec
truth_level: code-grounded
last_verified_commit: 3818b91
last_verified_date: 2026-06-29
validation_scope: docs-tooling only; extends tools/check_agent_contracts.py with a forward-coverage
  check. No runtime/bridge code, no network, no hardware. SOFTWARE-ONLY.
---

# Codex Implementation Spec — Active-doc lifecycle check (orphans + stale-classified)

You are Codex, implementing on `rb_ss_bridge_v2`. Work directly on `main` (no new branches).
Code and tests win over docs. Implement Part B exactly, in order, commit after each task.

## Part A — Context & root cause (verified; read, do not implement)

**Plain meaning.** A spec file (`docs/plans/active/laser_color_engine_design_spec.md`) sat in the
active-plans folder for ~10 days without being listed in either index that is supposed to track it.
Nothing failed. This task adds the missing guardrail so it can't happen again.

- **[confirmed] Root cause.** The three hard checkers only validate the *reverse* direction — that
  paths *referenced by* the routing docs exist (`tools/check_agent_contracts.py:144-150`,
  `referenced_paths` at `:86`). None of them validate the *forward* direction: that every file
  present in `docs/plans/active/` / `docs/prompts/active/` is actually referenced in the index or
  registry. So an unclassified file in `active/` keeps CI green forever.
- **[confirmed] `doc_index.md` claims to be "The single classification index for every doc in this
  repo"** (top of `docs/architecture/doc_index.md`), but no check enforces that claim.
- **[confirmed] The orphan that motivated this:** `laser_color_engine_design_spec.md` was added in
  PR #111, never added to `docs/status/active_work_registry.md` or `docs/architecture/doc_index.md`
  (git pickaxe shows it was never in either), and is now registered as AWR-111. An orphan scan today
  finds **0** remaining — so the new check must PASS on current HEAD.
- **[confirmed] Active dirs contain a glob reference, not just exact paths.** `doc_index.md` classifies
  prompts with the token `` `docs/prompts/active/*.md` `` (currently ~line 95). A naive exact-path
  matcher would wrongly flag every file in `docs/prompts/active/`. **The matcher MUST honor `*` globs.**
- **[confirmed] One active file is a symlink** —
  `docs/plans/active/soundswitch_importer_exporter_player_codex_spec.md` →
  `../../research/soundswitch/...`. It is referenced by exact path in `doc_index.md`, so it must stay
  classified. `Path.glob` yields it; `.exists()` follows the link. No special handling needed, but do
  not break on it.
- **[confirmed] Host file is stdlib-only, no network, no runtime import**
  (`tools/check_agent_contracts.py` docstring `:1-15`; `ROOT` at `:22`; backtick-token regex
  `CODE_REF_RE` at `:69`; `errors` list + exit at `:137-185`).
- **[confirmed] Wiring is automatic.** CI runs the file at `.github/workflows/docs.yml:22` and the
  local hook loops it at `tools/git-hooks/pre-commit:22`. Adding the check *inside* this file needs
  **no new CI/hook wiring**.
- **[confirmed] The reverse failure also exists — stale-classified docs.**
  `docs/prompts/active/rekordbox_mixer_active_deck_re_continuation_prompt.md` is classified in
  `doc_index.md` as `AGENT PROMPT (SUPERSEDED CONTEXT)` yet still lives in `docs/prompts/active/`; the
  active-deck runtime it handed off is implemented + software-tested (AWR-110). So a prompt can be
  executed/superseded and linger in `active/` looking pending. **"Executed" is not machine-detectable,
  but "classified retired (completed/superseded/archived) yet still in `active/`" is** — that is the
  signal Task 3 uses. Repo convention for spent one-shot prompts is **delete** (Git preserves);
  reusable review/capture prompts stay (`doc_index.md` lines ~95/106/125).

**Decision (locked):** extend `tools/check_agent_contracts.py` — do **not** create a new
`tools/check_docs_orphans.py` (that would duplicate `ROOT`/error-printing/`main` and require new CI
and hook wiring for zero benefit).

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Touch only `tools/check_agent_contracts.py` and one new test file. **No runtime/bridge code.**
- Keep the checker zero-dependency (stdlib only), no network, no hardware, no runtime-package import.
- Scope the new check to exactly two dirs: `docs/plans/active/` and `docs/prompts/active/`. Do **not**
  scan `completed/`, `archive/`, `research/`, or `history/` (those legitimately hold unindexed files,
  and `doc_index` references some via brace-list tokens that are not globs).

### Task 1 — `tools/check_agent_contracts.py`: add the forward-coverage check

Add near the top (after the existing `import re`):
```python
import fnmatch
```

Add module-level constants (next to the other lists, e.g. after `AGENTS_REQUIRED_ROUTES`):
```python
# Forward-coverage: every file in these dirs must be classified in one of the
# classifier docs below, or CI fails. This is the guardrail that catches a spec
# dropped into active/ without being registered (e.g. the AWR-111 orphan).
ACTIVE_DOC_GLOBS = ["docs/plans/active/*.md", "docs/prompts/active/*.md"]
CLASSIFIER_DOCS = [
    "docs/architecture/doc_index.md",
    "docs/status/active_work_registry.md",
]
```

Add two functions (place them after `referenced_paths`, `:88`):
```python
def classifier_tokens(texts: list[str]) -> set[str]:
    """All backtick-quoted tokens from the classifier docs (incl. glob/path tokens)."""
    tokens: set[str] = set()
    for text in texts:
        tokens.update(CODE_REF_RE.findall(text))
    return tokens


def is_classified(relpath: str, tokens: set[str]) -> bool:
    """True if relpath is named (exact path or basename) or glob-matched by any token."""
    name = relpath.rsplit("/", 1)[-1]
    for tok in tokens:
        if tok == relpath or tok == name:
            return True
        if "*" in tok and (fnmatch.fnmatch(relpath, tok) or fnmatch.fnmatch(name, tok)):
            return True
    return False
```

In `main()`, after the existing referenced-path loop (after `:150`, before the AGENTS route loop at
`:152`), add:
```python
    classifier_texts: list[str] = []
    for rel in CLASSIFIER_DOCS:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing classifier doc: {rel}")
            continue
        classifier_texts.append(path.read_text(encoding="utf-8"))
    tokens = classifier_tokens(classifier_texts)
    for glob in ACTIVE_DOC_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            rel = path.relative_to(ROOT).as_posix()
            if not is_classified(rel, tokens):
                errors.append(
                    f"unclassified active doc: {rel} — add it to "
                    "docs/architecture/doc_index.md or docs/status/active_work_registry.md"
                )
```

Update the module docstring (`:4-15`) to list the new check ("every file in docs/plans/active and
docs/prompts/active is classified in doc_index.md or active_work_registry.md").

Commit: `docs-tooling: fail check_agent_contracts on unclassified active docs`.

### Task 2 — `tests/test_docs_orphan_check.py`: pure-function tests for `is_classified`

Load the function from the tool by file path (`tools/` is not a package). No filesystem fixtures —
test the pure matcher only:
```python
import importlib.util, unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_agent_contracts",
    Path(__file__).resolve().parents[1] / "tools" / "check_agent_contracts.py",
)
cac = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(cac)


class TestIsClassified(unittest.TestCase):
    def test_exact_path(self):
        self.assertTrue(cac.is_classified("docs/plans/active/foo.md",
                                          {"docs/plans/active/foo.md"}))
    def test_basename(self):
        self.assertTrue(cac.is_classified("docs/plans/active/foo.md", {"foo.md"}))
    def test_glob_on_path(self):
        self.assertTrue(cac.is_classified("docs/prompts/active/x_prompt.md",
                                          {"docs/prompts/active/*.md"}))
    def test_glob_on_basename(self):
        self.assertTrue(cac.is_classified("docs/plans/active/rt_comet_a.md",
                                          {"rt_comet_*.md"}))
    def test_unclassified(self):
        self.assertFalse(cac.is_classified("docs/plans/active/orphan.md",
                                           {"docs/plans/active/other.md", "unrelated.md"}))


if __name__ == "__main__":
    unittest.main()
```
Commit: `tests: pure-function coverage for the orphan-check matcher`.

### Task 3 — `tools/check_agent_contracts.py`: flag stale-classified active docs (reverse of Task 1)

Add the matcher (after `is_classified`):
```python
RETIRED_LABEL_RE = re.compile(r"COMPLETED|SUPERSEDED|ARCHIVE|HISTORICAL|DEPRECATED", re.I)
ACTIVE_DOC_PREFIXES = ("docs/plans/active/", "docs/prompts/active/")

def misfiled_active_rows(doc_index_text: str) -> list[str]:
    """Paths whose doc_index row sits in an active/ dir but carries a retired status label."""
    bad: list[str] = []
    for line in doc_index_text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        paths = CODE_REF_RE.findall(cells[0])
        if paths and paths[0].startswith(ACTIVE_DOC_PREFIXES) and RETIRED_LABEL_RE.search(cells[1]):
            bad.append(paths[0])
    return bad
```

In `main()`, after the orphan loop, add:
```python
    doc_index_text = (ROOT / "docs/architecture/doc_index.md").read_text(encoding="utf-8")
    for path in misfiled_active_rows(doc_index_text):
        errors.append(
            f"stale-classified active doc: {path} is labeled retired (completed/superseded/"
            "archived) in doc_index but still in active/ — move it to completed/ or delete it "
            "(Git history preserves prompts)"
        )
```

Notes:
- **`PLANNED` is NOT a retired label.** The laser-color spec is `PLAN / SPEC (PLANNED — blocked)` —
  blocked-but-active, must NOT be flagged. `RETIRED_LABEL_RE` deliberately excludes `PLANNED`/`ACTIVE`.
- Rows whose path is in `completed/`, `archive/`, etc. are skipped by `ACTIVE_DOC_PREFIXES` even though
  their labels say SUPERSEDED — only `active/`-dir rows are flagged.

Extend `tests/test_docs_orphan_check.py` with a `TestMisfiled` class (pure, no files):
```python
class TestMisfiled(unittest.TestCase):
    def test_superseded_in_active_flagged(self):
        row = "| `docs/prompts/active/x.md` | AGENT PROMPT (SUPERSEDED CONTEXT) | n |"
        self.assertEqual(cac.misfiled_active_rows(row), ["docs/prompts/active/x.md"])
    def test_active_label_ok(self):
        row = "| `docs/prompts/active/x.md` | AGENT PROMPT (ACTIVE) | n |"
        self.assertEqual(cac.misfiled_active_rows(row), [])
    def test_planned_not_retired(self):
        row = "| `docs/plans/active/laser.md` | PLAN / SPEC (PLANNED — blocked) | n |"
        self.assertEqual(cac.misfiled_active_rows(row), [])
    def test_completed_dir_not_flagged(self):
        row = "| `docs/plans/completed/x.md` | COMPLETED / SUPERSEDED PLANNING | n |"
        self.assertEqual(cac.misfiled_active_rows(row), [])
```
Commit: `docs-tooling: flag stale-classified docs left in active/`.

**Precondition for green:** Task 3 will fail on current `main` because of the one real instance
(`rekordbox_mixer_active_deck_re_continuation_prompt.md`, labeled SUPERSEDED in `active/`). Resolve it
per operator decision BEFORE landing Task 3 — delete it and drop its `AWR-110` reference (Git
preserves), or reclassify if still genuinely active. Do not land Task 3 with CI red.

## Part C — Invariants that MUST still hold (live safety)

- **No runtime/bridge behavior change.** This touches only a docs checker + a test. The 200 Hz loop,
  StateManager, readers, outputs, and all live-mixing paths are untouched (`AGENTS.md §6`).
- Checker stays **zero-dep, no network, no hardware, no runtime-package import** (its existing
  contract, `tools/check_agent_contracts.py:1-15`). `fnmatch` is stdlib.
- The other two hard checks (`check_docs_metadata`, `check_docs_drift`) are unaffected.

## Part D — Tests
- New `tests/test_docs_orphan_check.py` (Task 2) — pure-function seam, no files/subprocess.
- Existing suite must stay green: `python3 -m unittest discover tests`.

## Part E — Acceptance (definition of done)
- [ ] `python3 tools/check_agent_contracts.py` **passes on current `main`** (0 orphans today). If it
      flags anything, the matcher is wrong (most likely missing glob handling) — fix before done.
- [ ] Manual negative proof: `touch docs/plans/active/zzz_orphan_probe.md`, run the checker → it must
      FAIL with the `unclassified active doc: …zzz_orphan_probe.md` line; then delete the probe and
      confirm it PASSES again. (Do not commit the probe.)
- [ ] `python3 -m unittest tests.test_docs_orphan_check` passes (5 cases).
- [ ] The other two hard checks still pass; full unittest suite still green.
- [ ] Only `tools/check_agent_contracts.py` and `tests/test_docs_orphan_check.py` changed. No runtime
      code, no new dependency, no new CI/hook wiring.
- [ ] Task 3 (reverse): an `active/`-dir row labeled retired (completed/superseded/archived) fails CI;
      `PLANNED` rows and `completed/`-dir rows do NOT. `TestMisfiled` passes.
- [ ] Precondition resolved: `rekordbox_mixer_active_deck_re_continuation_prompt.md` no longer trips
      the reverse check (deleted + `AWR-110` reference dropped, or reclassified per operator), so the
      whole `check_agent_contracts.py` passes on `main`.

## When you finish
- Commit per task with the messages above.
- Report: the checker output on clean `main` (pass), the negative-probe output (fail then pass),
  and the unittest result. State plainly that no runtime code changed.
