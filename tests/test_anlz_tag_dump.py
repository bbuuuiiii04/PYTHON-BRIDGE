import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import anlz_tag_dump  # noqa: E402


class _FakeTag:
    def __init__(self, entries=None):
        self.content = type("Content", (), {"entries": entries or [31, 15, 7]})()


class _FakeGridTag:
    def get_times(self):
        return [0.0, 0.5, 1.0, 1.5]


class _FakeAnlz:
    def __init__(self):
        self.tag_types = ["PWV3", "PQT2", "UNKN"]

    def getall_tags(self, tag_type):
        if tag_type == "PWV3":
            return [_FakeTag([31, 30, 20, 10])]
        if tag_type == "PQT2":
            return [_FakeGridTag()]
        if tag_type == "UNKN":
            return [_FakeTag(["weird", object()])]
        return []


class AnlzTagDumpTests(unittest.TestCase):
    def test_dump_file_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ANLZ0000.DAT"
            path.write_bytes(b"\x00\x01")
            with patch("rb_ss_bridge_v2.tools.anlz_tag_dump._parse_anlz_file", return_value=_FakeAnlz()):
                record = anlz_tag_dump.dump_file(path, limit_samples=2)

        self.assertTrue(record["exists"])
        self.assertIn("PWV3", record["tag_counts"])
        self.assertEqual(record["tag_counts"]["PWV3"], 1)
        self.assertIn("waveform_inference", record["tags"]["PWV3"][0])
        self.assertEqual(len(record["tags"]["PWV3"][0]["entry_samples"]), 2)

    def test_unknown_tags_do_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ANLZ0000.EXT"
            path.write_bytes(b"demo")
            with patch("rb_ss_bridge_v2.tools.anlz_tag_dump._parse_anlz_file", return_value=_FakeAnlz()):
                record = anlz_tag_dump.dump_file(path, limit_samples=3)
        self.assertEqual(record["errors"], [])
        self.assertIn("UNKN", record["tags"])

    def test_main_json_out_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            anlz = Path(td) / "ANLZ0000.DAT"
            out = Path(td) / "dump.json"
            anlz.write_bytes(b"abc")
            with patch("rb_ss_bridge_v2.tools.anlz_tag_dump._parse_anlz_file", return_value=_FakeAnlz()):
                with patch.object(
                    sys,
                    "argv",
                    ["anlz_tag_dump.py", "--json", "--out", str(out), str(anlz)],
                ):
                    code = anlz_tag_dump.main()
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("files", payload)

    def test_dump_file_handles_missing_pyrekordbox_without_importing_module(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ANLZ0000.DAT"
            path.write_bytes(b"\x00\x01")
            with patch(
                "rb_ss_bridge_v2.tools.anlz_tag_dump._parse_anlz_file",
                side_effect=ModuleNotFoundError("No module named pyrekordbox"),
            ):
                record = anlz_tag_dump.dump_file(path, limit_samples=2)
        self.assertTrue(any(err.startswith("pyrekordbox_import_failed:") for err in record["errors"]))

    def test_dump_file_parse_failure_is_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ANLZ0000.DAT"
            path.write_bytes(b"\x00\x01")
            with patch(
                "rb_ss_bridge_v2.tools.anlz_tag_dump._parse_anlz_file",
                side_effect=RuntimeError("boom"),
            ):
                record = anlz_tag_dump.dump_file(path, limit_samples=2)
        self.assertTrue(any(err.startswith("parse_failed:") for err in record["errors"]))


if __name__ == "__main__":
    unittest.main()
