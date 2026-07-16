"""AWR-257 — true-drop LED section identity + cycling.

Pure seams only (no files, no subprocess, no running bridge):
  * D1-D4  select_true_drops / drop_sections pure functions
  * D5      LED pool governance (_led_f2_drop_look_names section-aware + <=-tier union)
  * D6      laser byte-identity pin (_f2_laser_tiers reads RAW drops, ignores sections)
  * D7      advance cursor cycling (director) + scripted stand-down + load_gen reset
  * D8      red-team H1 pins (explicit anchor narrowing / dedupe / gate stack / resume)
  * D9      every meta.smart_drops reset path also resets meta.drop_sections

The spec (docs/plans/active/true_drop_section_cycling_spec_2026_07_15.md) is the
acceptance oracle. Status: software-tested; hardware-unvalidated.
"""

import inspect
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import led_config  # noqa: E402
from rb_ss_bridge_v2 import drop_presentation  # noqa: E402
from rb_ss_bridge_v2 import led_dispatch_policy as P  # noqa: E402
from rb_ss_bridge_v2 import lighting_moments_v2 as M  # noqa: E402
from rb_ss_bridge_v2.led_look_director import LEDLookDirector  # noqa: E402
from rb_ss_bridge_v2.models import DropSection, TrackMetadata  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402
from rb_ss_bridge_v2.smart_phrasing import (  # noqa: E402
    PhraseSegment,
    SmartPhrasingEngine,
    SmartPhrasingSnapshot,
    SECTION_ADVANCE_MIN_GAP_BEATS,
    build_phrase_segments_from_markers,
    drop_sections,
    runway_beats,
    select_true_drops,
)

_EXAMPLE = str(Path(__file__).resolve().parents[1]
               / "config" / "led_look_director.example.json")


def _seg(a, b, label):
    return PhraseSegment(start_beat=float(a), end_beat=float(b), label=label)


# ---------------------------------------------------------------------------
# D1 — select_true_drops
# ---------------------------------------------------------------------------
class TestSelectTrueDrops(unittest.TestCase):
    def test_continuation_dropped_runwayd_kept(self):
        # up 0->64 climbs into 64 (true); 128 has a chorus in front (continuation).
        segs = [_seg(0, 64, "up"), _seg(64, 128, "chorus"), _seg(128, 192, "chorus")]
        self.assertEqual(runway_beats(64.0, segs), 64.0)
        self.assertEqual(runway_beats(128.0, segs), 0.0)
        self.assertEqual(select_true_drops([64, 128], segs), [64])

    def test_all_disqualified_fails_open_to_input(self):
        segs = [_seg(0, 64, "chorus"), _seg(64, 128, "chorus")]
        # No runway anywhere -> non-empty input returned unchanged (never lose ID).
        self.assertEqual(select_true_drops([64, 128], segs), [64, 128])

    def test_empty_stays_empty(self):
        segs = [_seg(0, 64, "up")]
        self.assertEqual(select_true_drops([], segs), [])


# ---------------------------------------------------------------------------
# D2 — false-marker fixture (operator-ruled "I Cannot" shape)
# ---------------------------------------------------------------------------
class TestFalseMarker(unittest.TestCase):
    def test_false_marker_in_no_section_true_drop_governs(self):
        # marker 32 has no runway (false); 128 has an up runway (true drop).
        segs = build_phrase_segments_from_markers(
            anlz_buildups=[96], anlz_drops=[32, 128], anlz_breakdowns=[],
            smart_drops=[32, 128], total_beats=256,
        )
        true = select_true_drops([32, 128], segs)
        self.assertEqual(true, [128])
        secs = drop_sections(true, [32, 128], segs, total_beats=256)
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0].true_drop_beat, 128)
        # The false marker sits inside no section.
        spans = [(s.true_drop_beat, s.end_beat) for s in secs]
        self.assertFalse(any(lo <= 32 < hi for lo, hi in spans))
        self.assertTrue(any(lo <= 128 < hi for lo, hi in spans))


# ---------------------------------------------------------------------------
# D3 — no-buildup track (inferred 32-beat up qualifies every smart drop)
# ---------------------------------------------------------------------------
class TestNoBuildupTrack(unittest.TestCase):
    def test_inferred_up_qualifies_every_smart_drop(self):
        segs = build_phrase_segments_from_markers(
            anlz_buildups=[], anlz_drops=[64, 160], anlz_breakdowns=[],
            smart_drops=[64, 160], total_beats=256,
        )
        self.assertEqual(select_true_drops([64, 160], segs), [64, 160])


# ---------------------------------------------------------------------------
# D4 — drop_sections
# ---------------------------------------------------------------------------
class TestDropSections(unittest.TestCase):
    def test_end_at_first_non_chorus_and_advance_floor_and_T_excluded(self):
        segs = [
            _seg(0, 64, "up"),
            _seg(64, 96, "chorus"),
            _seg(96, 160, "chorus"),
            _seg(160, 192, "low"),
            _seg(192, 256, "chorus"),
        ]
        secs = drop_sections(
            [64, 192], [64, 96, 100, 112, 160, 192, 208, 240],
            segs, total_beats=256)
        by_t = {s.true_drop_beat: s for s in secs}
        # Section at 64: chorus run stops at the low segment (end 160).
        self.assertEqual(by_t[64].end_beat, 160.0)
        # 96 kept (32 after T); 100 skipped (4 < 16 floor); 112 kept (16 after 96).
        self.assertEqual(by_t[64].advance_beats, (96, 112))
        # T itself is never an advance.
        self.assertNotIn(64, by_t[64].advance_beats)

    def test_outro_trim_region_yields_no_advances(self):
        # M1/M2 pin: outro_start = total - 32 = 224; 208 kept, 240 suppressed.
        segs = [_seg(0, 64, "up"), _seg(64, 96, "chorus"),
                _seg(96, 160, "chorus"), _seg(160, 192, "low"),
                _seg(192, 256, "chorus")]
        secs = drop_sections([192], [192, 208, 240], segs, total_beats=256)
        self.assertEqual(secs[0].advance_beats, (208,))

    def test_clamp_to_next_true_drop(self):
        # One long chorus run spilling past the next true drop is clamped to it.
        segs = [_seg(0, 64, "up"), _seg(64, 256, "chorus")]
        secs = drop_sections([64, 128], [64, 128], segs, total_beats=256)
        self.assertEqual(secs[0].true_drop_beat, 64)
        self.assertEqual(secs[0].end_beat, 128.0)

    def test_no_raw_inside_yields_no_advances(self):
        segs = [_seg(0, 64, "up"), _seg(64, 128, "chorus")]
        secs = drop_sections([64], [64], segs, total_beats=256)
        self.assertEqual(secs[0].advance_beats, ())

    def test_unsorted_duplicate_raw_markers_handled(self):
        segs = [_seg(0, 64, "up"), _seg(64, 256, "chorus")]
        # Unsorted + duplicates + 100 (4 beats after 96) must not survive.
        secs = drop_sections([64], [112, 96, 96, 64, 100], segs, total_beats=1024)
        self.assertEqual(secs[0].advance_beats, (96, 112))

    def test_advance_gap_uses_named_constant(self):
        self.assertEqual(SECTION_ADVANCE_MIN_GAP_BEATS, 16)


# ---------------------------------------------------------------------------
# D5 / D8(a) — LED pool governance + explicit-anchor narrowing
# ---------------------------------------------------------------------------
_ROUTING = {
    "WALL": {1: ("rt_drop_chase_blue",),
             2: ("rt_drop_strobe_blue", "rt_drop_strobe_cyan"),
             3: ("rt_drop_white_aggressive",)},
    "COMET": {1: ("rt_drop_chase_red",),
              3: ("rt_drop_firework_explosion",)},
    "HOUSE": {1: ("rt_drop_chase_green",),
              2: ("rt_drop_strobe_cyan_white",)},
}


def _plan(mapping):
    """mapping: beat -> (family, tier)."""
    def for_drop(beat, tol=1.0):
        for b, (fam, tier) in mapping.items():
            if abs(b - beat) <= tol:
                return SimpleNamespace(decision=SimpleNamespace(family=fam, tier=tier))
        return None
    return SimpleNamespace(for_drop=for_drop)


class _F2Host(P.LEDDispatchPolicyMixin):
    """Minimal mixin host exposing just what the F2 narrowing methods read."""
    def __init__(self, *, plan, drop_sections=(), active_drop_beat=None,
                 scripted=0, f2_enabled=True):
        self._f2_enabled = f2_enabled
        self._f2_drop_look_routing = _ROUTING
        self._last_sp_state = SimpleNamespace(active_drop_beat=active_drop_beat)
        self._os = SimpleNamespace(active_deck=1)
        meta = SimpleNamespace(f2_plan=plan, drop_sections=drop_sections)
        self._deck = {1: SimpleNamespace(meta=meta, scripted_id=scripted)}
        self._led_v2_latch = False
        self._f4_enabled = False

    # Isolate the F2 term: the v2/F4 preference terms are inert here.
    def _led_v2_look_preference_predicate(self):
        return None

    def _led_f4_euphoric_bright(self):
        return None


class TestLedPoolGovernance(unittest.TestCase):
    def test_continuation_uses_section_true_drop_pool(self):
        # Section true drop is WALL/2; the continuation's OWN entry is COMET/3.
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,))
        host = _F2Host(plan=_plan({64: ("WALL", 2), 96: ("COMET", 3)}),
                       drop_sections=(section,))
        names = host._led_f2_drop_look_names(96.0)
        self.assertEqual(
            names, {"rt_drop_chase_blue", "rt_drop_strobe_blue", "rt_drop_strobe_cyan"})
        # Never the continuation's own COMET/3 look, never above the section tier.
        self.assertNotIn("rt_drop_white_aggressive", names)
        self.assertNotIn("rt_drop_firework_explosion", names)

    def test_outside_section_uses_own_entry_pool(self):
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,))
        host = _F2Host(plan=_plan({200: ("HOUSE", 2)}),
                       drop_sections=(section,), active_drop_beat=200.0)
        names = host._led_f2_drop_look_names()   # no explicit anchor -> active_drop_beat
        self.assertEqual(
            names, {"rt_drop_chase_green", "rt_drop_strobe_cyan_white"})

    def test_anchor_none_no_section_returns_no_narrowing(self):
        host = _F2Host(plan=_plan({64: ("WALL", 2)}), active_drop_beat=None)
        self.assertIsNone(host._led_f2_drop_look_names(None))
        self.assertIsNone(host._led_f2_drop_look_names())

    def test_le_tier_union_never_exceeds_section_tier(self):
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=())
        host = _F2Host(plan=_plan({64: ("WALL", 2)}), drop_sections=(section,))
        names = host._led_f2_drop_look_names(64.0)
        self.assertIn("rt_drop_chase_blue", names)         # tier 1 present
        self.assertIn("rt_drop_strobe_blue", names)        # tier 2 present
        self.assertNotIn("rt_drop_white_aggressive", names)  # tier 3 excluded

    def test_scripted_deck_stands_down(self):
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,))
        host = _F2Host(plan=_plan({64: ("WALL", 2)}),
                       drop_sections=(section,), scripted=7)
        self.assertIsNone(host._led_f2_drop_look_names(96.0))

    def test_explicit_anchor_narrows_when_active_drop_beat_is_none(self):
        # D8(a): the H1 ambush. active_drop_beat is None at an advance beat, so the
        # no-arg predicate loses narrowing; the explicit section anchor restores it.
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,))
        host = _F2Host(plan=_plan({64: ("WALL", 2)}),
                       drop_sections=(section,), active_drop_beat=None)
        self.assertIsNone(host._led_look_preference_predicate())          # full bank
        preds = host._led_look_preference_predicate(anchor_beat=64.0)      # narrowed
        self.assertIsNotNone(preds)
        candidates = ["rt_drop_chase_blue", "rt_drop_strobe_blue",
                      "rt_drop_white_aggressive", "rt_drop_firework_explosion"]
        for pred in preds:
            narrowed = [c for c in candidates if pred(c)]
            if narrowed:
                candidates = narrowed
        self.assertEqual(
            set(candidates), {"rt_drop_chase_blue", "rt_drop_strobe_blue"})


# ---------------------------------------------------------------------------
# D6 — laser byte-identity pin
# ---------------------------------------------------------------------------
class TestLaserByteIdentity(unittest.TestCase):
    def test_f2_laser_tiers_reads_raw_drops_ignores_sections(self):
        host = SimpleNamespace(_f2_enabled=True)
        plan = _plan({64: ("WALL", 2), 96: ("COMET", 3), 128: ("HOUSE", 1)})
        section = DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,))
        d_with = SimpleNamespace(
            scripted_id=0,
            meta=SimpleNamespace(f2_plan=plan, drop_sections=(section,)))
        d_without = SimpleNamespace(
            scripted_id=0,
            meta=SimpleNamespace(f2_plan=plan, drop_sections=()))
        out = StateManager._f2_laser_tiers(host, d_with, [64, 96, 128])
        # The mid-section marker 96 keeps its OWN COMET/3 (monster) tier — the
        # laser path never re-keys by section identity.
        self.assertEqual(out, {64: "intense", 96: "monster", 128: "standard"})
        # Sections present vs absent make ZERO difference to the laser tiers.
        self.assertEqual(
            StateManager._f2_laser_tiers(host, d_without, [64, 96, 128]), out)

    def test_laser_and_presentation_source_never_reference_sections(self):
        laser_src = inspect.getsource(StateManager._f2_laser_tiers)
        self.assertNotIn("drop_sections", laser_src)
        self.assertNotIn("section_advance", laser_src)
        dp_src = Path(drop_presentation.__file__).read_text()
        self.assertNotIn("drop_sections", dp_src)
        self.assertNotIn("section_advance", dp_src)


# ---------------------------------------------------------------------------
# D7 — advance cursor cycling (director) + reset with track (load_gen)
# ---------------------------------------------------------------------------
def _director():
    loaded = led_config.load_led_look_director_config(_EXAMPLE)
    assert loaded.available, loaded.errors
    return LEDLookDirector(
        replace(loaded.config, enabled=True, automation_enabled=True))


class TestAdvanceCursorCycling(unittest.TestCase):
    def test_commit_role_cycles_section_pool_without_repeat_then_wraps(self):
        director = _director()
        pool = {"rt_drop_strobe_blue", "rt_drop_strobe_cyan", "rt_drop_strobe_green"}
        pred = (lambda name, s=pool: name in s,)
        draws = [director.commit_role("drop", look_preference=pred).look
                 for _ in range(len(pool) * 2)]
        self.assertTrue(set(draws) <= pool)
        # One full pass covers every look exactly once (bag draw = no repeat).
        self.assertEqual(set(draws[:len(pool)]), pool)
        # Consecutive draws never repeat while the pool has > 1 look.
        for a, b in zip(draws, draws[1:]):
            self.assertNotEqual(a, b)


def _snap(abs_beat, sections, *, deck="1", track="t", playing=True):
    return SmartPhrasingSnapshot(
        deck_id=deck, track_id=track, is_playing=playing, abs_beat=abs_beat,
        phrase_segments=(), smart_drop_beats=(), breakdown_segments=(),
        phrase_lookahead_beats=16.0, drop_window_beats=8.0, post_drop_beats=16.0,
        transition_window_beats=8.0, drop_sections=sections,
    )


class TestAdvanceFiredSet(unittest.TestCase):
    SECTION = (DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,)),)

    def _cross(self, engine, track="t"):
        engine.update(_snap(95.0, self.SECTION, track=track))
        return engine.update(_snap(97.0, self.SECTION, track=track)).state

    def test_advance_fires_once_then_stays_quiet(self):
        eng = SmartPhrasingEngine()
        st = self._cross(eng)
        self.assertTrue(st.section_advance)
        self.assertEqual(st.section_advance_true_drop_beat, 64.0)
        self.assertEqual(st.section_advance_index, 0)
        # Same beat again -> already fired, no second advance.
        st2 = eng.update(_snap(99.0, self.SECTION)).state
        self.assertFalse(st2.section_advance)

    def test_fired_set_resets_with_track_change(self):
        eng = SmartPhrasingEngine()
        self.assertTrue(self._cross(eng, track="t1").section_advance)
        # New track (new load_gen -> new track_id) resets the advance fired-set.
        self.assertTrue(self._cross(eng, track="t2").section_advance)


class TestExactResumeLanding(unittest.TestCase):
    def test_resume_exactly_on_advance_beat_fires_once(self):
        section = (DropSection(true_drop_beat=64, end_beat=160.0, advance_beats=(96,)),)
        eng = SmartPhrasingEngine()
        # First tick lands exactly on the advance beat with no history (resume).
        st = eng.update(_snap(96.0, section)).state
        self.assertTrue(st.section_advance)
        self.assertEqual(st.section_advance_index, 0)
        # Re-issuing the same beat does not re-fire.
        st2 = eng.update(_snap(96.0, section)).state
        self.assertFalse(st2.section_advance)


# ---------------------------------------------------------------------------
# D8(b) — advance dispatch: unique role-key marker, dedupe exactly once
# ---------------------------------------------------------------------------
class _SendHost(P.LEDDispatchPolicyMixin):
    def __init__(self):
        self._led_last_auto_role_key = ""
        self._led_color_engine = None
        self._led_manual_override = ""
        self._led_smart_drop_blackout_key = ""
        self._led_v2_latch = False
        self._led_look_director = SimpleNamespace(
            commit_role=lambda role, diy_eligible=None, look_preference=None:
                SimpleNamespace(look="rt_drop_strobe_blue"))
        self.sent = []
        self.gated = []

    def _led_blackout_active(self):
        return False

    def _led_diy_eligible_predicate(self):
        return None

    def _led_look_preference_predicate(self, anchor_beat=None):
        return None

    def _led_inject_engine_colors(self, decision, **k):
        return decision

    def _led_inject_f4_seasoning(self, decision, *, role):
        return decision

    def _led_gate_no_look(self, *, reason, role, role_key, active_deck=None):
        self.gated.append(role_key)

    def _led_send_decision(self, decision, *, look, role, role_key,
                           automation, active_deck=None, sp_state=None):
        self.sent.append(role_key)
        return "accepted"


class TestAdvanceDispatchDedupe(unittest.TestCase):
    def _d(self):
        return SimpleNamespace(
            load_gen=7, meta=SimpleNamespace(content_id="c", filepath="f"))

    def _sp(self, idx):
        return SimpleNamespace(
            section_advance=True, smart_drop_crossing=False,
            section_advance_true_drop_beat=64.0, section_advance_index=idx)

    def test_unique_marker_and_dedupe_once(self):
        host = _SendHost()
        d = self._d()
        host._dispatch_led_section_advance(active=1, d=d, sp_state=self._sp(0))
        host._dispatch_led_section_advance(active=1, d=d, sp_state=self._sp(0))
        host._dispatch_led_section_advance(active=1, d=d, sp_state=self._sp(1))
        # a0 dispatched once (2nd identical call deduped), a1 is a distinct key.
        self.assertEqual(host.sent, ["1:7:drop:64.000:a0", "1:7:drop:64.000:a1"])


# ---------------------------------------------------------------------------
# D8(c) — gate stack blocks an advance under blackout / override / scripted
# ---------------------------------------------------------------------------
class _GateHost(P.LEDDispatchPolicyMixin):
    def __init__(self, *, blackout=False, manual="", scripted=0,
                 scripted_latch=True):
        self._led_look_director = object()
        self._led_scene_adapter = object()
        self._led_enabled_latch = True
        self._led_automation_enabled_latch = True
        self._blackout = blackout
        self._led_manual_override = manual
        self._led_scripted_mode_automation_latch = scripted_latch
        self._led_hold_active = False
        self._led_smart_drop_blackout_key = ""
        self._phrase_monotonic_enabled = False
        self._os = SimpleNamespace(active_deck=1, lighting_mode="autoloop")
        self.advance_calls = 0

    def _led_blackout_active(self):
        return self._blackout

    def _gate_led_automation(self, *a, **k):
        pass

    def _led_should_smart_drop_blackout(self, sp_state):
        return False

    def _dispatch_led_section_advance(self, *, active, d, sp_state):
        self.advance_calls += 1


class TestAdvanceGateStack(unittest.TestCase):
    def _deck(self, scripted=0):
        return SimpleNamespace(
            playing=True, scripted_id=scripted,
            meta=SimpleNamespace(filepath="f"))

    SP = SimpleNamespace(section_advance=True, smart_drop_crossing=False)

    def _run(self, host, scripted=0):
        host._dispatch_led_automation(
            active=1, d=self._deck(scripted), sp_state=self.SP,
            position_stale=False)
        return host.advance_calls

    def test_clean_state_dispatches_advance(self):
        self.assertEqual(self._run(_GateHost()), 1)

    def test_active_blackout_blocks_advance(self):
        self.assertEqual(self._run(_GateHost(blackout=True)), 0)

    def test_manual_override_blocks_advance(self):
        self.assertEqual(self._run(_GateHost(manual="rt_drop_x")), 0)

    def test_scripted_track_blocks_advance(self):
        host = _GateHost(scripted_latch=False)
        self.assertEqual(self._run(host, scripted=9), 0)


# ---------------------------------------------------------------------------
# D9 — every meta.smart_drops reset path also resets meta.drop_sections
# ---------------------------------------------------------------------------
class TestResetParity(unittest.TestCase):
    def test_track_metadata_clear_resets_both(self):
        m = TrackMetadata()
        m.smart_drops = [64, 128]
        m.drop_sections = (DropSection(64, 160.0, (96,)),)
        m.clear()
        self.assertEqual(m.smart_drops, [])
        self.assertEqual(m.drop_sections, ())

    def test_default_drop_sections_is_empty(self):
        self.assertEqual(TrackMetadata().drop_sections, ())

    def test_every_smart_drops_write_site_also_writes_drop_sections(self):
        # The only runtime write site is the markers_changed guard; enumerate the
        # smart_drops reset/write paths and prove each also touches drop_sections.
        sm_src = inspect.getsource(StateManager)
        # models.py clear() + field: both smart_drops and drop_sections present.
        from rb_ss_bridge_v2 import models
        models_text = Path(models.__file__).read_text()
        self.assertEqual(models_text.count("self.smart_drops = []"), 1)
        self.assertEqual(models_text.count("self.drop_sections = ()"), 1)
        # state_manager write site: the sole `meta.smart_drops =` is accompanied
        # by a `meta.drop_sections =` in the same guarded block.
        self.assertEqual(sm_src.count("meta.smart_drops = "), 1)
        self.assertEqual(sm_src.count("meta.drop_sections = "), 1)


if __name__ == "__main__":
    unittest.main()
