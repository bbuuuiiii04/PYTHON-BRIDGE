from __future__ import annotations

import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TOOL = Path(__file__).resolve().parents[1] / "tools" / "artnet_compare.py"
SPEC = importlib.util.spec_from_file_location("artnet_compare", TOOL)
artnet_compare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["artnet_compare"] = artnet_compare
SPEC.loader.exec_module(artnet_compare)


class ArtNetCompareTests(unittest.TestCase):
    def _packet(self, universe: int, value: int, timestamp_ns: int, sequence: int = 1):
        payload = bytes([value & 0xFF]) + bytes(511)
        return artnet_compare._packet(universe, payload, timestamp_ns, sequence)

    def _row(self, packet, index: int, **extra):
        row = {
            "type": "frame",
            "run_id": "run",
            "sequence": packet.sequence,
            "frame_index": index,
            "dmx_sha256": hashlib.sha256(packet.payload).hexdigest(),
        }
        row.update(extra)
        return row

    def test_self_check_passes_without_sockets_or_hardware(self) -> None:
        artnet_compare.run_self_check()

    def test_sequence_wrap_uses_ordered_sidecar_rows_not_sequence_key(self) -> None:
        packets = []
        rows = []
        for index in range(260):
            sequence = (index % 255) + 1
            timestamp = 1_000_000_000 + index * 10_000_000
            u0 = self._packet(0, index, timestamp, 0)
            u1 = self._packet(1, index, timestamp + 1_000_000, sequence)
            packets.extend((u0, u1))
            rows.append(self._row(u1, index + 1, scripted_active=True, soundswitch_id="script", elapsed_ms=index))

        result = artnet_compare.evaluate_trace(
            packets,
            sidecar_rows=rows,
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_extra_u1_frames_are_allowed_but_not_coverage_evidence(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        extra_before = self._packet(1, 99, 990_000_000, 1)
        u1 = self._packet(1, 1, 1_001_000_000, 2)

        result = artnet_compare.evaluate_trace(
            [u0, extra_before, u1],
            sidecar_rows=[
                self._row(extra_before, 1, static_slots=[8]),
                self._row(u1, 2),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"static:8"},
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_INCOMPLETE)
        self.assertEqual(result.remaining_coverage, ("static:8",))

    def test_u1_can_be_denser_than_u0_when_nearest_matches_agree(self) -> None:
        u0a = self._packet(0, 1, 1_000_000_000, 0)
        u0b = self._packet(0, 2, 1_020_000_000, 0)
        u1_extra_before = self._packet(1, 99, 990_000_000, 1)
        u1a = self._packet(1, 1, 1_001_000_000, 2)
        u1_extra_mid = self._packet(1, 88, 1_010_000_000, 3)
        u1b = self._packet(1, 2, 1_021_000_000, 4)
        u1_extra_after = self._packet(1, 77, 1_030_000_000, 5)

        result = artnet_compare.evaluate_trace(
            [u0a, u0b, u1_extra_before, u1a, u1_extra_mid, u1b, u1_extra_after],
            sidecar_rows=[
                self._row(u1_extra_before, 1),
                self._row(u1a, 2),
                self._row(u1_extra_mid, 3),
                self._row(u1b, 4),
                self._row(u1_extra_after, 5),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_unmatched_sidecar_or_missing_u1_sidecar_is_invalid(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        extra_u1 = self._packet(1, 1, 1_010_000_000, 2)

        result = artnet_compare.evaluate_trace(
            [u0, u1, extra_u1],
            sidecar_rows=[self._row(u1, 1)],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_INVALID)
        self.assertEqual(result.reason, "sidecar_missing:2")

        result = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[self._row(u1, 1), self._row(extra_u1, 2, static_slots=[8])],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"static:8"},
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_INVALID)
        self.assertEqual(result.reason, "sidecar_unmatched_frame")

    def test_streaming_tolerates_sidecar_ahead_and_defers_recent_frames(self) -> None:
        # The sink writes each sidecar row before sending its packet, so at a
        # live tick the file holds rows for frames whose U1 packets are still in
        # flight. Batch mode rejects that lead; streaming mode reconciles the
        # settled prefix and still reaches PASS.
        u0a = self._packet(0, 1, 1_000_000_000, 0)
        u1a = self._packet(1, 1, 1_001_000_000, 1)
        u0b = self._packet(0, 2, 1_100_000_000, 0)
        u1b = self._packet(1, 2, 1_101_000_000, 2)
        rows = [
            self._row(u1a, 1, scripted_active=True, soundswitch_id="script"),
            self._row(u1b, 2, scripted_active=True, soundswitch_id="script"),
            # sidecar row for a third frame whose U1 packet has not arrived yet
            self._row(self._packet(1, 2, 1_102_000_000, 3), 3, scripted_active=True, soundswitch_id="script"),
        ]
        common = dict(
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"scripted:script"},
        )

        batch = artnet_compare.evaluate_trace([u0a, u1a, u0b, u1b], sidecar_rows=rows, **common)
        self.assertEqual(batch.verdict, artnet_compare.VERDICT_INVALID)
        self.assertEqual(batch.reason, "sidecar_unmatched_frame")

        stream = artnet_compare.evaluate_trace(
            [u0a, u1a, u0b, u1b], sidecar_rows=rows, streaming=True, settle_ns=0, **common
        )
        self.assertEqual(stream.verdict, artnet_compare.VERDICT_PASS)

    def test_streaming_still_fails_a_real_byte_mismatch(self) -> None:
        # Deferring recent frames must not hide a genuine mismatch on a settled
        # frame.
        u0a = self._packet(0, 1, 1_000_000_000, 0)
        u1a = self._packet(1, 9, 1_001_000_000, 1)  # wrong bytes vs U0
        u0b = self._packet(0, 2, 1_100_000_000, 0)
        u1b = self._packet(1, 2, 1_101_000_000, 2)
        rows = [self._row(u1a, 1), self._row(u1b, 2)]
        result = artnet_compare.evaluate_trace(
            [u0a, u1a, u0b, u1b],
            sidecar_rows=rows,
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            streaming=True,
            settle_ns=0,
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_FAIL)

    def test_wrong_sidecar_frame_index_cannot_create_pass(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)

        result = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[self._row(u1, 999, scripted_active=True, soundswitch_id="script")],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"scripted:script"},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_INVALID)
        self.assertEqual(result.reason, "sidecar_frame_index_mismatch:1")

    def test_missing_run_id_anchor_is_invalid(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)

        cases = (
            ({}, None),
            ({"truth_check": {"run_id": "run"}}, None),
            ({}, {"run_id": "run"}),
            ({"run_id": "run"}, {"run_id": "run"}),
        )
        for bridge_status, sidecar_header in cases:
            with self.subTest(bridge_status=bridge_status, sidecar_header=sidecar_header):
                result = artnet_compare.evaluate_trace(
                    [u0, u1],
                    sidecar_rows=[self._row(u1, 1, scripted_active=True, soundswitch_id="script")],
                    sidecar_header=sidecar_header,
                    bridge_status=bridge_status,
                    required_coverage={"scripted:script"},
                )

                self.assertEqual(result.verdict, artnet_compare.VERDICT_INVALID)
                self.assertEqual(result.reason, "run_id_missing")

    def test_malformed_sidecar_frame_rows_are_invalid(self) -> None:
        header, rows, invalid = artnet_compare.parse_sidecar_jsonl(
            '{"type":"header","run_id":"run"}\n'
            '{"type":"frame","run_id":"run","sequence":"1","frame_index":1,"dmx_sha256":"bad"}\n'
        )

        self.assertEqual(header, {"type": "header", "run_id": "run"})
        self.assertEqual(rows, [])
        self.assertTrue(invalid)

    def test_partial_sidecar_final_line_is_pending_not_evidence(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        text = '{"type":"header","run_id":"run"}\n{"type":"frame"'

        header, rows, invalid = artnet_compare.parse_sidecar_jsonl(text)

        self.assertEqual(header, {"type": "header", "run_id": "run"})
        self.assertEqual(rows, [])
        self.assertFalse(invalid)
        self.assertTrue(artnet_compare._has_partial_sidecar_tail(text))

        pending = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=rows,
            sidecar_header=header,
            bridge_status={"truth_check": {"run_id": "run"}},
            sidecar_pending=True,
        )
        self.assertEqual(pending.verdict, artnet_compare.VERDICT_INCOMPLETE)
        self.assertEqual(pending.reason, "sidecar_pending")

        timed_out = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=rows,
            sidecar_header=header,
            bridge_status={"truth_check": {"run_id": "run"}},
        )
        self.assertEqual(timed_out.verdict, artnet_compare.VERDICT_INVALID)
        self.assertEqual(timed_out.reason, "sidecar_missing:1")

    def test_idle_deck_change_does_not_satisfy_transition_coverage(self) -> None:
        u0 = self._packet(0, 0, 1_000_000_000, 0)
        u1 = self._packet(1, 0, 1_001_000_000, 1)
        u0b = self._packet(0, 0, 1_010_000_000, 0)
        u1b = self._packet(1, 0, 1_011_000_000, 2)

        result = artnet_compare.evaluate_trace(
            [u0, u1, u0b, u1b],
            sidecar_rows=[
                self._row(u1, 1, active_deck=1),
                self._row(u1b, 2, active_deck=2),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"transition|deck|1->2"},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_INCOMPLETE)

    def test_idle_row_between_bases_does_not_poison_deck_transition(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        u0b = self._packet(0, 0, 1_010_000_000, 0)
        u1b = self._packet(1, 0, 1_011_000_000, 2)
        u0c = self._packet(0, 2, 1_020_000_000, 0)
        u1c = self._packet(1, 2, 1_021_000_000, 3)

        result = artnet_compare.evaluate_trace(
            [u0, u1, u0b, u1b, u0c, u1c],
            sidecar_rows=[
                self._row(u1, 1, scripted_active=True, soundswitch_id="script", active_deck=1),
                self._row(u1b, 2, active_deck=2),
                self._row(u1c, 3, scripted_active=True, soundswitch_id="script", active_deck=1),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"transition|deck|2->1"},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_INCOMPLETE)

    def test_scripted_timeline_coverage_requires_elapsed_events(self) -> None:
        required = {
            "scripted:script",
            "scripted_start|script",
            "scripted_event|script|0:0:cue:a",
            "scripted_event|script|50:1:cue:b",
            "scripted_end|script",
            "scripted_rapid_pair|script|0:0:cue:a|50:1:cue:b",
        }
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        partial = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[self._row(u1, 1, scripted_active=True, soundswitch_id="script", elapsed_ms=0)],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )
        self.assertEqual(partial.verdict, artnet_compare.VERDICT_INCOMPLETE)

        late_only = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[self._row(u1, 1, scripted_active=True, soundswitch_id="script", elapsed_ms=200)],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )
        self.assertEqual(late_only.verdict, artnet_compare.VERDICT_INCOMPLETE)

        u0b = self._packet(0, 2, 1_010_000_000, 0)
        u1b = self._packet(1, 2, 1_011_000_000, 2)
        complete = artnet_compare.evaluate_trace(
            [u0, u1, u0b, u1b],
            sidecar_rows=[
                self._row(u1, 1, scripted_active=True, soundswitch_id="script", elapsed_ms=0),
                self._row(u1b, 2, scripted_active=True, soundswitch_id="script", elapsed_ms=60),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )
        self.assertEqual(complete.verdict, artnet_compare.VERDICT_PASS)

    def test_scripted_id_coverage_normalizes_braces_and_case(self) -> None:
        track_id = "01234567-89ab-cdef-0123-456789abcdef"
        pack = SimpleNamespace(
            scripted={
                "ignored": SimpleNamespace(
                    supported_active=True,
                    soundswitch_id="{01234567-89AB-CDEF-0123-456789ABCDEF}",
                    document=SimpleNamespace(events=()),
                )
            },
            autoloop_bindings={},
            learned_midi_bindings=(),
        )
        required = artnet_compare.build_coverage_ledger(pack)
        self.assertIn(f"scripted:{track_id}", required)

        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        result = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[
                self._row(
                    u1,
                    1,
                    scripted_active=True,
                    soundswitch_id="{01234567-89AB-CDEF-0123-456789ABCDEF}",
                )
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_overlay_release_blackout_and_transition_coverage(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        u0b = self._packet(0, 2, 1_010_000_000, 0)
        u1b = self._packet(1, 2, 1_011_000_000, 2)
        u0c = self._packet(0, 2, 1_020_000_000, 0)
        u1c = self._packet(1, 2, 1_021_000_000, 3)
        u0d = self._packet(0, 2, 1_030_000_000, 0)
        u1d = self._packet(1, 2, 1_031_000_000, 4)
        required = {
            "scripted:script",
            "static:8",
            "static_over|scripted|8",
            "static_release|scripted|8",
            "autoloop:loop",
            "autoloop_visible:loop",
            "autoloop_phase:loop:0",
            "blackout:0:0",
            "blackout_over|autoloop_visible:loop|0:0",
            "blackout_release|autoloop_visible:loop|0:0",
            "transition|deck|1->2",
            "transition|mode|scripted->autoloop",
        }
        result = artnet_compare.evaluate_trace(
            [u0, u1, u0b, u1b, u0c, u1c, u0d, u1d],
            sidecar_rows=[
                self._row(u1, 1, scripted_active=True, soundswitch_id="script", elapsed_ms=0, active_deck=1, static_slots=[8]),
                self._row(u1b, 2, scripted_active=True, soundswitch_id="script", elapsed_ms=10, active_deck=1, static_slots=[]),
                self._row(u1c, 3, native_autoloop={"status": "rendering_active", "target_identity": "loop", "phase_tick": 100}, active_deck=2, visible=True, blackout=True, blackout_bindings=["0:0"]),
                self._row(u1d, 4, native_autoloop={"status": "rendering_active", "target_identity": "loop", "phase_tick": 200}, active_deck=2, visible=True, blackout=False, blackout_bindings=[]),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_failed_native_autoloop_status_does_not_satisfy_coverage(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)

        result = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[
                self._row(
                    u1,
                    1,
                    native_autoloop={"status": "missing_autoloop_file", "target_identity": "loop", "phase_tick": 100},
                    visible=True,
                )
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={"autoloop:loop"},
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_INCOMPLETE)

    def test_authored_dark_autoloop_static_overlay_and_release(self) -> None:
        u0 = self._packet(0, 0, 1_000_000_000, 0)
        u1 = self._packet(1, 0, 1_001_000_000, 1)
        u0b = self._packet(0, 0, 1_010_000_000, 0)
        u1b = self._packet(1, 0, 1_011_000_000, 2)
        required = {
            "autoloop:dark",
            "autoloop_authored_dark:dark",
            "autoloop_phase:dark:1",
            "static:8",
            "static_over|autoloop_authored_dark:dark|8",
            "static_release|autoloop_authored_dark:dark|8",
        }
        result = artnet_compare.evaluate_trace(
            [u0, u1, u0b, u1b],
            sidecar_rows=[
                self._row(u1, 1, native_autoloop={"status": "empty_dark_look", "target_identity": "dark", "phase_tick": 7_000}, active_dark=True, visible=False, static_slots=[8]),
                self._row(u1b, 2, native_autoloop={"status": "empty_dark_look", "target_identity": "dark", "phase_tick": 7_100}, active_dark=True, visible=False, static_slots=[]),
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage=required,
        )
        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_autoloop_phase_coverage_uses_loop_cycle_ticks(self) -> None:
        u0 = self._packet(0, 1, 1_000_000_000, 0)
        u1 = self._packet(1, 1, 1_001_000_000, 1)
        result = artnet_compare.evaluate_trace(
            [u0, u1],
            sidecar_rows=[
                self._row(
                    u1,
                    1,
                    native_autoloop={"status": "rendering_active", "target_identity": "loop", "phase_tick": 250},
                    visible=True,
                )
            ],
            sidecar_header={"run_id": "run"},
            bridge_status={"truth_check": {"run_id": "run"}},
            required_coverage={
                "autoloop:loop",
                "autoloop_visible:loop",
                "autoloop_cycle|loop|300",
                "autoloop_phase:loop:2",
            },
        )

        self.assertEqual(result.verdict, artnet_compare.VERDICT_PASS)

    def test_build_coverage_ledger_expands_runtime_exam_items(self) -> None:
        event_a = SimpleNamespace(time=0, source_order=0, reference_kind="cue", resolved_cue_guid="a", source_offset=10)
        event_b = SimpleNamespace(time=40, source_order=1, reference_kind="cue", resolved_cue_guid="b", source_offset=20)
        scripted_doc = SimpleNamespace(events=(event_a, event_b))
        loop_event = SimpleNamespace(time=0, source_order=0, boundary_frame=(77,) + (0,) * 18, patch=())
        loop_doc = SimpleNamespace(events=(loop_event,), cycle_ticks=300)
        pack = SimpleNamespace(
            scripted={"script": SimpleNamespace(supported_active=True, soundswitch_id="script", document=scripted_doc)},
            autoloops={"loop": SimpleNamespace(document=loop_doc)},
            autoloop_bindings={("note", 96): SimpleNamespace(target_identity="loop")},
            learned_midi_bindings=(
                SimpleNamespace(target_kind="static_look", target_slot=8),
                SimpleNamespace(target_kind="blackout_mask", channel_zero_based=0, data_byte=0),
            ),
        )

        required = artnet_compare.build_coverage_ledger(pack)

        self.assertIn("scripted_event|script|40:1:cue:b", required)
        self.assertIn("scripted_rapid_pair|script|0:0:cue:a|40:1:cue:b", required)
        self.assertIn("autoloop_visible:loop", required)
        self.assertIn("autoloop_cycle|loop|300", required)
        self.assertIn("autoloop_phase:loop:2", required)
        self.assertIn("static_over|autoloop_visible:loop|8", required)
        self.assertIn("blackout_release|scripted|0:0", required)
        self.assertIn("transition|mode|scripted->autoloop", required)

    def test_autoloop_visible_class_uses_full_rendered_content(self) -> None:
        loop_event = SimpleNamespace(time=0, source_order=0, boundary_frame=(0, 77) + (0,) * 17, patch=())
        pack = SimpleNamespace(
            scripted={},
            autoloops={"loop": SimpleNamespace(document=SimpleNamespace(events=(loop_event,)))},
            autoloop_bindings={("note", 96): SimpleNamespace(target_identity="loop")},
            learned_midi_bindings=(),
        )

        required = artnet_compare.build_coverage_ledger(pack)

        self.assertIn("autoloop_visible:loop", required)
        self.assertNotIn("autoloop_authored_dark:loop", required)


if __name__ == "__main__":
    unittest.main()
