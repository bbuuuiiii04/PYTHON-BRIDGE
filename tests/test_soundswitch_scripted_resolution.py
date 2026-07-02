"""Scripted cue-reference resolution tests (exact-R over stored keys).

The serialized timeline reference resolves EXACTLY against the file's own
``stored_key`` dictionary; reference 0 is the OFF/clear sentinel.
Capture-grounded: exact-R + venue precede-association byte-proven
2026-07-02 against parity_20260701T185231Z (261/261; see
soundswitch_scripted_resolution module docstring). This supersedes the
prior ``stored_key == R - 1`` reading, which was a bridge-side
reconciliation for a since-corrected venue value-association bug rather
than a true resolution rule.
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

    def test_positive_reference_resolves_exact_stored_key(self) -> None:
        # Byte-proof (261/261): reference R resolves to stored_key == R,
        # never R - 1.
        resolved = resolve_scripted_reference(44, {43: "neighbor", 44: "correct"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 44)
        self.assertEqual(resolved.resolved_cue_guid, "correct")

    def test_resolution_uses_stored_keys_not_dictionary_order(self) -> None:
        # Keys are a per-file permutation; insertion order must not matter,
        # only stored_key == R.
        resolved = resolve_scripted_reference(44, {7: "second", 44: "first"})
        self.assertEqual(resolved.resolved_stored_key, 44)
        self.assertEqual(resolved.resolved_cue_guid, "first")

    def test_missing_key_preserves_unresolved_candidate(self) -> None:
        # A miss keeps the attempted key (R itself) and yields no GUID
        # (skip-hold).
        resolved = resolve_scripted_reference(44, {7: "second"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 44)
        self.assertIsNone(resolved.resolved_cue_guid)

    def test_global_offset_rules_are_rejected_by_permuted_dictionary(self) -> None:
        # {FC10FC02} events: ref 209 -> key 209 exactly, while the
        # dictionary is a heavy permutation (key != position on 214/216
        # rows).  Neither R-1 nor R+1 lookups may reproduce the exact-R
        # resolution.
        key_map = {207: "r139", 208: "coverage", 209: "hyper", 210: "hyper-copy"}
        self.assertEqual(resolve_scripted_reference(209, key_map).resolved_cue_guid,
                         "hyper")
        self.assertNotEqual(resolve_scripted_reference(209, key_map).resolved_cue_guid,
                            "coverage")  # would be the stale R-1 reading
        self.assertNotEqual(resolve_scripted_reference(209, key_map).resolved_cue_guid,
                            "hyper-copy")  # would be an R+1 reading


if __name__ == "__main__":
    unittest.main()
