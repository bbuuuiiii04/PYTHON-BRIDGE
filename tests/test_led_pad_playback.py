from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.led_pad_playback import CueTimer, OwnershipGate, PadPlayback, SyntheticClock  # noqa: E402


class LedPadPlaybackTests(unittest.TestCase):
    def test_synthetic_clock_integrates_across_bpm_changes(self) -> None:
        now = [0.0]
        clock = SyntheticClock(bpm=120, time_fn=lambda: now[0])
        clock.play()

        now[0] = 10.0
        self.assertAlmostEqual(clock.anchor().abs_beat_pos, 20.0)
        clock.set_bpm(60)
        now[0] = 20.0

        self.assertAlmostEqual(clock.anchor().abs_beat_pos, 30.0)

    def test_status_beat_advances_with_fake_time(self) -> None:
        now = [0.0]
        playback = PadPlayback.__new__(PadPlayback)
        playback._clock = SyntheticClock(bpm=120.0, time_fn=lambda: now[0])
        playback._loop = True
        playback._playing_look = ""
        playback._last_error = ""
        playback._following = False
        playback._follow_bpm = None
        playback._manual_bpm = 120.0
        playback.tick = lambda: None
        playback._runner = type("Runner", (), {"status": lambda _self: {}})()

        now[0] = 5.0
        self.assertAlmostEqual(playback.status()["beat"], 0.0)

        playback._clock.play()
        now[0] = 6.0  # 1 s at 120 BPM → 2 beats
        self.assertAlmostEqual(playback.status()["beat"], 2.0)
        now[0] = 7.0
        self.assertAlmostEqual(playback.status()["beat"], 4.0)

        playback._clock.stop()
        frozen = playback.status()["beat"]
        now[0] = 20.0
        self.assertAlmostEqual(playback.status()["beat"], frozen)
        self.assertFalse(playback.status()["playing"])

    def test_cue_timer_stops_only_when_loop_is_off(self) -> None:
        now = [0.0]
        timer = CueTimer(time_fn=lambda: now[0])
        timer.start(cue_beats=4, bpm=120, loop=False)

        now[0] = 1.9
        self.assertFalse(timer.should_stop())
        now[0] = 2.0
        self.assertTrue(timer.should_stop())

        timer.start(cue_beats=4, bpm=120, loop=True)
        now[0] = 10.0
        self.assertFalse(timer.should_stop())

    def test_cue_timer_bpm_change_keeps_elapsed_beats(self) -> None:
        now = [0.0]
        timer = CueTimer(time_fn=lambda: now[0])
        timer.start(cue_beats=4, bpm=120, loop=False)
        now[0] = 1.0
        timer.set_bpm(60)

        now[0] = 2.9
        self.assertFalse(timer.should_stop())
        now[0] = 3.0
        self.assertTrue(timer.should_stop())

    def test_ownership_gate_transitions_reasserts_and_releases(self) -> None:
        now = [100.0]
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        appended: list[dict] = []
        slept: list[float] = []
        gate = OwnershipGate(
            time_fn=lambda: now[0],
            sleep_fn=slept.append,
            status_reader=lambda: status,
            appender=appended.append,
        )

        self.assertEqual(gate.refresh(), "bridge_owned")
        gate.request_takeover()
        self.assertEqual(gate.state, "pad_owned")
        self.assertEqual(appended, [{"cmd": "led_blackout", "reason": "led_pad"}])
        self.assertEqual(slept, [1.5])

        gate.poll_owned()
        self.assertEqual(appended[-1], {"cmd": "led_blackout", "reason": "led_pad"})
        status["led_look_director"]["emergency_blackout"] = True
        gate.poll_owned()
        self.assertEqual(len(appended), 2)

        gate.release()
        self.assertEqual(appended[-1], {"cmd": "led_clear_blackout", "reason": "led_pad"})
        self.assertEqual(gate.state, "free")

    def test_ownership_gate_bridge_down_writes_nothing_on_takeover(self) -> None:
        appended: list[dict] = []
        gate = OwnershipGate(status_reader=lambda: None, appender=appended.append, sleep_fn=lambda _seconds: None)

        gate.request_takeover()

        self.assertEqual(gate.state, "pad_owned")
        self.assertEqual(appended, [])

    def test_strobe_gate_names_missing_gate(self) -> None:
        spec = {"scene_ref": "beat_strobe", "allow_strobe": False, "safety_allow_strobe": True}
        with self.assertRaisesRegex(ValueError, "look.allow_strobe"):
            PadPlayback.validate_strobe(spec)

        spec = {"scene_ref": "beat_strobe", "allow_strobe": True, "safety_allow_strobe": False}
        with self.assertRaisesRegex(ValueError, "safety.allow_strobe"):
            PadPlayback.validate_strobe(spec)

    def test_build_spec_uses_stable_seed_and_renderer_defaults(self) -> None:
        raw = {"look_name": "rt_groove_chase", "scene_ref": "rt_groove_chase", "params": {}}
        spec_a = PadPlayback.build_spec(raw, 1.25)
        spec_b = PadPlayback.build_spec(raw, 2.5)

        self.assertEqual(spec_a.effect_name, "rt_groove_chase")
        self.assertEqual(spec_a.seed, spec_b.seed)
        self.assertGreater(spec_a.beat_division, 0)
        self.assertTrue(spec_a.sync_mode)

    def test_poll_once_ticks_every_wake_and_polls_every_eighth(self) -> None:
        playback = PadPlayback.__new__(PadPlayback)
        ticks: list[int] = []
        polls: list[int] = []
        playback.tick = lambda: ticks.append(1)
        playback._clock = type("Clock", (), {"playing": False})()
        playback._ownership = type("Owner", (), {"poll_owned": lambda _self: polls.append(1), "state": "free"})()
        playback._follow_tempo_from_status = lambda: None  # AWR-275 follow tested separately

        counter = 0
        for _ in range(8):
            counter = playback._poll_once(counter)

        self.assertEqual(len(ticks), 8)
        self.assertEqual(len(polls), 1)

    def _pad_with_gate(self, gate: OwnershipGate, *, playing: bool):
        playback = PadPlayback.__new__(PadPlayback)
        stopped: list[int] = []
        playback.tick = lambda: None
        playback.stop = lambda: stopped.append(1)
        playback._clock = type("Clock", (), {"playing": playing})()
        playback._ownership = gate
        playback._follow_tempo_from_status = lambda: None  # AWR-275 follow tested separately
        return playback, stopped

    def _run_poll_cycle(self, playback: PadPlayback) -> None:
        counter = 0
        for _ in range(8):  # counter 0..7 → one poll_owned/auto-stop check
            counter = playback._poll_once(counter)

    def test_playing_pad_auto_stops_when_bridge_owns_strip(self) -> None:
        now = [100.0]
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        gate = OwnershipGate(
            time_fn=lambda: now[0], status_reader=lambda: status,
            appender=lambda _c: None, sleep_fn=lambda _s: None,
        )  # gate.state starts "free"
        playback, stopped = self._pad_with_gate(gate, playing=True)
        self._run_poll_cycle(playback)
        self.assertEqual(stopped, [1])
        self.assertEqual(gate.last_warning, "auto_stopped_bridge_active")

    def test_pad_owned_takeover_never_auto_stops(self) -> None:
        now = [100.0]
        status = {"written_at": 100.0, "led_look_director": {"emergency_blackout": False}}
        gate = OwnershipGate(
            time_fn=lambda: now[0], status_reader=lambda: status,
            appender=lambda _c: None, sleep_fn=lambda _s: None,
        )
        gate.state = "pad_owned"  # deliberate takeover
        playback, stopped = self._pad_with_gate(gate, playing=True)
        self._run_poll_cycle(playback)
        self.assertEqual(stopped, [])
        self.assertEqual(gate.state, "pad_owned")

    def test_stale_or_absent_bridge_keeps_pad_playing(self) -> None:
        # Absent bridge status → pad is the only writer, keeps playing.
        gate_absent = OwnershipGate(
            time_fn=lambda: 100.0, status_reader=lambda: None,
            appender=lambda _c: None, sleep_fn=lambda _s: None,
        )
        playback, stopped = self._pad_with_gate(gate_absent, playing=True)
        self._run_poll_cycle(playback)
        self.assertEqual(stopped, [])

        # Stale bridge status (written >5 s ago) → treated as absent, keeps playing.
        stale = {"written_at": 50.0, "led_look_director": {"emergency_blackout": False}}
        gate_stale = OwnershipGate(
            time_fn=lambda: 100.0, status_reader=lambda: stale,
            appender=lambda _c: None, sleep_fn=lambda _s: None,
        )
        playback2, stopped2 = self._pad_with_gate(gate_stale, playing=True)
        self._run_poll_cycle(playback2)
        self.assertEqual(stopped2, [])


class LedPadTempoFollowTests(unittest.TestCase):
    """AWR-275: pad/lab playback follows the live music's bpm from the heartbeat."""

    def _follow_pad(self, *, bpm: float = 128.0, time_fn=None) -> PadPlayback:
        tf = time_fn or (lambda: 0.0)
        pb = PadPlayback.__new__(PadPlayback)
        pb._lock = threading.RLock()
        pb._clock = SyntheticClock(bpm=bpm, time_fn=tf)
        pb._timer = CueTimer(time_fn=tf)
        pb._manual_bpm = float(bpm)
        pb._following = False
        pb._follow_bpm = None
        return pb

    def test_fresh_status_bpm_is_followed_with_beat_continuity(self) -> None:
        now = [0.0]
        pb = self._follow_pad(bpm=120.0, time_fn=lambda: now[0])
        pb._clock.play()
        now[0] = 4.0  # 8 beats elapsed at 120 BPM
        before = pb._clock.beat()

        pb.apply_tempo_follow({"bpm": "140", "written_at": 0.0})
        after = pb._clock.beat()

        self.assertTrue(pb._following)
        self.assertAlmostEqual(pb._clock.bpm, 140.0)
        # No phase jump: beat position is continuous across the tempo change.
        self.assertAlmostEqual(before, after)
        self.assertGreaterEqual(after, before)  # monotonic
        # And it advances at the NEW rate afterwards.
        now[0] = 5.0  # +1 s at 140 BPM
        self.assertAlmostEqual(pb._clock.beat(), after + 140.0 / 60.0)

    def test_stale_or_absent_status_reverts_to_manual_preview(self) -> None:
        pb = self._follow_pad(bpm=125.0)
        pb.set_bpm(125.0)  # operator's manual Preview tempo
        pb.apply_tempo_follow({"bpm": "150"})
        self.assertTrue(pb._following)
        self.assertAlmostEqual(pb._clock.bpm, 150.0)

        # A manual set WHILE following is remembered but does not fight the music.
        pb.set_bpm(200.0)
        self.assertTrue(pb._following)
        self.assertAlmostEqual(pb._clock.bpm, 150.0)

        # Bridge gone (None) → release follow, fall back to the remembered manual.
        pb.apply_tempo_follow(None)
        self.assertFalse(pb._following)
        self.assertIsNone(pb._follow_bpm)
        self.assertAlmostEqual(pb._clock.bpm, 200.0)

    def test_small_wobble_below_threshold_does_not_churn_clock(self) -> None:
        now = [0.0]
        pb = self._follow_pad(bpm=128.0, time_fn=lambda: now[0])
        pb._clock.play()
        pb.apply_tempo_follow({"bpm": "128.0"})
        self.assertTrue(pb._following)
        anchor_before = pb._clock._anchor_time  # noqa: SLF001

        now[0] = 1.0
        pb.apply_tempo_follow({"bpm": "128.2"})  # |Δ| = 0.2 ≤ 0.3 → ignored
        self.assertAlmostEqual(pb._clock.bpm, 128.0)
        self.assertEqual(pb._clock._anchor_time, anchor_before)  # noqa: SLF001  (no re-anchor)

        pb.apply_tempo_follow({"bpm": "131.0"})  # |Δ| = 3 > 0.3 → applied
        self.assertAlmostEqual(pb._clock.bpm, 131.0)

    def test_garbage_bpm_is_ignored_and_stays_manual(self) -> None:
        pb = self._follow_pad(bpm=128.0)
        for bad in ({}, {"bpm": None}, {"bpm": ""}, {"bpm": "nope"}, {"bpm": "0"}, {"bpm": "999"}):
            pb.apply_tempo_follow(bad)
            self.assertFalse(pb._following, bad)
            self.assertAlmostEqual(pb._clock.bpm, 128.0)

    def test_follow_from_status_respects_awr261_freshness_window(self) -> None:
        now = [100.0]
        status = {"bpm": "142", "written_at": 100.0}
        gate = OwnershipGate(
            time_fn=lambda: now[0], status_reader=lambda: status,
            appender=lambda _c: None, sleep_fn=lambda _s: None,
        )
        pb = self._follow_pad(bpm=128.0)
        pb._ownership = gate

        pb._follow_tempo_from_status()  # fresh (0 s old) → follow
        self.assertTrue(pb._following)
        self.assertAlmostEqual(pb._clock.bpm, 142.0)

        now[0] = 110.0  # status is now >5 s old → stale
        pb._follow_tempo_from_status()  # stale → fall back to manual
        self.assertFalse(pb._following)
        self.assertAlmostEqual(pb._clock.bpm, 128.0)

    def test_status_payload_reports_tempo_mode(self) -> None:
        pb = self._follow_pad(bpm=128.0)
        pb._playing_look = ""
        pb._last_error = ""
        pb._loop = True
        pb.tick = lambda: None
        pb._runner = type("Runner", (), {"status": lambda _self: {}})()

        st = pb.status()
        self.assertEqual(st["tempo_source"], "manual")
        self.assertFalse(st["following"])

        pb.apply_tempo_follow({"bpm": "138"})
        st = pb.status()
        self.assertEqual(st["tempo_source"], "following")
        self.assertTrue(st["following"])
        self.assertAlmostEqual(st["follow_bpm"], 138.0)


if __name__ == "__main__":
    unittest.main()
