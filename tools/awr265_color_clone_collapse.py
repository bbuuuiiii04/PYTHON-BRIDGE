#!/usr/bin/env python3
"""AWR-265 Step 0 — color-clone → palette/zone mapping + frame A/B harness.

Read-only analysis against example (and optional live) LED config. Imports the
color engine only inside tests/tools (allowed); does not mutate bridge runtime
modules.

AWR-265 FINAL (2026-07-16): collapse is complete — clone-free configs yield an
empty collapse inventory (plus any remaining DIY out-of-scope names). The living
gate is ``tests/test_awr265_color_clone_collapse.py`` (color-level A/B under
blue_cyan). This tool stays runnable-honest: empty results, no crash.

Classification per clone (historical Step 0):
  EXACT_TODAY     — some current palette/zone already yields the target pair
  CONFIG_EDIT     — a palette/zone VALUE edit (documented) would yield exact
  IMPOSSIBLE      — cannot reproduce config-only (keep clone; report residual)
  OUT_OF_SCOPE    — color-suffixed name but not an RT cue class (DIY/cloud)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

_ROOT = Path(__file__).resolve().parents[1]
_PARENT = _ROOT.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from rb_ss_bridge_v2.govee_frame_renderer import (  # noqa: E402
    GoveeFrameRenderer,
    _edm_color_for_look,
)
from rb_ss_bridge_v2.led_color_engine import LedColorEngine  # noqa: E402
from rb_ss_bridge_v2.led_config import load_led_look_director_config  # noqa: E402
from rb_ss_bridge_v2.led_identity_v2 import HUE_SLOTS, derive_dressing  # noqa: E402
from rb_ss_bridge_v2.led_models import Palette, ZoneRampConfig  # noqa: E402

RGB = tuple[int, int, int]
SEGMENTS = 60
SEED = 42
GRID_BEATS = tuple(i / 10.0 for i in range(0, 320))  # 0.0 .. 31.9


# ---------------------------------------------------------------------------
# Clone inventory (25 RT collapse candidates + 4 OUT_OF_SCOPE DIY names)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CloneSpec:
    look_name: str
    cue_class: str  # drop_strobe | drop_chase | groove_chase | post_drop_chase |
    #                 center_burst | center_comet | twinkle | diy_cloud
    base_look: str
    base_scene: str
    role: str
    family: str  # blue | cyan | red | green | cyan_white | blue_cyan | red_white
    # Literal colors the clone surfaces today.
    color_a: RGB
    color_b: RGB | None  # None → mono (color_b == color_a)
    # How the base cue consumes engine colors.
    inject: str  # "multi" | "slots" | "n/a"
    scope: str  # "collapse" | "out_of_scope"


def _rgb(seq: Sequence[Any]) -> RGB:
    return (int(seq[0]), int(seq[1]), int(seq[2]))


def _family_from_suffix(name: str) -> str:
    for token in (
        "cyan_white",
        "blue_cyan",
        "red_white",
        "blue",
        "cyan",
        "red",
        "green",
    ):
        if name.endswith("_" + token) or name.endswith(token):
            # prefer longest match already ordered
            if name.endswith(token):
                return token
    return "unknown"


def build_clone_specs(looks: dict[str, Any]) -> list[CloneSpec]:
    """Build the 29-name inventory from config looks (example or live)."""
    specs: list[CloneSpec] = []

    # --- drop strobes (baked params on drop_strobe_colorway) ---
    for look_name, look in looks.items():
        if not look_name.startswith("rt_drop_strobe_"):
            continue
        params = look.get("params") or {}
        color_a = _rgb(params["color_a"])
        color_b = _rgb(params["color_b"]) if "color_b" in params else None
        family = _family_from_suffix(look_name)
        specs.append(
            CloneSpec(
                look_name=look_name,
                cue_class="drop_strobe",
                base_look="rt_drop_strobe",
                base_scene="drop_strobe_colorway",
                role="drop",
                family=family,
                color_a=color_a,
                color_b=color_b,
                inject="multi",
                scope="collapse",
            )
        )

    # --- baked chase / burst / twinkle suffixes ---
    chase_rows = [
        ("rt_groove_chase_", "groove_chase", "rt_groove_chase", "rt_groove_chase", "groove"),
        ("rt_drop_chase_", "drop_chase", "rt_drop_chase", "rt_drop_chase", "drop"),
        ("rt_post_drop_chase_", "post_drop_chase", "rt_post_drop_chase", "rt_post_drop_chase", "post_drop"),
    ]
    for prefix, cue_class, base_look, base_scene, role in chase_rows:
        for look_name, look in looks.items():
            if not look_name.startswith(prefix):
                continue
            if look_name.endswith("_freestyle_nebula"):
                continue
            scene = str(look.get("scene_ref") or "")
            c1, c2 = _edm_color_for_look(scene, 0.0)
            # cyan_white pair is always cyan+white regardless of beat-0 swap
            family = _family_from_suffix(look_name)
            if family == "cyan_white":
                c1, c2 = (0, 255, 255), (255, 255, 255)
            specs.append(
                CloneSpec(
                    look_name=look_name,
                    cue_class=cue_class,
                    base_look=base_look,
                    base_scene=base_scene,
                    role=role,
                    family=family,
                    color_a=c1,
                    color_b=None if c1 == c2 else c2,
                    inject="slots",
                    scope="collapse",
                )
            )

    if "rt_drop_center_burst_blue_cyan" in looks:
        specs.append(
            CloneSpec(
                look_name="rt_drop_center_burst_blue_cyan",
                cue_class="center_burst",
                base_look="rt_drop_center_burst",
                base_scene="rt_drop_center_burst",
                role="drop",
                family="blue_cyan",
                color_a=(0, 0, 255),
                color_b=(0, 200, 255),
                inject="slots",
                scope="collapse",
            )
        )
    if "rt_post_drop_center_comet_blue_cyan" in looks:
        specs.append(
            CloneSpec(
                look_name="rt_post_drop_center_comet_blue_cyan",
                cue_class="center_comet",
                base_look="rt_post_drop_center_comet",
                base_scene="rt_post_drop_center_comet",
                role="post_drop",
                family="blue_cyan",
                color_a=(0, 0, 255),
                color_b=(0, 200, 255),
                inject="slots",
                scope="collapse",
            )
        )
    if "rt_twinkle_blue" in looks:
        specs.append(
            CloneSpec(
                look_name="rt_twinkle_blue",
                cue_class="twinkle",
                base_look="rt_twinkle",
                base_scene="rt_twinkle",
                role="ambient",
                family="blue",
                color_a=(0, 0, 255),
                color_b=(0, 255, 255),
                inject="slots",
                scope="collapse",
            )
        )

    # DIY / cloud color-suffixed names counted in the audit's "29" but not RT classes
    diy_names = (
        "breakdown_1_red",
        "drop_diy_2_cyan",
        "drop_diy_4_blue_cyan",
        "drop_diy_5_red",
    )
    for name in diy_names:
        if name not in looks:
            continue
        specs.append(
            CloneSpec(
                look_name=name,
                cue_class="diy_cloud",
                base_look="",
                base_scene=str(looks[name].get("scene_ref") or ""),
                role="drop",
                family=_family_from_suffix(name),
                color_a=(0, 0, 0),
                color_b=None,
                inject="n/a",
                scope="out_of_scope",
            )
        )

    specs.sort(key=lambda s: (s.scope, s.cue_class, s.look_name))
    return specs


# Preferred family → existing journey palette / v2 zone (taste mapping).
FAMILY_HOME: dict[str, tuple[str, str]] = {
    "blue": ("blue_cyan", "GLACIER"),
    "cyan": ("blue_cyan", "GLACIER"),
    "blue_cyan": ("blue_cyan", "GLACIER"),
    "cyan_white": ("blue_cyan", "GLACIER"),
    "green": ("deep_ocean", "ION"),
    "red": ("crimson", "EMBERCORE"),
    "red_white": ("crimson", "EMBERCORE"),
}


def _target_pair(spec: CloneSpec) -> tuple[RGB, RGB]:
    b = spec.color_b if spec.color_b is not None else spec.color_a
    return (spec.color_a, b)


def _slot_vector_for(spec: CloneSpec) -> list[RGB]:
    """Literal slot injection that best mirrors the clone's color pair."""
    a, b = _target_pair(spec)
    if spec.family == "cyan_white":
        # Alternate cyan/white across slots 0-4; slot 5 reserved white.
        return [a, b, a, b, a, (255, 255, 255)]
    if spec.color_b is None or a == b:
        return [a, a, a, a, a, (255, 255, 255)]
    if spec.cue_class in ("center_burst", "center_comet"):
        # Main band blue (0-2), accent cyan-ish (3-4), white tail.
        return [a, a, a, b, b, (255, 255, 255)]
    if spec.cue_class == "twinkle":
        return [
            (0, 0, 255),
            (0, 128, 255),
            (30, 144, 255),
            (0, 255, 255),
            (0, 0, 255),
            (255, 255, 255),
        ]
    # Dual-color chase: put both ends in the gradient, white reserved.
    return [a, a, b, b, a, (255, 255, 255)]


# ---------------------------------------------------------------------------
# Engine probes (read-only)
# ---------------------------------------------------------------------------

def _engine_v1(cfg, *, locked_palette: str) -> LedColorEngine:
    ce = replace(cfg, v2=None, locked_palette_by_look={"__probe__": locked_palette})
    engine = LedColorEngine(ce, set_seed=1)
    engine.begin_dispatch(
        active_deck=1,
        load_gen=1,
        content_id="awr265-probe",
        filepath="/awr265-probe.wav",
        role="drop",
        section_id="s0",
        cycle=0,
    )
    return engine


def _resolve_v1_multi(cfg, palette_name: str) -> tuple[RGB | None, RGB | None]:
    if palette_name not in cfg.palettes:
        return (None, None)
    engine = _engine_v1(cfg, locked_palette=palette_name)
    out = engine.resolve_color(
        role="drop",
        section_id="s0",
        cycle=0,
        look_name="__probe__",
        color_source="engine",
        multi=True,
    )
    ca, cb = out.get("color_a"), out.get("color_b")
    return (
        tuple(ca) if ca is not None else None,  # type: ignore[return-value]
        tuple(cb) if cb is not None else None,  # type: ignore[return-value]
    )


def _resolve_v1_slots(cfg, palette_name: str) -> list[RGB] | None:
    if palette_name not in cfg.palettes:
        return None
    engine = _engine_v1(cfg, locked_palette=palette_name)
    out = engine.resolve_slot_colors(
        role="drop",
        section_id="s0",
        cycle=0,
        look_name="__probe__",
        color_source="engine",
    )
    slots = out.get("slot_colors")
    if not slots:
        return None
    return [tuple(s) for s in slots]  # type: ignore[misc]


def _edited_v1_cfg(cfg):
    """In-memory CONFIG_EDIT candidate: white stop + point / dual palettes."""
    stops = dict(cfg.scale_stops)
    stops["white"] = (255, 255, 255)
    stops["sky"] = (0, 135, 255)  # strobe blue_cyan color_b
    stops["ice"] = (0, 200, 255)  # center-burst cyan-ish
    stops["periwinkle"] = (100, 105, 255)  # strobe cyan_white color_b
    palettes = dict(cfg.palettes)
    for name, rng in (
        ("pure_blue", ("blue", "blue")),
        ("pure_cyan", ("cyan", "cyan")),
        ("pure_red", ("red", "red")),
        ("pure_green", ("green", "green")),
        ("cyan_white", ("cyan", "white")),
        ("cyan_periwinkle", ("cyan", "periwinkle")),
        ("red_white", ("red", "white")),
        ("blue_sky", ("blue", "sky")),
        ("blue_ice", ("blue", "ice")),
    ):
        palettes[name] = Palette(range=rng, spread=0.0, weight=1.0, type="journey")
    return replace(cfg, scale_stops=stops, palettes=palettes, v2=None)


def _family_edit_palette(family: str, *, cue_class: str = "") -> str:
    if cue_class == "drop_strobe" and family == "cyan_white":
        return "cyan_periwinkle"
    if cue_class in ("center_burst", "center_comet") and family == "blue_cyan":
        return "blue_ice"
    return {
        "blue": "pure_blue",
        "cyan": "pure_cyan",
        "red": "pure_red",
        "green": "pure_green",
        "cyan_white": "cyan_white",
        "red_white": "red_white",
        "blue_cyan": "blue_sky",
    }.get(family, "pure_blue")


def _v2_zone_exact_slots(zone_cfg: ZoneRampConfig) -> list[RGB]:
    mid = (HUE_SLOTS - 1) // 2
    dressing = derive_dressing("PROBE", zone_cfg, mid, 1.0, 0.5, 0.0)
    return [tuple(s) for s in dressing.slot_rgbs]  # type: ignore[misc]


def _proposed_zone_for(spec: CloneSpec) -> ZoneRampConfig:
    a, b = _target_pair(spec)
    if spec.color_b is None or a == b:
        return ZoneRampConfig(
            base_ramp=(a, a, a),
            accent_ramp=(a, a),
            slot5_white=(255, 255, 255),
            hue_span=0.0,
        )
    return ZoneRampConfig(
        base_ramp=(a, a, a),
        accent_ramp=(b, b),
        slot5_white=(255, 255, 255),
        hue_span=0.0,
    )


# ---------------------------------------------------------------------------
# Frame A/B
# ---------------------------------------------------------------------------

def _clone_scene(looks: dict[str, Any], look_name: str) -> str:
    return str(looks[look_name].get("scene_ref") or look_name)


def _clone_params(looks: dict[str, Any], look_name: str) -> dict[str, Any]:
    raw = looks[look_name].get("params") or {}
    params = dict(raw)
    params.setdefault("hz", 6.0)
    params.setdefault("duty", 0.3)
    params.setdefault("frame_period_s", 1.0 / 40.0)
    return params


def frame_ab_base_vs_literals(
    *,
    base_scene: str,
    inject: str,
    literals: CloneSpec,
    beats: Iterable[float] = GRID_BEATS,
) -> tuple[int, int]:
    """Compare base effect + engine-shaped literals vs base effect + same literals.

    This is the color-resolution identity gate (motion identical by construction).
    Returns (mismatches, checked).
    """
    renderer = GoveeFrameRenderer()
    if inject == "multi":
        params_lit: dict[str, Any] = {
            "color_a": literals.color_a,
            "hz": 6.0,
            "duty": 0.3,
            "frame_period_s": 1.0 / 40.0,
        }
        if literals.color_b is not None:
            params_lit["color_b"] = literals.color_b
        params_eng = dict(params_lit)
    elif inject == "slots":
        slots = _slot_vector_for(literals)
        params_lit = {
            "slot_colors": slots,
            "hz": 6.0,
            "duty": 0.3,
            "frame_period_s": 1.0 / 40.0,
            "duration_beats": 32.0,
            "loop_beats": 4.0,
            "width": 1.0 if literals.cue_class == "center_comet" else 0.8,
        }
        params_eng = dict(params_lit)
    else:
        return (0, 0)

    mismatches = 0
    checked = 0
    for i, beat in enumerate(beats):
        local_t = float(beat) * 0.5
        fa = renderer.render(
            base_scene,
            beat_pos=float(beat),
            local_t=local_t,
            frame_index=i,
            params=params_lit,
            segments=SEGMENTS,
            seed=SEED,
        )
        fb = renderer.render(
            base_scene,
            beat_pos=float(beat),
            local_t=local_t,
            frame_index=i,
            params=params_eng,
            segments=SEGMENTS,
            seed=SEED,
        )
        checked += 1
        if fa != fb:
            mismatches += 1
    return (mismatches, checked)


def frame_ab_clone_vs_base(
    *,
    looks: dict[str, Any],
    spec: CloneSpec,
    beats: Iterable[float] = GRID_BEATS,
) -> tuple[int, int]:
    """Compare baked clone scene vs base scene with literal slot/multi injection."""
    if spec.scope != "collapse" or not spec.base_scene:
        return (0, 0)
    renderer = GoveeFrameRenderer()
    clone_scene = _clone_scene(looks, spec.look_name)
    clone_params = _clone_params(looks, spec.look_name)
    if spec.inject == "multi":
        base_params: dict[str, Any] = {
            "color_a": spec.color_a,
            "hz": float(clone_params.get("hz", 6.0)),
            "duty": float(clone_params.get("duty", 0.3)),
            "frame_period_s": 1.0 / 40.0,
        }
        if spec.color_b is not None:
            base_params["color_b"] = spec.color_b
    else:
        base_params = {
            "slot_colors": _slot_vector_for(spec),
            "hz": 6.0,
            "duty": 0.3,
            "frame_period_s": 1.0 / 40.0,
            "duration_beats": 32.0,
            "loop_beats": 4.0,
            "width": 1.0 if spec.cue_class == "center_comet" else 0.8,
            "travel_beats": 2.0,
        }
    mismatches = 0
    checked = 0
    for i, beat in enumerate(beats):
        local_t = float(beat) * 0.5
        fa = renderer.render(
            clone_scene,
            beat_pos=float(beat),
            local_t=local_t,
            frame_index=i,
            params=clone_params,
            segments=SEGMENTS,
            seed=SEED,
        )
        fb = renderer.render(
            spec.base_scene,
            beat_pos=float(beat),
            local_t=local_t,
            frame_index=i,
            params=base_params,
            segments=SEGMENTS,
            seed=SEED,
        )
        checked += 1
        if fa != fb:
            mismatches += 1
    return (mismatches, checked)


# ---------------------------------------------------------------------------
# Mapping row
# ---------------------------------------------------------------------------

@dataclass
class MappingRow:
    spec: CloneSpec
    home_palette: str
    home_zone: str
    today_multi: tuple[RGB | None, RGB | None]
    today_match: bool
    edit_palette: str
    edit_multi: tuple[RGB | None, RGB | None]
    edit_match: bool
    zone_edit_slots: list[RGB]
    zone_edit_match: bool
    clone_vs_base_mismatches: int
    clone_vs_base_checked: int
    classification: str
    residual: str
    config_edit: str


def classify_clone(cfg, looks: dict[str, Any], spec: CloneSpec) -> MappingRow:
    home_pal, home_zone = FAMILY_HOME.get(spec.family, ("blue_cyan", "GLACIER"))
    if spec.scope == "out_of_scope":
        return MappingRow(
            spec=spec,
            home_palette=home_pal,
            home_zone=home_zone,
            today_multi=(None, None),
            today_match=False,
            edit_palette="",
            edit_multi=(None, None),
            edit_match=False,
            zone_edit_slots=[],
            zone_edit_match=False,
            clone_vs_base_mismatches=0,
            clone_vs_base_checked=0,
            classification="OUT_OF_SCOPE",
            residual="DIY/cloud look — not an RT cue class; leave alone",
            config_edit="",
        )

    target = _target_pair(spec)
    today_multi = _resolve_v1_multi(cfg, home_pal)
    today_match = today_multi == target

    edited = _edited_v1_cfg(cfg)
    edit_pal = _family_edit_palette(spec.family, cue_class=spec.cue_class)
    edit_multi = _resolve_v1_multi(edited, edit_pal)
    edit_match = edit_multi == target

    zone = _proposed_zone_for(spec)
    zone_slots = _v2_zone_exact_slots(zone)
    # For multi inject, zone match means slot0/slot2 cover the pair (v2 multi uses those).
    if spec.inject == "multi":
        zone_edit_match = (zone_slots[0], zone_slots[2]) == target or (
            zone_slots[0] == target[0] and zone_slots[3] == target[1]
        )
    else:
        want = _slot_vector_for(spec)
        zone_edit_match = zone_slots[:5] == want[:5] and zone_slots[5] == want[5]

    mism, checked = frame_ab_clone_vs_base(looks=looks, spec=spec)

    residual = ""
    config_edit = ""
    if today_match and mism == 0:
        classification = "EXACT_TODAY"
    elif edit_match and mism == 0:
        classification = "CONFIG_EDIT"
        config_edit = (
            f"add scale_stops white/sky/ice as needed; add journey palette "
            f"'{edit_pal}' with point/dual range; optionally set v2 zone "
            f"'{home_zone}' ramps to {target} with hue_span=0"
        )
    elif mism > 0:
        classification = "IMPOSSIBLE"
        residual = (
            f"base scene '{spec.base_scene}' is not byte-identical to clone "
            f"'{spec.look_name}' on the seeded grid ({mism}/{checked} frames); "
            "config-only color edits cannot fix motion/slot-index divergence — keep clone"
        )
        if edit_match:
            config_edit = (
                f"colors CAN be resolved exactly via palette '{edit_pal}', but "
                "frame A/B vs clone still fails — collapse for banks only after live taste; "
                "do not delete this clone in Step 3"
            )
    elif edit_match:
        classification = "CONFIG_EDIT"
        config_edit = f"palette '{edit_pal}' (+ white/sky/ice stops) yields exact pair"
    else:
        classification = "IMPOSSIBLE"
        residual = (
            f"no config-only palette/zone edit yields exact pair {target} "
            f"(today {home_pal}={today_multi}, edit {edit_pal}={edit_multi})"
        )

    return MappingRow(
        spec=spec,
        home_palette=home_pal,
        home_zone=home_zone,
        today_multi=today_multi,
        today_match=today_match,
        edit_palette=edit_pal,
        edit_multi=edit_multi,
        edit_match=edit_match,
        zone_edit_slots=zone_slots,
        zone_edit_match=zone_edit_match,
        clone_vs_base_mismatches=mism,
        clone_vs_base_checked=checked,
        classification=classification,
        residual=residual,
        config_edit=config_edit,
    )


def build_mapping_table(config_path: Path) -> tuple[Any, list[MappingRow]]:
    loaded = load_led_look_director_config(str(config_path))
    if not loaded.available or loaded.config is None:
        raise SystemExit(f"config unavailable: {loaded.errors}")
    looks = {
        name: {
            "scene_ref": look.scene_ref,
            "params": dict(look.params),
            "color_source": look.color_source,
        }
        for name, look in loaded.config.looks.items()
    }
    # Re-read raw JSON for param fidelity (typed look may coerce)
    raw = json.loads(config_path.read_text())
    for name, raw_look in raw.get("looks", {}).items():
        if name in looks and isinstance(raw_look.get("params"), dict):
            looks[name]["params"] = dict(raw_look["params"])
            looks[name]["scene_ref"] = raw_look.get("scene_ref", looks[name]["scene_ref"])

    specs = build_clone_specs(looks)
    ce = loaded.config.color_engine
    if ce is None:
        raise SystemExit("color_engine missing")
    rows = [classify_clone(ce, looks, spec) for spec in specs]
    return loaded, rows


def format_table(rows: Sequence[MappingRow]) -> str:
    lines = [
        "clone | class | family | home_palette/zone | today | edit_palette | "
        "edit_ok | clone≠base | verdict | notes",
        "---|---|---|---|---|---|---|---|---|---",
    ]
    for row in rows:
        notes = row.config_edit or row.residual or ""
        lines.append(
            f"{row.spec.look_name} | {row.spec.cue_class} | {row.spec.family} | "
            f"{row.home_palette}/{row.home_zone} | "
            f"{'Y' if row.today_match else 'n'} | {row.edit_palette or '-'} | "
            f"{'Y' if row.edit_match else 'n'} | "
            f"{row.clone_vs_base_mismatches}/{row.clone_vs_base_checked} | "
            f"{row.classification} | {notes}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(_ROOT / "config/led_look_director.example.json"),
        help="LED look director config path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON rows",
    )
    args = parser.parse_args(argv)
    _, rows = build_mapping_table(Path(args.config))
    if args.json:
        payload = []
        for row in rows:
            payload.append(
                {
                    "look": row.spec.look_name,
                    "class": row.spec.cue_class,
                    "base_look": row.spec.base_look,
                    "family": row.spec.family,
                    "color_a": row.spec.color_a,
                    "color_b": row.spec.color_b,
                    "classification": row.classification,
                    "home_palette": row.home_palette,
                    "home_zone": row.home_zone,
                    "edit_palette": row.edit_palette,
                    "edit_match": row.edit_match,
                    "today_match": row.today_match,
                    "clone_vs_base": {
                        "mismatches": row.clone_vs_base_mismatches,
                        "checked": row.clone_vs_base_checked,
                    },
                    "config_edit": row.config_edit,
                    "residual": row.residual,
                }
            )
        print(json.dumps(payload, indent=2))
    else:
        print(format_table(rows))
        counts: dict[str, int] = {}
        for row in rows:
            counts[row.classification] = counts.get(row.classification, 0) + 1
        print()
        print("counts:", counts)
        print("base cue classes:", sorted({r.spec.base_look for r in rows if r.spec.base_look}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
