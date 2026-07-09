"""Tests for tools/apply_gentle_drop_routing.py (Part C staging script).

Gentle set is RT-only: routing writes f2.drop_look_routing and does NOT touch the
bank; the 8 legacy drop_diy_* CLOUD chases are excluded everywhere (operator
cloud-disable) until Template-Lab RT recreations exist.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import apply_gentle_drop_routing as m  # noqa: E402

MODERN = [
    "rt_drop_chase_freestyle_nebula", "rt_drop_white_aggressive",
    "rt_drop_center_burst", "rt_drop_strobe_blue", "rt_drop_strobe_cyan",
    "rt_drop_strobe_green", "rt_drop_strobe_red", "rt_drop_strobe_red_white",
    "rt_drop_strobe_blue_cyan", "rt_drop_strobe_cyan_white", "rt_rainbow_drop",
    "rt_drop_firework_explosion",
]


def _fixture():
    """A config shaped like the live one post cloud-disable: RT-only drop bank
    (12 modern), f2.drop_look_routing = {}."""
    looks = {n: {"backend": None, "allow_strobe": True} for n in m.LEGACY_CLOUD}
    for n in MODERN:
        looks[n] = {"backend": "realtime_razer", "allow_strobe": True}
    for n in m.SOFT_QUARTET:
        looks[n] = {"backend": "realtime_razer", "allow_strobe": True}
    return {
        "enabled": True,
        "looks": looks,
        "banks": {"default": {"drop": list(MODERN), "groove": ["rt_groove_chase"]}},
        "f2": {"enabled": True, "drop_look_routing": {}, "flick_ms": 200},
        "unrelated_key": {"keep": "me"},
    }


class ApplyGentleDropRoutingTests(unittest.TestCase):
    def test_writes_rt_only_routing_and_leaves_bank_untouched(self):
        data = _fixture()
        bank_before = list(data["banks"]["default"]["drop"])
        self.assertTrue(m.apply(data))
        # bank is NOT mutated
        self.assertEqual(data["banks"]["default"]["drop"], bank_before)
        routing = data["f2"]["drop_look_routing"]
        self.assertEqual(sorted(routing), sorted(m.FAMILIES))
        for fam in m.FAMILIES:
            self.assertEqual(routing[fam]["1"], m.SOFT_QUARTET)  # tier1 = rt colorways only
            self.assertEqual(routing[fam]["2"], MODERN)          # tier2 = modern
            self.assertEqual(routing[fam]["3"], MODERN)          # tier3 = modern

    def test_no_cloud_look_anywhere_in_routing(self):
        data = _fixture()
        m.apply(data)
        names = [
            n for fam in data["f2"]["drop_look_routing"].values()
            for tier in fam.values() for n in tier
        ]
        self.assertFalse([n for n in names if n in set(m.LEGACY_CLOUD)])

    def test_legacy_in_bank_is_filtered_out_of_tiers_2_3(self):
        # Defensive RT-only guard: a stray cloud look in the bank must never reach
        # the routing table (it would resurrect transport fighting).
        data = _fixture()
        data["banks"]["default"]["drop"] = [m.LEGACY_CLOUD[0]] + list(MODERN)
        m.apply(data)
        tier2 = data["f2"]["drop_look_routing"]["WALL"]["2"]
        self.assertEqual(tier2, MODERN)
        self.assertNotIn(m.LEGACY_CLOUD[0], tier2)

    def test_idempotent_second_apply_no_change(self):
        data = _fixture()
        self.assertTrue(m.apply(data))
        self.assertFalse(m.apply(data))   # second run is a no-op

    def test_does_not_touch_other_keys(self):
        data = _fixture()
        before_unrelated = copy.deepcopy(data["unrelated_key"])
        before_banks = copy.deepcopy(data["banks"])
        before_f2_other = {k: v for k, v in data["f2"].items() if k != "drop_look_routing"}
        m.apply(data)
        self.assertEqual(data["unrelated_key"], before_unrelated)
        self.assertEqual(data["banks"], before_banks)   # ENTIRE banks block untouched
        self.assertEqual(
            {k: v for k, v in data["f2"].items() if k != "drop_look_routing"},
            before_f2_other,
        )

    def test_gentle_quartet_drops_absent_names(self):
        data = _fixture()
        del data["looks"]["rt_drop_chase_red"]   # absent from looks{} -> dropped
        m.apply(data)
        tier1 = data["f2"]["drop_look_routing"]["WALL"]["1"]
        self.assertEqual(
            tier1, ["rt_drop_chase_blue", "rt_drop_chase_cyan", "rt_drop_chase_green"],
        )

    def test_main_writes_once_then_no_op(self):
        import tempfile, os
        data = _fixture()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "cfg.json")
            Path(p).write_text(json.dumps(data), encoding="utf-8")
            rc1 = m.main(["--config", p])
            self.assertEqual(rc1, 0)
            after_first = Path(p).read_text(encoding="utf-8")
            rc2 = m.main(["--config", p])   # second run must not rewrite the file
            self.assertEqual(rc2, 0)
            self.assertEqual(Path(p).read_text(encoding="utf-8"), after_first)
            reloaded = json.loads(after_first)
            self.assertEqual(sorted(reloaded["f2"]["drop_look_routing"]), sorted(m.FAMILIES))
            self.assertEqual(reloaded["f2"]["drop_look_routing"]["WALL"]["1"], m.SOFT_QUARTET)


if __name__ == "__main__":
    unittest.main()
