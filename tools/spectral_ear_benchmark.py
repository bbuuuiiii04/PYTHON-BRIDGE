#!/usr/bin/env python3
"""Stage-1 EAR benchmark harness (AWR-200 / AWR-195 stage 1) — read-only.

What this tool IS today: a truthful substrate for the spectral ear benchmark.
It loads the operator's AWR-182 ear-truth labels, validates and normalizes them
WITHOUT changing them, applies the charter's explicit exclusions with reasons,
groups whole track/remix lineages, emits a deterministic coverage/group manifest
and a grouped leave-one-lineage-out (LOLO) fold inventory, and audits — per
metric axis — whether the labels can actually support a score today.

What this tool is NOT: it does not manufacture accuracy numbers. The AWR-182
labels are the operator's free-text ear verdicts ("maybe t2", "absolutely not
t3", "2 bar blackout"); they carry NO structured per-drop gold field. So every
accuracy axis (tier / family / darkness / growl / laser) is reported UNAVAILABLE
with the named missing field — never zero, never PASS. The ONE axis that needs
no operator gold is marker sensitivity: it re-runs the real production planner
(`lighting_moments_v2.build_track_plan`) at the drop marker ±1/±2 beats and
counts family/tier/darkness flips. That axis is computed only when `--resolve-db`
is given AND the tracks resolve to a current filepath + beatgrid + v4 cache hit;
otherwise it too is reported UNAVAILABLE with the exact blocker.

Anti-leak: label fields that locate or describe an example (content id, title,
track name, label id, his_words, measured snapshot, classification) may be used
to LOCATE an example and as ground truth, but must NEVER enter a predictor. The
production planner is only ever called with v4 features + beat indices, and every
call routes through the single `call_planner` boundary (positive allowlist +
`assert_no_leak`) so no locator/gold field can reach the model.

Safety: no extraction, no cache/config/runtime writes, no bridge/process
contact. `--resolve-db` opens the Rekordbox master.db READ-ONLY (the same read
the runtime bridge does) and reads the v4 cache READ-ONLY. Output goes to stdout
or an explicit `--report` path chosen by the caller. Stdlib-only in its own
logic; the optional metric imports production seams + pyrekordbox on demand.

    python3 tools/spectral_ear_benchmark.py                       # core, stdout
    python3 tools/spectral_ear_benchmark.py --labels PATH --report OUT.md
    python3 tools/spectral_ear_benchmark.py --resolve-db --head <sha>  # + marker axis
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LABELS = "local/labels/operator_track_labels_2026_07_09.jsonl"

# Rows whose `id` is one of these are session meta / hypotheses / tallies /
# queued-not-verdicted cards — NOT scorable examples.
META_IDS = {
    "SESSION-1-CLOSE",
    "B2-HYPOTHESIS",
    "B3-HYPOTHESIS-UPDATE",
    "B4-THRESHOLD-TALLY",
    "B5-QUEUED",
}

# Fields that must never be passed into a predictor/formula. Locators
# (content_id/title/track/id) are resolution-only; the rest are ground truth /
# operator verdicts. A predictor sees NONE of them.
LEAK_FORBIDDEN_FIELDS = frozenset({
    "content_id", "title_exact", "track", "id",
    "his_words", "his_words_followup", "measured", "classification",
    "notes", "decoded", "missing_dimension", "plan_gap", "expectation",
    # AWR-205 gold-label intake fields — operator per-drop gold + provenance keys.
    # Like the locators/verdicts above, none may reach a predictor; gold flows only
    # into scoring. call_planner's positive allowlist already blocks them; naming
    # them here also makes assert_no_leak reject a smuggled gold field on its own.
    "is_genuine_drop", "drop", "family_matches_track", "lineage_key", "marker_beat",
})

# The ONLY fields any production-planner call may carry. A positive allowlist:
# combined with LEAK_FORBIDDEN_FIELDS it makes the guard two-sided — a locator /
# gold field can't sneak in, and an unknown/typo'd field is rejected too. Every
# planner call routes through call_planner(), so this is the real invocation
# boundary, not a one-off check on a hand-built dict.
PLANNER_ALLOWED_FIELDS = frozenset({"v4", "drops", "buildups", "beatgrid_times_ms"})

# Explicit, cited exclusions keyed by the label's own `id` (charter §D + the
# AWR-182 label doc). Exclusions are operator/charter rulings, not something to
# auto-infer from free text; they are enumerated here and cross-checked against
# the row's structured `classification` token in `validate_exclusions`.
EXCLUSIONS: tuple[dict[str, str], ...] = (
    {"id": "B3-8", "reason": "scripted",
     "source": "B3-8 classification N/A-SCRIPTED; charter B3 rule (scripted tracks excluded)"},
    {"id": "B2-5", "reason": "unusable_grid",
     "source": "B2-5 EXCLUDED (broken Rekordbox analysis); charter 'unusable grids'"},
    {"id": "B3-3", "reason": "variable_bpm",
     "source": "B3-3 EXCLUDED (changes BPM); charter 'variable-tempo cases until local-tempo support exists'"},
    {"id": "B2-3", "reason": "marker_blocked_pending_remap",
     "source": "OCHO — charter §D: marker-indexed cases blocked until remapped against current ANLZ"},
    {"id": "B4-5", "reason": "marker_blocked_pending_remap",
     "source": "Latch — charter §D: marker-indexed cases blocked until remapped against current ANLZ"},
    # NOTE: REWIND (B1-5) is NOT excluded. Charter §D: "Include REWIND's
    # post-reanalysis eight-drop result now" and "Exclude invalid observations,
    # not repaired tracks." The old-grid snapshot in B1-5.measured is stale, but
    # it is never used for scoring (accuracy axes are unavailable) and REWIND
    # resolves live through its current grid; B1-5-AMEND-1 carries the current
    # truth. The lineage stays usable.
)
EXCLUSION_REASONS = (
    "scripted", "unusable_grid", "variable_bpm", "unresolved_version",
    "marker_blocked_pending_remap",
)

# Metric axes and whether a structured operator gold field exists in the labels.
# Every accuracy axis is UNAVAILABLE today: the labels are free text. The named
# field is what a curation pass must add before the axis can be scored.
ACCURACY_AXES: tuple[dict[str, str], ...] = (
    {"axis": "tier", "missing_field": "operator_tier (ordinal 1/2/3 per drop)",
     "loss": "squared ordered error (adjacent=1, T1<->T3=4) + missed-T3/false-T3 counts (charter C.1)"},
    {"axis": "family", "missing_field": "operator_family + per-drop within-track judgment",
     "loss": "family correctness + within-track flapping rate (charter C.4 / D)"},
    {"axis": "darkness", "missing_field": "operator_darkness_shape + start/end beat + bar count per drop",
     "loss": "detection FP/miss, raw-beat start/end error, exact bar-length agreement (charter C.1)"},
    {"axis": "growl", "missing_field": "operator_growl_span (start/end beat) per drop",
     "loss": "span overlap + boundary error (growl-centroid values are already present, aligned, "
             "and real-valued in the strict v4 cache; Stage-2 must still validate they are "
             "MUSICALLY correct — presence is not correctness)"},
    {"axis": "laser", "missing_field": "operator_laser_suitability (positive/negative) per drop",
     "loss": "pins only until label coverage supports rates (charter D); more laser labels wanted"},
)

# AWR-200 stays PARTIAL until EVERY required accuracy axis is scorable. The marker
# axis is a supporting robustness metric, NOT a completion gate — a 2-track marker
# pilot can never complete Stage 1 while the operator's taste axes are unscored.
REQUIRED_ACCURACY_AXES = tuple(a["axis"] for a in ACCURACY_AXES)

# SOL published marker-sensitivity reference (15 tracks / 113 markers, audio
# fixed, drop marker perturbed). Reproduced like-for-like only; not to be
# claimed improved-upon here. (sol_spectral_review_2026_07_09.md:163-166)
SOL_MARKER_REFERENCE = {
    "method": "15 labeled tracks / 113 current markers; audio held fixed; drop marker perturbed",
    "pm1": {"family": 6.2, "tier": 32.7, "darkness": 23.0},
    "pm2": {"family": 23.9, "tier": 46.0, "darkness": 62.8},
}

_WS = re.compile(r"\s+")

# --- AWR-205 gold-label intake (hybrid unit; operator ruling 2026-07-11) ------
# Positive field allowlists — same discipline as PLANNER_ALLOWED_FIELDS: any key
# not listed is a HARD error on load (catches typos / unknown fields fail-closed).
GOLD_ROW_FIELDS = frozenset({
    "lineage_key", "content_id", "track", "marker_beat", "marker_time",
    "is_genuine_drop", "drop",
})
GOLD_DROP_FIELDS = frozenset({
    "tier", "family", "family_matches_track", "darkness", "growl",
    "laser", "confidence", "notes",
})
GOLD_DARKNESS_FIELDS = frozenset({"shape", "start_beat", "end_beat", "bars"})
GOLD_GROWL_FIELDS = frozenset({"start_beat", "end_beat"})
GOLD_TIER_VALUES = frozenset({1, 2, 3, "unknown"})
GOLD_LASER_VALUES = frozenset({"yes", "no", "unknown"})
GOLD_RULING = (
    "hybrid unit (operator ruling 2026-07-11): every enumerated marker gets an "
    "is_genuine_drop yes/no; the nested `drop` field-set is filled ONLY on genuine "
    "drops. null = unlabeled (excluded from scoring). 'unknown' is always valid."
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    """One normalized label row. `raw` is kept verbatim (never mutated)."""
    kind: str                       # "primary" | "amendment" | "meta"
    label_id: str                   # the row's `id` (or a synthetic key)
    track: str                      # locator only
    content_id: str                 # locator only ("" if absent)
    lineage: str                    # grouping key
    amends: str                     # parent id for amendments, else ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Lineage:
    """A whole track/remix lineage — the LOLO grouping unit."""
    key: str
    track: str
    content_id: str
    entry_ids: tuple[str, ...]
    excluded: bool
    reason: str                     # exclusion reason, or "" when usable
    source: str                     # exclusion citation, or "" when usable


@dataclass(frozen=True)
class Marker:
    """One enumerated drop marker — the unit the gold template/loader keys on."""
    lineage: str                    # provenance key (matches Resolution.lineage)
    track: str
    content_id: str
    beat: int
    time: str                       # mm:ss from the beatgrid, or "" if not derivable


# ---------------------------------------------------------------------------
# Load + normalize (no mutation of row content)
# ---------------------------------------------------------------------------

def load_labels(path: str) -> list[dict[str, Any]]:
    """Read the JSONL machine layer. Each non-blank line must be a JSON object."""
    rows: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{lineno}: expected a JSON object, got {type(obj).__name__}")
        rows.append(obj)
    return rows


def _norm_track(track: str) -> str:
    return _WS.sub(" ", str(track or "").strip().lower())


def _lineage_key(content_id: str, track: str) -> str:
    # Exact track identity when Rekordbox content_id is present, else the
    # normalized track string. This collapses same-track entries (all of
    # Utopia's UT-*, REWIND's primary+amendment). It does NOT merge remix
    # siblings that live under different content_ids — none exist in this
    # corpus; when they arrive (e.g. the Give It To Me Good duplicate), a
    # curated lineage map must be added before LOLO folds are trustworthy.
    return f"cid:{content_id}" if content_id else f"trk:{_norm_track(track)}"


def normalize(rows: list[dict[str, Any]]) -> list[Entry]:
    """Classify every row as primary / amendment / meta. Content is untouched.
    An amendment's grouping lineage is resolved through its `amends` parent chain
    (see _resolve_amendment_lineages) so an amendment that carries no content_id
    or a different track string still leaves WITH its parent, never on its own."""
    entries: list[Entry] = []
    for i, r in enumerate(rows):
        label_id = str(r.get("id") or "")
        track = str(r.get("track") or "")
        content_id = str(r.get("content_id") or "")
        amends = str(r.get("amends") or "")
        if amends:
            kind = "amendment"
        elif label_id in META_IDS or not track:
            kind = "meta"
        else:
            kind = "primary"
        entries.append(Entry(
            kind=kind,
            label_id=label_id or f"_row{i}",
            track=track,
            content_id=content_id,
            lineage=_lineage_key(content_id, track) if track else f"_meta:{label_id or i}",
            amends=amends,
            raw=r,
        ))
    resolved, _warns = _resolve_amendment_lineages(entries)
    if resolved:
        entries = [replace(e, lineage=resolved[e.label_id]) if e.label_id in resolved else e
                   for e in entries]
    return entries


def _resolve_amendment_lineages(entries: list[Entry]) -> tuple[dict[str, str], list[str]]:
    """For each amendment, walk its `amends` parent chain to the primary ancestor
    and return {amendment_id: ancestor_lineage}. Broken links are NOT silently
    split: a duplicated amendment own-id, or a missing / cyclic / ambiguous (parent
    id shared by >1 row) / non-primary ancestor, each produce a loud warning and the
    amendment is left ungrouped on its own lineage. amendment_warnings() surfaces
    the warnings in the report."""
    by_id: dict[str, list[Entry]] = {}
    for e in entries:
        by_id.setdefault(e.label_id, []).append(e)
    resolved: dict[str, str] = {}
    warnings: list[str] = []
    for e in entries:
        if e.kind != "amendment":
            continue
        # An amendment whose OWN id is shared by >1 row would make the by-label_id
        # rewrite in normalize() rewrite every collided row (including a primary),
        # silently mis-grouping. Keep it OUT of `resolved` and warn — so `resolved`
        # only ever holds ids that occur exactly once, and the rewrite can never
        # target the wrong row.
        if len(by_id.get(e.label_id, ())) > 1:
            warnings.append(f"{e.label_id}: amendment id shared by {len(by_id[e.label_id])} rows "
                            "— left UNGROUPED (never silently merged/split)")
            continue
        seen = {e.label_id}
        cur = e
        problem = ""
        while cur.amends:
            pid = cur.amends
            if pid in seen:
                problem = f"cyclic amends link at {pid!r}"
                break
            seen.add(pid)
            parents = by_id.get(pid, [])
            if not parents:
                problem = f"amends unknown id {pid!r}"
                break
            if len(parents) > 1:
                problem = f"amends ambiguous id {pid!r} ({len(parents)} rows share it)"
                break
            cur = parents[0]
        if problem:
            warnings.append(f"{e.label_id}: {problem} — left UNGROUPED (never silently merged/split)")
            continue
        if cur.kind != "primary":
            warnings.append(f"{e.label_id}: amends chain resolves to non-primary row "
                            f"{cur.label_id!r} (kind={cur.kind}) — left UNGROUPED")
            continue
        resolved[e.label_id] = cur.lineage
    return resolved, warnings


def amendment_warnings(entries: list[Entry]) -> list[str]:
    """Report broken amendment parent links (missing/cyclic/ambiguous/non-primary)
    for the manifest. Deterministic; never silent."""
    return _resolve_amendment_lineages(entries)[1]


# ---------------------------------------------------------------------------
# Exclusions + lineage grouping
# ---------------------------------------------------------------------------

def _exclusion_for(label_id: str) -> Optional[dict[str, str]]:
    for ex in EXCLUSIONS:
        if ex["id"] == label_id:
            return ex
    return None


def validate_exclusions(entries: list[Entry]) -> list[str]:
    """Cross-check: every explicitly-excluded id must exist, and any row whose
    structured `classification` shouts EXCLUDED/SCRIPTED must be in the table.
    Returns human-readable warnings (surfaced in the report), never silent."""
    warnings: list[str] = []
    ids = {e.label_id for e in entries}
    for ex in EXCLUSIONS:
        if ex["id"] not in ids:
            warnings.append(f"exclusion for unknown id {ex['id']!r} — corpus changed?")
    for e in entries:
        if e.kind != "primary":
            continue
        cls = str(e.raw.get("classification") or "").upper()
        shouts = ("EXCLUDED" in cls) or ("N/A-SCRIPTED" in cls) or ("SCRIPTED" in cls and "EXCLUDED" in cls)
        if shouts and _exclusion_for(e.label_id) is None:
            warnings.append(
                f"{e.label_id}: classification says {e.raw.get('classification')!r} "
                "but no explicit exclusion is declared")
    return warnings


def build_lineages(entries: list[Entry]) -> list[Lineage]:
    """Group primary+amendment entries into lineages; apply track-level
    exclusions. A lineage is excluded if ANY of its entries carries an explicit
    exclusion (exclusions are track-level rulings)."""
    order: list[str] = []
    members: dict[str, list[Entry]] = {}
    for e in entries:
        if e.kind == "meta":
            continue
        members.setdefault(e.lineage, [])
        if e.lineage not in order:
            order.append(e.lineage)
        members[e.lineage].append(e)

    lineages: list[Lineage] = []
    for key in order:
        group = members[key]
        reason = source = ""
        for e in group:
            ex = _exclusion_for(e.label_id)
            if ex:
                reason, source = ex["reason"], ex["source"]
                break
        primary = next((e for e in group if e.kind == "primary"), group[0])
        lineages.append(Lineage(
            key=key,
            track=primary.track,
            content_id=primary.content_id,
            entry_ids=tuple(sorted(e.label_id for e in group)),
            excluded=bool(reason),
            reason=reason,
            source=source,
        ))
    return lineages


def identity_warnings(lineages: list[Lineage]) -> list[str]:
    """Deterministic identity-collision surface. Rows without a Rekordbox
    content_id are grouped by normalized title ONLY; that cannot tell apart two
    different tracks that share a title, nor merge one track spelled two ways. We
    do NOT guess identity here — we FLAG the ambiguity so a curation pass
    (content_ids / a curated lineage map) can resolve it. This keeps the known
    same-title collision limitation loud instead of silent."""
    warnings: list[str] = []
    by_title: dict[str, set[str]] = {}
    for ln in lineages:
        by_title.setdefault(_norm_track(ln.track), set()).add(ln.key)
    for title, keys in sorted(by_title.items()):
        if len(keys) > 1:
            warnings.append(
                f"identity ambiguity: normalized title {title!r} spans {len(keys)} lineages "
                f"({', '.join(sorted(keys))}) — no curated content_id map decides these; folds "
                "may mis-group. Curation work, NOT auto-resolved here.")
    no_cid = sum(1 for ln in lineages if not ln.content_id and not ln.excluded)
    if no_cid:
        warnings.append(
            f"identity limitation: {no_cid} usable lineages are grouped by normalized title only "
            "(no Rekordbox content_id). Same-title different-track collisions cannot be detected; "
            "a curated content_id lineage map is curation work, out of scope for this harness.")
    return warnings


# ---------------------------------------------------------------------------
# Folds (grouped leave-one-lineage-out)
# ---------------------------------------------------------------------------

def build_folds(lineages: list[Lineage]) -> list[dict[str, Any]]:
    """One LOLO fold per USABLE lineage: hold that lineage out, train on the
    rest. The real invariant proved here: the held-out lineage's ENTRY IDS (which
    already include its resolved amendments — see normalize) never appear in any
    train lineage. The old `held.key not in train_keys` check was tautological
    (train is built by excluding held.key); this entry-id disjointness catches a
    genuine grouping bug where an entry lands in two lineages."""
    usable = [ln for ln in lineages if not ln.excluded]
    folds: list[dict[str, Any]] = []
    for held in usable:
        train = [ln for ln in usable if ln.key != held.key]
        test_ids = set(held.entry_ids)
        train_ids = {eid for ln in train for eid in ln.entry_ids}
        overlap = test_ids & train_ids
        assert not overlap, f"lineage {held.key} shares entries {sorted(overlap)} with its train split"
        folds.append({
            "fold": len(folds),
            "held_out_lineage": held.key,
            "held_out_track": held.track,
            "test_entry_ids": list(held.entry_ids),
            "train_lineages": len(train),
            "train_entries": sum(len(ln.entry_ids) for ln in train),
        })
    return folds


# ---------------------------------------------------------------------------
# Axis availability audit (the honesty core)
# ---------------------------------------------------------------------------

def axis_availability(marker_scored: Optional[int],
                      marker_comparable: Optional[int] = None,
                      *, accuracy_scores: Optional[dict[str, dict[str, Any]]] = None
                      ) -> list[dict[str, Any]]:
    """Report, per axis, whether a score can be computed TODAY. Without gold
    (`accuracy_scores is None`) every accuracy axis is UNAVAILABLE — the labels are
    free text (unchanged AWR-200 behavior). With gold (AWR-205), an accuracy axis
    flips AVAILABLE only when BOTH hold: >=1 genuine-drop gold example exists AND a
    real scorer compared it to an actual per-marker model output; `accuracy_scores`
    carries that per-axis verdict (see score_accuracy_axes). Marker sensitivity is
    AVAILABLE only when at least one drop marker had a baseline decision
    (`marker_scored`) AND at least one COMPARABLE +-1/+-2 perturbation existed to
    flip against (`marker_comparable` = the sum of the two per-radius comparable
    denominators). A track can resolve — and even produce baseline decisions — yet
    have ZERO comparable perturbations (every offset out of range or colliding with
    another drop); both flip rates then come back None, so nothing was measured and
    the axis must read UNAVAILABLE, not a hollow AVAILABLE. `marker_comparable`
    defaults None so the gate fails closed toward UNAVAILABLE. Model-only; needs no
    operator gold."""
    scores = accuracy_scores or {}
    axes: list[dict[str, Any]] = []
    for a in ACCURACY_AXES:
        sc = scores.get(a["axis"])
        if sc is None:
            axes.append({
                "axis": a["axis"],
                "available": False,
                "gold_examples": 0,
                "loss_shape": a["loss"],
                "blocker": f"no structured {a['missing_field']} in labels — operator verdicts are free "
                           "text; requires a curation pass. Reported UNAVAILABLE, not zero/PASS.",
            })
        else:
            axes.append({
                "axis": a["axis"],
                "available": bool(sc["available"]),
                "gold_examples": int(sc.get("gold_examples", 0)),
                "loss_shape": a["loss"],
                "blocker": sc.get("blocker", ""),
                "score": sc.get("score"),
            })
    # AWR-205 yes/no layer axis — only surfaced once gold is loaded. NOT a required
    # accuracy axis (is_partial ignores it): it can never complete Stage 1.
    dc = scores.get("drop_classification")
    if dc is not None:
        axes.append({
            "axis": "drop_classification",
            "available": bool(dc["available"]),
            "gold_examples": int(dc.get("gold_examples", 0)),
            "loss_shape": "genuine-drop (yes/no) vs a planner per-marker genuine-drop/blackout decision",
            "blocker": dc.get("blocker", ""),
        })
    if marker_scored is None:
        marker = {
            "axis": "marker_sensitivity", "available": False, "gold_examples": 0,
            "loss_shape": "family/tier/darkness flip rate at drop marker +-1 / +-2 (model-only)",
            "blocker": "not run — pass --resolve-db to resolve tracks and compute it.",
        }
    elif marker_scored <= 0:
        marker = {
            "axis": "marker_sensitivity", "available": False, "gold_examples": 0,
            "loss_shape": "family/tier/darkness flip rate at drop marker +-1 / +-2 (model-only)",
            "blocker": "no marker scored — either no track resolved to a filepath + beatgrid + v4 "
                       "cache hit, or resolved tracks produced no baseline drop decision to perturb.",
        }
    elif not marker_comparable:
        marker = {
            "axis": "marker_sensitivity", "available": False, "gold_examples": 0,
            "loss_shape": "family/tier/darkness flip rate at drop marker +-1 / +-2 (model-only)",
            "blocker": f"{marker_scored} marker(s) had a baseline decision but none had a comparable "
                       "+-1/+-2 perturbation (every offset fell out of range or collided with another "
                       "drop); both flip rates are None, so nothing was measured.",
        }
    else:
        marker = {
            "axis": "marker_sensitivity", "available": True, "gold_examples": marker_scored,
            "loss_shape": "family/tier/darkness flip rate at drop marker +-1 / +-2 (model-only)",
            "blocker": "",
        }
    axes.append(marker)
    return axes


def is_partial(availability: list[dict[str, Any]]) -> bool:
    """Single source of truth for AWR-200's PARTIAL/complete status. PARTIAL until
    every REQUIRED accuracy axis is available. Marker-sensitivity availability is
    deliberately irrelevant — it can never, on its own, complete Stage 1."""
    avail = {a["axis"]: a["available"] for a in availability}
    return not all(avail.get(axis, False) for axis in REQUIRED_ACCURACY_AXES)


# ---------------------------------------------------------------------------
# Anti-leak guard
# ---------------------------------------------------------------------------

def assert_no_leak(model_inputs: dict[str, Any]) -> None:
    """Raise if any label-identifying/ground-truth field reached the predictor.
    Called inside call_planner() on every production-planner invocation."""
    bad = sorted(set(model_inputs) & LEAK_FORBIDDEN_FIELDS)
    if bad:
        raise ValueError(f"anti-leak violation: forbidden label fields reached the model: {bad}")


def call_planner(plan_fn: Callable[..., Any], model_inputs: dict[str, Any]) -> Any:
    """The single boundary EVERY production-planner call routes through. Enforces
    a positive allowlist (only v4 + beat indices) AND the forbidden-field guard,
    then unpacks and calls the planner. No planner call may bypass this — that is
    what keeps a label locator/gold field out of the model. Base and every
    perturbed call go through here, so the guard is not a one-off on a hand-built
    dict; it fires on each real invocation."""
    unexpected = sorted(set(model_inputs) - PLANNER_ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(
            f"anti-leak violation: non-model field(s) reached the planner: {unexpected}")
    assert_no_leak(model_inputs)
    return plan_fn(model_inputs["v4"], model_inputs["drops"], model_inputs["buildups"],
                   beatgrid_times_ms=model_inputs["beatgrid_times_ms"])


# ---------------------------------------------------------------------------
# Optional: resolution + marker-sensitivity metric (production seams; gated)
# ---------------------------------------------------------------------------

@dataclass
class Resolution:
    lineage: str
    track: str
    status: str                     # resolved | cache_miss | no_anlz | not_in_db | no_drops
    v4: Any = None
    drops: tuple[int, ...] = ()
    buildups: tuple[int, ...] = ()
    grid: tuple[float, ...] = ()


def _load_db_index(db_path: str) -> dict[str, dict[str, str]]:
    """content_id -> {filepath, anlz_abs, title} from the Rekordbox DB, READ-ONLY."""
    import os
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from pyrekordbox.db6 import Rekordbox6Database  # type: ignore
    share = Path("~/Library/Pioneer/rekordbox/share").expanduser()
    db = Rekordbox6Database(db_path, unlock=True)
    index: dict[str, dict[str, str]] = {}
    try:
        for c in db.get_content():
            if getattr(c, "rb_local_deleted", 0):
                continue
            fp = str(c.FolderPath or "")
            if not fp or not os.path.isfile(fp):
                continue
            rel = str(getattr(c, "AnalysisDataPath", "") or "")
            index[str(c.ID)] = {
                "filepath": fp,
                "anlz_abs": str(share / rel.lstrip("/")) if rel else "",
                "title": str(c.Title or ""),
            }
    finally:
        db.close()
    return index


def resolve_lineages(lineages: list[Lineage], db_index: dict[str, dict[str, str]]) -> list[Resolution]:
    """Resolve each USABLE lineage that carries a content_id to its current
    filepath + beatgrid + v4 cache entry. READ-ONLY (no extraction, no writes).
    Lineages without a content_id cannot be DB-resolved here (the B-row corpus
    stores only track names); reported as not_in_db so the coverage stays honest."""
    import os
    from rb_ss_bridge_v2 import spectral_cache
    from rb_ss_bridge_v2.anlz_reader import read_anlz_drops

    out: list[Resolution] = []
    for ln in lineages:
        if ln.excluded:
            continue
        rec = db_index.get(ln.content_id) if ln.content_id else None
        if rec is None:
            out.append(Resolution(ln.key, ln.track, "not_in_db"))
            continue
        anlz = rec["anlz_abs"]
        if not anlz or not os.path.isfile(anlz):
            out.append(Resolution(ln.key, ln.track, "no_anlz"))
            continue
        data = read_anlz_drops(anlz)
        drops = tuple(int(x) for x in data.drop_beat_indices)
        buildups = tuple(int(x) for x in data.buildup_beat_indices)
        grid = tuple(float(x) for x in (data.waveform_context.beatgrid_times_ms
                                        if data.waveform_context else ()))
        if not drops:
            out.append(Resolution(ln.key, ln.track, "no_drops", drops=drops, buildups=buildups, grid=grid))
            continue
        v4 = spectral_cache.get_cached_v4(rec["filepath"], grid)  # READ-ONLY; None on miss
        if v4 is None:
            out.append(Resolution(ln.key, ln.track, "cache_miss", drops=drops, buildups=buildups, grid=grid))
            continue
        out.append(Resolution(ln.key, ln.track, "resolved", v4=v4,
                              drops=drops, buildups=buildups, grid=grid))
    return out


def _decision_at(plan: Any, beat: int) -> Optional[tuple[str, int, str, int]]:
    """(family, tier, darkness_kind, darkness_beats) for the plan entry nearest
    `beat`, or None if no entry is within 1 beat."""
    entry = plan.for_drop(float(beat), tol=1.0)
    if entry is None:
        return None
    d = entry.decision
    return (d.family, int(d.tier), d.darkness.kind, int(d.darkness.beats))


def marker_sensitivity(
    resolutions: list[Resolution],
    plan_fn: Callable[..., Any],
) -> dict[str, Any]:
    """Reproduce SOL's marker-sensitivity metric: hold audio fixed, perturb each
    drop marker by +-1 and +-2 beats, count family/tier/darkness flips vs the
    baseline decision. Model-only — no operator gold. `plan_fn` is the production
    planner (injected so tests can drive a synthetic seam).

    Aggregation (documented, may differ from SOL's exact roll-up): a marker is
    "+-k sensitive" on an axis if the axis output differs from baseline at
    offset -k OR +k. A marker with NO comparable perturbed entry at radius k
    (both offsets fall out of range or collide with another drop, or the planner
    returns no comparable decision) cannot flip there, so it is REMOVED from that
    radius's denominator — `comparable_pm1`/`comparable_pm2` report those honest
    per-radius denominators. Markers with no baseline decision are counted under
    `skipped` and score nothing. Every planner call goes through call_planner().
    """
    axes = ("family", "tier", "darkness")
    counts: dict[str, Any] = {"markers": 0, "skipped": 0, "comparable": {1: 0, 2: 0},
                              "pm1": {a: 0 for a in axes}, "pm2": {a: 0 for a in axes}}

    def _plan(res: Resolution, marks: Any) -> Any:
        return call_planner(plan_fn, {
            "v4": res.v4, "drops": list(marks),
            "buildups": list(res.buildups), "beatgrid_times_ms": list(res.grid)})

    for res in resolutions:
        if res.status != "resolved" or not res.drops:
            continue
        n = int(getattr(res.v4, "n_beats", 0)) or (max(res.drops) + 4)
        base_plan = _plan(res, res.drops)
        others = set(res.drops)
        for m in res.drops:
            base = _decision_at(base_plan, m)
            if base is None:
                counts["skipped"] += 1
                continue
            counts["markers"] += 1
            for k in (1, 2):
                comparable = False
                flipped = {a: False for a in axes}
                for off in (-k, k):
                    mp = m + off
                    if mp < 0 or mp >= n or mp in (others - {m}):
                        continue
                    pert = sorted((others - {m}) | {mp})
                    pd = _decision_at(_plan(res, pert), mp)
                    if pd is None:
                        continue
                    comparable = True
                    if pd[0] != base[0]:
                        flipped["family"] = True
                    if pd[1] != base[1]:
                        flipped["tier"] = True
                    if (pd[2], pd[3]) != (base[2], base[3]):
                        flipped["darkness"] = True
                if not comparable:
                    # no comparable perturbation at this radius: this marker can
                    # never flip here, so it stays OUT of the radius denominator.
                    continue
                counts["comparable"][k] += 1
                for a in axes:
                    if flipped[a]:
                        counts[f"pm{k}"][a] += 1
    result: dict[str, Any] = {
        "markers": counts["markers"], "skipped": counts["skipped"],
        "tracks": sum(1 for r in resolutions if r.status == "resolved" and r.drops),
        "comparable_pm1": counts["comparable"][1], "comparable_pm2": counts["comparable"][2],
    }
    for k in (1, 2):
        key = f"pm{k}"
        denom = counts["comparable"][k]
        result[key] = {a: (round(100.0 * counts[key][a] / denom, 1) if denom else None)
                       for a in axes}
    return result


# ---------------------------------------------------------------------------
# AWR-205 gold-label intake: enumerate markers, emit template, strict load, score
# ---------------------------------------------------------------------------

def _mmss(ms: float) -> str:
    total = int(ms // 1000)
    return f"{total // 60}:{total % 60:02d}"


def enumerate_markers(resolutions: list[Resolution]) -> list[Marker]:
    """The marker set the marker-sensitivity pass iterates: every drop beat of a
    RESOLVED lineage (SAME `status == 'resolved' and res.drops` guard — not a
    parallel enumeration). Reused by the template emitter AND the gold loader so
    their provenance keys line up exactly. Deterministic: resolution order, then
    res.drops order (already sorted ints)."""
    out: list[Marker] = []
    for res in resolutions:
        if res.status != "resolved" or not res.drops:
            continue
        cid = res.lineage[4:] if res.lineage.startswith("cid:") else ""
        for beat in res.drops:
            b = int(beat)
            t = _mmss(res.grid[b]) if 0 <= b < len(res.grid) else ""
            out.append(Marker(res.lineage, res.track, cid, b, t))
    return out


def _template_row(mk: Marker) -> dict[str, Any]:
    """One all-null hybrid row: is_genuine_drop yes/no + the nested drop field-set."""
    return {
        "lineage_key": mk.lineage,
        "content_id": mk.content_id,
        "track": mk.track,
        "marker_beat": mk.beat,
        "marker_time": mk.time or None,
        "is_genuine_drop": None,
        "drop": {
            "tier": None,
            "family": None,
            "family_matches_track": None,
            "darkness": {"shape": None, "start_beat": None, "end_beat": None, "bars": None},
            "growl": {"start_beat": None, "end_beat": None},
            "laser": None,
            "confidence": None,
            "notes": None,
        },
    }


def build_gold_template(resolutions: list[Resolution], head: str, label_sha: str) -> dict[str, Any]:
    """Deterministic, all-null, provenance-keyed hybrid template over the resolved
    marker set. No wall-clock (determinism). One row per enumerated marker; rows
    carry title + mm:ss so a chat transcription session can fill them."""
    markers = enumerate_markers(resolutions)
    lineages = sorted({mk.lineage for mk in markers})
    return {
        "_header": {
            "head": head,
            "label_sha": label_sha,
            "generated_by": "spectral_ear_benchmark --emit-gold-template (deterministic; no wall-clock)",
            "ruling": GOLD_RULING,
            "markers": len(markers),
            "lineages": len(lineages),
        },
        "rows": [_template_row(mk) for mk in markers],
    }


def _template_has_labels(path: str) -> bool:
    """True if an existing OUT.json already carries ANY non-null is_genuine_drop.
    Missing or empty file -> False (nothing to protect)."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return False
    obj = json.loads(p.read_text(encoding="utf-8"))
    return any(r.get("is_genuine_drop") is not None for r in obj.get("rows", []))


def write_gold_template(obj: dict[str, Any], out_path: str) -> None:
    """Write the template, refusing to clobber a file that already has labels (or
    a non-empty file we can't recognise as a template). Empty/missing -> write."""
    p = Path(out_path)
    if p.is_file() and p.stat().st_size > 0:
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ValueError(
                f"refusing to overwrite {out_path!r}: existing file is not a gold "
                "template (unparseable JSON) — move it aside first.")
        if any(r.get("is_genuine_drop") is not None for r in existing.get("rows", [])):
            raise ValueError(
                f"refusing to overwrite {out_path!r}: it already contains filled "
                "is_genuine_drop labels — move it aside first, then re-emit.")
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_beat_pair(start: Any, end: Any, rid: str, name: str, errors: list[str]) -> None:
    for v, lbl in ((start, "start_beat"), (end, "end_beat")):
        if v is not None and not (_is_int(v) and v >= 0):
            errors.append(f"{rid}: {name}.{lbl} must be a non-negative integer or null (got {v!r})")
    if _is_int(start) and _is_int(end) and not (start < end):
        errors.append(f"{rid}: {name} start_beat ({start}) must be < end_beat ({end})")


def _validate_genuine_drop(drop: Any, rid: str, errors: list[str]) -> None:
    """Genuine-drop rows: enum fields valid-or-'unknown' (null is NOT allowed —
    use 'unknown'); beat fields sane. `unknown` is always valid."""
    if not isinstance(drop, dict):
        errors.append(f"{rid}: is_genuine_drop=true requires a `drop` object")
        return
    # bool is a Python int (True == 1, False == 0), so a bare `in GOLD_TIER_VALUES`
    # membership test would accept `tier: true` as tier 1 — reject bools first so a
    # JSON boolean is a hard error, not a silently-mislabeled tier.
    tier = drop.get("tier")
    if isinstance(tier, bool) or tier not in GOLD_TIER_VALUES:
        errors.append(f"{rid}: tier must be 1/2/3/'unknown' on a genuine drop (got {tier!r})")
    fam = drop.get("family")
    if not (fam == "unknown" or (isinstance(fam, str) and fam.strip())):
        errors.append(f"{rid}: family must be a non-empty string (free text or 'unknown') "
                      f"on a genuine drop (got {fam!r})")
    # accept only a real bool or 'unknown' — reject int 1/0 (same bool/int aliasing).
    fmt = drop.get("family_matches_track")
    if not (isinstance(fmt, bool) or fmt == "unknown"):
        errors.append(f"{rid}: family_matches_track must be true/false/'unknown' (got {fmt!r})")
    if drop.get("laser") not in GOLD_LASER_VALUES:
        errors.append(f"{rid}: laser must be 'yes'/'no'/'unknown' (got {drop.get('laser')!r})")
    dark = drop.get("darkness")
    if isinstance(dark, dict):
        shape = dark.get("shape")
        if shape is not None and not isinstance(shape, str):
            errors.append(f"{rid}: darkness.shape must be a string or null (got {shape!r})")
        _check_beat_pair(dark.get("start_beat"), dark.get("end_beat"), rid, "darkness", errors)
        bars = dark.get("bars")
        if bars is not None and not (_is_num(bars) and bars >= 0):
            errors.append(f"{rid}: darkness.bars must be a non-negative number or null (got {bars!r})")
    growl = drop.get("growl")
    if isinstance(growl, dict):
        _check_beat_pair(growl.get("start_beat"), growl.get("end_beat"), rid, "growl", errors)


def validate_gold(gold_obj: Any, marker_index: dict[tuple[str, int], Marker]) -> dict[str, Any]:
    """Strict, fail-closed schema validation of a filled gold file against the
    currently-enumerable marker set. Collects EVERY problem then raises ValueError
    naming each — no silent skips. Returns {labeled, total, rows, genuine_rows}."""
    if not isinstance(gold_obj, dict) or not isinstance(gold_obj.get("rows"), list):
        raise ValueError("gold: top-level object must have a 'rows' list")
    rows = gold_obj["rows"]
    errors: list[str] = []
    labeled = 0
    genuine_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for i, row in enumerate(rows):
        rid = (f"row[{i}] {row.get('lineage_key')!r}@{row.get('marker_beat')!r}"
               if isinstance(row, dict) else f"row[{i}]")
        if not isinstance(row, dict):
            errors.append(f"{rid}: must be an object")
            continue
        extra = set(row) - GOLD_ROW_FIELDS
        if extra:
            errors.append(f"{rid}: unknown field(s) {sorted(extra)}")
        lk, mb = row.get("lineage_key"), row.get("marker_beat")
        if not (isinstance(lk, str) and lk):
            errors.append(f"{rid}: lineage_key must be a non-empty string")
        if not _is_int(mb):
            errors.append(f"{rid}: marker_beat must be an integer")
        if isinstance(lk, str) and lk and _is_int(mb):
            key = (lk, mb)
            if key not in marker_index:
                errors.append(f"{rid}: no currently-enumerable marker matches this provenance key")
            if key in seen:
                errors.append(f"{rid}: duplicate provenance key {key}")
            seen.add(key)
        igd = row.get("is_genuine_drop")
        # must be a REAL bool or null — reject int 1/0 (1 == True would otherwise
        # pass, then get counted as labeled yet silently dropped from scoring).
        if not (igd is None or isinstance(igd, bool)):
            errors.append(f"{rid}: is_genuine_drop must be true/false/null (got {igd!r})")
        drop = row.get("drop")
        if drop is not None and not isinstance(drop, dict):
            errors.append(f"{rid}: drop must be an object or null")
        if isinstance(drop, dict):
            extra_d = set(drop) - GOLD_DROP_FIELDS
            if extra_d:
                errors.append(f"{rid}: drop unknown field(s) {sorted(extra_d)}")
            dark = drop.get("darkness")
            if dark is not None and not isinstance(dark, dict):
                errors.append(f"{rid}: drop.darkness must be an object or null")
            if isinstance(dark, dict):
                extra_dk = set(dark) - GOLD_DARKNESS_FIELDS
                if extra_dk:
                    errors.append(f"{rid}: darkness unknown field(s) {sorted(extra_dk)}")
            growl = drop.get("growl")
            if growl is not None and growl != "none" and not isinstance(growl, dict):
                errors.append(f"{rid}: growl must be an object, \"none\", or null")
            if isinstance(growl, dict):
                extra_g = set(growl) - GOLD_GROWL_FIELDS
                if extra_g:
                    errors.append(f"{rid}: growl unknown field(s) {sorted(extra_g)}")
        if igd is not None:
            labeled += 1
        if igd is True:
            _validate_genuine_drop(drop, rid, errors)
            genuine_rows.append(row)
    if errors:
        raise ValueError(f"gold validation failed ({len(errors)} problem(s)):\n  - "
                         + "\n  - ".join(errors))
    return {"labeled": labeled, "total": len(marker_index), "rows": rows, "genuine_rows": genuine_rows}


def score_accuracy_axes(gold_result: dict[str, Any], resolutions: list[Resolution],
                        plan_fn: Callable[..., Any]) -> dict[str, dict[str, Any]]:
    """Compare genuine-drop gold to REAL per-marker model output. Scores ONLY the
    axes the planner (DropDecision) exposes cleanly today — tier (int) and family
    (str) — each via the single call_planner boundary. darkness/growl/laser and the
    yes/no drop_classification layer have no verified like-for-like model output, so
    they report UNAVAILABLE with a precise blocker (fail toward UNAVAILABLE). An
    accuracy axis is AVAILABLE only with >=1 comparable genuine-drop example AND a
    real model decision at that marker."""
    res_by_lineage = {r.lineage: r for r in resolutions}
    plan_cache: dict[str, Any] = {}

    def decision_at(lineage: str, beat: int) -> Optional[tuple[str, int, str, int]]:
        res = res_by_lineage.get(lineage)
        if res is None or res.status != "resolved" or not res.drops:
            return None
        if lineage not in plan_cache:
            plan_cache[lineage] = call_planner(plan_fn, {
                "v4": res.v4, "drops": list(res.drops),
                "buildups": list(res.buildups), "beatgrid_times_ms": list(res.grid)})
        return _decision_at(plan_cache[lineage], beat)

    tier_ex: list[tuple[int, int]] = []
    fam_ex: list[tuple[str, str]] = []
    dark_n = growl_n = laser_n = 0
    for row in gold_result["genuine_rows"]:
        drop = row.get("drop") or {}
        # informational counts of labeled gold per axis (whether or not scorable)
        dark = drop.get("darkness") or {}
        if any(dark.get(k) is not None for k in GOLD_DARKNESS_FIELDS):
            dark_n += 1
        g_growl = drop.get("growl")
        if g_growl == "none" or (isinstance(g_growl, dict)
                                 and any(g_growl.get(k) is not None for k in GOLD_GROWL_FIELDS)):
            growl_n += 1
        if drop.get("laser") in ("yes", "no"):
            laser_n += 1
        md = decision_at(row["lineage_key"], int(row["marker_beat"]))
        if md is None:
            continue   # no real model output at this marker -> not comparable
        if drop.get("tier") in (1, 2, 3) and not isinstance(drop.get("tier"), bool):
            tier_ex.append((int(drop["tier"]), int(md[1])))
        fam = drop.get("family")
        if isinstance(fam, str) and fam.strip() and fam != "unknown":
            fam_ex.append((fam.strip().upper(), str(md[0]).strip().upper()))

    scores: dict[str, dict[str, Any]] = {}
    if tier_ex:
        exact = sum(1 for g, mo in tier_ex if g == mo)
        mse = round(sum((g - mo) ** 2 for g, mo in tier_ex) / len(tier_ex), 3)
        scores["tier"] = {
            "available": True, "gold_examples": len(tier_ex), "blocker": "",
            "score": {"examples": len(tier_ex), "exact": exact, "mse_ordinal": mse,
                      "missed_t3": sum(1 for g, mo in tier_ex if g == 3 and mo != 3),
                      "false_t3": sum(1 for g, mo in tier_ex if mo == 3 and g != 3)}}
    else:
        scores["tier"] = {"available": False, "gold_examples": 0,
            "blocker": "gold loaded but no genuine-drop tier example is comparable (all null/'unknown', "
                       "or their markers didn't resolve to a model decision)."}
    if fam_ex:
        correct = sum(1 for g, mo in fam_ex if g == mo)
        scores["family"] = {
            "available": True, "gold_examples": len(fam_ex), "blocker": "",
            "score": {"examples": len(fam_ex), "correct": correct,
                      "accuracy_pct": round(100.0 * correct / len(fam_ex), 1)}}
    else:
        scores["family"] = {"available": False, "gold_examples": 0,
            "blocker": "gold loaded but no genuine-drop family example is comparable (all null/'unknown', "
                       "or their markers didn't resolve to a model decision)."}
    # Unexposed axes — fail toward UNAVAILABLE with a verified per-axis blocker.
    scores["darkness"] = {"available": False, "gold_examples": dark_n,
        "blocker": "gold present; DropDecision exposes darkness (kind, beats, window) but the bar<->beat "
                   "unit and shape-vocab / start-end alignment to the operator's gold are unverified — "
                   "no like-for-like scorer this round (Stage-2)."}
    scores["growl"] = {"available": False, "gold_examples": growl_n,
        "blocker": "gold present; DropDecision exposes no per-drop growl span — nothing to score "
                   "against (Stage-2)."}
    scores["laser"] = {"available": False, "gold_examples": laser_n,
        "blocker": "gold present; DropDecision exposes no laser-suitability output — nothing to score "
                   "against (Stage-2)."}
    scores["drop_classification"] = {"available": False, "gold_examples": int(gold_result["labeled"]),
        "blocker": "yes/no gold recorded; the planner exposes no per-marker genuine-drop/blackout "
                   "classifier (DropDecision carries family/tier/darkness only, no is_genuine bit) — "
                   "Stage-2."}
    return scores


# ---------------------------------------------------------------------------
# Manifest + report (deterministic)
# ---------------------------------------------------------------------------

def build_manifest(entries: list[Entry], lineages: list[Lineage]) -> dict[str, Any]:
    by_kind = {"primary": 0, "amendment": 0, "meta": 0}
    for e in entries:
        by_kind[e.kind] += 1
    usable = [ln for ln in lineages if not ln.excluded]
    excluded = [ln for ln in lineages if ln.excluded]
    by_reason: dict[str, list[str]] = {}
    for ln in excluded:
        by_reason.setdefault(ln.reason, []).append(ln.track)
    usable_entries = sum(len(ln.entry_ids) for ln in usable)
    return {
        "rows_total": len(entries),
        "rows_by_kind": by_kind,
        "lineages_total": len(lineages),
        "lineages_usable": len(usable),
        "lineages_excluded": len(excluded),
        "usable_entries": usable_entries,
        "exclusions_by_reason": {k: sorted(v) for k, v in sorted(by_reason.items())},
        "usable_lineage_tracks": sorted(ln.track for ln in usable),
    }


def render_report(
    *,
    head: str,
    labels_path: str,
    label_sha: str,
    manifest: dict[str, Any],
    warnings: list[str],
    folds: list[dict[str, Any]],
    availability: list[dict[str, Any]],
    marker: Optional[dict[str, Any]],
    resolution_summary: Optional[dict[str, int]],
    gold_sha: Optional[str] = None,
    gold_coverage: Optional[dict[str, int]] = None,
) -> str:
    L: list[str] = []
    partial = is_partial(availability)
    L.append("# Spectral EAR benchmark — Stage-1 report (AWR-200)")
    L.append("")
    L.append(f"- HEAD: {head}")
    L.append(f"- labels: {labels_path}")
    L.append(f"- label sha256[:16]: {label_sha}")
    if gold_sha:
        L.append(f"- gold sha256[:16]: {gold_sha}")
        if gold_coverage:
            L.append(f"- gold coverage: {gold_coverage['labeled']}/{gold_coverage['total']} markers "
                     "labeled (is_genuine_drop non-null; null = unlabeled, excluded from scoring)")
    L.append(f"- AWR-200 status: {'PARTIAL' if partial else 'baseline-complete'}")
    L.append("- evidence class: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED")
    L.append("")
    L.append("## Coverage / group manifest")
    L.append(f"- rows: {manifest['rows_total']} "
             f"(primary {manifest['rows_by_kind']['primary']}, "
             f"amendment {manifest['rows_by_kind']['amendment']}, "
             f"meta {manifest['rows_by_kind']['meta']})")
    L.append(f"- lineages: {manifest['lineages_total']} "
             f"(usable {manifest['lineages_usable']}, excluded {manifest['lineages_excluded']})")
    L.append(f"- usable entries: {manifest['usable_entries']}")
    L.append("- exclusions by reason:")
    if manifest["exclusions_by_reason"]:
        for reason, tracks in manifest["exclusions_by_reason"].items():
            L.append(f"  - {reason}: {len(tracks)} — {', '.join(tracks)}")
    else:
        L.append("  - (none)")
    if warnings:
        L.append("- validation warnings:")
        for w in warnings:
            L.append(f"  - {w}")
    L.append("")
    L.append("## Grouped leave-one-lineage-out fold inventory")
    L.append(f"- folds: {len(folds)} (one per usable lineage; a lineage never splits train/test)")
    for f in folds:
        L.append(f"  - fold {f['fold']}: hold out {f['held_out_track']} "
                 f"({len(f['test_entry_ids'])} test entries) / "
                 f"train {f['train_lineages']} lineages, {f['train_entries']} entries")
    L.append("")
    L.append("## Per-axis metric availability (today)")
    L.append("No blended score is emitted; each axis stands alone.")
    for a in availability:
        state = "AVAILABLE" if a["available"] else "UNAVAILABLE"
        L.append(f"- **{a['axis']}**: {state}"
                 + (f" ({a['gold_examples']} examples)" if a["available"] else ""))
        L.append(f"  - loss: {a['loss_shape']}")
        if a.get("score"):
            L.append(f"  - score: {a['score']}")
        if a["blocker"]:
            L.append(f"  - blocker: {a['blocker']}")
    L.append("")
    L.append("## Marker-sensitivity axis (model-only; the one axis needing no operator gold)")
    usable = manifest["lineages_usable"]
    if resolution_summary is not None:
        resolved = resolution_summary.get("resolved", 0)
        not_in_db = resolution_summary.get("not_in_db", 0)
        L.append(f"- resolution: {resolved} of {usable} usable lineages resolved")
        for status in sorted(resolution_summary):
            L.append(f"  - {status}: {resolution_summary[status]}")
        if not_in_db:
            L.append(f"  - COVERAGE LIMIT: {not_in_db} usable lineages carry no content_id in the "
                     "label layer (only Sexy/Utopia do), so they cannot be DB-resolved. Adding "
                     "content_ids to the B-row labels is a curation task — until then the marker "
                     "axis is a proof-of-function pilot, NOT the corpus baseline.")
    if marker is not None and marker.get("markers"):
        c1 = marker.get("comparable_pm1", marker["markers"])
        c2 = marker.get("comparable_pm2", marker["markers"])
        L.append(f"- measured over {marker['tracks']} resolved tracks / "
                 f"{marker['markers']} scored markers ({marker['skipped']} skipped — no baseline "
                 "decision to perturb):")
        L.append(f"  - +-1 beat flips over {c1} markers comparable at +-1 "
                 f"({marker['markers'] - c1} not comparable, excluded from this denominator) — "
                 f"family {marker['pm1']['family']}%, tier {marker['pm1']['tier']}%, "
                 f"darkness {marker['pm1']['darkness']}%")
        L.append(f"  - +-2 beat flips over {c2} markers comparable at +-2 "
                 f"({marker['markers'] - c2} not comparable, excluded from this denominator) — "
                 f"family {marker['pm2']['family']}%, tier {marker['pm2']['tier']}%, "
                 f"darkness {marker['pm2']['darkness']}%")
        ref = SOL_MARKER_REFERENCE
        L.append(f"  - SOL published reference (DIFFERENT sample — {ref['method']}):")
        L.append(f"    +-1 family {ref['pm1']['family']}%, tier {ref['pm1']['tier']}%, "
                 f"darkness {ref['pm1']['darkness']}%; "
                 f"+-2 family {ref['pm2']['family']}%, tier {ref['pm2']['tier']}%, "
                 f"darkness {ref['pm2']['darkness']}%")
        L.append("  - NOT like-for-like: a DIFFERENT track/marker set (and possibly a different "
                 "roll-up) than SOL's 15-track / 113-marker sample. Do NOT compare the percentages "
                 "or claim improvement/regression. The aggregation is documented in "
                 "marker_sensitivity(); this only proves the harness computes the axis through the "
                 "real planner.")
    else:
        L.append("- UNAVAILABLE this run (pass --resolve-db, or resolution was incomplete — see above).")
    L.append("")
    L.append("## What Stage 1 can and cannot score today")
    scored = [a["axis"] for a in availability
              if a["axis"] in REQUIRED_ACCURACY_AXES and a["available"]]
    unscored = [a["axis"] for a in availability
                if a["axis"] in REQUIRED_ACCURACY_AXES and not a["available"]]
    can = ("- CAN: validated/grouped/leak-safe corpus manifest, LOLO fold inventory, and "
           "(with --resolve-db) the marker-sensitivity baseline via the real planner.")
    if scored:
        can += (f" With --gold, real per-drop scoring is now AVAILABLE for: {', '.join(scored)} "
                "(operator gold vs the real planner's per-marker decision).")
    L.append(can)
    if unscored:
        L.append(f"- CANNOT: accuracy axes still without gold+scorer ({', '.join(unscored)}) — either no "
                 "structured per-drop operator gold, or the planner exposes no like-for-like output yet "
                 "(darkness bar<->beat / shape mapping, growl span, laser suitability are Stage-2). "
                 "Growl-centroid values are present/aligned/real-valued in the strict v4 cache — their "
                 "MUSICAL correctness is a Stage-2 validation item, not a backfill gap. Every unscored "
                 "axis reads UNAVAILABLE with a named blocker, never zero or PASS.")
    else:
        L.append("- All required accuracy axes have gold + a scorer this run (see per-axis section).")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_corpus(labels_path: str) -> tuple[list[Entry], list[Lineage], list[Resolution]]:
    """Load → normalize → lineages → DB-resolve (READ-ONLY). Shared by the template
    emitter. Raises on any failure — fail loud, no marker-axis degrade path here."""
    entries = normalize(load_labels(labels_path))
    lineages = build_lineages(entries)
    db_path = str(Path("~/Library/Pioneer/rekordbox/master.db").expanduser())
    db_index = _load_db_index(db_path)
    resolutions = resolve_lineages(lineages, db_index)
    return entries, lineages, resolutions


def run(labels_path: str, *, resolve_db: bool, head: str,
        gold_path: Optional[str] = None) -> tuple[str, bool]:
    """Return (report_text, partial). Never writes anything (except a caller's
    --report). `gold_path` (AWR-205) requires resolve_db and fails LOUD on any
    schema violation — it never degrades to a success-shaped report."""
    if gold_path and not resolve_db:
        raise ValueError("--gold requires --resolve-db (gold scoring needs real model outputs)")
    rows = load_labels(labels_path)
    label_sha = hashlib.sha256(Path(labels_path).read_bytes()).hexdigest()[:16]
    entries = normalize(rows)
    lineages = build_lineages(entries)
    warnings = (validate_exclusions(entries)
                + amendment_warnings(entries)
                + identity_warnings(lineages))
    manifest = build_manifest(entries, lineages)
    folds = build_folds(lineages)

    marker: Optional[dict[str, Any]] = None
    resolution_summary: Optional[dict[str, int]] = None
    marker_scored: Optional[int] = None
    marker_comparable: Optional[int] = None
    resolutions: list[Resolution] = []
    accuracy_scores: Optional[dict[str, dict[str, Any]]] = None
    gold_sha: Optional[str] = None
    gold_coverage: Optional[dict[str, int]] = None
    if resolve_db:
        db_path = str(Path("~/Library/Pioneer/rekordbox/master.db").expanduser())
        try:
            db_index = _load_db_index(db_path)
            from rb_ss_bridge_v2.lighting_moments_v2 import build_track_plan
            resolutions = resolve_lineages(lineages, db_index)
            resolution_summary = {}
            for r in resolutions:
                resolution_summary[r.status] = resolution_summary.get(r.status, 0) + 1
            marker = marker_sensitivity(resolutions, build_track_plan)
            # availability keys off markers SCORED *and* at least one COMPARABLE
            # +-1/+-2 perturbation, not resolved-track count: a track can resolve,
            # even produce baseline decisions, yet have zero comparable perturbations
            # (both flip rates come back None) — that must read UNAVAILABLE (findings 3/4).
            marker_scored = marker.get("markers", 0)
            marker_comparable = marker.get("comparable_pm1", 0) + marker.get("comparable_pm2", 0)
        except Exception as exc:  # honest degrade: report the blocker, never fake a score
            resolution_summary = {"error": 0}
            warnings.append(f"--resolve-db failed ({type(exc).__name__}: {exc}); marker axis UNAVAILABLE")
            marker_scored = 0
            marker_comparable = 0
            if gold_path:
                raise   # gold must fail loud, never degrade to a success-shaped report
        if gold_path:
            from rb_ss_bridge_v2.lighting_moments_v2 import build_track_plan
            gold_bytes = Path(gold_path).read_bytes()
            gold_sha = hashlib.sha256(gold_bytes).hexdigest()[:16]
            marker_index = {(mk.lineage, mk.beat): mk for mk in enumerate_markers(resolutions)}
            gold_result = validate_gold(json.loads(gold_bytes.decode("utf-8")), marker_index)
            accuracy_scores = score_accuracy_axes(gold_result, resolutions, build_track_plan)
            gold_coverage = {"labeled": gold_result["labeled"], "total": gold_result["total"]}

    availability = axis_availability(marker_scored, marker_comparable, accuracy_scores=accuracy_scores)
    report = render_report(
        head=head, labels_path=labels_path, label_sha=label_sha,
        manifest=manifest, warnings=warnings, folds=folds,
        availability=availability, marker=marker, resolution_summary=resolution_summary,
        gold_sha=gold_sha, gold_coverage=gold_coverage,
    )
    partial = is_partial(availability)   # marker/drop_classification never complete Stage 1
    return report, partial


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stage-1 EAR benchmark harness (AWR-200), read-only.")
    ap.add_argument("--labels", default=DEFAULT_LABELS,
                    help=f"labels JSONL path (default: {DEFAULT_LABELS} if present)")
    ap.add_argument("--resolve-db", action="store_true",
                    help="opt-in: resolve tracks via Rekordbox master.db (READ-ONLY) and compute "
                         "the marker-sensitivity axis. Off by default.")
    ap.add_argument("--report", default="",
                    help="write the report to this path instead of stdout")
    ap.add_argument("--head", default="unknown",
                    help="HEAD sha to stamp into the report (caller-provided; determinism)")
    ap.add_argument("--emit-gold-template", default="", metavar="OUT.json",
                    help="AWR-205: emit an empty, provenance-keyed hybrid gold-label template over "
                         "the resolved marker set (requires --resolve-db; refuses to clobber a filled "
                         "file). Keep OUT.json under local/ — it is gitignored.")
    ap.add_argument("--gold", default="",
                    help="AWR-205: score against a FILLED gold-label file (requires --resolve-db). "
                         "Strict fail-closed schema validation; gold never reaches the planner.")
    args = ap.parse_args(argv)

    labels_path = args.labels
    if labels_path == DEFAULT_LABELS and not Path(labels_path).is_file():
        print(f"error: default labels not found at {labels_path}; pass --labels PATH", file=sys.stderr)
        return 2

    if args.emit_gold_template:
        if not args.resolve_db:
            print("error: --emit-gold-template requires --resolve-db", file=sys.stderr)
            return 2
        label_sha = hashlib.sha256(Path(labels_path).read_bytes()).hexdigest()[:16]
        _entries, _lineages, resolutions = _resolve_corpus(labels_path)
        obj = build_gold_template(resolutions, args.head, label_sha)
        write_gold_template(obj, args.emit_gold_template)   # raises if it would clobber labels
        print(f"wrote {args.emit_gold_template}: {obj['_header']['markers']} markers over "
              f"{obj['_header']['lineages']} resolved lineages (all is_genuine_drop null)")
        return 0

    if args.gold and not args.resolve_db:
        print("error: --gold requires --resolve-db", file=sys.stderr)
        return 2

    report, _partial = run(labels_path, resolve_db=args.resolve_db, head=args.head,
                           gold_path=(args.gold or None))
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"wrote {args.report}")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    # Allow `python3 tools/spectral_ear_benchmark.py` to import the package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
    raise SystemExit(main())
