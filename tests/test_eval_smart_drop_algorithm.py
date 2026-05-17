import contextlib
import io
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
