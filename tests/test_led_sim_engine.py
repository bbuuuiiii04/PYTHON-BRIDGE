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

    def test_render_timing_rejects_fractional_fps_and_nonfinite_or_out_of_range_values(self) -> None:
        invalid = (
            {"fps": 59.9, "duration_s": 1, "bpm": 120, "beat_division": 0},
            {"fps": 60, "duration_s": float("nan"), "bpm": 120, "beat_division": 0},
            {"fps": 60, "duration_s": 1, "bpm": 301, "beat_division": 0},
            {"fps": 60, "duration_s": 1, "bpm": 120, "beat_division": 16.1},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                engine.validate_render_timing(**values)


class CodecTests(unittest.TestCase):
    def test_roundtrip_equality(self) -> None:
        frames = engine.render_frames("beat_chase", params={}, seed=3, fps=20, duration_s=1.0, bpm=120.0, segments=60)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.jsonl"
            engine.write_frames_jsonl(
                path, frames, fps=20, duration_ms=1000, meta={"name": "beat_chase"},
            )
            back = engine.read_frames_jsonl(path)
        self.assertEqual(back["fps"], 20)
        self.assertEqual(back["segments"], 60)
        self.assertEqual(back["meta"], {"name": "beat_chase"})
        self.assertEqual(back["duration_ms"], 1000)
        self.assertEqual(back["duration_source"], "header")
        self.assertEqual(back["frames"], [[list(px) for px in frame] for frame in frames])

    def test_roundtrip_preserves_irregular_timestamps(self) -> None:
        frames = [[(0, 0, 0)], [(1, 2, 3)], [(4, 5, 6)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timed.jsonl"
            engine.write_frames_jsonl(path, frames, fps=60, t_ms=[0, 19, 41])
            back = engine.read_frames_jsonl(path)
        self.assertEqual(back["t_ms"], [0, 19, 41])
        self.assertEqual(back["duration_ms"], 58)
        self.assertEqual(back["duration_source"], "derived_from_timestamps_and_fps")

    def test_decreasing_timestamps_are_rejected_on_write_and_read(self) -> None:
        frames = [[(0, 0, 0)], [(1, 2, 3)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timed.jsonl"
            with self.assertRaisesRegex(ValueError, "nondecreasing"):
                engine.write_frames_jsonl(path, frames, fps=60, t_ms=[10, 5])

            header = json.dumps({"v": 1, "kind": "header", "fps": 60, "segments": 1, "meta": {}})
            first = json.dumps({"v": 1, "t_ms": 10, "frame": [[0, 0, 0]]})
            second = json.dumps({"v": 1, "t_ms": 5, "frame": [[1, 2, 3]]})
            path.write_text(f"{header}\n{first}\n{second}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r":3: t_ms must be nondecreasing"):
                engine.read_frames_jsonl(path)

    def test_duration_must_extend_past_final_timestamp(self) -> None:
        frames = [[(0, 0, 0)], [(1, 2, 3)]]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "short-duration.jsonl"
            with self.assertRaisesRegex(ValueError, "greater than the final t_ms"):
                engine.write_frames_jsonl(path, frames, fps=60, t_ms=[0, 20], duration_ms=20)
            header = json.dumps({
                "v": 1, "kind": "header", "fps": 60, "segments": 1,
                "duration_ms": 20, "meta": {},
            })
            lines = (
                json.dumps({"v": 1, "t_ms": 0, "frame": [[0, 0, 0]]}),
                json.dumps({"v": 1, "t_ms": 20, "frame": [[1, 2, 3]]}),
            )
            path.write_text(f"{header}\n{lines[0]}\n{lines[1]}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "greater than the final t_ms"):
                engine.read_frames_jsonl(path)

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

    def test_replay_rejects_booleans_in_integer_fields_and_pixels(self) -> None:
        cases = (
            (
                {"v": 1, "kind": "header", "fps": True, "segments": 1, "meta": {}},
                {"v": 1, "t_ms": 0, "frame": [[0, 0, 0]]},
            ),
            (
                {"v": 1, "kind": "header", "fps": 60, "segments": True, "meta": {}},
                {"v": 1, "t_ms": 0, "frame": [[0, 0, 0]]},
            ),
            (
                {"v": 1, "kind": "header", "fps": 60, "segments": 1, "duration_ms": True, "meta": {}},
                {"v": 1, "t_ms": 0, "frame": [[0, 0, 0]]},
            ),
            (
                {"v": 1, "kind": "header", "fps": 60, "segments": 1, "meta": {}},
                {"v": 1, "t_ms": 0, "frame": [[True, 0, 0]]},
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-bool.jsonl"
            with self.assertRaises(ValueError):
                engine.write_frames_jsonl(path, [[(True, 0, 0)]], fps=60)
            for header, frame in cases:
                with self.subTest(header=header, frame=frame):
                    path.write_text(f"{json.dumps(header)}\n{json.dumps(frame)}\n", encoding="utf-8")
                    with self.assertRaises(ValueError):
                        engine.read_frames_jsonl(path)


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

    def test_fps_must_be_an_integer(self) -> None:
        for value in (60.5, True):
            with self.subTest(value=value):
                self.assertTrue(any("fps must be an integer" in error for error in engine.validate_profile(_profile(fps=value))))

    def test_claimed_calibration_requires_domain_status_and_evidence(self) -> None:
        domains = {"color": "relative", "timing": "unmeasured", "spatial": "unmeasured"}
        errors = engine.validate_profile(_profile(
            calibration_status="relative", calibration_domains=domains, calibration_evidence={},
        ))
        self.assertTrue(any("sequence_version" in error for error in errors), errors)
        self.assertTrue(any("capture_sha256" in error for error in errors), errors)

        evidence = {
            "sequence_version": engine.CALIBRATION_SEQUENCE_VERSION,
            "sequence_sha256": "a" * 64,
            "capture_sha256": "b" * 64,
            "device_firmware": "recorded-by-operator",
            "phone_model": "test phone",
            "camera_settings": {"fps": 60, "locked": True},
            "capture_date": "2026-07-15",
            "measured_fields": ["gamma"],
            "fit_residuals": {"gamma_rmse": 0.01},
            "remaining_unknowns": ["absolute color"],
        }
        self.assertEqual(engine.validate_profile(_profile(
            calibration_status="relative", calibration_domains=domains,
            calibration_evidence=evidence,
        )), [])

    def test_measured_status_requires_all_domains_and_reference_instrument(self) -> None:
        domains = {"color": "measured", "timing": "measured", "spatial": "measured"}
        evidence = {
            "sequence_version": engine.CALIBRATION_SEQUENCE_VERSION,
            "sequence_sha256": "a" * 64,
            "capture_sha256": "b" * 64,
            "device_firmware": "test",
            "phone_model": "test",
            "camera_settings": {"locked": True},
            "capture_date": "2026-07-15",
            "measured_fields": ["all"],
            "fit_residuals": {"rmse": 0.01},
            "remaining_unknowns": [],
        }
        errors = engine.validate_profile(_profile(
            calibration_status="measured", calibration_domains=domains,
            calibration_evidence=evidence,
        ))
        self.assertTrue(any("reference_instrument" in error for error in errors), errors)


class LookCatalogTests(unittest.TestCase):
    def test_params_are_labeled_before_runtime_injection(self) -> None:
        catalog = engine.look_params_catalog()
        self.assertTrue(catalog["ok"], catalog["error"])
        self.assertTrue(catalog["looks"])
        self.assertTrue(all(
            look["params_stage"] == "pre_runtime_injection"
            for look in catalog["looks"].values()
        ))


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
            first = engine.calibration_sequence(name, fps=10)
            second = engine.calibration_sequence(name, fps=10)
            self.assertEqual(first, second)
            self.assertEqual(first["segments"], 60)
            self.assertEqual(len(first["frames"]), len(first["t_ms"]))
            self.assertEqual(first["duration_ms"], round(len(first["frames"]) * 1000 / 10))
            self.assertEqual(first["timing_source"], engine.TIMING_SOURCE_IDEAL_GRID)
            self.assertEqual(first["sequence_version"], engine.CALIBRATION_SEQUENCE_VERSION)
            self.assertEqual(len(first["sequence_sha256"]), 64)
            self.assertTrue(first["markers"])
            self.assertTrue(all(len(frame) == 60 for frame in first["frames"]))

    def test_segment_map_visits_all_segments_individually(self) -> None:
        result = engine.calibration_sequence("segment_map", fps=60)
        visited: dict[int, list[int]] = {16: [], 64: [], 255: []}
        for marker in result["markers"]:
            if marker["label"].startswith("segment "):
                frame = result["frames"][marker["frame"]]
                lit = [index for index, pixel in enumerate(frame) if pixel != (0, 0, 0)]
                self.assertEqual(len(lit), 1)
                level = frame[lit[0]][0]
                visited[level].extend(lit)
        for level in visited:
            self.assertEqual(visited[level], list(range(60)), level)

    def test_color_response_covers_sparse_alternating_full_and_near_black(self) -> None:
        result = engine.calibration_sequence("color_response", fps=10)
        labels = {marker["label"] for marker in result["markers"]}
        for label in ("red 1 isolated", "green 3 alternating", "white 255 full", "violet 128 full"):
            self.assertIn(label, labels)

    def test_timing_codes_are_unique_and_constant_load(self) -> None:
        result = engine.calibration_sequence("timing_response", fps=60)
        coded = [
            result["frames"][marker["frame"]]
            for marker in result["markers"]
            if marker["label"].startswith("timing pass 1 code ")
        ]
        self.assertEqual(len(coded), 256)
        self.assertEqual(len({tuple(frame) for frame in coded}), 256)
        lit_counts = {sum(pixel != (0, 0, 0) for pixel in frame) for frame in coded}
        self.assertEqual(lit_counts, {28})


if __name__ == "__main__":
    unittest.main()
