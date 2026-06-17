from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.logging_manager import LoggingManager, _DIAG_MODULES  # noqa: E402
from rb_ss_bridge_v2 import diagnostics  # noqa: E402

# Logger names every laser/LED/govee diagnostic path must be able to reach.
_REQUIRED_SUBSYSTEM_LOGGERS = (
    "laser_director", "laser_executor",
    "led_look_director", "led_color_engine", "beat_sync_engine",
    "govee_runtime_sender", "govee_realtime_runner",
    "govee_realtime_transport", "govee_frame_renderer", "govee_owner_state",
    "led_dispatch_coordinator", "govee_scene_adapter",
)


class DiagModuleCoverageTest(unittest.TestCase):
    def test_diag_modules_cover_laser_led_govee(self) -> None:
        mapped = set(_DIAG_MODULES.values())
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            self.assertIn(name, mapped, f"{name} missing from _DIAG_MODULES")

    def test_manager_enable_debug_sets_named_subsystems(self) -> None:
        mgr = LoggingManager()
        for name in ("laser_director", "led_color_engine", "govee_runtime_sender"):
            logging.getLogger(name).setLevel(logging.INFO)
        mgr.enable_debug("laser", "color", "rgb")
        self.assertEqual(logging.getLogger("laser_director").level, logging.DEBUG)
        self.assertEqual(logging.getLogger("led_color_engine").level, logging.DEBUG)
        self.assertEqual(logging.getLogger("govee_runtime_sender").level, logging.DEBUG)

    def test_diagnostics_enable_debug_covers_subsystems(self) -> None:
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)
        diagnostics.enable_debug()
        for name in _REQUIRED_SUBSYSTEM_LOGGERS:
            self.assertEqual(
                logging.getLogger(name).level, logging.DEBUG,
                f"{name} not set to DEBUG by diagnostics.enable_debug()",
            )


if __name__ == "__main__":
    unittest.main()
