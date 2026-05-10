from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.laser_map_wizard import (  # noqa: E402
    add_mapping_to_bank,
    apply_mapping,
    find_duplicate_notes,
    load_or_create_config,
    parse_midi_note,
    save_config_atomically,
    suggest_personality,
    suggest_role,
)


class LaserMapWizardTests(unittest.TestCase):
    def test_create_config_from_scratch_defaults_dry_run_true(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            cfg = load_or_create_config(path)
            self.assertTrue(cfg["dry_run"])
            self.assertEqual(cfg["default_personality"], "house")
            self.assertIn("safe_static", cfg["scenes"])
            self.assertIn("emergency_blackout", cfg["scenes"])

    def test_map_house_groove_updates_phrase_fields(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)
        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_scene"], scene)
        self.assertEqual(house["default_scene"], scene)
        self.assertIn(scene, house["phrase_bank"])
        self.assertEqual(cfg["scenes"][scene]["midi"]["note"], 37)

    def test_map_roles_update_expected_fields(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        b = apply_mapping(cfg, personality="house", role="buildup", note=38)
        d = apply_mapping(cfg, personality="house", role="drop", note=40)
        p = apply_mapping(cfg, personality="house", role="post_drop", note=41)
        k = apply_mapping(cfg, personality="house", role="breakdown", note=42)
        house = cfg["personalities"]["house"]
        self.assertEqual(house["buildup_scene"], b)
        self.assertEqual(house["drop_scene"], d)
        self.assertEqual(house["post_drop_scene"], p)
        self.assertEqual(house["breakdown_scene"], k)

    def test_drop_defaults_to_hold_for_beats(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="drop", note=40)
        midi = cfg["scenes"][scene]["midi"]
        self.assertEqual(midi["behavior"], "hold_beats")
        self.assertEqual(midi["kind"], "note_on")
        self.assertGreater(midi["hold_beats"], 0)

    def test_typo_suggestions(self) -> None:
        self.assertEqual(suggest_personality("housse"), "house")
        self.assertEqual(suggest_role("buidup"), "buildup")

    def test_invalid_notes_fail(self) -> None:
        with self.assertRaises(ValueError):
            parse_midi_note("-1")
        with self.assertRaises(ValueError):
            parse_midi_note("128")

    def test_duplicate_note_warning_detects_duplicates(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        apply_mapping(cfg, personality="house", role="groove", note=40)
        apply_mapping(cfg, personality="house", role="drop", note=40)
        duplicates = find_duplicate_notes(cfg)
        self.assertTrue(any(note == 40 for note, _ in duplicates))

    def test_add_bank_appends_new_scene(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = add_mapping_to_bank(cfg, personality="house", role="groove", note=45)
        bank = cfg["personalities"]["house"]["phrase_bank"]
        self.assertIn(first, bank)
        self.assertIn(second, bank)
        self.assertEqual(len(set(bank)), len(bank))

    def test_existing_custom_scenes_preserved(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        cfg["scenes"]["custom_scene"] = {
            "scene_type": "autoloop",
            "safety_class": "movement_low",
            "fallback_scene": "safe_static",
            "cooldown_beats": 4,
            "immediate": False,
            "midi": {
                "kind": "note_pulse",
                "behavior": "pulse",
                "channel": 1,
                "note": 99,
                "velocity": 127,
                "duration_ms": 80,
            },
        }
        apply_mapping(cfg, personality="house", role="groove", note=37)
        self.assertIn("custom_scene", cfg["scenes"])
        self.assertEqual(cfg["scenes"]["custom_scene"]["midi"]["note"], 99)

    def test_backup_created_before_save(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "laser_director.json"
            path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
            cfg = load_or_create_config(path)
            backup = save_config_atomically(cfg, path)
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
