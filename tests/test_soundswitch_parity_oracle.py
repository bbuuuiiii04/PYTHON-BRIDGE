"""Tests for the pure U0-grounded SoundSwitch parity oracle."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_laser_player import ZERO_FRAME
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedDocument,
    LoadedTimelineEvent,
    load_pack,
)
from rb_ss_bridge_v2.soundswitch_parity_oracle import (
    AutoloopSample,
    ScriptedSample,
    StaticSample,
    classify_autoloop,
    classify_scripted,
    classify_static,
)


def _event(time: int, order: int, patch=(), *, clear: bool = False) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time,
        source_order=order,
        source_offset=100 + order,
        reference_kind="clear_control" if clear else "cue",
        raw_reference=0 if clear else order + 1,
        patch=tuple(LoadedAttribute(0x493, channel, channel, value) for channel, value in patch),
    )


def _document(*events: LoadedTimelineEvent, cycle_ticks: int | None = None) -> LoadedDocument:
    return LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline", tuple(events), (), cycle_ticks)


class PureParityOracleTests(unittest.TestCase):
    def test_scripted_classifies_match_blip_value_diff_u0_dark_and_hold_shape(self) -> None:
        doc = _document(
            _event(10, 0, ((1, 7),)),
            _event(20, 1, clear=True),
            _event(30, 2, ((2, 9),)),
        )
        report = classify_scripted(doc, (
            ScriptedSample(0, ZERO_FRAME, "pre-first-dark"),
            ScriptedSample(10, (7,) + (0,) * 18, "match"),
            ScriptedSample(20, (7,) + (0,) * 18, "missing-hold"),
            ScriptedSample(30, (7, 9) + (0,) * 17, "value-diff"),
            ScriptedSample(31, ZERO_FRAME, "u0-dark-pack-lit"),
        ))
        self.assertEqual(report.verdict, "FAIL")
        self.assertEqual(report.truth_source, "SoundSwitch U0")
        self.assertEqual(report.counts["MATCH"], 1)
        self.assertEqual(report.counts["BLIP"], 1)
        self.assertEqual(report.counts["VALUE_DIFF"], 1)
        self.assertEqual(report.counts["U0_DARK"], 2)
        self.assertEqual(report.issues["missing_hold"], 1)
        self.assertEqual(report.issues["pack_lit_u0_dark"], 1)

    def test_autoloop_and_static_pass_when_u0_matches(self) -> None:
        loop = _document(_event(0, 0, ((1, 4),)), cycle_ticks=2400)
        self.assertTrue(classify_autoloop(loop, (AutoloopSample(0, (4,) + (0,) * 18),)).passed)
        self.assertTrue(classify_static((3,) + (0,) * 18, StaticSample((3,) + (0,) * 18)).passed)


@unittest.skipUnless(Path("local/soundswitch/rbss_canonical_pack/manifest.json").is_file(),
                     "local canonical pack fixture is unavailable")
class ReducedCaptureFixtureTests(unittest.TestCase):
    def test_reduced_capture_rows_fail_known_broken_pack_and_pass_lit_matches(self) -> None:
        fixture = json.loads(Path(
            "tests/fixtures/soundswitch/parity_oracle/scripted_reduced.json").read_text())
        pack = load_pack("local/soundswitch/rbss_canonical_pack")
        failing = set()
        matching = set()
        for ssid, rows in fixture["scripted"].items():
            samples = tuple(
                ScriptedSample(row["elapsed_ms"], tuple(row["u0_frame"]), row["label"])
                for row in rows
            )
            report = classify_scripted(pack.scripted[ssid], samples)
            if not report.passed:
                failing.add(ssid)
            for sample in report.samples:
                if sample.label == "lit-region-match" and sample.class_name == "MATCH":
                    matching.add(ssid)
        self.assertTrue({
            "ae9e3c61-af40-4392-80b4-380d39c631b9",
            "fc10fc02-93c2-418f-8815-16088884da42",
        }.issubset(failing))
        self.assertTrue({
            "528e8b22-bd17-41b9-a111-275d3e8b3031",
            "9947c65e-cfd1-476e-aa90-4aed65ae5f11",
        }.issubset(matching))


if __name__ == "__main__":
    unittest.main()
