from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import led_sim_engine as engine  # noqa: E402

_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_sim_profile.example.json"
_VIEW_JS = Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets" / "ledsim-view.js"


def _profile(**overrides) -> dict:
    base = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
    # Legacy override path: passing layout/room_mm without layouts → v1 shape for old tests.
    if (
        ("layout" in overrides or "room_mm" in overrides or "layout_locked" in overrides)
        and "layouts" not in overrides
    ):
        base.pop("layouts", None)
        base.pop("active_layout", None)
        base["schema"] = 1
        if "layout" not in overrides and "layout" not in base:
            pass
        # Reconstruct a v1 top-level layout from the former Home entry when needed.
        if "layout" not in overrides:
            # example is v2 — rebuild a default v1 layout from defaults
            room = overrides.get("room_mm", [5216, 2284])
            base["room_mm"] = room
            base["layout"] = engine.default_layout(room)
            base["layout_locked"] = False
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


class LayoutTests(unittest.TestCase):
    def test_fixed_led_pitch_in_true_mm(self) -> None:
        result = engine.layout_led_positions(_profile(layout=engine.default_layout()))
        self.assertAlmostEqual(result["led_pitch_mm"], 41.656, places=6)
        self.assertAlmostEqual(result["led_pitch_mm"], engine.H612D_LED_PITCH_MM, places=9)
        for index in range(1, 60):  # first segment is collinear on bottom edge
            a = result["leds_mm"][index - 1]
            b = result["leds_mm"][index]
            self.assertIsNotNone(a)
            self.assertIsNotNone(b)
            self.assertAlmostEqual(
                math.hypot(a[0] - b[0], a[1] - b[1]),
                engine.H612D_LED_PITCH_MM,
                places=5,
                msg=f"led {index - 1}->{index}",
            )

    def test_perimeter_matches_strip_with_real_gap_and_absolute_junction(self) -> None:
        room = [5216.0, 2284.0]
        points = engine.perimeter_preset_points(room)
        path_len = engine.polyline_arc_length(points)
        self.assertAlmostEqual(path_len, engine.H612D_LENGTH_MM, places=6)
        self.assertAlmostEqual(2.0 * (room[0] + room[1]) - path_len, 3.84, places=6)
        profile = _profile(room_mm=room, layout={
            "preset": "perimeter", "points_mm": points, "flip_chain": False,
        })
        result = engine.layout_led_positions(profile)
        self.assertEqual(result["unplaced_mm"], 0.0)
        self.assertEqual(result["excess_path_mm"], 0.0)
        top_center = tuple(points[3])
        self.assertAlmostEqual(result["junction_mm"][0], top_center[0], places=6)
        self.assertAlmostEqual(result["junction_mm"][1], top_center[1], places=6)
        at_junction = engine._point_at_arc_distance(
            result["points_mm"], engine.H612D_JUNCTION_MM, path_len,
        )
        self.assertAlmostEqual(at_junction[0], top_center[0], places=6)
        self.assertAlmostEqual(at_junction[1], top_center[1], places=6)

    def test_snake_is_three_runs_with_absolute_junction(self) -> None:
        room = [5216.0, 2284.0]
        points = engine.snake_preset_points(room)
        self.assertEqual(len(points), 6)  # 3 runs + 2 connectors
        path_len = engine.polyline_arc_length(points)
        self.assertAlmostEqual(path_len, engine.H612D_LENGTH_MM, places=5)
        # Three equal horizontal runs, two equal vertical connectors.
        run = abs(points[1][0] - points[0][0])
        conn = abs(points[2][1] - points[1][1])
        self.assertAlmostEqual(abs(points[3][0] - points[2][0]), run, places=5)
        self.assertAlmostEqual(abs(points[5][0] - points[4][0]), run, places=5)
        self.assertAlmostEqual(abs(points[4][1] - points[3][1]), conn, places=5)
        self.assertAlmostEqual(3.0 * run + 2.0 * conn, engine.H612D_LENGTH_MM, places=5)
        result = engine.layout_led_positions(_profile(room_mm=room, layout={
            "preset": "snake", "points_mm": points, "flip_chain": False,
        }))
        self.assertEqual(result["unplaced_mm"], 0.0)
        # Junction is absolute 7498.08 mm — on the middle run for this room, not a corner claim.
        mid_y = points[2][1]
        self.assertAlmostEqual(result["junction_mm"][1], mid_y, places=5)
        self.assertGreater(result["junction_mm"][0], min(points[2][0], points[3][0]))
        self.assertLess(result["junction_mm"][0], max(points[2][0], points[3][0]))

    def test_path_longer_than_strip_truncates_without_stretch(self) -> None:
        result = engine.layout_led_positions(_profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [20000.0, 0.0]],
            "flip_chain": False,
        }))
        self.assertAlmostEqual(result["excess_path_mm"], 20000.0 - engine.H612D_LENGTH_MM, places=6)
        self.assertEqual(result["unplaced_mm"], 0.0)
        self.assertAlmostEqual(result["end_mm"][0], engine.H612D_LENGTH_MM, places=6)
        self.assertAlmostEqual(result["path_end_mm"][0], 20000.0, places=6)
        # Pitch stays real even on a long guide.
        a, b = result["leds_mm"][0], result["leds_mm"][1]
        self.assertAlmostEqual(math.hypot(a[0] - b[0], a[1] - b[1]), engine.H612D_LED_PITCH_MM, places=6)

    def test_path_shorter_than_strip_reports_shortfall(self) -> None:
        result = engine.layout_led_positions(_profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [5000.0, 0.0]],
            "flip_chain": False,
        }))
        self.assertAlmostEqual(result["unplaced_mm"], engine.H612D_LENGTH_MM - 5000.0, places=6)
        self.assertEqual(result["excess_path_mm"], 0.0)
        placed = [led for led in result["leds_mm"] if led is not None]
        unplaced = [led for led in result["leds_mm"] if led is None]
        self.assertEqual(len(placed) + len(unplaced), 360)
        self.assertGreater(len(unplaced), 0)
        self.assertLess(len(placed), 360)
        self.assertIn("ft", result["path_label"])
        self.assertEqual(result["strip_label"], engine.format_length_mm(engine.H612D_LENGTH_MM))

    def test_flip_chain_reverses_led_order(self) -> None:
        base = engine.default_layout()
        forward = engine.layout_led_positions(_profile(layout={**base, "flip_chain": False}))
        flipped = engine.layout_led_positions(_profile(layout={**base, "flip_chain": True}))
        self.assertEqual(len(flipped["leds_mm"]), len(forward["leds_mm"]))
        for index, (got, expected) in enumerate(zip(flipped["leds_mm"], reversed(forward["leds_mm"]))):
            self.assertAlmostEqual(got[0], expected[0], places=9, msg=f"led {index} x")
            self.assertAlmostEqual(got[1], expected[1], places=9, msg=f"led {index} y")
        self.assertEqual(flipped["start_mm"], forward["end_mm"])
        self.assertEqual(flipped["end_mm"], forward["start_mm"])
        self.assertAlmostEqual(flipped["junction_mm"][0], forward["junction_mm"][0], places=9)
        self.assertAlmostEqual(flipped["junction_mm"][1], forward["junction_mm"][1], places=9)

    def test_missing_layout_defaults_to_perimeter_from_room(self) -> None:
        profile = _profile(room_mm=[4000.0, 2000.0])
        profile.pop("layout", None)
        result = engine.layout_led_positions(profile)
        expected = engine.perimeter_preset_points([4000.0, 2000.0])
        self.assertEqual(result["preset"], "perimeter")
        self.assertEqual(result["points_mm"], [tuple(p) for p in expected])

    def test_degenerate_polylines_never_crash(self) -> None:
        two = _profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [1000.0, 0.0]],
            "flip_chain": False,
        })
        result = engine.layout_led_positions(two)
        self.assertEqual(len(result["leds_mm"]), 360)
        zero_edge = _profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [0.0, 0.0], [500.0, 0.0]],
            "flip_chain": False,
        })
        result2 = engine.layout_led_positions(zero_edge)
        self.assertEqual(len(result2["leds_mm"]), 360)
        for point in result2["leds_mm"]:
            if point is None:
                continue
            self.assertTrue(math.isfinite(point[0]) and math.isfinite(point[1]))

    def test_layout_validation_accepts_presets_and_rejects_bad_points(self) -> None:
        self.assertEqual(engine.validate_profile(_profile(layout=engine.default_layout())), [])
        self.assertEqual(engine.validate_profile(_profile(
            room_mm=[5216, 2284],
            layout={"preset": "snake", "points_mm": engine.snake_preset_points(), "flip_chain": False},
        )), [])
        errors = engine.validate_profile(_profile(layout={
            "preset": "custom", "points_mm": [[0, 0]], "flip_chain": False,
        }))
        self.assertTrue(any("points_mm" in error for error in errors), errors)
        legacy = _profile(
            room_mm=[5216, 2284],
            corner_segments=[0, 20.9, 33.8, 50.9],
            start_corner=0,
            direction="cw",
        )
        legacy.pop("layout", None)
        self.assertEqual(engine.validate_profile(legacy), [])

    def test_perimeter_large_room_clamps_to_corners(self) -> None:
        # AF-1: gap wider than bottom wall must never emit coordinates outside [0, room].
        room = [10000.0, 10000.0]
        points = engine.perimeter_preset_points(room)
        self.assertEqual(points[0], [0.0, 0.0])
        self.assertEqual(points[-1], [10000.0, 0.0])
        for point in points:
            self.assertGreaterEqual(point[0], 0.0)
            self.assertLessEqual(point[0], 10000.0)
            self.assertGreaterEqual(point[1], 0.0)
            self.assertLessEqual(point[1], 10000.0)
        path_len = engine.polyline_arc_length(points)
        # U-path = W + 2H = 30000 > strip → excess, not outside points.
        result = engine.layout_led_positions(_profile(room_mm=room, layout={
            "preset": "perimeter", "points_mm": points, "flip_chain": False,
        }))
        self.assertAlmostEqual(path_len, 30000.0, places=6)
        self.assertGreater(result["excess_path_mm"], 0.0)
        self.assertEqual(result["unplaced_mm"], 0.0)

    def test_flip_chain_non_bool_coerces_false(self) -> None:
        resolved = engine.resolve_layout(_profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [1000.0, 0.0]],
            "flip_chain": 1,  # truthy but not bool — engine coerces False
        }))
        self.assertIs(resolved["flip_chain"], False)
        errors = engine.validate_profile(_profile(layout={
            "preset": "custom",
            "points_mm": [[0.0, 0.0], [1000.0, 0.0]],
            "flip_chain": 1,
        }))
        self.assertTrue(any("flip_chain" in error for error in errors), errors)

    def test_layout_points_outside_room_warn_not_reject(self) -> None:
        profile = _profile(
            room_mm=[5216, 2284],
            layout={
                "preset": "custom",
                "points_mm": [[-100.0, 0.0], [6000.0, 0.0]],
                "flip_chain": False,
            },
        )
        self.assertEqual(engine.validate_profile(profile), [])
        warnings = engine.profile_warnings(profile)
        self.assertTrue(any("outside room bounds" in warning for warning in warnings), warnings)

    def test_layout_and_calibration_locks_validate_as_bool(self) -> None:
        self.assertEqual(engine.validate_profile(_profile(
            layout_locked=False, calibration_locked=True,
        )), [])
        errors = engine.validate_profile(_profile(layout_locked=1))
        self.assertTrue(any("layout_locked" in error for error in errors), errors)
        errors = engine.validate_profile(_profile(calibration_locked="yes"))
        self.assertTrue(any("calibration_locked" in error for error in errors), errors)

    def test_junction_segment_tick_suppression_contract(self) -> None:
        # AF-4: segment 30 arc length is the junction; JS must skip that tick.
        self.assertAlmostEqual(30 * engine.H612D_SEGMENT_MM, engine.H612D_JUNCTION_MM, places=9)
        view_js = (
            Path(__file__).resolve().parents[1] / "tools" / "led_sim_assets" / "ledsim-view.js"
        ).read_text(encoding="utf-8")
        self.assertIn("export function shouldSuppressSegmentTick", view_js)
        self.assertIn("if (shouldSuppressSegmentTick(segment)) continue;", view_js)

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_js_layout_led_positions_parity_when_node_available(self) -> None:
        # F-4: silent Python↔JS layout divergence fails a local test when node exists.
        profile = _profile(layout=engine.default_layout())
        py = engine.layout_led_positions(profile)
        sample_idx = [0, 1, 30, 179, 180, 358, 359]
        script = (
            f"import {{ layoutLedPositions }} from {_VIEW_JS.resolve().as_uri()!r};\n"
            f"const profile = {json.dumps(profile)};\n"
            "const r = layoutLedPositions(profile);\n"
            f"const sampleIdx = {json.dumps(sample_idx)};\n"
            "process.stdout.write(JSON.stringify({\n"
            "  path_length_mm: r.path_length_mm,\n"
            "  junction_mm: r.junction_mm,\n"
            "  unplaced_mm: r.unplaced_mm,\n"
            "  excess_path_mm: r.excess_path_mm,\n"
            "  leds: sampleIdx.map((i) => r.leds_mm[i]),\n"
            "}));\n"
        )
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        js = json.loads(proc.stdout)
        self.assertAlmostEqual(js["path_length_mm"], py["path_length_mm"], delta=1e-6)
        self.assertAlmostEqual(js["unplaced_mm"], py["unplaced_mm"], delta=1e-6)
        self.assertAlmostEqual(js["excess_path_mm"], py["excess_path_mm"], delta=1e-6)
        self.assertAlmostEqual(js["junction_mm"][0], py["junction_mm"][0], delta=1e-6)
        self.assertAlmostEqual(js["junction_mm"][1], py["junction_mm"][1], delta=1e-6)
        for index, (got, expected) in enumerate(zip(js["leds"], (py["leds_mm"][i] for i in sample_idx))):
            self.assertIsNotNone(got)
            self.assertIsNotNone(expected)
            self.assertAlmostEqual(got[0], expected[0], delta=1e-6, msg=f"led sample {index} x")
            self.assertAlmostEqual(got[1], expected[1], delta=1e-6, msg=f"led sample {index} y")

    def test_format_length_feet_primary(self) -> None:
        self.assertEqual(engine.format_length_mm(engine.H612D_LENGTH_MM), "49.2 ft · 15.0 m")
        self.assertEqual(engine.format_length_mm(10 * engine.H612D_SEGMENT_MM), "8.2 ft · 2.5 m")


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


class LayoutLibraryTests(unittest.TestCase):
    def test_example_is_schema_v2_library(self) -> None:
        profile = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(profile["schema"], 2)
        self.assertIn("Home", profile["layouts"])
        self.assertEqual(profile["active_layout"], "Home")
        self.assertNotIn("layout", profile)
        self.assertNotIn("room_mm", profile)
        self.assertEqual(engine.validate_profile(profile), [])

    def test_migrate_v1_wraps_as_home_and_strips_old_keys(self) -> None:
        v1 = _profile(layout=engine.default_layout(), room_mm=[5216, 2284], layout_locked=True)
        self.assertEqual(v1["schema"], 1)
        migrated = engine.migrate_profile_to_v2(v1)
        self.assertEqual(migrated["schema"], 2)
        self.assertEqual(migrated["active_layout"], "Home")
        self.assertEqual(set(migrated["layouts"]), {"Home"})
        self.assertEqual(migrated["layouts"]["Home"]["layout_locked"], True)
        self.assertEqual(migrated["layouts"]["Home"]["room_mm"], [5216.0, 2284.0])
        for key in ("layout", "room_mm", "layout_locked"):
            self.assertNotIn(key, migrated)
        self.assertEqual(engine.validate_profile(migrated), [])

    def test_save_round_trip_writes_v2_without_legacy_keys(self) -> None:
        v1 = _profile(layout=engine.default_layout(), room_mm=[4000, 2000], layout_locked=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            engine.save_profile(path, v1)
            loaded = engine.load_profile(path)
        self.assertEqual(loaded["schema"], 2)
        self.assertIn("layouts", loaded)
        self.assertNotIn("layout", loaded)
        self.assertNotIn("room_mm", loaded)
        self.assertNotIn("layout_locked", loaded)
        self.assertEqual(engine.validate_profile(loaded), [])

    def test_validate_rejects_empty_library(self) -> None:
        profile = _profile()
        profile["layouts"] = {}
        errors = engine.validate_profile(profile)
        self.assertTrue(any("at least one layout" in error for error in errors), errors)

    def test_validate_rejects_missing_active(self) -> None:
        profile = _profile()
        profile.pop("active_layout", None)
        errors = engine.validate_profile(profile)
        self.assertTrue(any("active_layout" in error for error in errors), errors)

    def test_validate_rejects_dangling_active(self) -> None:
        profile = _profile()
        profile["active_layout"] = "Venue"
        errors = engine.validate_profile(profile)
        self.assertTrue(any("not in layouts" in error for error in errors), errors)

    def test_validate_rejects_bad_layout_name(self) -> None:
        profile = _profile()
        entry = profile["layouts"]["Home"]
        profile["layouts"] = {" " * 2: entry}
        profile["active_layout"] = "  "
        errors = engine.validate_profile(profile)
        self.assertTrue(any("layouts name" in error for error in errors), errors)

    def test_validate_rejects_too_many_layouts(self) -> None:
        profile = _profile()
        entry = profile["layouts"]["Home"]
        profile["layouts"] = {f"L{i:02d}": dict(entry) for i in range(25)}
        profile["active_layout"] = "L00"
        errors = engine.validate_profile(profile)
        self.assertTrue(any("at most 24" in error for error in errors), errors)

    def test_active_layout_drives_positions_and_room_size(self) -> None:
        home = engine.make_layout_entry(room_mm=[5216, 2284])
        venue = engine.make_layout_entry(
            preset="snake",
            points_mm=engine.snake_preset_points([6000, 3000]),
            room_mm=[6000, 3000],
            layout_locked=True,
        )
        profile = _profile(
            layouts={"Home": home, "Venue": venue},
            active_layout="Venue",
            schema=2,
        )
        profile.pop("layout", None)
        profile.pop("room_mm", None)
        profile.pop("layout_locked", None)
        self.assertEqual(engine.room_size_mm(profile), (6000.0, 3000.0))
        self.assertEqual(engine.resolve_layout(profile)["preset"], "snake")
        self.assertTrue(engine.active_layout_entry(profile)["layout_locked"])
        switched = dict(profile)
        switched["active_layout"] = "Home"
        self.assertEqual(engine.room_size_mm(switched), (5216.0, 2284.0))
        self.assertEqual(engine.resolve_layout(switched)["preset"], "perimeter")

    def test_v1_and_v2_shapes_both_validate(self) -> None:
        v1 = _profile(layout=engine.default_layout(), room_mm=[5216, 2284])
        v2 = engine.migrate_profile_to_v2(v1)
        self.assertEqual(engine.validate_profile(v1), [])
        self.assertEqual(engine.validate_profile(v2), [])

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_js_layout_led_positions_parity_on_v2_library(self) -> None:
        home = engine.make_layout_entry()
        venue = engine.make_layout_entry(
            preset="snake",
            points_mm=engine.snake_preset_points([4800, 2400]),
            room_mm=[4800, 2400],
        )
        profile = _profile(
            layouts={"Home": home, "Venue": venue},
            active_layout="Venue",
            schema=2,
        )
        for key in ("layout", "room_mm", "layout_locked"):
            profile.pop(key, None)
        py = engine.layout_led_positions(profile)
        sample_idx = [0, 1, 30, 179, 180, 358, 359]
        script = (
            f"import {{ layoutLedPositions }} from {_VIEW_JS.resolve().as_uri()!r};\n"
            f"const profile = {json.dumps(profile)};\n"
            "const r = layoutLedPositions(profile);\n"
            f"const sampleIdx = {json.dumps(sample_idx)};\n"
            "process.stdout.write(JSON.stringify({\n"
            "  path_length_mm: r.path_length_mm,\n"
            "  junction_mm: r.junction_mm,\n"
            "  unplaced_mm: r.unplaced_mm,\n"
            "  excess_path_mm: r.excess_path_mm,\n"
            "  leds: sampleIdx.map((i) => r.leds_mm[i]),\n"
            "}));\n"
        )
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        js = json.loads(proc.stdout)
        self.assertAlmostEqual(js["path_length_mm"], py["path_length_mm"], delta=1e-6)
        self.assertAlmostEqual(js["unplaced_mm"], py["unplaced_mm"], delta=1e-6)
        self.assertAlmostEqual(js["excess_path_mm"], py["excess_path_mm"], delta=1e-6)
        self.assertAlmostEqual(js["junction_mm"][0], py["junction_mm"][0], delta=1e-6)
        self.assertAlmostEqual(js["junction_mm"][1], py["junction_mm"][1], delta=1e-6)
        for index, (got, expected) in enumerate(zip(js["leds"], (py["leds_mm"][i] for i in sample_idx))):
            self.assertIsNotNone(got)
            self.assertIsNotNone(expected)
            self.assertAlmostEqual(got[0], expected[0], delta=1e-6, msg=f"led sample {index} x")
            self.assertAlmostEqual(got[1], expected[1], delta=1e-6, msg=f"led sample {index} y")


if __name__ == "__main__":
    unittest.main()
