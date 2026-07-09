"""Tests for M2.5 Patch D: Slotize drop chase and center burst."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    _EFFECTS,
    MAX_SLOTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    _M2_PHASE2A_PARAM_KEYS,
    _slot_drop_center_burst,
    _slot_drop_chase,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402


def _used_slots(field: list[list[float]]) -> set[int]:
    out: set[int] = set()
    for row in field:
        for slot_idx, intensity in enumerate(row):
            if intensity > 0.0:
                out.add(slot_idx)
    return out


class PatchDTests(unittest.TestCase):
    def _drop_chase(self, beat: float, *, segments: int = 36, frame_index: int = 0):
        return _slot_drop_chase(
            beat=beat,
            local_t=0.0,
            frame_index=frame_index,
            params={},
            segments=segments,
            seed=42,
        )

    def _center_burst(self, beat: float, *, segments: int = 36):
        return _slot_drop_center_burst(
            beat=beat,
            local_t=0.0,
            frame_index=0,
            params={},
            segments=segments,
            seed=42,
        )

    def test_both_slot_functions_return_segments_x_6(self) -> None:
        for fn in (self._drop_chase, self._center_burst):
            for beat in (0.0, 0.5, 1.5, 8.0, 12.25):
                field = fn(beat, segments=24)
                self.assertEqual(len(field), 24)
                for row in field:
                    self.assertEqual(len(row), MAX_SLOTS)

    def test_drop_chase_uses_slots_0_to_4_and_never_slot_5(self) -> None:
        used: set[int] = set()
        for tick in range(640):
            field = self._drop_chase(tick / 20.0, segments=36, frame_index=tick)
            used.update(_used_slots(field))
            for row in field:
                self.assertEqual(row[5], 0.0)
        for expected_slot in range(5):
            self.assertIn(expected_slot, used)
        self.assertNotIn(5, used)

    def test_center_burst_uses_slots_0_to_4_and_never_slot_5(self) -> None:
        used: set[int] = set()
        for tick in range(320):
            field = self._center_burst(tick / 40.0, segments=36)
            used.update(_used_slots(field))
            for row in field:
                self.assertEqual(row[5], 0.0)
        for expected_slot in range(5):
            self.assertIn(expected_slot, used)
        self.assertNotIn(5, used)

    def test_drop_chase_strobe_off_frames_are_dark(self) -> None:
        field = self._drop_chase(beat=0.07, segments=24)
        self.assertTrue(all(all(value == 0.0 for value in row) for row in field))

    def test_drop_chase_has_sparkle_intro_and_comet_phase(self) -> None:
        sparkle_used: set[int] = set()
        for tick in range(80):
            sparkle_used.update(_used_slots(self._drop_chase(tick / 20.0, segments=12, frame_index=tick)))
        self.assertTrue(sparkle_used & set(range(5)))

        comet = self._drop_chase(8.0, segments=36, frame_index=0)
        self.assertTrue(_used_slots(comet) & set(range(5)))

    def test_center_burst_preserves_even_pixels_only(self) -> None:
        for tick in range(320):
            field = self._center_burst(tick / 40.0, segments=36)
            for idx in range(1, len(field), 2):
                self.assertTrue(all(value == 0.0 for value in field[idx]))

    def test_center_burst_main_and_accent_band_split(self) -> None:
        # AWR-156 knob #4: the intra-burst hue sweep died -- a burst is now
        # ONE fixed slot for its whole pulse (main: burst_idx % 3 in slots
        # 0-2; accent: 2 + burst_idx % 3 in slots 2-4), not an intensity-swept
        # gradient. Sweep a wide beat range and bucket by is_accent (mirrors
        # the renderer's own burst_idx % 4 == 3 rule) so the assertions stay
        # independent of any particular hand-picked beat.
        main_slots: set[int] = set()
        accent_slots: set[int] = set()
        for tick in range(320):
            beat = tick / 40.0
            used = _used_slots(self._center_burst(beat, segments=36))
            burst_idx = int((beat % 8.0) * 2.0)
            if burst_idx % 4 == 3:
                accent_slots.update(used)
            else:
                main_slots.update(used)
        self.assertTrue({0, 1, 2}.issubset(main_slots))
        self.assertFalse(main_slots & {3, 4, 5})
        self.assertTrue({2, 3, 4}.issubset(accent_slots))
        self.assertFalse(accent_slots & {0, 1, 5})

    def test_patch_d_registrations(self) -> None:
        for name in ("rt_drop_chase", "rt_drop_center_burst"):
            self.assertIn(name, SLOT_EFFECTS)
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            keys = _M2_PHASE2A_PARAM_KEYS.get(name, frozenset())
            all_keys = REALTIME_EFFECT_PARAM_KEYS.get(name, frozenset())
            self.assertNotIn("slot_colors", keys)
            self.assertNotIn("slot_colors", all_keys)
        self.assertIn("rt_drop_chase", REALTIME_STROBE_EFFECTS)
        self.assertNotIn("rt_drop_center_burst", REALTIME_STROBE_EFFECTS)

    def test_legacy_drop_names_still_resolve(self) -> None:
        legacy_names = [
            "drop_chase_blue",
            "drop_chase_cyan",
            "drop_chase_red",
            "drop_chase_green",
            "drop_chase_cyan_white",
            "drop_center_burst_blue_cyan",
        ]
        for name in legacy_names:
            self.assertIn(name, REALTIME_EFFECT_NAMES)
            self.assertIn(name, _EFFECTS)

    def test_tracked_and_live_configs_validate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        # AWR-156: rt_drop_chase got a role-scoped width param (knob #9), and
        # was renamed to rt_post_drop_remnant_chase + moved drop -> post_drop
        # (bank recast, knob f, T6.4 amended to a rename) in the TRACKED
        # example config only; the live config is gitignored/read-only and
        # renders identically to today (old look name, old bank, no width)
        # until the operator mirrors it in. scene_ref stays rt_drop_chase
        # either way. rt_drop_center_burst is untouched by all of this.
        expected_by_rel = {
            "config/led_look_director.example.json": {
                "rt_post_drop_remnant_chase": ("rt_drop_chase", {"width": 4}, "post_drop"),
                "rt_drop_center_burst": ("rt_drop_center_burst", {}, "drop"),
            },
            "config/led_look_director.json": {
                "rt_drop_chase": ("rt_drop_chase", {}, "drop"),
                "rt_drop_center_burst": ("rt_drop_center_burst", {}, "drop"),
            },
        }
        for rel in ("config/led_look_director.example.json", "config/led_look_director.json"):
            cfg_path = root / rel
            if not cfg_path.exists():
                # Live config is gitignored / local-only; absent on CI. The
                # tracked example.json above still exercises validation.
                continue
            result = load_led_look_director_config(str(cfg_path))
            self.assertEqual(tuple(result.errors), (), f"{rel}: {result.errors}")
            for name, (scene_ref, params, role) in expected_by_rel[rel].items():
                self.assertIn(name, result.config.looks)
                look = result.config.looks[name]
                self.assertEqual(look.scene_ref, scene_ref)
                self.assertEqual(look.color_source, "engine")
                self.assertEqual(look.params, params, msg=f"{rel}:{name}")
                self.assertEqual(look.safety_class, "drop")
                self.assertIn(name, getattr(result.config.banks["default"], role), msg=f"{rel}:{name}")

    def test_drop_slot_color_smoke_and_snap(self) -> None:
        root = Path(__file__).resolve().parents[1]
        live = root / "config/led_look_director.json"
        if not live.exists():
            self.skipTest("live LED config not present (gitignored; local-only)")
        result = load_led_look_director_config(str(live))
        self.assertEqual(tuple(result.errors), ())
        self.assertFalse(result.config.color_engine.step_within_section.get("drop", True))
        self.assertEqual(result.config.color_engine.fade_beats_by_role.get("drop"), 0.0)

        for name in ("rt_drop_chase", "rt_drop_center_burst"):
            engine = LedColorEngine(result.config.color_engine, set_seed=123)
            engine.begin_dispatch(
                active_deck=1,
                load_gen=7,
                content_id=f"patch-d-{name}",
                filepath=f"/tracks/patch-d-{name}.wav",
                role="drop",
                section_id="drop-1",
                cycle=0,
            )
            first = engine.resolve_slot_colors(
                role="drop",
                section_id="drop-1",
                cycle=0,
                look_name=name,
                color_source="engine",
            )
            second = engine.resolve_slot_colors(
                role="drop",
                section_id="drop-1",
                cycle=1,
                look_name=name,
                color_source="engine",
            )
            slots = first["slot_colors"]
            self.assertEqual(len(slots), MAX_SLOTS)
            self.assertEqual(slots[5], (255, 255, 255))
            self.assertGreater(len(set(slots[:5])), 1)
            self.assertEqual(second["slot_colors_from"], second["slot_colors_to"])
            self.assertNotIn("fade_beats", second)


if __name__ == "__main__":
    unittest.main()
