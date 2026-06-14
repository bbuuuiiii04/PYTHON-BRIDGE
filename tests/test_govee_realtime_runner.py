from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer  # noqa: E402
from rb_ss_bridge_v2.govee_realtime_runner import EffectSpec, GoveeRealtimeRunner  # noqa: E402
from rb_ss_bridge_v2.led_models import BeatAnchor  # noqa: E402


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.frames: list[list[tuple[int, int, int]]] = []

    def activate(self) -> bool:
        self.calls.append("activate")
        return True

    def deactivate(self) -> bool:
        self.calls.append("deactivate")
        return True

    def set_brightness(self, value: int) -> bool:
        self.calls.append(f"brightness:{value}")
        return True

    def send_frame(self, frame) -> bool:  # type: ignore[no-untyped-def]
        self.calls.append("send_frame")
        self.frames.append(list(frame))
        return True

    def blackout(self) -> bool:
        self.calls.append("blackout")
        return True

    def close(self) -> None:
        self.calls.append("close")

    def status(self) -> dict:
        return {"frames_sent": len(self.frames), "send_error_count": 0, "last_error": ""}


def _anchor(now: float = 100.0, *, permitted: bool = True) -> BeatAnchor:
    return BeatAnchor(
        deck=1,
        abs_beat_pos=64.0,
        bpm=120.0,
        captured_monotonic=now,
        playing=True,
        permitted=permitted,
    )


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


if __name__ == "__main__":
    unittest.main()
