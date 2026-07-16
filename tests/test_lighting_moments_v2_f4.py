"""F4 texture-layer tests (AWR-164) — the S-2 CONTAINMENT proofs are the
acceptance, not an extra (spec Part C/E).

Two layers:
  * plan layer  — lighting_moments_v2 texture vector / euphoric / simmer / busy-
                  pulse (pure, computed on the async worker);
  * dispatch    — led_dispatch_policy F4 seasoning + euphoric look-preference,
                  exercised through a minimal LEDDispatchPolicyMixin subclass.

Containment law: with F4 on, the drop DECISION (family/tier/darkness/routing) is
byte-identical to F4-off — only params/variant fields differ. F4-off ⇒ family
defaults everywhere; F2-off (no plan) ⇒ F4 no-ops. Semantics locks pinned:
sustained_synth is never surfaced as "synth"; busy-pulse is computed-not-
consumed.
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import lighting_moments_v2 as M  # noqa: E402
from rb_ss_bridge_v2 import led_dispatch_policy as P  # noqa: E402
from rb_ss_bridge_v2 import led_config  # noqa: E402
from rb_ss_bridge_v2.led_look_director import LEDLookDirector  # noqa: E402
from rb_ss_bridge_v2.led_models import F4Config, LEDLookDecision  # noqa: E402

_EXAMPLE = str(Path(__file__).resolve().parents[1]
               / "config" / "led_look_director.example.json")

_SERIES = ("sub_db", "bass_db", "full_db", "growl_band_db", "perc_full",
           "attack_low_db", "onset_density_midhigh", "fluxsum_midhigh",
           "sustain_mid_db", "growl_flatness", "centroid_hz",
           "lowmid_db", "mid_db", "high_db", "air_db")


def mk_v4(n=64, ref=16.0, **overrides):
    """A fuller SpectralFeaturesV4 stub carrying every series the texture classes
    read (plus sub4/growl_band_frames), so texture computes rather than fail-soft."""
    series = {k: [0.0] * n for k in _SERIES}
    series["sub_db"] = [20.0] * n
    series["bass_db"] = [15.0] * n
    for k, v in overrides.items():
        series[k] = v
    return SimpleNamespace(
        series=series,
        sub4={"bass": [[10.0, 10.0, 10.0, 10.0]] * n},
        scalars={"loudness_ref_db": ref, "punch": 0.4, "drama": 0.4},
        n_beats=n,
        growl_band_frames=[],
        frame_hop_s=0.01,
    )


# --------------------------------------------------------------------------- #
# Plan layer — texture vector, euphoric/simmer runs, busy-pulse                #
# --------------------------------------------------------------------------- #
class TestTextureVector(unittest.TestCase):
    def test_majority_window(self):
        # bright_tilt True on the whole track → majority True in any window.
        v4 = mk_v4(centroid_hz=[9999.0] * 64, attack_low_db=[12.0] * 64)
        bank = M._texture_flag_bank(v4)
        tex = M._drop_texture(bank, onset_density_mh=1.5, drop=16)
        self.assertTrue(tex.bright_tilt)
        self.assertTrue(tex.kick_prominence)   # attack 12 over floor
        self.assertEqual(tex.onset_density_mh, 1.5)

    def test_window_majority_needs_half(self):
        flags = [True] * 8 + [False] * 8
        self.assertTrue(M._window_majority(flags, 0, 16))    # 8/16 == half
        self.assertFalse(M._window_majority(flags, 8, 8))    # all-False slice

    def test_texture_bank_failsoft_on_missing_series(self):
        # A v4 missing a series a texture class needs yields all-False for THAT
        # class (→ no seasoning), never an exception — texture must never cost the
        # family/tier/darkness plan.
        v4 = mk_v4(centroid_hz=[9999.0] * 64)
        del v4.series["centroid_hz"]                 # bright_tilt reads it
        bank = M._texture_flag_bank(v4)
        self.assertEqual(bank["bright_tilt"], [False] * 64)   # failed soft
        self.assertEqual(len(bank["stab"]), 64)               # others still compute


class TestEuphoricSimmerRuns(unittest.TestCase):
    def test_euphoric_ranges_need_min_run(self):
        flags = [True] * 8 + [False] * 4 + [True] * 7   # one qualifying run of 8
        self.assertEqual(M.euphoric_run_ranges(flags, min_run=8), ((0, 8),))

    def test_simmer_ranges_from_quiet(self):
        v4 = mk_v4(n=32, attack_low_db=[0.0] * 32, onset_density_midhigh=[0.0] * 32)
        self.assertEqual(M.simmer_run_ranges(v4, min_run=8), ((0, 32),))
        loud = mk_v4(n=32, attack_low_db=[10.0] * 32)
        self.assertEqual(M.simmer_run_ranges(loud, min_run=8), ())

    def test_plan_membership_lookup(self):
        plan = M.F2TrackPlan((), "swell", ((10, 30),), ((40, 60),))
        self.assertTrue(plan.is_euphoric(20))
        self.assertFalse(plan.is_euphoric(30))     # half-open
        self.assertTrue(plan.is_simmer(50))
        self.assertFalse(plan.is_simmer(20))


class TestBusyPulseUnconsumed(unittest.TestCase):
    def test_busy_pulse_recorded_but_no_consumer(self):
        # Computed into the plan (observability only) and behind an experimental
        # flag defaulting false. NO renderer or dispatch path may read it.
        self.assertFalse(F4Config().busy_pulse_experimental)
        src_dispatch = Path(P.__file__).read_text()
        src_render = (Path(P.__file__).parent / "govee_frame_renderer.py").read_text()
        self.assertNotIn("busy_pulse", src_dispatch)
        self.assertNotIn("busy_pulse", src_render)


def _real_v4(n=48):
    """The canonical real-shaped v4 (with sub4/duration_s) that decide_drop needs."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_spectral_profile import _v4 as mk
    v4 = mk(n_beats=n, scalars_overrides={"loudness_ref_db": 16.0})
    v4.series["sub_db"] = tuple(20.0 if not (28 <= i < 32) else 1.0 for i in range(n))
    v4.series["perc_full"] = tuple(0.6 for _ in range(n))
    v4.series["full_db"] = tuple(10.0 for _ in range(n))
    v4.series["bass_db"] = tuple(2.0 for _ in range(n))
    return v4


class TestPlanTimePurity(unittest.TestCase):
    def test_build_track_plan_is_pure(self):
        v4 = _real_v4()
        a = M.build_track_plan(v4, [16, 32], [0, 16])
        b = M.build_track_plan(v4, [16, 32], [0, 16])
        # frozen dataclasses compare by value; texture is plan-time, not per-tick.
        self.assertEqual(a.entries, b.entries)
        self.assertEqual((a.euphoric_runs, a.simmer_runs),
                         (b.euphoric_runs, b.simmer_runs))


# --------------------------------------------------------------------------- #
# Config layer                                                                 #
# --------------------------------------------------------------------------- #
class TestF4Config(unittest.TestCase):
    def test_absent_or_empty_is_disabled(self):
        self.assertFalse(F4Config.from_dict(None).enabled)
        self.assertFalse(F4Config.from_dict({}).enabled)
        self.assertFalse(led_config.load_f4_config("/no/such/file.json").enabled)

    def test_example_ships_enabled(self):
        cfg = led_config.load_f4_config(_EXAMPLE)
        self.assertTrue(cfg.enabled)
        self.assertFalse(cfg.busy_pulse_experimental)
        self.assertIn("house_sustain", cfg.variant_seasoning)
        self.assertTrue(cfg.euphoric_bright_looks)

    def test_failclosed_and_legacy_tolerant(self):
        cfg = F4Config.from_dict({
            "enabled": True,
            "variant_seasoning": {"x": {"good": 1.0, "flag": True,
                                        "nested": {"a": 1}, "name": "chase",
                                        "inf": float("inf")}},
            "legacy_unknown_key": 42,
        })
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.variant_seasoning["x"], {"good": 1.0, "name": "chase"})


# --------------------------------------------------------------------------- #
# Dispatch layer — CONTAINMENT proofs                                          #
# --------------------------------------------------------------------------- #
def mk_decision(look="rt_drop_x", params=None):
    return LEDLookDecision(
        look=look, target="room", action="scene", scene_ref="ref_" + look,
        reason="r", source="automation", priority=2, role="drop",
        backend="realtime_razer", params=dict(params or {}),
    )


def mk_entry(family="HOUSE", tier=2, bass_forward="", **tex):
    dec = SimpleNamespace(family=family, tier=tier, bass_forward=bass_forward)
    return SimpleNamespace(decision=dec, texture=M.DropTexture(**tex))


class FakePolicy(P.LEDDispatchPolicyMixin):
    """Minimal mixin host: just the attributes the F4 methods read."""
    def __init__(self, *, enabled, cfg, plan=None, beat=10.0,
                 active_drop_beat=100.0, scripted=0):
        self._f4_enabled = enabled
        self._f4_config = cfg
        self._last_sp_state = SimpleNamespace(active_drop_beat=active_drop_beat)
        self._os = SimpleNamespace(active_deck=1)
        self._deck = {1: SimpleNamespace(meta=SimpleNamespace(f2_plan=plan),
                                         scripted_id=scripted)}
        self._beat = beat

    def _led_abs_beat(self, sp_state):   # override the real position math
        return self._beat


def cfg_on():
    return led_config.load_f4_config(_EXAMPLE)


class TestContainment(unittest.TestCase):
    def test_f4_off_seasoning_is_identity(self):
        pol = FakePolicy(enabled=False, cfg=cfg_on())
        d = mk_decision(params={"a": 1})
        self.assertIs(pol._led_inject_f4_seasoning(d, role="drop"), d)

    def test_f2_off_no_plan_noops(self):
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=None)
        d = mk_decision()
        self.assertIs(pol._led_inject_f4_seasoning(d, role="drop"), d)

    def test_scripted_stands_down(self):
        plan = SimpleNamespace(for_drop=lambda b: mk_entry("HOUSE", 2, stab=True))
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=plan, scripted=7)
        d = mk_decision()
        self.assertIs(pol._led_inject_f4_seasoning(d, role="drop"), d)

    def test_seasoning_changes_only_params(self):
        entry = mk_entry("HOUSE", 2, stab=True)
        plan = SimpleNamespace(for_drop=lambda b: entry)
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=plan)
        d = mk_decision(params={"keep": 9})
        out = pol._led_inject_f4_seasoning(d, role="drop")
        # LEDLookDecision compares params with compare=False → equality proves
        # look/scene_ref/backend/routing/role byte-identical.
        self.assertEqual(out, d)
        self.assertNotEqual(dict(out.params), dict(d.params))   # params seasoned
        self.assertEqual(out.params["keep"], 9)                 # base params kept
        self.assertIn("sparkle_density", out.params)            # house_stab cell

    def test_unknown_texture_is_family_default(self):
        # A COMET drop maps to comet_default → {} → no seasoning (family default).
        entry = mk_entry("COMET", 3)
        plan = SimpleNamespace(for_drop=lambda b: entry)
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=plan)
        d = mk_decision()
        self.assertIs(pol._led_inject_f4_seasoning(d, role="drop"), d)

    def test_csn_bass_forward_drives_density(self):
        # D§5.1 anchor: CSN BKBBBKBBBKBBBKBB (12/16 B) → 0.2 + 0.75*0.4 = 0.5.
        entry = mk_entry("HOUSE", 2, sustained_bass=True)
        entry.decision.bass_forward = "BKBBBKBBBKBBBKBB"
        plan = SimpleNamespace(for_drop=lambda b: entry)
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=plan)
        out = pol._led_inject_f4_seasoning(mk_decision(), role="drop")
        self.assertEqual(out.params["sparkle_density"], 0.5)

    def test_bass_forward_scoped_to_house(self):
        # A WALL drop's mask must NOT override the trap/dense density.
        entry = mk_entry("WALL", 3, onset_density_mh=1.0)   # → wall_trap cell
        entry.decision.bass_forward = "BBBBBBBBBBBBBBBB"
        plan = SimpleNamespace(for_drop=lambda b: entry)
        pol = FakePolicy(enabled=True, cfg=cfg_on(), plan=plan)
        out = pol._led_inject_f4_seasoning(mk_decision(), role="drop")
        self.assertEqual(out.params["sparkle_density"], 0.2)   # wall_trap, not mask


class TestEuphoricPreference(unittest.TestCase):
    def _pol(self, plan, beat, enabled=True):
        pol = FakePolicy(enabled=enabled, cfg=cfg_on(), plan=plan, beat=beat)
        return pol

    def test_bright_only_inside_euphoric(self):
        plan = M.F2TrackPlan((), "swell", ((0, 32),), ())
        inside = self._pol(plan, beat=10)._led_f4_euphoric_bright()
        outside = self._pol(plan, beat=50)._led_f4_euphoric_bright()
        self.assertIsNotNone(inside)
        self.assertIsNone(outside)

    def test_f4_off_no_bright(self):
        plan = M.F2TrackPlan((), "swell", ((0, 32),), ())
        self.assertIsNone(self._pol(plan, 10, enabled=False)._led_f4_euphoric_bright())

    def test_euphoric_only_adds_preference_within_bank(self):
        # The euphoric term only ever NARROWS the intersection — it can never
        # select a look outside the routing/base set.
        base = lambda n: n in {"a", "b", "c"}
        bright = {"c", "d", "z"}
        pol = FakePolicy(enabled=True, cfg=cfg_on())
        pol._led_v2_look_preference_predicate = lambda: base
        pol._led_f2_drop_look_names = lambda: {"b", "c", "d"}
        pol._led_f4_euphoric_bright = lambda: bright
        preds = pol._led_look_preference_predicate()
        passing = ["a", "b", "c", "d", "z"]
        for pred in preds:
            narrowed = [n for n in passing if pred(n)]
            if narrowed:
                passing = narrowed
        self.assertEqual(passing, ["c"])   # intersection only; never z (outside)

    def test_empty_f2_f4_intersection_commits_inside_f2_cell(self):
        loaded = led_config.load_led_look_director_config(_EXAMPLE)
        self.assertTrue(loaded.available, msg=loaded.errors)
        director = LEDLookDirector(replace(loaded.config, enabled=True, automation_enabled=True))
        # AWR-265 step 2: color clones left banks.default.drop; use banked bases.
        f2_cell = {"rt_drop_chase", "rt_drop_center_burst"}
        bright = {"rt_drop_strobe_red"}
        pol = FakePolicy(enabled=True, cfg=cfg_on())
        pol._led_v2_look_preference_predicate = lambda: None
        pol._led_f2_drop_look_names = lambda: f2_cell
        pol._led_f4_euphoric_bright = lambda: bright

        decision = director.commit_role(
            "drop", look_preference=pol._led_look_preference_predicate(),
        )

        self.assertIn(decision.look, f2_cell)


class TestSemanticsLocks(unittest.TestCase):
    def test_sustained_synth_never_surfaced_as_synth(self):
        # C§6d/e: the clean-euphoric proxy counts vocals and is NEVER labelled
        # "synth" anywhere F4 surfaces. No texture field, plan field, seasoning
        # key, or euphoric surface names it "synth".
        self.assertFalse(hasattr(M.DropTexture(), "synth"))
        self.assertFalse(hasattr(M.F2TrackPlan((), "swell"), "synth"))
        cfg = led_config.load_f4_config(_EXAMPLE)
        for key in cfg.variant_seasoning:
            self.assertNotIn("synth", key)
        # the runtime seasoning-key function never emits a "synth" key either
        for fam in ("HOUSE", "WALL", "COMET", "NEUTRAL"):
            k = P._f4_drop_seasoning_key(fam, M.DropTexture(sustained_bass=True))
            self.assertNotIn("synth", k)


if __name__ == "__main__":
    unittest.main()
