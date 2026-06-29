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

    def test_retired_word_in_notes_not_label_ok(self):
        # "completed" in the notes cell, not the label cell, must NOT trip the check
        row = "| `docs/plans/active/ptr.md` | COMPATIBILITY POINTER | links to the completed spec |"
        self.assertEqual(cac.misfiled_active_rows(row), [])

    def test_completed_dir_not_flagged(self):
        row = "| `docs/plans/completed/x.md` | COMPLETED / SUPERSEDED PLANNING | n |"
        self.assertEqual(cac.misfiled_active_rows(row), [])


if __name__ == "__main__":
    unittest.main()
