#!/bin/bash
# RBSS Bridge — one-double-click installer (AWR-122 Saturday interim; the native
# in-app installer is M2 scope and replaces this).
#
# Sits on the stick next to "RBSS Bridge.dmg" and (optionally) RBSS_payload/.
# Installs EXACTLY two things and records every path it creates in a manifest:
#   1. RBSS Bridge.app            -> ~/Applications/
#   2. RBSS_payload/spectral_cache -> ~/Library/Application Support/RBSS Bridge/spectral_cache
# purge.command removes exactly the manifest paths — nothing else, ever.
#
# First run on a fresh Mac: right-click -> Open if double-click is blocked.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DMG="$HERE/RBSS Bridge.dmg"
PAYLOAD="$HERE/RBSS_payload/spectral_cache"
APP_DEST="$HOME/Applications/RBSS Bridge.app"
SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
CACHE_DEST="$SUPPORT/spectral_cache"
MANIFEST="$SUPPORT/install_manifest.txt"

if [ ! -f "$DMG" ]; then
    echo "install: no 'RBSS Bridge.dmg' next to this script — copy the DMG onto the stick first."
    exit 1
fi

echo "Installing RBSS Bridge (app + pre-warmed analysis if present)…"
MOUNT="$(hdiutil attach -nobrowse -readonly "$DMG" | awk -F$'\t' '/\/Volumes\//{print $NF; exit}')"
if [ -z "$MOUNT" ] || [ ! -d "$MOUNT/RBSS Bridge.app" ]; then
    echo "install: could not mount the DMG or it carries no RBSS Bridge.app."
    exit 1
fi
trap 'hdiutil detach "$MOUNT" -quiet >/dev/null 2>&1 || true' EXIT

mkdir -p "$HOME/Applications" "$SUPPORT"
rm -rf "$APP_DEST"
cp -R "$MOUNT/RBSS Bridge.app" "$APP_DEST"
printf '%s\n' "$APP_DEST" > "$MANIFEST"

if [ -d "$PAYLOAD" ]; then
    # File-level manifest: purge may only remove what THIS install created.
    copied=0
    (cd "$PAYLOAD" && find . -type f) | while IFS= read -r rel; do
        rel="${rel#./}"
        dest="$CACHE_DEST/$rel"
        mkdir -p "$(dirname "$dest")"
        cp "$PAYLOAD/$rel" "$dest"
        printf '%s\n' "$dest" >> "$MANIFEST"
    done
    copied="$( (cd "$PAYLOAD" && find . -type f) | wc -l | tr -d ' ')"
    echo "pre-warmed analysis installed: $copied entries (tracks are full-strength from first beat)."
else
    echo "NOTE: no RBSS_payload/spectral_cache on the stick — app installed without pre-warm"
    echo "      (each track analyzes ~15s on its first-ever play; lights stay beat-synced meanwhile)."
fi

echo "Done. The app is in ~/Applications — right-click 'RBSS Bridge' -> Open the first time."
open -R "$APP_DEST" || true
