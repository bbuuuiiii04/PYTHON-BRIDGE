# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the USB bridge launcher (Milestone 1).

Builds an onedir, windowed `.app` carrying its own Python + the full
rb_ss_bridge_v2 package, entry `usb_launcher.py`. Ad-hoc (or Apple Development)
signed and wrapped in a DMG downstream -- see docs/setup/usb_launcher_runbook.md.

PyInstaller specifics are [assumed] until the build proves them; verify against
the installed PyInstaller (6.21.0 on Python 3.14.6, Task 0). Only *.example.json
configs are bundled -- never the gitignored live configs or govee.env secrets.
"""
import glob
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
PARENT = os.path.abspath(os.path.join(REPO_ROOT, os.pardir))
# So `import rb_ss_bridge_v2` resolves during analysis -- the package IS the repo
# dir, imported from its parent (the same trick the watcher uses at runtime).
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)

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
]

# Bundle only example configs (live configs + govee.env are gitignored secrets).
datas = [
    (path, "rb_ss_bridge_v2/config")
    for path in glob.glob(os.path.join(REPO_ROOT, "config", "*.example.json"))
]
datas += collect_data_files("pyrekordbox")

a = Analysis(
    [os.path.join(REPO_ROOT, "usb_launcher.py")],
    pathex=[PARENT, REPO_ROOT],
    binaries=[],
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
        "CFBundleName": "RBSS Bridge",
        "CFBundleDisplayName": "RBSS Bridge",
    },
)
