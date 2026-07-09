"""Deletion-scope tests for packaging/stick/purge.command (AWR-122 interim).

The dangerous logic is purge's manifest-driven deletion: it must refuse without
a manifest, refuse without the typed PURGE confirmation, remove exactly the
manifest paths under the allowed roots, and skip anything outside them.
Runs the real script under a throwaway $HOME.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PURGE = Path(__file__).resolve().parents[1] / "packaging" / "stick" / "purge.command"


class PurgeCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.app = self.home / "Applications" / "RBSS Bridge.app"
        (self.app / "Contents").mkdir(parents=True)
        (self.app / "Contents" / "bin").write_text("x")
        self.support = self.home / "Library" / "Application Support" / "RBSS Bridge"
        self.cache_file = self.support / "spectral_cache" / "v4" / "a.json"
        self.cache_file.parent.mkdir(parents=True)
        self.cache_file.write_text("{}")
        self.manifest = self.support / "install_manifest.txt"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, stdin: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, HOME=str(self.home))
        return subprocess.run(
            ["bash", str(PURGE)], input=stdin, text=True,
            capture_output=True, env=env,
        )

    def _write_manifest(self, lines):
        self.manifest.write_text("".join(f"{line}\n" for line in lines))

    def test_refuses_without_manifest(self):
        result = self._run("PURGE\n")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.app.exists())

    def test_refuses_without_typed_confirmation(self):
        self._write_manifest([self.app, self.cache_file])
        result = self._run("no\n")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.app.exists())
        self.assertTrue(self.cache_file.exists())
        self.assertTrue(self.manifest.exists())

    def test_purge_removes_exactly_manifest_paths(self):
        self._write_manifest([self.app, self.cache_file])
        result = self._run("PURGE\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.app.exists())
        self.assertFalse(self.cache_file.exists())
        self.assertFalse(self.manifest.exists())
        self.assertFalse(self.support.exists())  # empty dirs pruned

    def test_skips_paths_outside_allowed_roots_and_dotdot(self):
        outside = self.home / "Documents" / "keep.txt"
        outside.parent.mkdir(parents=True)
        outside.write_text("precious")
        sneaky = f"{self.support}/spectral_cache/../../../Documents/keep.txt"
        self._write_manifest([outside, sneaky, self.cache_file])
        result = self._run("PURGE\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(outside.exists())          # outside root: skipped
        self.assertFalse(self.cache_file.exists())  # legitimate entry removed
        self.assertIn("outside allowed roots", result.stdout)
        self.assertIn("suspicious", result.stdout)


if __name__ == "__main__":
    unittest.main()
