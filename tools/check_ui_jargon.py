#!/usr/bin/env python3
"""Standing gate (AWR-264 / N10): ban engineer jargon from LED UI copy.

Scans pad/lab/sim asset files and CONTROL_META labels. Exits nonzero on hits.
Musician terms (BPM, beat, bar, drop, groove, buildup, breakdown) are allowed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Exact / phrase bans in user-facing surfaces (case-sensitive where noted).
BANNED_PHRASES: tuple[tuple[str, str], ...] = (
    ("Strobe Hz", "use 'Flashes per second'"),
    ("Strobe Duty", "use 'Flash length (%)'"),
    ("Strobe Rate", "use 'Flashes per beat'"),
    ("Beat Division", "use 'Trigger every … beats'"),
    ("Dim Floor", "use 'Minimum brightness'"),
    ("Fade Decay", "use 'Fade-out'"),
    ("Follow Show Color", "use 'Match the track'"),
    ("Locked Palette", "use 'Use set colors'"),
    ("show-colored", "use 'Uses show colors'"),
    ("time driven", "use 'Runs on a clock'"),
    ("beat sync", "use 'Locks to the beat'"),
    ("Bridge owns LEDs", "use 'The show is running the lights'"),
    ("Pad owns LEDs", "use 'This pad is running the lights'"),
    ("UNMEASURED", "use 'Colors not calibrated yet'"),
    ("NEVER TOUCHES THE STRIP", "use softened preview-only copy"),
    ("Never touches the strip", "use softened preview-only copy"),
    ("Configured look (before live injection)", "use 'Saved look'"),
    ("Flip chain", "use 'Reverse direction'"),
    ("safety.allow_strobe", "use plain safety copy"),
    ("launchctl", "use a plain sentence + copy-command button"),
    ("Neighbor bleed", "use 'Color spill'"),
    ("(px)", "use '(LEDs)'"),
    ("Sparkle Life (s)", "use '(seconds)'"),
)

# Label-only bans inside CONTROL_META / visible HTML headings.
BANNED_LABEL_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r">\s*Renderer\s*<"), "heading 'Renderer' → 'Effect'"),
    (re.compile(r'panel-label">Renderer<'), "heading 'Renderer' → 'Effect'"),
    (re.compile(r"\bvertices\b", re.I), "user copy 'vertices' → 'corners'"),
    (re.compile(r"\bvertex\b", re.I), "user copy 'vertex' → 'corner'"),
)

# Sim source-picker must not put raw rt_* ids in Option display text.
RAW_RT_OPTION = re.compile(
    r"new\s+Option\(\s*(?:name|draft\.name|entry\.name)\s*,",
)


def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    roots = (
        ROOT / "tools" / "led_pad_assets",
        ROOT / "tools" / "led_sim_assets",
    )
    for folder in roots:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix in {".html", ".js", ".css"} and path.is_file():
                files.append(path)
    controls = ROOT / "led_pad_controls.py"
    if controls.exists():
        files.append(controls)
    return sorted({path.resolve() for path in files})


def _is_code_identifier_context(line: str) -> bool:
    """Skip JS variable/property names that are not UI copy."""
    stripped = line.strip()
    if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("#"):
        return True
    # Property / function names containing vertex are internal.
    if re.search(r"\b(hitTestVertex|dragVertex|selectedVertex|vertexHit|Vertex)\b", line):
        return True
    return False


def main() -> int:
    hits: list[str] = []
    for path in _iter_scan_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        for phrase, hint in BANNED_PHRASES:
            if phrase in text:
                # Allow historical comments that explicitly document the rename.
                for i, line in enumerate(text.splitlines(), start=1):
                    if phrase not in line:
                        continue
                    if "AWR-264" in line and ("→" in line or "->" in line or "was" in line.lower()):
                        continue
                    hits.append(f"{rel}:{i}: banned {phrase!r} ({hint})")
        for pattern, hint in BANNED_LABEL_RES:
            for i, line in enumerate(text.splitlines(), start=1):
                if not pattern.search(line):
                    continue
                if _is_code_identifier_context(line):
                    continue
                # Skip pure code identifiers in camelCase APIs.
                if "vertex" in line.lower() and ("function" in line or "const " in line or "let " in line):
                    if "textContent" not in line and "innerHTML" not in line and '"' not in line and "'" not in line:
                        continue
                hits.append(f"{rel}:{i}: banned pattern ({hint}): {line.strip()[:120]}")
        if rel.endswith("sim-app.js") and RAW_RT_OPTION.search(text):
            for i, line in enumerate(text.splitlines(), start=1):
                if RAW_RT_OPTION.search(line):
                    hits.append(
                        f"{rel}:{i}: raw rt_* / machine id used as Option label "
                        "(pass humanEffectName(...) as the display text)"
                    )

    if hits:
        print("UI jargon check FAILED:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print(f"{len(hits)} hit(s).", file=sys.stderr)
        return 1
    print(f"UI jargon check OK ({len(_iter_scan_files())} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
