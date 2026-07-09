"""Tests for M2.5 Patch E1: Nebula family slot cues.

Covers:
- _slot_groove_nebula unit tests (shape, multi-slot, slot-5-zero, no-strobe-gate, opposing heads)
- _slot_drop_nebula and _slot_post_drop_nebula unit tests (shape, strobe gate, slot-5 white)
- Config: rt_groove_nebula, rt_drop_nebula, rt_post_drop_nebula look definitions
- Slot smoke: resolve_slot_colors for the three Patch E1 looks
- Scene-ref verification: all Patch E1 look scene_refs point to registered SLOT_EFFECTS
- Regression: 9 original SLOT_EFFECTS keys still present; E1 entries remain after later E patches
- Legacy nebula looks still in exempt_looks; legacy scene_refs still in _EFFECTS
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    MAX_SLOTS,
    REALTIME_EFFECT_NAMES,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    _EFFECTS,
    _M2_PHASE2A_PARAM_KEYS,
    _slot_drop_nebula,
    _slot_groove_nebula,
    _slot_post_drop_nebula,
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


def _call_groove_nebula(beat: float, *, segments: int = 60, frame_index: int = 0,
                        params: dict | None = None) -> list[list[float]]:
    return _slot_groove_nebula(
        beat=beat,
        local_t=0.0,
        frame_index=frame_index,
        params=params or {},
        segments=segments,
        seed=42,
    )


def _call_drop_nebula(beat: float, *, segments: int = 60, frame_index: int = 0,
                      params: dict | None = None) -> list[list[float]]:
    return _slot_drop_nebula(
        beat=beat,
        local_t=0.0,
        frame_index=frame_index,
        params=params or {},
        segments=segments,
        seed=42,
    )


def _call_post_drop_nebula(beat: float, *, segments: int = 60, frame_index: int = 0,
                           params: dict | None = None) -> list[list[float]]:
    return _slot_post_drop_nebula(
        beat=beat,
        local_t=0.0,
        frame_index=frame_index,
        params=params or {},
        segments=segments,
        seed=42,
    )


class SlotGrooveNebulaUnitTests(unittest.TestCase):
    """Unit tests for _slot_groove_nebula."""

    def test_shape_segments_x_6(self) -> None:
        """Returns MotionField of shape segments × 6."""
        for beat in (0.0, 0.5, 1.0, 2.0, 4.0):
            field = _call_groove_nebula(beat, segments=60)
            self.assertEqual(len(field), 60, f"outer length at beat={beat}")
            for row in field:
                self.assertEqual(len(row), MAX_SLOTS, f"inner length at beat={beat}")

    def test_slot_5_always_zero(self) -> None:
        """Slot 5 (white-burst reserved slot) is always 0.0."""
        for beat in (0.0, 0.125, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 3.99):
            field = _call_groove_nebula(beat, segments=60)
            for idx in range(60):
                self.assertEqual(
                    field[idx][5], 0.0,
                    f"slot 5 nonzero at beat={beat}, segment={idx}"
                )

    def test_multi_slot_use_at_fractional_beat(self) -> None:
        """At a fractional beat (e.g. 0.5), intensity is spread across multiple slot indices.

        At beat=0.5, pos1=7.5 and pos2=52.5. Pixels adjacent to those positions
        have intensities < 1.0, which map to slots 1 and 2 via slot_coord interpolation.
        """
        field = _call_groove_nebula(beat=0.5, segments=60)
        used = _used_slots(field)
        # Should activate at least 2 distinct slots from 0-4
        self.assertGreater(
            len(used & set(range(5))), 1,
            f"Expected multi-slot use at beat=0.5, got slots={sorted(used)}"
        )
        # Slot 5 must still be zero
        self.assertNotIn(5, used)

    def test_slot_5_zero_over_many_beats(self) -> None:
        """Slot 5 never receives intensity across a sweep of beats."""
        for tick in range(400):
            beat = tick / 50.0
            field = _call_groove_nebula(beat, segments=36, frame_index=tick)
            for idx in range(36):
                self.assertEqual(field[idx][5], 0.0,
                                 f"slot 5 nonzero at beat={beat:.3f}, segment={idx}")

    def test_no_strobe_gate(self) -> None:
        """_slot_groove_nebula has NO strobe gate.

        At beat=0.0625 (which is a strobe-off beat for 16th-note gating),
        the function must return a non-zero field because it has no strobe gate.
        """
        # beat=0.0625 → int(0.0625 * 16) % 2 == 1 → strobe-off for drop/post_drop fns
        field = _call_groove_nebula(beat=0.0625, segments=60)
        total = sum(field[idx][s] for idx in range(60) for s in range(5))
        self.assertGreater(total, 0.0,
                           "Expected nonzero output at beat=0.0625 (no strobe gate)")

    def test_opposing_direction_heads_diverge(self) -> None:
        """At beat=1.0, the two opposing heads are at separate segment positions.

        pos1 = 0.25 * 60 = 15.0 (forward head)
        pos2 = 0.75 * 60 = 45.0 (reverse head)
        Both contribute intensity to segment groups 30 apart on the ring.
        """
        field = _call_groove_nebula(beat=1.0, segments=60)

        # Collect nonzero segment indices
        active_segments = [idx for idx in range(60)
                           if any(field[idx][s] > 0.0 for s in range(5))]
        self.assertGreater(len(active_segments), 0, "No active segments at beat=1.0")

        # The two heads should be far apart: one near idx=15, one near idx=45
        # Check there are active segments in BOTH halves of the ring
        lower_half = [idx for idx in active_segments if idx < 30]
        upper_half = [idx for idx in active_segments if idx >= 30]
        self.assertTrue(
            lower_half and upper_half,
            f"Heads did not diverge: active_segments={active_segments}; "
            f"expected segments in both halves (0-29 and 30-59)"
        )

    def test_slots_0_to_4_activated_over_sweep(self) -> None:
        """A long beat sweep activates slots 0 through 4 (not just one slot).

        AWR-156 knob #4: the mashup died -- a spawn is now ONE fixed palette
        slot for its whole loop_beats cycle (cycle = int(cue_beat/loop_beats),
        slot = cycle % 5), not an intensity-swept gradient. The sweep window
        widened from 8 beats to 40 beats (10 full loop_beats cycles) so all 5
        cycle-derived slots still appear.
        """
        used: set[int] = set()
        for tick in range(1000):
            beat = tick / 25.0
            field = _call_groove_nebula(beat, segments=60, frame_index=tick)
            used.update(_used_slots(field))
        # Across all beats, all slots 0-4 should get hit at some point
        self.assertTrue(set(range(5)).issubset(used),
                        f"Expected slots 0-4 in sweep; got {sorted(used)}")
        self.assertNotIn(5, used, "Slot 5 should never be activated")


class SlotDropNebulaUnitTests(unittest.TestCase):
    """Unit tests for _slot_drop_nebula and _slot_post_drop_nebula."""

    def test_drop_nebula_shape_segments_x_6(self) -> None:
        field = _call_drop_nebula(beat=9.0, segments=60)
        self.assertEqual(len(field), 60)
        for row in field:
            self.assertEqual(len(row), MAX_SLOTS)

    def test_post_drop_nebula_shape_segments_x_6(self) -> None:
        field = _call_post_drop_nebula(beat=1.0, segments=60)
        self.assertEqual(len(field), 60)
        for row in field:
            self.assertEqual(len(row), MAX_SLOTS)

    def test_drop_nebula_strobe_gate_can_go_dark(self) -> None:
        # AWR-161: the strobe gate migrated to the wall-clock Hz gate
        # (_hz_strobe_on), driven by local_t not beat. Pin the real contract:
        # across one full strobe period at the reference hz 6.0 / duty 0.3
        # there must be BOTH lit frames and fully dark frames -- a strobe that
        # never goes dark is the exact bug this guards.
        cycle_s = 1.0 / 6.0
        params = {"hz": 6.0, "duty": 0.3}
        lit = dark = False
        for i in range(48):
            field = _slot_drop_nebula(
                beat=0.0625,
                local_t=cycle_s * i / 48.0,
                frame_index=i,
                params=params,
                segments=60,
                seed=42,
            )
            if sum(sum(row) for row in field) > 0.0:
                lit = True
            else:
                dark = True
        self.assertTrue(lit, "strobe never lit across a full period")
        self.assertTrue(dark, "strobe never went dark across a full period")

    def test_post_drop_nebula_strobe_gate_can_go_dark(self) -> None:
        # AWR-161: same Hz-gate contract as drop_nebula above -- sweep local_t
        # across one full 1/6 s period and require both lit and dark frames.
        cycle_s = 1.0 / 6.0
        params = {"hz": 6.0, "duty": 0.3}
        lit = dark = False
        for i in range(48):
            field = _slot_post_drop_nebula(
                beat=0.0625,
                local_t=cycle_s * i / 48.0,
                frame_index=i,
                params=params,
                segments=60,
                seed=42,
            )
            if sum(sum(row) for row in field) > 0.0:
                lit = True
            else:
                dark = True
        self.assertTrue(lit, "strobe never lit across a full period")
        self.assertTrue(dark, "strobe never went dark across a full period")

    def test_drop_nebula_comet_phase_uses_palette_and_white_slots(self) -> None:
        field = _call_drop_nebula(beat=9.0, segments=60)
        used = _used_slots(field)
        self.assertTrue(used & set(range(5)), f"no palette slots used: {sorted(used)}")
        self.assertIn(5, used, "white comet should use slot 5")

    def test_post_drop_nebula_uses_palette_and_white_slots(self) -> None:
        field = _call_post_drop_nebula(beat=1.0, segments=60)
        used = _used_slots(field)
        self.assertTrue(used & set(range(5)), f"no palette slots used: {sorted(used)}")
        self.assertIn(5, used, "white comet should use slot 5")


class PatchE1ConfigTests(unittest.TestCase):
    """Config validation and look-attribute tests for Patch E1."""

    def _load_config(self, rel: str):
        root = Path(__file__).resolve().parents[1]
        return load_led_look_director_config(str(root / rel))

    def test_rt_groove_nebula_look_example(self) -> None:
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), (), f"example config errors: {result.errors}")
        look = result.config.looks.get("rt_groove_nebula")
        self.assertIsNotNone(look, "rt_groove_nebula missing from example config")
        self.assertEqual(look.scene_ref, "rt_groove_nebula")
        self.assertEqual(look.color_source, "engine")
        self.assertFalse(look.allow_strobe)
        self.assertEqual(look.safety_class, "groove")

    def test_rt_drop_nebula_look_example(self) -> None:
        # AWR-156 T6.4 amendment: renamed to rt_post_drop_remnant_nebula
        # (LOOK-name rename only; scene_ref stays rt_drop_nebula).
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        look = result.config.looks.get("rt_post_drop_remnant_nebula")
        self.assertIsNotNone(look, "rt_post_drop_remnant_nebula missing from example config")
        self.assertEqual(look.scene_ref, "rt_drop_nebula")
        self.assertEqual(look.color_source, "engine")
        self.assertTrue(look.allow_strobe)
        self.assertEqual(look.safety_class, "drop")
        self.assertIsNone(result.config.looks.get("rt_drop_nebula"))

    def test_rt_post_drop_nebula_look_example(self) -> None:
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        look = result.config.looks.get("rt_post_drop_nebula")
        self.assertIsNotNone(look, "rt_post_drop_nebula missing from example config")
        self.assertEqual(look.scene_ref, "rt_post_drop_nebula")
        self.assertEqual(look.color_source, "engine")
        self.assertTrue(look.allow_strobe)
        self.assertEqual(look.safety_class, "post_drop")

    def test_both_nebula_configs_validate_with_zero_errors(self) -> None:
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), (), f"example config errors: {result.errors}")

    def test_new_looks_in_bank_rotations(self) -> None:
        """New looks appear in the correct bank rotation arrays."""
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        bank = result.config.banks.get("default")
        self.assertIsNotNone(bank)
        self.assertIn("rt_groove_nebula", bank.groove)
        # AWR-156 bank recast (f), T6.4 amended (rename not just move):
        # rt_drop_nebula moved drop -> post_drop AND renamed to
        # rt_post_drop_remnant_nebula ("current sparkling cues can play the
        # role of the sparkling remnants"); scene_ref stays rt_drop_nebula.
        self.assertIn("rt_post_drop_remnant_nebula", bank.post_drop)
        self.assertNotIn("rt_drop_nebula", bank.drop)
        self.assertNotIn("rt_post_drop_remnant_nebula", bank.drop)
        self.assertIn("rt_post_drop_nebula", bank.post_drop)

    def test_drop_nebula_pairs_to_post_drop_nebula(self) -> None:
        # AWR-156 bank recast (f): a post_drop-role look never fires a pair,
        # so rt_drop_nebula's drop_pairs entry was removed.
        result = self._load_config("config/led_look_director.example.json")
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        self.assertIsNone(result.config.drop_pairs.get("rt_drop_nebula"))
        self.assertIsNone(result.config.drop_pairs.get("rt_post_drop_remnant_nebula"))


class PatchE1SlotSmokeTests(unittest.TestCase):
    """Per-cue slot smoke tests."""

    def _load_config(self):
        root = Path(__file__).resolve().parents[1]
        return load_led_look_director_config(str(root / "config/led_look_director.example.json"))

    def test_patch_e1_looks_slot_smoke(self) -> None:
        """resolve_slot_colors for Patch E1 looks returns 6 slots with slot[5] pure white."""
        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())

        for look_name, role in (
            ("rt_groove_nebula", "groove"),
            ("rt_drop_nebula", "drop"),
            ("rt_post_drop_nebula", "post_drop"),
        ):
            engine = LedColorEngine(result.config.color_engine, set_seed=123)
            engine.begin_dispatch(
                active_deck=1,
                load_gen=7,
                content_id=f"patch-e1-{look_name}",
                filepath=f"/tracks/patch-e1-{look_name}.wav",
                role=role,
                section_id=f"{role}-1",
                cycle=0,
            )
            resolved = engine.resolve_slot_colors(
                role=role,
                section_id=f"{role}-1",
                cycle=0,
                look_name=look_name,
                color_source="engine",
            )
            slots = resolved["slot_colors"]
            self.assertEqual(len(slots), MAX_SLOTS, look_name)
            self.assertEqual(slots[5], (255, 255, 255), look_name)
            for i, rgb in enumerate(slots[:5]):
                self.assertEqual(len(rgb), 3, f"{look_name} slot {i}: {rgb}")
                for ch in rgb:
                    self.assertGreaterEqual(ch, 0)
                    self.assertLessEqual(ch, 255)

    def test_patch_e1_scene_refs_are_registered_in_slot_effects(self) -> None:
        """All Patch E1 look scene_refs must be registered in SLOT_EFFECTS."""
        result = self._load_config()
        self.assertTrue(result.available, f"config not available: {result.reason}")
        for look_name in ("rt_groove_nebula", "rt_post_drop_nebula"):
            scene_ref = result.config.looks[look_name].scene_ref
            self.assertEqual(scene_ref, look_name)
            self.assertIn(scene_ref, SLOT_EFFECTS)
        # AWR-156 T6.4 amendment: rt_drop_nebula was renamed to
        # rt_post_drop_remnant_nebula (LOOK-name rename only), so its
        # scene_ref no longer matches its look name.
        scene_ref = result.config.looks["rt_post_drop_remnant_nebula"].scene_ref
        self.assertEqual(scene_ref, "rt_drop_nebula")
        self.assertIn(scene_ref, SLOT_EFFECTS)


class PatchE1RegressionTests(unittest.TestCase):
    """Regression tests: original entries unchanged, legacy looks still resolve."""

    _ORIGINAL_SLOT_EFFECT_KEYS = frozenset({
        "rt_groove_chase",
        "rt_post_drop_chase",
        "rt_drop_chase",
        "rt_drop_center_burst",
        "groove_center_chase",
        "groove_center_burst_retract",
        "post_drop_firework_chase",
        "breakdown_full_breathing",
        "breakdown_star_twinkle",
    })

    def test_original_9_slot_effects_still_present(self) -> None:
        for key in self._ORIGINAL_SLOT_EFFECT_KEYS:
            self.assertIn(key, SLOT_EFFECTS, f"{key} missing from SLOT_EFFECTS")

    def test_slot_effects_preserves_e1_entries_after_later_patches(self) -> None:
        # AWR-156 added rt_groove_heartbeat + rt_post_drop_firework_remnants.
        self.assertEqual(
            len(SLOT_EFFECTS), 16,
            f"Expected 16 SLOT_EFFECTS after AWR-156, got {len(SLOT_EFFECTS)}: "
            f"{sorted(SLOT_EFFECTS.keys())}"
        )

    def test_patch_e1_looks_in_slot_effects(self) -> None:
        for name in ("rt_groove_nebula", "rt_drop_nebula", "rt_post_drop_nebula"):
            self.assertIn(name, SLOT_EFFECTS)

    def test_patch_e1_looks_in_realtime_effect_names(self) -> None:
        for name in ("rt_groove_nebula", "rt_drop_nebula", "rt_post_drop_nebula"):
            self.assertIn(name, REALTIME_EFFECT_NAMES)

    def test_rt_groove_nebula_not_in_strobe_effects(self) -> None:
        self.assertNotIn("rt_groove_nebula", REALTIME_STROBE_EFFECTS)

    def test_drop_and_post_drop_nebula_in_strobe_effects(self) -> None:
        self.assertIn("rt_drop_nebula", REALTIME_STROBE_EFFECTS)
        self.assertIn("rt_post_drop_nebula", REALTIME_STROBE_EFFECTS)

    def test_slot_colors_not_in_param_key_dicts(self) -> None:
        """slot_colors must never appear in any param-key allowlist."""
        for name, keys in _M2_PHASE2A_PARAM_KEYS.items():
            self.assertNotIn("slot_colors", keys,
                             f"slot_colors found in _M2_PHASE2A_PARAM_KEYS[{name!r}]")

    def test_legacy_nebula_looks_in_exempt_looks(self) -> None:
        """The three legacy freestyle nebula looks must still be in exempt_looks."""
        root = Path(__file__).resolve().parents[1]
        result = load_led_look_director_config(str(root / "config/led_look_director.example.json"))
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        exempt = result.config.color_engine.exempt_looks
        for name in (
            "rt_groove_freestyle_nebula",
            "rt_drop_chase_freestyle_nebula",
            "rt_post_drop_freestyle_nebula",
        ):
            self.assertIn(name, exempt, f"{name} missing from exempt_looks")

    def test_legacy_scene_refs_still_in_effects(self) -> None:
        """Legacy scene_refs groove_freestyle_nebula, drop_chase_freestyle_nebula,
        post_drop_freestyle_nebula must still resolve via _EFFECTS.
        """
        for scene_ref in (
            "groove_freestyle_nebula",
            "drop_chase_freestyle_nebula",
            "post_drop_freestyle_nebula",
        ):
            self.assertIn(scene_ref, _EFFECTS,
                          f"Legacy scene_ref {scene_ref!r} missing from _EFFECTS")

    def test_patch_e1_param_keys_registered(self) -> None:
        """Patch E1 scene refs must be in _M2_PHASE2A_PARAM_KEYS."""
        for name in ("rt_groove_nebula", "rt_drop_nebula", "rt_post_drop_nebula"):
            self.assertIn(name, _M2_PHASE2A_PARAM_KEYS)
            keys = _M2_PHASE2A_PARAM_KEYS[name]
            self.assertIn("duration_beats", keys)
            self.assertNotIn("slot_colors", keys)


if __name__ == "__main__":
    unittest.main()
