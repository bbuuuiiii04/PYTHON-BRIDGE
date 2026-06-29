from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.__main__ import (  # noqa: E402
    _initial_show_deck_for_startup,
    _offsets_have_mixer_authority,
    _rb_state_authoritative_kinds,
)
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.rb_offsets import load_offsets_for_version  # noqa: E402


class MainMixerAuthorityWiringTests(unittest.TestCase):
    def test_named_mixer_offsets_enable_default_mixer_authority(self):
        self.assertTrue(_offsets_have_mixer_authority(load_offsets_for_version("7.2.11")))
        self.assertFalse(_offsets_have_mixer_authority(load_offsets_for_version("7.2.10")))

    def test_mixer_authority_routes_support_events_when_old_direct_flags_off(self):
        kinds = _rb_state_authoritative_kinds(
            anlz_direct=False,
            play_direct=False,
            track_load_direct=False,
            master_direct=False,
            mixer_authority=True,
        )
        self.assertEqual(kinds, {Ev.MIXER_STATE, Ev.PLAY, Ev.PAUSE, Ev.MASTER_CHANGED})

    def test_mixer_authority_starts_idle_without_direct_master_seed(self):
        show_deck, rb_master_valid = _initial_show_deck_for_startup(
            1,
            "default startup",
            mixer_authority=True,
        )

        self.assertEqual(show_deck, 0)
        self.assertFalse(rb_master_valid)

    def test_direct_master_seed_can_seed_mixer_fallback_master(self):
        show_deck, rb_master_valid = _initial_show_deck_for_startup(
            2,
            "direct master seed",
            mixer_authority=True,
        )

        self.assertEqual(show_deck, 2)
        self.assertTrue(rb_master_valid)


if __name__ == "__main__":
    unittest.main()
