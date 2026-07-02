"""Tests for the pure U0-grounded SoundSwitch parity oracle."""
from __future__ import annotations

import json
import sys
import tempfile
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
from rb_ss_bridge_v2.soundswitch_scripted_resolution import resolve_scripted_reference
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures/soundswitch/parity_oracle/scripted_reduced.json"
AUTOLOOP_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures/soundswitch/parity_oracle/autoloop_reduced.json"
SOURCE_PROJECT = Path.home() / "Music/SoundSwitch/default.ssproj"


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


@unittest.skipUnless(SOURCE_PROJECT.joinpath(".ssproj").is_file(),
                     "canonical read-only SoundSwitch project is unavailable")
class ReducedCaptureFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.pack_path = Path(cls.workspace.name) / "pack"
        export_pack(SOURCE_PROJECT, cls.pack_path)
        cls.pack = load_pack(cls.pack_path)
        cls.fixture = json.loads(FIXTURE_PATH.read_text())
        cls.autoloop_fixture = json.loads(AUTOLOOP_FIXTURE_PATH.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def _samples(self, ssid: str) -> tuple[ScriptedSample, ...]:
        return tuple(
            ScriptedSample(int(row["elapsed_ms"]), tuple(row["u0_frame"]), str(row.get("label") or ""))
            for row in self.fixture["scripted"][ssid]
        )

    def _autoloop_samples(self, identity: str) -> tuple[AutoloopSample, ...]:
        return tuple(
            AutoloopSample(int(row["phase_tick"]), tuple(row["u0_frame"]), str(row.get("label") or ""))
            for row in self.autoloop_fixture["autoloop"][identity]
        )

    def test_reduced_capture_rows_match_fresh_export(self) -> None:
        failures = {}
        for ssid in self.fixture["scripted"]:
            report = classify_scripted(self.pack.scripted[ssid], self._samples(ssid))
            if not report.passed:
                failures[ssid] = dict(report.counts)
        self.assertEqual(failures, {})

    def test_divergence_ledger_documents_contamination_without_poisoning_pass_rows(self) -> None:
        ledger = self.fixture["capture_source_divergence"]
        ae9e = "ae9e3c61-af40-4392-80b4-380d39c631b9"
        fc10 = "fc10fc02-93c2-418f-8815-16088884da42"
        self.assertGreater(len(self.fixture["scripted"][ae9e]), 0)
        self.assertGreater(len(self.fixture["scripted"][fc10]), 0)
        self.assertTrue({"stale_source_edit", "cross_deck_bleed"}.issubset(
            {row["class"] for row in ledger[ae9e]}))
        self.assertIn("stale_source_edit", {row["class"] for row in ledger[fc10]})

    def test_autoloop_capture_rows_identify_passes_and_blockers(self) -> None:
        passed = set()
        failures = {}
        for identity, rows in self.autoloop_fixture["autoloop"].items():
            if not rows:
                continue
            report = classify_autoloop(self.pack.autoloops[identity], self._autoloop_samples(identity))
            if report.passed:
                passed.add(identity)
            else:
                failures[identity] = dict(report.issues)

        self.assertEqual(
            passed,
            {
                "SSAutoLoop18.ssfile",
                "SSAutoLoop3.ssfile",
                "SSAutoLoop5.ssfile",
                "SSAutoLoop52.ssfile",
                "SSAutoLoop53.ssfile",
                "SSAutoLoop54.ssfile",
                "SSAutoLoop55.ssfile",
            },
        )
        self.assertEqual(self.autoloop_fixture["autoloop"]["SSAutoLoop13.ssfile"], [])
        self.assertIn("value_diff", failures["SSAutoLoop14.ssfile"])
        self.assertIn("pack_lit_u0_dark", failures["SSAutoLoop6.ssfile"])

    def _shifted_key_document(self, ssid: str) -> LoadedDocument:
        scripted = json.loads((self.pack_path / f"scripted/{ssid}.json").read_text())["document"]
        venue = json.loads((self.pack_path / "venue_cues.json").read_text())
        patches = {
            row["cue_guid"]: tuple(
                LoadedAttribute(
                    int(attribute["fixture_group"]),
                    int(attribute["channel_id"]),
                    int(attribute["dmx_channel"]),
                    int(attribute["value"]),
                )
                for attribute in row["attributes"]
            )
            for row in venue["records"]
        }
        shifted_key_to_guid = {
            int(row["stored_key"]) + 1: str(row["cue_guid"])
            for row in scripted["cue_dictionary"]
        }
        events = []
        for order, row in enumerate(scripted["timeline"]):
            resolved = resolve_scripted_reference(int(row["raw_reference"]), shifted_key_to_guid)
            events.append(LoadedTimelineEvent(
                time=int(row["time"]),
                source_order=order,
                source_offset=int(row["source_offset"]),
                reference_kind=resolved.reference_kind,
                raw_reference=int(row["raw_reference"]),
                patch=patches.get(resolved.resolved_cue_guid or "", ()),
                record_version=int(row.get("record_version", 1)),
                resolved_stored_key=resolved.resolved_stored_key,
                resolved_cue_guid=resolved.resolved_cue_guid,
                boundary_frame=None,
            ))
        return LoadedDocument(
            scripted["relative_path"],
            scripted["layout"],
            tuple(events),
            (),
        )

    def test_shifted_key_map_negative_control_fails(self) -> None:
        passing_under_shifted_map = []
        for ssid in self.fixture["scripted"]:
            report = classify_scripted(self._shifted_key_document(ssid), self._samples(ssid))
            if report.passed:
                passing_under_shifted_map.append(ssid)
        self.assertEqual(passing_under_shifted_map, [])


if __name__ == "__main__":
    unittest.main()
