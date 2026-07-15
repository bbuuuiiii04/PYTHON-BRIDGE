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


def _request(
    port: int,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    content_type: str | None = "application/json",
    host: str | None = None,
) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    payload = json.dumps(body) if body is not None else None
    headers = {"Content-Type": content_type} if payload is not None and content_type else {}
    if host is not None:
        headers["Host"] = host
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
        self.assertEqual(catalog["calibration_sequence_version"], "h612d-cal-v2")
        self.assertEqual(catalog["calibration_capture_fps"], [10, 20, 30, 40, 60])
        self.assertEqual(catalog["profile_error"], "")
        self.assertIn("looks", catalog)
        self.assertIn("lab", catalog)
        self.assertTrue(all(
            look["params_stage"] == "pre_runtime_injection"
            for look in catalog["looks"]["looks"].values()
        ))

    def test_static_css_preserves_hidden_panel_semantics(self) -> None:
        with _server(self.profile_path) as port:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/sim.css")
            response = conn.getresponse()
            css = response.read().decode("utf-8")
            conn.close()
        self.assertEqual(response.status, 200)
        self.assertIn("[hidden] { display: none !important; }", css)

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
            self.assertEqual(result["frame_source"], "production_runner_offline")
            self.assertEqual(result["timing_source"], "ideal_grid")
            self.assertEqual(result["duration_ms"], 1000)

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

    def test_render_rejects_fractional_fps_and_bad_timing_numbers(self) -> None:
        cases = (
            ("fps", 59.9),
            ("fps", True),
            ("duration_s", float("nan")),
            ("bpm", float("inf")),
            ("bpm", 301),
            ("beat_division", 16.1),
        )
        with _server(self.profile_path) as port:
            for field, value in cases:
                with self.subTest(field=field, value=value):
                    status, result = _request(port, "POST", "/api/render", {
                        "source": "effect", "name": "solid", field: value,
                    })
                    self.assertEqual(status, 400, result)
                    self.assertIn(field, result["error"])

            status, result = _request(port, "POST", "/api/calibration", {
                "name": "segment_map", "fps": 59.9,
            })
        self.assertEqual(status, 400, result)
        self.assertIn("fps", result["error"])

    def test_posts_require_json_content_type_and_local_host(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(
                port,
                "POST",
                "/api/render_card",
                {"kind": "red"},
                content_type="text/plain",
            )
            self.assertEqual(status, 415, result)
            self.assertIn("Content-Type", result["error"])

            status, result = _request(
                port,
                "POST",
                "/api/render_card",
                {"kind": "red"},
                host="attacker.example",
            )
        self.assertEqual(status, 403, result)
        self.assertIn("Host", result["error"])

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

    def test_room_mm_repair_runs_even_when_layout_present(self) -> None:
        # AWR-246: v2 layouts carry room_mm inside each entry; migrate fills defaults.
        example = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json").read_text()
        )
        home = dict(example["layouts"]["Home"])
        home.pop("room_mm", None)
        example["layouts"] = {"Home": home}
        self.profile_path.write_text(json.dumps(example), encoding="utf-8")
        with _server(self.profile_path) as port:
            status, result = _request(port, "GET", "/api/profile")
        self.assertEqual(status, 200)
        active = result["profile"]["layouts"][result["profile"]["active_layout"]]
        self.assertEqual(active["room_mm"], list(led_sim_engine.DEFAULT_ROOM_MM))
        self.assertIn("profile_warnings", result)
        self.assertEqual(active.get("layout_locked"), False)
        self.assertEqual(result["profile"].get("calibration_locked"), False)

    def test_catalog_includes_profile_warnings(self) -> None:
        with _server(self.profile_path) as port:
            status, catalog = _request(port, "GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertIn("profile_warnings", catalog)
        self.assertIsInstance(catalog["profile_warnings"], list)
        active = catalog["profile"]["layouts"][catalog["profile"]["active_layout"]]
        self.assertIs(active["layout_locked"], False)
        self.assertIs(catalog["profile"]["calibration_locked"], False)

    def test_lock_flags_roundtrip_on_profile_save(self) -> None:
        example = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json").read_text()
        )
        example["layouts"]["Home"]["layout_locked"] = True
        example["calibration_locked"] = True
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/profile", example)
            self.assertEqual(status, 200, result)
            self.assertTrue(result["ok"])
            status, after = _request(port, "GET", "/api/profile")
        self.assertEqual(status, 200)
        active = after["profile"]["layouts"][after["profile"]["active_layout"]]
        self.assertIs(active["layout_locked"], True)
        self.assertIs(after["profile"]["calibration_locked"], True)

        # F-1: Calibrate-tab flow — start unlocked on disk, then POST with only
        # calibration_locked flipped true (knobs unchanged). Save must persist it.
        unlocked = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json").read_text()
        )
        unlocked["layouts"]["Home"]["layout_locked"] = False
        unlocked["calibration_locked"] = False
        with _server(self.profile_path) as port:
            status, _ = _request(port, "POST", "/api/profile", unlocked)
            self.assertEqual(status, 200)
            toggled = json.loads(json.dumps(unlocked))
            toggled["calibration_locked"] = True
            status, result = _request(port, "POST", "/api/profile", toggled)
            self.assertEqual(status, 200, result)
            self.assertTrue(result["ok"])
            status, after = _request(port, "GET", "/api/profile")
        self.assertEqual(status, 200)
        self.assertIs(after["profile"]["calibration_locked"], True)
        active = after["profile"]["layouts"][after["profile"]["active_layout"]]
        self.assertIs(active["layout_locked"], False)

    def test_v1_profile_migrates_on_get_and_save(self) -> None:
        v1 = {
            "schema": 1,
            "device_model": "H612D",
            "segments": 60,
            "physical_leds": 360,
            "leds_per_segment": 6,
            "strip_length_mm": 14996.16,
            "room_mm": [5216, 2284],
            "layout": led_sim_engine.default_layout([5216, 2284]),
            "layout_locked": True,
            "calibration_locked": False,
            "gamma": 1.0,
            "white_point": [1.0, 1.0, 1.0],
            "brightness": 1.0,
            "glow_radius": 1.0,
            "glow_gain": 1.0,
            "bleed": 0.0,
            "fps": 60,
            "latency_ms": 0,
            "hold_mode": "zoh",
            "slew_ms": 0,
            "bpm": 128,
            "calibration_status": "unmeasured",
            "calibration_domains": {
                "color": "unmeasured", "timing": "unmeasured", "spatial": "unmeasured",
            },
            "calibration_evidence": {},
        }
        self.profile_path.write_text(json.dumps(v1), encoding="utf-8")
        with _server(self.profile_path) as port:
            status, result = _request(port, "GET", "/api/profile")
            self.assertEqual(status, 200)
            self.assertEqual(result["profile"]["schema"], 2)
            self.assertEqual(result["profile"]["active_layout"], "Home")
            self.assertTrue(result["profile"]["layouts"]["Home"]["layout_locked"])
            self.assertNotIn("layout", result["profile"])
            status, saved = _request(port, "POST", "/api/profile", result["profile"])
            self.assertEqual(status, 200, saved)
        disk = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertEqual(disk["schema"], 2)
        self.assertNotIn("layout", disk)
        self.assertNotIn("room_mm", disk)

    def test_layout_delete_roundtrip_persists(self) -> None:
        """AWR-246 follow-up: removing a non-active layout via profile POST sticks on disk."""
        example = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json").read_text()
        )
        home = dict(example["layouts"]["Home"])
        example["layouts"] = {
            "Home": home,
            "Venue Test": dict(home),
        }
        example["active_layout"] = "Home"
        with _server(self.profile_path) as port:
            status, saved = _request(port, "POST", "/api/profile", example)
            self.assertEqual(status, 200, saved)
            self.assertTrue(saved["ok"])
            self.assertEqual(set(saved["profile"]["layouts"]), {"Home", "Venue Test"})

            pruned = json.loads(json.dumps(saved["profile"]))
            del pruned["layouts"]["Venue Test"]
            self.assertEqual(pruned["active_layout"], "Home")
            status, after_save = _request(port, "POST", "/api/profile", pruned)
            self.assertEqual(status, 200, after_save)
            self.assertTrue(after_save["ok"])
            self.assertEqual(set(after_save["profile"]["layouts"]), {"Home"})
            self.assertEqual(after_save["profile"]["active_layout"], "Home")

            status, fetched = _request(port, "GET", "/api/profile")
            self.assertEqual(status, 200)
            self.assertEqual(set(fetched["profile"]["layouts"]), {"Home"})
            self.assertEqual(fetched["profile"]["active_layout"], "Home")

        disk = json.loads(self.profile_path.read_text(encoding="utf-8"))
        self.assertEqual(set(disk["layouts"]), {"Home"})
        self.assertEqual(disk["active_layout"], "Home")
        self.assertNotIn("Venue Test", disk["layouts"])

    def test_delete_ui_uses_inpage_confirm_not_window_confirm(self) -> None:
        """AWR-246 third pass: Delete must use DOM confirm — window.confirm is silent-false in e2e."""
        root = Path(__file__).resolve().parents[1]
        js = (root / "tools" / "led_sim_assets" / "sim-app.js").read_text(encoding="utf-8")
        html = (root / "tools" / "led_sim_assets" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("window.confirm(", js)
        self.assertIn("confirmDialog(", js)
        self.assertIn('id="layout-delete"', html)
        self.assertIn('id="confirm-dialog"', html)
        self.assertIn('id="confirm-dialog-ok"', html)
        self.assertIn('id="confirm-dialog-cancel"', html)
        self.assertIn('id="error-banner"', html)

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

    def test_replay_rejects_non_h612d_segment_count(self) -> None:
        frames = led_sim_engine.test_card_frames("red", 1)
        jsonl_path = Path(self._tmp.name) / "one-segment.jsonl"
        led_sim_engine.write_frames_jsonl(jsonl_path, frames, fps=1, meta={})
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/replay/load", {"path": str(jsonl_path)})
        self.assertEqual(status, 400, result)
        self.assertIn("60", result["error"])

    def test_render_card(self) -> None:
        with _server(self.profile_path) as port:
            status, result = _request(port, "POST", "/api/render_card", {"kind": "gray50"})
            self.assertEqual(status, 200)
            self.assertEqual(result["frames"][0][0], [128, 128, 128])
            self.assertEqual(result["duration_ms"], 1000)
            self.assertEqual(result["frame_source"], "reference_generated_offline")
            self.assertEqual(result["timing_source"], "ideal_grid")
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
