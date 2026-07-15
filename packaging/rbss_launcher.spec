# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the USB bridge launcher (Milestone 1).

Builds an onedir, windowed `.app` carrying its own Python + the full
rb_ss_bridge_v2 package, entry `usb_launcher.py`. Ad-hoc (or Apple Development)
signed and wrapped in a DMG downstream -- see docs/setup/usb_launcher_runbook.md.

PyInstaller specifics are [assumed] until the build proves them; verify against
the installed PyInstaller (6.21.0 on Python 3.14.6, Task 0). Only *.example.json
configs are bundled -- never the gitignored live configs or govee.env secrets.

Bundle version: make_stick.sh exports RBSS_GENERATION into this process so
CFBundleShortVersionString/CFBundleVersion match the build manifest generation
(e.g. 39a2ffa5c770-20260712T225252Z). Outside make_stick, fall back to 0.0.1.

AWR-237: ships Homebrew hidapi's libhidapi.dylib under _MEIPASS/lib/ so frozen
--run-streamdeck works on guest Macs with no Homebrew. Hash-locked via
packaging/libhidapi_arm64.lock (AWR-229 discipline); missing/mismatched dylib
fails the build closed here and in make_stick.
"""
import glob
import hashlib
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Prefer the make_stick generation; keep a sane fallback for ad-hoc PyInstaller.
_BUNDLE_VERSION = (
    os.environ.get("RBSS_GENERATION")
    or os.environ.get("RBSS_BUNDLE_VERSION")
    or "0.0.1"
).strip() or "0.0.1"

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
PARENT = os.path.abspath(os.path.join(REPO_ROOT, os.pardir))
# So `import rb_ss_bridge_v2` resolves during analysis -- the package IS the repo
# dir, imported from its parent (the same trick the watcher uses at runtime).
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

_HIDAPI_LOCK = os.path.join(REPO_ROOT, "packaging", "libhidapi_arm64.lock")
_HIDAPI_CANDIDATES = (
    os.environ.get("RBSS_HIDAPI_DYLIB") or "",
    "/opt/homebrew/opt/hidapi/lib/libhidapi.dylib",
    "/usr/local/opt/hidapi/lib/libhidapi.dylib",
)


def _read_hidapi_expected_sha256(lock_path: str) -> str:
    with open(lock_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            return line.split()[0]
    raise SystemExit(
        "rbss_launcher.spec: packaging/libhidapi_arm64.lock has no SHA-256 line"
    )


def _resolve_hidapi_dylib() -> str:
    """Real Mach-O path for the locked hidapi dylib; fail closed if absent."""
    expected = _read_hidapi_expected_sha256(_HIDAPI_LOCK)
    for candidate in _HIDAPI_CANDIDATES:
        if not candidate:
            continue
        if not os.path.isfile(candidate):
            continue
        path = os.path.realpath(candidate)
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise SystemExit(
                "rbss_launcher.spec: libhidapi SHA-256 mismatch at %s "
                "(got %s, want %s from packaging/libhidapi_arm64.lock). "
                "brew reinstall/pin hidapi 0.15.0 or refresh the lock after review."
                % (path, actual, expected)
            )
        return path
    raise SystemExit(
        "rbss_launcher.spec: libhidapi.dylib not found (brew install hidapi, or "
        "set RBSS_HIDAPI_DYLIB=/path/to/libhidapi.dylib). Refusing a Stream-Deck-"
        "dead guest bundle."
    )


# Place under _MEIPASS/lib/ so usb_launcher.prepare_frozen_hidapi can point
# StreamDeck's Darwin Homebrew search ($PREFIX/lib/libhidapi.dylib) at the bundle.
binaries = [(_resolve_hidapi_dylib(), "lib")]

hiddenimports = []
hiddenimports += collect_submodules("rb_ss_bridge_v2")
hiddenimports += collect_submodules("StreamDeck")   # HID transports load dynamically
hiddenimports += collect_submodules("zeroconf")     # zeroconf._utils.* dynamic imports
hiddenimports += collect_submodules("pyrekordbox")
hiddenimports += [
    "rtmidi",
    "mido.backends.rtmidi",     # mido picks its backend by name at runtime
    "serial",
    "serial.tools.list_ports",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
    "pythonosc",
    # filepath_resolver imports these inside try/except (SoundSwitch track id);
    # PyInstaller can miss function-local guarded imports, so pin them.
    "mutagen", "mutagen.id3",
]
# AWR-222 dormant AX measurement probe — narrow ApplicationServices collection only.
hiddenimports += collect_submodules("ApplicationServices")

# Bundle only example configs (live configs + govee.env are gitignored secrets).
datas = [
    (path, "rb_ss_bridge_v2/config")
    for path in glob.glob(os.path.join(REPO_ROOT, "config", "*.example.json"))
]
datas += collect_data_files("pyrekordbox")
# Menubar status icons — bridge_menubar resolves ICON_DIR under sys._MEIPASS at
# this exact rb_ss_bridge_v2/scripts/icons layout, so a guest Mac shows an icon
# (not the /Users/bbui path that only exists on the maintainer's machine).
datas += [
    (path, "rb_ss_bridge_v2/scripts/icons")
    for path in glob.glob(os.path.join(REPO_ROOT, "scripts", "icons", "*.png"))
]
# Pad web UIs — the --run-laser-pad/--run-led-pad servers resolve their asset dir
# via __file__, which PyInstaller maps under _MEIPASS at the mirrored path, so
# the frozen pads serve their HTML/JS instead of a blank page. (Dirs are flat.)
for _pad in ("laser_pad_assets", "led_pad_assets"):
    datas += [
        (path, "rb_ss_bridge_v2/tools/%s" % _pad)
        for path in glob.glob(os.path.join(REPO_ROOT, "tools", _pad, "*"))
        if os.path.isfile(path)
    ]

a = Analysis(
    [os.path.join(REPO_ROOT, "usb_launcher.py")],
    pathex=[PARENT, REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

# Binary name carries `rb_ss_bridge_v2` so the operator's process check and the
# watcher/menubar regexes recognize the frozen bridge (design 3.2 req 1).
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="rb_ss_bridge_v2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,   # windowed -- this is the menubar app
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="rb_ss_bridge_v2",
)
app = BUNDLE(
    coll,
    name="RBSS Bridge.app",
    icon=None,
    bundle_identifier="com.bbui.rb-ss-bridge-v2",
    info_plist={
        "LSUIElement": True,   # menubar app, no Dock icon
        "NSLocalNetworkUsageDescription":
            "RBSS Bridge finds SoundSwitch and Govee lights on your local network.",
        "NSAppleEventsUsageDescription":
            "RBSS Bridge opens Terminal to show its read-only live log.",
        "NSAppBundlesUsageDescription": (
            "RBSS Bridge needs permission to update Rekordbox's app bundle only when "
            "you choose Patch Rekordbox, so it can enable lighting reads."
        ),
        "CFBundleName": "RBSS Bridge",
        "CFBundleDisplayName": "RBSS Bridge",
        # The locked native dependency set floors at macOS 12.3; declare it so an
        # older-macOS guest gets Finder's clean "requires macOS 12.3 or later"
        # instead of a raw dyld crash. Real version (not 0.0.0) so upgrades compare.
        "LSMinimumSystemVersion": "12.3",
        "CFBundleShortVersionString": _BUNDLE_VERSION,
        "CFBundleVersion": _BUNDLE_VERSION,
    },
)
