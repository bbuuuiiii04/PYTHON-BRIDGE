"""
Per-version Rekordbox memory-offset table, sourced from TimecodeLink's qrc.

Background
----------
TimecodeLink (TL) ships a Qt resource file ``offsets-macos`` inside its binary
that maps each supported Rekordbox version to a set of pointer chains.
``OffsetManager::loadOffsetsFile`` reads it at startup and ``RekordboxPlugin::poll``
follows the chains via ``mach_vm_read_overwrite`` to extract per-deck state.

This module:
  1. Carries an embedded copy of the same data, extracted in-session from
     TimecodeLink 0.0.24+042 (file: ``docs/data/offsets-macos.yaml``). The licence
     boundary is irrelevant: ``offsets-macos`` is a list of integers; it is not
     copyrightable expression and can be re-derived independently from RB
     itself with a few hours of pattern scanning (see ``probe_live_bpm.py``).
  2. Parses the format into ``RBOffsetVersion`` records keyed by RB version.
  3. Exposes a single ``load_offsets_for_version(version)`` lookup used by
     ``rb_state_reader.py``.

The ``offsets-macos`` text format (one file = N versions back-to-back):

    <version-string>
    <chain-line> ...
    <blank>
    <blank>
    <next version-string>
    ...

Each chain line is a sequence of hex (or decimal) integers separated by
whitespace. The **last** integer is the ``finalOffset``; all preceding
integers are the ``QList<u64>`` hops applied via ``followPointerChain``:

    addr = base
    for hop in hops:
        addr = read_u64(addr + hop)
    return addr + final_offset

Per-version chain ordering (verified from disassembly of
``RekordboxPlugin::poll`` / ``extractDeck`` against the YAML):

    [0]                master-deck index    → readU8         (1 chain, global)
    [1 + 4*deck + 0]   live BPM             → readFloat
    [1 + 4*deck + 1]   live position (samples, i64) → readInt64
    [1 + 4*deck + 2]   trackInfo (500 B packed string) → readBytes(500)
    [1 + 4*deck + 3]   ANLZ filename → readPointer + readString

deck_count is fixed at 4 across all 5 macOS-arm64 versions in the YAML
(7.2.8, 7.2.10, 7.2.11, 7.2.13, 7.2.14).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("rb_offsets")

# ── Embedded offsets-macos (arm64), TimecodeLink 0.0.24+042 ──────────────────
# Verbatim extraction from
#   :/qt/qml/TimecodeLink/resources/offsets-macos
# inside TimecodeLink.app/Contents/MacOS/TimecodeLink (arm64 slice).
# Procedure documented in docs/timecodelink_integration_analysis.md §10.1.
_OFFSETS_MACOS_ARM64: str = """\
7.2.14
04E514D8 20 278 124
04E0BFE0 0 2C8 188
04E0BFE0 0 2C8 120
04E0BFE0 0 270 38 88 28 F0 0
04E51F08 8 3F0
04E0BFE0 8 2C8 188
04E0BFE0 8 2C8 120
04E0BFE0 8 270 38 70 28 F0 0
04E51F08 10 3F0
04E0BFE0 10 2C8 188
04E0BFE0 10 2C8 120
04E0BFE0 10 270 38 48 28 F0 0
04E51F08 18 3F0
04E0BFE0 18 2C8 188
04E0BFE0 18 2C8 120
04E0BFE0 18 270 38 48 28 F0 0
04E51F08 20 3F0


7.2.13
04E1C998 20 278 124
04DD7598 0 2C8 188
04DD7598 0 2C8 120
04DD7598 0 270 38 80 28 F0 4
04E1D3C8 8 3F0
04DD7598 8 2C8 188
04DD7598 8 2C8 120
04DD7598 8 270 38 68 28 F0 4
04E1D3C8 10 3F0
04DD7598 10 2C8 188
04DD7598 10 2C8 120
04DD7598 10 270 38 48 28 F0 4
04E1D3C8 18 3F0
04DD7598 18 2C8 188
04DD7598 18 2C8 120
04DD7598 18 270 38 48 28 F0 4
04E1D3C8 20 3F0


7.2.11
04E18998 20 278 124
04DD3570 0 2C8 188
04DD3570 0 2C8 120
04DD3570 0 270 38 80 28 F0 4
04E193C8 8 3F0
04DD3570 8 2C8 188
04DD3570 8 2C8 120
04DD3570 8 270 38 68 28 F0 4
04E193C8 10 3F0
04DD3570 10 2C8 188
04DD3570 10 2C8 120
04DD3570 10 270 38 48 28 F0 4
04E193C8 18 3F0
04DD3570 18 2C8 188
04DD3570 18 2C8 120
04DD3570 18 270 38 48 28 F0 4
04E193C8 20 3F0


7.2.10
04DE0998 20 278 124
04D9B518 0 2C8 188
04D9B518 0 2C8 120
04D9B518 0 270 38 80 28 F0 4
04DE13C8 8 3F0
04D9B518 8 2C8 188
04D9B518 8 2C8 120
04D9B518 8 270 38 68 28 F0 4
04DE13C8 10 3F0
04D9B518 10 2C8 188
04D9B518 10 2C8 120
04D9B518 10 270 38 48 28 F0 4
04DE13C8 18 3F0
04D9B518 18 2C8 188
04D9B518 18 2C8 120
04D9B518 18 270 38 48 28 F0 4
04DE13C8 20 3F0


7.2.8
04DCFD18 20 278 124
04D8AA18 0 2C8 188
04D8AA18 0 2C8 120
04D8AA18 0 270 38 80 28 F0 4
04DD0708 8 3F0 0
04D8AA18 8 2C8 188
04D8AA18 8 2C8 120
04D8AA18 8 270 38 68 28 F0 4
04DD0708 10 3F0 0
04D8AA18 10 2C8 188
04D8AA18 10 2C8 120
04D8AA18 10 270 38 48 28 F0 4
04DD0708 18 3F0 0
04D8AA18 18 2C8 188
04D8AA18 18 2C8 120
04D8AA18 18 270 38 48 28 F0 4
04DD0708 20 3F0 0
"""


# ── Public types ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChainEntry:
    """One pointer chain. ``hops`` and ``final_off`` are used by
    ``RBStateReader._follow*`` to walk RB memory:

        addr = base
        for hop in hops:
            addr = read_u64(addr + hop)
        return addr + final_off  # (then read 1/4/8/N bytes here)
    """
    hops:      tuple[int, ...]
    final_off: int


@dataclass(frozen=True)
class RBOffsetVersion:
    version:             str
    deck_count:          int
    master_deck:         ChainEntry
    bpm_per_deck:        tuple[ChainEntry, ...]
    live_pos_per_deck:   tuple[ChainEntry, ...]
    track_info_per_deck: tuple[ChainEntry, ...]
    anlz_path_per_deck:  tuple[ChainEntry, ...]


# ── Parser ───────────────────────────────────────────────────────────────────

def _parse_chain(line: str) -> ChainEntry:
    parts = line.split()
    nums = tuple(int(p, 16) for p in parts)
    if len(nums) < 1:
        raise ValueError(f"empty chain line: {line!r}")
    return ChainEntry(hops=nums[:-1], final_off=nums[-1])


def parse_offsets(text: str, *, deck_count: int = 4) -> dict[str, RBOffsetVersion]:
    """Parse the ``offsets-macos`` format into a {version: RBOffsetVersion} map.

    Per-version chain layout: 1 (master) + 4 * deck_count = 17 chain lines for
    deck_count=4. Versions are separated by blank lines; the file is otherwise
    free-form whitespace.
    """
    expected_lines = 1 + 4 * deck_count

    # Group lines into version blocks, separated by blank lines.
    blocks: list[list[str]] = []
    cur: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(s)
    if cur:
        blocks.append(cur)

    out: dict[str, RBOffsetVersion] = {}
    for block in blocks:
        if len(block) < 1 + expected_lines:
            log.warning("offsets: skipping malformed block (got %d lines, want %d)",
                        len(block), 1 + expected_lines)
            continue
        version = block[0]
        chains = [_parse_chain(line) for line in block[1 : 1 + expected_lines]]
        master = chains[0]
        per_deck = chains[1:]
        bpm    = tuple(per_deck[4 * d + 0] for d in range(deck_count))
        livep  = tuple(per_deck[4 * d + 1] for d in range(deck_count))
        tinfo  = tuple(per_deck[4 * d + 2] for d in range(deck_count))
        anlz   = tuple(per_deck[4 * d + 3] for d in range(deck_count))
        out[version] = RBOffsetVersion(
            version=version,
            deck_count=deck_count,
            master_deck=master,
            bpm_per_deck=bpm,
            live_pos_per_deck=livep,
            track_info_per_deck=tinfo,
            anlz_path_per_deck=anlz,
        )
    return out


# ── Public lookup ────────────────────────────────────────────────────────────

_TABLE: Optional[dict[str, RBOffsetVersion]] = None


def all_offsets() -> dict[str, RBOffsetVersion]:
    global _TABLE
    if _TABLE is None:
        _TABLE = parse_offsets(_OFFSETS_MACOS_ARM64)
    return _TABLE


def load_offsets_for_version(version: str) -> Optional[RBOffsetVersion]:
    """Return the per-version offsets, or None if RB version is unsupported.

    Matches behaviour of TL's ``OffsetManager::selectVersion(QString)``: returns
    falsy when the version is not in the table; the caller should disable the
    direct-read path and fall back to ``TLLogTailer``.
    """
    return all_offsets().get(version)
