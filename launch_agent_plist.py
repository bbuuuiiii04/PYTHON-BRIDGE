"""Pure LaunchAgent plist generator for the USB bridge launcher.

Renders a plist the operator could install into ``~/Library/LaunchAgents`` for
permanent mode (M3). This module GENERATES only -- it never installs, loads, or
touches ``launchctl`` (M1 live-safety).

Every plist it emits sets ``ProcessType=Interactive`` (AWR-151, non-negotiable):
a ProcessType-less LaunchAgent gets macOS's background-QoS throttle -- the live
bridge ran at 28.1 fps until the flip to Interactive proved 60.0. Validate any
generated file with ``tools/check_launch_agents.py`` (``check(dir)``).
"""
from __future__ import annotations

import plistlib
from pathlib import Path

# Stable label -- keep constant so a reinstall replaces (not duplicates) the job.
DEFAULT_LABEL = "com.bbui.rb-ss-bridge-v2-launcher"


def render_launch_agent(
    program_arguments: list[str],
    *,
    label: str = DEFAULT_LABEL,
    run_at_load: bool = False,
) -> bytes:
    """Return the LaunchAgent plist XML bytes.

    ``program_arguments[0]`` must be the bundled binary whose name contains
    ``rb_ss_bridge_v2`` (so the operator's process check and
    ``tools/check_launch_agents.py`` both recognize it). ``ProcessType`` is
    always ``Interactive``.
    """
    if not program_arguments:
        raise ValueError("program_arguments must be non-empty")
    payload = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "ProcessType": "Interactive",
        "RunAtLoad": bool(run_at_load),
    }
    return plistlib.dumps(payload)


def write_launch_agent(
    path: str | Path,
    program_arguments: list[str],
    **kwargs,
) -> Path:
    """Write the generated plist to ``path`` and return it. Generation only."""
    out = Path(path)
    out.write_bytes(render_launch_agent(program_arguments, **kwargs))
    return out
