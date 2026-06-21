"""Tests for the export completeness verifier (no-silent-miss guarantee).

Proves the verifier (a) passes on the real Venue with declared==parsed, and
(b) FAILS LOUD when a cue would use a channel/group outside the supplied fixture
profile — i.e. a new/unknown cue can never be silently dropped.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MOD = _ROOT / "tools" / "ssfmt" / "re" / "verify_export_completeness.py"
sys.path.insert(0, str(_ROOT / "tools" / "ssfmt" / "re"))  # for parse_venue_cues
_spec = importlib.util.spec_from_file_location("verify_export_completeness", _MOD)
vc = importlib.util.module_from_spec(_spec)
sys.modules["verify_export_completeness"] = vc
_spec.loader.exec_module(vc)

VENUE = _ROOT / "tools" / "ssfmt" / "captures" / "snap" / "SoundSwitchVenues.bin"


class TestCompleteness(unittest.TestCase):
    def setUp(self):
        if not VENUE.exists():
            self.skipTest("frozen Venue snapshot not present")
        self.data = VENUE.read_bytes()

    def test_real_venue_is_complete(self):
        rep = vc.verify_venue(self.data)
        self.assertTrue(rep.ok, rep.summary())
        self.assertEqual(rep.declared_cue_count, rep.parsed_fixture_cues + rep.parsed_default_cues)

    def test_unknown_channel_fails_loud_not_silent(self):
        # Simulate a fixture profile that does NOT include CH19 (channel_id 270).
        # A cue using CH19 must be reported fatally, never silently dropped.
        restricted = tuple(c for c in vc.DEFAULT_CHANNEL_IDS if c != 270)
        rep = vc.verify_venue(self.data, channel_ids=restricted)
        self.assertFalse(rep.ok)
        self.assertTrue(any("channel_id 270" in f for f in rep.summary()["fatal"]),
                        rep.summary()["fatal"][:3])

    def test_unknown_group_fails_loud(self):
        restricted = tuple(g for g in vc.DEFAULT_FIXTURE_GROUPS if g != 0x496)
        rep = vc.verify_venue(self.data, fixture_groups=restricted)
        self.assertFalse(rep.ok)
        self.assertTrue(any("0x496" in f for f in rep.summary()["fatal"]))


if __name__ == "__main__":
    unittest.main()
