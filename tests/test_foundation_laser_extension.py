"""
Tests for Issue #6: Foundation prep for Laser Director extension points.

Covers:
  - OS2LConnection.is_connected() constant-time helper
  - StatusWriter laser_status_provider and default laser_director key
  - CommandReader callback failure reporting via _invoke_callback
  - ValidationRunner _check_laser() placeholder checks
"""
import queue
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.osl_output import OS2LConnection  # noqa: E402
from rb_ss_bridge_v2.runtime_status import (  # noqa: E402
    CommandReader,
    StatusWriter,
    _invoke_callback,
)
from rb_ss_bridge_v2.validation_runner import (  # noqa: E402
    STATUS_NA,
    ValidationRunner,
)


# ---------------------------------------------------------------------------
# OS2LConnection.is_connected
# ---------------------------------------------------------------------------

class OS2LConnectionIsConnectedTests(unittest.TestCase):
    def test_is_connected_false_initially(self) -> None:
        conn = OS2LConnection()
        self.assertFalse(conn.is_connected())

    def test_is_connected_true_when_flag_set(self) -> None:
        conn = OS2LConnection()
        conn._connected = True
        self.assertTrue(conn.is_connected())

    def test_is_connected_false_after_clearing_flag(self) -> None:
        conn = OS2LConnection()
        conn._connected = True
        conn._connected = False
        self.assertFalse(conn.is_connected())

    def test_is_connected_does_not_build_a_dict(self) -> None:
        """is_connected must not call status() or build any dict."""
        conn = OS2LConnection()
        with patch.object(conn, "status", side_effect=AssertionError("status() must not be called")):
            result = conn.is_connected()
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# StatusWriter — laser_director key and provider
# ---------------------------------------------------------------------------

def _make_status_writer(laser_status_provider=None):
    """Build a StatusWriter with minimal stubs."""
    sm = Mock()
    sm.snapshot.return_value = {"lighting_mode": "idle", "deck": {}}
    live_bpm = Mock()
    live_bpm.get_status.return_value = None
    live_bpm.get_summary.return_value = None
    pos_cache = Mock()
    pos_cache.get.return_value = None
    conn = SimpleNamespace(
        _connected=True,
        _send_q=queue.Queue(maxsize=10),
        _drop_count=0,
        status=lambda: {"connected": True, "queue_size": 0},
    )
    mirror = Mock()
    mirror.get_summary.return_value = {}
    validation_runner = Mock()
    validation_runner.last_result.return_value = Mock(to_dict=lambda: {})
    command_reader = Mock()
    command_reader.status.return_value = {}
    return StatusWriter(
        sm, live_bpm, pos_cache, conn, mirror,
        validation_runner, command_reader,
        laser_status_provider=laser_status_provider,
    )


class StatusWriterLaserTests(unittest.TestCase):
    def test_laser_director_key_present_without_provider(self) -> None:
        writer = _make_status_writer()
        snap = writer.snapshot()
        self.assertIn("laser_director", snap)

    def test_default_laser_status_when_no_provider(self) -> None:
        writer = _make_status_writer()
        snap = writer.snapshot()
        self.assertEqual(snap["laser_director"], {
            "available": False,
            "enabled": False,
            "reason": "not_configured",
        })

    def test_laser_status_provider_result_used(self) -> None:
        provider_result = {"available": True, "enabled": False, "reason": "ok"}
        writer = _make_status_writer(laser_status_provider=lambda: provider_result)
        snap = writer.snapshot()
        self.assertEqual(snap["laser_director"], provider_result)

    def test_laser_status_provider_exception_falls_back(self) -> None:
        def bad_provider():
            raise RuntimeError("provider boom")

        writer = _make_status_writer(laser_status_provider=bad_provider)
        snap = writer.snapshot()
        self.assertIn("laser_director", snap)
        self.assertEqual(snap["laser_director"]["available"], False)
        self.assertEqual(snap["laser_director"]["enabled"], False)
        self.assertEqual(snap["laser_director"]["reason"], "provider_error")
        self.assertIn("RuntimeError", snap["laser_director"]["last_error"])

    def test_existing_snapshot_keys_all_present(self) -> None:
        writer = _make_status_writer()
        snap = writer.snapshot()
        for key in ("schema", "written_at", "process", "state_manager",
                    "deck_runtime", "soundswitch", "mirror", "validation",
                    "commands", "recent_errors"):
            self.assertIn(key, snap, msg=f"missing key: {key}")

    def test_default_laser_status_is_a_copy(self) -> None:
        """Mutations to the returned dict must not affect the module default."""
        writer = _make_status_writer()
        snap = writer.snapshot()
        snap["laser_director"]["reason"] = "mutated"
        snap2 = writer.snapshot()
        self.assertEqual(snap2["laser_director"]["reason"], "not_configured")


# ---------------------------------------------------------------------------
# _invoke_callback and CommandReader failure reporting
# ---------------------------------------------------------------------------

class InvokeCallbackTests(unittest.TestCase):
    def test_returns_true_on_success(self) -> None:
        ok, detail = _invoke_callback(lambda: None)
        self.assertTrue(ok)
        self.assertEqual(detail, "")

    def test_returns_false_on_exception(self) -> None:
        def bad():
            raise RuntimeError("boom")
        ok, detail = _invoke_callback(bad)
        self.assertFalse(ok)
        self.assertIn("RuntimeError", detail)
        self.assertIn("boom", detail)

    def test_returns_false_when_callback_returns_false(self) -> None:
        ok, detail = _invoke_callback(lambda: False)
        self.assertFalse(ok)
        self.assertIn("returned False", detail)

    def test_returns_true_when_callback_returns_truthy(self) -> None:
        ok, detail = _invoke_callback(lambda: 42)
        self.assertTrue(ok)
        self.assertEqual(detail, "")


class CommandReaderCallbackFailureTests(unittest.TestCase):
    def test_smart_drop_exception_sets_last_error(self) -> None:
        def bad():
            raise RuntimeError("queue full")

        reader = CommandReader(Mock(), Mock(), smart_drop_toggle_callback=bad)
        reader.handle_command({"cmd": "toggle_smart_drop"})
        self.assertIn("toggle_smart_drop", reader.status()["last_error"])
        self.assertIn("RuntimeError", reader.status()["last_error"])
        self.assertIn("queue full", reader.status()["last_error"])

    def test_smart_drop_false_return_sets_last_error(self) -> None:
        reader = CommandReader(Mock(), Mock(), smart_drop_toggle_callback=lambda: False)
        reader.handle_command({"cmd": "toggle_smart_drop"})
        self.assertIn("toggle_smart_drop", reader.status()["last_error"])
        self.assertIn("returned False", reader.status()["last_error"])

    def test_smart_drop_success_clears_last_error(self) -> None:
        reader = CommandReader(Mock(), Mock(), smart_drop_toggle_callback=lambda: None)
        reader.handle_command({"cmd": "toggle_smart_drop"})
        self.assertEqual(reader.status()["last_error"], "")

    def test_smart_breakdown_exception_sets_last_error(self) -> None:
        def bad():
            raise RuntimeError("queue full")

        reader = CommandReader(Mock(), Mock(), smart_breakdown_toggle_callback=bad)
        reader.handle_command({"cmd": "toggle_smart_breakdown"})
        self.assertIn("toggle_smart_breakdown", reader.status()["last_error"])
        self.assertIn("RuntimeError", reader.status()["last_error"])
        self.assertIn("queue full", reader.status()["last_error"])

    def test_existing_toggle_smart_drop_no_callback_still_works(self) -> None:
        """No callback registered must not raise."""
        reader = CommandReader(Mock(), Mock())
        reader.handle_command({"cmd": "toggle_smart_drop"})
        self.assertEqual(reader.status()["last_error"], "")


# ---------------------------------------------------------------------------
# ValidationRunner — laser placeholder checks
# ---------------------------------------------------------------------------

_LASER_CHECK_NAMES = (
    "laser_config",
    "laser_safe_scene",
    "laser_emergency_scene",
    "laser_personality_refs",
    "laser_midi_dependency",
    "laser_midi_port",
    "laser_midi_queue",
)

_EXISTING_CHECK_NAMES = (
    "bridge_singleton",
    "soundswitch_connection",
    "rekordbox_process",
    "memory_deck_1",
    "memory_deck_2",
    "os2l_queue",
)


def _make_validation_runner():
    conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=10), _drop_count=0)
    sm = Mock()
    sm.snapshot.return_value = {
        "lighting_mode": "idle",
        "deck": {"1": {"filepath": "", "playing": False}, "2": {}},
    }
    live = Mock()
    live.get_status.return_value = None
    live.get_summary.return_value = SimpleNamespace(current_source="fallback")
    pos_cache = Mock()
    pos_cache.get.return_value = None  # no position snapshot — avoids format-spec errors on Mock
    return ValidationRunner(conn, pos_cache, live, sm, scripted_registry={})


class ValidationRunnerLaserPlaceholderTests(unittest.TestCase):
    def _run(self):
        runner = _make_validation_runner()
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            return runner.run()

    def test_all_laser_checks_present(self) -> None:
        result = self._run()
        names = {c.name for c in result.checks}
        for name in _LASER_CHECK_NAMES:
            self.assertIn(name, names, msg=f"missing check: {name}")

    def test_all_laser_checks_are_not_applicable(self) -> None:
        result = self._run()
        by_name = {c.name: c for c in result.checks}
        for name in _LASER_CHECK_NAMES:
            self.assertEqual(by_name[name].status, STATUS_NA, msg=f"{name} should be not_applicable")

    def test_existing_checks_still_present(self) -> None:
        result = self._run()
        names = {c.name for c in result.checks}
        for name in _EXISTING_CHECK_NAMES:
            self.assertIn(name, names, msg=f"pre-existing check missing: {name}")

    def test_result_state_is_done(self) -> None:
        result = self._run()
        self.assertEqual(result.state, "done")


if __name__ == "__main__":
    unittest.main()
