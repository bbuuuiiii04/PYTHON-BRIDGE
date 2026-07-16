"""AWR-264: UI jargon gate + CONTROL_META language + pad rename."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from rb_ss_bridge_v2.led_pad_controls import CONTROL_META, RENDER_LABELS
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService


_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class _FakePlayback:
    def ownership(self):
        return {"state": "free"}

    def status(self):
        return {"playing": False}


class UiJargonGateTests(unittest.TestCase):
    def test_check_ui_jargon_exits_clean(self) -> None:
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(
            [sys.executable, str(root / "tools" / "check_ui_jargon.py")],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)

    def test_control_meta_uses_musician_labels(self) -> None:
        self.assertEqual(CONTROL_META["hz"]["label"], "Flashes per second")
        self.assertEqual(CONTROL_META["duty"]["label"], "Flash length (%)")
        self.assertEqual(CONTROL_META["subdivision"]["label"], "Flashes per beat")
        self.assertEqual(CONTROL_META["beat_division"]["label"], "Trigger every … beats")
        self.assertEqual(CONTROL_META["dim_floor"]["label"], "Minimum brightness")
        self.assertNotIn("show-colored", RENDER_LABELS.get("rt_drop_chase", ""))


class PadRenameTests(unittest.TestCase):
    def test_rename_duplicate_preserves_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            service = LedPadService(path, dry_run=True, playback=_FakePlayback())
            payload = service.get_config_payload()
            # Prefer a realtime look that is not the global blackout target.
            blackout = str(payload["config"].get("blackout") or "")
            source = "rt_drop_chase" if "rt_drop_chase" in payload["config"]["looks"] else next(
                name for name in payload["config"]["looks"] if name != blackout
            )
            if source == blackout:
                self.skipTest("could not find a non-blackout look to rename")
            params_before = dict((payload["config"]["looks"][source].get("params") or {}))
            dup = service.duplicate_look({"source": source, "new_name": "awr264_dup_source"})
            self.assertTrue(dup.get("ok"), dup)
            res = service.rename_look({"name": "awr264_dup_source", "new_name": "renamed_awr264_look"})
            self.assertTrue(res.get("ok"), res)
            after = service.get_config_payload()
            looks = after["config"]["looks"]
            self.assertIn("renamed_awr264_look", looks)
            self.assertNotIn("awr264_dup_source", looks)
            self.assertIn(source, looks)  # original untouched
            self.assertEqual(looks["renamed_awr264_look"].get("params") or {}, params_before)
            self.assertIn("renamed_awr264_look", after["banks"].get("drafts") or [])


if __name__ == "__main__":
    unittest.main()
