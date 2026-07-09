#!/usr/bin/env python3
"""USB bridge launcher — the single frozen-bundle entrypoint (Milestone 1).

One PyInstaller binary plays every role by dispatching on its first flag, so the
bundle needs no host Python and no shell:

  (no args)            → the PyObjC menubar app
  --run-bridge         → the full bridge, in-process, with the shared launch profile
  --run-streamdeck     → the Stream Deck MIDI controller
  --run-frame-engine --fd N → the headless Govee frame-engine child (the frozen
                              re-exec-self target; MUST stay clear of AppKit)

Run as a plain script (``python3 usb_launcher.py …``) it behaves like a thin CLI
over the same modules the dev watcher launches, so it is unit-testable and
dev-runnable without building a bundle.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the rb_ss_bridge_v2 package importable when run as a bare script (the
# watcher relies on the same parent-dir import). Frozen, PyInstaller already has
# the package on sys.path; this only matters for source runs and tests.
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT.parent))


def _run_frame_engine(argv: list[str]) -> int:
    """Headless Govee frame-engine child. Dispatched BEFORE any AppKit import."""
    from rb_ss_bridge_v2.govee_frame_engine import main as frame_main

    frame_main(argv)  # argv == ["--fd", "<n>"]
    return 0


def _run_bridge() -> int:
    """Run the full bridge in-process with the shared launch profile."""
    from rb_ss_bridge_v2 import launch_profile
    from rb_ss_bridge_v2.__main__ import main as bridge_main

    # Force the 19 launch flags (parity with the watcher, which hardcodes them),
    # honoring an operator RBSS_LASER_CONFIG override for the config path.
    laser_cfg = os.environ.get("RBSS_LASER_CONFIG") or str(
        _REPO_ROOT / "config" / "laser_director.json"
    )
    os.environ.update(launch_profile.bridge_env(laser_cfg))
    bridge_main()
    return 0


def _run_streamdeck() -> int:
    """Run the Stream Deck MIDI controller (its own singleton lock guards doubles)."""
    from rb_ss_bridge_v2.streamdeck.streamdeck_midi import main as streamdeck_main

    streamdeck_main()
    return 0


def _run_menubar() -> int:
    """Run the PyObjC menubar app (imported lazily so headless modes never load Cocoa)."""
    from rb_ss_bridge_v2.scripts.bridge_menubar import main as menubar_main

    menubar_main()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _run_menubar()

    mode = args[0]
    if mode == "--run-frame-engine":
        return _run_frame_engine(args[1:])
    if mode == "--run-bridge":
        return _run_bridge()
    if mode == "--run-streamdeck":
        return _run_streamdeck()

    # Fail closed and surface — never a silent success-shaped fallback.
    sys.stderr.write(f"usb_launcher: unknown mode {mode!r}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
