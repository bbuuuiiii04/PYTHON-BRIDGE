"""Tests for drop_lifecycle.py — armed_this_tick correctness.

Invariant: armed_this_tick=True IFF arm() actually ran (mutate=True on an
allowed anchor).  A dry-run (mutate=False) on an allowed anchor must return
role="drop" but armed_this_tick=False.  A disallowed anchor must return
role="post_drop", armed_this_tick=False.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rb_ss_bridge_v2.drop_lifecycle import (  # noqa: E402
    DropLifecycle,
    DropLifecycleConfig,
    DropResult,
)

_PREDECESSORS = frozenset({"up", "low", "buildup", "breakdown"})


def _cfg(*, max_drops: int = 2, impact_beats: float = 8.0) -> DropLifecycleConfig:
    return DropLifecycleConfig(
        max_drops_in_a_row=max_drops,
        drop_impact_beats=impact_beats,
        post_drop_cycle_beats=32.0,
        impact_predecessors=_PREDECESSORS,
    )


def _sp(**kw) -> types.SimpleNamespace:
    """Build a duck-typed SmartPhrasing namespace with safe defaults."""
    defaults = dict(
        abs_beat=None,
        current_phrase_start_beat=None,
        beats_into_phrase=None,
        active_drop_beat=None,
        current_phrase_is_chorus=False,
        phrase_start_crossing=False,
        smart_drop_crossing=False,
        previous_phrase_label="other",
        current_phrase_label="other",
        smart_post_drop_active=False,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


class TestArmedThisTick(unittest.TestCase):
    """armed_this_tick must be True only when arm() actually ran."""

    def _allowed_anchor_sp(self) -> types.SimpleNamespace:
        """An sp that produces an allowed anchor (buildup → chorus crossing)."""
        return _sp(
            current_phrase_is_chorus=True,
            phrase_start_crossing=True,
            current_phrase_start_beat=128.0,
            previous_phrase_label="buildup",  # in _PREDECESSORS → allowed
            abs_beat=128.0,
        )

    def test_mutate_true_returns_armed_and_increments_count(self) -> None:
        """resolve(mutate=True) on allowed anchor: armed_this_tick=True, _impact_count increments."""
        lc = DropLifecycle(_cfg())
        sp = self._allowed_anchor_sp()

        result = lc.resolve(sp, mutate=True)

        self.assertEqual(result.role, "drop")
        self.assertTrue(result.armed_this_tick, "mutate=True must set armed_this_tick=True")
        self.assertEqual(lc._impact_count, 1, "arm() must have incremented _impact_count")
        self.assertIsNotNone(lc._impact_until_beat, "arm() must have set _impact_until_beat")

    def test_mutate_false_returns_drop_but_not_armed(self) -> None:
        """resolve(mutate=False) on allowed anchor: role=drop but armed_this_tick=False, no side-effects."""
        lc = DropLifecycle(_cfg())
        sp = self._allowed_anchor_sp()

        result = lc.resolve(sp, mutate=False)

        self.assertEqual(result.role, "drop")
        self.assertFalse(result.armed_this_tick, "dry-run must NOT set armed_this_tick=True")
        self.assertEqual(lc._impact_count, 0, "dry-run must NOT increment _impact_count")
        self.assertIsNone(lc._impact_until_beat, "dry-run must NOT set _impact_until_beat")
        self.assertIsNone(lc._first_drop_anchor_beat, "dry-run must NOT set _first_drop_anchor_beat")

    def test_disallowed_anchor_returns_post_drop_not_armed(self) -> None:
        """resolve on a disallowed anchor (other→chorus, no prior lifecycle): role=post_drop, armed=False."""
        lc = DropLifecycle(_cfg())
        sp = _sp(
            current_phrase_is_chorus=True,
            phrase_start_crossing=True,
            current_phrase_start_beat=64.0,
            previous_phrase_label="other",   # NOT in _PREDECESSORS, no prior lifecycle → disallowed
            abs_beat=64.0,
        )

        result = lc.resolve(sp, mutate=True)

        self.assertEqual(result.role, "post_drop")
        self.assertFalse(result.armed_this_tick)
        self.assertEqual(lc._impact_count, 0)

    def test_mutate_true_then_false_sees_consistent_role(self) -> None:
        """After arm() fires, dry-run on same tick returns same role without re-arming."""
        lc = DropLifecycle(_cfg())
        sp = self._allowed_anchor_sp()

        r1 = lc.resolve(sp, mutate=True)
        count_after_arm = lc._impact_count

        r2 = lc.resolve(sp, mutate=False)  # same sp, same tick

        self.assertEqual(r1.role, "drop")
        self.assertEqual(r2.role, "drop")
        self.assertTrue(r1.armed_this_tick)
        # mutate=False after arm: the anchor is now set so chorus→chorus path
        # might allow another arm, but we did NOT mutate, so count must not grow
        self.assertEqual(lc._impact_count, count_after_arm,
                         "second call with mutate=False must not increment _impact_count")


if __name__ == "__main__":
    unittest.main()
