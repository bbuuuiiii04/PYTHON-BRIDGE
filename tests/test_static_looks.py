import importlib.util
import struct
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "ssfmt" / "re" / "analyze_static_looks.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("analyze_static_looks", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


GUID = bytes.fromhex("b8ad2201b9e4c94696c898a7e8f6a5a9")


def _caf_string(value: str) -> bytes:
    encoded = (value + "\0").encode("utf-16le")
    return struct.pack("<II", 1, len(value) + 1) + encoded


def _look(name: str, value: int) -> bytes:
    data = bytearray(struct.pack("<I", 5) + _caf_string(name))
    for scalar in (0.25, 0.5):
        data += struct.pack("<II d", 1, 9, scalar)
    data += struct.pack("<IIQ", 1, 9, 0xFFFF0086)
    data += struct.pack("<II", 1, 9) + bytes(range(16))
    data += struct.pack("<IIIII", 1, 1, 0x493, 82, value * 0x01010101)
    return bytes(data)


def venue_fixture() -> bytes:
    data = bytearray(20)
    data += struct.pack("<II", 1, 4) + GUID + _caf_string("RAVE")
    data += b"prefix"
    data += GUID + struct.pack("<II", 1, 32)
    for slot in range(32):
        data += _look(f"LOOK {slot}", slot)
    return bytes(data)


class StaticLooksTests(unittest.TestCase):
    def test_parses_primary_venue_exact_32_slot_collection(self):
        data = venue_fixture()

        identity = MODULE.primary_venue_identity(data)
        collections = MODULE.parse_static_look_collections(data)
        looks = MODULE.parse_static_looks(data)

        self.assertEqual(identity["venue_guid"], GUID.hex())
        self.assertEqual(identity["venue_name"], "RAVE")
        self.assertEqual(len(collections), 1)
        self.assertEqual(len(looks), 32)
        self.assertEqual(looks[17]["slot_index"], 17)
        self.assertEqual(looks[17]["name"], "LOOK 17")
        self.assertEqual(looks[17]["groups"]["0x493"]["1"], 17)

    def test_rejects_non_primary_collection_as_active(self):
        data = bytearray(venue_fixture())
        data[28:44] = bytes(reversed(GUID))

        self.assertEqual(MODULE.parse_static_looks(bytes(data)), [])


if __name__ == "__main__":
    unittest.main()
