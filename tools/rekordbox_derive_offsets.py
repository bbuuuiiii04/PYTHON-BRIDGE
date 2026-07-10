#!/usr/bin/env python3
"""Offline version-extension tool for the Rekordbox memory-offset table.

Derives a new Rekordbox build's per-version chain base anchors from the
rekordbox **arm64 binary's symbol table**, so adding a supported version is a
deterministic ``nm`` lookup instead of hand reverse-engineering the RVAs.

Invariant (rekordbox 7.2.11, arm64 — reverse-engineered and verified against
``/Applications/rekordbox 7`` in this repo's RE session): three of the four
chain roots are exactly ``<SingletonClass>::singletonHolder + 0x40`` — the
instance pointer sits at a uniform +0x40 inside rekordbox's ``SingletonHolder<T>``
struct, so the anchor for a role is ``symbol_address + 0x40``:

    master (ApplicationMode)               __ZN15ApplicationMode15singletonHolderE               + 0x40
    anlz   (browse::LoadedContentsManager) __ZN6browse21LoadedContentsManager15singletonHolderE  + 0x40
    mixer  (djengine::DjEngineIF)          __ZN8djengine10DjEngineIF15singletonHolderE           + 0x40

The DECK root (bpm / live-pos / track_info) is an LLVM-merged file-static
global (``__MergedGlobals``) with NO stable per-global symbol; it is not
symbol-derivable and must be carried forward from the nearest known version and
confirmed by a live read (see docs/subsystems/rekordbox_readers.md). This tool
derives the three symbol-based anchors and flags the deck anchor.

This is an OFFLINE maintenance tool: nothing under the runtime package imports
it (same rule as tools/analyze_anlz_energy_corpus.py). The two module-level
functions ``parse_nm`` and ``derive_anchors`` are pure and are the test seam.

Usage:
    python3 tools/rekordbox_derive_offsets.py --binary "/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox"
    python3 tools/rekordbox_derive_offsets.py --binary <path> --expect 7.2.11   # self-check vs rb_offsets.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# role -> mangled nm symbol whose (address + INSTANCE_OFF) is the chain anchor.
SINGLETON_ANCHORS: dict[str, str] = {
    "master": "__ZN15ApplicationMode15singletonHolderE",
    "anlz":   "__ZN6browse21LoadedContentsManager15singletonHolderE",
    "mixer":  "__ZN8djengine10DjEngineIF15singletonHolderE",
}
INSTANCE_OFF = 0x40                 # SingletonHolder<T> instance-pointer offset (uniform across the 3)
DEFAULT_IMAGE_BASE = 0x100000000    # arm64 macOS __TEXT vmaddr
DECK_ROLE = "deck"                  # bpm/pos/track_info root — NOT symbol-derivable (__MergedGlobals)


def parse_nm(nm_text: str) -> dict[str, int]:
    """Parse ``nm --defined-only`` output into {symbol_name: address}.

    Lines are ``<hex-addr> <type> <name>``; undefined/malformed lines are
    skipped. Later duplicate names win (harmless — the anchor symbols are unique).
    """
    out: dict[str, int] = {}
    for line in nm_text.splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        out[parts[2]] = addr
    return out


def derive_anchors(symbols: dict[str, int], image_base: int = DEFAULT_IMAGE_BASE) -> dict[str, int]:
    """Return {role: anchor RVA} for the three symbol-derivable chain roots.

    ``anchor_rva = symbol_address + INSTANCE_OFF - image_base``. Fail-closed:
    raises KeyError naming every missing singleton symbol so a build that
    dropped/renamed a symbol produces NO offset rather than a silently wrong one.
    """
    missing = [sym for sym in SINGLETON_ANCHORS.values() if sym not in symbols]
    if missing:
        raise KeyError("rekordbox binary missing singleton symbol(s): " + ", ".join(sorted(missing)))
    return {
        role: symbols[sym] + INSTANCE_OFF - image_base
        for role, sym in SINGLETON_ANCHORS.items()
    }


def run_nm(binary: Path, arch: str = "arm64") -> str:
    return subprocess.run(
        ["nm", "-arch", arch, "-n", "--defined-only", str(binary)],
        capture_output=True, text=True, check=True,
    ).stdout


def read_image_base(binary: Path, arch: str = "arm64") -> int:
    """__TEXT vmaddr from ``otool -l``; falls back to the arm64 default."""
    try:
        out = subprocess.run(
            ["otool", "-arch", arch, "-l", str(binary)],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return DEFAULT_IMAGE_BASE
    in_text = False
    for line in out.splitlines():
        s = line.split()
        if len(s) >= 2 and s[0] == "segname" and s[1] == "__TEXT":
            in_text = True
        elif in_text and len(s) >= 2 and s[0] == "vmaddr":
            return int(s[1], 16)
    return DEFAULT_IMAGE_BASE


def _expected_from_table(version: str) -> dict[str, int]:
    """The known anchor RVAs for ``version`` from the shipped table, for --expect."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))
    from rb_ss_bridge_v2 import rb_offsets  # noqa: E402
    t = rb_offsets.all_offsets()[version]
    return {
        "master": t.master_deck.hops[0],
        "anlz": t.anlz_path_per_deck[0].hops[0],
        "mixer": t.mixer_deck1_upfader_raw.hops[0] if t.mixer_deck1_upfader_raw else -1,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", required=True, help="path to the rekordbox Mach-O (arm64 slice used)")
    ap.add_argument("--expect", metavar="VERSION",
                    help="self-check derived anchors against rb_offsets.py's row for VERSION (e.g. 7.2.11)")
    args = ap.parse_args(argv)

    binary = Path(args.binary)
    image_base = read_image_base(binary)
    anchors = derive_anchors(parse_nm(run_nm(binary)), image_base)

    print(f"image_base 0x{image_base:x}")
    for role in ("master", "anlz", "mixer"):
        print(f"  {role:6s} anchor RVA 0x{anchors[role]:x}   ({SINGLETON_ANCHORS[role]} + 0x{INSTANCE_OFF:x})")
    print(f"  {DECK_ROLE:6s} anchor RVA <manual>  (__MergedGlobals — not symbol-derivable; carry forward + live-read verify)")

    if args.expect:
        exp = _expected_from_table(args.expect)
        ok = all(anchors[r] == exp[r] for r in ("master", "anlz", "mixer"))
        for r in ("master", "anlz", "mixer"):
            flag = "OK" if anchors[r] == exp[r] else f"MISMATCH (table 0x{exp[r]:x})"
            print(f"  verify {r}: {flag}")
        print("VERIFY", "PASS" if ok else "FAIL", f"(vs {args.expect})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
