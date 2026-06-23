from __future__ import annotations

import queue
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.__main__ import _build_laser_startup_wiring  # noqa: E402
from rb_ss_bridge_v2.laser_config import LaserConfig, LaserConfigResult  # noqa: E402
from rb_ss_bridge_v2.laser_models import LaserMidiMessage, LaserPersonality, LaserScene  # noqa: E402
from rb_ss_bridge_v2.laser_models import LaserContext, LaserSceneDecision  # noqa: E402
from rb_ss_bridge_v2.models import BridgeEvent, Ev  # noqa: E402
from rb_ss_bridge_v2.runtime_status import StatusWriter  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402
from rb_ss_bridge_v2.validation_runner import (  # noqa: E402
    STATUS_FAIL,
    STATUS_NA,
    STATUS_PASS,
    ValidationRunner,
)


def _scene(name: str) -> LaserScene:
    return LaserScene(
        name=name,
        scene_type="static",
        safety_class="safe",
        midi=LaserMidiMessage(kind="note_pulse", channel=1, note=36, velocity=127, duration_ms=80),
    )


def _config(*, enabled: bool, dry_run: bool = True, with_personality: bool = True) -> LaserConfig:
    scenes = {
        "safe_scene_cfg": _scene("safe_scene_cfg"),
        "startup_scene_cfg": _scene("startup_scene_cfg"),
        "default_scene_cfg": _scene("default_scene_cfg"),
        "emergency_scene_cfg": _scene("emergency_scene_cfg"),
    }
    personalities = {}
    default_personality = ""
    if with_personality:
        personalities["house"] = LaserPersonality(
            name="house",
            safe_scene="safe_scene_cfg",
            default_scene="default_scene_cfg",
            phrase_scene="default_scene_cfg",
            buildup_scene="default_scene_cfg",
            pre_drop_scene="default_scene_cfg",
            drop_scene="default_scene_cfg",
            post_drop_scene="default_scene_cfg",
            breakdown_scene="default_scene_cfg",
            transition_scene="default_scene_cfg",
            drop_lifecycle_mirror=False,
        )
        default_personality = "house"

    return LaserConfig(
        enabled=enabled,
        dry_run=dry_run,
        smart_drop_mode="blackout_mask",
        midi_output_port="IAC Driver Bus 1",
        scenes=scenes,
        personalities=personalities,
        default_personality=default_personality,
        startup_scene="startup_scene_cfg",
        stop_scene="safe_scene_cfg",
        stale_scene="safe_scene_cfg",
        emergency_scene="emergency_scene_cfg",
        fallback_scene="safe_scene_cfg",
    )


def _ctx(
    *,
    playing: bool = True,
    position_stale: bool = False,
    active_track_loaded: bool = True,
    autoloop_ready: bool = True,
) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=playing,
        elapsed_ms=1000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=8.0,
        position_stale=position_stale,
        lighting_mode="autoloop",
        os2l_connected=True,
        active_track_loaded=active_track_loaded,
        autoloop_ready=autoloop_ready,
    )


class LaserStartupWiringTests(unittest.TestCase):
    def test_not_configured_returns_no_director_and_no_provider(self) -> None:
        result = LaserConfigResult(available=False, reason="not_configured")

        bundle = _build_laser_startup_wiring(result)

        self.assertIsNone(bundle.laser_director)
        self.assertIsNone(bundle.status_provider)
        self.assertIsNone(bundle.midi_output)
        self.assertIsNone(bundle.laser_executor)

    def test_invalid_config_returns_error_provider(self) -> None:
        result = LaserConfigResult(
            available=False,
            reason="invalid_config",
            errors=("missing scenes", "invalid emergency_scene"),
        )

        bundle = _build_laser_startup_wiring(result)

        self.assertIsNone(bundle.laser_director)
        self.assertIsNotNone(bundle.status_provider)
        status = bundle.status_provider()
        self.assertEqual(status["reason"], "invalid_config")
        self.assertEqual(status["errors"], ["missing scenes", "invalid emergency_scene"])

    def test_valid_disabled_builds_director_disabled(self) -> None:
        result = LaserConfigResult(available=True, reason="ok", config=_config(enabled=False))
        bundle = _build_laser_startup_wiring(result)
        try:
            self.assertIsNotNone(bundle.laser_director)
            self.assertIsNotNone(bundle.status_provider)
            self.assertIsNotNone(bundle.laser_executor)
            self.assertIsNotNone(bundle.midi_output)
            self.assertFalse(bundle.status_provider()["enabled"])
            self.assertTrue(bundle.status_provider()["available"])
        finally:
            if bundle.midi_output is not None:
                bundle.midi_output.stop()

    def test_scene_mapping_uses_fallback_and_default_personality(self) -> None:
        result = LaserConfigResult(available=True, reason="ok", config=_config(enabled=True, with_personality=True))
        bundle = _build_laser_startup_wiring(result)
        assert bundle.laser_director is not None
        try:
            director = bundle.laser_director
            director.tick(_ctx(playing=False), now=time.monotonic())
            self.assertEqual(director.status()["current_scene"], "")
            self.assertEqual(director.status()["last_reason"], "not_playing")

            director.tick(_ctx(playing=True, position_stale=False), now=time.monotonic())
            self.assertEqual(director.status()["current_scene"], "default_scene_cfg")

            director.set_emergency_blackout(True)
            director.tick(_ctx(), now=time.monotonic())
            self.assertEqual(director.status()["current_scene"], "emergency_scene_cfg")
            self.assertIn("executor", bundle.status_provider())
        finally:
            if bundle.midi_output is not None:
                bundle.midi_output.stop()

    def test_default_scene_falls_back_to_startup_scene_without_default_personality(self) -> None:
        result = LaserConfigResult(available=True, reason="ok", config=_config(enabled=True, with_personality=False))
        bundle = _build_laser_startup_wiring(result)
        assert bundle.laser_director is not None
        try:
            director = bundle.laser_director
            director.tick(_ctx(playing=True, position_stale=False), now=time.monotonic())
            self.assertEqual(director.status()["current_scene"], "startup_scene_cfg")
        finally:
            if bundle.midi_output is not None:
                bundle.midi_output.stop()


class LaserValidationWiringTests(unittest.TestCase):
    def _runner(self, laser_result: LaserConfigResult, midi_output: Optional[object] = None) -> ValidationRunner:
        conn = SimpleNamespace(_connected=True, _send_q=queue.Queue(maxsize=16), _drop_count=0)
        pos_cache = Mock()
        pos_cache.get.return_value = None
        live_bpm = Mock()
        live_bpm.get_status.return_value = None
        live_bpm.get_summary.return_value = None
        sm = Mock()
        sm.snapshot.return_value = {"deck": {}, "lighting_mode": "idle"}
        return ValidationRunner(
            conn,
            pos_cache,
            live_bpm,
            sm,
            scripted_registry={},
            laser_config_result=laser_result,
            midi_output=midi_output,
        )

    def test_disabled_config_marks_all_laser_checks_not_applicable(self) -> None:
        runner = self._runner(LaserConfigResult(available=True, reason="ok", config=_config(enabled=False)))
        checks = []
        runner._check_laser(lambda name, status, detail="": checks.append((name, status, detail)))

        self.assertTrue(checks)
        self.assertTrue(all(status == STATUS_NA for _name, status, _detail in checks))
        self.assertTrue(all(detail == "disabled" for _name, _status, detail in checks))

    def test_not_configured_marks_all_laser_checks_not_applicable(self) -> None:
        runner = self._runner(LaserConfigResult(available=False, reason="not_configured"))
        checks = []
        runner._check_laser(lambda name, status, detail="": checks.append((name, status, detail)))

        self.assertTrue(all(status == STATUS_NA for _name, status, _detail in checks))
        self.assertTrue(all(detail == "not_configured" for _name, _status, detail in checks))

    def test_invalid_config_reports_laser_config_fail_only(self) -> None:
        runner = self._runner(
            LaserConfigResult(available=False, reason="invalid_config", errors=("bad config",))
        )
        checks = []
        runner._check_laser(lambda name, status, detail="": checks.append((name, status, detail)))

        first = checks[0]
        self.assertEqual(first[0], "laser_config")
        self.assertEqual(first[1], STATUS_FAIL)
        self.assertIn("bad config", first[2])
        for name, status, detail in checks[1:]:
            self.assertNotEqual(name, "laser_config")
            self.assertEqual(status, STATUS_NA)
            self.assertEqual(detail, "invalid_config")

    def test_enabled_config_reports_laser_midi_checks(self) -> None:
        midi = Mock()
        midi.status.return_value = {
            "running": True,
            "dry_run": True,
            "degraded": False,
            "degraded_reason": "",
            "port_name": "IAC Driver Bus 1",
            "queue_size": 0,
            "queue_max": 64,
            "drop_count": 0,
            "last_error": "",
        }
        runner = self._runner(
            LaserConfigResult(available=True, reason="ok", config=_config(enabled=True)),
            midi_output=midi,
        )
        checks = []
        runner._check_laser(lambda name, status, detail="": checks.append((name, status, detail)))

        check_map = {name: (status, detail) for name, status, detail in checks}
        self.assertEqual(check_map["laser_config"][0], STATUS_PASS)
        self.assertEqual(check_map["laser_midi_dependency"][0], STATUS_PASS)
        self.assertEqual(check_map["laser_midi_port"][0], STATUS_NA)
        self.assertEqual(check_map["laser_midi_queue"][0], STATUS_PASS)

    def test_existing_non_laser_validation_checks_still_present(self) -> None:
        runner = self._runner(LaserConfigResult(available=False, reason="not_configured"))
        with patch("rb_ss_bridge_v2.validation_runner._pgrep_count", return_value=1):
            result = runner.run().to_dict()
        check_names = {check["name"] for check in result["checks"]}
        self.assertIn("bridge_singleton", check_names)
        self.assertIn("soundswitch_connection", check_names)
        self.assertIn("rekordbox_process", check_names)
        self.assertIn("os2l_queue", check_names)
        self.assertIn("laser_config", check_names)


class RuntimeStatusLaserWiringTests(unittest.TestCase):
    def test_snapshot_contains_laser_director_not_configured_default(self) -> None:
        sm = Mock()
        sm.snapshot.return_value = {"deck": {}}
        live_bpm = Mock()
        live_bpm.get_status.return_value = None
        live_bpm.get_summary.return_value = None
        pos_cache = Mock()
        pos_cache.get.return_value = None
        conn = Mock()
        conn.status.return_value = {"connected": False}
        validation_runner = Mock()
        validation_runner.last_result.return_value.to_dict.return_value = {"state": "idle"}
        command_reader = Mock()
        command_reader.status.return_value = {}
        writer = StatusWriter(
            sm,
            live_bpm,
            pos_cache,
            conn,
            validation_runner,
            command_reader,
        )

        snapshot = writer.snapshot()

        self.assertIn("laser_director", snapshot)
        self.assertEqual(
            snapshot["laser_director"],
            {"available": False, "enabled": False, "reason": "not_configured"},
        )


class LaserPersonalityUnknownNameTests(unittest.TestCase):
    def test_unknown_personality_does_not_wipe_executor_personality(self) -> None:
        cfg = _config(enabled=True, dry_run=True, with_personality=True)
        bundle = _build_laser_startup_wiring(LaserConfigResult(available=True, reason="ok", config=cfg))
        assert bundle.laser_director is not None
        assert bundle.laser_executor is not None
        assert bundle.personality_provider is not None
        midi_output = bundle.midi_output
        try:
            sm = StateManager(
                queue.Queue(maxsize=8),
                Mock(),
                Mock(),
                live_bpm=Mock(),
                laser_director=bundle.laser_director,
                laser_executor=bundle.laser_executor,
                laser_personality_provider=bundle.personality_provider,
            )
            before = bundle.laser_executor.status()
            self.assertTrue(before["role_cursors"])
            self.assertEqual(before["role_cursors"]["drop"], 0)

            bundle.laser_executor.on_decision(
                LaserSceneDecision(
                    scene="default_scene_cfg",
                    reason="drop_crossing",
                    priority=9,
                    source="policy",
                    role="drop",
                ),
                _ctx(),
            )
            bundle.laser_executor.on_decision(
                LaserSceneDecision(
                    scene="default_scene_cfg",
                    reason="post_drop_hold",
                    priority=10,
                    source="policy",
                    role="post_drop",
                ),
                _ctx(),
            )
            bundle.laser_executor.on_decision(
                LaserSceneDecision(
                    scene="default_scene_cfg",
                    reason="drop_crossing",
                    priority=9,
                    source="policy",
                    role="drop",
                ),
                _ctx(),
            )
            before = bundle.laser_executor.status()
            self.assertGreater(before["role_cursors"]["drop"], 0)
            sm._handle_event(
                BridgeEvent(
                    kind=Ev.LASER_SET_PERSONALITY,
                    deck=0,
                    payload={"personality": "missing_name"},
                    source="test",
                )
            )
            after = bundle.laser_executor.status()
            self.assertEqual(after["role_cursors"]["drop"], before["role_cursors"]["drop"])
        finally:
            if midi_output is not None:
                midi_output.stop()


if __name__ == "__main__":
    unittest.main()
