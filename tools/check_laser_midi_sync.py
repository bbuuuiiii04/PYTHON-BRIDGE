#!/usr/bin/env python3
"""Laser drop/post_drop bank ↔ scene MIDI sync checker (transitional).

Pure read-only reconciliation: loads the laser config, checks that every scene
referenced by drop_bank/post_drop_bank exists in `scenes` with a MIDI note, and
reports (channel, note) collisions across those banks. Non-cyclable entries
(scene_type != "autoloop") are reported as info, not errors.

Exit 0 on clean or info-only; exit 1 on genuine breaks (missing scene, note
collision). This is NOT a CI hard gate — SoundSwitch is being retired.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "laser_director.json"


def reconcile(config_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of issue dicts: {level, message, personality, bank, scene}."""
    issues: list[dict[str, Any]] = []
    scenes = config_dict.get("scenes", {})
    personalities = config_dict.get("personalities", {})

    for p_name, p_data in personalities.items():
        if not isinstance(p_data, dict):
            continue
        note_owners: dict[tuple[int, int], tuple[str, str]] = {}

        for bank_field in ("drop_bank", "post_drop_bank"):
            bank = p_data.get(bank_field, [])
            if not isinstance(bank, list):
                continue
            for scene_name in bank:
                if not isinstance(scene_name, str):
                    continue
                sd = scenes.get(scene_name)
                if sd is None or not isinstance(sd, dict):
                    issues.append({
                        "level": "error",
                        "message": f"bank entry references unknown scene",
                        "personality": p_name,
                        "bank": bank_field,
                        "scene": scene_name,
                    })
                    continue

                scene_type = sd.get("scene_type", "static")
                midi = sd.get("midi", {})
                note = (int(midi.get("channel", 1)), int(midi.get("note", 0)))

                if scene_type != "autoloop":
                    issues.append({
                        "level": "info",
                        "message": f"non-cyclable entry (scene_type={scene_type!r})",
                        "personality": p_name,
                        "bank": bank_field,
                        "scene": scene_name,
                    })

                prev = note_owners.get(note)
                if prev is not None:
                    prev_bank, prev_scene = prev
                    if prev_scene != scene_name:
                        issues.append({
                            "level": "error",
                            "message": (
                                f"(channel={note[0]}, note={note[1]}) collision: "
                                f"{prev_bank}/{prev_scene} vs {bank_field}/{scene_name}"
                            ),
                            "personality": p_name,
                            "bank": bank_field,
                            "scene": scene_name,
                        })
                else:
                    note_owners[note] = (bank_field, scene_name)

    return issues


def main() -> int:
    config_path = DEFAULT_CONFIG
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 1

    data = json.loads(config_path.read_text(encoding="utf-8"))
    issues = reconcile(data)

    errors = [i for i in issues if i["level"] == "error"]
    infos = [i for i in issues if i["level"] == "info"]

    for issue in issues:
        tag = "ERROR" if issue["level"] == "error" else "INFO"
        print(
            f"[{tag}] {issue['personality']}/{issue['bank']}/{issue['scene']}: "
            f"{issue['message']}"
        )

    if errors:
        print(f"\n{len(errors)} error(s), {len(infos)} info(s)", file=sys.stderr)
        return 1

    print(f"\nclean: 0 errors, {len(infos)} info(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
