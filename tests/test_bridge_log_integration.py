"""End-to-end proof for the AWR-125 logging pipeline (spec Part E).

A real subprocess runs bridge_log.init() -> emits across every category class
and level -> shutdown(). The parent then feeds the actual JSONL bytes that
subprocess produced through bridge_view's pure layer, proving the whole pipe
(writer -> file -> reader -> lenses) on real output, not fixtures:
header/footer records, lens routing, redaction, stderr mirroring, DEBUG
suppression, symlinks, and truncated-tail tolerance.

No bridge process, no hardware, no real /tmp paths (RBSS_RUNTIME_DIR tmpdir).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2 import bridge_view  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]

_CHILD = r"""
import logging
import bridge_log

bridge_log.init()
log = logging.getLogger("bridge")
log.info("legacy info line elapsed=1:23.456")
logging.getLogger("rb_memory").debug("candidate 0xdead rejected")  # below root INFO: must not land
with bridge_log.event_scope("track_load", deck=2, trace_id="abc123"):
    bridge_log.perf(
        "laser.scene", "scene beams->strobe (drop)",
        deck=1, beat=129.0,
        data={"scene": "strobe", "api_key": "SUPERSECRET", "reason": "drop"},
    )
bridge_log.health("os2l", "connect failed err=refused")
bridge_log.emit("sys.crash", "boom", lvl=logging.ERROR, exc_info=_make_exc())
bridge_log.shutdown()
"""

_CHILD_PRELUDE = r"""
def _make_exc():
    try:
        raise ValueError("integration-test-boom")
    except ValueError as exc:
        return exc
"""


class BridgeLogEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="rbss_e2e_")
        env = dict(os.environ, RBSS_RUNTIME_DIR=cls._tmp.name)
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD_PRELUDE + _CHILD],
            cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=30,
        )
        cls.returncode = proc.returncode
        cls.stderr = proc.stderr
        cls.log_dir = Path(cls._tmp.name) / "logs"
        runs = sorted(cls.log_dir.glob("bridge-*.jsonl"))
        cls.run_file = runs[0] if runs else None
        cls.lines = (
            cls.run_file.read_text(encoding="utf-8").splitlines() if cls.run_file else []
        )
        cls.records = [bridge_view.parse_record(l) for l in cls.lines]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _find(self, cat):
        return [r for r in self.records if r and r.get("cat") == cat]

    def test_subprocess_clean_exit_and_single_run_file(self):
        self.assertEqual(self.returncode, 0, self.stderr)
        self.assertIsNotNone(self.run_file)
        self.assertEqual(len(list(self.log_dir.glob("bridge-*.jsonl"))), 1)

    def test_every_line_parses_and_header_footer_bracket_the_run(self):
        self.assertTrue(self.records, "empty stream")
        self.assertTrue(all(r is not None for r in self.records),
                        "unparseable line in real output")
        self.assertEqual(self.records[0]["cat"], "sys.boot")
        self.assertEqual(self.records[0]["data"]["schema"], 1)
        self.assertEqual(self.records[-1]["cat"], "sys.shutdown")
        self.assertIn("dropped", self.records[-1]["data"])

    def test_perf_record_full_shape_and_lens_routing(self):
        (rec,) = self._find("perf.laser.scene")
        self.assertEqual(rec["lvl"], "INFO")
        self.assertEqual(rec["deck"], 1)
        self.assertEqual(rec["beat"], 129.0)
        self.assertEqual(rec["trace"], "abc123")
        lenses = bridge_view.lens_of(rec)
        self.assertIn("performance", {l.lower() for l in lenses})
        self.assertNotIn("operator", {l.lower() for l in lenses})

    def test_secret_redacted_in_real_bytes(self):
        raw = "\n".join(self.lines)
        self.assertNotIn("SUPERSECRET", raw)
        (rec,) = self._find("perf.laser.scene")
        self.assertEqual(rec["data"]["api_key"], "<redacted>")
        self.assertEqual(rec["data"]["scene"], "strobe")

    def test_health_and_error_route_to_operator(self):
        (health_rec,) = self._find("health.os2l")
        self.assertEqual(health_rec["lvl"], "WARNING")
        self.assertIn("operator", {l.lower() for l in bridge_view.lens_of(health_rec)})
        (crash,) = self._find("sys.crash")
        self.assertEqual(crash["lvl"], "ERROR")
        self.assertIn("integration-test-boom", crash.get("exc", ""))
        self.assertIn("operator", {l.lower() for l in bridge_view.lens_of(crash)})

    def test_legacy_line_lands_with_logger_cat_and_debug_is_suppressed(self):
        (legacy,) = self._find("bridge")
        self.assertIn("legacy info line", legacy["msg"])
        self.assertFalse(self._find("rb_memory"),
                         "DEBUG below root level must never reach the file")

    def test_warning_plus_mirrored_to_stderr_info_not(self):
        self.assertIn("connect failed", self.stderr)
        self.assertIn("boom", self.stderr)
        self.assertNotIn("legacy info line", self.stderr)

    def test_current_symlink_points_at_run_file(self):
        current = self.log_dir / "current.jsonl"
        self.assertTrue(current.is_symlink())
        self.assertEqual(current.resolve(), self.run_file.resolve())

    def test_truncated_tail_is_tolerated(self):
        self.assertIsNone(bridge_view.parse_record('{"cat": "perf.x", "trunc'))
        self.assertIsNone(bridge_view.parse_record(""))


if __name__ == "__main__":
    unittest.main()
