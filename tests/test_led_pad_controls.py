from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import govee_frame_renderer  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
)
from rb_ss_bridge_v2.govee_realtime_runner import _COLOR_SIG_KEYS  # noqa: E402
from rb_ss_bridge_v2.led_pad_controls import (  # noqa: E402
    CONTROL_META,
    PARAM_DEFAULT_OVERRIDES,
    controls_for,
    render_catalog,
)


class LedPadControlsTests(unittest.TestCase):
    def test_catalog_covers_every_realtime_render(self) -> None:
        catalog = render_catalog()
        names = {item["name"] for item in catalog}

        self.assertEqual(names, set(REALTIME_EFFECT_NAMES))

    def test_every_allowlisted_key_has_metadata(self) -> None:
        keys = set().union(*REALTIME_EFFECT_PARAM_KEYS.values())

        self.assertTrue(keys)
        self.assertEqual(keys, set(CONTROL_META))
        for scene_ref, allowed in REALTIME_EFFECT_PARAM_KEYS.items():
            control_keys = {item["key"] for item in controls_for(scene_ref)}
            self.assertEqual(control_keys, set(allowed))

    def test_strobe_and_slot_flags_match_renderer_sets(self) -> None:
        catalog = {item["name"]: item for item in render_catalog()}

        for name in REALTIME_EFFECT_NAMES:
            self.assertEqual(catalog[name]["slot_based"], name in SLOT_EFFECTS)
            self.assertEqual(catalog[name]["strobe"], name in REALTIME_STROBE_EFFECTS)

    def test_color_sig_metadata_matches_runner_signature_keys(self) -> None:
        flagged = {key for key, meta in CONTROL_META.items() if meta["color_sig"]}

        self.assertEqual(flagged, set(CONTROL_META) & set(_COLOR_SIG_KEYS))


class LedPadControlDefaultsTests(unittest.TestCase):
    """Guards CONTROL_META["default"] against drift.

    govee_frame_renderer.py has no defaults registry, so these defaults were
    hand-extracted from literal `params.get(key, DEFAULT)` fallbacks (full
    per-key/per-line audit table: docs/guides/led_pad.md). This pins both (a)
    every non-rgb control shipping an in-range default, and (b) the exact
    hand-extracted literals against the renderer source text, so an
    unrelated future edit to a fallback value in govee_frame_renderer.py
    fails this test instead of silently drifting from the pad UI.
    """

    def test_every_non_rgb_control_has_default_present_and_in_range(self) -> None:
        for scene_ref in REALTIME_EFFECT_NAMES:
            for control in controls_for(scene_ref):
                if control["kind"] == "rgb":
                    continue
                self.assertIn("default", control, control["key"])
                default = control["default"]
                if default is None:
                    continue
                if control["kind"] in ("number", "int") and control["min"] is not None and control["max"] is not None:
                    self.assertGreaterEqual(default, control["min"], control["key"])
                    self.assertLessEqual(default, control["max"], control["key"])
                if control["kind"] == "choice" and control["choices"]:
                    self.assertIn(default, control["choices"], control["key"])

    def test_hand_extracted_defaults_match_renderer_source_literals(self) -> None:
        source = Path(govee_frame_renderer.__file__).read_text()
        expected_literals = [
            'params.get("trail", 3)',
            'params.get("span_beats", 1.0)',
            'params.get("subdivision", 4)',
            'params.get("duty", 0.5)',
            'params.get("decay", 0.6)',
            'params.get("period_beats", 4.0)',
            'params.get("floor", 0.1)',
            'params.get("speed", 1.0)',
            'params.get("density", 0.2)',
            'params.get("duration_beats", _EDM_DURATION_BEATS)',
            'params.get("loop_beats", 4.0)',
            "params.get('burst_beats', 1.0)",
            "params.get('breath_beats', 8.0)",
            "params.get('drift_beats', 32.0)",
            'params.get("travel_beats", 1.0)',
            'params.get("travel_beats", 2.0)',
            'params.get("width", 0.8)',
            # AWR-156 additions.
            'params.get("hz", 6.0)',
            'params.get("duty", 0.3)',
            'params.get("start_width", 4.0)',
            'params.get("end_width", 1.0)',
            'params.get("build_beats", 16.0)',
            'params.get("dim_floor", 0.35)',
            'params.get("base_width", 1.5)',
            'params.get("pulse_width", 3.0)',
            'params.get("color_mode", 2)',
            'params.get("dim_beats", 8.0)',
            'params.get("ember_hold_beats", 8.0)',
            'params.get("ember_decay_beats", 2.0)',
            'params.get("sparkle_density", 0.35)',
            'params.get("sparkle_size", 1.0)',
            'params.get("sparkle_life_s", 0.8)',
            # AWR-191 wiring audit — AWR-187's drop_firework_explosion_2
            # divergent fallbacks (PARAM_DEFAULT_OVERRIDES rows, v1 keeps the
            # CONTROL_META globals above).
            'params.get("surge_beats", 0.25)',
            'params.get("bg_hold", 0.25)',
            'params.get("sparkle_density", 0.5)',
            'params.get("sparkle_life_s", 0.15)',
            # AWR-191 wiring audit — AWR-188's palette_comet (single global
            # default, same shape as rainbow_span).
            'params.get("palette_span", 1.0)',
        ]
        for literal in expected_literals:
            self.assertIn(literal, source, literal)
        self.assertEqual(govee_frame_renderer._EDM_DURATION_BEATS, 32.0)
        self.assertEqual(govee_frame_renderer.default_beat_division("anything"), 1.0)
        self.assertEqual(govee_frame_renderer.default_sync_mode("groove_chase_blue"), "overlap")
        self.assertEqual(govee_frame_renderer.default_sync_mode("beat_chase"), "retrigger")
        self.assertEqual(govee_frame_renderer.default_sync_mode("solid"), "continuous")

        # CONTROL_META values must match these literals exactly - no invented numbers.
        self.assertEqual(CONTROL_META["trail"]["default"], 3)
        self.assertEqual(CONTROL_META["span_beats"]["default"], 1.0)
        self.assertEqual(CONTROL_META["subdivision"]["default"], 4)
        self.assertEqual(CONTROL_META["duty"]["default"], 0.5)
        self.assertEqual(CONTROL_META["decay"]["default"], 0.6)
        self.assertEqual(CONTROL_META["period_beats"]["default"], 4.0)
        self.assertEqual(CONTROL_META["floor"]["default"], 0.1)
        self.assertEqual(CONTROL_META["speed"]["default"], 1.0)
        self.assertEqual(CONTROL_META["density"]["default"], 0.2)
        self.assertEqual(CONTROL_META["duration_beats"]["default"], 32.0)
        self.assertEqual(CONTROL_META["loop_beats"]["default"], 4.0)
        self.assertEqual(CONTROL_META["burst_beats"]["default"], 1.0)
        self.assertEqual(CONTROL_META["breath_beats"]["default"], 8.0)
        self.assertEqual(CONTROL_META["drift_beats"]["default"], 32.0)
        self.assertEqual(CONTROL_META["beat_division"]["default"], 1.0)
        # AWR-156 additions: single global default (shared by every scene_ref
        # that reads the key).
        self.assertEqual(CONTROL_META["hz"]["default"], 6.0)
        self.assertEqual(CONTROL_META["start_width"]["default"], 4.0)
        self.assertEqual(CONTROL_META["end_width"]["default"], 1.0)
        self.assertEqual(CONTROL_META["build_beats"]["default"], 16.0)
        self.assertEqual(CONTROL_META["dim_floor"]["default"], 0.35)
        self.assertEqual(CONTROL_META["base_width"]["default"], 1.5)
        self.assertEqual(CONTROL_META["pulse_width"]["default"], 3.0)
        self.assertEqual(CONTROL_META["color_mode"]["default"], 2)
        self.assertEqual(CONTROL_META["dim_beats"]["default"], 8.0)
        self.assertEqual(CONTROL_META["ember_hold_beats"]["default"], 8.0)
        self.assertEqual(CONTROL_META["ember_decay_beats"]["default"], 2.0)
        self.assertEqual(CONTROL_META["sparkle_density"]["default"], 0.35)
        self.assertEqual(CONTROL_META["sparkle_size"]["default"], 1.0)
        self.assertEqual(CONTROL_META["sparkle_life_s"]["default"], 0.8)
        # AWR-191: palette_comet's one new key (AWR-188).
        self.assertEqual(CONTROL_META["palette_span"]["default"], 1.0)

        # Divergent-by-scene or never-read-from-params keys: no single global
        # default exists, so the catalog must say "auto" (None), not guess.
        for null_key in ("travel_beats", "width", "trail_beats", "sync_mode"):
            self.assertIsNone(CONTROL_META[null_key]["default"], null_key)

        # Confirmed dead keys: never consumed by any params.get in this file.
        for dead_key in ("heads", "max_pulses", "spawn_on_wrap", "reverse"):
            self.assertIsNone(CONTROL_META[dead_key]["default"], dead_key)
            self.assertNotIn(f'params.get("{dead_key}"', source, dead_key)
            self.assertNotIn(f"params.get('{dead_key}'", source, dead_key)

    def test_travel_beats_and_width_overrides_match_source_literals(self) -> None:
        expected = {
            "groove_center_chase": {"travel_beats": 1.0},
            "post_drop_firework_chase": {"travel_beats": 1.0},
            "rt_post_drop_chase": {"travel_beats": 2.0, "width": 0.8},
            "rt_post_drop_nebula": {"travel_beats": 2.0, "width": 0.8},
            "rt_drop_chase": {"travel_beats": 2.0, "width": 0.8},
            "rt_drop_nebula": {"travel_beats": 2.0, "width": 0.8},
            # AWR-156: the Hz gate's duty fallback (0.3) differs from
            # beat_strobe's (0.5, the global CONTROL_META default).
            "drop_white_aggressive": {"duty": 0.3},
            "drop_strobe_colorway": {"duty": 0.3},
            # AWR-187: the redesigned firework's fallbacks diverge from v1's
            # (which set the CONTROL_META globals).
            "drop_firework_explosion_2": {
                "surge_beats": 0.25, "bg_hold": 0.25, "sparkle_density": 0.5,
                "sparkle_life_s": 0.15, "duty": 0.3,
            },
        }
        self.assertEqual(PARAM_DEFAULT_OVERRIDES, expected)
        for scene_ref, overrides in expected.items():
            controls = {item["key"]: item for item in controls_for(scene_ref)}
            for key, value in overrides.items():
                self.assertEqual(controls[key]["default"], value, f"{scene_ref}.{key}")


if __name__ == "__main__":
    unittest.main()
