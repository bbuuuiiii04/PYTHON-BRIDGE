"""AWR-258/259 static UI integrity checks (no browser required)."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_ASSETS = Path(__file__).resolve().parents[1] / "tools" / "led_pad_assets"
_SIM = Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets"


def _js_string_array(src: str, const_name: str) -> list[str]:
    match = re.search(
        rf"const\s+{re.escape(const_name)}\s*=\s*\[([^\]]*)\]",
        src,
    )
    if match is None:
        raise AssertionError(f"missing const {const_name}")
    raw = "[" + match.group(1) + "]"
    # JS string array → Python via JSON-ish: double quotes only.
    return list(ast.literal_eval(raw.replace("'", '"')))


class PadUiIntegrityTests(unittest.TestCase):
    def test_editor_fields_constant_drives_payload_and_save(self) -> None:
        """AWR-259: one EDITOR_FIELDS list; save + dirty snapshot must use it."""
        src = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        fields = _js_string_array(src, "EDITOR_FIELDS")
        self.assertEqual(
            fields,
            ["look", "params", "cue_beats", "slot_fill", "mono_chance", "locked_palette"],
        )
        self.assertIn("for (const key of EDITOR_FIELDS)", src)
        # Both editorPayload and saveCurrentEditor iterate EDITOR_FIELDS.
        self.assertGreaterEqual(src.count("EDITOR_FIELDS"), 3)
        self.assertIn('error === "stale_look"', src)
        self.assertIn(
            "Someone else edited this look — reload to get the latest, then re-apply",
            src,
        )
        self.assertIn("Discard all changes", src)
        self.assertIn("EVERY unsaved-to-show edit across", src)

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

    def test_lab_accept_fallback_note_present(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        html = (_ASSETS / "lab.html").read_text(encoding="utf-8")
        self.assertIn("acceptFallbackNote", lab)
        self.assertIn("snapshot_fallback", lab)
        self.assertIn(
            "Accepted saved values — your last live-tuned values weren't available",
            html,
        )
        self.assertIn('id="acceptFallbackNote"', html)


if __name__ == "__main__":
    unittest.main()
