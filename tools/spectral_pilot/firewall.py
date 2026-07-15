"""Feature + metadata firewall for the Phase-0 pilot (spec B5).

``FrozenFeatureRow`` is the ONLY thing a predictor sees about the query marker,
plus a list of ``EligibleDevelopmentRow``. Both hold only allowlisted acoustic/
structure fields; their constructors reject unknown keys, so a stray ``title``,
``path``, ``content_id`` or old ``label`` never crosses the boundary (test D4).

The two grouping keys (``recording_lineage_id`` / ``audio_duplicate_group``) are
*structure used only to drop same-lineage neighbours* — they are never placed in
the distance vector. ``marker_beat`` is the numeric locator B5 permits for
slicing audio; it is likewise never a feature.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Candidate C positive allowlist, exact order (spec B4). These 17 acoustic/
# structure descriptors are the only values a predictor may compute distance on.
ALLOWLIST = (
    "sub_db", "bass_db", "mid_db", "high_db", "air_db", "full_db", "low_swing_db",
    "attack_low_p90", "perc_low", "harm_ratio", "centroid_hz", "growl_flatness",
    "sustain_mid_db_d8", "sustain_high_db_d8", "onset_density_mh", "fluxsum_mh",
    "pre_gap_beats",
)
ALLOWLIST_SET = frozenset(ALLOWLIST)

# Anything a predictor may NEVER receive (spec B5). Kept explicit so the guard
# test and the constructor error message both name the offenders.
FORBIDDEN_KEYS = frozenset(
    {
        "title", "artist", "playlist", "genre", "cover_art", "content_id",
        "content_id_locator", "path", "path_text", "notes", "marker_name",
        "marker_type", "label", "human_label", "prediction", "confidence",
        "neighbour_id", "calibration_answer", "split_score",
    }
)


def _finite_vector(values: dict) -> dict:
    """Return the allowlist vector, rejecting non-numeric or nonfinite entries."""
    out = {}
    for k in ALLOWLIST:
        if k not in values:
            raise ValueError(f"FrozenFeatureRow missing allowlist field: {k}")
        v = values[k]
        t = type(v)
        if t not in (int, float):  # exact-type: reject numpy scalars + str
            raise TypeError(f"allowlist field {k} must be a builtin int/float, got {t!r}")
        if not math.isfinite(v):
            raise ValueError(f"allowlist field {k} is nonfinite: {v!r}")
        out[k] = float(v)
    return out


def _reject_forbidden(keys) -> None:
    bad = set(keys) & FORBIDDEN_KEYS
    if bad:
        raise ValueError(f"forbidden metadata reached the predictor firewall: {sorted(bad)}")


@dataclass(frozen=True)
class FrozenFeatureRow:
    """The query marker as a predictor sees it (spec B5)."""
    features: dict                          # allowlist -> float (validated)
    coverage: float
    marker_beat: int
    query_lineage_id: str                   # self-exclusion only, never a feature
    query_duplicate_group: str              # self-exclusion only, never a feature

    def __post_init__(self):
        _reject_forbidden(self.features.keys())      # a leak in the raw ctor still raises
        object.__setattr__(self, "features", _finite_vector(self.features))
        if not math.isfinite(float(self.coverage)):
            raise ValueError("coverage must be finite")

    @classmethod
    def from_window(cls, window: dict, *, query_lineage_id, query_duplicate_group, marker_beat):
        """Build from a ``drop_window_vector`` dict, rejecting any forbidden key."""
        _reject_forbidden(window.keys())
        return cls(
            features={k: window[k] for k in ALLOWLIST if k in window},
            coverage=float(window.get("coverage", 0.0)),
            marker_beat=int(marker_beat),
            query_lineage_id=query_lineage_id,
            query_duplicate_group=query_duplicate_group,
        )

    def vector(self, retained) -> list:
        return [self.features[k] for k in retained]


def build_query_row(window, *, query_lineage_id, query_duplicate_group, marker_beat):
    """Construction seam (spec B4/B10). Returns ``(FrozenFeatureRow, [])`` on a clean
    window, or ``(None, reasons)`` when an allowlist field is MISSING / non-numeric /
    NONFINITE — so the caller emits a named abstention instead of crashing a freeze.

    A forbidden key still RAISES: a metadata leak is never an abstention.
    """
    _reject_forbidden(window.keys())
    reasons = []
    for k in ALLOWLIST:
        if k not in window:
            reasons.append(f"missing_field:{k}")
            continue
        v = window[k]
        if type(v) not in (int, float):
            reasons.append(f"nonnumeric_field:{k}")
        elif not math.isfinite(v):
            reasons.append(f"nonfinite_field:{k}")
    if reasons:
        return None, reasons
    return FrozenFeatureRow(
        features={k: float(window[k]) for k in ALLOWLIST},
        coverage=float(window.get("coverage", 0.0)),
        marker_beat=int(marker_beat),
        query_lineage_id=query_lineage_id,
        query_duplicate_group=query_duplicate_group,
    ), []


@dataclass(frozen=True)
class EligibleDevelopmentRow:
    """A development neighbour: allowlist vector + grouping keys + per-axis targets.

    ``targets`` may be partial — an incomplete row is a neighbour only for the
    axes it actually carries (spec B3 development manifest rule).
    """
    features: dict
    coverage: float
    recording_lineage_id: str
    audio_duplicate_group: str
    track_instance_id: str
    marker_beat: int
    targets: dict = field(default_factory=dict)   # {"genuine": .., "hardness": .., "family": ..}

    def __post_init__(self):
        _reject_forbidden(self.features.keys())      # a candidate-fed leak still raises
        object.__setattr__(self, "features", _finite_vector(self.features))

    @classmethod
    def from_window(cls, window, *, recording_lineage_id, audio_duplicate_group,
                    track_instance_id, marker_beat, targets):
        _reject_forbidden(window.keys())
        _reject_forbidden(targets.keys() - {"genuine", "hardness", "family"})
        return cls(
            features={k: window[k] for k in ALLOWLIST if k in window},
            coverage=float(window.get("coverage", 0.0)),
            recording_lineage_id=recording_lineage_id,
            audio_duplicate_group=audio_duplicate_group,
            track_instance_id=track_instance_id,
            marker_beat=int(marker_beat),
            targets=dict(targets),
        )

    def vector(self, retained) -> list:
        return [self.features[k] for k in retained]
