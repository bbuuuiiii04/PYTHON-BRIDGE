from __future__ import annotations

import logging
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_fmt  # noqa: E402
from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402


def _capture(logger_name: str):
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.DEBUG)
    return logger, handler, prior_level, records


class _FakeTransport:
    def __init__(self, *, after_return: threading.Event | None = None) -> None:
        self.calls: list[str] = []
        self.thread_calls: list[tuple[str, int]] = []
        self.frames: list[list[tuple[int, int, int]]] = []
        self.after_return = after_return
        self.send_after_return = 0

    def _record(self, call: str) -> None:
        self.calls.append(call)
        self.thread_calls.append((call, threading.get_ident()))

    def activate(self) -> bool:
        self._record("activate")
        return True

    def deactivate(self) -> bool:
        self._record("deactivate")
        return True

    def set_brightness(self, value: int) -> bool:
        self._record(f"brightness:{value}")
        return True

    def send_frame(self, frame) -> bool:  # type: ignore[no-untyped-def]
        self._record("send_frame")
        if self.after_return is not None and self.after_return.is_set():
            self.send_after_return += 1
        self.frames.append(list(frame))
        return True

    def blackout(self) -> bool:
        self._record("blackout")
        return True

    def close(self) -> None:
        self._record("close")

    def status(self) -> dict:
        return {"frames_sent": len(self.frames), "send_error_count": 0, "last_error": ""}


def _anchor(
    now: float = 100.0,
    *,
    permitted: bool = True,
    playing: bool = True,
    abs_beat_pos: float = 64.0,
    bpm: float = 120.0,
) -> BeatAnchor:
    return BeatAnchor(
        deck=1,
        abs_beat_pos=abs_beat_pos,
        bpm=bpm,
        captured_monotonic=now,
        playing=playing,
        permitted=permitted,
    )


def _head_index(frame: list[tuple[int, int, int]]) -> int:
    luminance = [sum(px) for px in frame]
    return max(range(len(luminance)), key=lambda idx: luminance[idx])


def _lit_regions(frame: list[tuple[int, int, int]]) -> list[list[int]]:
    regions: list[list[int]] = []
    current: list[int] = []
    for idx, px in enumerate(frame):
        if sum(px) > 0:
            current.append(idx)
        elif current:
            regions.append(current)
            current = []
    if current:
        regions.append(current)
    return regions


class GoveeRealtimeRunnerTests(unittest.TestCase):
    def test_tick_activates_and_sends_frame_when_permitted(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(
            EffectSpec(
                effect_name="solid",
                params={"color": [1, 2, 3]},
                seed=1,
                applied_monotonic=100.0,
            )
        )

        runner._tick_once(_anchor(), 100.0)

        self.assertEqual(transport.calls[:3], ["activate", "brightness:100", "send_frame"])
        self.assertEqual(transport.frames[-1], [(1, 2, 3)] * 4)

    def test_unpermitted_anchor_holds_then_deactivates(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(
            transport,
            GoveeFrameRenderer(),
            segments=2,
            fps=30,
            grace_s=0.25,
        )
        runner.set_desired(
            EffectSpec("solid", {"color": [9, 9, 9]}, 1, 100.0)
        )
        runner._tick_once(_anchor(), 100.0)

        runner._tick_once(_anchor(permitted=False), 100.1)
        runner._tick_once(_anchor(permitted=False), 100.4)

        self.assertIn("send_frame", transport.calls)
        self.assertEqual(transport.calls[-1], "deactivate")

    def test_zero_bpm_anchor_stays_idle(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(
            EffectSpec("solid", {"color": [1, 2, 3]}, 1, 100.0)
        )
        zero_bpm = BeatAnchor(
            deck=1,
            abs_beat_pos=0.0,
            bpm=0.0,
            captured_monotonic=100.0,
            playing=True,
            permitted=True,
        )

        runner._tick_once(zero_bpm, 100.0)

        self.assertNotIn("activate", transport.calls)
        self.assertNotIn("send_frame", transport.calls)
        self.assertFalse(runner.status()["active"])

    def test_emergency_stop_blackouts_and_deactivates_immediately(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=2)
        runner.set_desired(
            EffectSpec("solid", {"color": [9, 9, 9]}, 1, 100.0)
        )
        runner._tick_once(_anchor(), 100.0)

        runner.emergency_stop()
        runner._tick_once(_anchor(), 100.01)

        self.assertEqual(transport.calls[-2:], ["blackout", "deactivate"])
        self.assertFalse(runner.status()["active"])

    def test_retrigger_comet_travels_full_strip_and_relaunches(self) -> None:
        transport = _FakeTransport()
        segments = 20
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=segments, fps=60)
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 1.0},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="retrigger",
                beat_division=1.0,
            )
        )

        start = 100.0
        # 120 bpm => one beat every 0.5 seconds. Stay below the next beat first
        # to prove this is a full-strip comet, not the old 4-beat dual chase
        # reset that only reached about 5/20 LEDs.
        for step in range(30):
            now = start + (step / 60.0)
            runner._tick_once(_anchor(start, abs_beat_pos=64.0, bpm=120.0), now)

        indices = [_head_index(frame) for frame in transport.frames]
        before_reset = indices[:-1]
        self.assertEqual(before_reset, sorted(before_reset))
        self.assertGreaterEqual(max(before_reset), int(segments * 0.6))

        runner._tick_once(_anchor(start, abs_beat_pos=64.0, bpm=120.0), start + 0.5)
        self.assertLessEqual(_head_index(transport.frames[-1]), 1)
        self.assertEqual(runner.status()["sync_mode"], "retrigger")
        self.assertEqual(runner.status()["instance_count"], 1)

    def test_overlap_comet_folds_multiple_instances_into_frame(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=60)
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 2.0, "trail_beats": 0.5},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="overlap",
                beat_division=1.0,
            )
        )

        start = 100.0
        for beat in (0.0, 1.0, 2.0):
            runner._tick_once(
                _anchor(start, abs_beat_pos=64.0 + beat, bpm=120.0),
                start + beat * 0.5,
            )

        self.assertGreaterEqual(runner.status()["instance_count"], 2)
        luminance = [sum(px) for px in transport.frames[-1]]
        self.assertGreaterEqual(sum(1 for value in luminance if value > 0), 10)
        self.assertGreater(luminance[0], 0)
        self.assertGreater(luminance[10], 0)

    def test_pause_continues_in_flight_comet_then_deactivates(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(
            transport,
            GoveeFrameRenderer(),
            segments=20,
            fps=60,
            grace_s=0.0,
        )
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 1.0, "trail_beats": 0.25},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="overlap",
                beat_division=1.0,
            )
        )

        start = 100.0
        runner._tick_once(_anchor(start, abs_beat_pos=64.0, bpm=120.0), start)
        initial_frame_index = runner.status()["frame_index"]
        initial_spawn_count = runner.status()["spawn_count"]
        initial_head = _head_index(transport.frames[-1])

        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.10)
        paused_head_1 = _head_index(transport.frames[-1])
        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.25)
        paused_head_2 = _head_index(transport.frames[-1])

        self.assertTrue(runner.status()["active"])
        self.assertGreater(runner.status()["frame_index"], initial_frame_index)
        self.assertEqual(runner.status()["spawn_count"], initial_spawn_count)
        self.assertGreater(paused_head_1, initial_head)
        self.assertGreater(paused_head_2, paused_head_1)

        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.70)
        self.assertEqual(runner.status()["instance_count"], 0)
        self.assertTrue(runner.status()["active"])
        self.assertTrue(all(sum(px) == 0 for px in transport.frames[-1]))

        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.71)
        self.assertFalse(runner.status()["active"])
        self.assertEqual(transport.calls[-1], "deactivate")

    def test_pause_with_no_in_flight_comet_idles_without_animate(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(
            transport,
            GoveeFrameRenderer(),
            segments=20,
            fps=60,
            grace_s=0.0,
        )
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 1.0},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="overlap",
                beat_division=1.0,
            )
        )
        runner._tick_once(_anchor(), 100.0)
        runner._engine.reset()
        frame_index = runner.status()["frame_index"]

        runner._tick_once(_anchor(playing=False), 100.1)

        self.assertFalse(runner.status()["active"])
        self.assertEqual(runner.status()["frame_index"], frame_index)
        self.assertEqual(transport.calls[-1], "deactivate")

    def test_emergency_during_pause_blackouts_and_clears_engine(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=60)
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 1.0},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="overlap",
                beat_division=1.0,
            )
        )
        runner._tick_once(_anchor(), 100.0)

        runner.emergency_stop()
        runner._tick_once(_anchor(playing=False), 100.1)

        self.assertEqual(transport.calls[-2:], ["blackout", "deactivate"])
        self.assertFalse(runner.status()["active"])
        self.assertEqual(runner.status()["instance_count"], 0)

    def test_resume_after_pause_to_dark_reconfigures_and_spawns(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(
            transport,
            GoveeFrameRenderer(),
            segments=20,
            fps=60,
            grace_s=0.0,
        )
        runner.set_desired(
            EffectSpec(
                effect_name="groove_chase_blue",
                params={"travel_beats": 1.0, "trail_beats": 0.25},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="overlap",
                beat_division=1.0,
            )
        )

        start = 100.0
        runner._tick_once(_anchor(start, abs_beat_pos=64.0, bpm=120.0), start)
        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.70)
        runner._tick_once(_anchor(start, playing=False, abs_beat_pos=64.0, bpm=120.0), start + 0.71)
        self.assertFalse(runner.status()["active"])
        self.assertEqual(runner.status()["instance_count"], 0)

        runner._tick_once(_anchor(start + 1.0, abs_beat_pos=66.0, bpm=120.0), start + 1.0)

        self.assertTrue(runner.status()["active"])
        self.assertEqual(runner.status()["instance_count"], 1)
        self.assertEqual(transport.calls[-3:], ["activate", "brightness:100", "send_frame"])

    def test_non_comet_effect_still_uses_legacy_render_path(self) -> None:
        class RecordingRenderer(GoveeFrameRenderer):
            def __init__(self) -> None:
                super().__init__()
                self.render_calls = 0
                self.comet_calls = 0

            def render(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                self.render_calls += 1
                return super().render(*args, **kwargs)

            def render_comet(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                self.comet_calls += 1
                return super().render_comet(*args, **kwargs)

        transport = _FakeTransport()
        renderer = RecordingRenderer()
        runner = GoveeRealtimeRunner(transport, renderer, segments=20, fps=60)
        runner.set_desired(
            EffectSpec(
                effect_name="breathe",
                params={},
                seed=1,
                applied_monotonic=100.0,
                sync_mode="continuous",
                beat_division=1.0,
            )
        )

        runner._tick_once(_anchor(), 100.0)

        self.assertEqual(renderer.comet_calls, 0)
        self.assertEqual(renderer.render_calls, 1)
        self.assertEqual(len(transport.frames[-1]), 20)

    def test_overlap_no_freeze_across_backward_wrap(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=30)
        spec = EffectSpec(
            effect_name="groove_chase_blue",
            params={},
            seed=1,
            applied_monotonic=100.0,
            sync_mode="overlap",
            beat_division=1.0,
        )
        runner.set_desired(spec)
        anchor_pre = BeatAnchor(
            deck=1,
            abs_beat_pos=7.5,
            bpm=120.0,
            captured_monotonic=100.0,
            playing=True,
            permitted=True,
        )
        runner._tick_once(anchor_pre, 100.0)
        frame_before = list(transport.frames[-1])
        anchor_wrap = BeatAnchor(
            deck=1,
            abs_beat_pos=0.0,
            bpm=120.0,
            captured_monotonic=100.5,
            playing=True,
            permitted=True,
        )
        runner._tick_once(anchor_wrap, 100.2)
        frame_after = transport.frames[-1]
        self.assertNotEqual(frame_before, frame_after)
        self.assertTrue(any(any(c > 0 for c in px) for px in frame_after))

    def test_manual_fire_trigger_spawns_without_signature_change(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=30)
        spec = EffectSpec(
            effect_name="groove_chase_blue",
            params={},
            seed=1,
            applied_monotonic=100.0,
            sync_mode="overlap",
            beat_division=1.0,
        )
        runner.set_desired(spec)
        runner._tick_once(_anchor(), 100.0)
        count_after_first = runner.status()["instance_count"]
        runner.set_desired(spec)
        runner.fire_trigger()
        runner._tick_once(_anchor(), 100.033)
        count_after_trigger = runner.status()["instance_count"]
        self.assertGreater(count_after_trigger, count_after_first)

    def test_manual_spam_capped(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=30)
        spec = EffectSpec(
            effect_name="groove_chase_blue",
            params={},
            seed=1,
            applied_monotonic=100.0,
            sync_mode="overlap",
            beat_division=1.0,
        )
        runner.set_desired(spec)
        for _ in range(100):
            runner.fire_trigger()
        runner._tick_once(_anchor(), 100.0)
        self.assertEqual(runner.status()["pending_manual"], 0)

    def test_force_deactivate_clears_engine(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=30)
        spec = EffectSpec(
            effect_name="groove_chase_blue",
            params={},
            seed=1,
            applied_monotonic=100.0,
            sync_mode="overlap",
            beat_division=1.0,
        )
        runner.set_desired(spec)
        runner._tick_once(_anchor(), 100.0)
        runner.force_deactivate()
        runner._tick_once(_anchor(), 100.01)
        self.assertEqual(runner.status()["instance_count"], 0)

    def test_force_deactivate_teardown_runs_on_runner_thread(self) -> None:
        after_return = threading.Event()
        transport = _FakeTransport(after_return=after_return)
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=120)
        runner.set_beat_provider(lambda: _anchor(time.monotonic()))
        runner.set_desired(
            EffectSpec(
                effect_name="solid",
                params={"color": [1, 2, 3]},
                seed=1,
                applied_monotonic=time.monotonic(),
            )
        )
        runner.start()
        deadline = time.monotonic() + 1.0
        while "send_frame" not in transport.calls and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertIn("send_frame", transport.calls)

        caller_id: list[int] = []

        def _caller() -> None:
            caller_id.append(threading.get_ident())
            runner.force_deactivate()
            after_return.set()

        caller = threading.Thread(target=_caller)
        caller.start()
        caller.join(timeout=1.0)
        self.assertFalse(caller.is_alive())

        deadline = time.monotonic() + 1.0
        while "deactivate" not in transport.calls and time.monotonic() < deadline:
            time.sleep(0.005)

        runner_calls = [
            ident for call, ident in transport.thread_calls
            if call in {"blackout", "deactivate"}
        ]
        self.assertEqual(transport.calls.count("blackout"), 1)
        self.assertEqual(transport.calls.count("deactivate"), 1)
        self.assertTrue(runner_calls)
        self.assertNotIn(caller_id[0], runner_calls)
        self.assertEqual(transport.send_after_return, 0)
        runner.stop()

    def test_emergency_teardown_clears_engine(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=20, fps=30)
        spec = EffectSpec(
            effect_name="groove_chase_blue",
            params={},
            seed=1,
            applied_monotonic=100.0,
            sync_mode="overlap",
            beat_division=1.0,
        )
        runner.set_desired(spec)
        runner._tick_once(_anchor(), 100.0)
        runner.emergency_stop()
        runner._tick_once(_anchor(), 100.01)
        self.assertEqual(runner.status()["instance_count"], 0)

    def test_reconcile_reactivates_within_cloud_suspect_window(self) -> None:
        """WI-6: after note_cloud_dispatch(), _tick_once re-sends activate()
        at approximately rt_reconcile_interval_s cadence within the window."""
        import os as _os
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(
            EffectSpec("solid", {"color": [1, 2, 3]}, 1, 100.0)
        )
        # Bring runner to active state
        runner._tick_once(_anchor(100.0), 100.0)
        pre_reconcile_activates = transport.calls.count("activate")
        self.assertEqual(pre_reconcile_activates, 1)

        # Simulate a cloud DIY dispatch with a 5-second window, 1-second interval
        t = 101.0
        runner.note_cloud_dispatch(t, window_s=5.0, interval_s=1.0)

        # Tick at t+1.1 (inside window, interval elapsed): reconcile fires
        runner._tick_once(_anchor(t + 1.1), t + 1.1)
        self.assertEqual(transport.calls.count("activate"), 2)
        self.assertEqual(runner.status()["rt_reconcile_count"], 1)

        # Tick at t+2.2 (another interval): reconcile fires again
        runner._tick_once(_anchor(t + 2.2), t + 2.2)
        self.assertEqual(transport.calls.count("activate"), 3)
        self.assertEqual(runner.status()["rt_reconcile_count"], 2)

        # Tick past window: no extra activate
        activates_before = transport.calls.count("activate")
        runner._tick_once(_anchor(t + 6.0), t + 6.0)
        self.assertEqual(transport.calls.count("activate"), activates_before)

    def test_reconcile_does_not_fire_when_not_active(self) -> None:
        """WI-6: reconcile must not fire activate() when the runner is inactive."""
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        # Don't tick to active state
        t = 100.0
        runner.note_cloud_dispatch(t, window_s=5.0, interval_s=0.1)
        runner._tick_once(None, t + 0.2)
        self.assertEqual(transport.calls.count("activate"), 0)
        self.assertEqual(runner.status()["rt_reconcile_count"], 0)

    def test_reconcile_status_counter_in_status_dict(self) -> None:
        """WI-8: rt_reconcile_count must appear in status()."""
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        self.assertIn("rt_reconcile_count", runner.status())
        self.assertEqual(runner.status()["rt_reconcile_count"], 0)


class _FailableTransport(_FakeTransport):
    """_FakeTransport with a togglable send_frame() failure for health-transition tests."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.fail = False

    def send_frame(self, frame) -> bool:
        self._record("send_frame")
        self.frames.append(list(frame))
        return not self.fail


class GoveeRealtimeRunnerHealthTransitionTests(unittest.TestCase):
    """AWR-125 W4: health.govee.rt edge-triggered emits on transport send result."""

    def setUp(self) -> None:
        bridge_fmt.reset_rate_state()

    def _spec(self) -> EffectSpec:
        return EffectSpec(
            effect_name="solid",
            params={"color": [1, 2, 3]},
            seed=1,
            applied_monotonic=100.0,
        )

    def test_send_failure_streak_emits_once(self) -> None:
        transport = _FailableTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(self._spec())
        logger, handler, prior_level, records = _capture("health.govee.rt")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        transport.fail = True
        runner._tick_once(_anchor(100.0), 100.0)
        runner._tick_once(_anchor(100.1), 100.1)  # repeat failure: must not re-log

        self.assertEqual(len(records), 1, f"expected exactly one send-failing record, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("send failing", records[0].getMessage())

    def test_send_recovers_after_failure_emits_once(self) -> None:
        transport = _FailableTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(self._spec())
        logger, handler, prior_level, records = _capture("health.govee.rt")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        transport.fail = True
        runner._tick_once(_anchor(100.0), 100.0)
        transport.fail = False
        runner._tick_once(_anchor(100.1), 100.1)
        runner._tick_once(_anchor(100.2), 100.2)  # repeat success: must not re-log recovery

        self.assertEqual(len(records), 2, f"expected failing+recovered only, got {records!r}")
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertEqual(records[1].levelname, "INFO")
        self.assertIn("recovered", records[1].getMessage())

    def test_first_ever_success_does_not_log_false_recovery(self) -> None:
        """A healthy runner that never failed must never claim 'recovered'."""
        transport = _FailableTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(self._spec())
        logger, handler, prior_level, records = _capture("health.govee.rt")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        runner._tick_once(_anchor(100.0), 100.0)

        self.assertEqual(records, [])

    def test_loop_thread_guard_emits_started_and_exited(self) -> None:
        transport = _FakeTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        logger, handler, prior_level, records = _capture("sys.thread")
        self.addCleanup(logger.setLevel, prior_level)
        self.addCleanup(logger.removeHandler, handler)

        runner.start()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not any(
            "GoveeRealtimeRunner started" in r.getMessage() for r in records
        ):
            time.sleep(0.01)
        runner.stop(timeout_s=0.5)

        self.assertTrue(any("GoveeRealtimeRunner started" in r.getMessage() for r in records))
        self.assertTrue(any("GoveeRealtimeRunner exited" in r.getMessage() for r in records))


if __name__ == "__main__":
    unittest.main()
