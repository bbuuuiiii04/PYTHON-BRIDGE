#!/bin/bash
# RBSS Bridge — one-command stick builder (AWR-186 Task 1, operator side).
#
# Usage:  bash packaging/make_stick.sh /Volumes/<stick>
#
# One run, from the repo root, does all of:
#   1. PyInstaller build + sign + DMG (the M1 runbook's exact commands), with the
#      DMG built FROM a staging dir so it carries BOTH "RBSS Bridge.app" AND
#      RBSS_payload/ (pre-warmed spectral cache + the home-parity configs the
#      native in-app installer consumes).
#   2. Payload staging (never inside the repo tree — mktemp -d only):
#        App Support spectral_cache        -> RBSS_payload/spectral_cache
#        live configs + govee.env (below)  -> RBSS_payload/home/
#      Secrets-on-stick is operator-APPROVED (2026-07-09 ~22:40, AWR-186 row).
#      Each copy is gated on the file existing; an EXISTING-but-unreadable
#      source aborts the run (fail closed) so a half-payload never ships.
#   3. Ship: copy the DMG + packaging/stick/*.command to the stick mount ($1).
#      Refuses unless $1 is a mounted volume with PIONEER/ present (that is the
#      rekordbox-exported stick; anything else is the wrong target).
#
# Home-parity payload list (from the AWR-186 Task 0 inventory — the bridge's
# live-config read points; the frozen bundle itself carries examples only):
#   govee.env                      (App Support; Govee cloud key)
#   laser_director.json            (config/; RBSS_LASER_CONFIG seam)
#   led_look_director.json         (config/; RBSS_LED_CONFIG seam)
#   soundswitch_pack_player.json   (config/; RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG seam)
#   laser_color_map.json           (config/; tracked file the bundle omits;
#                                   RBSS_LASER_COLOR_MAP_CONFIG seam)
#
# Test seams (unit tests only — never set these on a real build):
#   RBSS_MAKE_STICK_APP=<path>        use this prebuilt .app, skip the PyInstaller
#                                     build + sign (layout tests; no PyInstaller)
#   RBSS_MAKE_STICK_STAGE_ONLY=<dir>  assemble the staging layout into <dir>,
#                                     then stop (no hdiutil, no stick, no $1)
#   RBSS_MAKE_STICK_CONFIG_DIR=<dir>  read configs from <dir> instead of config/
#   (App Support resolves via $HOME, so tests point HOME at a throwaway dir.)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
CONFIG_DIR="${RBSS_MAKE_STICK_CONFIG_DIR:-$REPO_ROOT/config}"
PREBUILT_APP="${RBSS_MAKE_STICK_APP:-}"
STAGE_ONLY="${RBSS_MAKE_STICK_STAGE_ONLY:-}"
VENV="$REPO_ROOT/.build-venv-314"

HOME_PARITY_FILES=(
    "$SUPPORT/govee.env"
    "$CONFIG_DIR/laser_director.json"
    "$CONFIG_DIR/led_look_director.json"
    "$CONFIG_DIR/soundswitch_pack_player.json"
    "$CONFIG_DIR/laser_color_map.json"
)

fail() { echo "make_stick: $1" >&2; exit 1; }

# ── target checks first: refuse before spending minutes on a build ──────────
STICK="${1:-}"
if [ -z "$STAGE_ONLY" ]; then
    [ -n "$STICK" ] || fail "usage: bash packaging/make_stick.sh /Volumes/<stick>"
    [ -d "$STICK" ] || fail "'$STICK' is not a mounted volume."
    [ -d "$STICK/PIONEER" ] || fail "'$STICK' has no PIONEER/ — not the rekordbox-exported stick. Refusing."
fi

# ── staging dir: mktemp -d ONLY, never the repo tree ─────────────────────────
if [ -n "$STAGE_ONLY" ]; then
    STAGING="$STAGE_ONLY"
    mkdir -p "$STAGING"
else
    STAGING="$(mktemp -d /tmp/rbss_stick_staging.XXXXXX)"
    trap 'rm -rf "$STAGING"' EXIT
fi

# ── 1. build + sign (M1 runbook commands, verbatim), unless a test app given ─
if [ -n "$PREBUILT_APP" ]; then
    [ -d "$PREBUILT_APP" ] || fail "RBSS_MAKE_STICK_APP='$PREBUILT_APP' is not an app bundle dir."
    APP="$PREBUILT_APP"
else
    cd "$REPO_ROOT"
    if [ ! -x "$VENV/bin/pyinstaller" ]; then
        echo "make_stick: build venv missing — creating it (runbook commands)…"
        python3 -m venv --system-site-packages "$VENV"
        "$VENV/bin/python" -m pip install pyinstaller
    fi
    "$VENV/bin/pyinstaller" packaging/rbss_launcher.spec \
        --noconfirm --distpath dist --workpath build
    rm -rf build                                   # delete the intermediate (disk)
    bash packaging/sign.sh "dist/RBSS Bridge.app"
    APP="$REPO_ROOT/dist/RBSS Bridge.app"
fi

# ── 2. assemble staging: app + payload ───────────────────────────────────────
echo "make_stick: staging in $STAGING"
cp -R "$APP" "$STAGING/RBSS Bridge.app" || fail "step 'app copy' failed (source: $APP)."

CACHE_SRC="$SUPPORT/spectral_cache"
if [ -d "$CACHE_SRC" ]; then
    mkdir -p "$STAGING/RBSS_payload"
    cp -R "$CACHE_SRC" "$STAGING/RBSS_payload/spectral_cache" \
        || fail "step 'spectral_cache copy' failed — cache exists but is unreadable."
else
    echo "make_stick: NOTE — no spectral_cache at '$CACHE_SRC'; payload ships without pre-warm."
fi

mkdir -p "$STAGING/RBSS_payload/home"
for src in "${HOME_PARITY_FILES[@]}"; do
    if [ -e "$src" ]; then
        cp "$src" "$STAGING/RBSS_payload/home/" \
            || fail "step 'home-parity copy' failed on '$src' — exists but unreadable."
    else
        echo "make_stick: NOTE — '$src' absent; skipped (that subsystem falls back to its example/defaults on the guest Mac)."
    fi
done

PAYLOAD_COUNT="$(find "$STAGING/RBSS_payload" -type f 2>/dev/null | wc -l | tr -d ' ')"

if [ -n "$STAGE_ONLY" ]; then
    echo "make_stick: stage-only done — $PAYLOAD_COUNT payload file(s) in $STAGING"
    exit 0
fi

# ── 3. DMG from the staging dir (runbook command, -srcfolder = staging) ──────
DMG="$REPO_ROOT/dist/RBSS Bridge.dmg"
hdiutil create -volname "RBSS Bridge" -srcfolder "$STAGING" \
    -ov -format UDZO "$DMG" || fail "step 'DMG create' failed."

# ── 4. ship to the stick — into the operator's folder layout (2026-07-09:
#      everything bridge lives in "RBSS BRIDGE USB/" at the stick root) ───────
DEST="$STICK/RBSS BRIDGE USB"
mkdir -p "$DEST" || fail "step 'create stick folder' failed."
cp "$DMG" "$DEST/" || fail "step 'DMG to stick' failed."
cp "$REPO_ROOT/packaging/stick/install.command" "$REPO_ROOT/packaging/stick/purge.command" "$DEST/" \
    || fail "step 'stick commands copy' failed."
# Keep the interim helpers' sibling payload fresh: install.command reads
# RBSS_payload NEXT TO ITSELF, while the native installer reads it inside the
# DMG — refresh the sibling so the two install paths never drift.
if [ -d "$STAGING/RBSS_payload" ]; then
    rm -rf "$DEST/RBSS_payload"
    cp -R "$STAGING/RBSS_payload" "$DEST/RBSS_payload" \
        || fail "step 'sibling payload refresh' failed."
fi

DMG_SIZE="$(du -h "$DMG" | cut -f1)"
FREE="$(df -h "$STICK" | awk 'NR==2 {print $4}')"
echo "make_stick: DONE."
echo "  DMG:            $DMG_SIZE  ($DMG)"
echo "  payload files:  $PAYLOAD_COUNT (inside the DMG, RBSS_payload/)"
echo "  stick free:     $FREE  ($STICK)"
