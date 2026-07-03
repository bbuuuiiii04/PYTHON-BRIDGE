from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    REALTIME_EFFECT_NAMES,
    REALTIME_EFFECT_PARAM_KEYS,
    REALTIME_STROBE_EFFECTS,
    SLOT_EFFECTS,
)
from rb_ss_bridge_v2.govee_realtime_runner import _COLOR_SIG_KEYS  # noqa: E402
from rb_ss_bridge_v2.led_pad_controls import CONTROL_META, controls_for, render_catalog  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
