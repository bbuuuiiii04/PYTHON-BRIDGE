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

        self.assertEqual(pad_tabs, {"Pad": "/", "Lab": "/?view=lab", "Sim": "http://127.0.0.1:8767/"})
        self.assertEqual(lab_tabs, {"Pad": "/", "Lab": "/?view=lab", "Sim": "http://127.0.0.1:8767/"})
        self.assertEqual(
            sim_tabs,
            {
                "Pad": "http://127.0.0.1:8766/",
                "Lab": "http://127.0.0.1:8766/?view=lab",
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

        def _get(port: int, path: str, *, allow_redirect: bool = False) -> tuple[int, str, str | None]:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            res = conn.getresponse()
            body = res.read().decode("utf-8")
            status = res.status
            location = res.getheader("Location")
            conn.close()
            if not allow_redirect:
                self.assertEqual(status, 200, path)
            return status, body, location

        with _pad() as port:
            _st, pad_html, _loc = _get(port, "/")
            st_lab, _lab_body, lab_loc = _get(port, "/lab", allow_redirect=True)
            _st2, lab_view, _loc2 = _get(port, "/?view=lab")
        with _sim() as port:
            _st3, sim_html, _loc3 = _get(port, "/")

        self.assertEqual(st_lab, 302)
        self.assertEqual(lab_loc, "/?view=lab")
        self.assertEqual(_route_tab_hrefs(pad_html)["Sim"], "http://127.0.0.1:8767/")
        self.assertEqual(_route_tab_hrefs(lab_view)["Pad"], "/")
        self.assertEqual(_route_tab_hrefs(lab_view)["Lab"], "/?view=lab")
        self.assertEqual(_route_tab_hrefs(sim_html)["Pad"], "http://127.0.0.1:8766/")
        self.assertEqual(_route_tab_hrefs(sim_html)["Lab"], "http://127.0.0.1:8766/?view=lab")
        _id_not_hidden(pad_html, "lookGrid")
        _id_not_hidden(lab_view, "draftList")
        _id_not_hidden(sim_html, "stage")
        # AWR-273: shell document is on / (+ /?view=lab); /lab is redirect-only.
        self.assertIn('data-shell="lighting"', pad_html)
        self.assertIn('data-shell="lighting"', lab_view)
        self.assertIn('id="view-lab"', pad_html)
        self.assertIn('id="view-pad"', lab_view)


class Awr271LabInShellTests(unittest.TestCase):
    """R9a: Lab editor mounts inside Pad shell; R9c redirects /lab → /?view=lab."""

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
        self.assertIn('href="/?view=lab"', html)
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
        self.assertIn("/?view=lab", shell)
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

    def test_root_serves_shell_and_lab_path_redirects(self) -> None:
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

        def _get(port: int, path: str) -> tuple[int, str, str | None]:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path)
            res = conn.getresponse()
            body = res.read().decode("utf-8")
            status = res.status
            location = res.getheader("Location")
            conn.close()
            return status, body, location

        with _pad() as port:
            st_root, root, _ = _get(port, "/")
            st_lab, _lab, lab_loc = _get(port, "/lab")
            st_view, view, _ = _get(port, "/?view=lab")
        self.assertEqual(st_root, 200)
        self.assertEqual(st_lab, 302)
        self.assertEqual(lab_loc, "/?view=lab")
        self.assertEqual(st_view, 200)
        self.assertEqual(root, view)
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


class Awr273SingleLiveFireTests(unittest.TestCase):
    """R9c: lab Play-once (loop off) + /lab 302 → /?view=lab; pad tile Play stays primary live-fire."""

    def test_lab_play_once_ui_and_shell_redirect_wiring(self) -> None:
        html = (_ASSETS / "index.html").read_text(encoding="utf-8")
        lab = (_ASSETS / "lab.js").read_text(encoding="utf-8")
        shell = (_ASSETS / "shell.js").read_text(encoding="utf-8")
        web = Path(__file__).resolve().parents[1] / "tools" / "led_pad_web.py"
        web_src = web.read_text(encoding="utf-8")
        sim = (_SIM / "index.html").read_text(encoding="utf-8")

        # Preview is the headline verb; Play-once is secondary + clearly labeled.
        preview_line = [ln for ln in html.splitlines() if 'id="previewBtn"' in ln][0]
        play_line = [ln for ln in html.splitlines() if 'id="playDraftBtn"' in ln][0]
        self.assertIn("primary", preview_line)
        self.assertNotIn("primary", play_line)
        self.assertIn("Play once on lights", html)
        self.assertIn("Play once sends to the real lights", html)
        self.assertIn('id="stopDraftBtn"', html)
        self.assertIn("Play once on lights", lab)
        self.assertIn("lab-stop-armed", lab)

        # Shell + sim land on /?view=lab (no double-hop for sim).
        self.assertIn("/?view=lab", shell)
        self.assertIn('href="/?view=lab"', html)
        self.assertIn("http://127.0.0.1:8766/?view=lab", sim)
        self.assertNotIn("http://127.0.0.1:8766/lab\"", sim)
        self.assertIn('HTTPStatus.FOUND', web_src)
        self.assertIn('"/?view=lab"', web_src)
        # Lab play forces one-shot; does not mutate session via set_loop for this path.
        self.assertIn("loop=False", web_src)
        self.assertIn("lab live-fire is always one-shot", web_src)

    def test_lab_redirect_http_302(self) -> None:
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

        with _pad() as port:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/lab")
            res = conn.getresponse()
            body = res.read()
            status = res.status
            location = res.getheader("Location")
            conn.close()
            self.assertEqual(status, 302)
            self.assertEqual(location, "/?view=lab")
            self.assertEqual(body, b"")
            # Destination must be the shell (never 404).
            conn2 = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn2.request("GET", "/?view=lab")
            res2 = conn2.getresponse()
            html = res2.read().decode("utf-8")
            self.assertEqual(res2.status, 200)
            conn2.close()
            self.assertIn('data-shell="lighting"', html)
            self.assertIn('id="view-lab"', html)
            self.assertIn("Play once on lights", html)


# AWR-274 R11 — banned telemetry strings must not appear on cold main screens.
# Keep this list explicit: cold HTML outside Diagnostics / Setup must stay clean.
_AWR274_BANNED_COLD = (
    "FPS",
    "DRAW",
    "WAITING",
    "60 seg",
    "360 LEDs",
    "41.656",
    "mm/LED",
    "Real show engine",
    "Source ·",
    "not loaded yet",
)


def _strip_diagnostics_and_setup(html: str) -> str:
    """Remove Diagnostics corners + Setup panel bodies (telemetry may live there)."""
    out = re.sub(
        r'<details\b[^>]*\bid="diagnostics"[^>]*>.*?</details>',
        "",
        html,
        flags=re.S | re.I,
    )
    # Nested sections inside Setup — cut from opening tag through the close marker.
    marker = "<!-- #setup-panel -->"
    start = re.search(r'<section\b[^>]*\bid="setup-panel"[^>]*>', out, flags=re.I)
    if start and marker in out[start.start():]:
        end = out.index(marker, start.start()) + len(marker)
        out = out[: start.start()] + out[end:]
    # Scripts / help dialogs are not cold main chrome.
    out = re.sub(r"<script\b[^>]*>.*?</script>", "", out, flags=re.S | re.I)
    out = re.sub(
        r'<div\b[^>]*\bid="help-popover"[^>]*>.*?</div>',
        "",
        out,
        flags=re.S | re.I,
    )
    out = re.sub(
        r'<div\b[^>]*\bid="labHelpPopover"[^>]*>.*?</div>',
        "",
        out,
        flags=re.S | re.I,
    )
    return out


class Awr274SetupDiagnosticsTests(unittest.TestCase):
    """R11 remainder: Setup demotion + Diagnostics corner + cold-screen gate."""

    def test_sim_setup_demotes_layout_and_calibrate(self) -> None:
        html = (_SIM / "index.html").read_text(encoding="utf-8")
        js = (_SIM / "sim-app.js").read_text(encoding="utf-8")

        self.assertIn('id="tab-setup"', html)
        self.assertIn(">Setup<", html)
        self.assertIn('id="setup-panel"', html)
        self.assertIn('id="setup-tab-layout"', html)
        self.assertIn('id="setup-tab-calibrate"', html)
        # Top-level Layout/Calibrate tabs are gone (D2 bury-not-delete).
        self.assertNotIn('id="tab-layout"', html)
        self.assertNotIn('id="tab-calibrate"', html)
        self.assertIn('data-tab="setup"', html)
        # Nested panels + save path IDs preserved.
        self.assertIn('id="layout-panel"', html)
        self.assertIn('id="calibrate-panel"', html)
        self.assertIn('id="layout-add-corner"', html)
        self.assertIn('id="profile-save"', html)
        self.assertIn('id="knob-gamma"', html)
        # Advanced fold is closed by default + plain caution.
        self.assertIn("Advanced — screen color matching", html)
        self.assertIn("Defaults are fine for everyday use", html)
        calib = re.search(
            r'<details class="advanced calibration-controls"[^>]*>',
            html,
        )
        self.assertIsNotNone(calib)
        self.assertNotIn(" open", calib.group(0))

        # activeTab remains play|layout|calibrate for AWR-266 presentation.
        self.assertIn('view?.setPresentation(state.activeTab !== "layout")', js)
        self.assertIn('if (next === "setup")', js)
        self.assertIn('id="layout-dirty"', html)
        self.assertLess(html.index('id="layout-dirty"'), html.index('id="layout-panel"'))

    def test_diagnostics_corners_collapsed(self) -> None:
        sim = (_SIM / "index.html").read_text(encoding="utf-8")
        pad = (_ASSETS / "index.html").read_text(encoding="utf-8")
        shell = (_ASSETS / "shell.js").read_text(encoding="utf-8")

        for label, html in (("sim", sim), ("pad", pad)):
            match = re.search(
                r'<details\b([^>]*)\bid="diagnostics"([^>]*)>',
                html,
            )
            self.assertIsNotNone(match, f"{label} missing #diagnostics")
            attrs = match.group(1) + match.group(2)
            self.assertNotIn(" open", attrs, f"{label} Diagnostics must start collapsed")
            self.assertIn(">Diagnostics<", html)

        # Sim telemetry IDs live inside diagnostics.
        diag_block = re.search(
            r'<details\b[^>]*\bid="diagnostics"[^>]*>.*?</details>',
            sim,
            flags=re.S,
        )
        self.assertIsNotNone(diag_block)
        body = diag_block.group(0)
        for needle in (
            'id="fps-chip"',
            'id="paint-health"',
            'id="pipeline-badge"',
            'id="timing-readout"',
            'id="frame-label"',
            "60 seg",
            "41.656",
        ):
            self.assertIn(needle, body)

        # Beat meter stays a musician tool on the lab editor (not in Diagnostics).
        self.assertIn('id="beatMeter"', pad)
        pad_diag = re.search(
            r'<details\b[^>]*\bid="diagnostics"[^>]*>.*?</details>',
            pad,
            flags=re.S,
        )
        self.assertIsNotNone(pad_diag)
        self.assertNotIn('id="beatMeter"', pad_diag.group(0))

        # Shell shows Diagnostics on Lab only; never forces it open.
        self.assertIn('diag.hidden = !isLab', shell)
        self.assertNotIn('health.hidden = !isLab', shell)

    def test_cold_screens_zero_telemetry_strings(self) -> None:
        sim = (_SIM / "index.html").read_text(encoding="utf-8")
        pad = (_ASSETS / "index.html").read_text(encoding="utf-8")

        for label, html in (("sim Play", sim), ("pad/lab shell", pad)):
            cold = _strip_diagnostics_and_setup(html)
            for banned in _AWR274_BANNED_COLD:
                self.assertNotIn(
                    banned,
                    cold,
                    f"{label} cold chrome still contains banned telemetry {banned!r}",
                )

    def test_calibrate_value_round_trip_via_profile_save(self) -> None:
        """Change a calibrate knob value → Save → reload → persisted (API path)."""
        import json
        import tempfile
        import threading
        from contextlib import contextmanager
        from http.server import ThreadingHTTPServer

        from rb_ss_bridge_v2.tools.led_sim_web import LedSimService, build_handler

        example = Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json"

        @contextmanager
        def _sim():
            with tempfile.TemporaryDirectory() as td:
                profile = Path(td) / "led_sim_profile.json"
                profile.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
                service = LedSimService(profile_path=profile)
                server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    yield server.server_port, profile
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2.0)

        def _req(port: int, method: str, path: str, body=None):
            import http.client

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            raw = None if body is None else json.dumps(body).encode("utf-8")
            headers = {"Content-Type": "application/json"} if raw is not None else {}
            conn.request(method, path, body=raw, headers=headers)
            res = conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))
            status = res.status
            conn.close()
            return status, data

        with _sim() as (port, profile_path):
            st, before = _req(port, "GET", "/api/profile")
            self.assertEqual(st, 200)
            prof = before["profile"]
            original = float(prof.get("gamma", 1.0))
            changed = round(original + 0.37, 2)
            if changed == original:
                changed = round(original + 0.41, 2)
            prof["gamma"] = changed
            st, saved = _req(port, "POST", "/api/profile", prof)
            self.assertEqual(st, 200, saved)
            self.assertTrue(saved.get("ok"))
            st, after = _req(port, "GET", "/api/profile")
            self.assertEqual(st, 200)
            self.assertAlmostEqual(float(after["profile"]["gamma"]), changed, places=2)
            # Disk persistence (reload story).
            disk = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(float(disk["gamma"]), changed, places=2)

        # UI still wires Save values inside Setup → Calibrate advanced fold.
        html = (_SIM / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="setup-panel"'), html.index('id="profile-save"'))
        self.assertLess(html.index("Advanced — screen color matching"), html.index('id="knob-gamma"'))
        self.assertLess(html.index('id="knob-gamma"'), html.index('id="profile-save"'))


if __name__ == "__main__":
    unittest.main()

