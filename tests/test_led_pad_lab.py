from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.tools.led_pad_lab import LabRegistry, LabRenderer, load_lab_effects, render_preview_frames  # noqa: E402
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


def _write_two_effect_module(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "def fn_a(beat_pos, local_t, frame_index, params, segments, seed):",
                "    level = params.get('level', 1.0)",
                "    return [[level, 0, 0, 0, 0, 1] for _ in range(segments)]",
                "",
                "def fn_b(beat_pos, local_t, frame_index, params, segments, seed):",
                "    level = params.get('level', 1.0)",
                "    return [[0, level, 0, 0, 0, 1] for _ in range(segments)]",
                "",
                "LAB_EFFECTS = {'a': ('slot', fn_a), 'b': ('slot', fn_b)}",
                "",
            ]
        ),
        encoding="utf-8",
    )


class _FakePlayback:
    def __init__(self) -> None:
        self.playing = ""
        self.play_calls: list[dict] = []
        self.update_calls: list[dict] = []
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

    def update(self, spec: dict) -> None:
        self.update_calls.append(spec)
        self.playing = spec["look_name"]

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

    def test_render_preview_frames_deterministic_count_and_clamping(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            module = Path(td) / "effects_lab.py"
            _write_lab_module(module, 0.5)
            renderer = LabRenderer(module)
            renderer.reload()
            params = {"slot_colors": [(300, -5, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)]}

            frames_a = render_preview_frames(renderer, "lab_pulse", params=params, segments=4, seed=1, fps=10, bpm=120.0, beats=2.0)
            frames_b = render_preview_frames(renderer, "lab_pulse", params=params, segments=4, seed=1, fps=10, bpm=120.0, beats=2.0)

            expected_count = round(2.0 * 60.0 / 120.0 * 10)
            self.assertEqual(len(frames_a), expected_count)
            self.assertEqual(frames_a, frames_b)
            for frame in frames_a:
                self.assertEqual(len(frame), 4)
                for channel in frame:
                    self.assertEqual(len(channel), 3)
                    for value in channel:
                        self.assertIsInstance(value, int)
                        self.assertGreaterEqual(value, 0)
                        self.assertLessEqual(value, 255)

            floored = render_preview_frames(renderer, "lab_pulse", params=params, segments=4, seed=1, fps=1, bpm=200.0, beats=0.001)
            self.assertEqual(len(floored), 1)

            capped = render_preview_frames(renderer, "lab_pulse", params=params, segments=4, seed=1, fps=40, bpm=40.0, beats=32.0, max_frames=5)
            self.assertEqual(len(capped), 5)

    def _service_with_pulse_draft(self, root: Path, *, params: dict | None = None) -> tuple[LedPadService, _FakePlayback]:
        config = root / "led_look_director.json"
        shutil.copy2(_EXAMPLE_PATH, config)
        lab_dir = root / "led_lab"
        _write_lab_module(lab_dir / "effects_lab.py")
        registry = LabRegistry(lab_dir)
        registry.save({"name": "pulse", "kind": "slot", "fn": "pulse", "params": params or {}, "cue_beats": 8})
        playback = _FakePlayback()
        service = LedPadService(config, dry_run=True, playback=playback, lab_dir=lab_dir)
        return service, playback

    def test_lab_preview_returns_frames_without_playback_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_pulse_draft(Path(td))

            result = service.lab_preview({"name": "pulse", "beats": 1.0, "bpm": 120.0})

            self.assertTrue(result["ok"])
            self.assertIn("frames", result)
            self.assertTrue(result["frames"])
            self.assertIn("fps", result)
            self.assertIn("bpm", result)
            self.assertIn("beats", result)
            self.assertIn("segments", result)
            self.assertEqual(playback.play_calls, [])
            self.assertEqual(playback.update_calls, [])
            self.assertEqual(playback.playing, "")

    def test_lab_preview_unknown_draft_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._service_with_pulse_draft(Path(td))

            with self.assertRaises(ValueError):
                service.lab_preview({"name": "missing"})

    def test_lab_preview_unregistered_fn_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._service_with_pulse_draft(Path(td))
            service.lab_save({"name": "ghost", "kind": "slot", "fn": "ghost", "params": {}, "cue_beats": 8})

            with self.assertRaises(ValueError):
                service.lab_preview({"name": "ghost"})

    def test_lab_preview_broken_module_returns_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service, playback = self._service_with_pulse_draft(root)
            (root / "led_lab" / "effects_lab.py").write_text("def nope(:\n", encoding="utf-8")

            result = service.lab_preview({"name": "pulse"})

            self.assertFalse(result["ok"])
            self.assertTrue(result["traceback"])
            self.assertEqual(playback.play_calls, [])
            self.assertEqual(playback.update_calls, [])

    def test_lab_update_applies_and_overlays_payload_params_over_saved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_pulse_draft(Path(td), params={"level": 0.3})

            service.lab_play({"name": "pulse"})
            result = service.lab_update({"name": "pulse", "params": {"level": 0.9}})

            self.assertTrue(result["applied"])
            self.assertEqual(len(playback.update_calls), 1)
            self.assertEqual(playback.update_calls[0]["scene_ref"], "lab_pulse")
            self.assertEqual(playback.update_calls[0]["params"]["level"], 0.9)
            self.assertEqual(len(playback.play_calls), 1)

    def test_lab_update_not_applied_when_not_playing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_pulse_draft(Path(td))

            result = service.lab_update({"name": "pulse"})

            self.assertEqual(result, {"ok": True, "applied": False})
            self.assertEqual(service._playing_name, "")
            self.assertEqual(playback.update_calls, [])

    def test_lab_update_not_applied_for_different_playing_look(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_pulse_draft(Path(td))

            service.play({"name": "rt_groove_chase"})
            result = service.lab_update({"name": "pulse"})

            self.assertEqual(result, {"ok": True, "applied": False})
            self.assertEqual(playback.update_calls, [])

    def test_lab_update_live_code_swap_reflects_in_live_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service, _playback = self._service_with_pulse_draft(root)
            module = root / "led_lab" / "effects_lab.py"

            service.lab_play({"name": "pulse"})
            original_fn = service._lab_renderer.effects["pulse"][1]

            module.write_text(
                "\n".join(
                    [
                        "def pulse(beat_pos, local_t, frame_index, params, segments, seed):",
                        "    return [[0, params.get('level', 1.0), 0, 0, 0, 1] for _ in range(segments)]",
                        "LAB_EFFECTS = {'pulse': ('slot', pulse)}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            service.lab_update({"name": "pulse"})

            self.assertIsNot(service._lab_renderer.effects["pulse"][1], original_fn)

    def _service_with_ab_drafts(self, root: Path) -> tuple[LedPadService, _FakePlayback]:
        config = root / "led_look_director.json"
        shutil.copy2(_EXAMPLE_PATH, config)
        lab_dir = root / "led_lab"
        _write_two_effect_module(lab_dir / "effects_lab.py")
        registry = LabRegistry(lab_dir)
        registry.save({"name": "a", "kind": "slot", "fn": "fn_a", "params": {}, "cue_beats": 8})
        registry.save({"name": "b", "kind": "slot", "fn": "fn_b", "params": {}, "cue_beats": 8})
        playback = _FakePlayback()
        service = LedPadService(config, dry_run=True, playback=playback, lab_dir=lab_dir)
        return service, playback

    def test_lab_switch_seamlessly_swaps_between_lab_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_ab_drafts(Path(td))

            service.lab_play({"name": "a"})
            result = service.lab_switch({"name": "b"})

            self.assertTrue(result["ok"])
            self.assertTrue(result["applied"])
            self.assertEqual(len(playback.update_calls), 1)
            self.assertEqual(playback.update_calls[0]["scene_ref"], "lab_b")
            self.assertEqual(len(playback.play_calls), 1)
            self.assertEqual(service.runtime_status()["playing_look"], "lab_b")

            follow_up = service.lab_update({"name": "b", "params": {"level": 0.5}})
            self.assertTrue(follow_up["applied"])

    def test_lab_switch_refuses_when_nothing_playing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_ab_drafts(Path(td))

            result = service.lab_switch({"name": "b"})

            self.assertEqual(result, {"ok": False, "error": "no_lab_scene_playing"})
            self.assertEqual(playback.update_calls, [])

    def test_lab_switch_refuses_when_pad_look_playing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, playback = self._service_with_ab_drafts(Path(td))

            service.play({"name": "rt_groove_chase"})
            result = service.lab_switch({"name": "b"})

            self.assertEqual(result, {"ok": False, "error": "no_lab_scene_playing"})
            self.assertEqual(playback.update_calls, [])

    def test_lab_switch_unknown_draft_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            service, _playback = self._service_with_ab_drafts(Path(td))

            with self.assertRaises(ValueError):
                service.lab_switch({"name": "missing"})


if __name__ == "__main__":
    unittest.main()
