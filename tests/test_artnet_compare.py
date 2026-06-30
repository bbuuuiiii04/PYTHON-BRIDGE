from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TOOL = Path(__file__).resolve().parents[1] / "tools" / "artnet_compare.py"
SPEC = importlib.util.spec_from_file_location("artnet_compare", TOOL)
artnet_compare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["artnet_compare"] = artnet_compare
SPEC.loader.exec_module(artnet_compare)


class ArtNetCompareTests(unittest.TestCase):
    def test_self_check_passes_without_sockets_or_hardware(self) -> None:
        artnet_compare.run_self_check()


if __name__ == "__main__":
    unittest.main()
