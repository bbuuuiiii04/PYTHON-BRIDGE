"""Deterministic replay driven through the CLI path (test D13, spec B11).

Drives ``tools.spectral_pilot.__main__.main`` in-process on synthetic fixtures —
never the live library — and proves two runs produce byte-identical manifests,
verdict, and metrics, and that the ``--watch`` set is never touched.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.spectral_pilot.__main__ import main


def _run(argv):
    with contextlib.redirect_stdout(io.StringIO()):     # the CLI prints a status line
        main(argv)

SEED = "spectral-ai-pilot-v1-790c625-2026-07-14"


def _locators(n=20):
    return [dict(
        content_id_locator=f"loc-{i}", audio_sha256=f"{i:064x}", recording_lineage_id=f"lin-{i}",
        audio_duplicate_group=f"dup-{i}", artist=f"a{i}", title=f"t{i}", duration_s=200.0 + i,
        bpm=128.0 + i * 0.7, beatgrid_fingerprint=f"bg-{i}", marker_set_fingerprint=f"ms-{i}",
        label_store_hash="lh", n_beats=512, candidate_markers=[64, 128, 256],
    ) for i in range(n)]


def _verdict_inputs():
    return dict(
        pilot_seed=SEED, created_from_head="head", input_hashes={}, setup_failures=[],
        repeatability=dict(marker_repeats=6, hardness_repeats=6, family_repeats=4,
                           marker_contradictions=0, hardness_contradictions=0, family_contradictions=0),
        workload=dict(active_seconds=3000, decisions_total=100, operator_stop_exhausting=False),
        genuine=dict(comparable_calls=30, comparable_lineages=16, correct_delta=6,
                     lineage_win_margin=4, candidate_abstentions=2, stopped=False),
        hardness=dict(comparable_calls=26, comparable_lineages=14, correct_delta=6,
                      lineage_win_margin=4, candidate_abstentions=2, stopped=False),
        family=dict(comparable_lineages=14, correct_delta=4, lineage_win_margin=4,
                    candidate_abstentions=2, decisive_noncommittal_human=2, stopped=False),
        stability=dict(genuine_central_rows=28, hardness_central_rows=28,
                       genuine_flip_gap_pp=0.0, hardness_flip_gap_pp=0.0),
        seed_pool_eligible_lineages=18,
    )


class CliReplayTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.watch = self.root / "watch"
        self.watch.mkdir()
        (self.watch / "live.txt").write_text("do not touch")
        self.loc = self.root / "locators.json"
        self.loc.write_text(json.dumps(_locators()))
        self.cfg = self.root / "cfg.json"
        self.cfg.write_text(json.dumps(
            {"lineage_states": {l["content_id_locator"]: "confirmed" for l in _locators()}}))

    def tearDown(self):
        self._tmp.cleanup()

    def _select(self, ws):
        _run(["--workspace", str(ws), "--watch", str(self.watch),
              "select", "--locators", str(self.loc), "--config", str(self.cfg), "--head", "deadbeef"])

    def _score(self, ws):
        inp = self.root / "score_in.json"
        inp.write_text(json.dumps({"verdict_inputs": _verdict_inputs(), "metrics": {"note": "synthetic"}}))
        _run(["--workspace", str(ws), "--watch", str(self.watch), "score", "--inputs", str(inp)])

    def test_select_replay_byte_identical(self):
        a, b = self.root / "a", self.root / "b"
        self._select(a)
        self._select(b)
        for name in ("card_manifest.jsonl", "lineage_manifest.jsonl"):
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)
        self.assertEqual(len((a / "card_manifest.jsonl").read_text().splitlines()), 64)

    def test_score_replay_byte_identical(self):
        a, b = self.root / "a", self.root / "b"
        self._score(a)
        self._score(b)
        for name in ("verdict.json", "metrics.json"):
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)
        self.assertEqual(json.loads((a / "verdict.json").read_text())["integrated"], "PASS")

    def test_watch_set_untouched(self):
        self._select(self.root / "a")
        self.assertEqual(sorted(p.name for p in self.watch.iterdir()), ["live.txt"])
        self.assertEqual((self.watch / "live.txt").read_text(), "do not touch")


if __name__ == "__main__":
    unittest.main()
