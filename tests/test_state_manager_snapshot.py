import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import SmartPhrasingState  # noqa: E402
from rb_ss_bridge_v2.state_manager import STATE_MANAGER_PROFILE_ENV, StateManager  # noqa: E402


def _sp_state(**overrides) -> SmartPhrasingState:
    defaults = dict(
        current_phrase_label="other",
        current_phrase_is_up=False,
        current_phrase_is_chorus=False,
        current_phrase_is_low=False,
        next_smart_drop_beat=None,
        beats_to_next_drop=None,
        smart_drop_window_active=False,
        smart_drop_crossing=False,
        smart_drop_preclear_requested=False,
        smart_drop_rearm_requested=False,
        smart_post_drop_active=False,
        active_drop_beat=None,
        smart_buildup_active=False,
        smart_breakdown_active=False,
        breakdown_start_crossing=False,
        breakdown_end_crossing=False,
        smart_breakdown_clear_requested=False,
        smart_breakdown_restore_requested=False,
        transition_mask_should_arm=False,
        transition_mask_should_clear=False,
        transition_window_active=False,
        phrase_anchor_requested=False,
        phrase_anchor_preclear_requested=False,
        phrase_anchor_rearm_requested=False,
        phrase_anchor_target_beat=None,
        reason="test",
        breakdown_restore_beat=None,
    )
    defaults.update(overrides)
    return SmartPhrasingState(**defaults)


class StateManagerSnapshotTests(unittest.TestCase):
    def test_state_manager_profiler_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {STATE_MANAGER_PROFILE_ENV: "0"}):
            sm = StateManager(queue.Queue(), PositionCache(), Mock())

        self.assertIsNone(sm._profiler)

    def test_state_manager_profiler_enabled_by_env(self) -> None:
        with patch.dict("os.environ", {STATE_MANAGER_PROFILE_ENV: "1"}):
            sm = StateManager(queue.Queue(), PositionCache(), Mock())

        self.assertIsNotNone(sm._profiler)

    def test_snapshot_available_before_cadence_publish(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())

        snap = sm.snapshot()

        self.assertIn("active_deck", snap)
        self.assertIn("deck", snap)
        self.assertIn("1", snap["deck"])

    def test_snapshot_returns_copy_of_published_state(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._deck[1].playing = True
        sm._deck[1].meta.filepath = "/music/a.mp3"
        sm._deck[1].meta.bpm = 128.0
        sm._deck[1].scripted_id = 12
        sm._os.active_deck = 1
        sm._os.lighting_mode = "scripted"
        sm._publish_snapshot()

        first = sm.snapshot()
        first["deck"]["1"]["filepath"] = "mutated"
        second = sm.snapshot()

        self.assertEqual(second["active_deck"], 1)
        self.assertEqual(second["lighting_mode"], "scripted")
        self.assertEqual(second["deck"]["1"]["filepath"], "/music/a.mp3")
        self.assertEqual(second["deck"]["1"]["scripted_id"], 12)

    def test_snapshot_publish_skips_before_cadence_deadline(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        initial = sm.snapshot()
        sm._deck[1].meta.filepath = "/music/changed.mp3"

        did_publish = sm._maybe_publish_snapshot(sm._next_snapshot_publish_at - 0.001)
        current = sm.snapshot()

        self.assertFalse(did_publish)
        self.assertEqual(current["deck"]["1"]["filepath"], initial["deck"]["1"]["filepath"])

    def test_snapshot_publish_updates_at_cadence_deadline(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._deck[1].meta.filepath = "/music/changed.mp3"
        deadline = sm._next_snapshot_publish_at

        did_publish = sm._maybe_publish_snapshot(deadline)
        current = sm.snapshot()

        self.assertTrue(did_publish)
        self.assertEqual(current["deck"]["1"]["filepath"], "/music/changed.mp3")
        self.assertGreater(sm._next_snapshot_publish_at, deadline)

    def test_snapshot_safe_when_laser_executor_is_none(self) -> None:
        """_publish_snapshot should not crash if _laser_executor is None."""
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._laser_executor = None
        sm._os.drop_cut_armed = True
        # Must not raise.
        sm._publish_snapshot()
        snap = sm.snapshot()
        # transition-window reflects drop_cut_armed.
        self.assertTrue(snap["smart_drop_transition_window_active"])
        # blackout-active is False when no executor is present.
        self.assertFalse(snap["smart_drop_blackout_active"])

    def test_snapshot_safe_when_laser_executor_is_none_not_armed(self) -> None:
        """Snapshot distinguishes non-armed state from absent executor."""
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._laser_executor = None
        sm._os.drop_cut_armed = False
        sm._publish_snapshot()
        snap = sm.snapshot()
        self.assertFalse(snap["smart_drop_transition_window_active"])
        self.assertFalse(snap["smart_drop_blackout_active"])

    def test_snapshot_smart_phrasing_is_none_until_first_update(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        snap = sm.snapshot()
        self.assertIn("smart_phrasing", snap)
        self.assertIsNone(snap["smart_phrasing"])

    def test_snapshot_smart_phrasing_publishes_cached_state(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._last_sp_state = _sp_state(
            current_phrase_label="up",
            current_phrase_is_up=True,
            next_smart_drop_beat=128.0,
            beats_to_next_drop=32.0,
            transition_window_active=True,
            phrase_anchor_target_beat=192,
            reason="tick",
        )
        sm._publish_snapshot()
        snap = sm.snapshot()["smart_phrasing"]
        self.assertEqual(snap["phrase_label"], "up")
        self.assertTrue(snap["is_up"])
        self.assertEqual(snap["next_smart_drop_beat"], 128.0)
        self.assertEqual(snap["beats_to_next_drop"], 32.0)
        self.assertTrue(snap["transition_window_active"])
        self.assertEqual(snap["phrase_anchor_target_beat"], 192)
        self.assertEqual(snap["reason"], "tick")

    def test_snapshot_smart_phrasing_reflects_breakdown_active(self) -> None:
        sm = StateManager(queue.Queue(), PositionCache(), Mock())
        sm._last_sp_state = _sp_state(
            current_phrase_label="low",
            current_phrase_is_low=True,
            smart_breakdown_active=True,
            reason="breakdown",
        )
        sm._publish_snapshot()
        snap = sm.snapshot()["smart_phrasing"]
        self.assertEqual(snap["phrase_label"], "low")
        self.assertTrue(snap["is_low"])
        self.assertTrue(snap["smart_breakdown_active"])
        self.assertEqual(snap["reason"], "breakdown")


if __name__ == "__main__":
    unittest.main()
