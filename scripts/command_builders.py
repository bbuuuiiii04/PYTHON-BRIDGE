from __future__ import annotations

import shlex
from pathlib import Path


def build_laser_wizard_command(script_path: Path) -> str:
    repo_dir = script_path.resolve().parents[1]
    repo_parent = repo_dir.parent
    return (
        f"cd {shlex.quote(str(repo_parent))} "
        "&& python3 -m rb_ss_bridge_v2.tools.laser_map_wizard "
        f"|| (cd {shlex.quote(str(repo_dir))} && python3 scripts/laser_map_wizard.py)"
    )


def build_laser_pad_command(script_path: Path) -> str:
    repo_dir = script_path.resolve().parents[1]
    repo_parent = repo_dir.parent
    return (
        f"cd {shlex.quote(str(repo_parent))} "
        "&& python3 -m rb_ss_bridge_v2.scripts.laser_pad --host 0.0.0.0 --port 8765 "
        f"|| (cd {shlex.quote(str(repo_dir))} && python3 scripts/laser_pad.py --host 0.0.0.0 --port 8765)"
    )
