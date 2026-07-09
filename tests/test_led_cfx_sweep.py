"""AWR-173 CFX filter-sweep tests: envelope, dispatch gating, anchor provider,
child-side overlay, and config loader. Pure seams only — no mach, no live
process, no sockets."""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.state_manager import StateManager, CFX_STALE_AFTER_S
from rb_ss_bridge_v2.led_dispatch_policy import (
    LEDDispatchPolicyMixin,
    cfx_sweep_envelope,
    CfxEnvState,
    CFX_ANCHOR_DEAD_S,
    LED_IDLE_FREEWHEEL_BPM,
)
from rb_ss_bridge_v2.led_models import CfxSweepConfig, BeatAnchor
from rb_ss_bridge_v2.led_config import load_cfx_sweep_config
from rb_ss_bridge_v2.models import CfxDeckReading, CfxFilterSnapshot
from rb_ss_bridge_v2.govee_realtime_runner import _apply_cfx_overlay, GoveeRealtimeRunner, EffectSpec
from rb_ss_bridge_v2.govee_frame_engine_client import _anchor_to_wire
from rb_ss_bridge_v2.govee_frame_engine import _parse_cfx_rgb
from rb_ss_bridge_v2.govee_frame_renderer import GoveeFrameRenderer, _lerp, _scale


CFG = CfxSweepConfig(enabled=True)  # engage_deadband 0.02, thr 0.75, ramps, dim_floor 0.08


# ── Part D.3 — envelope unit tests (TRIGGER semantics, one-way return) ────────
class EnvelopeTests(unittest.TestCase):
    """Crossing the bloom threshold TRIGGERS a one-shot timed drain (dim 1->floor
    over drain_ms), then holds; the dim is NOT knob-tracked. Riding back below the
    threshold LATCHES a one-way release of the whole overlay that stays released for
    the entire ride down — re-firing needs a fresh sweep from neutral, so the return
    ride cannot re-bloom (operator return-ride ruling 2026-07-09)."""

    def test_ccw_and_neutral_are_exactly_neutral(self) -> None:
        # The operator's final ruling: knob at/below 12 o'clock does NOTHING.
        for knob in (0.0, 0.3, 0.49, 0.5):
            st = cfx_sweep_envelope(knob, CfxEnvState(), 0.1, CFG)
            self.assertEqual((st.mix, st.dim, st.fired), (0.0, 1.0, False), msg=f"knob={knob}")

    def test_jitter_at_exactly_half_is_neutral(self) -> None:
        # 0.5 is NOT engaged (deadband > 0): jitter at 12 o'clock does nothing.
        st = cfx_sweep_envelope(0.5, CfxEnvState(), 0.1, CFG)
        self.assertEqual((st.mix, st.dim, st.fired), (0.0, 1.0, False))

    def test_flood_only_below_threshold_ramps_mix_no_dim_no_fire(self) -> None:
        # Engaged but below the bloom threshold: flood in over flood_ramp_ms, dim 1.0,
        # never fires (never crossed). Unchanged from the original sub-threshold law.
        st = cfx_sweep_envelope(0.70, CfxEnvState(), CFG.flood_ramp_ms / 1000.0, CFG)
        self.assertEqual(st.mix, 1.0)     # full flood in one flood_ramp_ms step
        self.assertEqual(st.dim, 1.0)     # below threshold: no dimming
        self.assertFalse(st.fired)        # never fired
        half = cfx_sweep_envelope(0.70, CfxEnvState(), CFG.flood_ramp_ms / 2000.0, CFG)
        self.assertAlmostEqual(half.mix, 0.5, places=6)

    def test_flood_releases_at_deadband(self) -> None:
        # Returning under the deadband from a below-threshold (never-fired) flood
        # releases (mix -> 0) — the unchanged pre-fire behavior.
        flooded = CfxEnvState(mix=1.0, dim=1.0)
        st = cfx_sweep_envelope(0.4, flooded, CFG.release_ramp_ms / 1000.0, CFG)
        self.assertEqual(st.mix, 0.0)
        self.assertEqual(st.dim, 1.0)

    def test_crossing_fires_drain_once_to_floor(self) -> None:
        # Crossing the threshold fires the drain; a long dt drains dim to the floor.
        st = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)  # dt 1s >> drain_ms
        self.assertTrue(st.fired)                                # fired
        self.assertFalse(st.released)                            # still above thr, draining
        self.assertAlmostEqual(st.dim, CFG.dim_floor, places=6)  # drained to the floor
        self.assertEqual(st.mix, 1.0)                            # flood is the swell

    def test_hold_above_threshold_after_drain_changes_nothing(self) -> None:
        # Three DIFFERENT held knob values above the threshold, same elapsed time ->
        # identical dim. Knob position above threshold has NO effect (timed, not tracked).
        def held_dim(hold: float) -> float:
            fired = cfx_sweep_envelope(0.9, CfxEnvState(), 0.2, CFG)  # fire, partial drain
            return cfx_sweep_envelope(hold, fired, 0.2, CFG).dim      # keep holding
        dims = {round(held_dim(h), 9) for h in (0.80, 0.90, 1.0)}
        self.assertEqual(len(dims), 1, msg=f"held dims differ: {dims}")
        self.assertGreater(dims.pop(), CFG.dim_floor)  # partial (proves it is a timed ramp)

    def test_single_tick_jump_floods_and_fires(self) -> None:
        # A single tick from below the deadband straight past the threshold must not
        # miss the trigger: it both floods AND fires the drain.
        low = cfx_sweep_envelope(0.4, CfxEnvState(), 0.05, CFG)  # sitting below deadband
        self.assertFalse(low.fired)
        jumped = cfx_sweep_envelope(0.95, low, 1.0, CFG)
        self.assertTrue(jumped.fired)                             # fired
        self.assertGreater(jumped.mix, 0.0)                       # floods
        self.assertAlmostEqual(jumped.dim, CFG.dim_floor, places=6)  # and drains

    def test_release_after_fire_is_sequential_flood_then_brightness(self) -> None:
        # AWR-173 re-bloom fix: after firing, release is SEQUENTIAL, not concurrent. The
        # moment the knob drops below thr the overlay latches released; while the flood is
        # still up dim HOLDS at the floor and the flood drains to 0, and only THEN does
        # brightness rise. (The old behavior ramped mix and dim together and flared the
        # flood color back mid-release from a dark room.)
        fired = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)  # mix 1, dim floor, fired
        half = cfx_sweep_envelope(0.74, fired, CFG.release_ramp_ms / 2000.0, CFG)  # below thr
        self.assertTrue(half.released)                           # one-way release latched
        self.assertAlmostEqual(half.mix, 0.5, places=6)          # flood draining 1.0 -> 0.5
        self.assertAlmostEqual(half.dim, CFG.dim_floor, places=6)  # dim HELD (not risen) while mix > 0
        # A full-ramp step from mix 0.5 finishes draining the flood; dim still held.
        zeroed = cfx_sweep_envelope(0.74, half, CFG.release_ramp_ms / 1000.0, CFG)
        self.assertEqual(zeroed.mix, 0.0)                        # flood fully gone first
        self.assertAlmostEqual(zeroed.dim, CFG.dim_floor, places=6)  # brightness has NOT started rising
        # Only now, with the flood already 0, does brightness rise back to 1.0.
        restored = cfx_sweep_envelope(0.74, zeroed, CFG.release_ramp_ms / 1000.0, CFG)
        self.assertEqual((restored.mix, restored.dim), (0.0, 1.0))

    def test_return_ride_parked_above_deadband_stays_released(self) -> None:
        # Operator return-ride ruling: after firing, the moment the knob drops below thr
        # the overlay releases and STAYS released for the whole ride down — parking
        # anywhere above the deadband must never re-flood, re-dim, or re-fire.
        fired = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)  # mix 1, dim floor, fired
        self.assertTrue(fired.fired)
        st = fired
        for knob in (0.72, 0.65, 0.58, 0.55):   # engaged but below thr; walking down
            st = cfx_sweep_envelope(knob, st, 0.05, CFG)
            self.assertTrue(st.released)                # latched released for the whole ride
            self.assertLessEqual(st.mix, fired.mix)     # mix only fades, never re-floods
            self.assertGreaterEqual(st.dim, fired.dim)  # brightness restores, never re-drains
        # Park at 0.55 "forever": overlay finishes releasing and holds fully neutral.
        for _ in range(200):
            st = cfx_sweep_envelope(0.55, st, 0.05, CFG)
        self.assertEqual((st.mix, st.dim), (0.0, 1.0))  # fully released, no flood, no dim
        self.assertTrue(st.fired and st.released)       # still latched (not re-armed off-neutral)

    def test_return_ride_back_above_threshold_does_not_refire(self) -> None:
        # The return ride overshoots back above thr WITHOUT going to neutral: the latch
        # holds — no re-flood, no re-fire — until the knob actually reaches neutral.
        fired = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)  # mix 1, fired
        dip = cfx_sweep_envelope(0.70, fired, 0.05, CFG)          # below thr -> latch released
        self.assertTrue(dip.released)
        self.assertLess(dip.mix, fired.mix)                       # already fading out
        repush = cfx_sweep_envelope(0.95, dip, 0.05, CFG)         # shove back past thr
        self.assertTrue(repush.released)                          # STILL released — no re-fire
        self.assertLessEqual(repush.mix, dip.mix)                 # mix keeps fading, never re-blooms
        # Only a return to neutral re-arms, then a fresh sweep fires again.
        neutral = cfx_sweep_envelope(0.5, repush, 0.05, CFG)
        self.assertFalse(neutral.fired or neutral.released)       # re-armed at neutral
        refired = cfx_sweep_envelope(0.95, neutral, 1.0, CFG)
        self.assertTrue(refired.fired)                            # fired again like the first time
        self.assertAlmostEqual(refired.dim, CFG.dim_floor, places=6)

    def test_threshold_jitter_after_fire_does_not_rebloom(self) -> None:
        # Jitter across thr right after firing: the first dip below thr latches release,
        # and ticks that bounce back above thr must NOT snap mix/dim back up (no machine-gun).
        st = cfx_sweep_envelope(0.9, CfxEnvState(), 0.2, CFG)     # fire, partial drain
        self.assertTrue(st.fired)
        prev_mix = st.mix
        for knob in (0.745, 0.755, 0.745, 0.755, 0.745):         # jitter around thr 0.75
            st = cfx_sweep_envelope(knob, st, 0.01, CFG)
            self.assertTrue(st.fired, msg=f"knob={knob} lost the fired latch")
            self.assertLessEqual(st.mix, prev_mix + 1e-9, msg=f"knob={knob} re-bloomed")
            prev_mix = st.mix
        self.assertTrue(st.released)   # a sub-thr jitter tick latched the one-way release

    def test_release_from_drained_never_flares(self) -> None:
        # Leg 1: from a fully-drained (dark) room, releasing must NOT flare the flood color
        # back mid-release. The OLD concurrent ramp peaked mix*dim ~0.27 halfway through the
        # release; the sequential release keeps the visible product monotonically
        # non-increasing and never above the drained floor until the flood is fully gone,
        # then brightness rises alone. (Numeric: old peak ~0.27 vs held <= dim_floor 0.08.)
        drained = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)   # mix 1, dim floor, fired
        self.assertEqual(drained.mix, 1.0)
        self.assertAlmostEqual(drained.dim, CFG.dim_floor, places=6)
        st = drained
        prev_product = drained.mix * drained.dim
        saw_mix_zero = False
        for _ in range(400):                        # 400 * 5ms = 2s >> 2x release_ramp
            st = cfx_sweep_envelope(0.6, st, 0.005, CFG)   # engaged, below thr -> released
            self.assertTrue(st.released)
            product = st.mix * st.dim
            if st.mix > 0.0:
                # phase A: flood draining under a HELD dark dim — product only falls, no flare
                self.assertLessEqual(product, CFG.dim_floor + 1e-9)
                self.assertLessEqual(product, prev_product + 1e-9)
                self.assertAlmostEqual(st.dim, CFG.dim_floor, places=6)   # dim held while mix > 0
            else:
                saw_mix_zero = True
            prev_product = product
        self.assertTrue(saw_mix_zero)
        self.assertEqual((st.mix, st.dim), (0.0, 1.0))  # ends neutral: flood gone, brightness back

    def test_idle_from_drained_never_flares(self) -> None:
        # Same anti-flare property when the knob drops STRAIGHT to neutral in one tick from a
        # drained fire (enters IDLE with dim at the floor). Sequential release, no flare.
        drained = cfx_sweep_envelope(0.9, CfxEnvState(), 1.0, CFG)   # mix 1, dim floor, fired
        st = drained
        prev_product = drained.mix * drained.dim
        saw_mix_zero = False
        for _ in range(400):
            st = cfx_sweep_envelope(0.3, st, 0.005, CFG)   # neutral -> IDLE branch, re-armed
            self.assertFalse(st.fired or st.released)       # neutral clears the engagement
            product = st.mix * st.dim
            if st.mix > 0.0:
                self.assertLessEqual(product, CFG.dim_floor + 1e-9)
                self.assertLessEqual(product, prev_product + 1e-9)
                self.assertAlmostEqual(st.dim, CFG.dim_floor, places=6)
            else:
                saw_mix_zero = True
            prev_product = product
        self.assertTrue(saw_mix_zero)
        self.assertEqual((st.mix, st.dim), (0.0, 1.0))

    def test_never_fired_release_dim_stays_one(self) -> None:
        # A sub-threshold (never-fired) flood releasing: dim is already 1.0, so the sequential
        # release is byte-identical to the old concurrent ramp — dim never leaves 1.0, mix fades.
        flooded = cfx_sweep_envelope(0.70, CfxEnvState(), CFG.flood_ramp_ms / 1000.0, CFG)
        self.assertEqual((flooded.mix, flooded.dim, flooded.fired), (1.0, 1.0, False))
        st = flooded
        for _ in range(400):
            st = cfx_sweep_envelope(0.3, st, 0.005, CFG)   # back to neutral
            self.assertEqual(st.dim, 1.0)                   # dim never leaves 1.0
        self.assertEqual((st.mix, st.dim), (0.0, 1.0))

    def test_dt_zero_holds_and_is_safe(self) -> None:
        st = cfx_sweep_envelope(0.9, CfxEnvState(mix=0.3, dim=0.6), 0.0, CFG)
        self.assertEqual(st.mix, 0.3)   # no ramp with dt=0
        self.assertEqual(st.dim, 0.6)   # no ramp with dt=0
        self.assertTrue(st.fired)       # fire is edge-triggered, not dt-gated
        self.assertTrue(CFG.dim_floor <= st.dim <= 1.0)

    def test_out_of_range_and_nan_knob_are_safe(self) -> None:
        for knob in (-5.0, 5.0, float("nan"), float("inf")):
            st = cfx_sweep_envelope(knob, CfxEnvState(mix=0.5, dim=0.5), 0.1, CFG)
            self.assertTrue(0.0 <= st.mix <= 1.0, msg=f"knob={knob} mix={st.mix}")
            self.assertTrue(
                CFG.dim_floor - 1e-9 <= st.dim <= 1.0, msg=f"knob={knob} dim={st.dim}"
            )


# ── Part D.4 — dispatch gating + anchor provider ─────────────────────────────
def _reading(deck: int, filter_norm: float, *, valid: bool = True, reason: str = "ok") -> CfxDeckReading:
    return CfxDeckReading(
        deck=deck, filter_norm=filter_norm, selected_effect_id=0,
        unit_channel=deck - 1, valid=valid, reason=reason,
    )


def _snapshot(readings, updated_at: float) -> CfxFilterSnapshot:
    return CfxFilterSnapshot(valid=True, deck=readings, updated_at=updated_at, reason="ok")


def _sm_ns(cfg, snapshot, *, blackout=False, breakdown=False, darkest=(10, 0, 40),
           smart_drop_blackout=""):
    return SimpleNamespace(
        _cfx_sweep_config=cfg,
        _cfx_snapshot=snapshot,
        _led_blackout_active=(lambda: blackout),
        _os=SimpleNamespace(breakdown_active=breakdown),
        _led_color_engine=SimpleNamespace(v2_darkest_rgb=(lambda: darkest)),
        _led_smart_drop_blackout_key=smart_drop_blackout,
        _led_cfx_state=CfxEnvState(),
        _led_cfx_last_mono=0.0,
        _led_cfx_sweep="unset",
    )


def _compute(ns, active, now):
    StateManager._compute_led_cfx_sweep(ns, active, now)
    return ns._led_cfx_sweep


class DispatchGatingTests(unittest.TestCase):
    def _engaged_snapshot(self, now):
        return _snapshot({1: _reading(1, 0.9), 2: _reading(2, 0.5)}, now)

    def test_engaged_valid_produces_overlay_tuple(self) -> None:
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now))
        ns._led_cfx_last_mono = now - 1.0  # non-zero dt so the flood ramp advances
        out = _compute(ns, 1, now)
        self.assertIsNotNone(out)
        mix, dim, rgb, cap = out
        self.assertGreater(mix, 0.0)   # engaged knob 0.9 floods in
        self.assertLess(dim, 1.0)      # knob 0.9 > threshold 0.75 dims
        self.assertEqual(rgb, (10, 0, 40))
        self.assertEqual(cap, now)

    def test_feature_off_is_inert(self) -> None:
        now = 100.0
        ns = _sm_ns(CfxSweepConfig(enabled=False), self._engaged_snapshot(now))
        self.assertIsNone(_compute(ns, 1, now))

    def test_blackout_is_inert(self) -> None:
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), blackout=True)
        self.assertIsNone(_compute(ns, 1, now))

    def test_f2_darkness_hold_is_inert(self) -> None:
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), breakdown=True)
        self.assertIsNone(_compute(ns, 1, now))

    def test_smart_drop_tactical_blackout_is_inert_and_latches_released(self) -> None:
        # The pre-drop tactical blackout sets NO blackout owner and NO breakdown flag, yet
        # the room is meant to be pure black. A non-empty _led_smart_drop_blackout_key forces
        # the sweep OUTPUT inert (mix 0, dim 1, tuple None) so the dark-hue flood can't light
        # F2's intended-black drop moment. AWR-173 Leg 2 correction: a FIRED engagement comes
        # back LATCHED-RELEASED (not full-neutral) — the output is still zeroed, but the trigger
        # stays disarmed so the flood does NOT re-bloom on the healthy tick after the blackout
        # lifts; it re-arms only when the knob returns to neutral.
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), smart_drop_blackout="d1@480.0")
        ns._led_cfx_last_mono = now - 1.0
        ns._led_cfx_state = CfxEnvState(mix=0.7, dim=0.3, fired=True)  # mid-drain
        self.assertIsNone(_compute(ns, 1, now))
        self.assertEqual(ns._led_cfx_state, CfxEnvState(fired=True, released=True))  # zeroed output, latched

    def test_smart_drop_blackout_never_fired_resets_clean(self) -> None:
        # A blip over a PRE-FIRE flood (never fired) resets clean — knob-state behavior, so a
        # still-engaged pre-fire flood may resume when the mask lifts (correct, not a re-bloom).
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), smart_drop_blackout="d1@480.0")
        ns._led_cfx_last_mono = now - 1.0
        ns._led_cfx_state = CfxEnvState(mix=0.4, dim=1.0, fired=False)  # pre-fire flood
        self.assertIsNone(_compute(ns, 1, now))
        self.assertEqual(ns._led_cfx_state, CfxEnvState())   # full neutral: nothing fired to latch

    def test_sweep_resumes_when_tactical_blackout_clears(self) -> None:
        # Key cleared (== "") on the same engaged input: the sweep floods again.
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), smart_drop_blackout="")
        ns._led_cfx_last_mono = now - 1.0
        out = _compute(ns, 1, now)
        self.assertIsNotNone(out)
        self.assertGreater(out[0], 0.0)       # resumes from neutral (prev_mix 0 -> floods)

    def test_v2_off_no_dressing_is_inert(self) -> None:
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now), darkest=None)
        self.assertIsNone(_compute(ns, 1, now))

    def test_stale_snapshot_is_inert(self) -> None:
        now = 100.0
        stale = self._engaged_snapshot(now - (CFX_STALE_AFTER_S + 0.5))
        ns = _sm_ns(CFG, stale)
        self.assertIsNone(_compute(ns, 1, now))

    def test_missing_snapshot_is_inert(self) -> None:
        ns = _sm_ns(CFG, None)
        self.assertIsNone(_compute(ns, 1, 100.0))

    def test_invalid_active_deck_reading_is_inert(self) -> None:
        now = 100.0
        snap = _snapshot({1: _reading(1, 0.9, valid=False, reason="wrong_effect")}, now)
        ns = _sm_ns(CFG, snap)
        self.assertIsNone(_compute(ns, 1, now))

    def test_active_deck_zero_is_inert(self) -> None:
        now = 100.0
        ns = _sm_ns(CFG, self._engaged_snapshot(now))
        self.assertIsNone(_compute(ns, 0, now))

    def test_per_deck_independence_deck2_valid_deck1_invalid(self) -> None:
        now = 100.0
        snap = _snapshot(
            {1: _reading(1, 0.9, valid=False, reason="unreadable"), 2: _reading(2, 0.9)},
            now,
        )
        ns1 = _sm_ns(CFG, snap)
        ns2 = _sm_ns(CFG, snap)
        ns2._led_cfx_last_mono = now - 1.0                          # non-zero dt so it floods
        self.assertIsNone(_compute(ns1, 1, now))                    # deck 1 inert
        self.assertIsNotNone(_compute(ns2, 2, now))                 # deck 2 floods


class AnchorProviderTests(unittest.TestCase):
    def _anchor_ns(self, cfx_sweep, *, freewheel=False):
        now = time.monotonic()
        return SimpleNamespace(
            _led_idle_freewheel_since=(now if freewheel else None),
            _led_rt_permitted=True,
            _led_rt_beat=(1, 4.0, 128.0, now, True),
            _led_cfx_sweep=cfx_sweep,
        )

    def test_freewheel_branch_is_always_neutral(self) -> None:
        ns = self._anchor_ns((0.9, 0.3, (10, 0, 40), time.monotonic()), freewheel=True)
        anchor = LEDDispatchPolicyMixin.get_active_beat_anchor(ns)
        self.assertEqual(anchor.bpm, LED_IDLE_FREEWHEEL_BPM)
        self.assertEqual((anchor.cfx_mix, anchor.cfx_dim, anchor.cfx_rgb), (0.0, 1.0, None))

    def test_fresh_tuple_is_attached(self) -> None:
        ns = self._anchor_ns((0.8, 0.4, (10, 0, 40), time.monotonic()))
        anchor = LEDDispatchPolicyMixin.get_active_beat_anchor(ns)
        self.assertEqual((anchor.cfx_mix, anchor.cfx_dim, anchor.cfx_rgb), (0.8, 0.4, (10, 0, 40)))

    def test_stale_tuple_neutralized_at_provider(self) -> None:
        old = time.monotonic() - (CFX_ANCHOR_DEAD_S + 0.5)
        ns = self._anchor_ns((0.8, 0.4, (10, 0, 40), old))
        anchor = LEDDispatchPolicyMixin.get_active_beat_anchor(ns)
        self.assertEqual((anchor.cfx_mix, anchor.cfx_dim, anchor.cfx_rgb), (0.0, 1.0, None))

    def test_no_stored_tuple_is_neutral(self) -> None:
        ns = self._anchor_ns(None)
        anchor = LEDDispatchPolicyMixin.get_active_beat_anchor(ns)
        self.assertEqual((anchor.cfx_mix, anchor.cfx_dim, anchor.cfx_rgb), (0.0, 1.0, None))


# ── Part D.5 — child-side overlay ────────────────────────────────────────────
class ChildOverlayTests(unittest.TestCase):
    def test_parse_cfx_rgb(self) -> None:
        self.assertEqual(_parse_cfx_rgb([10, 20, 30]), (10, 20, 30))
        self.assertEqual(_parse_cfx_rgb([300, -5, 128]), (255, 0, 128))  # clamped
        self.assertIsNone(_parse_cfx_rgb(None))
        self.assertIsNone(_parse_cfx_rgb([1, 2]))
        self.assertIsNone(_parse_cfx_rgb("nope"))

    def _child_parse(self, wire: dict) -> BeatAnchor:
        # Mirror govee_frame_engine.handle_message's anchor construction exactly.
        return BeatAnchor(
            deck=int(wire["deck"]),
            abs_beat_pos=float(wire["abs_beat_pos"]),
            bpm=float(wire["bpm"]),
            captured_monotonic=float(wire["captured_monotonic"]),
            playing=bool(wire["playing"]),
            permitted=bool(wire["permitted"]),
            cfx_mix=float(wire.get("cfx_mix", 0.0)),
            cfx_dim=float(wire.get("cfx_dim", 1.0)),
            cfx_rgb=_parse_cfx_rgb(wire.get("cfx_rgb")),
        )

    def test_wire_round_trip_carries_cfx(self) -> None:
        a = BeatAnchor(1, 4.0, 128.0, 10.0, True, True, cfx_mix=0.8, cfx_dim=0.4, cfx_rgb=(10, 0, 40))
        wire = json.loads(json.dumps(_anchor_to_wire(a)))  # survive JSON transit
        parsed = self._child_parse(wire)
        self.assertEqual((parsed.cfx_mix, parsed.cfx_dim, parsed.cfx_rgb), (0.8, 0.4, (10, 0, 40)))

    def test_frozen_child_skew_missing_fields_parse_neutral(self) -> None:
        # An OLD parent's wire message has no cfx_* keys.
        wire = {"deck": 1, "abs_beat_pos": 4.0, "bpm": 128.0,
                "captured_monotonic": 10.0, "playing": True, "permitted": True}
        parsed = self._child_parse(wire)
        self.assertEqual((parsed.cfx_mix, parsed.cfx_dim, parsed.cfx_rgb), (0.0, 1.0, None))

    def test_apply_overlay_neutral_is_identity(self) -> None:
        frame = [(10, 20, 30), (40, 50, 60)]
        neutral = BeatAnchor(1, 0.0, 120.0, 0.0, True, True)  # cfx defaults
        self.assertIs(_apply_cfx_overlay(frame, neutral), frame)

    def test_apply_overlay_matches_scale_lerp(self) -> None:
        frame = [(200, 100, 50), (10, 240, 30), (0, 0, 0), (255, 255, 255)]
        a = BeatAnchor(1, 0.0, 120.0, 0.0, True, True, cfx_mix=0.6, cfx_dim=0.5, cfx_rgb=(20, 0, 80))
        got = _apply_cfx_overlay(frame, a)
        expected = [_scale(_lerp(px, (20, 0, 80), 0.6), 0.5) for px in frame]
        self.assertEqual(got, expected)

    def test_apply_overlay_dim_only(self) -> None:
        frame = [(100, 100, 100)]
        a = BeatAnchor(1, 0.0, 120.0, 0.0, True, True, cfx_mix=0.0, cfx_dim=0.5, cfx_rgb=None)
        self.assertEqual(_apply_cfx_overlay(frame, a), [_scale((100, 100, 100), 0.5)])

    def test_runner_permitted_frame_gets_overlay(self) -> None:
        transport = _RecordingTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(EffectSpec("solid", {"color": [100, 100, 100]}, 1, 100.0))
        anchor = BeatAnchor(1, 64.0, 120.0, 100.0, True, True,
                            cfx_mix=1.0, cfx_dim=0.5, cfx_rgb=(0, 0, 0))
        runner._tick_once(anchor, 100.0)
        composed = [(100, 100, 100)] * 4
        expected = [_scale(_lerp(px, (0, 0, 0), 1.0), 0.5) for px in composed]
        self.assertEqual(transport.frames[-1], expected)

    def test_runner_emergency_path_sends_no_overlay_frame(self) -> None:
        transport = _RecordingTransport()
        runner = GoveeRealtimeRunner(transport, GoveeFrameRenderer(), segments=4, fps=30)
        runner.set_desired(EffectSpec("solid", {"color": [100, 100, 100]}, 1, 100.0))
        anchor = BeatAnchor(1, 64.0, 120.0, 100.0, True, True,
                            cfx_mix=1.0, cfx_dim=0.5, cfx_rgb=(0, 0, 0))
        runner._tick_once(anchor, 100.0)          # normal frame
        n = len(transport.frames)
        runner._emergency.set()
        runner._tick_once(anchor, 100.1)          # emergency short-circuits before compose
        self.assertEqual(len(transport.frames), n)  # no overlay frame emitted


class _RecordingTransport:
    def __init__(self) -> None:
        self.frames: list = []

    def activate(self) -> bool: return True
    def deactivate(self) -> bool: return True
    def set_brightness(self, value: int) -> bool: return True
    def blackout(self) -> bool: return True
    def close(self) -> None: pass
    def status(self) -> dict: return {"frames_sent": len(self.frames)}

    def send_frame(self, frame) -> bool:
        self.frames.append(list(frame))
        return True


# ── Part D.6 — config loader ─────────────────────────────────────────────────
class ConfigLoaderTests(unittest.TestCase):
    def _write(self, block) -> str:
        import tempfile
        fd = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({} if block is None else {"cfx_sweep": block}, fd)
        fd.close()
        self.addCleanup(lambda: Path(fd.name).unlink(missing_ok=True))
        return fd.name

    def test_absent_block_is_disabled(self) -> None:
        cfg = load_cfx_sweep_config(self._write(None))
        self.assertFalse(cfg.enabled)

    def test_missing_file_is_disabled(self) -> None:
        self.assertFalse(load_cfx_sweep_config("/no/such/file.json").enabled)

    def test_valid_block_loads(self) -> None:
        cfg = load_cfx_sweep_config(self._write({"enabled": True, "bloom_threshold_norm": 0.8}))
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.bloom_threshold_norm, 0.8)

    def test_bloom_at_or_below_engage_point_rejected(self) -> None:
        # bloom_threshold_norm must exceed 0.5 + engage_deadband, else disabled.
        cfg = load_cfx_sweep_config(
            self._write({"enabled": True, "engage_deadband": 0.02, "bloom_threshold_norm": 0.52})
        )
        self.assertFalse(cfg.enabled)  # 0.52 <= 0.5 + 0.02 -> whole block disabled

    def test_out_of_range_values_disabled(self) -> None:
        for bad in ({"bloom_threshold_norm": 1.5}, {"dim_floor": 2.0}, {"flood_ramp_ms": 0.0}):
            block = {"enabled": True, **bad}
            self.assertFalse(load_cfx_sweep_config(self._write(block)).enabled, msg=str(bad))

    def test_drain_ms_field_defaults(self) -> None:
        self.assertEqual(CfxSweepConfig().drain_ms, 800.0)

    def test_drain_ms_field_loads(self) -> None:
        cfg = load_cfx_sweep_config(self._write({"enabled": True, "drain_ms": 500.0}))
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.drain_ms, 500.0)

    def test_unknown_key_is_ignored_live_config_compat(self) -> None:
        # The live config still carries the removed `rearm_hysteresis` key. Unknown keys
        # must be IGNORED, not fail the block, so the loader stays compatible.
        cfg = load_cfx_sweep_config(self._write(
            {"enabled": True, "bloom_threshold_norm": 0.642, "rearm_hysteresis": 0.05}
        ))
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.bloom_threshold_norm, 0.642)
        self.assertFalse(hasattr(cfg, "rearm_hysteresis"))  # the field is gone for good

    def test_drain_ms_out_of_range_disabled(self) -> None:
        for bad in ({"drain_ms": 0.0}, {"drain_ms": -1.0}):
            block = {"enabled": True, **bad}
            self.assertFalse(load_cfx_sweep_config(self._write(block)).enabled, msg=str(bad))


if __name__ == "__main__":
    unittest.main()
