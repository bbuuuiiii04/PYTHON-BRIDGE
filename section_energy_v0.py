"""Per-section energy grades — energy-fabric stage E2 (AWR-288), STATUS-ONLY.

**Describes sound; never times or triggers a cue.** At E2 there is NO consumer:
no LED / laser / SoundSwitch module may read these grades (a static import-fence
test enforces the allowlist). Absent / short / malformed data ⇒ `None` or `[]` —
never a fabricated grade. Constants are pinned; changing any — including the gate
thresholds — is a spec amendment with exec sign-off, NEVER an implementation
decision to make a run or test pass.

Unlike E1's `track_weight_v0`, this module IS runtime-imported (by
`state_manager.py` on the ANLZ worker thread), so it stays pure: stdlib only, and
the segment builders (`smart_phrasing.build_phrase_segments_from_markers`,
`spectral_profile.section_map`) are imported LAZILY inside `grade_sections` to
avoid any import-order coupling at bridge startup. The ONLY I/O is
`load_track_weight_store()` — worker / offline threads only, NEVER the push loop.

Two grades per section:
- `within_track` = the section's mean `full_db` mapped through the same
  loudness-relative span the repo's section tiers use (−8 dB → 0.0, −3 dB → 1.0,
  measured against the track's own `loudness_ref_db`). Exactly gain-invariant: a
  uniform per-track mastering offset shifts the section level and the reference
  together and cancels.
- `library_scaled` = `within_track × track_weight` (the ladder's §B.2 product
  law), or `None` when the E1 track-weight store is missing / refused.

E1REV closing law, enforced by construction: `load_track_weight_store()` returns
None unless the file parses, `schema_version == 1`, `accepted is True`, and
`tracks`/`distribution` are present dicts — so an `accepted: false` / missing /
malformed store yields no library-scaled grade, never a fabricated one.
"""
from __future__ import annotations

import json
import math
from typing import Any, Optional

# ---- pinned constants (a spec amendment moves any of these, never the impl) --
SECTION_QUIET_OFFSET_DB = -8.0   # same values as spectral_profile section tiers
SECTION_LOUD_OFFSET_DB = -3.0    # (NOT imported — runtime coupling stays one-way)
MIN_SECTION_BEATS = 4
STORE_SCHEMA_VERSION = 1
COVERAGE_GATE = 0.95             # G1, by_genre (Part D)
SPREAD_GATE_FRACTION = 0.90      # G2, by_genre (Part D)
SPREAD_MIN = 0.10                # G2 per-track within_track max-min
MIN_ACCEPT_N = 100               # G-gate corpus floor (== E1's MIN_ACCEPT_N)


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def load_track_weight_store(path) -> "Optional[dict]":
    """Refusal gate (Absolute Rules / E1REV law): the parsed E1 store dict, or
    None. Never raises on bad content — OSError / JSONDecodeError / shape
    problems all become a reasoned None."""
    try:
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(store, dict):
        return None
    if store.get("schema_version") != STORE_SCHEMA_VERSION:
        return None
    if store.get("accepted") is not True:
        return None
    if not isinstance(store.get("tracks"), dict):
        return None
    if not isinstance(store.get("distribution"), dict):
        return None
    return store


def store_track_weight(store: "dict", cache_key: str) -> "Optional[float]":
    """`store["tracks"][cache_key]["track_weight"]` as a finite float, else None."""
    try:
        tw = store["tracks"][cache_key]["track_weight"]
        tw = float(tw)
    except (KeyError, TypeError, ValueError):
        return None
    return tw if math.isfinite(tw) else None


def _normalized_segments(v4, anlz_drops, anlz_buildups, anlz_breakdowns):
    """(start, end_exclusive, label) integer beat ranges from the marker phrase
    segments, falling back to the audio-derived section map, then []. Lazy
    imports keep this module's top level stdlib-only."""
    from rb_ss_bridge_v2 import smart_phrasing  # noqa: PLC0415
    segs = smart_phrasing.build_phrase_segments_from_markers(
        list(anlz_buildups), list(anlz_drops), list(anlz_breakdowns),
        [], int(v4.n_beats))
    out = []
    for s in segs:
        out.append((int(s.start_beat), int(s.end_beat), str(s.label)))
    if out:
        return out
    from rb_ss_bridge_v2 import spectral_profile  # noqa: PLC0415
    blocks = spectral_profile.section_map(
        v4, drops=anlz_drops, buildups=anlz_buildups, breakdowns=anlz_breakdowns)
    for b in blocks:
        # section_map end_beat is inclusive (b-1); normalize to exclusive.
        out.append((int(b["start_beat"]), int(b["end_beat"]) + 1, "other"))
    return out


def grade_sections(v4, *, anlz_drops, anlz_buildups, anlz_breakdowns,
                   track_weight: "Optional[float]") -> "list[dict]":
    """The E2 core. Returns a list of self-describing section grades, or [] on
    missing `loudness_ref_db` / empty-or-short series / non-finite values."""
    scalars = getattr(v4, "scalars", None) or {}
    ref = scalars.get("loudness_ref_db")
    if ref is None:
        return []
    try:
        ref = float(ref)
    except (TypeError, ValueError):
        return []
    if not math.isfinite(ref):
        return []
    series = getattr(v4, "series", None) or {}
    full = series.get("full_db")
    if not full:
        return []
    n = int(getattr(v4, "n_beats", 0) or 0)
    if n <= 0 or len(full) < n:
        return []

    span = SECTION_LOUD_OFFSET_DB - SECTION_QUIET_OFFSET_DB          # 5.0 dB
    grades: "list[dict]" = []
    for start, end, label in _normalized_segments(
            v4, anlz_drops, anlz_buildups, anlz_breakdowns):
        s = max(0, start)
        e = min(n, end)
        if e - s < MIN_SECTION_BEATS:
            continue
        beats = full[s:e]
        if not beats or not all(isinstance(x, (int, float)) and math.isfinite(x)
                                for x in beats):
            continue
        rel = (sum(beats) / len(beats)) - ref
        within = _clip01((rel - SECTION_QUIET_OFFSET_DB) / span)
        lib = (within * track_weight
               if isinstance(track_weight, (int, float))
               and math.isfinite(track_weight) else None)
        grades.append({"start_beat": s, "end_beat": e, "label": label,
                       "within_track": within, "library_scaled": lib})
    return grades


def current_section(grades: "list[dict]", abs_beat: float) -> "Optional[dict]":
    """The section containing `abs_beat` ([start, end)), or None. Linear scan —
    at most a few dozen sections."""
    for g in grades:
        if g["start_beat"] <= abs_beat < g["end_beat"]:
            return g
    return None


def gates_verdict(n_by_genre_eligible: int, n_graded: int,
                  n_spread_ok: int) -> "tuple[bool, str]":
    """G1/G2 offline verdict. Precedence: corpus floor → G1 coverage → G2 spread.
    `n_by_genre_eligible` = by_genre tracks with BOTH a v4 entry AND an accepted-
    store row (E2REV F1); G1 polices segmentation/grade-math holes only."""
    if n_by_genre_eligible < MIN_ACCEPT_N:
        return (False, "insufficient_corpus")
    if n_graded / n_by_genre_eligible < COVERAGE_GATE:
        return (False, "insufficient_coverage")
    if n_graded <= 0 or n_spread_ok / n_graded < SPREAD_GATE_FRACTION:
        return (False, "flat_grades")
    return (True, "ok")
