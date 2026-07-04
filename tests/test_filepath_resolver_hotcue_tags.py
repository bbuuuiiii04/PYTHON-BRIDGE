"""Task 2 (drop_presentation): hot-cue -> laser_tag_beats wiring in filepath_resolver.

Behavior contract: docs/architecture/drop_presentation_authority.md §Solo Source
Contracts (tier 3, hot-cue tag). Verified schema: pyrekordbox.db6.DjmdCue rows via
Rekordbox6Database.get_cue(ContentID=..., rb_local_deleted=0) — NOT a `Cues` JSON
blob (that column exists on ContentCue but is not the live per-cue table; verified
directly against the installed pyrekordbox library and the operator's live
master.db on 2026-07-04: 413 named DjmdCue rows library-wide).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.filepath_resolver import _db_lookup_by_anlz  # noqa: E402


class FakeCue:
    def __init__(self, *, comment, in_msec, content_id="123", rb_local_deleted=0):
        self.Comment = comment
        self.InMsec = in_msec
        self.ContentID = content_id
        self.rb_local_deleted = rb_local_deleted


class FakeContent:
    def __init__(self, *, id_="123", analysis_data_path="", folder_path="/tracks/a.mp3",
                 bpm=12800, length=200):
        self.ID = id_
        self.AnalysisDataPath = analysis_data_path
        self.FolderPath = folder_path
        self.BPM = bpm
        self.Length = length


class FakeDB:
    """Mimics Rekordbox6Database.get_content()/get_cue() filtering semantics."""

    def __init__(self, content_rows, cue_rows):
        self._content_rows = content_rows
        self._cue_rows = cue_rows
        self.closed = False

    def get_content(self):
        return list(self._content_rows)

    def get_cue(self, **kwargs):
        result = []
        for cue in self._cue_rows:
            if "ContentID" in kwargs and cue.ContentID != kwargs["ContentID"]:
                continue
            if "rb_local_deleted" in kwargs and cue.rb_local_deleted != kwargs["rb_local_deleted"]:
                continue
            result.append(cue)
        return result

    def close(self):
        self.closed = True


_ANLZ_PATH = "/USBANLZ/P001/deadbeef-0000-0000-0000-000000000001/ANLZ0000.DAT"
_UUID = "deadbeef-0000-0000-0000-000000000001"
_BEATGRID = {
    "beatgrid_times_ms": [0.0, 500.0, 1000.0, 1500.0, 2000.0],
    "beatgrid_bpms": [120.0, 120.0, 120.0, 120.0, 120.0],
    "beatgrid_source": "test",
}


def _lookup(cue_rows, *, content_id="123", marker="LASER"):
    content = FakeContent(id_=content_id, analysis_data_path=_UUID)
    db = FakeDB([content], cue_rows)
    with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
         patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz", return_value=dict(_BEATGRID)), \
         patch("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id", return_value=""), \
         patch("rb_ss_bridge_v2.filepath_resolver._hotcue_marker", return_value=marker):
        return _db_lookup_by_anlz(_ANLZ_PATH), db


class HotcueTagWiringTests(unittest.TestCase):
    def test_matching_marker_cues_convert_to_beat_positions_case_insensitive(self) -> None:
        cues = (
            FakeCue(comment="laser", in_msec=1000),   # exact grid point -> beat 2.0
            FakeCue(comment="Big LASER Drop", in_msec=1500),  # beat 3.0, substring match
            FakeCue(comment="DROP", in_msec=250),      # navigation cue, must never trigger
            FakeCue(comment="BUILDUP", in_msec=750),   # navigation cue, must never trigger
        )
        result, db = _lookup(cues)
        self.assertIsNotNone(result)
        self.assertEqual(sorted(result["laser_tag_beats"]), [2.0, 3.0])
        self.assertTrue(db.closed)

    def test_deleted_cues_are_excluded(self) -> None:
        cues = (
            FakeCue(comment="LASER", in_msec=1000, rb_local_deleted=1),
        )
        result, _db = _lookup(cues)
        self.assertEqual(result["laser_tag_beats"], [])

    def test_no_marker_cues_yields_empty_list(self) -> None:
        cues = (FakeCue(comment="MAIN", in_msec=0), FakeCue(comment="OUTRO", in_msec=2000))
        result, _db = _lookup(cues)
        self.assertEqual(result["laser_tag_beats"], [])

    def test_configurable_marker_is_honored(self) -> None:
        cues = (FakeCue(comment="my_custom_tag here", in_msec=500),)
        result, _db = _lookup(cues, marker="my_custom_tag")
        self.assertEqual(result["laser_tag_beats"], [1.0])

    def test_beat_conversion_matches_shared_beatgrid_math(self) -> None:
        from rb_ss_bridge_v2.beat_math import _compute_beatgrid_position
        cues = (FakeCue(comment="LASER", in_msec=1750),)
        result, _db = _lookup(cues)
        expected = _compute_beatgrid_position(1750.0, _BEATGRID["beatgrid_times_ms"])[1]
        self.assertEqual(result["laser_tag_beats"], [expected])

    def test_unusable_beatgrid_skips_conversion_without_crashing(self) -> None:
        content = FakeContent(id_="123", analysis_data_path=_UUID)
        db = FakeDB([content], (FakeCue(comment="LASER", in_msec=1000),))
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch(
                 "rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz",
                 return_value={"beatgrid_times_ms": [], "beatgrid_bpms": [], "beatgrid_source": ""},
             ), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id", return_value=""), \
             patch("rb_ss_bridge_v2.filepath_resolver._hotcue_marker", return_value="LASER"):
            result = _db_lookup_by_anlz(_ANLZ_PATH)
        self.assertIsNotNone(result)
        self.assertEqual(result["laser_tag_beats"], [])

    def test_cue_read_failure_degrades_to_no_tags_but_keeps_track_resolution(self) -> None:
        class _ExplodingDB(FakeDB):
            def get_cue(self, **kwargs):
                raise RuntimeError("db locked")

        content = FakeContent(id_="123", analysis_data_path=_UUID, folder_path="/tracks/keep.mp3")
        db = _ExplodingDB([content], ())
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz", return_value=dict(_BEATGRID)), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id", return_value=""), \
             patch("rb_ss_bridge_v2.filepath_resolver._hotcue_marker", return_value="LASER"), \
             self.assertLogs("filepath_resolver", level="WARNING") as logs:
            result = _db_lookup_by_anlz(_ANLZ_PATH)
        self.assertIsNotNone(result)
        self.assertEqual(result["filepath"], "/tracks/keep.mp3")
        self.assertEqual(result["laser_tag_beats"], [])
        self.assertEqual(len(logs.records), 1)
        self.assertIn("laser-tag-read-failed", logs.records[0].getMessage())


if __name__ == "__main__":
    unittest.main()
