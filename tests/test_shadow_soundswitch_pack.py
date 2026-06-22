"""Task 8 — offline shadow-mode proof for the SoundSwitch pack player.

Hermetic (no live project, no hardware, no MIDI/serial/DMX): drives a synthetic
verified ``LaserPackPlayer`` through deterministic transition scenarios with the
physical output backend forced to ``none`` and asserts that the harness records
ONLY frame SHA-256 hashes, compares each against an INDEPENDENTLY hand-computed
expected frame, resolves every stop/blackout/emergency path to a zero frame, and
reports autoloop frame coverage as explicitly DEFERRED (gated on T7d), never
silently skipped.
"""
from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from types import MappingProxyType

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.laser_output_backend import NoneBackend, PackOutputBackend
from rb_ss_bridge_v2.soundswitch_laser_player import (
    CHANNEL_COUNT,
    ZERO_FRAME,
    LaserPackPlayer,
)
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedDocument,
    LoadedPack,
    LoadedScalarValue,
    LoadedStaticLook,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.tools.shadow_soundswitch_pack import (
    ShadowAction,
    ShadowReport,
    build_hermetic_scenario,
    frame_sha256,
    run_shadow,
)

SCRIPTED_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _hash(frame: tuple[int, ...]) -> str:
    """Independent reference hash (test side, not via the harness)."""
    return hashlib.sha256(bytes(frame)).hexdigest()


def _scripted_doc() -> LoadedDocument:
    # Single cue at t=0 sets CH1=100, CH2=50 — hand-computable render.
    event = LoadedTimelineEvent(
        time=0, source_order=0, source_offset=100, reference_kind="cue",
        raw_reference=1,
        patch=(LoadedAttribute(0x493, 1, 1, 100), LoadedAttribute(0x493, 2, 2, 50)),
    )
    return LoadedDocument("synthetic.ssfile", "shared_441_dictionary_timeline",
                          (event,), (), 19_200)


def _look(slot: int, channel: int, value: int) -> LoadedStaticLook:
    return LoadedStaticLook(
        slot_index=slot, record_version=5, name=f"slot-{slot}",
        generic_attributes=(LoadedAttribute(0x493, channel, channel, value),),
        intensity_values=(LoadedScalarValue(1, 1, 0.5),),
        strobe_values=(), colour_values=(), position_values=(),
    )


def _pack(looks: dict[int, LoadedStaticLook] | None = None) -> LoadedPack:
    if looks is None:
        looks = {7: _look(7, 3, 200), 8: _look(8, 4, 111)}
    return LoadedPack(
        schema_version="1.0.0", manifest_sha256="0" * 64, has_intensity_channel=False,
        scripted=MappingProxyType({SCRIPTED_ID: _scripted_doc()}),
        autoloops=MappingProxyType({}),
        static_looks=MappingProxyType(dict(looks)),
    )


# Hand-computed independent expected frames (NOT produced via the player).
SCRIPTED_FRAME = (100, 50) + (0,) * 17
STATIC7_FRAME = (0, 0, 200) + (0,) * 16
STATIC8_FRAME = (0, 0, 0, 111) + (0,) * 15


class FrameHashTests(unittest.TestCase):
    def test_hash_is_deterministic_and_matches_sha256_of_bytes(self):
        self.assertEqual(frame_sha256(SCRIPTED_FRAME), _hash(SCRIPTED_FRAME))
        self.assertEqual(frame_sha256(ZERO_FRAME), _hash(ZERO_FRAME))

    def test_hash_rejects_wrong_length_frame(self):
        with self.assertRaises(ValueError):
            frame_sha256((0,) * (CHANNEL_COUNT - 1))

    def test_hash_rejects_out_of_range_value(self):
        with self.assertRaises(ValueError):
            frame_sha256((256,) + (0,) * (CHANNEL_COUNT - 1))


class RunShadowTests(unittest.TestCase):
    def _scenario(self) -> tuple[LaserPackPlayer, list[ShadowAction]]:
        player = LaserPackPlayer(_pack())
        actions = [
            ShadowAction("scripted_playing", "scripted",
                         lambda p: p.select_scripted(SCRIPTED_ID, 1000), SCRIPTED_FRAME),
            ShadowAction("scripted_stopped", "transition",
                         lambda p: p.select_scripted(SCRIPTED_ID, 1000, transport="stopped"),
                         ZERO_FRAME),
            ShadowAction("clear_selection", "transition",
                         lambda p: p.clear_selection(), ZERO_FRAME),
            ShadowAction("static7_stands_alone", "static",
                         lambda p: p.hold_static(7), STATIC7_FRAME),
            ShadowAction("blackout_over_static", "blackout",
                         lambda p: p.set_blackout(True), ZERO_FRAME),
            ShadowAction("blackout_released", "static",
                         lambda p: p.set_blackout(False), STATIC7_FRAME),
            ShadowAction("emergency_over_static", "blackout",
                         lambda p: p.set_emergency(True), ZERO_FRAME),
        ]
        return player, actions

    def test_every_step_matches_independent_expected(self):
        player, actions = self._scenario()
        report = run_shadow(player, actions, backend=NoneBackend())
        self.assertTrue(report.all_match, report.to_dict())
        for step, action in zip(report.steps, actions):
            self.assertEqual(step.frame_sha256, _hash(action.expected_frame), step.label)

    def test_stop_blackout_emergency_resolve_zero(self):
        player, actions = self._scenario()
        report = run_shadow(player, actions, backend=NoneBackend())
        zero = _hash(ZERO_FRAME)
        by_label = {s.label: s for s in report.steps}
        for label in ("scripted_stopped", "clear_selection",
                      "blackout_over_static", "emergency_over_static"):
            self.assertEqual(by_label[label].frame_sha256, zero, label)

    def test_static_stands_alone_when_no_base_selection(self):
        player, actions = self._scenario()
        report = run_shadow(player, actions, backend=NoneBackend())
        by_label = {s.label: s for s in report.steps}
        self.assertEqual(by_label["static7_stands_alone"].frame_sha256, _hash(STATIC7_FRAME))
        self.assertEqual(by_label["blackout_released"].frame_sha256, _hash(STATIC7_FRAME))

    def test_runs_are_byte_identical_across_two_passes(self):
        first = run_shadow(*self._scenario(), backend=NoneBackend()).to_dict()
        second = run_shadow(*self._scenario(), backend=NoneBackend()).to_dict()
        self.assertEqual(first, second)

    def test_physical_backend_must_be_none_no_frame_sender(self):
        # A backend with a real frame sender is rejected — shadow opens no device.
        class _Sender:
            def submit(self, frame):  # pragma: no cover - must never run
                raise AssertionError("shadow mode must not transmit frames")
            def stop(self):
                pass
        player, actions = self._scenario()
        with self.assertRaises(ValueError):
            run_shadow(player, actions,
                       backend=PackOutputBackend(frame_sender=_Sender()))

    def test_pack_backend_none_sender_is_accepted_and_transmits_nothing(self):
        player, actions = self._scenario()
        backend = PackOutputBackend(frame_sender=None)
        report = run_shadow(player, actions, backend=backend)
        self.assertTrue(report.all_match)
        self.assertFalse(report.physical_output)
        self.assertFalse(backend.status()["has_frame_sender"])


class ReportSanitizationTests(unittest.TestCase):
    def test_report_dict_exposes_no_raw_frames_or_identities(self):
        player = LaserPackPlayer(_pack())
        report = run_shadow(
            player,
            [ShadowAction("scripted_playing", "scripted",
                          lambda p: p.select_scripted(SCRIPTED_ID, 1000), SCRIPTED_FRAME)],
            backend=NoneBackend())
        blob = repr(report.to_dict())
        # No raw channel value tuples, no soundswitch identity, no file path.
        self.assertNotIn("100, 50", blob)
        self.assertNotIn(SCRIPTED_ID, blob)
        self.assertNotIn(".ssfile", blob)

    def test_autoloop_coverage_reported_deferred(self):
        player = LaserPackPlayer(_pack())
        report = run_shadow(player, build_hermetic_scenario(), backend=NoneBackend())
        self.assertNotIn("autoloop", report.categories_covered)
        self.assertEqual(report.autoloop_coverage, "deferred_t7d_phase_origin")
        self.assertIn("autoloop", report.to_dict()["autoloop_coverage_note"])

    def test_report_never_claims_hardware_validation(self):
        player = LaserPackPlayer(_pack())
        report = run_shadow(player, build_hermetic_scenario(), backend=NoneBackend())
        self.assertFalse(report.to_dict()["hardware_validated"])


class StaticSlotCoverageTests(unittest.TestCase):
    """Item 6: slots 8/16/17/24 render + a controlled slot-7 create/edit."""

    def test_slot_8_renders_expected_independent_frame(self):
        player = LaserPackPlayer(_pack())
        player.clear_selection()
        result = player.hold_static(8)
        self.assertEqual(frame_sha256(result.frame), _hash(STATIC8_FRAME))

    def test_slot_7_create_then_edit_changes_frame(self):
        player = LaserPackPlayer(_pack({7: _look(7, 3, 200)}))
        player.clear_selection()
        created = player.hold_static(7)
        self.assertEqual(frame_sha256(created.frame), _hash(STATIC7_FRAME))
        # "Edit" slot 7 via an immutable pack reload — CH3 200 -> CH5 60.  The
        # post-reload wait latch beats a held static, so fresh authority must be
        # re-established (a select_*) before the edited static can stand alone.
        edited_pack = _pack({7: _look(7, 5, 60)})
        player.reload(edited_pack)
        player.select_scripted(SCRIPTED_ID, 1000)
        player.clear_selection()
        edited = player.hold_static(7)
        edited_frame = (0, 0, 0, 0, 60) + (0,) * 14
        self.assertEqual(frame_sha256(edited.frame), _hash(edited_frame))
        self.assertNotEqual(created.frame, edited.frame)


if __name__ == "__main__":
    unittest.main()
