#!/usr/bin/env python3
"""Machine-local ADVISORY check: bridge LaunchAgents must declare ProcessType.

Root cause AWR-151 Phase B (2026-07-08, flip-proven 28.1 vs 60.0 fps): launchd
applies a documented CPU/IO throttle to any LaunchAgent whose plist omits
`ProcessType`, and the throttle is inherited by the agent's whole coalition —
the bridge tree, the frame-engine child, and both pads all ran throttled for
this reason. This script warns if any agent that runs this repo's code (active
or .disabled) is missing `ProcessType=Interactive`, so a future plist edit or
re-enable cannot silently regress the fix.

Advisory only: reads ~/Library/LaunchAgents on THIS machine — deliberately NOT
a CI hard check (CI has no such directory). Run it manually or from a local
hook. Exit 1 on findings, 0 when clean or when the directory is absent.

Also warns when an agent pins an interpreter below the repo floor (Python
3.10+ syntax is in the import chains; the pads' old /usr/bin/python3 = 3.9
crashed on dataclass(slots=True) at the first restart after 2026-07-03).
"""
from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path

REPO_MARKER = "rb_ss_bridge_v2"
FLOOR = (3, 10)


def _interpreter_version(path: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run(
            [path, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=10,
        )
        major, minor = out.stdout.split()
        return int(major), int(minor)
    except Exception:
        return None


def check(agents_dir: Path) -> list[str]:
    findings: list[str] = []
    if not agents_dir.is_dir():
        return findings
    for plist_path in sorted(agents_dir.glob("*.plist*")):
        try:
            data = plistlib.loads(plist_path.read_bytes())
        except Exception:
            continue  # not a parseable plist — not ours to judge
        args = [str(a) for a in data.get("ProgramArguments", [])]
        if not any(REPO_MARKER in a for a in args):
            continue
        if data.get("ProcessType") != "Interactive":
            findings.append(
                f"{plist_path.name}: ProcessType is "
                f"{data.get('ProcessType')!r} — must be 'Interactive' "
                f"(launchd throttles the whole tree otherwise; AWR-151)"
            )
        if args:
            ver = _interpreter_version(args[0])
            if ver is not None and ver < FLOOR:
                findings.append(
                    f"{plist_path.name}: interpreter {args[0]} is Python "
                    f"{ver[0]}.{ver[1]} — below the repo floor "
                    f"{FLOOR[0]}.{FLOOR[1]} (import chain uses 3.10+ syntax)"
                )
    return findings


def main() -> int:
    agents_dir = Path(
        sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Library/LaunchAgents"
    )
    findings = check(agents_dir)
    if findings:
        print("launch-agent check found problems:")
        for f in findings:
            print(f"- {f}")
        return 1
    print("launch-agent check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
