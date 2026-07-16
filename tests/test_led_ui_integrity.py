"""AWR-258/259 static UI integrity checks (no browser required)."""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
        self.assertIn("Undo all changes", src)
        self.assertIn("EVERY unsaved-to-show edit across", src)
        # AWR-260 E: dirty count from live editor+draft state at modal-open.
        self.assertIn("snapshotEditor() !== state.cleanSnapshot", src)
        self.assertIn('drafts: "Untagged"', src)

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
        # AWR-260: Accept wires into production; Reject stays out of the show.
        self.assertIn("Live —", lab)
        self.assertIn("Rejected — stays out of the show", lab)

    def test_look_groups_shelf_references_real_looks(self) -> None:
        # GROUPSHELF: every data-look in the sim shelf must be a real saved look,
        # and each must be wired to the render path. Breaks if a look is renamed.
        from rb_ss_bridge_v2.tools.led_sim_engine import look_params_catalog

        html = (_SIM / "index.html").read_text(encoding="utf-8")
        js = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        shelf_looks = re.findall(r'data-look="([^"]+)"', html)
        self.assertTrue(shelf_looks, "no data-look buttons found in sim index.html")

        catalog = look_params_catalog()
        self.assertTrue(catalog["ok"], catalog.get("error"))
        known = set(catalog["looks"])
        for name in shelf_looks:
            self.assertIn(name, known, f"shelf look {name!r} not in look catalog")

        self.assertIn('querySelectorAll("[data-look]")', js)
        self.assertIn("playLookByName", js)

    def test_awr267_layout_corner_buttons_wired(self) -> None:
        """R6: Add/Remove corner buttons exist and handlers are attached."""
        html = (_SIM / "index.html").read_text(encoding="utf-8")
        js = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        self.assertIn('id="layout-add-corner"', html)
        self.assertIn('id="layout-remove-corner"', html)
        self.assertIn(">Add corner<", html)
        self.assertIn(">Remove corner<", html)
        self.assertIn('id="layout-dirty"', html)
        # Unsaved warning lives in the header, not only the Layout panel.
        self.assertLess(
            html.index('id="layout-dirty"'),
            html.index('id="layout-panel"'),
        )
        self.assertIn('id="help-what-is"', html)
        self.assertIn("never turns the real lights on", html)
        self.assertIn("addCornerFromButton", js)
        self.assertIn("removeCornerFromButton", js)
        self.assertIn(
            '$("layout-add-corner")?.addEventListener("click", addCornerFromButton)',
            js,
        )
        self.assertIn(
            '$("layout-remove-corner")?.addEventListener("click", removeCornerFromButton)',
            js,
        )
        # Existing dblclick path must remain (human check still pending).
        self.assertIn('canvas.addEventListener("dblclick"', js)
        self.assertIn("Puts the corners back to the saved", js)
        self.assertIn("Your unsaved layout changes go away", js)


class Awr267LayoutCornerMathTests(unittest.TestCase):
    """Unit-level midpoint insert + minimum-corner guard (JS helpers via node)."""

    def test_midpoint_insert_and_min_corner_guard(self) -> None:
        import json
        import subprocess

        script = r"""
import {
  canRemoveCorner,
  insertCornerAtEdgeMidpoint,
  longestEdgeIndex,
  midpointOnEdge,
  MIN_LAYOUT_CORNERS,
  removeCornerAt,
} from './tools/led_sim_assets/ledsim-view.js';

const points = [[0, 0], [10, 0], [10, 10]];
const mid = midpointOnEdge(points, 0);
const inserted = insertCornerAtEdgeMidpoint(points, 0);
const removed = removeCornerAt(inserted, 1);
const blocked = removeCornerAt([[0, 0], [1, 1]], 0);
const longest = longestEdgeIndex([[0, 0], [1, 0], [1, 100]]);

console.log(JSON.stringify({
  min: MIN_LAYOUT_CORNERS,
  mid,
  inserted,
  removed,
  blocked,
  canTwo: canRemoveCorner([[0, 0], [1, 1]]),
  canThree: canRemoveCorner(points),
  longest,
}));
"""
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(data["min"], 2)
        self.assertEqual(data["mid"], [5, 0])
        self.assertEqual(data["inserted"], [[0, 0], [5, 0], [10, 0], [10, 10]])
        self.assertEqual(data["removed"], [[0, 0], [10, 0], [10, 10]])
        self.assertIsNone(data["blocked"])
        self.assertFalse(data["canTwo"])
        self.assertTrue(data["canThree"])
        self.assertEqual(data["longest"], 1)


if __name__ == "__main__":
    unittest.main()
