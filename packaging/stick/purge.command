#!/bin/bash
# RBSS Bridge — confirmed uninstall (the shell fallback for when the app won't
# launch; the native menubar PURGE is the primary path). Kept at PARITY with
# install_controller.perform_purge: remove the manifest paths (the app under
# ~/Applications, allowlist-checked, no ".."), then clear the WHOLE App Support
# dir (runtime state + configs + Govee key + cache) and the logs — so no residue
# survives, whichever installer created it. Requires typing PURGE at the prompt.
set -euo pipefail

SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
MANIFEST="$SUPPORT/install_manifest.txt"
APPS_ROOT="$HOME/Applications"
LOGS="$HOME/Library/Logs/rb_ss_bridge"

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

# Full parity with perform_purge: after the manifest paths (the app), clear the
# ENTIRE App Support dir (runtime state/, configs, Govee key, cache, the manifest
# itself) and the logs — catching residue no manifest lists. Both are hardcoded,
# bounded constants under $HOME, so this rm -rf is as safe as perform_purge's.
rm -rf "$SUPPORT"
rm -rf "$LOGS"

echo "purge: removed $removed manifest item(s), then cleared App Support + logs."
echo "Remaining: permission entries in System Settings (macOS keeps those; inert)."
