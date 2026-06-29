#!/usr/bin/env python3
"""Agent navigation + change-contract checker (zero-deps, no network, no hardware).

Checks that:
  - subsystem cards, task playbooks, and contract docs exist;
  - file paths referenced in those docs actually exist;
  - every file in docs/plans/active and docs/prompts/active is classified in
    doc_index.md or active_work_registry.md;
  - AGENTS.md routes to the required playbooks/cards/contracts;
  - every contract in change_contracts.yml has the required fields;
  - every contract.key_symbol exists as a class/def/constant in the code;
  - every concrete file referenced by a contract (code_globs/inspect/docs_update)
    exists in the checkout.

It does not import the runtime package. The YAML is parsed with a tiny
indent-based reader so no third-party dependency is required.
"""
from __future__ import annotations

from pathlib import Path
import re
import fnmatch
import sys

ROOT = Path(__file__).resolve().parents[1]

SUBSYSTEM_CARDS = [
    "docs/subsystems/core_bridge.md",
    "docs/subsystems/rekordbox_readers.md",
    "docs/subsystems/soundswitch_output.md",
    "docs/subsystems/laser.md",
    "docs/subsystems/led_govee.md",
    "docs/subsystems/runtime_commands.md",
    "docs/subsystems/config.md",
    "docs/subsystems/tests.md",
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

CONTRACT_DOCS = [
    "docs/agents/change_contracts.md",
    "docs/agents/change_contracts.yml",
    "docs/agents/drift_detection.md",
]

REQUIRED_CONTRACTS = [
    "runtime_commands", "led_govee", "laser", "rekordbox_readers",
    "soundswitch_output", "config_schema", "tests", "docs",
]
REQUIRED_CONTRACT_FIELDS = ["code_globs", "inspect", "tests", "docs_update", "forbidden_assumptions"]

AGENTS_REQUIRED_ROUTES = [
    "docs/agents/change_contracts.yml",
    "docs/agents/change_contracts.md",
    "docs/agents/task_playbooks/change_runtime_command.md",
    "docs/subsystems/led_govee.md",
    "docs/subsystems/laser.md",
    "docs/subsystems/rekordbox_readers.md",
    "docs/subsystems/runtime_commands.md",
]

# Forward-coverage: every file in these dirs must be classified in one of the
# classifier docs below, or CI fails. This is the guardrail that catches a spec
# dropped into active/ without being registered (e.g. the AWR-111 orphan).
ACTIVE_DOC_GLOBS = ["docs/plans/active/*.md", "docs/prompts/active/*.md"]
CLASSIFIER_DOCS = [
    "docs/architecture/doc_index.md",
    "docs/status/active_work_registry.md",
]

# Reverse-coverage: a file in these dirs must NOT carry a retired status LABEL in its
# doc_index row (it should have moved to completed/ or been deleted). Catches an
# executed/superseded prompt left sitting in active/. Only the label cell is checked,
# so deliberate "COMPATIBILITY POINTER"-style stubs are not flagged.
ACTIVE_DOC_PREFIXES = ("docs/plans/active/", "docs/prompts/active/")
RETIRED_LABEL_RE = re.compile(r"COMPLETED|SUPERSEDED|ARCHIVE|HISTORICAL|DEPRECATED", re.I)

# Backtick tokens that are patterns/dirs, not concrete files to existence-check.
CODE_REF_RE = re.compile(r"`([^`]+)`")


def is_checkable_path(token: str) -> bool:
    if " " in token or "*" in token or token.endswith("/") or ".backup" in token:
        return False
    # Live/local config files (and the local backup) are gitignored by design and
    # absent from a clean checkout; only example configs are tracked and checkable.
    if token.startswith("config/"):
        return token.endswith(".example.json")
    return (
        token.startswith(("docs/", "tests/"))
        or token.endswith((".py", ".yml", ".yaml"))
        or token in {"README.md", "AGENTS.md", "pyproject.toml", "requirements-dev.txt", ".gitignore"}
    )


def referenced_paths(text: str) -> set[str]:
    return {t for t in CODE_REF_RE.findall(text) if is_checkable_path(t)}


def classifier_tokens(texts: list[str]) -> set[str]:
    """All backtick-quoted tokens from the classifier docs (incl. glob/path tokens)."""
    tokens: set[str] = set()
    for text in texts:
        tokens.update(CODE_REF_RE.findall(text))
    return tokens


def is_classified(relpath: str, tokens: set[str]) -> bool:
    """True if relpath is named (exact path or basename) or glob-matched by any token."""
    name = relpath.rsplit("/", 1)[-1]
    for tok in tokens:
        if tok == relpath or tok == name:
            return True
        if "*" in tok and (fnmatch.fnmatch(relpath, tok) or fnmatch.fnmatch(name, tok)):
            return True
    return False


def misfiled_active_rows(doc_index_text: str) -> list[str]:
    """Paths whose doc_index row sits in an active/ dir but carries a retired status label."""
    bad: list[str] = []
    for line in doc_index_text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        paths = CODE_REF_RE.findall(cells[0])
        if paths and paths[0].startswith(ACTIVE_DOC_PREFIXES) and RETIRED_LABEL_RE.search(cells[1]):
            bad.append(paths[0])
    return bad


def parse_contracts(text: str) -> dict[str, dict[str, list[str]]]:
    """Indent-based parser for the known change_contracts.yml shape."""
    contracts: dict[str, dict[str, list[str]]] = {}
    cur_contract: str | None = None
    cur_field: str | None = None
    in_contracts = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            in_contracts = line == "contracts:"
            cur_contract = cur_field = None
            continue
        if not in_contracts:
            continue
        if indent == 2 and line.endswith(":"):
            cur_contract = line[:-1]
            contracts[cur_contract] = {}
            cur_field = None
        elif indent == 4 and line.endswith(":") and cur_contract is not None:
            cur_field = line[:-1]
            contracts[cur_contract][cur_field] = []
        elif indent >= 6 and line.startswith("- ") and cur_contract and cur_field:
            contracts[cur_contract][cur_field].append(line[2:].strip())
    return contracts


def all_code_text() -> str:
    parts = []
    for path in sorted(ROOT.glob("*.py")):
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n".join(parts)


def symbol_defined(symbol: str, code: str) -> bool:
    # class/def definition, or module-level constant assignment.
    return bool(
        re.search(rf"^\s*(?:class|def)\s+{re.escape(symbol)}\b", code, re.M)
        or re.search(rf"^{re.escape(symbol)}\s*[:=]", code, re.M)
    )


def main() -> int:
    errors: list[str] = []

    for rel in SUBSYSTEM_CARDS + PLAYBOOKS + CONTRACT_DOCS:
        if not (ROOT / rel).exists():
            errors.append(f"missing agent routing doc: {rel}")

    for rel in SUBSYSTEM_CARDS + PLAYBOOKS + CONTRACT_DOCS + ["AGENTS.md"]:
        path = ROOT / rel
        if not path.exists():
            continue
        for ref in sorted(referenced_paths(path.read_text(encoding="utf-8"))):
            if not (ROOT / ref).exists():
                errors.append(f"{rel}: referenced path does not exist: {ref}")

    classifier_texts: list[str] = []
    for rel in CLASSIFIER_DOCS:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing classifier doc: {rel}")
            continue
        classifier_texts.append(path.read_text(encoding="utf-8"))
    tokens = classifier_tokens(classifier_texts)
    for glob in ACTIVE_DOC_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            rel = path.relative_to(ROOT).as_posix()
            if not is_classified(rel, tokens):
                errors.append(
                    f"unclassified active doc: {rel} — add it to "
                    "docs/architecture/doc_index.md or docs/status/active_work_registry.md"
                )

    doc_index_text = (
        (ROOT / "docs/architecture/doc_index.md").read_text(encoding="utf-8")
        if (ROOT / "docs/architecture/doc_index.md").exists() else ""
    )
    for path in misfiled_active_rows(doc_index_text):
        errors.append(
            f"stale-classified active doc: {path} is labeled retired (completed/"
            "superseded/archived) in doc_index but still in active/ — move it to "
            "completed/ or delete it (Git history preserves prompts)"
        )

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8") if (ROOT / "AGENTS.md").exists() else ""
    for route in AGENTS_REQUIRED_ROUTES:
        if route not in agents:
            errors.append(f"AGENTS.md missing required route: {route}")

    yml = ROOT / "docs/agents/change_contracts.yml"
    if not yml.exists():
        errors.append("missing change_contracts.yml")
    else:
        contracts = parse_contracts(yml.read_text(encoding="utf-8"))
        for name in REQUIRED_CONTRACTS:
            if name not in contracts:
                errors.append(f"change_contracts.yml missing required contract: {name}")
        code = all_code_text()
        for name, fields in contracts.items():
            for field in REQUIRED_CONTRACT_FIELDS:
                if field not in fields:
                    errors.append(f"contract {name}: missing field {field}")
            for symbol in fields.get("key_symbols", []):
                if not symbol_defined(symbol, code):
                    errors.append(f"contract {name}: key_symbol not found in code: {symbol}")
            for field in ("code_globs", "inspect", "docs_update"):
                for item in fields.get(field, []):
                    if is_checkable_path(item) and not (ROOT / item).exists():
                        errors.append(f"contract {name}.{field}: path does not exist: {item}")

    if errors:
        print("agent contract check failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("agent contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
