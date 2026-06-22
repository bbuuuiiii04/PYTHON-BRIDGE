"""T7d B1 — phase-trace capture integrity gate (offline oracle).

Proves the fail-closed rule: a missing footer, an unclean tracer close, or any
nonzero dropped/undrained count invalidates the ENTIRE capture run. There are no
timestamped drop ranges, so per-segment salvage is not attempted.

Loads ``validate_autoloop_capture`` from tools/ssfmt/re via importlib (its
sibling imports require that directory on sys.path), mirroring
tests/test_t7d_phase_contract.py.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_RE_DIR = Path(__file__).resolve().parents[1] / "tools" / "ssfmt" / "re"
sys.path.insert(0, str(_RE_DIR))
_MOD = _RE_DIR / "validate_autoloop_capture.py"
_spec = importlib.util.spec_from_file_location("validate_autoloop_capture", _MOD)
vac = importlib.util.module_from_spec(_spec)
sys.modules["validate_autoloop_capture"] = vac
_spec.loader.exec_module(vac)


def _footer(**over):
    base = {
        "kind": "phase_trace_footer",
        "dropped": 0,
        "undrained": 0,
        "close_ok": True,
        "timed_out": False,
        "writer_error": None,
    }
    base.update(over)
    return base


class PhaseTraceIntegrityTests(unittest.TestCase):
    def test_clean_footer_is_ok(self):
        ok, reason = vac.evaluate_phase_trace_integrity(_footer())
        self.assertTrue(ok, reason)

    def test_missing_footer_invalidates(self):
        ok, reason = vac.evaluate_phase_trace_integrity(None)
        self.assertFalse(ok)
        self.assertIn("missing", reason)

    def test_dropped_invalidates_whole_run(self):
        ok, reason = vac.evaluate_phase_trace_integrity(_footer(dropped=1))
        self.assertFalse(ok)
        self.assertIn("dropped=1", reason)

    def test_undrained_invalidates_whole_run(self):
        ok, _ = vac.evaluate_phase_trace_integrity(_footer(undrained=3))
        self.assertFalse(ok)

    def test_unclean_close_invalidates(self):
        ok, reason = vac.evaluate_phase_trace_integrity(
            _footer(close_ok=False, timed_out=True)
        )
        self.assertFalse(ok)
        self.assertIn("not clean", reason)

    def test_footer_loader_returns_last_footer(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "cap.jsonl"
            with p.open("w") as fh:
                fh.write(json.dumps({"kind": "autoloop_phase", "mono_ns": 1}) + "\n")
                fh.write(json.dumps(_footer(dropped=2)) + "\n")
            footer = vac.load_phase_trace_footer(p)
        self.assertIsNotNone(footer)
        self.assertEqual(footer["dropped"], 2)


if __name__ == "__main__":
    unittest.main()
