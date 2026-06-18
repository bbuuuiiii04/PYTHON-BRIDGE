"""Tests for M2.5 Patch S: random_with_mono_chance slot fill."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    REALTIME_EFFECT_PARAM_KEYS,
    _M2_PHASE2A_PARAM_KEYS,
)
from rb_ss_bridge_v2.led_color_engine import (  # noqa: E402
    LedColorEngine,
    _blend_white,
    _p_to_rgb,
)
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette  # noqa: E402


_SCALE_STOPS = {
    "green": (0, 255, 0),
    "cyan": (0, 255, 255),
    "blue": (0, 0, 255),
    "purple": (160, 0, 255),
    "magenta": (255, 0, 160),
    "red": (255, 0, 0),
}


def _config(
    *,
    strategy: str = "random_with_mono_chance",
    chance: float = 0.0,
    role: str = "groove",
    look: str = "L",
    palette: Palette | None = None,
    step_within_section: dict[str, bool] | None = None,
    fade_beats_by_role: dict[str, float] | None = None,
) -> ColorEngineConfig:
    return ColorEngineConfig(
        enabled=True,
        scale_stops=dict(_SCALE_STOPS),
        palette_dwell_tracks=4,
        snap_eligible_drop_indices=(2, 3),
        big_shift_chance=0.0,
        big_shift_weight_bias=1.0,
        drama_by_role=False,
        role_spread={},
        step_within_section=(
            step_within_section
            if step_within_section is not None
            else {"drop": False, "post_drop": True, "groove": True, "ambient": False}
        ),
        fade_beats_by_role=(
            fade_beats_by_role
            if fade_beats_by_role is not None
            else {"drop": 0.0, "post_drop": 2.0, "groove": 2.0, "ambient": 4.0}
        ),
        slot_fill_strategy_by_look={look: strategy},
        slot_mono_chance_by_look={look: chance},
        palettes={
            "wide": palette
            if palette is not None
            else Palette(range=("cyan", "red"), white=0.0, spread=0.0, weight=1.0)
        },
        set_seed_mode="fixed:12345",
    )


def _engine(cfg: ColorEngineConfig) -> LedColorEngine:
    engine = LedColorEngine(cfg, set_seed=12345)
    engine.begin_dispatch(
        active_deck=1,
        load_gen=11,
        content_id="cid-patch-s",
        filepath="/tracks/patch-s.wav",
        role="groove",
        section_id="intro",
        cycle=0,
    )
    return engine


def _slot_colors(
    engine: LedColorEngine,
    *,
    role: str = "groove",
    section_id: str = "s1",
    cycle: int = 0,
    look_name: str = "L",
) -> list[tuple[int, int, int]]:
    return engine.resolve_slot_colors(
        role=role,
        section_id=section_id,
        cycle=cycle,
        look_name=look_name,
        color_source="engine",
        slot_count=99,
    )["slot_colors"]


def _is_mono(slots: list[tuple[int, int, int]]) -> bool:
    return len(slots) == 6 and len(set(slots[:5])) == 1 and slots[5] == (255, 255, 255)


class PatchSRandomWithMonoChanceTests(unittest.TestCase):
    def test_mono_one_yields_solid_first_five_slots_and_white_tail(self) -> None:
        slots = _slot_colors(_engine(_config(chance=1.0)))
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[5], (255, 255, 255))
        self.assertEqual(len(set(slots[:5])), 1)

    def test_mono_zero_matches_random_with_replacement_exactly(self) -> None:
        mono = _slot_colors(
            _engine(_config(strategy="random_with_mono_chance", chance=0.0))
        )
        random_fill = _slot_colors(
            _engine(_config(strategy="random_with_replacement", chance=0.0))
        )
        self.assertEqual(mono, random_fill)

    def test_intermediate_chance_produces_hits_and_misses(self) -> None:
        engine = _engine(_config(chance=0.5))
        saw_mono = False
        saw_non_mono = False
        for cycle in range(80):
            slots = _slot_colors(engine, section_id=f"s{cycle}", cycle=cycle)
            saw_mono = saw_mono or _is_mono(slots)
            saw_non_mono = saw_non_mono or not _is_mono(slots)
        self.assertTrue(saw_mono)
        self.assertTrue(saw_non_mono)

    def test_determinism_across_engine_instances(self) -> None:
        kwargs = dict(section_id="break-8", cycle=7, role="post_drop")
        cfg = _config(chance=1.0)
        self.assertEqual(
            _slot_colors(_engine(cfg), **kwargs),
            _slot_colors(_engine(cfg), **kwargs),
        )

    def test_step_within_section_controls_cycle_variation(self) -> None:
        stepped = _engine(_config(chance=1.0, step_within_section={"groove": True}))
        stepped_vectors = {
            tuple(_slot_colors(stepped, section_id="same", cycle=cycle))
            for cycle in range(8)
        }
        self.assertGreater(len(stepped_vectors), 1)

        unstepped = _engine(_config(chance=1.0, step_within_section={"groove": False}))
        unstepped_vectors = {
            tuple(_slot_colors(unstepped, section_id="same", cycle=cycle))
            for cycle in range(8)
        }
        self.assertEqual(len(unstepped_vectors), 1)

    def test_white_blend_applies_to_mono_hue(self) -> None:
        palette = Palette(range=("red", "red"), white=0.5, spread=0.0, weight=1.0)
        engine = _engine(_config(chance=1.0, palette=palette))
        slots = _slot_colors(engine)
        raw = _p_to_rgb(1.0, engine._config.scale_stops, engine._stop_positions)
        expected = _blend_white(raw, palette.white)
        self.assertEqual(slots[:5], [expected] * 5)
        self.assertNotEqual(expected, raw)

    def test_degenerate_focus_still_solid_for_random_fill(self) -> None:
        palette = Palette(range=("red", "red"), white=0.0, spread=0.0, weight=1.0)
        random_fill = _slot_colors(
            _engine(_config(strategy="random_with_replacement", chance=0.0, palette=palette))
        )
        mono_miss = _slot_colors(
            _engine(_config(strategy="random_with_mono_chance", chance=0.0, palette=palette))
        )
        self.assertTrue(_is_mono(random_fill))
        self.assertTrue(_is_mono(mono_miss))
        self.assertEqual(random_fill, mono_miss)

    def test_fade_tail_applies_without_changing_drop_zero_fade_behavior(self) -> None:
        drop_engine = _engine(_config(chance=1.0, role="drop", fade_beats_by_role={"drop": 0.0}))
        drop_engine.resolve_slot_colors(
            role="drop", section_id="drop-a", cycle=0, look_name="L", color_source="engine"
        )
        drop_second = drop_engine.resolve_slot_colors(
            role="drop", section_id="drop-a", cycle=1, look_name="L", color_source="engine"
        )
        self.assertIn("slot_colors_from", drop_second)
        self.assertIn("slot_colors_to", drop_second)
        self.assertNotIn("fade_beats", drop_second)

        post_engine = _engine(_config(chance=1.0, role="post_drop"))
        post_engine.resolve_slot_colors(
            role="post_drop", section_id="post-a", cycle=0, look_name="L", color_source="engine"
        )
        post_second = post_engine.resolve_slot_colors(
            role="post_drop", section_id="post-a", cycle=1, look_name="L", color_source="engine"
        )
        self.assertIn("slot_colors_from", post_second)
        self.assertIn("slot_colors_to", post_second)
        self.assertEqual(post_second["fade_beats"], 2.0)

    def test_journey_rng_untouched_by_mono_slot_resolution(self) -> None:
        engine = _engine(_config(chance=1.0))
        before = engine._journey_rng.getstate()
        _slot_colors(engine)
        after = engine._journey_rng.getstate()
        self.assertEqual(before, after)

    def test_unknown_strategy_fails_safe_to_gradient(self) -> None:
        cfg = _config(strategy="weighted_random", chance=1.0)
        fallback = _slot_colors(_engine(cfg))
        gradient = _slot_colors(_engine(_config(strategy="gradient_even", chance=0.0)))
        self.assertEqual(fallback, gradient)
        self.assertEqual(len(fallback), 6)
        self.assertEqual(fallback[5], (255, 255, 255))

    def test_slot_colors_is_not_static_allowlisted(self) -> None:
        for keys in _M2_PHASE2A_PARAM_KEYS.values():
            self.assertNotIn("slot_colors", keys)
        for keys in REALTIME_EFFECT_PARAM_KEYS.values():
            self.assertNotIn("slot_colors", keys)

    def test_gradient_even_golden_vector_unchanged(self) -> None:
        palette = Palette(range=("cyan", "blue"), white=0.0, spread=0.0, weight=1.0)
        slots = _slot_colors(_engine(_config(strategy="gradient_even", palette=palette)))
        self.assertEqual(
            slots,
            [
                (0, 255, 255),
                (0, 191, 255),
                (0, 127, 255),
                (0, 64, 255),
                (0, 0, 255),
                (255, 255, 255),
            ],
        )


if __name__ == "__main__":
    unittest.main()
