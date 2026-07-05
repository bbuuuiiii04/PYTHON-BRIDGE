from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# rb_ss_bridge_v2.__main__ calls bridge_log.init() at import time (Task W2
# cutover). Redirect it into a throwaway dir so the import never touches the
# operator's real ~/Library/Logs or /tmp/bridge-events.jsonl, then shut it
# down immediately so test_bridge_log.py gets a clean, un-initialized
# singleton to exercise.
with mock.patch.dict(os.environ, {"RBSS_RUNTIME_DIR": tempfile.mkdtemp(prefix="rbss_test_runtime_")}):
    from rb_ss_bridge_v2 import __main__ as main_mod  # noqa: E402
    from rb_ss_bridge_v2.__main__ import (  # noqa: E402
        _direct_master_startup_seed,
        _initial_show_deck_for_startup,
        _offsets_have_mixer_authority,
        _rb_state_authoritative_kinds,
    )
from rb_ss_bridge_v2 import bridge_log  # noqa: E402
bridge_log.shutdown()
from rb_ss_bridge_v2.models import Ev  # noqa: E402
from rb_ss_bridge_v2.rb_offsets import load_offsets_for_version  # noqa: E402
from rb_ss_bridge_v2.rb_state_reader import DirectMasterStatus  # noqa: E402


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

    def test_raw_deck_c_direct_seed_falls_back_instead_of_aliasing(self):
        status = DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source="offset_table",
            reason="ok",
            rb_version="7.2.11",
            rb_raw=2,
            bridge_deck=1,
            pid=123,
            base=456,
        )
        with mock.patch.dict(os.environ, {"RBSS_MASTER_SEED_DIRECT": "1"}):
            with mock.patch.object(main_mod, "read_direct_master_status", return_value=status):
                deck, source = _direct_master_startup_seed("7.2.11", 1)

        self.assertEqual(deck, 1)
        self.assertEqual(source, "default startup")

    def test_raw_deck_ab_direct_seed_still_works_when_stable(self):
        status = DirectMasterStatus(
            attempted=True,
            supported=True,
            available=True,
            readable=True,
            source="offset_table",
            reason="ok",
            rb_version="7.2.11",
            rb_raw=1,
            bridge_deck=2,
            pid=123,
            base=456,
        )
        with mock.patch.dict(os.environ, {"RBSS_MASTER_SEED_DIRECT": "1"}):
            with mock.patch.object(main_mod, "read_direct_master_status", return_value=status):
                with mock.patch.object(main_mod.time, "sleep"):
                    deck, source = _direct_master_startup_seed("7.2.11", 1)

        self.assertEqual(deck, 2)
        self.assertEqual(source, "direct master seed")

    def test_running_log_uses_initialized_show_deck(self):
        source = inspect.getsource(main_mod.main)
        running_log = source[source.index("[MAIN] running"): source.index("def _on_laser_config_reload")]
        self.assertIn("initial_show_deck,\n        initial_active_source", running_log)
        self.assertNotIn("initial_active_deck,\n        initial_active_source", running_log)


if __name__ == "__main__":
    unittest.main()
