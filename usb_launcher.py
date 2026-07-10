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

# Where the operator's Govee secret lives (same path the watcher sources).
GOVEE_ENV_PATH = Path.home() / "Library" / "Application Support" / "RBSS Bridge" / "govee.env"


def _parse_env_file(text: str) -> dict[str, str]:
    """Parse KEY=VAL lines from a dotenv-style file.

    Tolerates ``export `` prefixes, ``#`` comments, blank lines, and surrounding
    single/double quotes on the value. Pure -- the test seam.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip().strip('"').strip("'")
    return out


def _load_govee_env(env=None, path=GOVEE_ENV_PATH) -> None:
    """Source govee.env (GOVEE_API_KEY etc.) into ``env``, existing keys winning.

    The watcher sources this before launching; the bundle must too, or Govee
    cloud is dead during a bundled/Test-the-Lights run. Missing file is a no-op.
    """
    target = os.environ if env is None else env
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return
    for key, value in _parse_env_file(text).items():
        target.setdefault(key, value)


def _run_frame_engine(argv: list[str]) -> int:
    """Headless Govee frame-engine child. Dispatched BEFORE any AppKit import."""
    from rb_ss_bridge_v2.govee_frame_engine import main as frame_main

    frame_main(argv)  # argv == ["--fd", "<n>"]
    return 0


def _run_bridge() -> int:
    """Run the full bridge in-process with the shared launch profile."""
    from rb_ss_bridge_v2 import launch_profile
    from rb_ss_bridge_v2.__main__ import main as bridge_main

    # Source govee.env first (the watcher does too) so GOVEE_API_KEY is present
    # -- otherwise Govee cloud is dead in a bundled / Test-the-Lights run.
    _load_govee_env()
    # Home-parity config overrides (AWR-186 M2): configs the native installer
    # landed in App Support win over the bundle-internal examples. Precedence
    # per config: explicit operator env > installed App Support copy > default.
    support_dir = GOVEE_ENV_PATH.parent
    try:
        present = {p.name for p in support_dir.iterdir()}
    except OSError:
        present = set()
    overrides = {
        env: path
        for env, path in launch_profile.app_support_config_env(
            str(support_dir), present
        ).items()
        if not os.environ.get(env)
    }
    # Point the native pack DMX renderer at the installed pack dir so it works on
    # a guest Mac (the config's pack_path is a build-machine absolute path). The
    # operator env wins; only set it when the installed pack actually exists.
    pack_dir = support_dir / "soundswitch_pack"
    if pack_dir.is_dir() and not os.environ.get("RBSS_SS_PACK_PATH"):
        os.environ["RBSS_SS_PACK_PATH"] = str(pack_dir)
    # Force the 19 launch flags (parity with the watcher, which hardcodes them),
    # honoring an operator RBSS_LASER_CONFIG override for the config path.
    laser_cfg = (
        os.environ.get("RBSS_LASER_CONFIG")
        or overrides.pop(launch_profile.LASER_CONFIG_ENV, None)
        or str(_REPO_ROOT / "config" / "laser_director.json")
    )
    os.environ.update(launch_profile.bridge_env(laser_cfg, extra=overrides))
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


def _run_replay_session(path: str) -> int:
    """Test the Lights: run the bridge fed by a recorded session, not live decks.

    Fails closed on the live-safety guards (Rekordbox running / no session file)
    with a plain-language message before any bridge starts.
    """
    from rb_ss_bridge_v2 import replay_event_source

    problem = replay_event_source.replay_preflight(path)
    if problem is not None:
        sys.stderr.write(f"Test the Lights: {problem}\n")
        return 1
    os.environ["RBSS_REPLAY_SESSION"] = path
    return _run_bridge()


def _run_patch_rekordbox() -> int:
    """Consent-gated Rekordbox get-task-allow patch (menubar/frozen entry).

    All UI is macOS dialogs (no terminal); the admin password prompt + codesign
    happen inside run_interactive_gui, so the menubar just fires-and-forgets this.
    """
    from rb_ss_bridge_v2 import rekordbox_patch

    return rekordbox_patch.run_interactive_gui()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _run_menubar()

    mode = args[0]
    if mode == "--run-frame-engine":
        return _run_frame_engine(args[1:])
    if mode == "--patch-rekordbox":
        return _run_patch_rekordbox()
    if mode == "--run-bridge":
        return _run_bridge()
    if mode == "--run-streamdeck":
        return _run_streamdeck()
    if mode == "--replay-session":
        if len(args) < 2 or not args[1]:
            sys.stderr.write("usb_launcher: --replay-session needs a session file path\n")
            return 2
        return _run_replay_session(args[1])

    # Fail closed and surface — never a silent success-shaped fallback.
    sys.stderr.write(f"usb_launcher: unknown mode {mode!r}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
