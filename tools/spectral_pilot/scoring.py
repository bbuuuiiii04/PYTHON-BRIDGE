"""Metrics, dual-ledger reconciliation, repeatability, stability (spec B8).

Pure functions that turn frozen prediction + response data into the exact numbers
``verdict.compute_verdict`` consumes. Scoring rule (B8): ``correct`` is 1 only on
an exact answer match, else 0; an abstention scores 0 and is counted separately;
a paired lineage is win/loss/tie by the sign of its summed row deltas.
"""
from __future__ import annotations

from datetime import datetime

# decisive family answers that can contradict each other (B8)
_DECISIVE_FAMILY = frozenset({"WALL", "COMET", "HOUSE", "mixed", "none"})
_MARKER_OPPOSITE = {("genuine", "not_genuine"), ("not_genuine", "genuine")}
_HARDNESS_OPPOSITE = {("harder", "softer"), ("softer", "harder")}

FOUR_STATES = frozenset(
    {"predicted", "abstained_with_reason", "excluded_with_prespecified_reason", "hard_failure"}
)


class ReconcileError(ValueError):
    """A row that lands in zero or multiple states, or a ledger cross-check miss."""


def prediction_state(row) -> str:
    if getattr(row, "error_state", None):
        return "hard_failure"
    if row.abstained:
        return "abstained_with_reason"
    return "predicted"


def reconcile_axis(frozen_ids, prediction_rows, excluded_ids, human_states) -> dict:
    """Every frozen target lands in exactly one prediction state; predicted rows
    must carry a human state (spec B8). Raises ``ReconcileError`` otherwise.

    ``human_states``: target_id -> "answered" | "human_unavailable" (or a truth
    value; only its presence is checked here).
    """
    pred = {r.target_id: r for r in prediction_rows}
    excluded = set(excluded_ids)
    states = {}
    for tid in frozen_ids:
        in_pred, in_exc = tid in pred, tid in excluded
        if in_pred and in_exc:
            raise ReconcileError(f"{tid} both predicted and excluded")
        if in_exc:
            states[tid] = "excluded_with_prespecified_reason"
        elif in_pred:
            states[tid] = prediction_state(pred[tid])
        else:
            raise ReconcileError(f"{tid} has no prediction state")
        if states[tid] == "predicted" and human_states.get(tid) is None:
            raise ReconcileError(f"predicted row {tid} has no human state")
    # reverse direction: a human-answered target with neither prediction nor exclusion
    for tid, hs in human_states.items():
        if hs == "answered" and tid not in states:
            raise ReconcileError(f"answered target {tid} absent from prediction manifest")
    return states


def state_counts(states: dict) -> dict:
    out = {s: 0 for s in FOUR_STATES}
    for s in states.values():
        out[s] += 1
    return out


def paired_scoring(rows) -> dict:
    """Paired candidate-vs-baseline scoring over decisive-truth rows (spec B8).

    ``rows``: dicts ``{lineage, truth, candidate_pred, baseline_pred}``. ``truth``
    is the decisive human answer (caller drops unsure / marker-wrong). A ``None``
    prediction is an abstention (scores 0, counted separately).
    """
    by_lin = {}
    abstentions = 0
    correct_delta = 0
    for r in rows:
        cc = 1 if r["candidate_pred"] == r["truth"] else 0
        cb = 1 if r["baseline_pred"] == r["truth"] else 0
        if r["candidate_pred"] is None:
            abstentions += 1
        correct_delta += cc - cb
        by_lin[r["lineage"]] = by_lin.get(r["lineage"], 0) + (cc - cb)
    wins = sum(1 for v in by_lin.values() if v > 0)
    losses = sum(1 for v in by_lin.values() if v < 0)
    return {
        "comparable_calls": len(rows), "comparable_lineages": len(by_lin),
        "correct_delta": correct_delta, "lineage_win_margin": wins - losses,
        "candidate_abstentions": abstentions,
    }


def repeatability_counters(repeats, *, re_exposed_card_ids=()) -> dict:
    """Hidden-repeat consistency (spec B8). ``repeats``: ``{axis, answers:[a,b]}``,
    optionally carrying ``source_card_id`` / ``instance_card_id``.

    Direct contradictions only: genuine<->not_genuine, harder<->softer, any change
    between two decisive family answers. tied / marker-wrong / unsure transitions
    are reported, not opposites (they never count as contradictions here).

    A repeat pair whose source or instance card was ``re_exposed`` on resume (played
    without a commit before an interrupt, per B6/ResumeState) is excluded from the
    gate-2 counters — the interrupt makes that pair non-comparable.
    """
    re_exposed = set(re_exposed_card_ids)
    counts = {"marker": 0, "hardness": 0, "family": 0}
    contra = {"marker": 0, "hardness": 0, "family": 0}
    for rp in repeats:
        if re_exposed and (rp.get("source_card_id") in re_exposed
                           or rp.get("instance_card_id") in re_exposed):
            continue
        ax = rp["axis"]
        a, b = rp["answers"]
        counts[ax] += 1
        if ax == "family":
            if a in _DECISIVE_FAMILY and b in _DECISIVE_FAMILY and a != b:
                contra[ax] += 1
        elif ax == "marker":
            if (a, b) in _MARKER_OPPOSITE:
                contra[ax] += 1
        elif ax == "hardness":
            if (a, b) in _HARDNESS_OPPOSITE:
                contra[ax] += 1
    return {
        "marker_repeats": counts["marker"], "hardness_repeats": counts["hardness"],
        "family_repeats": counts["family"], "marker_contradictions": contra["marker"],
        "hardness_contradictions": contra["hardness"], "family_contradictions": contra["family"],
    }


def stability_flips(rows) -> dict:
    """Marker-shift stability (spec B8). ``rows``: ``{central, shifts:[...]}``.

    ``central`` is the frozen-window class or ``"abstain"``. Each shift is a class,
    ``"abstain"``, or ``"invalid"``. Central abstention -> row unavailable. A row is
    comparable only with >=3 valid shifts; the flip denominator is all valid shifts
    on comparable rows; a shift flips if it changes class or becomes abstain.
    """
    comparable_rows = 0
    valid_shifts = 0
    flips = 0
    for r in rows:
        if r["central"] == "abstain":
            continue
        valid = [s for s in r["shifts"] if s != "invalid"]
        if len(valid) < 3:
            continue
        comparable_rows += 1
        for s in valid:
            valid_shifts += 1
            if s != r["central"]:
                flips += 1
    flip_rate = (flips / valid_shifts) if valid_shifts else 0.0
    return {"comparable_rows": comparable_rows, "valid_shifts": valid_shifts, "flip_rate": flip_rate}


def flip_gap_pp(candidate_flip_rate: float, baseline_flip_rate: float) -> float:
    """Percentage-point gap; positive means the candidate flips more (worse)."""
    return round((candidate_flip_rate - baseline_flip_rate) * 100.0, 6)


def prediction_freeze_setup_failures(freeze_utc, first_commit_utc) -> list:
    """Gate-1 setup check (spec B8): predictions must freeze BEFORE any human
    response. A ``freeze_utc`` at or after the earliest ``commit_utc`` is a
    post-label prediction — a setup hard FAIL. Returns named failures (empty if
    fine, or if there are no responses yet).
    """
    if first_commit_utc is None:
        return []
    try:
        frozen = datetime.fromisoformat(freeze_utc)
        first = datetime.fromisoformat(first_commit_utc)
    except ValueError:
        return [f"unparseable freeze/commit timestamp: {freeze_utc!r} / {first_commit_utc!r}"]
    if frozen >= first:
        return [f"post_label_prediction: freeze_utc {freeze_utc} >= first commit_utc {first_commit_utc}"]
    return []
