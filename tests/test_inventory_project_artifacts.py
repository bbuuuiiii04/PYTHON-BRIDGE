import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_static_looks import venue_fixture


MODULE_PATH = (
    Path(__file__).parents[1] / "tools" / "ssfmt" / "re" / "inventory_project_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location("inventory_project_artifacts", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _sig(value: int) -> bytes:
    return struct.pack("<I", value)


def _string(value: str) -> bytes:
    return _sig(0x01380305) + value.encode() + b"\0"


class InventoryProjectArtifactsTests(unittest.TestCase):
    def test_decodes_named_midi_control_map(self):
        data = bytearray()
        data += _sig(0xDEADBEEF)
        data += struct.pack("<HB", 1, 1)
        data += _sig(0x01380308) + struct.pack("<Q", 1)
        data += _string("IAC Driver Bus 1")
        data += _sig(0x01380306) + struct.pack("<Q", 1)
        data += struct.pack("<I", 19)
        data += _sig(0x01380306) + struct.pack("<Q", 2)
        data += _sig(0x01380307) + bytes([0, 96, 0])
        data += _string("SoundSwitch.Controls.AutoLoopsPlayAutoloop96") + b"\x01"
        data += _sig(0x01380307) + bytes([1, 7, 1])
        data += _string("SoundSwitch.Controls.StaticOverride7") + b"\x00"
        data += _sig(0x01380306) + struct.pack("<Q", 2) + b"\xaa\xbb"
        data += _sig(0xDEADBEEF)

        decoded = MODULE._decode_recordable_control_map(bytes(data))

        self.assertEqual(decoded["version"], 1)
        self.assertEqual(decoded["device_count"], 1)
        self.assertEqual(decoded["binding_count"], 2)
        self.assertEqual(
            decoded["bindings"][0],
            {
                "device_name": "IAC Driver Bus 1",
                "collection_id": 19,
                "message_type": "note",
                "message_type_raw": 0,
                "data_byte": 96,
                "channel_zero_based": 0,
                "channel_one_based": 1,
                "control_path": "SoundSwitch.Controls.AutoLoopsPlayAutoloop96",
                "enabled": True,
            },
        )
        self.assertEqual(decoded["bindings"][1]["message_type"], "control_change")
        self.assertEqual(decoded["bindings"][1]["channel_one_based"], 2)
        self.assertFalse(decoded["bindings"][1]["enabled"])
        self.assertEqual(decoded["devices"][0]["feedback_bytes_hex"], "aabb")
        self.assertEqual(decoded["enabled_event_collision_count"], 0)

    def test_reports_enabled_midi_event_collisions(self):
        data = bytearray()
        data += _sig(0xDEADBEEF)
        data += struct.pack("<HB", 1, 1)
        data += _sig(0x01380308) + struct.pack("<Q", 1)
        data += _string("DDJ-800")
        data += _sig(0x01380306) + struct.pack("<Q", 1)
        data += struct.pack("<I", 0)
        data += _sig(0x01380306) + struct.pack("<Q", 2)
        for path in (
            "SoundSwitch.Controls.StaticOverride8",
            "SoundSwitch.Controls.StaticOverride17",
        ):
            data += _sig(0x01380307) + bytes([0, 127, 9])
            data += _string(path) + b"\x01"
        data += _sig(0x01380306) + struct.pack("<Q", 0)
        data += _sig(0xDEADBEEF)

        decoded = MODULE._decode_recordable_control_map(bytes(data))

        self.assertEqual(decoded["enabled_event_collision_count"], 1)
        self.assertEqual(
            decoded["enabled_event_collisions"][0]["control_paths"],
            [
                "SoundSwitch.Controls.StaticOverride17",
                "SoundSwitch.Controls.StaticOverride8",
            ],
        )

    def test_decodes_control_label_state_modes(self):
        data = bytearray()
        data += _sig(0xDEADBEEF)
        data += struct.pack("<H", 1)
        data += _sig(0x01380308) + struct.pack("<Q", 2)
        data += _string("SoundSwitch.Controls.StaticOverride8")
        data += bytes.fromhex("4cb166ff") + b"\x00"
        data += _string("SoundSwitch.Controls.StaticOverride9")
        data += bytes.fromhex("ff00a5ff") + b"\x01"
        data += _sig(0xDEADBEEF)

        decoded = MODULE._decode_recordable_control_label_state(bytes(data))

        self.assertEqual(decoded["control_count"], 2)
        self.assertEqual(decoded["controls"][0]["interaction_mode"], "press")
        self.assertEqual(decoded["controls"][1]["interaction_mode"], "toggle")

    def test_inventory_leaves_control_registry_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / ".ssproj").write_text('{"id":"x","version":"2.10.3"}')
            recordable = project / "recordable"
            recordable.mkdir()
            (recordable / "registry.dat").write_bytes(
                _sig(0xDEADBEEF) + struct.pack("<H", 1) + _sig(0x01380308)
            )

            report = MODULE.analyze(project)

        artifact = report["artifacts"][1]
        self.assertEqual(artifact["format"], "structured binary control registry")
        self.assertIn("unsupported_reason", artifact)
        self.assertNotIn("control_map", artifact)

    def test_resolves_autoloop_control_through_category_order(self):
        artifacts = [
            {
                "control_label_state": {
                    "controls": [
                        {
                            "control_path": "SoundSwitch.Controls.StaticOverride17",
                            "interaction_mode": "toggle",
                        }
                    ]
                }
            },
            {
                "relative_path": "recordable/map.dat",
                "sha256": "abc",
                "control_map": {
                    "bindings": [
                        {
                            "device_name": "IAC Driver Bus 1",
                            "collection_id": 0,
                            "message_type": "note",
                            "data_byte": 96,
                            "channel_one_based": 1,
                            "control_path": "SoundSwitch.Controls.AutoLoopsPlayAutoloop96",
                            "enabled": True,
                        },
                        {
                            "device_name": "IAC Driver Bus 1",
                            "collection_id": 0,
                            "message_type": "note",
                            "data_byte": 64,
                            "channel_one_based": 1,
                            "control_path": "SoundSwitch.Controls.AutoLoopsPlayAutoloop64",
                            "enabled": True,
                        },
                        {
                            "device_name": "IAC Driver Bus 1",
                            "collection_id": 0,
                            "message_type": "note",
                            "data_byte": 127,
                            "channel_one_based": 1,
                            "control_path": "SoundSwitch.Controls.AutoLoopsPlayAutoloop127",
                            "enabled": True,
                        },
                        {
                            "device_name": "IAC Driver Bus 1",
                            "collection_id": 0,
                            "message_type": "note",
                            "data_byte": 1,
                            "channel_one_based": 1,
                            "control_path": "SoundSwitch.Controls.StaticOverride1",
                            "enabled": True,
                        },
                    ]
                },
            }
        ]
        catalog = {
            "entries": [
                {
                    "app_log_index": 3,
                    "file_number": 4,
                    "display_name": "DROP ONE",
                },
                {
                    "app_log_index": 17,
                    "file_number": 18,
                    "display_name": "BUILD ONE",
                },
            ],
            "category_order": [
                {"category_index": 0, "category": "BREAKDOWN", "app_log_indices": []},
                {"category_index": 1, "category": "GROOVE", "app_log_indices": []},
                {"category_index": 2, "category": "BUILDUP", "app_log_indices": [17]},
                {"category_index": 3, "category": "DROP", "app_log_indices": [3]},
            ],
        }

        rows = MODULE._resolve_autoloop_midi_bindings(artifacts, catalog)

        self.assertEqual(len(rows), 3)
        by_note = {row["midi_note"]: row for row in rows}
        self.assertEqual(by_note[64]["autoloop_file"], "SSAutoLoop18.ssfile")
        self.assertEqual(by_note[96]["autoloop_file"], "SSAutoLoop4.ssfile")
        self.assertEqual(by_note[127]["status"], "unresolved")
        self.assertIn("exceeds", by_note[127]["unresolved_reason"])

    def test_resolves_static_override_to_primary_venue_slot(self):
        artifacts = [
            {
                "control_label_state": {
                    "controls": [
                        {
                            "control_path": "SoundSwitch.Controls.StaticOverride17",
                            "interaction_mode": "toggle",
                        }
                    ]
                }
            },
            {
                "relative_path": "recordable/map.dat",
                "sha256": "abc",
                "control_map": {
                    "bindings": [
                        {
                            "device_name": "DDJ-800",
                            "collection_id": 0,
                            "message_type": "note",
                            "data_byte": 127,
                            "channel_one_based": 10,
                            "control_path": "SoundSwitch.Controls.StaticOverride17",
                            "enabled": True,
                        }
                    ]
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            venue = Path(tmp) / "SoundSwitchVenues.bin"
            venue.write_bytes(venue_fixture())
            report = MODULE._resolve_static_look_midi_bindings(artifacts, venue)

        self.assertEqual(report["status"], "resolved")
        self.assertEqual(report["binding_count"], 1)
        self.assertEqual(report["bindings"][0]["slot_index"], 17)
        self.assertEqual(report["bindings"][0]["interaction_mode"], "toggle")
        self.assertEqual(report["bindings"][0]["name"], "LOOK 17")
        self.assertEqual(report["bindings"][0]["groups"]["0x493"]["1"], 17)

    def test_cross_checks_referenced_bridge_scenes_without_exposing_port(self):
        artifacts = [
            {
                "control_map": {
                    "bindings": [
                        {
                            "device_name": "Test Bus",
                            "channel_one_based": 1,
                            "data_byte": 96,
                            "message_type": "note",
                            "enabled": True,
                            "control_path": "SoundSwitch.Controls.AutoLoopsPlayAutoloop96",
                        }
                    ]
                }
            }
        ]
        bindings = [
            {
                "device_name": "Test Bus",
                "midi_channel_one_based": 1,
                "midi_note": 96,
                "status": "resolved",
                "autoloop_file": "SSAutoLoop4.ssfile",
                "app_log_index": 3,
            }
        ]
        config = {
            "midi_output_port": "Test Bus",
            "default_personality": "house",
            "personalities": {
                "house": {
                    "drop_bank": ["drop"],
                    "safe_scene": "safe",
                    "post_drop_bank": [],
                }
            },
            "fallback_scene": "safe",
            "scenes": {
                "drop": {
                    "midi": {"channel": 1, "note": 96},
                    "scene_type": "autoloop",
                    "safety_class": "safe",
                },
                "safe": {
                    "midi": {"channel": 2, "note": 0},
                    "scene_type": "static",
                    "safety_class": "safe",
                },
                "unused": {
                    "midi": {"channel": 1, "note": 41},
                    "scene_type": "autoloop",
                    "safety_class": "safe",
                },
            },
            "manual_commands": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "laser.json"
            config_path.write_text(__import__("json").dumps(config))
            report = MODULE._bridge_scene_binding_inventory(
                artifacts, bindings, config_path
            )

        by_scene = {row["scene"]: row for row in report["scenes"]}
        self.assertEqual(by_scene["drop"]["status"], "resolved_autoloop_binding")
        self.assertEqual(by_scene["safe"]["status"], "no_decoded_project_binding")
        self.assertEqual(by_scene["unused"]["referenced_by"], [])
        self.assertNotIn("midi_output_port", report)


if __name__ == "__main__":
    unittest.main()
