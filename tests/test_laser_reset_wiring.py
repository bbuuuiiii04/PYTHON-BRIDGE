"""Integration tests for the six StateManager -> laser reset-wiring sites (B3 / Task 3d).

These guard that StateManager actually calls reset_runtime_state on the director and
executor at every teardown transition, with the right reason, and with the deliberate
asymmetry that scripted/idle reset the DIRECTOR ONLY (the executor keeps its state on
those transitions). The director's own reset behavior is unit-tested in
test_laser_director_lifecycle.py; this file proves the wiring around it.
"""
from __future__ import annotations

import queue
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402


def _reasons(mock) -> list:
    return [c.kwargs.get("reason") for c in mock.reset_runtime_state.call_args_list]


class TestLaserResetWiring(unittest.TestCase):
    def setUp(self) -> None:
        self.sm = StateManager(queue.Queue(), PositionCache(), Mock())
        self.director = Mock()
        self.executor = Mock()
        self.sm._laser_director = self.director
        self.sm._laser_executor = self.executor

    def test_master_changed_resets_both(self) -> None:
        self.sm._on_master_changed(2, "test")
        self.director.reset_runtime_state.assert_any_call(reason="master_changed")
        self.executor.reset_runtime_state.assert_any_call(reason="master_changed")

    def test_track_loaded_resets_both(self) -> None:
        self.sm._os.active_deck = 1
        ev = types.SimpleNamespace(payload={}, source="test")
        self.sm._on_track_loaded(1, "title", ev)
        self.director.reset_runtime_state.assert_any_call(reason="active_track_loaded")
        self.executor.reset_runtime_state.assert_any_call(reason="active_track_loaded")

    def test_stop_resets_both(self) -> None:
        self.sm._do_stop(1, 1000)
        self.director.reset_runtime_state.assert_any_call(reason="stop")
        self.executor.reset_runtime_state.assert_any_call(reason="stop")

    def test_resume_resets_both(self) -> None:
        self.sm._do_resume(1, 1000, 120.0)
        self.director.reset_runtime_state.assert_any_call(reason="resume")
        self.executor.reset_runtime_state.assert_any_call(reason="resume")

    def test_scripted_resets_director_only(self) -> None:
        self.sm._arm_scripted = Mock()  # isolate the wiring from scripted arming
        self.sm._apply_lighting(1, "scripted", 1000, 120.0)
        self.director.reset_runtime_state.assert_any_call(reason="scripted")
        # Deliberate asymmetry: the executor is NOT reset on scripted transitions.
        self.executor.reset_runtime_state.assert_not_called()

    def test_idle_resets_director_only(self) -> None:
        self.sm._apply_lighting(1, "idle", 1000, 120.0)
        self.director.reset_runtime_state.assert_any_call(reason="idle")
        # Deliberate asymmetry: the executor is NOT reset on idle transitions.
        self.executor.reset_runtime_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
