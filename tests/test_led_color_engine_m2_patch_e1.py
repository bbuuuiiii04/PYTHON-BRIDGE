"""Tests for M2.5 Patch E1: Nebula family slot cues.

Covers:
- _slot_groove_nebula unit tests (shape, multi-slot, slot-5-zero, no-strobe-gate, opposing heads)
- Config: rt_groove_nebula look definition
- Slot smoke: resolve_slot_colors for the surviving Patch E1 look
- Scene-ref verification: the Patch E1 look scene_ref points to a registered SLOT_EFFECT
- Regression: original SLOT_EFFECTS keys still present; E1 entry remains after later patches
- Legacy groove nebula look still in exempt_looks; its legacy scene_ref still in _EFFECTS

The drop / post-drop nebula halves of Patch E1 were retired in the 2026-07-17
cue dedup (indistinguishable comet-train repeats); only the groove nebula and
the shared legacy groove scene_ref survive here.
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
    _slot_groove_nebula,
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

    def test_nebula_config_validates_with_zero_errors(self) -> None:
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
        # 2026-07-17 dedup: the drop/post-drop nebula looks are retired, so
        # neither they nor their renamed remnant twins may reappear in a bank.
        for retired in ("rt_drop_nebula", "rt_post_drop_nebula",
                        "rt_post_drop_remnant_nebula"):
            self.assertNotIn(retired, bank.drop, retired)
            self.assertNotIn(retired, bank.post_drop, retired)


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
        for look_name in ("rt_groove_nebula",):
            scene_ref = result.config.looks[look_name].scene_ref
            self.assertEqual(scene_ref, look_name)
            self.assertIn(scene_ref, SLOT_EFFECTS)


class PatchE1RegressionTests(unittest.TestCase):
    """Regression tests: original entries unchanged, legacy looks still resolve."""

    _ORIGINAL_SLOT_EFFECT_KEYS = frozenset({
        "rt_groove_chase",
        "rt_drop_center_burst",
        "groove_center_chase",
        "groove_center_burst_retract",
        "post_drop_firework_chase",
        "breakdown_full_breathing",
        "breakdown_star_twinkle",
    })

    def test_original_slot_effects_still_present(self) -> None:
        for key in self._ORIGINAL_SLOT_EFFECT_KEYS:
            self.assertIn(key, SLOT_EFFECTS, f"{key} missing from SLOT_EFFECTS")

    def test_slot_effects_preserves_e1_entries_after_later_patches(self) -> None:
        # AWR-156 added rt_groove_heartbeat + the remnants tail (now `sparkle`);
        # AWR-188 Part G added palette_comet; the 2026-07-17 dedup deleted the
        # four slot comet-trains.
        self.assertEqual(
            len(SLOT_EFFECTS), 13,
            f"Expected 13 SLOT_EFFECTS after the 2026-07-17 dedup, got "
            f"{len(SLOT_EFFECTS)}: {sorted(SLOT_EFFECTS.keys())}"
        )

    def test_patch_e1_looks_in_slot_effects(self) -> None:
        for name in ("rt_groove_nebula",):
            self.assertIn(name, SLOT_EFFECTS)

    def test_patch_e1_looks_in_realtime_effect_names(self) -> None:
        for name in ("rt_groove_nebula",):
            self.assertIn(name, REALTIME_EFFECT_NAMES)

    def test_rt_groove_nebula_not_in_strobe_effects(self) -> None:
        self.assertNotIn("rt_groove_nebula", REALTIME_STROBE_EFFECTS)

    def test_slot_colors_not_in_param_key_dicts(self) -> None:
        """slot_colors must never appear in any param-key allowlist."""
        for name, keys in _M2_PHASE2A_PARAM_KEYS.items():
            self.assertNotIn("slot_colors", keys,
                             f"slot_colors found in _M2_PHASE2A_PARAM_KEYS[{name!r}]")

    def test_legacy_nebula_looks_in_exempt_looks(self) -> None:
        """The surviving legacy freestyle nebula look must still be exempt."""
        root = Path(__file__).resolve().parents[1]
        result = load_led_look_director_config(str(root / "config/led_look_director.example.json"))
        self.assertTrue(result.available, f"config not available: {result.reason}")
        self.assertEqual(tuple(result.errors), ())
        exempt = result.config.color_engine.exempt_looks
        for name in ("rt_groove_freestyle_nebula",):
            self.assertIn(name, exempt, f"{name} missing from exempt_looks")

    def test_legacy_scene_refs_still_in_effects(self) -> None:
        """Legacy scene_ref groove_freestyle_nebula must still resolve via
        _EFFECTS (its drop / post-drop siblings were retired 2026-07-17).
        """
        for scene_ref in ("groove_freestyle_nebula",):
            self.assertIn(scene_ref, _EFFECTS,
                          f"Legacy scene_ref {scene_ref!r} missing from _EFFECTS")

    def test_patch_e1_param_keys_registered(self) -> None:
        """Patch E1 scene refs must be in _M2_PHASE2A_PARAM_KEYS."""
        for name in ("rt_groove_nebula",):
            self.assertIn(name, _M2_PHASE2A_PARAM_KEYS)
            keys = _M2_PHASE2A_PARAM_KEYS[name]
            self.assertIn("duration_beats", keys)
            self.assertNotIn("slot_colors", keys)


if __name__ == "__main__":
    unittest.main()
