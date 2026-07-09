#!/bin/bash
# RBSS Bridge — confirmed uninstall (AWR-122 Saturday interim; the native menubar
# PURGE with confirmation is M2 scope and replaces this).
#
# Removes EXACTLY the paths install.command recorded in its manifest — never a
# blanket delete. Every manifest path must sit under ~/Applications or the
# RBSS Bridge Application Support folder, must not contain "..", or it is skipped.
# Requires typing PURGE at the prompt.
set -euo pipefail

SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
MANIFEST="$SUPPORT/install_manifest.txt"
APPS_ROOT="$HOME/Applications"

if [ ! -f "$MANIFEST" ]; then
    echo "purge: no install manifest at '$MANIFEST' — nothing install.command installed here. Refusing."
    exit 1
fi

echo "This removes the RBSS Bridge app and its installed analysis data from THIS Mac."
printf 'Type PURGE and press Return to confirm: '
read -r reply
if [ "$reply" != "PURGE" ]; then
    echo "purge: not confirmed — nothing removed."
    exit 1
fi

removed=0
while IFS= read -r path; do
    [ -n "$path" ] || continue
    case "$path" in
        *..*) echo "purge: skipping suspicious path: $path"; continue ;;
        "$APPS_ROOT"/*|"$SUPPORT"/*) ;;
        *) echo "purge: skipping path outside allowed roots: $path"; continue ;;
    esac
    rm -rf "$path"
    removed=$((removed + 1))
done < "$MANIFEST"

rm -f "$MANIFEST"
# Prune now-empty dirs the install created; rmdir refuses non-empty ones by design.
find "$SUPPORT/spectral_cache" -type d -empty -delete 2>/dev/null || true
rmdir "$SUPPORT" 2>/dev/null || true

echo "purge: removed $removed installed item(s)."
echo "Remaining (not created by the installer): permission entries in System Settings"
echo "(macOS keeps those) and any logs under ~/Library/Logs/rb_ss_bridge from runs."
