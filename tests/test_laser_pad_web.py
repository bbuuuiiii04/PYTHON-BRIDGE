from __future__ import annotations

import http.client
import json
import re
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

from rb_ss_bridge_v2.tools.laser_pad_web import LaserPadService, build_handler
from rb_ss_bridge_v2.tools.laser_config_ops import _ensure_house_personality, verify_mappings_runtime


class _DummyMidiOut:
    def __init__(self) -> None:
        self.messages = []

    def send(self, msg):
        self.messages.append(msg)


class _DummyOpenOutputCtx:
    def __init__(self, out: _DummyMidiOut) -> None:
        self.out = out

    def __enter__(self) -> _DummyMidiOut:
        return self.out

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class LaserPadWebTests(unittest.TestCase):
    @contextmanager
    def _running_server(self, service: LaserPadService):
        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def _request_json(
        self,
        *,
        port: int,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> tuple[int, dict | None, str]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3.0)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        status = response.status
        conn.close()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        return status, parsed, raw

    def test_get_config_returns_pad_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            payload = service.get_config_payload()

        self.assertIn("config", payload)
        self.assertIn("_pad_meta", payload["config"])
        self.assertIn("errors", payload)
        self.assertIn("warnings", payload)

    def test_get_config_duplicate_refs_use_object_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 90,
                        "channel": 2,
                    }
                }
            )
            service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 90,
                        "channel": 2,
                    }
                }
            )

            payload = service.get_config_payload()

        hard_dupes = payload.get("hard_duplicates", [])
        self.assertTrue(hard_dupes)
        refs = hard_dupes[0].get("refs", [])
        self.assertTrue(refs)
        self.assertIsInstance(refs[0], dict)
        self.assertIn("personality", refs[0])
        self.assertIn("role", refs[0])
        self.assertIn("scene_name", refs[0])

    def test_get_config_payload_uses_single_loader_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with patch.object(service, "_load_config_result", wraps=service._load_config_result) as loader:
                service.get_config_payload()

        self.assertEqual(loader.call_count, 1)

    def test_test_note_dry_run_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service._draft["dry_run"] = True

            with patch("rb_ss_bridge_v2.tools.laser_pad_web.mido.open_output") as open_output:
                result = service.test_note(
                    {
                        "channel": 1,
                        "note": 60,
                        "velocity": 100,
                        "behavior": "pulse",
                        "duration_ms": 120,
                    }
                )

        open_output.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["sent_ms"], 120)

    def test_test_note_hold_beats_bpm_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service._draft["dry_run"] = False
            service._draft["midi_output_port"] = "Test Port"
            dummy_out = _DummyMidiOut()

            with (
                patch(
                    "rb_ss_bridge_v2.tools.laser_pad_web.mido.open_output",
                    return_value=_DummyOpenOutputCtx(dummy_out),
                ) as open_output,
                patch("rb_ss_bridge_v2.tools.laser_pad_web.time.sleep") as sleep,
            ):
                result = service.test_note(
                    {
                        "channel": 2,
                        "note": 64,
                        "velocity": 127,
                        "behavior": "hold_beats",
                        "hold_beats": 4,
                        "bpm": 120,
                    }
                )

        open_output.assert_called_once_with("Test Port")
        sleep.assert_called_once_with(2.0)
        self.assertEqual(len(dummy_out.messages), 2)
        self.assertTrue(result["ok"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["sent_ms"], 2000)

    def test_midi_ports_lists_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with patch(
                "rb_ss_bridge_v2.tools.laser_pad_web.mido.get_output_names",
                return_value=["IAC Driver Bus 1", "LoopMIDI"],
            ):
                ports = service.get_midi_ports()

        self.assertEqual(ports, ["IAC Driver Bus 1", "LoopMIDI"])

    def test_create_personality_adds_skeleton_and_persists_in_draft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            self.assertNotIn("techno", service.get_config_payload()["config"]["personalities"])

            result = service.create_personality({"name": "techno"})
            personalities = service.get_config_payload()["config"]["personalities"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "techno")
        self.assertIn("techno", personalities)
        skeleton = personalities["techno"]
        self.assertEqual(skeleton["phrase_interval_beats"], 32)
        self.assertEqual(skeleton["minimum_scene_hold_beats"], 8)
        self.assertEqual(skeleton["buildup_lookahead_beats"], 32)
        self.assertEqual(skeleton["phrase_bank"], [])
        self.assertEqual(skeleton["safe_scene"], "safe_static")

    def test_create_personality_rejects_duplicate_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.create_personality({"name": "house"})

    def test_create_personality_rejects_empty_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.create_personality({"name": "   "})

    def test_create_personality_normalizes_to_lowercase(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            result = service.create_personality({"name": "  Techno-Mix  "})
            personalities = service.get_config_payload()["config"]["personalities"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "techno-mix")
        self.assertIn("techno-mix", personalities)

    def test_rename_personality_moves_entry_and_updates_default_reference(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            self.assertEqual(
                service.get_config_payload()["config"]["default_personality"], "house"
            )

            result = service.rename_personality({"old": "house", "new": "club_house"})
            cfg = service.get_config_payload()["config"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "club_house")
        self.assertNotIn("house", cfg["personalities"])
        self.assertIn("club_house", cfg["personalities"])
        self.assertEqual(cfg["default_personality"], "club_house")
        self.assertEqual(cfg["_pad_meta"]["ui"]["last_personality"], "club_house")

    def test_rename_personality_keeps_default_when_renaming_other(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.create_personality({"name": "techno"})

            service.rename_personality({"old": "techno", "new": "deep_techno"})
            cfg = service.get_config_payload()["config"]

        self.assertEqual(cfg["default_personality"], "house")
        self.assertIn("deep_techno", cfg["personalities"])
        self.assertNotIn("techno", cfg["personalities"])

    def test_rename_personality_rejects_unknown_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.rename_personality({"old": "missing", "new": "x"})

    def test_rename_personality_rejects_collision(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.create_personality({"name": "techno"})
            with self.assertRaises(ValueError):
                service.rename_personality({"old": "techno", "new": "house"})

    def test_rename_personality_same_name_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            result = service.rename_personality({"old": "house", "new": "House"})
            cfg = service.get_config_payload()["config"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["name"], "house")
        self.assertIn("house", cfg["personalities"])

    def test_duplicate_personality_deep_copies_source_with_independent_dict(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {"mapping": {"personality": "house", "role": "groove", "note": 38, "channel": 1}}
            )
            before_house = service.get_config_payload()["config"]["personalities"]["house"]
            before_house_bank = list(before_house.get("phrase_bank", []))
            self.assertGreater(len(before_house_bank), 0)

            result = service.duplicate_personality({"source": "house", "name": "deep_house"})
            cfg = service.get_config_payload()["config"]
            personalities = cfg["personalities"]

            self.assertTrue(result["ok"])
            self.assertEqual(result["name"], "deep_house")
            self.assertIn("deep_house", personalities)
            self.assertEqual(
                personalities["deep_house"]["phrase_bank"], before_house_bank
            )
            self.assertEqual(cfg["default_personality"], "house")

            # patching house's bank must NOT bleed into deep_house (independence)
            service.apply_draft_patch(
                {"patch": {"personalities": {"house": {"phrase_bank": ["__only_house__"]}}}}
            )
            after = service.get_config_payload()["config"]["personalities"]
            self.assertEqual(after["house"]["phrase_bank"], ["__only_house__"])
            self.assertEqual(after["deep_house"]["phrase_bank"], before_house_bank)

    def test_duplicate_personality_rejects_unknown_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.duplicate_personality({"source": "missing", "name": "x"})

    def test_duplicate_personality_rejects_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.duplicate_personality({"source": "house", "name": "house"})

    def test_delete_personality_removes_entry_and_reassigns_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.create_personality({"name": "techno"})
            self.assertEqual(
                service.get_config_payload()["config"]["default_personality"], "house"
            )

            result = service.delete_personality({"name": "house"})
            cfg = service.get_config_payload()["config"]

        self.assertTrue(result["ok"])
        self.assertNotIn("house", cfg["personalities"])
        self.assertEqual(cfg["default_personality"], "techno")
        self.assertEqual(cfg["_pad_meta"]["ui"]["last_personality"], "techno")

    def test_delete_personality_keeps_default_when_other_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.create_personality({"name": "techno"})

            service.delete_personality({"name": "techno"})
            cfg = service.get_config_payload()["config"]

        self.assertEqual(cfg["default_personality"], "house")
        self.assertNotIn("techno", cfg["personalities"])

    def test_delete_personality_rejects_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.delete_personality({"name": "missing"})

    def test_delete_personality_rejects_last_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.delete_personality({"name": "house"})

    def test_rename_personality_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/personality/rename",
                    payload={"old": "house", "new": "club_house"},
                )
            cfg = service.get_config_payload()["config"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertIn("club_house", cfg["personalities"])

    def test_duplicate_personality_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/personality/duplicate",
                    payload={"source": "house", "name": "deep_house"},
                )
            cfg = service.get_config_payload()["config"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertIn("deep_house", cfg["personalities"])

    def test_delete_personality_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.create_personality({"name": "techno"})
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/personality/delete",
                    payload={"name": "techno"},
                )
            cfg = service.get_config_payload()["config"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertNotIn("techno", cfg["personalities"])

    def test_create_personality_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/personality/create",
                    payload={"name": "techno"},
                )
            personalities = service.get_config_payload()["config"]["personalities"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertIn("techno", personalities)

    def test_bank_rename_via_pad_meta_patch_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            banks = service.get_config_payload()["config"]["_pad_meta"]["banks"]
            renamed = [dict(bank) for bank in banks]
            renamed[0]["name"] = "Groove Lab"
            renamed[1]["channel"] = 2

            result = service.apply_draft_patch(
                {"patch": {"_pad_meta": {"banks": renamed}}}
            )
            after = service.get_config_payload()["config"]["_pad_meta"]["banks"]

        self.assertTrue(result["ok"])
        self.assertEqual(after[0]["name"], "Groove Lab")
        self.assertEqual(after[1]["channel"], 2)
        self.assertEqual(len(after[0]["notes"]), 32)

    def test_reset_banks_restores_default_four_by_thirtytwo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "patch": {
                        "_pad_meta": {
                            "banks": [
                                {"id": "bank_only", "channel": 9, "name": "Solo", "notes": list(range(0, 128))}
                            ]
                        }
                    }
                }
            )
            self.assertEqual(
                len(service.get_config_payload()["config"]["_pad_meta"]["banks"]),
                1,
            )

            result = service.reset_banks_to_default()
            banks = service.get_config_payload()["config"]["_pad_meta"]["banks"]

        self.assertTrue(result["ok"])
        self.assertEqual(len(banks), 4)
        self.assertEqual(banks[0]["notes"][0], 0)
        self.assertEqual(banks[-1]["notes"][-1], 127)

    def test_reset_banks_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/banks/reset",
                )
            banks = service.get_config_payload()["config"]["_pad_meta"]["banks"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertEqual(len(banks), 4)

    def test_apply_role_cooldown_updates_all_scenes_in_role_bank(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            a = service.apply_draft_patch(
                {"mapping": {"personality": "house", "role": "groove", "note": 37, "channel": 1}}
            )["scene_name"]
            b = service.apply_draft_patch(
                {"mapping": {"personality": "house", "role": "groove", "note": 45, "channel": 1}}
            )["scene_name"]

            result = service.apply_role_cooldown(
                {"personality": "house", "role": "groove", "cooldown_beats": 24}
            )
            scenes = service.get_config_payload()["config"]["scenes"]

        self.assertTrue(result["ok"])
        self.assertEqual(scenes[a]["cooldown_beats"], 24)
        self.assertEqual(scenes[b]["cooldown_beats"], 24)

    def test_apply_role_cooldown_rejects_unknown_role(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.apply_role_cooldown(
                    {"personality": "house", "role": "no_such_role", "cooldown_beats": 8}
                )

    def test_apply_role_cooldown_rejects_negative_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service.apply_role_cooldown(
                    {"personality": "house", "role": "groove", "cooldown_beats": -1}
                )

    def test_apply_role_cooldown_http_route_returns_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            scene_name = service.apply_draft_patch(
                {"mapping": {"personality": "house", "role": "drop", "note": 40, "channel": 1}}
            )["scene_name"]
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/role_cooldown",
                    payload={"personality": "house", "role": "drop", "cooldown_beats": 64},
                )
            scenes = service.get_config_payload()["config"]["scenes"]

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload.get("ok"))
        self.assertEqual(scenes[scene_name]["cooldown_beats"], 64)

    def test_manual_blackout_on_off_round_trip_via_draft_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            payload = {
                "manual_commands": {
                    "blackout_on": {
                        "kind": "note_on",
                        "behavior": "note_on",
                        "channel": 1,
                        "note": 0,
                        "velocity": 127,
                    },
                    "blackout_off": {
                        "kind": "note_off",
                        "behavior": "note_off",
                        "channel": 1,
                        "note": 1,
                        "velocity": 0,
                    },
                }
            }
            result = service.apply_draft_patch({"patch": payload})
            after = service.get_config_payload()["config"]

        self.assertTrue(result["ok"])
        self.assertEqual(after["manual_commands"]["blackout_on"]["note"], 0)
        self.assertEqual(after["manual_commands"]["blackout_off"]["note"], 1)

    def test_manual_blackout_clear_removes_command(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "patch": {
                        "manual_commands": {
                            "blackout_on": {
                                "kind": "note_on",
                                "behavior": "note_on",
                                "channel": 1,
                                "note": 5,
                                "velocity": 100,
                            }
                        }
                    }
                }
            )
            self.assertIsNotNone(
                service.get_config_payload()["config"]
                .get("manual_commands", {})
                .get("blackout_on")
            )

            service.apply_draft_patch(
                {"patch": {"manual_commands": {"blackout_on": None}}}
            )
            after = service.get_config_payload()["config"].get("manual_commands", {})

        self.assertNotIn("blackout_on", after)

    def test_smart_drop_mode_round_trips_via_draft_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            self.assertEqual(
                service.get_config_payload()["config"]["smart_drop_mode"],
                "blackout_mask",
            )

            result = service.apply_draft_patch(
                {"patch": {"smart_drop_mode": "legacy_rearm"}}
            )
            after = service.get_config_payload()["config"]["smart_drop_mode"]

        self.assertTrue(result["ok"])
        self.assertEqual(after, "legacy_rearm")

    def test_lifecycle_scenes_round_trip_via_draft_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            scenes = service.get_config_payload()["config"]["scenes"]
            self.assertIn("safe_static", scenes)

            patch_body = {
                "startup_scene": "safe_static",
                "stop_scene": "safe_static",
                "stale_scene": "safe_static",
                "emergency_scene": "safe_static",
                "fallback_scene": "safe_static",
            }
            result = service.apply_draft_patch({"patch": patch_body})
            after = service.get_config_payload()["config"]

        self.assertTrue(result["ok"])
        for key, value in patch_body.items():
            self.assertEqual(after[key], value)

    def test_enabled_toggle_round_trips_via_draft_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            before = service.get_config_payload()["config"]["enabled"]
            self.assertFalse(before)

            result = service.apply_draft_patch({"patch": {"enabled": True}})
            after = service.get_config_payload()["config"]["enabled"]

        self.assertTrue(result["ok"])
        self.assertTrue(after)

    def test_default_personality_round_trips_via_draft_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            before_payload = service.get_config_payload()["config"]
            self.assertIn("house", before_payload.get("personalities", {}))
            before = before_payload.get("default_personality")

            result = service.apply_draft_patch(
                {"patch": {"default_personality": "house"}}
            )
            after = service.get_config_payload()["config"]["default_personality"]

        self.assertTrue(result["ok"])
        self.assertEqual(after, "house")
        if before != "house":
            self.assertNotEqual(after, before)

    def test_draft_round_trip_patch_then_get_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "patch": {
                        "_pad_meta": {
                            "ui": {
                                "last_bank_id": "bank_5",
                            }
                        }
                    }
                }
            )
            payload = service.get_config_payload()

        self.assertEqual(payload["config"]["_pad_meta"]["ui"]["last_bank_id"], "bank_5")

    def test_draft_mapping_update_creates_scene_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            result = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 103,
                        "channel": 2,
                        "velocity": 110,
                        "behavior": "hold_beats",
                        "hold_beats": 4,
                        "cooldown_beats": 12,
                        "label": "drop impact 1",
                    }
                }
            )
            payload = service.get_config_payload()

        self.assertTrue(result["ok"])
        scene_name = result["scene_name"]
        scene = payload["config"]["scenes"][scene_name]
        self.assertEqual(scene["midi"]["note"], 103)
        self.assertEqual(scene["midi"]["channel"], 2)
        self.assertEqual(scene["midi"]["behavior"], "hold_beats")
        self.assertEqual(scene["label"], "drop impact 1")

    def test_drag_drop_reassignment_patch_sequence_updates_scene_notes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            src = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 60,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            dst = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 61,
                        "channel": 1,
                    }
                }
            )["scene_name"]

            service.apply_draft_patch(
                {
                    "patch": {
                        "scenes": {
                            src: {"midi": {"note": 61, "channel": 1}},
                            dst: {"midi": {"note": 60, "channel": 1}},
                        }
                    }
                }
            )
            payload = service.get_config_payload()
            scenes = payload["config"]["scenes"]

        self.assertEqual(scenes[src]["midi"]["note"], 61)
        self.assertEqual(scenes[dst]["midi"]["note"], 60)

    def test_draft_patch_null_removes_scene_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            scene_name = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 63,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            self.assertIn(scene_name, service.get_config_payload()["config"]["scenes"])

            service.apply_draft_patch({"patch": {"scenes": {scene_name: None}}})
            scenes = service.get_config_payload()["config"]["scenes"]

        self.assertNotIn(scene_name, scenes)

    def test_remove_drop_mapping_drop_mode_clears_post_drop_refs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            drop_scene = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 40,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            second_drop_scene = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 43,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            config = service.get_config_payload()["config"]
            pdata = config["personalities"]["house"]
            self.assertTrue(pdata.get("post_drop_scene"))
            self.assertIn(second_drop_scene, pdata.get("drop_bank", []))

            new_bank = [name for name in pdata.get("drop_bank", []) if name != drop_scene]
            next_primary = new_bank[0]

            patch = {
                "scenes": {drop_scene: None},
                "personalities": {
                    "house": {
                        "drop_bank": new_bank,
                        "drop_scene": next_primary,
                        "post_drop_scene": next_primary,
                        "post_drop_bank": [next_primary],
                    }
                },
            }
            service.apply_draft_patch({"patch": patch})
            validation = service.validate_draft()
            updated = service.get_config_payload()["config"]["personalities"]["house"]

        self.assertEqual(validation["errors"], [])
        self.assertEqual(updated.get("post_drop_scene"), next_primary)
        self.assertEqual(updated.get("drop_scene"), next_primary)

    def test_remove_drop_mapping_emphasized_mode_does_not_clear_post_drop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "patch": {
                        "personalities": {
                            "house": {
                                "drop_style": "emphasized_drop",
                            }
                        }
                    }
                }
            )
            drop_scene = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 41,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            post_drop_scene = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "post_drop",
                        "note": 42,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            patch = {
                "scenes": {drop_scene: None},
                "personalities": {
                    "house": {
                        "drop_bank": [],
                        "drop_scene": "",
                    }
                },
            }
            service.apply_draft_patch({"patch": patch})
            updated = service.get_config_payload()["config"]["personalities"]["house"]

        self.assertEqual(updated.get("post_drop_scene"), post_drop_scene)
        self.assertIn(post_drop_scene, updated.get("post_drop_bank", []))

    def test_commit_writes_backup_and_returns_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)

            result = service.commit_draft()
            backup_exists = bool(result["backup_path"]) and Path(result["backup_path"]).exists()

        self.assertTrue(result["ok"])
        self.assertIn("errors", result)
        self.assertIn("warnings", result)
        self.assertTrue(result["backup_path"])
        self.assertTrue(backup_exists)

    def test_history_diff_bad_name_returns_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/history/not-a-backup/diff",
                )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("error", payload)

    def test_history_diff_missing_file_returns_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/history/laser_director.json.bak-20990101-000000/diff",
                )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("history entry not found", str(payload.get("error", "")))

    def test_history_path_rejects_traversal_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self.assertRaises(ValueError):
                service._history_path("laser_director.json.bak-../etc/passwd")

    def test_static_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            service = LaserPadService(path)
            assets = Path(td) / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            (assets / "index.html").write_text("ok", encoding="utf-8")
            sibling = Path(td) / "assets2"
            sibling.mkdir(parents=True, exist_ok=True)
            (sibling / "escape.txt").write_text("escape", encoding="utf-8")

            with patch("rb_ss_bridge_v2.tools.laser_pad_web._ASSETS_DIR", assets):
                with self._running_server(service) as port:
                    status, _payload, _raw = self._request_json(
                        port=port,
                        method="GET",
                        path="/static/../assets2/escape.txt",
                    )

        self.assertEqual(status, 403)

    def test_root_serves_updated_laser_pad_markup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, _payload, raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/",
                )

        self.assertEqual(status, 200)
        self.assertIn("💾 Save &amp; Apply", raw)
        self.assertIn("Manual MIDI Test", raw)
        self.assertIn("Automatic scenes", raw)
        self.assertIn("Lasers enabled", raw)
        self.assertIn("Test mode", raw)
        self.assertIn("Type port name…", raw)
        self.assertIn("PRIMARY MAPPING", raw)
        self.assertIn("Cooldown beats", raw)
        self.assertIn("save-badge", raw)
        self.assertIn("submitModalPrompt", raw)
        self.assertIn("modal-fields", raw)
        self.assertIn("Manual MIDI Test", raw)
        self.assertIn("has-changes", raw)
        self.assertNotIn("quick-test-row", raw)
        self.assertNotIn("MIDI Output Port", raw)
        self.assertNotIn("Lifecycle Scenes", raw)
        self.assertNotIn("💾 Commit", raw)

    def test_pad_js_uses_in_app_modals_not_native_dialogs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, _payload, raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/static/pad.js",
                )

        self.assertEqual(status, 200)
        self.assertIn("openPromptModal(", raw)
        self.assertIn("openConfirmModal(", raw)
        self.assertIsNone(
            re.search(r"\b(?:window\.)?(?:prompt|confirm)\s*\(", raw),
            "pad.js still contains a native prompt()/confirm() call",
        )

    def test_draft_patch_rejects_non_list_banks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            before = service.get_config_payload()["config"]["_pad_meta"]["banks"]
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/draft",
                    payload={"patch": {"_pad_meta": {"banks": {"bad": True}}}},
                )
            after = service.get_config_payload()["config"]["_pad_meta"]["banks"]

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertEqual(after, before)

    def test_draft_patch_rejects_non_dict_pad_meta(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            before_type = type(service.get_config_payload()["config"]["_pad_meta"])
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/draft",
                    payload={"patch": {"_pad_meta": "bad"}},
                )
            after_type = type(service.get_config_payload()["config"]["_pad_meta"])

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIs(after_type, before_type)

    def test_test_note_rejects_note_above_127(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/test_note",
                    payload={"channel": 1, "note": 128, "velocity": 100},
                )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("note must be in 0-127", str(payload.get("error", "")))

    def test_test_note_rejects_channel_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/test_note",
                    payload={"channel": 0, "note": 60, "velocity": 100},
                )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("channel must be in 1-16", str(payload.get("error", "")))

    def test_test_note_rejects_velocity_negative(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/test_note",
                    payload={"channel": 1, "note": 60, "velocity": -1},
                )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("velocity must be in 0-127", str(payload.get("error", "")))

    def test_commit_with_invalid_draft_does_not_persist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            original = {"enabled": False}
            path.write_text(json.dumps(original), encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            service = LaserPadService(path)
            service.apply_draft_patch(
                {
                    "patch": {
                        "personalities": {
                            "house": {
                                "drop_scene": "missing_scene_name",
                            }
                        }
                    }
                }
            )

            result = service.commit_draft()
            after = path.read_text(encoding="utf-8")

        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        self.assertEqual(before, after)

    def test_verify_endpoint_matches_runtime_checks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            service = LaserPadService(path)
            draft_payload = service.get_config_payload()["config"]
            tmp_verify_path = Path(td) / "expected_verify.json"
            tmp_verify_path.write_text(json.dumps(draft_payload, indent=2, sort_keys=True), encoding="utf-8")

            expected = verify_mappings_runtime(tmp_verify_path)
            actual = service.verify_draft()["checks"]

        self.assertEqual(actual, expected)

    def test_runtime_status_route_returns_slim_laser_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "written_at": time.time(),
                        "laser_director": {
                            "enabled": True,
                            "emergency": False,
                            "personality": "house",
                            "current_scene": "drop_001",
                            "last_reason": "phrase_anchor_drop",
                        },
                    }
                ),
                encoding="utf-8",
            )
            service = LaserPadService(Path(td) / "laser_director.json", status_path=status_path)

            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/runtime_status",
                )

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertTrue(payload["available"])
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["active_personality"], "house")
        self.assertEqual(payload["current_scene"], "drop_001")
        self.assertEqual(payload["last_reason"], "phrase_anchor_drop")
        self.assertLess(payload["stale_seconds"], 5.0)

    def test_runtime_status_route_treats_missing_or_stale_file_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "status.json"
            service = LaserPadService(Path(td) / "laser_director.json", status_path=status_path)

            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/runtime_status",
                )

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "status_file_missing_or_stale")

    def test_runtime_status_route_reports_parse_error_without_500(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            status_path = Path(td) / "status.json"
            status_path.write_text("{bad", encoding="utf-8")
            service = LaserPadService(Path(td) / "laser_director.json", status_path=status_path)

            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/runtime_status",
                )

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertFalse(payload["available"])
        self.assertEqual(payload["reason"], "parse_error")

    def test_verify_http_route_returns_checks_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="POST",
                    path="/api/verify",
                )

        self.assertEqual(status, 200)
        assert payload is not None
        self.assertIsInstance(payload.get("checks"), list)

    def test_mapping_velocity_patch_preserves_existing_note_on_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            scene_name = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 66,
                        "channel": 1,
                        "behavior": "note_on",
                        "velocity": 90,
                    }
                }
            )["scene_name"]

            service.apply_draft_patch(
                {
                    "patch": {
                        "scenes": {
                            scene_name: {
                                "midi": {
                                    "velocity": 117,
                                }
                            }
                        }
                    }
                }
            )
            scene = service.get_config_payload()["config"]["scenes"][scene_name]

        self.assertEqual(scene["midi"]["velocity"], 117)
        self.assertEqual(scene["midi"]["behavior"], "note_on")

    def test_get_config_preserves_manual_blackout_on_after_patch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            service.apply_draft_patch(
                {
                    "patch": {
                        "manual_commands": {
                            "blackout_on": {
                                "kind": "note_on",
                                "behavior": "note_on",
                                "channel": 1,
                                "note": 42,
                                "velocity": 127,
                            }
                        }
                    }
                }
            )
            with self._running_server(service) as port:
                status, payload, _raw = self._request_json(
                    port=port,
                    method="GET",
                    path="/api/config",
                )

        self.assertEqual(status, 200)
        assert payload is not None
        cfg = payload.get("config", {})
        self.assertEqual(
            cfg.get("manual_commands", {}).get("blackout_on", {}).get("note"),
            42,
        )

    def test_history_listing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            service.commit_draft()

            items = service.list_history()

        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(items[0]["name"].startswith("laser_director.json.bak-"))

    def test_list_history_returns_json_error_on_stat_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            service.commit_draft()
            with self._running_server(service) as port:
                with patch.object(service, "list_history", side_effect=OSError("file gone")):
                    status, payload, _raw = self._request_json(
                        port=port,
                        method="GET",
                        path="/api/history",
                    )

        self.assertEqual(status, 400)
        assert payload is not None
        self.assertFalse(payload.get("ok", True))
        self.assertIn("error", payload)

    def test_restore_loads_draft_no_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)

            service.commit_draft()
            service.apply_draft_patch({"patch": {"enabled": True}})
            second_commit = service.commit_draft()
            backup_name = Path(second_commit["backup_path"]).name

            service.apply_draft_patch({"patch": {"enabled": False}})
            disk_before = path.read_text(encoding="utf-8")
            restored = service.restore_history(backup_name)
            disk_after = path.read_text(encoding="utf-8")

        self.assertEqual(disk_before, disk_after)
        self.assertFalse(restored["config"]["enabled"])

    def test_restore_history_without_pad_meta_injects_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            backup_name = f"{path.name}.bak-20260513-040000"
            backup_path = path.parent / backup_name
            backup_path.write_text(
                json.dumps(
                    {
                        "enabled": False,
                        "personalities": {
                            "house": {
                                "phrase_scene": "",
                                "phrase_bank": [],
                                "drop_scene": "",
                                "drop_bank": [],
                                "post_drop_scene": "",
                                "post_drop_bank": [],
                                "breakdown_scene": "",
                                "breakdown_bank": [],
                                "buildup_scene": "",
                                "buildup_bank": [],
                            }
                        },
                        "scenes": {},
                    }
                ),
                encoding="utf-8",
            )
            service = LaserPadService(path)

            restored = service.restore_history(backup_name)

        self.assertIsInstance(restored["config"].get("_pad_meta"), dict)
        self.assertIn("banks", restored["config"]["_pad_meta"])
        self.assertTrue(restored["config"]["_pad_meta"]["banks"])

    def test_restore_history_blank_personality_fields_are_filled(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            backup_name = f"{path.name}.bak-20260513-050000"
            backup_path = path.parent / backup_name

            legacy = service.get_config_payload()["config"]
            legacy_house = legacy["personalities"]["house"]
            legacy_house["phrase_scene"] = ""
            legacy_house["buildup_scene"] = ""
            legacy_house["drop_scene"] = ""
            legacy_house["post_drop_scene"] = ""
            legacy_house["breakdown_scene"] = ""
            legacy_house["phrase_bank"] = []
            legacy_house["buildup_bank"] = []
            legacy_house["drop_bank"] = []
            legacy_house["post_drop_bank"] = []
            legacy_house["breakdown_bank"] = []
            backup_path.write_text(json.dumps(legacy), encoding="utf-8")

            service.restore_history(backup_name)
            validation = service.validate_draft()

        self.assertEqual(validation["errors"], [])

    def test_restore_history_scene_fields_are_actually_populated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            backup_name = f"{path.name}.bak-20260513-050001"
            backup_path = path.parent / backup_name

            legacy = service.get_config_payload()["config"]
            legacy_house = legacy["personalities"]["house"]
            legacy_house["phrase_scene"] = ""
            legacy_house["buildup_scene"] = ""
            legacy_house["drop_scene"] = ""
            legacy_house["post_drop_scene"] = ""
            legacy_house["breakdown_scene"] = ""
            legacy_house["phrase_bank"] = []
            legacy_house["buildup_bank"] = []
            legacy_house["drop_bank"] = []
            legacy_house["post_drop_bank"] = []
            legacy_house["breakdown_bank"] = []
            backup_path.write_text(json.dumps(legacy), encoding="utf-8")

            service.restore_history(backup_name)
            house = service.get_config_payload()["config"]["personalities"]["house"]

        scene_fields = [
            "phrase_scene",
            "buildup_scene",
            "drop_scene",
            "post_drop_scene",
            "breakdown_scene",
        ]
        bank_fields = [
            "phrase_bank",
            "buildup_bank",
            "drop_bank",
            "post_drop_bank",
            "breakdown_bank",
        ]
        for field in scene_fields:
            self.assertIsInstance(house.get(field), str)
            self.assertTrue(house.get(field))
        for field in bank_fields:
            self.assertIsInstance(house.get(field), list)
            self.assertTrue(house.get(field))

    def test_ensure_house_personality_does_not_overwrite_populated_fields(self) -> None:
        config = {
            "scenes": {
                "custom_phrase": {},
                "custom_buildup": {},
                "custom_drop": {},
                "custom_post_drop": {},
                "custom_breakdown": {},
            },
            "personalities": {
                "house": {
                    "phrase_scene": "custom_phrase",
                    "buildup_scene": "custom_buildup",
                    "drop_scene": "custom_drop",
                    "post_drop_scene": "custom_post_drop",
                    "breakdown_scene": "custom_breakdown",
                    "phrase_bank": ["custom_phrase"],
                    "buildup_bank": ["custom_buildup"],
                    "drop_bank": ["custom_drop"],
                    "post_drop_bank": ["custom_post_drop"],
                    "breakdown_bank": ["custom_breakdown"],
                }
            },
        }
        expected = json.loads(json.dumps(config["personalities"]["house"]))

        _ensure_house_personality(config)
        house = config["personalities"]["house"]

        for key, value in expected.items():
            self.assertEqual(house.get(key), value)

    def test_restore_history_then_discard_re_reads_disk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            service.commit_draft()

            service.apply_draft_patch({"patch": {"enabled": True}})
            second_commit = service.commit_draft()
            backup_name = Path(second_commit["backup_path"]).name

            service.restore_history(backup_name)
            discarded = service.discard_draft()
            on_disk = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(discarded["config"]["enabled"], on_disk["enabled"])

    def test_set_primary_via_patch_reorders_bank_and_updates_scene_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            first = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 37,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            second = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "groove",
                        "note": 45,
                        "channel": 1,
                    }
                }
            )["scene_name"]
            before = service.get_config_payload()["config"]["personalities"]["house"]
            self.assertEqual(before.get("phrase_scene"), first)

            patch = {
                "personalities": {
                    "house": {
                        "phrase_scene": second,
                        "phrase_bank": [second, first],
                    }
                }
            }
            service.apply_draft_patch({"patch": patch})
            after = service.get_config_payload()["config"]["personalities"]["house"]

        self.assertEqual(after.get("phrase_scene"), second)
        self.assertEqual(after.get("phrase_bank", [])[:2], [second, first])

    def test_remove_last_drop_mapping_leaves_drop_scene_empty_not_safe_static(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service = LaserPadService(Path(td) / "laser_director.json")
            drop_scene = service.apply_draft_patch(
                {
                    "mapping": {
                        "personality": "house",
                        "role": "drop",
                        "note": 40,
                        "channel": 1,
                    }
                }
            )["scene_name"]

            patch = {
                "scenes": {drop_scene: None},
                "personalities": {
                    "house": {
                        "drop_bank": [],
                        "drop_scene": "",
                        "post_drop_scene": "",
                        "post_drop_bank": [],
                    }
                },
            }
            service.apply_draft_patch({"patch": patch})
            updated = service.get_config_payload()["config"]["personalities"]["house"]

        self.assertEqual(updated.get("drop_scene"), "")
        self.assertNotEqual(updated.get("drop_scene"), "safe_static")
        self.assertEqual(updated.get("post_drop_scene"), "")
        self.assertNotEqual(updated.get("post_drop_scene"), "safe_static")

    def test_commit_draft_saves_current_draft_not_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            original_loader = service._load_config_result
            mutate_once = {"done": False}

            def loader_with_midflight_mutation(config):
                if not mutate_once["done"]:
                    mutate_once["done"] = True
                    with service._lock:
                        service._draft["enabled"] = True
                return original_loader(config)

            with patch.object(service, "_load_config_result", side_effect=loader_with_midflight_mutation):
                result = service.commit_draft()
            on_disk = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(result["ok"])
        self.assertTrue(on_disk["enabled"])

    def test_commit_draft_rejects_if_second_snapshot_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            original = {"enabled": False}
            path.write_text(json.dumps(original), encoding="utf-8")
            service = LaserPadService(path)
            original_loader = service._load_config_result
            mutate_once = {"done": False}

            def loader_with_midflight_mutation(config):
                if not mutate_once["done"]:
                    mutate_once["done"] = True
                    with service._lock:
                        service._draft["personalities"]["house"]["drop_scene"] = "missing_scene_name"
                return original_loader(config)

            with patch.object(service, "_load_config_result", side_effect=loader_with_midflight_mutation):
                result = service.commit_draft()
            on_disk = json.loads(path.read_text(encoding="utf-8"))

        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        self.assertEqual(on_disk, original)

    def test_commit_draft_validation_failure_leaves_disk_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            original = {"enabled": False}
            path.write_text(json.dumps(original), encoding="utf-8")
            service = LaserPadService(path)
            with service._lock:
                service._draft["personalities"]["house"]["drop_scene"] = "missing_scene_name"

            result = service.commit_draft()
            on_disk = json.loads(path.read_text(encoding="utf-8"))

        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])
        self.assertEqual(on_disk, original)

    def test_discard_draft_drops_in_memory_changes_and_re_reads_disk(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)

            service.apply_draft_patch({"patch": {"enabled": True}})
            payload = service.discard_draft()
            disk = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["config"]["enabled"], disk["enabled"])
        self.assertFalse(payload["config"]["enabled"])

    def test_concurrent_draft_patch_and_commit_is_consistent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            errors: list[Exception] = []

            def patch_worker() -> None:
                for _ in range(50):
                    try:
                        service.apply_draft_patch({"patch": {"enabled": True}})
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            def commit_worker() -> None:
                for _ in range(50):
                    try:
                        service.commit_draft()
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            t1 = threading.Thread(target=patch_worker)
            t2 = threading.Thread(target=commit_worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            on_disk = json.loads(path.read_text(encoding="utf-8"))
            validation = service.validate_draft()

        self.assertEqual(errors, [])
        self.assertIsInstance(on_disk, dict)
        self.assertIn("errors", validation)
        self.assertEqual(validation["errors"], [])

    def test_list_history_skips_deleted_entry_during_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            service.commit_draft()
            service.commit_draft()

            backups = sorted(path.parent.glob(f"{path.name}.bak-*"))
            self.assertGreaterEqual(len(backups), 2)
            missing_name = backups[0].name
            original_stat = Path.stat

            def flaky_stat(candidate):
                if candidate.name == missing_name:
                    raise OSError("file disappeared")
                return original_stat(candidate)

            with patch("pathlib.Path.stat", autospec=True, side_effect=flaky_stat):
                items = service.list_history()

        self.assertEqual(len(items), len(backups) - 1)
        self.assertTrue(all(item["name"] != missing_name for item in items))

    def test_list_history_all_entries_unreadable_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            service = LaserPadService(path)
            service.commit_draft()
            service.commit_draft()

            original_stat = Path.stat

            def flaky_stat(candidate):
                if candidate.name.startswith(f"{path.name}.bak-"):
                    raise OSError("unreadable")
                return original_stat(candidate)

            with patch("pathlib.Path.stat", autospec=True, side_effect=flaky_stat):
                items = service.list_history()

        self.assertEqual(items, [])

    def test_commit_draft_does_not_block_concurrent_test_note(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False, "dry_run": True}), encoding="utf-8")
            service = LaserPadService(path)
            service.apply_draft_patch({"patch": {"dry_run": True}})

            entered_loader = threading.Event()
            release_loader = threading.Event()
            note_done = threading.Event()
            commit_errors: list[Exception] = []
            note_errors: list[Exception] = []

            original_loader = service._load_config_result

            def slow_loader(config):
                entered_loader.set()
                release_loader.wait(timeout=1.0)
                return original_loader(config)

            def commit_worker() -> None:
                try:
                    result = service.commit_draft()
                    if not result.get("ok"):
                        raise RuntimeError("commit_draft returned non-ok")
                except Exception as exc:  # noqa: BLE001
                    commit_errors.append(exc)

            def note_worker() -> None:
                try:
                    result = service.test_note({"channel": 1, "note": 60, "velocity": 100})
                    if not result.get("ok"):
                        raise RuntimeError("test_note returned non-ok")
                except Exception as exc:  # noqa: BLE001
                    note_errors.append(exc)
                finally:
                    note_done.set()

            with patch.object(service, "_load_config_result", side_effect=slow_loader):
                commit_thread = threading.Thread(target=commit_worker)
                commit_thread.start()
                self.assertTrue(entered_loader.wait(timeout=1.0))
                note_thread = threading.Thread(target=note_worker)
                note_thread.start()

                note_finished_while_loader_blocked = note_done.wait(timeout=0.5)

                release_loader.set()
                commit_thread.join(timeout=2.0)
                note_thread.join(timeout=2.0)

        self.assertTrue(note_finished_while_loader_blocked)
        self.assertEqual(commit_errors, [])
        self.assertEqual(note_errors, [])


if __name__ == "__main__":
    unittest.main()
