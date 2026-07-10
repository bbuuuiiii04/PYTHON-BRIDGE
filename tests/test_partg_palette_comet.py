"""Part G (AWR-188): palette-cycling comet — renderer primitive, example-config
pair wiring, and the live-config staging script tools/apply_partg_palette_comet.py.

The primitive generalizes the pulled BAKED-rainbow pair: a slot effect whose
color phase (strip position + time cycle, the accepted rainbow_ordered shape)
quantizes onto the runtime-injected palette slots instead of the HSV wheel. On
rainbow-classified tracks the PALETTE is rainbow, so the same effect goes
rainbow there — a palette, not a renderer branch.
"""
import copy
import glob
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import apply_partg_palette_comet as m  # noqa: E402

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
    GoveeFrameRenderer,
    _slot_palette_comet,
)
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402

_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config" / "led_look_director.example.json"

SEG = 60
DROP_PARAMS = {"width": 6, "cycle_beats": 1, "travel_per_beat": 30}


def _palette(n: int) -> list[list[int]]:
    return [[(37 * i) % 256, (91 * i + 10) % 256, (53 * i + 20) % 256] for i in range(1, n + 1)]


def _slots_used(params: dict, beats: list[float], seed: int = 7) -> set[int]:
    used: set[int] = set()
    for beat in beats:
        field = _slot_palette_comet(beat, 0.0, 0, params, SEG, seed)
        for px in field:
            for slot, intensity in enumerate(px):
                if intensity > 0.0:
                    used.add(slot)
    return used


class PaletteCometRendererTests(unittest.TestCase):
    def test_registration_and_c5_allowlist(self):
        # A SLOT effect (the dispatch layer injects the palette for
        # scene_ref-in-SLOT_EFFECTS looks) and NOT a strobe.
        self.assertIn("palette_comet", SLOT_EFFECTS)
        self.assertIn("palette_comet", REALTIME_EFFECT_NAMES)
        self.assertNotIn("palette_comet", REALTIME_STROBE_EFFECTS)
        allowed = REALTIME_EFFECT_PARAM_KEYS["palette_comet"]
        for key in ("width", "cycle_beats", "palette_span", "travel_per_beat",
                    "loop_beats", "duration_beats"):
            self.assertIn(key, allowed, key)
        # slot_colors is RUNTIME-injected, never a static config key (C5).
        self.assertNotIn("slot_colors", allowed)

    def test_deterministic_same_seed_same_frame(self):
        r = GoveeFrameRenderer()
        params = {**DROP_PARAMS, "slot_colors": _palette(6)}
        frames = [
            r.render("palette_comet", beat_pos=5.3, local_t=1.7, frame_index=i,
                     params=params, segments=SEG, seed=1234)
            for i in (0, 99)  # frame_index must not matter either
        ]
        self.assertEqual(frames[0], frames[1])
        self.assertTrue(any(px != (0, 0, 0) for px in frames[0]))

    def test_palette_length_sweep_cycles_exactly_the_palette_slots(self):
        beats = [i / 16.0 for i in range(0, 33)]  # two full cycle_beats=1 cycles
        for n in (3, 5, 6):
            params = {**DROP_PARAMS, "slot_colors": _palette(n)}
            expected = set(range(min(n, 5)))
            used = _slots_used(params, beats)
            self.assertEqual(used, expected, f"palette length {n}: slots used {used}")

    def test_slot_discipline_slot5_reserved_for_white(self):
        # Even with a full 6-slot v2 dressing the comet never writes slot 5.
        beats = [i / 16.0 for i in range(0, 33)]
        used = _slots_used({**DROP_PARAMS, "slot_colors": _palette(6)}, beats)
        self.assertNotIn(5, used)

    def test_no_injected_palette_fails_bright_white(self):
        # Module rule: a slot effect without an injected palette fails BRIGHT
        # (default single white slot), never dark.
        r = GoveeFrameRenderer()
        frame = r.render("palette_comet", beat_pos=2.25, local_t=0.5, frame_index=0,
                         params=dict(DROP_PARAMS), segments=SEG, seed=9)
        lit = [px for px in frame if px != (0, 0, 0)]
        self.assertTrue(lit)
        for px in lit:
            self.assertEqual(px[0], px[1])
            self.assertEqual(px[1], px[2])

    def test_seed_walks_the_palette_start_offset(self):
        params = {**DROP_PARAMS, "slot_colors": _palette(5)}
        fields = [
            _slot_palette_comet(0.25, 0.0, 0, params, SEG, seed)
            for seed in range(8)
        ]
        self.assertTrue(any(f != fields[0] for f in fields[1:]),
                        "8 seeds all produced the identical frame — start offset dead")

    def test_post_drop_paced_by_loop_beats_without_travel_per_beat(self):
        # The post_drop look has no travel_per_beat: the legacy loop_beats pace
        # must still move the heads between beats (accepted-as-is feel).
        params = {"width": 2, "cycle_beats": 8, "slot_colors": _palette(6)}
        a = _slot_palette_comet(0.0, 0.0, 0, params, SEG, 7)
        b = _slot_palette_comet(1.0, 0.0, 0, params, SEG, 7)
        self.assertNotEqual(a, b)


class PaletteCometPairWiringTests(unittest.TestCase):
    def test_example_config_defines_and_pairs_the_looks(self):
        result = load_led_look_director_config(str(_EXAMPLE_PATH))
        self.assertTrue(result.available, msg=result.errors)
        looks = result.config.looks
        drop = looks["rt_drop_palette_comet"]
        post = looks["rt_post_drop_palette_comet"]
        for look in (drop, post):
            self.assertEqual(look.scene_ref, "palette_comet")
            self.assertEqual(look.color_source, "engine")  # palette injection
            self.assertFalse(look.allow_strobe)
            self.assertEqual(look.backend, "realtime_razer")
        self.assertEqual(drop.safety_class, "drop")
        self.assertEqual(post.safety_class, "post_drop")
        pair = result.config.drop_pairs["rt_drop_palette_comet"]
        self.assertEqual(pair.post_drop, "rt_post_drop_palette_comet")

    def test_script_look_defs_match_the_example_config(self):
        raw = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
        for name, spec in m.LOOK_DEFS.items():
            self.assertEqual(raw["looks"][name], spec, name)


def _mini_fixture() -> dict:
    """Minimal Round-A-landed shape for the pure apply()/verify() tests."""
    return {
        "looks": {"rt_blackout": {}},
        "drop_pairs": {},
        "banks": {"default": {"drop": ["rt_drop_center_burst"],
                              "post_drop": ["rt_post_drop_chase"],
                              "groove": ["rt_groove_chase"]}},
        "f2": {"enabled": True, "drop_look_routing": {
            "WALL": {"2": ["a"], "3": ["b"]},
            "COMET": {"1": ["q"], "2": ["rt_drop_center_burst"], "3": ["rt_drop_center_burst"]},
        }},
        "unrelated": {"keep": "me"},
    }


class ApplyPartGScriptTests(unittest.TestCase):
    def test_apply_stages_everything_add_if_missing(self):
        data = _mini_fixture()
        self.assertTrue(m.apply(data))
        self.assertFalse(m.verify(data), m.verify(data))
        # COMET family only — WALL untouched.
        self.assertEqual(data["f2"]["drop_look_routing"]["WALL"], {"2": ["a"], "3": ["b"]})
        # Appends keep existing order.
        self.assertEqual(data["banks"]["default"]["drop"],
                         ["rt_drop_center_burst", m.DROP_LOOK])
        self.assertEqual(data["banks"]["default"]["post_drop"],
                         ["rt_post_drop_chase", m.POST_DROP_LOOK])
        self.assertEqual(data["unrelated"], {"keep": "me"})
        self.assertEqual(data["banks"]["default"]["groove"], ["rt_groove_chase"])

    def test_apply_is_idempotent(self):
        data = _mini_fixture()
        self.assertTrue(m.apply(data))
        snapshot = copy.deepcopy(data)
        self.assertFalse(m.apply(data))
        self.assertEqual(data, snapshot)

    def test_apply_never_clobbers_an_operator_tuned_look(self):
        data = _mini_fixture()
        tuned = {"scene_ref": "palette_comet", "params": {"width": 3.3}}
        data["looks"][m.DROP_LOOK] = copy.deepcopy(tuned)
        m.apply(data)
        self.assertEqual(data["looks"][m.DROP_LOOK], tuned)

    def test_apply_refuses_a_pre_round_a_config(self):
        data = _mini_fixture()
        del data["f2"]["drop_look_routing"]["COMET"]
        with self.assertRaises(ValueError):
            m.apply(data)

    def test_main_end_to_end_on_the_example_config(self):
        # The example config is a real full config: exercises the loader gate,
        # the timestamped backup, the atomic write, and idempotence.
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "led_look_director.json")
            Path(p).write_text(_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(m.main(["--config", p]), 0)
            self.assertEqual(len(glob.glob(p + ".backup_partg_*")), 1)
            after_first = Path(p).read_text(encoding="utf-8")
            reloaded = json.loads(after_first)
            self.assertFalse(m.verify(reloaded), m.verify(reloaded))
            comet = reloaded["f2"]["drop_look_routing"]["COMET"]
            self.assertIn(m.DROP_LOOK, comet["2"])
            self.assertIn(m.DROP_LOOK, comet["3"])
            self.assertNotIn(m.DROP_LOOK, reloaded["f2"]["drop_look_routing"]["WALL"]["2"])
            # Second run: no rewrite, no second backup.
            self.assertEqual(m.main(["--config", p]), 0)
            self.assertEqual(Path(p).read_text(encoding="utf-8"), after_first)
            self.assertEqual(len(glob.glob(p + ".backup_partg_*")), 1)

    def test_main_refuses_and_writes_nothing_pre_round_a(self):
        raw = json.loads(_EXAMPLE_PATH.read_text(encoding="utf-8"))
        del raw["f2"]["drop_look_routing"]["COMET"]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "led_look_director.json")
            before = json.dumps(raw, indent=2)
            Path(p).write_text(before, encoding="utf-8")
            self.assertEqual(m.main(["--config", p]), 2)
            self.assertEqual(Path(p).read_text(encoding="utf-8"), before)
            self.assertEqual(glob.glob(p + ".backup_partg_*"), [])


if __name__ == "__main__":
    unittest.main()
