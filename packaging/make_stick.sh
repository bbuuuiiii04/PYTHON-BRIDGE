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
#   3. Ship: copy the DMG and incrementally refresh lighting_sidecar/ on the
#      stick mount ($1). RBSS_payload stays inside the DMG only.
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
#   RBSS_MAKE_STICK_SOURCE_ONLY=1     load validation helpers, then stop
#   RBSS_MAKE_STICK_SIDECAR_EXPORTER=<path>  replace the exporter in tests
#   RBSS_MAKE_STICK_SIDECAR_PYTHON=<path>    replace its Python in tests
#   RBSS_MAKE_STICK_BINDINGS=<path>   replace the canonical MIDI bindings in tests
#   RBSS_MAKE_STICK_FAIL_BEFORE_SWAP=1  test rollback before the commit
#   RBSS_MAKE_STICK_FAIL_AFTER_HIDE=1   test rollback after hiding the old surface
#   (App Support resolves via $HOME, so tests point HOME at a throwaway dir.)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPPORT="$HOME/Library/Application Support/RBSS Bridge"
CONFIG_DIR="${RBSS_MAKE_STICK_CONFIG_DIR:-$REPO_ROOT/config}"
PREBUILT_APP="${RBSS_MAKE_STICK_APP:-}"
STAGE_ONLY="${RBSS_MAKE_STICK_STAGE_ONLY:-}"
SIDECAR_EXPORTER="${RBSS_MAKE_STICK_SIDECAR_EXPORTER:-$REPO_ROOT/tools/lighting_sidecar_export.py}"
BINDINGS_SRC="${RBSS_MAKE_STICK_BINDINGS:-$REPO_ROOT/local/soundswitch/.rbss_canonical_pack.midi_bindings.json}"
# Build venv from a python.org, LOW-deployment-target Python (NOT Homebrew, whose
# arm64 macOS-15 libpython hard-binds macOS-13 symbols like _mkfifoat and crashes
# on older Macs — DEFECT-1). python.org ships a universal2 interpreter, but the
# PRODUCED APP IS arm64 / Apple-Silicon-ONLY (pip pulls arm64 wheels on Apple
# Silicon; the spec sets no target_arch) — the only supported ship target. A
# post-build lipo assertion (below) fails closed if the built arch drifts from it.
VENV="$REPO_ROOT/.build-venv-u2"
WHEELHOUSE="$REPO_ROOT/.build-wheelhouse-macos12-arm64-cp313"
WHEEL_LOCK="$REPO_ROOT/packaging/macos12_arm64_cp313.lock"
SOURCE_LOCK="$REPO_ROOT/packaging/macos12_arm64_cp313_source.lock"
BUILD_PYTHON_VERSION="3.13.14"
SIDECAR_PYTHON="${RBSS_MAKE_STICK_SIDECAR_PYTHON:-$VENV/bin/python}"
# The honest foreign-Mac floor. Official CPython 3.13 SciPy wheels are tagged
# macOS 12.0 but their actual Mach-O slices require 12.3. The binary scan below
# enforces the real floor; macOS 12.0-12.2 are intentionally unsupported.
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.3}"

HOME_PARITY_FILES=(
    "$SUPPORT/govee.env"
    "$CONFIG_DIR/laser_director.json"
    "$CONFIG_DIR/led_look_director.json"
    "$CONFIG_DIR/soundswitch_pack_player.json"
    "$CONFIG_DIR/laser_color_map.json"
)

fail() { echo "make_stick: $1" >&2; exit 1; }

GIT_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null)" \
    || fail "cannot read the repository generation; refusing an unidentifiable build."
[[ "$GIT_HEAD" =~ ^[0-9a-f]{40}$ ]] \
    || fail "repository generation is malformed; refusing an unidentifiable build."
BUILD_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUILD_TIMESTAMP_COMPACT="$(date -u +%Y%m%dT%H%M%SZ)"
SOURCE_DIRTY=false
if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=no)" ]; then
    SOURCE_DIRTY=true
fi
GENERATION="${GIT_HEAD:0:12}-${BUILD_TIMESTAMP_COMPACT}"
[ "$SOURCE_DIRTY" = false ] || GENERATION="$GENERATION-dirty"

version_at_most() {
    awk -v have="$1" -v want="$2" '
        BEGIN {
            if (have !~ /^[0-9]+([.][0-9]+)*$/ || want !~ /^[0-9]+([.][0-9]+)*$/) exit 1
            hn = split(have, h, "."); wn = split(want, w, ".")
            for (i = 1; i <= hn || i <= wn; i++) {
                if ((h[i] + 0) < (w[i] + 0)) exit 0
                if ((h[i] + 0) > (w[i] + 0)) exit 1
            }
            exit 0
        }
    '
}

build_python_is_supported() {
    local py="$1" archs
    [ -x "$py" ] || return 1
    RBSS_LOCKED_PYTHON_VERSION="$BUILD_PYTHON_VERSION" "$py" -c 'import os, sys, sysconfig
def version(value): return tuple(int(part) for part in str(value).split("."))
target = sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET")
want = tuple(int(part) for part in os.environ["RBSS_LOCKED_PYTHON_VERSION"].split("."))
try: ok = sys.version_info[:3] == want and bool(target) and version(target) <= version(os.environ["MACOSX_DEPLOYMENT_TARGET"])
except (KeyError, TypeError, ValueError): ok = False
sys.exit(0 if ok else 1)' 2>/dev/null || return 1
    archs="$(lipo -archs "$py" 2>/dev/null || true)"
    case "$archs" in
        *x86_64*arm64*|*arm64*x86_64*) return 0 ;;
    esac
    return 1
}

inspect_native_tree_macos_target() {
    local root="$1" label="$2" require_macho="${3:-0}"
    local file minoses minos macho_count=0 bad_count=0
    while IFS= read -r -d '' file; do
        file -b "$file" 2>/dev/null | grep -q 'Mach-O' || continue
        macho_count=$((macho_count + 1))
        if ! minoses="$(vtool -show-build "$file" 2>/dev/null | awk '$1 == "minos" {print $2}')" || [ -z "$minoses" ]; then
            echo "make_stick: cannot read the minimum macOS version from '$label/${file#"$root"/}'." >&2
            return 1
        fi
        while IFS= read -r minos; do
            if ! version_at_most "$minos" "$MACOSX_DEPLOYMENT_TARGET"; then
                bad_count=$((bad_count + 1))
                if [ "$bad_count" -le 10 ]; then
                    echo "make_stick: incompatible native file: $label/${file#"$root"/} requires macOS $minos (max $MACOSX_DEPLOYMENT_TARGET)" >&2
                fi
            fi
        done <<< "$minoses"
    done < <(find "$root" -type f -print0)
    if [ "$require_macho" = "1" ] && [ "$macho_count" -eq 0 ]; then
        echo "make_stick: no Mach-O files found in '$label'." >&2
        return 1
    fi
    [ "$bad_count" -eq 0 ]
}

validate_app_macos_target() {
    local app="$1"
    [ -d "$app/Contents" ] || fail "cannot inspect macOS compatibility: '$app' is not an app bundle."
    inspect_native_tree_macos_target "$app/Contents" "${app##*/}/Contents" 1 \
        || fail "native bundle compatibility check failed; refusing to ship."
    echo "make_stick: all native app files target macOS $MACOSX_DEPLOYMENT_TARGET or older."
}

wheel_tag_is_supported() {
    local wheel="${1##*/}" stem platform tag major minor
    stem="${wheel%.whl}"
    platform="${stem##*-}"
    IFS='.' read -r -a tags <<< "$platform"
    for tag in "${tags[@]}"; do
        [ "$tag" = "any" ] && continue
        case "$tag" in
            macosx_*_arm64|macosx_*_universal2)
                major="${tag#macosx_}"; major="${major%%_*}"
                minor="${tag#macosx_${major}_}"; minor="${minor%%_*}"
                version_at_most "$major.$minor" "$MACOSX_DEPLOYMENT_TARGET" || return 1
                ;;
            *) return 1 ;;
        esac
    done
}

verify_locked_artifacts() {
    local lock="$1" directory="$2" line expected filename actual
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; esac
        expected="${line#*--hash=sha256:}"; expected="${expected%% *}"
        filename="${line##*# }"
        [ -f "$directory/$filename" ] || { echo "make_stick: locked artifact missing: $filename" >&2; return 1; }
        actual="$(shasum -a 256 "$directory/$filename" | awk '{print $1}')" || return 1
        [ "$actual" = "$expected" ] || { echo "make_stick: locked artifact hash mismatch: $filename" >&2; return 1; }
    done < "$lock"
}

download_locked_artifacts() {
    local py="$1" directory="$2" wheel_lock="$3" source_lock="$4"
    [ -f "$source_lock" ] || return 1
    "$py" -m pip download --dest "$directory" --require-hashes --no-deps \
        --only-binary=:all: --platform macosx_12_0_arm64 --python-version 3.13 \
        --implementation cp --abi cp313 --abi abi3 --abi none \
        --requirement "$wheel_lock" || return 1
    # pip prepares PEP 517 metadata even for an sdist download, which would
    # create an untracked build environment. Fetch the one hash-locked source
    # artifact directly; verify_locked_artifacts authenticates it immediately.
    curl -fsSL \
        https://files.pythonhosted.org/packages/source/p/python-rtmidi/python_rtmidi-1.5.8.tar.gz \
        -o "$directory/python_rtmidi-1.5.8.tar.gz"
}

validate_wheel_macos_target() {
    local wheel="$1" unpack
    wheel_tag_is_supported "$wheel" \
        || { echo "make_stick: incompatible wheel tag: ${wheel##*/}" >&2; return 1; }
    unpack="$(mktemp -d /tmp/rbss_wheel_check.XXXXXX)" || return 1
    if ! unzip -qq "$wheel" -d "$unpack"; then
        rm -rf "$unpack"
        echo "make_stick: cannot inspect wheel: ${wheel##*/}" >&2
        return 1
    fi
    if ! inspect_native_tree_macos_target "$unpack" "${wheel##*/}" 0; then
        rm -rf "$unpack"
        return 1
    fi
    rm -rf "$unpack"
}

validate_locked_wheelhouse() {
    local directory="$1" wheel
    local required=(
        numpy-2.4.6-cp313-cp313-macosx_11_0_arm64.whl
        scipy-1.18.0-cp313-cp313-macosx_12_0_arm64.whl
        numba-0.66.0-cp313-cp313-macosx_12_0_arm64.whl
        llvmlite-0.48.0-cp313-cp313-macosx_12_0_arm64.whl
        librosa-0.10.2.post1-py3-none-any.whl
        soundfile-0.14.0-py2.py3-none-macosx_11_0_arm64.whl
    )
    for wheel in "${required[@]}"; do
        [ -f "$directory/$wheel" ] || { echo "make_stick: required low-target wheel missing: $wheel" >&2; return 1; }
    done
    while IFS= read -r -d '' wheel; do
        validate_wheel_macos_target "$wheel" || return 1
    done < <(find "$directory" -maxdepth 1 -type f -name '*.whl' -print0)
}

build_lock_fingerprint() {
    local py="$1"
    { shasum -a 256 "$WHEEL_LOCK" "$SOURCE_LOCK"; "$py" -VV; } | shasum -a 256 | awk '{print $1}'
}

venv_is_locked() {
    local stamp="$VENV/.rbss-macos12-lock"
    build_python_is_supported "$VENV/bin/python" &&
        [ -x "$VENV/bin/pyinstaller" ] &&
        [ -f "$stamp" ] &&
        [ "$(cat "$stamp")" = "$(build_lock_fingerprint "$VENV/bin/python")" ] &&
        "$VENV/bin/python" -m pip check >/dev/null 2>&1 &&
        "$VENV/bin/python" "$REPO_ROOT/usb_launcher.py" --check-deps >/dev/null 2>&1
}

build_python_rtmidi_wheel() {
    local py="$1" directory="$2" wheel matches=()
    # --no-build-isolation makes meson-python shell out to the `meson` and `ninja`
    # console scripts, which pip installed in the venv's bin. Invoking python by
    # absolute path does NOT put that bin on PATH, so add it for this one build.
    PATH="$(dirname "$py"):$PATH" "$py" -m pip wheel --no-deps --no-build-isolation \
        --wheel-dir "$directory" "$directory/python_rtmidi-1.5.8.tar.gz" >&2 || return 1
    while IFS= read -r -d '' wheel; do matches+=("$wheel"); done \
        < <(find "$directory" -maxdepth 1 -type f -name 'python_rtmidi-1.5.8-cp313-cp313-macosx_*_arm64.whl' -print0)
    [ "${#matches[@]}" -eq 1 ] || { echo "make_stick: expected one CPython 3.13 ARM64 python-rtmidi wheel." >&2; return 1; }
    validate_wheel_macos_target "${matches[0]}" || return 1
    echo "${matches[0]}"
}

export_lighting_sidecar() {
    [ -x "$SIDECAR_PYTHON" ] \
        || fail "lighting sidecar Python is unavailable at '$SIDECAR_PYTHON'."
    "$SIDECAR_PYTHON" "$SIDECAR_EXPORTER" --dest "$1" \
        || fail "lighting sidecar export failed; stick update is incomplete."
}

validate_parity_data() {
    RBSS_HOME_DIR="$1" RBSS_PACK_DIR="$2" RBSS_SIDECAR_DIR="$3" \
    RBSS_BINDINGS="$4" RBSS_CACHE_DIR="$5" python3 - <<'PY'
import json
import os
from pathlib import Path

home = Path(os.environ["RBSS_HOME_DIR"])
pack = Path(os.environ["RBSS_PACK_DIR"])
sidecar = Path(os.environ["RBSS_SIDECAR_DIR"])
bindings = Path(os.environ["RBSS_BINDINGS"])
cache = Path(os.environ["RBSS_CACHE_DIR"])
required_home = {
    "govee.env",
    "laser_director.json",
    "led_look_director.json",
    "soundswitch_pack_player.json",
    "laser_color_map.json",
}
if not home.is_dir() or {p.name for p in home.iterdir() if p.is_file()} != required_home:
    raise SystemExit("managed home payload is incomplete")
for name in required_home - {"govee.env"}:
    value = json.loads((home / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"managed config is not a JSON object: {name}")
key_rows = [
    line.split("=", 1)[1].strip()
    for line in (home / "govee.env").read_text(encoding="utf-8").splitlines()
    if line.startswith("GOVEE_API_KEY=")
]
if len(key_rows) != 1 or not key_rows[0]:
    raise SystemExit("govee.env has no non-empty GOVEE_API_KEY")

if not pack.is_dir() or not (pack / "manifest.json").is_file():
    raise SystemExit("canonical SoundSwitch pack or manifest.json is missing")
pack_files = sorted(path for path in pack.rglob("*") if path.is_file())
if not pack_files:
    raise SystemExit("canonical SoundSwitch pack is empty")
for path in pack_files:
    if path.suffix == ".json":
        json.loads(path.read_text(encoding="utf-8"))

if not cache.is_dir() or not any(path.is_file() for path in cache.rglob("*")):
    raise SystemExit("analysis cache is missing or empty")

index = json.loads((sidecar / "index.json").read_text(encoding="utf-8"))
tracks = index.get("tracks") if isinstance(index, dict) else None
if (
    index.get("schema_version") != 1
    or not isinstance(tracks, list)
    or not tracks
    or index.get("track_count") != len(tracks)
):
    raise SystemExit("lighting sidecar index is empty or malformed")

rows = json.loads(bindings.read_text(encoding="utf-8"))
required_binding = {"channel", "interaction", "name", "note", "target_kind"}
if (
    not isinstance(rows, list)
    or not rows
    or any(not isinstance(row, dict) or set(row) != required_binding for row in rows)
):
    raise SystemExit("Stream Deck MIDI bindings are empty or malformed")
PY
}

write_build_manifest() {
    RBSS_MANIFEST_ROOT="$1" RBSS_MANIFEST_PATH="$2" \
    RBSS_GENERATION="$GENERATION" RBSS_BUILD_TIMESTAMP="$BUILD_TIMESTAMP" \
    RBSS_GIT_HEAD="$GIT_HEAD" RBSS_SOURCE_DIRTY="$SOURCE_DIRTY" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["RBSS_MANIFEST_ROOT"])
dest = Path(os.environ["RBSS_MANIFEST_PATH"])
files = []
for path in sorted(p for p in root.rglob("*") if p.is_file() and p != dest):
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    files.append({
        "path": str(path.relative_to(root)),
        "size": path.stat().st_size,
        "sha256": digest.hexdigest(),
    })
value = {
    "schema_version": 1,
    "generation": os.environ["RBSS_GENERATION"],
    "built_at": os.environ["RBSS_BUILD_TIMESTAMP"],
    "git_head": os.environ["RBSS_GIT_HEAD"],
    "source_dirty": os.environ["RBSS_SOURCE_DIRTY"] == "true",
    "files": files,
}
dest.parent.mkdir(parents=True, exist_ok=True)
tmp = dest.with_name(dest.name + ".tmp")
tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(tmp, dest)
PY
}

verify_build_manifest() {
    RBSS_MANIFEST_ROOT="$1" RBSS_MANIFEST_PATH="$2" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path, PurePath

root = Path(os.environ["RBSS_MANIFEST_ROOT"])
manifest_path = Path(os.environ["RBSS_MANIFEST_PATH"])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected = {}
for row in manifest.get("files", []):
    rel = row.get("path") if isinstance(row, dict) else None
    pure = PurePath(rel) if isinstance(rel, str) else PurePath("..")
    if (
        not isinstance(rel, str)
        or pure.is_absolute()
        or ".." in pure.parts
        or rel in expected
        or set(row) != {"path", "size", "sha256"}
    ):
        raise SystemExit("unsafe build manifest row")
    expected[rel] = (row["size"], row["sha256"])
actual = {
    str(path.relative_to(root))
    for path in root.rglob("*")
    if path.is_file() and path != manifest_path
}
if actual != set(expected):
    raise SystemExit("build manifest file list mismatch")
for rel, (size, wanted) in expected.items():
    path = root / rel
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.stat().st_size != size or digest != wanted:
        raise SystemExit(f"build manifest integrity mismatch: {rel}")
PY
}

tree_allocated_bytes() {
    python3 - "$@" <<'PY'
import os
import sys
from pathlib import Path
allocation = os.statvfs(sys.argv[1]).f_frsize or os.statvfs(sys.argv[1]).f_bsize
total = 0
for name in sys.argv[2:]:
    root = Path(name)
    files = [root] if root.is_file() else (
        [path for path in root.rglob("*") if path.is_file()] if root.is_dir() else []
    )
    for path in files:
        size = path.stat().st_size
        total += ((size + allocation - 1) // allocation) * allocation
print(total)
PY
}

publish_generation() {
    local stick="$1" dmg="$2" sidecar="$3" dest
    local required free stage previous had_old=0
    dest="$stick/RBSS BRIDGE USB"
    previous="$stick/.RBSS BRIDGE USB.previous"

    # FAT32 does not support macOS RENAME_SWAP. Recover a power-interrupted
    # prior two-rename commit before doing any new work.
    if [ ! -e "$dest" ] && [ -d "$previous" ]; then
        mv "$previous" "$dest" \
            || fail "cannot restore the prior complete bridge generation."
    elif [ -e "$dest" ] && [ -e "$previous" ]; then
        if [ -f "$dest/lighting_sidecar/.rbss_build_manifest.json" ] && \
            verify_build_manifest "$dest" "$dest/lighting_sidecar/.rbss_build_manifest.json"; then
            rm -rf "$previous"
        else
            fail "an interrupted bridge update left two generations; preserving both for recovery."
        fi
    fi

    if [ "$(stat -f %T "$stick")" = "msdos" ] && \
        [ "$(stat -f %z "$dmg")" -gt 4294967295 ]; then
        fail "the DMG exceeds FAT32's 4 GB file limit; prior stick generation is unchanged."
    fi
    required="$(( $(tree_allocated_bytes "$stick" "$dmg" "$sidecar") + 1048576 ))"
    free="$(( $(df -Pk "$stick" | awk 'NR==2 {print $4}') * 1024 ))"
    [ "$free" -ge "$required" ] \
        || fail "insufficient stick space for a rollback-safe update (need $required bytes, have $free)."

    stage="$(mktemp -d "$stick/.rbss-publish-new.XXXXXX")" \
        || fail "cannot create transactional staging on the stick."
    if ! COPYFILE_DISABLE=1 cp "$dmg" "$stage/RBSS Bridge.dmg"; then
        rm -rf "$stage"
        fail "step 'DMG transactional copy' failed; prior stick generation is unchanged."
    fi
    if ! COPYFILE_DISABLE=1 cp -R "$sidecar" "$stage/lighting_sidecar"; then
        rm -rf "$stage"
        fail "step 'sidecar transactional copy' failed; prior stick generation is unchanged."
    fi
    if ! write_build_manifest "$stage" "$stage/lighting_sidecar/.rbss_build_manifest.json"; then
        rm -rf "$stage"
        fail "step 'publication manifest' failed; prior stick generation is unchanged."
    fi
    if ! verify_build_manifest "$stage" "$stage/lighting_sidecar/.rbss_build_manifest.json"; then
        rm -rf "$stage"
        fail "step 'publication integrity check' failed; prior stick generation is unchanged."
    fi
    if ! sync; then
        rm -rf "$stage"
        fail "stick flush failed; prior stick generation is unchanged."
    fi

    if [ "${RBSS_MAKE_STICK_FAIL_BEFORE_SWAP:-}" = "1" ]; then
        rm -rf "$stage"
        fail "test stop before publication commit; prior stick generation is unchanged."
    fi
    if [ -e "$dest" ]; then
        if [ ! -d "$dest" ] || [ -L "$dest" ]; then
            rm -rf "$stage"
            fail "existing bridge surface is not a normal directory; refusing to replace it."
        fi
        had_old=1
        if ! mv "$dest" "$previous"; then
            rm -rf "$stage"
            fail "cannot hide the prior stick generation; it remains unchanged."
        fi
        if [ "${RBSS_MAKE_STICK_FAIL_AFTER_HIDE:-}" = "1" ] || ! mv "$stage" "$dest"; then
            mv "$previous" "$dest" \
                || fail "publication commit failed and the prior generation could not be restored; preserve the hidden previous folder."
            rm -rf "$stage"
            fail "publication commit failed; the prior generation was restored."
        fi
    else
        if ! mv "$stage" "$dest"; then
            rm -rf "$stage"
            fail "first publication commit failed; no partial bridge surface was exposed."
        fi
    fi

    if ! verify_build_manifest "$dest" "$dest/lighting_sidecar/.rbss_build_manifest.json"; then
        if [ "$had_old" = "1" ]; then
            mv "$dest" "$stage" \
                || fail "published verification failed and the new generation could not be hidden."
            mv "$previous" "$dest" \
                || fail "published verification failed and automatic rollback also failed; preserve both bridge folders for recovery."
            rm -rf "$stage"
        else
            mv "$dest" "$stage" \
                || fail "published verification failed and the incomplete first generation could not be hidden."
            rm -rf "$stage"
        fi
        fail "published verification failed; the prior generation was restored."
    fi
    if ! sync; then
        if [ "$had_old" = "1" ]; then
            mv "$dest" "$stage" \
                || fail "stick flush failed and the new generation could not be hidden."
            mv "$previous" "$dest" \
                || fail "stick flush failed and the prior generation could not be restored."
            rm -rf "$stage"
        fi
        fail "stick flush failed after publication; the prior generation was restored when available."
    fi

    # Removing the proven old surface now also removes retired command helpers
    # and the retired sibling RBSS_payload, never before the new set is proven.
    if [ "$had_old" = "1" ]; then
        rm -rf "$previous"
    fi
}

# ── build interpreter: python.org, low deployment target ─────────────────────
# Homebrew's Python targets macOS 15, so a bundle built with it crashes on older
# macOS (Symbol not found: _mkfifoat). Require a python.org FRAMEWORK build with a
# low deployment target; python.org ships it universal2, which is a reliable marker
# for that build (the produced app is still arm64 — see the header). Override with
# RBSS_BUILD_PYTHON=/path/to/python3.
find_build_python() {
    local candidates=() py
    [ -n "${RBSS_BUILD_PYTHON:-}" ] && candidates+=("$RBSS_BUILD_PYTHON")
    candidates+=("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3")
    for py in "${candidates[@]}"; do
        [ -x "$py" ] || continue
        build_python_is_supported "$py" || continue
        echo "$py"
        return 0
    done
    return 1
}

if [ "${RBSS_MAKE_STICK_SOURCE_ONLY:-}" = "1" ]; then
    return 0 2>/dev/null || exit 0
fi

# ── target checks first: refuse before spending minutes on a build ──────────
STICK="${1:-}"
if [ -z "$STAGE_ONLY" ]; then
    [ -n "$STICK" ] || fail "usage: bash packaging/make_stick.sh /Volumes/<stick>"
    [ -d "$STICK" ] || fail "'$STICK' is not a mounted volume."
    [ -d "$STICK/PIONEER" ] || fail "'$STICK' has no PIONEER/ — not the rekordbox-exported stick. Refusing."
    DEST="$STICK/RBSS BRIDGE USB"
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
    if ! venv_is_locked; then
        BUILD_PY="$(find_build_python)" || fail "python.org universal2 Python $BUILD_PYTHON_VERSION is required. Install that exact macOS installer or set RBSS_BUILD_PYTHON=/path/to/its/python3."
        echo "make_stick: build interpreter → $BUILD_PY (universal2, target $MACOSX_DEPLOYMENT_TARGET)"
        rm -rf "$VENV" "$WHEELHOUSE"
        mkdir -p "$WHEELHOUSE"
        {
            "$BUILD_PY" -m venv "$VENV" &&
            download_locked_artifacts "$BUILD_PY" "$WHEELHOUSE" "$WHEEL_LOCK" "$SOURCE_LOCK" &&
            verify_locked_artifacts "$WHEEL_LOCK" "$WHEELHOUSE" &&
            verify_locked_artifacts "$SOURCE_LOCK" "$WHEELHOUSE" &&
            validate_locked_wheelhouse "$WHEELHOUSE" &&
            "$VENV/bin/python" -m pip install --no-index --no-deps --require-hashes \
                --find-links "$WHEELHOUSE" --requirement "$WHEEL_LOCK" &&
            RTMIDI_WHEEL="$(build_python_rtmidi_wheel "$VENV/bin/python" "$WHEELHOUSE")" &&
            "$VENV/bin/python" -m pip install --no-index --no-deps "$RTMIDI_WHEEL" &&
            "$VENV/bin/python" -m pip install --no-index --no-deps --no-build-isolation . &&
            "$VENV/bin/python" -m pip check &&
            "$VENV/bin/python" "$REPO_ROOT/usb_launcher.py" --check-deps &&
            build_lock_fingerprint "$VENV/bin/python" > "$VENV/.rbss-macos12-lock"
        } || {
            rm -rf "$VENV"
            fail "locked macOS 12.3 build environment setup failed; no app or DMG was produced."
        }
    fi
    RBSS_GENERATION="$GENERATION" "$VENV/bin/pyinstaller" packaging/rbss_launcher.spec \
        --noconfirm --distpath dist --workpath build
    # Stamp the same generation into Info.plist again before signing so a
    # PyInstaller/env miss cannot ship the fallback 0.0.1 against a real
    # build-manifest generation. No-op when the values already match.
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $GENERATION" \
        "dist/RBSS Bridge.app/Contents/Info.plist"
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $GENERATION" \
        "dist/RBSS Bridge.app/Contents/Info.plist"
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
    # The launcher can be compatible while an embedded wheel is not. Inspect every
    # Mach-O in the finished app and reject any slice newer than the declared floor.
    validate_app_macos_target "$REPO_ROOT/dist/RBSS Bridge.app"
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
[ -d "$CACHE_SRC" ] \
    || fail "required analysis cache is missing at '$CACHE_SRC'; refusing a non-parity package."
mkdir -p "$STAGING/RBSS_payload"
cp -R "$CACHE_SRC" "$STAGING/RBSS_payload/spectral_cache" \
    || fail "step 'spectral_cache copy' failed — cache exists but is unreadable."

mkdir -p "$STAGING/RBSS_payload/home"
for src in "${HOME_PARITY_FILES[@]}"; do
    [ -f "$src" ] \
        || fail "required managed home file is missing: '${src##*/}'."
    cp "$src" "$STAGING/RBSS_payload/home/" \
        || fail "step 'home-parity copy' failed on '${src##*/}' — exists but unreadable."
done

# The exported SoundSwitch pack itself (the show): read pack_path from the live
# config and copy the whole dir into the payload, so the guest Mac's native pack
# DMG renderer has something to load (its config pack_path is a build-machine
# absolute path). RBSS_SS_PACK_PATH on the guest points the renderer here.
PACK_CFG="$CONFIG_DIR/soundswitch_pack_player.json"
PACK_SRC="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); path=value.get("pack_path","") if isinstance(value,dict) else ""; print(path or "")' "$PACK_CFG")" \
    || fail "step 'pack config read' failed — soundswitch_pack_player.json is unreadable or not valid JSON."
[ -n "$PACK_SRC" ] \
    || fail "canonical SoundSwitch pack_path is empty; refusing a non-parity package."
[ -d "$PACK_SRC" ] \
    || fail "step 'pack copy' failed — configured canonical pack is not a readable directory."
cp -R "$PACK_SRC" "$STAGING/RBSS_payload/soundswitch_pack" \
    || fail "step 'pack copy' failed — canonical pack dir is unreadable."

[ -f "$BINDINGS_SRC" ] \
    || fail "required Stream Deck MIDI bindings are missing."
cp "$BINDINGS_SRC" "$STAGING/RBSS_payload/streamdeck_midi_bindings.json" \
    || fail "step 'Stream Deck bindings copy' failed."
cmp -s "$BINDINGS_SRC" "$STAGING/RBSS_payload/streamdeck_midi_bindings.json" \
    || fail "Stream Deck MIDI bindings changed during copy."

# Seed a private working copy from the prior published sidecar so the exporter
# can reuse unchanged tracks. The visible old sidecar is never edited in place.
SIDECAR_WORK="$STAGING/.rbss-sidecar-work"
mkdir -p "$SIDECAR_WORK"
if [ -z "$STAGE_ONLY" ] && [ -d "$DEST/lighting_sidecar" ]; then
    COPYFILE_DISABLE=1 cp -R "$DEST/lighting_sidecar" "$SIDECAR_WORK/lighting_sidecar" \
        || fail "step 'sidecar seed copy' failed; prior stick generation is unchanged."
    rm -f "$SIDECAR_WORK/lighting_sidecar/.rbss_build_manifest.json"
    find "$SIDECAR_WORK/lighting_sidecar" -type f \
        \( -name '._*' -o -name '.DS_Store' \) -exec rm -f {} +
fi
export_lighting_sidecar "$SIDECAR_WORK"
[ -f "$SIDECAR_WORK/lighting_sidecar/index.json" ] \
    || fail "lighting sidecar export produced no index."
cp -R "$SIDECAR_WORK/lighting_sidecar" "$STAGING/RBSS_payload/lighting_sidecar" \
    || fail "step 'sidecar payload copy' failed."
rm -rf "$SIDECAR_WORK"

validate_parity_data \
    "$STAGING/RBSS_payload/home" \
    "$STAGING/RBSS_payload/soundswitch_pack" \
    "$STAGING/RBSS_payload/lighting_sidecar" \
    "$STAGING/RBSS_payload/streamdeck_midi_bindings.json" \
    "$STAGING/RBSS_payload/spectral_cache" \
    || fail "required home-parity data is malformed or incomplete."

write_build_manifest "$STAGING" "$STAGING/RBSS_payload/build_manifest.json" \
    || fail "step 'package build manifest' failed."
verify_build_manifest "$STAGING" "$STAGING/RBSS_payload/build_manifest.json" \
    || fail "staged package failed its build-manifest integrity check."

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
publish_generation "$STICK" "$DMG" "$STAGING/RBSS_payload/lighting_sidecar"

DMG_SIZE="$(du -h "$DMG" | cut -f1)"
FREE="$(df -h "$STICK" | awk 'NR==2 {print $4}')"
echo "make_stick: DONE."
echo "  DMG:            $DMG_SIZE  ($DMG)"
echo "  payload files:  $PAYLOAD_COUNT (inside the DMG, RBSS_payload/)"
echo "  stick free:     $FREE  ($STICK)"
