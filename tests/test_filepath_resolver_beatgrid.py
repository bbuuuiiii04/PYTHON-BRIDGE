import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.filepath_resolver import _extract_beatgrid_from_anlz


class FakeTag:
    def __init__(self, times_s, bpms):
        self._times_s = times_s
        self._bpms = bpms

    def get_times(self):
        return self._times_s

    def get_bpms(self):
        return self._bpms


class FakeAnlz:
    def __init__(self, tags):
        self._tags = tags

    def getall_tags(self, tag_type):
        return self._tags.get(tag_type, [])


class BeatgridResolverTests(unittest.TestCase):
    def test_pqt2_wins_over_pqtz_when_valid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dat = Path(td) / "ANLZ0000.DAT"
            ext = Path(td) / "ANLZ0000.EXT"
            dat.touch()
            ext.touch()

            def parse_file(path):
                if Path(path).suffix == ".EXT":
                    return FakeAnlz({"PQT2": [FakeTag([2.0, 2.5], [130.0, 131.0])]})
                return FakeAnlz({"PQTZ": [FakeTag([1.0, 1.5], [120.0, 121.0])]})

            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=parse_file):
                grid = _extract_beatgrid_from_anlz(str(dat))

        self.assertEqual(grid["beatgrid_source"], "PQT2:ANLZ0000.EXT")
        self.assertEqual(grid["beatgrid_times_ms"], [2000.0, 2500.0])
        self.assertEqual(grid["beatgrid_bpms"], [130.0, 131.0])

    def test_pqtz_used_when_pqt2_is_absent_or_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dat = Path(td) / "ANLZ0000.DAT"
            ext = Path(td) / "ANLZ0000.EXT"
            dat.touch()
            ext.touch()

            def parse_file(path):
                if Path(path).suffix == ".EXT":
                    return FakeAnlz({"PQT2": [FakeTag([2.0], [130.0])]})
                return FakeAnlz({"PQTZ": [FakeTag([1.0, 1.5], [120.0, 121.0])]})

            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=parse_file):
                grid = _extract_beatgrid_from_anlz(str(dat))

        self.assertEqual(grid["beatgrid_source"], "PQTZ:ANLZ0000.DAT")
        self.assertEqual(grid["beatgrid_times_ms"], [1000.0, 1500.0])

    def test_missing_or_corrupt_anlz_returns_empty_grid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dat = Path(td) / "ANLZ0000.DAT"
            dat.touch()

            with patch("pyrekordbox.anlz.AnlzFile.parse_file", side_effect=ValueError("bad")):
                grid = _extract_beatgrid_from_anlz(str(dat))

        self.assertEqual(grid["beatgrid_times_ms"], [])
        self.assertEqual(grid["beatgrid_bpms"], [])
        self.assertEqual(grid["beatgrid_source"], "")


if __name__ == "__main__":
    unittest.main()
