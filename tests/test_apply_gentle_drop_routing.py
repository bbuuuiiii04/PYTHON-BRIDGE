"""Tests for tools/apply_gentle_drop_routing.py (Part C staging script)."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import apply_gentle_drop_routing as m  # noqa: E402


def _fixture(quartet_strobe=True):
    """A config shaped like the live one AFTER the mirror stripped legacy:
    drop bank = 12 modern only, f2.drop_look_routing = {}."""
    looks = {n: {"backend": None, "allow_strobe": True} for n in m.LEGACY_8}
    modern = [
        "rt_drop_chase_freestyle_nebula", "rt_drop_white_aggressive",
        "rt_drop_center_burst", "rt_drop_strobe_blue", "rt_drop_strobe_cyan",
        "rt_drop_strobe_green", "rt_drop_strobe_red", "rt_drop_strobe_red_white",
        "rt_drop_strobe_blue_cyan", "rt_drop_strobe_cyan_white", "rt_rainbow_drop",
        "rt_drop_firework_explosion",
    ]
    for n in modern:
        looks[n] = {"backend": "realtime_razer", "allow_strobe": True}
    for n in m.SOFT_QUARTET:
        looks[n] = {"backend": "realtime_razer", "allow_strobe": quartet_strobe}
    return {
        "enabled": True,
        "looks": looks,
        "banks": {"default": {"drop": list(modern), "groove": ["rt_groove_chase"]}},
        "f2": {"enabled": True, "drop_look_routing": {}, "flick_ms": 200},
        "unrelated_key": {"keep": "me"},
    }, modern


class ApplyGentleDropRoutingTests(unittest.TestCase):
    def test_apply_readds_legacy_and_writes_routing(self):
        data, modern = _fixture()
        changed = m.apply(data)
        self.assertTrue(changed)
        drop = data["banks"]["default"]["drop"]
        # legacy re-added, legacy-first, no duplicates, modern preserved
        self.assertEqual(drop[:8], m.LEGACY_8)
        self.assertEqual(drop[8:], modern)
        self.assertEqual(len(drop), 20)
        routing = data["f2"]["drop_look_routing"]
        self.assertEqual(sorted(routing), sorted(m.FAMILIES))
        for fam in m.FAMILIES:
            self.assertEqual(routing[fam]["1"], m.LEGACY_8 + m.SOFT_QUARTET)  # tier1 = legacy + colorways
            self.assertEqual(routing[fam]["2"], modern)       # tier2 = modern
            self.assertEqual(routing[fam]["3"], modern)       # tier3 = modern

    def test_idempotent_second_apply_no_change(self):
        data, _ = _fixture()
        self.assertTrue(m.apply(data))
        self.assertFalse(m.apply(data))   # second run is a no-op

    def test_does_not_touch_unrelated_keys(self):
        data, _ = _fixture()
        before_unrelated = copy.deepcopy(data["unrelated_key"])
        before_groove = copy.deepcopy(data["banks"]["default"]["groove"])
        before_f2_other = {k: v for k, v in data["f2"].items() if k != "drop_look_routing"}
        m.apply(data)
        self.assertEqual(data["unrelated_key"], before_unrelated)
        self.assertEqual(data["banks"]["default"]["groove"], before_groove)
        self.assertEqual(
            {k: v for k, v in data["f2"].items() if k != "drop_look_routing"},
            before_f2_other,
        )

    def test_gentle_quartet_included_by_name_regardless_of_strobe(self):
        # allow_strobe is a permission flag, not character — the colorways go in
        # tier 1 by name even though the fixture marks them allow_strobe=true.
        data, _ = _fixture(quartet_strobe=True)
        m.apply(data)
        tier1 = data["f2"]["drop_look_routing"]["WALL"]["1"]
        self.assertEqual(tier1, m.LEGACY_8 + m.SOFT_QUARTET)

    def test_gentle_quartet_drops_absent_names(self):
        data, _ = _fixture()
        del data["looks"]["rt_drop_chase_red"]   # absent from looks{} -> dropped
        m.apply(data)
        tier1 = data["f2"]["drop_look_routing"]["WALL"]["1"]
        self.assertEqual(
            tier1,
            m.LEGACY_8 + ["rt_drop_chase_blue", "rt_drop_chase_cyan", "rt_drop_chase_green"],
        )

    def test_build_target_stable_when_bank_already_has_legacy(self):
        # If the bank arrives WITH legacy (e.g. example config / second config),
        # modern is still just the non-legacy entries and order is stable.
        data, modern = _fixture()
        data["banks"]["default"]["drop"] = m.LEGACY_8 + modern
        new_drop, routing = m.build_target(data)
        self.assertEqual(new_drop, m.LEGACY_8 + modern)
        self.assertEqual(routing["WALL"]["2"], modern)

    def test_main_writes_once_then_no_op(self):
        import tempfile, os
        data, _ = _fixture()
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "cfg.json")
            Path(p).write_text(json.dumps(data), encoding="utf-8")
            rc1 = m.main(["--config", p])
            self.assertEqual(rc1, 0)
            after_first = Path(p).read_text(encoding="utf-8")
            # second run must not rewrite the file
            rc2 = m.main(["--config", p])
            self.assertEqual(rc2, 0)
            self.assertEqual(Path(p).read_text(encoding="utf-8"), after_first)
            # and the routing landed
            reloaded = json.loads(after_first)
            self.assertEqual(sorted(reloaded["f2"]["drop_look_routing"]), sorted(m.FAMILIES))


if __name__ == "__main__":
    unittest.main()
