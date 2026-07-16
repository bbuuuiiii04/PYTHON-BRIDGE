"""AWR-264: UI jargon gate + pad rename slug path."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from rb_ss_bridge_v2.led_pad_controls import CONTROL_META, RENDER_LABELS
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService


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
    def test_rename_look_preserves_bank_and_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            live = root / "live.json"
            draft = root / "draft.json"
            cfg = {
                "looks": {
                    "old_look": {
                        "scene_ref": "beat_strobe",
                        "brightness": 80,
                        "params": {"hz": 6.0, "duty": 0.3},
                    }
                },
                "banks": {"default": {"drop": ["old_look"], "ambient": [], "groove": [], "buildup": [], "pre_drop": [], "post_drop": [], "breakdown": [], "utility": []}},
                "color_engine": {
                    "palettes": {"blue_cyan": {}},
                    "slot_fill_strategy_by_look": {"old_look": "gradient_even"},
                    "locked_palette_by_look": {},
                    "slot_mono_chance_by_look": {},
                },
                "safety": {"allow_strobe": True},
                "_pad_meta": {"drafts": [], "looks": {"old_look": {"cue_beats": 16}}, "ui": {}, "pad_session": {"touched": [], "moved": [], "deleted": []}},
            }
            live.write_text("{}", encoding="utf-8")
            import json
            draft.write_text(json.dumps(copy.deepcopy(cfg)), encoding="utf-8")
            # Seed live with same looks so validation paths that compare live stay calm.
            live.write_text(json.dumps(copy.deepcopy(cfg)), encoding="utf-8")
            service = LedPadService(live_path=live, draft_path=draft, dry_run=True)
            # Service may wrap/normalize — pull through get if needed.
            res = service.rename_look({"name": "old_look", "new_name": "my_drop_strobe"})
            self.assertTrue(res.get("ok"), res)
            self.assertEqual(res.get("name"), "my_drop_strobe")
            payload = service.get_config_payload()
            looks = payload["config"]["looks"]
            self.assertIn("my_drop_strobe", looks)
            self.assertNotIn("old_look", looks)
            self.assertEqual(looks["my_drop_strobe"]["params"]["hz"], 6.0)
            banks = payload["banks"]
            self.assertIn("my_drop_strobe", banks.get("drop") or [])
            self.assertNotIn("old_look", banks.get("drop") or [])


if __name__ == "__main__":
    unittest.main()
