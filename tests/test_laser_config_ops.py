from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_config import load_laser_director_config
from rb_ss_bridge_v2.ss_metadata_importer import LookCatalog, LookRecord
from rb_ss_bridge_v2.tools.laser_config_ops import (
    _ensure_personality_exists,
    apply_mapping,
    detect_mixed_role_cooldowns,
    find_bank_range_collisions,
    find_duplicate_notes,
    find_duplicate_notes_keyed,
    find_soft_duplicate_notes,
    load_or_create_config,
    render_personality_summary,
    save_config_atomically,
    update_personality_timing,
    update_role_bank_cooldown,
    update_scene_cooldown,
    update_scene_safety_class,
    validate_config_data,
    verify_mappings_runtime,
)


class LaserConfigOpsTests(unittest.TestCase):
    def test_apply_mapping_creates_scene_and_updates_bank(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            scene_name = apply_mapping(cfg, personality="house", role="groove", note=99)

        self.assertIn(scene_name, cfg["scenes"])
        self.assertIn(scene_name, cfg["personalities"]["house"]["phrase_bank"])
        self.assertEqual(cfg["scenes"][scene_name]["midi"]["note"], 99)

    def test_find_duplicate_notes_detects_collision(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            apply_mapping(cfg, personality="house", role="groove", note=50)
            apply_mapping(cfg, personality="house", role="drop", note=50)

        duplicates = find_duplicate_notes(cfg)
        self.assertTrue(any(note == 50 for note, _ in duplicates))

    def test_apply_mapping_same_note_different_channel_keeps_both(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            scene_a = apply_mapping(cfg, personality="house", role="groove", note=88, channel=1)
            scene_b = apply_mapping(cfg, personality="house", role="groove", note=88, channel=2)

        self.assertNotEqual(scene_a, scene_b)
        self.assertIn(scene_a, cfg["scenes"])
        self.assertIn(scene_b, cfg["scenes"])
        self.assertIn(scene_a, cfg["personalities"]["house"]["phrase_bank"])
        self.assertIn(scene_b, cfg["personalities"]["house"]["phrase_bank"])
        self.assertEqual(cfg["scenes"][scene_a]["midi"].get("channel"), 1)
        self.assertEqual(cfg["scenes"][scene_b]["midi"].get("channel"), 2)

    def test_apply_mapping_preserves_ss_look_name_on_existing_scene(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            scene = apply_mapping(cfg, personality="house", role="groove", note=77)
            cfg["scenes"][scene]["ss_look_name"] = "BLUE FANNING"

            same_scene = apply_mapping(cfg, personality="house", role="groove", note=77)

        self.assertEqual(same_scene, scene)
        self.assertEqual(cfg["scenes"][scene]["ss_look_name"], "BLUE FANNING")

    def test_validate_config_data_warns_for_unknown_ss_look_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            scene = apply_mapping(cfg, personality="house", role="groove", note=78)
            cfg["scenes"][scene]["ss_look_name"] = "RENAMED LOOK"

        catalog = LookCatalog(
            (
                LookRecord(
                    name="BLUE FANNING",
                    source_file="SoundSwitchVenues.bin",
                    bank_header="STATIC LASERS",
                    look_type="static",
                ),
            )
        )
        _errors, warnings = validate_config_data(cfg, ss_catalog=catalog)

        self.assertTrue(
            any("unknown SoundSwitch look 'RENAMED LOOK'" in warning for warning in warnings)
        )

    def test_validate_config_data_clean_example_no_errors(self) -> None:
        example_path = Path(__file__).resolve().parents[1] / "config" / "laser_director.example.json"
        cfg = json.loads(example_path.read_text(encoding="utf-8"))

        errors, _warnings = validate_config_data(cfg)
        self.assertEqual(errors, [])

    def test_save_config_atomically_writes_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            cfg = load_or_create_config(path)

            backup = save_config_atomically(cfg, path)

            self.assertIsNotNone(backup)
            self.assertTrue(path.exists())
            self.assertTrue(backup.exists())

    def test_save_config_atomically_unique_backup_for_rapid_commits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            cfg = load_or_create_config(path)

            with patch("rb_ss_bridge_v2.tools.laser_config_ops.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = datetime(2026, 5, 13, 4, 0, 0, 123456)
                backup1 = save_config_atomically(cfg, path)
                backup2 = save_config_atomically(cfg, path)
            backup1_exists = bool(backup1) and backup1.exists()
            backup2_exists = bool(backup2) and backup2.exists()

        self.assertIsNotNone(backup1)
        self.assertIsNotNone(backup2)
        self.assertNotEqual(backup1, backup2)
        self.assertTrue(backup1_exists)
        self.assertTrue(backup2_exists)

    def test_save_config_atomically_cleans_up_temp_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            cfg = load_or_create_config(path)

            with patch(
                "rb_ss_bridge_v2.tools.laser_config_ops.json.dump",
                side_effect=RuntimeError("dump failed"),
            ):
                with self.assertRaises(RuntimeError):
                    save_config_atomically(cfg, path)

            leftovers = list(path.parent.glob(f"{path.name}.tmp-*"))

        self.assertEqual(leftovers, [])

    def test_verify_mappings_runtime_passes_on_example(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            cfg = load_or_create_config(path)
            apply_mapping(cfg, personality="house", role="groove", note=37)
            apply_mapping(cfg, personality="house", role="drop", note=40)
            cfg["manual_commands"] = {
                "blackout_on": {
                    "kind": "note_on",
                    "behavior": "note_on",
                    "channel": 1,
                    "note": 90,
                    "velocity": 127,
                },
                "blackout_off": {
                    "kind": "note_off",
                    "behavior": "note_off",
                    "channel": 1,
                    "note": 90,
                    "velocity": 0,
                },
            }
            save_config_atomically(cfg, path)

            checks = verify_mappings_runtime(path)

        failed = [item for item in checks if not item["ok"]]
        self.assertEqual(failed, [], msg=str(checks))
        role_rows = [row for row in checks if row.get("role") == "drop"]
        self.assertTrue(role_rows)
        self.assertEqual(role_rows[0]["note"], 40)
        self.assertEqual(role_rows[0]["channel"], 1)

    def test_laser_models_label_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            cfg = load_or_create_config(path)
            scene_name = apply_mapping(cfg, personality="house", role="groove", note=101)
            cfg["scenes"][scene_name]["label"] = "drop impact 1"
            save_config_atomically(cfg, path)

            loaded = load_laser_director_config(str(path))

        self.assertTrue(loaded.available, msg=str(loaded.errors))
        assert loaded.config is not None
        self.assertEqual(loaded.config.scenes[scene_name].label, "drop impact 1")

    def test_pad_meta_injected_on_first_open(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            cfg = load_or_create_config(path)

        self.assertIn("_pad_meta", cfg)
        pad_meta = cfg["_pad_meta"]
        self.assertEqual(pad_meta["schema_version"], 1)
        self.assertEqual(len(pad_meta["banks"]), 4)
        expected_ranges = [(0, 31), (32, 63), (64, 95), (96, 127)]
        for bank, (lo, hi) in zip(pad_meta["banks"], expected_ranges):
            self.assertEqual(len(bank["notes"]), 32)
            self.assertEqual(bank["notes"][0], lo)
            self.assertEqual(bank["notes"][-1], hi)
        bank_ids = [bank["id"] for bank in pad_meta["banks"]]
        self.assertEqual(bank_ids, ["bank_1", "bank_2", "bank_3", "bank_4"])
        covered = sorted(
            note for bank in pad_meta["banks"] for note in bank["notes"]
        )
        self.assertEqual(covered, list(range(0, 128)))

    def test_pad_meta_legacy_five_bank_layout_is_migrated_to_four_by_thirtytwo(self) -> None:
        legacy_pad_meta = {
            "schema_version": 1,
            "banks": [
                {"id": "bank_1", "channel": 1, "name": "Bank 1", "notes": list(range(0, 24))},
                {"id": "bank_2", "channel": 1, "name": "Bank 2", "notes": list(range(24, 48))},
                {"id": "bank_3", "channel": 1, "name": "Bank 3", "notes": list(range(48, 72))},
                {"id": "bank_4", "channel": 1, "name": "Bank 4", "notes": list(range(72, 96))},
                {"id": "bank_5", "channel": 2, "name": "Bank 5", "notes": list(range(96, 128))},
            ],
            "ui": {"last_bank_id": "bank_1"},
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(
                json.dumps({"enabled": False, "_pad_meta": legacy_pad_meta}),
                encoding="utf-8",
            )

            cfg = load_or_create_config(path)

        banks = cfg["_pad_meta"]["banks"]
        self.assertEqual(len(banks), 4)
        expected = [(0, 31), (32, 63), (64, 95), (96, 127)]
        for bank, (lo, hi) in zip(banks, expected):
            self.assertEqual(len(bank["notes"]), 32)
            self.assertEqual(bank["notes"][0], lo)
            self.assertEqual(bank["notes"][-1], hi)

    def test_pad_meta_custom_banks_are_left_alone(self) -> None:
        custom_pad_meta = {
            "schema_version": 1,
            "banks": [
                {"id": "bank_1", "channel": 1, "name": "My Custom Bank", "notes": list(range(0, 64))},
                {"id": "bank_2", "channel": 2, "name": "Second Custom", "notes": list(range(64, 128))},
            ],
            "ui": {"last_bank_id": "bank_1"},
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(
                json.dumps({"enabled": False, "_pad_meta": custom_pad_meta}),
                encoding="utf-8",
            )

            cfg = load_or_create_config(path)

        banks = cfg["_pad_meta"]["banks"]
        self.assertEqual(len(banks), 2)
        self.assertEqual(banks[0]["name"], "My Custom Bank")
        self.assertEqual(len(banks[0]["notes"]), 64)

    def test_pad_meta_missing_or_empty_banks_repopulated_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(
                json.dumps({"enabled": False, "_pad_meta": {"schema_version": 1, "banks": []}}),
                encoding="utf-8",
            )

            cfg = load_or_create_config(path)

        banks = cfg["_pad_meta"]["banks"]
        self.assertEqual(len(banks), 4)
        self.assertEqual(banks[0]["notes"][0], 0)
        self.assertEqual(banks[-1]["notes"][-1], 127)

    def test_pad_meta_preserved_on_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            first = load_or_create_config(path)
            first["_pad_meta"]["ui"]["last_bank_id"] = "custom_bank"
            save_config_atomically(first, path)

            second = load_or_create_config(path)

        self.assertEqual(second["_pad_meta"]["ui"]["last_bank_id"], "custom_bank")

    def test_duplicate_notes_channel_aware(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            apply_mapping(cfg, personality="house", role="groove", note=88, channel=1)
            apply_mapping(cfg, personality="house", role="drop", note=88, channel=2)
            apply_mapping(cfg, personality="house", role="breakdown", note=88, channel=2)

        hard_dupes = find_duplicate_notes_keyed(cfg, by="channel_note")

        self.assertTrue(any(key == (2, 88) for key, _ in hard_dupes))
        self.assertFalse(any(key == (1, 88) for key, _ in hard_dupes))

    def test_soft_duplicate_notes_cross_channel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg = load_or_create_config(Path(td) / "laser_director.json")
            apply_mapping(cfg, personality="house", role="groove", note=92, channel=1)
            apply_mapping(cfg, personality="house", role="drop", note=92, channel=2)

        soft_dupes = find_soft_duplicate_notes(cfg)
        legacy_dupes = find_duplicate_notes(cfg)

        self.assertTrue(any(note == 92 for note, _ in soft_dupes))
        self.assertEqual(soft_dupes, legacy_dupes)

    def test_validate_config_data_uses_provided_loader_result_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            cfg = load_or_create_config(path)
            save_config_atomically(cfg, path)
            loader_result = load_laser_director_config(str(path))

            with patch("rb_ss_bridge_v2.tools.laser_config_ops.tempfile.NamedTemporaryFile") as named_tmp:
                errors, warnings = validate_config_data(cfg, loader_result=loader_result)

        named_tmp.assert_not_called()
        self.assertEqual(errors, [])
        self.assertIsInstance(warnings, list)

    def test_bank_range_collision_helper_ignores_non_overlapping_ranges(self) -> None:
        pad_meta = {
            "banks": [
                {"id": "bank_1", "channel": 1, "notes": list(range(0, 32))},
                {"id": "bank_2", "channel": 1, "notes": list(range(32, 64))},
            ]
        }

        self.assertEqual(find_bank_range_collisions(pad_meta), [])

    def test_bank_range_collision_helper_warns_for_same_channel_overlap(self) -> None:
        pad_meta = {
            "banks": [
                {"id": "bank_1", "channel": 1, "notes": [32, 33, 34]},
                {"id": "bank_2", "channel": 1, "notes": [34, 35]},
            ]
        }

        collisions = find_bank_range_collisions(pad_meta)

        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]["bank_a"], "bank_1")
        self.assertEqual(collisions[0]["bank_b"], "bank_2")
        self.assertEqual(collisions[0]["channel"], 1)
        self.assertEqual(collisions[0]["overlap_notes"], [34])

    def test_bank_range_collision_helper_ignores_different_channels(self) -> None:
        pad_meta = {
            "banks": [
                {"id": "bank_1", "channel": 1, "notes": [32, 33, 34]},
                {"id": "bank_2", "channel": 2, "notes": [34, 35]},
            ]
        }

        self.assertEqual(find_bank_range_collisions(pad_meta), [])

    def test_validate_config_data_surfaces_bank_overlap_as_warning(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        cfg["_pad_meta"]["banks"][1]["notes"] = [31, 32, 33]

        errors, warnings = validate_config_data(cfg)

        self.assertEqual(errors, [])
        self.assertTrue(any("bank channel overlap" in warning for warning in warnings))

    def test_apply_mapping_keeps_primary_and_appends_bank(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = apply_mapping(cfg, personality="house", role="groove", note=45)

        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_scene"], first)
        self.assertEqual(house["default_scene"], first)
        self.assertEqual(house["phrase_bank"], [first, second])

    def test_drop_mode_reuses_drop_mapping_for_post_drop(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        drop_scene = apply_mapping(cfg, personality="house", role="drop", note=40)

        house = cfg["personalities"]["house"]
        self.assertEqual(house["drop_style"], "drop_mode")
        self.assertEqual(house["post_drop_scene"], drop_scene)
        self.assertEqual(house["post_drop_bank"], [drop_scene])

    def test_emphasized_drop_supports_separate_post_drop_mapping(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        cfg["personalities"]["house"]["drop_style"] = "emphasized_drop"
        drop_scene = apply_mapping(cfg, personality="house", role="drop", note=40)
        post_scene = apply_mapping(cfg, personality="house", role="post_drop", note=41)

        house = cfg["personalities"]["house"]
        self.assertNotEqual(drop_scene, post_scene)
        self.assertEqual(house["drop_scene"], drop_scene)
        self.assertEqual(house["post_drop_scene"], post_scene)

    def test_existing_legacy_personality_shape_is_reshaped(self) -> None:
        cfg = {
            "enabled": False,
            "dry_run": True,
            "default_personality": "legacy",
            "personalities": {
                "legacy": {
                    "scene": "legacy_scene",
                }
            },
            "scenes": {
                "legacy_scene": {
                    "scene_type": "autoloop",
                    "safety_class": "movement_low",
                    "fallback_scene": "safe_static",
                    "cooldown_beats": 8,
                    "immediate": False,
                    "midi": {
                        "kind": "note_pulse",
                        "behavior": "pulse",
                        "channel": 1,
                        "note": 12,
                        "velocity": 127,
                        "duration_ms": 80,
                    },
                }
            },
        }

        scene = apply_mapping(cfg, personality="legacy", role="groove", note=37)

        legacy = cfg["personalities"]["legacy"]
        self.assertEqual(legacy["phrase_scene"], scene)
        self.assertIn(scene, legacy["phrase_bank"])
        self.assertIn("drop_style", legacy)

    def test_existing_personality_defaults_are_backfilled_with_isolated_mutables(self) -> None:
        cfg = {
            "personalities": {
                "house": {
                    "safe_scene": "custom_safe",
                },
            },
        }

        _ensure_personality_exists(cfg, "house")

        house = cfg["personalities"]["house"]
        self.assertEqual(house["safe_scene"], "custom_safe")
        self.assertEqual(house["phrase_bank"], [])
        self.assertEqual(house["minimum_scene_hold_beats"], 8)

        house["phrase_bank"].append("mutated_scene")
        cfg["personalities"]["techno"] = {"safe_scene": "techno_safe"}
        _ensure_personality_exists(cfg, "techno")

        self.assertEqual(cfg["personalities"]["techno"]["phrase_bank"], [])

    def test_personality_timing_scene_cooldown_and_safety_mutators(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)

        update_personality_timing(
            cfg,
            personality="house",
            phrase_interval_beats=48,
            minimum_scene_hold_beats=10,
            buildup_lookahead_beats=24,
        )
        update_scene_cooldown(cfg, scene_name=scene, cooldown_beats=12.5)
        update_scene_safety_class(cfg, scene_name=scene, safety_class="strobe")

        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_interval_beats"], 48)
        self.assertEqual(house["minimum_scene_hold_beats"], 10)
        self.assertEqual(house["buildup_lookahead_beats"], 24)
        self.assertEqual(cfg["scenes"][scene]["cooldown_beats"], 12.5)
        self.assertEqual(cfg["scenes"][scene]["safety_class"], "strobe")

    def test_role_bank_cooldown_and_mixed_cooldown_detection(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = apply_mapping(cfg, personality="house", role="groove", note=45)
        cfg["scenes"][first]["cooldown_beats"] = 16
        cfg["scenes"][second]["cooldown_beats"] = 8

        mixed, values = detect_mixed_role_cooldowns(cfg, personality="house", role="groove")
        update_role_bank_cooldown(cfg, personality="house", role="groove", cooldown_beats=18)

        self.assertTrue(mixed)
        self.assertEqual(values, [8.0, 16.0])
        for scene in cfg["personalities"]["house"]["phrase_bank"]:
            self.assertEqual(cfg["scenes"][scene]["cooldown_beats"], 18.0)

    def test_summary_displays_cooldown_behavior_and_drop_mode(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        apply_mapping(cfg, personality="house", role="groove", note=37)
        apply_mapping(cfg, personality="house", role="groove", note=45)
        apply_mapping(cfg, personality="house", role="drop", note=40)

        summary = render_personality_summary(cfg, "house")

        self.assertIn("house (default)", summary)
        self.assertIn("notes 37,45", summary)
        self.assertIn("Drop style: Drop mode", summary)
        self.assertNotIn("post_drop", summary)


if __name__ == "__main__":
    unittest.main()
