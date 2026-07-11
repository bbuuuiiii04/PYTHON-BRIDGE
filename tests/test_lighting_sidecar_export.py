"""AWR-210 lighting-sidecar exporter — pure-seam tests (no real DB/cache).

Covers: index-build determinism, incremental skip + prune logic, sibling ANLZ
copy completeness, skip-with-reason on unreadable input, fingerprint parity
with the runtime resolver, and the never-write-outside-dest guard (Part C).
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from rb_ss_bridge_v2 import filepath_resolver, spectral_cache
from rb_ss_bridge_v2.tools import lighting_sidecar_export as sidecar


class FakeContent:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _make_anlz_set(share: Path, uuid: str) -> Path:
    """Create DAT + EXT + 2EX siblings; return the .DAT path."""
    d = share / uuid
    d.mkdir(parents=True)
    dat = d / "ANLZ0000.DAT"
    for suffix, blob in ((".DAT", b"DAT"), (".EXT", b"EXTdata"), (".2EX", b"2EX!")):
        (d / f"ANLZ0000{suffix}").write_bytes(blob)
    return dat


class SafeDestGuard(unittest.TestCase):
    def test_within_dest_ok(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "lighting_sidecar"
            got = sidecar.safe_dest(root, "anlz/42/ANLZ0000.DAT")
            self.assertEqual(
                str(got),
                os.path.join(os.path.abspath(str(root)), "anlz/42/ANLZ0000.DAT"))

    def test_escape_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "lighting_sidecar"
            for bad in ("../config/govee.env", "../../etc/passwd", "/etc/passwd"):
                with self.assertRaises(ValueError):
                    sidecar.safe_dest(root, bad)


class IndexDeterminism(unittest.TestCase):
    def test_records_sorted_and_stable(self):
        recs = [{"content_id": "30"}, {"content_id": "2"}, {"content_id": "100"}]
        built_at = {"head": "abc", "timestamp": "t"}
        idx1 = sidecar.build_index(list(recs), built_at=built_at)
        idx2 = sidecar.build_index(list(reversed(recs)), built_at=built_at)
        self.assertEqual([r["content_id"] for r in idx1["tracks"]], ["2", "30", "100"])
        self.assertEqual(idx1, idx2)
        self.assertEqual(idx1["track_count"], 3)


class SignatureAndIncremental(unittest.TestCase):
    def test_signature_and_unchanged(self):
        with TemporaryDirectory() as tmp:
            a = Path(tmp) / "ANLZ0000.DAT"
            a.write_bytes(b"x")
            dest = Path(tmp) / "d"
            dest.mkdir()
            df = dest / "copy.DAT"
            df.write_bytes(b"x")
            sig = sidecar.source_signature([a], None)
            rec = {"source_sig": sig}
            self.assertTrue(sidecar.unchanged(rec, sig, [df]))
            # dest file gone → must re-export
            self.assertFalse(sidecar.unchanged(rec, sig, [dest / "missing"]))
            # source changed → sig differs → re-export
            a.write_bytes(b"xyz")
            self.assertFalse(sidecar.unchanged(rec, sidecar.source_signature([a], None), [df]))
            # no prior record → re-export
            self.assertFalse(sidecar.unchanged(None, sig, [df]))

    def test_prune_targets(self):
        self.assertEqual(sidecar.prune_targets({"1", "2", "9"}, {"2"}), ["1", "9"])
        self.assertEqual(sidecar.prune_targets({"2"}, {"2", "3"}), [])


class FingerprintParity(unittest.TestCase):
    def test_same_symbol_as_resolver(self):
        # The resolver imports the fingerprint from spectral_cache; the tool uses
        # the same one — parity by construction, not by a parallel implementation.
        self.assertIs(spectral_cache._beatgrid_fingerprint,
                      filepath_resolver._beatgrid_fingerprint)

    def test_record_fingerprint_matches(self):
        grid = [0.0, 500.0, 1000.0, 1500.0]
        self.assertEqual(
            sidecar.spectral_cache._beatgrid_fingerprint(grid),
            spectral_cache._beatgrid_fingerprint(grid),
        )


class ExportTrack(unittest.TestCase):
    def _patches(self, tmp, *, grid, candidates_from_share=True, v4_source=None):
        share = Path(tmp) / "share"
        dat = _make_anlz_set(share, "UUID-1")
        ctx = mock.patch.multiple(
            sidecar,
            _local_anlz_path=lambda p: str(dat),
            _extract_beatgrid_from_anlz=lambda p: {"beatgrid_times_ms": list(grid)},
            _v4_source_path=lambda fp, g: v4_source,
            _read_soundswitch_id=lambda fp: "SSID-9",
            _fetch_laser_tag_beats=lambda db, cid, g, m: [4.0, 68.0],
            _hotcue_marker=lambda: "LASER",
        )
        if not candidates_from_share:
            ctx = mock.patch.multiple(
                sidecar,
                _local_anlz_path=lambda p: str(Path(tmp) / "gone" / "X.DAT"),
                _extract_beatgrid_from_anlz=lambda p: {"beatgrid_times_ms": list(grid)},
            )
        return ctx, dat

    def test_copies_all_siblings(self):
        with TemporaryDirectory() as tmp:
            v4src = Path(tmp) / "v4src.json"
            v4src.write_text('{"schema_version": 4}')
            ctx, _dat = self._patches(tmp, grid=[0.0, 500.0, 1000.0], v4_source=v4src)
            sidecar_root = Path(tmp) / "lighting_sidecar"
            with ctx:
                rec, reason, reused = sidecar._export_track(
                    db=None,
                    content=FakeContent(ID=7, AnalysisDataPath="/x", FolderPath="/song.wav",
                                        BPM=12800, Length=210, Title="T", ArtistName="A"),
                    sidecar_root=sidecar_root, old_record=None, full=True)
            self.assertIsNone(reason)
            self.assertFalse(reused)
            self.assertEqual(sorted(rec["anlz_relpaths"]), [
                "anlz/7/ANLZ0000.2EX", "anlz/7/ANLZ0000.DAT", "anlz/7/ANLZ0000.EXT"])
            for rp in rec["anlz_relpaths"]:
                self.assertTrue((sidecar_root / rp).exists(), rp)
            self.assertEqual(rec["v4_relpath"], "v4/7.json")
            self.assertTrue((sidecar_root / "v4/7.json").exists())
            self.assertEqual(rec["soundswitch_id"], "SSID-9")
            self.assertEqual(rec["laser_tag_beats"], [4.0, 68.0])
            self.assertEqual(rec["bpm"], 128.0)
            self.assertEqual(rec["duration_s"], 210.0)
            self.assertEqual(rec["beatgrid_fingerprint"],
                             spectral_cache._beatgrid_fingerprint([0.0, 500.0, 1000.0]))
            # Part C: only anlz/ + v4/ land in the sidecar — nothing else.
            for root, _dirs, files in os.walk(sidecar_root):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), sidecar_root)
                    self.assertTrue(rel.startswith(("anlz/", "v4/")), rel)

    def test_skip_no_analysis(self):
        with TemporaryDirectory() as tmp:
            rec, reason, _ = sidecar._export_track(
                db=None, content=FakeContent(ID=1, AnalysisDataPath="", FolderPath=""),
                sidecar_root=Path(tmp) / "s", old_record=None, full=True)
            self.assertIsNone(rec)
            self.assertEqual(reason, "no_analysis")
            self.assertEqual(sidecar.reason_class(reason), "expected")

    def test_skip_anlz_missing_is_unexpected(self):
        with TemporaryDirectory() as tmp:
            ctx, _ = self._patches(tmp, grid=[0.0, 1.0], candidates_from_share=False)
            with ctx:
                rec, reason, _ = sidecar._export_track(
                    db=None, content=FakeContent(ID=1, AnalysisDataPath="/x", FolderPath="/f"),
                    sidecar_root=Path(tmp) / "s", old_record=None, full=True)
            self.assertIsNone(rec)
            self.assertEqual(reason, "anlz_missing")
            self.assertEqual(sidecar.reason_class(reason), "unexpected")

    def test_skip_no_beatgrid(self):
        with TemporaryDirectory() as tmp:
            share = Path(tmp) / "share"
            dat = _make_anlz_set(share, "U")
            with mock.patch.multiple(
                sidecar,
                _local_anlz_path=lambda p: str(dat),
                _extract_beatgrid_from_anlz=lambda p: {"beatgrid_times_ms": [0.0]},
            ):
                rec, reason, _ = sidecar._export_track(
                    db=None, content=FakeContent(ID=1, AnalysisDataPath="/x", FolderPath="/f"),
                    sidecar_root=Path(tmp) / "s", old_record=None, full=True)
            self.assertIsNone(rec)
            self.assertEqual(reason, "no_beatgrid")
            self.assertEqual(sidecar.reason_class(reason), "expected")

    def test_incremental_reuse_then_refresh(self):
        with TemporaryDirectory() as tmp:
            ctx, dat = self._patches(tmp, grid=[0.0, 500.0, 1000.0])
            sidecar_root = Path(tmp) / "lighting_sidecar"
            content = FakeContent(ID=7, AnalysisDataPath="/x", FolderPath="/f.wav",
                                  BPM=12800, Length=210, Title="T", ArtistName="A")
            with ctx:
                rec, _, _ = sidecar._export_track(None, content, sidecar_root, None, full=True)
                # second run, incremental, sources unchanged → reuse, no reason
                rec2, reason2, reused2 = sidecar._export_track(
                    None, content, sidecar_root, rec, full=False)
                self.assertTrue(reused2)
                self.assertIsNone(reason2)
                self.assertEqual(rec2, rec)
                # touch a source ANLZ → sig changes → re-export (not reused)
                os.utime(dat, (dat.stat().st_atime, dat.stat().st_mtime + 5))
                _, _, reused3 = sidecar._export_track(
                    None, content, sidecar_root, rec, full=False)
                self.assertFalse(reused3)


if __name__ == "__main__":
    unittest.main()
