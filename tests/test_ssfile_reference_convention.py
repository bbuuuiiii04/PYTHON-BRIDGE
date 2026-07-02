"""Focused tests for physical SoundSwitch .ssfile timeline decoding and safe
cue-reference candidate handling.

These lock in the session findings (see docs/research/soundswitch/soundswitch_ssfile_format.md
and memory project_ss_ref_convention):
  - timeline time is a full signed 32-bit value (negative pre-roll preserved);
  - timeline records expose exact-key/direct and historical one-based candidate indices;
  - generic parser resolution defaults to ``ambiguous``; the bounded runtime/export
    path selects exact serialized-key lookup.

The research tools live in tools/ssfmt/re and import each other by bare module
name, so that directory is added to sys.path here.
"""
from __future__ import annotations

import importlib.util
import inspect
from datetime import datetime
import struct
import sys
import tempfile
import unittest
from pathlib import Path

_RE_DIR = Path(__file__).resolve().parent.parent / "tools" / "ssfmt" / "re"


def _load(module_name: str):
    """Load a tools/ssfmt/re module by path WITHOUT mutating sys.path.

    A persistent sys.path insertion would let other test modules' bare imports
    resolve into tools/ssfmt/re and pollute global test state, so we register
    each module in sys.modules instead (analyze_scripted_ssfile does
    ``from analyze_ssfile_structure import ...``, which then resolves there).
    """
    spec = importlib.util.spec_from_file_location(module_name, _RE_DIR / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


autoloop = _load("analyze_ssfile_structure")
scripted = _load("analyze_scripted_ssfile")
scripted_layouts = _load("analyze_scripted_layouts")
layered = _load("layered_renderer")
_load("parse_artnet_pcap")
_load("parse_venue_cues")
scripted_validator = _load("validate_scripted_capture")


def _make_record(elapsed: int, raw_reference: int) -> bytes:
    """Build one 16-byte timeline record (field_a=field_b=1)."""
    return struct.pack("<IIiI", 1, 1, elapsed, raw_reference)


class DecodeTimelineTimeTests(unittest.TestCase):
    def test_signed_negative_pre_roll_values(self):
        # Observed autoloop pre-roll values must round-trip as full signed 32-bit.
        for value in (-86, -76, -1, -200000):
            encoded = value & 0xFFFFFFFF
            low = encoded & 0xFF
            high = (encoded >> 8) & 0x00FFFFFF
            self.assertEqual(autoloop.decode_timeline_time(high, low), value)

    def test_positive_and_zero(self):
        for value in (0, 1, 601, 1800, 19271, 346802):
            encoded = value & 0xFFFFFFFF
            low = encoded & 0xFF
            high = (encoded >> 8) & 0x00FFFFFF
            self.assertEqual(autoloop.decode_timeline_time(high, low), value)
            # scripted decoder shares the same implementation
            self.assertEqual(scripted.decode_timeline_time(high, low), value)


class TimelineRecordCandidateTests(unittest.TestCase):
    def test_direct_and_one_based_candidates_exposed(self):
        rec = scripted.timeline_record(_make_record(133271, 22), 0, "ambiguous")
        self.assertEqual(rec["raw_cue_reference"], 22)
        self.assertEqual(rec["direct_dictionary_index"], 22)
        self.assertEqual(rec["one_based_dictionary_index"], 21)
        self.assertIsNone(rec["resolved_dictionary_index"])  # ambiguous never picks
        self.assertEqual(rec["reference_kind"], "cue")

    def test_rule_selects_resolved_index(self):
        data = _make_record(0, 21)
        self.assertEqual(
            scripted.timeline_record(data, 0, "exact_key")["resolved_dictionary_index"], 21
        )
        self.assertEqual(
            scripted.timeline_record(data, 0, "direct")["resolved_dictionary_index"], 21
        )
        self.assertEqual(
            scripted.timeline_record(data, 0, "one_based")["resolved_dictionary_index"], 20
        )

    def test_raw_zero_is_clear_control(self):
        rec = scripted.timeline_record(_make_record(116022, 0), 0, "direct")
        self.assertEqual(rec["reference_kind"], "clear_control")
        self.assertIsNone(rec["direct_dictionary_index"])
        self.assertIsNone(rec["one_based_dictionary_index"])
        self.assertIsNone(rec["resolved_dictionary_index"])

    def test_elapsed_negative_preserved_in_record(self):
        rec = scripted.timeline_record(_make_record(-76, 21), 0, "ambiguous")
        self.assertEqual(rec["elapsed"], -76)

    def test_autoloop_rejects_unsupported_entry_version(self):
        malformed = bytearray(_make_record(0, 1))
        malformed[:4] = struct.pack("<I", 0x01000001)
        with self.assertRaisesRegex(ValueError, "entry version"):
            autoloop._timeline_record(bytes(malformed), 0, "ambiguous")

    def test_autoloop_does_not_promote_undeclared_tail_to_timeline(self):
        data = bytearray(autoloop.EVENT_COUNT_OFFSET)
        data[:4] = autoloop.MAGIC
        data[4:8] = struct.pack("<I", 3)
        data += struct.pack("<I", 0)  # intensity-node count
        data += bytes(autoloop.POST_EVENTS_SHARED_SIZE - 1)
        data += struct.pack("<I", 1)  # cue-map version (first byte overlaps anchor)
        data += struct.pack("<I", 0)  # cue dictionary count
        data += struct.pack("<I", 0)  # declared timeline count
        data += _make_record(0, 1)  # undeclared but record-shaped tail
        data += bytes.fromhex("08000000010000000001")

        with self.assertRaisesRegex(ValueError, "undeclared byte"):
            autoloop._parse_legacy_autoloop_structure(bytes(data), "ambiguous")

    def test_autoloop_reads_full_little_endian_timeline_count(self):
        data = bytearray(autoloop.EVENT_COUNT_OFFSET)
        data[:4] = autoloop.MAGIC
        data[4:8] = struct.pack("<I", 3)
        data += struct.pack("<I", 0)
        data += bytes(autoloop.POST_EVENTS_SHARED_SIZE - 1)
        data += struct.pack("<I", 1)  # cue-map version
        data += struct.pack("<I", 1)  # one dictionary entry
        data += bytes.fromhex("00112233445566778899aabbccddeeff")
        data += struct.pack("<I", 0)
        data += struct.pack("<I", 257)
        data += b"".join(_make_record(index, 0) for index in range(257))
        data += bytes.fromhex("08000000010000000001")

        parsed = autoloop._parse_legacy_autoloop_structure(
            bytes(data), "one_based"
        )
        self.assertEqual(parsed["declared_timeline_count"], 257)
        self.assertEqual(parsed["timeline_count"], 257)
        self.assertEqual(parsed["continuation_timeline_count"], 0)
        self.assertEqual(parsed["timeline"][-1]["time"], 256)

    def test_scripted_referenced_guids_follow_resolved_dictionary_keys(self):
        cues = [
            {"cue_index": 0, "guid": "zero"},
            {"cue_index": 1, "guid": "one"},
        ]
        timeline = [
            {"resolved_dictionary_index": 1},
            {"resolved_dictionary_index": None},
            {"resolved_dictionary_index": 1},
        ]
        self.assertEqual(
            scripted_layouts._referenced_cue_guids(cues, timeline), ["one"]
        )


class SafeDefaultRegressionTests(unittest.TestCase):
    """Generic tools preserve candidates; the version-locked product is explicit."""

    def test_autoloop_parser_defaults_to_ambiguous(self):
        sig = inspect.signature(autoloop.parse_autoloop_structure)
        self.assertEqual(sig.parameters["reference_rule"].default, "ambiguous")

    def test_scripted_parser_defaults_to_ambiguous(self):
        sig = inspect.signature(scripted.parse_scripted_structure)
        self.assertEqual(sig.parameters["reference_rule"].default, "ambiguous")

    def test_scripted_timeline_record_defaults_to_ambiguous(self):
        sig = inspect.signature(scripted.timeline_record)
        self.assertEqual(sig.parameters["reference_rule"].default, "ambiguous")


class ScriptedRenderAtElapsedTests(unittest.TestCase):
    def setUp(self):
        self.parsed = {
            "reference_rule": "exact_key",
            "cues": [
                {"cue_index": 1, "guid": "color", "offset": 100},
                {"cue_index": 2, "guid": "position", "offset": 120},
            ],
            # Deliberately stored out of chronological order. Equal elapsed values
            # would retain source order as the deterministic tie-break.
            "timeline": [
                {
                    "offset": 220,
                    "elapsed": 2000,
                    "raw_cue_reference": 2,
                    "resolved_dictionary_index": 2,
                    "reference_kind": "cue",
                },
                {
                    "offset": 200,
                    "elapsed": 1000,
                    "raw_cue_reference": 1,
                    "resolved_dictionary_index": 1,
                    "reference_kind": "cue",
                },
                {
                    "offset": 240,
                    "elapsed": 3000,
                    "raw_cue_reference": 0,
                    "resolved_dictionary_index": None,
                    "reference_kind": "clear_control",
                },
            ],
        }
        self.cues = {
            "color": {"name": "RED", "offset": 10, "patch": {8: 24, 9: 42}},
            "position": {"name": "POSITION", "offset": 20, "patch": {1: 7, 3: 9}},
        }

    def render(self, elapsed_ms):
        return layered.render_at_elapsed(
            self.parsed,
            self.cues,
            elapsed_ms,
            initial_state_policy="all_zero_static_render",
            control_channels=(8, 9, 11),
        )

    def test_decoupled_color_persists_across_position_and_clear(self):
        at_position = self.render(2500)["state"]["rendered_state"]
        self.assertEqual(at_position[0], 7)
        self.assertEqual(at_position[2], 9)
        self.assertEqual(at_position[7:9], [24, 42])

        after_clear = self.render(3500)["state"]["rendered_state"]
        self.assertEqual(after_clear[0], 0)
        self.assertEqual(after_clear[2], 0)
        self.assertEqual(after_clear[7:9], [24, 42])

    def test_seek_backward_pause_and_refire_are_history_independent(self):
        forward = self.render(2500)
        backward = self.render(1500)
        paused = self.render(1500)
        refired = self.render(2500)

        self.assertEqual(backward, paused)
        self.assertEqual(forward, refired)
        self.assertEqual(backward["state"]["rendered_state"][0], 0)
        self.assertEqual(backward["state"]["rendered_state"][7:9], [24, 42])

    def test_delayed_wire_sample_includes_later_compound_cue(self):
        parsed = {
            **self.parsed,
            "cues": self.parsed["cues"]
            + [{"cue_index": 3, "guid": "color2", "offset": 140}],
            "timeline": self.parsed["timeline"]
            + [
                {
                    "offset": 260,
                    "elapsed": 2001,
                    "raw_cue_reference": 3,
                    "resolved_dictionary_index": 3,
                    "reference_kind": "cue",
                }
            ],
        }
        cues = {
            **self.cues,
            "color2": {"name": "BLUE", "offset": 30, "patch": {8: 200, 9: 201}},
        }

        immediate = layered.render_at_elapsed(
            parsed, cues, 2000, control_channels=(8, 9, 11)
        )
        sampled = layered.render_at_elapsed(
            parsed, cues, 2030, control_channels=(8, 9, 11)
        )

        self.assertEqual(immediate["state"]["rendered_state"][7:9], [24, 42])
        self.assertEqual(sampled["state"]["rendered_state"][7:9], [200, 201])

    def test_ambiguous_provenance_fails_closed(self):
        self.parsed["reference_rule"] = "ambiguous"
        with self.assertRaisesRegex(ValueError, "explicit exact_key/direct/one_based"):
            self.render(2500)

    def test_transport_play_pause_end_unload_and_refire(self):
        def transport(state, elapsed=2500):
            return layered.render_playback_state(
                self.parsed,
                self.cues,
                elapsed,
                state,
                initial_state_policy="all_zero_static_render",
                control_channels=(8, 9, 11),
            )

        playing = transport("playing")
        paused = transport("paused")
        ended = transport("ended")
        unloaded = transport("unloaded")
        refired = transport("playing")

        self.assertEqual(playing["state"], paused["state"])
        self.assertEqual(playing["state"], refired["state"])
        self.assertEqual(ended["state"]["rendered_state"], [0] * 19)
        self.assertEqual(unloaded["state"]["rendered_state"], [0] * 19)
        self.assertEqual(ended["transport_output_policy"], "all_zero_idle")

    def test_transport_wrapper_rejects_unknown_state_and_mixed_provenance(self):
        with self.assertRaisesRegex(ValueError, "transport_state must be"):
            layered.render_playback_state(
                self.parsed, self.cues, 2500, "seeking", control_channels=(8, 9, 11)
            )
        self.parsed["reference_rule"] = "mixed"
        with self.assertRaisesRegex(ValueError, "explicit exact_key/direct/one_based"):
            layered.render_playback_state(
                self.parsed, self.cues, 2500, "ended", control_channels=(8, 9, 11)
            )


class ScriptedValidatorReferenceGateTests(unittest.TestCase):
    def test_explicit_rules_are_accepted(self):
        for rule in ("exact_key", "direct", "one_based"):
            self.assertEqual(
                scripted_validator.require_resolvable_reference_rule(rule), rule
            )

    def test_ambiguous_and_mixed_fail_closed(self):
        for rule in ("ambiguous", "mixed"):
            with self.assertRaisesRegex(ValueError, "fail closed"):
                scripted_validator.require_resolvable_reference_rule(rule)

    def test_bridge_arm_scripted_anchors_track_zero(self):
        reference = datetime(2026, 6, 20, 16, 6, 40).timestamp()
        with tempfile.TemporaryDirectory() as directory:
            bridge_log = Path(directory) / "bridge.log"
            bridge_log.write_text(
                "15:00:00.000 [INFO] [SM] arm-scripted  deck=1  "
                "id=8  elapsed=0:00.000\n"
                "16:06:34.900 [INFO] [SM] arm-scripted  deck=2  "
                "id=9  elapsed=0:00.100\n"
                "\x1b[95m16:06:35.039 [INFO] [SM] arm-scripted  deck=1  "
                "id=10  elapsed=0:00.040\x1b[0m\n"
            )
            result = scripted_validator.bridge_scripted_start(
                bridge_log, reference, owner_deck=1
            )

        expected = datetime(2026, 6, 20, 16, 6, 35, 39000).timestamp() - 0.040
        self.assertAlmostEqual(result["start_epoch"], expected, places=6)
        self.assertEqual(result["deck"], 1)
        self.assertEqual(result["line_number"], 3)

    def test_elapsed_parser_accepts_minute_and_hour_forms(self):
        self.assertEqual(scripted_validator.elapsed_seconds("0:00.040"), 0.040)
        self.assertEqual(scripted_validator.elapsed_seconds("1:02:03.500"), 3723.5)

    def test_missing_bridge_anchor_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge_log = Path(directory) / "bridge.log"
            bridge_log.write_text("16:06:35.039 [INFO] [SM] stop deck=1\n")
            with self.assertRaisesRegex(ValueError, "no arm-scripted observation"):
                scripted_validator.bridge_scripted_start(
                    bridge_log,
                    datetime(2026, 6, 20, 16, 6, 40).timestamp(),
                    owner_deck=1,
                )

    def test_bridge_position_observations_classify_transport_discontinuities(self):
        reference = datetime(2026, 6, 20, 16, 20, 0).timestamp()
        with tempfile.TemporaryDirectory() as directory:
            bridge_log = Path(directory) / "bridge.log"
            bridge_log.write_text(
                "16:20:00.000 [INFO] [SM] pos  deck=1  0:10.000  mode=scripted\n"
                "16:20:05.000 [INFO] [SM] pos  deck=1  0:15.000  mode=scripted\n"
                "16:20:10.000 [INFO] [SM] pos  deck=1  0:15.000  mode=scripted\n"
                "16:20:15.000 [INFO] [SM] pos  deck=1  0:20.000  mode=scripted\n"
                "16:20:20.000 [INFO] [SM] pos  deck=1  0:05.000  mode=scripted\n"
                "16:20:21.000 [INFO] [SM] mode  deck=1  scripted→idle  "
                "elapsed=0:05.500\n"
                "16:20:24.000 [INFO] [SM] stop  deck=1  elapsed=0:05.500\n"
            )
            rows = scripted_validator.bridge_position_observations(
                bridge_log, reference, owner_deck=1
            )
            zero_rows = scripted_validator.bridge_zero_output_observations(
                bridge_log, reference, owner_deck=1
            )

        scripted_validator.classify_position_edges(rows)
        self.assertEqual(
            [row["edge_from_previous"] for row in rows],
            [
                "initial",
                "continuous",
                "paused_or_ended",
                "resume_or_refire",
                "backward_discontinuity_seek_or_loop",
            ],
        )
        self.assertEqual(
            [row["marker_kind"] for row in zero_rows],
            ["scripted_to_idle", "stop"],
        )


if __name__ == "__main__":
    unittest.main()
