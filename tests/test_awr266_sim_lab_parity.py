"""AWR-266: shared ledsim-player clock + sim/lab stage parity tripwires."""
from __future__ import annotations

import http.client
import shutil
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, build_handler  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_PATH = _ROOT / "config" / "led_look_director.example.json"
_PLAYER_JS = _ROOT / "tools" / "led_sim_assets" / "ledsim-player.js"
_VIEW_JS = _ROOT / "tools" / "led_sim_assets" / "ledsim-view.js"
_SIM_APP = _ROOT / "tools" / "led_sim_assets" / "sim-app.js"
_LAB_JS = _ROOT / "tools" / "led_pad_assets" / "lab.js"


class _FakePlayback:
    def status(self):
        return {"bridge_owned": False}


@contextmanager
def _pad_http(service: LedPadService):
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


class Awr266PlayerParityTests(unittest.TestCase):
    def test_player_module_exports_lab_formula_helpers(self) -> None:
        src = _PLAYER_JS.read_text(encoding="utf-8")
        self.assertIn("export function frameIndexAt", src)
        self.assertIn("export function startOffsetForFrame", src)
        self.assertIn("export function createFramePlayer", src)
        # Exact lab preview formula (AWR-266 binding).
        self.assertIn("Math.floor((ts - start) / 1000 * fps)", src)
        self.assertIn("ts - (Math.max(0, Number(frameIndex) || 0) / safeFps) * 1000", src)

    def test_sim_and_lab_import_shared_player(self) -> None:
        sim = _SIM_APP.read_text(encoding="utf-8")
        lab = _LAB_JS.read_text(encoding="utf-8")
        self.assertIn('from "./ledsim-player.js"', sim)
        self.assertIn("createFramePlayer", sim)
        self.assertIn('import("/static/sim/ledsim-player.js")', lab)
        self.assertIn("createFramePlayer", lab)
        # Old per-page screen clocks must not remain.
        self.assertNotIn("Holding the previous output for measured latency", sim)
        self.assertNotIn("applyMeasuredSlew", sim)
        self.assertNotIn("Math.floor((ts - start) / 1000 * preview.fps)", lab)

    def test_sim_defaults_to_presentation_mode(self) -> None:
        sim = _SIM_APP.read_text(encoding="utf-8")
        view = _VIEW_JS.read_text(encoding="utf-8")
        self.assertIn(
            'createLedSimView($("fixture-canvas"), state.profile, {presentation: true})',
            sim,
        )
        self.assertIn('view?.setPresentation(state.activeTab !== "layout")', sim)
        self.assertIn("setPresentation(next)", view)
        self.assertIn('presentation ? "end"', view)
        self.assertIn("if (presentation) return;", view)

    def test_pad_serves_player_js(self) -> None:
        self.assertTrue(_PLAYER_JS.is_file())
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            service = LedPadService(path, dry_run=True, playback=_FakePlayback())
            with _pad_http(service) as server:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                conn.request("GET", "/static/sim/ledsim-player.js")
                res = conn.getresponse()
                body = res.read()
                ctype = res.getheader("Content-Type") or ""
                conn.close()
        self.assertEqual(res.status, 200)
        self.assertIn("javascript", ctype.lower())
        self.assertEqual(body, _PLAYER_JS.read_bytes())
        self.assertIn(b"createFramePlayer", body)


if __name__ == "__main__":
    unittest.main()
