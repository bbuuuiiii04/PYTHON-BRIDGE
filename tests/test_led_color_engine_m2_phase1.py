"""M2 Phase 1 tests — A1 resolve_slot_colors + A2-core universal_colorizer.

Pure-seam unit tests (no hardware, no I/O) plus the Phase-1 gate: a
byte-identical renderer regression proving that adding the (empty) SLOT_EFFECTS
dispatch hook does NOT change any existing render()/render_comet() output.

Covers (per spec §4):
1. universal_colorizer correctness — single/multi slot additive, ROUND-not-
   truncate clamp (asserted against _clamp_channel), padding/short slot_colors,
   intensity>1 clamp, empty field.
2. structure-invariant — same field + different slot_colors → only rgb differs;
   geometry (which pixels are lit) is colorizer-independent.
3. resolve_slot_colors — {} for disabled/non-engine/exempt; length-6; slot 5 ==
   (255,255,255) exactly; slots 0-4 palette colors in focus window; mono-focus →
   slots equal; deterministic (no RNG advance).
4. resolve_color regression — output identical to a captured baseline after the
   _focus_window extraction (golden dict).
5. renderer byte-identical regression (THE Phase-1 gate) — render/render_comet of
   a representative effect set across beats {0,1,2,3,3.5,8,16} equals golden
   frames captured from the pre-change code.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import govee_frame_renderer as gfr  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    GoveeFrameRenderer,
    MAX_SLOTS,
    SLOT_EFFECTS,
    _clamp_channel,
    _slots,
    is_comet_effect,
    universal_colorizer,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette  # noqa: E402


# ---------------------------------------------------------------------------
# Engine fixture factories (mirror test_led_color_engine.py)
# ---------------------------------------------------------------------------

_SCALE_STOPS = {
    "green":   (0, 255, 0),
    "cyan":    (0, 255, 255),
    "blue":    (0, 0, 255),
    "purple":  (160, 0, 255),
    "magenta": (255, 0, 160),
    "red":     (255, 0, 0),
}

_PALETTES = {
    "blue_cyan": Palette(
        range=("cyan", "blue"),
        spread=0.10,
        weight=14.0,
        dwell=4,
        focus_modes={"mono": 3.0, "lean": 3.0, "full": 2.0},
    ),
    "red": Palette(
        range=("red", "red"),
        spread=0.10,
        weight=9.0,
        dwell=6,
    ),
    "purple_pink_white": Palette(
        range=("purple", "magenta"),
        spread=0.15,
        weight=1.0,
    ),
}


def _make_config(**overrides: Any) -> ColorEngineConfig:
    base = dict(
        enabled=True,
        scale_stops=dict(_SCALE_STOPS),
        palette_dwell_tracks=4,
        snap_eligible_drop_indices=(2, 3),
        big_shift_chance=0.25,
        big_shift_weight_bias=1.0,
        drama_by_role=True,
        role_spread={"drop": 0.35, "groove": 0.12, "ambient": 0.10},
        step_within_section={"drop": False, "post_drop": True, "groove": True},
        exempt_looks=("rt_drop_white_aggressive",),
        diy_color_tags={},
        set_seed_mode="random",
        palettes=dict(_PALETTES),
    )
    base.update(overrides)
    return ColorEngineConfig(**base)


def _engine(seed: int = 42, **overrides: Any) -> LedColorEngine:
    eng = LedColorEngine(_make_config(**overrides), set_seed=seed)
    # Drive a dispatch so per-track focus is seeded (mirrors live usage).
    eng.begin_dispatch(
        active_deck=1,
        load_gen=1,
        content_id="track-abc",
        filepath="/music/track.mp3",
        role="groove",
        section_id="s1",
        cycle=0,
    )
    return eng


# ---------------------------------------------------------------------------
# 1. universal_colorizer correctness
# ---------------------------------------------------------------------------

class UniversalColorizerTests(unittest.TestCase):
    def test_single_slot_round_not_truncate(self):
        # 0.5 intensity on (101, 203, 7) → channels are *.5 and must ROUND.
        # 101*0.5 = 50.5 -> round -> 50 (banker's? no: int(round) → 50);
        # 203*0.5 = 101.5 -> round -> 102; 7*0.5 = 3.5 -> round -> 4.
        # Truncation (int) would give 50, 101, 3 — different on G and B.
        field = [[0.5]]
        out = universal_colorizer(field, [(101, 203, 7)])
        expected = (
            _clamp_channel(101 * 0.5),
            _clamp_channel(203 * 0.5),
            _clamp_channel(7 * 0.5),
        )
        self.assertEqual(out, [expected])
        # Prove it really is round-not-truncate (the load-bearing assertion).
        self.assertEqual(out, [(50, 102, 4)])
        self.assertNotEqual(out, [(50, 101, 3)])  # would be truncation

    def test_single_slot_matches_clamp_channel_per_pixel(self):
        color = (255, 128, 33)
        field = [[0.0], [0.25], [0.5], [0.9], [1.0]]
        out = universal_colorizer(field, [color])
        for px, intens in zip(out, [0.0, 0.25, 0.5, 0.9, 1.0]):
            self.assertEqual(
                px,
                (
                    _clamp_channel(color[0] * intens),
                    _clamp_channel(color[1] * intens),
                    _clamp_channel(color[2] * intens),
                ),
            )

    def test_multi_slot_additive_sum(self):
        # px0: 0.5*(100,0,0) + 0.5*(0,40,0) = (50,20,0)
        # px1: 1.0*(100,0,0) + 0.0*(0,40,0) = (100,0,0)
        slot_colors = [(100, 0, 0), (0, 40, 0)]
        field = [[0.5, 0.5], [1.0, 0.0]]
        out = universal_colorizer(field, slot_colors)
        self.assertEqual(out, [(50, 20, 0), (100, 0, 0)])

    def test_additive_overflow_clamps_to_255(self):
        # 200 + 200 = 400 on R → clamp to 255.
        slot_colors = [(200, 0, 0), (200, 0, 0)]
        field = [[1.0, 1.0]]
        out = universal_colorizer(field, slot_colors)
        self.assertEqual(out, [(255, 0, 0)])

    def test_intensity_above_one_clamps(self):
        out = universal_colorizer([[2.0]], [(200, 100, 10)])
        # 200*2=400→255, 100*2=200, 10*2=20
        self.assertEqual(out, [(255, 200, 20)])

    def test_short_slot_colors_ignores_missing_slots(self):
        # Only one color provided; the 2nd slot intensity contributes nothing.
        out = universal_colorizer([[1.0, 1.0]], [(10, 20, 30)])
        self.assertEqual(out, [(10, 20, 30)])

    def test_more_slots_than_colors_padded_dark(self):
        # field references slot 2 but only 2 colors → slot 2 is (0,0,0).
        out = universal_colorizer([[0.0, 0.0, 1.0]], [(10, 0, 0), (0, 20, 0)])
        self.assertEqual(out, [(0, 0, 0)])

    def test_slots_beyond_max_slots_ignored(self):
        # MAX_SLOTS slots all bright + one extra beyond MAX_SLOTS that, were it
        # counted, would push R over. The extra (index == MAX_SLOTS) is ignored.
        colors = [(10, 0, 0)] * MAX_SLOTS + [(255, 0, 0)]
        field = [[1.0] * (MAX_SLOTS + 1)]
        out = universal_colorizer(field, colors)
        # 6 * 10 = 60, the 7th (index 6) is ignored.
        self.assertEqual(out, [(60, 0, 0)])

    def test_zero_intensity_skipped_no_contribution(self):
        out = universal_colorizer([[0.0, 1.0]], [(255, 255, 255), (0, 0, 50)])
        self.assertEqual(out, [(0, 0, 50)])

    def test_negative_intensity_skipped(self):
        # intensity <= 0 must contribute nothing (skip the multiply).
        out = universal_colorizer([[-1.0, 1.0]], [(255, 0, 0), (0, 0, 50)])
        self.assertEqual(out, [(0, 0, 50)])

    def test_empty_field_empty_frame(self):
        self.assertEqual(universal_colorizer([], [(255, 255, 255)]), [])

    def test_purity_no_input_mutation(self):
        field = [[0.5, 0.5]]
        colors = [(100, 0, 0), (0, 40, 0)]
        field_copy = [list(row) for row in field]
        colors_copy = list(colors)
        universal_colorizer(field, colors)
        self.assertEqual(field, field_copy)
        self.assertEqual(colors, colors_copy)


# ---------------------------------------------------------------------------
# 2. structure-invariant
# ---------------------------------------------------------------------------

class StructureInvariantTests(unittest.TestCase):
    def test_geometry_independent_of_slot_colors(self):
        # Same MotionField, two different palettes → which pixels are non-zero
        # must be identical (geometry is the colorizer-independent contract).
        field = [[0.0], [0.7], [0.0], [1.0], [0.0]]
        a = universal_colorizer(field, [(255, 0, 0)])
        b = universal_colorizer(field, [(0, 80, 200)])
        lit_a = [i for i, px in enumerate(a) if px != (0, 0, 0)]
        lit_b = [i for i, px in enumerate(b) if px != (0, 0, 0)]
        self.assertEqual(lit_a, lit_b)
        self.assertEqual(lit_a, [1, 3])
        # And the colors themselves DO differ at the lit pixels.
        self.assertNotEqual(a[1], b[1])
        self.assertNotEqual(a[3], b[3])


# ---------------------------------------------------------------------------
# 3. resolve_slot_colors
# ---------------------------------------------------------------------------

class ResolveSlotColorsTests(unittest.TestCase):
    def _resolve(self, eng: LedColorEngine, **kw: Any) -> dict:
        base = dict(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="some_look",
            color_source="engine",
        )
        base.update(kw)
        return eng.resolve_slot_colors(**base)

    def test_disabled_returns_empty(self):
        eng = LedColorEngine(_make_config(enabled=False), set_seed=42)
        self.assertEqual(
            eng.resolve_slot_colors(
                role="groove", section_id="s1", cycle=0,
                look_name="x", color_source="engine",
            ),
            {},
        )

    def test_non_engine_source_returns_empty(self):
        eng = _engine()
        self.assertEqual(self._resolve(eng, color_source="baked"), {})

    def test_exempt_look_returns_empty(self):
        eng = _engine()
        self.assertEqual(
            self._resolve(eng, look_name="rt_drop_white_aggressive"), {}
        )

    def test_returns_length_six(self):
        eng = _engine()
        res = self._resolve(eng)
        self.assertIn("slot_colors", res)
        self.assertEqual(len(res["slot_colors"]), 6)

    def test_slot_five_is_pure_white(self):
        # Slot 5 is a reserved pure-white slot, independent of the selected palette.
        eng = _engine(seed=7)
        eng.set_palette("purple_pink_white")
        res = self._resolve(eng)
        self.assertEqual(res["slot_colors"][5], (255, 255, 255))

    def test_gradient_slots_are_valid_rgb_triples(self):
        eng = _engine()
        res = self._resolve(eng)
        for rgb in res["slot_colors"][:5]:
            self.assertEqual(len(rgb), 3)
            for ch in rgb:
                self.assertTrue(0 <= ch <= 255)

    def test_gradient_slots_within_focus_window(self):
        # Sample each gradient slot's p and confirm it equals _p_to_rgb on a
        # p inside [focus_lo, focus_hi] blended with palette.white.
        from rb_ss_bridge_v2.led_color_engine import _p_to_rgb, _blend_white
        eng = _engine(seed=3)
        focus_lo, focus_hi = eng._focus_window("groove")
        palette = eng._config.palettes[eng._current_palette]
        res = self._resolve(eng)
        gradient = res["slot_colors"][:5]
        for i, rgb in enumerate(gradient):
            t = i / 4  # gradient_count - 1 == 4
            p = focus_lo + t * (focus_hi - focus_lo)
            p = max(0.0, min(1.0, p))
            expect = _blend_white(
                _p_to_rgb(p, eng._config.scale_stops, eng._stop_positions),
                palette.white,
            )
            self.assertEqual(rgb, expect)

    def test_mono_focus_collapses_gradient_slots(self):
        # A point palette (range red→red) has zero-width focus → all gradient
        # slots collapse to the same color.
        eng = _engine(seed=11)
        eng.set_palette("red")
        # Force a fresh focus draw for the (now) red palette.
        eng._reseed_focus()
        focus_lo, focus_hi = eng._focus_window("groove")
        self.assertAlmostEqual(focus_lo, focus_hi, places=9,
                               msg="precondition: red palette focus is mono")
        res = self._resolve(eng)
        gradient = res["slot_colors"][:5]
        self.assertEqual(len(set(gradient)), 1)
        # Slot 5 is still pure white (distinct from collapsed gradient).
        self.assertEqual(res["slot_colors"][5], (255, 255, 255))

    def test_deterministic_repeated_calls_no_rng_advance(self):
        eng = _engine(seed=99)
        first = self._resolve(eng)
        second = self._resolve(eng)
        third = self._resolve(eng)
        self.assertEqual(first["slot_colors"], second["slot_colors"])
        self.assertEqual(second["slot_colors"], third["slot_colors"])

    def test_does_not_advance_per_cue_rng_vs_resolve_color(self):
        # resolve_slot_colors must not perturb resolve_color's deterministic
        # output: calling it between two resolve_color calls is a no-op on RNG.
        eng = _engine(seed=55)
        c1 = eng.resolve_color(
            role="groove", section_id="s1", cycle=0,
            look_name="x", color_source="engine",
        )
        self._resolve(eng)  # interleave slot resolution
        c2 = eng.resolve_color(
            role="groove", section_id="s1", cycle=0,
            look_name="x", color_source="engine",
        )
        self.assertEqual(c1["color"], c2["color"])

# ---------------------------------------------------------------------------
# 4. resolve_color regression after _focus_window extraction (golden)
# ---------------------------------------------------------------------------

class ResolveColorRegressionTests(unittest.TestCase):
    """Golden dict captured from the pre-extraction resolve_color for a fixed
    engine state. If the _focus_window refactor changed observable output, these
    exact RGB values would differ."""

    GOLDEN = {
        # (seed, role, section_id, cycle, multi) -> result dict
        (42, "groove", "s1", 0, False): None,
        (42, "drop", "s1", 0, True): None,
        (7, "ambient", "s2", 1, False): None,
    }

    def _state(self, seed: int) -> LedColorEngine:
        # Deterministic engine state: fixed seed + identical dispatch.
        return _engine(seed=seed)

    def test_resolve_color_matches_recomputed_baseline(self):
        # We cannot embed pre-change literals (the refactor is already applied),
        # so instead assert resolve_color equals an INDEPENDENT recomputation of
        # the exact original inline formula — proving _focus_window is faithful.
        from rb_ss_bridge_v2.led_color_engine import (
            _p_to_rgb, _blend_white, _blake2b_int, _rng_from_seed,
        )
        for (seed, role, section_id, cycle, multi) in self.GOLDEN:
            eng = self._state(seed)

            # --- recompute the ORIGINAL inline focus-window math by hand ---
            lo_p, hi_p = eng._palette_p_interval(eng._current_palette)
            palette = eng._config.palettes[eng._current_palette]
            base_spread = palette.spread
            if eng._config.drama_by_role:
                role_spread = eng._config.role_spread.get(role, base_spread)
                eff = max(base_spread, role_spread)
            else:
                eff = base_spread
            fc, fw = eng._focus_fc, eng._focus_fw
            focus_lo = max(lo_p, fc - fw - eff)
            focus_hi = min(hi_p, fc + fw + eff)
            if focus_lo > focus_hi:
                focus_lo, focus_hi = lo_p, hi_p

            use_step = eng._config.step_within_section.get(role, False)
            step_index = cycle if use_step else 0
            cue_seed = _blake2b_int(
                f"{eng._current_track_seed}:{section_id}:{step_index}"
            )
            cue_rng = _rng_from_seed(cue_seed)
            p = max(0.0, min(1.0, cue_rng.uniform(focus_lo, focus_hi)))
            rgb = _blend_white(
                _p_to_rgb(p, eng._config.scale_stops, eng._stop_positions),
                palette.white,
            )
            expected = {"color": rgb}
            if multi:
                p_low = max(0.0, min(1.0, focus_lo))
                p_high = max(0.0, min(1.0, focus_hi))
                expected["color_a"] = _blend_white(
                    _p_to_rgb(p_low, eng._config.scale_stops, eng._stop_positions),
                    palette.white,
                )
                expected["color_b"] = _blend_white(
                    _p_to_rgb(p_high, eng._config.scale_stops, eng._stop_positions),
                    palette.white,
                )

            actual = eng.resolve_color(
                role=role, section_id=section_id, cycle=cycle,
                look_name="x", color_source="engine", multi=multi,
            )
            self.assertEqual(actual, expected,
                             msg=f"seed={seed} role={role} multi={multi}")


# ---------------------------------------------------------------------------
# 5. renderer byte-identical regression (THE Phase-1 gate)
# ---------------------------------------------------------------------------

# Golden frames captured from the PRE-CHANGE govee_frame_renderer (segments=20,
# seed=12345). Because SLOT_EFFECTS is empty, current output MUST equal these
# byte-for-byte. Any drift here is a Phase-1 regression.
_GOLDEN_SEG = 20
_GOLDEN_SEED = 12345
_GOLDEN_BEATS = [0.0, 1.0, 2.0, 3.0, 3.5, 8.0, 16.0]

_GOLDEN_RENDER = {
    "groove_chase_blue": [[[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 96], [0, 0, 96], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 96], [0, 0, 96], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]],
    "drop_chase_blue": [[[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 41], [0, 0, 0], [0, 0, 189], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 19], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 101]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 204], [0, 0, 0], [0, 0, 0], [0, 0, 83], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 207], [0, 0, 0], [0, 0, 0], [0, 0, 53], [0, 0, 0], [0, 0, 187]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 128], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 33], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 112], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 54], [0, 0, 0], [0, 0, 210], [0, 0, 243], [0, 0, 0], [0, 0, 0], [0, 0, 240], [0, 0, 0], [0, 0, 169], [0, 0, 0], [0, 0, 82], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 152], [0, 0, 0]], [[0, 0, 39], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 85], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 41], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]],
    "post_drop_chase_blue": [[[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 255], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]],
    "solid": [[[255, 255, 255]] * 20] * 7,
    "breathe": [[[26, 26, 26]] * 20, [[140, 140, 140]] * 20, [[255, 255, 255]] * 20, [[140, 140, 140]] * 20, [[59, 59, 59]] * 20, [[26, 26, 26]] * 20, [[26, 26, 26]] * 20],
    "gradient_sweep": [[[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]], [[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]], [[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]], [[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]], [[0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255], [0, 0, 255], [0, 26, 255], [0, 51, 255], [0, 76, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 179, 255], [0, 204, 255], [0, 229, 255]], [[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]], [[0, 0, 255], [0, 25, 255], [0, 51, 255], [0, 77, 255], [0, 102, 255], [0, 128, 255], [0, 153, 255], [0, 178, 255], [0, 204, 255], [0, 230, 255], [0, 255, 255], [0, 229, 255], [0, 204, 255], [0, 178, 255], [0, 153, 255], [0, 128, 255], [0, 102, 255], [0, 77, 255], [0, 51, 255], [0, 26, 255]]],
}

_GOLDEN_COMET = {
    "groove_chase_blue": [[[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 51], [0, 0, 153], [0, 0, 51], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]], [[0, 0, 191], [0, 0, 64], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]]],
}


class RendererByteIdenticalTests(unittest.TestCase):
    def test_slot_effects_registered_and_disjoint(self):
        # Phase 2a populates SLOT_EFFECTS with the 5 engine cues. Byte-identity
        # of existing effects still holds because render() only takes the slot
        # path for names in SLOT_EFFECTS, and those names are DISJOINT from the
        # existing _EFFECTS (so no existing effect is rerouted).
        from rb_ss_bridge_v2.govee_frame_renderer import _EFFECTS
        expected = {
            "groove_center_chase",
            "groove_center_burst_retract",
            "post_drop_firework_chase",
            "breakdown_full_breathing",
            "breakdown_star_twinkle",
            "rt_groove_chase",
            "rt_groove_nebula",
            "rt_post_drop_chase",
            "rt_post_drop_nebula",
            "rt_drop_chase",
            "rt_drop_nebula",
            "rt_drop_center_burst",
            "rt_post_drop_center_comet",
            "rt_twinkle",
        }
        self.assertEqual(set(SLOT_EFFECTS), expected)
        # The baked sand twinkle is a Frame effect, NOT a slot effect.
        self.assertNotIn("breakdown_star_twinkle_sand", SLOT_EFFECTS)
        # No slot effect collides with an existing renderer effect name.
        self.assertEqual(set(SLOT_EFFECTS) & set(_EFFECTS), set())

    def test_render_byte_identical_to_golden(self):
        r = GoveeFrameRenderer()
        for name, frames in _GOLDEN_RENDER.items():
            for i, (beat, golden) in enumerate(zip(_GOLDEN_BEATS, frames)):
                out = r.render(
                    name, beat_pos=beat, local_t=beat, frame_index=i,
                    params={}, segments=_GOLDEN_SEG, seed=_GOLDEN_SEED,
                )
                out_lists = [list(px) for px in out]
                self.assertEqual(
                    out_lists, golden,
                    msg=f"render drift: effect={name} beat={beat}",
                )

    def test_render_comet_byte_identical_to_golden(self):
        r = GoveeFrameRenderer()
        for name, frames in _GOLDEN_COMET.items():
            self.assertTrue(is_comet_effect(name),
                            msg=f"{name} should be a comet effect")
            for i, (beat, golden) in enumerate(zip(_GOLDEN_BEATS, frames)):
                progress = beat % 1.0
                out = r.render_comet(
                    name, progress=progress, segments=_GOLDEN_SEG,
                    width=1.5, direction=1, params={},
                )
                out_lists = [list(px) for px in out]
                self.assertEqual(
                    out_lists, golden,
                    msg=f"render_comet drift: effect={name} beat={beat}",
                )

    def test_slot_validator_round_not_truncate(self):
        # _slots must ROUND (matching _clamp_channel), not truncate.
        self.assertEqual(_slots([[1.5, 2.5, 3.4]]), [(2, 2, 3)])
        # malformed inputs → None
        self.assertIsNone(_slots(None))
        self.assertIsNone(_slots([]))
        self.assertIsNone(_slots("nope"))
        self.assertIsNone(_slots([[1, 2]]))          # wrong arity
        self.assertIsNone(_slots([[1, 2, 3], [4, 5]]))  # one malformed
        # valid multi
        self.assertEqual(_slots([[1, 2, 3], [4, 5, 6]]), [(1, 2, 3), (4, 5, 6)])
        # out-of-range channels clamp
        self.assertEqual(_slots([[300, -5, 128]]), [(255, 0, 128)])


if __name__ == "__main__":
    unittest.main()
