#!/usr/bin/env python3
"""Docs metadata checker (zero-deps, no network, no hardware).

Verifies the lean agent-documentation system: every required doc exists, the
status docs carry a YAML-style header with the required keys, and the public
entrypoints link the agent system together. It deliberately does not police
every historical markdown file; old-doc classification lives in
docs/architecture/doc_index.md, not in this checker.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

# Existing authoritative architecture docs predate the header system; we require
# they exist but do not force a YAML header on them.
EXISTING_AUTHORITATIVE = [
    "docs/architecture/current_architecture.md",
    "docs/architecture/runtime_invariants.md",
    "docs/architecture/bridge_design.md",
]

REQUIRED_DOCS = [
    "README.md",
    "AGENTS.md",
    "docs/architecture/doc_index.md",
    *EXISTING_AUTHORITATIVE,
    "docs/status/project_status.md",
    "docs/status/current_working_setup.md",
    "docs/status/feature_status_matrix.md",
    "docs/status/support_matrix.md",
    "docs/status/validation_matrix.md",
    "docs/status/known_limitations.md",
    "docs/status/active_work_registry.md",
    "docs/subsystems/core_bridge.md",
    "docs/subsystems/rekordbox_readers.md",
    "docs/subsystems/soundswitch_output.md",
    "docs/subsystems/laser.md",
    "docs/subsystems/led_govee.md",
    "docs/subsystems/runtime_commands.md",
    "docs/subsystems/config.md",
    "docs/subsystems/tests.md",
    "docs/setup/local_setup.md",
    "docs/setup/configuration.md",
    "docs/setup/runtime_commands.md",
    "docs/setup/troubleshooting.md",
    "docs/validation/validation_policy.md",
    "docs/validation/software_test_inventory.md",
    "docs/validation/hardware_validation_log.md",
    "docs/agents/change_contracts.md",
    "docs/agents/change_contracts.yml",
    "docs/agents/drift_detection.md",
    "docs/archive/README.md",
]

PLAYBOOKS = [
    "docs/agents/task_playbooks/change_runtime_command.md",
    "docs/agents/task_playbooks/change_led_govee_behavior.md",
    "docs/agents/task_playbooks/change_laser_behavior.md",
    "docs/agents/task_playbooks/change_rekordbox_reader.md",
    "docs/agents/task_playbooks/update_config_schema.md",
    "docs/agents/task_playbooks/add_tests.md",
    "docs/agents/task_playbooks/update_docs.md",
    "docs/agents/task_playbooks/review_agent_changes.md",
]

REQUIRED_HEADER_KEYS = [
    "doc_status:",
    "truth_level:",
    "last_verified_commit:",
    "last_verified_date:",
    "validation_scope:",
]

# Files exempt from the YAML header requirement: the two entrypoints, the YAML
# data file, and the pre-existing authoritative architecture docs.
HEADER_EXEMPT = {
    "README.md",
    "AGENTS.md",
    "docs/agents/change_contracts.yml",
    *EXISTING_AUTHORITATIVE,
}

STRICT_HEADER_DOCS = [p for p in REQUIRED_DOCS + PLAYBOOKS if p not in HEADER_EXEMPT]

# AGENTS.md must route to these (the lean entrypoint folds the rest inline).
AGENTS_REQUIRED_LINKS = [
    "docs/agents/change_contracts.md",
    "docs/agents/change_contracts.yml",
    "docs/agents/task_playbooks/",
    "docs/subsystems/",
    "docs/architecture/doc_index.md",
]


def check_header(rel: str) -> list[str]:
    path = ROOT / rel
    if not path.exists():
        return [f"missing required doc: {rel}"]
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return [f"{rel}: missing YAML-style status header"]
    try:
        header = text.split("---", 2)[1]
    except IndexError:
        return [f"{rel}: malformed YAML-style status header"]
    return [f"{rel}: missing header key {key}" for key in REQUIRED_HEADER_KEYS if key not in header]


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED_DOCS + PLAYBOOKS:
        if not (ROOT / rel).exists():
            errors.append(f"missing required file: {rel}")

    for rel in STRICT_HEADER_DOCS:
        errors.extend(check_header(rel))

    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8") if (ROOT / "AGENTS.md").exists() else ""

    if "AGENTS.md" not in readme:
        errors.append("README.md must link to AGENTS.md")
    for link in AGENTS_REQUIRED_LINKS:
        if link not in agents:
            errors.append(f"AGENTS.md must reference {link}")

    hw = ROOT / "docs/validation/hardware_validation_log.md"
    if hw.exists() and "hardware-unvalidated" not in hw.read_text(encoding="utf-8").lower():
        errors.append("hardware validation log must preserve hardware-unvalidated status until evidence exists")

    backup = ROOT / "config" / "led_look_director.json.backup_1781599611"
    if backup.exists():
        print(f"warning: local backup exists and must not be staged: {backup.relative_to(ROOT)}")

    if errors:
        print("docs metadata check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("docs metadata check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
