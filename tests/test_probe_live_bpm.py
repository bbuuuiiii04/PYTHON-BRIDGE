import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.probe_live_bpm import (
    Hit,
    _cached_candidates_for_session,
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

    def test_verdict_passes_moving_value_matching_expected_after(self) -> None:
        self.assertEqual(
            _verdict_for_samples([126.0, 128.5, 132.29], expected_after=132.3, tolerance=0.25, min_delta=0.05),
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
