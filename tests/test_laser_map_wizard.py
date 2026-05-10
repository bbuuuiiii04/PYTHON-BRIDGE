from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.laser_map_wizard import (  # noqa: E402
    apply_mapping,
    detect_mixed_role_cooldowns,
    find_duplicate_notes,
    get_main_menu_options,
    is_back_command,
    load_or_create_config,
    parse_midi_note,
    render_personality_summary,
    save_config_atomically,
    suggest_personality,
    suggest_role,
    update_personality_timing,
    update_scene_safety_class,
    update_scene_cooldown,
    update_role_bank_cooldown,
    _warn_duplicate_note,
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

    def test_first_mapping_sets_primary_and_phrase_bank(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)
        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_scene"], scene)
        self.assertEqual(house["default_scene"], scene)
        self.assertIn(scene, house["phrase_bank"])
        self.assertEqual(cfg["scenes"][scene]["midi"]["note"], 37)

    def test_second_mapping_auto_appends_bank_keeps_primary(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = apply_mapping(cfg, personality="house", role="groove", note=45)
        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_scene"], first)
        self.assertEqual(house["phrase_bank"], [first, second])
        self.assertNotEqual(first, second)

    def test_auto_bank_for_all_roles(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        apply_mapping(cfg, personality="house", role="buildup", note=38)
        apply_mapping(cfg, personality="house", role="buildup", note=47)
        apply_mapping(cfg, personality="house", role="drop", note=40)
        apply_mapping(cfg, personality="house", role="drop", note=48)
        apply_mapping(cfg, personality="house", role="post_drop", note=41)
        apply_mapping(cfg, personality="house", role="post_drop", note=49)
        apply_mapping(cfg, personality="house", role="breakdown", note=42)
        apply_mapping(cfg, personality="house", role="breakdown", note=50)
        house = cfg["personalities"]["house"]
        self.assertEqual(len(house["buildup_bank"]), 2)
        self.assertEqual(len(house["drop_bank"]), 2)
        self.assertEqual(len(house["post_drop_bank"]), 2)
        self.assertEqual(len(house["breakdown_bank"]), 2)

    def test_drop_defaults_to_hold_for_beats(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="drop", note=40)
        midi = cfg["scenes"][scene]["midi"]
        self.assertEqual(midi["behavior"], "hold_beats")
        self.assertEqual(midi["kind"], "note_on")
        self.assertGreater(midi["hold_beats"], 0)

    def test_role_defaults_write_internal_safety_class(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        roles = [
            ("groove", 37, "movement_low"),
            ("buildup", 38, "movement_medium"),
            ("drop", 40, "high_impact"),
            ("post_drop", 41, "movement_high"),
            ("breakdown", 42, "movement_low"),
        ]
        for role, note, expected in roles:
            scene = apply_mapping(cfg, personality="house", role=role, note=note)
            self.assertEqual(cfg["scenes"][scene]["safety_class"], expected)

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

    def test_duplicate_note_warning_defaults_to_no(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        apply_mapping(cfg, personality="house", role="groove", note=37)
        apply_mapping(cfg, personality="house", role="drop", note=37)
        self.assertFalse(_warn_duplicate_note(cfg, 37, ("house", "drop"), confirm_response=""))

    def test_duplicate_bank_entries_are_not_added(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        again = apply_mapping(cfg, personality="house", role="groove", note=37)
        bank = cfg["personalities"]["house"]["phrase_bank"]
        self.assertEqual(first, again)
        self.assertEqual(bank.count(first), 1)

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

    def test_back_commands_supported(self) -> None:
        for token in ("esc", "back", "b", "cancel", "\x1b"):
            self.assertTrue(is_back_command(token))

    def test_timing_menu_reachable_from_main_menu(self) -> None:
        options = get_main_menu_options()
        self.assertIn("Timing / Cooldowns", options)
        self.assertIn("Advanced Safety Metadata", options)
        self.assertNotIn("Edit one scene cooldown", options)

    def test_edit_personality_timing_updates_fields(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        update_personality_timing(
            cfg,
            personality="house",
            phrase_interval_beats=48,
            minimum_scene_hold_beats=10,
            buildup_lookahead_beats=24,
        )
        house = cfg["personalities"]["house"]
        self.assertEqual(house["phrase_interval_beats"], 48)
        self.assertEqual(house["minimum_scene_hold_beats"], 10)
        self.assertEqual(house["buildup_lookahead_beats"], 24)

    def test_edit_scene_cooldown_updates_field(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)
        update_scene_cooldown(cfg, scene_name=scene, cooldown_beats=12.5)
        self.assertEqual(cfg["scenes"][scene]["cooldown_beats"], 12.5)

    def test_invalid_cooldown_values_fail(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)
        with self.assertRaises(ValueError):
            update_scene_cooldown(cfg, scene_name=scene, cooldown_beats=-1)

    def test_role_bank_cooldown_update(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = apply_mapping(cfg, personality="house", role="groove", note=45)
        notes_before = {
            first: cfg["scenes"][first]["midi"]["note"],
            second: cfg["scenes"][second]["midi"]["note"],
        }
        behavior_before = {
            first: cfg["scenes"][first]["midi"]["behavior"],
            second: cfg["scenes"][second]["midi"]["behavior"],
        }
        update_role_bank_cooldown(
            cfg,
            personality="house",
            role="groove",
            cooldown_beats=18,
        )
        for scene in cfg["personalities"]["house"]["phrase_bank"]:
            self.assertEqual(cfg["scenes"][scene]["cooldown_beats"], 18.0)
            self.assertEqual(cfg["scenes"][scene]["midi"]["note"], notes_before[scene])
            self.assertEqual(cfg["scenes"][scene]["midi"]["behavior"], behavior_before[scene])
        self.assertEqual(cfg["personalities"]["house"]["phrase_scene"], first)

    def test_role_cooldown_update_for_other_banks(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        role_map = [
            ("buildup", [38, 47], "buildup_bank"),
            ("drop", [40, 48], "drop_bank"),
            ("post_drop", [41, 49], "post_drop_bank"),
            ("breakdown", [42, 50], "breakdown_bank"),
        ]
        for role, notes, bank_field in role_map:
            for note in notes:
                apply_mapping(cfg, personality="house", role=role, note=note)
            update_role_bank_cooldown(cfg, personality="house", role=role, cooldown_beats=11)
            for scene in cfg["personalities"]["house"][bank_field]:
                self.assertEqual(cfg["scenes"][scene]["cooldown_beats"], 11.0)

    def test_mixed_role_cooldowns_detected(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        first = apply_mapping(cfg, personality="house", role="groove", note=37)
        second = apply_mapping(cfg, personality="house", role="groove", note=45)
        cfg["scenes"][first]["cooldown_beats"] = 16
        cfg["scenes"][second]["cooldown_beats"] = 8
        mixed, values = detect_mixed_role_cooldowns(
            cfg,
            personality="house",
            role="groove",
        )
        self.assertTrue(mixed)
        self.assertEqual(values, [8.0, 16.0])

    def test_summary_displays_cooldown_and_behavior(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        apply_mapping(cfg, personality="house", role="groove", note=37)
        apply_mapping(cfg, personality="house", role="groove", note=45)
        apply_mapping(cfg, personality="house", role="drop", note=40)
        summary = render_personality_summary(cfg, "house")
        self.assertIn("house (default)", summary)
        self.assertIn("groove", summary)
        self.assertIn("notes 37,45", summary)
        self.assertIn("hold 4 beats", summary)
        self.assertNotIn("Gentle movement", summary)
        self.assertNotIn("High impact", summary)

    def test_advanced_safety_edit_updates_value(self) -> None:
        cfg = load_or_create_config(Path("/tmp/not-used.json"))
        scene = apply_mapping(cfg, personality="house", role="groove", note=37)
        update_scene_safety_class(cfg, scene_name=scene, safety_class="strobe")
        self.assertEqual(cfg["scenes"][scene]["safety_class"], "strobe")


if __name__ == "__main__":
    unittest.main()
