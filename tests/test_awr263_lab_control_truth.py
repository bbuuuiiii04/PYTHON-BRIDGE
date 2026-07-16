"""AWR-263: lab control truth + New-cue clone flow (master-plan R4)."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from rb_ss_bridge_v2.led_pad_controls import (
    FIREWORK_EXPLOSION_LAB_SPECS,
    CONTROL_META,
    effective_lab_specs,
)
from rb_ss_bridge_v2.tools.led_pad_lab import LabRegistry, slugify_lab_name
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService, _lab_firework_specs_dead


_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


class _FakePlayback:
    ownership_state = "free"
    bpm = 128.0
    loop = True
    playing = ""
    frame_index = 0

    def ownership(self) -> dict:
        return {"state": self.ownership_state, "warning": ""}

    def request_takeover(self) -> None:
        self.ownership_state = "pad_owned"

    def play(self, spec: dict, *, cue_beats: float, loop: bool) -> None:
        self.playing = spec["look_name"]

    def update(self, spec: dict) -> None:
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
        self.ownership_state = "free"
        self.stop()

    def status(self) -> dict:
        return {"playing_look": self.playing, "frame_index": self.frame_index, "playing": bool(self.playing)}


class SlugifyLabNameTests(unittest.TestCase):
    def test_display_name_to_slug_with_collision_suffix(self) -> None:
        self.assertEqual(slugify_lab_name("My Test Cue"), "my_test_cue")
        self.assertEqual(
            slugify_lab_name("My Test Cue", {"my_test_cue", "my_test_cue_2"}),
            "my_test_cue_3",
        )


class FireworkSpecRepairTests(unittest.TestCase):
    def test_dead_color_b_and_sparkles_rate_detected(self) -> None:
        dead = {
            "color_b_r": {"kind": "slider", "label": "Sparkles R", "min": 0, "max": 255, "step": 5},
            "sparkles_per_beat": {"kind": "slider", "label": "Rate", "min": 2, "max": 16, "step": 2},
        }
        self.assertTrue(_lab_firework_specs_dead(dead, "drop_firework_explosion_2"))
        self.assertFalse(_lab_firework_specs_dead(FIREWORK_EXPLOSION_LAB_SPECS, "drop_firework_explosion_2"))
        self.assertIn("spark_a_r", FIREWORK_EXPLOSION_LAB_SPECS)
        self.assertNotIn("sparkles_per_beat", FIREWORK_EXPLOSION_LAB_SPECS)
        self.assertNotIn("color_b_r", FIREWORK_EXPLOSION_LAB_SPECS)


class LabListDecorationsTests(unittest.TestCase):
    def test_list_marks_previewable_and_upgrades_enums(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = root / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, cfg)
            lab_dir = root / "led_lab"
            lab_dir.mkdir()
            (lab_dir / "effects_lab.py").write_text(
                "def pulse(beat_pos, local_t, frame_index, params, segments, seed):\n"
                "    return [(0, 0, 0)] * max(0, int(segments))\n"
                "LAB_EFFECTS = {'pulse': ('frame', pulse)}\n",
                encoding="utf-8",
            )
            registry = LabRegistry(lab_dir)
            registry.save({
                "name": "pulse",
                "kind": "frame",
                "fn": "pulse",
                "params": {"zone": 1, "texture": 0},
                "param_specs": {
                    "zone": {"kind": "slider", "label": "Zone", "min": 0, "max": 6, "step": 1},
                    "texture": {"kind": "slider", "label": "Texture", "min": 0, "max": 2, "step": 1},
                },
            })
            registry.save({
                "name": "shell_only",
                "kind": "slot",
                "fn": "shell_only",
                "params": {},
                "param_specs": {},
            })
            service = LedPadService(cfg, dry_run=True, playback=_FakePlayback(), lab_dir=lab_dir)
            listed = service.lab_list()
            by_name = {e["name"]: e for e in listed["entries"]}
            self.assertTrue(by_name["pulse"]["previewable"])
            self.assertFalse(by_name["shell_only"]["previewable"])
            self.assertEqual(by_name["pulse"]["effective_param_specs"]["zone"]["kind"], "select")
            self.assertEqual(by_name["pulse"]["effective_param_specs"]["texture"]["kind"], "select")
            labels = [o["label"] for o in by_name["pulse"]["effective_param_specs"]["zone"]["options"]]
            self.assertEqual(labels[0], "GLA")


class CycleBeatsLabelTests(unittest.TestCase):
    def test_draft_cycle_beats_label_not_rainbow_stomped(self) -> None:
        specs = {
            "cycle_beats": {
                "kind": "slider",
                "label": "Beats per collision",
                "min": 2,
                "max": 8,
                "step": 1,
            },
        }
        effective, _ = effective_lab_specs(specs)
        self.assertEqual(effective["cycle_beats"]["label"], "Beats per collision")
        self.assertEqual(CONTROL_META["cycle_beats"]["label"], "Color cycle (beats)")


class CloneNewPayloadContractTests(unittest.TestCase):
    """Server-side shape the New dialog posts when cloning a starter."""

    def test_clone_keeps_fn_and_specs_under_new_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            registry = LabRegistry(Path(td) / "led_lab")
            registry.save({
                "name": "starter_cue",
                "kind": "frame",
                "fn": "drop_firework_explosion_2",
                "params": {"surge_beats": 0.5},
                "param_specs": {"surge_beats": {"kind": "slider", "label": "Surge", "min": 0.1, "max": 4, "step": 0.1}},
                "brief": "old",
                "status": "accepted",
            })
            starter = registry.get("starter_cue")
            display = "My Test Cue"
            name = slugify_lab_name(display, {starter["name"]})
            registry.save({
                "name": name,
                "kind": starter["kind"],
                "fn": starter["fn"],
                "params": dict(starter["params"]),
                "param_specs": dict(starter["param_specs"]),
                "brief": display,
                "status": "iterating",
            })
            clone = registry.get(name)
            self.assertEqual(name, "my_test_cue")
            self.assertEqual(clone["fn"], "drop_firework_explosion_2")
            self.assertEqual(clone["brief"], "My Test Cue")
            self.assertEqual(clone["status"], "iterating")
            self.assertEqual(clone["param_specs"]["surge_beats"]["label"], "Surge")


if __name__ == "__main__":
    unittest.main()
