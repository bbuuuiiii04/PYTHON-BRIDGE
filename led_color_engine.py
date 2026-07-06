"""LED Color Engine — M1 implementation.

Pure, self-contained module.  No imports from other bridge modules except
led_models and bridge_log (perf("led.palette") emits at palette-change
commits only — AWR-125; bridge_log import has no side effects).  No other
side-effects, no I/O.

Public API (exactly as M1b integration expects):

    class LedColorEngine:
        def __init__(self, config: ColorEngineConfig, *, set_seed: int | None = None) -> None
        @property
        def enabled(self) -> bool
        def begin_dispatch(self, *, active_deck: int, load_gen: int, content_id: str,
                           filepath: str, role: str, section_id: str, cycle: int,
                           moments_blocked: bool = False, scripted: bool = False) -> None
        def diy_eligible(self, look_name: str) -> bool
        def resolve_color(self, *, role: str, section_id: str, cycle: int, look_name: str,
                          color_source: str, multi: bool = False) -> dict[str, Any]
        # live-control stubs:
        def lock(self) -> None
        def unlock(self) -> None
        def set_palette(self, name: str) -> None
        def queue_palette(self, name: str) -> None
        def unqueue_palette(self, name: str) -> None
        def shift(self) -> None
        def snapshot(self) -> dict

Spec references:
  §1  — linear hue scale + p_to_rgb piecewise lerp
  §2  — engine state, palette/dwell, drop-snap, per-track focus, per-cue resolution
  §6  — DIY eligibility
  §15.2 — dispatch-driven track detection
  §15.3 — hashed seeds, two independent RNG instances
  §15.6 — live-control precedence; diy_eligible hooks

NOTE: White accents as a *standalone random event* (a separate white_chance knob
that spontaneously fires white on any cue) are OUT OF M1 SCOPE — §7 defines no
such config field, and inventing it would add unsolicited config.  The per-palette
`white` field blends the resolved p→RGB toward (255,255,255); that IS implemented.
A future §8 operator-surface feature could add white accent triggering via a
separate config key in M3+.
"""
from __future__ import annotations

import collections
import colorsys
import random
import struct
from hashlib import blake2b
from typing import Any

from . import bridge_log
from .led_models import ColorEngineConfig, Palette
from .led_identity_v2 import (
    Claim,
    Dressing,
    RANKS,
    claim_allowed,
    content_hash,
    derive_dressing,
    is_hard_pivot,
)


# ---------------------------------------------------------------------------
# Scale / interpolation helpers
# ---------------------------------------------------------------------------

def _scale_stop_positions(scale_stops: dict[str, tuple[int, int, int]]) -> dict[str, float]:
    """Assign each stop in insertion order an evenly-spaced position in [0,1]."""
    stops = list(scale_stops.keys())
    n = len(stops)
    if n == 1:
        return {stops[0]: 0.0}
    return {name: i / (n - 1) for i, name in enumerate(stops)}


def _p_to_rgb(
    p: float,
    scale_stops: dict[str, tuple[int, int, int]],
    stop_positions: dict[str, float],
) -> tuple[int, int, int]:
    """Piecewise-linear interpolation between adjacent scale stops.

    p is clamped to [0, 1].  The scale never passes through orange/yellow
    as resting positions because the stops themselves exclude those hues;
    interpolation between adjacent stops (green→cyan, cyan→blue, …)
    travels through the cool-color corridor only.
    """
    p = max(0.0, min(1.0, p))
    stops = list(scale_stops.keys())
    positions = [stop_positions[s] for s in stops]
    rgbs = [scale_stops[s] for s in stops]

    # Edge cases
    if p <= positions[0]:
        return rgbs[0]
    if p >= positions[-1]:
        return rgbs[-1]

    # Find the two adjacent stops bracketing p
    for i in range(len(positions) - 1):
        lo, hi = positions[i], positions[i + 1]
        if lo <= p <= hi:
            if hi == lo:
                return rgbs[i]
            t = (p - lo) / (hi - lo)
            r = int(round(rgbs[i][0] + t * (rgbs[i + 1][0] - rgbs[i][0])))
            g = int(round(rgbs[i][1] + t * (rgbs[i + 1][1] - rgbs[i][1])))
            b = int(round(rgbs[i][2] + t * (rgbs[i + 1][2] - rgbs[i][2])))
            return (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
            )
    return rgbs[-1]


def _blend_white(rgb: tuple[int, int, int], white: float) -> tuple[int, int, int]:
    """Lerp rgb toward (255,255,255) by white amount ∈ [0,1]."""
    w = max(0.0, min(1.0, white))
    r = int(round(rgb[0] + w * (255 - rgb[0])))
    g = int(round(rgb[1] + w * (255 - rgb[1])))
    b = int(round(rgb[2] + w * (255 - rgb[2])))
    return (r, g, b)


def _hue_to_rgb(hue: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 1.0, 1.0)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------

def _blake2b_int(data: str) -> int:
    """Hash a UTF-8 string to a 64-bit unsigned int via blake2b."""
    return int.from_bytes(
        blake2b(data.encode("utf-8"), digest_size=8).digest(), "big"
    )


def _rng_from_seed(seed: int) -> random.Random:
    rng = random.Random()
    rng.seed(seed)
    return rng


# ---------------------------------------------------------------------------
# Weighted random selection helper
# ---------------------------------------------------------------------------

def _weighted_choice(
    rng: random.Random,
    choices: list[str],
    weights: list[float],
    exclude: str | None = None,
    bias: float = 1.0,
) -> str:
    """Pick one item from choices by weight.

    If bias != 1.0: effective_weight = weight ** (1 / bias), so higher bias
    compresses high weights downward → rarer palettes become relatively more
    likely.  bias=1.0 is no-op.

    exclude: if set, that item is removed from the pool before selection.
    If the pool would be empty after exclusion, falls back to the full pool
    (shouldn't happen with ≥2 palettes).
    """
    paired = list(zip(choices, weights))
    if exclude is not None:
        filtered = [(c, w) for c, w in paired if c != exclude]
        if filtered:
            paired = filtered

    if bias != 1.0 and bias > 0:
        paired = [(c, w ** (1.0 / bias)) for c, w in paired]

    total = sum(w for _, w in paired)
    if total <= 0:
        return paired[0][0] if paired else choices[0]

    r = rng.random() * total
    cumulative = 0.0
    for c, w in paired:
        cumulative += w
        if r <= cumulative:
            return c
    return paired[-1][0]


# ---------------------------------------------------------------------------
# Per-track focus helpers
# ---------------------------------------------------------------------------

_FOCUS_MODES = ("mono", "lean", "full")


def _draw_focus(
    rng: random.Random,
    palette: Palette,
    lo_p: float,
    hi_p: float,
) -> tuple[float, float]:
    """Draw focus center fc and half-width fw for a track inside [lo_p, hi_p].

    Returns (fc, fw) where the effective focus window is [fc-fw, fc+fw]
    intersected with [lo_p, hi_p].

    For point palettes (lo_p == hi_p), returns (lo_p, 0.0) — no-op.
    """
    span = hi_p - lo_p
    if span <= 1e-9:
        return (lo_p, 0.0)

    # Choose mode
    modes = palette.focus_modes  # may be empty → full
    if modes:
        names = list(modes.keys())
        weights = [float(modes[n]) for n in names]
        total = sum(weights)
        if total <= 0:
            mode = "full"
        else:
            r = rng.random() * total
            cum = 0.0
            mode = names[-1]
            for nm, w in zip(names, weights):
                cum += w
                if r <= cum:
                    mode = nm
                    break
    else:
        mode = "full"

    if mode == "full":
        # spans the whole range
        fc = (lo_p + hi_p) / 2.0
        fw = span / 2.0
    elif mode == "lean":
        # narrow width near one end
        fw = span * rng.uniform(0.10, 0.25)
        # center near one end, leaving room for fw
        side = rng.choice([-1, 1])
        if side < 0:
            fc = lo_p + fw + rng.uniform(0.0, span * 0.20)
        else:
            fc = hi_p - fw - rng.uniform(0.0, span * 0.20)
        fc = max(lo_p + fw, min(hi_p - fw, fc))
    else:  # mono
        # zero width at one end
        fw = 0.0
        fc = rng.choice([lo_p, hi_p])

    return (fc, fw)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class LedColorEngine:
    """Stateful LED color engine — M1 milestone.

    Thread-safety: NOT thread-safe.  Callers must serialize access (as the
    state_manager dispatch thread already does for all LED state).
    """

    def __init__(
        self,
        config: ColorEngineConfig,
        *,
        set_seed: int | None = None,
    ) -> None:
        self._config = config

        # --- derive set_seed ---
        if set_seed is not None:
            self._set_seed = set_seed
        else:
            mode = config.set_seed_mode
            if mode == "random":
                self._set_seed = random.SystemRandom().getrandbits(63)
            elif mode.startswith("fixed:"):
                self._set_seed = int(mode.split(":", 1)[1])
            else:
                # fallback: random
                self._set_seed = random.SystemRandom().getrandbits(63)

        # Two independent RNG instances (§15.3 / M5)
        # journey_rng: palette selection, dwell, snap probability
        self._journey_rng: random.Random = _rng_from_seed(self._set_seed)
        # Note: per-cue rng is constructed on-demand from per-cue seeds

        # --- build stop positions (insertion order) ---
        self._stop_positions: dict[str, float] = _scale_stop_positions(
            config.scale_stops
        )

        # --- palette library ---
        self._palette_names: list[str] = list(config.palettes.keys())
        self._palette_weights: list[float] = [
            config.palettes[n].weight for n in self._palette_names
        ]

        # --- live-control state ---
        self._lock: bool = False
        self._queued_palette: str = ""
        self._hold_track: bool = False
        self._mode_override: dict[str, str] | None = None
        self._fade_from_p: float | None = None
        self._fade_target: str = ""
        self._fade_start_beat: float = 0.0
        self._fade_end_beat: float = 0.0

        # --- journey state ---
        self._current_palette: str = self._pick_palette()
        dwell = config.palettes[self._current_palette].dwell
        self._dwell_remaining: int = (
            dwell if dwell is not None else config.palette_dwell_tracks
        )
        self._anchor_p: float = self._palette_center(self._current_palette)

        # --- per-track state ---
        self._current_track_key: tuple[int, int] | None = None
        self._recent_keys: collections.deque[tuple[int, int]] = collections.deque(
            maxlen=3
        )
        self._current_track_seed: int = 0
        # focus window: (fc, fw)
        self._focus_fc: float = self._anchor_p
        self._focus_fw: float = 0.0

        # per-track drop tracking
        self._drop_section_index: int = 0
        self._last_drop_section_id: str = ""

        # Phase 3: previous color tracking for fades
        self._prev_color: dict[tuple[Any, ...], dict[str, Any]] = {}

        # LIGHTING ENGINE v2 state. Kept fully separate from v1 journey state.
        self._v2_cfg = config.v2 if config.v2 is not None and config.v2.enabled else None
        self._v2_active = bool(self._v2_cfg)
        self._v2_dressing: dict[int, Dressing] = {}
        self._v2_record: dict[int, dict[str, Any]] = {}
        self._v2_track_key_by_deck: dict[int, str] = {}
        self._v2_load_gen_by_deck: dict[int, int] = {}
        self._v2_current_deck: int = 0
        self._v2_current_track_key: tuple[int, int] | None = None
        self._v2_manual: str = ""
        self._v2_staged: tuple[str, float] | None = None
        self._v2_flip_fade: tuple[tuple[tuple[int, int, int], ...], float] | None = None
        self._v2_pending_flip_fade: tuple[tuple[tuple[int, int, int], ...], float] | None = None
        self._v2_reset_until: float | None = None
        self._v2_pending_reset_beats: float | None = None
        self._v2_bloomed: set[str] = set()
        self._v2_bloom_pending: tuple[tuple[tuple[int, int, int], ...], float] | None = None
        self._v2_bloom_until: float | None = None
        self._v2_claims: list[Claim] = []
        self._v2_first_seen_beat: float | None = None
        self._v2_now: float = 0.0
        self._v2_current_identity_key: str = ""
        self._v2_moments_blocked: bool = False
        self._v2_stand_down: bool = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def reset_fade_memory(self) -> None:
        """Clear previous color memory (fade endpoints) upon idle or emergency."""
        self._prev_color.clear()
        if self._v2_active:
            self._v2_flip_fade = None
            self._v2_pending_flip_fade = None
            self._v2_bloom_pending = None
            self._v2_bloom_until = None
            self._v2_pending_reset_beats = None
            self._v2_reset_until = None
            self._v2_first_seen_beat = None

    # ------------------------------------------------------------------
    # Dispatch-driven track + drop detection (§15.2)
    # ------------------------------------------------------------------

    def begin_dispatch(
        self,
        *,
        active_deck: int,
        load_gen: int,
        content_id: str,
        filepath: str,
        role: str,
        section_id: str,
        cycle: int,
        moments_blocked: bool = False,
        scripted: bool = False,
    ) -> None:
        """Called at the start of each automation dispatch (injection seam).

        Detects new audible track (via (active_deck, load_gen) key deque)
        and new drop sections.  Advances journey state accordingly.
        """
        self._v2_stand_down = bool(scripted and self._v2_active)
        if self._v2_active and not self._v2_stand_down:
            self._v2_begin_dispatch(
                active_deck=active_deck,
                load_gen=load_gen,
                content_id=content_id,
                filepath=filepath,
                role=role,
                section_id=section_id,
                cycle=cycle,
                moments_blocked=moments_blocked,
            )
            return

        track_key = (active_deck, load_gen)

        if track_key not in self._recent_keys:
            # --- NEW audible track ---
            self._current_track_key = track_key
            self._recent_keys.append(track_key)

            # Reseed per-track focus
            identifier = content_id or filepath or str(load_gen)
            self._current_track_seed = _blake2b_int(
                f"{self._set_seed}:{active_deck}:{identifier}"
            )

            # Reset drop tracking for this track
            self._drop_section_index = 0
            self._last_drop_section_id = ""
            if self._mode_override is None:
                self._hold_track = False
                self._fade_from_p = None
                self._fade_target = ""
            
            # Reset previous color memory
            self._prev_color.clear()

            if self._mode_override is None:
                if self._queued_palette:
                    name = self._queued_palette
                    self._queued_palette = ""
                    if name in self._config.palettes:
                        # Operator-queued palette commits here (on track change).
                        self._apply_palette_now(name, reason="operator")
                elif not self._lock:
                    self._dwell_remaining -= 1
                    if self._dwell_remaining <= 0:
                        new_palette = self._pick_palette()
                        self._apply_palette_now(new_palette, reason="dwell")

            # Reseed per-track focus (after palette may have changed)
            self._reseed_focus()

        if self._mode_override is not None:
            return

        # --- Drop section tracking ---
        if role == "drop":
            if section_id != self._last_drop_section_id:
                self._drop_section_index += 1
                self._last_drop_section_id = section_id

                # Evaluate snap (§2 Drop-snap)
                if (
                    not self._lock
                    and not self._hold_track
                    and self._drop_section_index in self._config.snap_eligible_drop_indices
                ):
                    if self._journey_rng.random() < self._config.big_shift_chance:
                        # re-pick a DIFFERENT palette, biased toward rarer ones
                        prev = self._current_palette
                        new_palette = self._pick_palette(
                            exclude=self._current_palette,
                            bias=self._config.big_shift_weight_bias,
                        )
                        self._current_palette = new_palette
                        self._anchor_p = self._palette_center(new_palette)
                        # NOTE: no dwell reset on snap — next track change handles it
                        # Reseed focus for this snapped palette
                        self._reseed_focus()
                        # AWR-125: snap deliberately bypasses _apply_palette_now
                        # (no dwell reset), so its palette-change record is
                        # emitted inline here.
                        bridge_log.perf(
                            "led.palette",
                            "palette %s->%s (%s)",
                            prev,
                            new_palette,
                            "drop_snap",
                            data={
                                "palette": new_palette,
                                "prev": prev,
                                "reason": "drop_snap",
                                "locked": self._lock,
                            },
                        )

    # ------------------------------------------------------------------
    # DIY eligibility (§6, §15.6)
    # ------------------------------------------------------------------

    def diy_eligible(self, look_name: str) -> bool:
        """Return True if the DIY look is eligible under the current palette.

        True when:
          - engine disabled (no filtering)
          - look has no tag (untagged = always eligible)
          - tag is a special sentinel: BIG_DROP_SIGNATURE, white, TODO, or
            contains '+' (compound) — conservatively always eligible in M1
          - tag names a stop that falls within the current palette p-interval
            expanded by palette.spread
        """
        if not self._config.enabled:
            return True

        tag = self._config.diy_color_tags.get(look_name)
        if tag is None:
            # Untagged → always eligible
            return True

        # Special sentinels → always eligible in M1
        if tag in ("BIG_DROP_SIGNATURE", "white", "TODO") or "+" in tag:
            return True

        # Map tag (a stop name) to p-position
        tag_p = self._stop_positions.get(tag)
        if tag_p is None:
            # Unknown stop → conservatively eligible
            return True

        # Current palette p-interval ± spread
        palette = self._config.palettes.get(self._current_palette)
        if palette is None:
            return True

        lo_p, hi_p = self._palette_p_interval(self._current_palette)
        spread = palette.spread
        lo_allowed = lo_p - spread
        hi_allowed = hi_p + spread

        return lo_allowed <= tag_p <= hi_allowed

    # ------------------------------------------------------------------
    # Color resolution (§2 Layer 1 spread + white)
    # ------------------------------------------------------------------

    def _focus_window(self, role: str) -> tuple[float, float]:
        """Compute the [focus_lo, focus_hi] p-window for the current palette.

        Shared by resolve_color and resolve_slot_colors so the focus math is
        defined exactly once.  Mirrors the original inline computation:
        the current palette p-interval, widened by the effective spread
        (role-spread widening when drama_by_role), clamped to the interval,
        with a lo>hi safety fallback to the full interval.

        Precondition: self._current_palette is a valid palette (callers verify
        ``palette is not None`` before calling).
        """
        lo_p, hi_p = self._palette_p_interval(self._current_palette)
        palette = self._config.palettes[self._current_palette]

        # Determine effective spread (widened for drops if drama_by_role)
        base_spread = palette.spread
        if self._config.drama_by_role:
            role_spread = self._config.role_spread.get(role, base_spread)
            effective_spread = max(base_spread, role_spread)
        else:
            effective_spread = base_spread

        # Focus window, clamped to palette interval
        fc = self._focus_fc
        fw = self._focus_fw

        focus_lo = max(lo_p, fc - fw - effective_spread)
        focus_hi = min(hi_p, fc + fw + effective_spread)
        # Ensure lo <= hi
        if focus_lo > focus_hi:
            focus_lo, focus_hi = lo_p, hi_p
        return (focus_lo, focus_hi)

    def resolve_color(
        self,
        *,
        role: str,
        section_id: str,
        cycle: int,
        look_name: str,
        color_source: str,
        multi: bool = False,
    ) -> dict[str, Any]:
        """Resolve a per-cue color injection dict.

        Returns {} (inject nothing) if:
          - engine disabled
          - color_source != "engine"
          - look_name in config.exempt_looks

        Otherwise returns {"color": (r, g, b)} or, with multi=True,
        also {"color_a": (r, g, b), "color_b": (r, g, b)}.
        "color" is always present when injecting.
        """
        if self._v2_active and not self._v2_stand_down:
            return self._v2_resolve_color(
                role=role,
                section_id=section_id,
                cycle=cycle,
                look_name=look_name,
                color_source=color_source,
                multi=multi,
            )
        if not self._config.enabled:
            return {}
        if color_source != "engine":
            return {}
        if look_name in self._config.exempt_looks:
            return {}

        palette_name = self._config.locked_palette_by_look.get(look_name, self._current_palette)
        if self._mode_override is not None:
            palette_name = self._mode_override.get(role, self._mode_override.get("*", palette_name))
        palette = self._config.palettes.get(palette_name)
        if palette is None:
            return {}

        if palette.type == "fixed_rgb" and palette.rgb is not None:
            rgb = palette.rgb
            result: dict[str, Any] = {"color": rgb}
            if multi:
                result["color_a"] = rgb
                result["color_b"] = rgb
            return result
        if palette.type == "rainbow":
            p = ((cycle % 64) / 64.0 + (_blake2b_int(f"{section_id}:{role}") % 997) / 997.0) % 1.0
            rgb = _hue_to_rgb(p)
            result = {"color": rgb}
            if multi:
                result["color_a"] = _hue_to_rgb(p + 0.33)
                result["color_b"] = _hue_to_rgb(p + 0.66)
            return result

        if look_name in self._config.locked_palette_by_look or self._mode_override is not None:
            focus_lo, focus_hi = self._palette_p_interval(palette_name)
        else:
            focus_lo, focus_hi = self._focus_window(role)

        # Per-cue seed (deterministic per section / step)
        use_step = self._config.step_within_section.get(role, False)
        step_index = cycle if use_step else 0
        cue_seed = _blake2b_int(
            f"{self._current_track_seed}:{section_id}:{step_index}"
        )
        cue_rng = _rng_from_seed(cue_seed)

        # Roll p within focus window
        p = cue_rng.uniform(focus_lo, focus_hi)
        p = max(0.0, min(1.0, p))

        rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
        rgb = _blend_white(rgb, palette.white)

        result: dict[str, Any] = {"color": rgb}

        if multi:
            # Two-color effects: p_low = low end of focus window, p_high = high end
            p_low = max(0.0, min(1.0, focus_lo))
            p_high = max(0.0, min(1.0, focus_hi))
            rgb_a = _p_to_rgb(p_low, self._config.scale_stops, self._stop_positions)
            rgb_a = _blend_white(rgb_a, palette.white)
            rgb_b = _p_to_rgb(p_high, self._config.scale_stops, self._stop_positions)
            rgb_b = _blend_white(rgb_b, palette.white)
            result["color_a"] = rgb_a
            result["color_b"] = rgb_b

        color_shape = "color_a/color_b" if multi else "color"
        mem_key = (self._current_track_key, role, section_id, look_name, color_shape)
        prev = self._prev_color.get(mem_key)
        self._prev_color[mem_key] = dict(result)

        if prev:
            result["color_from"] = prev["color"]
            result["color_to"] = result["color"]
            if multi:
                result["color_a_from"] = prev["color_a"]
                result["color_a_to"] = result["color_a"]
                result["color_b_from"] = prev["color_b"]
                result["color_b_to"] = result["color_b"]
            fade_beats = float(self._config.fade_beats_by_role.get(role, 0.0))
            if fade_beats > 0.0:
                result["fade_beats"] = fade_beats

        return result

    def resolve_slot_colors(
        self,
        *,
        role: str,
        section_id: str,
        cycle: int,
        look_name: str,
        color_source: str,
        slot_count: int = 6,
    ) -> dict[str, Any]:
        """Resolve a slot-color palette vector for slot-based effects (§15.1).

        Returns {} (inject nothing) under the SAME early-returns as
        resolve_color: engine disabled, color_source != "engine", or the look
        is exempt.

        Otherwise returns ``{"slot_colors": [rgb0, ..., rgb5]}``:
          - M2.5 slot output is always 6 slots, with slot 5 reserved as pure white.
          - `gradient_even` is deterministic and RNG-free. It ignores cycle/section_id.
          - `random_with_replacement` uses a fresh local RNG with exact salt:
            `f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1"`.
          - `random_with_mono_chance` uses a separate mono roll stream; a miss
            reuses the exact random_with_replacement fill stream.
          - `step_index` is derived from `cycle` only when `step_within_section[role]`
            is true, otherwise 0.
        """
        if self._v2_active and not self._v2_stand_down:
            return self._v2_resolve_slot_colors(
                role=role,
                section_id=section_id,
                cycle=cycle,
                look_name=look_name,
                color_source=color_source,
                slot_count=slot_count,
            )
        if not self._config.enabled:
            return {}
        if color_source != "engine":
            return {}
        if look_name in self._config.exempt_looks:
            return {}

        palette_name = self._config.locked_palette_by_look.get(look_name, self._current_palette)
        if self._mode_override is not None:
            palette_name = self._mode_override.get(role, self._mode_override.get("*", palette_name))
        palette = self._config.palettes.get(palette_name)
        if palette is None:
            return {}

        if palette.type == "fixed_rgb" and palette.rgb is not None:
            return {"slot_colors": [palette.rgb, palette.rgb, palette.rgb, palette.rgb, palette.rgb, (255, 255, 255)]}
        if palette.type == "rainbow":
            return {
                "slot_colors": [
                    _hue_to_rgb((cycle + i) / 6.0)
                    for i in range(5)
                ] + [(255, 255, 255)]
            }

        if look_name in self._config.locked_palette_by_look or self._mode_override is not None:
            focus_lo, focus_hi = self._palette_p_interval(palette_name)
        else:
            focus_lo, focus_hi = self._focus_window(role)

        n = 6  # M2.5 slot invariant ignores caller slot_count

        strategy = (
            self._config.slot_fill_strategy_by_look.get(look_name)
            or self._config.slot_fill_strategy_by_role.get(role)
            or "gradient_even"
        )
        # Defensive: config validation (§2.D / led_config) rejects any strategy
        # outside this allowlist, so this is only reachable if a malformed config
        # bypassed validation. Fail safe to the documented default rather than
        # fall through to an empty (length-0) slot vector that would break the
        # fixed 6-slot invariant downstream. RNG-free; gradient output unchanged.
        if strategy not in ("gradient_even", "random_with_replacement", "random_with_mono_chance"):
            strategy = "gradient_even"

        slots: list[tuple[int, int, int]] = []
        if strategy == "gradient_even":
            gradient_count = n - 1  # last slot reserved for pure white
            for i in range(gradient_count):
                if gradient_count <= 1:
                    p = focus_lo
                else:
                    t = i / (gradient_count - 1)
                    p = focus_lo + t * (focus_hi - focus_lo)
                p = max(0.0, min(1.0, p))
                rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                rgb = _blend_white(rgb, palette.white)
                slots.append(rgb)
    
            # Reserved white slot (pure white, not blended, not palette-derived).
            slots.append((255, 255, 255))
        elif strategy == "random_with_replacement":
            use_step = self._config.step_within_section.get(role, False)
            step_index = cycle if use_step else 0
            fill_seed = _blake2b_int(f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1")
            fill_rng = _rng_from_seed(fill_seed)
            for _ in range(5):
                p = fill_rng.uniform(focus_lo, focus_hi)
                p = max(0.0, min(1.0, p))
                rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                rgb = _blend_white(rgb, palette.white)
                slots.append(rgb)
            slots.append((255, 255, 255))
        elif strategy == "random_with_mono_chance":
            use_step = self._config.step_within_section.get(role, False)
            step_index = cycle if use_step else 0
            mono_chance = self._config.slot_mono_chance_by_look.get(look_name, 0.0)
            # Dedicated mono stream: chance==0.0 must miss without perturbing the
            # existing :slotfill:v1 stream used by random_with_replacement.
            mono_seed = _blake2b_int(
                f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:mono:v1"
            )
            mono_rng = _rng_from_seed(mono_seed)
            if mono_rng.random() < mono_chance:
                p = mono_rng.uniform(focus_lo, focus_hi)
                p = max(0.0, min(1.0, p))
                rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                rgb = _blend_white(rgb, palette.white)
                for _ in range(5):
                    slots.append(rgb)
                slots.append((255, 255, 255))
            else:
                fill_seed = _blake2b_int(
                    f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1"
                )
                fill_rng = _rng_from_seed(fill_seed)
                for _ in range(5):
                    p = fill_rng.uniform(focus_lo, focus_hi)
                    p = max(0.0, min(1.0, p))
                    rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                    rgb = _blend_white(rgb, palette.white)
                    slots.append(rgb)
                slots.append((255, 255, 255))

        result: dict[str, Any] = {"slot_colors": slots}
        mem_key = (self._current_track_key, role, section_id, look_name, "slot_colors")
        prev = self._prev_color.get(mem_key)
        self._prev_color[mem_key] = dict(result)

        if prev:
            result["slot_colors_from"] = prev["slot_colors"]
            result["slot_colors_to"] = result["slot_colors"]
            fade_beats = float(self._config.fade_beats_by_role.get(role, 0.0))
            if fade_beats > 0.0:
                result["fade_beats"] = fade_beats

        return result

    # ------------------------------------------------------------------
    # Operator-reserved future LED Pad / Stream Deck controls. Future callers
    # outside StateManager must route through BridgeEvents/runtime commands.
    # ------------------------------------------------------------------

    def lock(self) -> None:
        """Freeze automatic palette selection (dwell drift + drop-snap). A
        queued palette still applies at the next track boundary and the lock
        transfers to it (palette_control_authority.md Rule 8)."""
        self._lock = True

    def unlock(self) -> None:
        """Release palette freeze."""
        self._lock = False

    def set_palette(self, name: str) -> None:
        """Jump to a specific palette immediately."""
        if name not in self._config.palettes:
            return  # no-op for unknown names
        self._queued_palette = ""
        self._fade_from_p = None
        self._fade_target = ""
        self._hold_track = True
        self._apply_palette_now(name, reason="operator")

    def queue_palette(self, name: str) -> None:
        """Stage a palette to take effect on the next track change."""
        if name in self._config.palettes:
            self._queued_palette = name

    def unqueue_palette(self, name: str) -> None:
        """Clear a staged palette only when it matches."""
        if self._queued_palette == name:
            self._queued_palette = ""

    def override_palette(self, name: str, *, start_beat: float, end_beat: float) -> None:
        """Fade to a palette now and hold it for this track."""
        if name not in self._config.palettes:
            return
        self._queued_palette = ""
        self._hold_track = True
        self._fade_from_p = self._anchor_p
        self._fade_target = name
        self._fade_start_beat = float(start_beat)
        self._fade_end_beat = max(float(end_beat), self._fade_start_beat)

    def advance_fade(self, abs_beat: float) -> None:
        if self._v2_active and not self._v2_stand_down:
            self._v2_advance(abs_beat)
            return
        if self._fade_from_p is None or not self._fade_target:
            return
        end = self._fade_end_beat
        start = self._fade_start_beat
        target_p = self._palette_center(self._fade_target)
        if end <= start or abs_beat >= end:
            self._apply_palette_now(self._fade_target, reason="fade")
            self._fade_from_p = None
            self._fade_target = ""
            return
        t = max(0.0, min(1.0, (float(abs_beat) - start) / (end - start)))
        self._anchor_p = self._fade_from_p + (target_p - self._fade_from_p) * t

    def color_state(self) -> dict[str, Any]:
        if self._v2_active:
            rgb = self._v2_manual_rgb()
            palette = self._v2_manual
            if rgb is None:
                dressing = self._v2_active_dressing()
                rgb = dressing.slot_rgbs[2] if dressing is not None else (0, 220, 255)
                palette = f"v2:{dressing.zone}" if dressing is not None else "v2:NEUTRAL"
            return {
                "rgb": rgb,
                "palette": palette,
                "white_sand_active": self._v2_manual == "white_sand",
                "rainbow_active": self._v2_manual == "rainbow",
            }
        mapped = tuple((self._mode_override or {}).values())
        return {
            "rgb": _p_to_rgb(self._anchor_p, self._config.scale_stops, self._stop_positions),
            "palette": self._current_palette,
            "white_sand_active": self._current_palette == "white_sand" or "white_sand" in mapped,
            "rainbow_active": self._mode_override is not None,
        }

    def set_mode_override(self, mapping: dict[str, str]) -> None:
        if self._fade_from_p is not None and self._fade_target:
            self._apply_palette_now(self._fade_target, reason="fade")
            self._fade_from_p = None
            self._fade_target = ""
        self._mode_override = {str(k): str(v) for k, v in mapping.items()}

    def clear_mode_override(self) -> None:
        self._mode_override = None

    def shift(self) -> None:
        """Re-select a distant palette immediately (manual dramatic shift)."""
        self._fade_from_p = None
        self._fade_target = ""
        new_palette = self._pick_palette(
            exclude=self._current_palette,
            bias=self._config.big_shift_weight_bias,
        )
        self._apply_palette_now(new_palette, reason="operator")

    def snapshot(self) -> dict:
        """Return current engine state for tests / status display."""
        snap = {
            "current_palette": self._current_palette,
            "anchor_p": self._anchor_p,
            "dwell_remaining": self._dwell_remaining,
            "drop_section_index": self._drop_section_index,
            "lock": self._lock,
            "queued_palette": self._queued_palette,
            "hold_track": self._hold_track,
            "fading": self._fade_from_p is not None,
            "fade_target": self._fade_target,
            "rainbow": self._mode_override is not None,
        }
        if self._v2_cfg is not None:
            dressing = self._v2_active_dressing()
            record = self._v2_record.get(self._v2_current_deck, {})
            snap.update({
                "engine": "v2" if self._v2_active else "v1",
                "zone": dressing.zone if dressing is not None else "",
                "corrected": bool(record.get("correction")),
                "staged_zone": self._v2_staged[0] if self._v2_staged else "",
                "manual": self._v2_manual,
            })
        return snap

    # ------------------------------------------------------------------
    # v2 helpers
    # ------------------------------------------------------------------

    def set_v2_active(self, active: bool) -> None:
        next_active = bool(active and self._v2_cfg is not None)
        if self._v2_active == next_active:
            return
        self.reset_fade_memory()
        self._v2_active = next_active
        self._v2_manual = ""
        self._v2_staged = None
        self._v2_flip_fade = None
        self._v2_pending_flip_fade = None
        self._v2_reset_until = None
        self._v2_pending_reset_beats = None
        self._v2_bloom_pending = None
        self._v2_bloom_until = None
        self._v2_claims.clear()
        self._v2_first_seen_beat = None
        self._v2_current_identity_key = ""
        self._v2_moments_blocked = False
        self._v2_stand_down = False

    def set_scripted_stand_down(self, scripted: bool) -> None:
        self._v2_stand_down = bool(scripted and self._v2_active)

    def set_track_identity(self, deck: int, load_gen: int, key: str, record: dict[str, Any]) -> None:
        if self._v2_cfg is None:
            return
        dressing = self._v2_dressing_from_record(record, key)
        self._v2_dressing[int(deck)] = dressing
        self._v2_record[int(deck)] = dict(record)
        self._v2_track_key_by_deck[int(deck)] = str(key)
        self._v2_load_gen_by_deck[int(deck)] = int(load_gen)

    def stage_zone(self, zone: str, commit_beat: float) -> None:
        if self._v2_cfg is None or zone not in self._v2_cfg.zones:
            return
        self._v2_staged = (zone, float(commit_beat))

    def unstage_zone(self, zone: str) -> None:
        if self._v2_staged and self._v2_staged[0] == zone:
            self._v2_staged = None

    def apply_zone_override(self, zone: str, *, start_beat: float, end_beat: float) -> None:
        if self._v2_cfg is None or zone not in self._v2_cfg.zones:
            return
        outgoing = self._v2_active_dressing()
        self._v2_apply_zone(zone)
        if outgoing is not None:
            self._v2_flip_fade = (outgoing.slot_rgbs, max(float(end_beat), float(start_beat)))

    def clear_zone_override(self) -> None:
        self._v2_staged = None

    def set_manual(self, name: str) -> None:
        if name not in {"white_sand", "red", "green", "blue", "rainbow"}:
            return
        self._v2_manual = "" if self._v2_manual == name else name

    def clear_manual(self) -> None:
        self._v2_manual = ""

    def _v2_begin_dispatch(
        self,
        *,
        active_deck: int,
        load_gen: int,
        content_id: str,
        filepath: str,
        role: str,
        section_id: str,
        cycle: int,
        moments_blocked: bool,
    ) -> None:
        if self._v2_cfg is None:
            return
        track_key = (active_deck, load_gen)
        key = content_id or filepath or str(load_gen)
        now = self._v2_now
        self._v2_current_identity_key = str(key)
        self._v2_moments_blocked = bool(moments_blocked)
        if track_key != self._v2_current_track_key:
            outgoing = self._v2_active_dressing()
            self._v2_current_track_key = track_key
            self._v2_current_deck = active_deck
            self._v2_manual = ""
            self._v2_staged = None
            self._v2_bloom_pending = None
            self._v2_bloom_until = None
            self._v2_first_seen_beat = None
            if self._v2_load_gen_by_deck.get(active_deck) != load_gen:
                self._v2_install_default(active_deck, load_gen, key)
            incoming = self._v2_active_dressing()
            if outgoing is not None and incoming is not None:
                self._v2_pending_flip_fade = (
                    outgoing.slot_rgbs,
                    max(0.0, self._v2_cfg.soft_flip_beats),
                )
                if (
                    not moments_blocked
                    and self._v2_cfg.palate_reset_enabled
                    and is_hard_pivot(outgoing.zone, incoming.zone)
                ):
                    self._v2_pending_reset_beats = max(0.0, self._v2_cfg.palate_reset_beats)
                else:
                    self._v2_pending_reset_beats = None
        self._v2_current_deck = active_deck
        if self._v2_manual:
            self._v2_claims = [Claim(RANKS["manual"], now, float("inf"), "manual")]
        else:
            self._v2_claims = [c for c in self._v2_claims if c.end_beat > now and c.tag != "manual"]
        if moments_blocked:
            self._v2_pending_reset_beats = None

    def _v2_resolve_color(
        self,
        *,
        role: str,
        section_id: str,
        cycle: int,
        look_name: str,
        color_source: str,
        multi: bool,
    ) -> dict[str, Any]:
        if not self._config.enabled or color_source != "engine" or look_name in self._config.exempt_looks:
            return {}
        manual = self._v2_manual_rgb(cycle=cycle, section_id=section_id, role=role)
        if manual is not None:
            result: dict[str, Any] = {"color": manual}
            if multi:
                result["color_a"] = manual
                result["color_b"] = manual
            return result
        dressing = self._v2_active_dressing()
        if dressing is None:
            return {}
        multi_slots = dressing.slot_rgbs
        if self._v2_reset_until is not None and self._v2_now < self._v2_reset_until:
            neutral = self._v2_neutral_dressing() or dressing
            dim = self._v2_cfg.palate_reset_dim if self._v2_cfg else 1.0
            multi_slots = tuple(self._scale_rgb(slot_rgb, dim) for slot_rgb in neutral.slot_rgbs)
            rgb = multi_slots[2]
        else:
            use_step = self._config.step_within_section.get(role, False)
            step_index = cycle if use_step else 0
            key_hash = int(self._v2_record.get(self._v2_current_deck, {}).get("key_hash", 0))
            cue_seed = _blake2b_int(f"{key_hash}:{section_id}:{step_index}:v2")
            p = _rng_from_seed(cue_seed).uniform(0.0, 1.0)
            rgb = self._v2_base_pick(dressing, p)
        result = {"color": rgb}
        if multi:
            result["color_a"] = multi_slots[0]
            result["color_b"] = multi_slots[2]
        self._v2_apply_fade_fields(result, role, multi=multi)
        return result

    def _v2_resolve_slot_colors(
        self,
        *,
        role: str,
        section_id: str,
        cycle: int,
        look_name: str,
        color_source: str,
        slot_count: int,
    ) -> dict[str, Any]:
        if not self._config.enabled or color_source != "engine" or look_name in self._config.exempt_looks:
            return {}
        manual = self._v2_manual_rgb(cycle=cycle, section_id=section_id, role=role)
        if manual is not None:
            if self._v2_manual == "rainbow":
                slots = [_hue_to_rgb((cycle + i) / 6.0) for i in range(5)] + [(255, 255, 255)]
            else:
                slots = [manual, manual, manual, manual, manual, (255, 255, 255)]
            return {"slot_colors": slots}
        dressing = self._v2_active_dressing()
        if dressing is None:
            return {}
        slots = list(dressing.slot_rgbs)
        if self._v2_reset_until is not None and self._v2_now < self._v2_reset_until:
            dim = self._v2_cfg.palate_reset_dim if self._v2_cfg else 1.0
            neutral = self._v2_neutral_dressing() or dressing
            slots = [self._scale_rgb(rgb, dim) for rgb in neutral.slot_rgbs[:5]] + [(255, 255, 255)]
        result: dict[str, Any] = {"slot_colors": slots}
        self._v2_apply_fade_fields(result, role, slots=True)
        return result

    def _v2_advance(self, abs_beat: float) -> None:
        now = float(abs_beat)
        self._v2_now = now
        if self._v2_pending_flip_fade is not None:
            slots, duration = self._v2_pending_flip_fade
            self._v2_flip_fade = (slots, now + duration)
            self._v2_pending_flip_fade = None
        if self._v2_pending_reset_beats is not None:
            if not self._v2_moments_blocked:
                claim = Claim(
                    RANKS["palate_reset"],
                    now,
                    now + self._v2_pending_reset_beats,
                    "palate_reset",
                )
                if claim_allowed(claim, self._v2_claims):
                    self._v2_reset_until = claim.end_beat
                    self._v2_claims.append(claim)
            self._v2_pending_reset_beats = None
        if self._v2_staged is not None and now >= self._v2_staged[1]:
            self._v2_apply_zone(self._v2_staged[0])
            self._v2_staged = None
        if self._v2_flip_fade is not None and now >= self._v2_flip_fade[1]:
            self._v2_flip_fade = None
        if self._v2_reset_until is not None and now >= self._v2_reset_until:
            self._v2_reset_until = None
        if self._v2_bloom_until is not None and now >= self._v2_bloom_until:
            self._v2_bloom_pending = None
            self._v2_bloom_until = None
        self._v2_claims = [c for c in self._v2_claims if c.end_beat > now]
        if self._v2_moments_blocked:
            if self._v2_bloom_pending is None and self._v2_bloom_until is None:
                self._v2_first_seen_beat = None
            return
        self._v2_maybe_arm_bloom(self._v2_current_identity_key, now)

    def _v2_maybe_arm_bloom(self, key: str, now: float) -> None:
        if self._v2_cfg is None or not self._v2_cfg.bloom_enabled or self._v2_manual:
            return
        if key in self._v2_bloomed:
            return
        if self._v2_first_seen_beat is None:
            self._v2_first_seen_beat = now
            return
        if now - self._v2_first_seen_beat < self._v2_cfg.bloom_hold_beats:
            return
        dressing = self._v2_active_dressing()
        if dressing is None:
            return
        claim = Claim(RANKS["bloom"], now, now + self._v2_cfg.bloom_beats, "bloom")
        if not claim_allowed(claim, self._v2_claims):
            self._v2_bloomed.add(key)
            return
        self._v2_bloom_pending = (
            tuple(self._scale_rgb(rgb, self._v2_cfg.bloom_dim) for rgb in dressing.slot_rgbs),
            claim.end_beat,
        )
        self._v2_bloom_until = claim.end_beat
        self._v2_claims.append(claim)
        self._v2_bloomed.add(key)

    def _v2_apply_fade_fields(self, result: dict[str, Any], role: str, *, multi: bool = False, slots: bool = False) -> None:
        fade_from: tuple[tuple[int, int, int], ...] | None = None
        fade_until: float | None = None
        if self._v2_flip_fade is not None:
            fade_from, fade_until = self._v2_flip_fade
        elif self._v2_bloom_pending is not None:
            fade_from, fade_until = self._v2_bloom_pending
        if fade_from is None or fade_until is None:
            return
        remaining = max(0.0, fade_until - self._v2_now)
        fade_beats = remaining or float(self._config.fade_beats_by_role.get(role, 0.0))
        if slots:
            result["slot_colors_from"] = list(fade_from)
            result["slot_colors_to"] = list(result["slot_colors"])
            result["fade_beats"] = fade_beats
            return
        result["color_from"] = fade_from[2]
        result["color_to"] = result["color"]
        if multi:
            result["color_a_from"] = fade_from[0]
            result["color_a_to"] = result["color_a"]
            result["color_b_from"] = fade_from[2]
            result["color_b_to"] = result["color_b"]
        result["fade_beats"] = fade_beats

    def _v2_neutral_dressing(self) -> Dressing | None:
        if self._v2_cfg is None or "NEUTRAL" not in self._v2_cfg.zones:
            return None
        record = self._v2_record.get(self._v2_current_deck, {})
        key_hash = int(record.get("key_hash", content_hash(self._v2_current_identity_key)))
        return derive_dressing(
            "NEUTRAL",
            self._v2_cfg.zones["NEUTRAL"],
            key_hash,
            0.5,
            0.5,
            0.0,
        )

    def _v2_active_dressing(self) -> Dressing | None:
        if self._v2_current_deck:
            return self._v2_dressing.get(self._v2_current_deck)
        return None

    def _v2_install_default(self, deck: int, load_gen: int, key: str) -> None:
        if self._v2_cfg is None:
            return
        key_hash = content_hash(key)
        dressing = derive_dressing("NEUTRAL", self._v2_cfg.zones["NEUTRAL"], key_hash, 0.5, 0.5, 0.0)
        record = {
            "zone": "NEUTRAL",
            "hue_slot": dressing.hue_slot,
            "depth_variant": dressing.depth_variant,
            "sat_floor": dressing.sat_floor,
            "span": dressing.span,
            "budget": dressing.budget,
            "style": dressing.style,
            "base": "provisional",
            "scores": {},
            "analysis_rev": "v4",
            "correction": None,
            "norm_inputs": {"bass": 0.5, "drama": 0.5, "punch": 0.0},
            "key_hash": key_hash,
        }
        self.set_track_identity(deck, load_gen, key, record)

    def _v2_dressing_from_record(self, record: dict[str, Any], key: str) -> Dressing:
        if self._v2_cfg is None:
            raise RuntimeError("v2 disabled")
        correction = record.get("correction")
        zone = str((correction or {}).get("zone") or record.get("zone") or "NEUTRAL")
        if zone not in self._v2_cfg.zones:
            zone = "NEUTRAL"
        norm_inputs = record.get("norm_inputs") if isinstance(record.get("norm_inputs"), dict) else {}
        key_hash = int(record.get("key_hash", content_hash(key)))
        return derive_dressing(
            zone,
            self._v2_cfg.zones[zone],
            key_hash,
            float(norm_inputs.get("bass", 0.5)),
            float(norm_inputs.get("drama", 0.5)),
            float(norm_inputs.get("punch", 0.0)),
        )

    def _v2_apply_zone(self, zone: str) -> None:
        if self._v2_cfg is None or zone not in self._v2_cfg.zones:
            return
        record = dict(self._v2_record.get(self._v2_current_deck, {}))
        if not record:
            return
        record["correction"] = {"zone": zone}
        key = self._v2_track_key_by_deck.get(self._v2_current_deck, "")
        self.set_track_identity(
            self._v2_current_deck,
            self._v2_load_gen_by_deck.get(self._v2_current_deck, 0),
            key,
            record,
        )

    def _v2_manual_rgb(
        self,
        *,
        cycle: int = 0,
        section_id: str = "",
        role: str = "",
    ) -> tuple[int, int, int] | None:
        if not self._v2_manual:
            return None
        if self._v2_manual == "white_sand":
            palette = self._config.palettes.get("white_sand")
            return palette.rgb if palette is not None and palette.rgb is not None else (255, 235, 200)
        if self._v2_manual == "red":
            return (255, 0, 0)
        if self._v2_manual == "green":
            return (0, 255, 0)
        if self._v2_manual == "blue":
            return (0, 0, 255)
        if self._v2_manual == "rainbow":
            p = ((cycle % 64) / 64.0 + (_blake2b_int(f"{section_id}:{role}") % 997) / 997.0) % 1.0
            return _hue_to_rgb(p)
        return None

    def _v2_base_pick(self, dressing: Dressing, p: float) -> tuple[int, int, int]:
        slots = dressing.slot_rgbs
        if p < 0.5:
            a, b = slots[0], slots[1]
            t = p / 0.5
        else:
            a, b = slots[1], slots[2]
            t = (p - 0.5) / 0.5
        return tuple(max(0, min(255, int(round(a[i] + (b[i] - a[i]) * t)))) for i in range(3))  # type: ignore[return-value]

    def _scale_rgb(self, rgb: tuple[int, int, int], scale: float) -> tuple[int, int, int]:
        scale = max(0.0, min(1.0, float(scale)))
        return tuple(max(1, min(255, int(round(v * scale)))) for v in rgb)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _pick_palette(
        self,
        exclude: str | None = None,
        bias: float | None = None,
    ) -> str:
        """Pick a palette by weight from the journey rng."""
        if not self._palette_names:
            raise RuntimeError("No palettes configured")
        b = bias if bias is not None else 1.0
        return _weighted_choice(
            self._journey_rng,
            self._palette_names,
            self._palette_weights,
            exclude=exclude,
            bias=b,
        )

    def _palette_p_interval(self, name: str) -> tuple[float, float]:
        """Return (lo_p, hi_p) for the named palette's range stops."""
        palette = self._config.palettes[name]
        stop_a, stop_b = palette.range
        p_a = self._stop_positions.get(stop_a, 0.0)
        p_b = self._stop_positions.get(stop_b, 0.0)
        return (min(p_a, p_b), max(p_a, p_b))

    def _palette_center(self, name: str) -> float:
        lo, hi = self._palette_p_interval(name)
        return (lo + hi) / 2.0

    def _apply_palette_now(self, name: str, *, reason: str = "dwell") -> None:
        prev = self._current_palette
        self._current_palette = name
        self._anchor_p = self._palette_center(name)
        dwell = self._config.palettes[name].dwell
        self._dwell_remaining = (
            dwell if dwell is not None else self._config.palette_dwell_tracks
        )
        self._reseed_focus()
        # AWR-125: one perf record per palette-change commit, never per-tick
        # (every caller is edge-triggered: dwell expiry, queued apply, fade
        # completion, or an operator control).
        bridge_log.perf(
            "led.palette",
            "palette %s->%s (%s)",
            prev,
            name,
            reason,
            data={
                "palette": name,
                "prev": prev,
                "reason": reason,
                "locked": self._lock,
            },
        )

    def _reseed_focus(self) -> None:
        """Re-draw per-track focus using current_track_seed."""
        palette = self._config.palettes.get(self._current_palette)
        if palette is None:
            return
        lo_p, hi_p = self._palette_p_interval(self._current_palette)
        focus_rng = _rng_from_seed(self._current_track_seed)
        self._focus_fc, self._focus_fw = _draw_focus(focus_rng, palette, lo_p, hi_p)
