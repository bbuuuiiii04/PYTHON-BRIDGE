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
