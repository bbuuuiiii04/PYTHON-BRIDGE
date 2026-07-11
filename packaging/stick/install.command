#!/bin/bash
# RBSS Bridge — one-double-click installer (the shell fallback for when the app
# itself won't launch, e.g. an old-macOS crash; the native in-app installer is
# the primary path). Kept at FULL-PAYLOAD PARITY with install_controller.py.
#
# Sits on the stick next to "RBSS Bridge.dmg" and RBSS_payload/. Installs the app
# plus the whole payload, recording every path it creates in a manifest:
#   1. RBSS Bridge.app              -> ~/Applications/
#   2. RBSS_payload/spectral_cache  -> App Support/spectral_cache   (pre-warm)
#   3. RBSS_payload/home/*          -> App Support/*                (govee.env + configs)
#   4. RBSS_payload/soundswitch_pack -> App Support/soundswitch_pack (the show)
# purge.command clears the whole App Support dir (manifest + runtime residue).
#
# First run on a fresh Mac: right-click -> Open if double-click is blocked.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DMG="$HERE/RBSS Bridge.dmg"
PAYLOAD_ROOT="$HERE/RBSS_payload"
APP_DEST="$HOME/Applications/RBSS Bridge.app"
SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
MANIFEST="$SUPPORT/install_manifest.txt"

# Copy a payload subtree file-level into App Support, appending every dest to the
# manifest (so purge removes exactly what we created) — mirrors perform_install.
install_tree() {
    local src="$1" dest_root="$2" absent_note="$3" rel dest n=0
    if [ ! -d "$src" ]; then echo "$absent_note"; return 0; fi
    while IFS= read -r rel; do
        rel="${rel#./}"
        dest="$dest_root/$rel"
        mkdir -p "$(dirname "$dest")"
        cp "$src/$rel" "$dest"
        printf '%s\n' "$dest" >> "$MANIFEST"
        n=$((n + 1))
    done < <(cd "$src" && find . -type f)
    echo "installed $n file(s) -> $dest_root"
}

if [ ! -f "$DMG" ]; then
    echo "install: no 'RBSS Bridge.dmg' next to this script — copy the DMG onto the stick first."
    exit 1
fi

echo "Installing RBSS Bridge (app + pre-warmed analysis if present)…"
MOUNT="$(hdiutil attach -nobrowse -readonly "$DMG" | awk -F$'\t' '/\/Volumes\//{print $NF; exit}')"
# Arm the detach trap BEFORE the mount check, so a mounted-but-no-app early exit
# still detaches (an empty $MOUNT is harmless — hdiutil detach "" is swallowed).
trap 'hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true' EXIT
if [ -z "$MOUNT" ] || [ ! -d "$MOUNT/RBSS Bridge.app" ]; then
    echo "install: could not mount the DMG or it carries no RBSS Bridge.app."
    exit 1
fi

mkdir -p "$HOME/Applications" "$SUPPORT"
rm -rf "$APP_DEST"
cp -R "$MOUNT/RBSS Bridge.app" "$APP_DEST"
printf '%s\n' "$APP_DEST" > "$MANIFEST"

# Full payload parity with the native installer (install_controller.perform_install):
# analysis cache + home-parity configs/Govee key + the SoundSwitch pack.
install_tree "$PAYLOAD_ROOT/spectral_cache" "$SUPPORT/spectral_cache" \
    "NOTE: no pre-warmed analysis on the stick — each track analyzes ~15s on first play (lights stay beat-synced)."

if [ -d "$PAYLOAD_ROOT/home" ]; then
    homed=0
    for src in "$PAYLOAD_ROOT/home"/*; do
        [ -f "$src" ] || continue
        dest="$SUPPORT/$(basename "$src")"
        # Don't overwrite an operator's tuned config on reinstall (parity with
        # install_controller.perform_install).
        if [ -e "$dest" ]; then echo "kept existing $(basename "$dest")"; continue; fi
        cp "$src" "$dest"
        printf '%s\n' "$dest" >> "$MANIFEST"
        homed=$((homed + 1))
    done
    echo "installed $homed config/key file(s) (Govee cloud + live show configs)."
else
    echo "NOTE: no RBSS_payload/home on the stick — bridge runs on example configs, no Govee cloud."
fi

install_tree "$PAYLOAD_ROOT/soundswitch_pack" "$SUPPORT/soundswitch_pack" \
    "NOTE: no SoundSwitch pack on the stick — native pack output has nothing to load."

echo "Done. The app is in ~/Applications — right-click 'RBSS Bridge' -> Open the first time."
open -R "$APP_DEST" || true
