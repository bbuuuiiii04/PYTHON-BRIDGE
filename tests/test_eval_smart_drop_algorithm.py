import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import eval_smart_drop_algorithm as eval_tool  # noqa: E402


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "validation"
    / "smart_drop_synthetic_corpus.yaml"
)


class EvalSmartDropAlgorithmTests(unittest.TestCase):
    def test_evaluate_runs_against_synthetic_corpus(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = eval_tool.main(["evaluate", "--corpus", str(FIXTURE)])

        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("exact  +/-1", text)
        self.assertIn("v2 (waveform + spectral)", text)
        self.assertIn("Per-feature ablation", text)
        self.assertIn("Per-track holdout", text)

    def test_scaffold_runs_without_requiring_real_anlz(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = eval_tool.main([
                "scaffold",
                "--anlz",
                "/synthetic/ANLZ0000.DAT",
                "--audio",
                "/synthetic/track.wav",
                "--title",
                "Synthetic",
                "--split",
                "training",
            ])

        self.assertEqual(code, 0)
        self.assertIn('title: "Synthetic"', out.getvalue())
        self.assertIn("drops:", out.getvalue())

    def test_tune_runs_when_analysis_extra_is_available(self) -> None:
        try:
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest("scipy not installed")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = eval_tool.main(["tune", "--corpus", str(FIXTURE)])

        self.assertEqual(code, 0)
        self.assertIn("MULTI_FEATURE_WEIGHTS_V2", out.getvalue())
        self.assertIn("condition number", out.getvalue())


class FakeDb:
    def __init__(self, contents, paths=None, cues_by_content=None):
        self._contents = contents; self._paths = paths or {}; self._cues = cues_by_content or {}
    def get_content(self):
        return self._contents
    def get_anlz_paths(self, content):
        return self._paths.get(content.Title, [f"/anlz/{content.Title}.DAT"])
    def get_cue(self, ContentID=None):
        if ContentID is None:
            return [cue for cues in self._cues.values() for cue in cues]
        cues = self._cues.get(ContentID, [])
        if isinstance(cues, Exception):
            raise cues
        return cues
    def close(self):
        pass

class FakeAnlz:
    def __init__(self, pco2=(), pcob=()):
        self._tags = {k: [SimpleNamespace(content=SimpleNamespace(entries=list(v)))]
                      for k, v in {"PCO2": pco2, "PCOB": pcob}.items()}
    def getall_tags(self, tag_type):
        return self._tags.get(tag_type, [])

def cue(ms, comment="", hot=0):
    return SimpleNamespace(time=ms, comment=comment, hot_cue=hot)

def db_cue(content_id, ms, comment="", hot=False):
    return SimpleNamespace(ContentID=content_id, InMsec=ms, Comment=comment,
                           is_hot_cue=hot, is_memory_cue=not hot)

def content(title, id=1):
    return SimpleNamespace(ID=id, Title=title, FolderPath=f"/music/{title}.wav")

def anlz_data(drops=(64,), beats=120):
    return SimpleNamespace(drop_beat_indices=list(drops),
                           waveform_context=SimpleNamespace(beatgrid_times_ms=[i * 500.0 for i in range(beats)]))

class LabelFromCuesTests(unittest.TestCase):
    def run_label(self, contents, pco2=(), pcob=(), drops=(64,), paths=None, extra=(), db_cues=None):
        cue_map = {next(c.ID for c in contents if c.Title == title): cues
                   for title, cues in (db_cues or {}).items()}
        db = FakeDb(contents, paths, cue_map); out, err = io.StringIO(), io.StringIO()
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch.object(eval_tool, "read_anlz_drops", return_value=anlz_data(drops)), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(eval_tool.main(["label-from-cues", "--exclude-scripted", "", *extra]), 0)
        return eval_tool._parse_simple_yaml_corpus(out.getvalue()), out.getvalue(), err.getvalue()

    def test_includes_track_with_drop_cue(self):
        self.assertEqual(self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP")]})[0][0]["drops"][0]["correct_beat"], 64)

    def test_excludes_track_without_drop_cue(self):
        rows, out, _err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "break")]})
        self.assertEqual((rows, out), ([], ""))

    def test_excludes_scripted_titles(self):
        with tempfile.NamedTemporaryFile("w") as tl:
            tl.write('track_id: "Track A"\naddress: /bridge/track_loaded\nvalue: 2\n')
            tl.flush()
            rows, _out, err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP")]}, extra=["--exclude-scripted", tl.name])
        self.assertEqual(rows, []); self.assertIn("excluded 1 scripted tracks", err)

    def test_prefers_drop_commented_cue_over_closer_unmarked_cue(self):
        rows, _out, _err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, ""), db_cue(1, 32500, "DROP")]})
        self.assertEqual(rows[0]["drops"][0]["correct_beat"], 65)

    def test_no_cue_in_window_emits_null_correct_beat(self):
        rows, _out, _err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 40000, "DROP")]})
        drops = rows[0]["drops"]
        self.assertIsNone(drops[0]["correct_beat"]); self.assertIn("manual fill", drops[0]["notes"])
        self.assertIsNone(drops[1]["rekordbox_beat"]); self.assertEqual(drops[1]["correct_beat"], 80)

    def test_hot_cue_with_drop_comment_counts(self):
        self.assertEqual(self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP", hot=True)]})[0][0]["drops"][0]["correct_beat"], 64)

    def test_no_anlz_path_skips_silently(self):
        rows, out, err = self.run_label([content("Track A")], paths={"Track A": []}, db_cues={"Track A": [db_cue(1, 32000, "DROP")]})
        self.assertEqual((rows, out), ([], "")); self.assertNotIn("Track A", err)

    def test_per_track_failure_is_isolated(self):
        contents = [content("Bad Track", 1), content("Good Track", 2)]
        db = FakeDb(contents, cues_by_content={1: RuntimeError("corrupt header"),
                                               2: [db_cue(2, 32000, "DROP")]})
        out, err = io.StringIO(), io.StringIO()
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=db), \
             patch.object(eval_tool, "read_anlz_drops", return_value=anlz_data((64,))), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(eval_tool.main(["label-from-cues", "--exclude-scripted", ""]), 0)
        rows = eval_tool._parse_simple_yaml_corpus(out.getvalue())
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["title"], "Good Track")
        self.assertIn("skipped Bad Track", err.getvalue())
        self.assertIn("errors (per-track exceptions): 1", err.getvalue())

    def test_holdout_titles_overrides_split(self):
        with tempfile.NamedTemporaryFile("w") as f:
            f.write("Track A\n")
            f.flush()
            rows, _out, _err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP")]}, extra=["--holdout-titles", f.name])
        self.assertEqual(rows[0]["split"], "holdout")

    def test_output_to_file_writes_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "foo.yaml")
            rows, out, _err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP")]}, extra=["--output", path])
            self.assertEqual((rows, out), ([], "")); self.assertIn('title: "Track A"', Path(path).read_text())

    def test_pcob_legacy_cue_with_no_comment_does_not_trigger_inclusion(self):
        self.assertEqual(self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "")]})[0], [])

    def test_missing_tl_playlist_file_falls_through_with_warning(self):
        rows, _out, err = self.run_label([content("Track A")], db_cues={"Track A": [db_cue(1, 32000, "DROP")]}, extra=["--exclude-scripted", "/tmp/no-such-tl.yaml"])
        self.assertEqual(rows[0]["title"], "Track A"); self.assertIn("warning: scripted playlist missing", err)


if __name__ == "__main__":
    unittest.main()
