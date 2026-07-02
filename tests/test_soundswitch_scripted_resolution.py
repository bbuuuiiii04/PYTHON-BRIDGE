"""Scripted cue-reference resolution tests (1-based refs over 0-based keys).

The serialized timeline reference space is 1-based over the file's own
0-based ``stored_key`` dictionary; reference 0 is the OFF/clear sentinel.
Capture-grounded: parity_20260701T185231Z (see
soundswitch_scripted_resolution module docstring).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_scripted_resolution import resolve_scripted_reference


class ScriptedResolutionTests(unittest.TestCase):
    def test_raw_zero_is_clear_control(self) -> None:
        resolved = resolve_scripted_reference(0, {1: "cue"})
        self.assertEqual(resolved.reference_kind, "clear_control")
        self.assertIsNone(resolved.resolved_stored_key)
        self.assertIsNone(resolved.resolved_cue_guid)

    def test_positive_reference_is_one_based_over_stored_keys(self) -> None:
        # U0 evidence: {528E8B22} ref 26 renders the key-25 cue (TURQOISE),
        # never the key-26 cue (GREEN); 100.0% dwell match under R-1.
        resolved = resolve_scripted_reference(44, {43: "correct", 44: "neighbor"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 43)
        self.assertEqual(resolved.resolved_cue_guid, "correct")

    def test_resolution_uses_stored_keys_not_dictionary_order(self) -> None:
        # Keys are a per-file permutation; only stored_key == R-1 may match.
        resolved = resolve_scripted_reference(44, {7: "second", 43: "first"})
        self.assertEqual(resolved.resolved_stored_key, 43)
        self.assertEqual(resolved.resolved_cue_guid, "first")

    def test_missing_key_preserves_unresolved_candidate(self) -> None:
        # A miss keeps the attempted key and yields no GUID (skip-hold).
        resolved = resolve_scripted_reference(44, {7: "second"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 43)
        self.assertIsNone(resolved.resolved_cue_guid)

    def test_global_offset_rules_are_rejected_by_permuted_dictionary(self) -> None:
        # {FC10FC02} events: ref 209 -> key 208 while the dictionary is a heavy
        # permutation (key != position on 214/216 rows).  Direct (R) and R+1
        # lookups must not reproduce the R-1 resolution.
        key_map = {207: "r139", 208: "coverage", 209: "hyper", 210: "hyper-copy"}
        self.assertEqual(resolve_scripted_reference(209, key_map).resolved_cue_guid,
                         "coverage")
        self.assertNotEqual(resolve_scripted_reference(210, key_map).resolved_cue_guid,
                            "coverage")
        self.assertNotEqual(resolve_scripted_reference(208, key_map).resolved_cue_guid,
                            "coverage")


if __name__ == "__main__":
    unittest.main()
