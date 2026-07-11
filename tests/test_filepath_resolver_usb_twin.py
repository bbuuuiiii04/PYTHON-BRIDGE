from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.filepath_resolver import (  # noqa: E402
    FilepathResolver,
    _beatgrids_match,
    _db_lookup_by_anlz,
    _is_device_export_anlz_path,
    _local_anlz_path,
    _unique_usb_twin,
    _usb_twin_prefilter,
)


_LOCAL_ID = "938c2a63-a637-4000-8000-000000000001"
_LOCAL_REL = f"PIONEER/USBANLZ/967/{_LOCAL_ID}/ANLZ0000.DAT"
_LOCAL_PATH = f"/local/share/{_LOCAL_REL}"
_USB_PATH = "/Volumes/MINK/PIONEER/USBANLZ/P018/000086A0/ANLZ0000.DAT"
_GRID = [i * 500.0 for i in range(401)]


class _FakeDB:
    def __init__(self, contents):
        self.contents = list(contents)
        self.closed = False

    def get_content(self):
        return list(self.contents)

    def get_cue(self, **_kwargs):
        return []

    def close(self):
        self.closed = True


def _content(**overrides):
    values = {
        "ID": "123",
        "Title": "Twin Track",
        "Artist": SimpleNamespace(Name="Twin Artist"),
        "FolderPath": "/music/twin.wav",
        "AnalysisDataPath": _LOCAL_REL,
        "BPM": 12800,
        "Length": 200,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _grid(times=None):
    times = list(_GRID if times is None else times)
    return {
        "beatgrid_times_ms": times,
        "beatgrid_bpms": [128.0] * len(times),
        "beatgrid_source": "test",
    }


class UsbTwinPureTests(unittest.TestCase):
    def test_device_detection_excludes_local_uuid_paths(self) -> None:
        self.assertFalse(_is_device_export_anlz_path(_LOCAL_PATH))
        self.assertTrue(_is_device_export_anlz_path(_USB_PATH))
        self.assertTrue(_is_device_export_anlz_path(
            "/PIONEER/USBANLZ/P018/000086A0/ANLZ0000.DAT"
        ))

    def test_fingerprint_exact_twin_and_mismatches(self) -> None:
        self.assertTrue(_beatgrids_match(_GRID, _GRID))
        self.assertFalse(_beatgrids_match(_GRID, _GRID[:-2]))
        shifted = list(_GRID)
        shifted[len(shifted) // 2] += 100.0
        self.assertFalse(_beatgrids_match(_GRID, shifted))

    def test_unique_match_and_ambiguous_fail_closed(self) -> None:
        first, second = object(), object()
        different = _grid([value + 100.0 for value in _GRID])
        twin, count = _unique_usb_twin(_GRID, [(first, _grid()), (second, different)])
        self.assertIs(twin[0], first)
        self.assertEqual(count, 1)

        twin, count = _unique_usb_twin(_GRID, [(second, different)])
        self.assertIsNone(twin)
        self.assertEqual(count, 0)

        twin, count = _unique_usb_twin(_GRID, [(first, _grid()), (second, _grid())])
        self.assertIsNone(twin)
        self.assertEqual(count, 2)

    def test_cross_analysis_collision_cannot_flip_identity_without_tags(self) -> None:
        # Red-team collision class: Limitless (Extended Mix) / Rude Boy
        # (Cazes Edit), both 126 BPM and 429 beats.  The old 10 ms window
        # selected the wrong song after an 11 ms cross-analysis shift.
        true_song, wrong_song = object(), object()
        foreign = [value + 11.0 for value in _GRID]
        collider = [value + 15.0 for value in _GRID]

        twin, count = _unique_usb_twin(
            foreign,
            [(true_song, _grid(_GRID)), (wrong_song, _grid(collider))],
        )

        self.assertIsNone(twin)
        self.assertEqual(count, 0)

    def test_bpm_duration_prefilter_runs_before_grid_reads(self) -> None:
        exact = _content(ID="exact")
        wrong_bpm = _content(ID="bpm", BPM=12790)
        wrong_duration = _content(ID="duration", Length=210)
        deleted = _content(ID="deleted", rb_local_deleted=1)
        self.assertEqual(
            _usb_twin_prefilter([exact, wrong_bpm, wrong_duration, deleted], _grid()),
            [exact],
        )


class UsbTwinResolverTests(unittest.TestCase):
    def _lookup(self, anlz_path: str):
        db = _FakeDB([_content()])

        def extract(path: str):
            return _grid() if path == anlz_path or path == _local_anlz_path(_LOCAL_REL) else _grid([])

        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz", side_effect=extract), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id", return_value="{SSID}"), \
             patch("rb_ss_bridge_v2.filepath_resolver._hotcue_marker", return_value="LASER"):
            result = _db_lookup_by_anlz(anlz_path)
        self.assertTrue(db.closed)
        return result

    def test_usb_twin_payload_matches_local_payload_plus_local_anlz_path(self) -> None:
        local = self._lookup(_LOCAL_PATH)
        usb = self._lookup(_USB_PATH)
        self.assertIsNotNone(local)
        self.assertIsNotNone(usb)
        local_anlz_path = usb.pop("local_anlz_path")
        self.assertEqual(usb, local)
        self.assertEqual(local_anlz_path, _local_anlz_path(_LOCAL_REL))

    def test_unresolved_usb_skips_lsof_even_with_wrong_open_click_file(self) -> None:
        resolver = FilepathResolver(queue.Queue(), Mock())
        with patch("rb_ss_bridge_v2.filepath_resolver._db_lookup_by_anlz", return_value=None), \
             patch("rb_ss_bridge_v2.filepath_resolver._lsof_audio_files", return_value=[
                 "/music/Click Sound 01 Electronic.wav"
             ]) as lsof_files, \
             patch.object(resolver, "resolve_async") as fallback, \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            resolver._resolve_anlz_worker(1, 7, _USB_PATH, "trace")

        fallback.assert_not_called()
        lsof_files.assert_not_called()
        self.assertTrue(resolver._queue.empty())
        self.assertTrue(any("action=skip-lsof" in line for line in logs.output))

    def test_local_uuid_miss_keeps_existing_lsof_fallback(self) -> None:
        resolver = FilepathResolver(queue.Queue(), Mock())
        with patch("rb_ss_bridge_v2.filepath_resolver._db_lookup_by_anlz", return_value=None), \
             patch.object(resolver, "resolve_async") as fallback:
            resolver._resolve_anlz_worker(2, 9, _LOCAL_PATH, "trace")
        fallback.assert_called_once_with(2, 9, trace_id="trace")

    def test_cross_analysis_uses_exact_pdb_tags_plus_relaxed_grid(self) -> None:
        content = _content()
        db = _FakeDB([content])
        usb_grid = _grid([value + 11.0 for value in _GRID])
        local_grid = _grid()
        device_track = {
            "track_id": 77,
            "title": "  TWIN track ",
            "artist": "Twin Artist",
            "duration_s": 200,
            "bpm": 128.0,
        }

        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz",
                   side_effect=lambda path: usb_grid if path == _USB_PATH else local_grid), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_device_pdb_track",
                   return_value=device_track), \
             patch("rb_ss_bridge_v2.filepath_resolver.os.path.isfile", return_value=True), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_soundswitch_id",
                   return_value="{SSID}"), \
             patch("rb_ss_bridge_v2.filepath_resolver._hotcue_marker", return_value="LASER"):
            result = _db_lookup_by_anlz(_USB_PATH)

        self.assertEqual(result["content_id"], "123")
        self.assertEqual(result["local_anlz_path"], _local_anlz_path(_LOCAL_REL))
        self.assertEqual(result["soundswitch_id"], "{SSID}")

    def test_pdb_tags_cannot_override_bpm_conflict(self) -> None:
        content = _content(BPM=12000)
        db = _FakeDB([content])
        device_track = {
            "track_id": 77,
            "title": "Twin Track",
            "artist": "Twin Artist",
            "duration_s": 200,
            "bpm": 128.0,
        }
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz",
                   return_value=_grid()), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_device_pdb_track",
                   return_value=device_track), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            result = _db_lookup_by_anlz(_USB_PATH)

        self.assertIsNone(result)
        self.assertTrue(any("usb-pdb-conflict" in line for line in logs.output))

    def test_missing_pdb_tags_fail_cross_analysis_closed(self) -> None:
        db = _FakeDB([_content()])
        local_shifted = _grid([value + 11.0 for value in _GRID])
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz",
                   side_effect=lambda path: _grid() if path == _USB_PATH else local_shifted), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_device_pdb_track",
                   return_value=None), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            result = _db_lookup_by_anlz(_USB_PATH)

        self.assertIsNone(result)
        self.assertTrue(any("usb-crossanalysis-unconfirmed" in line for line in logs.output))

    def test_imported_track_without_analysis_says_how_to_fix_it(self) -> None:
        content = _content(AnalysisDataPath="")
        db = _FakeDB([content])
        device_track = {
            "track_id": 77,
            "title": "Twin Track",
            "artist": "Twin Artist",
            "duration_s": 200,
            "bpm": 128.0,
        }
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch("rb_ss_bridge_v2.filepath_resolver._extract_beatgrid_from_anlz",
                   return_value=_grid()), \
             patch("rb_ss_bridge_v2.filepath_resolver._read_device_pdb_track",
                   return_value=device_track), \
             self.assertLogs("filepath_resolver", level="INFO") as logs:
            result = _db_lookup_by_anlz(_USB_PATH)

        self.assertIsNone(result)
        joined = "\n".join(logs.output)
        self.assertIn("imported-not-analyzed", joined)
        self.assertIn("finish analysis in Rekordbox", joined)


if __name__ == "__main__":
    unittest.main()
