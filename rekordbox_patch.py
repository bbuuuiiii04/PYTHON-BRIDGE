"""Detect and (with explicit consent) patch Rekordbox so the bridge can read it.

The bridge reads Rekordbox's live state via ``task_for_pid`` (see ``rb_memory.py``),
which macOS only permits when the TARGET — rekordbox — carries the
``com.apple.security.get-task-allow`` entitlement. Stock Rekordbox from
Pioneer/AlphaTheta is Developer-ID signed + notarized and does NOT carry it, so
on an un-patched Mac the bridge launches but reads nothing.

This module re-signs Rekordbox **ad-hoc** with ``get-task-allow`` added
(preserving its existing entitlements), replicating the signature already present
and proven working on the maintainer's primary Mac (ad-hoc + get-task-allow +
disable-library-validation).

THIS MODIFIES A THIRD-PARTY APP, so it is deliberately conservative:
  * **opt-in** — never runs without explicit operator consent (CLI ``--apply`` /
    menubar confirmation); ``--check``/``--dry-run`` do nothing destructive;
  * **refused while Rekordbox is running** — you re-sign a quit app, then relaunch
    it for the new signature to take effect;
  * **guarded** — only ever touches a bundle whose id is ``com.pioneerdj.rekordboxdj``;
  * **fail-closed + verified** — ``codesign --verify`` then re-reads get-task-allow;
    on any failure it reports the step and tells you to reinstall Rekordbox;
  * **reversible** only by reinstalling/updating Rekordbox (a RB update reverts the
    patch — expected; re-run this after an update).

CLI:
    python3 -m rb_ss_bridge_v2.rekordbox_patch --check
    python3 -m rb_ss_bridge_v2.rekordbox_patch --dry-run
    python3 -m rb_ss_bridge_v2.rekordbox_patch --apply         # prompts to confirm
    python3 -m rb_ss_bridge_v2.rekordbox_patch --apply --yes    # no prompt (menubar/admin use)
"""
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REKORDBOX_APP_PATHS: tuple[Path, ...] = (
    Path("/Applications/rekordbox 7/rekordbox.app"),
    Path("/Applications/rekordbox 6/rekordbox.app"),
    Path("/Applications/rekordbox/rekordbox.app"),
)
REKORDBOX_BUNDLE_ID = "com.pioneerdj.rekordboxdj"

# The entitlements that make the bridge's read work, matching the proven-working
# ad-hoc signature on the maintainer's primary Mac. Merged OVER the app's existing
# entitlements (everything else preserved), so Rekordbox keeps its own capabilities.
GET_TASK_ALLOW = "com.apple.security.get-task-allow"
ADDED_ENTITLEMENTS: dict[str, bool] = {
    GET_TASK_ALLOW: True,
    "com.apple.security.cs.disable-library-validation": True,
    "com.apple.security.cs.allow-unsigned-executable-memory": True,
}


# ── Pure, testable seams ─────────────────────────────────────────────────────

def parse_entitlements_output(data: bytes) -> dict:
    """Extract the entitlements dict from ``codesign -d --entitlements`` output.

    codesign prints an XML plist (possibly with leading/trailing noise); an
    unsigned app or one with no entitlements yields no plist. Returns {} on
    anything unparseable — fail-open to "no entitlements known" is safe because
    the caller then treats the app as needing a patch and re-verifies after.
    """
    if not data:
        return {}
    start = data.find(b"<?xml")
    if start == -1:
        start = data.find(b"<plist")
    end = data.rfind(b"</plist>")
    if start == -1 or end == -1:
        return {}
    try:
        obj = plistlib.loads(data[start:end + len(b"</plist>")])
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def build_patched_entitlements(current: dict) -> dict:
    """Current entitlements with the bridge-read entitlements merged in."""
    merged = dict(current)
    merged.update(ADDED_ENTITLEMENTS)
    return merged


def needs_patch(current: dict) -> bool:
    """True unless get-task-allow is already present and true."""
    return current.get(GET_TASK_ALLOW) is not True


def codesign_argv(app: Path, entitlements_path: Path) -> list[str]:
    """The ad-hoc re-sign command. NOT ``--deep``: only the main bundle is
    re-signed (its executable is the process the bridge attaches to); nested
    Pioneer-signed frameworks stay intact and load via disable-library-validation."""
    return [
        "codesign", "--force", "--sign", "-",
        "--entitlements", str(entitlements_path), str(app),
    ]


# ── On-machine inspection (read-only) ────────────────────────────────────────

def find_rekordbox(app_paths: tuple[Path, ...] | None = None) -> Path | None:
    for app in (app_paths or REKORDBOX_APP_PATHS):
        if app.exists():
            return app
    return None


def bundle_id(app: Path) -> str:
    try:
        with open(app / "Contents" / "Info.plist", "rb") as fh:
            return str(plistlib.load(fh).get("CFBundleIdentifier", ""))
    except OSError:
        return ""


def read_entitlements(app: Path) -> dict:
    try:
        proc = subprocess.run(
            ["codesign", "-d", "--entitlements", ":-", "--xml", str(app)],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_entitlements_output(proc.stdout or b"")


def has_get_task_allow(app: Path) -> bool:
    return read_entitlements(app).get(GET_TASK_ALLOW) is True


def is_rekordbox_running() -> bool:
    try:
        return subprocess.run(
            ["pgrep", "-x", "rekordbox"], capture_output=True, timeout=10
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False  # can't tell -> treat as not running; apply_patch re-guards


# ── The patch ────────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    ok: bool
    action: str            # "already_patched" | "would_patch" | "patched" | "refused" | "failed"
    message: str
    command: list[str] | None = None


def apply_patch(app: Path, *, dry_run: bool = True) -> PatchResult:
    """Re-sign ``app`` ad-hoc with get-task-allow, fail-closed and verified.

    dry_run=True (default) does NO modification — it returns the exact codesign
    command that WOULD run. Callers must pass dry_run=False AND have obtained
    explicit consent to modify Rekordbox.
    """
    if bundle_id(app) != REKORDBOX_BUNDLE_ID:
        return PatchResult(False, "refused",
                           f"{app} is not Rekordbox (bundle id != {REKORDBOX_BUNDLE_ID}); refusing to sign.")
    if is_rekordbox_running():
        return PatchResult(False, "refused",
                           "Rekordbox is running — quit it first (re-sign only takes effect on relaunch).")

    current = read_entitlements(app)
    if not needs_patch(current):
        return PatchResult(True, "already_patched",
                           "Rekordbox already carries get-task-allow — nothing to do.")

    merged = build_patched_entitlements(current)
    # Write the entitlements to a temp plist codesign will read.
    with tempfile.NamedTemporaryFile("wb", suffix=".plist", delete=False) as fh:
        plistlib.dump(merged, fh)
        ents_path = Path(fh.name)
    argv = codesign_argv(app, ents_path)

    if dry_run:
        return PatchResult(True, "would_patch",
                           "Dry run — Rekordbox NOT modified. This command would add get-task-allow.",
                           command=argv)

    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        return PatchResult(False, "failed", f"codesign did not run: {exc}", command=argv)
    if proc.returncode != 0:
        hint = ""
        if "not permitted" in (proc.stderr or "").lower() or "permission denied" in (proc.stderr or "").lower():
            hint = " (needs admin — run with sudo, or use the menubar which prompts for your password)"
        return PatchResult(False, "failed",
                           f"codesign failed{hint}: {proc.stderr.strip()}", command=argv)

    # Verify the re-sign is valid AND the entitlement actually took.
    verify = subprocess.run(["codesign", "--verify", "--strict", str(app)],
                            capture_output=True, text=True, timeout=120)
    if verify.returncode != 0:
        return PatchResult(False, "failed",
                           "Re-sign did not verify — Rekordbox signature may be broken. "
                           "Reinstall Rekordbox to restore it. Details: " + verify.stderr.strip(),
                           command=argv)
    if not has_get_task_allow(app):
        return PatchResult(False, "failed",
                           "Re-sign succeeded but get-task-allow is still absent — no change took effect.",
                           command=argv)
    return PatchResult(True, "patched",
                       "Rekordbox patched — relaunch Rekordbox, then start the bridge and it will read it.",
                       command=argv)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Enable the bridge to read Rekordbox memory on this Mac.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="report whether Rekordbox is already patched (default)")
    g.add_argument("--dry-run", action="store_true", help="show the exact command without modifying anything")
    g.add_argument("--apply", action="store_true", help="apply the patch (Rekordbox must be quit)")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt (for menubar/admin use)")
    args = ap.parse_args(argv)

    app = find_rekordbox()
    if app is None:
        print("Rekordbox not found in /Applications.")
        return 2

    if args.apply:
        if not args.yes:
            print(f"About to RE-SIGN {app} ad-hoc to add get-task-allow.")
            print("  - This modifies Rekordbox (a Rekordbox update will revert it).")
            print("  - Quit Rekordbox first. You may be asked for your admin password.")
            if input("Type YES to proceed: ").strip() != "YES":
                print("Aborted.")
                return 1
        result = apply_patch(app, dry_run=False)
    elif args.dry_run:
        result = apply_patch(app, dry_run=True)
    else:  # --check (default)
        patched = has_get_task_allow(app)
        running = is_rekordbox_running()
        print(f"Rekordbox: {app}")
        print(f"  get-task-allow present: {'YES (bridge can read it)' if patched else 'NO (bridge will read nothing)'}")
        print(f"  running now: {'yes' if running else 'no'}")
        if not patched:
            print("  -> run with --apply to enable reads (quit Rekordbox first).")
        return 0 if patched else 3

    print(result.message)
    if result.command and (args.dry_run or not result.ok):
        print("  command:", " ".join(result.command))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
