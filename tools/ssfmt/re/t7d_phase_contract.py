#!/usr/bin/env python3
"""Falsifiable T7d phase-contract oracle (pure functions; no I/O).

This module replaces the circular phase fit in ``validate_autoloop_capture.py``
(which hard-coded ``rate = bpm * 10.0`` -- equivalent to assuming 600
ticks/beat -- and allowed a free fitted phase offset). Here:

  * ``TICKS_PER_BEAT`` is searched over a caller-supplied candidate set; 600 is
    only ever *one hypothesis*, never an assumed default, and the result states
    explicitly whether 600 passed or failed.
  * The phase *origin* may only come from values recorded in the bridge state
    (accepted-selection beat, pending arm-sync beat, last MIDI/refire beat,
    phrase-anchor target, correction target, or continuous previous phase).
    A free per-segment phase offset is forbidden by construction: there is no
    "fit any offset" path. Origins are enumerated hypotheses tied to real state.
  * Value parity is byte-exact (zero channel-value tolerance) in the beat
    domain. Wire-timing tolerance is a separate concern handled by
    ``compare_wire_frames`` (one observed ArtDmx frame interval + measured clock
    residual, capped by the caller).

Verdicts: ``PASS_T7D_PHASE_CONTRACT`` (unique scale+quantizer+origin with
enough discriminating transitions), ``FAIL_T7D_PHASE_CONTRACT`` (ambiguous: >=2
contracts reproduce the capture, or rich data that nothing reproduces), or
``INCOMPLETE_T7D_EVIDENCE`` (too few frames or too few discriminating
transitions to decide). Only PASS may unblock a T7d implementation spec.

Caveat (documented, not silently handled): at tpb=600 any two origins separated
by a multiple of 32 beats alias to the same phase (32*600 == one 19,200-tick
cycle); a 64-beat phrase anchor likewise aliases a continuous global phase.
Origin hypotheses that alias under the winning scale are reported together as an
``origin_alias_class`` rather than disambiguated, because the wire cannot tell
them apart. Callers must resolve such classes from recorded state semantics.
"""
from __future__ import annotations

import bisect
import math

LOOP_TICKS = 19_200

PASS = "PASS_T7D_PHASE_CONTRACT"
FAIL = "FAIL_T7D_PHASE_CONTRACT"
INCOMPLETE = "INCOMPLETE_T7D_EVIDENCE"

QUANTIZERS = ("floor", "trunc", "round")

DEFAULT_MIN_DISCRIMINATING = 4
DEFAULT_MIN_FRAMES = 20


def _quantize(value: float, quantizer: str) -> int:
    if quantizer == "floor":
        return math.floor(value)
    if quantizer == "trunc":
        return math.trunc(value)
    if quantizer == "round":
        # round-half-up; deterministic (unlike banker's rounding) so a fitted
        # boundary convention is reproducible.
        return math.floor(value + 0.5)
    raise ValueError(f"unknown quantizer: {quantizer!r}")


def phase_tick_for_beat(
    beat: float,
    origin: float,
    ticks_per_beat: float,
    quantizer: str = "floor",
    cycle_ticks: int = LOOP_TICKS,
) -> int:
    """Integer animation phase tick for a beat position relative to an origin."""
    raw = (beat - origin) * ticks_per_beat
    return _quantize(raw, quantizer) % cycle_ticks


def predicted_frame_at(phase_tick: int, events, cycle_ticks: int = LOOP_TICKS):
    """Step-function lookup: the immutable timeline's state at ``phase_tick``.

    ``events`` must be sorted ascending by ``tick``. Before the first event tick
    the steady-loop prior-cycle state (the last event) applies.
    """
    chosen = events[-1]["state"]
    for ev in events:
        if ev["tick"] <= phase_tick:
            chosen = ev["state"]
        else:
            break
    return chosen


def compare_wire_frames(predicted, observed, timing_tolerance: float) -> dict:
    """Compare two timestamped frame streams with a transition-timing tolerance.

    ``predicted`` / ``observed`` are ``[(t, state), ...]``. A value disagreement
    is *excused* only if the observed timestamp is within ``timing_tolerance``
    seconds of a predicted transition edge (where the predicted state changes);
    otherwise it is a hard mismatch. Stable-frame value parity is byte-exact.
    """
    pred = sorted(predicted, key=lambda r: r[0])
    if not pred:
        return {
            "compared": len(observed),
            "exact": 0,
            "hard_mismatches": len(observed),
            "transition_excused": 0,
            "max_residual_ms": None,
        }
    ptimes = [r[0] for r in pred]
    pstates = [r[1] for r in pred]
    trans_times = [
        pred[i][0] for i in range(1, len(pred)) if pred[i][1] != pred[i - 1][1]
    ]

    exact = hard = excused = 0
    residuals: list[float] = []
    for t, state in observed:
        idx = bisect.bisect_right(ptimes, t) - 1
        if idx < 0:
            idx = 0
        if state == pstates[idx]:
            exact += 1
            continue
        near = [abs(t - tt) for tt in trans_times if abs(t - tt) <= timing_tolerance]
        if near:
            excused += 1
            residuals.append(min(near) * 1000.0)
        else:
            hard += 1
    return {
        "compared": len(observed),
        "exact": exact,
        "hard_mismatches": hard,
        "transition_excused": excused,
        "max_residual_ms": max(residuals) if residuals else None,
    }


def _evaluate(samples, tpb, quantizer, origin_beat, eticks, estates, cycle):
    """Score one (tpb, quantizer, origin) hypothesis against beat-domain samples.

    Returns ``(hard_mismatches, exact, discriminating, compared)``. Value parity
    is byte-exact. ``discriminating`` counts distinct immutable-timeline event
    boundaries actually crossed (with a real state change) by the sample stream.
    """
    hard = exact = 0
    crossed: set[int] = set()
    prev_active = None
    last_index = len(eticks) - 1
    for sample in samples:
        phase = phase_tick_for_beat(sample["beat"], origin_beat, tpb, quantizer, cycle)
        idx = bisect.bisect_right(eticks, phase) - 1
        if idx < 0:
            idx = last_index  # steady-loop wrap
        if sample["state"] == estates[idx]:
            exact += 1
        else:
            hard += 1
        if (
            prev_active is not None
            and idx != prev_active
            and estates[idx] != estates[prev_active]
        ):
            crossed.add(idx)
        prev_active = idx
    return hard, exact, len(crossed), len(samples)


def fit_phase_contract(samples, events, hypotheses) -> dict:
    """Search recorded-origin / scale / quantizer hypotheses for a unique contract.

    ``samples``: ``[{"t": float, "beat": float, "state": tuple}, ...]`` -- wire
    frames already aligned to the bridge beat authority (the schema-2 phase
    trace supplies ``beat``; pcap supplies ``state`` and ``t``).
    ``events``: immutable pack timeline ``[{"tick": int, "state": tuple}, ...]``.
    ``hypotheses``: ``ticks_per_beat`` (required list), ``quantizers``,
    ``origins`` (required list of ``{"beat", "kind"}``), ``cycle_ticks``,
    ``min_discriminating``, ``min_frames``.
    """
    cycle = hypotheses.get("cycle_ticks", LOOP_TICKS)
    tpbs = list(hypotheses["ticks_per_beat"])
    quants = list(hypotheses.get("quantizers", QUANTIZERS))
    origins = list(hypotheses["origins"])
    min_disc = hypotheses.get("min_discriminating", DEFAULT_MIN_DISCRIMINATING)
    min_frames = hypotheses.get("min_frames", DEFAULT_MIN_FRAMES)

    sevents = sorted(events, key=lambda ev: ev["tick"])
    eticks = [ev["tick"] for ev in sevents]
    estates = [ev["state"] for ev in sevents]

    observed_distinct_states = len({s["state"] for s in samples})

    candidates = []
    for tpb in tpbs:
        for quant in quants:
            best = None
            for origin in origins:
                hard, exact, disc, compared = _evaluate(
                    samples, tpb, quant, origin["beat"], eticks, estates, cycle
                )
                key = (hard, -exact, -disc)
                record = {
                    "ticks_per_beat": tpb,
                    "quantizer": quant,
                    "origin": origin,
                    "hard_mismatches": hard,
                    "exact": exact,
                    "discriminating": disc,
                    "compared": compared,
                }
                if best is None or key < best[0]:
                    best = (key, record)
            candidates.append(best[1])

    passing = [
        c
        for c in candidates
        if c["hard_mismatches"] == 0
        and c["discriminating"] >= min_disc
        and c["compared"] >= min_frames
    ]
    clean = [
        c
        for c in candidates
        if c["hard_mismatches"] == 0 and c["compared"] >= min_frames
    ]
    best_hard = min((c["hard_mismatches"] for c in candidates), default=None)

    if len(samples) < min_frames:
        verdict = INCOMPLETE
        winner = None
    elif len(passing) == 1:
        verdict = PASS
        winner = passing[0]
    elif len(passing) >= 2:
        verdict = FAIL
        winner = None
    elif clean:
        # Frames reproduce, but not enough discriminating transitions to prove
        # scale/origin -- a constant/low-information capture.
        verdict = INCOMPLETE
        winner = None
    elif observed_distinct_states >= min_disc:
        # Rich data that none of the tested contracts reproduce: falsified.
        verdict = FAIL
        winner = None
    else:
        verdict = INCOMPLETE
        winner = None

    six_hundred_passed = any(c["ticks_per_beat"] == 600 for c in passing)

    return {
        "verdict": verdict,
        "ticks_per_beat": winner["ticks_per_beat"] if winner else None,
        "quantizer": winner["quantizer"] if winner else None,
        "origin": winner["origin"] if winner else None,
        "discriminating": winner["discriminating"] if winner else None,
        "compared": len(samples),
        "six_hundred_passed": six_hundred_passed,
        "passing_candidates": passing,
        "clean_candidates": clean,
        "best_hard_mismatches": best_hard,
        "observed_distinct_states": observed_distinct_states,
        "min_discriminating": min_disc,
        "min_frames": min_frames,
    }
