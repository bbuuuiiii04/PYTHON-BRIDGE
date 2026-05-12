import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import analyze_anlz_energy_corpus  # noqa: E402


class _EntriesTag:
    def __init__(self, entries, mood=1):
        self.content = type("Content", (), {"entries": entries, "mood": mood})()


class _PssiEntry:
    def __init__(self, kind: int, beat: int):
        self.kind = kind
        self.beat = beat


class _BeatgridTag:
    def __init__(self, times_s):
        self._times_s = list(times_s)

    def get_times(self):
        return self._times_s


class _FakeAnlz:
    def __init__(self, tags):
        self._tags = tags

    def getall_tags(self, tag_type):
        return self._tags.get(tag_type, [])


class AnalyzeAnlzEnergyCorpusTests(unittest.TestCase):
    def test_analyze_track_from_manifest_data(self) -> None:
        track = {
            "track_filepath": "/music/test.mp3",
            "anlz_path": "/tmp/ANLZ0000.DAT",
            "waveform_values": ([10.0] * 120) + ([60.0] * 120),
            "waveform_source": "PWV3",
            "beatgrid_times_ms": [float(i * 500) for i in range(200)],
            "drop_beats": [64],
            "breakdown_beats": [32],
            "buildup_beats": [48],
            "total_ms": 100000.0,
        }
        summary, rows = analyze_anlz_energy_corpus._analyze_track(track, track_index=1, pre_beats=16, post_beats=16)
        self.assertEqual(summary["record_type"], "track")
        self.assertEqual(summary["waveform_source"], "PWV3")
        self.assertEqual(summary["track_index"], 1)
        self.assertTrue(rows)
        self.assertTrue(all("class_name" in row for row in rows))
        self.assertTrue(all("pre_mean" in row and "post_mean" in row for row in rows))

    def test_main_manifest_with_waveform_values_does_not_force_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "manifest.json"
            jsonl_out = Path(td) / "report.jsonl"
            md_out = Path(td) / "report.md"

            payload = [
                {
                    "track_filepath": "/music/a.mp3",
                    "anlz_path": "/tmp/ANLZ0000.DAT",
                    "waveform_values": ([5.0] * 150) + ([50.0] * 150),
                    "waveform_source": "PWAV",
                    "beatgrid_times_ms": [float(i * 500) for i in range(220)],
                    "drop_beats": [96],
                    "breakdown_beats": [48],
                    "buildup_beats": [80],
                    "total_ms": 110000.0,
                }
            ]
            manifest.write_text(json.dumps(payload), encoding="utf-8")

            argv = [
                "analyze_anlz_energy_corpus.py",
                "--manifest",
                str(manifest),
                "--jsonl-out",
                str(jsonl_out),
                "--report-out",
                str(md_out),
            ]
            with patch.object(sys, "argv", argv), patch(
                "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root"
            ) as mocked_extract:
                code = analyze_anlz_energy_corpus.main()
                mocked_extract.assert_not_called()
            self.assertEqual(code, 0)

            lines = [line for line in jsonl_out.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 2)
            parsed = [json.loads(line) for line in lines]
            track_rows = [row for row in parsed if row["record_type"] == "track"]
            marker_rows = [row for row in parsed if row["record_type"] == "marker"]
            self.assertEqual(len(track_rows), 1)
            self.assertEqual(track_rows[0]["waveform_source"], "PWAV")
            self.assertTrue(marker_rows)
            self.assertIn("waveform_source", marker_rows[0])
            self.assertIn("pre_mean", marker_rows[0])
            self.assertIn("post_mean", marker_rows[0])
            self.assertTrue(all(isinstance(item, dict) for item in parsed))

            report_text = md_out.read_text(encoding="utf-8")
            self.assertIn("ANLZ Energy Corpus Report", report_text)
            self.assertIn("suggested Performance Profile", report_text)

    def test_manifest_with_only_anlz_path_uses_extraction_and_preserves_manifest_fields(self) -> None:
        manifest_track = {
            "track_filepath": "/music/preserved.mp3",
            "anlz_path": "/usb/ANLZ0000.DAT",
            "beatgrid_times_ms": [1000.0, 1500.0, 2000.0, 2500.0],
            "drop_beats": [2],
            "breakdown_beats": [],
            "buildup_beats": [],
            "total_ms": 9999.0,
        }
        extracted = {
            "waveform_values": [1.0] * 64,
            "waveform_source": "PWV3",
            "beatgrid_times_ms": [0.0, 500.0],  # should be ignored
            "drop_beats": [15],  # should be ignored
            "breakdown_beats": [8],  # should be ignored
            "buildup_beats": [12],  # should be ignored
            "total_ms": 7777.0,  # should be ignored
            "errors": [],
        }
        with patch(
            "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root",
            return_value=extracted,
        ) as mocked_extract:
            normalized = analyze_anlz_energy_corpus._normalize_manifest_track(manifest_track)
        mocked_extract.assert_called_once_with("/usb/ANLZ0000.DAT")
        self.assertEqual(normalized["beatgrid_times_ms"], manifest_track["beatgrid_times_ms"])
        self.assertEqual(normalized["drop_beats"], [2])
        self.assertEqual(normalized["total_ms"], 9999.0)
        self.assertEqual(normalized["waveform_source"], "PWV3")
        self.assertEqual(len(normalized["waveform_values"]), 64)

    def test_manifest_extraction_failure_degrades_gracefully(self) -> None:
        manifest_track = {
            "track_filepath": "/music/failure.mp3",
            "anlz_path": "/missing/ANLZ0000.DAT",
            "beatgrid_times_ms": [0.0, 500.0, 1000.0],
            "drop_beats": [1],
            "breakdown_beats": [],
            "buildup_beats": [],
            "total_ms": 1500.0,
        }
        with patch(
            "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root",
            return_value={"errors": ["parse_failed:no_readable_anlz:/missing/ANLZ0000.DAT"]},
        ):
            normalized = analyze_anlz_energy_corpus._normalize_manifest_track(manifest_track)
            summary, marker_rows = analyze_anlz_energy_corpus._analyze_track(
                normalized, track_index=1, pre_beats=16, post_beats=16
            )
        self.assertIn("waveform_extraction_failed", summary["warnings"])
        self.assertEqual(marker_rows[0]["class_name"], "low_confidence")
        self.assertIn("warning", marker_rows[0])

    def test_profile_classification_unknown_when_no_markers(self) -> None:
        profile = analyze_anlz_energy_corpus._classify_profile([])
        self.assertEqual(profile, "unknown")

    def test_profile_classification_contrast_label(self) -> None:
        profile = analyze_anlz_energy_corpus._classify_profile(
            [
                {"marker_kind": "breakdown", "class_name": "high"},
                {"marker_kind": "breakdown", "class_name": "peak"},
            ]
        )
        self.assertEqual(profile, "contrast")

    def test_extract_waveform_and_grid_per_root_not_global(self) -> None:
        root1 = "/a/ANLZ0000.DAT"
        root2 = "/b/ANLZ0000.DAT"

        candidate_map = {
            root1: [Path("/a/ANLZ0000.EXT"), Path("/a/ANLZ0000.DAT")],
            root2: [Path("/b/ANLZ0000.EXT"), Path("/b/ANLZ0000.DAT")],
        }

        def fake_candidate(path):
            return candidate_map[path]

        def fake_parse(path: Path):
            base_drop = 9 if str(path).startswith("/a/") else 13
            return _FakeAnlz(
                {
                    "PWV3": [_EntriesTag([31] * 64)],
                    "PQT2": [_BeatgridTag([i * 0.5 for i in range(40)])],
                    "PSSI": [_EntriesTag([_PssiEntry(5, base_drop)], mood=1)],
                }
            )

        with patch(
            "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._candidate_anlz_paths",
            side_effect=fake_candidate,
        ), patch(
            "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._parse_anlz_file",
            side_effect=fake_parse,
        ):
            result1 = analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root(root1)
            result2 = analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root(root2)

        self.assertEqual(result1["drop_beats"], [8])
        self.assertEqual(result2["drop_beats"], [12])

    def test_main_anlz_multiple_paths_produces_per_track_records(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            jsonl_out = Path(td) / "report.jsonl"
            md_out = Path(td) / "report.md"
            path1 = "/root/one/ANLZ0000.DAT"
            path2 = "/root/two/ANLZ0000.DAT"

            def fake_extract(path):
                if path == path1:
                    return {
                        "waveform_values": [10.0] * 120,
                        "waveform_source": "PWV3",
                        "beatgrid_times_ms": [float(i * 500) for i in range(64)],
                        "drop_beats": [16],
                        "breakdown_beats": [],
                        "buildup_beats": [],
                        "total_ms": 32000.0,
                        "errors": [],
                    }
                return {
                    "waveform_values": [5.0] * 120,
                    "waveform_source": "PWAV",
                    "beatgrid_times_ms": [float(i * 500) for i in range(64)],
                    "drop_beats": [20],
                    "breakdown_beats": [],
                    "buildup_beats": [],
                    "total_ms": 32000.0,
                    "errors": [],
                }

            argv = [
                "analyze_anlz_energy_corpus.py",
                "--anlz",
                path1,
                path2,
                "--jsonl-out",
                str(jsonl_out),
                "--report-out",
                str(md_out),
            ]
            with patch.object(sys, "argv", argv), patch(
                "rb_ss_bridge_v2.tools.analyze_anlz_energy_corpus._extract_waveform_and_grid_for_root",
                side_effect=fake_extract,
            ):
                code = analyze_anlz_energy_corpus.main()
            self.assertEqual(code, 0)

            records = [
                json.loads(line)
                for line in jsonl_out.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            track_records = [row for row in records if row["record_type"] == "track"]
            marker_records = [row for row in records if row["record_type"] == "marker"]
            self.assertEqual(len(track_records), 2)
            self.assertGreaterEqual(len(marker_records), 2)
            self.assertEqual({row["anlz_path"] for row in track_records}, {path1, path2})
            self.assertTrue(all("waveform_source" in row for row in track_records))
            self.assertTrue(all("waveform_source" in row for row in marker_records))
            self.assertTrue(all("pre_mean" in row and "post_mean" in row for row in marker_records))

    def test_malformed_manifest_shows_cli_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad_manifest.json"
            path.write_text("{bad json", encoding="utf-8")
            argv = [
                "analyze_anlz_energy_corpus.py",
                "--manifest",
                str(path),
                "--jsonl-out",
                str(Path(td) / "out.jsonl"),
            ]
            with patch.object(sys, "argv", argv), self.assertRaises(SystemExit) as cm:
                analyze_anlz_energy_corpus.main()
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
