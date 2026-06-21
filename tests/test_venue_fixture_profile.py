import importlib.util
import struct
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "ssfmt" / "re" / "parse_venue_cues.py"
SPEC = importlib.util.spec_from_file_location("parse_venue_cues", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _definition(channel_id: int, name: str) -> bytes:
    encoded = (name + "\0").encode("utf-16le")
    return struct.pack("<IIII", 2, channel_id, 1, len(encoded) // 2) + encoded


class VenueFixtureProfileTests(unittest.TestCase):
    def test_extracts_first_definition_in_dmx_order(self):
        data = bytearray(b"prefix")
        data += _definition(83, "Auto Mode")
        data += b"noise"
        data += _definition(82, "On/Off")
        data += _definition(83, "Second Mode Name")

        channels = MODULE.parse_fixture_profile_channels(bytes(data))

        self.assertEqual(
            [(row["channel_id"], row["dmx_channel"], row["name"]) for row in channels],
            [(82, 1, "On/Off"), (83, 2, "Auto Mode")],
        )

    def test_rejects_non_profile_strings(self):
        data = struct.pack("<IIII", 1, 82, 1, 7) + "On/Off\0".encode("utf-16le")
        self.assertEqual(MODULE.parse_fixture_profile_channels(data), [])


if __name__ == "__main__":
    unittest.main()
