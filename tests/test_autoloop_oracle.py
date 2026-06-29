"""Synthetic tests for the offline SoundSwitch Autoloop oracle core."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_laser_player import render_autoloop_frame
from rb_ss_bridge_v2.soundswitch_pack_loader import (
    LoadedAttribute,
    LoadedDocument,
    LoadedTimelineEvent,
)
from rb_ss_bridge_v2.tools.ssfmt.re.autoloop_oracle.active_look import (
    UNRELIABLE_GROUNDTRUTH,
    ActiveLookResolver,
    LookEvent,
)
from rb_ss_bridge_v2.tools.ssfmt.re.autoloop_oracle.diff import (
    frame_mismatch,
    phase_tick,
    predicted_frame,
    score,
    search,
)


def _event(time: int, order: int, value: int) -> LoadedTimelineEvent:
    return LoadedTimelineEvent(
        time=time,
        source_order=order,
        source_offset=order,
        reference_kind="cue",
        raw_reference=order + 1,
        patch=(LoadedAttribute(0x493, 1, 1, value),),
    )


def _loop() -> LoadedDocument:
    return LoadedDocument(
        "SSAutoLoopSynthetic.ssfile",
        "shared_441_dictionary_timeline",
        tuple(_event(index * 600, index, index + 1) for index in range(8)),
        (),
        19_200,
    )


def _frames(loop: LoadedDocument, beats: tuple[float, ...], *, offset: float = 0.0,
            latency: float = 0.0):
    return [
        (beat + latency, predicted_frame(loop, beat, offset))
        for beat in beats
    ]


class AutoloopOracleDiffTests(unittest.TestCase):
    def test_exact_match_scores_all_frames(self) -> None:
        loop = _loop()
        result = score(
            _frames(loop, (0.0, 1.0, 2.0)),
            lambda t: t,
            lambda _t: loop.relative_path,
            {loop.relative_path: loop},
            latency_s=0.0,
            phase_offset_beats=0.0,
            tol=0,
        )
        self.assertEqual(result.scored_frames, 3)
        self.assertEqual(result.exact_match_rate, 1.0)

    def test_phase_offset_recovery(self) -> None:
        loop = _loop()
        best = search(
            _frames(loop, (0.0, 1.0, 2.0), offset=2.0),
            lambda t: t,
            lambda _t: loop.relative_path,
            {loop.relative_path: loop},
            latency_grid=(0.0,),
            phase_grid=(0.0, 1.0, 2.0, 3.0),
            tol=0,
        )
        self.assertEqual(best.phase_offset_beats, 2.0)
        self.assertEqual(best.score.exact_match_rate, 1.0)

    def test_latency_recovery(self) -> None:
        loop = _loop()
        best = search(
            _frames(loop, (0.8, 1.8, 2.8), latency=0.25),
            lambda t: t,
            lambda _t: loop.relative_path,
            {loop.relative_path: loop},
            latency_grid=(0.0, 0.25, 0.5),
            phase_grid=(0.0,),
            tol=0,
        )
        self.assertEqual(best.latency_s, 0.25)
        self.assertEqual(best.score.exact_match_rate, 1.0)

    def test_deliberate_mismatch_is_not_a_false_pass(self) -> None:
        loop = _loop()
        timestamp, actual = _frames(loop, (0.0,))[0]
        corrupted = (actual[0] + 1, *actual[1:])
        self.assertEqual(frame_mismatch(predicted_frame(loop, 0.0, 0.0), corrupted, 0), 1)
        result = score(
            [(timestamp, corrupted)],
            lambda t: t,
            lambda _t: loop.relative_path,
            {loop.relative_path: loop},
            latency_s=0.0,
            phase_offset_beats=0.0,
            tol=0,
        )
        self.assertEqual(result.exact_match_frames, 0)
        self.assertEqual(result.per_channel_mismatches, {1: 1})

    def test_wrap_correctness(self) -> None:
        loop = _loop()
        self.assertEqual(
            render_autoloop_frame(loop, phase_tick(33.0, 0.0)),
            render_autoloop_frame(loop, phase_tick(1.0, 0.0)),
        )

    def test_autocycle_guard_excludes_gap(self) -> None:
        loop = _loop()
        resolver = ActiveLookResolver([
            LookEvent(0.0, 64, loop.relative_path, 0.0, "synthetic"),
        ])
        result = score(
            [(40.0, predicted_frame(loop, 40.0, 0.0))],
            lambda t: t,
            resolver,
            {loop.relative_path: loop},
            latency_s=0.0,
            phase_offset_beats=0.0,
            tol=0,
        )
        self.assertEqual(result.scored_frames, 0)
        self.assertEqual(result.excluded_counts, {UNRELIABLE_GROUNDTRUTH: 1})


if __name__ == "__main__":
    unittest.main()
