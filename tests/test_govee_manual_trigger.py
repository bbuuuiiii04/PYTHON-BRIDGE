"""Pure-function tests for `govee_manual_trigger.validate_provenance` (AWR-179 D4-F1).

The manual Govee trigger's provenance gate must fail SAFE on the things that
actually matter (stale artifacts, wrong branch, missing evidence) but must NOT
gate on the phase-1 manifest's git commit differing from the current HEAD:
auto-sync moves HEAD every turn, so a commit-equality gate made the tool
permanently unusable even with fresh, correct evidence. Commit drift is now a
recorded warning, not an error.

No network, no device I/O, no real git: `repo_context` is a plain dict and the
artifact-path constants are pointed at temp files.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import govee_manual_trigger as govee_module

_NOW = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
_CAPTURE_CMD = "python3 tools/govee_capability_capture.py --live"


def _artifact(path: str, generated_at: datetime, *, source_command: str = _CAPTURE_CMD) -> dict:
    return {
        "path": path,
        "generated_at": generated_at.isoformat(),
        "source_command": source_command,
    }


class ValidateProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.summary_path = tmp / "summary.txt"
        self.devices_path = tmp / "devices.json"
        self.scenes_path = tmp / "scenes.json"
        for path in (self.summary_path, self.devices_path, self.scenes_path):
            path.write_text("{}", encoding="utf-8")
        patches = [
            mock.patch.object(govee_module, "PHASE1_SUMMARY_PATH", self.summary_path),
            mock.patch.object(govee_module, "PHASE1_DEVICES_PATH", self.devices_path),
            mock.patch.object(govee_module, "PHASE1_SCENES_PATH", self.scenes_path),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def _repo_context(self, branch: str = "main", commit: str = "a" * 40) -> dict:
        return {"branch": branch, "commit": commit}

    def _fresh_manifest(self, *, branch: str = "main", commit: str = "b" * 40,
                        include_devices: bool = True) -> dict:
        fresh = _NOW - timedelta(hours=1)
        artifacts = [_artifact(str(self.summary_path), fresh)]
        if include_devices:
            artifacts.append(_artifact(str(self.devices_path), fresh))
        artifacts.append(_artifact(str(self.scenes_path), fresh))
        return {
            "repo_branch": branch,
            "repo_commit": commit,
            "artifacts_written": artifacts,
        }

    def test_fresh_artifacts_with_commit_drift_pass_and_record_warning(self):
        # HEAD moved under a still-fresh manifest: gate must PASS, drift recorded.
        manifest = self._fresh_manifest(commit="b" * 40)
        result = govee_module.validate_provenance(manifest, self._repo_context(commit="a" * 40), _NOW)
        self.assertTrue(result["ok_for_devices"])
        self.assertIn("phase1_manifest_commit_drift", result["warnings"])
        self.assertNotIn("phase1_manifest_commit_mismatch", result["errors"])

    def test_stale_artifacts_fail(self):
        manifest = self._fresh_manifest()
        stale = _NOW - timedelta(hours=25)
        manifest["artifacts_written"] = [
            _artifact(str(self.summary_path), stale),
            _artifact(str(self.devices_path), stale),
        ]
        result = govee_module.validate_provenance(manifest, self._repo_context(), _NOW)
        self.assertFalse(result["ok_for_devices"])
        self.assertIn("devices_artifact_stale", result["errors"])

    def test_branch_mismatch_fails(self):
        manifest = self._fresh_manifest(branch="feature-x")
        result = govee_module.validate_provenance(manifest, self._repo_context(branch="main"), _NOW)
        self.assertFalse(result["ok_for_devices"])
        self.assertIn("phase1_manifest_branch_mismatch", result["errors"])

    def test_missing_devices_record_fails(self):
        manifest = self._fresh_manifest(include_devices=False)
        result = govee_module.validate_provenance(manifest, self._repo_context(), _NOW)
        self.assertFalse(result["ok_for_devices"])
        self.assertIn("devices_provenance_missing", result["errors"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
