from __future__ import annotations

import copy
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import rb_ss_bridge_v2.tools.led_pad_web as led_pad_web  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_web import (  # noqa: E402
    LedPadService,
    StaleLook,
    build_handler,
    compute_config_stale,
    freshness_restart_due,
    process_start_time,
    resolve_sim_profile_state,
    sim_profile_response,
    status_file_is_fresh,
)


_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"
_SIM_VIEW_JS = Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets" / "ledsim-view.js"
_SIM_EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json"


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
            # Commit now validates the MERGED result. Only a *touched* look reaches
            # the merge, so mark it — otherwise the invalid param would be dropped
            # (live's clean copy wins) and commit would wrongly succeed.
            service._draft["looks"]["rt_groove_chase"]["params"]["not_allowed"] = 1
            service._draft["_pad_meta"]["pad_session"]["touched"] = ["rt_groove_chase"]

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

    def test_commit_merge_preserves_unmanaged_blocks(self) -> None:
        # F2/F4 present before == present after: a stale draft can't clobber them.
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            live = json.loads(path.read_text(encoding="utf-8"))
            live["zz_future"] = {"hello": [1, 2, 3]}  # a block the pad never heard of
            path.write_text(json.dumps(live), encoding="utf-8")
            before = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("f2", before)
            self.assertIn("f4", before)
            # Draft predates those blocks — simulate the 14:29 stale-draft state.
            for block in ("f2", "f4", "zz_future"):
                service._draft.pop(block, None)
            service._persist_draft_locked()

            self.assertTrue(service.save_look(
                {"name": "rt_groove_chase", "look": {"scene_ref": "rt_groove_chase"}, "params": {}}
            )["ok"])
            self.assertTrue(service.commit({})["ok"])

            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(after["f2"], before["f2"])
            self.assertEqual(after["f4"], before["f4"])
            self.assertEqual(after["zz_future"], {"hello": [1, 2, 3]})

    def test_commit_merge_preserves_untouched_live_look(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            # Another tool adds a look after the draft was created.
            live = json.loads(path.read_text(encoding="utf-8"))
            new_look = copy.deepcopy(live["looks"]["rt_groove_chase"])
            new_look["params"] = {"loop_beats": 8.0, "width": 1.0}
            live["looks"]["zz_new_live"] = new_look
            path.write_text(json.dumps(live), encoding="utf-8")

            self.assertTrue(service.save_look(
                {"name": "rt_groove_chase", "look": {"scene_ref": "rt_groove_chase"}, "params": {}}
            )["ok"])
            self.assertTrue(service.commit({})["ok"])

            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("zz_new_live", after["looks"])
            self.assertEqual(after["looks"]["zz_new_live"]["params"], {"loop_beats": 8.0, "width": 1.0})

    def test_commit_merge_applies_deletion_and_keeps_unrelated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            self.assertTrue(service.duplicate_look({"source": "rt_groove_chase", "new_name": "zz_del"})["ok"])
            self.assertTrue(service.commit({})["ok"])
            self.assertIn("zz_del", json.loads(path.read_text(encoding="utf-8"))["looks"])

            self.assertTrue(service.delete_look({"name": "zz_del"})["ok"])
            self.assertTrue(service.commit({})["ok"])

            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("zz_del", after["looks"])
            self.assertNotIn("zz_del", after.get("_pad_meta", {}).get("drafts", []))
            for names in after["banks"]["default"].values():
                self.assertNotIn("zz_del", names)
            self.assertIn("f2", after)
            self.assertIn("rt_groove_chase", after["looks"])

    def test_commit_merge_keeps_live_params_for_untouched_stale_look(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            live_params = dict(json.loads(path.read_text(encoding="utf-8"))["looks"]["rt_groove_chase"]["params"])
            self.assertTrue(live_params)  # the example ships real params here
            # Draft's copy of an untouched look goes stale (loses its params).
            service._draft["looks"]["rt_groove_chase"]["params"] = {}
            service._persist_draft_locked()

            self.assertTrue(service.duplicate_look({"source": "rt_twinkle", "new_name": "zz_other"})["ok"])
            self.assertTrue(service.commit({})["ok"])

            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(after["looks"]["rt_groove_chase"]["params"], live_params)

    def test_commit_params_edit_preserves_live_bank_move(self) -> None:
        # LIVE moves a look to a new bank after the draft was created; the pad
        # only edits that look's params (no move). Commit must keep the LIVE
        # placement, not replay the stale draft's placement.
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            live = json.loads(path.read_text(encoding="utf-8"))
            live["banks"]["default"]["groove"].remove("rt_groove_chase")
            live["banks"]["default"]["ambient"].append("rt_groove_chase")
            path.write_text(json.dumps(live), encoding="utf-8")

            self.assertTrue(service.save_look(
                {"name": "rt_groove_chase", "look": {"scene_ref": "rt_groove_chase"}, "params": {}}
            )["ok"])
            self.assertTrue(service.commit({})["ok"])

            banks = json.loads(path.read_text(encoding="utf-8"))["banks"]["default"]
            self.assertIn("rt_groove_chase", banks["ambient"])     # LIVE placement kept
            self.assertNotIn("rt_groove_chase", banks["groove"])   # stale draft NOT replayed

    def test_commit_applies_pad_move_over_live_bank(self) -> None:
        # Same LIVE move, but this time the pad explicitly moves the look to a
        # third bank. The pad's move must win.
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            live = json.loads(path.read_text(encoding="utf-8"))
            live["banks"]["default"]["groove"].remove("rt_groove_chase")
            live["banks"]["default"]["ambient"].append("rt_groove_chase")
            path.write_text(json.dumps(live), encoding="utf-8")

            self.assertTrue(service.move_look({"name": "rt_groove_chase", "bank": "buildup"})["ok"])
            self.assertTrue(service.commit({})["ok"])

            banks = json.loads(path.read_text(encoding="utf-8"))["banks"]["default"]
            self.assertIn("rt_groove_chase", banks["buildup"])     # pad move applied
            self.assertNotIn("rt_groove_chase", banks["ambient"])  # live placement overridden
            self.assertNotIn("rt_groove_chase", banks["groove"])

    def test_history_restore_restores_bank_placement_on_commit(self) -> None:
        # A restore must bring back the backup's bank placement, not just look
        # content — so it marks restored looks moved as well as touched.
        with tempfile.TemporaryDirectory() as td:
            service, _playback, path = self._service(td)
            first = service.commit({})  # writes a .bak-* of the pristine live
            self.assertTrue(first["ok"])
            backup_name = Path(first["backup_path"]).name

            live = json.loads(path.read_text(encoding="utf-8"))
            live["banks"]["default"]["groove"].remove("rt_groove_chase")
            live["banks"]["default"]["ambient"].append("rt_groove_chase")
            path.write_text(json.dumps(live), encoding="utf-8")

            self.assertTrue(service.history_restore(backup_name)["ok"])
            self.assertTrue(service.commit({})["ok"])

            banks = json.loads(path.read_text(encoding="utf-8"))["banks"]["default"]
            self.assertIn("rt_groove_chase", banks["groove"])      # backup placement restored
            self.assertNotIn("rt_groove_chase", banks["ambient"])

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

    def test_v2_enabled_pad_still_injects_slot_colors_from_test_palette(self) -> None:
        """AWR-240: fresh pad LedColorEngine has no v2 dressing; stand down to v1 fill.

        Without set_scripted_stand_down(True), resolve_slot_colors returns {} and
        slot cues render black/white-only in pad preview and lab play.
        """
        with tempfile.TemporaryDirectory() as td:
            path = self._copy_config(td)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["color_engine"]["v2"]["enabled"] = True
            path.write_text(json.dumps(data), encoding="utf-8")
            playback = _FakePlayback()
            service = LedPadService(path, dry_run=True, playback=playback)
            service.session({"test_palette": "blue_cyan"})

            result = service.play({"name": "rt_groove_chase"})

            self.assertTrue(result["ok"])
            colors = playback.play_calls[-1]["spec"]["params"]["slot_colors"]
            self.assertEqual(len(colors), 6)
            self.assertTrue(
                any(tuple(c) != (0, 0, 0) for c in colors[:5]),
                f"expected non-black slot colors, got {colors!r}",
            )
            self.assertEqual(tuple(colors[5]), (255, 255, 255))

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
            self.assertFalse(result.get("snapshot_fallback", False))
            self.assertEqual(entry["status"], "accepted")
            # Saved params == author params + live overlay, pre-injection.
            self.assertEqual(entry["params"], {"level": 0.9})
            self.assertNotIn("slot_colors", entry["params"])
            # What actually played DID carry the injected palette colors.
            self.assertIn("slot_colors", playback.play_calls[0]["spec"]["params"])

    def test_lab_accept_persists_editor_phrase_without_prior_play(self) -> None:
        """AWR-251 M-1: Accept with dirty phrase writes phrase + accepted status."""
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({
                "name": "pulse", "kind": "slot", "fn": "pulse",
                "params": {"level": 0.3}, "cue_beats": 8,
                "target_role": "", "timing_mode": "unknown", "brief": "old",
            })
            result = service.lab_accept({
                "name": "pulse",
                "params": {"level": 0.3},
                "target_role": "drop",
                "timing_mode": "beat",
                "brief": "walkthrough phrase",
                "notes": "kept",
                "cue_beats": 16,
            })
            entry = service._lab.get("pulse")
            disk = json.loads((Path(td) / "led_lab" / "drafts.json").read_text(encoding="utf-8"))
            disk_entry = next(e for e in disk["entries"] if e["name"] == "pulse")

            self.assertTrue(result["ok"])
            self.assertFalse(result["snapshotted"])
            self.assertEqual(entry["status"], "accepted")
            self.assertEqual(entry["target_role"], "drop")
            self.assertEqual(entry["timing_mode"], "beat")
            self.assertEqual(entry["brief"], "walkthrough phrase")
            self.assertEqual(entry["notes"], "kept")
            self.assertEqual(entry["cue_beats"], 16.0)
            self.assertEqual(disk_entry["status"], "accepted")
            self.assertEqual(disk_entry["target_role"], "drop")
            self.assertEqual(disk_entry["brief"], "walkthrough phrase")

    def test_lab_reject_persists_editor_fields(self) -> None:
        """AWR-251 M-1: Reject also saves what the editor shows."""
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({
                "name": "pulse", "kind": "slot", "fn": "pulse",
                "params": {"level": 0.2}, "cue_beats": 8, "brief": "a",
            })
            result = service.lab_reject({
                "name": "pulse",
                "params": {"level": 0.7},
                "brief": "rejected look",
                "notes": "nope",
                "target_role": "groove",
                "timing_mode": "time",
                "cue_beats": 32,
            })
            entry = service._lab.get("pulse")
            self.assertTrue(result["ok"])
            self.assertEqual(entry["status"], "rejected")
            self.assertEqual(entry["params"], {"level": 0.7})
            self.assertEqual(entry["brief"], "rejected look")
            self.assertEqual(entry["target_role"], "groove")

    def test_lab_update_does_not_mutate_drafts_json(self) -> None:
        """AWR-251 M-2: /api/lab/update is runtime-apply only."""
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._lab_service(td)
            service.lab_save({
                "name": "pulse", "kind": "slot", "fn": "pulse",
                "params": {"level": 0.3}, "cue_beats": 8,
            })
            drafts_path = Path(td) / "led_lab" / "drafts.json"
            before = drafts_path.read_text(encoding="utf-8")
            service.lab_play({"name": "pulse", "params": {"level": 0.3}})
            playback.update_calls.clear()

            result = service.lab_update({"name": "pulse", "params": {"level": 0.95}})
            after = drafts_path.read_text(encoding="utf-8")

            self.assertTrue(result["ok"])
            self.assertTrue(result["applied"])
            self.assertEqual(before, after)
            self.assertEqual(service._lab.get("pulse")["params"], {"level": 0.3})
            self.assertEqual(len(playback.update_calls), 1)

    def test_lab_accept_without_play_reports_not_snapshotted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.3}, "cue_beats": 8})

            result = service.lab_accept({"name": "pulse"})
            entry = service._lab.get("pulse")

            self.assertTrue(result["ok"])
            self.assertFalse(result["snapshotted"])
            self.assertTrue(result["snapshot_fallback"])
            self.assertEqual(entry["status"], "accepted")
            self.assertEqual(entry["params"], {"level": 0.3})

    def test_lab_accept_uses_persisted_snapshot_after_restart(self) -> None:
        """AWR-259 L8: last-applied survives pad restart (new LedPadService)."""
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            lab_dir = Path(td) / "led_lab"
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.3}, "cue_beats": 8})
            service.lab_play({"name": "pulse", "params": {"level": 0.9}})
            snap_path = lab_dir / "last_applied.json"
            self.assertTrue(snap_path.exists())
            on_disk = json.loads(snap_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["pulse"], {"level": 0.9})

            # Simulate pad restart: new service, empty memory, same lab dir.
            restarted, _ = self._lab_service(td)
            result = restarted.lab_accept({"name": "pulse"})
            entry = restarted._lab.get("pulse")

            self.assertTrue(result["ok"])
            self.assertTrue(result["snapshotted"])
            self.assertFalse(result["snapshot_fallback"])
            self.assertEqual(entry["params"], {"level": 0.9})

    def test_save_look_rejects_stale_updated_stamp(self) -> None:
        """AWR-259 L7: Tab A save then Tab B stale stamp → 409 stale_look."""
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            first = service.save_look({
                "name": "rt_groove_chase",
                "look": {"scene_ref": "rt_groove_chase", "brightness": 20},
                "params": {},
                "updated": "",
            })
            self.assertTrue(first["ok"])
            stamp_a = first["updated"]
            self.assertTrue(stamp_a)

            second = service.save_look({
                "name": "rt_groove_chase",
                "look": {"scene_ref": "rt_groove_chase", "brightness": 20},
                "params": {},
                "updated": stamp_a,
            })
            self.assertTrue(second["ok"])
            stamp_b = second["updated"]
            self.assertNotEqual(stamp_a, stamp_b)

            with self.assertRaises(StaleLook) as ctx:
                service.save_look({
                    "name": "rt_groove_chase",
                    "look": {"scene_ref": "rt_groove_chase", "brightness": 90},
                    "params": {},
                    "updated": stamp_a,  # stale Tab B
                })
            self.assertEqual(ctx.exception.code, "stale_look")
            # Winning tab's brightness still on draft.
            self.assertEqual(
                service._draft["looks"]["rt_groove_chase"]["brightness"],
                20,
            )

            # Fresh stamp still saves.
            third = service.save_look({
                "name": "rt_groove_chase",
                "look": {"scene_ref": "rt_groove_chase", "brightness": 55},
                "params": {},
                "updated": stamp_b,
            })
            self.assertTrue(third["ok"])
            self.assertEqual(
                service._draft["looks"]["rt_groove_chase"]["brightness"],
                55,
            )

    def test_save_look_stale_via_http_returns_409(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback, _path = self._service(td)
            first = service.save_look({
                "name": "rt_groove_chase",
                "look": {"scene_ref": "rt_groove_chase", "brightness": 20},
                "params": {},
                "updated": "",
            })
            with self._running_server(service) as port:
                status, payload = self._request_json(
                    port,
                    "POST",
                    "/api/look/save",
                    {
                        "name": "rt_groove_chase",
                        "look": {"scene_ref": "rt_groove_chase", "brightness": 90},
                        "params": {},
                        "updated": "",  # stale vs first save's stamp
                    },
                )
            self.assertEqual(status, 409)
            self.assertEqual(payload["error"], "stale_look")
            self.assertEqual(payload["disk_updated"], first["updated"])

    def test_session_test_palette_live_updates_playing_lab_draft(self) -> None:
        """AWR-243 F5: test_palette must color-push while a lab_* scene is playing."""
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._lab_service(td)
            service.lab_save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 0.5}, "cue_beats": 8})
            service.session({"test_palette": "blue_cyan"})
            play = service.lab_play({"name": "pulse"})
            self.assertTrue(play["ok"])
            self.assertTrue(str(service._playing_name).startswith("lab_"))
            self.assertIsNone(service._last_play_editor)
            before = copy.deepcopy(playback.play_calls[-1]["spec"]["params"]["slot_colors"])
            playback.update_calls.clear()

            service.session({"test_palette": "violet"})

            self.assertEqual(len(playback.update_calls), 1)
            after = playback.update_calls[0]["params"]["slot_colors"]
            self.assertEqual(len(after), 6)
            self.assertEqual(after[5], (255, 255, 255))
            self.assertNotEqual(after, before)

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

    def test_lab_preview_default_beats_equals_full_cue_beats(self) -> None:
        # AWR-247: default was min(cue_beats, 8) so 32-beat cues only previewed 2 bars.
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({
                "name": "pulse", "kind": "slot", "fn": "pulse",
                "params": {"level": 1.0}, "cue_beats": 32,
            })
            result = service.lab_preview({"name": "pulse", "bpm": 120.0})
            self.assertTrue(result["ok"])
            self.assertEqual(result["beats"], 32.0)
            # fps defaults to target realtime fps (capped ≤40); at 120 BPM → 2 beats/sec.
            expected_frames = int(round(result["fps"] * (32.0 * 60.0 / 120.0)))
            self.assertEqual(len(result["frames"]), expected_frames)
            # Explicit short window still honored.
            short = service.lab_preview({"name": "pulse", "beats": 8.0, "bpm": 120.0})
            self.assertEqual(short["beats"], 8.0)

    def test_lab_list_decorates_effective_specs_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._lab_service(td)
            service.lab_save({
                "name": "pulse", "kind": "slot", "fn": "pulse", "params": {},
                "param_specs": {"floor": {"kind": "slider", "label": "Old", "min": 0.2, "max": 2.0, "step": 0.1}},
            })

            entry = service.lab_list()["entries"][0]

            self.assertEqual(entry["spec_conflicts"], ["floor"])
            self.assertEqual(entry["effective_param_specs"]["floor"]["max"], 1)
            # Decoration only — stored spec unchanged.
            self.assertEqual(entry["param_specs"]["floor"]["max"], 2.0)

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


class FreshnessRestartDueTests(unittest.TestCase):
    """Pure watchdog decision: change present, settled, and safe."""

    BASE = {"a.py": 1.0, "b.py": 2.0}

    def test_no_change_is_false(self) -> None:
        self.assertFalse(freshness_restart_due(self.BASE, dict(self.BASE), playing=False, pad_owned=False, stable_age_s=60.0))

    def test_change_while_playing_is_false(self) -> None:
        current = {**self.BASE, "a.py": 9.0}
        self.assertFalse(freshness_restart_due(self.BASE, current, playing=True, pad_owned=False, stable_age_s=60.0))

    def test_change_while_pad_owned_is_false(self) -> None:
        current = {**self.BASE, "a.py": 9.0}
        self.assertFalse(freshness_restart_due(self.BASE, current, playing=False, pad_owned=True, stable_age_s=60.0))

    def test_fresh_change_below_min_stable_is_false(self) -> None:
        current = {**self.BASE, "a.py": 9.0}
        self.assertFalse(freshness_restart_due(self.BASE, current, playing=False, pad_owned=False, stable_age_s=1.0))

    def test_stable_change_idle_not_owned_is_true(self) -> None:
        current = {**self.BASE, "a.py": 9.0}
        self.assertTrue(freshness_restart_due(self.BASE, current, playing=False, pad_owned=False, stable_age_s=3.0))

    def test_missing_watched_file_counts_as_changed_once_stable(self) -> None:
        current = {"a.py": 1.0}  # b.py vanished
        self.assertFalse(freshness_restart_due(self.BASE, current, playing=False, pad_owned=False, stable_age_s=1.0))
        self.assertTrue(freshness_restart_due(self.BASE, current, playing=False, pad_owned=False, stable_age_s=5.0))


class ConfigStaleComputationTests(unittest.TestCase):
    """AWR-255/261: live config mtime vs bridge start (fake clocks only)."""

    def test_stale_when_config_newer_than_bridge_start(self) -> None:
        out = compute_config_stale(
            config_mtime=1_000_100.0,
            bridge_started_at=1_000_000.0,
            last_commit_at=None,
            now=1_000_200.0,
        )
        self.assertTrue(out["stale"])
        self.assertEqual(out["signal"], "bridge_start")
        self.assertEqual(out["lag_s"], 100.0)
        self.assertTrue(out["bridge_live"])

    def test_fresh_when_bridge_started_after_config(self) -> None:
        out = compute_config_stale(
            config_mtime=1_000_000.0,
            bridge_started_at=1_000_050.0,
            last_commit_at=1_000_000.0,
            now=1_000_200.0,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "bridge_start")
        self.assertEqual(out["lag_s"], -50.0)

    def test_fresh_when_mtime_equals_start(self) -> None:
        out = compute_config_stale(
            config_mtime=50.0,
            bridge_started_at=50.0,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "bridge_start")
        self.assertEqual(out["lag_s"], 0.0)

    def test_commit_proxy_when_start_unknown(self) -> None:
        out = compute_config_stale(
            config_mtime=200.0,
            bridge_started_at=None,
            last_commit_at=199.0,
        )
        self.assertTrue(out["stale"])
        self.assertEqual(out["signal"], "commit_proxy")
        self.assertIsNone(out["lag_s"])

    def test_no_signal_when_start_and_commit_unknown(self) -> None:
        out = compute_config_stale(
            config_mtime=200.0,
            bridge_started_at=None,
            last_commit_at=None,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "none")

    def test_missing_config_mtime_is_not_stale(self) -> None:
        out = compute_config_stale(
            config_mtime=None,
            bridge_started_at=10.0,
            last_commit_at=20.0,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "none")

    def test_bridge_start_wins_over_commit_proxy(self) -> None:
        out = compute_config_stale(
            config_mtime=100.0,
            bridge_started_at=150.0,
            last_commit_at=100.0,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "bridge_start")

    def test_not_running_when_bridge_not_live(self) -> None:
        out = compute_config_stale(
            config_mtime=200.0,
            bridge_started_at=100.0,
            last_commit_at=199.0,
            bridge_live=False,
        )
        self.assertFalse(out["stale"])
        self.assertEqual(out["signal"], "not_running")
        self.assertFalse(out["bridge_live"])
        self.assertIsNone(out["bridge_started_at"])

    def test_status_file_freshness_window(self) -> None:
        now = 1_000.0
        self.assertTrue(status_file_is_fresh(999.0, now=now))
        self.assertTrue(status_file_is_fresh(995.1, now=now))
        self.assertFalse(status_file_is_fresh(995.0, now=now))
        self.assertFalse(status_file_is_fresh(900.0, now=now))
        self.assertFalse(status_file_is_fresh(None, now=now))
        self.assertFalse(status_file_is_fresh(0, now=now))

    def test_process_start_time_self_pid(self) -> None:
        started = process_start_time(os.getpid())
        self.assertIsNotNone(started)
        assert started is not None
        self.assertLessEqual(started, time.time() + 1.0)
        self.assertGreater(started, time.time() - 86400.0 * 30)

    def test_process_start_time_dead_pid(self) -> None:
        self.assertIsNone(process_start_time(2_147_483_646))


class ConfigStaleRuntimeStatusTests(unittest.TestCase):
    """AWR-261: status freshness gates bridge.live (synthetic files + fake time)."""

    NOW = 1_000_000.0

    def _service(self, td: str) -> LedPadService:
        path = Path(td) / "led_look_director.json"
        shutil.copy2(_EXAMPLE_PATH, path)
        service = LedPadService(path, dry_run=True, playback=_FakePlayback())
        service._status_path = Path(td) / "status.json"
        return service

    def _write_status(self, service: LedPadService, payload: dict) -> None:
        service._status_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_fresh_status_older_config_is_green(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            started = self.NOW - 100.0
            config_mtime = started - 50.0
            os.utime(service._config_path, (config_mtime, config_mtime))
            self._write_status(
                service,
                {
                    "written_at": self.NOW - 1.0,
                    "process": {"pid": 4242, "state": "on"},
                },
            )
            with patch.object(led_pad_web, "process_start_time", return_value=started):
                payload = service.runtime_status(now=self.NOW)
            self.assertTrue(payload["bridge"]["live"])
            self.assertEqual(payload["bridge"]["state"], "running")
            stale = payload["config_stale"]
            self.assertFalse(stale["stale"])
            self.assertEqual(stale["signal"], "bridge_start")
            self.assertTrue(stale["bridge_live"])

    def test_fresh_status_newer_config_warns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            started = self.NOW - 100.0
            config_mtime = started + 25.0
            os.utime(service._config_path, (config_mtime, config_mtime))
            self._write_status(
                service,
                {
                    "written_at": self.NOW - 0.5,
                    "process": {"pid": 4242, "state": "on"},
                },
            )
            with patch.object(led_pad_web, "process_start_time", return_value=started):
                payload = service.runtime_status(now=self.NOW)
            self.assertTrue(payload["bridge"]["live"])
            stale = payload["config_stale"]
            self.assertTrue(stale["stale"])
            self.assertEqual(stale["signal"], "bridge_start")
            self.assertEqual(stale["lag_s"], 25.0)

    def test_stale_status_file_is_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            self._write_status(
                service,
                {
                    "written_at": self.NOW - 60.0,
                    "process": {"pid": 4242, "state": "on"},
                },
            )
            with patch.object(led_pad_web, "process_start_time", return_value=self.NOW - 200.0):
                payload = service.runtime_status(now=self.NOW)
            self.assertFalse(payload["bridge"]["live"])
            self.assertEqual(payload["bridge"]["state"], "not_running")
            stale = payload["config_stale"]
            self.assertFalse(stale["stale"])
            self.assertEqual(stale["signal"], "not_running")
            self.assertFalse(stale["bridge_live"])

    def test_missing_status_file_is_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            self.assertFalse(service._status_path.exists())
            payload = service.runtime_status(now=self.NOW)
            self.assertFalse(payload["bridge"]["live"])
            self.assertEqual(payload["bridge"]["state"], "not_running")
            self.assertEqual(payload["config_stale"]["signal"], "not_running")

    def test_fresh_status_dead_pid_is_cant_tell(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            config_mtime = self.NOW - 10.0
            os.utime(service._config_path, (config_mtime, config_mtime))
            service._last_commit_at = config_mtime
            self._write_status(
                service,
                {
                    "written_at": self.NOW - 1.0,
                    "process": {"pid": 2_147_483_646, "state": "on"},
                },
            )
            with patch.object(led_pad_web, "process_start_time", return_value=None):
                payload = service.runtime_status(now=self.NOW)
            self.assertTrue(payload["bridge"]["live"])
            stale = payload["config_stale"]
            self.assertTrue(stale["stale"])
            self.assertEqual(stale["signal"], "commit_proxy")

    def test_parseable_but_stale_file_is_not_live(self) -> None:
        """Regression: yesterday's status file must not keep bridge.live=True."""
        with tempfile.TemporaryDirectory() as td:
            service = self._service(td)
            self._write_status(
                service,
                {
                    "written_at": self.NOW - 86_400.0,
                    "process": {"pid": os.getpid(), "state": "on"},
                },
            )
            payload = service.runtime_status(now=self.NOW)
            self.assertFalse(payload["bridge"]["live"])
            self.assertEqual(payload["config_stale"]["signal"], "not_running")


class LiveChangedFingerprintTests(unittest.TestCase):
    def test_live_changed_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            service = LedPadService(path, dry_run=True, playback=_FakePlayback())

            fresh = service.get_config_payload()
            self.assertFalse(fresh["live_changed"])

            # Dirty the draft, then mutate live underneath it.
            service.session({"bpm": 141})
            live = json.loads(path.read_text(encoding="utf-8"))
            live["_external_touch"] = True
            path.write_text(json.dumps(live), encoding="utf-8")
            self.assertTrue(service.get_config_payload()["live_changed"])

            # Discard reloads live and re-bases the fingerprint.
            service.discard({})
            self.assertFalse(service.get_config_payload()["live_changed"])

            # Same again, healed by commit this time.
            service.session({"bpm": 142})
            live["_external_touch_2"] = True
            path.write_text(json.dumps(live), encoding="utf-8")
            self.assertTrue(service.get_config_payload()["live_changed"])
            self.assertTrue(service.commit({})["ok"])
            self.assertFalse(service.get_config_payload()["live_changed"])


class CacheControlTests(unittest.TestCase):
    def test_json_and_static_responses_send_no_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, path)
            service = LedPadService(path, dry_run=True, playback=_FakePlayback())
            server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                headers = {}
                for label, target in (("json", "/api/config"), ("static", "/static/pad.css")):
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                    conn.request("GET", target)
                    res = conn.getresponse()
                    res.read()
                    headers[label] = res.getheader("Cache-Control")
                    conn.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2.0)

            self.assertEqual(headers["json"], "no-cache")
            self.assertEqual(headers["static"], "no-cache")


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


class SimRoomHookupRouteTests(unittest.TestCase):
    """AWR-245: pad serves sim view JS + profile JSON read-only (fail-soft)."""

    def _service(self, td: str) -> LedPadService:
        path = Path(td) / "led_look_director.json"
        shutil.copy2(_EXAMPLE_PATH, path)
        return LedPadService(path, dry_run=True, playback=_FakePlayback())

    def test_sim_view_js_served_with_javascript_content_type(self) -> None:
        self.assertTrue(_SIM_VIEW_JS.is_file())
        with tempfile.TemporaryDirectory() as td, _pad_http(self._service(td)) as server:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/static/sim/ledsim-view.js")
            res = conn.getresponse()
            body = res.read()
            ctype = res.getheader("Content-Type") or ""
            conn.close()

        self.assertEqual(res.status, 200)
        self.assertIn("javascript", ctype.lower())
        self.assertEqual(body, _SIM_VIEW_JS.read_bytes())
        self.assertIn(b"createLedSimView", body)

    def test_sim_view_js_missing_returns_404(self) -> None:
        missing = Path("/tmp/rbss_awr245_missing_ledsim_view.js")
        if missing.exists():
            missing.unlink()
        previous = led_pad_web._SIM_VIEW_JS
        led_pad_web._SIM_VIEW_JS = missing
        try:
            with tempfile.TemporaryDirectory() as td, _pad_http(self._service(td)) as server:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                conn.request("GET", "/static/sim/ledsim-view.js")
                res = conn.getresponse()
                res.read()
                conn.close()
            self.assertEqual(res.status, 404)
        finally:
            led_pad_web._SIM_VIEW_JS = previous

    def test_sim_profile_ok_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td, _pad_http(self._service(td)) as server:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            conn.request("GET", "/api/sim/profile")
            res = conn.getresponse()
            payload = json.loads(res.read().decode("utf-8"))
            conn.close()

        self.assertEqual(res.status, 200)
        self.assertTrue(payload.get("ok"))
        profile = payload["profile"]
        self.assertIsInstance(profile, dict)
        self.assertIn("room_mm", profile)
        self.assertIn("layout", profile)
        self.assertIsInstance(profile.get("layout_locked"), bool)
        self.assertIsInstance(profile.get("calibration_locked"), bool)

        # Helper matches HTTP payload for the default paths.
        direct = sim_profile_response()
        self.assertTrue(direct["ok"])
        self.assertEqual(direct["profile"].keys(), profile.keys())

    def test_sim_profile_failure_shape_when_example_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing_example = Path(td) / "no_such_example.json"
            missing_live = Path(td) / "no_such_live.json"
            payload = sim_profile_response(
                example_path=missing_example,
                profile_path=missing_live,
            )
            self.assertFalse(payload.get("ok"))
            self.assertIn("error", payload)
            self.assertNotIn("profile", payload)

            profile, err = resolve_sim_profile_state(
                example_path=missing_example,
                profile_path=missing_live,
            )
            self.assertEqual(profile, {})
            self.assertTrue(err)

    def test_sim_profile_falls_back_to_example_on_bad_live(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad_live = Path(td) / "led_sim_profile.json"
            bad_live.write_text("{not-json", encoding="utf-8")
            payload = sim_profile_response(
                example_path=_SIM_EXAMPLE,
                profile_path=bad_live,
            )
            self.assertTrue(payload.get("ok"))
            self.assertIn("profile", payload)
            self.assertIn("profile_error", payload)
            self.assertIn("led_sim_profile.json", payload["profile_error"])

    def test_lab_room_profile_refreshes_on_preview(self) -> None:
        """AWR-250: Lab must re-fetch /api/sim/profile on Preview + Room toggle (no forever memo)."""
        root = Path(__file__).resolve().parents[1]
        lab_js = (root / "tools" / "led_pad_assets" / "lab.js").read_text(encoding="utf-8")
        self.assertIn("PROFILE_TTL_MS", lab_js)
        self.assertIn("layoutFingerprint", lab_js)
        self.assertIn("ensureRoomView({refresh: true})", lab_js)
        self.assertIn("ensureRoomProfile({force:", lab_js)
        self.assertNotIn("fetched once per page load", lab_js)

    def test_awr251_lab_save_contract_wiring(self) -> None:
        """AWR-251: Accept saves editor; auto-apply never labSave; search is name/brief/notes."""
        root = Path(__file__).resolve().parents[1]
        lab_js = (root / "tools" / "led_pad_assets" / "lab.js").read_text(encoding="utf-8")
        lab_html = (root / "tools" / "led_pad_assets" / "lab.html").read_text(encoding="utf-8")
        pad_core = (root / "tools" / "led_pad_assets" / "pad-core.js").read_text(encoding="utf-8")
        self.assertIn("async function acceptDraft(", lab_js)
        self.assertIn("api.labAccept(payload)", lab_js)
        self.assertIn('status: "accepted"', lab_js)
        self.assertIn('api.labReject({...currentPayload(), status: "rejected"})', lab_js)
        self.assertIn("editorMemory", lab_js)
        self.assertIn("stashEditor()", lab_js)
        self.assertIn("api.labUpdate({name: state.current.name, params})", lab_js)
        self.assertNotIn("api.labSave(currentPayload())", lab_js.split("function queueAutoApply")[1].split("function hexByte")[0])
        self.assertIn("function labDraftSearchHit(", lab_js)
        self.assertIn("name.includes(q) || brief.includes(q) || notes.includes(q)", lab_js)
        self.assertIn("exactName", lab_js)
        self.assertIn("⇄ Switch live lights", lab_js)
        self.assertIn("scrollIntoView", lab_js)
        self.assertIn("Live apply paused", lab_html)
        self.assertIn('typeof body === "string" ? {name: body} : body', pad_core)

    def test_lab_draft_search_is_substring_not_subsequence(self) -> None:
        """AWR-251 residue: 'walkthrough' must not hit an entry that only has those letters scattered."""
        import subprocess

        root = Path(__file__).resolve().parents[1]
        lab_js = root / "tools" / "led_pad_assets" / "lab.js"
        script = f"""
const fs = require('fs');
const src = fs.readFileSync({str(lab_js)!r}, 'utf8');
const start = src.indexOf('function labDraftSearchHit(');
if (start < 0) throw new Error('labDraftSearchHit missing');
const end = src.indexOf('function matchesFilters(', start);
const fnSrc = src.slice(start, end);
eval(fnSrc);
const ghost = {{
  name: 'pair_rainbow',
  brief: 'warm path with light accents',
  notes: 'try the room glow when through',
}};
// Letters of "walkthrough" can be picked from brief+notes, but the substring is absent.
const hay = (ghost.brief + ' ' + ghost.notes).toLowerCase();
if (hay.includes('walkthrough')) throw new Error('fixture accidentally contains substring');
if (labDraftSearchHit(ghost, 'walkthrough')) throw new Error('subsequence falsely matched');
if (labDraftSearchHit(ghost, 'pair_rainbow') !== true) throw new Error('name substring failed');
if (labDraftSearchHit(ghost, 'warm path') !== true) throw new Error('brief substring failed');
if (labDraftSearchHit({{name:'x', brief:'', notes:'nope'}}, 'walkthrough') !== false)
  throw new Error('absent token must return false');
// Zero-row contract: filter a list with a token in none of the three fields.
const entries = [ghost, {{name:'pulse', brief:'old', notes:''}}];
const q = 'zzzz_absent_token';
const hits = entries.filter(e => labDraftSearchHit(e, q));
if (hits.length !== 0) throw new Error('expected zero rows, got ' + hits.length);
console.log('ok');
"""
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
