"""Unit tests for the embedded TimecodeLink offsets-macos table."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.rb_offsets import (
    ChainEntry,
    RBOffsetVersion,
    all_offsets,
    load_offsets_for_version,
    parse_offsets,
)


EXPECTED_VERSIONS = {"7.2.8", "7.2.10", "7.2.11", "7.2.13", "7.2.14"}


class EmbeddedTableTests(unittest.TestCase):
    def test_all_supported_versions_loaded(self) -> None:
        self.assertEqual(set(all_offsets().keys()), EXPECTED_VERSIONS)

    def test_load_for_unsupported_returns_none(self) -> None:
        self.assertIsNone(load_offsets_for_version("9.9.9"))
        self.assertIsNone(load_offsets_for_version(""))

    def test_load_for_supported_returns_offset_version(self) -> None:
        v = load_offsets_for_version("7.2.11")
        assert v is not None
        self.assertIsInstance(v, RBOffsetVersion)
        self.assertEqual(v.version, "7.2.11")
        self.assertEqual(v.deck_count, 4)


class V7211ChainTests(unittest.TestCase):
    """Verify the verbatim RB 7.2.11 chain values from the extracted YAML."""

    def setUp(self) -> None:
        v = load_offsets_for_version("7.2.11")
        assert v is not None
        self.v: RBOffsetVersion = v

    def test_master_chain(self) -> None:
        self.assertEqual(
            self.v.master_deck,
            ChainEntry(hops=(0x04E18998, 0x20, 0x278), final_off=0x124),
        )

    def test_per_deck_bpm_chains(self) -> None:
        for d, off in enumerate([0x0, 0x8, 0x10, 0x18]):
            self.assertEqual(
                self.v.bpm_per_deck[d],
                ChainEntry(hops=(0x04DD3570, off, 0x2C8), final_off=0x188),
                msg=f"deck {d}",
            )

    def test_per_deck_live_pos_chains(self) -> None:
        for d, off in enumerate([0x0, 0x8, 0x10, 0x18]):
            self.assertEqual(
                self.v.live_pos_per_deck[d],
                ChainEntry(hops=(0x04DD3570, off, 0x2C8), final_off=0x120),
                msg=f"deck {d}",
            )

    def test_per_deck_track_info_uses_explicit_per_deck_hops(self) -> None:
        expected = [
            ChainEntry(hops=(0x04DD3570, 0x0,  0x270, 0x38, 0x80, 0x28, 0xF0), final_off=0x4),
            ChainEntry(hops=(0x04DD3570, 0x8,  0x270, 0x38, 0x68, 0x28, 0xF0), final_off=0x4),
            ChainEntry(hops=(0x04DD3570, 0x10, 0x270, 0x38, 0x48, 0x28, 0xF0), final_off=0x4),
            ChainEntry(hops=(0x04DD3570, 0x18, 0x270, 0x38, 0x48, 0x28, 0xF0), final_off=0x4),
        ]
        self.assertEqual(list(self.v.track_info_per_deck), expected)

    def test_per_deck_anlz_chains(self) -> None:
        for d, off in enumerate([0x8, 0x10, 0x18, 0x20]):
            self.assertEqual(
                self.v.anlz_path_per_deck[d],
                ChainEntry(hops=(0x04E193C8, off), final_off=0x3F0),
                msg=f"deck {d}",
            )


_MINI = """\
1.0.0
DEAD 0 100 4
B0 0 C0 1
B0 0 C0 2
B0 0 D0 3
A0 8 9
B0 8 C0 1
B0 8 C0 2
B0 8 D0 3
A0 10 9


"""


class ParserTests(unittest.TestCase):
    def test_parser_with_deck_count_2(self) -> None:
        table = parse_offsets(_MINI, deck_count=2)
        self.assertIn("1.0.0", table)
        v = table["1.0.0"]
        self.assertEqual(v.deck_count, 2)
        self.assertEqual(len(v.bpm_per_deck), 2)
        self.assertEqual(
            v.master_deck,
            ChainEntry(hops=(0xDEAD, 0x0, 0x100), final_off=0x4),
        )
        self.assertEqual(
            v.bpm_per_deck[0],
            ChainEntry(hops=(0xB0, 0x0, 0xC0), final_off=0x1),
        )
        self.assertEqual(
            v.bpm_per_deck[1],
            ChainEntry(hops=(0xB0, 0x8, 0xC0), final_off=0x1),
        )

    def test_parser_skips_truncated_blocks(self) -> None:
        truncated = "1.0.0\nAA 0 0 1\n"
        table = parse_offsets(truncated)
        self.assertNotIn("1.0.0", table)


class ChainEntryTests(unittest.TestCase):
    def test_chain_entry_is_hashable(self) -> None:
        c = ChainEntry(hops=(1, 2, 3), final_off=4)
        {c}

    def test_chain_entry_is_immutable(self) -> None:
        c = ChainEntry(hops=(1, 2, 3), final_off=4)
        with self.assertRaises(Exception):
            c.final_off = 99  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
