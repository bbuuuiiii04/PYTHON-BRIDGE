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
#        soundswitch_pack (config pack_path; the exported show) -> RBSS_payload/soundswitch_pack
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
# Build venv from a python.org, LOW-deployment-target Python (NOT Homebrew, whose
# arm64 macOS-15 libpython hard-binds macOS-13 symbols like _mkfifoat and crashes
# on older Macs — DEFECT-1). python.org ships a universal2 interpreter, but the
# PRODUCED APP IS arm64 / Apple-Silicon-ONLY (pip pulls arm64 wheels on Apple
# Silicon; the spec sets no target_arch) — the only supported ship target. A
# post-build lipo assertion (below) fails closed if the built arch drifts from it.
VENV="$REPO_ROOT/.build-venv-u2"
# The oldest macOS the produced .app targets (11.0 is a safe floor clearing the
# reported macOS 12 crash); the interpreter's low target, not universal2, is the fix.
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"

HOME_PARITY_FILES=(
    "$SUPPORT/govee.env"
    "$CONFIG_DIR/laser_director.json"
    "$CONFIG_DIR/led_look_director.json"
    "$CONFIG_DIR/soundswitch_pack_player.json"
    "$CONFIG_DIR/laser_color_map.json"
)

fail() { echo "make_stick: $1" >&2; exit 1; }

# ── build interpreter: python.org, low deployment target ─────────────────────
# Homebrew's Python targets macOS 15, so a bundle built with it crashes on older
# macOS (Symbol not found: _mkfifoat). Require a python.org FRAMEWORK build with a
# low deployment target; python.org ships it universal2, which is a reliable marker
# for that build (the produced app is still arm64 — see the header). Override with
# RBSS_BUILD_PYTHON=/path/to/python3.
find_build_python() {
    local candidates=() py v archs
    [ -n "${RBSS_BUILD_PYTHON:-}" ] && candidates+=("$RBSS_BUILD_PYTHON")
    # Prefer a STABLE version — numba/llvmlite (librosa's deps, REQUIRED for
    # spectral analysis) ship wheels for stable Pythons; the very newest Python
    # often has none yet. Newest last so the build gets full spectral by default.
    for v in 3.13 3.12 3.11 3.14; do
        candidates+=("/Library/Frameworks/Python.framework/Versions/$v/bin/python3")
    done
    for py in "${candidates[@]}"; do
        [ -x "$py" ] || continue
        # deployment target must be < 13 (else macOS-13 symbols get hard-bound)…
        "$py" -c 'import sys,sysconfig; t=sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET") or "0"; sys.exit(0 if int(str(t).split(".")[0])<13 else 1)' 2>/dev/null || continue
        # …and it must be a universal2 framework build (both slices) — python.org's
        # reliable low-target marker; distinguishes it from Homebrew's arm64 build.
        archs="$(lipo -archs "$py" 2>/dev/null || true)"
        case "$archs" in
            *x86_64*arm64*|*arm64*x86_64*) echo "$py"; return 0 ;;
        esac
    done
    return 1
}

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
    # Reuse the venv ONLY if it has pyinstaller AND every runtime dep (--check-deps
    # imports the full required set). A narrow probe (pyinstaller + a few libs) would
    # let a STALE venv built before a dep was added (e.g. mutagen) pass, skip the pip
    # install, and ship a bundle missing that dep — the guest then silently degrades.
    if [ ! -x "$VENV/bin/pyinstaller" ] || \
       ! "$VENV/bin/python" "$REPO_ROOT/usb_launcher.py" --check-deps >/dev/null 2>&1; then
        BUILD_PY="$(find_build_python)" || fail "no python.org universal2 Python (target <13) found. Install the 'macOS 64-bit universal2 installer' for Python 3.12/3.13 from python.org, or set RBSS_BUILD_PYTHON=/path/to/python3. A Homebrew Python builds a bundle that crashes on macOS < 15 (DEFECT-1)."
        echo "make_stick: build interpreter → $BUILD_PY (universal2, target $MACOSX_DEPLOYMENT_TARGET)"
        # Rebuild from scratch: never carry a stale/partial venv (wrong interpreter,
        # or missing deps). No --system-site-packages (that pulled Homebrew's
        # arm64/target-15 packages back in). Spectral is REQUIRED — the full rig
        # installs on a stable python.org build; only the very newest Python may
        # lack a numba wheel. ANY step failing REMOVES the venv so the next run — or
        # an RBSS_BUILD_PYTHON=3.13 retry — starts clean instead of reusing it.
        rm -rf "$VENV"
        {
            "$BUILD_PY" -m venv "$VENV" &&
            "$VENV/bin/python" -m pip install --upgrade pip &&
            "$VENV/bin/python" -m pip install pyinstaller &&
            "$VENV/bin/python" -m pip install ".[bundle,analysis,spectral]"
        } || {
            rm -rf "$VENV"
            fail "build venv setup failed on $("$BUILD_PY" -V 2>&1). If it was the spectral deps, numba/llvmlite likely have no wheel for this Python yet — install a python.org 3.12 or 3.13 universal2 build (both have them), set RBSS_BUILD_PYTHON=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3, and rerun. Spectral is required; the bundle is NOT shipped without it."
        }
    fi
    "$VENV/bin/pyinstaller" packaging/rbss_launcher.spec \
        --noconfirm --distpath dist --workpath build
    rm -rf build                                   # delete the intermediate (disk)
    bash packaging/sign.sh "dist/RBSS Bridge.app"
    # Strip any quarantine so a foreign Mac's Gatekeeper doesn't second-guess the
    # ad-hoc signature (a plain USB/DMG copy adds none, but be explicit).
    xattr -cr "$REPO_ROOT/dist/RBSS Bridge.app" 2>/dev/null || true
    # Fail CLOSED if the built binary's arch drifts from the declared target
    # (arm64 / Apple Silicon). This ship is Apple-Silicon-only; a binary with no
    # arm64 slice would not run on the target and must never leave the build.
    APP_BIN="$REPO_ROOT/dist/RBSS Bridge.app/Contents/MacOS/rb_ss_bridge_v2"
    BUILT_ARCHS="$(lipo -archs "$APP_BIN" 2>/dev/null || echo "")"
    case " $BUILT_ARCHS " in
        *" arm64 "*) echo "make_stick: built arch = [$BUILT_ARCHS] — arm64 present, Apple-Silicon target OK." ;;
        *) fail "built binary arch '[$BUILT_ARCHS]' has no arm64 slice — this ship is Apple-Silicon-only; refusing to ship a bundle that won't run on the target." ;;
    esac
    # Fail CLOSED if the BUILT app is missing any required runtime dep — the reuse
    # guard above cannot catch every way a venv might drift, so verify the real
    # bundle can import the whole rig (mutagen etc.) exactly like the arch check.
    "$APP_BIN" --check-deps || fail "the built app is missing a required runtime dependency (see the MISSING line above). Delete .build-venv-u2 and rebuild, or check pyproject/spec. Refusing to ship a bundle that would degrade on the guest."
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

# The exported SoundSwitch pack itself (the show): read pack_path from the live
# config and copy the whole dir into the payload, so the guest Mac's native pack
# DMG renderer has something to load (its config pack_path is a build-machine
# absolute path). RBSS_SS_PACK_PATH on the guest points the renderer here.
PACK_CFG="$CONFIG_DIR/soundswitch_pack_player.json"
if [ -e "$PACK_CFG" ]; then
    # A config that EXISTS but can't be parsed/read is a hard error: never ship a
    # stick that silently carries no show. (The old `2>/dev/null || true` swallowed
    # a malformed config into an empty pack_path and then "succeeded" with no pack.)
    # Absent config or an empty pack_path stays backward-compatible no-pack.
    PACK_SRC="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pack_path","") or "")' "$PACK_CFG")" \
        || fail "step 'pack config read' failed — '$PACK_CFG' exists but is unreadable or not valid JSON."
    if [ -n "$PACK_SRC" ]; then
        # A declared non-empty pack_path MUST resolve to a readable directory — a
        # non-empty path pointing nowhere is a broken config, not "no pack".
        [ -d "$PACK_SRC" ] || fail "step 'pack copy' failed — pack_path '$PACK_SRC' is not a readable directory."
        cp -R "$PACK_SRC" "$STAGING/RBSS_payload/soundswitch_pack" \
            || fail "step 'pack copy' failed — pack dir unreadable ($PACK_SRC)."
    fi
fi

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
