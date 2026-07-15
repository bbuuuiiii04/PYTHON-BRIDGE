"""No-runtime-importer, workspace fence, byte identity, no-network (tests D11, D12)."""
import socket
import tempfile
import unittest
from pathlib import Path

from tools.spectral_pilot import guards
from tools.spectral_pilot import session as S


class NoRuntimeImporterTests(unittest.TestCase):
    def test_no_runtime_module_imports_spectral_pilot(self):
        offenders = guards.no_runtime_importer_offenders()
        self.assertEqual(offenders, [], f"runtime modules import spectral_pilot: {offenders}")

    def test_guard_detects_import_forms(self):
        for src in (
            "from tools.spectral_pilot import canonical",
            "import tools.spectral_pilot.selection",
            "from tools import spectral_pilot",
            "importlib.import_module('tools.spectral_pilot.verdict')",
        ):
            self.assertTrue(guards._imports_spectral_pilot(src), src)
        self.assertFalse(guards._imports_spectral_pilot("from rb_ss_bridge_v2 import hardness_v0"))


class ForbiddenImportTests(unittest.TestCase):
    def test_no_network_or_subprocess_at_module_level(self):
        found = guards.forbidden_module_level_imports()
        self.assertEqual(found, {}, f"forbidden module-level imports: {found}")


class ByteIdentityTests(unittest.TestCase):
    def test_listing_hash_detects_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.txt").write_text("x")
            before = guards.listing_hash([root])
            self.assertEqual(before, guards.listing_hash([root]))   # stable
            (root / "b.txt").write_text("y")
            after = guards.listing_hash([root])
            self.assertNotEqual(before, after)

    def test_assert_unchanged(self):
        guards.assert_unchanged("h", "h")           # no raise
        with self.assertRaises(RuntimeError):
            guards.assert_unchanged("h1", "h2")


class WorkspaceFenceTests(unittest.TestCase):
    def test_safe_path_rejects_escape(self):
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            self.assertTrue(str(S._safe_path(ws, "responses.jsonl")).startswith(str(ws.resolve())))
            with self.assertRaises(ValueError):
                S._safe_path(ws, "../escape.jsonl")
            with self.assertRaises(ValueError):
                S._safe_path(ws, "/etc/passwd")


class NoNetworkTests(unittest.TestCase):
    def test_guard_blocks_socket_and_restores(self):
        with guards.no_network_guard():
            with self.assertRaises(RuntimeError):
                socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # restored afterwards
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.close()


if __name__ == "__main__":
    unittest.main()
