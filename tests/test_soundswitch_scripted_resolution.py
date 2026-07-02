"""Exact-key scripted cue resolution tests."""
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

    def test_positive_reference_uses_exact_serialized_key_not_order(self) -> None:
        resolved = resolve_scripted_reference(44, {7: "second", 44: "first"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 44)
        self.assertEqual(resolved.resolved_cue_guid, "first")

    def test_missing_exact_key_preserves_unresolved_candidate(self) -> None:
        resolved = resolve_scripted_reference(44, {7: "second"})
        self.assertEqual(resolved.reference_kind, "cue")
        self.assertEqual(resolved.resolved_stored_key, 44)
        self.assertIsNone(resolved.resolved_cue_guid)


if __name__ == "__main__":
    unittest.main()
