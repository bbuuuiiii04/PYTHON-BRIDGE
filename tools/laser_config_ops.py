from __future__ import annotations

import json
import copy
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Optional

from ..laser_config import LaserConfigResult, load_laser_director_config
from ..laser_executor import LaserSceneExecutor
from ..laser_models import LaserContext, LaserMidiMessage, LaserSceneDecision

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "laser_director.json"
_DEFAULT_PORT = "IAC Driver Bus 1"
_DEFAULT_PERSONALITY = "house"
_PERSONALITY_ALIASES = {"default": _DEFAULT_PERSONALITY}
_ROLE_CHOICES = ("groove", "buildup", "drop", "post_drop", "breakdown")
_DROP_STYLE_DROP_MODE = "drop_mode"
_DROP_STYLE_EMPHASIZED = "emphasized_drop"
_ROLE_FIELD_MAP = {
    "groove": ("phrase_scene", "phrase_bank"),
    "buildup": ("buildup_scene", "buildup_bank"),
    "drop": ("drop_scene", "drop_bank"),
    "post_drop": ("post_drop_scene", "post_drop_bank"),
    "breakdown": ("breakdown_scene", "breakdown_bank"),
}
_SAFETY_KEY_TO_LABEL = {
    "safe": "Safe",
    "movement_low": "Gentle movement",
    "movement_medium": "Medium movement",
    "movement_high": "High movement",
    "high_impact": "High impact / drop hit",
    "strobe": "Strobe",
    "blackout": "Blackout",
}
_ROLE_DEFAULTS = {
    "groove": {
        "scene_type": "autoloop",
        "safety_class": "movement_low",
        "fallback_resolver": lambda p: "safe_static",
        "cooldown_beats": 16.0,
        "immediate": False,
        "behavior": "pulse",
    },
    "buildup": {
        "scene_type": "autoloop",
        "safety_class": "movement_medium",
        "fallback_resolver": lambda p: p.get("phrase_scene") or "safe_static",
        "cooldown_beats": 8.0,
        "immediate": False,
        "behavior": "pulse",
    },
    "drop": {
        "scene_type": "autoloop",
        "safety_class": "high_impact",
        "fallback_resolver": lambda p: (
            p.get("post_drop_scene") or p.get("phrase_scene") or "safe_static"
        ),
        "cooldown_beats": 32.0,
        "immediate": False,
        "behavior": "pulse",
    },
    "post_drop": {
        "scene_type": "autoloop",
        "safety_class": "movement_high",
        "fallback_resolver": lambda p: p.get("phrase_scene") or "safe_static",
        "cooldown_beats": 16.0,
        "immediate": False,
        "behavior": "pulse",
    },
    "breakdown": {
        "scene_type": "autoloop",
        "safety_class": "movement_low",
        "fallback_resolver": lambda p: "safe_static",
        "cooldown_beats": 8.0,
        "immediate": False,
        "behavior": "pulse",
    },
}


def _default_pad_meta(default_personality: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "banks": [
            {
                "id": "bank_1",
                "channel": 1,
                "name": "Bank 1",
                "notes": list(range(0, 32)),
                "default_role": "groove",
                "default_behavior": "pulse",
                "default_duration_ms": 80,
                "default_safety": "movement_low",
                "default_cooldown_beats": 16,
            },
            {
                "id": "bank_2",
                "channel": 1,
                "name": "Bank 2",
                "notes": list(range(32, 64)),
                "default_role": "buildup",
                "default_behavior": "pulse",
                "default_duration_ms": 80,
                "default_safety": "movement_medium",
                "default_cooldown_beats": 8,
            },
            {
                "id": "bank_3",
                "channel": 1,
                "name": "Bank 3",
                "notes": list(range(64, 96)),
                "default_role": "drop",
                "default_behavior": "pulse",
                "default_duration_ms": 80,
                "default_safety": "high_impact",
                "default_cooldown_beats": 32,
            },
            {
                "id": "bank_4",
                "channel": 1,
                "name": "Bank 4",
                "notes": list(range(96, 128)),
                "default_role": "breakdown",
                "default_behavior": "pulse",
                "default_duration_ms": 80,
                "default_safety": "movement_low",
                "default_cooldown_beats": 8,
            },
        ],
        "ui": {
            "bpm_for_test_fire": 128,
            "last_personality": default_personality,
            "last_bank_id": "bank_1",
            "drawer_width_px": 420,
            "show_advanced": False,
        },
        "note_labels": {},
    }


_LEGACY_STALE_BANK_RANGES = (
    (0, 24),
    (24, 48),
    (48, 72),
    (72, 96),
    (96, 128),
)


def _looks_like_legacy_stale_default_banks(banks: list[Any]) -> bool:
    if len(banks) != len(_LEGACY_STALE_BANK_RANGES):
        return False
    for bank, (lo, hi) in zip(banks, _LEGACY_STALE_BANK_RANGES):
        if not isinstance(bank, dict):
            return False
        notes = bank.get("notes")
        if not isinstance(notes, list):
            return False
        if list(notes) != list(range(lo, hi)):
            return False
        if not str(bank.get("name", "")).startswith("Bank "):
            return False
    return True


def _ensure_pad_meta(config: dict[str, Any]) -> None:
    default_personality = str(config.get("default_personality", _DEFAULT_PERSONALITY))
    existing = config.get("_pad_meta")
    if not isinstance(existing, dict):
        config["_pad_meta"] = _default_pad_meta(default_personality)
        return

    banks = existing.get("banks")
    needs_reset = (
        not isinstance(banks, list)
        or len(banks) == 0
        or _looks_like_legacy_stale_default_banks(banks)
    )
    if needs_reset:
        defaults = _default_pad_meta(default_personality)
        existing["banks"] = defaults["banks"]
        if not isinstance(existing.get("ui"), dict):
            existing["ui"] = defaults["ui"]
        if not isinstance(existing.get("note_labels"), dict):
            existing["note_labels"] = defaults["note_labels"]
        existing.setdefault("schema_version", defaults["schema_version"])


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    value: str
    suggestion: str = ""


def suggest_personality(name: str) -> str:
    choices = [_DEFAULT_PERSONALITY, "default"]
    matches = get_close_matches(name, choices, n=1, cutoff=0.6)
    return matches[0] if matches else ""


def suggest_role(name: str) -> str:
    matches = get_close_matches(name, list(_ROLE_CHOICES), n=1, cutoff=0.6)
    return matches[0] if matches else ""


def canonical_personality(name: str) -> str:
    return _PERSONALITY_ALIASES.get(name.strip().lower(), name.strip().lower())


def _get_drop_style(config: dict[str, Any], personality: str) -> str:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return _DROP_STYLE_DROP_MODE
    style = str(pdata.get("drop_style", _DROP_STYLE_DROP_MODE))
    if style not in (_DROP_STYLE_DROP_MODE, _DROP_STYLE_EMPHASIZED):
        return _DROP_STYLE_DROP_MODE
    return style


def _visible_roles(config: dict[str, Any], personality: str) -> tuple[str, ...]:
    if _get_drop_style(config, personality) == _DROP_STYLE_EMPHASIZED:
        return _ROLE_CHOICES
    return ("groove", "buildup", "drop", "breakdown")


def validate_personality(name: str, personalities: dict[str, Any]) -> ValidationResult:
    raw = (name or "").strip().lower()
    canonical = canonical_personality(raw)
    if canonical in personalities:
        return ValidationResult(valid=True, value=canonical)
    suggestion = suggest_personality(raw)
    if suggestion:
        return ValidationResult(
            valid=False,
            value=canonical,
            suggestion=canonical_personality(suggestion),
        )
    return ValidationResult(valid=False, value=canonical)


def validate_role(name: str) -> ValidationResult:
    role = (name or "").strip().lower()
    if role in _ROLE_CHOICES:
        return ValidationResult(valid=True, value=role)
    return ValidationResult(valid=False, value=role, suggestion=suggest_role(role))


def parse_midi_note(value: str) -> int:
    try:
        note = int(value.strip())
    except Exception as exc:  # noqa: BLE001
        raise ValueError("MIDI note must be 0-127.") from exc
    if not (0 <= note <= 127):
        raise ValueError("MIDI note must be 0-127.")
    return note


def _parse_channel(value: str) -> int:
    channel = int(value.strip())
    if not (1 <= channel <= 16):
        raise ValueError("MIDI channel must be 1-16.")
    return channel


def _ensure_scene_baselines(config: dict[str, Any]) -> None:
    scenes = config.setdefault("scenes", {})
    scenes.setdefault(
        "safe_static",
        {
            "scene_type": "static",
            "safety_class": "safe",
            "fallback_scene": "safe_static",
            "cooldown_beats": 0,
            "immediate": True,
            "midi": {
                "kind": "note_pulse",
                "behavior": "pulse",
                "channel": 1,
                "note": 36,
                "velocity": 127,
                "duration_ms": 80,
            },
        },
    )
    scenes.setdefault(
        "emergency_blackout",
        {
            "scene_type": "utility",
            "safety_class": "blackout",
            "fallback_scene": "safe_static",
            "cooldown_beats": 0,
            "immediate": True,
            "midi": {
                "kind": "note_pulse",
                "behavior": "pulse",
                "channel": 1,
                "note": 44,
                "velocity": 127,
                "duration_ms": 80,
            },
        },
    )


def _ensure_house_personality(config: dict[str, Any]) -> None:
    scenes = config.setdefault("scenes", {})
    defaults = [
        ("house_groove_1", "groove", 37),
        ("house_buildup_1", "buildup", 38),
        ("house_drop_1", "drop", 40),
        ("house_post_drop_1", "post_drop", 41),
        ("house_breakdown_1", "breakdown", 42),
    ]
    for scene_name, role, note in defaults:
        role_defaults = _ROLE_DEFAULTS[role]
        scenes.setdefault(
            scene_name,
            {
                "scene_type": role_defaults["scene_type"],
                "safety_class": role_defaults["safety_class"],
                "fallback_scene": role_defaults["fallback_resolver"]({}),
                "cooldown_beats": role_defaults["cooldown_beats"],
                "immediate": role_defaults["immediate"],
                "midi": _build_midi_payload(
                    note,
                    behavior=role_defaults["behavior"],
                    hold_beats=float(role_defaults.get("hold_beats", 0.0)),
                ),
            },
        )
    role_scene_defaults = {
        "phrase_scene": "house_groove_1",
        "buildup_scene": "house_buildup_1",
        "drop_scene": "house_drop_1",
        "post_drop_scene": "house_drop_1",
        "breakdown_scene": "house_breakdown_1",
    }
    role_bank_fields = {
        "phrase_bank": "phrase_scene",
        "buildup_bank": "buildup_scene",
        "drop_bank": "drop_scene",
        "post_drop_bank": "post_drop_scene",
        "breakdown_bank": "breakdown_scene",
    }
    personalities = config.setdefault("personalities", {})
    if _DEFAULT_PERSONALITY in personalities:
        existing = personalities.get(_DEFAULT_PERSONALITY)
        if not isinstance(existing, dict):
            return
        for scene_field, default_scene_name in role_scene_defaults.items():
            if isinstance(existing.get(scene_field), str) and existing.get(scene_field):
                continue
            if default_scene_name in scenes:
                existing[scene_field] = default_scene_name
        for bank_field, scene_field in role_bank_fields.items():
            primary = existing.get(scene_field)
            bank = existing.get(bank_field)
            if isinstance(bank, list) and bank:
                continue
            if isinstance(primary, str) and primary:
                existing[bank_field] = [primary]
        return
    personalities[_DEFAULT_PERSONALITY] = {
        "safe_scene": "safe_static",
        "default_scene": "house_groove_1",
        "phrase_scene": "house_groove_1",
        "buildup_scene": "house_buildup_1",
        "pre_drop_scene": "",
        "drop_scene": "house_drop_1",
        "post_drop_scene": "house_drop_1",
        "breakdown_scene": "house_breakdown_1",
        "transition_scene": "safe_static",
        "phrase_bank": ["house_groove_1"],
        "buildup_bank": ["house_buildup_1"],
        "drop_bank": ["house_drop_1"],
        "post_drop_bank": ["house_drop_1"],
        "breakdown_bank": ["house_breakdown_1"],
        "allow_high_impact": True,
        "drop_style": _DROP_STYLE_DROP_MODE,
        "phrase_interval_beats": 32,
        "minimum_scene_hold_beats": 8,
        "buildup_lookahead_beats": 32,
        "buildup_approach_beats": 8,
        "buildup_hold_beats": 8,
        "pre_drop_lookahead_beats": 4,
    }


def _ensure_core_fields(config: dict[str, Any]) -> None:
    config.setdefault("enabled", False)
    config.setdefault("dry_run", True)
    config.setdefault("smart_drop_mode", "blackout_mask")
    config.setdefault("midi_output_port", _DEFAULT_PORT)
    config.setdefault("startup_scene", "safe_static")
    config.setdefault("stop_scene", "safe_static")
    config.setdefault("stale_scene", "safe_static")
    config.setdefault("emergency_scene", "emergency_blackout")
    config.setdefault("fallback_scene", "safe_static")
    config.setdefault("default_personality", _DEFAULT_PERSONALITY)


def load_or_create_config(path: Path = _DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    _ensure_core_fields(data)
    _ensure_scene_baselines(data)
    _ensure_house_personality(data)
    _ensure_pad_meta(data)
    return data


def _iter_personality_role_scene_refs(
    config: dict[str, Any],
) -> list[tuple[str, str, str, dict[str, Any]]]:
    scenes = config.get("scenes", {})
    personalities = config.get("personalities", {})
    refs: list[tuple[str, str, str, dict[str, Any]]] = []
    for pname, pdata in personalities.items():
        if not isinstance(pdata, dict):
            continue
        drop_scene = pdata.get("drop_scene")
        for role, (scene_field, bank_field) in _ROLE_FIELD_MAP.items():
            scene_names: list[str] = []
            single = pdata.get(scene_field)
            if isinstance(single, str) and single:
                scene_names.append(single)
            bank = pdata.get(bank_field) or []
            if isinstance(bank, list):
                for scene in bank:
                    if isinstance(scene, str) and scene and scene not in scene_names:
                        scene_names.append(scene)
            for scene_name in scene_names:
                if (
                    role == "post_drop"
                    and _get_drop_style(config, pname) == _DROP_STYLE_DROP_MODE
                    and isinstance(drop_scene, str)
                    and drop_scene
                    and scene_name == drop_scene
                ):
                    continue
                scene = scenes.get(scene_name, {})
                midi = scene.get("midi", {})
                refs.append((pname, role, scene_name, midi if isinstance(midi, dict) else {}))
    return refs


def find_duplicate_notes_keyed(
    config: dict[str, Any],
    *,
    by: str = "channel_note",
) -> list[tuple[Any, list[tuple[str, str, str]]]]:
    if by not in {"channel_note", "note"}:
        raise ValueError("by must be 'channel_note' or 'note'.")
    grouped: dict[Any, list[tuple[str, str, str]]] = {}
    for pname, role, scene_name, midi in _iter_personality_role_scene_refs(config):
        note = midi.get("note")
        if not isinstance(note, int):
            continue
        if by == "channel_note":
            channel = midi.get("channel", 1)
            if not isinstance(channel, int):
                channel = 1
            key: Any = (channel, note)
        else:
            key = note
        grouped.setdefault(key, []).append((pname, role, scene_name))
    return sorted((key, refs) for key, refs in grouped.items() if len(refs) > 1)


def find_soft_duplicate_notes(config: dict[str, Any]) -> list[tuple[int, list[tuple[str, str, str]]]]:
    return [
        (int(note), refs)
        for note, refs in find_duplicate_notes_keyed(config, by="note")
    ]


def find_duplicate_notes(config: dict[str, Any]) -> list[tuple[int, list[tuple[str, str, str]]]]:
    return find_soft_duplicate_notes(config)


def _role_scene_name(personality: str, role: str, index: int = 1) -> str:
    return f"{personality}_{role}_{index}"


def _next_scene_name(config: dict[str, Any], personality: str, role: str) -> str:
    scenes = config.get("scenes", {})
    i = 1
    while True:
        candidate = _role_scene_name(personality, role, i)
        if candidate not in scenes:
            return candidate
        i += 1


def _find_scene_for_note(
    *,
    config: dict[str, Any],
    personality: str,
    role: str,
    note: int,
    channel: int = 1,
) -> str:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return ""
    scenes = config.get("scenes", {})
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    candidates: list[str] = []
    single = pdata.get(scene_field)
    if isinstance(single, str) and single:
        candidates.append(single)
    bank = pdata.get(bank_field) or []
    if isinstance(bank, list):
        for name in bank:
            if isinstance(name, str) and name and name not in candidates:
                candidates.append(name)
    for name in candidates:
        scene = scenes.get(name, {})
        midi = scene.get("midi", {})
        midi_note = midi.get("note")
        midi_channel = midi.get("channel", 1)
        if isinstance(midi_note, int) and int(midi_note) == int(note) and int(midi_channel) == int(channel):
            return name
    return ""


def _build_midi_payload(
    note: int,
    *,
    channel: int = 1,
    velocity: int = 127,
    behavior: str = "pulse",
    duration_ms: int = 80,
    hold_ms: int = 0,
    hold_beats: float = 0.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "channel": int(channel),
        "note": int(note),
        "velocity": int(velocity),
        "behavior": behavior,
    }
    if behavior == "pulse":
        payload["kind"] = "note_pulse"
        payload["duration_ms"] = int(duration_ms)
    elif behavior == "hold_ms":
        payload["kind"] = "note_on"
        payload["hold_ms"] = int(hold_ms)
    elif behavior == "hold_beats":
        payload["kind"] = "note_on"
        payload["hold_beats"] = float(hold_beats)
    elif behavior == "note_on":
        payload["kind"] = "note_on"
    elif behavior == "note_off":
        payload["kind"] = "note_off"
    else:
        payload["kind"] = "note_pulse"
        payload["behavior"] = "pulse"
        payload["duration_ms"] = int(duration_ms)
    return payload


def _ensure_personality_exists(config: dict[str, Any], personality: str) -> None:
    personalities = config.setdefault("personalities", {})
    defaults = {
        "safe_scene": "safe_static",
        "default_scene": "",
        "phrase_scene": "",
        "buildup_scene": "",
        "pre_drop_scene": "",
        "drop_scene": "",
        "post_drop_scene": "",
        "breakdown_scene": "",
        "transition_scene": "safe_static",
        "phrase_bank": [],
        "buildup_bank": [],
        "drop_bank": [],
        "post_drop_bank": [],
        "breakdown_bank": [],
        "allow_high_impact": False,
        "drop_style": _DROP_STYLE_DROP_MODE,
        "phrase_interval_beats": 32,
        "minimum_scene_hold_beats": 8,
        "buildup_lookahead_beats": 32,
    }
    if personality in personalities:
        existing = personalities.get(personality)
        if isinstance(existing, dict):
            for key, value in defaults.items():
                if key not in existing:
                    existing[key] = copy.deepcopy(value)
        return
    personalities[personality] = copy.deepcopy(defaults)


def apply_mapping(
    config: dict[str, Any],
    *,
    personality: str,
    role: str,
    note: int,
    channel: int = 1,
    velocity: int = 127,
    add_to_bank: bool = False,
    replace_primary: bool = False,
    behavior: Optional[str] = None,
    hold_ms: Optional[int] = None,
    hold_beats: Optional[float] = None,
    cooldown_beats: Optional[float] = None,
    safety_class: Optional[str] = None,
    immediate: Optional[bool] = None,
) -> str:
    if role not in _ROLE_CHOICES:
        raise ValueError(f"unknown role: {role}")
    if not (0 <= int(note) <= 127):
        raise ValueError("MIDI note must be 0-127.")
    if not (1 <= int(channel) <= 16):
        raise ValueError("MIDI channel must be 1-16.")

    personality = canonical_personality(personality)
    _ensure_core_fields(config)
    _ensure_scene_baselines(config)
    _ensure_personality_exists(config, personality)
    scenes = config.setdefault("scenes", {})
    pdata = config["personalities"][personality]
    drop_style = _get_drop_style(config, personality)
    if role == "post_drop" and drop_style == _DROP_STYLE_DROP_MODE:
        raise ValueError("post_drop mapping is only available in Emphasized drop style.")
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    defaults = _ROLE_DEFAULTS[role]
    bank = pdata.setdefault(bank_field, [])
    if not isinstance(bank, list):
        bank = []
        pdata[bank_field] = bank

    if (
        role == "post_drop"
        and drop_style == _DROP_STYLE_EMPHASIZED
        and isinstance(pdata.get("drop_scene"), str)
        and pdata.get("post_drop_scene") == pdata.get("drop_scene")
    ):
        drop_scene_name = str(pdata.get("drop_scene"))
        pdata["post_drop_scene"] = ""
        bank = [name for name in bank if name != drop_scene_name]
        pdata[bank_field] = bank

    primary_scene = pdata.get(scene_field)
    has_primary = isinstance(primary_scene, str) and primary_scene in scenes
    existing_scene_for_note = _find_scene_for_note(
        config=config,
        personality=personality,
        role=role,
        note=int(note),
        channel=int(channel),
    )
    if existing_scene_for_note:
        scene_name = existing_scene_for_note
    elif add_to_bank or (has_primary and not replace_primary):
        scene_name = _next_scene_name(config, personality, role)
        if scene_name not in bank:
            bank.append(scene_name)
    elif has_primary and replace_primary:
        scene_name = str(primary_scene)
    else:
        scene_name = _next_scene_name(config, personality, role)
        pdata[scene_field] = scene_name
        if scene_name not in bank:
            bank.insert(0, scene_name)

    fallback_scene = defaults["fallback_resolver"](pdata)
    scene = scenes.get(scene_name, {})
    scene["scene_type"] = scene.get("scene_type", defaults["scene_type"])
    scene["safety_class"] = safety_class or scene.get("safety_class") or defaults["safety_class"]
    scene["fallback_scene"] = scene.get("fallback_scene") or fallback_scene
    scene["cooldown_beats"] = (
        float(cooldown_beats)
        if cooldown_beats is not None
        else float(scene.get("cooldown_beats", defaults["cooldown_beats"]))
    )
    scene["immediate"] = (
        bool(immediate)
        if immediate is not None
        else bool(scene.get("immediate", defaults["immediate"]))
    )
    resolved_behavior = behavior or scene.get("midi", {}).get("behavior") or defaults["behavior"]
    resolved_hold_beats = (
        float(hold_beats)
        if hold_beats is not None
        else float(scene.get("midi", {}).get("hold_beats", defaults.get("hold_beats", 0.0)))
    )
    resolved_hold_ms = (
        int(hold_ms)
        if hold_ms is not None
        else int(scene.get("midi", {}).get("hold_ms", 0))
    )
    scene["midi"] = _build_midi_payload(
        int(note),
        channel=int(channel),
        velocity=int(velocity),
        behavior=resolved_behavior,
        hold_ms=resolved_hold_ms,
        hold_beats=resolved_hold_beats,
    )
    scenes[scene_name] = scene
    if role == "groove":
        if replace_primary or not pdata.get("phrase_scene"):
            pdata["phrase_scene"] = scene_name
        if not pdata.get("default_scene"):
            pdata["default_scene"] = pdata.get("phrase_scene") or scene_name
    else:
        if replace_primary or not pdata.get(scene_field):
            pdata[scene_field] = scene_name
    if role == "drop" and drop_style == _DROP_STYLE_DROP_MODE:
        pdata["post_drop_scene"] = scene_name
        post_bank = pdata.setdefault("post_drop_bank", [])
        if not isinstance(post_bank, list):
            post_bank = []
            pdata["post_drop_bank"] = post_bank
        if scene_name not in post_bank:
            post_bank.clear()
            post_bank.append(scene_name)
    primary_name = pdata.get(scene_field if role != "groove" else "phrase_scene")
    if isinstance(primary_name, str) and primary_name and primary_name not in bank:
        bank.insert(0, primary_name)
    return scene_name


def add_mapping_to_bank(config: dict[str, Any], **kwargs: Any) -> str:
    kwargs["add_to_bank"] = True
    return apply_mapping(config, **kwargs)


def validate_config_data(
    config: dict[str, Any],
    *,
    loader_result: Optional[LaserConfigResult] = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    result = loader_result
    if result is None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(config, fp, indent=2, sort_keys=True)
            temp_path = fp.name
        try:
            result = load_laser_director_config(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
    assert result is not None
    if not result.available:
        errors.extend(result.errors)
    for note, refs in find_duplicate_notes(config):
        refs_text = ", ".join(f"{p}:{r}:{s}" for p, r, s in refs)
        warnings.append(f"duplicate note {note}: {refs_text}")
    for collision in find_bank_range_collisions(config.get("_pad_meta", {})):
        notes = collision["overlap_notes"]
        if not notes:
            note_text = "notes unknown"
        elif len(notes) == 1:
            note_text = f"note {notes[0]}"
        else:
            note_text = f"notes {notes[0]}-{notes[-1]}"
        warnings.append(
            "bank channel overlap: "
            f"{collision['bank_a']} <-> {collision['bank_b']} on "
            f"Ch{collision['channel']} {note_text}"
        )
    personalities = config.get("personalities", {})
    scenes = config.get("scenes", {})
    for pname, pdata in personalities.items():
        if not isinstance(pdata, dict):
            continue
        allow_hi = bool(pdata.get("allow_high_impact", False))
        drop_scene = pdata.get("drop_scene")
        if isinstance(drop_scene, str) and drop_scene in scenes:
            scene = scenes[drop_scene]
            if scene.get("safety_class") == "high_impact" and not allow_hi:
                warnings.append(
                    f"personality '{pname}' drop scene is high_impact while allow_high_impact=false"
                )
    manual_commands = config.get("manual_commands", {})
    blackout_on = (
        manual_commands.get("blackout_on")
        if isinstance(manual_commands, dict)
        else config.get("manual_blackout_on")
    )
    blackout_off = (
        manual_commands.get("blackout_off")
        if isinstance(manual_commands, dict)
        else config.get("manual_blackout_off")
    )
    has_drop_mapping = False
    for pdata in personalities.values():
        if not isinstance(pdata, dict):
            continue
        drop_scene = pdata.get("drop_scene")
        if isinstance(drop_scene, str) and drop_scene:
            has_drop_mapping = True
            break
    smart_drop_mode = str(config.get("smart_drop_mode", "blackout_mask")).strip().lower()
    if smart_drop_mode == "blackout_mask" and has_drop_mapping:
        has_blackout_on = isinstance(blackout_on, dict)
        has_blackout_off = isinstance(blackout_off, dict)
        if not has_blackout_on:
            warnings.append(
                "manual_commands.blackout_on is not configured; blackout_mask mode cannot arm blackout MIDI"
            )
        if not has_blackout_off:
            warnings.append(
                "manual_commands.blackout_off is not configured; blackout_mask mode cannot clear blackout MIDI"
            )
        if not has_blackout_on and not has_blackout_off:
            warnings.append(
                "Smart Drop mode is blackout_mask but blackout commands are missing; transitions will run without blackout masking"
            )
        if bool(config.get("enabled")) and not bool(config.get("dry_run", True)) and (
            not has_blackout_on or not has_blackout_off
        ):
            warnings.append(
                "LIVE WARNING: enabled=true and dry_run=false with incomplete blackout commands in blackout_mask mode"
            )
    elif smart_drop_mode == "legacy_rearm":
        if isinstance(blackout_on, dict) or isinstance(blackout_off, dict):
            warnings.append(
                "manual blackout commands are configured but smart_drop_mode=legacy_rearm; blackout commands are unused"
            )
    return errors, warnings


def find_bank_range_collisions(pad_meta: dict[str, Any]) -> list[dict[str, Any]]:
    banks = pad_meta.get("banks", []) if isinstance(pad_meta, dict) else []
    if not isinstance(banks, list):
        return []
    out: list[dict[str, Any]] = []
    for i, bank_a in enumerate(banks):
        if not isinstance(bank_a, dict):
            continue
        for bank_b in banks[i + 1 :]:
            if not isinstance(bank_b, dict):
                continue
            try:
                channel_a = int(bank_a.get("channel", 1))
                channel_b = int(bank_b.get("channel", 1))
            except (TypeError, ValueError):
                continue
            if channel_a != channel_b:
                continue
            notes_a = set(bank_a.get("notes") or [])
            notes_b = set(bank_b.get("notes") or [])
            overlap = sorted(int(note) for note in notes_a & notes_b)
            if overlap:
                out.append(
                    {
                        "bank_a": bank_a.get("id"),
                        "bank_b": bank_b.get("id"),
                        "channel": channel_a,
                        "overlap_notes": overlap[:8],
                    }
                )
    return out


def save_config_atomically(
    config: dict[str, Any],
    path: Path = _DEFAULT_CONFIG_PATH,
) -> Optional[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = path.with_name(f"{path.name}.bak-{ts}")
        if backup_path.exists():
            suffix = 1
            while True:
                candidate = path.with_name(f"{path.name}.bak-{ts}-{suffix}")
                if not candidate.exists():
                    backup_path = candidate
                    break
                suffix += 1
        shutil.copy2(path, backup_path)
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(path.parent),
            prefix=f"{path.name}.tmp-",
        ) as fp:
            temp_path = Path(fp.name)
            json.dump(config, fp, indent=2, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return backup_path


def _describe_behavior(midi: dict[str, Any]) -> str:
    behavior = str(midi.get("behavior", "pulse"))
    if behavior == "hold_beats":
        beats = midi.get("hold_beats", 0)
        return f"hold {beats:g} beats"
    if behavior == "hold_ms":
        return f"hold {int(midi.get('hold_ms', 0))} ms"
    if behavior == "note_on":
        return "note_on only"
    if behavior == "note_off":
        return "note_off only"
    return "pulse"


def _scene_names_for_role(config: dict[str, Any], personality: str, role: str) -> list[str]:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return []
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    names: list[str] = []
    primary = pdata.get(scene_field)
    if isinstance(primary, str) and primary:
        names.append(primary)
    bank = pdata.get(bank_field) or []
    if isinstance(bank, list):
        for name in bank:
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return names


def _role_scene_names(config: dict[str, Any], personality: str, role: str) -> list[str]:
    return _scene_names_for_role(config, personality, role)


def detect_mixed_role_cooldowns(
    config: dict[str, Any],
    *,
    personality: str,
    role: str,
) -> tuple[bool, list[float]]:
    scenes = config.get("scenes", {})
    values: list[float] = []
    for scene_name in _role_scene_names(config, personality, role):
        scene = scenes.get(scene_name, {})
        values.append(float(scene.get("cooldown_beats", _ROLE_DEFAULTS[role]["cooldown_beats"])))
    uniq = sorted(set(values))
    return (len(uniq) > 1), uniq


def update_scene_safety_class(
    config: dict[str, Any],
    *,
    scene_name: str,
    safety_class: str,
) -> None:
    if safety_class not in _SAFETY_KEY_TO_LABEL:
        raise ValueError(f"unsupported safety_class: {safety_class}")
    scenes = config.setdefault("scenes", {})
    if scene_name not in scenes:
        raise ValueError(f"unknown scene: {scene_name}")
    scenes[scene_name]["safety_class"] = safety_class


def render_personality_summary(config: dict[str, Any], personality: str) -> str:
    personality = canonical_personality(personality)
    pdata = config.get("personalities", {}).get(personality, {})
    scenes = config.get("scenes", {})
    title = f"{personality} (default)" if personality == _DEFAULT_PERSONALITY else personality
    lines: list[str] = [title]
    visible_roles = _visible_roles(config, personality)
    for role in visible_roles:
        names = _role_scene_names(config, personality, role)
        if not names:
            lines.append(f"  {role:10s} note -           cooldown -    pulse")
            continue
        notes: list[str] = []
        cooldowns: list[float] = []
        behaviors: list[str] = []
        for scene_name in names:
            scene = scenes.get(scene_name, {})
            midi = scene.get("midi", {})
            note = midi.get("note", "?")
            notes.append(str(note))
            cooldowns.append(float(scene.get("cooldown_beats", _ROLE_DEFAULTS[role]["cooldown_beats"])))
            behaviors.append(_describe_behavior(midi))
        note_text = f"notes {','.join(notes)}" if len(notes) > 1 else f"note {notes[0]}"
        cooldown_set = sorted(set(cooldowns))
        cooldown_text = (
            f"cooldown {cooldown_set[0]:g}"
            if len(cooldown_set) == 1
            else f"cooldown mixed({','.join(f'{c:g}' for c in cooldown_set)})"
        )
        behavior_set = sorted(set(behaviors))
        behavior_text = behavior_set[0] if len(behavior_set) == 1 else "mixed"
        lines.append(f"  {role:10s} {note_text:15s} {cooldown_text:14s} {behavior_text}")
    style = _get_drop_style(config, personality)
    if style == _DROP_STYLE_EMPHASIZED:
        lines.append("\nDrop style: Emphasized drop")
    else:
        lines.append("\nDrop style: Drop mode")
        lines.append("Post-drop: uses the same drop autoloop mapping")
    lines.append("\nTiming:")
    lines.append(f"  Groove phrase length: {pdata.get('phrase_interval_beats', 32)} beats")
    lines.append(f"  Minimum scene hold: {pdata.get('minimum_scene_hold_beats', 8)} beats")
    lines.append(f"  Buildup lookahead: {pdata.get('buildup_lookahead_beats', 32)} beats")
    return "\n".join(lines)


def _primary_scene_for_role(config: dict[str, Any], personality: str, role: str) -> str:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return ""
    scene_field, _ = _ROLE_FIELD_MAP[role]
    primary = pdata.get(scene_field)
    if isinstance(primary, str):
        return primary
    return ""


def update_scene_cooldown(
    config: dict[str, Any],
    *,
    scene_name: str,
    cooldown_beats: float,
) -> None:
    if cooldown_beats < 0:
        raise ValueError("cooldown_beats must be non-negative.")
    scenes = config.setdefault("scenes", {})
    if scene_name not in scenes:
        raise ValueError(f"unknown scene: {scene_name}")
    scenes[scene_name]["cooldown_beats"] = float(cooldown_beats)


def update_personality_timing(
    config: dict[str, Any],
    *,
    personality: str,
    phrase_interval_beats: Optional[int] = None,
    minimum_scene_hold_beats: Optional[int] = None,
    buildup_lookahead_beats: Optional[int] = None,
) -> None:
    pdata = config.setdefault("personalities", {}).setdefault(personality, {})
    if phrase_interval_beats is not None:
        if phrase_interval_beats < 1:
            raise ValueError("phrase_interval_beats must be positive.")
        pdata["phrase_interval_beats"] = int(phrase_interval_beats)
    if minimum_scene_hold_beats is not None:
        if minimum_scene_hold_beats < 0:
            raise ValueError("minimum_scene_hold_beats must be non-negative.")
        pdata["minimum_scene_hold_beats"] = int(minimum_scene_hold_beats)
    if buildup_lookahead_beats is not None:
        if buildup_lookahead_beats < 1:
            raise ValueError("buildup_lookahead_beats must be positive.")
        pdata["buildup_lookahead_beats"] = int(buildup_lookahead_beats)


def update_role_bank_cooldown(
    config: dict[str, Any],
    *,
    personality: str,
    role: str,
    cooldown_beats: float,
) -> None:
    if role not in _ROLE_CHOICES:
        raise ValueError(f"unknown role: {role}")
    if cooldown_beats < 0:
        raise ValueError("cooldown_beats must be non-negative.")
    for scene_name in _scene_names_for_role(config, personality, role):
        update_scene_cooldown(config, scene_name=scene_name, cooldown_beats=cooldown_beats)


def update_personality_cooldown(
    config: dict[str, Any],
    *,
    personality: str,
    cooldown_beats: float,
) -> None:
    for role in _ROLE_CHOICES:
        update_role_bank_cooldown(
            config,
            personality=personality,
            role=role,
            cooldown_beats=cooldown_beats,
        )


class _DryCheckMidiOutput:
    def __init__(self) -> None:
        self.calls: list[tuple[LaserMidiMessage, str]] = []

    def trigger(self, msg: LaserMidiMessage, priority: str = "normal") -> bool:
        self.calls.append((msg, priority))
        return True

    def status(self) -> dict:
        return {"dry_run": True, "trigger_count": len(self.calls)}


def _verify_ctx(abs_beat: float, *, autoloop_tick_just_fired: bool = False) -> LaserContext:
    return LaserContext(
        active_deck=1,
        playing=True,
        elapsed_ms=1000,
        bpm=128.0,
        beatpos=0.0,
        abs_beat=abs_beat,
        position_stale=False,
        lighting_mode="autoloop",
        os2l_connected=True,
        active_track_loaded=True,
        autoloop_ready=True,
        autoloop_tick_just_fired=autoloop_tick_just_fired,
        scripted_id=0,
    )


def verify_mappings_runtime(config_path: Path = _DEFAULT_CONFIG_PATH) -> list[dict[str, Any]]:
    result = load_laser_director_config(str(config_path))
    checks: list[dict[str, Any]] = []

    def add_check(
        name: str,
        ok: bool,
        detail: str,
        *,
        personality_name: str = "",
        role: str = "",
        scene_name: str = "",
        channel: Optional[int] = None,
        note: Optional[int] = None,
    ) -> None:
        row: dict[str, Any] = {
            "name": name,
            "ok": ok,
            "detail": detail,
            "personality": personality_name,
            "role": role,
            "scene_name": scene_name,
        }
        if channel is not None:
            row["channel"] = int(channel)
        if note is not None:
            row["note"] = int(note)
        checks.append(row)

    if not result.available or result.config is None:
        reason = result.reason if result.reason else "config unavailable"
        add_check("config load", False, reason)
        return checks
    cfg = result.config
    if str(getattr(cfg, "smart_drop_mode", "blackout_mask")) == "blackout_mask":
        has_blackout_pair = cfg.manual_blackout_on is not None and cfg.manual_blackout_off is not None
        add_check(
            "smart_drop_blackout_commands",
            has_blackout_pair,
            "ready" if has_blackout_pair else "missing blackout_on/blackout_off for blackout_mask mode",
        )
    personality = cfg.personalities.get(cfg.default_personality or "")
    if personality is None:
        add_check("default personality", False, "missing default personality")
        return checks

    midi = _DryCheckMidiOutput()
    ex = LaserSceneExecutor(config=cfg, midi_output=midi, personality=personality)
    role_specs = [
        ("groove", personality.phrase_scene, "default_init"),
        ("buildup", personality.buildup_scene, "buildup_to_drop_window"),
        ("drop", personality.drop_scene, "drop_crossing"),
        ("breakdown", personality.breakdown_scene, "breakdown_hold"),
    ]
    if personality.post_drop_scene and personality.post_drop_scene != personality.drop_scene:
        role_specs.insert(3, ("post_drop", personality.post_drop_scene, "post_drop_hold"))
    elif personality.post_drop_scene == personality.drop_scene:
        drop_scene = cfg.scenes.get(personality.drop_scene)
        add_check(
            "post_drop",
            True,
            "uses same mapping as drop (Drop mode)",
            personality_name=cfg.default_personality or "",
            role="post_drop",
            scene_name=personality.drop_scene,
            channel=drop_scene.midi.channel if drop_scene else None,
            note=drop_scene.midi.note if drop_scene else None,
        )
    beat = 100.0
    for role, scene_name, reason in role_specs:
        scene = cfg.scenes.get(scene_name)
        if scene is None:
            add_check(
                f"{role}",
                False,
                f"missing scene '{scene_name}'",
                personality_name=cfg.default_personality or "",
                role=role,
                scene_name=scene_name,
            )
            beat += 64.0
            continue
        before = len(midi.calls)
        ex.on_decision(
            LaserSceneDecision(
                scene=scene_name,
                reason=reason,
                priority=10,
                source="policy",
                role="phrase" if role == "groove" else role,
            ),
            _verify_ctx(beat, autoloop_tick_just_fired=(role == "groove")),
        )
        after = len(midi.calls)
        if after != before + 1:
            add_check(
                f"{role}",
                False,
                "no midi trigger",
                personality_name=cfg.default_personality or "",
                role=role,
                scene_name=scene_name,
                channel=scene.midi.channel,
                note=scene.midi.note,
            )
            beat += 64.0
            continue
        sent, _ = midi.calls[-1]
        expect_note = scene.midi.note
        if int(sent.note) != int(expect_note):
            add_check(
                f"{role}",
                False,
                f"expected note {expect_note}, got {sent.note}",
                personality_name=cfg.default_personality or "",
                role=role,
                scene_name=scene_name,
                channel=scene.midi.channel,
                note=scene.midi.note,
            )
            beat += 64.0
            continue
        if scene.midi.behavior == "hold_beats":
            ok = sent.behavior == "hold_ms" and int(sent.hold_ms) > 0
            add_check(
                f"{role}",
                ok,
                f"note {sent.note} hold conversion",
                personality_name=cfg.default_personality or "",
                role=role,
                scene_name=scene_name,
                channel=scene.midi.channel,
                note=scene.midi.note,
            )
        else:
            add_check(
                f"{role}",
                True,
                f"note {sent.note} {_describe_behavior({'behavior': sent.behavior, 'hold_ms': sent.hold_ms, 'hold_beats': sent.hold_beats})}",
                personality_name=cfg.default_personality or "",
                role=role,
                scene_name=scene_name,
                channel=scene.midi.channel,
                note=scene.midi.note,
            )
        beat += 64.0

    cooldown_scene = cfg.scenes.get(personality.phrase_scene)
    if cooldown_scene is None or cooldown_scene.cooldown_beats <= 0:
        add_check(
            "cooldown enforcement",
            False,
            "NOT IMPLEMENTED",
            personality_name=cfg.default_personality or "",
            role="groove",
            scene_name=personality.phrase_scene,
        )
        return checks
    midi2 = _DryCheckMidiOutput()
    ex2 = LaserSceneExecutor(config=cfg, midi_output=midi2, personality=personality)
    ex2.on_decision(
        LaserSceneDecision(
            scene=personality.phrase_scene,
            reason="default_init",
            priority=10,
            source="policy",
            role="phrase",
        ),
        _verify_ctx(500.0, autoloop_tick_just_fired=True),
    )
    ex2.on_decision(
        LaserSceneDecision(
            scene=personality.phrase_scene,
            reason="phrase_boundary",
            priority=10,
            source="policy",
            role="phrase",
        ),
        _verify_ctx(500.0 + max(0.0, cooldown_scene.cooldown_beats - 1.0), autoloop_tick_just_fired=True),
    )
    blocked = len(midi2.calls) == 1 and ex2.status().get("last_error") == "role_cooldown_blocked"
    add_check(
        "cooldown enforcement",
        blocked,
        "role_cooldown_blocked" if blocked else "cooldown not enforced",
        personality_name=cfg.default_personality or "",
        role="groove",
        scene_name=personality.phrase_scene,
        channel=cooldown_scene.midi.channel,
        note=cooldown_scene.midi.note,
    )
    return checks
