from __future__ import annotations

import copy
import math
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    BeatSegment,
    PhraseLabel,
    PhraseSegment,
    SmartPhrasingEngine,
    SmartPhrasingSnapshot,
)


PROPERTY_SETTINGS = settings(max_examples=200, deadline=1000)
VALID_LABELS: tuple[PhraseLabel, ...] = ("up", "chorus", "low", "other")


def _default_snapshot(**overrides) -> SmartPhrasingSnapshot:
    values = dict(
        deck_id="1",
        track_id="track-a",
        is_playing=True,
        abs_beat=0.0,
        phrase_segments=(),
        smart_drop_beats=(),
        breakdown_segments=(),
        phrase_lookahead_beats=32.0,
        drop_window_beats=4.0,
        post_drop_beats=8.0,
        transition_window_beats=4.0,
    )
    values.update(overrides)
    return SmartPhrasingSnapshot(**values)


@st.composite
def monotone_beat_sequence(draw, min_len: int = 2, max_len: int = 200) -> list[float]:
    length = draw(st.integers(min_value=min_len, max_value=max_len))
    start = draw(st.integers(min_value=0, max_value=2000))
    increments = draw(
        st.lists(
            st.integers(min_value=1, max_value=16),
            min_size=length - 1,
            max_size=length - 1,
        )
    )
    beats = [start / 4.0]
    cursor = start
    for inc in increments:
        cursor += inc
        beats.append(cursor / 4.0)
    return beats


@st.composite
def phrase_segments(draw, max_count: int = 10) -> tuple[PhraseSegment, ...]:
    count = draw(st.integers(min_value=0, max_value=max_count))
    cursor = draw(st.integers(min_value=0, max_value=64))
    segments: list[PhraseSegment] = []
    for _ in range(count):
        gap = draw(st.integers(min_value=0, max_value=16))
        duration = draw(st.integers(min_value=1, max_value=64))
        start = cursor + gap
        end = start + duration
        label = draw(st.sampled_from(VALID_LABELS))
        segments.append(PhraseSegment(start / 4.0, end / 4.0, label))
        cursor = end
    return tuple(segments)


@st.composite
def smart_drop_beats(draw, within_range: tuple[float, float]) -> tuple[float, ...]:
    low, high = within_range
    if high < low:
        return ()
    lo = math.ceil(low * 4)
    hi = math.floor(high * 4)
    if hi < lo:
        return ()
    max_count = min(32, hi - lo + 1)
    count = draw(st.integers(min_value=0, max_value=max_count))
    raw = draw(
        st.lists(
            st.integers(min_value=lo, max_value=hi),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )
    return tuple(v / 4.0 for v in sorted(raw))


@st.composite
def breakdown_segments(
    draw,
    within_range: tuple[float, float],
    max_count: int = 10,
) -> tuple[BeatSegment, ...]:
    low, high = within_range
    if high <= low:
        return ()
    lo = math.ceil(low * 4)
    hi = math.floor(high * 4)
    if hi - lo < 1:
        return ()
    max_possible = min(max_count, (hi - lo + 1) // 2)
    count = draw(st.integers(min_value=0, max_value=max_possible))
    if count == 0:
        return ()
    points = draw(
        st.lists(
            st.integers(min_value=lo, max_value=hi),
            min_size=count * 2,
            max_size=count * 2,
            unique=True,
        )
    )
    ordered = sorted(points)
    segments = []
    for start, end in zip(ordered[0::2], ordered[1::2]):
        if start < end:
            segments.append(BeatSegment(start / 4.0, end / 4.0))
    return tuple(segments)


@st.composite
def snapshot_factory(
    draw,
    *,
    within_range: tuple[float, float] = (0.0, 256.0),
) -> SmartPhrasingSnapshot:
    low, high = within_range
    abs_beat = draw(
        st.integers(
            min_value=math.ceil(low * 4),
            max_value=max(math.ceil(low * 4), math.floor(high * 4)),
        )
    ) / 4.0
    return _default_snapshot(
        deck_id=draw(st.sampled_from(("1", "2", "deck-a"))),
        track_id=draw(st.sampled_from(("track-a", "track-b"))),
        is_playing=True,
        abs_beat=abs_beat,
        phrase_segments=draw(phrase_segments()),
        smart_drop_beats=draw(smart_drop_beats(within_range)),
        breakdown_segments=draw(breakdown_segments(within_range)),
        phrase_lookahead_beats=draw(st.integers(min_value=1, max_value=128)) / 2.0,
        drop_window_beats=draw(st.integers(min_value=1, max_value=64)) / 2.0,
        post_drop_beats=draw(st.integers(min_value=1, max_value=64)) / 2.0,
        transition_window_beats=draw(st.integers(min_value=1, max_value=64)) / 2.0,
    )


@st.composite
def _drop_crossing_case(draw) -> tuple[list[float], tuple[float, ...]]:
    beats = draw(monotone_beat_sequence())
    drops = draw(smart_drop_beats((beats[0], beats[-1])))
    return beats, drops


@st.composite
def _breakdown_case(draw) -> tuple[BeatSegment, list[float]]:
    start = draw(st.integers(min_value=8, max_value=512)) / 4.0
    duration = draw(st.integers(min_value=1, max_value=128)) / 4.0
    end = start + duration
    before = start - draw(st.integers(min_value=1, max_value=16)) / 4.0
    after = end + draw(st.integers(min_value=0, max_value=16)) / 4.0
    interior_count = draw(st.integers(min_value=0, max_value=20))
    interior: list[float] = []
    if end - start > 0.25:
        possible = range(math.ceil(start * 4), math.floor(end * 4) + 1)
        interior_raw = draw(
            st.lists(
                st.sampled_from(list(possible)),
                min_size=interior_count,
                max_size=interior_count,
            )
        )
        interior = [value / 4.0 for value in interior_raw if start <= value / 4.0 <= end]
    beats = sorted({before, start, *interior, end, after})
    return BeatSegment(start, end), beats


class TestSmartPhrasingProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(_drop_crossing_case())
    def test_drop_crossings_never_exceed_drops_in_range(self, case):
        beats, drops = case
        engine = SmartPhrasingEngine()
        first = beats[0]
        all_drops = tuple(sorted({first - 0.25, *drops}))
        snap = _default_snapshot(abs_beat=first - 0.25, smart_drop_beats=all_drops)
        engine.update(snap)

        crossings = 0
        for beat in beats:
            result = engine.update(replace(snap, abs_beat=beat))
            crossings += int(result.state.smart_drop_crossing)

        expected = sum(1 for drop in all_drops if first <= drop <= beats[-1])
        self.assertLessEqual(crossings, expected)

    # Known limitation: engine fires at most one crossing per tick.
    @unittest.expectedFailure
    @PROPERTY_SETTINGS
    @given(_drop_crossing_case())
    def test_drop_crossings_single_tick_multi_drop_limitation(self, case):
        """Current engine emits one boolean crossing even when one tick jumps over multiple drops."""
        beats, drops = case
        engine = SmartPhrasingEngine()
        first = beats[0]
        snap = _default_snapshot(abs_beat=first - 0.25, smart_drop_beats=drops)
        engine.update(snap)

        crossings = 0
        for beat in beats:
            result = engine.update(replace(snap, abs_beat=beat))
            crossings += int(result.state.smart_drop_crossing)

        expected = sum(1 for drop in drops if first <= drop <= beats[-1])
        self.assertEqual(crossings, expected)

    @PROPERTY_SETTINGS
    @given(
        snapshot_factory(within_range=(0.0, 128.0)),
        st.sampled_from(
            (
                "not_playing",
                "no_deck",
                "no_track",
                "no_beat",
                "deck_change",
                "track_change",
                "backward_jump",
            )
        ),
    )
    def test_reset_idempotency(self, normal_tick, reset_kind):
        normal_tick = replace(
            normal_tick,
            deck_id="1",
            track_id="track-a",
            is_playing=True,
            abs_beat=max(1.0, float(normal_tick.abs_beat or 1.0)),
        )
        dirty = replace(
            normal_tick,
            deck_id="dirty-deck",
            track_id="dirty-track",
            abs_beat=normal_tick.abs_beat + 32.0,
        )
        engine = SmartPhrasingEngine()
        engine.update(dirty)

        if reset_kind == "not_playing":
            engine.update(replace(normal_tick, is_playing=False))
            observed = engine.update(normal_tick).state
            expected = SmartPhrasingEngine().update(normal_tick).state
        elif reset_kind == "no_deck":
            engine.update(replace(normal_tick, deck_id=None))
            observed = engine.update(normal_tick).state
            expected = SmartPhrasingEngine().update(normal_tick).state
        elif reset_kind == "no_track":
            engine.update(replace(normal_tick, track_id=None))
            observed = engine.update(normal_tick).state
            expected = SmartPhrasingEngine().update(normal_tick).state
        elif reset_kind == "no_beat":
            engine.update(replace(normal_tick, abs_beat=None))
            observed = engine.update(normal_tick).state
            expected = SmartPhrasingEngine().update(normal_tick).state
        elif reset_kind == "deck_change":
            trigger = replace(normal_tick, deck_id="2")
            observed = engine.update(trigger).state
            expected = SmartPhrasingEngine().update(trigger).state
        elif reset_kind == "track_change":
            # Prime with same deck so deck_change doesn't shadow track_change.
            engine2 = SmartPhrasingEngine()
            engine2.update(
                replace(
                    normal_tick,
                    track_id="dirty-track",
                    abs_beat=normal_tick.abs_beat + 32.0,
                )
            )
            trigger = replace(normal_tick, track_id="track-b")
            observed = engine2.update(trigger).state
            expected = SmartPhrasingEngine().update(trigger).state
        else:
            engine2 = SmartPhrasingEngine()
            engine2.update(normal_tick)
            trigger = replace(normal_tick, abs_beat=max(0.0, normal_tick.abs_beat - 1.0))
            observed = engine2.update(trigger).state
            expected = SmartPhrasingEngine().update(trigger).state

        self.assertEqual(observed, expected)

    @PROPERTY_SETTINGS
    @given(snapshot_factory(within_range=(0.0, 256.0)))
    def test_transition_mask_should_arm_is_rising_edge(self, snap):
        engine = SmartPhrasingEngine()
        first = engine.update(snap).state.transition_mask_should_arm
        second = engine.update(snap).state.transition_mask_should_arm
        self.assertLessEqual(int(first) + int(second), 1)

    @PROPERTY_SETTINGS
    @given(_breakdown_case())
    def test_breakdown_crossings_dedup_per_playthrough(self, case):
        segment, beats = case
        engine = SmartPhrasingEngine()
        snap = _default_snapshot(
            abs_beat=beats[0],
            breakdown_segments=(segment,),
        )

        start_crossings = 0
        end_crossings = 0
        for beat in beats:
            state = engine.update(replace(snap, abs_beat=beat)).state
            start_crossings += int(state.breakdown_start_crossing)
            end_crossings += int(state.breakdown_end_crossing)

        self.assertEqual(start_crossings, 1)
        self.assertEqual(end_crossings, 1)

    @PROPERTY_SETTINGS
    @given(_breakdown_case())
    def test_jump_over_breakdown_fires_start_and_end_crossings(self, case):
        segment, _beats = case
        before = segment.start_beat - 0.25
        after = segment.end_beat + 0.25
        engine = SmartPhrasingEngine()
        snap = _default_snapshot(
            abs_beat=before,
            breakdown_segments=(segment,),
        )

        engine.update(snap)
        state = engine.update(replace(snap, abs_beat=after)).state

        self.assertTrue(state.breakdown_start_crossing)
        self.assertTrue(state.breakdown_end_crossing)

    @PROPERTY_SETTINGS
    @given(snapshot_factory(within_range=(0.0, 256.0)))
    def test_update_does_not_mutate_snapshot(self, snap):
        before = copy.deepcopy(snap)
        with self.assertRaises(FrozenInstanceError):
            snap.abs_beat = 1.0  # type: ignore[misc]

        SmartPhrasingEngine().update(snap)

        self.assertEqual(snap, before)


if __name__ == "__main__":
    unittest.main()
