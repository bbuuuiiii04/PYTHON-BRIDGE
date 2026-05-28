import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import smart_drop_telemetry_summary as summary  # noqa: E402


FIELDS = [
    "schema",
    "created_at",
    "source",
    "anlz_beat",
    "suggested_beat",
    "anlz_elapsed_ms",
    "suggested_elapsed_ms",
    "score_at_anlz",
    "score_at_suggested",
    "confidence",
    "top_candidates_json",
    "feature_breakdown_json",
    "correct_beat",
    "correct_elapsed_ms",
    "notes",
]


class SmartDropTelemetrySummaryTests(unittest.TestCase):
    def test_summary_reports_counts_histogram_sources_and_features(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "smart_drop.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerow({
                    "schema": "1",
                    "created_at": "1780000000.0",
                    "source": "v2_spectral",
                    "anlz_beat": "64",
                    "suggested_beat": "72",
                    "anlz_elapsed_ms": "32000",
                    "suggested_elapsed_ms": "36000",
                    "score_at_anlz": "0.1",
                    "score_at_suggested": "0.9",
                    "confidence": "0.8",
                    "top_candidates_json": json.dumps([
                        {"beat": 72, "score": 0.9},
                        {"beat": 80, "score": 0.7},
                    ]),
                    "feature_breakdown_json": json.dumps({
                        "silence_frame_pre": 0.8,
                        "amplitude_jump_at_c": 0.5,
                    }),
                    "correct_beat": "80",
                    "correct_elapsed_ms": "40000",
                    "notes": "",
                })
                writer.writerow({
                    "schema": "1",
                    "created_at": "1780000100.0",
                    "source": "v2_waveform",
                    "anlz_beat": "32",
                    "suggested_beat": "32",
                    "anlz_elapsed_ms": "16000",
                    "suggested_elapsed_ms": "16000",
                    "score_at_anlz": "1.0",
                    "score_at_suggested": "1.0",
                    "confidence": "0.0",
                    "top_candidates_json": json.dumps([{"beat": 32, "score": 1.0}]),
                    "feature_breakdown_json": json.dumps({"silence_frame_pre": 0.2}),
                    "correct_beat": "",
                    "correct_elapsed_ms": "",
                    "notes": "",
                })

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = summary.main(["--csv", str(path), "--since", "2026-01-01"])

        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("decisions: 2", text)
        self.assertIn("labeled: 1", text)
        self.assertIn("v2_spectral: 1 decisions, 1 labeled", text)
        self.assertIn("+8: 1", text)
        self.assertIn("+0: 1", text)
        self.assertIn("labeled_exact: 0/1", text)
        self.assertIn("mean_score_at_correct_candidate: 0.700000 (1 rows)", text)
        self.assertIn("silence_frame_pre: 0.500000", text)

    def test_missing_csv_returns_empty_summary(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = summary.main(["--csv", "/tmp/rbss-does-not-exist.csv"])

        self.assertEqual(code, 0)
        self.assertIn("decisions: 0", out.getvalue())

    def test_since_accepts_bare_date_and_iso_timestamp(self) -> None:
        self.assertIsNone(summary._parse_since(None))
        self.assertIsNone(summary._parse_since(""))
        self.assertAlmostEqual(
            summary._parse_since("2026-05-20"),
            summary._parse_since("2026-05-20T00:00:00+00:00"),
        )

    def test_since_treats_naive_datetime_as_utc(self) -> None:
        naive = summary._parse_since("2026-05-20T12:00:00")
        utc = summary._parse_since("2026-05-20T12:00:00+00:00")
        self.assertEqual(naive, utc)


if __name__ == "__main__":
    unittest.main()
