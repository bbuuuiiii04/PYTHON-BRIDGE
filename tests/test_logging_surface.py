"""Surface-level logging assertions ported off logging_manager.py (Task W5).

logging_manager.py and tests/test_logging_diag_coverage.py were deleted as
part of the AWR-125 logging overhaul teardown: the runtime module/deck/event
filter maze, LogStats, the control-file watcher, and diagnostics.enable_debug/
is_debug are all gone. Three properties from the old suite were still
meaningful against the new bridge_log pipeline and are re-verified here:

  * ERROR-level records are never silently lost by a per-logger floor raised
    via BRIDGE_LOG_LEVELS (the practical replacement for the old
    LoggingManager.should_emit() ERROR bypass — there is no module/deck/event
    allow-list left to bypass, but the same "errors must always surface"
    guarantee still needs a regression test).
  * BRIDGE_LOG_LEVELS parsing: valid "name=LEVEL" entries apply; malformed
    entries (no "=", empty name, unknown level name) are ignored, not raised.
  * BRIDGE_DEBUG=1 sets logging.root to DEBUG (root stays INFO otherwise).

Follows tests/test_bridge_log.py's isolation pattern: RBSS_RUNTIME_DIR is
env-patched to a tmpdir everywhere init() is exercised, and shutdown() runs
in tearDown so no real bridge/hardware path is ever touched.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_log  # noqa: E402


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class ErrorAlwaysPassesTest(unittest.TestCase):
    """A logger whose floor is raised (to cut noise) must still surface ERROR."""

    _LOGGER_NAME = "test_w5_error_floor_logger"

    def setUp(self) -> None:
        self._orig_handlers = list(logging.root.handlers)
        self._orig_level = logging.root.level
        self._tmp = tempfile.TemporaryDirectory()
        self._env_patch = mock.patch.dict(os.environ, {
            "RBSS_RUNTIME_DIR": self._tmp.name,
            "BRIDGE_LOG_LEVELS": f"{self._LOGGER_NAME}=WARNING",
        }, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        bridge_log.shutdown()
        self._env_patch.stop()
        self._tmp.cleanup()
        logging.root.handlers = self._orig_handlers
        logging.root.setLevel(self._orig_level)
        logging.getLogger(self._LOGGER_NAME).setLevel(logging.NOTSET)

    def test_error_passes_when_logger_floor_raised_to_warning(self) -> None:
        bridge_log.init()
        logger = logging.getLogger(self._LOGGER_NAME)
        self.assertEqual(logger.getEffectiveLevel(), logging.WARNING)

        capture = _CaptureHandler()
        logger.addHandler(capture)
        try:
            logger.info("suppressed by the raised floor")
            logger.error("must still get through")
        finally:
            logger.removeHandler(capture)

        levels = [r.levelno for r in capture.records]
        self.assertNotIn(logging.INFO, levels)
        self.assertIn(logging.ERROR, levels)


class BridgeLogLevelsParsingTest(unittest.TestCase):
    """init() applies valid 'name=LEVEL' entries and ignores malformed ones."""

    _VALID = "test_w5_bridge_log_levels_valid"
    _UNKNOWN_LEVEL = "test_w5_bridge_log_levels_unknown"
    _SPACED = "test_w5_bridge_log_levels_spaced"

    def setUp(self) -> None:
        self._orig_handlers = list(logging.root.handlers)
        self._orig_level = logging.root.level
        self._tmp = tempfile.TemporaryDirectory()
        levels = ",".join([
            f"{self._VALID}=DEBUG",
            "malformed-no-equals-sign",
            "=empty-name-with-a-level",
            f"{self._UNKNOWN_LEVEL}=NOTALEVEL",
            f"  {self._SPACED} = WARNING  ",
        ])
        self._env_patch = mock.patch.dict(os.environ, {
            "RBSS_RUNTIME_DIR": self._tmp.name,
            "BRIDGE_LOG_LEVELS": levels,
        }, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        bridge_log.shutdown()
        self._env_patch.stop()
        self._tmp.cleanup()
        logging.root.handlers = self._orig_handlers
        logging.root.setLevel(self._orig_level)
        for name in (self._VALID, self._UNKNOWN_LEVEL, self._SPACED):
            logging.getLogger(name).setLevel(logging.NOTSET)

    def test_valid_entry_applied(self) -> None:
        bridge_log.init()
        self.assertEqual(logging.getLogger(self._VALID).level, logging.DEBUG)

    def test_unknown_level_name_ignored(self) -> None:
        bridge_log.init()
        self.assertEqual(logging.getLogger(self._UNKNOWN_LEVEL).level, logging.NOTSET)

    def test_whitespace_padded_entry_still_applies(self) -> None:
        bridge_log.init()
        self.assertEqual(logging.getLogger(self._SPACED).level, logging.WARNING)

    def test_junk_entries_do_not_raise(self) -> None:
        # init() itself would have raised during setUp's first call below if a
        # malformed entry ("no =" / empty name) broke parsing.
        bridge_log.init()
        self.assertEqual(logging.getLogger(self._VALID).level, logging.DEBUG)


class BridgeDebugRootLevelTest(unittest.TestCase):
    """BRIDGE_DEBUG=1 sets logging.root to DEBUG; unset leaves it at INFO."""

    def setUp(self) -> None:
        self._orig_handlers = list(logging.root.handlers)
        self._orig_level = logging.root.level
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        bridge_log.shutdown()
        logging.root.handlers = self._orig_handlers
        logging.root.setLevel(self._orig_level)
        self._tmp.cleanup()

    def test_bridge_debug_set_yields_debug_root(self) -> None:
        with mock.patch.dict(os.environ, {
            "RBSS_RUNTIME_DIR": self._tmp.name,
            "BRIDGE_DEBUG": "1",
        }, clear=False):
            bridge_log.init()
        self.assertEqual(logging.root.level, logging.DEBUG)

    def test_bridge_debug_unset_yields_info_root(self) -> None:
        with mock.patch.dict(os.environ, {"RBSS_RUNTIME_DIR": self._tmp.name}, clear=False):
            os.environ.pop("BRIDGE_DEBUG", None)
            bridge_log.init()
        self.assertEqual(logging.root.level, logging.INFO)


if __name__ == "__main__":
    unittest.main()
