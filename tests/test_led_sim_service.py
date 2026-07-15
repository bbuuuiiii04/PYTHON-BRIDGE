from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import led_sim_engine  # noqa: E402
from rb_ss_bridge_v2.tools.led_sim_web import LedSimService, build_handler  # noqa: E402


@contextmanager
def _server(profile_path: Path):
    service = LedSimService(profile_path=profile_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    payload = json.dumps(body) if body is not None else None
    headers = {"Content-Type": "application/json"} if payload else {}
    conn.request(method, path, payload, headers)
    response = conn.getresponse()
    data = json.loads(response.read())
    conn.close()
    return response.status, data


class LedSimServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.profile_path = Path(self._tmp.name) / "led_sim_profile.json"

    def test_catalog_shape(self) -> None:
        with _server(self.profile_path) as port:
            status, catalog = _request(port, "GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertTrue(catalog["effects"])
        self.assertIn("beat_chase", catalog["effects"])
        self.assertEqual(catalog["profile"]["segments"], 60)
        self.assertEqual(catalog["device"]["physical_leds"], 360)
        self.assertEqual(catalog["device"]["leds_per_segment"], 6)
        self.assertIn("timing_response", catalog["calibration_sequences"])
        self.assertEqual(catalog["profile_error"], "")
        self.assertIn("looks", catalog)
        self.assertIn("lab", catalog)

    def test_render_counts_and_caps(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/render", {
                "source": "effect", "name": "beat_chase", "duration_s": 1, "fps": 30,
            })
            self.assertEqual(status, 200)
            self.assertEqual(len(result["frames"]), 30)  # fps * duration
            self.assertEqual(result["segments"], 60)
            self.assertTrue(all(len(frame) == 60 for frame in result["frames"]))
            self.assertEqual(len(result["t_ms"]), 30)
            self.assertEqual(result["pipeline"], "runtime")

            status, result = _request(port, "POST", "/api/render", {
                "source": "effect", "name": "beat_chase", "duration_s": 31,
            })
            self.assertEqual(status, 400)
            self.assertIn("duration_s", result["error"])

            status, result = _request(port, "POST", "/api/render", {
                "source": "effect", "name": "beat_chase", "duration_s": 1, "fps": 121,
            })
            self.assertEqual(status, 400)
            self.assertIn("fps", result["error"])

    def test_profile_post_validate_reject_writes_nothing(self) -> None:
        with _server(self.profile_path) as port:
            _, current = _request(port, "GET", "/api/profile")
            bad = dict(current["profile"])
            bad["gamma"] = 99
            status, result = _request(port, "POST", "/api/profile", bad)
        self.assertEqual(status, 400)
        self.assertTrue(any("gamma" in error for error in result["errors"]))
        self.assertFalse(self.profile_path.exists())

    def test_profile_post_valid_roundtrip(self) -> None:
        with _server(self.profile_path) as port:
            _, current = _request(port, "GET", "/api/profile")
            good = dict(current["profile"])
            good["gamma"] = 2.2
            good["operator_note"] = "kept"
            status, result = _request(port, "POST", "/api/profile", good)
            self.assertEqual(status, 200)
            self.assertTrue(result["ok"])
            _, after = _request(port, "GET", "/api/profile")
        self.assertTrue(self.profile_path.exists())
        self.assertEqual(after["profile"]["gamma"], 2.2)
        self.assertEqual(after["profile"]["operator_note"], "kept")
        self.assertEqual(after["profile_error"], "")

    def test_old_profile_inherits_h612d_defaults_without_rewrite(self) -> None:
        self.profile_path.write_text(json.dumps({"schema": 1, "segments": 60, "gamma": 1.5}), encoding="utf-8")
        with _server(self.profile_path) as port:
            status, result = _request(port, "GET", "/api/profile")
        self.assertEqual(status, 200)
        self.assertEqual(result["profile"]["gamma"], 1.5)
        self.assertEqual(result["profile"]["physical_leds"], 360)
        self.assertEqual(result["profile_error"], "")

    def test_lab_degradation_keeps_catalog_serving(self) -> None:
        with mock.patch.object(led_sim_engine, "_import_lab", side_effect=RuntimeError("lab exploded")):
            with _server(self.profile_path) as port:
                status, catalog = _request(port, "GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertIn("lab exploded", catalog["lab_error"])
        self.assertFalse(catalog["lab"]["ok"])
        self.assertIn("beat_chase", catalog["effects"])  # production path unaffected

    def test_replay_path_fence_and_load(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/replay/load", {"path": "/etc/passwd"})
            self.assertEqual(status, 400)
            self.assertIn("path", result["error"])

            frames = led_sim_engine.test_card_frames("red", 60)
            jsonl_path = Path(self._tmp.name) / "card.jsonl"
            led_sim_engine.write_frames_jsonl(jsonl_path, frames, fps=1, meta={})
            status, result = _request(port, "POST", "/api/replay/load", {"path": str(jsonl_path)})
        self.assertEqual(status, 200)
        self.assertEqual(result["segments"], 60)
        self.assertEqual(result["frames"][0][0], [255, 0, 0])

    def test_render_card(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/render_card", {"kind": "gray50"})
            self.assertEqual(status, 200)
            self.assertEqual(result["frames"][0][0], [128, 128, 128])
            status, result = _request(port, "POST", "/api/render_card", {"kind": "nope"})
        self.assertEqual(status, 400)

    def test_calibration_sequence_endpoint(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/calibration", {
                "name": "segment_map", "fps": 60,
            })
            self.assertEqual(status, 200)
            self.assertEqual(result["segments"], 60)
            self.assertEqual(len(result["frames"]), len(result["t_ms"]))
            self.assertTrue(result["markers"])

            status, result = _request(port, "POST", "/api/calibration", {"name": "nope"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
