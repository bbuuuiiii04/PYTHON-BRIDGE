from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Optional

from ..laser_config import load_laser_director_config
from ..laser_executor import LaserSceneExecutor
from ..laser_models import LaserContext, LaserMidiMessage, LaserSceneDecision
from ..midi_output import MidiOutput

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
_SAFETY_LABEL_TO_KEY = {
    "safe": "safe",
    "gentle movement": "movement_low",
    "medium movement": "movement_medium",
    "high movement": "movement_high",
    "high impact / drop hit": "high_impact",
    "strobe": "strobe",
    "blackout": "blackout",
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
_RESET = "\033[0m"
_GREEN = "\033[92m"
_YELLOW = "\033[33m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_MAGENTA = "\033[95m"
_GRAY = "\033[90m"
_BACK_TOKENS = {"\x1b", "esc", "back", "b", "cancel"}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    value: str
    suggestion: str = ""


class BackRequested(Exception):
    pass


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def is_back_command(value: str) -> bool:
    return (value or "").strip().lower() in _BACK_TOKENS


def _input(prompt: str) -> str:
    return input(_c(prompt, _CYAN)).strip()


def _input_with_back(prompt: str) -> str:
    helper = _c("(Press Escape or type 'back' to go back)", _GRAY)
    entered = _input(f"{prompt} {helper}")
    if is_back_command(entered):
        raise BackRequested()
    return entered


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
    personalities = config.setdefault("personalities", {})
    if _DEFAULT_PERSONALITY in personalities:
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
    return data


def find_duplicate_notes(config: dict[str, Any]) -> list[tuple[int, list[tuple[str, str, str]]]]:
    scenes = config.get("scenes", {})
    personalities = config.get("personalities", {})
    by_note: dict[int, list[tuple[str, str, str]]] = {}
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
                # In Drop mode, post_drop intentionally aliases drop for runtime compatibility.
                # Do not emit duplicate-note warnings for that internal alias.
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
                note = midi.get("note")
                if isinstance(note, int):
                    by_note.setdefault(note, []).append((pname, role, scene_name))
    return sorted((note, refs) for note, refs in by_note.items() if len(refs) > 1)


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
        if isinstance(midi.get("note"), int) and int(midi["note"]) == int(note):
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
    if personality in personalities:
        return
    personalities[personality] = {
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

    # If user switched to Emphasized drop, the first explicit post_drop mapping
    # should replace the Drop-mode alias instead of appending behind it.
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


def validate_config_data(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
        json.dump(config, fp, indent=2, sort_keys=True)
        temp_path = fp.name
    try:
        result = load_laser_director_config(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
    if not result.available:
        errors.extend(result.errors)
    for note, refs in find_duplicate_notes(config):
        refs_text = ", ".join(f"{p}:{r}:{s}" for p, r, s in refs)
        warnings.append(f"duplicate note {note}: {refs_text}")
    personalities = config.get("personalities", {})
    scenes = config.get("scenes", {})
    for pname, pdata in personalities.items():
        if not isinstance(pdata, dict):
            continue
        allow_hi = bool(pdata.get("allow_high_impact", False))
        drop_scene = pdata.get("drop_scene")
        if isinstance(drop_scene, str) and drop_scene in scenes:
            s = scenes[drop_scene]
            if s.get("safety_class") == "high_impact" and not allow_hi:
                warnings.append(
                    f"personality '{pname}' drop scene is high_impact while allow_high_impact=false"
                )
    return errors, warnings


def save_config_atomically(
    config: dict[str, Any],
    path: Path = _DEFAULT_CONFIG_PATH,
) -> Optional[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_name(f"{path.name}.bak-{ts}")
        shutil.copy2(path, backup_path)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(path.parent),
        prefix=f"{path.name}.tmp-",
    ) as fp:
        json.dump(config, fp, indent=2, sort_keys=True)
        fp.write("\n")
        temp_path = Path(fp.name)
    temp_path.replace(path)
    return backup_path


def _print_header() -> None:
    print(_c("\nLASER MIDI MAPPING WIZARD\n", _CYAN))
    print("Step 1: In SoundSwitch, map your Static Look or Autoloop to a MIDI note.")
    print("Step 2: Come back here and tell the bridge what that note means.")
    print("Step 3: The bridge will save the mapping automatically.\n")
    print(_c("Personalities:", _CYAN))
    print("  house (default) - house/groove mappings")
    print("  default         - alias for house")
    print(_c("\nRoles:", _CYAN))
    print("  groove     - normal playing / phrase groove")
    print("  buildup    - UP section before a Smart Drop")
    print("  drop       - exact drop hit")
    print("  breakdown  - low-energy/breakdown section")
    print(_c("  post_drop  - shown only in Emphasized drop style", _GRAY))
    print(_c("\nMIDI notes: 0-127", _CYAN))
    print(_c("\nA bank is multiple scenes for one role. Banks rotate round-robin.", _GRAY))
    print(_c("Adding another note to the same role automatically adds it to that role's bank.\n", _GRAY))


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


def _display_personality(config: dict[str, Any], personality: str) -> None:
    text = render_personality_summary(config, personality)
    for line in text.splitlines():
        if line.strip() == f"{canonical_personality(personality)} (default)" or line.strip() == canonical_personality(personality):
            print(_c(f"\n{line}", _MAGENTA))
        elif line == "Timing:":
            print(_c(line, _CYAN))
        else:
            print(line)


def _show_mappings(config: dict[str, Any]) -> None:
    _display_personality(config, _DEFAULT_PERSONALITY)


def _pick_personality(config: dict[str, Any]) -> str:
    personalities = config.get("personalities", {})
    while True:
        entered = _input_with_back("Personality [house/default]:")
        result = validate_personality(entered, personalities)
        if result.valid:
            return result.value
        print(_c(f"Unknown personality: {entered}", _YELLOW))
        if result.suggestion:
            print(_c(f"Did you mean: {result.suggestion}?", _YELLOW))
            print("1. Use suggestion")
            print(f"2. Create new personality '{result.value}'")
            print("3. Re-enter")
            choice = _input_with_back(">")
            if choice == "1":
                return result.suggestion
            if choice == "2":
                confirm = _input_with_back(
                    f"Create new personality '{result.value}'? type YES to confirm:"
                )
                if confirm == "YES":
                    return result.value
            continue
        print("Re-enter.")


def _pick_role(config: dict[str, Any], personality: str) -> str:
    roles = _visible_roles(config, personality)
    role_text = "/".join(roles)
    while True:
        entered = _input_with_back(f"Role [{role_text}]:")
        result = validate_role(entered)
        if result.valid and result.value in roles:
            return result.value
        print(_c(f"Unknown role: {entered}", _RED))
        if result.suggestion:
            print(_c(f"Did you mean: {result.suggestion}?", _YELLOW))


def _pick_note() -> int:
    while True:
        entered = _input_with_back("MIDI note (0-127):")
        try:
            return parse_midi_note(entered)
        except ValueError as exc:
            print(_c(str(exc), _RED))


def _warn_duplicate_note(
    config: dict[str, Any],
    note: int,
    target: tuple[str, str],
    *,
    confirm_response: Optional[str] = None,
) -> bool:
    refs: list[tuple[str, str, str]] = []
    for dup_note, dup_refs in find_duplicate_notes(config):
        if dup_note == note:
            refs = dup_refs
            break
    if refs:
        role_target = f"{target[0]} {target[1]}"
        print(_c(f"Warning: note {note} is already mapped:", _YELLOW))
        for p, role, scene in refs:
            print(f"  {p} {role} -> {scene}")
        print(f"You are trying to map:\n  {role_target}")
        if confirm_response is None:
            confirm_response = _input("Continue? y/N:")
        return (confirm_response or "").strip().lower() == "y"
    return True


def _pick_behavior(role: str, scene_type: str) -> tuple[str, int, float]:
    default_behavior = _ROLE_DEFAULTS[role]["behavior"]
    if role in ("buildup", "breakdown"):
        default_behavior = "hold_beats"
    if role == "drop" and scene_type == "static":
        default_behavior = "hold_beats"
    print(_c("\nHow should this MIDI note behave?", _CYAN))
    print("  1. Trigger pulse - short press")
    print("  2. Hold for beats - held for musical duration")
    print("  3. Hold for ms - held for fixed milliseconds")
    print("  4. Note on only - advanced/manual")
    print("  5. Note off only - advanced/manual")
    print(_c("If the look requires a held button, choose Hold.", _GRAY))
    choice = _input_with_back(f"Select [default={default_behavior}]:")
    mapping = {
        "1": "pulse",
        "2": "hold_beats",
        "3": "hold_ms",
        "4": "note_on",
        "5": "note_off",
    }
    behavior = mapping.get(choice, default_behavior)
    hold_ms = 0
    hold_beats = 0.0
    if behavior == "hold_beats":
        entered = _input_with_back("Hold beats [default 4]:") or "4"
        hold_beats = max(0.25, min(128.0, float(entered)))
    if behavior == "hold_ms":
        entered = _input_with_back("Hold milliseconds [default 500]:") or "500"
        hold_ms = max(10, min(30000, int(entered)))
    return behavior, hold_ms, hold_beats


def _pick_normal_behavior() -> tuple[str, int, float]:
    entered = _input_with_back(
        "Behavior [pulse] (use hold only in advanced behavior settings):"
    ).strip().lower()
    if entered and entered != "pulse":
        print(_c("Normal setup uses pulse for SoundSwitch autoloops. Falling back to pulse.", _YELLOW))
    return ("pulse", 0, 0.0)


def _pick_advanced_behavior(role: str, scene_type: str) -> tuple[str, int, float]:
    print(_c("\nAdvanced behavior settings", _CYAN))
    print(_c("Use pulse for normal SoundSwitch autoloops.", _GRAY))
    return _pick_behavior(role, scene_type)


def _edit_personality_timing(config: dict[str, Any], personality: str) -> bool:
    pdata = config["personalities"][personality]
    print(_c("\nTiming / Cooldowns", _CYAN))
    print(_c("Groove phrase length = how often groove changes can happen.", _GRAY))
    print(_c("Minimum scene hold = how long scenes stay before normal changes.", _GRAY))
    print(_c("Buildup lookahead = beats before a Smart Drop buildup is allowed.", _GRAY))
    phrase = _input_with_back(f"Groove phrase length ({pdata.get('phrase_interval_beats', 32)}):")
    hold = _input_with_back(f"Minimum scene hold ({pdata.get('minimum_scene_hold_beats', 8)}):")
    lookahead = _input_with_back(f"Buildup lookahead ({pdata.get('buildup_lookahead_beats', 32)}):")
    changed = False
    if phrase:
        update_personality_timing(
            config,
            personality=personality,
            phrase_interval_beats=max(1, int(phrase)),
        )
        changed = True
    if hold:
        update_personality_timing(
            config,
            personality=personality,
            minimum_scene_hold_beats=max(0, int(hold)),
        )
        changed = True
    if lookahead:
        update_personality_timing(
            config,
            personality=personality,
            buildup_lookahead_beats=max(1, int(lookahead)),
        )
        changed = True
    return changed


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


def _pick_scene_from_personality(config: dict[str, Any], personality: str) -> str:
    scenes = config.get("scenes", {})
    options: list[str] = []
    for role in _ROLE_CHOICES:
        for scene_name in _scene_names_for_role(config, personality, role):
            if scene_name not in options:
                options.append(scene_name)
    if not options:
        raise BackRequested()
    print(_c("\nSelect scene:", _CYAN))
    for idx, scene_name in enumerate(options, start=1):
        midi = scenes.get(scene_name, {}).get("midi", {})
        print(f"  {idx}. {scene_name} (note {midi.get('note', '?')})")
    while True:
        entered = _input_with_back("Scene number:")
        try:
            i = int(entered)
        except ValueError:
            print(_c("Enter a valid number.", _RED))
            continue
        if 1 <= i <= len(options):
            return options[i - 1]
        print(_c("Out of range.", _RED))


def _pick_float_non_negative(prompt: str) -> float:
    while True:
        entered = _input_with_back(prompt)
        try:
            value = float(entered)
        except ValueError:
            print(_c("Enter a number.", _RED))
            continue
        if value < 0:
            print(_c("Value must be non-negative.", _RED))
            continue
        return value


def _print_role_bank(config: dict[str, Any], personality: str, role: str) -> None:
    scenes = config.get("scenes", {})
    names = _role_scene_names(config, personality, role)
    print(_c(f"\n{personality} / {role} cooldown", _CYAN))
    print(f"\nCurrent {role} bank:")
    if not names:
        print(_c("  (empty)", _GRAY))
        return
    for idx, scene_name in enumerate(names, start=1):
        scene = scenes.get(scene_name, {})
        midi = scene.get("midi", {})
        note = midi.get("note", "?")
        cooldown = scene.get("cooldown_beats", _ROLE_DEFAULTS[role]["cooldown_beats"])
        print(f"  {idx}. {scene_name:18s} note {note:<3} cooldown {cooldown:g}")


def _set_drop_style(config: dict[str, Any], personality: str) -> bool:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return False
    current = _get_drop_style(config, personality)
    print(_c("\nDrop style", _CYAN))
    print(f"Current: {'Emphasized drop' if current == _DROP_STYLE_EMPHASIZED else 'Drop mode'}")
    print("  1. Drop mode (single drop mapping; post-drop uses same scene)")
    print("  2. Emphasized drop (separate drop and post-drop mappings)")
    choice = _input_with_back("Select style [1/2]:")
    if choice not in {"1", "2"}:
        print(_c("No change.", _YELLOW))
        return False
    selected = _DROP_STYLE_DROP_MODE if choice == "1" else _DROP_STYLE_EMPHASIZED
    pdata["drop_style"] = selected
    if selected == _DROP_STYLE_DROP_MODE:
        drop_scene = pdata.get("drop_scene")
        if isinstance(drop_scene, str) and drop_scene:
            pdata["post_drop_scene"] = drop_scene
            pdata["post_drop_bank"] = [drop_scene]
    print(_c("Drop style updated.", _GREEN))
    return True


def _edit_timing_menu(config: dict[str, Any], personality: str) -> bool:
    changed = False
    while True:
        print(_c("\nTiming / Cooldowns", _CYAN))
        print("  1. Edit global personality timing")
        print("  2. Edit role cooldown")
        print("  3. Set drop style")
        print("  0. Back")
        try:
            choice = _input_with_back(">")
        except BackRequested:
            return changed
        if choice == "1":
            try:
                changed = _edit_personality_timing(config, personality) or changed
            except BackRequested:
                continue
            continue
        if choice == "2":
            try:
                role = _pick_role(config, personality)
                _print_role_bank(config, personality, role)
                mixed, values = detect_mixed_role_cooldowns(
                    config,
                    personality=personality,
                    role=role,
                )
                if mixed:
                    joined = ", ".join(f"{v:g}" for v in values)
                    print(_c(f"{personality}/{role} has mixed cooldowns: {joined}", _YELLOW))
                    if _input("Normalize all mappings to one cooldown? y/N:").lower() != "y":
                        continue
                cooldown = _pick_float_non_negative(
                    f"Set cooldown for all {role} mappings (beats):"
                )
                preview: list[tuple[str, float, float]] = []
                scenes = config.get("scenes", {})
                for scene_name in _role_scene_names(config, personality, role):
                    old = float(
                        scenes.get(scene_name, {}).get(
                            "cooldown_beats",
                            _ROLE_DEFAULTS[role]["cooldown_beats"],
                        )
                    )
                    preview.append((scene_name, old, cooldown))
                print(_c("\nPreview:", _CYAN))
                for scene_name, old, new in preview:
                    print(f"  {scene_name} cooldown {old:g} -> {new:g}")
                if _input("Apply role cooldown? y/N:").lower() != "y":
                    continue
                update_role_bank_cooldown(
                    config,
                    personality=personality,
                    role=role,
                    cooldown_beats=cooldown,
                )
                print(_c(f"Updated {role} role cooldown -> {cooldown:g}", _GREEN))
                changed = True
            except BackRequested:
                continue
            continue
        if choice == "3":
            try:
                changed = _set_drop_style(config, personality) or changed
            except BackRequested:
                continue
            continue
        if choice == "0":
            return changed
        print(_c("Unknown menu option.", _RED))


def _set_port(config: dict[str, Any]) -> None:
    port = _input_with_back(
        f"MIDI output port [{config.get('midi_output_port', _DEFAULT_PORT)}]:"
    )
    if port:
        config["midi_output_port"] = port
        print(_c("MIDI output port updated.", _GREEN))


def _toggle_dry_run(config: dict[str, Any]) -> None:
    config["dry_run"] = not bool(config.get("dry_run", True))
    status = "true" if config["dry_run"] else "false"
    print(_c(f"dry_run={status}", _YELLOW))


def _test_note(config: dict[str, Any]) -> None:
    print(_c("\nTEST NOTE (manual only)", _YELLOW))
    if _input_with_back("Send a test note now? y/N:").lower() != "y":
        return
    note = _pick_note()
    channel = _parse_channel(_input_with_back("Channel [1]:") or "1")
    out = MidiOutput(port_name=config.get("midi_output_port", _DEFAULT_PORT), dry_run=False)
    out.start()
    try:
        msg = LaserMidiMessage(
            kind="note_pulse",
            behavior="pulse",
            channel=channel,
            note=note,
            velocity=127,
            duration_ms=80,
        )
        ok = out.trigger(msg, priority="high")
        time.sleep(0.2)
        status = out.status()
        if not ok or status.get("degraded"):
            print(_c(f"Test failed/degraded: {status.get('degraded_reason', 'unknown')}", _RED))
        else:
            print(_c("Test note sent.", _GREEN))
    finally:
        out.stop()


def _final_preview(config: dict[str, Any], personality: str) -> None:
    _display_personality(config, personality)


def _save_and_exit(config: dict[str, Any], path: Path) -> bool:
    _final_preview(config, _DEFAULT_PERSONALITY)
    if _input("Save changes? y/N:").lower() != "y":
        return False
    backup = save_config_atomically(config, path=path)
    errors, warnings = validate_config_data(config)
    if backup:
        print(_c(f"Backup created: {backup}", _GRAY))
    for warning in warnings:
        print(_c(f"Warning: {warning}", _YELLOW))
    if errors:
        print(_c("Config validation failed after save:", _RED))
        for err in errors:
            print(_c(f"  - {err}", _RED))
    else:
        print(_c("Saved. Restart bridge for changes to take effect.", _GREEN))
    return True


def _pick_scene_from_role(config: dict[str, Any], personality: str, role: str) -> str:
    names = _role_scene_names(config, personality, role)
    if not names:
        raise BackRequested()
    scenes = config.get("scenes", {})
    print(_c(f"\nSelect {role} mapping:", _CYAN))
    for idx, scene_name in enumerate(names, start=1):
        scene = scenes.get(scene_name, {})
        midi = scene.get("midi", {})
        print(f"  {idx}. {scene_name} (note {midi.get('note', '?')}, {_describe_behavior(midi)})")
    while True:
        entered = _input_with_back("Mapping number:")
        try:
            pick = int(entered)
        except ValueError:
            print(_c("Enter a valid number.", _RED))
            continue
        if 1 <= pick <= len(names):
            return names[pick - 1]
        print(_c("Out of range.", _RED))


def _set_primary_scene(config: dict[str, Any], personality: str, role: str, scene_name: str) -> None:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    bank = pdata.get(bank_field) or []
    if scene_name in bank:
        bank = [scene_name] + [s for s in bank if s != scene_name]
        pdata[bank_field] = bank
    pdata[scene_field] = scene_name
    if role == "groove" and not pdata.get("default_scene"):
        pdata["default_scene"] = scene_name


def _remove_scene_from_role(config: dict[str, Any], personality: str, role: str, scene_name: str) -> None:
    pdata = config.get("personalities", {}).get(personality, {})
    if not isinstance(pdata, dict):
        return
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    bank = [s for s in (pdata.get(bank_field) or []) if s != scene_name]
    pdata[bank_field] = bank
    scenes = config.get("scenes", {})
    scenes.pop(scene_name, None)
    if pdata.get(scene_field) == scene_name:
        pdata[scene_field] = bank[0] if bank else ""
    if role == "groove" and pdata.get("default_scene") == scene_name:
        pdata["default_scene"] = pdata.get("phrase_scene") or "safe_static"


def _edit_existing_mapping_flow(config: dict[str, Any]) -> bool:
    try:
        personality = _pick_personality(config)
        role = _pick_role(config, personality)
        scene_name = _pick_scene_from_role(config, personality, role)
    except BackRequested:
        return False
    scenes = config.get("scenes", {})
    scene = scenes.get(scene_name, {})
    if not scene:
        return False
    while True:
        midi = scene.setdefault("midi", {})
        print(_c(f"\nEdit mapping: {scene_name}", _CYAN))
        print(f"  note={midi.get('note', '?')}  behavior={_describe_behavior(midi)}")
        print("  1. Change MIDI note")
        print("  2. Advanced: Change behavior / hold length")
        print("  3. Remove mapping from bank")
        print("  4. Set as primary")
        print("  0. Back")
        try:
            choice = _input_with_back(">")
        except BackRequested:
            return False
        if choice == "1":
            try:
                note = _pick_note()
            except BackRequested:
                continue
            midi["note"] = note
            print(_c("MIDI note updated.", _GREEN))
            return True
        if choice == "2":
            try:
                behavior, hold_ms, hold_beats = _pick_advanced_behavior(
                    role,
                    str(scene.get("scene_type", "autoloop")),
                )
            except BackRequested:
                continue
            midi.update(
                _build_midi_payload(
                    int(midi.get("note", 0)),
                    channel=int(midi.get("channel", 1)),
                    velocity=int(midi.get("velocity", 127)),
                    behavior=behavior,
                    hold_ms=hold_ms,
                    hold_beats=hold_beats,
                )
            )
            print(_c("Behavior updated.", _GREEN))
            return True
        if choice == "3":
            if _input("Remove this mapping from bank? y/N:").lower() != "y":
                continue
            _remove_scene_from_role(config, personality, role, scene_name)
            print(_c("Mapping removed.", _GREEN))
            return True
        if choice == "4":
            _set_primary_scene(config, personality, role, scene_name)
            print(_c("Primary mapping updated.", _GREEN))
            return True
        if choice == "0":
            return False
        print(_c("Unknown menu option.", _RED))


def _advanced_safety_menu(config: dict[str, Any]) -> bool:
    print(_c("\nAdvanced Safety Metadata", _CYAN))
    print(_c("Most users should not change this. Safety class is internal metadata used by the bridge to block risky scenes.", _YELLOW))
    try:
        personality = _pick_personality(config)
        role = _pick_role(config, personality)
        scene_name = _pick_scene_from_role(config, personality, role)
    except BackRequested:
        return False
    scene = config.get("scenes", {}).get(scene_name, {})
    current = scene.get("safety_class", _ROLE_DEFAULTS[role]["safety_class"])
    print(f"Current safety_class: {current}")
    print("Options:")
    keys = list(_SAFETY_KEY_TO_LABEL.keys())
    for idx, key in enumerate(keys, start=1):
        print(f"  {idx}. {key}")
    try:
        entered = _input_with_back("Choose safety class:")
    except BackRequested:
        return False
    try:
        index = int(entered)
        selected = keys[index - 1]
    except Exception:
        selected = entered.strip().lower()
    if selected not in _SAFETY_KEY_TO_LABEL:
        print(_c("Invalid safety class.", _RED))
        return False
    update_scene_safety_class(config, scene_name=scene_name, safety_class=selected)
    print(_c("Safety metadata updated.", _GREEN))
    return True


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


def verify_mappings_runtime(config_path: Path = _DEFAULT_CONFIG_PATH) -> list[tuple[str, bool, str]]:
    result = load_laser_director_config(str(config_path))
    checks: list[tuple[str, bool, str]] = []
    if not result.available or result.config is None:
        reason = result.reason if result.reason else "config unavailable"
        checks.append(("config load", False, reason))
        return checks
    cfg = result.config
    personality = cfg.personalities.get(cfg.default_personality or "")
    if personality is None:
        checks.append(("default personality", False, "missing default personality"))
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
        checks.append(("post_drop", True, "uses same mapping as drop (Drop mode)"))
    beat = 100.0
    for role, scene_name, reason in role_specs:
        scene = cfg.scenes.get(scene_name)
        if scene is None:
            checks.append((f"{role}", False, f"missing scene '{scene_name}'"))
            beat += 64.0
            continue
        before = len(midi.calls)
        ex.on_decision(
            LaserSceneDecision(scene=scene_name, reason=reason, priority=10, source="policy", role="phrase" if role == "groove" else role),
            _verify_ctx(beat, autoloop_tick_just_fired=(role == "groove")),
        )
        after = len(midi.calls)
        if after != before + 1:
            checks.append((f"{role}", False, "no midi trigger"))
            beat += 64.0
            continue
        sent, _ = midi.calls[-1]
        expect_note = scene.midi.note
        if int(sent.note) != int(expect_note):
            checks.append((f"{role}", False, f"expected note {expect_note}, got {sent.note}"))
            beat += 64.0
            continue
        if scene.midi.behavior == "hold_beats":
            ok = sent.behavior == "hold_ms" and int(sent.hold_ms) > 0
            checks.append((f"{role}", ok, f"note {sent.note} hold conversion"))
        else:
            checks.append((f"{role}", True, f"note {sent.note} {_describe_behavior({'behavior': sent.behavior, 'hold_ms': sent.hold_ms, 'hold_beats': sent.hold_beats})}"))
        beat += 64.0

    cooldown_scene = cfg.scenes.get(personality.phrase_scene)
    if cooldown_scene is None or cooldown_scene.cooldown_beats <= 0:
        checks.append(("cooldown enforcement", False, "NOT IMPLEMENTED"))
        return checks
    midi2 = _DryCheckMidiOutput()
    ex2 = LaserSceneExecutor(config=cfg, midi_output=midi2, personality=personality)
    ex2.on_decision(
        LaserSceneDecision(scene=personality.phrase_scene, reason="default_init", priority=10, source="policy", role="phrase"),
        _verify_ctx(500.0, autoloop_tick_just_fired=True),
    )
    ex2.on_decision(
        LaserSceneDecision(scene=personality.phrase_scene, reason="phrase_boundary", priority=10, source="policy", role="phrase"),
        _verify_ctx(500.0 + max(0.0, cooldown_scene.cooldown_beats - 1.0), autoloop_tick_just_fired=True),
    )
    blocked = len(midi2.calls) == 1 and ex2.status().get("last_error") == "role_cooldown_blocked"
    checks.append(("cooldown enforcement", blocked, "role_cooldown_blocked" if blocked else "cooldown not enforced"))
    return checks


def _verify_mappings_menu(config_path: Path) -> None:
    print(_c("\nVerify mappings actually work", _CYAN))
    checks = verify_mappings_runtime(config_path)
    for label, ok, detail in checks:
        state = "PASS" if ok else "FAIL"
        color = _GREEN if ok else _RED
        print(_c(f"{label}: {state}", color) + f"  {detail}")


def get_main_menu_options() -> list[str]:
    return [
        "Show current mappings",
        "Add or update mapping",
        "Edit existing mapping",
        "Timing / Cooldowns",
        "Advanced Safety Metadata",
        "Verify mappings actually work",
        "Validate mappings",
        "Test a MIDI note",
        "Set MIDI output port",
        "Toggle dry_run",
        "Save and exit",
        "Exit without saving",
    ]


def _handle_map_flow(config: dict[str, Any], *, replace_primary: bool = False) -> bool:
    personality = ""
    role = ""
    note = 0
    behavior = "pulse"
    hold_ms = 0
    hold_beats = 0.0
    role_cooldown = 0.0
    step = "personality"
    while True:
        try:
            if step == "personality":
                personality = _pick_personality(config)
                step = "role"
                continue
            if step == "role":
                role = _pick_role(config, personality)
                step = "note"
                continue
            if step == "note":
                note = _pick_note()
                step = "behavior"
                continue
            if step == "behavior":
                behavior, hold_ms, hold_beats = _pick_normal_behavior()
                step = "cooldown"
                continue
            if step == "cooldown":
                default_cd = _ROLE_DEFAULTS[role]["cooldown_beats"]
                entered = _input_with_back(f"Role cooldown beats [default {default_cd:g}]:")
                if not entered:
                    role_cooldown = float(default_cd)
                else:
                    try:
                        value = float(entered)
                    except ValueError:
                        print(_c("Cooldown must be a number.", _RED))
                        continue
                    if value < 0:
                        print(_c("Cooldown must be non-negative.", _RED))
                        continue
                    role_cooldown = value
                step = "mode"
                continue
            if step == "mode":
                _ensure_personality_exists(config, personality)
                effective_replace_primary = replace_primary
                existing_for_note = _find_scene_for_note(
                    config=config,
                    personality=personality,
                    role=role,
                    note=note,
                )
                if not existing_for_note and _primary_scene_for_role(config, personality, role):
                    print(_c("\nThis role already has a primary scene.", _CYAN))
                    print("  1. Add this mapping to bank (default)")
                    print("  2. Replace primary scene")
                    print("  3. Cancel")
                    mode = _input_with_back("Choice [1]:")
                    if mode == "2":
                        effective_replace_primary = True
                    elif mode == "3":
                        return False
                    else:
                        effective_replace_primary = False
                draft = json.loads(json.dumps(config))
                scene_name = apply_mapping(
                    draft,
                    personality=personality,
                    role=role,
                    note=note,
                    replace_primary=effective_replace_primary,
                    behavior=behavior,
                    hold_ms=hold_ms or None,
                    hold_beats=hold_beats or None,
                )
                update_role_bank_cooldown(
                    draft,
                    personality=personality,
                    role=role,
                    cooldown_beats=role_cooldown,
                )
                if not _warn_duplicate_note(draft, note, (personality, role)):
                    return False
                print(_c("\nPreview:", _CYAN))
                print(render_personality_summary(draft, personality))
                if _input("Apply this mapping? y/N:").lower() != "y":
                    return False
                config.clear()
                config.update(draft)
                print(_c(f"Updated {personality}:{role} -> {scene_name} (note {note})", _GREEN))
                print(_c("Tip: mapping the same personality + role again auto-adds to that bank.", _GRAY))
                print(_c("Banks rotate round-robin during performance.", _GRAY))
                return True
        except BackRequested:
            if step == "personality":
                return False
            if step == "role":
                step = "personality"
            elif step == "note":
                step = "role"
            elif step == "behavior":
                step = "note"
            elif step == "cooldown":
                step = "behavior"
            elif step == "mode":
                step = "cooldown"


def run_wizard(config_path: Path = _DEFAULT_CONFIG_PATH) -> int:
    try:
        config = load_or_create_config(config_path)
    except json.JSONDecodeError as exc:
        print(_c(f"Config JSON parse error: {exc}", _RED))
        return 2

    _print_header()
    dirty = False
    while True:
        print(_c("\nMain Menu", _CYAN))
        options = get_main_menu_options()
        for idx, option in enumerate(options, start=1):
            print(f"  {idx}. {option}")
        print("  0. Exit without saving")
        print(_c("Press Escape or type 'back' to go back.", _GRAY))
        choice = _input(">")
        if is_back_command(choice):
            if dirty and _input("Unsaved changes. Exit without saving? y/N:").lower() != "y":
                continue
            print(_c("Exit without saving.", _YELLOW))
            return 0
        if choice == "1":
            _show_mappings(config)
            continue
        if choice == "2":
            dirty = _handle_map_flow(config, replace_primary=False) or dirty
            continue
        if choice == "3":
            dirty = _edit_existing_mapping_flow(config) or dirty
            continue
        if choice == "4":
            try:
                dirty = _edit_timing_menu(config, _DEFAULT_PERSONALITY) or dirty
            except BackRequested:
                continue
            continue
        if choice == "5":
            dirty = _advanced_safety_menu(config) or dirty
            continue
        if choice == "6":
            _verify_mappings_menu(config_path)
            continue
        if choice == "7":
            errors, warnings = validate_config_data(config)
            if not errors and not warnings:
                print(_c("Validation passed.", _GREEN))
                continue
            for warning in warnings:
                print(_c(f"Warning: {warning}", _YELLOW))
            for err in errors:
                print(_c(f"Error: {err}", _RED))
            continue
        if choice == "8":
            try:
                _test_note(config)
            except BackRequested:
                continue
            continue
        if choice == "9":
            try:
                _set_port(config)
                dirty = True
            except BackRequested:
                continue
            continue
        if choice == "10":
            _toggle_dry_run(config)
            dirty = True
            continue
        if choice == "11":
            if _save_and_exit(config, config_path):
                return 0
            continue
        if choice == "12" or choice == "0":
            print(_c("Exit without saving.", _YELLOW))
            return 0
        print(_c("Unknown menu option.", _RED))


def main() -> int:
    path = _DEFAULT_CONFIG_PATH
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser().resolve()
    return run_wizard(path)


if __name__ == "__main__":
    raise SystemExit(main())
