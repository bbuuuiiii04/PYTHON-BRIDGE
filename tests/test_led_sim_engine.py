from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import led_sim_engine as engine  # noqa: E402

_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json"


def _profile(**overrides) -> dict:
    base = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
    base.update(overrides)
    return base


class BleedTests(unittest.TestCase):
    def test_linear_strip_exact_values_without_endpoint_wrap(self) -> None:
        frame = [(100, 0, 0), (0, 100, 0), (0, 0, 100), (0, 0, 0)]
        out = engine.apply_bleed(frame, 0.5)
        self.assertEqual(out, [(75, 25, 0), (25, 50, 25), (0, 25, 50), (0, 0, 25)])

    def test_bleed_zero_identity(self) -> None:
        frame = [(1, 2, 3), (4, 5, 6), (7, 8, 9)]
        self.assertEqual(engine.apply_bleed(frame, 0.0), frame)

    def test_clamped_channels_stay_in_range(self) -> None:
        frame = [(255, 255, 255)] * 4
        out = engine.apply_bleed(frame, 1.0)
        self.assertEqual(out, frame)  # convex kernel: white stays white
        for px in engine.apply_bleed([(0, 0, 0), (255, 0, 0)], 0.7):
            for channel in px:
                self.assertGreaterEqual(channel, 0)
                self.assertLessEqual(channel, 255)


class H612DModelTests(unittest.TestCase):
    def test_expands_every_segment_to_six_emitters(self) -> None:
        frame = [(1, 2, 3), (4, 5, 6)]
        expanded = engine.expand_segments(frame)
        self.assertEqual(expanded, [(1, 2, 3)] * 6 + [(4, 5, 6)] * 6)
        self.assertEqual(len(engine.expand_segments([(0, 0, 0)] * 60)), 360)

    def test_reference_transfer_and_bleed(self) -> None:
        profile = _profile(gamma=1.0, brightness=0.5, white_point=[1.0, 0.5, 2.0], bleed=0.0)
        self.assertEqual(engine.transform_color((200, 200, 100), profile), (100, 50, 100))
        self.assertEqual(engine.device_segments([(200, 200, 100)], profile), [(100, 50, 100)])


class RenderAdapterTests(unittest.TestCase):
    def test_determinism_and_shape(self) -> None:
        kwargs = dict(params={}, seed=7, fps=30, duration_s=2.0, bpm=120.0, segments=60)
        first = engine.render_frames("beat_chase", **kwargs)
        second = engine.render_frames("beat_chase", **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 60)  # fps * duration
        self.assertEqual(len(first[0]), 60)  # segments wide

    def test_runtime_capture_uses_production_runner(self) -> None:
        frames = engine.render_runtime_frames(
            "solid", params={"color": [1, 2, 3]}, seed=7,
            fps=20, duration_s=0.5, bpm=120.0, segments=60,
        )
        self.assertEqual(len(frames), 10)
        self.assertTrue(all(frame == [(1, 2, 3)] * 60 for frame in frames))

    def test_unknown_name_fails_dark(self) -> None:
        # Pinned to render_preview_frames parity: the production renderer returns
        # all-black frames for unknown names (no exception).
        frames = engine.render_frames(
            "no_such_effect_xyz", params={}, seed=1, fps=10, duration_s=1.0, bpm=120.0, segments=60,
        )
        self.assertEqual(len(frames), 10)
        self.assertTrue(all(px == (0, 0, 0) for frame in frames for px in frame))


class CodecTests(unittest.TestCase):
    def test_roundtrip_equality(self) -> None:
        frames = engine.render_frames("beat_chase", params={}, seed=3, fps=20, duration_s=1.0, bpm=120.0, segments=60)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            engine.write_frames_jsonl(path, frames, fps=20, meta={"name": "beat_chase"})
            back = engine.read_frames_jsonl(path)
        self.assertEqual(back["fps"], 20)
        self.assertEqual(back["segments"], 60)
        self.assertEqual(back["meta"], {"name": "beat_chase"})
        self.assertEqual(back["frames"], [[list(px) for px in frame] for frame in frames])

    def test_roundtrip_preserves_irregular_timestamps(self) -> None:
        frames = [[(0, 0, 0)], [(1, 2, 3)], [(4, 5, 6)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timed.jsonl"
            engine.write_frames_jsonl(path, frames, fps=60, t_ms=[0, 19, 41])
            back = engine.read_frames_jsonl(path)
        self.assertEqual(back["t_ms"], [0, 19, 41])

    def test_corrupt_line_raises_with_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            header = json.dumps({"v": 1, "kind": "header", "fps": 10, "segments": 2, "meta": {}})
            good = json.dumps({"v": 1, "t_ms": 0, "frame": [[1, 2, 3], [4, 5, 6]]})
            path.write_text(f"{header}\n{good}\nnot json at all\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                engine.read_frames_jsonl(path)
        self.assertIn(":3:", str(ctx.exception))

    def test_header_segment_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mismatch.jsonl"
            header = json.dumps({"v": 1, "kind": "header", "fps": 10, "segments": 60, "meta": {}})
            short = json.dumps({"v": 1, "t_ms": 0, "frame": [[1, 2, 3], [4, 5, 6]]})
            path.write_text(f"{header}\n{short}\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                engine.read_frames_jsonl(path)
        self.assertIn(":2:", str(ctx.exception))


class ProfileTests(unittest.TestCase):
    def test_save_load_roundtrip_preserves_unknown_keys(self) -> None:
        profile = _profile()
        profile["operator_note"] = "kept"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            engine.save_profile(path, profile)
            back = engine.load_profile(path)
        self.assertEqual(back, profile)
        self.assertEqual(back["operator_note"], "kept")

    def test_invalid_save_rejected_with_named_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            with self.assertRaises(ValueError) as ctx:
                engine.save_profile(path, _profile(gamma=99))
            self.assertFalse(path.exists())
        self.assertIn("gamma", str(ctx.exception))

    def test_example_profile_is_valid(self) -> None:
        self.assertEqual(engine.validate_profile(_profile()), [])

    def test_h612d_physical_shape_is_fixed(self) -> None:
        errors = engine.validate_profile(_profile(physical_leds=359, leds_per_segment=5))
        self.assertTrue(any("physical_leds" in error for error in errors), errors)
        self.assertTrue(any("leds_per_segment" in error for error in errors), errors)


class TestCardTests(unittest.TestCase):
    def test_exact_expected_pixels(self) -> None:
        expected = {
            "white": (255, 255, 255),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "gray50": (128, 128, 128),
        }
        for kind, color in expected.items():
            frames = engine.test_card_frames(kind, 60)
            self.assertEqual(len(frames), 1)
            self.assertEqual(len(frames[0]), 60)
            self.assertTrue(all(px == color for px in frames[0]), kind)
        single = engine.test_card_frames("single_segment", 60)
        self.assertEqual(len(single), 1)
        self.assertEqual(single[0][0], (255, 255, 255))
        self.assertTrue(all(px == (0, 0, 0) for px in single[0][1:]))
        with self.assertRaises(ValueError):
            engine.test_card_frames("nope", 60)


class CalibrationSequenceTests(unittest.TestCase):
    def test_sequences_are_deterministic_timed_h612d_frames(self) -> None:
        for name in engine.CALIBRATION_SEQUENCE_NAMES:
            first = engine.calibration_sequence(name, fps=60)
            second = engine.calibration_sequence(name, fps=60)
            self.assertEqual(first, second)
            self.assertEqual(first["segments"], 60)
            self.assertEqual(len(first["frames"]), len(first["t_ms"]))
            self.assertTrue(first["markers"])
            self.assertTrue(all(len(frame) == 60 for frame in first["frames"]))

    def test_segment_map_visits_all_segments_individually(self) -> None:
        result = engine.calibration_sequence("segment_map", fps=60)
        visited = []
        for marker in result["markers"]:
            if marker["label"].startswith("segment "):
                frame = result["frames"][marker["frame"]]
                lit = [index for index, pixel in enumerate(frame) if pixel != (0, 0, 0)]
                visited.extend(lit)
        self.assertEqual(visited, list(range(60)))


if __name__ == "__main__":
    unittest.main()
