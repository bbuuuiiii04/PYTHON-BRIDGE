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
        self.assertIn("unsaved Pad look edit across", src)
        # AWR-260 E: dirty count from live editor+draft state at modal-open.
        self.assertIn("snapshotEditor() !== state.cleanSnapshot", src)
        self.assertIn('drafts: "Untagged"', src)
        # AWR-272: scary Save-to-show primary path is gone.
        self.assertNotIn("Save to show", src)
        self.assertNotIn("Bridge restart required", src)
        self.assertIn("Push pad edits", src)

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
        # AWR-260/272: Accept wires into production; Reject stays out of the show.
        self.assertIn("Added to your show", lab)
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


def _route_tab_hrefs(html: str) -> dict[str, str]:
    """Map Pad/Lab/Sim label → href inside the first route-tabs nav."""
    nav = re.search(
        r'<nav class="route-tabs"[^>]*>(.*?)</nav>',
        html,
        flags=re.S,
    )
    if nav is None:
        raise AssertionError("missing route-tabs nav")
    found = re.findall(
        r'<a\b([^>]*)>(Pad|Lab|Sim)</a>',
        nav.group(1),
    )
    out: dict[str, str] = {}
    for attrs, label in found:
        href_m = re.search(r'href="([^"]+)"', attrs)
        if href_m is None:
            raise AssertionError(f"{label} tab missing href")
        out[label] = href_m.group(1)
    return out


def _id_not_hidden(html: str, element_id: str) -> None:
    """Assert id=… exists and that opening tag is not marked hidden."""
    match = re.search(
        rf'<(?P<tag>\w+)\b(?P<attrs>[^>]*\bid="{re.escape(element_id)}"[^>]*)>',
        html,
    )
    if match is None:
        raise AssertionError(f"missing #{element_id}")
    attrs = match.group("attrs")
    if re.search(r"\bhidden\b", attrs):
        raise AssertionError(f"#{element_id} is hidden on initial markup")


class Awr270OneShellTests(unittest.TestCase):
    """R8 chrome: shared Pad|Lab|Sim nav (N9 hrefs) + honest landings."""

    def test_shared_nav_hrefs_n9(self) -> None:
        pad = (_ASSETS / "index.html").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.html").read_text(encoding="utf-8")
        sim = (_SIM / "index.html").read_text(encoding="utf-8")

        pad_tabs = _route_tab_hrefs(pad)
        lab_tabs = _route_tab_hrefs(lab)
        sim_tabs = _route_tab_hrefs(sim)

        self.assertEqual(pad_tabs, {"Pad": "/", "Lab": "/lab", "Sim": "http://127.0.0.1:8767/"})
        self.assertEqual(lab_tabs, {"Pad": "/", "Lab": "/lab", "Sim": "http://127.0.0.1:8767/"})
        self.assertEqual(
            sim_tabs,
            {
                "Pad": "http://127.0.0.1:8766/",
                "Lab": "http://127.0.0.1:8766/lab",
                "Sim": "http://127.0.0.1:8767/",
            },
        )
        # Pad↔lab must stay relative; no absolute :8766 self-links on pad server pages.
        self.assertNotIn("127.0.0.1:8766", pad)
        self.assertNotIn("127.0.0.1:8766", lab)
        for html in (pad, lab, sim):
            self.assertIn("LIGHTING CONSOLE", html)
            self.assertIn('class="eyebrow"', html)

    def test_landing_containers_present_not_hidden(self) -> None:
        pad = (_ASSETS / "index.html").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.html").read_text(encoding="utf-8")
        sim = (_SIM / "index.html").read_text(encoding="utf-8")

        _id_not_hidden(pad, "lookGrid")
        _id_not_hidden(lab, "draftList")
        _id_not_hidden(lab, "labPreviewHero")
        _id_not_hidden(sim, "stage")
        _id_not_hidden(sim, "fixture-canvas")
        # R5/R6 jargon / page-purpose must not regress.
        self.assertIn('id="help-what-is"', sim)
        self.assertIn("never turns the real lights on", sim)
        self.assertIn('id="help-btn"', sim)
        # AWR-271: lab help lives in the shared shell; visibility is view-toggled.
        self.assertIn('id="labHelpBtn"', lab)
        self.assertIn("labHelpBtn", (_ASSETS / "shell.js").read_text(encoding="utf-8"))

    def test_pad_landing_bank_prefers_content(self) -> None:
        src = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        self.assertIn("function pickLandingBank()", src)
        self.assertIn("state.landingPicked", src)
        self.assertIn("No looks yet", src)
        self.assertIn("Nothing in this shelf", src)
        # Preference order: phrase banks before empty drafts.
        self.assertLess(src.index("bank !== \"drafts\""), src.index("state.banks.drafts"))

    def test_lab_empty_landing_copy(self) -> None:
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        self.assertIn("No drafts yet — press New to make one.", lab)
        self.assertIn("Press New to make one, or clear the filters above.", lab)

    def test_initial_get_serves_landing_shell(self) -> None:
        import http.client
        import tempfile
        import threading
        from contextlib import contextmanager
        from http.server import ThreadingHTTPServer

        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler as pad_handler
        from rb_ss_bridge_v2.tools.led_sim_web import LedSimService, build_handler as sim_handler

        example = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"

        @contextmanager
        def _pad():
            with tempfile.TemporaryDirectory() as td:
                cfg = Path(td) / "led_look_director.json"
                cfg.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
                service = LedPadService(cfg, dry_run=True)
                server = ThreadingHTTPServer(("127.0.0.1", 0), pad_handler(service))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    yield server.server_port
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2.0)

        @contextmanager
        def _sim():
            with tempfile.TemporaryDirectory() as td:
                profile = Path(td) / "led_sim_profile.json"
                service = LedSimService(profile_path=profile)
                server = ThreadingHTTPServer(("127.0.0.1", 0), sim_handler(service))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    yield server.server_port
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2.0)

        def _get(port: int, path: str) -> str:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            res = conn.getresponse()
            body = res.read().decode("utf-8")
            status = res.status
            conn.close()
            self.assertEqual(status, 200, path)
            return body

        with _pad() as port:
            pad_html = _get(port, "/")
            lab_html = _get(port, "/lab")
        with _sim() as port:
            sim_html = _get(port, "/")

        self.assertEqual(_route_tab_hrefs(pad_html)["Sim"], "http://127.0.0.1:8767/")
        self.assertEqual(_route_tab_hrefs(lab_html)["Pad"], "/")
        self.assertEqual(_route_tab_hrefs(sim_html)["Pad"], "http://127.0.0.1:8766/")
        _id_not_hidden(pad_html, "lookGrid")
        _id_not_hidden(lab_html, "draftList")
        _id_not_hidden(sim_html, "stage")
        # AWR-271: / and /lab serve the same shell document (not a redirect).
        self.assertIn('data-shell="lighting"', pad_html)
        self.assertIn('data-shell="lighting"', lab_html)
        self.assertIn('id="view-lab"', pad_html)
        self.assertIn('id="view-pad"', lab_html)


class Awr271LabInShellTests(unittest.TestCase):
    """R9a: Lab editor mounts inside Pad shell; /lab still serves the same component."""

    def test_shared_shell_markup_and_scripts(self) -> None:
        html = (_ASSETS / "index.html").read_text(encoding="utf-8")
        lab_link = (_ASSETS / "lab.html")
        shell = (_ASSETS / "shell.js").read_text(encoding="utf-8")
        lab_js = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        pad_js = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        core = (_ASSETS / "pad-core.js").read_text(encoding="utf-8")

        # One document hosts both views + shared chrome.
        self.assertIn('data-shell="lighting"', html)
        self.assertIn('id="view-pad"', html)
        self.assertIn('id="view-lab"', html)
        self.assertIn('data-shell-view="pad"', html)
        self.assertIn('data-shell-view="lab"', html)
        self.assertIn("/static/shell.js", html)
        self.assertIn("/static/lab.js", html)
        self.assertIn("/static/pad-ui.js", html)
        # Lab disk entry is the shared shell (symlink or identical bytes).
        self.assertTrue(lab_link.is_symlink() or lab_link.read_text(encoding="utf-8") == html)
        if lab_link.is_symlink():
            self.assertEqual(lab_link.resolve(), (_ASSETS / "index.html").resolve())

        # Shell switches views without full navigation for Pad↔Lab.
        self.assertIn("history.pushState", shell)
        self.assertIn("data-shell-view", shell)
        self.assertIn("lab-route", shell)
        self.assertNotIn("iframe", shell)

        # One Lab store export; Accept path untouched (still labAccept).
        self.assertIn("window.LabEditor", lab_js)
        self.assertIn("api.labAccept", lab_js)
        self.assertIn("isEditorDirty()", lab_js)
        self.assertIn("beforeunload", lab_js)
        self.assertIn('error === "stale_entry"', lab_js)
        self.assertIn("shellShared", lab_js)

        # Pad STOP reaches Lab beat meter via shared export.
        self.assertIn("LabEditor.onEmergencyStop", pad_js)
        # PadHealth accepts multiple subscribers (pad + lab).
        self.assertIn("state.subs", core)
        self.assertIn("state.subs.push", core)

    def test_integrity_behaviors_still_present_on_merged_component(self) -> None:
        """AWR-258/259/260 loss scenarios must still be wired in the shared lab.js."""
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        html = (_ASSETS / "index.html").read_text(encoding="utf-8")

        # Lab lock+CAS / stale flows.
        self.assertIn("stale_entry", lab)
        self.assertIn("updated", lab)
        # Discard / dirty scope.
        self.assertIn("isEditorDirty()", lab)
        self.assertIn("EDITOR_FIELDS", pad)
        self.assertIn("locked_palette", pad)
        self.assertIn('error === "stale_look"', pad)
        self.assertIn("Undo all changes", pad)
        # Accept still present in UI + JS (AWR-260 wire-in); AWR-272 verb pair copy.
        self.assertIn('id="acceptBtn"', html)
        self.assertIn("labAccept", lab)
        self.assertIn("Added to your show", lab)
        self.assertIn("Save draft", html)
        self.assertIn("Accept — adds it to your show", html)
        self.assertNotIn("Save to show", html)
        self.assertIn("snapshot_fallback", lab)
        for label, src in (("lab.js", lab), ("pad-ui.js", pad)):
            self.assertIn("beforeunload", src, f"{label} missing beforeunload")

    def test_lab_and_root_serve_identical_shell(self) -> None:
        import http.client
        import tempfile
        import threading
        from contextlib import contextmanager
        from http.server import ThreadingHTTPServer

        from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler as pad_handler

        example = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"

        @contextmanager
        def _pad():
            with tempfile.TemporaryDirectory() as td:
                cfg = Path(td) / "led_look_director.json"
                cfg.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
                service = LedPadService(cfg, dry_run=True)
                server = ThreadingHTTPServer(("127.0.0.1", 0), pad_handler(service))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    yield server.server_port
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2.0)

        def _get(port: int, path: str) -> tuple[int, str]:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            res = conn.getresponse()
            body = res.read().decode("utf-8")
            status = res.status
            conn.close()
            return status, body

        with _pad() as port:
            st_root, root = _get(port, "/")
            st_lab, lab = _get(port, "/lab")
        self.assertEqual(st_root, 200)
        self.assertEqual(st_lab, 200)
        # Not a redirect — same shell body (R9c is when /lab becomes redirect-only).
        self.assertEqual(root, lab)
        self.assertIn('data-shell="lighting"', root)
        self.assertIn('id="view-lab"', root)
        self.assertIn('id="acceptBtn"', root)
        self.assertIn("/static/shell.js", root)


class Awr272VerbPairTests(unittest.TestCase):
    """R9b: Save draft + Accept are the operator pair; retired primary verbs gone."""

    def test_primary_verb_pair_and_retired_primary_copy(self) -> None:
        html = (_ASSETS / "index.html").read_text(encoding="utf-8")
        pad = (_ASSETS / "pad-ui.js").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")

        # Primary Lab pair (musician-legible).
        self.assertIn(">Save draft<", html)
        self.assertIn("Accept — adds it to your show", html)
        self.assertIn("Reject — keep out of show", html)
        self.assertIn('id="saveDraftBtn"', html)
        self.assertIn('id="acceptBtn"', html)
        self.assertIn("api.labSave", lab)
        self.assertIn("api.labAccept", lab)
        self.assertIn("Rejected — stays out of the show", lab)

        # Status chips survive.
        for chip in ("Work in progress", "Accepted", "Rejected"):
            self.assertIn(chip, html)

        # Retired scary primary path.
        for banned in (
            "Save to show",
            "Save draft to the show",
            "live show file",
            "Bridge restart required",
            "bridge restart required",
        ):
            self.assertNotIn(banned, html)
            self.assertNotIn(banned, pad)

        # Pad push demoted to secondary menu (not a headline primary).
        self.assertIn('id="padMoreActions"', html)
        self.assertIn("Push pad edits", html)
        # commitBtn must not be class=primary anymore.
        commit_line = [ln for ln in html.splitlines() if 'id="commitBtn"' in ln][0]
        self.assertNotIn("primary", commit_line)
        self.assertIn("ghost", commit_line)

        # Reload stays secondary/dev-ish with plain words.
        self.assertIn("Reload effect code", html)
        self.assertNotIn("Reload code</button>", html)

        # Integrity wiring untouched.
        self.assertIn('error === "stale_entry"', lab)
        self.assertIn('error === "stale_look"', pad)
        self.assertIn("locked_palette", pad)

    def test_accept_messages_plain_english(self) -> None:
        from rb_ss_bridge_v2.tools import led_pad_web as web

        src = Path(web.__file__).read_text(encoding="utf-8")
        self.assertIn("In your show —", src)
        self.assertIn("your lights will use them at the next bridge start", src)
        self.assertNotIn("Bridge restart required", src)
        self.assertNotIn("Committed - bridge restart required", src)
