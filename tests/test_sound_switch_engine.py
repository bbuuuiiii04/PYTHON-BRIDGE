import contextlib
import logging
import queue
import sys
import unittest
from unittest import mock
from pathlib import Path
from unittest.mock import Mock, call

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.models import TrackMetadata  # noqa: E402
from rb_ss_bridge_v2.osl_output import OS2LConnection, OS2LOutput  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.sound_switch_engine import SoundSwitchEngine  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager, _send_direct_autoloop_rearm  # noqa: E402
from rb_ss_bridge_v2 import bridge_fmt  # noqa: E402
from rb_ss_bridge_v2 import bridge_log  # noqa: E402


class _PerfRecordCapture(logging.Handler):
    """Captures build_record()-shaped dicts emitted to a perf.* logger."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(bridge_log.build_record(record))


@contextlib.contextmanager
def _capture_perf(cat: str):
    logger = logging.getLogger(f"perf.{cat}")
    handler = _PerfRecordCapture()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


@contextlib.contextmanager
def _capture_health(sub: str):
    """Captures raw LogRecords emitted to a health.* logger (AWR-125 W4)."""
    logger = logging.getLogger(f"health.{sub}")
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


class DeckRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sse = SoundSwitchEngine(Mock())

    def test_deck_route_deck1(self) -> None:
        self.assertEqual(self.sse.deck_route(1), (1, 2, 3, 4))

    def test_deck_route_deck2(self) -> None:
        self.assertEqual(self.sse.deck_route(2), (2, 1, 3, 4))

    def test_deck_route_always_four_decks(self) -> None:
        self.assertEqual(len(self.sse.deck_route(1)), 4)
        self.assertEqual(len(self.sse.deck_route(2)), 4)

    def test_send_loop_off_delegates_to_output(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_loop_off(3)
        out.send_loop_off.assert_called_once_with(3)

    def test_send_deck_clear_delegates_to_output(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_deck_clear(4)
        out.send_deck_clear.assert_called_once_with(4)

    def test_autoloop_deck_load_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_autoloop_deck_load(1, 2, 1, arm_meta)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(deck, arm_meta, 1, play="on") for deck in (1, 2, 3, 4)],
        )

    def test_send_autoloop_clear_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_autoloop_clear(2)
        self.assertEqual(
            out.send_deck_clear.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )
        self.assertEqual(
            out.send_loop_off.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )

    def test_send_smart_transition_clear_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_smart_transition_clear(2)
        self.assertEqual(
            out.send_deck_clear.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )
        self.assertEqual(
            out.send_loop_off.call_args_list,
            [call(deck) for deck in (2, 1, 3, 4)],
        )

    def test_send_smart_transition_clear_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_smart_transition_clear(1)
        self.assertEqual(
            out.send_deck_clear.call_args_list,
            [call(deck) for deck in (1, 2, 3, 4)],
        )
        self.assertEqual(
            out.send_loop_off.call_args_list,
            [call(deck) for deck in (1, 2, 3, 4)],
        )

    def test_send_autoloop_bpm_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_autoloop_bpm(1, 130.0)
        self.assertEqual(
            out.send_bpm.call_args_list,
            [call(deck, 130.0) for deck in (1, 2, 3, 4)],
        )

    def test_send_live_bpm_follow_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_live_bpm_follow(2, 130.0)
        self.assertEqual(
            out.send_bpm.call_args_list,
            [call(deck, 130.0) for deck in (2, 1, 3, 4)],
        )

    def test_send_live_bpm_follow_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_live_bpm_follow(1, 128.5)
        self.assertEqual(
            out.send_bpm.call_args_list,
            [call(deck, 128.5) for deck in (1, 2, 3, 4)],
        )

    def test_send_live_bpm_follow_passes_bpm_arg_verbatim(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_live_bpm_follow(1, 127.37)
        self.assertEqual(len(out.send_bpm.call_args_list), 4)
        for args in out.send_bpm.call_args_list:
            self.assertEqual(args, call(args.args[0], 127.37))

    def test_send_scripted_arm_phase0_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_scripted_arm_phase0(2)
        self.assertEqual(
            out._sub.call_args_list,
            [call(f"deck {dk} get_filepath", "", verbose=True) for dk in (2, 1, 3, 4)],
        )
        self.assertEqual(out.send_loop_off.call_args_list, [call(dk) for dk in (2, 1, 3, 4)])
        self.assertEqual(
            out.send_deck_play.call_args_list,
            [call(dk, "off") for dk in (2, 1, 3, 4)],
        )

    def test_send_scripted_arm_phase0_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        sse.send_scripted_arm_phase0(1)
        self.assertEqual(out.send_loop_off.call_args_list, [call(dk) for dk in (1, 2, 3, 4)])

    def test_send_scripted_arm_phase1_fans_out_via_deck_route(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(2, arm_meta, 2)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 2, play="on", elapsed_ms=0) for dk in (2, 1, 3, 4)],
        )

    def test_send_scripted_arm_phase1_deck1_route_order(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(1, arm_meta, 1)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 1, play="on", elapsed_ms=0) for dk in (1, 2, 3, 4)],
        )

    def test_send_scripted_arm_phase1_active_differs_from_armed_deck(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(1, arm_meta, 2)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 2, play="on", elapsed_ms=0) for dk in (1, 2, 3, 4)],
        )

    def test_send_scripted_arm_phase1_threads_elapsed_ms(self) -> None:
        out = Mock()
        sse = SoundSwitchEngine(out)
        arm_meta = Mock()
        sse.send_scripted_arm_phase1(1, arm_meta, 1, elapsed_ms=1234)
        self.assertEqual(
            out.send_deck_load.call_args_list,
            [call(dk, arm_meta, 1, play="on", elapsed_ms=1234) for dk in (1, 2, 3, 4)],
        )


class StateManagerWiringTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def test_state_manager_init_creates_sse(self) -> None:
        sm = self._sm()
        self.assertIsInstance(sm._sse, SoundSwitchEngine)

    def test_state_manager_sse_shares_output(self) -> None:
        sm = self._sm()
        self.assertIs(sm._sse._out, sm._out)


class StateManagerRouteFanoutTests(unittest.TestCase):
    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def _configure_active_deck(self, sm: StateManager, active: int, bpm: float) -> None:
        d = sm._deck[active]
        d.meta.filepath = f"/music/deck-{active}.mp3"
        d.meta.bpm = bpm
        d.meta.first_beat_ms = 0.0
        d.meta.beatgrid_times_ms = [i * 500.0 for i in range(256)]
        d.meta.beatgrid_bpms = [bpm for _ in range(256)]
        d.meta.total_ms = 180_000.0

    def _assert_fanout(self, sm: StateManager, expected_decks: list[int], bpm: float) -> None:
        self.assertEqual(sm._out.send_deck_clear.call_args_list, [call(deck) for deck in expected_decks])
        self.assertEqual(sm._out.send_loop_off.call_args_list, [call(deck) for deck in expected_decks])
        self.assertEqual(sm._out.send_bpm.call_args_list, [call(deck, bpm) for deck in expected_decks])

    def test_direct_autoloop_rearm_fanout_uses_deck1_route_order(self) -> None:
        sm = self._sm()
        sm._sse.send_autoloop_deck_load = Mock()
        self._configure_active_deck(sm, active=1, bpm=130.0)
        with _capture_perf("autoloop") as records:
            ok = _send_direct_autoloop_rearm(
                sm, active=1, mirror=2, bpm=130.0, elapsed_ms=32_005, reason="test", target_beat=64
            )
        self.assertTrue(ok)
        self._assert_fanout(sm, [1, 2, 3, 4], 130.0)
        rearm_records = [r for r in records if r["data"]["action"] == "rearm"]
        self.assertEqual(len(rearm_records), 1)
        self.assertEqual(rearm_records[0]["data"]["deck"], 1)
        self.assertEqual(rearm_records[0]["data"]["reason"], "test")
        self.assertEqual(rearm_records[0]["data"]["target_beat"], 64)

    def test_direct_autoloop_rearm_fanout_uses_deck2_route_order(self) -> None:
        sm = self._sm()
        sm._sse.send_autoloop_deck_load = Mock()
        self._configure_active_deck(sm, active=2, bpm=131.0)
        ok = _send_direct_autoloop_rearm(
            sm, active=2, mirror=1, bpm=131.0, elapsed_ms=32_005, reason="test", target_beat=64
        )
        self.assertTrue(ok)
        self._assert_fanout(sm, [2, 1, 3, 4], 131.0)


class OS2LOutputSendDeckLoadPerfTests(unittest.TestCase):
    """send_deck_load's [OS2L] deck-load INFO line -> perf("ss", "deck-load ...")."""

    def test_send_deck_load_emits_single_perf_ss_record(self) -> None:
        out = OS2LOutput(Mock())
        meta = TrackMetadata(
            filepath="/tmp/track.mp3",
            soundswitch_id="{aaaa}",
            bpm=128.0,
            first_beat_ms=0.0,
            total_ms=180_000.0,
        )

        with _capture_perf("ss") as records:
            out.send_deck_load(2, meta, active_deck=1, play="on", elapsed_ms=5000)

        deck_load_records = [r for r in records if r["data"]["action"] == "deck-load"]
        self.assertEqual(len(deck_load_records), 1)
        data = deck_load_records[0]["data"]
        self.assertEqual(data["deck"], 2)
        self.assertEqual(data["active"], 1)
        self.assertEqual(data["ssid"], "{aaaa}")
        self.assertEqual(data["bpm"], 128.0)
        self.assertEqual(data["play"], "on")
        self.assertEqual(data["loop"], "off")  # scripted track (has soundswitch_id) -> loop off


class ScriptedArmPerfEmitTests(unittest.TestCase):
    """_arm_scripted / _check_pending_arm perf("scripted", ...) sites."""

    def _sm(self) -> StateManager:
        return StateManager(queue.Queue(), PositionCache(), Mock())

    def test_arm_scripted_unregistered_no_ssid_emits_arm_fail_warning(self) -> None:
        sm = self._sm()
        with _capture_perf("scripted") as records:
            sm._arm_scripted(1, 999)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["lvl"], "WARNING")
        self.assertEqual(records[0]["data"]["action"], "arm-fail")
        self.assertEqual(records[0]["data"]["deck"], 1)
        self.assertEqual(records[0]["data"]["id"], 999)

    def test_arm_scripted_direct_mode_emits_arm_and_phase2(self) -> None:
        sm = self._sm()
        d = sm._deck[1]
        d.meta.filepath = "/tmp/scripted-direct.wav"
        d.meta.bpm = 128.0
        d.meta.soundswitch_id = "ssid-direct"

        with _capture_perf("scripted") as records:
            sm._arm_scripted(1, 555)
            self.assertIsNotNone(sm._pending_arm)
            sm._pending_arm.fire_at = 0.0
            sm._check_pending_arm()

        by_action = {r["data"]["action"]: r for r in records}
        self.assertEqual(sorted(by_action), ["arm", "arm-phase2"])
        self.assertEqual(by_action["arm"]["data"]["deck"], 1)
        self.assertEqual(by_action["arm"]["data"]["id"], 555)
        self.assertEqual(by_action["arm-phase2"]["data"]["deck"], 1)
        self.assertEqual(by_action["arm-phase2"]["data"]["id"], 555)


class OS2LConnectionHealthTransitionTests(unittest.TestCase):
    """AWR-125 W4: health.os2l / health.queue edge-triggered emits.

    _reconnect_loop/_sender_loop are only ever called directly here (never
    .start()'d) so no real thread, socket, or sleep is exercised: socket.socket
    is patched out entirely, and time.sleep is patched to set the stop Event so
    each call performs exactly one loop iteration.
    """

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()

    def _run_reconnect_once(self, conn: OS2LConnection) -> None:
        conn._stop.clear()

        def _fast_sleep(_secs: float) -> None:
            conn._stop.set()

        with mock.patch("rb_ss_bridge_v2.osl_output.time.sleep", side_effect=_fast_sleep):
            conn._reconnect_loop()

    def test_connect_success_emits_health_os2l_info(self) -> None:
        conn = OS2LConnection()
        fake_sock = Mock()
        with mock.patch("rb_ss_bridge_v2.osl_output.socket.socket", return_value=fake_sock):
            with _capture_health("os2l") as records:
                self._run_reconnect_once(conn)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "INFO")
        self.assertIn("connected", records[0].getMessage())
        self.assertTrue(conn.is_connected())

    def test_connect_failure_streak_emits_once(self) -> None:
        conn = OS2LConnection()
        with mock.patch("rb_ss_bridge_v2.osl_output.socket.socket", side_effect=OSError("refused")):
            with _capture_health("os2l") as records:
                self._run_reconnect_once(conn)
                self._run_reconnect_once(conn)  # same failure again: must not re-log

        self.assertEqual(len(records), 1, f"{records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("connect-fail", records[0].getMessage())

    def test_send_error_emits_health_os2l(self) -> None:
        conn = OS2LConnection()
        failing_sock = Mock()
        failing_sock.sendall.side_effect = OSError("broken pipe")
        conn._sock = failing_sock
        conn._connected = True
        conn._send_q.put_nowait(b'{"evt":"beat"}\n')
        conn._send_q.put_nowait(None)  # sentinel: _sender_loop exits right after

        with _capture_health("os2l") as records:
            conn._sender_loop()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("send-error", records[0].getMessage())
        self.assertFalse(conn.is_connected())

    def test_send_queue_full_emits_health_queue_throttled(self) -> None:
        conn = OS2LConnection()
        conn._send_q = queue.Queue(maxsize=1)
        conn.send({"evt": "beat"})  # fills the single slot

        with _capture_health("queue") as records:
            conn.send({"evt": "beat"})  # drop #1: logs
            conn.send({"evt": "beat"})  # drop #2: throttled, silent

        self.assertEqual(len(records), 1, f"{records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("queue full", records[0].getMessage())


if __name__ == "__main__":
    unittest.main()
