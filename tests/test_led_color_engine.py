"""Unit tests for led_color_engine.py — M1 milestone.

Coverage:
- p_to_rgb piecewise interpolation (correct values; no orange/yellow resting colors)
- Weighted palette selection statistical ordering
- Dwell: palette held for N tracks then re-picked
- Lock: freezes palette across tracks AND suppresses snap
- drop_section_index increments only on NEW drop sections, resets per track
- Snap: excludes current palette; fires with seeded probability; suppressed by lock
- Focus: mono → near-single-color vs full → wide window
- resolve_color: {} for disabled / baked / exempt; valid RGB otherwise
- multi=True returns color_a / color_b (plus "color")
- diy_eligible: tag→range filtering; untagged/white/signature always True; lock unrelated
- Track detection via (active, load_gen) deque — A→B→A flap does NOT advance dwell
- Determinism: same set_seed + same call sequence ⇒ identical colors
- Seed variety: different set_seed ⇒ different colors (statistically)
- snapshot() reflects live-control mutations; lock freezes drift/snap
"""
from __future__ import annotations

import logging
import random
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.led_color_engine import (  # noqa: E402
    LedColorEngine,
    _p_to_rgb,
    _blend_white,
    _scale_stop_positions,
)
from rb_ss_bridge_v2.led_models import ColorEngineConfig, Palette  # noqa: E402


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

_DEFAULT_SCALE_STOPS = {
    "green":   (0, 255, 0),
    "cyan":    (0, 255, 255),
    "blue":    (0, 0, 255),
    "purple":  (160, 0, 255),
    "magenta": (255, 0, 160),
    "red":     (255, 0, 0),
}

_DEFAULT_PALETTES = {
    "blue_cyan": Palette(
        range=("cyan", "blue"),
        white=0.0,
        spread=0.10,
        weight=14.0,
        dwell=4,
        focus_modes={"mono": 3.0, "lean": 3.0, "full": 2.0},
    ),
    "red": Palette(
        range=("red", "red"),
        white=0.0,
        spread=0.10,
        weight=9.0,
        dwell=6,
    ),
    "green": Palette(
        range=("green", "green"),
        white=0.0,
        spread=0.08,
        weight=4.0,
        dwell=5,
    ),
    "red_white": Palette(
        range=("red", "red"),
        white=0.4,
        spread=0.10,
        weight=3.0,
    ),
    "cyan_blue_purple": Palette(
        range=("cyan", "purple"),
        white=0.0,
        spread=0.22,
        weight=3.0,
        focus_modes={"mono": 2.0, "lean": 3.0, "full": 3.0},
    ),
    "purple_pink_white": Palette(
        range=("purple", "magenta"),
        white=0.5,
        spread=0.15,
        weight=1.0,
    ),
}


def _make_config(**overrides: Any) -> ColorEngineConfig:
    """Build a ColorEngineConfig with default palettes, overridable."""
    base = dict(
        enabled=True,
        scale_stops=dict(_DEFAULT_SCALE_STOPS),
        palette_dwell_tracks=4,
        snap_eligible_drop_indices=(2, 3),
        big_shift_chance=0.25,
        big_shift_weight_bias=1.0,
        drama_by_role=True,
        role_spread={"drop": 0.35, "groove": 0.12, "ambient": 0.10},
        step_within_section={"drop": False, "post_drop": True, "groove": True},
        fade_beats_by_role={
            "drop": 0.0, "buildup": 0.0, "breakdown": 4.0,
            "post_drop": 2.0, "groove": 2.0, "ambient": 4.0,
        },
        exempt_looks=("rt_drop_white_aggressive", "rt_post_drop_white_shatter"),
        diy_color_tags={
            "groove_diy_red_chasing": "red",
            "groove_diy_blue_sparkle": "blue",
            "groove_diy_bright_white_chase": "white",
            "buildup_diy_white_sparse": "white",
            "drop_diy_rainbow_sparkle": "BIG_DROP_SIGNATURE",
            "groove_diy_groove": "TODO",
            "drop_diy_1_red_white_chase": "red+white",
            "ambient_pb_halves": "purple",
        },
        set_seed_mode="random",
        palettes=dict(_DEFAULT_PALETTES),
    )
    base.update(overrides)
    return ColorEngineConfig(**base)


def _engine(seed: int = 42, **overrides: Any) -> LedColorEngine:
    """Create a deterministic engine with set_seed=seed."""
    return LedColorEngine(_make_config(**overrides), set_seed=seed)


def _dispatch(
    engine: LedColorEngine,
    *,
    deck: int = 1,
    load_gen: int = 1,
    content_id: str = "track-abc",
    filepath: str = "/music/track.mp3",
    role: str = "groove",
    section_id: str = "s1",
    cycle: int = 0,
) -> None:
    engine.begin_dispatch(
        active_deck=deck,
        load_gen=load_gen,
        content_id=content_id,
        filepath=filepath,
        role=role,
        section_id=section_id,
        cycle=cycle,
    )


def _color(
    engine: LedColorEngine,
    *,
    role: str = "groove",
    section_id: str = "s1",
    cycle: int = 0,
    look_name: str = "some_look",
    color_source: str = "engine",
    multi: bool = False,
) -> dict:
    return engine.resolve_color(
        role=role,
        section_id=section_id,
        cycle=cycle,
        look_name=look_name,
        color_source=color_source,
        multi=multi,
    )


# ---------------------------------------------------------------------------
# p_to_rgb tests
# ---------------------------------------------------------------------------

class TestPToRgb(unittest.TestCase):

    def setUp(self) -> None:
        self._stops = dict(_DEFAULT_SCALE_STOPS)
        self._pos = _scale_stop_positions(self._stops)

    def _rgb(self, p: float) -> tuple[int, int, int]:
        return _p_to_rgb(p, self._stops, self._pos)

    def test_exact_stop_green(self) -> None:
        self.assertEqual(self._rgb(0.0), (0, 255, 0))

    def test_exact_stop_red(self) -> None:
        self.assertEqual(self._rgb(1.0), (255, 0, 0))

    def test_exact_stop_cyan(self) -> None:
        # cyan is at 1/5 = 0.2
        self.assertEqual(self._rgb(0.2), (0, 255, 255))

    def test_exact_stop_blue(self) -> None:
        # blue is at 2/5 = 0.4
        self.assertEqual(self._rgb(0.4), (0, 0, 255))

    def test_exact_stop_purple(self) -> None:
        # purple at 3/5 = 0.6
        r, g, b = self._rgb(0.6)
        self.assertEqual((r, g, b), (160, 0, 255))

    def test_exact_stop_magenta(self) -> None:
        # magenta at 4/5 = 0.8
        r, g, b = self._rgb(0.8)
        self.assertEqual((r, g, b), (255, 0, 160))

    def test_midpoint_green_cyan(self) -> None:
        # midpoint between green(0.0) and cyan(0.2) → p=0.1
        r, g, b = self._rgb(0.1)
        # green=(0,255,0), cyan=(0,255,255) → mid=(0,255,127 or 128)
        self.assertEqual(r, 0)
        self.assertEqual(g, 255)
        self.assertIn(b, (127, 128))

    def test_clamped_below_zero(self) -> None:
        self.assertEqual(self._rgb(-0.5), self._rgb(0.0))

    def test_clamped_above_one(self) -> None:
        self.assertEqual(self._rgb(1.5), self._rgb(1.0))

    def test_piecewise_not_endpoint_lerp(self) -> None:
        """Piecewise lerp at p=0.5 (midpoint blue↔purple) is NOT the same
        as a direct green→red lerp.  Direct green→red at 0.5 would give
        (127,127,0) — orange/yellow.  Piecewise must give something blue/purple.
        """
        r, g, b = self._rgb(0.5)
        # Direct lerp between green (0,255,0) and red (255,0,0) at 0.5
        # would give (127,127,0) — yellow.  That must NOT happen.
        direct_lerp_g = 127  # approximation
        self.assertFalse(
            r > 50 and g > 50 and b < 50,
            msg=f"p=0.5 gave ({r},{g},{b}) — looks orange/yellow (direct-lerp bug)"
        )
        # p=0.5 is midpoint between blue(0.4) and purple(0.6) → should have blue/purple
        # blue=(0,0,255) purple=(160,0,255) → mid=(80,0,255)
        self.assertGreater(b, 200)

    def test_no_orange_yellow_full_scale(self) -> None:
        """Sample p in [0,1] → no resting orange/yellow (R>120 AND G in [60,200] AND B<60)."""
        for i in range(101):
            p = i / 100.0
            r, g, b = self._rgb(p)
            is_orange_yellow = r > 120 and 60 <= g <= 200 and b < 60
            self.assertFalse(
                is_orange_yellow,
                msg=f"p={p:.2f} → RGB({r},{g},{b}) looks orange/yellow"
            )

    def test_no_orange_yellow_every_default_palette_range(self) -> None:
        """Sample across each default palette's p-interval → no orange/yellow."""
        pos = self._pos
        for pal_name, pal in _DEFAULT_PALETTES.items():
            stop_a, stop_b = pal.range
            p_a = pos.get(stop_a, 0.0)
            p_b = pos.get(stop_b, 0.0)
            lo_p, hi_p = min(p_a, p_b), max(p_a, p_b)
            span = hi_p - lo_p
            if span < 1e-9:
                # Point palette — test just the one point
                r, g, b = self._rgb(lo_p)
                is_oy = r > 120 and 60 <= g <= 200 and b < 60
                self.assertFalse(is_oy, msg=f"{pal_name} point p={lo_p} → ({r},{g},{b}) orange/yellow")
                continue
            for i in range(21):
                p = lo_p + (i / 20.0) * span
                r, g, b = self._rgb(p)
                is_oy = r > 120 and 60 <= g <= 200 and b < 60
                self.assertFalse(
                    is_oy,
                    msg=f"{pal_name} p={p:.3f} → RGB({r},{g},{b}) orange/yellow"
                )


class TestBlendWhite(unittest.TestCase):
    def test_zero_white_unchanged(self) -> None:
        self.assertEqual(_blend_white((0, 0, 255), 0.0), (0, 0, 255))

    def test_full_white(self) -> None:
        self.assertEqual(_blend_white((0, 0, 255), 1.0), (255, 255, 255))

    def test_half_white(self) -> None:
        r, g, b = _blend_white((0, 0, 0), 0.5)
        self.assertIn(r, (127, 128))
        self.assertIn(g, (127, 128))
        self.assertIn(b, (127, 128))


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def _run_sequence(self, seed: int) -> list[tuple]:
        """Run a fixed dispatch+resolve sequence and collect colors."""
        e = _engine(seed=seed)
        results = []
        for lg in range(1, 6):
            _dispatch(e, load_gen=lg, section_id=f"s{lg}")
            c = _color(e, section_id=f"s{lg}")
            results.append(c.get("color"))
        return results

    def test_same_seed_same_output(self) -> None:
        a = self._run_sequence(seed=12345)
        b = self._run_sequence(seed=12345)
        self.assertEqual(a, b)

    def test_different_seed_different_output(self) -> None:
        a = self._run_sequence(seed=111)
        b = self._run_sequence(seed=999)
        # It's astronomically unlikely all 5 colors match across seeds
        self.assertNotEqual(a, b)

    def test_same_seed_fixed_mode(self) -> None:
        cfg = _make_config(set_seed_mode="fixed:777")
        e1 = LedColorEngine(cfg)
        e2 = LedColorEngine(cfg)
        _dispatch(e1, load_gen=1)
        _dispatch(e2, load_gen=1)
        c1 = _color(e1)
        c2 = _color(e2)
        self.assertEqual(c1, c2)


# ---------------------------------------------------------------------------
# Weighted selection statistical test
# ---------------------------------------------------------------------------

class TestWeightedSelection(unittest.TestCase):

    def test_high_weight_palette_selected_more_often(self) -> None:
        """blue_cyan(14) should dominate over purple_pink_white(1)."""
        # Use a fixed seed for reproducibility
        e = _engine(seed=42)
        counts: dict[str, int] = {name: 0 for name in _DEFAULT_PALETTES}

        N = 200
        for i in range(N):
            # Each engine has fresh state; simulate by driving many track changes
            _dispatch(e, load_gen=i + 1, section_id=f"s{i}")
            snap = e.snapshot()
            counts[snap["current_palette"]] = counts.get(snap["current_palette"], 0) + 1

        # blue_cyan (weight 14) should appear more than purple_pink_white (weight 1)
        self.assertGreater(
            counts.get("blue_cyan", 0),
            counts.get("purple_pink_white", 0),
            msg=f"counts={counts}"
        )
        # red (weight 9) should appear more than green (weight 4)
        self.assertGreater(
            counts.get("red", 0) + counts.get("blue_cyan", 0),
            counts.get("purple_pink_white", 0) + counts.get("green", 0),
            msg=f"counts={counts}"
        )


# ---------------------------------------------------------------------------
# Dwell tests
# ---------------------------------------------------------------------------

class TestDwell(unittest.TestCase):

    def test_dwell_holds_palette(self) -> None:
        """Palette should not change within dwell window."""
        # blue_cyan has dwell=4
        e = _engine(seed=100)
        # Force initial palette to blue_cyan by patching after construction
        # (we need to control which palette is first selected)
        # Instead, just track: within dwell, current_palette must stay constant
        snap0 = e.snapshot()
        initial = snap0["current_palette"]
        initial_dwell = snap0["dwell_remaining"]

        # Drive load_gen changes up to (but not past) dwell expiry
        for i in range(initial_dwell - 1):
            _dispatch(e, load_gen=i + 2)

        snap_end = e.snapshot()
        # Should still be on the same palette (dwell not yet expired)
        self.assertEqual(snap_end["current_palette"], initial)

    def test_dwell_expires_repick(self) -> None:
        """After dwell_remaining reaches 0, a new track triggers a re-pick."""
        # Use a config with dwell=1 to force immediate expiry
        minimal_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0, dwell=1),
            "p2": Palette(range=("red", "red"), weight=1.0, dwell=1),
        }
        cfg = _make_config(palettes=minimal_pal, palette_dwell_tracks=1)

        # Run many seeds to ensure we see a palette change in at least one
        palette_changed = False
        for seed in range(50):
            e = LedColorEngine(cfg, set_seed=seed)
            initial = e.snapshot()["current_palette"]
            # Advance 5 tracks; dwell=1 means first new track decrements to 0
            for lg in range(1, 10):
                _dispatch(e, load_gen=lg)
            final = e.snapshot()["current_palette"]
            if final != initial:
                palette_changed = True
                break

        self.assertTrue(palette_changed, "Palette never re-picked even after many expirations")

    def test_dwell_decrements_per_track_not_per_dispatch(self) -> None:
        """Repeated dispatch calls for the same (deck, load_gen) do not decrement dwell."""
        e = _engine(seed=42)
        snap0 = e.snapshot()
        initial_dwell = snap0["dwell_remaining"]

        # Dispatch same track many times — should not advance dwell
        for _ in range(5):
            _dispatch(e, deck=1, load_gen=999, section_id="s1")

        snap1 = e.snapshot()
        # dwell_remaining should be initial_dwell - 1 (only first appearance counts)
        self.assertEqual(snap1["dwell_remaining"], initial_dwell - 1)


# ---------------------------------------------------------------------------
# Track detection (A→B→A flap)
# ---------------------------------------------------------------------------

class TestTrackDetection(unittest.TestCase):

    def test_flap_does_not_advance_dwell(self) -> None:
        """A→B→A within the recent-keys deque does not count A's re-appearance as new."""
        e = _engine(seed=42)
        snap0 = e.snapshot()
        initial_dwell = snap0["dwell_remaining"]

        _dispatch(e, deck=1, load_gen=1)  # A — new
        _dispatch(e, deck=1, load_gen=2)  # B — new
        _dispatch(e, deck=1, load_gen=1)  # A again — in deque, NOT new

        snap = e.snapshot()
        # Two genuinely new tracks seen → dwell should be initial - 2
        self.assertEqual(snap["dwell_remaining"], initial_dwell - 2)

    def test_distinct_tracks_advance_dwell(self) -> None:
        """Three distinct tracks → dwell decrements three times."""
        e = _engine(seed=42)
        snap0 = e.snapshot()
        initial_dwell = snap0["dwell_remaining"]

        _dispatch(e, deck=1, load_gen=1)
        _dispatch(e, deck=1, load_gen=2)
        _dispatch(e, deck=1, load_gen=3)

        snap = e.snapshot()
        self.assertEqual(snap["dwell_remaining"], initial_dwell - 3)

    def test_same_key_no_dwell_advance(self) -> None:
        """Identical (deck, load_gen) never advances dwell after first appearance."""
        e = _engine(seed=42)
        snap0 = e.snapshot()
        initial_dwell = snap0["dwell_remaining"]

        for _ in range(10):
            _dispatch(e, deck=1, load_gen=42)

        snap = e.snapshot()
        self.assertEqual(snap["dwell_remaining"], initial_dwell - 1)


# ---------------------------------------------------------------------------
# Lock tests
# ---------------------------------------------------------------------------

class TestLock(unittest.TestCase):

    def test_lock_freezes_palette_across_tracks(self) -> None:
        """lock=True: palette does not change even after dwell expires."""
        single_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0, dwell=1),
            "p2": Palette(range=("red", "red"), weight=1.0, dwell=1),
        }
        cfg = _make_config(palettes=single_pal, palette_dwell_tracks=1)
        e = LedColorEngine(cfg, set_seed=99)
        initial = e.snapshot()["current_palette"]
        e.lock()

        for lg in range(1, 20):
            _dispatch(e, load_gen=lg)

        snap = e.snapshot()
        self.assertEqual(snap["current_palette"], initial)
        self.assertTrue(snap["lock"])

    def test_unlock_allows_palette_change(self) -> None:
        """After unlock, normal drift resumes on next track change."""
        single_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0, dwell=1),
            "p2": Palette(range=("red", "red"), weight=1.0, dwell=1),
        }
        cfg = _make_config(palettes=single_pal, palette_dwell_tracks=1)

        changed = False
        for seed in range(50):
            e = LedColorEngine(cfg, set_seed=seed)
            initial = e.snapshot()["current_palette"]
            e.lock()
            # Drive several tracks — locked, no change
            for lg in range(1, 5):
                _dispatch(e, load_gen=lg)
            e.unlock()
            # Drive more tracks — should now drift
            for lg in range(5, 15):
                _dispatch(e, load_gen=lg)
            if e.snapshot()["current_palette"] != initial:
                changed = True
                break

        self.assertTrue(changed, "Palette never changed after unlock")

    def test_lock_suppresses_snap(self) -> None:
        """lock=True: snap never fires even on eligible drop sections."""
        # Use big_shift_chance=1.0 so snap would ALWAYS fire when unlocked
        e = _engine(seed=42, big_shift_chance=1.0, snap_eligible_drop_indices=(1, 2, 3))
        _dispatch(e, load_gen=1)
        initial = e.snapshot()["current_palette"]
        e.lock()

        # Trigger many drop sections
        for i in range(10):
            _dispatch(e, load_gen=1, role="drop", section_id=f"drop{i}")

        snap = e.snapshot()
        self.assertEqual(snap["current_palette"], initial)

    def test_lock_snapshot(self) -> None:
        e = _engine(seed=42)
        self.assertFalse(e.snapshot()["lock"])
        e.lock()
        self.assertTrue(e.snapshot()["lock"])
        e.unlock()
        self.assertFalse(e.snapshot()["lock"])


# ---------------------------------------------------------------------------
# Drop section index + snap tests
# ---------------------------------------------------------------------------

class TestDropSectionIndex(unittest.TestCase):

    def test_drop_index_increments_on_new_section(self) -> None:
        e = _engine(seed=42, big_shift_chance=0.0)  # no snap interference
        _dispatch(e, load_gen=1)
        self.assertEqual(e.snapshot()["drop_section_index"], 0)

        _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
        self.assertEqual(e.snapshot()["drop_section_index"], 1)

        _dispatch(e, load_gen=1, role="drop", section_id="drop_B")
        self.assertEqual(e.snapshot()["drop_section_index"], 2)

    def test_drop_index_no_increment_same_section(self) -> None:
        e = _engine(seed=42, big_shift_chance=0.0)
        _dispatch(e, load_gen=1)
        _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
        idx_after_first = e.snapshot()["drop_section_index"]
        # Same section_id again
        _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
        _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
        self.assertEqual(e.snapshot()["drop_section_index"], idx_after_first)

    def test_drop_index_resets_on_new_track(self) -> None:
        e = _engine(seed=42, big_shift_chance=0.0)
        _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
        _dispatch(e, load_gen=1, role="drop", section_id="drop_B")
        self.assertGreater(e.snapshot()["drop_section_index"], 0)

        # Load new track
        _dispatch(e, load_gen=2)
        self.assertEqual(e.snapshot()["drop_section_index"], 0)

    def test_snap_excludes_current_palette(self) -> None:
        """Snap must pick a DIFFERENT palette (never the current one)."""
        # Use big_shift_chance=1.0 to guarantee snap fires; use 2-palette config
        two_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0),
            "p2": Palette(range=("red", "red"), weight=1.0),
        }
        cfg = _make_config(
            palettes=two_pal,
            big_shift_chance=1.0,
            snap_eligible_drop_indices=(1,),
        )
        # Run many seeds to confirm it always picks the other
        for seed in range(30):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=1)
            initial = e.snapshot()["current_palette"]
            # Trigger first drop section → eligible → snap fires
            _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
            after = e.snapshot()["current_palette"]
            self.assertNotEqual(
                after, initial,
                msg=f"seed={seed}: snap re-picked same palette '{initial}'"
            )

    def test_snap_fires_probabilistically(self) -> None:
        """With big_shift_chance=0.5 and many seeds, snap fires ~50% of the time."""
        two_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0),
            "p2": Palette(range=("red", "red"), weight=1.0),
        }
        cfg = _make_config(
            palettes=two_pal,
            big_shift_chance=0.5,
            snap_eligible_drop_indices=(1,),
        )
        snapped = 0
        N = 100
        for seed in range(N):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=1)
            initial = e.snapshot()["current_palette"]
            _dispatch(e, load_gen=1, role="drop", section_id="drop_A")
            if e.snapshot()["current_palette"] != initial:
                snapped += 1

        # With p=0.5, expect roughly 40-60 out of 100
        self.assertGreater(snapped, 25, msg=f"Snap fired only {snapped}/100 times")
        self.assertLess(snapped, 85, msg=f"Snap fired {snapped}/100 times (too high)")


# ---------------------------------------------------------------------------
# Focus tests
# ---------------------------------------------------------------------------

class TestFocus(unittest.TestCase):

    def test_mono_focus_narrow_color_range(self) -> None:
        """mono focus mode → colors near a single end of the palette."""
        mono_pal = {
            "blue_cyan": Palette(
                range=("cyan", "blue"),
                white=0.0,
                spread=0.0,  # no extra spread
                weight=1.0,
                focus_modes={"mono": 1.0},  # only mono
            ),
        }
        cfg = _make_config(palettes=mono_pal, drama_by_role=False)

        # Collect many colors across multiple tracks
        colors = []
        for seed in range(10):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=1 + seed * 10)
            for sid in range(5):
                c = _color(e, section_id=f"s{sid}")
                if "color" in c:
                    colors.append(c["color"])

        # Under mono focus, colors should cluster near cyan or blue
        # Both cyan=(0,255,255) and blue=(0,0,255) have R≈0
        # They should NOT be spread across the whole range (e.g. purple)
        non_zero_red = sum(1 for r, g, b in colors if r > 100)
        self.assertLess(
            non_zero_red, len(colors) // 2,
            msg="mono focus produced too many high-red colors (not near cyan/blue)"
        )

    def test_full_focus_spans_range(self) -> None:
        """full focus mode → colors spread across the whole palette interval."""
        full_pal = {
            "cyan_blue_purple": Palette(
                range=("cyan", "purple"),
                white=0.0,
                spread=0.0,
                weight=1.0,
                focus_modes={"full": 1.0},  # only full
            ),
        }
        cfg = _make_config(palettes=full_pal, drama_by_role=False)

        colors = []
        for seed in range(20):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=1 + seed)
            for sid in range(10):
                c = _color(e, section_id=f"s{sid}", cycle=sid)
                if "color" in c:
                    colors.append(c["color"])

        # Full range cyan..purple: should see blues (0,0,255) AND cyan-ish (0,255,x)
        # Cyan has high G, blue has high B, purple has high R
        high_g = sum(1 for r, g, b in colors if g > 150)
        high_b = sum(1 for r, g, b in colors if b > 150)
        # Both should appear in a wide focus
        self.assertGreater(high_g, 0, "No cyan-ish colors in full focus")
        self.assertGreater(high_b, 0, "No blue-ish colors in full focus")


# ---------------------------------------------------------------------------
# resolve_color tests
# ---------------------------------------------------------------------------

class TestResolveColor(unittest.TestCase):

    def test_disabled_returns_empty(self) -> None:
        cfg = _make_config(enabled=False)
        e = LedColorEngine(cfg, set_seed=1)
        _dispatch(e, load_gen=1)
        self.assertEqual(_color(e), {})

    def test_baked_color_source_returns_empty(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        result = _color(e, color_source="baked")
        self.assertEqual(result, {})

    def test_exempt_look_returns_empty(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        result = _color(e, look_name="rt_drop_white_aggressive")
        self.assertEqual(result, {})

    def test_engine_source_returns_color(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        result = _color(e, color_source="engine")
        self.assertIn("color", result)
        r, g, b = result["color"]
        self.assertIsInstance(r, int)
        self.assertIn(r, range(0, 256))
        self.assertIn(g, range(0, 256))
        self.assertIn(b, range(0, 256))

    def test_multi_returns_color_a_color_b(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        result = _color(e, multi=True)
        self.assertIn("color", result)
        self.assertIn("color_a", result)
        self.assertIn("color_b", result)
        for key in ("color", "color_a", "color_b"):
            r, g, b = result[key]
            self.assertIn(r, range(0, 256))
            self.assertIn(g, range(0, 256))
            self.assertIn(b, range(0, 256))

    def test_multi_false_no_color_ab(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        result = _color(e, multi=False)
        self.assertNotIn("color_a", result)
        self.assertNotIn("color_b", result)

    def test_white_palette_blends_toward_white(self) -> None:
        """red_white palette (white=0.4) → color should be noticeably whitened."""
        white_pal = {
            "red_white": Palette(
                range=("red", "red"),
                white=0.4,
                spread=0.0,
                weight=1.0,
            ),
        }
        cfg = _make_config(palettes=white_pal, drama_by_role=False)
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        result = _color(e)
        r, g, b = result["color"]
        # red=(255,0,0) blended 40% toward white → g,b > 0
        # g ≈ 0 + 0.4*(255-0) = 102
        self.assertGreater(g, 50, "White blend should raise green channel")
        self.assertGreater(b, 50, "White blend should raise blue channel")

    def test_resolve_color_deterministic(self) -> None:
        """Same seed + same call sequence → same color every time."""
        def run(seed: int) -> Any:
            e = _engine(seed=seed)
            _dispatch(e, load_gen=5)
            return _color(e, section_id="sX", cycle=3)["color"]

        self.assertEqual(run(123), run(123))

    def test_resolve_color_varies_across_sections(self) -> None:
        """Different section_id/cycle seeds should produce different colors.

        Use a wide-range palette with full focus mode and spread to ensure
        the focus window is large enough that different seeds produce different p values.
        """
        wide_pal = {
            "cyan_blue_purple": Palette(
                range=("cyan", "purple"),
                white=0.0,
                spread=0.15,
                weight=1.0,
                focus_modes={"full": 1.0},  # always full range
            ),
        }
        cfg = _make_config(
            palettes=wide_pal,
            drama_by_role=False,
            step_within_section={"drop": False, "post_drop": True, "groove": True},
        )

        # Collect colors from many (section_id, cycle) combos across multiple track seeds
        all_colors: list[tuple] = []
        for seed in range(5):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=seed + 1, role="groove", section_id="sA")
            for i in range(10):
                c = _color(e, role="groove", section_id=f"s{i}", cycle=i)
                if "color" in c:
                    all_colors.append(c["color"])

        unique = set(all_colors)
        self.assertGreater(len(unique), 1, "All section/cycle combos produced identical color")

    def test_no_orange_yellow_from_engine(self) -> None:
        """Engine-resolved colors must never be orange/yellow (R>120 AND G in [60,200] AND B<60)."""
        e = _engine(seed=0)
        for lg in range(1, 8):
            _dispatch(e, load_gen=lg)
            for sid in range(5):
                c = _color(e, section_id=f"s{sid}", cycle=sid)
                if "color" in c:
                    r, g, b = c["color"]
                    is_oy = r > 120 and 60 <= g <= 200 and b < 60
                    self.assertFalse(
                        is_oy,
                        msg=f"lg={lg} sid={sid} → ({r},{g},{b}) orange/yellow"
                    )


# ---------------------------------------------------------------------------
# diy_eligible tests
# ---------------------------------------------------------------------------

class TestDiyEligible(unittest.TestCase):

    def test_disabled_always_true(self) -> None:
        """When engine disabled, all DIY looks are eligible."""
        cfg = _make_config(enabled=False)
        e = LedColorEngine(cfg, set_seed=1)
        self.assertTrue(e.diy_eligible("groove_diy_red_chasing"))
        self.assertTrue(e.diy_eligible("anything_untagged"))

    def test_untagged_always_eligible(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        self.assertTrue(e.diy_eligible("some_unregistered_look_name"))

    def test_white_tag_always_eligible(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        self.assertTrue(e.diy_eligible("groove_diy_bright_white_chase"))
        self.assertTrue(e.diy_eligible("buildup_diy_white_sparse"))

    def test_big_drop_signature_always_eligible(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        self.assertTrue(e.diy_eligible("drop_diy_rainbow_sparkle"))

    def test_todo_always_eligible(self) -> None:
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        self.assertTrue(e.diy_eligible("groove_diy_groove"))

    def test_compound_tag_always_eligible(self) -> None:
        """Tags containing '+' are compound → always eligible in M1."""
        e = _engine(seed=1)
        _dispatch(e, load_gen=1)
        self.assertTrue(e.diy_eligible("drop_diy_1_red_white_chase"))

    def test_stop_tag_filtered_by_range(self) -> None:
        """A stop-tagged look is eligible only if its stop falls in palette interval ± spread."""
        # Force engine to blue_cyan palette
        blue_cyan_only = {
            "blue_cyan": Palette(range=("cyan", "blue"), white=0.0, spread=0.10, weight=1.0),
        }
        cfg = _make_config(
            palettes=blue_cyan_only,
            diy_color_tags={
                "diy_blue": "blue",
                "diy_red": "red",
                "ambient_pb_halves": "purple",
            }
        )
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)

        # Blue is within the blue_cyan palette's range → eligible
        self.assertTrue(e.diy_eligible("diy_blue"))
        # Red is outside (far right of scale) → not eligible under blue_cyan
        self.assertFalse(e.diy_eligible("diy_red"))

    def test_stop_tag_eligible_when_in_range(self) -> None:
        """Confirm a purple-tagged look is eligible under cyan_blue_purple palette."""
        purple_pal = {
            "cyan_blue_purple": Palette(
                range=("cyan", "purple"),
                white=0.0,
                spread=0.05,
                weight=1.0,
            ),
        }
        cfg = _make_config(
            palettes=purple_pal,
            diy_color_tags={"ambient_pb_halves": "purple"},
        )
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        # purple is the right end of cyan_blue_purple → eligible
        self.assertTrue(e.diy_eligible("ambient_pb_halves"))


# ---------------------------------------------------------------------------
# Live-control stubs
# ---------------------------------------------------------------------------

class TestLiveControlStubs(unittest.TestCase):

    def test_set_palette_jumps_immediately(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        e.set_palette("red")
        self.assertEqual(e.snapshot()["current_palette"], "red")

    def test_set_palette_invalid_name_noop(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        initial = e.snapshot()["current_palette"]
        e.set_palette("does_not_exist")
        self.assertEqual(e.snapshot()["current_palette"], initial)

    def test_queue_palette_stored(self) -> None:
        e = _engine(seed=42)
        e.queue_palette("red")
        self.assertEqual(e.snapshot()["queued_palette"], "red")

    def test_unqueue_palette_clears_only_matching_queue(self) -> None:
        e = _engine(seed=42)
        e.queue_palette("red")

        e.unqueue_palette("green")
        self.assertEqual(e.snapshot()["queued_palette"], "red")

        e.unqueue_palette("red")
        self.assertEqual(e.snapshot()["queued_palette"], "")

    def test_queue_palette_applied_on_next_track(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        e.queue_palette("red")
        # Next new track → queue consumed
        _dispatch(e, load_gen=2)
        snap = e.snapshot()
        self.assertEqual(snap["current_palette"], "red")
        self.assertEqual(snap["queued_palette"], "")

    def test_queue_cleared_after_apply(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        e.queue_palette("red")
        _dispatch(e, load_gen=2)
        self.assertEqual(e.snapshot()["queued_palette"], "")

    def test_shift_changes_palette(self) -> None:
        """shift() re-selects a distant palette (excluding current)."""
        two_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0),
            "p2": Palette(range=("red", "red"), weight=1.0),
        }
        cfg = _make_config(palettes=two_pal)
        changed = False
        for seed in range(20):
            e = LedColorEngine(cfg, set_seed=seed)
            _dispatch(e, load_gen=1)
            initial = e.snapshot()["current_palette"]
            e.shift()
            after = e.snapshot()["current_palette"]
            if after != initial:
                changed = True
                break
        self.assertTrue(changed, "shift() never changed palette across 20 seeds")

    def test_snapshot_reflects_all_fields(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        snap = e.snapshot()
        required = {"current_palette", "anchor_p", "dwell_remaining",
                    "drop_section_index", "lock", "queued_palette"}
        for key in required:
            self.assertIn(key, snap, msg=f"snapshot() missing '{key}'")

    def test_color_state_reads_anchor_without_mutating_engine(self) -> None:
        palettes = dict(_DEFAULT_PALETTES)
        palettes["white_sand"] = Palette(type="fixed_rgb", weight=0.0, rgb=(255, 235, 200))
        palettes["rainbow"] = Palette(type="rainbow", weight=0.0)
        e = LedColorEngine(_make_config(palettes=palettes), set_seed=42)
        _dispatch(e, load_gen=1)
        e.override_palette("red", start_beat=0.0, end_beat=8.0)
        e.advance_fade(4.0)

        before = (
            e.snapshot(),
            e._journey_rng.getstate(),
            dict(e._prev_color),
            e._anchor_p,
            e._current_palette,
        )
        state = e.color_state()
        after = (
            e.snapshot(),
            e._journey_rng.getstate(),
            dict(e._prev_color),
            e._anchor_p,
            e._current_palette,
        )

        self.assertEqual(after, before)
        self.assertEqual(state["rgb"], _p_to_rgb(e._anchor_p, e._config.scale_stops, e._stop_positions))
        self.assertEqual(state["palette"], e._current_palette)
        self.assertFalse(state["white_sand_active"])
        self.assertFalse(state["rainbow_active"])

        e.set_mode_override({"breakdown": "white_sand", "*": "rainbow"})
        state = e.color_state()
        self.assertTrue(state["white_sand_active"])
        self.assertTrue(state["rainbow_active"])

    def test_lock_suppresses_dwell_decrement(self) -> None:
        """When locked, dwell_remaining does NOT decrease on track changes."""
        two_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0, dwell=2),
            "p2": Palette(range=("red", "red"), weight=1.0, dwell=2),
        }
        cfg = _make_config(palettes=two_pal, palette_dwell_tracks=2)
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        snap0 = e.snapshot()
        initial_dwell = snap0["dwell_remaining"]

        e.lock()
        # Drive many track changes
        for lg in range(2, 12):
            _dispatch(e, load_gen=lg)

        # Dwell should be unchanged (locked)
        snap_after = e.snapshot()
        self.assertEqual(snap_after["dwell_remaining"], initial_dwell)


# ---------------------------------------------------------------------------
# resolve_slot_colors tests
# ---------------------------------------------------------------------------

class TestResolveSlotColors(unittest.TestCase):

    def test_gradient_even_returns_6_slots_with_white_tail(self) -> None:
        cfg = _make_config()
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        
        # Test default slot_count=6
        res = e.resolve_slot_colors(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="some_look",
            color_source="engine",
            slot_count=6,
        )
        slots = res.get("slot_colors", [])
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[5], (255, 255, 255))

        # Test arbitrary slot_count=10 (should be ignored, exactly 6 slots returned)
        res_large = e.resolve_slot_colors(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="some_look",
            color_source="engine",
            slot_count=10,
        )
        self.assertEqual(len(res_large.get("slot_colors", [])), 6)
        self.assertEqual(res_large.get("slot_colors", [])[5], (255, 255, 255))
        
        # Test arbitrary slot_count=0 (should be ignored, exactly 6 slots returned)
        res_zero = e.resolve_slot_colors(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="some_look",
            color_source="engine",
            slot_count=0,
        )
        self.assertEqual(len(res_zero.get("slot_colors", [])), 6)
        self.assertEqual(res_zero.get("slot_colors", [])[5], (255, 255, 255))

    def test_random_with_replacement_determinism(self) -> None:
        cfg = _make_config(
            slot_fill_strategy_by_look={"rt_groove_chase": "random_with_replacement"},
            # Force a single wide palette to ensure random draws are noticeably different
            palettes={
                "wide": Palette(range=("cyan", "red"), weight=1.0)
            }
        )
        
        def run_once(section_id: str, cycle: int) -> list:
            e = LedColorEngine(cfg, set_seed=42)
            _dispatch(e, load_gen=1)
            return e.resolve_slot_colors(
                role="groove",
                section_id=section_id,
                cycle=cycle,
                look_name="rt_groove_chase",
                color_source="engine",
                slot_count=6,
            )["slot_colors"]

        # 1. Determinism: same inputs -> same output
        res1 = run_once("s1", 0)
        res2 = run_once("s1", 0)
        self.assertEqual(res1, res2)

        # 2. Output length is strictly 6 with slot 5 white
        self.assertEqual(len(res1), 6)
        self.assertEqual(res1[5], (255, 255, 255))

        # 3. Different section_id -> different output
        res3 = run_once("s2", 0)
        self.assertNotEqual(res1, res3)

        # 4. Different step_index (cycle) -> different output
        # groove has step_within_section=True in _make_config
        res4 = run_once("s1", 1)
        self.assertNotEqual(res1, res4)

    def test_random_with_replacement_ignores_slot_count(self) -> None:
        cfg = _make_config(
            slot_fill_strategy_by_look={"rt_groove_chase": "random_with_replacement"}
        )
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        res = e.resolve_slot_colors(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="rt_groove_chase",
            color_source="engine",
            slot_count=10,
        )
        slots = res.get("slot_colors", [])
        self.assertEqual(len(slots), 6)
        self.assertEqual(slots[5], (255, 255, 255))

    def test_unknown_strategy_fails_safe_to_gradient(self) -> None:
        # Defensive guard: a strategy string that bypassed config validation
        # must fail safe to gradient_even (6 slots, slot 5 white), NEVER an
        # empty vector. Proven by matching the gradient_even output for the
        # same context.
        cfg = _make_config(
            slot_fill_strategy_by_look={"bogus_look": "weighted_random"}
        )
        e = LedColorEngine(cfg, set_seed=42)
        _dispatch(e, load_gen=1)
        bogus = e.resolve_slot_colors(
            role="groove", section_id="s1", cycle=0,
            look_name="bogus_look", color_source="engine", slot_count=6,
        )["slot_colors"]
        gradient = e.resolve_slot_colors(
            role="groove", section_id="s1", cycle=0,
            look_name="plain_look", color_source="engine", slot_count=6,
        )["slot_colors"]
        self.assertEqual(len(bogus), 6)
        self.assertEqual(bogus[5], (255, 255, 255))
        # Fell back to gradient_even, not random and not empty.
        self.assertEqual(bogus, gradient)

    def test_locked_palette_resolves_without_touching_journey_state(self) -> None:
        cfg = _make_config(locked_palette_by_look={"locked_look": "red"})
        e = LedColorEngine(cfg, set_seed=42)
        e.set_palette("blue_cyan")
        _dispatch(e, load_gen=1)
        before = e.snapshot()

        locked = e.resolve_color(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="locked_look",
            color_source="engine",
        )
        after = e.snapshot()
        unlocked = e.resolve_color(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="unlocked_look",
            color_source="engine",
        )

        self.assertEqual(after, before)
        self.assertGreater(locked["color"][0], locked["color"][2])
        self.assertNotEqual(locked["color"], unlocked["color"])

    def test_locked_slot_palette_and_absent_mapping_parity(self) -> None:
        locked_cfg = _make_config(locked_palette_by_look={"locked_look": "red"})
        locked_engine = LedColorEngine(locked_cfg, set_seed=7)
        locked_engine.set_palette("blue_cyan")
        _dispatch(locked_engine, load_gen=1)

        locked = locked_engine.resolve_slot_colors(
            role="groove",
            section_id="s1",
            cycle=0,
            look_name="locked_look",
            color_source="engine",
        )["slot_colors"]

        control_cfg = _make_config()
        with_absent = LedColorEngine(locked_cfg, set_seed=7)
        control = LedColorEngine(control_cfg, set_seed=7)
        _dispatch(with_absent, load_gen=1)
        _dispatch(control, load_gen=1)
        self.assertEqual(
            with_absent.resolve_slot_colors(
                role="groove",
                section_id="s1",
                cycle=0,
                look_name="unmapped_look",
                color_source="engine",
            ),
            control.resolve_slot_colors(
                role="groove",
                section_id="s1",
                cycle=0,
                look_name="unmapped_look",
                color_source="engine",
            ),
        )
        self.assertEqual(len(locked), 6)
        self.assertEqual(locked[5], (255, 255, 255))
        self.assertTrue(all(color[0] >= color[2] for color in locked[:5]))


class TestRainbowPalette(unittest.TestCase):
    def test_rainbow_uses_full_hue_wheel_for_color_and_slots(self) -> None:
        palettes = dict(_DEFAULT_PALETTES)
        palettes["rainbow"] = Palette(type="rainbow", weight=0.0)
        engine = LedColorEngine(_make_config(palettes=palettes), set_seed=7)
        engine.set_mode_override({"*": "rainbow"})

        colors = [
            engine.resolve_color(
                role="drop",
                section_id="rainbow-section",
                cycle=cycle,
                look_name="rainbow_look",
                color_source="engine",
            )["color"]
            for cycle in range(64)
        ]
        slots = engine.resolve_slot_colors(
            role="drop",
            section_id="rainbow-section",
            cycle=0,
            look_name="rainbow_look",
            color_source="engine",
        )["slot_colors"]

        def warm(rgb: tuple[int, int, int]) -> bool:
            r, g, b = rgb
            return r > 180 and g > 120 and b < 80

        self.assertTrue(any(warm(rgb) for rgb in colors), colors)
        self.assertTrue(any(warm(rgb) for rgb in slots[:5]), slots)

# ---------------------------------------------------------------------------
# Module-level import sanity
# ---------------------------------------------------------------------------

class TestImport(unittest.TestCase):
    def test_module_importable(self) -> None:
        import rb_ss_bridge_v2.led_color_engine as m
        self.assertTrue(hasattr(m, "LedColorEngine"))

    def test_engine_instantiable_with_empty_like_config(self) -> None:
        """Engine with minimal valid config (one palette) doesn't crash on init."""
        minimal = {
            "only_blue": Palette(range=("blue", "blue"), weight=1.0),
        }
        cfg = _make_config(palettes=minimal)
        e = LedColorEngine(cfg, set_seed=0)
        self.assertIsNotNone(e)
        self.assertTrue(e.enabled)

    def test_enabled_property_mirrors_config(self) -> None:
        cfg_on = _make_config(enabled=True)
        cfg_off = _make_config(enabled=False)
        self.assertTrue(LedColorEngine(cfg_on, set_seed=0).enabled)
        self.assertFalse(LedColorEngine(cfg_off, set_seed=0).enabled)


# ---------------------------------------------------------------------------
# AWR-125 W3b: perf("led.palette") emit assertions
# ---------------------------------------------------------------------------

class TestPalettePerfEmits(unittest.TestCase):
    """Capture-handler pattern on logging.getLogger("perf.led.palette");
    no bridge_log.init() — the pure engine must emit through plain stdlib
    logging with zero pipeline setup."""

    def setUp(self) -> None:
        self._logger = logging.getLogger("perf.led.palette")
        self.records: list[logging.LogRecord] = []
        outer = self

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                outer.records.append(record)

        self._handler = _Capture()
        self._prior_level = self._logger.level
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.DEBUG)

    def tearDown(self) -> None:
        self._logger.setLevel(self._prior_level)
        self._logger.removeHandler(self._handler)

    def test_dwell_expiry_emits_reason_dwell_per_commit(self) -> None:
        minimal_pal = {
            "p1": Palette(range=("blue", "blue"), weight=1.0, dwell=1),
            "p2": Palette(range=("red", "red"), weight=1.0, dwell=1),
        }
        cfg = _make_config(palettes=minimal_pal, palette_dwell_tracks=1)
        e = LedColorEngine(cfg, set_seed=7)

        _dispatch(e, load_gen=1)
        _dispatch(e, load_gen=2)
        _dispatch(e, load_gen=3)

        # dwell=1 → every new track expires dwell → one commit each
        self.assertEqual(len(self.records), 3)
        for rec in self.records:
            self.assertEqual(rec.cat, "perf.led.palette")
            self.assertEqual(rec.data["reason"], "dwell")
            self.assertIn("palette", rec.data)
            self.assertIn("prev", rec.data)
            self.assertFalse(rec.data["locked"])

    def test_same_track_dispatch_emits_nothing(self) -> None:
        e = _engine(seed=42)  # default palettes: all dwell >= 4
        _dispatch(e, load_gen=1)
        for _ in range(10):
            _dispatch(e, load_gen=1)
        self.assertEqual(len(self.records), 0)

    def test_queued_palette_applies_with_reason_operator(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        initial = e.snapshot()["current_palette"]
        target = next(n for n in _DEFAULT_PALETTES if n != initial)

        e.queue_palette(target)
        self.assertEqual(len(self.records), 0)  # queueing alone emits nothing

        _dispatch(e, load_gen=2)  # queued palette commits on track change

        self.assertEqual(len(self.records), 1)
        rec = self.records[0]
        self.assertEqual(rec.cat, "perf.led.palette")
        self.assertEqual(rec.data["reason"], "operator")
        self.assertEqual(rec.data["palette"], target)
        self.assertEqual(rec.data["prev"], initial)

    def test_set_palette_emits_reason_operator(self) -> None:
        e = _engine(seed=42)
        initial = e.snapshot()["current_palette"]
        target = next(n for n in _DEFAULT_PALETTES if n != initial)

        e.set_palette(target)

        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.records[0].data["reason"], "operator")
        self.assertEqual(self.records[0].data["palette"], target)
        self.assertEqual(self.records[0].data["prev"], initial)

    def test_drop_snap_emits_reason_drop_snap(self) -> None:
        e = _engine(
            seed=42,
            big_shift_chance=1.0,
            snap_eligible_drop_indices=(1,),
        )
        initial = e.snapshot()["current_palette"]

        _dispatch(e, load_gen=1, role="drop", section_id="d1")

        self.assertEqual(len(self.records), 1)
        rec = self.records[0]
        self.assertEqual(rec.data["reason"], "drop_snap")
        self.assertEqual(rec.data["prev"], initial)
        self.assertNotEqual(rec.data["palette"], initial)  # snap excludes current

    def test_override_fade_emits_reason_fade_only_at_completion(self) -> None:
        e = _engine(seed=42)
        _dispatch(e, load_gen=1)
        initial = e.snapshot()["current_palette"]
        target = next(n for n in _DEFAULT_PALETTES if n != initial)

        e.override_palette(target, start_beat=0.0, end_beat=8.0)
        e.advance_fade(2.0)
        e.advance_fade(4.0)
        self.assertEqual(len(self.records), 0)  # mid-fade ticks emit nothing

        e.advance_fade(8.0)  # completion commit
        e.advance_fade(9.0)  # fade cleared — no further emits

        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.records[0].data["reason"], "fade")
        self.assertEqual(self.records[0].data["palette"], target)

    def test_shift_emits_reason_operator(self) -> None:
        e = _engine(seed=42)
        e.shift()
        self.assertEqual(len(self.records), 1)
        self.assertEqual(self.records[0].data["reason"], "operator")


if __name__ == "__main__":
    unittest.main()
