from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from rb_ss_bridge_v2.tools import export_soundswitch_pack as export_module


class SourceFingerprintParityTests(unittest.TestCase):
    def _import_menubar(self):
        scripts_dir = REPO_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        try:
            return importlib.import_module("bridge_menubar")
        except ModuleNotFoundError as exc:
            if exc.name in {"objc", "AppKit", "Foundation"}:
                self.skipTest(f"PyObjC unavailable: {exc.name}")
            raise

    def test_tool_and_menubar_fingerprints_remain_in_lockstep(self) -> None:
        bridge_menubar = self._import_menubar()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "project.ssproj"
            nested = bundle / "nested"
            nested.mkdir(parents=True)
            first = bundle / "project.ssfile"
            second = nested / "lighting.ssfile"
            first.write_bytes(b"abc")
            second.write_bytes(b"lighting")
            (bundle / "linked.ssfile").symlink_to(first)

            self.assertEqual(
                export_module._source_content_fingerprint(bundle),
                bridge_menubar._source_content_fingerprint(bundle),
            )
            self.assertEqual(
                export_module._source_stat_signature(bundle),
                bridge_menubar._source_stat_signature(bundle),
            )
            absent = root / "absent.ssproj"
            self.assertIsNone(export_module._source_content_fingerprint(absent))
            self.assertIsNone(bridge_menubar._source_content_fingerprint(absent))
            self.assertIsNone(export_module._source_stat_signature(absent))
            self.assertIsNone(bridge_menubar._source_stat_signature(absent))

            before = export_module._source_content_fingerprint(bundle)
            first.write_bytes(b"abd")
            after = export_module._source_content_fingerprint(bundle)
            self.assertNotEqual(before, after)
            self.assertEqual(after, bridge_menubar._source_content_fingerprint(bundle))

            before_utime = export_module._source_content_fingerprint(bundle)
            stat = first.stat()
            os.utime(
                first,
                ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
            )
            self.assertEqual(
                before_utime, export_module._source_content_fingerprint(bundle),
            )
            self.assertEqual(
                export_module._source_content_fingerprint(bundle),
                bridge_menubar._source_content_fingerprint(bundle),
            )
            self.assertEqual(
                export_module._source_stat_signature(bundle),
                bridge_menubar._source_stat_signature(bundle),
            )

    def test_ignore_set_skips_files_in_lockstep(self) -> None:
        bridge_menubar = self._import_menubar()
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "project.ssproj"
            bundle.mkdir()
            (bundle / "project.ssfile").write_bytes(b"content")
            opaque = bundle / "demo.mp4"
            opaque.write_bytes(b"v1")
            ignore = frozenset({"demo.mp4"})

            base = export_module._source_content_fingerprint(bundle, ignore=ignore)
            self.assertEqual(
                base, bridge_menubar._source_content_fingerprint(bundle, ignore=ignore),
            )
            # Rewriting an ignored file must not move the fingerprint, on either side.
            opaque.write_bytes(b"v2-rewritten-and-longer")
            self.assertEqual(
                base, export_module._source_content_fingerprint(bundle, ignore=ignore),
            )
            self.assertEqual(
                base, bridge_menubar._source_content_fingerprint(bundle, ignore=ignore),
            )
            # Without the ignore the change is visible (proves the file is real).
            self.assertNotEqual(
                base, export_module._source_content_fingerprint(bundle),
            )


if __name__ == "__main__":
    unittest.main()
