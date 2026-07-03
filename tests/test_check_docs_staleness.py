import importlib.util
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_docs_staleness",
    Path(__file__).resolve().parents[1] / "tools" / "check_docs_staleness.py",
)
cds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cds)


class TestResolve(unittest.TestCase):
    def test_recursive_glob_returns_nested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "x" / "nested").mkdir(parents=True)
            (root / "x" / "nested" / "a.py").write_text("", encoding="utf-8")

            self.assertEqual(cds.resolve("x/**", root), ["x/nested/a.py"])

    def test_literal_paths_and_star_globs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir()
            (root / "a" / "one.py").write_text("", encoding="utf-8")
            (root / "a" / "dir.py").mkdir()

            self.assertEqual(cds.resolve("a/one.py", root), ["a/one.py"])
            self.assertEqual(cds.resolve("a/*.py", root), ["a/one.py"])


class TestImplFiles(unittest.TestCase):
    def test_tools_count_when_globbed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools" / "assets").mkdir(parents=True)
            (root / "tools" / "foo.py").write_text("", encoding="utf-8")
            (root / "tools" / "assets" / "app.js").write_text("", encoding="utf-8")

            self.assertEqual(
                cds.impl_files(["tools/**"], root),
                ["tools/assets/app.js", "tools/foo.py"],
            )

    def test_docs_are_not_impl_except_data_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs" / "subsystems").mkdir(parents=True)
            (root / "docs" / "data").mkdir()
            (root / "docs" / "subsystems" / "foo.md").write_text("", encoding="utf-8")
            (root / "docs" / "data" / "offsets.yaml").write_text("", encoding="utf-8")

            self.assertEqual(cds.impl_files(["docs/**"], root), ["docs/data/offsets.yaml"])


class TestParseContracts(unittest.TestCase):
    def test_minimal_contracts_yml(self):
        contracts = cds.parse_contracts(
            """
contracts:
  demo:
    code_globs:
      - tools/**
    docs_update:
      - docs/subsystems/demo.md
"""
        )

        self.assertEqual(contracts["demo"]["code_globs"], ["tools/**"])
        self.assertEqual(contracts["demo"]["docs_update"], ["docs/subsystems/demo.md"])


if __name__ == "__main__":
    unittest.main()
