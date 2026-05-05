import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.probe_live_bpm import (
    Hit,
    _cached_candidates_for_session,
    _results_from_samples,
    _select_validation_hits,
    _verdict_for_samples,
)


def _hit(addr: int, value: float, score: float, region: str) -> Hit:
    return Hit(
        addr=addr,
        type_name="f32",
        value=value,
        role="bpm",
        score=score,
        region=region,
        nearest_anchor="container",
        anchor_delta=addr - 0x1000,
    )


class ProbeLiveBpmValidationTests(unittest.TestCase):
    def test_verdict_rejects_static_values(self) -> None:
        self.assertEqual(
            _verdict_for_samples([126.0, 126.0, 126.0], expected_after=132.3, tolerance=0.25, min_delta=0.05),
            "stale",
        )

    def test_verdict_rejects_zero_start_churn(self) -> None:
        self.assertEqual(
            _verdict_for_samples([0.0, 130.0, 125.0], expected_after=125.0, tolerance=0.25, min_delta=0.05),
            "zero_start_churn",
        )

    def test_verdict_rejects_zero_end_decay(self) -> None:
        self.assertEqual(
            _verdict_for_samples([130.0, 125.0, 0.0], expected_after=125.0, tolerance=0.25, min_delta=0.05),
            "zero_end_decay",
        )

    def test_verdict_keeps_all_zero_values_stale(self) -> None:
        self.assertEqual(
            _verdict_for_samples([0.0, 0.0, 0.0], expected_after=125.0, tolerance=0.25, min_delta=0.05),
            "stale",
        )

    def test_verdict_passes_moving_value_matching_expected_after(self) -> None:
        self.assertEqual(
            _verdict_for_samples([126.0, 128.5, 132.29], expected_after=132.3, tolerance=0.25, min_delta=0.05),
            "pass",
        )

    def test_verdict_passes_smooth_move_matching_expected_after(self) -> None:
        self.assertEqual(
            _verdict_for_samples(
                [130.0, 129.5, 129.0, 128.5, 125.0],
                expected_after=125.0,
                tolerance=0.25,
                min_delta=0.05,
            ),
            "pass",
        )

    def test_verdict_flags_wrong_final_value(self) -> None:
        self.assertEqual(
            _verdict_for_samples([126.0, 128.5, 130.0], expected_after=132.3, tolerance=0.25, min_delta=0.05),
            "moved_wrong_value",
        )

    def test_validation_selection_penalizes_render_cache_regions(self) -> None:
        hits = [
            _hit(0x2000, 132.1, 0.0, "vmmap:IOAccelerator"),
            _hit(0x3000, 132.2, 0.1, "vmmap:MALLOC_TINY"),
            _hit(0x4000, 132.3, 0.2, "secondary1 +/-0x10000"),
        ]

        selected = _select_validation_hits(hits, limit=2)

        self.assertEqual([hit.addr for hit in selected], [0x3000, 0x4000])

    def test_results_from_samples_records_trace_metadata(self) -> None:
        hit = _hit(0x3000, 130.0, 0.0, "vmmap:MALLOC_TINY")

        results = _results_from_samples(
            [hit],
            {(hit.addr, hit.type_name): [130.0, 132.5, 125.0]},
            {(hit.addr, hit.type_name): [0.0, 0.2, 0.4]},
            expected_after=125.0,
            tolerance=0.25,
            min_delta=0.05,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].verdict, "pass")
        self.assertEqual(results[0].num_discontinuities, 2)
        self.assertEqual(results[0].timestamps, (0.0, 0.2, 0.4))
        self.assertEqual(results[0].values, (130.0, 132.5, 125.0))

    def test_cache_filter_matches_pid_base_and_deck(self) -> None:
        cache = {
            "sessions": [
                {
                    "pid": 111,
                    "base": "0xaaa",
                    "deck": 2,
                    "candidates": [{"addr": "0x1", "type": "f32"}],
                },
                {
                    "pid": 222,
                    "base": "0xaaa",
                    "deck": 2,
                    "candidates": [{"addr": "0x2", "type": "f32"}],
                },
                {
                    "pid": 111,
                    "base": "0xaaa",
                    "deck": 1,
                    "candidates": [{"addr": "0x3", "type": "f32"}],
                },
            ]
        }

        candidates = _cached_candidates_for_session(cache, pid=111, base=0xAAA, deck=2)

        self.assertEqual(candidates, [{"addr": "0x1", "type": "f32"}])


if __name__ == "__main__":
    unittest.main()
