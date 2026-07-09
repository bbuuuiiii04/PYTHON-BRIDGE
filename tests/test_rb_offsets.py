"""Unit tests for the embedded offsets-macos table."""
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

    def test_named_mixer_chains(self) -> None:
        self.assertEqual(
            self.v.mixer_deck1_upfader_raw,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 0, 0x470), final_off=0x30),
        )
        self.assertEqual(
            self.v.mixer_deck2_upfader_raw,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 8, 0x470), final_off=0x30),
        )
        self.assertEqual(
            self.v.mixer_deck1_low_raw,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 0, 0x460, 0x30), final_off=0x38),
        )
        self.assertEqual(
            self.v.mixer_deck2_low_raw,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 8, 0x460, 0x30), final_off=0x38),
        )

    def test_named_cfx_chains(self) -> None:
        # AWR-173: verbatim CFX FILTER chains, RE-proven for RB 7.2.11.
        self.assertEqual(
            self.v.cfx_deck1_filter_param0,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 0, 0x480, 0, 0x1E0, 0, 0x88, 0), final_off=0xE8),
        )
        self.assertEqual(
            self.v.cfx_deck2_filter_param0,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 8, 0x480, 0, 0x1E0, 0, 0x88, 0), final_off=0xE8),
        )
        self.assertEqual(
            self.v.cfx_deck1_selected_id,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 0, 0x480, 0, 0x1E0, 0, 0x88, 0), final_off=0x70),
        )
        self.assertEqual(
            self.v.cfx_deck2_selected_id,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 8, 0x480, 0, 0x1E0, 0, 0x88, 0), final_off=0x70),
        )
        self.assertEqual(
            self.v.cfx_deck1_unit_channel,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 0, 0x480, 0, 0x1E0, 0), final_off=0xD0),
        )
        self.assertEqual(
            self.v.cfx_deck2_unit_channel,
            ChainEntry(hops=(0x04E16EE8, 0xA8, 0x458, 0, 0x2C8, 8, 0x480, 0, 0x1E0, 0), final_off=0xD0),
        )

    def test_other_versions_have_no_cfx_chains(self) -> None:
        # Feature inert by construction off 7.2.11.
        for ver in ("7.2.8", "7.2.10", "7.2.13", "7.2.14"):
            v = load_offsets_for_version(ver)
            assert v is not None
            self.assertIsNone(v.cfx_deck1_filter_param0, msg=ver)
            self.assertIsNone(v.cfx_deck2_unit_channel, msg=ver)


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
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertIsNone(v.mixer_deck2_upfader_raw)
        self.assertIsNone(v.mixer_deck1_low_raw)
        self.assertIsNone(v.mixer_deck2_low_raw)

    def test_parser_skips_truncated_blocks(self) -> None:
        truncated = "1.0.0\nAA 0 0 1\n"
        table = parse_offsets(truncated)
        self.assertNotIn("1.0.0", table)

    def test_partial_mixer_labels_fail_closed(self) -> None:
        text = _MINI + "\n"
        text = text.replace("\n\n\n", "\nMIXER_D1_UPFADER_RAW 1 2\n\n\n", 1)
        v = parse_offsets(text, deck_count=2)["1.0.0"]
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertIsNone(v.mixer_deck2_upfader_raw)
        self.assertIsNone(v.mixer_deck1_low_raw)
        self.assertIsNone(v.mixer_deck2_low_raw)

    def test_duplicate_mixer_label_fails_closed(self) -> None:
        text = _MINI.replace(
            "\n\n\n",
            "\n" + "\n".join([
                "MIXER_D1_UPFADER_RAW 1 10",
                "MIXER_D1_UPFADER_RAW 1 20",
                "MIXER_D2_UPFADER_RAW 2 10",
                "MIXER_D1_LOW_RAW 3 10",
                "MIXER_D2_LOW_RAW 4 10",
                "",
                "",
                "",
            ]),
            1,
        )
        v = parse_offsets(text, deck_count=2)["1.0.0"]
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertIsNone(v.mixer_deck2_upfader_raw)

    def test_anonymous_trailing_chain_does_not_become_authority(self) -> None:
        text = _MINI.replace("\n\n\n", "\nAA BB CC\n\n\n", 1)
        with self.assertLogs("rb_offsets", level="WARNING") as captured:
            v = parse_offsets(text, deck_count=2)["1.0.0"]
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertIn("anonymous trailing chain", "\n".join(captured.output))

    def test_unknown_labeled_trailing_line_does_not_become_authority(self) -> None:
        text = _MINI.replace("\n\n\n", "\nFILTER_D1_PARAM0 1 2\n\n\n", 1)
        with self.assertLogs("rb_offsets", level="WARNING") as captured:
            v = parse_offsets(text, deck_count=2)["1.0.0"]
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertIsNone(v.mixer_deck2_upfader_raw)
        self.assertIn("unknown optional label", "\n".join(captured.output))


_VALID_CFX = [
    "CFX_D1_FILTER_PARAM0 1 2 3",
    "CFX_D2_FILTER_PARAM0 1 2 3",
    "CFX_D1_SELECTED_ID 1 2 4",
    "CFX_D2_SELECTED_ID 1 2 4",
    "CFX_D1_UNIT_CHANNEL 1 5",
    "CFX_D2_UNIT_CHANNEL 1 5",
]
_VALID_MIXER = [
    "MIXER_D1_UPFADER_RAW 1 10",
    "MIXER_D2_UPFADER_RAW 2 10",
    "MIXER_D1_LOW_RAW 3 10",
    "MIXER_D2_LOW_RAW 4 10",
]


def _mini_with(lines: list[str]) -> str:
    return _MINI.replace("\n\n\n", "\n" + "\n".join(lines + ["", "", ""]), 1)


class CfxParserTests(unittest.TestCase):
    """AWR-173: the CFX group parses independently of the mixer group; each fails
    closed only on its OWN malformed lines."""

    def test_valid_cfx_group_parses_to_six_chains(self) -> None:
        v = parse_offsets(_mini_with(_VALID_CFX), deck_count=2)["1.0.0"]
        self.assertEqual(v.cfx_deck1_filter_param0, ChainEntry(hops=(0x1, 0x2), final_off=0x3))
        self.assertEqual(v.cfx_deck2_filter_param0, ChainEntry(hops=(0x1, 0x2), final_off=0x3))
        self.assertEqual(v.cfx_deck1_selected_id, ChainEntry(hops=(0x1, 0x2), final_off=0x4))
        self.assertEqual(v.cfx_deck2_selected_id, ChainEntry(hops=(0x1, 0x2), final_off=0x4))
        self.assertEqual(v.cfx_deck1_unit_channel, ChainEntry(hops=(0x1,), final_off=0x5))
        self.assertEqual(v.cfx_deck2_unit_channel, ChainEntry(hops=(0x1,), final_off=0x5))
        # No mixer labels present -> mixer stays None (independent groups).
        self.assertIsNone(v.mixer_deck1_upfader_raw)

    def test_partial_cfx_group_fails_closed(self) -> None:
        v = parse_offsets(_mini_with(_VALID_CFX[:3]), deck_count=2)["1.0.0"]
        self.assertIsNone(v.cfx_deck1_filter_param0)
        self.assertIsNone(v.cfx_deck1_unit_channel)

    def test_duplicate_cfx_label_fails_closed(self) -> None:
        v = parse_offsets(_mini_with(_VALID_CFX + ["CFX_D1_FILTER_PARAM0 9 9"]), deck_count=2)["1.0.0"]
        self.assertIsNone(v.cfx_deck1_filter_param0)

    def test_bad_cfx_group_does_not_disable_healthy_mixer(self) -> None:
        # Valid mixer + malformed (partial) CFX: mixer parses, CFX all None.
        v = parse_offsets(_mini_with(_VALID_MIXER + _VALID_CFX[:2]), deck_count=2)["1.0.0"]
        self.assertEqual(v.mixer_deck1_upfader_raw, ChainEntry(hops=(0x1,), final_off=0x10))
        self.assertIsNone(v.cfx_deck1_filter_param0)

    def test_bad_mixer_group_does_not_disable_healthy_cfx(self) -> None:
        # Malformed (partial) mixer + valid CFX: CFX parses, mixer all None.
        v = parse_offsets(_mini_with(_VALID_MIXER[:2] + _VALID_CFX), deck_count=2)["1.0.0"]
        self.assertIsNone(v.mixer_deck1_upfader_raw)
        self.assertEqual(v.cfx_deck1_filter_param0, ChainEntry(hops=(0x1, 0x2), final_off=0x3))

    def test_anonymous_trailing_chain_still_ignored_with_cfx(self) -> None:
        with self.assertLogs("rb_offsets", level="WARNING") as captured:
            v = parse_offsets(_mini_with(_VALID_CFX + ["AA BB CC"]), deck_count=2)["1.0.0"]
        self.assertEqual(v.cfx_deck1_filter_param0, ChainEntry(hops=(0x1, 0x2), final_off=0x3))
        self.assertIn("anonymous trailing chain", "\n".join(captured.output))


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
