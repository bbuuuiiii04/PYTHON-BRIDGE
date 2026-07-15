"""Candidate contracts for the Phase-0 pilot (spec B4).

Five methods, no learned model anywhere:
- ``current_f2_790c625``       baseline A  — read-only F2 mapping
- ``development_majority_v1``  baseline B  — exact majority, genuine axis only
- ``v4_exact_retrieval_v1``    candidate C — scaled-Euclidean k=3-lineage retrieval
- ``hardness_v0_all_markers_v1`` / ``approach_v0_diagnostic_v1`` — diagnostics
  (never in integrated PASS).

All predictors take only a ``FrozenFeatureRow`` (or family descriptor) plus
eligible development rows and return a deterministic ``PredictionRow``: permuting
the neighbour order never changes the output hash (test D5).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from .canonical import sha256_hex
from .firewall import ALLOWLIST, EligibleDevelopmentRow, FrozenFeatureRow
from .schemas import SCHEMA_VERSION, PredictionRow

BASELINE_A = "current_f2_790c625"
BASELINE_B = "development_majority_v1"
CANDIDATE_C = "v4_exact_retrieval_v1"
DIAG_HARDNESS = "hardness_v0_all_markers_v1"
DIAG_APPROACH = "approach_v0_diagnostic_v1"

_TIER_ORD = {"T1": 1, "T2": 2, "T3": 3}
_ORD_TIER = {1: "T1", 2: "T2", 3: "T3"}


# --- numpy-backed statistics (method="linear" percentile, deterministic) ------
def _np():
    import numpy as np
    return np


def _median(values) -> float:
    return float(_np().median(_np().asarray(values, dtype=float)))


def _mad(values) -> float:
    a = _np().asarray(values, dtype=float)
    return float(_np().median(_np().abs(a - _np().median(a))))


def _percentile_linear(values, q) -> float:
    if not values:
        return math.inf
    return float(_np().percentile(_np().asarray(values, dtype=float), q, method="linear"))


# --- scaler (spec B4 candidate C) --------------------------------------------
@dataclass(frozen=True)
class ScalerStats:
    medians: dict
    mads: dict
    retained: tuple
    retained_field_hash: str
    ood_threshold: float
    scaler_population_hash: str
    allowlist: tuple

    def scale(self, features: dict) -> list:
        return [(features[k] - self.medians[k]) / self.mads[k] for k in self.retained]


def _euclid(a, b) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def fit_scaler(population_rows, allowlist=ALLOWLIST) -> ScalerStats:
    """Frozen per-field median centering + MAD scaling over the scaler population.

    Zero-MAD fields are dropped and the retained list is hashed (spec B4). The OOD
    threshold is the leave-one-lineage-out nearest-distance 95th percentile.
    """
    vectors = [r.features for r in population_rows]
    medians = {k: _median([v[k] for v in vectors]) for k in allowlist}
    mads = {k: _mad([v[k] for v in vectors]) for k in allowlist}
    retained = tuple(k for k in allowlist if mads[k] > 0.0)
    retained_field_hash = sha256_hex(list(retained))

    # leave-one-lineage-out nearest distances over the population
    scaled = [[(r.features[k] - medians[k]) / mads[k] for k in retained] for r in population_rows]
    lineages = [r.recording_lineage_id for r in population_rows]
    nn = []
    for i in range(len(population_rows)):
        best = math.inf
        for j in range(len(population_rows)):
            if i == j or lineages[i] == lineages[j]:
                continue
            best = min(best, _euclid(scaled[i], scaled[j]))
        if best != math.inf:
            nn.append(best)
    ood_threshold = _percentile_linear(nn, 95.0) if nn else math.inf

    pop_hash = sha256_hex(sorted([r.track_instance_id, r.marker_beat,
                                  [r.features[k] for k in allowlist]] for r in population_rows))
    return ScalerStats(medians, mads, retained, retained_field_hash, ood_threshold,
                       pop_hash, tuple(allowlist))


# --- generic retrieval core ---------------------------------------------------
def _retrieve(query_features, dev_items, scaler, *, query_lineage, query_dup, k=3):
    """Return (n_eligible_lineages, top_k_items, nearest_distance).

    ``dev_items`` need ``.features/.recording_lineage_id/.audio_duplicate_group/
    .track_instance_id/.marker_beat``. Excludes the query's lineage + dup group,
    keeps the nearest row per lineage, takes the k nearest lineages. Tie-break is
    (distance, track_instance_id, marker_beat) — order-independent (D5).
    """
    qv = scaler.scale(query_features)
    by_lin = {}
    for r in dev_items:
        if r.recording_lineage_id == query_lineage or r.audio_duplicate_group == query_dup:
            continue
        d = _euclid(qv, scaler.scale(r.features))
        cand = (d, r.track_instance_id, r.marker_beat)
        cur = by_lin.get(r.recording_lineage_id)
        if cur is None or cand < (cur[0], cur[1], cur[2]):
            by_lin[r.recording_lineage_id] = (d, r.track_instance_id, r.marker_beat, r)
    ranked = sorted(by_lin.values(), key=lambda t: (t[0], t[1], t[2]))
    top = ranked[:k]
    nearest = top[0][0] if top else math.inf
    return len(by_lin), top, nearest


def _pred(method, axis, target_id, *, prediction, abstained, reasons,
          eligible=(), excluded=(), distances=(), raw_score=None, scaler=None,
          manifest_hash="", input_hash="", pilot_seed=""):
    return PredictionRow(
        schema_version=SCHEMA_VERSION, pilot_seed=pilot_seed, method_version=method, axis=axis,
        target_id=target_id, manifest_hash=manifest_hash, input_hash=input_hash,
        scaler_population_hash=(scaler.scaler_population_hash if scaler else ""),
        eligible_neighbour_ids=list(eligible), excluded_neighbour_ids=list(excluded),
        distances=[float(d) for d in distances], prediction=prediction, abstained=abstained,
        raw_score=raw_score, reason_codes=list(reasons), error_state=None,
    )


def abstain(method, axis, target_id, reasons, *, pilot_seed="", manifest_hash="", input_hash=""):
    """Named abstention PredictionRow for a build_query_row reason list (spec B4/B10)."""
    return _pred(method, axis, target_id, prediction=None, abstained=True, reasons=list(reasons),
                 pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash)


def _coverage_ok(frozen_row) -> bool:
    return frozen_row.coverage >= 16.0


# --- candidate C: retrieval ---------------------------------------------------
def predict_retrieval_genuine(frozen_row, dev_rows, scaler, target_id, *,
                              pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    def P(**kw):
        return _pred(CANDIDATE_C, "genuine", target_id, scaler=scaler,
                     pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash, **kw)
    if not _coverage_ok(frozen_row):
        return P(prediction=None, abstained=True, reasons=["coverage_lt_16"])
    if not scaler.retained:
        return P(prediction=None, abstained=True, reasons=["zero_retained_fields"])
    dev = [r for r in dev_rows if "genuine" in r.targets]
    n_lin, top, nearest = _retrieve(frozen_row.features, dev, scaler,
                                    query_lineage=frozen_row.query_lineage_id,
                                    query_dup=frozen_row.query_duplicate_group)
    if n_lin < 3:
        return P(prediction=None, abstained=True, reasons=["lt_3_eligible_lineages"])
    if nearest > scaler.ood_threshold:
        return P(prediction=None, abstained=True, reasons=["ood"], distances=[nearest])
    votes = Counter(r.targets["genuine"] for (_, _, _, r) in top)
    ordered = votes.most_common()
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return P(prediction=None, abstained=True, reasons=["vote_tie"])
    pred = ordered[0][0]
    return P(prediction=pred, abstained=False, reasons=[],
             eligible=[r.track_instance_id for (_, _, _, r) in top],
             distances=[d for (d, _, _, _) in top], raw_score=ordered[0][1] / len(top))


def predict_retrieval_hardness(frozen_row, dev_rows, scaler, target_id, anchor_tier, *,
                               pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    def P(**kw):
        return _pred(CANDIDATE_C, "hardness", target_id, scaler=scaler,
                     pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash, **kw)
    if not _coverage_ok(frozen_row):
        return P(prediction=None, abstained=True, reasons=["coverage_lt_16"])
    if anchor_tier not in _TIER_ORD:
        return P(prediction=None, abstained=True, reasons=["missing_anchor_tier"])
    if not scaler.retained:
        return P(prediction=None, abstained=True, reasons=["zero_retained_fields"])
    dev = [r for r in dev_rows if "hardness" in r.targets]
    n_lin, top, nearest = _retrieve(frozen_row.features, dev, scaler,
                                    query_lineage=frozen_row.query_lineage_id,
                                    query_dup=frozen_row.query_duplicate_group)
    if n_lin < 3:
        return P(prediction=None, abstained=True, reasons=["lt_3_eligible_lineages"])
    if nearest > scaler.ood_threshold:
        return P(prediction=None, abstained=True, reasons=["ood"], distances=[nearest])
    ords = sorted(_TIER_ORD[r.targets["hardness"]] for (_, _, _, r) in top)
    median_ord = ords[len(ords) // 2]  # k=3 -> middle
    pred = _pair_label(median_ord, _TIER_ORD[anchor_tier])
    return P(prediction=pred, abstained=False, reasons=[],
             eligible=[r.track_instance_id for (_, _, _, r) in top],
             distances=[d for (d, _, _, _) in top], raw_score=float(median_ord))


def _pair_label(pred_ord, anchor_ord) -> str:
    if pred_ord > anchor_ord:
        return "harder"
    if pred_ord < anchor_ord:
        return "softer"
    return "tied"


def predict_retrieval_family(query_desc, dev_descs, scaler, target_id, *,
                             pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    """Family retrieval over per-lineage montage descriptors (median+IQR)."""
    def P(**kw):
        return _pred(CANDIDATE_C, "family", target_id, scaler=scaler,
                     pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash, **kw)
    if not scaler.retained:
        return P(prediction=None, abstained=True, reasons=["zero_retained_fields"])
    n_lin, top, nearest = _retrieve(query_desc.features, dev_descs, scaler,
                                    query_lineage=query_desc.recording_lineage_id,
                                    query_dup=query_desc.audio_duplicate_group)
    if n_lin < 3:
        return P(prediction=None, abstained=True, reasons=["lt_3_eligible_lineages"])
    if nearest > scaler.ood_threshold:
        return P(prediction=None, abstained=True, reasons=["ood"], distances=[nearest])
    votes = Counter(r.targets["family"] for (_, _, _, r) in top)
    ordered = votes.most_common()
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return P(prediction=None, abstained=True, reasons=["vote_tie"])
    return P(prediction=ordered[0][0], abstained=False, reasons=[],
             eligible=[r.track_instance_id for (_, _, _, r) in top],
             distances=[d for (d, _, _, _) in top])


def montage_descriptor_features(row_a: dict, row_b: dict, allowlist=ALLOWLIST) -> dict:
    """median + IQR over exactly the two montage rows per lineage (spec B4)."""
    out = {}
    for k in allowlist:
        pair = sorted((float(row_a[k]), float(row_b[k])))
        out[k + "__med"] = (pair[0] + pair[1]) / 2.0
        out[k + "__iqr"] = pair[1] - pair[0]
    return out


FAMILY_ALLOWLIST = tuple(k + s for k in ALLOWLIST for s in ("__med", "__iqr"))


# --- baseline A: read-only F2 mapping ----------------------------------------
def predict_baseline_a_family(target_id, plan_family_a, plan_family_b, *,
                              pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    """Two-moment family from F2 (spec B4): NEUTRAL->none, both match->family, differ->mixed."""
    prov = dict(pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash)
    if plan_family_a is None or plan_family_b is None:
        return _pred(BASELINE_A, "family", target_id, prediction=None, abstained=True,
                     reasons=["f2_plan_missing"], **prov)
    fa = "none" if plan_family_a == "NEUTRAL" else plan_family_a
    fb = "none" if plan_family_b == "NEUTRAL" else plan_family_b
    pred = fa if fa == fb else "mixed"
    return _pred(BASELINE_A, "family", target_id, prediction=pred, abstained=False, reasons=[], **prov)


def predict_baseline_a_hardness(target_id, marker_tier, anchor_tier, *,
                                pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    prov = dict(pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash)
    if marker_tier not in _TIER_ORD or anchor_tier not in _TIER_ORD:
        return _pred(BASELINE_A, "hardness", target_id, prediction=None, abstained=True,
                     reasons=["missing_tier"], **prov)
    return _pred(BASELINE_A, "hardness", target_id,
                 prediction=_pair_label(_TIER_ORD[marker_tier], _TIER_ORD[anchor_tier]),
                 abstained=False, reasons=[], **prov)


def predict_baseline_a_genuine(target_id, *, pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    """F2 has no genuine-marker classifier; it abstains (spec B4)."""
    return _pred(BASELINE_A, "genuine", target_id, prediction=None, abstained=True,
                 reasons=["f2_abstains_genuine"],
                 pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash)


# --- baseline B: development majority (genuine axis only) ---------------------
def predict_baseline_b_genuine(target_id, dev_rows, *,
                               pilot_seed="", manifest_hash="", input_hash="") -> PredictionRow:
    prov = dict(pilot_seed=pilot_seed, manifest_hash=manifest_hash, input_hash=input_hash)
    labels = [r.targets["genuine"] for r in dev_rows if "genuine" in r.targets]
    votes = Counter(labels)
    ordered = votes.most_common()
    if not ordered:
        return _pred(BASELINE_B, "genuine", target_id, prediction=None, abstained=True,
                     reasons=["no_comparable_targets"], **prov)
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return _pred(BASELINE_B, "genuine", target_id, prediction=None, abstained=True,
                     reasons=["dev_majority_tie"], **prov)
    return _pred(BASELINE_B, "genuine", target_id, prediction=ordered[0][0], abstained=False,
                 reasons=[], raw_score=ordered[0][1] / len(labels), **prov)


# --- diagnostics (never in integrated PASS) ----------------------------------
def _ensure_runtime_on_path():
    """Put the repo package root on sys.path so ``rb_ss_bridge_v2`` imports resolve.

    Mirrors the offline-tool precedent (tools/hardness_ablation.py). Called lazily
    from the diagnostics only; Phase-0 unit tests never touch this path.
    """
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[3])  # -> dir containing rb_ss_bridge_v2/
    if root not in sys.path:
        sys.path.insert(0, root)


def diagnostic_hardness_v0(v4, marker_beat, baseline, *, reducer="max"):
    """Frozen hardness_v0 at one marker (spec B4). Returns a plain dict or None.

    ``baseline`` is a ``hardness_v0.TrackBaseline`` (built once per track via
    ``hardness_v0.track_baseline``). ``None`` on missing baseline / malformed v4 /
    out-of-range marker — a named abstention, never a phantom T3.
    """
    _ensure_runtime_on_path()
    from rb_ss_bridge_v2 import hardness_v0  # read-only, offline; lazy
    res = hardness_v0.hardness_result(v4, marker_beat, baseline, reducer=reducer)
    if res is None:
        return None
    return {
        "H": float(res.h), "t3_fire": bool(res.t3), "winning_path": res.winning_path,
        "winning_offset": res.winning_offset,
        "marker_shift_range": list(res.marker_shift_range),
    }


def diagnostic_approach_v0(v4, marker_beat, *, approach_len, **kw):
    """Raw four-view approach descriptors + ±2-beat robustness (spec B4). No class.

    Thin pass-through to ``approach_features_v0.approach_features``; the caller
    supplies the pre-drop approach window (``approach_len`` here). Returns the raw
    ``ApproachFeatures`` dataclass — the diagnostic emits descriptors only.
    """
    _ensure_runtime_on_path()
    from rb_ss_bridge_v2 import approach_features_v0  # read-only, offline; lazy
    return approach_features_v0.approach_features(v4, marker_beat, approach_len=approach_len, **kw)
