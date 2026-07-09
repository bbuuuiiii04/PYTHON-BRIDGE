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


# ── Part D.3 — envelope unit tests ───────────────────────────────────────────
class EnvelopeTests(unittest.TestCase):
    def test_ccw_and_neutral_are_exactly_neutral(self) -> None:
        # The operator's final ruling: knob at/below 12 o'clock does NOTHING.
        for knob in (0.0, 0.3, 0.49, 0.5):
            mix, dim = cfx_sweep_envelope(knob, 0.0, 0.1, CFG)
            self.assertEqual((mix, dim), (0.0, 1.0), msg=f"knob={knob}")

    def test_engage_ramps_mix_to_one_at_flood_ramp_ms(self) -> None:
        # dt == flood_ramp_ms (in seconds) drives a full 0->1 flood in one step.
        mix, _ = cfx_sweep_envelope(0.9, 0.0, CFG.flood_ramp_ms / 1000.0, CFG)
        self.assertEqual(mix, 1.0)
        half, _ = cfx_sweep_envelope(0.9, 0.0, CFG.flood_ramp_ms / 2000.0, CFG)
        self.assertAlmostEqual(half, 0.5, places=6)

    def test_below_threshold_dim_is_exactly_one(self) -> None:
        # Engaged but below the bloom threshold: flood in, but no dimming yet.
        mix, dim = cfx_sweep_envelope(0.70, 1.0, 1.0, CFG)  # 0.70 < thr 0.75
        self.assertEqual(dim, 1.0)
        self.assertEqual(mix, 1.0)

    def test_above_threshold_dim_monotonic_and_hits_floor(self) -> None:
        thr = CFG.bloom_threshold_norm
        prev = None
        for knob in [thr, 0.80, 0.85, 0.90, 0.95, 1.0]:
            _, dim = cfx_sweep_envelope(knob, 1.0, 1.0, CFG)
            if prev is not None:
                self.assertLessEqual(dim, prev + 1e-9, msg=f"knob={knob} not monotonic")
            prev = dim
        _, dim_top = cfx_sweep_envelope(1.0, 1.0, 1.0, CFG)
        self.assertAlmostEqual(dim_top, CFG.dim_floor, places=6)

    def test_dim_refills_on_the_way_back_down(self) -> None:
        _, dim_high = cfx_sweep_envelope(0.95, 1.0, 1.0, CFG)
        _, dim_low = cfx_sweep_envelope(0.80, 1.0, 1.0, CFG)
        self.assertLess(dim_high, dim_low)  # lower knob -> brighter (refills)

    def test_boundary_continuity_at_threshold_no_jump(self) -> None:
        thr = CFG.bloom_threshold_norm
        _, dim_at = cfx_sweep_envelope(thr, 1.0, 1.0, CFG)
        _, dim_just_above = cfx_sweep_envelope(thr + 1e-6, 1.0, 1.0, CFG)
        self.assertEqual(dim_at, 1.0)
        self.assertAlmostEqual(dim_just_above, 1.0, places=4)

    def test_release_ramps_mix_to_zero_at_release_ramp_ms(self) -> None:
        mix, _ = cfx_sweep_envelope(0.4, 1.0, CFG.release_ramp_ms / 1000.0, CFG)
        self.assertEqual(mix, 0.0)

    def test_dt_zero_holds_mix_and_is_safe(self) -> None:
        mix, dim = cfx_sweep_envelope(0.9, 0.3, 0.0, CFG)
        self.assertEqual(mix, 0.3)  # no ramp with dt=0
        self.assertTrue(0.0 <= dim <= 1.0)

    def test_out_of_range_and_nan_knob_are_safe(self) -> None:
        for knob in (-5.0, 5.0, float("nan"), float("inf")):
            mix, dim = cfx_sweep_envelope(knob, 0.5, 0.1, CFG)
            self.assertTrue(0.0 <= mix <= 1.0, msg=f"knob={knob} mix={mix}")
            self.assertTrue(CFG.dim_floor - 1e-9 <= dim <= 1.0, msg=f"knob={knob} dim={dim}")

    def test_jitter_at_exactly_half_is_neutral(self) -> None:
        # 0.5 is NOT engaged (deadband > 0): jitter at 12 o'clock does nothing.
        mix, dim = cfx_sweep_envelope(0.5, 0.0, 0.1, CFG)
        self.assertEqual((mix, dim), (0.0, 1.0))


# ── Part D.4 — dispatch gating + anchor provider ─────────────────────────────
def _reading(deck: int, filter_norm: float, *, valid: bool = True, reason: str = "ok") -> CfxDeckReading:
    return CfxDeckReading(
        deck=deck, filter_norm=filter_norm, selected_effect_id=0,
        unit_channel=deck - 1, valid=valid, reason=reason,
    )


def _snapshot(readings, updated_at: float) -> CfxFilterSnapshot:
    return CfxFilterSnapshot(valid=True, deck=readings, updated_at=updated_at, reason="ok")


def _sm_ns(cfg, snapshot, *, blackout=False, breakdown=False, darkest=(10, 0, 40)):
    return SimpleNamespace(
        _cfx_sweep_config=cfg,
        _cfx_snapshot=snapshot,
        _led_blackout_active=(lambda: blackout),
        _os=SimpleNamespace(breakdown_active=breakdown),
        _led_color_engine=SimpleNamespace(v2_darkest_rgb=(lambda: darkest)),
        _led_cfx_prev_mix=0.0,
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
        self.assertIsNone(_compute(_sm_ns(CFG, snap), 1, now))       # deck 1 inert
        self.assertIsNotNone(_compute(_sm_ns(CFG, snap), 2, now))    # deck 2 floods


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


if __name__ == "__main__":
    unittest.main()
