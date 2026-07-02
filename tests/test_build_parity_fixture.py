"""Tests for the reduced SoundSwitch parity fixture builder seams."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack_loader import (  # noqa: E402
    LoadedAttribute,
    LoadedDocument,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.tools.ssfmt.build_parity_fixture import (  # noqa: E402
    join_sidecar_to_mono,
    screen_rows,
    select_rows,
)


def _frame(*values: int) -> list[int]:
    return list(values) + [0] * (19 - len(values))


def _event(time: int, order: int, patch: tuple[tuple[int, int], ...]) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time,
        source_order=order,
        source_offset=100 + order,
        reference_kind="cue",
        raw_reference=order + 1,
        patch=tuple(LoadedAttribute(0x493, channel, channel, value) for channel, value in patch),
    )


def _doc(*events: LoadedTimelineEvent) -> LoadedDocument:
    return LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline", events, ())


class BuildParityFixtureTests(unittest.TestCase):
    def test_join_sidecar_to_mono_uses_ordered_sequence_sha_pairs_through_wrap(self) -> None:
        sidecar = [
            {"soundswitch_id": "{AAAA}", "sequence": 254, "dmx_sha256": "a", "elapsed_ms": 10,
             "frame_index": 1},
            {"soundswitch_id": "{AAAA}", "sequence": 255, "dmx_sha256": "z", "elapsed_ms": 20,
             "frame_index": 2},
            {"soundswitch_id": "{AAAA}", "sequence": 0, "dmx_sha256": "z", "elapsed_ms": 30,
             "frame_index": 3},
        ]
        u1 = [
            {"sequence": 254, "dmx_sha256": "a", "mono_ns": 100},
            {"sequence": 255, "dmx_sha256": "z", "mono_ns": 200},
            {"sequence": 0, "dmx_sha256": "z", "mono_ns": 300},
        ]
        result = join_sidecar_to_mono(sidecar, u1, witness_ssids=["aaaa"])
        self.assertEqual([row["mono_ns"] for row in result.rows], [100, 200, 300])
        self.assertEqual(result.stats["dropped"], 0)

    def test_join_sidecar_to_mono_counts_dropped_rows(self) -> None:
        result = join_sidecar_to_mono(
            [{"soundswitch_id": "aaaa", "sequence": 1, "dmx_sha256": "missing",
              "elapsed_ms": 10, "frame_index": 1}],
            [{"sequence": 2, "dmx_sha256": "other", "mono_ns": 100}],
            witness_ssids=["aaaa"],
            lookahead=1,
        )
        self.assertEqual(result.rows, ())
        self.assertEqual(result.stats["dropped"], 1)

    def test_select_rows_keeps_only_steady_runs_inside_alignment_windows(self) -> None:
        joined = [
            {"ssid": "aaaa", "elapsed_ms": 1148, "mono_ns": 1_200_000_000,
             "frame_index": 10},
            {"ssid": "aaaa", "elapsed_ms": 2500, "mono_ns": 2_200_000_000,
             "frame_index": 20},
        ]
        runs = [
            {"s": 1_000_000_000, "e": 1_400_000_000, "f": tuple(_frame(7))},
            {"s": 2_150_000_000, "e": 2_250_000_000, "f": tuple(_frame(9))},
        ]
        rows = select_rows(
            joined,
            runs,
            [_event(1000, 0, ((1, 7),)), _event(4000, 1, ((1, 9),))],
            [{"t_start_mono": 1.0, "t_end_mono": 1.3}],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["elapsed_ms"], 1148)
        self.assertEqual(rows[0]["u0_frame"], _frame(7))

    def test_select_rows_accepts_recovered_frame_index_windows(self) -> None:
        joined = [{"ssid": "aaaa", "elapsed_ms": 1150, "mono_ns": 10_200_000_000,
                   "frame_index": 42}]
        runs = [{"s": 10_000_000_000, "e": 10_400_000_000, "f": tuple(_frame(7))}]
        rows = select_rows(
            joined,
            runs,
            [_event(1000, 0, ((1, 7),))],
            [{"frame_index_start": 40, "frame_index_end": 50}],
        )
        self.assertEqual(len(rows), 1)

    def test_screen_rows_splits_matches_cross_deck_bleed_and_stale_source_edit(self) -> None:
        document = _doc(
            _event(100, 0, ((1, 7),)),
            _event(300, 1, ((2, 9),)),
        )
        rows = [
            {"elapsed_ms": 100, "u0_frame": _frame(7), "label": "match", "mono_ns": 1},
            {"elapsed_ms": 200, "u0_frame": _frame(5), "label": "unreachable", "mono_ns": 2},
            {"elapsed_ms": 100, "u0_frame": _frame(0, 9), "label": "reachable_wrong_time",
             "mono_ns": 3},
        ]
        witnesses, divergence = screen_rows(rows, document)
        self.assertEqual([row["label"] for row in witnesses], ["match"])
        self.assertEqual([row["class"] for row in divergence],
                         ["cross_deck_bleed", "stale_source_edit"])


if __name__ == "__main__":
    unittest.main()
