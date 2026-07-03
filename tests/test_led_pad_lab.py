from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_lab import LabRegistry, LabRenderer, load_lab_effects  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_web import LedPadService  # noqa: E402

_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"


def _write_lab_module(path: Path, value: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "def pulse(beat_pos, local_t, frame_index, params, segments, seed):",
                f"    level = params.get('level', {value})",
                "    return [[level, 0, 0, 0, 0, 1] for _ in range(segments)]",
                "LAB_EFFECTS = {'pulse': ('slot', pulse)}",
                "",
            ]
        ),
        encoding="utf-8",
    )


class _FakePlayback:
    def __init__(self) -> None:
        self.playing = ""
        self.play_calls: list[dict] = []
        self.frame_index = 0

    def ownership(self) -> dict:
        return {"state": "free", "warning": ""}

    def play(self, spec: dict, *, cue_beats: float, loop: bool) -> None:
        self.playing = spec["look_name"]
        self.play_calls.append({"spec": spec, "cue_beats": cue_beats, "loop": loop})

    def status(self) -> dict:
        self.frame_index += 1
        return {"playing": bool(self.playing), "playing_look": self.playing, "frame_index": self.frame_index}

    def set_bpm(self, _bpm: float) -> None:
        pass

    def set_loop(self, _loop: bool) -> None:
        pass

    def update(self, _spec: dict) -> None:
        pass

    def stop(self) -> None:
        self.playing = ""

    def emergency_stop(self) -> None:
        self.stop()

    def release(self) -> None:
        self.stop()


class LedPadLabTests(unittest.TestCase):
    def test_registry_round_trip_and_name_collision(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            registry = LabRegistry(Path(td) / "led_lab")
            saved = registry.save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {"level": 1}, "brief": "b", "notes": "n"})

            self.assertEqual(saved["entry"]["name"], "pulse")
            self.assertEqual(registry.get("pulse")["params"], {"level": 1})
            with self.assertRaisesRegex(ValueError, "collides"):
                registry.save({"name": "rt_groove_chase", "kind": "slot", "fn": "pulse"})

    def test_hot_reload_and_broken_module_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            module = Path(td) / "effects_lab.py"
            _write_lab_module(module, 0.25)
            first = load_lab_effects(module)
            _write_lab_module(module, 0.75)
            second = load_lab_effects(module)
            module.write_text("def nope(:\n", encoding="utf-8")
            broken = load_lab_effects(module)

            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertIsNot(first["effects"]["pulse"][1], second["effects"]["pulse"][1])
            self.assertFalse(broken["ok"])
            self.assertIn("Traceback", broken["traceback"])

    def test_lab_renderer_slot_colorizes_unknown_dark_and_production_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            module = Path(td) / "effects_lab.py"
            _write_lab_module(module)
            renderer = LabRenderer(module)
            renderer.reload()
            params = {"slot_colors": [(10, 0, 0), (0, 10, 0), (0, 0, 10), (1, 1, 1), (2, 2, 2), (255, 255, 255)]}

            frame = renderer.render("lab_pulse", beat_pos=0, local_t=0, frame_index=0, params=params, segments=3, seed=1)
            unknown = renderer.render("lab_missing", beat_pos=0, local_t=0, frame_index=0, params=params, segments=3, seed=1)
            direct = GoveeFrameRenderer().render("rt_twinkle", beat_pos=1, local_t=0.5, frame_index=2, params={}, segments=4, seed=3)
            delegated = renderer.render("rt_twinkle", beat_pos=1, local_t=0.5, frame_index=2, params={}, segments=4, seed=3)

            self.assertEqual(frame, [(255, 255, 255)] * 3)
            self.assertEqual(unknown, [(0, 0, 0)] * 3)
            self.assertEqual(delegated, direct)

    def test_lab_play_preempts_pad_play_in_shared_slot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "led_look_director.json"
            shutil.copy2(_EXAMPLE_PATH, config)
            lab_dir = root / "led_lab"
            _write_lab_module(lab_dir / "effects_lab.py")
            registry = LabRegistry(lab_dir)
            registry.save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": {}, "cue_beats": 8})
            playback = _FakePlayback()
            service = LedPadService(config, dry_run=True, playback=playback, lab_dir=lab_dir)

            service.play({"name": "rt_groove_chase"})
            service.lab_play({"name": "pulse"})

            self.assertEqual(playback.play_calls[0]["spec"]["look_name"], "rt_groove_chase")
            self.assertEqual(playback.play_calls[1]["spec"]["look_name"], "lab_pulse")
            self.assertEqual(service.runtime_status()["playing_look"], "lab_pulse")


if __name__ == "__main__":
    unittest.main()
