"""Synthetic, non-circular tests for the falsifiable T7d phase-contract oracle.

These tests deliberately do NOT import ground truth from the module under
test. Observed wire frames are generated from an independent re-derivation of
the phase math (``_gen_phase`` / ``_state_at``) so that a passing fit is a real
recovery proof, not a tautology. The oracle must:

  * recover the true ticks/beat (both a true-600 and a true-non-600 case),
  * explicitly test and be able to *reject* 600,
  * pin origin/reset/continue/snap from recorded-state hypotheses only,
  * count blackout/zero frames as mismatches (never free skips),
  * return INCOMPLETE on insufficient discriminating transitions or gaps,
  * return FAIL on ambiguity (>=2 candidates reproduce the capture).
"""
from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

_MOD = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "ssfmt"
    / "re"
    / "t7d_phase_contract.py"
)
_spec = importlib.util.spec_from_file_location("t7d_phase_contract", _MOD)
t7d = importlib.util.module_from_spec(_spec)
sys.modules["t7d_phase_contract"] = t7d
_spec.loader.exec_module(t7d)

CYCLE = 19_200


# --- independent ground-truth generators (NOT from the module under test) ----


def _gen_phase(beat, origin, tpb, quant, cycle=CYCLE):
    x = (beat - origin) * tpb
    if quant == "floor":
        q = math.floor(x)
    elif quant == "trunc":
        q = math.trunc(x)
    elif quant == "round":
        q = math.floor(x + 0.5)
    else:  # pragma: no cover - test guard
        raise ValueError(quant)
    return q % cycle


def _state_at(phase, events, cycle=CYCLE):
    chosen = events[-1]["state"]  # steady-loop wrap: before first tick -> last
    for ev in events:
        if ev["tick"] <= phase:
            chosen = ev["state"]
        else:
            break
    return chosen


def _events(transitions):
    return [
        {"tick": int(t), "state": tuple(int(v) for v in s)}
        for t, s in sorted(transitions)
    ]


def _dense_events():
    """Six distinct, unevenly spaced states across the 19,200-tick cycle."""
    base = [0] * 19
    out = []
    spots = [0, 1700, 5200, 9100, 13400, 16800]
    for i, tick in enumerate(spots):
        st = list(base)
        st[0] = 10 + i * 7
        st[6] = (i * 53) % 256
        st[14] = (200 - i * 11) % 256
        out.append((tick, tuple(st)))
    return _events(out)


def _samples(beats, origin, tpb, quant, events, bpm, cycle=CYCLE):
    spb = 60.0 / bpm
    rows = []
    for b in beats:
        phase = _gen_phase(b, origin, tpb, quant, cycle)
        rows.append({"t": b * spb, "beat": b, "state": _state_at(phase, events, cycle)})
    return rows


def _frange(start, stop, step):
    n = int(round((stop - start) / step))
    return [round(start + i * step, 6) for i in range(n + 1)]


class PhaseTickTests(unittest.TestCase):
    def test_six_hundred_maps_thirty_two_beats_to_one_cycle(self):
        # 600 ticks/beat * 32 beats == 19,200 == exactly one cycle wrap to 0.
        self.assertEqual(t7d.phase_tick_for_beat(32.0, 0.0, 600, "floor"), 0)
        self.assertEqual(t7d.phase_tick_for_beat(16.0, 0.0, 600, "floor"), 9600)

    def test_floor_and_trunc_differ_for_fractional_negative_offsets(self):
        # raw = -0.001 * 600 = -0.6 (fractional, negative pre-roll):
        # floor(-0.6) = -1 -> wraps to 19199; trunc(-0.6) = 0.
        floor = t7d.phase_tick_for_beat(-0.001, 0.0, 600, "floor")
        trunc = t7d.phase_tick_for_beat(-0.001, 0.0, 600, "trunc")
        self.assertEqual(floor, (-1) % CYCLE)
        self.assertEqual(trunc, 0)
        self.assertNotEqual(floor, trunc)


class PredictedFrameTests(unittest.TestCase):
    def test_before_first_tick_uses_last_event_state(self):
        # First event tick is 1700, so phase 10 is in the steady-loop wrap region.
        events = _events(
            [(1700, (1,) + (0,) * 18), (9100, (2,) + (0,) * 18), (16800, (3,) + (0,) * 18)]
        )
        self.assertEqual(t7d.predicted_frame_at(10, events), events[-1]["state"])

    def test_after_tick_uses_that_event_state(self):
        events = _events(
            [(1700, (1,) + (0,) * 18), (9100, (2,) + (0,) * 18), (16800, (3,) + (0,) * 18)]
        )
        self.assertEqual(t7d.predicted_frame_at(9200, events), events[1]["state"])


class FitTrue600Tests(unittest.TestCase):
    def test_recovers_600_and_rejects_alternatives(self):
        events = _dense_events()
        origin = 4.0
        beats = _frange(4.0, 40.0, 0.05)  # dense fractional sampling breaks aliasing
        samples = _samples(beats, origin, 600, "floor", events, bpm=128.0)
        hyp = {
            # Scale-recovery is isolated from quantizer determination: a single
            # quantizer candidate here (the quantizer is pinned by a separate
            # boundary-straddling test).
            "ticks_per_beat": [480, 600, 720, 19800],
            "quantizers": ["floor"],
            "origins": [{"beat": 4.0, "kind": "arm_sync"}, {"beat": 0.0, "kind": "global"}],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.PASS)
        self.assertEqual(result["ticks_per_beat"], 600)
        self.assertEqual(result["origin"]["kind"], "arm_sync")
        self.assertTrue(result["six_hundred_passed"])


class FitTrueNon600Tests(unittest.TestCase):
    def test_recovers_480_and_explicitly_rejects_600(self):
        events = _dense_events()
        origin = 0.0
        beats = _frange(0.0, 48.0, 0.05)
        samples = _samples(beats, origin, 480, "floor", events, bpm=120.0)
        hyp = {
            "ticks_per_beat": [400, 480, 600, 720],
            "quantizers": ["floor"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.PASS)
        self.assertEqual(result["ticks_per_beat"], 480)
        self.assertFalse(result["six_hundred_passed"])  # 600 must be rejected


class FitTwoBpmRejectsWallClockTests(unittest.TestCase):
    def test_beat_domain_fit_holds_across_two_bpms(self):
        # Same beat-domain truth at two BPMs; a wall-clock (rate=bpm*10) fit
        # cannot reproduce both, but the true beat-domain tpb does.
        events = _dense_events()
        origin = 0.0
        s1 = _samples(_frange(0, 40, 0.05), origin, 600, "floor", events, bpm=120.0)
        s2 = _samples(_frange(0, 40, 0.05), origin, 600, "floor", events, bpm=150.0)
        hyp = {
            "ticks_per_beat": [480, 600, 720],
            "quantizers": ["floor"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
        }
        r1 = t7d.fit_phase_contract(s1, events, hyp)
        r2 = t7d.fit_phase_contract(s2, events, hyp)
        self.assertEqual(r1["ticks_per_beat"], 600)
        self.assertEqual(r2["ticks_per_beat"], 600)
        self.assertEqual(r1["verdict"], t7d.PASS)
        self.assertEqual(r2["verdict"], t7d.PASS)


class OriginContractTests(unittest.TestCase):
    def test_continuous_origin_selected_over_reset(self):
        # Truth: phase continues from a global origin (no reset at the edge).
        events = _dense_events()
        beats = _frange(10.0, 50.0, 0.05)
        samples = _samples(beats, 0.0, 600, "floor", events, bpm=128.0)
        hyp = {
            "ticks_per_beat": [600],
            "quantizers": ["floor"],
            "origins": [
                {"beat": 0.0, "kind": "continuous_global"},
                {"beat": 10.0, "kind": "reset_at_edge"},
            ],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.PASS)
        self.assertEqual(result["origin"]["kind"], "continuous_global")

    def test_snap_to_phrase_target_origin_selected(self):
        events = _dense_events()
        # Truth snaps to a phrase target at beat 20 (deliberately NOT a multiple
        # of 32 beats from the alternative origin: 20*600=12000 is not a multiple
        # of the 19,200-tick cycle, so the two origins are distinguishable).
        beats = _frange(21.0, 61.0, 0.05)
        samples = _samples(beats, 20.0, 600, "floor", events, bpm=128.0)
        hyp = {
            "ticks_per_beat": [600],
            "quantizers": ["floor"],
            "origins": [
                {"beat": 20.0, "kind": "phrase_anchor_snap"},
                {"beat": 0.0, "kind": "continuous_global"},
            ],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.PASS)
        self.assertEqual(result["origin"]["kind"], "phrase_anchor_snap")


class IncompleteEvidenceTests(unittest.TestCase):
    def test_too_few_discriminating_transitions_is_incomplete(self):
        events = _events([(0, [1] + [0] * 18), (9600, [2] + [0] * 18)])  # 1 transition
        beats = _frange(0.0, 40.0, 0.05)
        samples = _samples(beats, 0.0, 600, "floor", events, bpm=128.0)
        hyp = {
            "ticks_per_beat": [480, 600, 720],
            "quantizers": ["floor"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.INCOMPLETE)

    def test_missing_samples_spanning_a_transition_is_incomplete(self):
        events = _dense_events()
        beats = _frange(4.0, 40.0, 0.05)
        samples = _samples(beats, 4.0, 600, "floor", events, bpm=128.0)
        # Drop every sample whose observed state is one of the middle events,
        # erasing discriminating transitions so coverage falls below threshold.
        drop = {events[2]["state"], events[3]["state"], events[4]["state"]}
        sparse = [s for s in samples if s["state"] not in drop]
        hyp = {
            "ticks_per_beat": [480, 600, 720],
            "quantizers": ["floor"],
            "origins": [{"beat": 4.0, "kind": "arm_sync"}],
            "min_discriminating": 5,
        }
        result = t7d.fit_phase_contract(sparse, events, hyp)
        self.assertEqual(result["verdict"], t7d.INCOMPLETE)


class AmbiguityTests(unittest.TestCase):
    def test_integer_beat_aliasing_yields_fail_ambiguous(self):
        # Sample only at integer beats: tpb=600 and tpb=600+CYCLE alias exactly,
        # so the oracle must report ambiguity (FAIL), never silently pick one.
        events = _dense_events()
        beats = [float(b) for b in range(0, 40)]
        samples = _samples(beats, 0.0, 600, "floor", events, bpm=128.0)
        hyp = {
            "ticks_per_beat": [600, 600 + CYCLE],
            "quantizers": ["floor"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
            "min_discriminating": 4,
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.FAIL)
        self.assertGreaterEqual(len(result["passing_candidates"]), 2)


class BlackoutContaminationTests(unittest.TestCase):
    def test_unexplained_zero_frames_are_hard_mismatches(self):
        events = _dense_events()
        beats = _frange(0.0, 40.0, 0.05)
        samples = _samples(beats, 0.0, 600, "floor", events, bpm=128.0)
        zero = tuple([0] * 19)
        # Inject zero/blackout frames far from any transition boundary.
        for idx in (50, 150, 250, 350, 450):
            samples[idx] = dict(samples[idx], state=zero)
        hyp = {
            "ticks_per_beat": [600],
            "quantizers": ["floor"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        # The injected zeros must register as hard mismatches; the true tpb
        # therefore does NOT pass cleanly -> not a PASS verdict.
        self.assertNotEqual(result["verdict"], t7d.PASS)
        self.assertGreaterEqual(result["best_hard_mismatches"], 5)


class QuantizerDeterminationTests(unittest.TestCase):
    def test_floor_distinguished_from_round_by_below_boundary_samples(self):
        # Five evenly discriminating boundaries. Samples placed just BELOW each
        # boundary (raw = T - 0.3) still show the pre-boundary state under floor,
        # but round() crosses up into the post-boundary state -> round mismatches.
        states = [tuple([k] + [0] * 18) for k in range(6)]
        ticks = [0, 50, 150, 250, 350, 450]
        events = _events(list(zip(ticks, states)))
        tpb, origin = 600, 0.0
        raws = []
        for boundary in (50, 150, 250, 350, 450):
            raws.append(boundary - 0.3)  # discriminates floor (pre) vs round (post)
        raws += [float(x) for x in range(0, 500, 7)]  # filler for frame count
        samples = []
        for raw in raws:
            beat = origin + raw / tpb
            samples.append(
                {"t": beat * 0.5, "beat": beat, "state": _state_at(math.floor(raw), events)}
            )
        hyp = {
            "ticks_per_beat": [600],
            "quantizers": ["floor", "round"],
            "origins": [{"beat": 0.0, "kind": "arm_sync"}],
        }
        result = t7d.fit_phase_contract(samples, events, hyp)
        self.assertEqual(result["verdict"], t7d.PASS)
        self.assertEqual(result["quantizer"], "floor")


class CompareWireFramesTests(unittest.TestCase):
    def test_clock_skew_within_tolerance_is_excused(self):
        # Predicted transition at t=1.0; observed shifted by +30ms.
        a = (1,) + (0,) * 18
        b = (2,) + (0,) * 18
        predicted = [(0.95, a), (1.00, b), (1.05, b)]
        observed = [(0.95, a), (1.00, a), (1.05, b)]  # transition lands one frame late
        res = t7d.compare_wire_frames(predicted, observed, timing_tolerance=0.05)
        self.assertEqual(res["hard_mismatches"], 0)
        self.assertGreaterEqual(res["transition_excused"], 1)

    def test_skew_beyond_tolerance_is_hard_mismatch(self):
        a = (1,) + (0,) * 18
        b = (2,) + (0,) * 18
        predicted = [(1.00, b), (1.20, b)]
        observed = [(1.00, a), (1.20, b)]  # 200ms late, tolerance 50ms
        res = t7d.compare_wire_frames(predicted, observed, timing_tolerance=0.05)
        self.assertEqual(res["hard_mismatches"], 1)


if __name__ == "__main__":
    unittest.main()
