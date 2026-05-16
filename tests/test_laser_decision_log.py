from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_decision_log import LaserDecision, LaserDecisionLog  # noqa: E402
from rb_ss_bridge_v2.laser_director import LaserDirector  # noqa: E402
from rb_ss_bridge_v2.laser_models import LaserContext  # noqa: E402


def _decision(index: int) -> LaserDecision:
    return LaserDecision(
        mono=float(index),
        wall=1000.0 + index,
        scene=f"scene_{index}",
        prev_scene=f"scene_{index - 1}",
        reason=f"reason_{index}",
        abs_beat=64.0 + index,
        deck=1,
        personality="default",
        lighting_mode="autoloop",
        triggered_by="scene_change",
    )


def _ctx(
    *,
    active_deck: int = 1,
    abs_beat: float = 64.0,
    lighting_mode: str = "autoloop",
) -> LaserContext:
    return LaserContext(
        active_deck=active_deck,
        playing=True,
        elapsed_ms=60_000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=abs_beat,
        position_stale=False,
        lighting_mode=lighting_mode,
        os2l_connected=True,
        active_track_loaded=True,
        autoloop_ready=True,
    )


class LaserDecisionLogTests(unittest.TestCase):
    def test_ringbuffer_capacity_is_respected(self) -> None:
        log = LaserDecisionLog(capacity=3)

        for index in range(5):
            log.record(_decision(index))

        self.assertEqual([d.scene for d in log.recent(10)], ["scene_2", "scene_3", "scene_4"])
        self.assertEqual(len(log.as_dicts()), 3)

    def test_eviction_order_keeps_oldest_remaining_first(self) -> None:
        log = LaserDecisionLog(capacity=2)

        log.record(_decision(1))
        log.record(_decision(2))
        log.record(_decision(3))

        self.assertEqual([d.reason for d in log.recent()], ["reason_2", "reason_3"])
        self.assertEqual([d["reason"] for d in log.as_dicts()], ["reason_2", "reason_3"])

    def test_dict_serialization_is_stable(self) -> None:
        log = LaserDecisionLog(capacity=4)
        decision = LaserDecision(
            mono=12.5,
            wall=1700000000.0,
            scene="house_phrase_1",
            prev_scene="",
            reason="default_init",
            abs_beat=None,
            deck=2,
            personality="peak",
            lighting_mode="autoloop",
            triggered_by="scene_change",
        )

        log.record(decision)

        self.assertEqual(
            log.as_dicts(),
            [
                {
                    "mono": 12.5,
                    "wall": 1700000000.0,
                    "scene": "house_phrase_1",
                    "prev_scene": "",
                    "reason": "default_init",
                    "abs_beat": None,
                    "deck": 2,
                    "personality": "peak",
                    "lighting_mode": "autoloop",
                    "triggered_by": "scene_change",
                }
            ],
        )

    def test_recent_limits_returned_decisions(self) -> None:
        log = LaserDecisionLog(capacity=5)
        for index in range(4):
            log.record(_decision(index))

        self.assertEqual([d.scene for d in log.recent(2)], ["scene_2", "scene_3"])
        self.assertEqual(log.recent(0), [])


class LaserDirectorDecisionLogIntegrationTests(unittest.TestCase):
    def test_status_exposes_scene_change_and_reason_update(self) -> None:
        director = LaserDirector(enabled=True, default_scene="house_phrase_1")
        director.set_personality("peak")

        with patch("rb_ss_bridge_v2.laser_director.time.time", return_value=1700.0):
            director.tick(_ctx(active_deck=2, abs_beat=64.0), now=10.0)
        with patch("rb_ss_bridge_v2.laser_director.time.time", return_value=1701.0):
            director.tick(_ctx(active_deck=2, abs_beat=65.0), now=11.0)

        decisions = director.status()["recent_decisions"]

        self.assertEqual(len(decisions), 2)
        self.assertEqual(
            decisions[0],
            {
                "mono": 10.0,
                "wall": 1700.0,
                "scene": "house_phrase_1",
                "prev_scene": "",
                "reason": "default_init",
                "abs_beat": 64.0,
                "deck": 2,
                "personality": "peak",
                "lighting_mode": "autoloop",
                "triggered_by": "scene_change",
            },
        )
        self.assertEqual(
            decisions[1],
            {
                "mono": 11.0,
                "wall": 1701.0,
                "scene": "house_phrase_1",
                "prev_scene": "house_phrase_1",
                "reason": "default",
                "abs_beat": 65.0,
                "deck": 2,
                "personality": "peak",
                "lighting_mode": "autoloop",
                "triggered_by": "reason_update",
            },
        )

    def test_status_limits_recent_decisions_to_32(self) -> None:
        director = LaserDirector(enabled=True)
        with patch("rb_ss_bridge_v2.laser_director.time.time", return_value=1700.0):
            for index in range(40):
                director.set_manual_override(f"manual_{index}", ttl_s=10.0)
                director.tick(_ctx(abs_beat=float(index)), now=float(index))

        decisions = director.status()["recent_decisions"]

        self.assertEqual(len(decisions), 32)
        self.assertEqual(decisions[0]["scene"], "manual_8")
        self.assertEqual(decisions[-1]["scene"], "manual_39")


if __name__ == "__main__":
    unittest.main()
