from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    EDM_BUILDS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    GoveeFrameRenderer,
    _drop_chase_spawn_times,
    _ember_field,
    _head_weights,
    _hz_strobe_on,
    _slot_breakdown_star_twinkle,
    _slot_drop_center_burst,
    _slot_drop_chase,
    _slot_drop_nebula,
    _slot_groove_chase,
    _slot_groove_nebula,
    _slot_post_drop_center_comet,
    _slot_post_drop_chase,
    _slot_post_drop_nebula,
    _slot_rt_groove_heartbeat,
    _slot_rt_post_drop_firework_remnants,
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

    def test_breakdown_star_twinkle_never_lights_slot_five(self) -> None:
        """AWR-152 T7: color_slot draws from 0..4 only — no random pure-white stars."""
        for beat in (0.0, 3.5, 12.25, 40.0, 97.5):
            for frame_index in range(5):
                field = _slot_breakdown_star_twinkle(
                    beat, 0.0, frame_index, {}, segments=30, seed=1
                )
                for pixel in field:
                    self.assertEqual(pixel[5], 0.0)

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

    def test_drop_chase_flashes_on_the_hz_gate_independent_of_bpm(self) -> None:
        """AWR-161: migrated off int(beat*16)%2 onto the wall-clock Hz gate --
        the on/off split now comes from local_t, not beat, at any BPM."""
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
            beat_pos=9.0,
            local_t=0.1,
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

    def test_post_drop_chase_flashes_on_the_hz_gate_independent_of_bpm(self) -> None:
        """AWR-161: migrated off int(beat*16)%2 onto the wall-clock Hz gate."""
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
            beat_pos=0.0,
            local_t=0.1,
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

        # AWR-161: migrated off int(beat*16)%2 onto the wall-clock Hz gate.
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
            beat_pos=0.0,
            local_t=0.1,
            frame_index=1,
            params={},
            segments=20,
            seed=42,
        )

        self.assertGreater(sum(sum(px) for px in on_frame), 0)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_drop_white_aggressive_full_strip_hz_strobe(self) -> None:
        """AWR-156: rebuilt on the Hz gate — local_t-driven, not beat-driven."""
        renderer = GoveeFrameRenderer()
        on_frame = renderer.render(
            "drop_white_aggressive",
            beat_pos=999.0,  # beat is irrelevant to the Hz gate now
            local_t=0.0,
            frame_index=0,
            params={},
            segments=20,
            seed=42,
        )
        off_frame = renderer.render(
            "drop_white_aggressive",
            beat_pos=999.0,
            local_t=0.1,  # default hz 6.0/duty 0.3 -> ON window is [0, 0.05)
            frame_index=1,
            params={},
            segments=20,
            seed=42,
        )
        # On-phase: every segment full white. Off-phase: fully dark.
        self.assertEqual(on_frame, [(255, 255, 255)] * 20)
        self.assertEqual(off_frame, [(0, 0, 0)] * 20)

    def test_drop_white_aggressive_hz_duty_params_drive_the_gate(self) -> None:
        """hz/duty are static config params now (allowlisted, not defaults-only)."""
        renderer = GoveeFrameRenderer()
        # hz=1.0 duty=0.5 -> cycle 1.0s, ON for [0, 0.5).
        on = renderer.render("drop_white_aggressive", beat_pos=0.0, local_t=0.4,
                              frame_index=0, params={"hz": 1.0, "duty": 0.5}, segments=4, seed=1)
        off = renderer.render("drop_white_aggressive", beat_pos=0.0, local_t=0.6,
                               frame_index=0, params={"hz": 1.0, "duty": 0.5}, segments=4, seed=1)
        self.assertEqual(on, [(255, 255, 255)] * 4)
        self.assertEqual(off, [(0, 0, 0)] * 4)


class HzStrobeGateTests(unittest.TestCase):
    """AWR-156 Task 7.1: the shared Hz gate (_hz_strobe_on)."""

    def test_bpm_invariant_same_local_t_series_ignores_beat(self) -> None:
        params = {"hz": 6.0, "duty": 0.3}
        local_ts = [t / 100.0 for t in range(0, 200)]
        pattern_a = [_hz_strobe_on(t, {**params, "_probe": "beat=0"}) for t in local_ts]
        pattern_b = [_hz_strobe_on(t, {**params, "_probe": "beat=999999"}) for t in local_ts]
        self.assertEqual(pattern_a, pattern_b)
        self.assertGreater(sum(pattern_a), 0)
        self.assertLess(sum(pattern_a), len(pattern_a))

    def test_frame_aware_widening_lands_at_least_one_on_frame_every_cycle(self) -> None:
        hz, duty = 6.0, 0.3
        frame_period = 1.0 / 28.0
        params = {"hz": hz, "duty": duty, "frame_period_s": frame_period}
        cycle_s = 1.0 / hz
        # ON window must be >= 1.6 frames wide.
        on_s = duty * cycle_s
        widened_on_s = max(on_s, min(cycle_s * 0.9, 1.6 * frame_period))
        self.assertGreaterEqual(widened_on_s, 1.6 * frame_period - 1e-9)

        seen_cycles: dict[int, bool] = {}
        t = 0.0
        for _ in range(400):
            cycle_idx = int(t // cycle_s)
            hit = _hz_strobe_on(t, params)
            seen_cycles[cycle_idx] = seen_cycles.get(cycle_idx, False) or hit
            t += frame_period
        # Every cycle we swept through landed at least one ON frame.
        complete_cycles = max(seen_cycles) if seen_cycles else 0
        for cycle_idx in range(complete_cycles):
            self.assertTrue(seen_cycles[cycle_idx], msg=f"cycle {cycle_idx} never lit")

    def test_hz_capped_at_ten(self) -> None:
        local_ts = [t / 1000.0 for t in range(0, 500)]
        capped = [_hz_strobe_on(t, {"hz": 10.0, "duty": 0.3}) for t in local_ts]
        over = [_hz_strobe_on(t, {"hz": 999.0, "duty": 0.3}) for t in local_ts]
        self.assertEqual(capped, over)

    def test_duty_capped_at_half(self) -> None:
        local_ts = [t / 1000.0 for t in range(0, 500)]
        capped = [_hz_strobe_on(t, {"hz": 2.0, "duty": 0.5}) for t in local_ts]
        over = [_hz_strobe_on(t, {"hz": 2.0, "duty": 999.0}) for t in local_ts]
        self.assertEqual(capped, over)

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

    def test_phase3_param_unlock_defaults_are_frame_identical(self) -> None:
        renderer = GoveeFrameRenderer()
        cases = {
            "rt_groove_chase": ({"loop_beats": 4.0}, {"loop_beats": 5.0}, 1.25),
            "rt_groove_nebula": ({"loop_beats": 4.0}, {"loop_beats": 5.0}, 1.25),
            "rt_drop_chase": ({"travel_beats": 2.0, "width": 0.8}, {"travel_beats": 3.0, "width": 1.2}, 9.25),
            "rt_post_drop_chase": ({"travel_beats": 2.0, "width": 0.8}, {"travel_beats": 3.0, "width": 1.2}, 1.25),
            "rt_drop_nebula": ({"travel_beats": 2.0, "width": 0.8}, {"travel_beats": 3.0, "width": 1.2}, 9.25),
            "rt_post_drop_nebula": ({"travel_beats": 2.0, "width": 0.8}, {"travel_beats": 3.0, "width": 1.2}, 1.25),
            "groove_center_chase": ({"travel_beats": 1.0}, {"travel_beats": 2.0}, 0.5),
            "post_drop_firework_chase": ({"travel_beats": 1.0}, {"travel_beats": 2.0}, 0.5),
        }
        slot_colors = {
            "slot_colors": [
                (255, 0, 0),
                (255, 80, 0),
                (0, 255, 0),
                (0, 0, 255),
                (180, 0, 255),
                (255, 255, 255),
            ]
        }
        for name, (defaults, changed, beat_pos) in cases.items():
            with self.subTest(name=name):
                absent = renderer.render(name, beat_pos=beat_pos, local_t=0.0, frame_index=3, params=slot_colors, segments=20, seed=11)
                explicit_default = renderer.render(name, beat_pos=beat_pos, local_t=0.0, frame_index=3, params={**slot_colors, **defaults}, segments=20, seed=11)
                explicit_changed = renderer.render(name, beat_pos=beat_pos, local_t=0.0, frame_index=3, params={**slot_colors, **changed}, segments=20, seed=11)
                self.assertEqual(absent, explicit_default)
                self.assertNotEqual(absent, explicit_changed)


class DropStrobeColorwayTests(unittest.TestCase):
    """AWR-156 Task 7.3."""

    def test_solid_color_a_on_off(self) -> None:
        renderer = GoveeFrameRenderer()
        on = renderer.render("drop_strobe_colorway", beat_pos=0.0, local_t=0.0, frame_index=0,
                              params={"color_a": [10, 20, 30], "hz": 6.0, "duty": 0.3}, segments=5, seed=1)
        off = renderer.render("drop_strobe_colorway", beat_pos=0.0, local_t=0.1, frame_index=0,
                               params={"color_a": [10, 20, 30], "hz": 6.0, "duty": 0.3}, segments=5, seed=1)
        self.assertEqual(on, [(10, 20, 30)] * 5)
        self.assertEqual(off, [(0, 0, 0)] * 5)

    def test_alternating_color_a_color_b_by_flash_index(self) -> None:
        renderer = GoveeFrameRenderer()
        params = {"color_a": [255, 0, 0], "color_b": [0, 255, 0], "hz": 6.0, "duty": 0.3}
        flash0 = renderer.render("drop_strobe_colorway", beat_pos=0.0, local_t=0.0,
                                  frame_index=0, params=params, segments=3, seed=1)
        flash1 = renderer.render("drop_strobe_colorway", beat_pos=0.0, local_t=1.0 / 6.0,
                                  frame_index=0, params=params, segments=3, seed=1)
        self.assertEqual(flash0, [(255, 0, 0)] * 3)
        self.assertEqual(flash1, [(0, 255, 0)] * 3)

    def test_color_a_defaults_white_when_absent(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render("drop_strobe_colorway", beat_pos=0.0, local_t=0.0,
                                 frame_index=0, params={}, segments=3, seed=1)
        self.assertEqual(frame, [(255, 255, 255)] * 3)

    def test_registered_as_strobe_effect(self) -> None:
        self.assertIn("drop_strobe_colorway", REALTIME_EFFECT_NAMES)
        self.assertIn("drop_strobe_colorway", REALTIME_STROBE_EFFECTS)


class Awr161HzMigrationCoverageTests(unittest.TestCase):
    """AWR-161 Task 5: every remaining beat-tied strobe gate migrated onto
    _hz_strobe_on (Task 1) flashes at the hz-derived rate independent of
    BPM, its hz/duty knobs are dialable, and every migrated effect carries
    the allowlist entries (the C5 guard -- an un-allowlisted static param
    disables all LED)."""

    _NON_SLOT_NAMES = (
        "post_drop_center_comet_blue_cyan",
        "drop_chase_blue", "drop_chase_cyan", "drop_chase_red",
        "drop_chase_green", "drop_chase_cyan_white",
        "post_drop_chase_blue", "post_drop_chase_cyan", "post_drop_chase_red",
        "post_drop_chase_green", "post_drop_chase_cyan_white",
        "post_drop_freestyle_nebula",
        "drop_chase_freestyle_nebula",
    )
    _SLOT_FNS = {
        "rt_post_drop_chase": _slot_post_drop_chase,
        "rt_post_drop_nebula": _slot_post_drop_nebula,
        "rt_drop_chase": _slot_drop_chase,
        "rt_drop_nebula": _slot_drop_nebula,
        "rt_post_drop_center_comet": _slot_post_drop_center_comet,
    }

    def test_non_slot_effects_flash_on_the_hz_gate_independent_of_bpm(self) -> None:
        renderer = GoveeFrameRenderer()
        for name in self._NON_SLOT_NAMES:
            # beat_pos varies (standing in for two different BPM mappings of
            # the same wall-clock moment) -- the on/off split must come from
            # local_t alone, per every migrated effect.
            for beat_pos in (0.0, 9.0):
                with self.subTest(name=name, beat_pos=beat_pos):
                    on_frame = renderer.render(name, beat_pos=beat_pos, local_t=0.0,
                                                frame_index=0, params={}, segments=20, seed=5)
                    off_frame = renderer.render(name, beat_pos=beat_pos, local_t=0.1,
                                                 frame_index=0, params={}, segments=20, seed=5)
                    self.assertEqual(off_frame, [(0, 0, 0)] * 20, msg=f"{name} not dark off-gate")
                    self.assertGreater(sum(sum(px) for px in on_frame), 0, msg=f"{name} dark on-gate")

    def test_slot_effects_flash_on_the_hz_gate_independent_of_bpm(self) -> None:
        for name, fn in self._SLOT_FNS.items():
            for beat_pos in (0.0, 9.0):
                with self.subTest(name=name, beat_pos=beat_pos):
                    on_field = fn(beat_pos, 0.0, 0, {}, 20, 5)
                    off_field = fn(beat_pos, 0.1, 0, {}, 20, 5)
                    self.assertEqual(sum(sum(row) for row in off_field), 0.0, msg=f"{name} not dark off-gate")
                    self.assertGreater(sum(sum(row) for row in on_field), 0.0, msg=f"{name} dark on-gate")

    def test_hz_duty_params_are_dialable(self) -> None:
        renderer = GoveeFrameRenderer()
        # hz=1.0 duty=0.5 -> cycle 1.0s, ON for [0, 0.5).
        params = {"hz": 1.0, "duty": 0.5}
        on = renderer.render("drop_chase_blue", beat_pos=9.0, local_t=0.4,
                              frame_index=0, params=params, segments=20, seed=1)
        off = renderer.render("drop_chase_blue", beat_pos=9.0, local_t=0.6,
                               frame_index=0, params=params, segments=20, seed=1)
        self.assertGreater(sum(sum(px) for px in on), 0)
        self.assertEqual(off, [(0, 0, 0)] * 20)

        on_field = _slot_drop_chase(9.0, 0.4, 0, params, 20, 1)
        off_field = _slot_drop_chase(9.0, 0.6, 0, params, 20, 1)
        self.assertGreater(sum(sum(row) for row in on_field), 0.0)
        self.assertEqual(sum(sum(row) for row in off_field), 0.0)

    def test_c5_guard_hz_duty_allowlisted_for_every_migrated_effect(self) -> None:
        for name in self._NON_SLOT_NAMES:
            with self.subTest(name=name):
                allowed = REALTIME_EFFECT_PARAM_KEYS.get(name, frozenset())
                self.assertIn("hz", allowed, msg=name)
                self.assertIn("duty", allowed, msg=name)
        for name in self._SLOT_FNS:
            with self.subTest(name=name):
                allowed = REALTIME_EFFECT_PARAM_KEYS.get(name, frozenset())
                self.assertIn("hz", allowed, msg=name)
                self.assertIn("duty", allowed, msg=name)


class Awr156ParamAllowlistTests(unittest.TestCase):
    """AWR-156 Task 7.3/7.4: C5 guard — every static param used by a new or
    changed look must have an allowlist entry, or the look disables all LED."""

    def test_new_and_changed_looks_have_allowlist_entries(self) -> None:
        expected = {
            "drop_white_aggressive": {"hz", "duty"},
            "drop_strobe_colorway": {"color_a", "color_b", "hz", "duty"},
            "buildup_balloon_comet": {"start_width", "end_width", "build_beats",
                                      "dim_floor", "loop_beats", "color"},
            "rt_groove_heartbeat": {"base_width", "pulse_width", "decay",
                                    "loop_beats", "color_mode"},
            "rt_post_drop_firework_remnants": {"dim_beats", "ember_hold_beats",
                                               "ember_decay_beats", "sparkle_density",
                                               "sparkle_size", "sparkle_life_s"},
            "rt_groove_chase": {"width"},
            "rt_groove_nebula": {"width"},
            "rt_post_drop_center_comet": {"width"},
        }
        for name, keys in expected.items():
            with self.subTest(name=name):
                allowed = REALTIME_EFFECT_PARAM_KEYS.get(name, frozenset())
                for key in keys:
                    self.assertIn(key, allowed, msg=f"{name} missing allowlist entry for {key}")

    def test_new_promoted_looks_registered(self) -> None:
        for name in ("buildup_balloon_comet", "drop_strobe_colorway"):
            self.assertIn(name, REALTIME_EFFECT_NAMES)
        for name in ("rt_groove_heartbeat", "rt_post_drop_firework_remnants"):
            self.assertIn(name, SLOT_EFFECTS)
            self.assertIn(name, REALTIME_EFFECT_NAMES)
        # Not strobes.
        for name in ("buildup_balloon_comet", "rt_groove_heartbeat", "rt_post_drop_firework_remnants"):
            self.assertNotIn(name, REALTIME_STROBE_EFFECTS)


class BuildupBalloonCometTests(unittest.TestCase):
    """AWR-156 Task 7.4."""

    def _params(self, **overrides):
        base = {"start_width": 6, "end_width": 0.8, "build_beats": 32,
                "dim_floor": 0.05, "loop_beats": 4, "color": [255, 255, 255]}
        base.update(overrides)
        return base

    def test_brightness_monotonically_shrinks_over_build_beats(self) -> None:
        renderer = GoveeFrameRenderer()
        peaks = []
        for beat in (0.0, 8.0, 16.0, 24.0, 31.9):
            frame = renderer.render("buildup_balloon_comet", beat_pos=beat, local_t=0.0,
                                     frame_index=0, params=self._params(), segments=40, seed=1)
            peaks.append(max(sum(px) for px in frame))
        for earlier, later in zip(peaks, peaks[1:]):
            self.assertGreaterEqual(earlier, later)
        self.assertGreater(peaks[0], peaks[-1])

    def test_default_color_is_pure_white(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render("buildup_balloon_comet", beat_pos=0.0, local_t=0.0,
                                 frame_index=0, params={}, segments=10, seed=1)
        lit = [px for px in frame if sum(px) > 0]
        self.assertTrue(lit)
        for px in lit:
            self.assertEqual(px[0], px[1])
            self.assertEqual(px[1], px[2])


class RainbowOrderedTests(unittest.TestCase):
    """AWR-161 Task 2: rainbow pair promotion (comet_rainbow_ordered port)."""

    def test_registered_and_not_a_strobe(self) -> None:
        self.assertIn("rainbow_ordered", REALTIME_EFFECT_NAMES)
        self.assertNotIn("rainbow_ordered", REALTIME_STROBE_EFFECTS)

    def test_beat_locked_travel_advances_travel_per_beat_pixels_ignoring_local_t(self) -> None:
        """travel_per_beat present -> beat-locked head advance, independent of
        local_t (the AWR-156 movement fix: never BPM/time-tied)."""
        renderer = GoveeFrameRenderer()
        segments = 120
        params = {"width": 0.5, "travel_per_beat": 30.0, "loop_beats": 4.0, "cycle_beats": 1e6}
        # Two very different local_t values stand in for two different BPM
        # mappings of the same beat position -- the head must land identically
        # either way.
        for local_t in (0.02, 5.7):
            frame_a = renderer.render("rainbow_ordered", beat_pos=2.0, local_t=local_t,
                                       frame_index=0, params=params, segments=segments, seed=1)
            frame_b = renderer.render("rainbow_ordered", beat_pos=3.0, local_t=local_t,
                                       frame_index=0, params=params, segments=segments, seed=1)
            self.assertEqual(max(frame_a[60]), 255, msg=f"local_t={local_t}")
            self.assertEqual(max(frame_b[90]), 255, msg=f"local_t={local_t}")

    def test_legacy_pace_matches_loop_beats_formula_when_travel_per_beat_absent(self) -> None:
        """travel_per_beat absent -> legacy loop_beats pace (the post-drop
        look's accepted-as-is feel) survives byte-stable."""
        renderer = GoveeFrameRenderer()
        segments = 60
        params = {"width": 0.5, "loop_beats": 4.0, "cycle_beats": 1e6}
        for beat, expected_idx in ((1.0, 15), (2.0, 30), (3.0, 45)):
            frame = renderer.render("rainbow_ordered", beat_pos=beat, local_t=0.0,
                                     frame_index=0, params=params, segments=segments, seed=1)
            self.assertEqual(max(frame[expected_idx]), 255, msg=f"beat={beat}")

    def test_hue_ordered_by_position_value_stays_full_at_the_peak(self) -> None:
        """Hue comes from strip position (an ordered spectrum); brightness
        only dims value -- at the anti-aliased peak the color is full HSV
        value/saturation."""
        renderer = GoveeFrameRenderer()
        segments = 40
        params = {"width": 0.5, "rainbow_span": 1.0, "loop_beats": 1e6, "cycle_beats": 1e6}
        frame = renderer.render("rainbow_ordered", beat_pos=0.0, local_t=0.0,
                                 frame_index=0, params=params, segments=segments, seed=1)
        self.assertEqual(frame[0], (255, 0, 0))
        self.assertEqual(frame[20], (0, 255, 255))


class HeadWeightsPeakNormalizationTests(unittest.TestCase):
    """AWR-156 Task 7.4: the 0.53x between-pixel dip regression test."""

    def test_peak_weight_is_always_one_regardless_of_subpixel_offset(self) -> None:
        segments = 20
        for width in (0.8, 1.5, 3.0, 4.5):
            for pos in [i / 4.0 for i in range(0, segments * 4)]:
                weights = _head_weights(pos, width, segments)
                self.assertAlmostEqual(max(weights.values()), 1.0, places=9,
                                        msg=f"dip at pos={pos} width={width}")


class GrooveHeartbeatTests(unittest.TestCase):
    """AWR-156 Task 7.4."""

    def _field(self, **params):
        base = {"base_width": 1.5, "pulse_width": 3.0, "decay": 0.3, "loop_beats": 4.0}
        base.update(params)
        return _slot_rt_groove_heartbeat(0.0, 0.0, 0, base, 20, 1)

    def test_color_mode_0_both_heads_slot_1(self) -> None:
        field = self._field(color_mode=0)
        for row in field:
            for slot in (0, 2, 3, 4, 5):
                self.assertEqual(row[slot], 0.0)

    def test_color_mode_2_default_head1_slot1_head2_slot3(self) -> None:
        field = self._field(color_mode=2)
        for row in field:
            for slot in (0, 2, 4, 5):
                self.assertEqual(row[slot], 0.0)
        self.assertTrue(any(row[1] > 0 for row in field))
        self.assertTrue(any(row[3] > 0 for row in field))

    def test_color_modes_1_and_3_write_only_slots_1_and_3(self) -> None:
        for mode in (1, 3):
            field = self._field(color_mode=mode)
            for row in field:
                for slot in (0, 2, 4, 5):
                    self.assertEqual(row[slot], 0.0, msg=f"mode {mode} wrote slot {slot}")

    def test_slots_never_exceed_0_through_4(self) -> None:
        for mode in (0, 1, 2, 3):
            field = self._field(color_mode=mode)
            for row in field:
                self.assertEqual(row[5], 0.0)


class DropFireworkExplosionTests(unittest.TestCase):
    """AWR-161 Task 3: contrast-gated firework explosion promotion.

    The operator's condition is promote-only-if-verified: this class's
    test_post_surge_ember_contrast_gate is the measured gate from the spec
    (max per-pixel deviation from the plain background >= 60/255 at default
    params, sampled post-surge). If this fails, the effect must not ship.
    """

    # bg (255, 240, 220) * bg_hold (0.7) * bg_level (1.0), clamped -- the
    # plain background color once the post-surge settle finishes.
    _BG_REF = (178, 168, 154)

    def test_post_surge_ember_contrast_gate(self) -> None:
        renderer = GoveeFrameRenderer()
        seg = 40
        max_dev = 0
        for tick in range(400):
            frame = renderer.render(
                "drop_firework_explosion",
                beat_pos=2.0,  # well past surge_beats(0.5) + the 0.5-beat settle
                local_t=tick / 40.0,
                frame_index=tick,
                params={},
                segments=seg,
                seed=7,
            )
            for px in frame:
                dev = max(abs(px[c] - self._BG_REF[c]) for c in range(3))
                max_dev = max(max_dev, dev)
        self.assertGreaterEqual(max_dev, 60, msg=f"measured ember contrast {max_dev}/255")

    def test_registered_and_not_a_strobe(self) -> None:
        self.assertIn("drop_firework_explosion", REALTIME_EFFECT_NAMES)
        self.assertNotIn("drop_firework_explosion", REALTIME_STROBE_EFFECTS)

    def test_surge_resolves_down_to_bg_hold_not_stuck_at_full(self) -> None:
        renderer = GoveeFrameRenderer()
        seg = 20
        # No embers (density 0) isolates the background/surge math.
        params = {"sparkle_density": 0.0}
        peak = renderer.render("drop_firework_explosion", beat_pos=0.5, local_t=0.0,
                                frame_index=0, params=params, segments=seg, seed=1)
        settled = renderer.render("drop_firework_explosion", beat_pos=2.0, local_t=0.0,
                                   frame_index=0, params=params, segments=seg, seed=1)
        self.assertEqual(peak, [(255, 240, 220)] * seg)
        self.assertEqual(settled, [self._BG_REF] * seg)

    def test_embers_are_time_based_not_beat_tied(self) -> None:
        """AWR-153 sparkle ruling: sparkles are continuous/time-based, never
        beat-tied -- the ember layer must depend on local_t, not beat."""
        renderer = GoveeFrameRenderer()
        seg = 40
        frame_a = renderer.render("drop_firework_explosion", beat_pos=5.0, local_t=0.3,
                                   frame_index=0, params={}, segments=seg, seed=3)
        frame_b = renderer.render("drop_firework_explosion", beat_pos=99.0, local_t=0.3,
                                   frame_index=0, params={}, segments=seg, seed=3)
        # Beat only drives the surge/settle background level, which is already
        # fully settled by beat 5; embers at the same local_t must match.
        self.assertEqual(frame_a, frame_b)
        frame_c = renderer.render("drop_firework_explosion", beat_pos=5.0, local_t=0.9,
                                   frame_index=0, params={}, segments=seg, seed=3)
        self.assertNotEqual(frame_a, frame_c)


class PostDropFireworkRemnantsTests(unittest.TestCase):
    """AWR-156 Task 7.4."""

    def _params(self, **overrides):
        base = {"dim_beats": 8, "ember_hold_beats": 8, "ember_decay_beats": 2,
                "sparkle_density": 0.35, "sparkle_size": 1.0, "sparkle_life_s": 0.8}
        base.update(overrides)
        return base

    def test_ember_full_at_or_before_hold_beats(self) -> None:
        field = _slot_rt_post_drop_firework_remnants(8.0, 5.0, 0, self._params(), 20, 1)
        ember_total = sum(sum(row[:5]) for row in field)
        self.assertGreater(ember_total, 0.0)

    def test_ember_zero_by_beat_ten_point_five(self) -> None:
        field = _slot_rt_post_drop_firework_remnants(10.5, 5.0, 0, self._params(), 20, 1)
        for row in field:
            for slot in range(5):
                self.assertEqual(row[slot], 0.0)

    def test_slot_five_carries_only_background(self) -> None:
        field = _slot_rt_post_drop_firework_remnants(0.0, 0.3, 0, self._params(), 20, 1)
        for row in field:
            self.assertAlmostEqual(row[5], 1.0, places=9)

    def test_embers_only_write_slots_zero_through_four(self) -> None:
        field = _slot_rt_post_drop_firework_remnants(2.0, 1.5, 0, self._params(), 20, 1)
        # background at beat 2 is 1 - 2/8 = 0.75, distinct from any ember contribution
        for row in field:
            self.assertAlmostEqual(row[5], 0.75, places=9)

    def test_deterministic_for_same_seed_and_local_t(self) -> None:
        a = _slot_rt_post_drop_firework_remnants(2.0, 1.5, 0, self._params(), 20, 7)
        b = _slot_rt_post_drop_firework_remnants(2.0, 1.5, 0, self._params(), 20, 7)
        self.assertEqual(a, b)
        c = _slot_rt_post_drop_firework_remnants(2.0, 1.5, 0, self._params(), 20, 8)
        self.assertNotEqual(a, c)


class Knob4MashupDeathTests(unittest.TestCase):
    """AWR-156 Task 7.5: per-spawn single slot, intensity is brightness only."""

    def test_groove_chase_two_heads_land_on_different_slots(self) -> None:
        field = _slot_groove_chase(1.0, 0.0, 0, {"loop_beats": 4.0}, 20, 1)
        touched = {slot for row in field for slot in range(6) if row[slot] > 0}
        self.assertEqual(len(touched), 2)
        for row in field:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertLessEqual(len(lit), 1)

    def test_groove_nebula_two_heads_land_on_different_slots(self) -> None:
        field = _slot_groove_nebula(1.0, 0.0, 0, {"loop_beats": 4.0}, 20, 1)
        touched = {slot for row in field for slot in range(6) if row[slot] > 0}
        self.assertEqual(len(touched), 2)
        for row in field:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertLessEqual(len(lit), 1)

    def test_post_drop_chase_single_slot_per_spawn(self) -> None:
        # cue_beat=0.5 -> exactly one spawn active (_drop_chase_spawn_times
        # start=0.0): spawn_idx=0 -> slot 0.
        spawns = _drop_chase_spawn_times(0.5, start=0.0)
        self.assertEqual([idx for _, idx in spawns], [0])
        field = _slot_post_drop_chase(0.5, 0.0, 0, {}, 20, 1)
        lit_rows = [row for row in field if sum(row) > 0]
        self.assertTrue(lit_rows)
        for row in lit_rows:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertEqual(lit, [0])

    def test_drop_nebula_palette_branch_single_slot_white_branch_untouched(self) -> None:
        field = _slot_drop_nebula(9.5, 0.0, 0, {}, 20, 1)
        for row in field:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertLessEqual(len(lit), 1)

    def test_post_drop_nebula_palette_branch_single_slot_white_branch_untouched(self) -> None:
        field = _slot_post_drop_nebula(1.5, 0.0, 0, {}, 20, 1)
        for row in field:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertLessEqual(len(lit), 1)
        # Confirm both a palette slot (0-4) and the white slot (5) still fire
        # somewhere across the frame -- the white branch is untouched.
        any_palette = any(row[s] > 0 for row in field for s in range(5))
        any_white = any(row[5] > 0 for row in field)
        self.assertTrue(any_palette)
        self.assertTrue(any_white)

    def test_drop_center_burst_main_and_accent_bands_survive(self) -> None:
        main_field = _slot_drop_center_burst(0.0, 0.0, 0, {}, 20, 1)
        main_lit = {s for row in main_field for s in range(3) if row[s] > 0}
        self.assertTrue(main_lit)
        self.assertTrue(main_lit.issubset({0, 1, 2}))
        for row in main_field:
            for s in (3, 4, 5):
                self.assertEqual(row[s], 0.0)

        accent_field = _slot_drop_center_burst(1.5, 0.0, 0, {}, 20, 1)
        accent_lit = {s for row in accent_field for s in range(6) if row[s] > 0}
        self.assertTrue(accent_lit)
        self.assertTrue(accent_lit.issubset({2, 3, 4}))

    def test_post_drop_center_comet_single_slot_per_pass(self) -> None:
        field = _slot_post_drop_center_comet(0.0, 0.0, 0, {}, 20, 1)
        for row in field:
            lit = [s for s in range(6) if row[s] > 0]
            self.assertLessEqual(len(lit), 1)

    def test_positional_mapping_prototypes_untouched(self) -> None:
        """_slot_groove_center_chase and _slot_post_drop_firework_chase are NOT
        mashup sites (Absolute Rules exclusion) -- they still use the ordered
        gradient split across two adjacent slots (a sub-pixel comet position
        lands between two slot boundaries)."""
        from rb_ss_bridge_v2.govee_frame_renderer import _slot_groove_center_chase
        found_split = False
        for beat in [i / 7.0 for i in range(50)]:
            field = _slot_groove_center_chase(beat, 0.0, 0, {"travel_beats": 1.0}, 20, 1)
            if any(sum(1 for v in row if v > 0) > 1 for row in field):
                found_split = True
                break
        self.assertTrue(found_split, msg="expected the ordered gradient split to survive untouched")


class Task9BakedWhiteSlot5Tests(unittest.TestCase):
    """AWR-156 Task 9 (operator refinement): slot-5 zone tint narrowed to
    nebula comets only; firework bursts render baked pure white."""

    _TINT = [(10, 20, 30), (40, 50, 60), (70, 80, 90), (100, 110, 120),
             (130, 140, 150), (200, 10, 220)]

    def test_firework_chase_burst_pixels_render_literal_pure_white(self) -> None:
        renderer = GoveeFrameRenderer()
        # beat 3.5: cue_beat % 4 == 3.5 >= 3 -> the slot-5 white burst window.
        frame = renderer.render("post_drop_firework_chase", beat_pos=3.5, local_t=0.0,
                                 frame_index=0, params={"slot_colors": self._TINT}, segments=20, seed=1)
        self.assertTrue(any(px == (255, 255, 255) for px in frame))
        self.assertFalse(any(px == self._TINT[5] for px in frame))

    def test_nebula_white_comets_render_the_injected_slot5_tint(self) -> None:
        renderer = GoveeFrameRenderer()
        for name in ("rt_drop_nebula", "rt_post_drop_nebula"):
            with self.subTest(name=name):
                frame = renderer.render(name, beat_pos=9.5, local_t=0.0, frame_index=0,
                                         params={"slot_colors": self._TINT}, segments=20, seed=1)
                self.assertTrue(any(px == self._TINT[5] for px in frame), msg=name)
                self.assertFalse(any(px == (255, 255, 255) for px in frame), msg=name)

    def test_remnants_background_renders_the_injected_slot5_tint(self) -> None:
        renderer = GoveeFrameRenderer()
        frame = renderer.render("rt_post_drop_firework_remnants", beat_pos=0.0, local_t=0.3,
                                 frame_index=0, params={"slot_colors": self._TINT}, segments=20, seed=1)
        self.assertTrue(any(px == self._TINT[5] for px in frame))


if __name__ == "__main__":
    unittest.main()
