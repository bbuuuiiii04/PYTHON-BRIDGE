from __future__ import annotations

import sys
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
        self.assertEqual(appended[-1], {"cmd": "led_clear_blackout"})
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


if __name__ == "__main__":
    unittest.main()
