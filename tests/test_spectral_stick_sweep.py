"""Enumeration-core tests for tools/spectral_stick_sweep.py (AWR-183).

Pure-seam tests: ``collect_tracks`` takes the PPTH reader and isfile as
callables, so no stick, no pyrekordbox, and no audio are needed.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from spectral_stick_sweep import collect_tracks


class CollectTracksTests(unittest.TestCase):
    MOUNT = "/Volumes/USB"

    def test_maps_ppth_under_mount_and_strips_leading_slash(self):
        tracks = collect_tracks(
            ["/Volumes/USB/PIONEER/USBANLZ/P01/A/ANLZ0000.DAT"],
            lambda dat: "/Contents/Artist/Album/track.wav",
            self.MOUNT,
            lambda path: True,
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["filepath"], "/Volumes/USB/Contents/Artist/Album/track.wav")
        self.assertEqual(tracks[0]["anlz_abs"], "/Volumes/USB/PIONEER/USBANLZ/P01/A/ANLZ0000.DAT")
        self.assertEqual(tracks[0]["title"], "track.wav")

    def test_skips_unreadable_ppth(self):
        tracks = collect_tracks(
            ["/x/ANLZ0000.DAT"], lambda dat: "", self.MOUNT, lambda path: True,
        )
        self.assertEqual(tracks, [])

    def test_skips_missing_audio(self):
        tracks = collect_tracks(
            ["/x/ANLZ0000.DAT"],
            lambda dat: "/Contents/gone.wav",
            self.MOUNT,
            lambda path: False,
        )
        self.assertEqual(tracks, [])

    def test_dedupes_same_audio_first_dat_wins(self):
        tracks = collect_tracks(
            ["/x/B/ANLZ0000.DAT", "/x/A/ANLZ0000.DAT"],
            lambda dat: "/Contents/same.wav",
            self.MOUNT,
            lambda path: True,
        )
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["anlz_abs"], "/x/A/ANLZ0000.DAT")  # sorted order, first kept


if __name__ == "__main__":
    unittest.main()
