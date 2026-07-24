"""Tests for tools/apply_gentle_drop_routing.py (Part C staging script).

Gentle set is RT-only. The four rt_drop_chase colorways must live IN the bank or
the tier-1 routing cell intersects to empty and fail-opens to the full bank (a
silent no-op on every gentle drop) — so the script appends them to
banks.default.drop. tiers 2/3 stay the 12 pre-existing modern looks. The 8 legacy
drop_diy_* CLOUD chases are excluded everywhere (operator cloud-disable).
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
    """Live-shaped config post cloud-disable: RT-only drop bank = 12 modern (the
    colorways NOT yet in the bank — the trap), f2.drop_look_routing = {}."""
    looks = {n: {"backend": None, "allow_strobe": True} for n in m.LEGACY_CLOUD}
    for n in MODERN + m.SOFT_QUARTET:
        looks[n] = {"backend": "realtime_razer", "allow_strobe": True}
    return {
        "enabled": True,
        "looks": looks,
        "banks": {"default": {"drop": list(MODERN), "groove": ["rt_groove_chase"]}},
        "f2": {"enabled": True, "drop_look_routing": {}, "flick_ms": 200},
        "unrelated_key": {"keep": "me"},
    }


class ApplyGentleDropRoutingTests(unittest.TestCase):
    def test_appends_colorways_to_bank_and_writes_routing(self):
        data = _fixture()
        self.assertTrue(m.apply(data))
        # colorways appended after the existing 12 modern (order stable, no dupes)
        self.assertEqual(data["banks"]["default"]["drop"], MODERN + m.SOFT_QUARTET)
        routing = data["f2"]["drop_look_routing"]
        self.assertEqual(sorted(routing), sorted(m.FAMILIES))
        for fam in m.FAMILIES:
            self.assertEqual(routing[fam]["1"], m.SOFT_QUARTET)  # tier1 = rt colorways
            self.assertEqual(routing[fam]["2"], MODERN)          # tier2 = 12 modern
            self.assertEqual(routing[fam]["3"], MODERN)          # tier3 = 12 modern

    def test_tier1_is_subset_of_resulting_bank(self):
        # THE trap: tier-1 names absent from the bank make the cell fail-open to the
        # full bank. Every tier-1 name must be in the resulting bank, all families.
        data = _fixture()
        m.apply(data)
        bank = set(data["banks"]["default"]["drop"])
        for fam, cell in data["f2"]["drop_look_routing"].items():
            self.assertTrue(set(cell["1"]).issubset(bank), f"{fam} tier-1 not in bank")

    def test_tiers_2_3_exclude_the_quartet(self):
        # Big drops must not rotate into the gentle chases.
        data = _fixture()
        m.apply(data)
        q = set(m.SOFT_QUARTET)
        for fam, cell in data["f2"]["drop_look_routing"].items():
            self.assertFalse(set(cell["2"]) & q, f"{fam} tier-2 has a colorway")
            self.assertFalse(set(cell["3"]) & q, f"{fam} tier-3 has a colorway")

    def test_no_cloud_look_anywhere_in_routing(self):
        data = _fixture()
        m.apply(data)
        names = [
            n for fam in data["f2"]["drop_look_routing"].values()
            for tier in fam.values() for n in tier
        ]
        self.assertFalse([n for n in names if n in set(m.LEGACY_CLOUD)])

    def test_stray_cloud_in_bank_filtered_out_of_tiers_2_3(self):
        data = _fixture()
        data["banks"]["default"]["drop"] = [m.LEGACY_CLOUD[0]] + list(MODERN)
        m.apply(data)
        tier2 = data["f2"]["drop_look_routing"]["WALL"]["2"]
        self.assertEqual(tier2, MODERN)
        self.assertNotIn(m.LEGACY_CLOUD[0], tier2)

    def test_add_if_missing_no_dupes(self):
        # A colorway already in the bank is not duplicated.
        data = _fixture()
        data["banks"]["default"]["drop"] = list(MODERN) + ["rt_drop_chase_blue"]
        m.apply(data)
        bank = data["banks"]["default"]["drop"]
        self.assertEqual(bank.count("rt_drop_chase_blue"), 1)
        self.assertEqual(set(bank), set(MODERN) | set(m.SOFT_QUARTET))

    def test_idempotent_second_apply_no_change(self):
        data = _fixture()
        self.assertTrue(m.apply(data))
        self.assertFalse(m.apply(data))   # second run is a no-op

    def test_does_not_touch_other_keys(self):
        data = _fixture()
        before_unrelated = copy.deepcopy(data["unrelated_key"])
        before_groove = copy.deepcopy(data["banks"]["default"]["groove"])
        before_f2_other = {k: v for k, v in data["f2"].items() if k != "drop_look_routing"}
        m.apply(data)
        self.assertEqual(data["unrelated_key"], before_unrelated)
        self.assertEqual(data["banks"]["default"]["groove"], before_groove)  # only drop changed
        self.assertEqual(
            {k: v for k, v in data["f2"].items() if k != "drop_look_routing"},
            before_f2_other,
        )

    def test_gentle_quartet_drops_absent_names(self):
        # Absent from looks{} -> not in tier-1 AND not added to the bank.
        data = _fixture()
        del data["looks"]["rt_drop_chase_red"]
        m.apply(data)
        tier1 = data["f2"]["drop_look_routing"]["WALL"]["1"]
        self.assertEqual(tier1, ["rt_drop_chase_blue", "rt_drop_chase_cyan", "rt_drop_chase_green"])
        self.assertNotIn("rt_drop_chase_red", data["banks"]["default"]["drop"])

    def test_main_writes_once_then_no_op(self):
        import contextlib, io, os, tempfile
        data = _fixture()
        # main() is a CLI: it prints a [before]/[after]/[result] report to stdout.
        # Keep that out of the suite's stdout (a reviewer mistook the leaked
        # "[result] already applied" line for an import-time side effect); the
        # test still exercises the real write-once idempotency below.
        with tempfile.TemporaryDirectory() as td, \
                contextlib.redirect_stdout(io.StringIO()):
            p = os.path.join(td, "cfg.json")
            Path(p).write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(m.main(["--config", p]), 0)
            after_first = Path(p).read_text(encoding="utf-8")
            self.assertEqual(m.main(["--config", p]), 0)   # second run must not rewrite
            self.assertEqual(Path(p).read_text(encoding="utf-8"), after_first)
            reloaded = json.loads(after_first)
            self.assertEqual(reloaded["banks"]["default"]["drop"], MODERN + m.SOFT_QUARTET)
            self.assertEqual(reloaded["f2"]["drop_look_routing"]["WALL"]["1"], m.SOFT_QUARTET)


if __name__ == "__main__":
    unittest.main()
