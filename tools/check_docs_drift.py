#!/usr/bin/env python3
"""Code/docs drift checker (zero-deps, no network, no hardware).

The high-value check: the accepted runtime command surface and runtime file
paths are parsed straight out of runtime_status.py and compared against the
command docs, so docs cannot silently drift from parse_command(). It also
guards the accepted repo-facing validation status string and the required
agent routes/contracts.
"""
from __future__ import annotations

from pathlib import Path
import ast
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

VALIDATION_STATUS = "SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED"


def read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_runtime_constants() -> tuple[str | None, str | None]:
    text = read("runtime_status.py")
    status = re.search(r'^STATUS_PATH\s*=\s*["\']([^"\']+)["\']', text, re.M)
    commands = re.search(r'^COMMANDS_PATH\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return (status.group(1) if status else None, commands.group(1) if commands else None)


def parse_allowed_commands() -> set[str]:
    text = read("runtime_status.py")
    if not text:
        return set()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allowed" and isinstance(node.value, ast.Set):
                    values = {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                    if values:
                        return values
    return set()


def commands_documented(text: str, commands: set[str]) -> list[str]:
    return [cmd for cmd in sorted(commands) if f"`{cmd}`" not in text and cmd not in text]


def main() -> int:
    errors: list[str] = []

    status_path, commands_path = parse_runtime_constants()
    allowed = parse_allowed_commands()

    if not allowed:
        errors.append("could not parse allowed runtime commands from runtime_status.py")
    for const, name in [(status_path, "STATUS_PATH"), (commands_path, "COMMANDS_PATH")]:
        if not const:
            errors.append(f"could not parse {name} from runtime_status.py")

    for rel in ["docs/setup/runtime_commands.md", "docs/subsystems/runtime_commands.md"]:
        text = read(rel)
        if not text:
            errors.append(f"missing runtime command doc: {rel}")
            continue
        for path in (status_path, commands_path):
            if path and path not in text:
                errors.append(f"{rel}: missing runtime path {path}")
        for cmd in commands_documented(text, allowed):
            errors.append(f"{rel}: missing accepted command {cmd}")

    for rel in ["README.md", "AGENTS.md", "docs/status/project_status.md", "docs/status/validation_matrix.md"]:
        text = read(rel)
        if not text:
            errors.append(f"missing status doc: {rel}")
        elif VALIDATION_STATUS not in text:
            errors.append(f"{rel}: missing accepted repo-facing validation status")

    hw = read("docs/validation/hardware_validation_log.md")
    if not hw:
        errors.append("missing status doc: docs/validation/hardware_validation_log.md")
    elif "HARDWARE-UNVALIDATED" not in hw:
        errors.append("docs/validation/hardware_validation_log.md: missing hardware-unvalidated status")

    agents = read("AGENTS.md")
    for route in ["docs/agents/change_contracts.md", "docs/agents/change_contracts.yml",
                  "docs/agents/task_playbooks/", "docs/subsystems/"]:
        if route not in agents:
            errors.append(f"AGENTS.md missing required agent route: {route}")

    contracts = read("docs/agents/change_contracts.yml")
    for key in ["runtime_commands", "led_govee", "laser", "rekordbox_readers",
                "soundswitch_output", "config_schema", "tests", "docs"]:
        if f"  {key}:" not in contracts:
            errors.append(f"change_contracts.yml missing contract: {key}")
    for field in ["code_globs:", "inspect:", "tests:", "docs_update:", "forbidden_assumptions:"]:
        if field not in contracts:
            errors.append(f"change_contracts.yml missing field type: {field}")

    if errors:
        print("docs drift check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("docs drift check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
