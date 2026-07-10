"""M2 Phase 2a tests — the 6 new prototype cues in the renderer.

Pure unit tests (no hardware, no I/O).  All effects are called directly; engine
cues (MotionField) are colorized with synthetic slot_colors to inspect output.

Covers (per spec §5):
1. Each engine cue returns a valid MotionField (shape [segments][MAX_SLOTS],
   intensities >= 0); the baked sand cue returns a Frame with max channel <= the
   30% cap.
2. Structure-invariance: a cue rendered at one beat with two different synthetic
   slot_colors lights an identical set of pixel indices (geometry is
   color-independent).
3. Determinism: same (beat, segments, params) -> byte-identical MotionField, and
   the ignored EffectFn args (local_t/frame_index/seed) do not perturb output.
4. Smoothness (fractional motion): groove_center_chase's right-half intensity
   centroid advances by SMALL non-integer amounts across sub-beat steps — proves
   no integer snapping of the moving head.
5. Firework timing: post_drop_firework_chase has slot-5 energy ONLY when
   cue_beat % 4 >= 3; zero slot-5 elsewhere; the comet (slots 0-4) is present
   throughout.
6. post_drop_chase_* untouched: post_drop_chase_blue still renders to a captured
   golden frame.
7. Registration + Phase-1 byte-identical gate are still green (the latter by
   importing and running the Phase-1 suite's renderer regression).
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import govee_frame_renderer as gfr  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    EDM_BUILDS,
    GoveeFrameRenderer,
    MAX_SLOTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    _EFFECTS,
    _SYNC_PARAM_KEYS,
    universal_colorizer,
)

_ENGINE_CUES = (
    "groove_center_chase",
    "groove_center_burst_retract",
    "post_drop_firework_chase",
    "breakdown_full_breathing",
    "breakdown_star_twinkle",
)
_SAND = "breakdown_star_twinkle_sand"
_ALL_SIX = _ENGINE_CUES + (_SAND,)

# A six-entry synthetic palette.  Every slot is FULL brightness (255) on a single
# channel so the colorizer's per-channel rounding behaves identically regardless
# of WHICH channel carries it.  This isolates geometry (which pixels light) from
# brightness/rounding, which is what structure-invariance actually asserts: two
# palettes whose slots differ only in HUE (channel placement), not magnitude,
# must light the identical set of pixels for the same MotionField.
_PALETTE_A: list[tuple[int, int, int]] = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 255),  # slot 5 = pure white (firework slot)
]
# Same per-slot magnitude (255 on one channel) but a different channel for each
# slot, so colors differ at lit pixels while rounding stays identical.
_PALETTE_B: list[tuple[int, int, int]] = [
    (0, 0, 255),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 0, 0),
    (255, 255, 255),  # slot 5 white in both (the firework slot is fixed white)
]


def _call_engine(name: str, beat: float, segments: int,
                 params: dict[str, Any] | None = None,
                 local_t: float = 0.0, frame_index: int = 0, seed: int = 1):
    return SLOT_EFFECTS[name](
        float(beat), float(local_t), int(frame_index),
        params or {}, int(segments), int(seed),
    )


def _call_sand(beat: float, segments: int, params: dict[str, Any] | None = None):
    return _EFFECTS[_SAND](
        float(beat), float(beat), 0, params or {}, int(segments), 1,
    )


# ---------------------------------------------------------------------------
# 1. MotionField shape / sand cap + Frame type
# ---------------------------------------------------------------------------

class MotionFieldShapeTests(unittest.TestCase):
    def test_engine_cues_return_valid_motion_field(self):
        segments = 48
        for name in _ENGINE_CUES:
            for beat in (0.0, 0.5, 1.0, 2.5, 3.5, 7.0, 16.3, 31.9):
                field = _call_engine(name, beat, segments)
                self.assertEqual(len(field), segments,
                                 msg=f"{name}@{beat}: segment count")
                for row in field:
                    self.assertEqual(len(row), MAX_SLOTS,
                                     msg=f"{name}@{beat}: slot count")
                    for v in row:
                        self.assertIsInstance(v, float,
                                              msg=f"{name}@{beat}: intensity type")
                        self.assertGreaterEqual(v, 0.0,
                                                msg=f"{name}@{beat}: non-negative")

    def test_engine_cues_actually_light_something(self):
        # A vacuous all-zero field would trivially pass shape checks; assert each
        # cue emits energy at a beat where it should be active.
        segments = 48
        active_beat = {
            "groove_center_chase": 0.5,
            "groove_center_burst_retract": 0.3,
            "post_drop_firework_chase": 0.5,
            "breakdown_full_breathing": 2.0,   # mid-inhale of the 8-beat breath
            "breakdown_star_twinkle": 0.0,
        }
        for name, beat in active_beat.items():
            field = _call_engine(name, beat, segments)
            total = sum(v for row in field for v in row)
            self.assertGreater(total, 0.0, msg=f"{name}@{beat} produced no light")

    def test_sand_returns_frame_of_rgb_tuples(self):
        segments = 48
        frame = _call_sand(0.3, segments)
        self.assertEqual(len(frame), segments)
        for px in frame:
            self.assertIsInstance(px, tuple)
            self.assertEqual(len(px), 3)
            for ch in px:
                self.assertIsInstance(ch, int)

    def test_sand_obeys_30pct_cap(self):
        # The prototype scales by 0.3 then int()-truncates each channel.  The
        # theoretical max is int(255 * 1.0 * 0.3) = 76 = round(0.3*255).
        cap = round(0.3 * 255)  # 76
        segments = 64
        observed_max = 0
        any_lit = False
        for beat in (0.0, 0.4, 0.9, 1.7, 2.6, 3.1, 5.5, 9.3):
            frame = _call_sand(beat, segments)
            for px in frame:
                m = max(px)
                observed_max = max(observed_max, m)
                if m > 0:
                    any_lit = True
                for ch in px:
                    self.assertLessEqual(ch, cap, msg=f"sand@{beat} channel {ch} > {cap}")
        self.assertTrue(any_lit, msg="sand never lit any pixel across the sweep")
        # The cap is meaningfully exercised (not just trivially under it).
        self.assertGreater(observed_max, 0)
        self.assertLessEqual(observed_max, cap)


# ---------------------------------------------------------------------------
# 2. Structure-invariance (geometry is color-independent)
# ---------------------------------------------------------------------------

class StructureInvarianceTests(unittest.TestCase):
    def test_lit_pixel_set_independent_of_palette(self):
        segments = 50
        for name in _ENGINE_CUES:
            # Pick a beat where the cue is active for each.
            beat = {
                "groove_center_chase": 0.5,
                "groove_center_burst_retract": 0.3,
                "post_drop_firework_chase": 3.5,  # comet + fireworks both active
                "breakdown_full_breathing": 2.0,
                "breakdown_star_twinkle": 0.0,
            }[name]
            field = _call_engine(name, beat, segments)
            frame_a = universal_colorizer(field, _PALETTE_A)
            frame_b = universal_colorizer(field, _PALETTE_B)
            lit_a = [i for i, px in enumerate(frame_a) if px != (0, 0, 0)]
            lit_b = [i for i, px in enumerate(frame_b) if px != (0, 0, 0)]
            self.assertEqual(lit_a, lit_b,
                             msg=f"{name}: lit-pixel geometry changed with palette")
            self.assertTrue(lit_a, msg=f"{name}: nothing lit (vacuous invariance)")
            # The colors themselves DO differ at SOME lit pixel (so the test is
            # not vacuously passing on two identical palettes).  The two palettes
            # share slot 5 (white firework), so pixels lit purely by slot 5 will
            # match — but the gradient slots 0-4 differ in hue, so at least one
            # lit pixel must differ.
            self.assertTrue(
                any(frame_a[i] != frame_b[i] for i in lit_a),
                msg=f"{name}: palette swap produced identical colors everywhere",
            )


# ---------------------------------------------------------------------------
# 3. Determinism
# ---------------------------------------------------------------------------

class DeterminismTests(unittest.TestCase):
    def test_engine_cue_byte_identical_repeat(self):
        segments = 47
        for name in _ENGINE_CUES:
            for beat in (0.5, 3.5, 17.25):
                first = _call_engine(name, beat, segments)
                second = _call_engine(name, beat, segments)
                self.assertEqual(first, second, msg=f"{name}@{beat} not repeatable")

    def test_ignored_args_do_not_affect_output(self):
        # local_t / frame_index / seed are ignored by these cues; output must be
        # identical regardless (proves the per-pixel reseed uses the prototype's
        # own idx-based seed, not the bridge seed).
        segments = 47
        for name in _ENGINE_CUES:
            for beat in (0.5, 3.5):
                base = _call_engine(name, beat, segments,
                                    local_t=0.0, frame_index=0, seed=1)
                varied = _call_engine(name, beat, segments,
                                      local_t=123.4, frame_index=99, seed=777)
                self.assertEqual(base, varied,
                                 msg=f"{name}@{beat} drifted with ignored args")

    def test_sand_byte_identical_repeat(self):
        segments = 47
        for beat in (0.3, 3.1, 11.7):
            self.assertEqual(_call_sand(beat, segments), _call_sand(beat, segments))


# ---------------------------------------------------------------------------
# 4. Smoothness — fractional motion (the no-int-snap guard)
# ---------------------------------------------------------------------------

class FractionalSmoothnessTests(unittest.TestCase):
    def _right_half_centroid(self, field, center):
        num = 0.0
        den = 0.0
        for idx, row in enumerate(field):
            if idx < center:
                continue
            v = sum(row)
            if v <= 0:
                continue
            num += (idx - center) * v
            den += v
        return num / den if den > 0 else None

    def test_comet_centroid_advances_fractionally(self):
        # groove_center_chase is symmetric about the center, so the WHOLE-strip
        # centroid is pinned at center.  Instead measure the right-half intensity
        # centroid: as the comet head travels outward it must advance by small,
        # NON-INTEGER amounts across sub-beat steps.  Integer snapping would make
        # the centroid jump only on whole-pixel boundaries / stay constant
        # between steps.
        segments = 60
        center = segments / 2.0
        beats = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
        centroids = []
        for b in beats:
            field = _call_engine("groove_center_chase", b, segments)
            c = self._right_half_centroid(field, center)
            self.assertIsNotNone(c, msg=f"no right-half energy at beat {b}")
            centroids.append(c)

        # (a) It is NOT constant across sub-beat steps (motion exists).
        self.assertGreater(len(set(round(c, 6) for c in centroids)), 1,
                           msg="centroid is constant — no sub-beat motion")

        # (b) Strictly monotonically increasing by small fractional steps.
        diffs = [centroids[i + 1] - centroids[i] for i in range(len(centroids) - 1)]
        for d in diffs:
            self.assertGreater(d, 0.0, msg="centroid did not advance outward")
            self.assertLess(d, 2.0, msg="centroid jumped too far for a 0.05-beat step")

        # (c) At least one centroid is genuinely fractional (not an integer
        #     index) — the decisive no-int-snap assertion.
        self.assertTrue(
            any(abs(c - round(c)) > 1e-6 for c in centroids),
            msg="every centroid landed on an integer — looks integer-snapped",
        )


# ---------------------------------------------------------------------------
# 5. Firework timing (slot 5)
# ---------------------------------------------------------------------------

class FireworkTimingTests(unittest.TestCase):
    def _slot5_energy(self, beat, segments):
        field = _call_engine("post_drop_firework_chase", beat, segments)
        return sum(row[5] for row in field)

    def _comet_energy(self, beat, segments):
        field = _call_engine("post_drop_firework_chase", beat, segments)
        return sum(row[s] for row in field for s in range(5))

    def test_slot5_only_on_fourth_beat(self):
        segments = 60
        # cue_beat % 4 < 3  -> NO slot-5 energy.
        for beat in (0.0, 0.5, 1.5, 2.5, 2.99, 4.5, 6.5, 16.5):
            self.assertEqual(self._slot5_energy(beat, segments), 0.0,
                             msg=f"unexpected slot-5 energy at beat {beat}")
        # cue_beat % 4 >= 3 -> slot-5 fireworks fire.
        fired = False
        for beat in (3.02, 3.25, 3.5, 3.75, 7.5, 31.5):
            if self._slot5_energy(beat, segments) > 0.0:
                fired = True
        self.assertTrue(fired, msg="no slot-5 fireworks fired on any 4th beat")

    def test_slot5_present_at_a_specific_fourth_beat(self):
        # Be concrete: beat 3.5 (cue_beat % 4 == 3.5) must light slot 5.
        self.assertGreater(self._slot5_energy(3.5, 60), 0.0)

    def test_comet_present_throughout(self):
        segments = 60
        for beat in (0.5, 1.5, 2.5, 3.5):
            self.assertGreater(self._comet_energy(beat, segments), 0.0,
                               msg=f"comet (slots 0-4) absent at beat {beat}")

    def test_duration_beats_respected_via_edm_beat(self):
        # cue_beat = beat % duration_beats.  With duration_beats=4, beat=7.5 maps
        # to cue_beat=3.5 -> fireworks; beat=4.5 maps to cue_beat=0.5 -> none.
        segments = 60
        params = {"duration_beats": 4.0}
        e_fire = sum(
            row[5]
            for row in _call_engine("post_drop_firework_chase", 7.5, segments, params)
        )
        e_none = sum(
            row[5]
            for row in _call_engine("post_drop_firework_chase", 4.5, segments, params)
        )
        self.assertGreater(e_fire, 0.0)
        self.assertEqual(e_none, 0.0)


# ---------------------------------------------------------------------------
# 6. post_drop_chase_* family untouched
# ---------------------------------------------------------------------------

class PostDropChaseUntouchedTests(unittest.TestCase):
    # Golden frame captured from post_drop_chase_blue (segments=20, seed=12345,
    # beat=1.0, frame_index=3).  Adding the new firework cue must not disturb it.
    _GOLDEN_BLUE = [
        [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
        [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
        [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
        [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
    ]

    def test_post_drop_chase_blue_unchanged(self):
        r = GoveeFrameRenderer()
        out = r.render(
            "post_drop_chase_blue", beat_pos=1.0, local_t=1.0, frame_index=3,
            params={}, segments=20, seed=12345,
        )
        self.assertEqual([list(px) for px in out], self._GOLDEN_BLUE)

    def test_firework_chase_is_distinct_from_chase_blue(self):
        # post_drop_firework_chase is its OWN look, not a member of the
        # post_drop_chase_* family.
        self.assertNotIn("post_drop_firework_chase", EDM_BUILDS)
        self.assertIn("post_drop_firework_chase", SLOT_EFFECTS)
        # The old blue chase is a baked Frame effect, not a slot effect.
        self.assertNotIn("post_drop_chase_blue", SLOT_EFFECTS)


# ---------------------------------------------------------------------------
# 7. Registration + Phase-1 gate
# ---------------------------------------------------------------------------

class RegistrationTests(unittest.TestCase):
    def test_slot_effects_has_engine_and_m2_5_cues(self):
        self.assertEqual(
            set(SLOT_EFFECTS),
            set(_ENGINE_CUES) | {
                "rt_groove_chase",
                "rt_groove_nebula",
                "rt_post_drop_chase",
                "rt_post_drop_nebula",
                "rt_drop_chase",
                "rt_drop_nebula",
                "rt_drop_center_burst",
                "rt_post_drop_center_comet",
                "rt_twinkle",
                # AWR-156: promoted accepted looks.
                "rt_groove_heartbeat",
                "rt_post_drop_firework_remnants",
                # AWR-188 Part G: palette-cycling comet (rainbow generalization).
                "palette_comet",
            },
        )

    def test_sand_baked_in_effects_not_slots(self):
        self.assertIn(_SAND, _EFFECTS)
        self.assertNotIn(_SAND, SLOT_EFFECTS)

    def test_realtime_effect_names_includes_all_six(self):
        for name in _ALL_SIX:
            self.assertIn(name, REALTIME_EFFECT_NAMES, msg=name)

    def test_firework_in_strobe_set(self):
        self.assertIn("post_drop_firework_chase", REALTIME_STROBE_EFFECTS)

    def test_param_keys_additive_and_complete(self):
        std = frozenset({"duration_beats"}) | _SYNC_PARAM_KEYS
        for name in _ALL_SIX:
            keys = REALTIME_EFFECT_PARAM_KEYS[name]
            # Standard EDM keys present for every new name.
            self.assertTrue(std.issubset(keys), msg=f"{name} missing std keys")
            # slot_colors is runtime-injected and must NOT be allowlisted.
            self.assertNotIn("slot_colors", keys, msg=f"{name} leaked slot_colors")
        # Per-cue runtime knobs are allowlisted.
        self.assertIn("burst_beats", REALTIME_EFFECT_PARAM_KEYS["groove_center_burst_retract"])
        self.assertIn("breath_beats", REALTIME_EFFECT_PARAM_KEYS["breakdown_full_breathing"])
        self.assertIn("drift_beats", REALTIME_EFFECT_PARAM_KEYS["breakdown_full_breathing"])

    def test_slot_cues_not_in_edm_builds(self):
        for name in _ENGINE_CUES:
            self.assertNotIn(name, EDM_BUILDS, msg=name)

    def test_render_path_colorizes_slot_cue(self):
        # End-to-end: render() takes the slot path for an engine cue and applies
        # the injected slot_colors palette.
        r = GoveeFrameRenderer()
        params = {"slot_colors": [list(c) for c in _PALETTE_A]}
        out = r.render(
            "post_drop_firework_chase", beat_pos=3.5, local_t=3.5, frame_index=0,
            params=params, segments=60, seed=1,
        )
        self.assertEqual(len(out), 60)
        # White fireworks on slot 5 -> some pixels should carry white energy on
        # all three channels (slot-5 color is (255,255,255)).
        self.assertTrue(any(px[0] > 0 and px[1] > 0 and px[2] > 0 for px in out),
                        msg="no white firework pixels in colorized output")


class Phase1GateStillGreenTests(unittest.TestCase):
    # The Phase-1 BYTE-IDENTICAL renderer regression must still pass: adding the
    # slot cues must not change any existing render()/render_comet() output.
    #
    # NOTE: Phase-1's class ALSO has test_slot_effects_is_empty, which asserts
    # SLOT_EFFECTS == {}.  That precondition is INTENTIONALLY stale now that
    # Phase 2a registers the 5 engine cues (it can only be retired by editing the
    # Phase-1 file, which is out of scope here).  We therefore re-run ONLY the
    # two byte-identical methods, which are the actual "byte-identical gate".
    _BYTE_IDENTICAL_METHODS = (
        "test_render_byte_identical_to_golden",
        "test_render_comet_byte_identical_to_golden",
    )

    def test_phase1_byte_identical_methods_still_pass(self):
        phase1_path = Path(__file__).resolve().with_name("test_led_color_engine_m2_phase1.py")
        spec = importlib.util.spec_from_file_location("test_led_color_engine_m2_phase1_local", phase1_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        p1 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(p1)

        suite = unittest.TestSuite()
        for method in self._BYTE_IDENTICAL_METHODS:
            suite.addTest(p1.RendererByteIdenticalTests(method))
        result = unittest.TextTestRunner(verbosity=0).run(suite)
        self.assertTrue(result.wasSuccessful(),
                        msg="Phase-1 byte-identical gate regressed")

    def test_slot_effects_is_no_longer_empty(self):
        # Phase-1's own test_slot_effects_is_empty asserted {} — confirm Phase 2a
        # has intentionally populated it by design.
        self.assertNotEqual(SLOT_EFFECTS, {})


if __name__ == "__main__":
    unittest.main()
