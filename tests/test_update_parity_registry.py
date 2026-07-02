"""Pure tests for the Autoloop parity-registry negative-pinning seam.

`build_autoloop_registry()` is I/O-bound (it loads a pack directory and a
fixture file from disk), so these tests exercise the pure per-identity record
builder it delegates to, `_autoloop_registry_record()`. That function decides,
given a loop and its fixture capture rows, whether the loop gets a registry
entry at all and -- if it does -- whether that entry is pinned PASS or FAIL.

The behavior under test is the negative-pinning fix: a loop with capture rows
that now FAIL classification must still get a registry entry (verdict FAIL),
not silently fall through to no-entry (which would let the compiler treat it
as `algorithm_generalized` instead of failing closed to `unverified_parity`).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedAutoloop,
    LoadedDocument,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.tools.ssfmt.update_parity_registry import _autoloop_registry_record


def _event(time: int, order: int, patch=()) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time,
        source_order=order,
        source_offset=100 + order,
        reference_kind="cue",
        raw_reference=order + 1,
        patch=tuple(LoadedAttribute(0x493, channel, channel, value) for channel, value in patch),
    )


def _loop(*events: LoadedTimelineEvent, cycle_ticks: int = 2400) -> LoadedAutoloop:
    document = LoadedDocument(
        "SSAutoLoop99.ssfile", "shared_441_dictionary_timeline", tuple(events), (), cycle_ticks,
    )
    return LoadedAutoloop("SSAutoLoop99.ssfile", True, document)


class AutoloopRegistryRecordTests(unittest.TestCase):
    def test_rows_present_and_report_pass_writes_pass_verdict(self) -> None:
        loop = _loop(_event(0, 0, ((1, 4),)))
        rows = [{"phase_tick": 0, "u0_frame": [4] + [0] * 18, "label": "match"}]

        record = _autoloop_registry_record(
            loop, rows,
            capture_id="capture-1", divergence_entry=[],
            source_sha="source-sha", layout="shared_441_dictionary_timeline",
            venue_sha="venue-sha",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["verdict"], "PASS")
        self.assertEqual(record["rows_total"], 1)
        self.assertEqual(record["rows_passed"], 1)
        self.assertEqual(record["capture_id"], "capture-1")
        self.assertEqual(record["source_sha256"], "source-sha")
        self.assertEqual(record["venue_source_sha256"], "venue-sha")
        self.assertEqual(record["layout"], "shared_441_dictionary_timeline")
        self.assertEqual(record["divergence"], [])
        self.assertEqual(record["truth_source"], "SoundSwitch U0")

    def test_rows_present_and_report_fail_writes_fail_verdict_with_divergence(self) -> None:
        # The loop renders channel 1 = 4 at tick 0, but the capture row records
        # a different lit value -> VALUE_DIFF -> the oracle report is FAIL.
        # This is the witnessed-regression case: capture evidence exists and
        # disagrees with the current render, so the loop must be PINNED FAIL,
        # not silently dropped back to no-entry / generalization.
        loop = _loop(_event(0, 0, ((1, 4),)))
        rows = [{"phase_tick": 0, "u0_frame": [9] + [0] * 18, "label": "value-diff"}]
        divergence_entry = [{"reason": "sibling_segment_failed_oracle", "segment": "x"}]

        record = _autoloop_registry_record(
            loop, rows,
            capture_id="capture-1", divergence_entry=divergence_entry,
            source_sha="source-sha", layout="shared_441_dictionary_timeline",
            venue_sha="venue-sha",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual(record["rows_total"], 1)
        self.assertEqual(record["rows_passed"], 0)
        self.assertEqual(record["divergence"], divergence_entry)

    def test_no_rows_returns_no_entry(self) -> None:
        loop = _loop(_event(0, 0, ((1, 4),)))

        record = _autoloop_registry_record(
            loop, [],
            capture_id="capture-1", divergence_entry=[{"unrelated": True}],
            source_sha="source-sha", layout="shared_441_dictionary_timeline",
            venue_sha="venue-sha",
        )

        self.assertIsNone(record)

    def test_non_list_divergence_entry_is_normalized_to_empty_list(self) -> None:
        loop = _loop(_event(0, 0, ((1, 4),)))
        rows = [{"phase_tick": 0, "u0_frame": [4] + [0] * 18, "label": "match"}]

        record = _autoloop_registry_record(
            loop, rows,
            capture_id="capture-1", divergence_entry=None,
            source_sha="source-sha", layout="shared_441_dictionary_timeline",
            venue_sha="venue-sha",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record["divergence"], [])


if __name__ == "__main__":
    unittest.main()
