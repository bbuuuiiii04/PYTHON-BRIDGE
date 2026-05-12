import queue
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import PositionSnapshot  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.validation_runner import (  # noqa: E402
    STATUS_NA,
    STATUS_PASS,
    STATUS_WARN,
    STATUS_WARMING,
    ValidationRunner,
)


class ValidationRunnerTests(unittest.TestCase):
    def _make_laser_runner(self, *, laser_config_result, laser_status_provider=None):
        conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=10), _drop_count=0)
        cache = PositionCache()
        live = Mock()
        live.get_status.return_value = None
        live.get_summary.return_value = SimpleNamespace(current_source="fallback")
        sm = Mock()
        sm.snapshot.return_value = {
            "lighting_mode": "autoloop",
            "autoloop_arm_pending": False,
            "deck": {
                "1": {"filepath": "/music/a.mp3", "playing": True, "scripted_id": 0},
                "2": {"filepath": "", "playing": False, "scripted_id": 0},
            },
        }
        midi_output = Mock()
        midi_output.status.return_value = {
            "queue_size": 0,
            "queue_max": 256,
            "drop_count": 0,
            "degraded_reason": "",
            "port_name": "IAC Driver Bus 1",
        }
        return ValidationRunner(
            conn,
            cache,
            live,
            sm,
            scripted_registry={},
            laser_config_result=laser_config_result,
            midi_output=midi_output,
            laser_status_provider=laser_status_provider,
        )

    def test_contextual_live_bpm_and_memory_statuses(self) -> None:
        conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=10), _drop_count=0)
        cache = PositionCache()
        cache.update(PositionSnapshot(deck=1, elapsed_ms=1000, playing=True, updated_at=time.monotonic()))
        live = Mock()
        live.get_status.side_effect = lambda deck: (
            SimpleNamespace(valid=True, bpm=128.0, source="offset_table") if deck == 1 else None
        )
        live.get_summary.return_value = SimpleNamespace(current_source="fallback")
        sm = Mock()
        sm.snapshot.return_value = {
            "lighting_mode": "autoloop",
            "autoloop_arm_pending": False,
            "deck": {
                "1": {"filepath": "/music/a.mp3", "playing": True, "scripted_id": 0},
                "2": {"filepath": "", "playing": False, "scripted_id": 0},
            },
        }
        runner = ValidationRunner(conn, cache, live, sm, scripted_registry={})

        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            result = runner.run().to_dict()

        checks = {check["name"]: check for check in result["checks"]}
        self.assertEqual(checks["memory_deck_1"]["status"], STATUS_PASS)
        self.assertEqual(checks["memory_deck_2"]["status"], STATUS_NA)
        self.assertEqual(checks["live_bpm_deck_1"]["status"], STATUS_PASS)
        self.assertEqual(checks["live_bpm_deck_2"]["status"], STATUS_NA)
        self.assertEqual(checks["autoloop"]["status"], STATUS_PASS)

    def test_loaded_deck_without_live_bpm_is_warming(self) -> None:
        conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=10), _drop_count=0)
        cache = PositionCache()
        live = Mock()
        live.get_status.return_value = None
        live.get_summary.return_value = SimpleNamespace(current_source="fallback")
        sm = Mock()
        sm.snapshot.return_value = {
            "lighting_mode": "idle",
            "deck": {"1": {"filepath": "/music/a.mp3", "playing": False}, "2": {}},
        }
        runner = ValidationRunner(conn, cache, live, sm, scripted_registry={})

        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}

        self.assertEqual(checks["live_bpm_deck_1"].status, STATUS_WARMING)
        self.assertEqual(checks["soundswitch_connection"].status, STATUS_PASS)

    def test_disconnected_soundswitch_warns(self) -> None:
        conn = SimpleNamespace(_connected=False, _send_q=queue.Queue(maxsize=10), _drop_count=0)
        runner = ValidationRunner(conn, PositionCache(), Mock(), Mock(), scripted_registry={})

        self.assertEqual(runner._check_soundswitch()[0], STATUS_WARN)

    def test_laser_director_runtime_not_applicable_when_not_configured(self) -> None:
        laser_result = SimpleNamespace(reason="not_configured", config=None, errors=())
        runner = self._make_laser_runner(
            laser_config_result=laser_result,
            laser_status_provider=lambda: {"available": False, "reason": "not_configured"},
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_NA)
        self.assertEqual(checks["laser_director_runtime"].detail, "not_configured")

    def test_laser_director_runtime_pass_when_enabled_and_healthy(self) -> None:
        laser_result = SimpleNamespace(
            reason="ok",
            config=SimpleNamespace(
                enabled=True,
                dry_run=False,
                fallback_scene="safe_static",
                emergency_scene="emergency_blackout",
            ),
            errors=(),
        )
        runner = self._make_laser_runner(
            laser_config_result=laser_result,
            laser_status_provider=lambda: {
                "available": True,
                "enabled": True,
                "current_scene": "house_phrase_1",
                "executor": {"midi": {}},
            },
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_PASS)
        self.assertIn("scene=house_phrase_1", checks["laser_director_runtime"].detail)

    def test_laser_director_runtime_warn_on_emergency(self) -> None:
        laser_result = SimpleNamespace(
            reason="ok",
            config=SimpleNamespace(
                enabled=True,
                dry_run=False,
                fallback_scene="safe_static",
                emergency_scene="emergency_blackout",
            ),
            errors=(),
        )
        runner = self._make_laser_runner(
            laser_config_result=laser_result,
            laser_status_provider=lambda: {
                "available": True,
                "enabled": True,
                "emergency": True,
                "executor": {"midi": {}},
            },
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_WARN)
        self.assertEqual(checks["laser_director_runtime"].detail, "emergency_blackout_latched")

    def test_laser_director_runtime_warn_on_midi_degraded(self) -> None:
        laser_result = SimpleNamespace(
            reason="ok",
            config=SimpleNamespace(
                enabled=True,
                dry_run=False,
                fallback_scene="safe_static",
                emergency_scene="emergency_blackout",
            ),
            errors=(),
        )
        runner = self._make_laser_runner(
            laser_config_result=laser_result,
            laser_status_provider=lambda: {
                "available": True,
                "enabled": True,
                "executor": {"midi": {"degraded_reason": "dependency_missing"}},
            },
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_WARN)
        self.assertEqual(checks["laser_director_runtime"].detail, "dependency_missing")

    def test_laser_director_runtime_warn_on_last_error(self) -> None:
        laser_result = SimpleNamespace(
            reason="ok",
            config=SimpleNamespace(
                enabled=True,
                dry_run=False,
                fallback_scene="safe_static",
                emergency_scene="emergency_blackout",
            ),
            errors=(),
        )
        runner = self._make_laser_runner(
            laser_config_result=laser_result,
            laser_status_provider=lambda: {
                "available": True,
                "enabled": True,
                "last_error": "midi_trigger_rejected",
                "executor": {"midi": {}},
            },
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_WARN)
        self.assertEqual(checks["laser_director_runtime"].detail, "midi_trigger_rejected")

    def test_laser_director_runtime_not_applicable_when_midi_not_wired(self) -> None:
        laser_result = SimpleNamespace(
            reason="ok",
            config=SimpleNamespace(
                enabled=True,
                dry_run=False,
                fallback_scene="safe_static",
                emergency_scene="emergency_blackout",
            ),
            errors=(),
        )
        conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=10), _drop_count=0)
        cache = PositionCache()
        live = Mock()
        live.get_status.return_value = None
        live.get_summary.return_value = SimpleNamespace(current_source="fallback")
        sm = Mock()
        sm.snapshot.return_value = {
            "lighting_mode": "autoloop",
            "autoloop_arm_pending": False,
            "deck": {
                "1": {"filepath": "/music/a.mp3", "playing": True, "scripted_id": 0},
                "2": {"filepath": "", "playing": False, "scripted_id": 0},
            },
        }
        runner = ValidationRunner(
            conn,
            cache,
            live,
            sm,
            scripted_registry={},
            laser_config_result=laser_result,
            midi_output=None,
            laser_status_provider=lambda: {"available": True, "enabled": True},
        )
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            checks = {c.name: c for c in runner.run().checks}
        self.assertEqual(checks["laser_director_runtime"].status, STATUS_NA)
        self.assertEqual(checks["laser_director_runtime"].detail, "not_wired")


if __name__ == "__main__":
    unittest.main()
