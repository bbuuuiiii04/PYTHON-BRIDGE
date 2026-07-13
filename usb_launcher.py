#!/usr/bin/env python3
"""USB bridge launcher — the single frozen-bundle entrypoint (Milestone 1).

One PyInstaller binary plays every role by dispatching on its first flag, so the
bundle needs no host Python and no shell:

  (no args)            → the PyObjC menubar app
  --run-bridge         → the full bridge, in-process, with the shared launch profile
  --run-streamdeck     → the Stream Deck MIDI controller
  --run-laser-pad      → the Laser Pad web server (port 8765)
  --run-led-pad        → the LED Pad web server (port 8766)
  --run-log-viewer     → the bundled read-only live log viewer
  --check-deps         → import every required runtime dep; nonzero if any missing
                         (build-time fail-closed guard against a stale bundle)
  --probe-rekordbox-accessibility → dormant Rekordbox Accessibility MEASUREMENT
                         probe only (AWR-222); never starts the bridge; not a reader
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
    # numba (librosa's JIT, on the spectral path) needs a WRITABLE cache dir; the
    # frozen bundle is read-only/code-signed, so point it at App Support — else
    # numba re-JITs every start or tries to write into the signed .app. setdefault
    # honors an operator override.
    os.environ.setdefault("NUMBA_CACHE_DIR", str(support_dir / "numba_cache"))
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


def _pad_config_path(filename: str, env_key: str) -> str:
    """The config file a pad must edit: an explicit operator env override, else the
    installed App Support copy the bridge actually runs on, else the repo default.

    A frozen guest keeps its live config in App Support (the native installer
    lands it there), NOT in the bundle — which ships only
    *.example.json. Without this the pad would open a blank/default config AND a
    Save would write into sys._MEIPASS inside the code-signed .app, mutating the
    signed bundle (invalidating the signature and its TCC grants). We pass an
    explicit --config so the pad reads and writes the SAME file as the bridge."""
    override = os.environ.get(env_key)
    if override:
        return override
    installed = GOVEE_ENV_PATH.parent / filename
    # Frozen: _REPO_ROOT is sys._MEIPASS INSIDE the read-only, code-signed bundle,
    # which ships only *.example.json. NEVER return that path — the pad would seed a
    # default config and its Save would write into the signed .app (mutating the
    # signature; wiped on reinstall). Always use the WRITABLE App Support path the
    # bridge also resolves; load_or_create_config creates it there if absent, so pad
    # and bridge agree on one file.
    if getattr(sys, "frozen", False):
        return str(installed)
    if installed.exists():
        return str(installed)
    return str(_REPO_ROOT / "config" / filename)


def _run_laser_pad() -> int:
    """Run the Laser Pad web server (default port 8765), pointed at the same live
    config the bridge runs on (App Support on a guest), never the bundle default."""
    from rb_ss_bridge_v2.tools.laser_pad_web import main as laser_pad_main

    config = _pad_config_path("laser_director.json", "RBSS_LASER_CONFIG")
    return int(laser_pad_main(["--config", config]) or 0)


def _run_led_pad() -> int:
    """Run the LED Pad web server (default port 8766); see _run_laser_pad."""
    from rb_ss_bridge_v2.tools.led_pad_web import main as led_pad_main

    config = _pad_config_path("led_look_director.json", "RBSS_LED_CONFIG")
    return int(led_pad_main(["--config", config]) or 0)


def _run_log_viewer() -> int:
    """Run the bundled viewer; frozen guests never need a host Python."""
    from rb_ss_bridge_v2.bridge_view import main as viewer_main

    return int(viewer_main() or 0)


# Every runtime dependency the bundle MUST carry (import names). Kept as declared:
# base (mido/pyobjc/pyrekordbox/python-osc/zeroconf) + bundle
# (streamdeck/Pillow/python-rtmidi/pyserial/mutagen) + analysis (numpy/scipy) +
# spectral (librosa/soundfile). PyInstaller (a build tool) is NOT bundled, so it's
# excluded here.
_REQUIRED_BUNDLE_MODULES = (
    "mutagen", "rtmidi", "serial", "PIL", "mido", "objc",
    "ApplicationServices",
    "pyrekordbox", "pythonosc", "zeroconf", "StreamDeck",
    "numpy", "scipy", "librosa", "soundfile",
)


def _run_rekordbox_accessibility_probe(argv: list[str]) -> int:
    """Dormant AX measurement probe. Lazy import only; never starts the bridge."""
    from rb_ss_bridge_v2.usb_launcher_ax_probe import main as probe_main

    return int(probe_main(argv) or 0)


def _run_check_deps() -> int:
    """Import every required runtime dependency; exit nonzero naming the missing
    ones. Run post-build against the FROZEN app so a stale/incomplete build venv
    (e.g. missing mutagen, which only WARNs as a spec hiddenimport) FAILS THE BUILD
    CLOSED instead of silently shipping a bundle that degrades on the guest — the
    same fail-closed discipline as the lipo arch check. Imports third-party packages
    only (no bridge modules, no AppKit), so it stays headless + side-effect-free."""
    import importlib

    missing = []
    for mod in _REQUIRED_BUNDLE_MODULES:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # ImportError, or a submodule init failure
            missing.append(f"{mod} ({type(exc).__name__})")
    if missing:
        sys.stderr.write("usb_launcher: MISSING bundle deps: " + ", ".join(missing) + "\n")
        return 1
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
    if mode == "--probe-rekordbox-accessibility":
        return _run_rekordbox_accessibility_probe(args[1:])
    if mode == "--patch-rekordbox":
        return _run_patch_rekordbox()
    if mode == "--run-bridge":
        return _run_bridge()
    if mode == "--run-streamdeck":
        return _run_streamdeck()
    if mode == "--run-laser-pad":
        return _run_laser_pad()
    if mode == "--run-led-pad":
        return _run_led_pad()
    if mode == "--run-log-viewer":
        return _run_log_viewer()
    if mode == "--check-deps":
        return _run_check_deps()
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
