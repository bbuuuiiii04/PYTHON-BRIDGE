import sys
import os
import queue
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import (  # noqa: E402
    BridgeEvent, DeckState, Ev, OutputState, PositionSnapshot, SmartDropEnergyShadow, TrackMetadata,
)
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import (  # noqa: E402
    StateManager,
    _phrase_anchor_tick,
    _send_direct_autoloop_rearm,
    _select_smart_drops,
    _smart_drop_tick,
    _smart_breakdown_tick,
)


def _sm(drops=None, filepath="/music/drop.mp3"):
    out = Mock()
    deck = DeckState(number=1)
    deck.meta.filepath = filepath
    deck.meta.bpm = 130.0
    deck.meta.first_beat_ms = 0.0
    deck.meta.beatgrid_times_ms = [i * 500.0 for i in range(160)]
    deck.meta.anlz_drops = list(drops or [])
    deck.meta.smart_drops = list(drops or [])
    sm = SimpleNamespace(
        _os=OutputState(lighting_mode="autoloop"),
        _deck={1: deck, 2: DeckState(number=2)},
        _out=out,
    )
    sm._autoloop_target_elapsed_for_beat = Mock(
        side_effect=lambda beat, _elapsed, _bpm, _meta: (beat * 500, "grid")
    )
    sm._send_autoloop_deck_load = Mock()
    return sm


def _manager(env=None):
    env = env or {}
    with patch.dict(os.environ, env, clear=False):
        return StateManager(queue.Queue(), PositionCache(), Mock())


def _arm_drop_cut(sm):
    sm._os.drop_cut_armed = True
    sm._os.drop_rearm_beat = 64
    sm._os.phrase_anchor_last_beat = 64


class SmartRearmFlagTests(unittest.TestCase):
    def test_global_switch_off_disables_both(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "0",
            "RBSS_SMART_DROP": "1",
            "RBSS_PHRASE_ANCHOR": "1",
        })
        self.assertFalse(sm._smart_rearm_experiment)
        self.assertFalse(sm._smart_drop_enabled)
        self.assertFalse(sm._phrase_anchor_enabled)

    def test_global_switch_on_enables_defaults(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "1",
            "RBSS_PHRASE_ANCHOR": "1",
        })
        self.assertTrue(sm._smart_rearm_experiment)
        self.assertTrue(sm._smart_drop_enabled)
        self.assertTrue(sm._phrase_anchor_enabled)

    def test_experiment_off_skips_anlz_worker(self) -> None:
        sm = _manager({"RBSS_SMART_REARM_EXPERIMENT": "0"})
        resolver = Mock()
        sm.attach_resolver(resolver)
        sm._pending_anlz_path[1] = "/tmp/ANLZ0000.EXT"
        with patch("rb_ss_bridge_v2.state_manager.threading.Thread") as thread:
            sm._on_track_loaded(1, "track", BridgeEvent(Ev.TRACK_LOADED, 1))
        resolver.resolve_by_anlz.assert_called_once()
        thread.assert_not_called()

    def test_smart_drop_kill_switch_disables_cut(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "0",
            "RBSS_PHRASE_ANCHOR": "1",
        })
        self.assertFalse(sm._smart_drop_enabled)
        self.assertTrue(sm._phrase_anchor_enabled)

    def test_phrase_anchor_kill_switch_disables_anchor(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "1",
            "RBSS_PHRASE_ANCHOR": "0",
        })
        self.assertTrue(sm._smart_drop_enabled)
        self.assertFalse(sm._phrase_anchor_enabled)

    def test_smart_breakdown_kill_switch_disables_breakdown(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_BREAKDOWN": "0",
        })
        self.assertFalse(sm._smart_breakdown_enabled)

    def test_toggle_smart_drop_flips_runtime_state(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "0",
        })
        self.assertFalse(sm._smart_drop_enabled)
        sm.toggle_smart_drop()
        self.assertTrue(sm._smart_drop_enabled)

    def test_toggle_smart_drop_off_clears_pending_cut(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "1",
        })
        _arm_drop_cut(sm)
        sm.toggle_smart_drop()
        self.assertFalse(sm._smart_drop_enabled)
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_toggle_smart_drop_ignored_when_experiment_off(self) -> None:
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "0",
            "RBSS_SMART_DROP": "0",
        })
        sm.toggle_smart_drop()
        self.assertFalse(sm._smart_drop_enabled)


class SmartRearmResetTests(unittest.TestCase):
    def test_clear_smart_rearm_state_clears_pending_blackout_window(self) -> None:
        sm = _manager()
        sm._laser_executor = Mock()
        sm._clear_smart_rearm_state()
        sm._laser_executor.clear_pending_blackout.assert_called_once_with(
            reason="smart_rearm_state_cleared"
        )

    def test_drop_cut_cleared_on_idle_transition(self) -> None:
        sm = _manager()
        _arm_drop_cut(sm)
        sm._apply_lighting(1, "idle", 0, 130.0)
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)
        self.assertEqual(sm._os.phrase_anchor_last_beat, -1)

    def test_executor_runtime_state_resets_on_master_change(self) -> None:
        sm = _manager()
        sm._laser_executor = Mock()
        sm._on_master_changed(2, "test")
        sm._laser_executor.reset_runtime_state.assert_called_once_with(
            reason="master_changed"
        )

    def test_master_change_clears_smart_drop_rearm_flags(self) -> None:
        sm = _manager()
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 64
        sm._on_master_changed(2, "test")
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_executor_runtime_state_resets_on_active_track_loaded(self) -> None:
        sm = _manager()
        sm._laser_executor = Mock()
        sm._on_track_loaded(1, "track", BridgeEvent(Ev.TRACK_LOADED, 1))
        sm._laser_executor.reset_runtime_state.assert_called_once_with(
            reason="active_track_loaded"
        )

    def test_executor_runtime_state_resets_on_stop(self) -> None:
        sm = _manager()
        sm._laser_executor = Mock()
        sm._do_stop(1, 1000)
        sm._laser_executor.reset_runtime_state.assert_called_once_with(
            reason="stop"
        )

    def test_drop_cut_cleared_on_scripted_transition(self) -> None:
        sm = _manager()
        sm._deck[1].scripted_id = 12
        _arm_drop_cut(sm)
        sm._apply_lighting(1, "scripted", 0, 150.0)
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_drop_cut_cleared_on_active_track_load(self) -> None:
        sm = _manager()
        _arm_drop_cut(sm)
        sm._on_track_loaded(1, "track", BridgeEvent(Ev.TRACK_LOADED, 1))
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_drop_cut_cleared_on_master_change(self) -> None:
        sm = _manager()
        _arm_drop_cut(sm)
        sm._on_master_changed(2, "test")
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_drop_cut_cleared_on_rb_restart(self) -> None:
        sm = _manager()
        _arm_drop_cut(sm)
        sm._handle_event(BridgeEvent(Ev.RB_RESTARTED, 0, {"pid": 123}))
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)


class SmartDropTests(unittest.TestCase):
    def test_selector_preserves_middle_drops_without_clustering(self) -> None:
        selected = _select_smart_drops(
            [64, 80, 96, 196, 372, 404],
            total_beats=597,
        )
        self.assertEqual(selected, [64, 80, 96, 196, 372, 404])

    def test_selector_filters_intro_drops(self) -> None:
        selected = _select_smart_drops([8, 16, 32, 64], total_beats=160)
        self.assertEqual(selected, [32, 64])

    def test_selector_filters_outro_when_total_beats_known(self) -> None:
        selected = _select_smart_drops([64, 560, 580], total_beats=597)
        self.assertEqual(selected, [64, 560])

    def test_selector_skips_outro_filter_without_total_beats(self) -> None:
        selected = _select_smart_drops([64, 580], total_beats=0)
        self.assertEqual(selected, [64, 580])

    def test_selector_sorts_and_dedupes(self) -> None:
        selected = _select_smart_drops([96, 64, 64, 80], total_beats=160)
        self.assertEqual(selected, [64, 80, 96])

    def test_anlz_data_stores_raw_selected_and_energy_shadow(self) -> None:
        sm = _manager({"RBSS_SMART_REARM_EXPERIMENT": "1"})
        sm._deck[1].load_gen = 7
        sm._deck[1].meta.beatgrid_times_ms = [i * 500.0 for i in range(100)]
        shadow = [
            SmartDropEnergyShadow(8, 12, 4_000, 6_000, 0.1, 0.3, 0.2),
            SmartDropEnergyShadow(32, 40, 16_000, 20_000, 0.2, 0.4, 0.2),
            SmartDropEnergyShadow(64, 64, 32_000, 32_000, 0.5, 0.5, 0.0),
            SmartDropEnergyShadow(96, 100, 48_000, 50_000, 0.1, 0.6, 0.5),
        ]

        sm._handle_event(BridgeEvent(
            Ev.ANLZ_DATA,
            1,
            {
                "drop_beat_indices": [8, 32, 64, 96],
                "energy_shadow": shadow,
                "load_gen": 7,
            },
        ))

        self.assertEqual(sm._deck[1].meta.anlz_drops, [8, 32, 64, 96])
        self.assertEqual(sm._deck[1].meta.smart_drops, [32, 64])
        self.assertEqual(
            [item.anlz_beat for item in sm._deck[1].meta.smart_drop_energy_shadow],
            [32, 64],
        )

    def test_energy_shadow_log_uses_elapsed_timestamps(self) -> None:
        sm = _manager({"RBSS_SMART_REARM_EXPERIMENT": "1"})
        sm._deck[1].load_gen = 7

        with self.assertLogs("state_manager", level="INFO") as captured:
            sm._handle_event(BridgeEvent(
                Ev.ANLZ_DATA,
                1,
                {
                    "drop_beat_indices": [32],
                    "energy_shadow": [SmartDropEnergyShadow(
                        32, 40, 16_000, 20_000, 0.2, 0.4, 0.2
                    )],
                    "load_gen": 7,
                },
            ))

        output = "\n".join(captured.output)
        self.assertIn("anlz_elapsed=0:16.000", output)
        self.assertIn("suggested_elapsed=0:20.000", output)
        self.assertNotIn("suggested=40", output)

    def test_anlz_data_accepts_breakdowns_and_buildups(self) -> None:
        sm = _manager({"RBSS_SMART_REARM_EXPERIMENT": "1"})
        sm._deck[1].load_gen = 7
        sm._deck[1].meta.beatgrid_times_ms = [i * 500.0 for i in range(320)]

        sm._handle_event(BridgeEvent(
            Ev.ANLZ_DATA,
            1,
            {
                "drop_beat_indices": [32, 160, 192, 328],
                "breakdown_beat_indices": [64, 224],
                "buildup_beat_indices": [96, 112, 144, 232],
                "mood": 1,
                "load_gen": 7,
            },
        ))

        self.assertEqual(sm._deck[1].meta.anlz_breakdowns, [64, 224])
        self.assertEqual(sm._deck[1].meta.smart_breakdowns, [64, 224])
        self.assertEqual(sm._deck[1].meta.anlz_buildups, [96, 112, 144, 232])
        self.assertEqual(sm._deck[1].meta.anlz_mood, 1)

    def test_stale_anlz_data_does_not_mutate_drop_lists(self) -> None:
        sm = _manager({"RBSS_SMART_REARM_EXPERIMENT": "1"})
        sm._deck[1].load_gen = 7
        sm._deck[1].meta.anlz_drops = [64]
        sm._deck[1].meta.smart_drops = [64]
        sm._deck[1].meta.smart_drop_energy_shadow = [
            SmartDropEnergyShadow(64, 64, 32_000, 32_000, 0.5, 0.5, 0.0)
        ]

        sm._handle_event(BridgeEvent(
            Ev.ANLZ_DATA,
            1,
            {"drop_beat_indices": [96], "load_gen": 6},
        ))

        self.assertEqual(sm._deck[1].meta.anlz_drops, [64])
        self.assertEqual(sm._deck[1].meta.smart_drops, [64])
        self.assertEqual(
            [item.anlz_beat for item in sm._deck[1].meta.smart_drop_energy_shadow],
            [64],
        )

    def test_track_metadata_clear_clears_raw_selected_and_shadow_drops(self) -> None:
        meta = TrackMetadata(
            anlz_drops=[64],
            smart_drops=[64],
            smart_drop_energy_shadow=[
                SmartDropEnergyShadow(64, 64, 32_000, 32_000, 0.5, 0.5, 0.0)
            ],
        )
        meta.clear()
        self.assertEqual(meta.anlz_drops, [])
        self.assertEqual(meta.smart_drops, [])
        self.assertEqual(meta.smart_drop_energy_shadow, [])

    def test_runtime_uses_selected_drops_not_raw_anlz_drops(self) -> None:
        sm = _sm([64])
        sm._deck[1].meta.smart_drops = [96]
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 92, 46_000), 1)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 96)

    def test_intro_filtered_raw_drop_does_not_fire(self) -> None:
        sm = _sm([16])
        sm._deck[1].meta.smart_drops = []
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 12, 6_000), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_smart_drop_skipped_while_transition_arm_pending(self) -> None:
        sm = _sm([64])
        sm._os.autoloop_arm_pending = True
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_smart_drop_skipped_while_pending_arm_meta_set(self) -> None:
        sm = _sm([64])
        sm._os.pending_autoloop_arm_meta = TrackMetadata(filepath="/music/pending.mp3")
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_smart_drop_skipped_while_breakdown_active(self) -> None:
        sm = _sm([68])
        sm._os.breakdown_active = True
        sm._os.breakdown_restore_beat = 96
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 64, 32_000), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_pre_drop_blackout_arms_4_beats_before_drop_without_os2l_cut(self) -> None:
        sm = _sm([64])
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 60, 30_000), 1)
        self.assertEqual(sm._out.send_deck_clear.call_count, 0)
        self.assertEqual(sm._out.send_loop_off.call_count, 0)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 64)

    def test_blackout_mode_crossing_relies_on_post_phrase_anchor_cleanup_order(self) -> None:
        sm = _sm([64])
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 64
        sm._os.phrase_anchor_last_beat = 0
        # Keep drop_cut_armed true through phrase-anchor processing so same-beat
        # phrase-anchor rearm is suppressed before crossing cleanup clears flags.
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 64, 32_005), 2)
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_005, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_cut_does_not_fire_before_window(self) -> None:
        sm = _sm([64])
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 55, 27_500), 0)
        sm._out.send_deck_clear.assert_not_called()
        self.assertFalse(sm._os.drop_cut_armed)

    def test_drop_crossing_returns_signal_without_direct_rearm(self) -> None:
        sm = _sm([64])
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 64
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 64, 32_005), 2)
        sm._send_autoloop_deck_load.assert_not_called()
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 64)
        self.assertEqual(sm._os.phrase_anchor_last_beat, -1)

    def test_smart_drop_crossing_blocks_same_beat_phrase_anchor_rearm(self) -> None:
        sm = _sm([64])
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 64
        sm._os.phrase_anchor_last_beat = 0
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 64, 32_005), 2)
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_005, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_smart_drop_crossing_does_not_update_phrase_anchor_directly(self) -> None:
        sm = _sm([60])
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 60
        sm._os.phrase_anchor_last_beat = 0
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 60, 30_005), 2)
        self.assertEqual(sm._os.phrase_anchor_last_beat, 0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_past_drops_scanned_but_ignored(self) -> None:
        sm = _sm([32, 64, 128])
        self.assertEqual(_smart_drop_tick(sm, 1, 2, 130.0, 124, 62_000), 1)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 128)

    def test_legacy_mode_uses_cut_and_rearm_when_explicitly_selected(self) -> None:
        sm = _sm([64])
        signal = _smart_drop_tick(
            sm, 1, 2, 130.0, 60, 30_000, blackout_mode=False
        )
        self.assertEqual(signal, 1)
        self.assertEqual(sm._out.send_deck_clear.call_count, 4)
        self.assertEqual(sm._out.send_loop_off.call_count, 4)
        self.assertTrue(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 64)

        signal = _smart_drop_tick(
            sm, 1, 2, 130.0, 64, 32_005, blackout_mode=False
        )
        self.assertEqual(signal, 2)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._os.drop_rearm_beat, 0)

    def test_rearm_uses_autoloop_arm_bpm(self) -> None:
        sm = _sm([64])
        sm._os.autoloop_arm_bpm = 130.5
        _send_direct_autoloop_rearm(sm, 1, 2, 131.0, 32_005, "test", target_beat=64)
        arm_meta = sm._send_autoloop_deck_load.call_args.args[3]
        self.assertEqual(arm_meta.bpm, 130.5)

    def test_rearm_falls_back_to_push_bpm_when_arm_bpm_zero(self) -> None:
        sm = _sm([64])
        sm._os.autoloop_arm_bpm = 0.0
        _send_direct_autoloop_rearm(sm, 1, 2, 131.0, 32_005, "test", target_beat=64)
        arm_meta = sm._send_autoloop_deck_load.call_args.args[3]
        self.assertEqual(arm_meta.bpm, 131.0)

    def test_rearm_uses_target_elapsed_for_drop_beat(self) -> None:
        sm = _sm([64])
        _send_direct_autoloop_rearm(sm, 1, 2, 131.0, 32_125, "test", target_beat=64)
        arm_meta = sm._send_autoloop_deck_load.call_args.args[3]
        self.assertEqual(arm_meta.elapsed_ms, 32_000)


class SmartDropBlackoutFallbackTests(unittest.TestCase):
    def _prepare_manager(self):
        sm = _manager({
            "RBSS_SMART_REARM_EXPERIMENT": "1",
            "RBSS_SMART_DROP": "1",
        })
        deck = sm._deck[1]
        deck.playing = True
        deck.meta.filepath = "/music/drop.mp3"
        deck.meta.bpm = 120.0
        deck.meta.first_beat_ms = 0.0
        deck.meta.smart_drops = [2]
        sm._os.active_deck = 1
        sm._os.lighting_mode = "autoloop"
        sm._os.lighting_desired = "autoloop"
        sm._os.was_playing = True
        sm._os.last_sent_bpm = 120.0
        sm._os.last_beat_elapsed_ms = 0
        sm._os.last_armed_filepath = deck.meta.filepath
        sm._os.drop_cut_armed = True
        sm._os.drop_rearm_beat = 2
        sm._cache.update(
            PositionSnapshot(1, elapsed_ms=1000, playing=True, updated_at=time.monotonic())
        )
        sm._laser_executor = Mock()
        sm._laser_executor.smart_drop_blackout_enabled.return_value = True
        return sm

    def test_crossing_clears_pending_blackout_when_laser_director_missing(self) -> None:
        sm = self._prepare_manager()
        sm._laser_director = None
        with patch("rb_ss_bridge_v2.state_manager._smart_drop_tick", return_value=2):
            sm._push_tick()
        sm._laser_executor.clear_pending_blackout.assert_called_once_with(
            reason="smart_drop_crossing_without_drop_decision"
        )
        self.assertFalse(sm._os.drop_cut_armed)

    def test_crossing_clears_pending_blackout_when_decision_is_none(self) -> None:
        sm = self._prepare_manager()
        sm._laser_director = Mock()
        sm._laser_director.tick.return_value = None
        with patch("rb_ss_bridge_v2.state_manager._smart_drop_tick", return_value=2):
            sm._push_tick()
        sm._laser_executor.clear_pending_blackout.assert_called_once_with(
            reason="smart_drop_crossing_without_drop_decision"
        )
        self.assertFalse(sm._os.drop_cut_armed)

    def test_crossing_clears_pending_blackout_when_non_drop_decision_wins(self) -> None:
        sm = self._prepare_manager()
        sm._laser_director = Mock()
        sm._laser_director.tick.return_value = SimpleNamespace(reason="manual_override")
        with patch("rb_ss_bridge_v2.state_manager._smart_drop_tick", return_value=2):
            sm._push_tick()
        sm._laser_executor.clear_pending_blackout.assert_called_once_with(
            reason="smart_drop_crossing_without_drop_decision"
        )

    def test_crossing_does_not_double_clear_when_drop_decision_emitted(self) -> None:
        sm = self._prepare_manager()
        sm._laser_director = Mock()
        sm._laser_director.tick.return_value = SimpleNamespace(reason="drop_crossing")
        with patch("rb_ss_bridge_v2.state_manager._smart_drop_tick", return_value=2):
            sm._push_tick()
        sm._laser_executor.clear_pending_blackout.assert_not_called()

    def test_blackout_arm_does_not_trigger_when_laser_director_disabled(self) -> None:
        sm = self._prepare_manager()
        sm._os.drop_cut_armed = False
        sm._os.drop_rearm_beat = 0
        sm._deck[1].meta.smart_drops = [6]
        sm._laser_director = Mock()
        sm._laser_director.is_enabled.return_value = False
        sm._laser_director.tick.return_value = None
        sm._push_tick()
        sm._laser_executor.trigger_blackout_on.assert_not_called()
        sm._laser_executor.clear_pending_blackout.assert_any_call(
            reason="laser_director_disabled"
        )

    def test_blackout_arm_signal_passes_through_context_without_direct_trigger_call(self) -> None:
        sm = self._prepare_manager()
        sm._os.drop_cut_armed = False
        sm._os.drop_rearm_beat = 0
        sm._deck[1].meta.smart_drops = [6]
        sm._laser_director = Mock()
        sm._laser_director.is_enabled.return_value = True
        sm._laser_director.tick.return_value = SimpleNamespace(
            scene="up",
            reason="buildup_to_drop_window",
            role="buildup",
        )
        sm._push_tick()
        sm._laser_executor.trigger_blackout_on.assert_not_called()
        _, ctx = sm._laser_executor.on_decision.call_args.args
        self.assertTrue(ctx.smart_drop_blackout_arm)

    def test_laser_set_enabled_false_clears_pending_blackout_once(self) -> None:
        sm = self._prepare_manager()
        sm._laser_director = Mock()
        sm._laser_director.is_enabled.return_value = True
        sm._handle_event(
            BridgeEvent(
                Ev.LASER_SET_ENABLED,
                0,
                {"enabled": False},
            )
        )
        sm._laser_executor.clear_pending_blackout.assert_called_once_with(
            reason="laser_director_disabled"
        )


class SnapshotStatusTests(unittest.TestCase):
    def test_snapshot_distinguishes_transition_window_from_blackout_pending(self) -> None:
        sm = _manager()
        sm._os.drop_cut_armed = True
        sm._laser_executor = Mock()
        sm._laser_executor.status.return_value = {
            "blackout_pending_for_drop_window": False
        }
        sm._publish_snapshot()
        self.assertTrue(sm._published_snapshot["smart_drop_transition_window_active"])
        self.assertFalse(sm._published_snapshot["smart_drop_blackout_active"])


class PhraseAnchorTests(unittest.TestCase):
    def test_phrase_anchor_skipped_while_transition_arm_pending(self) -> None:
        sm = _sm()
        sm._os.autoloop_arm_pending = True
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_skipped_while_pending_arm_meta_set(self) -> None:
        sm = _sm()
        sm._os.pending_autoloop_arm_meta = TrackMetadata(filepath="/music/pending.mp3")
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_fires_at_64(self) -> None:
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_snaps_to_nearby_future_drop(self) -> None:
        sm = _sm([60])
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 58, 29_000, 58.0)
        sm._send_autoloop_deck_load.assert_not_called()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 60, 30_000, 60.0)
        sm._send_autoloop_deck_load.assert_not_called()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_does_not_snap_to_past_drop(self) -> None:
        sm = _sm([55])
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 62, 31_000, 62.0)
        sm._send_autoloop_deck_load.assert_not_called()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_blocked_by_drop_cut(self) -> None:
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        sm._os.drop_cut_armed = True
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_blocked_by_breakdown_active(self) -> None:
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        sm._os.breakdown_active = True
        sm._os.breakdown_restore_beat = 96
        _phrase_anchor_tick(sm, 1, 2, 130.0, 64, 32_000, 64.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_init_sentinel(self) -> None:
        sm = _sm()
        _phrase_anchor_tick(sm, 1, 2, 130.0, 75, 37_500, 75.0)
        sm._send_autoloop_deck_load.assert_not_called()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 64)

    def test_phrase_anchor_skips_stale_missed_anchor(self) -> None:
        # Recovery rebases from this_beat=120, so next anchor is 120+64=184.
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 120, 60_000, 120.0)
        sm._send_autoloop_deck_load.assert_not_called()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 120)

    def test_phrase_anchor_does_not_fire_at_128_after_stale_recovery(self) -> None:
        # After recovery at beat 120, next anchor is 184 — not 128.
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 120, 60_000, 120.0)
        self.assertEqual(sm._os.phrase_anchor_last_beat, 120)
        _phrase_anchor_tick(sm, 1, 2, 130.0, 128, 64_000, 128.0)
        sm._send_autoloop_deck_load.assert_not_called()

    def test_phrase_anchor_fires_at_184_after_stale_recovery(self) -> None:
        # After recovery at beat 120, anchor fires at 120+64=184.
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        _phrase_anchor_tick(sm, 1, 2, 130.0, 120, 60_000, 120.0)
        _phrase_anchor_tick(sm, 1, 2, 130.0, 184, 92_000, 184.0)
        sm._send_autoloop_deck_load.assert_called_once()
        self.assertEqual(sm._os.phrase_anchor_last_beat, 184)

    def test_phrase_anchor_pre_clear_fires_one_beat_before(self) -> None:
        # phrase_anchor_last_beat=0, no drops → next_anchor=64.
        # At beat 63 (next_anchor - 1): clear fires 4 times, loop_off 4 times,
        # no deck load, returns False.
        sm = _sm()
        sm._os.phrase_anchor_last_beat = 0
        result = _phrase_anchor_tick(sm, 1, 2, 130.0, 63, 31_500, 63.0)
        self.assertFalse(result)
        self.assertEqual(sm._out.send_deck_clear.call_count, 4)
        self.assertEqual(sm._out.send_loop_off.call_count, 4)
        sm._send_autoloop_deck_load.assert_not_called()
        # phrase_anchor_last_beat must NOT advance — anchor hasn't fired yet.
        self.assertEqual(sm._os.phrase_anchor_last_beat, 0)


if __name__ == "__main__":
    unittest.main()

class SmartBreakdownTests(unittest.TestCase):
    def test_breakdown_marker_prevents_smart_drop_precut(self):
        sm = _sm()
        sm._deck[1].meta.smart_drops = [96]
        sm._deck[1].meta.smart_breakdowns = [92]
        sm._smart_breakdown_enabled = True

        _smart_drop_tick(sm, 1, 2, 130.0, 88, 44_000)
        self.assertFalse(sm._os.drop_cut_armed)
        self.assertEqual(sm._out.send_deck_clear.call_count, 0)

        _smart_breakdown_tick(sm, 1, 2, 130.0, 92, 46_000)
        self.assertTrue(sm._os.breakdown_active)
        self.assertEqual(sm._os.breakdown_restore_beat, 96)

    def test_breakdown_cuts_and_restores(self):
        sm = _sm()
        sm._deck[1].meta.smart_breakdowns = [32]
        sm._deck[1].meta.smart_drops = [64]
        sm._smart_breakdown_enabled = True
        
        # Tick before breakdown
        _smart_breakdown_tick(sm, 1, 2, 130.0, 30, 15_000)
        self.assertFalse(sm._os.breakdown_active)
        
        # Tick on breakdown beat
        _smart_breakdown_tick(sm, 1, 2, 130.0, 32, 16_000)
        self.assertTrue(sm._os.breakdown_active)
        self.assertEqual(sm._os.breakdown_restore_beat, 64)
        self.assertEqual(sm._out.send_deck_clear.call_count, 4)
        self.assertEqual(sm._out.send_loop_off.call_count, 4)
        
        # Tick inside breakdown
        _smart_breakdown_tick(sm, 1, 2, 130.0, 40, 20_000)
        self.assertTrue(sm._os.breakdown_active)
        
        # Tick on restore beat
        _smart_breakdown_tick(sm, 1, 2, 130.0, 64, 32_000)
        self.assertFalse(sm._os.breakdown_active)
        sm._send_autoloop_deck_load.assert_called_once()
