from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from rb_ss_bridge_v2.session_replayer import CapturedSession, ReplayHarness  # noqa: E402
from rb_ss_bridge_v2.state_manager import STATE_MANAGER_PROFILE_ENV  # noqa: E402


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "replay"
    / "fixtures"
    / "perf_baseline.jsonl"
)
RUN_PERF = os.environ.get("RBSS_RUN_PERF") == "1"


def _percentile_ms(series, percentile: float) -> float:
    values = sorted(float(v) for v in series._values)
    if not values:
        return 0.0
    index = min(len(values) - 1, int(len(values) * percentile))
    return values[index]


def _max_ms(series) -> float:
    values = list(series._values)
    return max(values) if values else 0.0


class PushLatencyPerfTests(unittest.TestCase):
    @unittest.skipUnless(RUN_PERF, "set RBSS_RUN_PERF=1 to run performance budget tests")
    def test_state_manager_push_latency_budget(self) -> None:
        if not FIXTURE.exists():
            self.skipTest(
                "missing performance replay fixture: "
                f"{FIXTURE}. Generate it from a real bridge session with "
                "python scripts/record_session.py for about 30 seconds of "
                "normal track playback; do not fabricate it."
            )

        session = CapturedSession.from_jsonl(FIXTURE)
        harness = ReplayHarness(session)

        with patch.dict(os.environ, {STATE_MANAGER_PROFILE_ENV: "1"}):
            result = harness.run_for(seconds=30)

        profiler = result.state_manager._profiler
        self.assertIsNotNone(profiler)

        push_p99 = _percentile_ms(profiler._push, 0.99)
        drain_p99 = _percentile_ms(profiler._drain, 0.99)
        snapshot_p99 = _percentile_ms(profiler._snapshot, 0.99)
        overrun_rate = profiler._overrun_count / max(1, result.ticks)

        self.assertLess(
            push_p99,
            2.0,
            "p99(push_ms) exceeded budget "
            f"(p99={push_p99:.3f} max={_max_ms(profiler._push):.3f} ticks={result.ticks})",
        )
        self.assertLess(
            drain_p99,
            0.5,
            "p99(drain_ms) exceeded budget "
            f"(p99={drain_p99:.3f} max={_max_ms(profiler._drain):.3f} ticks={result.ticks})",
        )
        self.assertLess(
            snapshot_p99,
            1.0,
            "p99(snapshot_ms) exceeded budget "
            f"(p99={snapshot_p99:.3f} max={_max_ms(profiler._snapshot):.3f} ticks={result.ticks})",
        )
        self.assertLess(
            overrun_rate,
            0.001,
            "StateManager overrun rate exceeded 0.1% "
            f"(overruns={profiler._overrun_count} ticks={result.ticks})",
        )


if __name__ == "__main__":
    unittest.main()
