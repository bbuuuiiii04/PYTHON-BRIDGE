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
from ..laser_models import LaserMidiMessage
from ..midi_output import MidiOutput

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "laser_director.json"
_DEFAULT_PORT = "IAC Driver Bus 1"
_DEFAULT_PERSONALITY = "house"
_PERSONALITY_ALIASES = {"default": _DEFAULT_PERSONALITY}
_ROLE_CHOICES = ("groove", "buildup", "drop", "post_drop", "breakdown")
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
        "scene_type": "static",
        "safety_class": "high_impact",
        "fallback_resolver": lambda p: (
            p.get("post_drop_scene") or p.get("phrase_scene") or "safe_static"
        ),
        "cooldown_beats": 32.0,
        "immediate": True,
        "behavior": "hold_beats",
        "hold_beats": 4.0,
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


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    value: str
    suggestion: str = ""


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def suggest_personality(name: str) -> str:
    choices = [_DEFAULT_PERSONALITY, "default"]
    matches = get_close_matches(name, choices, n=1, cutoff=0.6)
    return matches[0] if matches else ""


def suggest_role(name: str) -> str:
    matches = get_close_matches(name, list(_ROLE_CHOICES), n=1, cutoff=0.6)
    return matches[0] if matches else ""


def canonical_personality(name: str) -> str:
    return _PERSONALITY_ALIASES.get(name.strip().lower(), name.strip().lower())


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
        "post_drop_scene": "house_post_drop_1",
        "breakdown_scene": "house_breakdown_1",
        "transition_scene": "safe_static",
        "phrase_bank": ["house_groove_1"],
        "buildup_bank": ["house_buildup_1"],
        "drop_bank": ["house_drop_1"],
        "post_drop_bank": ["house_post_drop_1"],
        "breakdown_bank": ["house_breakdown_1"],
        "allow_high_impact": False,
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
    scene_field, bank_field = _ROLE_FIELD_MAP[role]
    defaults = _ROLE_DEFAULTS[role]
    bank = pdata.setdefault(bank_field, [])
    if not isinstance(bank, list):
        bank = []
        pdata[bank_field] = bank

    scene_name = ""
    if add_to_bank:
        scene_name = _next_scene_name(config, personality, role)
        bank.append(scene_name)
    else:
        existing = pdata.get(scene_field)
        if isinstance(existing, str) and existing in scenes:
            scene_name = existing
        elif bank:
            first = bank[0]
            if isinstance(first, str) and first in scenes:
                scene_name = first
        if not scene_name:
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
        pdata["phrase_scene"] = scene_name
        if not pdata.get("default_scene"):
            pdata["default_scene"] = scene_name
    else:
        pdata[scene_field] = scene_name
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


def _input(prompt: str) -> str:
    return input(_c(prompt, _CYAN)).strip()


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
    print("  post_drop  - sustained look after drop hit")
    print("  breakdown  - low-energy/breakdown section")
    print(_c("\nMIDI notes: 0-127", _CYAN))
    print(_c("\nA bank is multiple scenes for one role. Banks rotate round-robin.\n", _GRAY))


def _display_personality(config: dict[str, Any], personality: str) -> None:
    personality = canonical_personality(personality)
    pdata = config.get("personalities", {}).get(personality, {})
    scenes = config.get("scenes", {})
    title = f"{personality} (default)" if personality == _DEFAULT_PERSONALITY else personality
    print(_c(f"\nPersonality: {title}", _MAGENTA))
    for role in _ROLE_CHOICES:
        scene_field, bank_field = _ROLE_FIELD_MAP[role]
        bank = pdata.get(bank_field) or []
        print(_c(f"\n{role} bank:", _CYAN))
        if not bank:
            single = pdata.get(scene_field)
            if isinstance(single, str) and single:
                bank = [single]
        if not bank:
            print(_c("  (empty)", _GRAY))
            continue
        for idx, scene_name in enumerate(bank, start=1):
            scene = scenes.get(scene_name, {})
            midi = scene.get("midi", {})
            note = midi.get("note", "?")
            groove_tag = " (groove)" if role == "groove" and "phrase" in scene_name else ""
            print(f"  {idx}. {scene_name:22s} note {note}{groove_tag}")


def _show_mappings(config: dict[str, Any]) -> None:
    _display_personality(config, _DEFAULT_PERSONALITY)


def _pick_personality(config: dict[str, Any]) -> str:
    personalities = config.get("personalities", {})
    while True:
        entered = _input("Personality [house/default]: ")
        result = validate_personality(entered, personalities)
        if result.valid:
            return result.value
        print(_c(f"Unknown personality: {entered}", _YELLOW))
        if result.suggestion:
            print(_c(f"Did you mean: {result.suggestion}?", _YELLOW))
            print("1. Use suggestion")
            print(f"2. Create new personality '{result.value}'")
            print("3. Re-enter")
            choice = _input("> ")
            if choice == "1":
                return result.suggestion
            if choice == "2":
                confirm = _input(
                    f"Create new personality '{result.value}'? type YES to confirm: "
                )
                if confirm == "YES":
                    return result.value
            continue
        print("Re-enter.")


def _pick_role() -> str:
    while True:
        entered = _input("Role [groove/buildup/drop/post_drop/breakdown]: ")
        result = validate_role(entered)
        if result.valid:
            return result.value
        print(_c(f"Unknown role: {entered}", _RED))
        if result.suggestion:
            print(_c(f"Did you mean: {result.suggestion}?", _YELLOW))


def _pick_note() -> int:
    while True:
        entered = _input("MIDI note (0-127): ")
        try:
            return parse_midi_note(entered)
        except ValueError as exc:
            print(_c(str(exc), _RED))


def _warn_duplicate(config: dict[str, Any], note: int, target: tuple[str, str]) -> bool:
    duplicates = find_duplicate_notes(config)
    for dup_note, refs in duplicates:
        if dup_note != note:
            continue
        role_target = f"{target[0]} {target[1]}"
        print(_c(f"Warning: note {note} is already mapped:", _YELLOW))
        for p, role, scene in refs:
            print(f"  {p} {role} -> {scene}")
        print(f"You are trying to map:\n  {role_target}")
        return _input("Continue? y/N: ").lower() == "y"
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
    choice = _input(f"Select [default={default_behavior}]: ")
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
        entered = _input("Hold beats [default 4]: ") or "4"
        hold_beats = max(0.25, min(128.0, float(entered)))
    if behavior == "hold_ms":
        entered = _input("Hold milliseconds [default 500]: ") or "500"
        hold_ms = max(10, min(30000, int(entered)))
    return behavior, hold_ms, hold_beats


def _edit_timing(config: dict[str, Any], personality: str) -> None:
    pdata = config["personalities"][personality]
    print(_c("\nAdvanced Timing / Cooldowns", _CYAN))
    print(_c("Groove phrase length = how often groove changes can happen.", _GRAY))
    print(_c("Minimum scene hold = how long scenes stay before normal changes.", _GRAY))
    print(_c("Buildup lookahead = beats before a Smart Drop buildup is allowed.", _GRAY))
    phrase = _input(
        f"Groove phrase length ({pdata.get('phrase_interval_beats', 32)}): "
    )
    hold = _input(
        f"Minimum scene hold ({pdata.get('minimum_scene_hold_beats', 8)}): "
    )
    lookahead = _input(
        f"Buildup lookahead ({pdata.get('buildup_lookahead_beats', 32)}): "
    )
    if phrase:
        pdata["phrase_interval_beats"] = max(1, int(phrase))
    if hold:
        pdata["minimum_scene_hold_beats"] = max(0, int(hold))
    if lookahead:
        pdata["buildup_lookahead_beats"] = max(1, int(lookahead))


def _set_port(config: dict[str, Any]) -> None:
    port = _input(f"MIDI output port [{config.get('midi_output_port', _DEFAULT_PORT)}]: ")
    if port:
        config["midi_output_port"] = port
        print(_c("MIDI output port updated.", _GREEN))


def _toggle_dry_run(config: dict[str, Any]) -> None:
    config["dry_run"] = not bool(config.get("dry_run", True))
    status = "true" if config["dry_run"] else "false"
    print(_c(f"dry_run={status}", _YELLOW))


def _test_note(config: dict[str, Any]) -> None:
    print(_c("\nTEST NOTE (manual only)", _YELLOW))
    if _input("Send a test note now? y/N: ").lower() != "y":
        return
    note = _pick_note()
    channel = _parse_channel(_input("Channel [1]: ") or "1")
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
    scenes = config.get("scenes", {})
    pdata = config.get("personalities", {}).get(personality, {})
    title = f"{personality} (default)" if personality == _DEFAULT_PERSONALITY else personality
    print(_c(f"\n{title}", _MAGENTA))
    for role in _ROLE_CHOICES:
        scene_field, _ = _ROLE_FIELD_MAP[role]
        scene_name = pdata.get(scene_field, "")
        scene = scenes.get(scene_name, {})
        midi = scene.get("midi", {})
        note = midi.get("note", "?")
        safety = _SAFETY_KEY_TO_LABEL.get(scene.get("safety_class", "safe"), scene.get("safety_class", "safe"))
        cooldown = scene.get("cooldown_beats", 0)
        print(f"  {role:10s} note {note:<4} {safety:18s} cooldown {cooldown}")
    print(_c("\nTiming:", _CYAN))
    print(f"  groove phrase length: {pdata.get('phrase_interval_beats', 32)} beats")
    print(f"  minimum scene hold: {pdata.get('minimum_scene_hold_beats', 8)} beats")
    print(f"  buildup lookahead: {pdata.get('buildup_lookahead_beats', 32)} beats")


def _save_and_exit(config: dict[str, Any], path: Path) -> bool:
    _final_preview(config, _DEFAULT_PERSONALITY)
    if _input("Save changes? y/N: ").lower() != "y":
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


def run_wizard(config_path: Path = _DEFAULT_CONFIG_PATH) -> int:
    try:
        config = load_or_create_config(config_path)
    except json.JSONDecodeError as exc:
        print(_c(f"Config JSON parse error: {exc}", _RED))
        return 2

    _print_header()
    while True:
        print(_c("\nMain Menu", _CYAN))
        print("  1. Show current mappings")
        print("  2. Add or update mapping")
        print("  3. Add mapping to bank")
        print("  4. Validate mappings")
        print("  5. Test a MIDI note")
        print("  6. Set MIDI output port")
        print("  7. Toggle dry_run")
        print("  8. Advanced Timing / Cooldowns")
        print("  9. Save and exit")
        print("  0. Exit without saving")
        choice = _input("> ")
        if choice == "1":
            _show_mappings(config)
            continue
        if choice in {"2", "3"}:
            personality = _pick_personality(config)
            role = _pick_role()
            note = _pick_note()
            _ensure_personality_exists(config, personality)
            scene_type = _ROLE_DEFAULTS[role]["scene_type"]
            behavior, hold_ms, hold_beats = _pick_behavior(role, scene_type)
            if not _warn_duplicate(config, note, (personality, role)):
                continue
            scene_name = apply_mapping(
                config,
                personality=personality,
                role=role,
                note=note,
                add_to_bank=(choice == "3"),
                behavior=behavior,
                hold_ms=hold_ms or None,
                hold_beats=hold_beats or None,
            )
            print(_c(f"Updated {personality}:{role} -> {scene_name} (note {note})", _GREEN))
            continue
        if choice == "4":
            errors, warnings = validate_config_data(config)
            if not errors and not warnings:
                print(_c("Validation passed.", _GREEN))
                continue
            for warning in warnings:
                print(_c(f"Warning: {warning}", _YELLOW))
            for err in errors:
                print(_c(f"Error: {err}", _RED))
            continue
        if choice == "5":
            _test_note(config)
            continue
        if choice == "6":
            _set_port(config)
            continue
        if choice == "7":
            _toggle_dry_run(config)
            continue
        if choice == "8":
            _edit_timing(config, _DEFAULT_PERSONALITY)
            continue
        if choice == "9":
            _save_and_exit(config, config_path)
            return 0
        if choice == "0":
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
