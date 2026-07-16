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

    def test_legacy_bank_tab_hides_when_empty(self) -> None:
        """AWR-265 FINAL: Legacy tab hidden when bank gone/empty — never errors."""
        src = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        self.assertIn('bank === "legacy_color_suffix"', src)
        self.assertIn("legacy_color_suffix) || []).length > 0", src)
        self.assertIn('state.activeBank = "drafts"', src)

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

    def test_awr267_add_corner_marks_layout_dirty(self) -> None:
        """Gate FIX: Add-corner must diverge live vs saved snapshot (dirty chip).

        Historical bug was NOT a shallow savedProfile snapshot. ensureLayoutLibrary
        rebuilt the active entry on every call; insertIndexForEdge/storedIndex re-enter
        ensure*, so `activeEntry().points_mm.splice(insertIndexForEdge(...), ...)`
        spliced an orphaned array and markDirty saw no change. Drag/remove assigned a
        new array onto a fresh activeEntry() and looked fine.
        """
        import json
        import subprocess

        script = r"""
const LAYOUT_KEYS = ["layouts", "active_layout"];
const DEFAULT_ROOM_MM = [5216, 2284];

function clone(value) {
  return typeof structuredClone === "function"
    ? structuredClone(value)
    : JSON.parse(JSON.stringify(value));
}
function pickKeys(profile, keys) {
  const out = {};
  for (const key of keys) {
    if (profile && Object.prototype.hasOwnProperty.call(profile, key)) out[key] = profile[key];
  }
  return out;
}
function makeLayoutEntry(source = {}) {
  const room = Array.isArray(source.room_mm) && source.room_mm.length === 2
    ? [Number(source.room_mm[0]), Number(source.room_mm[1])]
    : DEFAULT_ROOM_MM.slice();
  let points = source.points_mm;
  if (!Array.isArray(points) || points.length < 2) {
    points = [[0, 0], [10, 0], [10, 10], [0, 10]];
  }
  return {
    preset: source.preset || "perimeter",
    points_mm: points.map((point) => [Number(point[0]), Number(point[1])]),
    flip_chain: typeof source.flip_chain === "boolean" ? source.flip_chain : false,
    room_mm: room,
    layout_locked: typeof source.layout_locked === "boolean" ? source.layout_locked : false,
  };
}
function isStableLayoutEntry(entry) {
  return Boolean(
    entry
    && typeof entry === "object"
    && Array.isArray(entry.points_mm)
    && entry.points_mm.length >= 2
    && Array.isArray(entry.room_mm)
    && entry.room_mm.length === 2,
  );
}
function ensureLayoutLibrary(profile, {alwaysRebuild} = {}) {
  const entry = profile.layouts[profile.active_layout];
  if (alwaysRebuild || !isStableLayoutEntry(entry)) {
    profile.layouts[profile.active_layout] = makeLayoutEntry(entry && typeof entry === "object" ? entry : {});
  }
  return profile;
}

function layoutDirty(profile, saved) {
  return JSON.stringify(pickKeys(profile, LAYOUT_KEYS))
    !== JSON.stringify(pickKeys(saved, LAYOUT_KEYS));
}

function simulateAddCorner(alwaysRebuild) {
  const profile = {
    active_layout: "Home",
    layouts: {
      Home: makeLayoutEntry({
        points_mm: [[0, 0], [10, 0], [10, 10], [0, 10]],
        room_mm: [100, 100],
        preset: "perimeter",
      }),
    },
  };
  ensureLayoutLibrary(profile, {alwaysRebuild});
  const saved = clone(profile);
  ensureLayoutLibrary(saved, {alwaysRebuild});

  // Mirror the old call shape: base activeEntry() then arg insertIndexForEdge → ensure*.
  function activeEntry() {
    ensureLayoutLibrary(profile, {alwaysRebuild});
    return profile.layouts[profile.active_layout];
  }
  function insertIndexForEdge(edgeIndex) {
    ensureLayoutLibrary(profile, {alwaysRebuild}); // re-enter like production helper
    return edgeIndex + 1;
  }

  const mid = [5, 0];
  // Old buggy expression (orphan when alwaysRebuild):
  activeEntry().points_mm.splice(insertIndexForEdge(0), 0, mid);
  const orphanBugDirty = layoutDirty(profile, saved);
  const orphanLen = profile.layouts.Home.points_mm.length;

  // Fixed path used by addCornerFromButton: capture entry, then assign.
  const profile2 = {
    active_layout: "Home",
    layouts: {
      Home: makeLayoutEntry({
        points_mm: [[0, 0], [10, 0], [10, 10], [0, 10]],
        room_mm: [100, 100],
        preset: "perimeter",
      }),
    },
  };
  ensureLayoutLibrary(profile2, {alwaysRebuild: false});
  const saved2 = clone(profile2);
  function activeEntry2() {
    ensureLayoutLibrary(profile2, {alwaysRebuild: false});
    return profile2.layouts[profile2.active_layout];
  }
  function insertIndexForEdge2(edgeIndex) {
    ensureLayoutLibrary(profile2, {alwaysRebuild: false});
    return edgeIndex + 1;
  }
  const entry = activeEntry2();
  const insertAt = insertIndexForEdge2(0);
  entry.points_mm = [
    ...entry.points_mm.slice(0, insertAt),
    mid,
    ...entry.points_mm.slice(insertAt),
  ];
  entry.preset = "custom";

  return {
    orphanBugDirty,
    orphanLen,
    fixedDirty: layoutDirty(profile2, saved2),
    fixedLen: profile2.layouts.Home.points_mm.length,
    savedLen: saved2.layouts.Home.points_mm.length,
    samePointsRef: profile2.layouts.Home.points_mm === saved2.layouts.Home.points_mm,
  };
}

const broken = simulateAddCorner(true);
const fixed = simulateAddCorner(false);
console.log(JSON.stringify({broken, fixed}));
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
        # Prove the old always-rebuild ensure* path hides Add-corner from dirty.
        self.assertFalse(data["broken"]["orphanBugDirty"])
        self.assertEqual(data["broken"]["orphanLen"], 4)
        # Stable ensure* + assign path diverges the snapshot.
        self.assertTrue(data["fixed"]["fixedDirty"])
        self.assertEqual(data["fixed"]["fixedLen"], 5)
        self.assertEqual(data["fixed"]["savedLen"], 4)
        self.assertFalse(data["fixed"]["samePointsRef"])

        js = (_SIM / "sim-app.js").read_text(encoding="utf-8")
        self.assertIn("isStableLayoutEntry", js)
        self.assertIn("structuredClone", js)
        # Add-corner must assign a new points_mm array, not splice in the ensure*-arg expression.
        self.assertIn("entry.points_mm = [", js)
        self.assertNotIn(
            "activeEntry().points_mm.splice(insertIndexForEdge",
            js,
        )



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
