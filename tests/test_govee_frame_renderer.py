from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    EDM_BUILDS,
    REALTIME_EFFECT_NAMES,
    REALTIME_STROBE_EFFECTS,
    GoveeFrameRenderer,
    default_sync_mode,
    is_comet_effect,
)


ACTIVE_CUES = (
    "buildup_ramp_1",
    "buildup_ramp_2",
    "buildup_ramp_3",
    "buildup_white_zone_strobe",
    "buildup_white_half_strobe",
    "buildup_freestyle_nebula",
    "groove_chase_blue",
    "groove_chase_cyan",
    "groove_chase_red",
    "groove_chase_green",
    "groove_chase_cyan_white",
    "groove_freestyle_nebula",
    "drop_chase_blue",
    "drop_chase_cyan",
    "drop_chase_red",
    "drop_chase_green",
    "drop_chase_cyan_white",
    "drop_chase_freestyle_nebula",
    "post_drop_chase_blue",
    "post_drop_chase_cyan",
    "post_drop_chase_red",
    "post_drop_chase_green",
    "post_drop_chase_cyan_white",
)


class GoveeFrameRendererTests(unittest.TestCase):
    def test_requested_active_cues_are_registered(self) -> None:
        for cue in ACTIVE_CUES:
            self.assertIn(cue, EDM_BUILDS)

    def test_active_cues_render_segment_frames(self) -> None:
        renderer = GoveeFrameRenderer()
        for cue in ACTIVE_CUES:
            with self.subTest(cue=cue):
                frame = renderer.render(
                    cue,
                    beat_pos=8.25,
                    local_t=1.5,
                    frame_index=12,
                    params={},
                    segments=20,
                    seed=123,
                )
                self.assertEqual(len(frame), 20)
                for pixel in frame:
                    self.assertEqual(len(pixel), 3)
                    self.assertTrue(all(0 <= value <= 255 for value in pixel))

    def test_renderer_is_deterministic_for_fixed_inputs(self) -> None:
        renderer = GoveeFrameRenderer()

        a = renderer.render(
            "drop_chase_freestyle_nebula",
            beat_pos=2.125,
            local_t=0.4,
            frame_index=3,
            params={},
            segments=20,
            seed=77,
        )
        b = renderer.render(
            "drop_chase_freestyle_nebula",
            beat_pos=2.125,
            local_t=0.4,
            frame_index=3,
            params={},
            segments=20,
            seed=77,
        )

        self.assertEqual(a, b)

    def test_every_effect_returns_exactly_segments_pixels(self) -> None:
        # The transport rejects any frame whose length != segments, so the
        # renderer must always emit exactly `segments` pixels (padding dark if
        # an effect under-produces). Sweep all effects across extreme inputs.
        renderer = GoveeFrameRenderer()
        for name in sorted(REALTIME_EFFECT_NAMES):
            for segments in (1, 4, 7, 20):
                for beat_pos in (0.0, 0.3, 7.9, 16.2, 31.5, 999.9):
                    for local_t in (0.0, 0.5, 9.9):
                        with self.subTest(name=name, segments=segments, beat_pos=beat_pos, local_t=local_t):
                            frame = renderer.render(
                                name,
                                beat_pos=beat_pos,
                                local_t=local_t,
                                frame_index=3,
                                params={},
                                segments=segments,
                                seed=5,
                            )
                            self.assertEqual(len(frame), segments)

    def test_short_effect_output_is_padded_dark(self) -> None:
        # Inject a deliberately under-producing effect and confirm the renderer
        # pads it back up to `segments` rather than emitting a short frame.
        import rb_ss_bridge_v2.govee_frame_renderer as mod

        renderer = GoveeFrameRenderer()
        mod._EFFECTS["_short_test_effect"] = lambda *a, **k: [(1, 2, 3)]
        try:
            frame = renderer.render(
                "_short_test_effect",
                beat_pos=0.0,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=5,
                seed=1,
            )
        finally:
            del mod._EFFECTS["_short_test_effect"]

        self.assertEqual(frame, [(1, 2, 3), (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)])

    def test_unknown_effect_fails_dark(self) -> None:
        renderer = GoveeFrameRenderer()

        frame = renderer.render(
            "missing_effect",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=4,
            seed=1,
        )

        self.assertEqual(frame, [(0, 0, 0)] * 4)

    def test_comet_frame_exits_strip(self) -> None:
        renderer = GoveeFrameRenderer()
        dark = renderer.render_comet(
            "groove_chase_blue",
            progress=2.0,
            segments=20,
            width=0.8,
            direction=1,
            params={},
        )
        self.assertTrue(all(sum(px) <= 4 for px in dark))
        lit = renderer.render_comet(
            "groove_chase_blue",
            progress=0.0,
            segments=20,
            width=0.8,
            direction=1,
            params={},
        )
        self.assertGreater(lit[0][0] + lit[0][1] + lit[0][2], 0)

    def test_comet_keeps_steady_brightness_between_segments(self) -> None:
        renderer = GoveeFrameRenderer()

        on_segment = renderer.render_comet(
            "groove_chase_blue",
            progress=1.0 / 20.0,
            segments=20,
            width=0.8,
            direction=1,
            params={},
        )
        between_segments = renderer.render_comet(
            "groove_chase_blue",
            progress=1.5 / 20.0,
            segments=20,
            width=0.8,
            direction=1,
            params={},
        )

        on_total = sum(sum(px) for px in on_segment)
        between_total = sum(sum(px) for px in between_segments)
        self.assertGreater(on_total, 0)
        self.assertGreater(between_total, 0)
        self.assertLess(abs(on_total - between_total), on_total * 0.15)

    def test_comet_default_stays_compact(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render_comet(
            "groove_chase_blue",
            progress=10.5 / 20.0,
            segments=20,
            width=0.8,
            direction=1,
            params={"color": (255, 255, 255), "travel_beats": 2.0},
        )

        luminance = [sum(px) for px in frame]
        lit = [idx for idx, value in enumerate(luminance) if value > 0]
        self.assertLessEqual(len(lit), 2)
        self.assertEqual(lit, [10, 11])
        self.assertEqual(luminance[9], 0)
        self.assertEqual(luminance[12], 0)
        self.assertEqual(luminance[13], 0)

    def test_comet_glides_smoothly(self) -> None:
        renderer = GoveeFrameRenderer()
        centers: list[float] = []
        for position in (6.0 + step * 0.125 for step in range(17)):
            frame = renderer.render_comet(
                "groove_chase_blue",
                progress=position / 20.0,
                segments=20,
                width=0.8,
                direction=1,
                params={"color": (255, 255, 255), "travel_beats": 2.0, "trail_beats": 0.0},
            )
            luminance = [sum(px) for px in frame]
            total = sum(luminance)
            centers.append(sum(idx * value for idx, value in enumerate(luminance)) / total)

        deltas = [right - left for left, right in zip(centers, centers[1:])]
        self.assertTrue(all(delta > 0.0 for delta in deltas))
        self.assertLess(max(deltas), 0.18)

    def test_groove_chase_defaults_to_overlap_named_scene(self) -> None:
        self.assertEqual(default_sync_mode("groove_chase_blue"), "overlap")

    def test_is_comet_effect_only_matches_groove_chases(self) -> None:
        for name in (
            "groove_chase_blue",
            "groove_chase_cyan",
            "groove_chase_red",
            "groove_chase_green",
            "groove_chase_cyan_white",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_comet_effect(name))
        for name in ("beat_chase", "breathe", "twinkle_blue", "groove_freestyle_nebula"):
            with self.subTest(name=name):
                self.assertFalse(is_comet_effect(name))

    def test_buildup_ramp_3_calculates_active_comets_statelessly(self) -> None:
        import rb_ss_bridge_v2.govee_frame_renderer as mod

        self.assertEqual(mod._buildup_ramp_3_spawn_times(15.5), [(14.0, 2.0), (15.0, 2.0)])
        self.assertEqual(mod._buildup_ramp_3_spawn_times(16.25), [(15.0, 2.0), (16.0, 1.0)])
        self.assertEqual(
            mod._buildup_ramp_3_spawn_times(24.0),
            [(23.0, 1.0), (23.5, 1.0), (24.0, 1.0)],
        )
        self.assertEqual(
            mod._buildup_ramp_3_spawn_times(24.75),
            [(24.0, 1.0), (24.25, 1.0), (24.5, 1.0), (24.75, 1.0)],
        )

    def test_buildup_ramp_3_uses_white_comet_frames(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render(
            "buildup_ramp_3",
            beat_pos=16.25,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertGreater(sum(sum(px) for px in frame), 0)
        for red, green, blue in frame:
            self.assertEqual(red, green)
            self.assertEqual(green, blue)

    def test_buildup_ramp_3_final_phase_applies_sixteenth_strobe_mask(self) -> None:
        renderer = GoveeFrameRenderer()

        on_frame = renderer.render(
            "buildup_ramp_3",
            beat_pos=24.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )
        off_frame = renderer.render(
            "buildup_ramp_3",
            beat_pos=24.125,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertGreater(sum(sum(px) for px in on_frame), 0)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_drop_chase_calculates_post_sparkle_comets_statelessly(self) -> None:
        import rb_ss_bridge_v2.govee_frame_renderer as mod

        self.assertEqual(mod._drop_chase_spawn_times(7.99), [])
        self.assertEqual(mod._drop_chase_spawn_times(8.0), [(8.0, 0)])
        self.assertEqual(mod._drop_chase_spawn_times(9.5), [(8.0, 0), (9.0, 1)])
        self.assertEqual(mod._drop_chase_spawn_times(31.5), [(30.0, 22), (31.0, 23)])

    def test_drop_chase_keeps_sparkle_before_eight_beats(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render(
            "drop_chase_blue",
            beat_pos=4.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertGreater(sum(sum(px) for px in frame), 0)
        lit = [idx for idx, px in enumerate(frame) if sum(px) > 0]
        self.assertGreaterEqual(len(lit), 2)

    def test_drop_chase_post_sparkle_uses_color_comets(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render(
            "drop_chase_blue",
            beat_pos=9.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertGreater(sum(sum(px) for px in frame), 0)
        for red, green, blue in frame:
            self.assertEqual(red, 0)
            self.assertEqual(green, 0)
            self.assertGreaterEqual(blue, 0)

    def test_drop_chase_cyan_white_alternates_comet_colors(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render(
            "drop_chase_cyan_white",
            beat_pos=9.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertIn((255, 255, 255), frame)
        self.assertIn((0, 255, 255), frame)

    def test_drop_chase_freestyle_nebula_uses_comet_chase_after_sparkle(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render(
            "drop_chase_freestyle_nebula",
            beat_pos=9.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertIn((255, 255, 255), frame)
        self.assertIn((0, 255, 255), frame)

    def test_drop_chase_keeps_sixteenth_strobe_mask(self) -> None:
        renderer = GoveeFrameRenderer()
        on_frame = renderer.render(
            "drop_chase_blue",
            beat_pos=9.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )
        off_frame = renderer.render(
            "drop_chase_blue",
            beat_pos=9.0625,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=1,
        )

        self.assertGreater(sum(sum(px) for px in on_frame), 0)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_post_drop_chase_starts_on_comet_without_sparkle_intro(self) -> None:
        renderer = GoveeFrameRenderer()

        frame = renderer.render(
            "post_drop_chase_blue",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=123,
        )

        self.assertEqual(len(frame), 20)
        lit = [idx for idx, pixel in enumerate(frame) if pixel != (0, 0, 0)]
        self.assertTrue(lit)
        self.assertLessEqual(max(lit) - min(lit), 4)

    def test_post_drop_chase_keeps_comets_through_full_cycle(self) -> None:
        # Regression: the +8 offset reuse trick made comets stop spawning ~8
        # beats early, leaving the tail of every 32-beat cycle dark. A standalone
        # chase keeps comets alive late into the cycle.
        renderer = GoveeFrameRenderer()
        for beat in (24.0, 28.0, 30.0):
            frame = renderer.render(
                "post_drop_chase_blue",
                beat_pos=beat,
                local_t=0.0,
                frame_index=0,
                params={},
                segments=20,
                seed=123,
            )
            lit = sum(sum(px) for px in frame)
            self.assertGreater(lit, 0, msg=f"dark tail at beat {beat}")

    def test_post_drop_chase_keeps_sixteenth_strobe_mask(self) -> None:
        renderer = GoveeFrameRenderer()

        on_frame = renderer.render(
            "post_drop_chase_cyan_white",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=123,
        )
        off_frame = renderer.render(
            "post_drop_chase_cyan_white",
            beat_pos=0.0625,
            local_t=0.0,
            frame_index=1,
            params={},
            segments=20,
            seed=123,
        )

        self.assertGreater(sum(sum(px) for px in on_frame), 0)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_aggressive_shatter_pair_registered_as_strobe(self) -> None:
        for name in ("drop_white_aggressive", "post_drop_white_shatter"):
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            self.assertIn(name, REALTIME_STROBE_EFFECTS)
            self.assertIn(name, EDM_BUILDS)

    def test_freestyle_nebula_post_drop_pair_registered_as_strobe(self) -> None:
        for name in ("drop_chase_freestyle_nebula", "post_drop_freestyle_nebula"):
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            self.assertIn(name, REALTIME_STROBE_EFFECTS)
            self.assertIn(name, EDM_BUILDS)

        renderer = GoveeFrameRenderer()
        on_frame = renderer.render(
            "post_drop_freestyle_nebula",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=42,
        )
        off_frame = renderer.render(
            "post_drop_freestyle_nebula",
            beat_pos=0.0625,
            local_t=0.0,
            frame_index=1,
            params={},
            segments=20,
            seed=42,
        )

        self.assertGreater(sum(sum(px) for px in on_frame), 0)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_drop_white_aggressive_full_strip_32nd_strobe(self) -> None:
        renderer = GoveeFrameRenderer()
        on_frame = renderer.render(
            "drop_white_aggressive",
            beat_pos=0.0,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=42,
        )
        off_frame = renderer.render(
            "drop_white_aggressive",
            beat_pos=0.0625,
            local_t=0.0,
            frame_index=1,
            params={},
            segments=20,
            seed=42,
        )
        # On-phase: every segment full white. Off-phase: fully dark.
        self.assertEqual(on_frame, [(255, 255, 255)] * 20)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_post_drop_white_shatter_dissolves_and_is_pure_white(self) -> None:
        renderer = GoveeFrameRenderer()
        segments = 20

        def lit_count(beat: float, frame_index: int) -> int:
            frame = renderer.render(
                "post_drop_white_shatter",
                beat_pos=beat,
                local_t=0.0,
                frame_index=frame_index,
                params={},
                segments=segments,
                seed=99,
            )
            # Every lit pixel is exactly full white (no dimmed twinkle).
            for px in frame:
                self.assertIn(px, {(0, 0, 0), (255, 255, 255)})
            return sum(1 for px in frame if px != (0, 0, 0))

        # Average density at the start (rate ~13) must clearly exceed the held
        # floor (rate ~3) after the 4-beat dissolve.
        early = sum(lit_count(0.0, fi) for fi in range(40)) / 40.0
        late = sum(lit_count(8.0, fi) for fi in range(40)) / 40.0
        self.assertGreater(early, late + 3.0)
        self.assertGreater(early, 9.0)   # ~13/frame expected
        self.assertLess(late, 6.0)       # ~3/frame floor expected

    def test_post_drop_white_shatter_reshuffles_each_frame_but_is_deterministic(self) -> None:
        renderer = GoveeFrameRenderer()
        kwargs = dict(beat_pos=0.0, local_t=0.0, params={}, segments=20, seed=7)
        f0 = renderer.render("post_drop_white_shatter", frame_index=0, **kwargs)
        f0_again = renderer.render("post_drop_white_shatter", frame_index=0, **kwargs)
        f1 = renderer.render("post_drop_white_shatter", frame_index=1, **kwargs)
        # Same (beat, frame_index, seed) -> identical; different frame -> different pattern.
        self.assertEqual(f0, f0_again)
        self.assertNotEqual(f0, f1)

    def test_fold_additive_clamps(self) -> None:
        bright = [(255, 255, 255)] * 4
        folded = GoveeFrameRenderer.fold_additive([bright, bright], 4)
        for px in folded:
            self.assertLessEqual(max(px), 255)


if __name__ == "__main__":
    unittest.main()
