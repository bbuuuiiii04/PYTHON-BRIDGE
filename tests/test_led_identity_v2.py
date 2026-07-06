from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_identity_v2 import (
    Claim,
    IdentityStore,
    RANKS,
    assign_zone,
    claim_allowed,
    content_hash,
    derive_dressing,
    identity_scores,
    is_hard_pivot,
    norm,
    record_from_dressing,
)
from rb_ss_bridge_v2.led_models import ZoneRampConfig


ZONE = ZoneRampConfig(
    base_ramp=((10, 40, 120), (0, 120, 255), (0, 220, 255)),
    accent_ramp=((120, 240, 255), (210, 250, 255)),
)


def _record(key: str, zone: str = "GLACIER", base: str = "measured") -> dict:
    dressing = derive_dressing(zone, ZONE, content_hash(key), 0.5, 0.4, 0.2)
    return record_from_dressing(
        dressing,
        key_hash=content_hash(key),
        base=base,
        scores={"aggression": 0.2, "luminance": 0.5, "distortion": 0.1},
        norm_inputs={"bass": 0.5, "drama": 0.4, "punch": 0.2},
    )


class IdentityMathTests(unittest.TestCase):
    def test_norm_clamps(self) -> None:
        self.assertEqual(norm(-1, 0, 10), 0.0)
        self.assertEqual(norm(20, 0, 10), 1.0)
        self.assertEqual(norm(5, 0, 10), 0.5)

    def test_zone_splits(self) -> None:
        self.assertEqual(assign_zone({"aggression": 0.268, "luminance": 0.436, "distortion": 0.12}), "GLACIER")
        self.assertEqual(assign_zone({"aggression": 0.233, "luminance": 0.267, "distortion": 0.12}), "DEEP_POOL")
        self.assertEqual(assign_zone({"aggression": 0.5, "luminance": 0.19, "distortion": 0.1}), "VOLT")
        self.assertEqual(assign_zone({"aggression": 0.5, "luminance": 0.9, "distortion": 1.0}), "EMBERCORE")
        self.assertEqual(assign_zone({"aggression": 0.418, "luminance": 0.52, "distortion": 0.0}), "ION")
        self.assertEqual(assign_zone({"aggression": 0.417, "luminance": 0.28, "distortion": 0.0}), "TWILIGHT")

    def test_scores_use_frozen_formula(self) -> None:
        scores = identity_scores(
            {"punch": 1.2, "grit": 0.0776},
            {
                "attack_low_p90": 38.875,
                "onset_mh_p90": 4.0,
                "brightness_med": 1456.5,
                "growl_timbre_p90": 0.377,
            },
            synth_rate=0.725,
        )
        self.assertEqual(scores, {"aggression": 1.0, "luminance": 1.0, "distortion": 1.0})

    def test_dressing_is_deterministic_and_non_black(self) -> None:
        key_hash = content_hash("track-1")
        a = derive_dressing("GLACIER", ZONE, key_hash, 0.5, 0.25, 0.7)
        b = derive_dressing("GLACIER", ZONE, key_hash, 0.5, 0.25, 0.7)
        c = derive_dressing("GLACIER", ZONE, content_hash("track-2"), 0.5, 0.25, 0.7)
        self.assertEqual(a, b)
        self.assertNotEqual((a.hue_slot, a.depth_variant), (c.hue_slot, c.depth_variant))
        self.assertEqual(a.slot_rgbs[5], (255, 255, 255))
        self.assertTrue(all(rgb != (0, 0, 0) for rgb in a.slot_rgbs))
        self.assertEqual(a.style, "sharp")

    def test_hard_pivot(self) -> None:
        self.assertTrue(is_hard_pivot("GLACIER", "ION"))
        self.assertFalse(is_hard_pivot("GLACIER", "TWILIGHT"))

    def test_claim_ranks(self) -> None:
        active = [Claim(RANKS["manual"], 10.0, 999.0, "manual")]
        self.assertFalse(claim_allowed(Claim(RANKS["bloom"], 12.0, 14.0, "bloom"), active))
        self.assertTrue(claim_allowed(Claim(RANKS["bloom"], 1.0, 2.0, "bloom"), active))
        self.assertTrue(claim_allowed(Claim(RANKS["manual"], 12.0, 14.0, "manual2"), active))


class IdentityStoreTests(unittest.TestCase):
    def test_missing_and_corrupt_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            self.assertEqual(IdentityStore.load(missing).to_dict(), {"version": 1, "tracks": {}})
            corrupt = Path(tmp) / "bad.json"
            corrupt.write_text("{bad", encoding="utf-8")
            store = IdentityStore.load(corrupt)
            self.assertTrue(store.degraded)
            self.assertFalse(store.write_allowed)
            self.assertEqual(corrupt.read_text(encoding="utf-8"), "{bad")

    def test_freeze_first_write_and_provisional_upgrade(self) -> None:
        store = IdentityStore()
        first = _record("a", "GLACIER")
        second = _record("a", "ION")
        self.assertTrue(store.freeze("a", first))
        self.assertFalse(store.freeze("a", second))
        self.assertEqual(store.get("a")["zone"], "GLACIER")

        self.assertTrue(store.set_correction("b", "VOLT"))
        provisional = store.get("b")
        self.assertEqual(provisional["base"], "provisional")
        self.assertEqual(provisional["correction"], {"zone": "VOLT"})
        measured = _record("b", "DEEP_POOL")
        self.assertTrue(store.freeze("b", measured))
        upgraded = store.get("b")
        self.assertEqual(upgraded["base"], "measured")
        self.assertEqual(upgraded["zone"], "DEEP_POOL")
        self.assertEqual(upgraded["correction"], {"zone": "VOLT"})
        self.assertTrue(store.clear_correction("b"))
        self.assertIsNone(store.get("b")["correction"])

    def test_to_dict_schema(self) -> None:
        store = IdentityStore()
        store.freeze("a", _record("a"))
        payload = store.to_dict()
        self.assertEqual(payload["version"], 1)
        self.assertIn("tracks", payload)
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
