from __future__ import annotations

import http.client
import json
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


_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class _FakePlayback:
    def __init__(self) -> None:
        self.ownership_state = "free"
        self.play_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.bpm = 128.0
        self.loop = True
        self.playing = ""
        self.frame_index = 0
        self.takeovers = 0
        self.releases = 0

    def ownership(self) -> dict:
        return {"state": self.ownership_state, "warning": ""}

    def request_takeover(self) -> None:
        self.takeovers += 1
        self.ownership_state = "pad_owned"

    def play(self, spec: dict, *, cue_beats: float, loop: bool) -> None:
        self.play_calls.append({"spec": spec, "cue_beats": cue_beats, "loop": loop})
        self.playing = spec["look_name"]
        self.loop = loop
        self.frame_index += 1

    def update(self, spec: dict) -> None:
        self.update_calls.append(spec)
        self.frame_index += 1

    def set_bpm(self, bpm: float) -> None:
        self.bpm = bpm

    def set_loop(self, loop: bool) -> None:
        self.loop = loop

    def stop(self) -> None:
        self.playing = ""

    def emergency_stop(self) -> None:
        self.playing = ""

    def release(self) -> None:
        self.releases += 1
        self.ownership_state = "free"
        self.stop()

    def status(self) -> dict:
        self.frame_index += 1
        return {"playing_look": self.playing, "frame_index": self.frame_index, "playing": bool(self.playing)}


class LedPadServiceTests(unittest.TestCase):
    def _copy_config(self, td: str) -> Path:
        path = Path(td) / "led_look_director.json"
        shutil.copy2(_EXAMPLE_PATH, path)
        return path

    def _service(self, td: str, playback: _FakePlayback | None = None) -> tuple[LedPadService, _FakePlayback, Path]:
        playback = playback or _FakePlayback()
        path = self._copy_config(td)
        return LedPadService(path, dry_run=True, playback=playback), playback, path

    def _lab_service(self, td: str) -> tuple[LedPadService, _FakePlayback]:
        playback = _FakePlayback()
        path = self._copy_config(td)
        lab_dir = Path(td) / "led_lab"
        lab_dir.mkdir(parents=True, exist_ok=True)
        # No white-slot weight: 'level' alone controls brightness, so level 0.0
        # renders fully dark (used by the preview params-overlay test).
        (lab_dir / "effects_lab.py").write_text(
            "def pulse(beat_pos, local_t, frame_index, params, segments, seed):\n"
            "    return [[params.get('level', 1.0), 0, 0, 0, 0, 0] for _ in range(segments)]\n"
            "LAB_EFFECTS = {'pulse': ('slot', pulse)}\n",
            encoding="utf-8",
        )
        return LedPadService(path, dry_run=True, playback=playback, lab_dir=lab_dir), playback

    @contextmanager
    def _running_server(self, service: LedPadService):
        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def _request_json(self, port: int, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        raw = res.read().decode("utf-8")
        conn.close()
        return res.status, json.loads(raw)

    def test_draft_load_persist_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            service.session({"bpm": 132, "loop": False})

            reloaded = LedPadService(path, dry_run=True, playback=_FakePlayback())

            self.assertEqual(reloaded.get_config_payload()["config"]["_pad_meta"]["ui"]["bpm"], 132)
            self.assertFalse(reloaded.get_config_payload()["config"]["_pad_meta"]["ui"]["loop"])

    def test_move_duplicate_delete_enforce_single_bank(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)

            dup = service.duplicate_look({"source": "rt_groove_chase", "new_name": "rt_groove_chase_copy"})
            self.assertTrue(dup["ok"])
            self.assertIn("rt_groove_chase_copy", service.get_config_payload()["banks"]["drafts"])

            moved = service.move_look({"name": "rt_groove_chase_copy", "bank": "ambient"})
            self.assertTrue(moved["ok"])
            payload = service.get_config_payload()
            memberships = [bank for bank, names in payload["banks"].items() if "rt_groove_chase_copy" in names]
            self.assertEqual(memberships, ["ambient"])

            deleted = service.delete_look({"name": "rt_groove_chase_copy"})
            self.assertTrue(deleted["ok"])
            self.assertNotIn("rt_groove_chase_copy", service.get_config_payload()["config"]["looks"])

    def test_guards_safe_blackout_and_drop_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)

            with self.assertRaisesRegex(ValueError, "protected"):
                service.move_look({"name": "room_blackout", "bank": "drafts"})
            with self.assertRaisesRegex(ValueError, "protected"):
                service.delete_look({"name": "room_blackout"})
            with self.assertRaisesRegex(ValueError, "drop pair"):
                service.delete_look({"name": "rt_drop_chase_blue"})

    def test_unknown_param_rejected_before_merge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)

            with self.assertRaisesRegex(ValueError, "unknown params"):
                service.save_look(
                    {
                        "name": "rt_groove_chase",
                        "look": {"scene_ref": "rt_groove_chase"},
                        "params": {"not_allowed": 1},
                    }
                )

    def test_commit_blocks_invalid_and_preserves_live_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            before = path.read_bytes()
            service._draft["looks"]["rt_groove_chase"]["params"]["not_allowed"] = 1

            result = service.commit({})

            self.assertFalse(result["ok"])
            self.assertIn("not_allowed", "\n".join(result["errors"]))
            self.assertEqual(path.read_bytes(), before)

    def test_commit_writes_backup_and_resets_draft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            service.session({"bpm": 131})

            result = service.commit({})

            self.assertTrue(result["ok"])
            self.assertTrue(Path(result["backup_path"]).exists())
            self.assertTrue(service.draft_path.exists())
            self.assertEqual(json.loads(path.read_text())["_pad_meta"]["ui"]["bpm"], 131)

    def test_discard_deletes_draft_and_reloads_live(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            service.session({"bpm": 133})

            payload = service.discard({})

            self.assertFalse(service.draft_path.exists())
            self.assertNotEqual(payload["config"]["_pad_meta"]["ui"]["bpm"], 133)

    def test_dirty_computation_reports_global_bank_and_look(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            service.duplicate_look({"source": "rt_groove_chase", "new_name": "rt_groove_chase_copy"})

            dirty = service.get_config_payload()["dirty"]

            self.assertTrue(dirty["global"])
            self.assertTrue(dirty["banks"]["drafts"])
            self.assertIn("rt_groove_chase_copy", dirty["looks"])

    def test_play_builds_deterministic_engine_slot_spec(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback, _path = self._service(td)
            service.session({"test_palette": "blue_cyan", "loop": True})

            first = service.play({"name": "rt_groove_chase"})
            second = service.play({"name": "rt_groove_chase"})

            self.assertTrue(first["ok"])
            colors = playback.play_calls[-1]["spec"]["params"]["slot_colors"]
            self.assertEqual(len(colors), 6)
            self.assertEqual(colors[5], (255, 255, 255))
            self.assertEqual(first["spec"]["params"]["slot_colors"], second["spec"]["params"]["slot_colors"])

    def test_locked_palette_ignores_session_test_palette(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback, _path = self._service(td)
            service.save_look({"name": "rt_groove_chase", "look": {"scene_ref": "rt_groove_chase"}, "params": {}, "locked_palette": "crimson"})
            service.session({"test_palette": "blue_cyan"})
            service.play({"name": "rt_groove_chase"})
            first = playback.play_calls[-1]["spec"]["params"]["slot_colors"]

            service.session({"test_palette": "violet"})
            service.play({"name": "rt_groove_chase"})
            second = playback.play_calls[-1]["spec"]["params"]["slot_colors"]

            self.assertEqual(first, second)
            self.assertTrue(all(color[0] >= color[2] for color in first[:5]))

    def test_update_ignores_wrong_or_missing_playing_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback, _path = self._service(td)

            no_play = service.update({"name": "rt_groove_chase"})
            service.play({"name": "rt_groove_chase"})
            wrong_name = service.update({"name": "rt_twinkle"})

            self.assertEqual(no_play, {"ok": True, "applied": False})
            self.assertEqual(wrong_name, {"ok": True, "applied": False})
            self.assertEqual(playback.update_calls, [])

    def test_update_uses_unsaved_slot_fill_and_mono_chance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback, _path = self._service(td)
            service.session({"test_palette": "blue_cyan"})

            service.play({"name": "rt_groove_chase"})
            gradient = playback.play_calls[-1]["spec"]["params"]["slot_colors"]
            updated = service.update(
                {
                    "name": "rt_groove_chase",
                    "editor": {
                        "look": {"scene_ref": "rt_groove_chase"},
                        "params": {},
                        "slot_fill": "random_with_mono_chance",
                        "mono_chance": 1.0,
                    },
                }
            )

            self.assertTrue(updated["applied"])
            mono = playback.update_calls[-1]["params"]["slot_colors"]
            self.assertNotEqual(mono, gradient)
            self.assertEqual(len({tuple(color) for color in mono[:5]}), 1)

    def test_ownership_required_and_takeover(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            playback = _FakePlayback()
            playback.ownership_state = "bridge_owned"
            service, playback, _path = self._service(td, playback)

            blocked = service.play({"name": "rt_groove_chase"})
            allowed = service.play({"name": "rt_groove_chase", "takeover": True})

            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["error"], "ownership_required")
            self.assertTrue(allowed["ok"])
            self.assertEqual(playback.takeovers, 1)

    def test_session_persists_and_updates_playback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback, _path = self._service(td)

            payload = service.session({"bpm": 140, "test_palette": "violet", "loop": False})

            self.assertEqual(playback.bpm, 140)
            self.assertFalse(playback.loop)
            self.assertEqual(payload["session"]["test_palette"], "violet")

    def test_http_smoke_get_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            with self._running_server(service) as port:
                status, payload = self._request_json(port, "GET", "/api/config")

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertIn("config", payload)

    def test_http_smoke_get_access_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            with self._running_server(service) as port:
                status, payload = self._request_json(port, "GET", "/api/access")

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["loopback_only"])
            self.assertIsNone(payload["lan_url"])
            self.assertEqual(payload["bound_host"], "127.0.0.1")

    def test_lab_accept_snapshots_last_applied_pre_injection_params(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.3}, "cue_beats": 8})

            service.lab_play({"name": "pulse", "params": {"level": 0.9}})
            result = service.lab_accept({"name": "pulse"})
            entry = service._lab.get("pulse")

            self.assertTrue(result["ok"])
            self.assertTrue(result["snapshotted"])
            self.assertEqual(entry["status"], "accepted")
            # Saved params == author params + live overlay, pre-injection.
            self.assertEqual(entry["params"], {"level": 0.9})
            self.assertNotIn("slot_colors", entry["params"])
            # What actually played DID carry the injected palette colors.
            self.assertIn("slot_colors", playback.play_calls[0]["spec"]["params"])

    def test_lab_accept_without_play_reports_not_snapshotted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.3}, "cue_beats": 8})

            result = service.lab_accept({"name": "pulse"})
            entry = service._lab.get("pulse")

            self.assertTrue(result["ok"])
            self.assertFalse(result["snapshotted"])
            self.assertEqual(entry["status"], "accepted")
            self.assertEqual(entry["params"], {"level": 0.3})

    def test_lab_preview_honors_posted_params_without_prior_save(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.0}, "cue_beats": 8})

            dark = service.lab_preview({"name": "pulse", "beats": 1.0, "bpm": 120.0})
            lit = service.lab_preview({"name": "pulse", "params": {"level": 1.0}, "beats": 1.0, "bpm": 120.0})

            self.assertTrue(dark["ok"])
            self.assertTrue(all(tuple(pixel) == (0, 0, 0) for frame in dark["frames"] for pixel in frame))
            self.assertTrue(lit["ok"])
            self.assertTrue(any(tuple(pixel) != (0, 0, 0) for frame in lit["frames"] for pixel in frame))
            # The overlay never persisted.
            self.assertEqual(service._lab.get("pulse")["params"], {"level": 0.0})

    def test_http_lab_archive_route_and_unknown_name_400(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}})
            with self._running_server(service) as port:
                status, payload = self._request_json(port, "POST", "/api/lab/archive", {"name": "pulse"})
                bad_status, bad_payload = self._request_json(port, "POST", "/api/lab/archive", {"name": "missing"})

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["entry"]["status"], "promoted")
            self.assertEqual(bad_status, 400)
            self.assertFalse(bad_payload["ok"])
            self.assertIn("unknown lab draft", bad_payload["error"])

    def test_http_smoke_post_invalid_look_save_returns_400(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            with self._running_server(service) as port:
                status, payload = self._request_json(
                    port,
                    "POST",
                    "/api/look/save",
                    {"name": "Bad Name!", "look": {}, "params": {}},
                )

            self.assertEqual(status, 400)
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
