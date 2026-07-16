"""AWR-258 static UI integrity checks (no browser required)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_ASSETS = Path(__file__).resolve().parents[1] / "tools" / "led_pad_assets"
_SIM = Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets"


class PadUiIntegrityTests(unittest.TestCase):
    def test_save_current_editor_payload_covers_every_editor_payload_field(self) -> None:
        src = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        ep = re.search(
            r"function editorPayload\(\)\s*\{[\s\S]*?return\s*\{([^}]+)\}",
            src,
        )
        self.assertIsNotNone(ep)
        dirty_keys = set(re.findall(r"(\w+)\s*:", ep.group(1)))
        save = re.search(
            r"async function saveCurrentEditor\(\)\s*\{[\s\S]*?api\.saveLook\(\{([\s\S]*?)\}\)",
            src,
        )
        self.assertIsNotNone(save)
        save_keys = set(re.findall(r"(\w+)\s*:", save.group(1)))
        save_keys.discard("name")
        missing = dirty_keys - save_keys
        self.assertFalse(
            missing,
            f"saveCurrentEditor omits dirty-tracked editorPayload fields: {sorted(missing)}",
        )

    def test_beforeunload_guards_present_on_lab_pad_sim(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        sim = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        for label, src in (("lab.js", lab), ("pad-ui.js", pad), ("sim-app.js", sim)):
            self.assertIn("beforeunload", src, f"{label} missing beforeunload guard")

    def test_lab_reconnect_stashes_dirty_same_name(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        self.assertIn("isEditorDirty()", lab)
        self.assertRegex(
            lab,
            r"function selectDraft\(name\)\s*\{[\s\S]*isEditorDirty\(\)",
        )


if __name__ == "__main__":
    unittest.main()
