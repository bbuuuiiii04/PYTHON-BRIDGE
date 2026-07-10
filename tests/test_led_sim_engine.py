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


class GeometryTests(unittest.TestCase):
    def test_default_profile_covers_four_walls_on_perimeter(self) -> None:
        profile = _profile()
        geo = engine.segment_geometry(profile)
        self.assertEqual(len(geo), 60)
        width, height = profile["room_mm"]
        for entry in geo:
            x, y = entry["x_mm"], entry["y_mm"]
            on_x_edge = abs(x) < 1e-6 or abs(x - width) < 1e-6
            on_y_edge = abs(y) < 1e-6 or abs(y - height) < 1e-6
            self.assertTrue(on_x_edge or on_y_edge, f"segment {entry['segment']} off perimeter: {x}, {y}")
        self.assertEqual(sorted({entry["wall"] for entry in geo}), [0, 1, 2, 3])

    def test_normals_point_inward(self) -> None:
        profile = _profile()
        geo = engine.segment_geometry(profile)
        cx, cy = profile["room_mm"][0] / 2, profile["room_mm"][1] / 2
        for entry in geo:
            dot = (cx - entry["x_mm"]) * entry["nx"] + (cy - entry["y_mm"]) * entry["ny"]
            self.assertGreater(dot, 0, f"segment {entry['segment']} normal not inward")

    def test_direction_flip_reverses_travel_order(self) -> None:
        # Shoelace winding of the ordered centers flips sign when direction flips.
        def winding(geo: list[dict]) -> float:
            total = 0.0
            for i, entry in enumerate(geo):
                nxt = geo[(i + 1) % len(geo)]
                total += (nxt["x_mm"] - entry["x_mm"]) * (nxt["y_mm"] + entry["y_mm"])
            return total

        cw = winding(engine.segment_geometry(_profile(direction="cw")))
        ccw = winding(engine.segment_geometry(_profile(direction="ccw")))
        self.assertNotEqual(cw, 0.0)
        self.assertNotEqual(ccw, 0.0)
        self.assertLess(cw * ccw, 0)  # opposite signs = reversed travel

    def test_start_corner_rotation_shifts_mapping(self) -> None:
        self.assertEqual(engine.segment_geometry(_profile(start_corner=0))[0]["wall"], 0)
        self.assertEqual(engine.segment_geometry(_profile(start_corner=1))[0]["wall"], 1)

    def test_validate_rejects_bad_corner_lists(self) -> None:
        non_ascending = engine.validate_profile(_profile(corner_segments=[0.0, 30.0, 20.0, 50.0]))
        self.assertTrue(any("ascending" in e for e in non_ascending), non_ascending)
        out_of_range = engine.validate_profile(_profile(corner_segments=[0.0, 20.0, 30.0, 60.5]))
        self.assertTrue(any("corner_segments" in e for e in out_of_range), out_of_range)
        wrong_count = engine.validate_profile(_profile(corner_segments=[0.0, 20.0, 30.0]))
        self.assertTrue(any("4 numbers" in e for e in wrong_count), wrong_count)


class BleedTests(unittest.TestCase):
    def test_ring_wrap_exact_values(self) -> None:
        frame = [(100, 0, 0), (0, 100, 0), (0, 0, 100), (0, 0, 0)]
        out = engine.apply_bleed(frame, 0.5)
        self.assertEqual(out, [(50, 25, 0), (25, 50, 25), (0, 25, 50), (25, 0, 25)])

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


class RenderAdapterTests(unittest.TestCase):
    def test_determinism_and_shape(self) -> None:
        kwargs = dict(params={}, seed=7, fps=30, duration_s=2.0, bpm=120.0, segments=60)
        first = engine.render_frames("beat_chase", **kwargs)
        second = engine.render_frames("beat_chase", **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 60)  # fps * duration
        self.assertEqual(len(first[0]), 60)  # segments wide

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


if __name__ == "__main__":
    unittest.main()
