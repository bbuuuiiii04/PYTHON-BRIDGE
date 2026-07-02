from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools.ssfmt.time_domain_exam import (  # noqa: E402
    LinearFit,
    dmx_sha256,
    linear_fit,
    nearest_run_start,
    summarize,
    unwrap_ticks,
)


class TimeDomainExamTests(unittest.TestCase):
    def test_linear_fit_predicts_simple_line(self) -> None:
        fit = linear_fit([(0, 10), (5, 20), (10, 30)])
        self.assertIsInstance(fit, LinearFit)
        assert fit is not None
        self.assertAlmostEqual(fit.predict(7), 24)

    def test_linear_fit_rejects_flat_x(self) -> None:
        self.assertIsNone(linear_fit([(1, 2), (1, 3)]))

    def test_unwrap_ticks_handles_cycle_wrap(self) -> None:
        rows = [{"phase_tick": 19100}, {"phase_tick": 19150}, {"phase_tick": 10}, {"phase_tick": 50}]
        self.assertEqual(unwrap_ticks(rows, 19200), [19100, 19150, 19210, 19250])

    def test_nearest_run_start_respects_radius(self) -> None:
        self.assertEqual(nearest_run_start([100, 200, 300], 240, radius_ms=1), 200)
        self.assertIsNone(nearest_run_start([100], 2_000_000_000, radius_ms=1))

    def test_summarize_counts_wire_frame_outliers(self) -> None:
        summary = summarize([1, -2, 45])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["beyond_one_wire_frame"], 1)
        self.assertEqual(summary["max_abs_ms"], 45)

    def test_dmx_sha256_hashes_full_universe_payload(self) -> None:
        self.assertEqual(dmx_sha256([1, 2]), dmx_sha256([1, 2] + [0] * 510))
        self.assertNotEqual(dmx_sha256([1, 2]), dmx_sha256([1, 3]))


if __name__ == "__main__":
    unittest.main()
