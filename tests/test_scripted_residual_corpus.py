"""Synthetic tests for the research-only scripted residual corpus."""
from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


_RE_DIR = Path(__file__).resolve().parent.parent / "tools" / "ssfmt" / "re"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _RE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("parse_venue_cues")
corpus = _load("build_scripted_residual_corpus")


GUID = "00112233445566778899aabbccddeeff"


def _venue_record() -> bytes:
    name = "TEST\0".encode("utf-16le")
    entries = b"".join(
        struct.pack("<III", 1, group, 82) + bytes([17]) * 4
        for group in (0x493, 0x496)
    )
    return (
        struct.pack("<I", 5)
        + name
        + b"\xaa\xbb\xcc\xdd"
        + bytes.fromhex(GUID)
        + struct.pack("<III", 7, 1, 1)
        + bytes.fromhex("ffeeddccbbaa99887766554433221100")
        + struct.pack("<III", 1, 1, 2)
        + entries
    )


def _event(sequence: int, elapsed: int, *, exact: bool = False, guid: str | None = GUID):
    residuals = [] if exact else [{"channel": 1, "expected": 17, "actual": 0, "delta": -17}]
    return {
        "sequence": sequence,
        "source_sequence": sequence,
        "time": elapsed,
        "record_offset": 100 + sequence * 16,
        "raw_cue_reference": sequence + 1,
        "resolved_dictionary_index": sequence,
        "reference_kind": "cue",
        "guid": guid,
        "cue_name": "TEST" if guid else None,
        "patch": {"1": 17} if guid else {},
        "expected_wire_state": [17] + [0] * 18,
        "observed_wire_state": [0] * 19,
        "byte_exact": exact,
        "channel_residuals": residuals,
        "state": {"control_layers": {"fixture_control": {"8": 9}}},
    }


def _report(group: str, pcap: str, events: list[dict], *, positions=None):
    return {
        "scripted_file": "/tmp/{11111111-2222-3333-4444-555555555555}.ssfile",
        "scripted_file_sha256": "scripted",
        "fixture_group": group,
        "reference_rule": "one_based",
        "pcap": pcap,
        "pcap_sha256": f"sha-{pcap}",
        "venue": "/tmp/Venue.bin",
        "venue_sha256": "venue",
        "events": events,
        "bridge_position_samples": positions or [],
    }


class ScriptedResidualCorpusTests(unittest.TestCase):
    def setUp(self):
        self.venue = _venue_record()

    def build(self, rows):
        return corpus.build_corpus(rows, self.venue)

    def test_output_order_is_deterministic_across_input_order_and_groups(self):
        a = ("b.json", "report-b", _report("0x496", "b.pcap", [_event(0, 100)]))
        b = ("a.json", "report-a", _report("0x493", "a.pcap", [_event(0, 100)]))
        self.assertEqual(self.build([a, b]), self.build([b, a]))
        self.assertEqual(
            [row["fixture_group"] for row in self.build([a, b])["observations"]],
            ["0x493", "0x496"],
        )

    def test_duplicate_states_remain_distinct_and_cluster_together(self):
        report = _report("0x493", "a.pcap", [_event(0, 100), _event(1, 101)])
        result = self.build([("a.json", "report", report)])
        self.assertEqual(result["residual_observation_count"], 2)
        self.assertEqual(result["cluster_count"], 1)
        self.assertEqual(result["clusters"][0]["observation_count"], 2)

    def test_adjacent_compound_cue_spacing_and_raw_record_are_preserved(self):
        report = _report("0x493", "a.pcap", [_event(0, 100), _event(1, 101)])
        result = self.build([("a.json", "report", report)])
        first = result["observations"][0]
        self.assertEqual(first["timeline_context"]["spacing_to_next_ms"], 1)
        self.assertEqual(first["venue_cue_record"]["raw_hex"], self.venue.hex())
        self.assertIn("unknown_u8_0x00", first["venue_cue_record"]["header_fields"])

    def test_missing_guid_fails_visible_without_dropping_observation(self):
        report = _report("0x493", "a.pcap", [_event(0, 100, guid=None)])
        result = self.build([("a.json", "report", report)])
        row = result["observations"][0]
        self.assertIsNone(row["venue_cue_record"])
        self.assertIn("missing_guid", row["signature_key"])

    def test_exact_and_residual_uses_of_same_guid_are_reported(self):
        report = _report(
            "0x493", "a.pcap", [_event(0, 100, exact=True), _event(1, 101)]
        )
        result = self.build([("a.json", "report", report)])
        usage = next(row for row in result["cue_usage"] if row["cue_identity"] == GUID)
        self.assertEqual(len(usage["exact_uses"]), 1)
        self.assertEqual(len(usage["residual_uses"]), 1)

    def test_position_residual_uses_active_compound_event(self):
        events = [_event(0, 100), _event(1, 101, exact=True)]
        positions = [
            {
                "elapsed_ms": 101,
                "line_number": 5,
                "edge_from_previous": "forward_seek",
                "expected_wire_state": [17] + [0] * 18,
                "observed_wire_state": [0] * 19,
                "byte_exact": False,
                "channel_residuals": [
                    {"channel": 1, "expected": 17, "actual": 0, "delta": -17}
                ],
            }
        ]
        report = _report("0x493", "a.pcap", events, positions=positions)
        result = self.build([("a.json", "report", report)])
        position = next(
            row for row in result["observations"] if row["observation_kind"] == "position"
        )
        self.assertEqual(position["timeline_context"]["current"]["sequence"], 1)


if __name__ == "__main__":
    unittest.main()
