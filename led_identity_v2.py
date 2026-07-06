"""Pure identity helpers for LIGHTING ENGINE v2 Feature 1.

No runtime I/O happens here except ``IdentityStore.load``. Bass normalization is
configured live; the default p5/p95 anchors are 0.5856/0.9688 from
``python3 tools/calibrate_identity_v2.py`` over 666 valid local spectral v4
cache entries on 2026-07-06.
"""
from __future__ import annotations

import colorsys
import json
import logging
import os
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from typing import Iterable, NamedTuple

from .led_models import ZoneRampConfig

log = logging.getLogger(__name__)

NORM_ANCHORS = {
    "punch": (0.4298, 1.2),
    "attack_low_p90": (6.7, 38.875),
    "grit": (0.0137, 0.0776),
    "onset_mh_p90": (2.0, 4.0),
    "brightness_med": (341.8, 1456.5),
    "synth_rate": (0.053, 0.725),
    "growl_timbre_p90": (0.1528, 0.377),
    "drama": (7.0, 23.375),
}
AGGRESSION_SPLIT = 0.418
EMBERCORE_DISTORTION = 0.75
ION_LUMINANCE = 0.52
GLACIER_LUMINANCE = 0.40
DEEP_POOL_LUMINANCE = 0.28
ZONES = ("GLACIER", "DEEP_POOL", "TWILIGHT", "ION", "VOLT", "EMBERCORE")
ALL_ZONES = ZONES + ("NEUTRAL",)
SMOOTH_ZONES = frozenset({"GLACIER", "DEEP_POOL", "TWILIGHT", "NEUTRAL"})
HUE_SLOTS = 16
DEPTH_VARIANTS = 3
WHITE = (255, 255, 255)


class Claim(NamedTuple):
    rank: int
    start_beat: float
    end_beat: float
    tag: str


RANKS = {
    "manual": 0,
    "drop": 1,
    "landing": 2,
    "dip": 3,
    "blend_resolve": 4,
    "palate_reset": 5,
    "bloom": 6,
    "stinger": 7,
    "texture": 8,
    "simmer": 9,
}


@dataclass(frozen=True)
class Dressing:
    zone: str
    hue_slot: int
    depth_variant: int
    sat_floor: float
    span: float
    budget: float
    style: str
    slot_rgbs: tuple[tuple[int, int, int], ...]


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * clip(t)


def norm(v: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return clip((float(v) - lo) / (hi - lo))


def identity_scores(
    axes: dict[str, float],
    scalars: dict[str, float],
    synth_rate: float,
) -> dict[str, float]:
    a = NORM_ANCHORS
    aggression = (
        0.35 * norm(axes["punch"], *a["punch"])
        + 0.25 * norm(scalars["attack_low_p90"], *a["attack_low_p90"])
        + 0.25 * norm(axes["grit"], *a["grit"])
        + 0.15 * norm(scalars["onset_mh_p90"], *a["onset_mh_p90"])
    )
    luminance = (
        0.60 * norm(scalars["brightness_med"], *a["brightness_med"])
        + 0.40 * norm(synth_rate, *a["synth_rate"])
    )
    distortion = norm(scalars["growl_timbre_p90"], *a["growl_timbre_p90"])
    return {
        "aggression": clip(aggression),
        "luminance": clip(luminance),
        "distortion": clip(distortion),
    }


def assign_zone(scores: dict[str, float]) -> str:
    aggression = float(scores["aggression"])
    luminance = float(scores["luminance"])
    distortion = float(scores["distortion"])
    if aggression >= AGGRESSION_SPLIT:
        if distortion >= EMBERCORE_DISTORTION:
            return "EMBERCORE"
        if luminance >= ION_LUMINANCE:
            return "ION"
        return "VOLT"
    if luminance >= GLACIER_LUMINANCE:
        return "GLACIER"
    if luminance < DEEP_POOL_LUMINANCE:
        return "DEEP_POOL"
    return "TWILIGHT"


def content_key(content_id: str, filepath: str) -> str:
    if content_id:
        return str(content_id)
    return "path:" + os.path.realpath(str(filepath))


def content_hash(key: str) -> int:
    return int.from_bytes(blake2b(str(key).encode("utf-8"), digest_size=8).digest(), "big")


def _clamp_rgb(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(round(v)))) for v in rgb)  # type: ignore[return-value]


def _ramp_at(ramp: tuple[tuple[int, int, int], ...], t: float) -> tuple[int, int, int]:
    t = clip(t)
    if t <= 0.5:
        local = t / 0.5
        a, b = ramp[0], ramp[1]
    else:
        local = (t - 0.5) / 0.5
        a, b = ramp[1], ramp[2]
    return _clamp_rgb(tuple(a[i] + (b[i] - a[i]) * local for i in range(3)))


def _adjust_rgb(
    rgb: tuple[int, int, int],
    hue_offset: float,
    sat_floor: float,
) -> tuple[int, int, int]:
    r, g, b = (v / 255.0 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    nr, ng, nb = colorsys.hsv_to_rgb((h + hue_offset) % 1.0, max(s, sat_floor), v)
    return _clamp_rgb((nr * 255, ng * 255, nb * 255))


def derive_dressing(
    zone: str,
    zone_cfg: ZoneRampConfig,
    key_hash: int,
    norm_bass: float,
    norm_drama: float,
    norm_punch: float,
) -> Dressing:
    hue_slot = key_hash % HUE_SLOTS
    depth_variant = (key_hash // HUE_SLOTS) % DEPTH_VARIANTS
    sat_floor = clip(lerp(0.55, 0.85, norm_bass) + (-0.05, 0.0, 0.05)[depth_variant], 0.40, 0.95)
    span = lerp(0.8, 0.35, norm_bass)
    hue_offset = ((hue_slot / (HUE_SLOTS - 1)) - 0.5) * zone_cfg.hue_span
    base_ramp = tuple(zone_cfg.base_ramp)
    accent_ramp = tuple(zone_cfg.accent_ramp)
    base_slots = tuple(
        _adjust_rgb(_ramp_at(base_ramp, 1.0 - span * (2 - i) / 2.0), hue_offset, sat_floor)
        for i in range(3)
    )
    accent_slots = tuple(_adjust_rgb(rgb, hue_offset, sat_floor) for rgb in accent_ramp)
    return Dressing(
        zone=zone,
        hue_slot=hue_slot,
        depth_variant=depth_variant,
        sat_floor=sat_floor,
        span=span,
        budget=lerp(0.3, 1.0, norm_drama),
        style="sharp" if norm_punch >= 0.6 else "flowing",
        slot_rgbs=base_slots + accent_slots + (WHITE,),
    )


def is_hard_pivot(zone_a: str, zone_b: str) -> bool:
    return (zone_a in SMOOTH_ZONES) != (zone_b in SMOOTH_ZONES)


def _overlaps(a: Claim, b: Claim) -> bool:
    return a.start_beat < b.end_beat and b.start_beat < a.end_beat


def claim_allowed(new: Claim, active: Iterable[Claim]) -> bool:
    return not any(_overlaps(new, cur) and cur.rank < new.rank for cur in active)


def record_from_dressing(
    dressing: Dressing,
    *,
    key_hash: int,
    base: str,
    scores: dict[str, float] | None,
    norm_inputs: dict[str, float],
    analysis_rev: str = "v4",
    correction: dict[str, str] | None = None,
) -> dict:
    return {
        "zone": dressing.zone,
        "hue_slot": dressing.hue_slot,
        "depth_variant": dressing.depth_variant,
        "sat_floor": dressing.sat_floor,
        "span": dressing.span,
        "budget": dressing.budget,
        "style": dressing.style,
        "base": base,
        "scores": dict(scores or {}),
        "analysis_rev": analysis_rev,
        "correction": correction,
        "norm_inputs": {
            "bass": float(norm_inputs.get("bass", 0.5)),
            "drama": float(norm_inputs.get("drama", 0.5)),
            "punch": float(norm_inputs.get("punch", 0.0)),
        },
        "key_hash": int(key_hash),
    }


def provisional_record_for_key(key: str) -> dict:
    key_hash = content_hash(key)
    return {
        "zone": "NEUTRAL",
        "hue_slot": key_hash % HUE_SLOTS,
        "depth_variant": (key_hash // HUE_SLOTS) % DEPTH_VARIANTS,
        "sat_floor": 0.70,
        "span": 0.575,
        "budget": 0.65,
        "style": "flowing",
        "base": "provisional",
        "scores": {},
        "analysis_rev": "v4",
        "correction": None,
        "norm_inputs": {"bass": 0.5, "drama": 0.5, "punch": 0.0},
        "key_hash": key_hash,
    }


class IdentityStore:
    def __init__(
        self,
        tracks: dict[str, dict] | None = None,
        *,
        degraded: bool = False,
        write_allowed: bool = True,
    ) -> None:
        self._tracks = {str(k): dict(v) for k, v in (tracks or {}).items() if isinstance(v, dict)}
        self.degraded = bool(degraded)
        self.write_allowed = bool(write_allowed)

    @classmethod
    def load(cls, path: str | Path) -> "IdentityStore":
        target = Path(path)
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning(
                "[LED] identity-store-load-failed path=%s err=%s",
                target,
                type(exc).__name__,
            )
            return cls(degraded=True, write_allowed=False)
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("tracks"), dict):
            log.warning("[LED] identity-store-malformed path=%s", target)
            return cls(degraded=True, write_allowed=False)
        return cls(raw["tracks"])

    def to_dict(self) -> dict:
        return {"version": 1, "tracks": {key: dict(value) for key, value in self._tracks.items()}}

    def get(self, key: str) -> dict | None:
        record = self._tracks.get(str(key))
        return dict(record) if record is not None else None

    def freeze(self, key: str, record: dict) -> bool:
        key = str(key)
        incoming = dict(record)
        existing = self._tracks.get(key)
        if existing is None:
            self._tracks[key] = incoming
            return True
        if existing.get("base") == "measured":
            return False
        if incoming.get("base") != "measured":
            return False
        correction = existing.get("correction")
        self._tracks[key] = incoming
        self._tracks[key]["correction"] = correction
        return True

    def set_correction(self, key: str, zone: str) -> bool:
        key = str(key)
        if zone not in ALL_ZONES:
            raise ValueError(f"unknown zone: {zone}")
        if key not in self._tracks:
            self._tracks[key] = provisional_record_for_key(key)
        record = self._tracks[key]
        correction = {"zone": zone}
        if record.get("correction") == correction:
            return False
        record["correction"] = correction
        return True

    def clear_correction(self, key: str) -> bool:
        record = self._tracks.get(str(key))
        if not record or record.get("correction") is None:
            return False
        record["correction"] = None
        return True


class LedIdentityV2:
    """Tiny facade so contract checks have one stable symbol to route to."""

    content_key = staticmethod(content_key)
    content_hash = staticmethod(content_hash)
    identity_scores = staticmethod(identity_scores)
    assign_zone = staticmethod(assign_zone)
    derive_dressing = staticmethod(derive_dressing)
    is_hard_pivot = staticmethod(is_hard_pivot)
    claim_allowed = staticmethod(claim_allowed)
