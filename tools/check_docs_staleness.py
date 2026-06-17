#!/usr/bin/env python3
"""Doc staleness checker (zero third-party deps; uses git via stdlib subprocess).

Drift the other checkers can't see: docs that were correct when written but whose
*implementation* has since changed. For each contract in change_contracts.yml it
asks git whether any implementation file in `code_globs` has commits after the
recorded `last_verified_commit`. If so, the docs that contract governs
(`docs_update`) should be re-verified against code.

Advisory by default (prints, exit 0) so it never blocks routine commits. Use
--strict to make staleness a hard failure (e.g. a release gate). --report always
prints the full per-contract table. --base COMMIT overrides the baseline.

Implementation files = bridge *.py (excluding tools/), config/*.json, and
docs/data/*.yaml. Doc/.github/tooling paths are ignored: a doc changing does not
make itself stale.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
YML = ROOT / "docs/agents/change_contracts.yml"


def git(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, check=False,
        )
    except (OSError, FileNotFoundError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def parse_contracts(text: str) -> dict[str, dict[str, list[str]]]:
    contracts: dict[str, dict[str, list[str]]] = {}
    cur_c: str | None = None
    cur_f: str | None = None
    in_contracts = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            in_contracts = line == "contracts:"
            cur_c = cur_f = None
            continue
        if not in_contracts:
            continue
        if indent == 2 and line.endswith(":"):
            cur_c, cur_f = line[:-1], None
            contracts[cur_c] = {}
        elif indent == 4 and line.endswith(":") and cur_c:
            cur_f = line[:-1]
            contracts[cur_c][cur_f] = []
        elif indent >= 6 and line.startswith("- ") and cur_c and cur_f:
            contracts[cur_c][cur_f].append(line[2:].strip())
    return contracts


def is_impl(path: str) -> bool:
    if path.startswith("tools/"):
        return False
    if path.endswith(".py"):
        return True
    if path.startswith("config/") and path.endswith(".json"):
        return True
    if path.startswith("docs/data/") and path.endswith((".yaml", ".yml")):
        return True
    return False


def resolve(item: str) -> list[str]:
    if item.endswith("/**") or item.endswith("/"):
        return []
    if "*" in item:
        return [p.relative_to(ROOT).as_posix() for p in ROOT.glob(item) if p.is_file()]
    return [item]


def impl_files(code_globs: list[str]) -> list[str]:
    out: list[str] = []
    for g in code_globs:
        for f in resolve(g):
            if is_impl(f) and (ROOT / f).exists():
                out.append(f)
    return sorted(set(out))


def changed_since(base: str, path: str) -> bool:
    code, out = git("log", "--format=%h", f"{base}..HEAD", "--", path)
    return code == 0 and bool(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether implementation changed since docs were verified.")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any contract is stale")
    ap.add_argument("--report", action="store_true", help="print the full per-contract table")
    ap.add_argument("--base", help="override baseline commit (default: change_contracts.yml last_verified_commit)")
    args = ap.parse_args()

    code, head = git("rev-parse", "--short", "HEAD")
    if code != 0 or not head:
        print("staleness: not a git checkout or git unavailable; skipping (advisory).")
        return 0

    if not YML.exists():
        print("staleness: docs/agents/change_contracts.yml missing; skipping.")
        return 0
    text = YML.read_text(encoding="utf-8")
    m = re.search(r"^last_verified_commit:\s*(\S+)", text, re.M)
    base = args.base or (m.group(1) if m else None)
    if not base:
        print("staleness: no last_verified_commit baseline found; skipping.")
        return 0

    rc, _ = git("rev-parse", "--verify", "--quiet", base)
    if rc != 0:
        print(f"staleness: baseline commit {base} not in history; skipping (advisory).")
        return 0

    contracts = parse_contracts(text)
    stale: list[tuple[str, list[str], list[str]]] = []
    rows: list[tuple[str, int, int]] = []
    for name, fields in contracts.items():
        impl = impl_files(fields.get("code_globs", []))
        changed = [f for f in impl if changed_since(base, f)]
        rows.append((name, len(impl), len(changed)))
        if changed:
            stale.append((name, changed, fields.get("docs_update", [])))

    if args.report:
        print(f"staleness report — baseline {base} → HEAD {head}")
        print(f"{'contract':22} {'impl files':>10} {'changed':>8}  status")
        for name, n_impl, n_changed in rows:
            status = "STALE" if n_changed else "fresh"
            print(f"{name:22} {n_impl:>10} {n_changed:>8}  {status}")
        print()

    if stale:
        print(f"staleness: {len(stale)} contract(s) may be stale (impl changed since {base}):")
        for name, changed, docs in stale:
            print(f"- {name}: changed {', '.join(changed)}")
            if docs:
                print(f"    re-verify: {', '.join(docs)}")
        print("Re-verify those docs against code, then bump last_verified_commit.")
        if args.strict:
            return 1
        return 0

    print(f"staleness: no contract is stale (impl unchanged since {base}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
