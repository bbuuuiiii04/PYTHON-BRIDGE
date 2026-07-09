"""Pin the single-source bridge launch profile (launch_profile.py).

The env set here is the ONE the live watcher and the USB bundle both launch
with. If this test and the watcher's `exec env` block ever disagree, a live set
silently runs a different bridge than every past set — so this pins names AND
values, including the two 2026-07-09 deltas (STICKY removed, COOLDOWN=0), and
proves the watcher actually reads this module.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.launch_profile import (  # noqa: E402
    BRIDGE_ENV,
    LASER_CONFIG_ENV,
    bridge_argv,
    bridge_env,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHER = REPO_ROOT / "scripts" / "ss_bridge_watcher.sh"

# The exact 19 RBSS_* flags the watcher launches with, copied from
# ss_bridge_watcher.sh start_bridge() at the 2026-07-09 HEAD. Keep this literal
# (not derived from BRIDGE_ENV) so a drift in the module is caught by a failing
# assertion, not hidden by shared state.
EXPECTED_FLAGS = {
    "RBSS_GOVEE_REALTIME": "1",
    "RBSS_LIVE_BPM_FOLLOW": "1",
    "RBSS_ANLZ_DIRECT": "1",
    "RBSS_POS_CHAIN_DIRECT": "1",
    "RBSS_POS_CHAIN_SKIP_OBJC": "1",
    "RBSS_MASTER_SEED_DIRECT": "1",
    "RBSS_MASTER_DIRECT": "1",
    "RBSS_PLAY_DIRECT": "1",
    "RBSS_TRACK_LOAD_DIRECT": "1",
    "RBSS_SCRIPTED_DIRECT": "1",
    "RBSS_SCRIPTED_SHOWFILE_DIRECT": "1",
    "RBSS_SMART_REARM_EXPERIMENT": "1",
    "RBSS_SMART_DROP": "1",
    "RBSS_SMART_BREAKDOWN": "1",
    "RBSS_LED_PHRASE_MONOTONIC": "1",
    "RBSS_LED_MIN_DWELL": "1",
    "RBSS_LED_CANCEL_PENDING": "1",
    "RBSS_LED_RT_RECONCILE": "1",
    "RBSS_LED_TRANSPORT_COOLDOWN": "0",
}


class BridgeEnvSetTests(unittest.TestCase):
    def test_bridge_env_flags_match_watcher_set_exactly(self) -> None:
        self.assertEqual(BRIDGE_ENV, EXPECTED_FLAGS)

    def test_transport_cooldown_is_zero_not_one(self) -> None:
        # AWR-149 delta: the flag exists and is "0". A regression to "1" would
        # re-enable the old cooldown behavior.
        self.assertEqual(BRIDGE_ENV["RBSS_LED_TRANSPORT_COOLDOWN"], "0")

    def test_transport_sticky_is_absent(self) -> None:
        # AWR-149 delta: RBSS_LED_TRANSPORT_STICKY was removed from the launch
        # env. It must not creep back into the shared profile.
        self.assertNotIn("RBSS_LED_TRANSPORT_STICKY", BRIDGE_ENV)

    def test_all_values_are_strings(self) -> None:
        # env values cross a shell / os.environ boundary; ints would break both.
        for key, value in BRIDGE_ENV.items():
            self.assertIsInstance(value, str, key)


class BridgeEnvMergeTests(unittest.TestCase):
    def test_adds_laser_config_path(self) -> None:
        env = bridge_env("/some/laser.json")
        self.assertEqual(env[LASER_CONFIG_ENV], "/some/laser.json")

    def test_includes_every_base_flag(self) -> None:
        env = bridge_env("/x.json")
        for key, value in EXPECTED_FLAGS.items():
            self.assertEqual(env[key], value, key)

    def test_extra_merges_last_and_can_override(self) -> None:
        env = bridge_env("/x.json", extra={"RBSS_SMART_DROP": "0", "GOVEE_API_KEY": "abc"})
        self.assertEqual(env["RBSS_SMART_DROP"], "0")   # intentional override
        self.assertEqual(env["GOVEE_API_KEY"], "abc")   # host-specific addition

    def test_does_not_mutate_module_constant(self) -> None:
        bridge_env("/x.json", extra={"RBSS_SMART_DROP": "0"})
        self.assertEqual(BRIDGE_ENV["RBSS_SMART_DROP"], "1")

    def test_bridge_argv(self) -> None:
        self.assertEqual(
            bridge_argv("/opt/homebrew/bin/python3"),
            ["/opt/homebrew/bin/python3", "-m", "rb_ss_bridge_v2"],
        )


class WatcherSingleSourceTests(unittest.TestCase):
    def test_watcher_reads_launch_profile(self) -> None:
        # Single-source proof: the watcher must import this module rather than
        # carrying its own hand-maintained copy of the flag list.
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn("launch_profile", text)

    def test_watcher_no_longer_hardcodes_the_flag_list(self) -> None:
        # If the old inline `exec env RBSS_..=1 \` block came back, the watcher
        # and the module could drift again. A couple of representative flags
        # should no longer appear as literal `NAME=VALUE` shell tokens.
        text = WATCHER.read_text(encoding="utf-8")
        self.assertNotIn("RBSS_GOVEE_REALTIME=1", text)
        self.assertNotIn("RBSS_LED_TRANSPORT_COOLDOWN=0", text)


if __name__ == "__main__":
    unittest.main()
